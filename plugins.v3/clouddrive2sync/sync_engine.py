"""同步引擎 (v0.3.0 多任务): 每个任务独立跑一轮 源->目标 处理。

任务模式:
- sync   同步: 增量复制; 源端变化重新复制; 源端消失标记 source_gone
- backup 备份: 只增不减; 源文件变化时目标保留旧版 (强制 Rename 再复制一份),
         源端消失不处理目标, 也不标记 gone
- move   移动: 复制 + CopyTask 完成确认后才 DeleteFile 删源,
         删除失败保留状态, 下一轮重试删源; 可选清理源端空目录

CD2 的 CopyFile 是异步操作: 返回 success 只代表复制任务已提交,
完成判定以官方 GetCopyTasks 的 CopyTask 状态为准 (Completed 且
failedFiles=0 即成功)。不校验目标文件: 目标文件会被 MoviePilot
整理功能移走, 缺失属正常现象, 据此判失败会误报并导致重复复制。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

try:
    from .cd2_client import Cd2Error, Cd2File, parent_and_name
    from .store import state_key_of
except ImportError:  # 直接以顶层模块加载时
    from cd2_client import Cd2Error, Cd2File, parent_and_name
    from store import state_key_of


def _norm_root(path):
    path = str(path or "").strip()
    if not path:
        return ""
    return "/" + path.strip("/")


def _join(root, rel):
    return root + "/" + rel if rel else root


# CopyTask 在任务列表里查不到时的宽限: 超过后按已完成处理
# (任务可能已被 CD2 清理; 目标文件也可能已被整理移走, 无法反查)
_NO_TASK_GRACE_SECONDS = 1800


@dataclass
class SyncSummary:
    scanned: int = 0
    skipped: int = 0
    copied: int = 0
    verified: int = 0
    pending: int = 0
    failed: int = 0
    deferred: int = 0
    moved: int = 0
    gone_marked: int = 0
    cleaned: dict = field(default_factory=dict)
    skipped_run: bool = False
    tasks: list = field(default_factory=list)


@dataclass
class TaskSummary:
    task_id: str = ""
    name: str = ""
    mode: str = "sync"
    scanned: int = 0
    skipped: int = 0
    copied: int = 0
    verified: int = 0
    pending: int = 0
    failed: int = 0
    deferred: int = 0
    moved: int = 0
    gone_marked: int = 0
    error: str = ""


class SyncEngine:
    """多任务同步引擎, 与宿主/传输层解耦, 可用假客户端单测。"""

    def __init__(self, store, client, config, logger=None):
        self.store = store
        self.client = client
        self.config = config
        self.logger = logger
        self._lock = threading.Lock()
        self._last_cleanup = 0.0
        self._target_cache = {}
        self._ensured_dirs = set()
        self._settled_keys = set()

    def _log(self, msg):
        if self.logger:
            self.logger.info("[CloudDrive2Sync] " + msg)

    # ---------- 目录工具 ----------

    def _walk_source(self, root):
        files = []
        queue = [root]
        visited = set()
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            for item in self.client.list_sub_files(current):
                if item.is_directory:
                    queue.append(item.full_path)
                else:
                    files.append(item)
        return files

    def _target_listing(self, target_dir, force_refresh=False):
        if not force_refresh and target_dir in self._target_cache:
            return self._target_cache[target_dir]
        try:
            items = self.client.list_sub_files(
                target_dir, force_refresh=force_refresh
            )
            listing = {it.name: it for it in items}
        except Cd2Error:
            listing = {}
        self._target_cache[target_dir] = listing
        return listing

    def _ensure_dir(self, target_dir):
        if target_dir in self._ensured_dirs:
            return
        try:
            self.client.list_sub_files(target_dir)
            self._ensured_dirs.add(target_dir)
            return
        except Cd2Error:
            pass
        parent, name = parent_and_name(target_dir)
        if parent != target_dir:
            self._ensure_dir(parent)
        self.client.create_folder(parent, name)
        self._ensured_dirs.add(target_dir)
        self._target_cache.pop(target_dir, None)

    @staticmethod
    def _check_ok(src, dst):
        if dst is None:
            return False
        if src.check_value and dst.check_value:
            return src.check_value == dst.check_value
        return int(src.size) == int(dst.size)

    # ---------- 异步复制校验 ----------

    def _copy_tasks(self):
        getter = getattr(self.client, "get_copy_tasks", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception as exc:
            self._log("GetCopyTasks 失败, 本轮按目标文件出现与否判断: " + str(exc))
            return None

    @staticmethod
    def _find_copy_task(tasks, source_path, dest_dir):
        if not tasks:
            return None
        parent, _ = parent_and_name(source_path)
        candidates = []
        for task in tasks:
            if int(getattr(task, "task_mode", 0) or 0) != 0:
                continue
            if str(task.dest_path).rstrip("/") != dest_dir.rstrip("/"):
                continue
            tsrc = str(task.source_path)
            if tsrc == source_path:
                candidates.append((0, task))
            elif tsrc == parent or source_path.startswith(tsrc.rstrip("/") + "/"):
                candidates.append((1, task))
        if not candidates:
            return None

        def sort_key(pair):
            rank, task = pair
            active = 0 if not (task.is_completed or task.is_failed) else 1
            return (active, rank, -float(getattr(task, "start_time", 0) or 0))

        candidates.sort(key=sort_key)
        return candidates[0][1]

    def _verify_state(self, state):
        """返回 (outcome, detail): outcome in done / failed / pending。

        完成判定以 CD2 官方 CopyTask 状态为准: Completed 且
        failedFiles=0 即成功, 不查目标文件 (目标会被 MoviePilot
        整理移走, 缺失是正常现象)。
        """
        source_path = state["source_path"]
        target_path = state["target_path"]
        target_dir, name = parent_and_name(target_path)
        tasks = self._copy_tasks()
        task = self._find_copy_task(tasks, source_path, target_dir)
        if task is not None:
            if task.is_failed:
                detail = "; ".join(task.errors) or "CD2 复制任务失败"
                return "failed", detail
            if not task.is_completed:
                return "pending", task.status_name
            failed_files = int(getattr(task, "failed_files", 0) or 0)
            if failed_files > 0:
                detail = "; ".join(task.errors) or (
                    "CD2 任务完成但有 %d 个文件失败" % failed_files
                )
                return "failed", detail
            return "done", ""
        if tasks is None:
            # GetCopyTasks 不可用 (旧客户端) 才退回目标出现判断
            src = Cd2File(
                id=str(state.get("source_file_id") or ""),
                name=name,
                full_path=source_path,
                size=int(state.get("size") or 0),
                check_value=str(state.get("check_value") or ""),
            )
            dst = self._target_listing(target_dir, force_refresh=True).get(name)
            if self._check_ok(src, dst):
                return "done", ""
            return "pending", "目标文件尚未出现"
        # 任务列表里查不到: 可能已被 CD2 清理。提交超过宽限期仍无记录,
        # 按已完成处理 (提交当时已被服务端接受); 宽限期内继续等待。
        submitted = state.get("submitted_at") or state.get("first_seen_at")
        if submitted and time.time() - float(submitted) > _NO_TASK_GRACE_SECONDS:
            return "done", "CD2 任务列表已无此任务, 按提交成功视为完成"
        return "pending", "等待 CD2 复制任务出现"

    def _poll_verify(self, state):
        wait = max(0, int(self.config.verify_wait_seconds))
        interval = max(1, int(self.config.verify_interval_seconds))
        deadline = time.time() + wait
        while True:
            outcome, detail = self._verify_state(state)
            if outcome != "pending" or time.time() >= deadline:
                return outcome, detail
            time.sleep(min(interval, max(0.0, deadline - time.time())))

    # ---------- 移动模式: 校验后删源 ----------

    def _delete_source(self, task, state):
        """移动模式在目标校验通过后删源文件, 成功后清掉状态行。

        返回 True 表示源已删除 (或本来就不存在)。
        """
        source_path = state["source_path"]
        try:
            self.client.delete_file(source_path)
        except Exception as exc:
            self._log("移动模式删源失败 (下轮重试) " + source_path + ": " + str(exc))
            return False
        self.store.delete_state(state["state_key"])
        if task.delete_empty_dirs:
            self._cleanup_empty_dirs(task, source_path)
        return True

    def _cleanup_empty_dirs(self, task, file_path):
        """从文件父目录向上清理空目录, 不动任务源根目录本身。"""
        source_root = _norm_root(task.source_path)
        parent, _ = parent_and_name(file_path)
        while parent and parent != source_root and parent != "/":
            try:
                items = self.client.list_sub_files(parent)
            except Exception:
                return
            if items:
                return
            try:
                self.client.delete_file(parent)
            except Exception:
                return
            parent, _ = parent_and_name(parent)

    # ---------- 单个任务 ----------

    def _settle_copying(self, task, tsum):
        self._settled_keys = set()
        now = time.time()
        timeout_secs = max(1, int(self.config.pending_timeout_hours)) * 3600
        for state in self.store.list_states_by_status("copying",
                                                      task_id=task.id):
            outcome, detail = self._verify_state(state)
            if outcome == "done":
                self.store.upsert_done(
                    state_key=state["state_key"],
                    task_id=task.id,
                    source_path=state["source_path"],
                    source_file_id=state.get("source_file_id") or "",
                    size=int(state.get("size") or 0),
                    check_value=state.get("check_value") or "",
                    target_path=state["target_path"],
                )
                self.store.finish_open_task(state["source_path"], "done",
                                            task_id=task.id)
                tsum.verified += 1
                self._settled_keys.add(state["state_key"])
                if task.mode == "move":
                    if self._delete_source(task, state):
                        tsum.moved += 1
                continue
            if outcome == "pending":
                submitted = state.get("submitted_at") or state.get("first_seen_at")
                if submitted and now - float(submitted) > timeout_secs:
                    outcome = "failed"
                    detail = "复制超时: 已提交 %d 小时仍未完成" % (
                        timeout_secs // 3600
                    )
                else:
                    tsum.pending += 1
                    continue
            self.store.record_failure(
                state_key=state["state_key"],
                task_id=task.id,
                source_path=state["source_path"],
                source_file_id=state.get("source_file_id") or "",
                size=int(state.get("size") or 0),
                check_value=state.get("check_value") or "",
                target_path=state["target_path"],
                error=detail,
            )
            self.store.finish_open_task(state["source_path"], "failed",
                                        error=detail, task_id=task.id)
            tsum.failed += 1
            self._settled_keys.add(state["state_key"])
            self._log("异步复制失败 " + state["source_path"] + ": " + detail)

    def _recheck_failed(self, task, tsum):
        """一轮结束后自动复检失败项: 以 CopyTask 状态为准。

        任务其实已完成 (Completed 且 failedFiles=0) 的, 把状态修正为
        已同步 —— 典型是目标文件被 MoviePilot 整理移走后被旧逻辑
        误判的失败, 以及重试次数已耗尽、本来不会再被处理的项目。
        """
        tasks = self._copy_tasks()
        if tasks is None:
            return
        for state in self.store.list_states_by_status("failed",
                                                      task_id=task.id):
            target_dir, _ = parent_and_name(state["target_path"])
            ct = self._find_copy_task(tasks, state["source_path"], target_dir)
            if ct is None or not ct.is_completed:
                continue
            if int(getattr(ct, "failed_files", 0) or 0) > 0:
                continue
            self.store.upsert_done(
                state_key=state["state_key"],
                task_id=task.id,
                source_path=state["source_path"],
                source_file_id=state.get("source_file_id") or "",
                size=int(state.get("size") or 0),
                check_value=state.get("check_value") or "",
                target_path=state["target_path"],
            )
            self.store.finish_open_task(state["source_path"], "done",
                                        task_id=task.id)
            tsum.verified += 1
            self._log("失败项复检: CD2 任务已完成, 修正为已同步 "
                      + state["source_path"])

    def _run_task(self, task):
        cfg = self.config
        tsum = TaskSummary(task_id=task.id, name=task.name, mode=task.mode)
        source_root = _norm_root(task.source_path)
        target_root = _norm_root(task.target_path)
        if not source_root or not target_root:
            tsum.error = "源目录 / 目标目录未配置"
            return tsum
        self._target_cache = {}
        self._ensured_dirs = set()

        self._settle_copying(task, tsum)

        files = self._walk_source(source_root)
        tsum.scanned = len(files)
        seen_keys = set()
        base_policy = task.conflict_policy or cfg.conflict_policy or "skip"

        for src in files:
            rel = src.full_path[len(source_root):].lstrip("/")
            target_path = _join(target_root, rel)
            target_dir, _ = parent_and_name(target_path)
            key = state_key_of(task.id, src.id, src.full_path)
            seen_keys.add(key)
            if key in self._settled_keys:
                continue
            state = self.store.get_state(key)

            if state and state.get("status") == "copying":
                continue

            if state and state.get("status") == "excluded":
                # 用户在页面上手动排除的文件, 不再同步
                tsum.skipped += 1
                continue

            unchanged = (
                state
                and state.get("status") == "done"
                and int(state.get("size") or 0) == int(src.size)
                and (
                    not src.check_value
                    or not state.get("check_value")
                    or state.get("check_value") == src.check_value
                )
            )
            if unchanged:
                # 已同步且源未变化: 直接跳过, 不查目标文件 ——
                # 目标可能已被 MoviePilot 整理移走, 查不到不等于没同步,
                # 据此重传会陷入 "复制 -> 被移走 -> 再复制" 的死循环。
                if task.mode == "move":
                    # 目标早已就位但上次删源失败: 只补删源, 不重新复制
                    state_like = dict(state)
                    state_like["state_key"] = key
                    if self._delete_source(task, state_like):
                        tsum.moved += 1
                    continue
                self.store.touch_seen(key)
                tsum.skipped += 1
                continue

            if (
                state
                and state.get("status") == "failed"
                and int(state.get("retry_count") or 0) >= int(cfg.max_retries)
                and int(state.get("size") or 0) == int(src.size)
                and state.get("check_value") == src.check_value
            ):
                tsum.deferred += 1
                continue

            # 备份模式: 已备份过的文件发生变化时, 目标保留旧版,
            # 新版用 Rename 策略复制 (CD2 自动改名), 不覆盖旧备份
            policy = base_policy
            if task.mode == "backup" and state and state.get("status") == "done":
                policy = "rename"

            row_id = self.store.begin_task(
                file_name=src.name,
                source_path=src.full_path,
                target_path=target_path,
                size=src.size,
                task_id=task.id,
            )
            try:
                self._ensure_dir(target_dir)
                self.client.copy_file(
                    [src.full_path], target_dir, conflict_policy=policy
                )
            except Exception as exc:
                if "DEADLINE_EXCEEDED" in str(exc) or "Deadline Exceeded" in str(exc):
                    # 提交超时不等于没提交: CD2 很可能已经建好任务在传了。
                    # 记为 copying, 后续轮次按 CopyTask 状态结算,
                    # 不记失败、不重复提交。
                    self.store.upsert_copying(
                        state_key=key,
                        task_id=task.id,
                        source_path=src.full_path,
                        source_file_id=src.id,
                        size=src.size,
                        check_value=src.check_value,
                        target_path=target_path,
                    )
                    tsum.pending += 1
                    self._log(
                        "提交复制超时 (任务可能已在 CD2 端创建, 转跨轮校验) "
                        + src.full_path
                    )
                    continue
                self.store.record_failure(
                    state_key=key,
                    task_id=task.id,
                    source_path=src.full_path,
                    source_file_id=src.id,
                    size=src.size,
                    check_value=src.check_value,
                    target_path=target_path,
                    error=str(exc),
                )
                self.store.finish_task(row_id, "failed", error=str(exc))
                tsum.failed += 1
                self._log("提交复制失败 " + src.full_path + ": " + str(exc))
                continue

            state_like = {
                "state_key": key,
                "source_path": src.full_path,
                "target_path": target_path,
                "source_file_id": src.id,
                "size": src.size,
                "check_value": src.check_value,
            }
            outcome, detail = self._poll_verify(state_like)
            if outcome == "done":
                self.store.upsert_done(
                    state_key=key,
                    task_id=task.id,
                    source_path=src.full_path,
                    source_file_id=src.id,
                    size=src.size,
                    check_value=src.check_value,
                    target_path=target_path,
                )
                self.store.finish_task(row_id, "done")
                tsum.copied += 1
                if task.mode == "move":
                    if self._delete_source(task, state_like):
                        tsum.moved += 1
            elif outcome == "failed":
                self.store.record_failure(
                    state_key=key,
                    task_id=task.id,
                    source_path=src.full_path,
                    source_file_id=src.id,
                    size=src.size,
                    check_value=src.check_value,
                    target_path=target_path,
                    error=detail,
                )
                self.store.finish_task(row_id, "failed", error=detail)
                tsum.failed += 1
                self._log("异步复制失败 " + src.full_path + ": " + detail)
            else:
                self.store.upsert_copying(
                    state_key=key,
                    task_id=task.id,
                    source_path=src.full_path,
                    source_file_id=src.id,
                    size=src.size,
                    check_value=src.check_value,
                    target_path=target_path,
                )
                tsum.pending += 1

        if task.mode != "backup":
            # 备份模式只增不减: 源端消失不标记 gone
            tsum.gone_marked = self.store.mark_missing_as_gone(
                seen_keys, task_id=task.id
            )

        self._recheck_failed(task, tsum)

        self._log(
            "任务[%s|%s]完成: 扫描 %d, 跳过 %d, 复制完成 %d, 跨轮校验 %d, "
            "移动删源 %d, 进行中 %d, 失败 %d, 暂缓 %d, 源端消失 %d"
            % (
                task.name, task.mode, tsum.scanned, tsum.skipped, tsum.copied,
                tsum.verified, tsum.moved, tsum.pending, tsum.failed,
                tsum.deferred, tsum.gone_marked,
            )
        )
        return tsum

    # ---------- 主流程 ----------

    def run_once(self, task_id=None):
        if not self._lock.acquire(blocking=False):
            self._log("上一轮还在运行, 跳过本轮")
            return SyncSummary(skipped_run=True)
        try:
            return self._run_all_locked(task_id)
        finally:
            self._lock.release()

    def _run_all_locked(self, task_id=None):
        summary = SyncSummary()
        tasks = [
            t for t in self.config.tasks
            if t.enabled and (task_id is None or t.id == task_id)
        ]
        if not tasks:
            summary.skipped_run = True
            return summary
        for task in tasks:
            try:
                tsum = self._run_task(task)
            except Exception as exc:
                tsum = TaskSummary(task_id=task.id, name=task.name,
                                   mode=task.mode, error=str(exc))
                self._log("任务[%s]运行异常: %s" % (task.name, exc))
            summary.tasks.append(tsum.__dict__)
            for fname in (
                "scanned", "skipped", "copied", "verified", "pending",
                "failed", "deferred", "moved", "gone_marked",
            ):
                setattr(summary, fname,
                        getattr(summary, fname) + getattr(tsum, fname))
            if tsum.error:
                summary.failed += 1

        now = time.time()
        if now - self._last_cleanup >= 86400:
            cfg = self.config
            summary.cleaned = self.store.cleanup(
                history_retention_days=cfg.history_retention_days,
                failed_retention_days=cfg.failed_retention_days,
                state_tombstone_days=cfg.state_tombstone_days,
                now=now,
            )
            self._last_cleanup = now
        return summary
