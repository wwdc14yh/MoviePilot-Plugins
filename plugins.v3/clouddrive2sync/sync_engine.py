"""同步引擎: 提交 CD2 异步复制 -> 按 CopyTask 状态跨轮校验 -> 记录。

CD2 的 CopyFile 是异步操作: 返回 success 只代表复制任务已提交,
目标文件不会立即出现, 立即复查必然失败 (v0.1 的教训)。完成判定:

1. GetCopyTasks 里对应 CopyTask 的 status:
   Completed=已完成, Failed=已失败, 其余 (Pending/Scanning/Scanned) = 进行中;
2. 任务 Completed 后再 forceRefresh 目标目录, 做快速校验
   (优先 CD2 服务端哈希 check_value, 没有哈希退回比 size);
3. 查不到对应 CopyTask 时, 以目标文件是否出现并校验通过为准。

流程:
- 每轮先结算上一轮遗留的 copying 状态 (完成/失败/超时), 不重复提交;
- 新文件提交后在本轮内短轮询 (verify_wait_seconds), 没完成就留到下一轮,
  copying 超过 pending_timeout_hours 仍未完成才判失败重试;
- 任务运行中自动跳过本轮 (非阻塞锁)。
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


@dataclass
class SyncSummary:
    scanned: int = 0
    skipped: int = 0
    copied: int = 0
    verified: int = 0
    pending: int = 0
    failed: int = 0
    deferred: int = 0
    gone_marked: int = 0
    cleaned: dict = field(default_factory=dict)
    skipped_run: bool = False


class SyncEngine:
    """一轮同步的全部逻辑, 与宿主/传输层解耦, 可用假客户端单测。"""

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
        """BFS 递归列源目录, 返回文件列表 (目录本身不返回)。"""
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
        """确保目标目录存在, 不存在就逐级 CreateFolder。"""
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
        """快速校验: 两边都有哈希比哈希, 否则比 size。"""
        if dst is None:
            return False
        if src.check_value and dst.check_value:
            return src.check_value == dst.check_value
        return int(src.size) == int(dst.size)

    # ---------- 异步复制校验 ----------

    def _copy_tasks(self):
        """拉 CD2 复制任务列表; 客户端不支持或调用失败时返回 None。"""
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
        """在 CopyTask 列表里找与某个文件对应的任务。

        CopyTask 以 (sourcePath, destPath) 为键, 粒度可能是单文件,
        也可能是包含该文件的目录任务, 两种都认。
        """
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
        # 排序: 还在跑的任务优先 (重提后旧的失败/完成任务还留在列表里,
        # 不能让旧任务覆盖新任务的状态), 其次精确匹配, 其次开始时间最新
        def sort_key(pair):
            rank, task = pair
            active = 0 if not (task.is_completed or task.is_failed) else 1
            return (active, rank, -float(getattr(task, "start_time", 0) or 0))

        candidates.sort(key=sort_key)
        return candidates[0][1]

    def _verify_state(self, state):
        """判断一个已提交复制的文件现在是什么状态。

        返回 (outcome, detail): outcome in done / failed / pending。
        """
        source_path = state["source_path"]
        target_path = state["target_path"]
        target_dir, name = parent_and_name(target_path)
        src = Cd2File(
            id=str(state.get("source_file_id") or ""),
            name=name,
            full_path=source_path,
            size=int(state.get("size") or 0),
            check_value=str(state.get("check_value") or ""),
        )
        task = self._find_copy_task(self._copy_tasks(), source_path, target_dir)
        if task is not None:
            if task.is_failed:
                detail = "; ".join(task.errors) or "CD2 复制任务失败"
                return "failed", detail
            if not task.is_completed:
                return "pending", task.status_name
            dst = self._target_listing(target_dir, force_refresh=True).get(name)
            if self._check_ok(src, dst):
                return "done", ""
            return "failed", "CD2 任务已完成, 但目标文件缺失或校验不一致"
        dst = self._target_listing(target_dir, force_refresh=True).get(name)
        if self._check_ok(src, dst):
            return "done", ""
        return "pending", "目标文件尚未出现"

    def _poll_verify(self, state):
        """提交后在本轮内短轮询, 最多等 verify_wait_seconds。"""
        wait = max(0, int(self.config.verify_wait_seconds))
        interval = max(1, int(self.config.verify_interval_seconds))
        deadline = time.time() + wait
        while True:
            outcome, detail = self._verify_state(state)
            if outcome != "pending" or time.time() >= deadline:
                return outcome, detail
            time.sleep(min(interval, max(0.0, deadline - time.time())))

    def _settle_copying(self, summary):
        """结算遗留的 copying 状态: 完成入账, 失败记录, 超时判失败。

        本轮已结算 (done/failed) 的 key 记入 self._settled_keys,
        主流程这一轮不再重复处理它们, 避免重复计数和同轮重提。
        """
        self._settled_keys = set()
        now = time.time()
        timeout_secs = max(1, int(self.config.pending_timeout_hours)) * 3600
        for state in self.store.list_states_by_status("copying"):
            outcome, detail = self._verify_state(state)
            if outcome == "done":
                self.store.upsert_done(
                    state_key=state["state_key"],
                    source_path=state["source_path"],
                    source_file_id=state.get("source_file_id") or "",
                    size=int(state.get("size") or 0),
                    check_value=state.get("check_value") or "",
                    target_path=state["target_path"],
                )
                self.store.finish_open_task(state["source_path"], "done")
                summary.verified += 1
                self._settled_keys.add(state["state_key"])
                continue
            if outcome == "pending":
                submitted = state.get("submitted_at") or state.get("first_seen_at")
                if submitted and now - float(submitted) > timeout_secs:
                    outcome = "failed"
                    detail = "复制超时: 已提交 %d 小时仍未完成" % (
                        timeout_secs // 3600
                    )
                else:
                    summary.pending += 1
                    continue
            # failed
            self.store.record_failure(
                state_key=state["state_key"],
                source_path=state["source_path"],
                source_file_id=state.get("source_file_id") or "",
                size=int(state.get("size") or 0),
                check_value=state.get("check_value") or "",
                target_path=state["target_path"],
                error=detail,
            )
            self.store.finish_open_task(state["source_path"], "failed",
                                        error=detail)
            summary.failed += 1
            self._settled_keys.add(state["state_key"])
            self._log("异步复制失败 " + state["source_path"] + ": " + detail)

    # ---------- 主流程 ----------

    def run_once(self):
        if not self._lock.acquire(blocking=False):
            self._log("上一轮还在运行, 跳过本轮")
            return SyncSummary(skipped_run=True)
        try:
            return self._run_once_locked()
        finally:
            self._lock.release()

    def _run_once_locked(self):
        cfg = self.config
        source_root = _norm_root(cfg.source_path)
        target_root = _norm_root(cfg.target_path)
        if not source_root or not target_root:
            raise ValueError("source_path / target_path 未配置")
        self._target_cache = {}
        self._ensured_dirs = set()
        summary = SyncSummary()

        # 先结算上一轮提交、还没完成的异步复制
        self._settle_copying(summary)

        files = self._walk_source(source_root)
        summary.scanned = len(files)
        seen_keys = set()

        for src in files:
            rel = src.full_path[len(source_root):].lstrip("/")
            target_path = _join(target_root, rel)
            target_dir, _ = parent_and_name(target_path)
            key = state_key_of(src.id, src.full_path)
            seen_keys.add(key)
            if key in self._settled_keys:
                # 本轮结算阶段刚处理完, 不重复计数/重提
                continue
            state = self.store.get_state(key)

            if state and state.get("status") == "copying":
                # 已在结算阶段处理, 不重复提交
                continue

            if state and state.get("status") == "done":
                if int(state.get("size") or 0) == int(src.size) and (
                    not src.check_value
                    or not state.get("check_value")
                    or state.get("check_value") == src.check_value
                ):
                    dst = self._target_listing(target_dir).get(src.name)
                    if self._check_ok(src, dst):
                        self.store.touch_seen(key)
                        summary.skipped += 1
                        continue

            if (
                state
                and state.get("status") == "failed"
                and int(state.get("retry_count") or 0) >= int(cfg.max_retries)
                and int(state.get("size") or 0) == int(src.size)
                and state.get("check_value") == src.check_value
            ):
                summary.deferred += 1
                continue

            task_id = self.store.begin_task(
                file_name=src.name,
                source_path=src.full_path,
                target_path=target_path,
                size=src.size,
            )
            try:
                self._ensure_dir(target_dir)
                self.client.copy_file(
                    [src.full_path], target_dir,
                    conflict_policy=cfg.conflict_policy,
                )
            except Exception as exc:
                self.store.record_failure(
                    state_key=key,
                    source_path=src.full_path,
                    source_file_id=src.id,
                    size=src.size,
                    check_value=src.check_value,
                    target_path=target_path,
                    error=str(exc),
                )
                self.store.finish_task(task_id, "failed", error=str(exc))
                summary.failed += 1
                self._log("提交复制失败 " + src.full_path + ": " + str(exc))
                continue

            # CopyFile 返回成功只是任务已提交, 校验要按异步状态来
            state_like = {
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
                    source_path=src.full_path,
                    source_file_id=src.id,
                    size=src.size,
                    check_value=src.check_value,
                    target_path=target_path,
                )
                self.store.finish_task(task_id, "done")
                summary.copied += 1
            elif outcome == "failed":
                self.store.record_failure(
                    state_key=key,
                    source_path=src.full_path,
                    source_file_id=src.id,
                    size=src.size,
                    check_value=src.check_value,
                    target_path=target_path,
                    error=detail,
                )
                self.store.finish_task(task_id, "failed", error=detail)
                summary.failed += 1
                self._log("异步复制失败 " + src.full_path + ": " + detail)
            else:
                self.store.upsert_copying(
                    state_key=key,
                    source_path=src.full_path,
                    source_file_id=src.id,
                    size=src.size,
                    check_value=src.check_value,
                    target_path=target_path,
                )
                # 面板任务保持 syncing, 下一轮结算时再结掉
                summary.pending += 1

        summary.gone_marked = self.store.mark_missing_as_gone(seen_keys)

        now = time.time()
        if now - self._last_cleanup >= 86400:
            summary.cleaned = self.store.cleanup(
                history_retention_days=cfg.history_retention_days,
                failed_retention_days=cfg.failed_retention_days,
                state_tombstone_days=cfg.state_tombstone_days,
                now=now,
            )
            self._last_cleanup = now

        self._log(
            "本轮完成: 扫描 %d, 跳过 %d, 复制完成 %d, 跨轮校验完成 %d, "
            "进行中 %d, 失败 %d, 暂缓 %d, 源端消失标记 %d"
            % (
                summary.scanned,
                summary.skipped,
                summary.copied,
                summary.verified,
                summary.pending,
                summary.failed,
                summary.deferred,
                summary.gone_marked,
            )
        )
        return summary
