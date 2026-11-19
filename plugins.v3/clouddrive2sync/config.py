"""CloudDrive2Sync 配置模型。

有 pydantic 时用 pydantic 模型 (MoviePilot 宿主环境), 没有时退回 dataclass,
两者字段和接口 (from_dict / to_dict) 一致。
"""
from __future__ import annotations

_FIELDS = (
    "enabled",
    "cd2_address",
    "cd2_token",
    "source_path",
    "target_path",
    "interval_minutes",
    "conflict_policy",
    "max_retries",
    "verify_wait_seconds",
    "verify_interval_seconds",
    "pending_timeout_hours",
    "history_retention_days",
    "failed_retention_days",
    "state_tombstone_days",
    "onlyonce",
)

_DEFAULTS = {
    "enabled": False,
    "cd2_address": "127.0.0.1:19798",
    "cd2_token": "",
    "source_path": "",
    "target_path": "",
    "interval_minutes": 30,
    "conflict_policy": "skip",
    "max_retries": 5,
    "verify_wait_seconds": 30,
    "verify_interval_seconds": 5,
    "pending_timeout_hours": 24,
    "history_retention_days": 30,
    "failed_retention_days": 90,
    "state_tombstone_days": 30,
    "onlyonce": False,
}


def _pick(data):
    data = data or {}
    return {k: data[k] for k in _FIELDS if k in data}


try:
    from pydantic import BaseModel

    class SyncConfig(BaseModel):
        """插件配置 (pydantic 版)。"""

        enabled: bool = _DEFAULTS["enabled"]
        cd2_address: str = _DEFAULTS["cd2_address"]
        cd2_token: str = _DEFAULTS["cd2_token"]
        source_path: str = _DEFAULTS["source_path"]
        target_path: str = _DEFAULTS["target_path"]
        interval_minutes: int = _DEFAULTS["interval_minutes"]
        conflict_policy: str = _DEFAULTS["conflict_policy"]
        max_retries: int = _DEFAULTS["max_retries"]
        verify_wait_seconds: int = _DEFAULTS["verify_wait_seconds"]
        verify_interval_seconds: int = _DEFAULTS["verify_interval_seconds"]
        pending_timeout_hours: int = _DEFAULTS["pending_timeout_hours"]
        history_retention_days: int = _DEFAULTS["history_retention_days"]
        failed_retention_days: int = _DEFAULTS["failed_retention_days"]
        state_tombstone_days: int = _DEFAULTS["state_tombstone_days"]
        onlyonce: bool = _DEFAULTS["onlyonce"]

        @classmethod
        def from_dict(cls, data):
            return cls(**_pick(data))

        def to_dict(self):
            return {k: getattr(self, k) for k in _FIELDS}

except Exception:  # 无 pydantic 的环境 (本地测试) 用 dataclass
    from dataclasses import dataclass

    @dataclass
    class SyncConfig:
        """插件配置 (dataclass 版, 字段与 pydantic 版一致)。"""

        enabled: bool = _DEFAULTS["enabled"]
        cd2_address: str = _DEFAULTS["cd2_address"]
        cd2_token: str = _DEFAULTS["cd2_token"]
        source_path: str = _DEFAULTS["source_path"]
        target_path: str = _DEFAULTS["target_path"]
        interval_minutes: int = _DEFAULTS["interval_minutes"]
        conflict_policy: str = _DEFAULTS["conflict_policy"]
        max_retries: int = _DEFAULTS["max_retries"]
        verify_wait_seconds: int = _DEFAULTS["verify_wait_seconds"]
        verify_interval_seconds: int = _DEFAULTS["verify_interval_seconds"]
        pending_timeout_hours: int = _DEFAULTS["pending_timeout_hours"]
        history_retention_days: int = _DEFAULTS["history_retention_days"]
        failed_retention_days: int = _DEFAULTS["failed_retention_days"]
        state_tombstone_days: int = _DEFAULTS["state_tombstone_days"]
        onlyonce: bool = _DEFAULTS["onlyonce"]

        @classmethod
        def from_dict(cls, data):
            return cls(**_pick(data))

        def to_dict(self):
            return {k: getattr(self, k) for k in _FIELDS}
