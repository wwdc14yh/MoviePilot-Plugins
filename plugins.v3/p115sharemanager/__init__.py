"""P115-ShareManager: 115 网盘剧集完结自动分享插件 (MoviePilot V3)。

v0.1.0:
- 多任务监听 115 路径, TMDB 判完结 (按季/按整剧两档, 配置项切换),
  延迟分享 (洗板时间), 复制到 115 临时路径并英文重命名, 创建长期
  分享 (固定码 wwdc), share_snap 回读校验, TG 频道推送, 删临时
  (60 秒后, 已验证不影响分享), 立即删源文件夹 (进回收站)。
- 115 登录: 平台可选扫码 (p115qrcode) + 手动粘贴 Cookie 兜底。
- TMDB: 宿主 chain.tmdb_info 优先, 直连 API 兜底 (需 tmdb_api_key)。
"""
from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
import uuid
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
        chain = None

        def get_data_path(self):
            if self._data_path_override:
                return Path(self._data_path_override)
            return Path.cwd() / ".p115share_data"

        def update_config(self, config):
            self._saved_config = config
            return True

        def post_message(self, *args, **kwargs):
            return None

try:
    from app.sdk.logging import logger
except Exception:  # pragma: no cover
    import logging

    logger = logging.getLogger("P115ShareManager")

try:
    from .config import (COMPLETION_RULE_TITLES, DEFAULT_CRON,
                         _GLOBAL_FIELDS, _as_bool_or_none, ShareConfig,
                         ShareTask, validate_cron)
    from .p115_client import P115ClientWrapper, P115Error
    from .share_engine import ShareEngine
    from .store import ShareStore
    from .tmdb import TmdbClient
except ImportError:  # 直接以顶层模块加载时
    from config import (COMPLETION_RULE_TITLES, DEFAULT_CRON,
                        _GLOBAL_FIELDS, _as_bool_or_none, ShareConfig,
                        ShareTask, validate_cron)
    from p115_client import P115ClientWrapper, P115Error
    from share_engine import ShareEngine
    from store import ShareStore
    from tmdb import TmdbClient

# 敏感字段在 /status 回显时打码; 保存时收到 "******" 视为未改动
_MASKED = "******"
_SECRET_FIELDS = ("tg_bot_token", "tmdb_api_key", "recycle_password")

# 扫码登录平台 (p115qrcode.AVAILABLE_APPS 的子集)
QR_PLATFORMS = [
    {"value": "web", "title": "网页端 (115生活)"},
    {"value": "ios", "title": "iOS (115生活)"},
    {"value": "android", "title": "安卓 (115生活)"},
    {"value": "ipad", "title": "iPad (115生活)"},
    {"value": "tv", "title": "安卓电视 (115生活)"},
    {"value": "wechatmini", "title": "微信小程序 (115生活)"},
]
QR_SESSION_TTL = 600  # 扫码会话有效期 (秒)


def _mask_config(data):
    data = dict(data)
    for key in _SECRET_FIELDS:
        if data.get(key):
            data[key] = _MASKED
    return data


class P115ShareManager(_PluginBase):
    """115 剧集完结自动分享插件主类。"""

    plugin_name = "115 剧集分享管家"
    plugin_desc = "监听 115 网盘剧集, TMDB 判完结后自动复制到临时路径、" \
        "英文重命名、创建长期分享并推送到 Telegram 频道, 随后按配置删除或保留源文件夹。"
    plugin_icon = "P115ShareManager.png"
    plugin_version = "0.1.10"
    plugin_author = "Hu"
    author_url = ""
    plugin_config_prefix = "p115sharemanager_"
    plugin_order = 60
    auth_level = 1

    _config: ShareConfig = None
    _store: ShareStore = None
    _client: P115ClientWrapper = None
    _tmdb: TmdbClient = None
    _engine: ShareEngine = None
    _qr_sessions: dict = {}

    # ---------- 生命周期 ----------

    def init_plugin(self, config: dict | None = None) -> None:
        """读取配置, 建立本次运行状态; 必须可重复调用。"""
        self.stop_service()
        self._config = ShareConfig.from_dict(config or {})
        if not self._config.enabled:
            return
        db_path = self.get_data_path() / "p115sharemanager.db"
        self._store = ShareStore(db_path)
        self._tmdb = TmdbClient(
            chain=getattr(self, "chain", None),
            api_key=self._config.tmdb_api_key,
            api_domain=self._config.tmdb_api_domain,
            language=self._config.tmdb_language,
            logger=logger,
            proxy_url=self._config.proxy_url)
        self._init_115_client()
        self._engine = ShareEngine(
            self._store, self._client, self._config, self._tmdb,
            logger=logger, notify=self._send_tg)
        if self._config.onlyonce:
            self._config.onlyonce = False
            saved = self._config.to_dict()
            self.update_config(saved)
            self._run_once_async()

    def _init_115_client(self):
        """按 Cookie 文件初始化 115 客户端 (无 Cookie 时为 None)。"""
        cookie_file = self.get_data_path() / "115-cookies.txt"
        if not cookie_file.exists():
            self._client = None
            return
        try:
            self._client = P115ClientWrapper(cookie_file, logger=logger)
            self._client.debug = bool(
                self._config and self._config.debug_logging)
            if not self._client.is_logged_in():
                self._client = None
        except Exception as exc:
            logger.warning("[P115-ShareManager] 115 客户端初始化失败: %s",
                           exc)
            self._client = None

    def _run_once_async(self, task_id=None):
        """立即扫描一次: 直接开守护线程跑, 不走宿主一次性任务。
        宿主一次性任务 (add_plugin_once_job) 只是登记, 实际由
        调度器按约 15 分钟的周期处理, 点了「立即扫描」也要等
        一个周期才跑 (实测 12:13 登记、12:28 才开始); 守护线程
        点下即跑。引擎自带锁, 并发扫描会被跳过, 不会重复跑。
        顺带修一个附带问题: 宿主一次性任务调 run_scan 时不带
        task_id, 任务级「立即扫描」实际会扫全部任务; 线程方式
        能正确传 task_id, 只扫点的那个任务。"""
        threading.Thread(target=self.run_scan,
                         kwargs={"task_id": task_id},
                         daemon=True).start()

    def get_state(self) -> bool:
        return bool(self._config and self._config.enabled)

    def stop_service(self) -> None:
        if self._engine is not None:
            try:
                self._engine.request_stop()
            except Exception:
                pass
        if self._store is not None:
            try:
                self._store.close()
            except Exception:
                pass
            self._store = None
        self._engine = None
        self._client = None
        self._tmdb = None

    # ---------- 扫描入口 ----------

    def run_scan(self, task_id=None):
        """执行一轮扫描 (全部任务, 或指定 task_id 的单个任务)。"""
        if self._engine is None:
            return {"skipped_run": True, "reason": "plugin not initialized"}
        return self._engine.run_once(task_id=task_id)

    # ---------- Vue 前端 (模块联邦) ----------

    def get_render_mode(self):
        """Vue 联邦渲染: 产物在 dist/assets (remoteEntry.js)。"""
        return "vue", "dist/assets"

    def get_sidebar_nav(self) -> list[dict[str, Any]]:
        """侧栏全页入口: 分享总览页 (AppPage 组件)。"""
        if not self.get_state():
            return []
        return [
            {
                "nav_key": "main",
                "title": "115 分享管家",
                "icon": "mdi-share-variant",
                "section": "organize",
                "permission": "manage",
                "order": 60,
            }
        ]

    # ---------- 定时服务 ----------

    def get_service(self) -> list[dict[str, Any]]:
        """周期扫描服务, 由宿主调度器管理 (每任务独立 cron)。"""
        if not self.get_state() or self._config is None:
            return []
        from apscheduler.triggers.cron import CronTrigger

        services = []
        for task in self._config.tasks:
            if not task.enabled:
                continue
            cron = task.effective_cron(self._config.cron)
            try:
                trigger = CronTrigger.from_crontab(cron)
            except Exception as exc:
                logger.warning(
                    "[P115-ShareManager] 任务 %s 的 cron %s 非法 (%s), "
                    "用全局默认 %s",
                    task.name, cron, exc, DEFAULT_CRON)
                trigger = CronTrigger.from_crontab(DEFAULT_CRON)
            services.append(
                {
                    "id": "P115ShareManager.Scan.%s" % task.id,
                    "name": "115 剧集分享扫描 - %s" % (task.name or task.id),
                    "trigger": trigger,
                    "func": self.run_scan,
                    "kwargs": {"task_id": task.id},
                }
            )
        return services

    # ---------- 远程命令 ----------

    def _handle_plugin_action(self, event) -> None:
        """处理 PluginAction 事件, 只响应本插件的 /p115share 动作。"""
        event_data = getattr(event, "event_data", None) or {}
        if isinstance(event_data, dict) and event_data.get("action") != "p115share_run":
            return
        if not self.get_state() or self._engine is None:
            logger.warning("[P115-ShareManager] /p115share 已触发, 但插件未启用或未初始化")
            return
        logger.info("[P115-ShareManager] /p115share 触发一次扫描")
        self._run_once_async()
        post = getattr(self, "post_message", None)
        if callable(post):
            try:
                post(title="P115-ShareManager", text="已触发一次扫描, 进度见插件分享页。")
            except Exception as exc:
                logger.warning("[P115-ShareManager] 发送触发确认失败: %s", exc)

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
        """注册远程命令 /p115share, 触发一次扫描。"""
        return [
            {
                "cmd": "/p115share",
                "event": EventType.PluginAction,
                "desc": "立即执行一次 115 剧集完结扫描",
                "category": "插件命令",
                "data": {"action": "p115share_run"},
            }
        ]

    # ---------- TG 推送 ----------

    def _send_tg(self, title, text, poster_url=""):
        """TG 推送: 优先宿主 post_message (复用 MoviePilot 的 bot);
        自带 Bot Token 时改走直连 Bot API。
        海报一律以图片发 (宿主 post_message 的 image 参数 / 直连
        sendPhoto), 不再把海报 URL 贴进正文。返回 (ok, error)。"""
        channel = self._config.tg_channel_chat_id if self._config else ""
        if not channel:
            return True, ""
        if self._config and self._config.tg_use_own_bot \
                and self._config.tg_bot_token:
            return self._send_tg_direct(title, text, poster_url)
        post = getattr(self, "post_message", None)
        if not callable(post):
            return False, "宿主 post_message 不可用, 请配自带 Bot Token"
        try:
            from app.schemas.types import MessageType, NotificationChannel
            kwargs = dict(channel=NotificationChannel.Telegram,
                          mtype=MessageType.Plugin, title=title,
                          text=text, userid=channel)
            if poster_url:
                try:
                    # 宿主支持 image 参数时以图片发海报
                    post(**dict(kwargs, image=poster_url))
                    return True, ""
                except TypeError:
                    # 宿主 post_message 不接受 image 参数: 退回纯文本
                    pass
                except Exception:
                    # 发图失败 (如海报 URL 拉不到): 同频道退回纯文本
                    pass
            post(**kwargs)
        except Exception:
            try:
                post(title=title, text=text)
            except Exception as exc:
                return False, str(exc)
        return True, ""

    def _send_tg_direct(self, title, text, poster_url=""):
        """直连 Telegram Bot API 发消息/海报。"""
        token = self._config.tg_bot_token
        channel = self._config.tg_channel_chat_id
        body = "%s\n%s" % (title, text)
        try:
            if poster_url:
                payload = {"chat_id": channel, "photo": poster_url,
                           "caption": body}
                self._tg_api("sendPhoto", payload)
            else:
                self._tg_api("sendMessage",
                             {"chat_id": channel, "text": body})
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def _tg_api(self, method, payload):
        url = "https://api.telegram.org/bot%s/%s" % (
            self._config.tg_bot_token, method)
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError("Telegram API 失败: %s" % result)

    # ---------- API ----------

    def get_api(self) -> list[dict[str, Any]]:
        return [
            {"path": "/status", "endpoint": self.api_status,
             "methods": ["GET"], "auth": "bear", "summary": "插件状态与任务概览"},
            {"path": "/jobs", "endpoint": self.api_jobs,
             "methods": ["GET"], "auth": "bear", "summary": "分享作业列表 (分页)"},
            {"path": "/history", "endpoint": self.api_history,
             "methods": ["GET"], "auth": "bear", "summary": "作业历史 (分页)"},
            {"path": "/scan_now", "endpoint": self.api_scan_now,
             "methods": ["POST"], "auth": "bear", "summary": "立即扫描一次"},
            {"path": "/share_now", "endpoint": self.api_share_now,
             "methods": ["POST"], "auth": "bear", "summary": "立即分享某个作业 (跳过延迟)"},
            {"path": "/retry", "endpoint": self.api_retry,
             "methods": ["POST"], "auth": "bear", "summary": "重试失败作业"},
            {"path": "/save_task", "endpoint": self.api_save_task,
             "methods": ["POST"], "auth": "bear", "summary": "新建或更新一个监听任务"},
            {"path": "/delete_task", "endpoint": self.api_delete_task,
             "methods": ["POST"], "auth": "bear", "summary": "删除一个监听任务"},
            {"path": "/save_global", "endpoint": self.api_save_global,
             "methods": ["POST"], "auth": "bear", "summary": "保存全局设置"},
            {"path": "/115_login_platforms",
             "endpoint": self.api_115_login_platforms,
             "methods": ["GET"], "auth": "bear", "summary": "可扫码登录的平台列表"},
            {"path": "/qrcode", "endpoint": self.api_qrcode,
             "methods": ["GET"], "auth": "bear", "summary": "生成扫码登录二维码"},
            {"path": "/qrcode_status", "endpoint": self.api_qrcode_status,
             "methods": ["GET"], "auth": "bear", "summary": "查询扫码状态"},
            {"path": "/115_status", "endpoint": self.api_115_status,
             "methods": ["GET"], "auth": "bear", "summary": "115 登录状态"},
            {"path": "/115_set_cookie", "endpoint": self.api_115_set_cookie,
             "methods": ["POST"], "auth": "bear", "summary": "手动粘贴 Cookie 登录"},
            {"path": "/115_logout", "endpoint": self.api_115_logout,
             "methods": ["POST"], "auth": "bear", "summary": "退出 115 登录"},
            {"path": "/tmdb_test", "endpoint": self.api_tmdb_test,
             "methods": ["GET"], "auth": "bear", "summary": "测试 TMDB 查询"},
        ]

    def _login_status(self):
        # 登录状态与插件开关无关: Cookie 只存在磁盘文件里, 禁用插件
        # 只停扫描、不删 Cookie。但 stop_service() 会丢掉内存里的
        # 115 客户端, init_plugin 禁用时又不再重建, 于是 _client
        # 为 None 时这里误报“登录已过期” (v0.1.5 前的 bug)。
        # 修正: _client 为空时按 Cookie 文件懒恢复, 再判断。
        if self._client is None:
            self._init_115_client()
        if self._client is None or not self._client.is_logged_in():
            return {"logged_in": False, "user_name": "",
                    "need_relogin": True, "last_error": "115 未登录"}
        try:
            info = self._client.login_info()
            return {"logged_in": True,
                    "user_name": info.get("user_name") or "",
                    "need_relogin": False, "last_error": ""}
        except P115Error as exc:
            return {"logged_in": False, "user_name": "",
                    "need_relogin": True, "last_error": str(exc)}

    def api_status(self):
        tasks = []
        if self._config:
            for task in self._config.tasks:
                tasks.append({
                    "id": task.id,
                    "name": task.name,
                    "watch_path": task.watch_path,
                    "enabled": task.enabled,
                    "cron": task.effective_cron(self._config.cron),
                    "delay_hours": task.effective_delay_hours(
                        self._config.delay_hours),
                    "delete_source": task.delete_source,
                    "delete_source_effective":
                        task.effective_delete_source(
                            self._config.delete_source),
                    "counts": (self._store.count_jobs(task.id)
                               if self._store else {}),
                })
        return {
            "enabled": self.get_state(),
            "login": self._login_status(),
            "tasks": tasks,
            "config": _mask_config(self._config.to_dict())
            if self._config else {},
        }

    def api_jobs(self, task_id: str = None, status: str = None,
                 limit: int = 20, offset: int = 0):
        if self._store is None:
            return {"jobs": [], "total": 0, "limit": int(limit),
                    "offset": int(offset)}
        jobs = self._store.list_jobs(
            task_id=task_id or None, status=status or None,
            limit=int(limit), offset=int(offset))
        counts = self._store.count_jobs(task_id or None)
        total = counts.get(status) if status else sum(counts.values())
        return {"jobs": jobs, "total": total, "limit": int(limit),
                "offset": int(offset)}

    def api_history(self, job_id: int = None, limit: int = 50,
                    offset: int = 0):
        if self._store is None:
            return {"items": [], "total": 0, "limit": int(limit),
                    "offset": int(offset)}
        items = self._store.list_history(
            job_id=job_id or None, limit=int(limit), offset=int(offset))
        total = self._store.count_history(job_id or None)
        return {"items": items, "total": total, "limit": int(limit),
                "offset": int(offset)}

    def api_scan_now(self, task_id: str = None):
        if self._engine is None:
            return {"ok": False, "error": "插件未启用"}
        self._run_once_async(task_id=task_id or None)
        return {"ok": True, "started": True}

    def api_share_now(self, job_id: int = 0, skip_delay: bool = True):
        if self._engine is None:
            return {"ok": False, "error": "插件未启用"}
        return self._engine.share_now(int(job_id), skip_delay=bool(skip_delay))

    def api_retry(self, job_id: int = 0):
        if self._engine is None:
            return {"ok": False, "error": "插件未启用"}
        return self._engine.retry_job(int(job_id))

    # ---------- 任务增删改 ----------

    def _persist_config(self):
        """把当前配置落盘并重新初始化插件。返回 {"ok": bool, "error": str}。"""
        saved = self._config.to_dict()
        try:
            self.update_config(saved)
        except Exception as exc:
            logger.error("[P115-ShareManager] 保存配置失败: %s", exc)
            return {"ok": False, "error": "保存配置失败: " + str(exc)}
        try:
            self.init_plugin(saved)
        except Exception as exc:
            logger.error("[P115-ShareManager] 重新初始化失败: %s", exc)
            return {"ok": False, "error": "配置已保存, 但重新初始化失败: " + str(exc)}
        return {"ok": True}

    def api_save_task(self, id: str = "", name: str = "",
                      watch_path: str = "", enabled: bool = True,
                      cron: str = "", delay_hours: int = None,
                      delete_source: str = ""):
        """新建任务 (无 id 或 id 不存在) 或更新已有任务 (id 命中)。
        参数必须是显式标量: 宿主把插件 API 注册为 FastAPI 路由,
        dict 参数和 **kwargs 都会被 FastAPI 判为参数不正确 (422)。
        delete_source: "global" (跟随全局) / "yes" / "no"。"""
        if self._config is None:
            return {"ok": False, "error": "插件未初始化"}
        if cron:
            ok, err = validate_cron(cron)
            if not ok:
                return {"ok": False, "error": err}
        data = {"id": id, "name": name, "enabled": enabled,
                "watch_path": watch_path, "cron": cron,
                "delay_hours": delay_hours,
                "delete_source": _as_bool_or_none(delete_source)}
        new_task = ShareTask.from_dict(data)
        if not new_task.watch_path:
            return {"ok": False, "error": "监听路径必填"}
        replaced = False
        for idx, existing in enumerate(self._config.tasks):
            if existing.id == new_task.id:
                self._config.tasks[idx] = new_task
                replaced = True
                break
        if not replaced:
            # 新建: 强制生成新 id, 绝不复用已有任务的 id/状态
            new_task.id = uuid.uuid4().hex[:12]
            self._config.tasks.append(new_task)
        res = self._persist_config()
        if not res.get("ok"):
            return res
        return {"ok": True, "task": new_task.to_dict(),
                "created": not replaced}

    def api_delete_task(self, task_id: str = ""):
        if self._config is None or not task_id:
            return {"ok": False, "error": "参数缺失"}
        before = len(self._config.tasks)
        self._config.tasks = [
            t for t in self._config.tasks if t.id != task_id
        ]
        if len(self._config.tasks) == before:
            return {"ok": False, "error": "任务不存在"}
        if self._store is not None:
            try:
                self._store.purge_task(task_id)
            except Exception as exc:
                logger.error("[P115-ShareManager] 清理任务记录失败: %s", exc)
        return self._persist_config()

    def api_save_global(self, enabled: bool = None, temp_path: str = None,
                        completion_rule: str = None, delay_hours: int = None,
                        cron: str = None, receive_code: str = None,
                        tg_enabled: bool = None,
                        tg_channel_chat_id: str = None,
                        tg_use_own_bot: bool = None,
                        tg_bot_token: str = None,
                        tmdb_api_key: str = None,
                        tmdb_api_domain: str = None,
                        tmdb_language: str = None,
                        max_retries: int = None,
                        history_retention_days: int = None,
                        failed_retention_days: int = None,
                        recycle_password: str = None,
                        onlyonce: bool = None,
                        debug_logging: bool = None,
                        proxy_url: str = None,
                        delete_source: bool = None,
                        share_interval_seconds: int = None):
        """保存全局设置: 只合并传入的全局字段, 任务列表原样保留。
        参数必须是显式标量 (原因同 api_save_task)。敏感字段收到
        "******" 视为未改动。"""
        payload = {
            "enabled": enabled, "temp_path": temp_path,
            "completion_rule": completion_rule, "delay_hours": delay_hours,
            "cron": cron, "receive_code": receive_code,
            "tg_enabled": tg_enabled,
            "tg_channel_chat_id": tg_channel_chat_id,
            "tg_use_own_bot": tg_use_own_bot, "tg_bot_token": tg_bot_token,
            "tmdb_api_key": tmdb_api_key,
            "tmdb_api_domain": tmdb_api_domain,
            "tmdb_language": tmdb_language, "max_retries": max_retries,
            "history_retention_days": history_retention_days,
            "failed_retention_days": failed_retention_days,
            "recycle_password": recycle_password, "onlyonce": onlyonce,
            "debug_logging": debug_logging, "proxy_url": proxy_url,
            "delete_source": delete_source,
            "share_interval_seconds": share_interval_seconds,
        }
        payload = {k: v for k, v in payload.items()
                   if v is not None and v != _MASKED}
        if self._config is None:
            self._config = ShareConfig.from_dict({})
        if payload.get("cron"):
            ok, err = validate_cron(payload["cron"])
            if not ok:
                return {"ok": False, "error": err}
        if payload.get("completion_rule") not in (None, "season", "show"):
            return {"ok": False, "error": "完结检查规则只能是 season 或 show"}
        data = self._config.to_dict()
        for key in _GLOBAL_FIELDS:
            if key in payload:
                data[key] = payload[key]
        self._config = ShareConfig.from_dict(data)
        res = self._persist_config()
        if not res.get("ok"):
            return res
        if self._client is not None:
            self._client.debug = bool(self._config.debug_logging)
        if self._tmdb is not None:
            self._tmdb.set_proxy(self._config.proxy_url)
        return {"ok": True, "config": _mask_config(self._config.to_dict())}

    # ---------- 115 登录 ----------

    def api_115_login_platforms(self):
        return QR_PLATFORMS

    def api_qrcode(self, platform: str = "web"):
        """生成扫码登录二维码。返回 {ok, token, qrcode, qrcode_url}。
        qrcode 为 base64 PNG (需 qrcode 库), 否则为空、前端用
        qrcode_url 显示链接。"""
        if self._client is None:
            self._init_115_client()
        if self._client is None:
            cookie_file = self.get_data_path() / "115-cookies.txt"
            self._client = P115ClientWrapper(cookie_file, logger=logger)
            self._client.debug = bool(
                self._config and self._config.debug_logging)
        if platform not in [p["value"] for p in QR_PLATFORMS]:
            platform = "web"
        try:
            session = self._client.qrcode_start(platform)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        token = uuid.uuid4().hex[:12]
        self._qr_sessions[token] = {
            "uid": session["uid"], "time": session["time"],
            "sign": session["sign"], "app": platform,
            "created": time.time()}
        qrcode_png = self._make_qrcode_png(session["qrcode_url"])
        return {"ok": True, "token": token,
                "qrcode": qrcode_png,
                "qrcode_url": session["qrcode_url"],
                "expires_in": QR_SESSION_TTL}

    @staticmethod
    def _make_qrcode_png(url):
        try:
            import base64
            import io

            import qrcode

            img = qrcode.make(url)
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            return "data:image/png;base64," + base64.b64encode(
                buf.getvalue()).decode("ascii")
        except Exception:
            return ""

    def api_qrcode_status(self, token: str = ""):
        session = self._qr_sessions.get(token or "")
        if not session:
            return {"status": "expired", "logged_in": False}
        if time.time() - session["created"] > QR_SESSION_TTL:
            self._qr_sessions.pop(token, None)
            return {"status": "expired", "logged_in": False}
        if self._client is None:
            return {"status": "waiting", "logged_in": False}
        try:
            status = self._client.qrcode_status(session)
        except Exception as exc:
            return {"status": "waiting", "logged_in": False,
                    "error": str(exc)}
        if status != "confirmed":
            return {"status": status, "logged_in": False}
        try:
            info = self._client.qrcode_result(session)
        except Exception as exc:
            # v0.1.0 的 bug: 这里回了 status=confirmed + logged_in=False,
            # 前端按 confirmed 判成功, 于是“扫码登录成功”和“登录已过期”
            # 同时出现。失败必须回 failed, 前端才显示真实错误。
            self._qr_sessions.pop(token, None)
            return {"status": "failed", "logged_in": False,
                    "error": "取回登录信息失败: %s" % exc}
        self._qr_sessions.pop(token, None)
        if self._engine is not None:
            self._engine.client = self._client
        return {"status": "confirmed", "logged_in": True,
                "user_name": (info.get("user_name") or "") if isinstance(info, dict) else ""}

    def api_115_status(self):
        return self._login_status()

    def api_115_set_cookie(self, cookie: str = ""):
        """手动粘贴 Cookie 登录 (扫码不可用时的兜底)。"""
        cookie = (cookie or "").strip()
        if not cookie:
            return {"ok": False, "error": "Cookie 为空"}
        cookie_file = self.get_data_path() / "115-cookies.txt"
        wrapper = P115ClientWrapper(cookie_file, logger=logger)
        try:
            info = wrapper.save_cookie(cookie)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        self._client = wrapper
        if self._engine is not None:
            self._engine.client = wrapper
        return {"ok": True, "logged_in": True,
                "user_name": (info.get("user_name") or "")
                if isinstance(info, dict) else ""}

    def api_115_logout(self):
        cookie_file = self.get_data_path() / "115-cookies.txt"
        try:
            cookie_file.unlink(missing_ok=True)
        except Exception:
            pass
        self._client = None
        if self._engine is not None:
            self._engine.client = None
        return {"ok": True}

    def api_tmdb_test(self, tmdbid: int = 0):
        """测试 TMDB 查询: 宿主优先, 直连兜底。"""
        if self._tmdb is None:
            return {"ok": False, "error": "插件未启用"}
        try:
            info, via = self._tmdb.get_show(int(tmdbid))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        seasons = []
        for season in info.get("seasons") or []:
            seasons.append({
                "season_number": season.get("season_number"),
                "episode_count": season.get("episode_count"),
                "air_date": season.get("air_date") or "",
            })
        return {"ok": True, "via": via, "status": info.get("status") or "",
                "en_title": info.get("en_title")
                or info.get("original_name") or "",
                "seasons": seasons}

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
                        "插件开关",
                        "115 剧集完结自动分享",
                        row(
                            col(switch("enabled", "启用插件"), md=6),
                            col(switch("onlyonce", "保存后立即扫描一次"), md=6),
                        ),
                        alert(
                            "115 登录请在插件页面扫码 (可选登录平台) 或粘贴"
                            " Cookie; 监听任务在插件页面新建, 不在表单里。"
                        ),
                    ),
                    card(
                        "分享设置",
                        "临时路径、完结规则与延迟分享",
                        row(
                            col(
                                text(
                                    "temp_path",
                                    "115 临时分享路径",
                                    hint="待分享文件临时复制到这里, 分享后删掉",
                                    placeholder="/115分享暂存",
                                )
                            ),
                            col(
                                {
                                    "component": "VSelect",
                                    "props": {
                                        "model": "completion_rule",
                                        "label": "完结检查规则",
                                        "hint": "按季: 某季集数对上即分享该季; 按整剧: status=Ended 且全部季对上才整剧分享",
                                        "items": [
                                            {"title": "按季完结分享",
                                             "value": "season"},
                                            {"title": "按整剧完结分享",
                                             "value": "show"},
                                        ],
                                    },
                                }
                            ),
                        ),
                        row(
                            col(
                                text(
                                    "delay_hours",
                                    "延迟分享 (小时)",
                                    hint="完结后等多久再分享 (洗板时间)",
                                    type_="number",
                                )
                            ),
                            col(
                                text(
                                    "cron",
                                    "全局默认检查频率 (cron)",
                                    hint="每任务可覆盖; 一天一次如 0 8 * * *",
                                    placeholder="0 */6 * * *",
                                )
                            ),
                        ),
                        row(
                            col(
                                text(
                                    "receive_code",
                                    "分享提取码",
                                    hint="固定提取码, 默认 wwdc",
                                    placeholder="wwdc",
                                )
                            ),
                            col(
                                text(
                                    "max_retries",
                                    "失败最大重试次数",
                                    type_="number",
                                )
                            ),
                        ),
                        row(
                            col(
                                text(
                                    "share_interval_seconds",
                                    "批量分享间隔 (秒)",
                                    hint="两次创建分享之间至少间隔多少秒, 防 115 风控; 0 = 不延迟",
                                    type_="number",
                                ),
                                md=6,
                            ),
                        ),
                        row(
                            col(
                                switch(
                                    "delete_source",
                                    "分享后删除源文件",
                                    hint="关 = 分享成功后保留源文件, 只删临时目录; 每个任务可单独覆盖",
                                ),
                                md=6,
                            ),
                            col(
                                switch(
                                    "debug_logging",
                                    "详细日志 (排查用)",
                                    hint="打开后每次 115 调用、每季完结判定都会记到 MoviePilot 日志; 平时建议关",
                                ),
                                md=6,
                            ),
                        ),
                    ),
                    card(
                        "Telegram 推送",
                        "分享成功后推送到频道",
                        row(
                            col(switch("tg_enabled", "启用 TG 推送"), md=6),
                            col(
                                text(
                                    "tg_channel_chat_id",
                                    "频道 Chat ID",
                                    hint="频道 ID (如 -1001234567890)",
                                )
                            ),
                        ),
                        row(
                            col(switch("tg_use_own_bot", "用自带 Bot (可发海报)"), md=6),
                            col(
                                text(
                                    "tg_bot_token",
                                    "自带 Bot Token",
                                    hint="不用自带 Bot 时复用 MoviePilot 的 Bot",
                                    type_="password",
                                )
                            ),
                        ),
                    ),
                    card(
                        "TMDB 兜底",
                        "宿主自带 TMDB 优先; 宿主查不到时走直连 (需 Key)",
                        row(
                            col(
                                text(
                                    "tmdb_api_key",
                                    "TMDB API Key",
                                    hint="留空则只用宿主 TMDB",
                                    type_="password",
                                )
                            ),
                            col(
                                text(
                                    "tmdb_api_domain",
                                    "TMDB API 域名",
                                    placeholder="api.themoviedb.org/3",
                                )
                            ),
                        ),
                        row(
                            col(
                                text(
                                    "proxy_url",
                                    "TMDB 直连代理地址",
                                    hint="仅 TMDB 直连兜底时走代理; 115 网盘调用一律直连, 不走代理; 留空 = 直连",
                                    placeholder="http://192.168.2.2:7890",
                                )
                            ),
                        ),
                        row(
                            col(
                                text(
                                    "history_retention_days",
                                    "成功历史保留 (天)",
                                    type_="number",
                                )
                            ),
                            col(
                                text(
                                    "recycle_password",
                                    "回收站清空密码 (6 位, 可选)",
                                    hint="默认不清空回收站",
                                    type_="password",
                                )
                            ),
                        ),
                    ),
                ],
            }
        ]
        return form, ShareConfig().to_dict()

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
        counts = self._store.count_jobs()
        overview = (
            "监听中 %d · 待延迟 %d · 已分享 %d · 失败 %d"
            % (counts.get("watching", 0), counts.get("pending_delay", 0),
               counts.get("done", 0), counts.get("failed", 0))
        )
        header = {
            "component": "VCard",
            "props": {"variant": "tonal", "class": "mb-4"},
            "content": [
                {"component": "VCardTitle",
                 "props": {"text": "115 剧集分享管家"}},
                {"component": "VCardSubtitle", "props": {"text": overview}},
            ],
        }
        items = []
        for job in self._store.list_jobs(limit=20):
            status = job["status"]
            label = {
                "watching": "监听中", "pending_delay": "待延迟分享",
                "ready": "待分享", "copying": "复制中", "sharing": "分享中",
                "shared": "已分享待推送", "done": "已分享", "failed": "失败",
                "unknown": "未知",
            }.get(status, status)
            parts = [label]
            if job["season_number"] == -1:
                parts.append("整剧 %d/%d 集" % (job["local_count"],
                                               job["tmdb_count"]))
            else:
                parts.append("S%02d %d/%d 集" % (
                    job["season_number"], job["local_count"],
                    job["tmdb_count"]))
            if job.get("share_url"):
                parts.append(job["share_url"])
            if job.get("last_error"):
                parts.append(str(job["last_error"]))
            items.append(
                {
                    "component": "VListItem",
                    "props": {
                        "title": "%s%s" % (
                            job["show_name"],
                            "" if job["season_number"] == -1
                            else " S%02d" % job["season_number"]),
                        "subtitle": " · ".join(parts),
                        "prepend-icon": "mdi-share-variant",
                    },
                }
            )
        if not items:
            items.append(
                {
                    "component": "VListItem",
                    "props": {
                        "title": "暂无分享作业",
                        "subtitle": "启用插件并等待一轮扫描, 或在配置页勾选立即扫描一次",
                        "prepend-icon": "mdi-information",
                    },
                }
            )
        job_card = {
            "component": "VCard",
            "props": {"variant": "outlined"},
            "content": [
                {"component": "VCardTitle", "props": {"text": "分享作业"}},
                {"component": "VList", "content": items},
            ],
        }
        return [header, job_card]
