"""CloudDrive2Sync: CloudDrive2 网盘 A -> B 增量同步插件 (MoviePilot V3)。

骨架版本 0.1.0:
- 生命周期 / 配置表单 / 任务页面 / API / 定时服务已接好;
- 同步逻辑在 sync_engine.py, 状态库在 store.py, CD2 客户端在 cd2_client.py;
- 定时服务走宿主 get_service(), 不自建调度器;
- 立即运行走宿主 add_plugin_once_job(), 宿主没有该接口时退回线程执行。
"""
from __future__ import annotations

import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from app.sdk.plugin import _PluginBase
except Exception:  # 无宿主环境 (本地测试) 时的最小替身
    class _PluginBase:
        """仅供本地导入/测试的替身基类。"""

        _data_path_override = None

        def get_data_path(self):
            if self._data_path_override:
                return Path(self._data_path_override)
            return Path.cwd() / ".cd2sync_data"

        def update_config(self, config):
            self._saved_config = config
            return True

try:
    from app.sdk.logging import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("CloudDrive2Sync")

try:
    from .cd2_client import Cd2GrpcClient
    from .config import SyncConfig
    from .store import SyncStore
    from .sync_engine import SyncEngine
except ImportError:  # 直接以顶层模块加载时
    from cd2_client import Cd2GrpcClient
    from config import SyncConfig
    from store import SyncStore
    from sync_engine import SyncEngine


def _human_size(size):
    value = float(size or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return ("%.2f %s" % (value, unit)) if unit != "B" else ("%d B" % value)
        value /= 1024
    return "%d B" % (size or 0)


class CloudDrive2Sync(_PluginBase):
    """CloudDrive2 网盘增量同步插件主类。"""

    plugin_name = "CloudDrive2 网盘增量同步"
    plugin_desc = "基于 CloudDrive2 gRPC API 的 A 网盘到 B 网盘增量同步, 不走本地中转。"
    plugin_icon = "CloudDrive2.png"
    plugin_version = "0.1.0"
    plugin_author = "Hu"
    author_url = ""
    plugin_config_prefix = "clouddrive2sync_"
    plugin_order = 60
    auth_level = 1

    _config: SyncConfig = None
    _store: SyncStore = None
    _client: Cd2GrpcClient = None
    _engine: SyncEngine = None

    # ---------- 生命周期 ----------

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置, 建立本次运行状态; 必须可重复调用。"""
        self.stop_service()
        self._config = SyncConfig.from_dict(config or {})
        if not self._config.enabled:
            return
        db_path = self.get_data_path() / "clouddrive2sync.db"
        self._store = SyncStore(db_path)
        self._client = Cd2GrpcClient(
            self._config.cd2_address, token=self._config.cd2_token
        )
        self._engine = SyncEngine(self._store, self._client, self._config,
                                  logger=logger)
        if self._config.onlyonce:
            self._config.onlyonce = False
            saved = self._config.to_dict()
            self.update_config(saved)
            self._run_once_async()

    def _run_once_async(self):
        """立即运行一次: 优先宿主调度器, 没有就开守护线程。"""
        try:
            from app.sdk import scheduler as scheduler_sdk

            add_job = getattr(scheduler_sdk, "add_plugin_once_job", None)
        except Exception:
            add_job = None
        if add_job:
            add_job(
                self.__class__.__name__,
                "sync_once",
                self.run_sync,
                "CloudDrive2Sync 立即同步一次",
                delay_seconds=3,
            )
        else:
            threading.Thread(target=self.run_sync, daemon=True).start()

    def get_state(self) -> bool:
        return bool(self._config and self._config.enabled)

    def stop_service(self) -> None:
        """释放客户端和数据库连接; 可重复调用。"""
        if self._client is not None:
            try:
                self._client.close()
            finally:
                self._client = None
        if self._store is not None:
            try:
                self._store.close()
            finally:
                self._store = None
        self._engine = None

    # ---------- 同步入口 ----------

    def run_sync(self):
        """执行一轮同步, 返回 summary 字典 (供 API / 调度调用)。"""
        if self._engine is None:
            return {"skipped_run": True, "reason": "plugin not initialized"}
        summary = self._engine.run_once()
        return asdict(summary)

    # ---------- 定时服务 ----------

    def get_service(self) -> list[dict[str, Any]]:
        """周期同步服务, 由宿主调度器管理。"""
        if not self.get_state() or self._config is None:
            return []
        from apscheduler.triggers.interval import IntervalTrigger

        return [
            {
                "id": "CloudDrive2Sync.Sync",
                "name": "CloudDrive2 网盘增量同步",
                "trigger": IntervalTrigger(
                    minutes=max(1, int(self._config.interval_minutes))
                ),
                "func": self.run_sync,
                "kwargs": {},
            }
        ]

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        """远程命令暂未注册 (骨架), 手动触发走 API 或配置页立即运行。"""
        return []

    # ---------- API ----------

    def get_api(self) -> list[dict[str, Any]]:
        return [
            {
                "path": "/run_once",
                "endpoint": self.api_run_once,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "立即执行一轮同步",
            },
            {
                "path": "/tasks",
                "endpoint": self.api_tasks,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "最近同步任务列表",
            },
            {
                "path": "/status",
                "endpoint": self.api_status,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "插件状态与状态库计数",
            },
        ]

    def api_run_once(self):
        return self.run_sync()

    def api_tasks(self, limit: int = 50):
        if self._store is None:
            return []
        return self._store.list_tasks(limit=int(limit))

    def api_status(self):
        return {
            "enabled": self.get_state(),
            "source_path": self._config.source_path if self._config else "",
            "target_path": self._config.target_path if self._config else "",
            "states": self._store.count_states() if self._store else {},
        }

    # ---------- 配置表单 ----------

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        def text_field(model, label, **extra):
            props = {"model": model, "label": label}
            props.update(extra)
            return {"component": "VTextField", "props": props}

        form = [
            {
                "component": "VForm",
                "content": [
                    {"component": "VSwitch",
                     "props": {"model": "enabled", "label": "启用插件"}},
                    text_field("cd2_address", "CloudDrive2 gRPC 地址"),
                    text_field("cd2_token", "CloudDrive2 API Token",
                               type="password"),
                    text_field("source_path", "源目录 (A 网盘)"),
                    text_field("target_path", "目标目录 (B 网盘)"),
                    text_field("interval_minutes", "轮询间隔 (分钟)",
                               type="number"),
                    text_field("history_retention_days", "成功历史保留 (天)",
                               type="number"),
                    text_field("failed_retention_days", "失败历史保留 (天)",
                               type="number"),
                    text_field("state_tombstone_days", "源端消失宽限 (天)",
                               type="number"),
                    text_field("max_retries", "失败最大重试次数", type="number"),
                    {"component": "VSwitch",
                     "props": {"model": "onlyonce", "label": "立即运行一次"}},
                ],
            }
        ]
        return form, SyncConfig().to_dict()

    # ---------- 任务页面 (最小版, 对应截图的列表形态) ----------

    def get_page(self) -> list[dict]:
        if self._store is None:
            return [
                {
                    "component": "VAlert",
                    "props": {
                        "type": "info",
                        "variant": "tonal",
                        "text": "插件未启用或尚未初始化。",
                    },
                }
            ]
        status_label = {
            "syncing": "同步中",
            "done": "完成",
            "failed": "失败",
        }
        items = []
        for task in self._store.list_tasks(limit=50):
            status = status_label.get(task["status"], task["status"])
            subtitle = "%s · %s · %s" % (
                status,
                _human_size(task["size"]),
                task["target_path"],
            )
            if task.get("error"):
                subtitle += " · " + str(task["error"])
            items.append(
                {
                    "component": "VListItem",
                    "props": {"title": task["file_name"], "subtitle": subtitle},
                }
            )
        if not items:
            items.append(
                {
                    "component": "VListItem",
                    "props": {"title": "暂无同步任务", "subtitle": ""},
                }
            )
        return [{"component": "VList", "content": items}]
