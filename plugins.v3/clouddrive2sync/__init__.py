"""CloudDrive2Sync: CloudDrive2 网盘 A -> B 增量同步插件 (MoviePilot V3)。

v0.2.0:
- CD2 CopyFile 是异步操作, 完成判定改为 GetCopyTasks 的 CopyTask 状态
  + 跨轮校验, 不再在提交后立即复查 (必然失败);
- 配置表单分组卡片化, 任务页面美化 (状态图标/概览卡片)。
v0.2.1:
- 注册远程命令 /cd2sync (EventType.PluginAction, action=cd2sync_run),
  触发一次增量同步, 与配置页“立即运行一次”走同一入口。
"""
from __future__ import annotations

import threading
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

try:
    from app.schemas.types import EventType
    from app.sdk.events import Event, eventmanager
except Exception:  # 无宿主环境 (本地测试) 时的最小替身
    Event = None  # type: ignore
    eventmanager = None  # type: ignore

    class EventType:  # type: ignore
        """仅供本地导入/测试的替身, 宿主里用真实枚举。"""

        PluginAction = "PluginAction"

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
    from .cd2_client import Cd2Error, Cd2GrpcClient
    from .config import SyncConfig
    from .store import SyncStore
    from .sync_engine import SyncEngine
except ImportError:  # 直接以顶层模块加载时
    from cd2_client import Cd2Error, Cd2GrpcClient
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


def _human_time(ts):
    if not ts:
        return ""
    return time.strftime("%m-%d %H:%M", time.localtime(float(ts)))


class CloudDrive2Sync(_PluginBase):
    """CloudDrive2 网盘增量同步插件主类。"""

    plugin_name = "CloudDrive2 网盘增量同步"
    plugin_desc = "基于 CloudDrive2 gRPC API 的 A 网盘到 B 网盘增量同步, 异步复制跨轮校验, 不走本地中转。"
    plugin_icon = "CloudDrive2.png"
    plugin_version = "0.4.0"
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

    def run_sync(self, task_id=None):
        """执行一轮同步 (全部任务, 或指定 task_id 的单个任务)。"""
        if self._engine is None:
            return {"skipped_run": True, "reason": "plugin not initialized"}
        summary = self._engine.run_once(task_id=task_id)
        return asdict(summary)

    # ---------- Vue 前端 (模块联邦) ----------

    def get_render_mode(self):
        """Vue 联邦渲染: 产物在 dist/assets (remoteEntry.js)。"""
        return "vue", "dist/assets"

    def get_sidebar_nav(self) -> list[dict[str, Any]]:
        """侧栏全页入口: 任务总览页 (AppPage 组件)。"""
        if not self.get_state():
            return []
        return [
            {
                "nav_key": "main",
                "title": "CloudDrive2 同步",
                "icon": "mdi-cloud-sync",
                "section": "organize",
                "permission": "manage",
                "order": 60,
            }
        ]

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

    # ---------- 远程命令 ----------

    def _handle_plugin_action(self, event) -> None:
        """处理 PluginAction 事件, 只响应本插件的 /cd2sync 动作。

        触发方式与配置页“立即运行一次”相同 (走 _run_once_async,
        宿主调度器优先, 否则守护线程), 不在事件回调里同步跑完整轮
        同步, 避免阻塞消息回复。未启用 / 未初始化时只记日志, 不报错。
        """
        event_data = getattr(event, "event_data", None) or {}
        if isinstance(event_data, dict) and event_data.get("action") != "cd2sync_run":
            return
        if not self.get_state() or self._engine is None:
            logger.warning("[CloudDrive2Sync] /cd2sync 已触发, 但插件未启用或未初始化")
            return
        logger.info("[CloudDrive2Sync] /cd2sync 触发一次增量同步")
        self._run_once_async()
        post = getattr(self, "post_message", None)
        if callable(post):
            try:
                post(title="CloudDrive2Sync", text="已触发一次增量同步, 进度见插件任务页。")
            except Exception as exc:  # 宿主消息接口签名不同时不影响同步本身
                logger.warning("[CloudDrive2Sync] 发送触发确认失败: " + str(exc))

    if eventmanager is not None:
        @eventmanager.register(EventType.PluginAction)
        def run_command(self, event: "Event") -> None:
            """宿主环境: 按官方文档注册 PluginAction 处理器。"""
            self._handle_plugin_action(event)
    else:
        def run_command(self, event) -> None:
            """本地测试环境: 无宿主事件管理器时, 方法仍可直接调用单测。"""
            self._handle_plugin_action(event)

    @staticmethod
    def get_command() -> list[dict[str, Any]]:
        """注册远程命令 /cd2sync, 触发一次增量同步。

        格式按官方 Plugin_Development.md §9.1:
        cmd + EventType.PluginAction + data.action 路由。
        """
        return [
            {
                "cmd": "/cd2sync",
                "event": EventType.PluginAction,
                "desc": "立即执行一次 CloudDrive2 增量同步",
                "category": "插件命令",
                "data": {"action": "cd2sync_run"},
            }
        ]

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
            {
                "path": "/files",
                "endpoint": self.api_files,
                "methods": ["GET"],
                "auth": "bear",
                "summary": "按任务列出文件级同步状态",
            },
            {
                "path": "/retry_file",
                "endpoint": self.api_retry_file,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "重试某个失败文件 (清记录并重跑所属任务)",
            },
            {
                "path": "/delete_file",
                "endpoint": self.api_delete_file,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "删除目标端副本并排除该文件 (不再同步)",
            },
        ]

    def api_run_once(self, task_id: str = None):
        return self.run_sync(task_id=task_id or None)

    def api_tasks(self, limit: int = 50, task_id: str = None):
        if self._store is None:
            return []
        return self._store.list_tasks(
            limit=int(limit), task_id=task_id or None
        )

    def api_status(self):
        tasks = []
        if self._config:
            for task in self._config.tasks:
                tasks.append(
                    {
                        "id": task.id,
                        "name": task.name,
                        "enabled": task.enabled,
                        "mode": task.mode,
                        "source_path": task.source_path,
                        "target_path": task.target_path,
                        "conflict_policy": task.conflict_policy,
                        "delete_empty_dirs": task.delete_empty_dirs,
                        "states": (
                            self._store.count_states(task.id)
                            if self._store
                            else {}
                        ),
                        "done_size": (
                            self._store.sum_done_size(task.id)
                            if self._store
                            else 0
                        ),
                    }
                )
        return {
            "enabled": self.get_state(),
            "tasks": tasks,
            "states": self._store.count_states() if self._store else {},
        }

    def api_files(self, task_id: str = None, status: str = None,
                  limit: int = 200):
        if self._store is None:
            return []
        rows = self._store.list_states(
            task_id=task_id or None, status=status or None,
            limit=int(limit),
        )
        for row in rows:
            row["file_name"] = str(row.get("source_path") or "").rstrip(
                "/"
            ).rsplit("/", 1)[-1]
        return rows

    def api_retry_file(self, state_key: str = ""):
        """重试失败文件: 删掉失败状态行, 然后异步重跑它所属的任务。"""
        if self._store is None or not state_key:
            return {"ok": False, "error": "参数缺失"}
        state = self._store.get_state(state_key)
        if state is None:
            return {"ok": False, "error": "记录不存在"}
        if state.get("status") == "copying":
            return {"ok": False, "error": "文件正在同步中, 不能重试"}
        task_id = state.get("task_id") or None
        self._store.delete_state(state_key)
        threading.Thread(
            target=self.run_sync, kwargs={"task_id": task_id}, daemon=True
        ).start()
        return {"ok": True, "task_id": task_id}

    def api_delete_file(self, state_key: str = ""):
        """删除文件: 删目标端副本 + 标记 excluded (该任务不再同步它)。

        源文件不动 (移动模式的源文件此前已按规则删除)。同步中的文件
        不能删 (CD2 复制任务无法按单文件取消)。
        """
        if self._store is None or self._client is None or not state_key:
            return {"ok": False, "error": "参数缺失或插件未初始化"}
        state = self._store.get_state(state_key)
        if state is None:
            return {"ok": False, "error": "记录不存在"}
        if state.get("status") == "copying":
            return {"ok": False, "error": "文件正在同步中, 不能删除"}
        if state.get("status") == "done":
            try:
                self._client.delete_file(state["target_path"])
            except Cd2Error as exc:
                return {"ok": False, "error": "删除目标文件失败: " + str(exc)}
        self._store.set_excluded(state_key)
        return {"ok": True}

    # ---------- 配置表单 ----------

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        def switch(model, label, hint=""):
            props = {"model": model, "label": label}
            if hint:
                props["hint"] = hint
            return {"component": "VSwitch", "props": props}

        def text(model, label, hint="", placeholder="", type_=None):
            props = {"model": model, "label": label}
            if hint:
                props["hint"] = hint
            if placeholder:
                props["placeholder"] = placeholder
            if type_:
                props["type"] = type_
            return {"component": "VTextField", "props": props}

        def col(content, md=6):
            return {
                "component": "VCol",
                "props": {"cols": 12, "md": md},
                "content": [content],
            }

        def row(*cols):
            return {"component": "VRow", "content": list(cols)}

        def card(title, subtitle, *rows_):
            return {
                "component": "VCard",
                "props": {"variant": "outlined", "class": "mb-4"},
                "content": [
                    {"component": "VCardTitle", "props": {"text": title}},
                    {"component": "VCardSubtitle", "props": {"text": subtitle}},
                    {"component": "VCardText", "content": list(rows_)},
                ],
            }

        def alert(text_):
            return {
                "component": "VAlert",
                "props": {"type": "info", "variant": "tonal", "text": text_},
            }

        form = [
            {
                "component": "VForm",
                "content": [
                    card(
                        "连接设置",
                        "CloudDrive2 gRPC 服务与插件开关",
                        row(
                            col(switch("enabled", "启用插件"), md=6),
                            col(switch("onlyonce", "保存后立即运行一次"), md=6),
                        ),
                        row(
                            col(
                                text(
                                    "cd2_address",
                                    "CloudDrive2 gRPC 地址",
                                    hint="CD2 的 gRPC 监听地址, 默认端口 19798",
                                    placeholder="127.0.0.1:19798",
                                )
                            ),
                            col(
                                text(
                                    "cd2_token",
                                    "API Token",
                                    hint="在 CloudDrive2 设置中创建, 只给文件读写权限即可",
                                    type_="password",
                                )
                            ),
                        ),
                    ),
                    card(
                        "同步路径",
                        "从 A 网盘目录增量同步到 B 网盘目录, 保持相对目录结构",
                        row(
                            col(
                                text(
                                    "source_path",
                                    "源目录 (A 网盘)",
                                    hint="例如 /115/待同步",
                                    placeholder="/网盘名/源目录",
                                )
                            ),
                            col(
                                text(
                                    "target_path",
                                    "目标目录 (B 网盘)",
                                    hint="例如 /阿里云盘/已同步",
                                    placeholder="/网盘名/目标目录",
                                )
                            ),
                        ),
                    ),
                    card(
                        "同步策略",
                        "轮询与冲突处理",
                        row(
                            col(
                                text(
                                    "interval_minutes",
                                    "轮询间隔 (分钟)",
                                    hint="每隔多久扫描一次源目录并结算未完成的复制",
                                    type_="number",
                                )
                            ),
                            col(
                                {
                                    "component": "VSelect",
                                    "props": {
                                        "model": "conflict_policy",
                                        "label": "目标已存在同名文件时",
                                        "hint": "传给 CD2 CopyFile 的冲突策略",
                                        "items": [
                                            {"title": "跳过 (Skip)",
                                             "value": "skip"},
                                            {"title": "覆盖 (Overwrite)",
                                             "value": "overwrite"},
                                            {"title": "重命名 (Rename)",
                                             "value": "rename"},
                                        ],
                                    },
                                }
                            ),
                        ),
                        row(
                            col(
                                text(
                                    "max_retries",
                                    "失败最大重试次数",
                                    hint="超过后暂缓, 文件有变化或人工介入后再试",
                                    type_="number",
                                ),
                                md=6,
                            )
                        ),
                    ),
                    card(
                        "异步校验与记录清理",
                        "网盘复制是异步的: 提交成功不等于传完, 完成状态跨轮询确认",
                        alert(
                            "复制提交后先在本轮等待一小段时间确认, 没传完的会"
                            "留在“同步中”, 后续每轮自动结算, 不会误判失败, "
                            "也不会重复提交。"
                        ),
                        row(
                            col(
                                text(
                                    "verify_wait_seconds",
                                    "提交后本轮等待 (秒)",
                                    hint="0 表示提交后不等待, 全部留到下一轮结算",
                                    type_="number",
                                )
                            ),
                            col(
                                text(
                                    "verify_interval_seconds",
                                    "等待时轮询间隔 (秒)",
                                    type_="number",
                                )
                            ),
                        ),
                        row(
                            col(
                                text(
                                    "pending_timeout_hours",
                                    "同步中超时判失败 (小时)",
                                    hint="大文件跨盘慢时调大, 避免误判",
                                    type_="number",
                                )
                            ),
                            col(
                                text(
                                    "history_retention_days",
                                    "成功历史保留 (天)",
                                    type_="number",
                                )
                            ),
                        ),
                        row(
                            col(
                                text(
                                    "failed_retention_days",
                                    "失败历史保留 (天)",
                                    type_="number",
                                )
                            ),
                            col(
                                text(
                                    "state_tombstone_days",
                                    "源文件消失后宽限 (天)",
                                    hint="防改名/移动误判, 到期才删同步状态",
                                    type_="number",
                                )
                            ),
                        ),
                    ),
                ],
            }
        ]
        return form, SyncConfig().to_dict()

    # ---------- 任务页面 ----------

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
        counts = self._store.count_states()
        cfg = self._config
        overview = (
            "源目录 %s → 目标目录 %s · 已同步 %d · 同步中 %d · 失败 %d · "
            "源端已消失 %d"
            % (
                (cfg.source_path if cfg else "") or "-",
                (cfg.target_path if cfg else "") or "-",
                counts.get("done", 0),
                counts.get("copying", 0),
                counts.get("failed", 0),
                counts.get("source_gone", 0),
            )
        )
        header = {
            "component": "VCard",
            "props": {"variant": "tonal", "class": "mb-4"},
            "content": [
                {"component": "VCardTitle",
                 "props": {"text": "CloudDrive2 增量同步"}},
                {"component": "VCardSubtitle", "props": {"text": overview}},
            ],
        }
        status_meta = {
            "syncing": ("同步中", "mdi-progress-clock"),
            "done": ("完成", "mdi-check-circle"),
            "failed": ("失败", "mdi-alert-circle"),
        }
        items = []
        for task in self._store.list_tasks(limit=50):
            label, icon = status_meta.get(
                task["status"], (task["status"], "mdi-file")
            )
            parts = [
                label,
                _human_size(task["size"]),
                _human_time(task.get("started_at")),
                str(task["target_path"]),
            ]
            if task["status"] == "syncing":
                elapsed = int(time.time() - float(task["started_at"]))
                if elapsed >= 60:
                    parts.append("已进行 %d 分钟" % (elapsed // 60))
            if task.get("error"):
                parts.append(str(task["error"]))
            items.append(
                {
                    "component": "VListItem",
                    "props": {
                        "title": task["file_name"],
                        "subtitle": " · ".join(p for p in parts if p),
                        "prepend-icon": icon,
                    },
                }
            )
        if not items:
            items.append(
                {
                    "component": "VListItem",
                    "props": {
                        "title": "暂无同步任务",
                        "subtitle": "启用插件并等待一轮同步, 或在配置页勾选立即运行一次",
                        "prepend-icon": "mdi-information",
                    },
                }
            )
        task_card = {
            "component": "VCard",
            "props": {"variant": "outlined"},
            "content": [
                {"component": "VCardTitle", "props": {"text": "同步任务"}},
                {"component": "VList", "content": items},
            ],
        }
        return [header, task_card]
