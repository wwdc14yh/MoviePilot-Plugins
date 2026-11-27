"""P115-ShareManager 配置模型 (v0.1)。

全局配置 (115 临时路径/完结规则/延迟/TG/TMDB 兜底/重试) + 任务列表:
每个任务 = 一个监听路径 + 独立 cron 检查频率 + 可覆盖的延迟。

完结检查规则 (completion_rule, 见 design-v0.2 §3):
- season (默认): 某季 115 已有集号集合 == TMDB 该季已播集号集合即分享该季,
  不要求整剧 Ended;
- show (严格): 整剧 status=Ended 且全部季集数都对上才整剧分享。
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field

COMPLETION_RULES = ("season", "show")
COMPLETION_RULE_TITLES = {
    "season": "按季完结分享",
    "show": "按整剧完结分享",
}

DEFAULT_CRON = "0 */6 * * *"  # 每 6 小时

_GLOBAL_FIELDS = (
    "enabled",
    "temp_path",
    "completion_rule",
    "delay_hours",
    "cron",
    "receive_code",
    "tg_enabled",
    "tg_channel_chat_id",
    "tg_use_own_bot",
    "tg_bot_token",
    "tmdb_api_key",
    "tmdb_api_domain",
    "tmdb_language",
    "max_retries",
    "history_retention_days",
    "failed_retention_days",
    "recycle_password",
    "onlyonce",
    "debug_logging",
    "proxy_url",
    "delete_source",
    "share_interval_seconds",
)

_GLOBAL_DEFAULTS = {
    "enabled": False,
    "temp_path": "/115分享暂存",
    "completion_rule": "season",
    "delay_hours": 48,
    "cron": DEFAULT_CRON,
    "receive_code": "wwdc",
    "tg_enabled": True,
    "tg_channel_chat_id": "",
    "tg_use_own_bot": False,
    "tg_bot_token": "",
    "tmdb_api_key": "",
    "tmdb_api_domain": "api.themoviedb.org/3",
    "tmdb_language": "zh-CN",
    "max_retries": 3,
    "history_retention_days": 90,
    "failed_retention_days": 90,
    "recycle_password": "",
    "onlyonce": False,
    "debug_logging": False,
    "proxy_url": "",
    "delete_source": True,
    "share_interval_seconds": 60,
}

_TASK_FIELDS = (
    "id",
    "name",
    "enabled",
    "watch_path",
    "cron",
    "delay_hours",
    "delete_source",
    "completion_rule",
)

# cron 每段取值范围: 分 时 日 月 周
_CRON_RANGES = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
_FIELD_RE = re.compile(r"^(\*|(\d+)(-\d+)?)(/\d+)?$")


def validate_cron(expr):
    """校验 5 段 cron 表达式。优先用宿主的 CronTrigger (最权威),
    本地无 apscheduler 时用自有校验。返回 (ok, error)。"""
    expr = (expr or "").strip()
    if not expr:
        return False, "cron 表达式为空"
    try:
        from apscheduler.triggers.cron import CronTrigger

        CronTrigger.from_crontab(expr)
        return True, ""
    except ImportError:
        pass
    except Exception as exc:
        return False, "cron 表达式非法: %s" % exc
    parts = expr.split()
    if len(parts) != 5:
        return False, "cron 表达式应为 5 段 (分 时 日 月 周)"
    for idx, part in enumerate(parts):
        lo, hi = _CRON_RANGES[idx]
        for atom in part.split(","):
            match = _FIELD_RE.match(atom)
            if not match:
                return False, "cron 第 %d 段非法: %s" % (idx + 1, atom)
            base = match.group(1)
            if base != "*":
                start = int(base.split("-")[0])
                end = int(base.split("-")[1]) if "-" in base else start
                if not (lo <= start <= hi and lo <= end <= hi and start <= end):
                    return False, "cron 第 %d 段超出范围: %s" % (idx + 1, atom)
            step = match.group(4)
            if step and int(step[1:]) < 1:
                return False, "cron 步长非法: %s" % atom
    return True, ""


def _as_bool(value, default=False):
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    if value is None:
        return default
    return bool(value)


def _as_bool_or_none(value):
    """三态布尔: None/''/'global' = 跟随全局, 其余按真假解析。"""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("", "global", "none", "null"):
            return None
        return text in ("true", "1", "yes", "on")
    return bool(value)


def _as_int(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_rule_or_none(value):
    """任务级完结规则三态: None/''/'global' = 跟随全局,
    'season'/'show' = 本任务指定; 其它值 (含旧数据脏值) 视为跟随全局。"""
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("", "global", "none", "null"):
            return None
        if text in COMPLETION_RULES:
            return text
        return None
    return None


@dataclass
class ShareTask:
    """一个监听任务: 一个 115 路径 + 独立检查频率。"""

    id: str = ""
    name: str = ""
    enabled: bool = True
    watch_path: str = ""
    cron: str = ""  # 空 = 用全局默认
    delay_hours: int | None = None  # None = 用全局延迟
    delete_source: bool | None = None  # None = 跟随全局
    completion_rule: str | None = None  # None = 跟随全局 (存量任务默认)

    @classmethod
    def from_dict(cls, data):
        data = dict(data or {})
        task = cls(**{k: data[k] for k in _TASK_FIELDS if k in data})
        task.enabled = _as_bool(data.get("enabled"), True)
        if task.delay_hours is not None and task.delay_hours != "":
            task.delay_hours = _as_int(task.delay_hours, None)
            if task.delay_hours is not None and task.delay_hours < 0:
                task.delay_hours = 0
        else:
            task.delay_hours = None
        task.delete_source = _as_bool_or_none(task.delete_source)
        task.completion_rule = _as_rule_or_none(task.completion_rule)
        task.cron = (task.cron or "").strip()
        if task.cron:
            ok, _ = validate_cron(task.cron)
            if not ok:
                task.cron = ""
        if not task.id:
            task.id = uuid.uuid4().hex[:12]
        if not task.name:
            task.name = task.watch_path or "未命名任务"
        return task

    def to_dict(self):
        return {k: getattr(self, k) for k in _TASK_FIELDS}

    def effective_cron(self, global_cron):
        return self.cron or global_cron or DEFAULT_CRON

    def effective_delay_hours(self, global_delay):
        if self.delay_hours is None:
            return int(global_delay or 0)
        return int(self.delay_hours)

    def effective_delete_source(self, global_delete_source):
        """分享后是否删源: 任务未指定 (None) 时跟随全局。"""
        if self.delete_source is None:
            return bool(global_delete_source)
        return bool(self.delete_source)

    def effective_completion_rule(self, global_rule):
        """本任务的完结检查规则: 未指定 (None, 存量任务默认) 时
        跟随全局; 全局非法值也回落到默认按季分享。"""
        if self.completion_rule in COMPLETION_RULES:
            return self.completion_rule
        if global_rule in COMPLETION_RULES:
            return global_rule
        return "season"


def _parse_tasks(raw):
    tasks = []
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            raw = json.loads(raw)
        except Exception:
            raw = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict):
                tasks.append(ShareTask.from_dict(item))
    seen = set()
    for task in tasks:
        if task.id in seen:
            task.id = uuid.uuid4().hex[:12]
        seen.add(task.id)
    return tasks


@dataclass
class ShareConfig:
    """插件全局配置 + 任务列表。"""

    enabled: bool = _GLOBAL_DEFAULTS["enabled"]
    temp_path: str = _GLOBAL_DEFAULTS["temp_path"]
    completion_rule: str = _GLOBAL_DEFAULTS["completion_rule"]
    delay_hours: int = _GLOBAL_DEFAULTS["delay_hours"]
    cron: str = _GLOBAL_DEFAULTS["cron"]
    receive_code: str = _GLOBAL_DEFAULTS["receive_code"]
    tg_enabled: bool = _GLOBAL_DEFAULTS["tg_enabled"]
    tg_channel_chat_id: str = _GLOBAL_DEFAULTS["tg_channel_chat_id"]
    tg_use_own_bot: bool = _GLOBAL_DEFAULTS["tg_use_own_bot"]
    tg_bot_token: str = _GLOBAL_DEFAULTS["tg_bot_token"]
    tmdb_api_key: str = _GLOBAL_DEFAULTS["tmdb_api_key"]
    tmdb_api_domain: str = _GLOBAL_DEFAULTS["tmdb_api_domain"]
    tmdb_language: str = _GLOBAL_DEFAULTS["tmdb_language"]
    max_retries: int = _GLOBAL_DEFAULTS["max_retries"]
    history_retention_days: int = _GLOBAL_DEFAULTS["history_retention_days"]
    failed_retention_days: int = _GLOBAL_DEFAULTS["failed_retention_days"]
    recycle_password: str = _GLOBAL_DEFAULTS["recycle_password"]
    onlyonce: bool = _GLOBAL_DEFAULTS["onlyonce"]
    debug_logging: bool = _GLOBAL_DEFAULTS["debug_logging"]
    proxy_url: str = _GLOBAL_DEFAULTS["proxy_url"]
    delete_source: bool = _GLOBAL_DEFAULTS["delete_source"]
    share_interval_seconds: int = _GLOBAL_DEFAULTS["share_interval_seconds"]
    tasks: list = field(default_factory=list)

    @classmethod
    def from_dict(cls, data):
        data = data or {}
        cfg = cls(**{k: data[k] for k in _GLOBAL_FIELDS if k in data})
        cfg.enabled = _as_bool(data.get("enabled"), False)
        cfg.tg_enabled = _as_bool(data.get("tg_enabled"), True)
        cfg.tg_use_own_bot = _as_bool(data.get("tg_use_own_bot"), False)
        cfg.onlyonce = _as_bool(data.get("onlyonce"), False)
        cfg.debug_logging = _as_bool(data.get("debug_logging"), False)
        cfg.delete_source = _as_bool(data.get("delete_source"), True)
        cfg.delay_hours = max(0, _as_int(data.get("delay_hours"), 48))
        cfg.max_retries = max(0, _as_int(data.get("max_retries"), 3))
        cfg.share_interval_seconds = max(
            0, _as_int(data.get("share_interval_seconds"), 60))
        cfg.history_retention_days = max(1, _as_int(
            data.get("history_retention_days"), 90))
        cfg.failed_retention_days = max(1, _as_int(
            data.get("failed_retention_days"), 90))
        if cfg.completion_rule not in COMPLETION_RULES:
            cfg.completion_rule = "season"
        cfg.cron = (cfg.cron or "").strip() or DEFAULT_CRON
        ok, _ = validate_cron(cfg.cron)
        if not ok:
            cfg.cron = DEFAULT_CRON
        cfg.receive_code = (cfg.receive_code or "wwdc").strip()
        cfg.temp_path = (cfg.temp_path or "/115分享暂存").strip()
        cfg.proxy_url = (cfg.proxy_url or "").strip()
        cfg.tasks = _parse_tasks(data.get("tasks"))
        return cfg

    def to_dict(self):
        result = {k: getattr(self, k) for k in _GLOBAL_FIELDS}
        result["tasks"] = [t.to_dict() for t in self.tasks]
        return result

    def get_task(self, task_id):
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None
