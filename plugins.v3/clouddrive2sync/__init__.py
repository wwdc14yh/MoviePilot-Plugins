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
    from .config import SyncConfig, SyncTask
    from .store import SyncStore
    from .sync_engine import SyncEngine
except ImportError:  # 直接以顶层模块加载时
    from cd2_client import Cd2Error, Cd2GrpcClient
    from config import SyncConfig, SyncTask
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
    plugin_version = "0.6.3"
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
            self._config.cd2_address,
            token=self._config.cd2_token,
            copy_timeout=max(30, int(self._config.copy_timeout_seconds or 180)),
            logger=logger,
        )
        self._client.debug_logging = bool(self._config.debug_logging)
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
        """释放客户端和数据库连接; 可重复调用。

        若正好有一轮同步在跑, 先通知引擎收尾并短暂等待 (最多 3 秒),
        避免在跑的轮次被硬关连接/通道打断; 等不到也不强等 ——
        存储层会自动重开连接, 客户端通道关闭会自动重连重试。
        """
        engine = self._engine
        acquired = False
        if engine is not None:
            try:
                engine.request_stop()
                acquired = engine._lock.acquire(timeout=3)
            except Exception:
                acquired = False
        try:
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
        finally:
            if acquired and engine is not None:
                engine._lock.release()

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

        services = []
        for task in self._config.tasks:
            if not task.enabled:
                continue
            services.append(
                {
                    "id": "CloudDrive2Sync.Sync.%s" % task.id,
                    "name": "CloudDrive2 网盘同步 - %s" % (task.name or task.id),
                    "trigger": IntervalTrigger(
                        minutes=max(1, int(task.interval_minutes or 30))
                    ),
                    "func": self.run_sync,
                    "kwargs": {"task_id": task.id},
                }
            )
        services.append(
            {
                "id": "CloudDrive2Sync.Poll",
                "name": "CloudDrive2 复制任务状态轮询对账",
                "trigger": IntervalTrigger(
                    seconds=max(
                        5, int(self._config.copy_poll_interval_seconds
                               or 10)
                    )
                ),
                "func": self.run_poll,
                "kwargs": {},
            }
        )
        return services

    def run_poll(self):
        """后台轮询对账入口 (宿主调度器周期调用, 间隔读全局配置)。"""
        if self._engine is None:
            return {"skipped": True, "reason": "plugin not initialized"}
        return self._engine.poll_copy_tasks()

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
            {
                "path": "/save_task",
                "endpoint": self.api_save_task,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "新建或更新一个任务 (直接落盘配置)",
            },
            {
                "path": "/delete_task",
                "endpoint": self.api_delete_task,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "删除一个任务 (直接落盘配置)",
            },
            {
                "path": "/save_global",
                "endpoint": self.api_save_global,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "保存全局设置 (直接落盘配置)",
            },
            {
                "path": "/settle",
                "endpoint": self.api_settle,
                "methods": ["POST"],
                "auth": "bear",
                "summary": "快速结算 (只按 CopyTask 状态更新同步中/失败项, 不跑整轮)",
            },
        ]

    def api_settle(self):
        """快速结算: 页面打开/刷新时调用, 让状态及时跟上 CD2。"""
        if self._engine is None:
            return {"ok": False, "error": "插件未启用"}
        import time as _time

        now = _time.time()
        if now - getattr(self, "_last_settle_ts", 0) < 5:
            return {"ok": True, "skipped": "throttled"}
        self._last_settle_ts = now
        return {"ok": True, "settled": self._engine.settle_only()}

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
                        "max_concurrent_sync": task.max_concurrent_sync,
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
            "config": self._config.to_dict() if self._config else {},
        }

    def api_files(self, task_id: str = None, status: str = None,
                  limit: int = 20, offset: int = 0):
        """服务端分页: 返回 {files, total, limit, offset}, 避免长列表卡顿。"""
        if self._store is None:
            return {"files": [], "total": 0, "limit": int(limit),
                    "offset": int(offset)}
        rows = self._store.list_states(
            task_id=task_id or None, status=status or None,
            limit=int(limit), offset=int(offset),
        )
        total = self._store.count_states_filtered(
            task_id=task_id or None, status=status or None
        )
        for row in rows:
            row["file_name"] = str(row.get("source_path") or "").rstrip(
                "/"
            ).rsplit("/", 1)[-1]
        return {"files": rows, "total": total, "limit": int(limit),
                "offset": int(offset)}

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

    # ---------- 任务增删改 (总览页直接操作, 不绕配置页) ----------

    def _persist_config(self):
        """把当前配置落盘并重新初始化插件 (任务列表以此为准)。

        返回 {"ok": bool, "error": str}; 失败原因要回给前端,
        不能让异常冒成 500 只显示一句"失败"。
        """
        saved = self._config.to_dict()
        try:
            self.update_config(saved)
        except Exception as exc:
            logger.error("[CloudDrive2Sync] 保存配置失败: %s", exc)
            return {"ok": False, "error": "保存配置失败: " + str(exc)}
        try:
            self.init_plugin(saved)
        except Exception as exc:
            logger.error("[CloudDrive2Sync] 重新初始化失败: %s", exc)
            return {"ok": False, "error": "配置已保存, 但重新初始化失败: " + str(exc)}
        return {"ok": True}

    def api_save_task(self, id: str = "", name: str = "", enabled: bool = True,
                      mode: str = "sync", source_path: str = "",
                      target_path: str = "", conflict_policy: str = "",
                      delete_empty_dirs: bool = False,
                      max_concurrent_sync: int = 1,
                      interval_minutes: int = 30):
        """新建任务 (无 id 或 id 不存在) 或更新已有任务 (id 命中)。

        参数必须是显式标量: 宿主把插件 API 注册为 FastAPI 路由,
        dict 参数和 **kwargs 都会被 FastAPI 判为参数不正确 (422)。
        前端一律用查询参数提交, 与 run_once/delete_task 等接口一致。
        """
        data = {
            "id": id, "name": name, "enabled": enabled, "mode": mode,
            "source_path": source_path, "target_path": target_path,
            "conflict_policy": conflict_policy,
            "delete_empty_dirs": delete_empty_dirs,
            "max_concurrent_sync": max_concurrent_sync,
            "interval_minutes": interval_minutes,
        }
        if self._config is None:
            return {"ok": False, "error": "插件未初始化"}
        new_task = SyncTask.from_dict(data)
        if not new_task.source_path or not new_task.target_path:
            return {"ok": False, "error": "源目录和目标目录必填"}
        replaced = False
        for idx, existing in enumerate(self._config.tasks):
            if existing.id == new_task.id:
                self._config.tasks[idx] = new_task
                replaced = True
                break
        if not replaced:
            # 新建: 强制生成新 id, 绝不复用已有任务的 id/状态
            import uuid as _uuid

            new_task.id = _uuid.uuid4().hex[:12]
            self._config.tasks.append(new_task)
        res = self._persist_config()
        if not res.get("ok"):
            return res
        return {"ok": True, "task": new_task.to_dict(), "created": not replaced}

    def api_delete_task(self, task_id: str = ""):
        if self._config is None or not task_id:
            return {"ok": False, "error": "参数缺失"}
        before = len(self._config.tasks)
        self._config.tasks = [
            t for t in self._config.tasks if t.id != task_id
        ]
        if len(self._config.tasks) == before:
            return {"ok": False, "error": "任务不存在"}
        # 先取消该任务在 CD2 里进行中的复制任务 (按需用 CancelCopyTask)
        if self._store is not None and self._client is not None:
            try:
                from .cd2_client import parent_and_name as _pan

                for st in self._store.list_states_by_status(
                        "copying", task_id=task_id):
                    tdir, _ = _pan(st["target_path"])
                    try:
                        self._client.cancel_copy_task(
                            st["source_path"], tdir)
                    except Exception as exc:
                        logger.info(
                            "[CloudDrive2Sync] 取消复制任务失败 %s: %s",
                            st["source_path"], exc)
            except Exception as exc:
                logger.info("[CloudDrive2Sync] 删除任务时取消复制失败: %s",
                            exc)
        # 连带清掉该任务的同步状态与历史记录 (已传到目标端的文件不删)
        if self._store is not None:
            try:
                self._store.purge_task(task_id)
            except Exception as exc:
                logger.error("[CloudDrive2Sync] 清理任务记录失败: %s", exc)
        return self._persist_config()

    def api_save_global(self, enabled: bool = None, cd2_address: str = None,
                        cd2_token: str = None,
                        max_retries: int = None,
                        pending_timeout_hours: int = None,
                        copy_timeout_seconds: int = None,
                        history_retention_days: int = None,
                        failed_retention_days: int = None,
                        state_tombstone_days: int = None,
                        onlyonce: bool = None,
                        debug_logging: bool = None,
                        copy_poll_interval_seconds: int = None):
        """保存全局设置: 只合并传入的全局字段, 任务列表原样保留。

        参数必须是显式标量 (原因同 api_save_task: FastAPI 校验)。
        让插件页面 (含侧边栏整页) 自带全局设置入口, 不依赖宿主跳转。
        """
        payload = {
            "enabled": enabled, "cd2_address": cd2_address,
            "cd2_token": cd2_token,
            "max_retries": max_retries,
            "pending_timeout_hours": pending_timeout_hours,
            "copy_timeout_seconds": copy_timeout_seconds,
            "history_retention_days": history_retention_days,
            "failed_retention_days": failed_retention_days,
            "state_tombstone_days": state_tombstone_days,
            "onlyonce": onlyonce,
            "debug_logging": debug_logging,
            "copy_poll_interval_seconds": copy_poll_interval_seconds,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        if self._config is None:
            self._config = SyncConfig.from_dict({})
        data = self._config.to_dict()
        from .config import _GLOBAL_FIELDS

        for key in _GLOBAL_FIELDS:
            if key in payload:
                data[key] = payload[key]
        self._config = SyncConfig.from_dict(data)
        res = self._persist_config()
        if not res.get("ok"):
            return res
        return {"ok": True, "config": self._config.to_dict()}

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
                                    "copy_poll_interval_seconds",
                                    "复制任务轮询间隔 (秒)",
                                    hint="后台多久拉一次 CD2 复制任务状态与本地对账",
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
                            "复制提交后由后台轮询对账确认完成 (间隔见“复制"
                            "任务轮询间隔”), 没传完的留在“同步中”, 不会误判"
                            "失败, 也不会重复提交。"
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
