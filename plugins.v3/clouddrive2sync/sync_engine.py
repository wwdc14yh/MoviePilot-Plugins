"""同步引擎: 轮询拉源目录 -> 对比状态库 -> CD2 复制 -> 复查 -> 记录。

规则 (design-v0.1.md):
- 任务运行中自动跳过本轮 (非阻塞锁)。
- 库中存在且校验通过, 且目标端复查文件还在 -> 跳过。
- 复制走 CD2 CopyFile, 服务端跨盘复制, 不经本地中转。
- 快速校验优先 check_value (CD2 服务端哈希), 没有哈希时退回比 size。
- 失败记录 retry_count, 达到上限后本轮不再重试, 下一轮仍会再评估状态;
  失败任务保留更久, 见 store.cleanup。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

try:
    from .cd2_client import Cd2Error, parent_and_name
    from .store import state_key_of
except ImportError:  # 直接以顶层模块加载时
    from cd2_client import Cd2Error, parent_and_name
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
        seen_keys = set()

        files = self._walk_source(source_root)
        summary.scanned = len(files)

        for src in files:
            rel = src.full_path[len(source_root):].lstrip("/")
            target_path = _join(target_root, rel)
            target_dir, _ = parent_and_name(target_path)
            key = state_key_of(src.id, src.full_path)
            seen_keys.add(key)
            state = self.store.get_state(key)

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
                self.client.copy_file([src.full_path], target_dir)
                dst = self._target_listing(target_dir, force_refresh=True).get(
                    src.name
                )
                if not self._check_ok(src, dst):
                    raise Cd2Error("复制后复查不通过: 目标文件缺失或校验不一致")
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
                self._log("同步失败 " + src.full_path + ": " + str(exc))
                continue

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
            "本轮完成: 扫描 %d, 跳过 %d, 复制 %d, 失败 %d, 暂缓 %d, "
            "源端消失标记 %d"
            % (
                summary.scanned,
                summary.skipped,
                summary.copied,
                summary.failed,
                summary.deferred,
                summary.gone_marked,
            )
        )
        return summary
