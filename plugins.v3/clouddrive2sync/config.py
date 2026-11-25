"""CloudDrive2Sync 配置模型 (v0.3.0: 多任务)。

全局配置 (连接/调度/校验/清理) + 任务列表 tasks:
每个任务 = 一组独立的 源目录 -> 目标目录 + 模式:
- sync   同步: 增量复制, 源端变化重新复制, 源端消失按宽限期处理状态
- backup 备份: 只增不减, 源文件变化时目标保留旧版 (强制改名复制新版),
         源端消失不动目标
- move   移动: 复制并校验完成后删除源文件 (可选清理空目录)

注: v0.6.2 起不再做旧单任务配置迁移, tasks 为空就是没有任务。
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
    "max_retries",
    "pending_timeout_hours",
    "copy_timeout_seconds",
    "history_retention_days",
    "failed_retention_days",
    "state_tombstone_days",
    "onlyonce",
    "debug_logging",
    "copy_poll_interval_seconds",
)

_GLOBAL_DEFAULTS = {
    "enabled": False,
    "cd2_address": "127.0.0.1:19798",
    "cd2_token": "",
    "max_retries": 5,
    "pending_timeout_hours": 24,
    "copy_timeout_seconds": 180,
    "history_retention_days": 30,
    "failed_retention_days": 90,
    "state_tombstone_days": 30,
    "onlyonce": False,
    "debug_logging": False,
    "copy_poll_interval_seconds": 10,
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
    "interval_minutes",
    "allowed_suffixes",
)


def parse_allowed_suffixes(value):
    """解析任务级允许后缀: 逗号隔开, 点可写可不写, 不区分大小写。

    返回归一化后的后缀集合 (不带点, 全小写); 空字符串/None ->
    空集合, 表示不限制, 同步所有后缀。
    """
    result = set()
    for part in str(value or "").replace("，", ",").split(","):
        suffix = part.strip().lstrip(".").strip().lower()
        if suffix:
            result.add(suffix)
    return result


def normalize_allowed_suffixes(value):
    """把允许后缀写回统一形式: "mkv,mp4,srt", 空 = 全部。"""
    return ",".join(sorted(parse_allowed_suffixes(value)))


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
    interval_minutes: int = 30  # 本任务的扫描间隔 (分钟, 独立调度)
    allowed_suffixes: str = ""  # 仅同步的后缀名, 逗号隔开 (如 mkv,mp4);
    # 空 = 不限制, 同步所有后缀; 点可写可不写, 不区分大小写

    def allowed_suffix_set(self):
        return parse_allowed_suffixes(self.allowed_suffixes)

    def suffix_allowed(self, file_name):
        """文件名是否在允许后缀内: 不限制 -> 全部允许; 否则只看
        最后一个点后的后缀 (无后缀的文件不在允许列表内)。"""
        allowed = self.allowed_suffix_set()
        if not allowed:
            return True
        name = str(file_name or "")
        if "." not in name or name.endswith("."):
            return False
        return name.rsplit(".", 1)[-1].lower() in allowed

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
        task.allowed_suffixes = normalize_allowed_suffixes(
            task.allowed_suffixes)
        if task.max_concurrent_sync < 1:
            task.max_concurrent_sync = 1
        try:
            task.interval_minutes = int(task.interval_minutes or 30)
        except (TypeError, ValueError):
            task.interval_minutes = 30
        if task.interval_minutes < 1:
            task.interval_minutes = 1
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


def _parse_tasks(raw):
    """解析 tasks 配置: 接受 list / JSON 字符串。没有任务就是没有,
    不再从旧单任务字段迁移生成 (删掉最后一个任务后不能被"复活")。"""
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
    return tasks


@dataclass
class SyncConfig:
    """插件全局配置 + 任务列表。"""

    enabled: bool = _GLOBAL_DEFAULTS["enabled"]
    cd2_address: str = _GLOBAL_DEFAULTS["cd2_address"]
    cd2_token: str = _GLOBAL_DEFAULTS["cd2_token"]
    max_retries: int = _GLOBAL_DEFAULTS["max_retries"]
    pending_timeout_hours: int = _GLOBAL_DEFAULTS["pending_timeout_hours"]
    copy_timeout_seconds: int = _GLOBAL_DEFAULTS["copy_timeout_seconds"]
    history_retention_days: int = _GLOBAL_DEFAULTS["history_retention_days"]
    failed_retention_days: int = _GLOBAL_DEFAULTS["failed_retention_days"]
    state_tombstone_days: int = _GLOBAL_DEFAULTS["state_tombstone_days"]
    onlyonce: bool = _GLOBAL_DEFAULTS["onlyonce"]
    debug_logging: bool = _GLOBAL_DEFAULTS["debug_logging"]
    copy_poll_interval_seconds: int = _GLOBAL_DEFAULTS[
        "copy_poll_interval_seconds"]
    tasks: list = field(default_factory=list)
    # 顶层路径仅由 to_dict 按第一个任务回填展示, 不参与任务解析
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
        cfg.tasks = _parse_tasks(data.get("tasks"))
        return cfg

    def to_dict(self):
        result = {k: getattr(self, k) for k in _GLOBAL_FIELDS}
        result["tasks"] = [t.to_dict() for t in self.tasks]
        # 顶层路径仅作展示: 有任务时取第一个任务的, 没有任务就是空,
        # 不能残留已删任务的路径 (会被误当成还有任务)
        first = self.tasks[0] if self.tasks else None
        result["source_path"] = first.source_path if first else ""
        result["target_path"] = first.target_path if first else ""
        result["conflict_policy"] = self.conflict_policy
        return result

    def get_task(self, task_id):
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None
