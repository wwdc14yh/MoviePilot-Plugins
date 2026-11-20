"""CloudDrive2Sync 配置模型 (v0.3.0: 多任务)。

全局配置 (连接/调度/校验/清理) + 任务列表 tasks:
每个任务 = 一组独立的 源目录 -> 目标目录 + 模式:
- sync   同步: 增量复制, 源端变化重新复制, 源端消失按宽限期处理状态
- backup 备份: 只增不减, 源文件变化时目标保留旧版 (强制改名复制新版),
         源端消失不动目标
- move   移动: 复制并校验完成后删除源文件 (可选清理空目录)

兼容: v0.2 及更早的单任务配置 (顶层 source_path/target_path) 在 from_dict
时自动迁移成一个 sync 模式的默认任务。
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field

TASK_MODES = ("sync", "backup", "move")
CONFLICT_POLICIES = ("skip", "overwrite", "rename")

_GLOBAL_FIELDS = (
    "enabled",
    "cd2_address",
    "cd2_token",
    "interval_minutes",
    "max_retries",
    "verify_wait_seconds",
    "verify_interval_seconds",
    "pending_timeout_hours",
    "copy_timeout_seconds",
    "history_retention_days",
    "failed_retention_days",
    "state_tombstone_days",
    "onlyonce",
)

_GLOBAL_DEFAULTS = {
    "enabled": False,
    "cd2_address": "127.0.0.1:19798",
    "cd2_token": "",
    "interval_minutes": 30,
    "max_retries": 5,
    "verify_wait_seconds": 30,
    "verify_interval_seconds": 5,
    "pending_timeout_hours": 24,
    "copy_timeout_seconds": 180,
    "history_retention_days": 30,
    "failed_retention_days": 90,
    "state_tombstone_days": 30,
    "onlyonce": False,
}

_TASK_FIELDS = (
    "id",
    "name",
    "enabled",
    "mode",
    "source_path",
    "target_path",
    "conflict_policy",
    "delete_empty_dirs",
    "max_concurrent_sync",
)


@dataclass
class SyncTask:
    """一个同步/备份/移动任务。"""

    id: str = ""
    name: str = ""
    enabled: bool = True
    mode: str = "sync"
    source_path: str = ""
    target_path: str = ""
    conflict_policy: str = ""  # 空 = 用全局; sync/backup/move 各有默认处理
    delete_empty_dirs: bool = False  # 仅 move 模式: 删源文件后清理空目录
    max_concurrent_sync: int = 1  # 每轮最多同时进行的文件同步数 (本任务独立)

    @classmethod
    def from_dict(cls, data):
        data = dict(data or {})
        for key in ("enabled", "delete_empty_dirs"):
            value = data.get(key)
            if isinstance(value, str):
                data[key] = value.strip().lower() in ("true", "1", "yes", "on")
        task = cls(**{k: data[k] for k in _TASK_FIELDS if k in data})
        try:
            task.max_concurrent_sync = int(task.max_concurrent_sync or 1)
        except (TypeError, ValueError):
            task.max_concurrent_sync = 1
        if task.max_concurrent_sync < 1:
            task.max_concurrent_sync = 1
        if not task.id:
            task.id = uuid.uuid4().hex[:12]
        if task.mode not in TASK_MODES:
            task.mode = "sync"
        if task.conflict_policy and task.conflict_policy not in CONFLICT_POLICIES:
            task.conflict_policy = ""
        if not task.name:
            task.name = task.source_path or "未命名任务"
        return task

    def to_dict(self):
        return {k: getattr(self, k) for k in _TASK_FIELDS}


def _parse_tasks(raw, legacy):
    """解析 tasks 配置: 接受 list / JSON 字符串; 为空时用旧单任务字段迁移。"""
    tasks = []
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                tasks.append(SyncTask.from_dict(item))
    # id 去重: 重复 id 会让两个任务共用同一份同步状态, 后出现的重新生成
    seen = set()
    for task in tasks:
        if task.id in seen:
            task.id = uuid.uuid4().hex[:12]
        seen.add(task.id)
    if not tasks:
        source = str(legacy.get("source_path") or "").strip()
        target = str(legacy.get("target_path") or "").strip()
        if source or target:
            tasks.append(
                SyncTask.from_dict(
                    {
                        "name": "默认任务",
                        "mode": "sync",
                        "source_path": source,
                        "target_path": target,
                        "conflict_policy": legacy.get("conflict_policy") or "",
                    }
                )
            )
    return tasks


@dataclass
class SyncConfig:
    """插件全局配置 + 任务列表。"""

    enabled: bool = _GLOBAL_DEFAULTS["enabled"]
    cd2_address: str = _GLOBAL_DEFAULTS["cd2_address"]
    cd2_token: str = _GLOBAL_DEFAULTS["cd2_token"]
    interval_minutes: int = _GLOBAL_DEFAULTS["interval_minutes"]
    max_retries: int = _GLOBAL_DEFAULTS["max_retries"]
    verify_wait_seconds: int = _GLOBAL_DEFAULTS["verify_wait_seconds"]
    verify_interval_seconds: int = _GLOBAL_DEFAULTS["verify_interval_seconds"]
    pending_timeout_hours: int = _GLOBAL_DEFAULTS["pending_timeout_hours"]
    copy_timeout_seconds: int = _GLOBAL_DEFAULTS["copy_timeout_seconds"]
    history_retention_days: int = _GLOBAL_DEFAULTS["history_retention_days"]
    failed_retention_days: int = _GLOBAL_DEFAULTS["failed_retention_days"]
    state_tombstone_days: int = _GLOBAL_DEFAULTS["state_tombstone_days"]
    onlyonce: bool = _GLOBAL_DEFAULTS["onlyonce"]
    tasks: list = field(default_factory=list)
    # 旧单任务字段, 仅迁移来源, 不再单独使用
    source_path: str = ""
    target_path: str = ""
    conflict_policy: str = "skip"

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        cfg = cls(**{k: data[k] for k in _GLOBAL_FIELDS if k in data})
        cfg.source_path = str(data.get("source_path") or "")
        cfg.target_path = str(data.get("target_path") or "")
        cfg.conflict_policy = str(data.get("conflict_policy") or "skip")
        cfg.tasks = _parse_tasks(data.get("tasks"), data)
        return cfg

    def to_dict(self):
        result = {k: getattr(self, k) for k in _GLOBAL_FIELDS}
        result["tasks"] = [t.to_dict() for t in self.tasks]
        # 顶层路径保留第一个任务的值, 兼容旧前端/外部读取
        first = self.tasks[0] if self.tasks else None
        result["source_path"] = first.source_path if first else self.source_path
        result["target_path"] = first.target_path if first else self.target_path
        result["conflict_policy"] = self.conflict_policy
        return result

    def get_task(self, task_id):
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None
