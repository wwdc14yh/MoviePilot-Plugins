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
        self._stopped = False
        self._last_cleanup = 0.0
        self._target_cache = {}
        self._ensured_dirs = set()
        self._settled_keys = set()
        self._backlog = {}

    def _log(self, msg):
        if self.logger:
            self.logger.info("[CloudDrive2Sync] " + msg)

    # ---------- 目录工具 ----------

    def _debug(self, msg):
        if getattr(self.config, "debug_logging", False):
            self._log("[详细] " + msg)

    def _walk_source(self, root):
        """遍历源目录, 返回 (文件列表, 是否完整)。

        根目录列举失败仍然抛错 (整轮失败); 子目录失败只跳过该目录
        并标记不完整 —— 例如某个 WebDAV 子目录上游异常时,
        不该让整个任务全军覆没; 不完整时本轮不做源端消失标记,
        避免把暂时看不到的文件误判为已删除。
        """
        files = []
        queue = [root]
        visited = set()
        complete = True
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            try:
                items = self.client.list_sub_files(current)
            except Cd2Error as exc:
                if current == root:
                    raise
                complete = False
                self._log("跳过无法列出的目录 %s: %s" % (current, exc))
                continue
            dirs_here = 0
            for item in items:
                if item.is_directory:
                    queue.append(item.full_path)
                    dirs_here += 1
                else:
                    files.append(item)
            self._debug("遍历 %s: %d 项 (子目录 %d)"
                        % (current, len(items), dirs_here))
        return files, complete

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
            self._log("GetCopyTasks 失败, 本轮对账跳过: " + str(exc))
            return None

    @staticmethod
    def _find_copy_task(tasks, source_path, dest_dir, target_path=None):
        if not tasks:
            return None
        parent, _ = parent_and_name(source_path)
        candidates = []
        for task in tasks:
            if int(getattr(task, "task_mode", 0) or 0) != 0:
                continue
            tdest = str(task.dest_path).rstrip("/")
            # CD2 的 destPath 多数是目标文件夹, 也可能是目标文件全路径
            if tdest == dest_dir.rstrip("/"):
                dest_rank = 0
            elif target_path and tdest == target_path.rstrip("/"):
                dest_rank = 1
            else:
                continue
            tsrc = str(task.source_path)
            if tsrc == source_path:
                candidates.append((dest_rank, task))
            elif tsrc == parent or source_path.startswith(tsrc.rstrip("/") + "/"):
                candidates.append((dest_rank + 2, task))
        if not candidates:
            return None

        def sort_key(pair):
            rank, task = pair
            active = 0 if not (task.is_completed or task.is_failed) else 1
            return (active, rank, -float(getattr(task, "start_time", 0) or 0))

        candidates.sort(key=sort_key)
        return candidates[0][1]

    def _verify_state(self, state, tasks):
        """按给定的 CD2 任务列表判定一个 copying 状态的当前结局。

        返回 (outcome, detail, matched): outcome in done/failed/pending,
        matched 是命中的 Cd2CopyTask (没有时 None)。完成判定只看
        CopyTask 状态 (Completed 且 failedFiles=0), 不查目标文件 ——
        目标会被 MoviePilot 整理移走, 缺失是正常现象。
        """
        source_path = state["source_path"]
        target_path = state["target_path"]
        target_dir, _name = parent_and_name(target_path)
        task = self._find_copy_task(tasks, source_path, target_dir,
                                    target_path=target_path)
        if task is not None:
            self._debug(
                "校验 %s: 匹配到 CD2 任务 %s -> %s [状态 %s, 已传 %d/%d, "
                "失败文件 %d]"
                % (source_path, task.source_path, task.dest_path,
                   task.status_name, task.uploaded_files, task.total_files,
                   task.failed_files)
            )
            if task.is_failed:
                detail = "; ".join(task.errors) or "CD2 复制任务失败"
                return "failed", detail, task
            if not task.is_completed:
                return "pending", task.status_name, task
            failed_files = int(getattr(task, "failed_files", 0) or 0)
            if failed_files > 0:
                detail = "; ".join(task.errors) or (
                    "CD2 任务完成但有 %d 个文件失败" % failed_files
                )
                return "failed", detail, task
            return "done", "", task
        # 任务列表里查不到: 可能已被 CD2 清理。提交超过宽限期仍无记录,
        # 按已完成处理 (提交当时已被服务端接受); 宽限期内继续等待。
        submitted = state.get("submitted_at") or state.get("first_seen_at")
        if submitted and time.time() - float(submitted) > _NO_TASK_GRACE_SECONDS:
            return "done", "CD2 任务列表已无此任务, 按提交成功视为完成", None
        return "pending", "等待 CD2 复制任务出现", None

    # ---------- 失败判定: 源/目标不存在 ----------

    def _path_exists(self, path):
        """实查路径是否存在: True/False; 查不准 (父目录都列不出) 返回
        None。列父目录看名字在不在, 文件和目录都适用。"""
        parent, name = parent_and_name(path)
        try:
            items = self.client.list_sub_files(parent)
        except Exception:
            return None
        return any(it.name == name for it in items)

    def _failure_not_exist_reason(self, state, detail):
        """判断一次远端失败是不是"源/目标不存在"导致的。

        先实查源文件、再实查目标目录, 都查不准时才看错误文本。
        返回命中的原因字符串; 不是这类失败返回空串。
        """
        if self._path_exists(state["source_path"]) is False:
            return "源文件不存在"
        target_dir, _ = parent_and_name(state["target_path"])
        if self._path_exists(target_dir) is False:
            return "目标目录不存在"
        text = (detail or "").lower()
        for kw in ("不存在", "not found", "not exist", "no such", "404"):
            if kw in text:
                return "源或目标不存在 (按错误信息判断)"
        return ""

    # ---------- 对账结果落地 ----------

    def _apply_done(self, task, state, tsum, remove_keys, matched):
        """远端已完成: 记成功, 移动模式删源, 并登记待清理的 CD2 任务。"""
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
        if matched is not None:
            # taskKey 用 CD2 返回的原始路径拼, 不做任何归一化
            remove_keys.append(
                "%s:%s" % (matched.source_path, matched.dest_path))
        if task.mode == "move":
            if self._delete_source(task, state):
                tsum.moved += 1

    def _apply_failed(self, task, state, tsum, detail, matched):
        """远端失败的落地处理。

        源/目标不存在 -> 标记跳过 (excluded), 不再重试; 其它失败 ->
        记失败, 在"失败最大重试次数"内调 RestartCopyTask 自动重启,
        超限则停在失败, 等页面手动重试。
        """
        reason = self._failure_not_exist_reason(state, detail)
        if reason:
            note = "已跳过 (%s): %s" % (reason, detail)
            self.store.mark_skipped(state["state_key"], note)
            self.store.finish_open_task(state["source_path"], "failed",
                                        error=note, task_id=task.id)
            tsum.failed += 1
            self._log("复制失败且不再重试 " + state["source_path"]
                      + ": " + note)
            return
        retries = self.store.record_failure(
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
        self._log("异步复制失败 " + state["source_path"] + ": " + detail)
        if matched is None:
            return
        if retries > int(self.config.max_retries):
            self._log("已达最大重试次数, 不再自动重启 "
                      + state["source_path"])
            return
        try:
            self.client.restart_copy_task(matched.source_path,
                                          matched.dest_path)
        except Exception as exc:
            self._log("自动重启复制任务失败 " + state["source_path"]
                      + ": " + str(exc))
            return
        self.store.mark_copying(state["state_key"])
        _parent, fname = parent_and_name(state["source_path"])
        self.store.begin_task(
            file_name=fname,
            source_path=state["source_path"],
            target_path=state["target_path"],
            size=int(state.get("size") or 0),
            task_id=task.id,
        )
        self._log("失败任务已自动重启 (第 %d 次) %s"
                  % (retries, state["source_path"]))

    def _submit_one(self, task, tsum, cand):
        """提交一个文件的复制。成功/超时返回 (row_id, state), 失败返回
        (row_id, None) 并已记失败。"""
        src = cand["src"]
        key = cand["key"]
        target_path = cand["target_path"]
        row_id = self.store.begin_task(
            file_name=src.name,
            source_path=src.full_path,
            target_path=target_path,
            size=src.size,
            task_id=task.id,
        )
        state_like = {
            "state_key": key,
            "source_path": src.full_path,
            "target_path": target_path,
            "source_file_id": src.id,
            "size": src.size,
            "check_value": src.check_value,
        }
        try:
            self._ensure_dir(cand["target_dir"])
            self.client.copy_file(
                [src.full_path], cand["target_dir"],
                conflict_policy=cand["policy"],
            )
        except Exception as exc:
            if "DEADLINE_EXCEEDED" in str(exc) or "Deadline Exceeded" in str(exc):
                # 提交超时不等于没提交: CD2 很可能已经建好任务在传了。
                # 记为 copying, 后续按 CopyTask 状态结算, 不记失败。
                self.store.upsert_copying(
                    state_key=key, task_id=task.id,
                    source_path=src.full_path, source_file_id=src.id,
                    size=src.size, check_value=src.check_value,
                    target_path=target_path,
                )
                self._log("提交复制超时 (任务可能已在 CD2 端创建, 转跨轮校验) "
                          + src.full_path)
                return row_id, state_like
            self.store.record_failure(
                state_key=key, task_id=task.id,
                source_path=src.full_path, source_file_id=src.id,
                size=src.size, check_value=src.check_value,
                target_path=target_path, error=str(exc),
            )
            self.store.finish_task(row_id, "failed", error=str(exc))
            tsum.failed += 1
            self._log("提交复制失败 " + src.full_path + ": " + str(exc))
            return row_id, None
        self.store.upsert_copying(
            state_key=key, task_id=task.id,
            source_path=src.full_path, source_file_id=src.id,
            size=src.size, check_value=src.check_value,
            target_path=target_path,
        )
        return row_id, state_like

    def _submit_candidates(self, task, tsum, candidates, in_flight, limit):
        """按并发上限提交候选: 在传数 (含往轮未完成的) 不超过 limit。

        超出部分计暂缓: 名额随轮询对账完成而腾出时补交, 或等下一轮
        扫描。完成状态一律由 poll_copy_tasks 对账, 这里提交完即返回。
        """
        idx = 0
        total = len(candidates)
        while idx < total and in_flight < limit:
            cand = candidates[idx]
            idx += 1
            _row_id, state_like = self._submit_one(task, tsum, cand)
            if state_like is not None:
                in_flight += 1
        tsum.deferred += (total - idx)

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

    # ---------- 轮询对账 (后台服务, 间隔读全局配置) ----------

    def poll_copy_tasks(self):
        """把数据库状态与 CD2 远端状态对齐 (本地必须与远端一致)。

        - 远端 Completed: 记成功 (移动模式删源), 并用 RemoveCopyTasks
          按 key 删掉这条 CD2 已完成任务
        - 远端 Failed: 源/目标不存在 -> 标记跳过; 其它 -> 记失败并
          在重试上限内 RestartCopyTask 自动重启
        - 进行中: 不处理, 等下一轮轮询
        - 数据库里的失败记录若远端其实已完成, 修正为已同步
        轮询间隔由全局配置 copy_poll_interval_seconds 控制 (宿主
        get_service 注册), 本方法只负责一轮对账。扫描轮次腾出名额后,
        有积压的任务会在对账后补一轮扫描提交。
        """
        if not self._lock.acquire(blocking=False):
            return {"skipped": True}
        try:
            tasks_by_id = {t.id: t for t in self.config.tasks}
            copying = self.store.list_states_by_status("copying")
            failed_states = self.store.list_states_by_status("failed")
            if not copying and not failed_states:
                return {}
            cd2_tasks = self._copy_tasks()
            if cd2_tasks is None:
                self._log("轮询对账跳过: GetCopyTasks 不可用")
                return {"skipped": True}
            if getattr(self.config, "debug_logging", False):
                counter = getattr(self.client, "get_all_tasks_count", None)
                if counter is not None:
                    try:
                        self._debug("GetAllTasksCount: %s" % (counter(),))
                    except Exception:
                        pass
            tsums = {}

            def _tsum(task):
                if task.id not in tsums:
                    tsums[task.id] = TaskSummary(
                        task_id=task.id, name=task.name, mode=task.mode)
                return tsums[task.id]

            remove_keys = []
            touched = set()
            timeout_secs = max(
                1, int(self.config.pending_timeout_hours)) * 3600
            now = time.time()
            for state in copying:
                task = tasks_by_id.get(state.get("task_id") or "")
                if task is None:
                    continue
                tsum = _tsum(task)
                outcome, detail, matched = self._verify_state(
                    state, cd2_tasks)
                if outcome == "done":
                    self._apply_done(task, state, tsum, remove_keys,
                                     matched)
                    touched.add(task.id)
                elif outcome == "failed":
                    self._apply_failed(task, state, tsum, detail, matched)
                    touched.add(task.id)
                else:
                    submitted = (state.get("submitted_at")
                                 or state.get("first_seen_at"))
                    if submitted and now - float(submitted) > timeout_secs:
                        self._apply_failed(
                            task, state, tsum,
                            "复制超时: 已提交 %d 小时仍未完成"
                            % (timeout_secs // 3600),
                            None,
                        )
                        touched.add(task.id)
                    else:
                        tsum.pending += 1
            # 失败记录复检: 远端其实已完成的, 修正为已同步
            for state in failed_states:
                task = tasks_by_id.get(state.get("task_id") or "")
                if task is None:
                    continue
                target_dir, _ = parent_and_name(state["target_path"])
                matched = self._find_copy_task(
                    cd2_tasks, state["source_path"], target_dir,
                    target_path=state["target_path"])
                if matched is None or not matched.is_completed:
                    continue
                if int(getattr(matched, "failed_files", 0) or 0) > 0:
                    continue
                self._apply_done(task, state, _tsum(task), remove_keys,
                                 matched)
                touched.add(task.id)
                self._log("失败项复检: CD2 任务已完成, 修正为已同步 "
                          + state["source_path"])
            if remove_keys:
                try:
                    removed = self.client.remove_copy_tasks(remove_keys)
                    self._debug("RemoveCopyTasks 清理已完成任务 %d 条"
                                % removed)
                except Exception as exc:
                    self._log("清理 CD2 已完成任务失败 (不影响同步结果): "
                              + str(exc))
            # 积压补交: 本轮有任务腾出名额且之前扫描有暂缓文件的, 补一轮
            for task in self.config.tasks:
                if (task.id in touched and self._backlog.get(task.id)
                        and task.enabled):
                    self._target_cache = {}
                    self._ensured_dirs = set()
                    try:
                        self._run_task(task)
                    except Exception as exc:
                        self._log("积压补交异常 [%s]: %s"
                                  % (task.name, exc))
            return {
                tid: {
                    "verified": t.verified, "failed": t.failed,
                    "pending": t.pending,
                }
                for tid, t in tsums.items()
            }
        finally:
            self._lock.release()

    def settle_only(self):
        """页面打开/刷新时的快速对账: 与后台轮询同一套逻辑。"""
        return self.poll_copy_tasks()

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

        self._debug(
            "任务[%s]开始: 模式=%s 源=%s 目标=%s 并发=%d 冲突策略=%s"
            % (task.name, task.mode, source_root, target_root,
               max(1, int(getattr(task, "max_concurrent_sync", 1) or 1)),
               task.conflict_policy or cfg.conflict_policy or "skip")
        )

        # 本任务并发上限: 还在同步中的 + 本轮新提交的, 不超过这个数
        limit = max(1, int(getattr(task, "max_concurrent_sync", 1) or 1))
        in_flight = int(self.store.count_states(task.id).get("copying", 0))
        candidates = []

        files, walk_complete = self._walk_source(source_root)
        tsum.scanned = len(files)
        seen_keys = set()
        base_policy = task.conflict_policy or cfg.conflict_policy or "skip"

        for src in files:
            rel = src.full_path[len(source_root):].lstrip("/")
            target_path = _join(target_root, rel)
            target_dir, _ = parent_and_name(target_path)
            key = state_key_of(task.id, src.id, src.full_path)
            seen_keys.add(key)
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

            candidates.append({
                "src": src, "key": key, "target_path": target_path,
                "target_dir": target_dir, "policy": policy,
            })

        self._submit_candidates(task, tsum, candidates, in_flight, limit)
        self._backlog[task.id] = tsum.deferred > 0
        # 本任务当前在传总数 (含往轮未完成的), 供运行摘要展示
        tsum.pending = int(
            self.store.count_states(task.id).get("copying", 0))

        if task.mode != "backup" and walk_complete:
            # 备份模式只增不减: 源端消失不标记 gone;
            # 遍历不完整 (有目录没列出来) 时也不标记, 防误判
            tsum.gone_marked = self.store.mark_missing_as_gone(
                seen_keys, task_id=task.id
            )

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

    def request_stop(self):
        """插件重初始化/停止时调用: 当前任务收尾后本轮提前结束。"""
        self._stopped = True

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
            if self._stopped:
                self._log("插件重初始化, 本轮提前结束")
                break
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
