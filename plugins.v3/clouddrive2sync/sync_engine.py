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


# CopyTask 在任务列表里查不到时的宽限 (v0.7.0 需求 1): 提交后任务
# 一般秒级就会出现在 GetCopyTasks 里, 超过宽限仍查不到, 视为该任务
# 已不存在 -> 删除同步项, 下次扫描重新提交。只作用于 copying 状态。
_NO_TASK_GRACE_SECONDS = 600

# GetCopyTasks 单轮轮询内的重试次数 (v0.7.0 需求 2)
_POLL_FETCH_ATTEMPTS = 3
# GetCopyTasks 连续失败多少个轮询周期后, 按库存路径删除双侧记录
_POLL_ERROR_DELETE_THRESHOLD = 3
# 轮询补齐时提前扫描的最小间隔 (秒): 队列空但有名额时才触发,
# 避免每 10 秒轮询都全量遍历源目录 (v0.7.0 需求 3)
_EARLY_SCAN_MIN_INTERVAL = 300
# CD2 任务里已有文件失败但任务未结束时, 连续多少个轮询周期
# uploaded_bytes/uploaded_files 无进展就按失败处理 (v0.7.0 需求 4,
# 两京十五日 S01E05 那种 "已扫描但文件已失败" 的情况)
_NO_PROGRESS_POLLS = 2


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
        # 每任务的内存待提交队列: 扫描时因并发上限暂缓的候选,
        # 轮询对账腾出名额后直接从队列补交, 不必等下一轮扫描
        self._pending_queue = {}
        # 每任务最近一次扫描时间 (轮询提前扫描的节流依据)
        self._last_scan_at = {}
        # GetCopyTasks 连续失败状态 (内存, 经 /status 的 poll_error
        # 给前端显示): 连续失败次数 / 最近错误文本 / 最近失败时间
        self._poll_error_count = 0
        self._poll_error_text = ""
        self._poll_error_at = 0.0
        # "任务未结束但已有文件失败" 的无进展跟踪:
        # state_key -> (uploaded_bytes, uploaded_files, 连续无进展轮数)
        self._stalled = {}

    @property
    def poll_error(self):
        """当前轮询错误状态; 没有错误时返回 None (供 /status 展示)。"""
        if not self._poll_error_count:
            return None
        return {
            "count": self._poll_error_count,
            "error": self._poll_error_text,
            "at": self._poll_error_at,
        }

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

    def _fetch_copy_tasks(self):
        """拉取 CD2 复制任务列表, 单轮内重试 _POLL_FETCH_ATTEMPTS 次。

        返回 (tasks, error): 成功时 error 为空串; 客户端没有该方法时
        返回 (None, "") 表示不可用 (不对账, 也不计轮询错误); 重试后
        仍失败返回 (None, 错误文本), 由轮询层累计连续失败次数 ——
        拉不到列表时绝不做任何删除 (需求 1/2 的安全前提)。
        """
        getter = getattr(self.client, "get_copy_tasks", None)
        if getter is None:
            return None, ""
        last_exc = None
        for _ in range(_POLL_FETCH_ATTEMPTS):
            try:
                return getter(), ""
            except Exception as exc:
                last_exc = exc
        return None, str(last_exc)

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

        返回 (outcome, detail, matched): outcome in
        done/failed/pending/missing, matched 是命中的 Cd2CopyTask
        (没有时 None)。完成判定只看 CopyTask 状态 (Completed 且
        failedFiles=0), 不查目标文件 —— 目标会被 MoviePilot 整理
        移走, 缺失是正常现象。
        身份校验 (需求 5): 单文件任务再核对 total_bytes 与记录的
        文件大小, 对不上视为未匹配 (同路径换了文件)。
        查不到任务 (需求 1): 宽限期内继续等; 超过宽限返回 missing,
        由对账层删除该同步项, 下次扫描重新提交。
        """
        source_path = state["source_path"]
        target_path = state["target_path"]
        state_key = state["state_key"]
        target_dir, _name = parent_and_name(target_path)
        task = self._find_copy_task(tasks, source_path, target_dir,
                                    target_path=target_path)
        if task is not None and int(getattr(task, "total_files", 0) or 0) == 1:
            state_size = int(state.get("size") or 0)
            task_bytes = int(getattr(task, "total_bytes", 0) or 0)
            if state_size and task_bytes and task_bytes != state_size:
                self._debug(
                    "校验 %s: CD2 单文件任务大小 %d 与记录 %d 不一致, "
                    "视为未匹配" % (source_path, task_bytes, state_size)
                )
                task = None
        if task is not None:
            self._debug(
                "校验 %s: 匹配到 CD2 任务 %s -> %s [状态 %s, 已传 %d/%d, "
                "失败文件 %d]"
                % (source_path, task.source_path, task.dest_path,
                   task.status_name, task.uploaded_files, task.total_files,
                   task.failed_files)
            )
            if task.is_failed:
                self._stalled.pop(state_key, None)
                detail = "; ".join(task.errors) or "CD2 复制任务失败"
                return "failed", detail, task
            if not task.is_completed:
                failed_files = int(getattr(task, "failed_files", 0) or 0)
                if failed_files > 0:
                    # 任务没结束但已有文件失败 (如 S01E05: 任务级还是
                    # "已扫描", 文件已失败): 连续 _NO_PROGRESS_POLLS 个
                    # 轮询周期无进展就按失败处理, 不再无限期挂同步中
                    sig = (int(getattr(task, "uploaded_bytes", 0) or 0),
                           int(getattr(task, "uploaded_files", 0) or 0))
                    prev = self._stalled.get(state_key)
                    if prev and prev[0] == sig[0] and prev[1] == sig[1]:
                        stall_count = prev[2] + 1
                    else:
                        stall_count = 1
                    self._stalled[state_key] = (sig[0], sig[1], stall_count)
                    if stall_count >= _NO_PROGRESS_POLLS:
                        self._stalled.pop(state_key, None)
                        detail = "; ".join(task.errors) or (
                            "CD2 任务有 %d 个文件失败且无进展"
                            % failed_files
                        )
                        return "failed", detail, task
                else:
                    self._stalled.pop(state_key, None)
                return "pending", task.status_name, task
            failed_files = int(getattr(task, "failed_files", 0) or 0)
            self._stalled.pop(state_key, None)
            if failed_files > 0:
                detail = "; ".join(task.errors) or (
                    "CD2 任务完成但有 %d 个文件失败" % failed_files
                )
                return "failed", detail, task
            return "done", "", task
        # 任务列表里查不到: 宽限期内继续等 (任务可能还没建好);
        # 超过宽限仍无记录 -> missing, 对账层删同步项等下次扫描。
        submitted = state.get("submitted_at") or state.get("first_seen_at")
        if submitted and time.time() - float(submitted) > _NO_TASK_GRACE_SECONDS:
            return "missing", "CD2 复制任务不存在", None
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
        self._stalled.pop(state["state_key"], None)
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

    def _delete_cd2_task(self, source_path, dest_dir_or_path):
        """尽力删掉 CD2 侧的一条复制任务: 先 CancelCopyTask 再按
        taskKey RemoveCopyTasks。失败只记日志 (本地记录的删除不依赖它)。"""
        try:
            self.client.cancel_copy_task(source_path, dest_dir_or_path)
        except Exception as exc:
            self._log("取消 CD2 复制任务失败 %s: %s" % (source_path, exc))
        try:
            self.client.remove_copy_tasks(
                ["%s:%s" % (source_path, dest_dir_or_path)])
        except Exception as exc:
            self._log("删除 CD2 复制任务失败 %s: %s" % (source_path, exc))

    def _delete_cd2_task_for_state(self, state):
        """按同步记录里存的源路径/目标文件路径删 CD2 任务:
        taskKey 的 dest 用目标目录 (与 api_delete_task 的做法一致)。"""
        target_dir, _ = parent_and_name(state["target_path"])
        self._delete_cd2_task(state["source_path"], target_dir)

    def _apply_missing(self, task, state, tsum):
        """需求 1: CD2 复制任务列表里查不到且已过宽限期 ->
        删除该同步项, 面板行结为失败留痕, 下次扫描重新提交。"""
        submitted = state.get("submitted_at") or state.get("first_seen_at")
        self._log(
            "CD2 复制任务不存在, 删除同步项 (下次扫描重新提交): "
            "文件=%s 源=%s 目标=%s 提交时间=%s"
            % (state.get("file_name") or state["source_path"],
               state["source_path"], state["target_path"],
               time.strftime("%Y-%m-%d %H:%M:%S",
                             time.localtime(float(submitted)))
               if submitted else "-")
        )
        self.store.delete_state(state["state_key"])
        self.store.finish_open_task(
            state["source_path"], "failed",
            error="CD2 任务不存在, 已删除, 等待下次扫描重新提交",
            task_id=task.id)
        self._stalled.pop(state["state_key"], None)

    def _apply_failed(self, task, state, tsum, detail, matched):
        """远端失败的落地处理。

        源/目标不存在 -> 标记跳过 (excluded), 不再重试; 其它失败 ->
        记失败, 在"失败最大重试次数"内调 RestartCopyTask 自动重启;
        超过上限 -> 删除 CD2 侧复制任务与本地 sync_state 行 (需求 4),
        面板历史行已在上面结为失败保留 (原因与重试次数可查),
        源文件还在时下次扫描会重新发现并提交。
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
            self._delete_cd2_task(matched.source_path, matched.dest_path)
            self.store.delete_state(state["state_key"])
            self._stalled.pop(state["state_key"], None)
            self._log(
                "已达最大重试次数 (%d), 已删除 CD2 复制任务与同步记录: %s"
                % (int(self.config.max_retries), state["source_path"]))
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
                    cd2_task_key="%s:%s" % (src.full_path,
                                            cand["target_dir"]),
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
            cd2_task_key="%s:%s" % (src.full_path, cand["target_dir"]),
        )
        return row_id, state_like

    def _submit_candidates(self, task, tsum, candidates, in_flight, limit):
        """按并发上限提交候选: 在传数 (含往轮未完成的) 不超过 limit。

        超出部分计暂缓并原样返回 (未提交的候选列表): 扫描轮次把它们
        存进内存待提交队列, 轮询对账腾出名额后直接补交。完成状态
        一律由 poll_copy_tasks 对账, 这里提交完即返回。
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
        return candidates[idx:]

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
          在重试上限内 RestartCopyTask 自动重启; 超限删双侧记录
        - 远端未结束但已有文件失败且连续 2 个轮询无进展: 按失败处理
        - 远端查不到该任务且已过 10 分钟宽限: 删同步项, 等下次扫描
        - 进行中: 不处理, 等下一轮轮询
        - 数据库里的失败记录若远端其实已完成, 修正为已同步
        - GetCopyTasks 拉取失败: 不做任何删除, 累计连续失败次数并
          经 /status 暴露; 连续 3 个周期失败后按库存路径删双侧记录
        对账后按每任务并发上限从内存待提交队列补齐在传数; 队列空
        且有名额时节流触发提前扫描。
        轮询间隔由全局配置 copy_poll_interval_seconds 控制 (宿主
        get_service 注册), 本方法只负责一轮对账。
        """
        if not self._lock.acquire(blocking=False):
            return {"skipped": True}
        try:
            return self._poll_locked()
        finally:
            self._lock.release()

    def _handle_poll_fetch_error(self, error_text, copying, tasks_by_id):
        """GetCopyTasks 本轮重试后仍失败: 累计连续失败次数;
        达到阈值后, 对每个 copying 项按库存路径删 CD2 任务并删本地
        记录 (列表接口本身不可用, 只能按库存路径逐项删)。"""
        self._poll_error_count += 1
        self._poll_error_text = error_text
        self._poll_error_at = time.time()
        self._log("GetCopyTasks 连续失败 %d 次: %s"
                  % (self._poll_error_count, error_text))
        result = {"poll_error": self.poll_error, "poll_failed": True}
        if self._poll_error_count < _POLL_ERROR_DELETE_THRESHOLD:
            return result
        deleted = 0
        for state in copying:
            task = tasks_by_id.get(state.get("task_id") or "")
            if task is None:
                continue
            self._delete_cd2_task_for_state(state)
            self.store.delete_state(state["state_key"])
            self.store.finish_open_task(
                state["source_path"], "failed",
                error="CD2 任务列表持续报错, 已删除复制任务与同步记录: "
                      + error_text,
                task_id=task.id)
            self._stalled.pop(state["state_key"], None)
            deleted += 1
        self._log("GetCopyTasks 连续 %d 个周期失败, 已按库存路径删除 "
                  "%d 个同步项的 CD2 任务与本地记录"
                  % (self._poll_error_count, deleted))
        # 记录已删完, 计数清零, 避免之后每个周期重复触发删除流程
        self._poll_error_count = 0
        self._poll_error_text = ""
        self._poll_error_at = 0.0
        result["deleted"] = deleted
        return result

    def _poll_locked(self):
        tasks_by_id = {t.id: t for t in self.config.tasks}
        copying = self.store.list_states_by_status("copying")
        failed_states = self.store.list_states_by_status("failed")
        queue_pending = any(
            self._pending_queue.get(t.id) for t in self.config.tasks)
        if not copying and not failed_states and not queue_pending:
            return {}
        cd2_tasks, fetch_error = self._fetch_copy_tasks()
        if cd2_tasks is None:
            if fetch_error:
                return self._handle_poll_fetch_error(
                    fetch_error, copying, tasks_by_id)
            self._log("轮询对账跳过: GetCopyTasks 不可用")
            return {"skipped": True}
        if self._poll_error_count:
            self._log("GetCopyTasks 已恢复 (此前连续失败 %d 次)"
                      % self._poll_error_count)
            self._poll_error_count = 0
            self._poll_error_text = ""
            self._poll_error_at = 0.0
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
            elif outcome == "failed":
                self._apply_failed(task, state, tsum, detail, matched)
            elif outcome == "missing":
                self._apply_missing(task, state, tsum)
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
            # 身份校验 (需求 5): 单文件任务大小对不上不算这条的完成
            if int(getattr(matched, "total_files", 0) or 0) == 1:
                state_size = int(state.get("size") or 0)
                task_bytes = int(getattr(matched, "total_bytes", 0) or 0)
                if state_size and task_bytes and task_bytes != state_size:
                    continue
            self._apply_done(task, state, _tsum(task), remove_keys,
                             matched)
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
        self._top_up()
        return {
            tid: {
                "verified": t.verified, "failed": t.failed,
                "pending": t.pending,
            }
            for tid, t in tsums.items()
        }

    def _top_up(self):
        """轮询补齐 (需求 3): 对账后每个启用任务的在传数低于并发
        上限时, 先从内存待提交队列直接补交; 队列空仍有名额时,
        节流 (距上次扫描 <5 分钟不触发) 提前跑一轮扫描补齐。"""
        for task in self.config.tasks:
            if not task.enabled:
                continue
            limit = max(1, int(getattr(task, "max_concurrent_sync", 1)
                               or 1))
            in_flight = int(
                self.store.count_states(task.id).get("copying", 0))
            if in_flight >= limit:
                continue
            queue = self._pending_queue.get(task.id) or []
            if queue:
                tsum = TaskSummary(task_id=task.id, name=task.name,
                                   mode=task.mode)
                remaining = self._submit_candidates(
                    task, tsum, list(queue), in_flight, limit)
                self._pending_queue[task.id] = remaining
                self._backlog[task.id] = bool(remaining)
                submitted = len(queue) - len(remaining)
                if submitted:
                    self._log("轮询补齐 [%s]: 从待提交队列补交 %d 个"
                              % (task.name, submitted))
                continue
            last_scan = self._last_scan_at.get(task.id, 0.0)
            if time.time() - last_scan < _EARLY_SCAN_MIN_INTERVAL:
                continue
            self._last_scan_at[task.id] = time.time()
            self._target_cache = {}
            self._ensured_dirs = set()
            try:
                self._run_task(task)
            except Exception as exc:
                self._log("轮询提前扫描异常 [%s]: %s" % (task.name, exc))

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

        self._last_scan_at[task.id] = time.time()

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
                # 身份校验 (需求 5): 文件名 + 源/目标路径必须与记录
                # 一致才算同一个文件; file_name 为空 (异常数据) 时
                # 不单独据此判变化
                and state.get("source_path") == src.full_path
                and state.get("target_path") == target_path
                and (
                    not state.get("file_name")
                    or state.get("file_name") == src.name
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

        remaining = self._submit_candidates(task, tsum, candidates,
                                            in_flight, limit)
        # 暂缓的候选存进内存队列, 轮询对账腾出名额后直接补交
        self._pending_queue[task.id] = remaining
        self._backlog[task.id] = bool(remaining)
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
