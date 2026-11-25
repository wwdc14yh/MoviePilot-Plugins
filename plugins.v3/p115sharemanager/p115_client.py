"""115 网盘客户端封装 (基于 p115client, 见 design-v0.2 §4/附录)。

调用约定 (2026-11-24 真实账号验证通过, 见 design-v0.2 附录 B):
- 只有部分接口带 iOS UA + app="ios" (fs_copy_app/fs_rename_app/
  fs_delete_app/fs_makedirs_app/share_send_app/share_update_app);
  fs_dir_getid/fs_files/share_snap/share_update 不带 (验证脚本同款),
  带错参数可能调不通; v0.1.1 之前写错的 fs_getid 在 p115client 里
  根本不存在, 正确是 fs_dir_getid (v0.1.2 修);
- 站内复制 fs_copy_app: 必须同步调 (不传 async_=True)。参考仓库
  P115-Share 传 async_=True 是因为它是异步 FastAPI 应用 (会 await
  协程); 本插件是同步的, 传 async_=True 会返回一个没人 await 的
  协程, 复制根本没提交, 等待循环会静默轮询 600 秒后报超时 (v0.1.3 修);
  同步调返回成功只表示任务已提交, 仍需轮询目标目录比对文件数/大小
  确认落地 (wait_copy);
- 分享 share_send_app 默认有效期只有 15 天, 必须再调一次
  share_update_app(share_duration=-1) 才变长期, 同时固定提取码;
- 删临时目录不影响已分享内容 (share_snap 回读验证通过);
- fs_delete_app 删到回收站; 回收站清空需 6 位安全密码 (可选, 默认不做)。

代理后端: 本机直连用默认 urllib3-future 后端; 沙箱/代理环境下
若默认后端报 SSL 错误, 自动改用 requests_request 后端重试。
"""
from __future__ import annotations

import re
import time
import urllib.parse
from pathlib import Path

IOS_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 115Life/8.7.0"
)
IOS_KW = {"app": "ios", "headers": {"User-Agent": IOS_UA}}

# 115 返回的限流标记: {"margin": N} 表示限流 N 秒
_MARGIN_RE = re.compile(r"\{\s*['\"]margin['\"]\s*:\s*(\d+)")


class P115Error(Exception):
    """115 调用失败 (含登录失效/限流/405 风控等)。"""


def _is_ssl_error(exc):
    msg = str(exc)
    return any(k in msg for k in (
        "WRONG_VERSION_NUMBER", "SSLError", "SSL", "MaxRetryError",
        "Connection reset", "Connection aborted"))


def _safe_args(args, kwargs):
    """调用参数摘要 (每项截断到 200 字符, 不含 Cookie 等敏感值):
    仅供详细日志使用。"""
    parts = []
    for value in list(args):
        text = repr(value)
        parts.append(text if len(text) <= 200 else text[:200] + "...")
    for key, value in kwargs.items():
        if key == "request":
            continue
        text = repr(value)
        parts.append("%s=%s" % (
            key, text if len(text) <= 200 else text[:200] + "..."))
    return ", ".join(parts)


class P115ClientWrapper:
    """p115client 的薄封装: Cookie 文件持久化 + iOS 约定 + 代理后端兜底。"""

    def __init__(self, cookie_file, logger=None, request_backend="auto"):
        self.cookie_file = Path(cookie_file)
        self.logger = logger
        self._client = None
        self._use_proxy_backend = (request_backend == "requests")
        self.need_relogin = False
        # 详细日志开关 (配置 debug_logging): 打开后每次 115 调用的
        # 方法名/参数摘要/返回 state 都记到 MoviePilot 日志
        self.debug = False
        # 注意: 115 调用一律直连, 不走代理 (用户要求: 代理只给 TMDB
        # 直连兜底用, 见 tmdb.py)。不要在这里加代理。
        self._load_client()

    # ---------- 初始化 ----------

    def _load_client(self):
        cookie = ""
        if self.cookie_file.exists():
            cookie = self.cookie_file.read_text(encoding="utf-8").strip()
        if not cookie:
            self._client = None
            return
        try:
            from p115client import P115Client

            self._client = P115Client(cookie)
        except Exception as exc:
            raise P115Error("初始化 115 客户端失败: %s" % exc)

    def save_cookie(self, cookie):
        """保存 Cookie 字符串并重建客户端。"""
        cookie = (cookie or "").strip()
        if not cookie:
            raise P115Error("Cookie 为空")
        self.cookie_file.parent.mkdir(parents=True, exist_ok=True)
        self.cookie_file.write_text(cookie, encoding="utf-8")
        self.need_relogin = False
        self._load_client()
        return self.login_info()

    def is_logged_in(self):
        return self._client is not None

    # ---------- 内部: 请求后端与响应检查 ----------

    def _rq(self):
        """当前请求后端 kwargs (仅 SSL 兜底时走 requests 后端)。
        115 调用不走代理, 这里不带 proxies。"""
        if not self._use_proxy_backend:
            return {}
        try:
            from requests_request import request as proxy_request

            return {"request": proxy_request}
        except Exception:
            return {}

    def _call(self, fn, *args, **kwargs):
        """调一次 115 API: 失败时按规则处理 (限流等 N 秒重试一次;
        SSL 错误时切换代理后端重试一次; 405 标记需重新登录)。
        debug 开启时记方法名/参数摘要/返回 state, 便于排查。"""
        if self._client is None:
            raise P115Error("115 未登录, 请先扫码或粘贴 Cookie 登录")
        kwargs.update(self._rq())
        if self.debug and self.logger:
            self.logger.debug(
                "[P115-ShareManager] 115 调用 %s(%s)",
                getattr(fn, "__name__", fn),
                _safe_args(args, kwargs))
        try:
            resp = self._request_once(fn, args, kwargs)
        except Exception as exc:
            if self._use_proxy_backend:
                raise self._wrap(exc)
            if _is_ssl_error(exc):
                try:
                    from requests_request import request  # noqa: F401

                    self._use_proxy_backend = True
                    if self.logger:
                        self.logger.info(
                            "[P115-ShareManager] 默认请求后端报 SSL 错误, "
                            "改用 requests 代理后端重试")
                    kwargs.update(self._rq())
                    resp = self._request_once(fn, args, kwargs)
                except P115Error:
                    raise
                except Exception as exc2:
                    raise self._wrap(exc2)
            else:
                raise self._wrap(exc)
        if self.debug and self.logger:
            state = (resp.get("state") if isinstance(resp, dict)
                     else type(resp).__name__)
            self.logger.debug(
                "[P115-ShareManager] 115 返回 %s state=%s",
                getattr(fn, "__name__", fn), state)
        return resp

    def _request_once(self, fn, args, kwargs):
        """调一次 115 API, 遇限流标记 {"margin": N} 时等 N 秒再调一次
        (限流不计入重试); 405 标记需重新登录。"""
        resp = fn(*args, **kwargs)
        if isinstance(resp, dict) and resp.get("margin") is not None:
            wait = int(resp["margin"])
            if self.logger:
                self.logger.warning(
                    "[P115-ShareManager] 115 限流, 等待 %d 秒后重试", wait)
            time.sleep(min(wait, 120))
            resp = fn(*args, **kwargs)
        return resp

    def _wrap(self, exc):
        msg = str(exc)
        if "405" in msg or "登录" in msg or "login" in msg.lower():
            self.need_relogin = True
            return P115Error("115 登录失效 (405), 请重新扫码登录")
        if "rate_limited" in msg:
            return P115Error(msg)
        return P115Error(str(exc))

    # ---------- 账号 ----------

    def login_info(self):
        """返回登录信息 dict (state/user_name 等); 失败抛 P115Error。"""
        info = self._call(self._client.login_info)
        if isinstance(info, dict) and info.get("state") is False:
            self.need_relogin = True
            raise P115Error("115 登录失效, 请重新扫码登录")
        return info if isinstance(info, dict) else {}

    def user_name(self):
        try:
            info = self.login_info()
            return info.get("user_name") or info.get("user_id") or ""
        except Exception:
            return ""

    # ---------- 目录与文件 ----------

    @staticmethod
    def _item(raw):
        """fs_files 短键映射: n=名, fid=文件 id (目录为空), cid=目录 id,
        s=大小; 目录 = 无 fid。"""
        return {
            "name": raw.get("n", ""),
            "id": raw.get("fid") or raw.get("cid") or 0,
            "cid": raw.get("cid") or 0,
            "fid": raw.get("fid") or 0,
            "size": int(raw.get("s") or 0),
            "is_dir": not raw.get("fid"),
        }

    def getid(self, path):
        """路径 -> 目录 id (cid); 不存在抛 P115Error。
        注意: p115client 里的方法叫 fs_dir_getid (不是 fs_getid),
        且不带 iOS 参数 (验证脚本同款: fs_dir_getid(path))。"""
        resp = self._call(self._client.fs_dir_getid, path)
        cid = resp.get("id") if isinstance(resp, dict) else None
        if not cid:
            cid = (resp.get("data") or {}).get("id") \
                if isinstance(resp, dict) else None
        if not cid:
            raise P115Error("115 路径不存在: %s" % path)
        return int(cid)

    def list_dir(self, cid, limit=100):
        """列出目录全部内容 (自动翻页)。返回 _item 列表。"""
        items = []
        offset = 0
        while True:
            # 注意: fs_files 不带 iOS 参数 (验证脚本同款)
            resp = self._call(
                self._client.fs_files,
                {"cid": int(cid), "limit": int(limit), "offset": offset,
                 "show_dir": 1})
            data = resp.get("data", []) if isinstance(resp, dict) else []
            if not data:
                break
            items.extend(self._item(r) for r in data)
            if len(data) < limit:
                break
            offset += limit
        return items

    def makedirs(self, path):
        """建目录 (含父级), 返回 cid。"""
        resp = self._call(self._client.fs_makedirs_app, path, **IOS_KW)
        cid = resp.get("cid") if isinstance(resp, dict) else None
        if not cid:
            raise P115Error("创建目录失败: %s" % path)
        return int(cid)

    def ensure_dir(self, path):
        """目录存在返回 cid, 否则创建。"""
        try:
            return self.getid(path)
        except P115Error:
            return self.makedirs(path)

    # ---------- 复制 / 重命名 / 删除 ----------

    def copy(self, source_ids, target_cid):
        """站内复制: 提交即返回, 需轮询确认落地。
        注意: 不要传 async_=True (见模块 docstring): 同步调才会真正
        提交复制请求, 传了会返回没人 await 的协程, 复制根本没发生。
        提交被 115 拒绝 (state=False) 时立即抛错, 别等 600 秒轮询
        超时才发现。"""
        resp = self._call(
            self._client.fs_copy_app,
            list(source_ids), pid=int(target_cid), **IOS_KW)
        if isinstance(resp, dict) and resp.get("state") is False:
            raise P115Error("115 复制提交被拒绝: %s" % resp)
        return resp

    def wait_copy(self, target_cid, expect_names_sizes, timeout=600,
                  poll_interval=5):
        """轮询目标目录, 直到指定文件 (名 -> 大小) 全部落地且大小匹配
        (允许 0.2% 误差)。超时返回 False。
        每 30 秒记一条等待进度, 避免“卡住”时日志里一片空白。"""
        start = time.time()
        deadline = start + timeout
        expect = {n: int(s) for n, s in expect_names_sizes.items()}
        last_log = start
        while time.time() < deadline:
            try:
                current = {i["name"]: i["size"]
                           for i in self.list_dir(target_cid)
                           if not i["is_dir"]}
            except P115Error:
                current = {}
            ok = True
            landed = 0
            for name, size in expect.items():
                got = current.get(name)
                if got is None or abs(got - size) > max(1, size * 0.002):
                    ok = False
                else:
                    landed += 1
            if ok:
                return True
            now = time.time()
            if self.logger and now - last_log >= 30:
                last_log = now
                self.logger.info(
                    "[P115-ShareManager] 复制等待中: 已等 %d 秒, "
                    "已落地 %d/%d 个文件",
                    int(now - start), landed, len(expect))
            time.sleep(poll_interval)
        return False

    def rename(self, file_id, new_name):
        """重命名单个文件/目录 (新名含扩展名)。"""
        self._call(self._client.fs_rename_app, (int(file_id), new_name),
                   **IOS_KW)

    def rename_many(self, pairs):
        """批量重命名 [(fid, new_name), ...]。"""
        pairs = [(int(fid), name) for fid, name in pairs]
        if not pairs:
            return
        self._call(self._client.fs_rename_app, pairs, **IOS_KW)

    def delete(self, ids):
        """删除文件/目录到回收站。"""
        ids = [int(i) for i in ids]
        if not ids:
            return
        self._call(self._client.fs_delete_app, ids, **IOS_KW)

    def recyclebin_clean(self, password):
        """清空回收站 (需 6 位安全密码, 默认不做)。
        注意: recyclebin_clean_app(payload=tid, password=...),
        密码是关键字参数, 不是位置参数 (v0.1.2 前误把密码当了 tid)。"""
        if not password:
            raise P115Error("未配置回收站安全密码")
        self._call(self._client.recyclebin_clean_app, "",
                   password=password, **IOS_KW)

    # ---------- 分享 ----------

    def create_share(self, file_ids):
        """创建分享。返回 (share_code, receive_code)。"""
        fids = ",".join(str(int(i)) for i in file_ids)
        resp = self._call(self._client.share_send_app, fids, **IOS_KW)
        data = resp.get("data", {}) if isinstance(resp, dict) else {}
        code = data.get("share_code")
        receive = data.get("receive_code") or ""
        if not code:
            raise P115Error("创建分享失败: %s" % resp)
        return code, receive

    def set_share_longterm(self, share_code, receive_code):
        """设长期有效 + 固定提取码。返回响应 (share_ex_time=-1 即长期)。"""
        resp = self._call(
            self._client.share_update_app,
            {"share_code": share_code, "receive_code": receive_code,
             "share_duration": -1},
            **IOS_KW)
        return resp

    def share_snap(self, share_code, receive_code, cid=0, limit=1000):
        """按分享码 + 提取码回读分享内某目录的内容。
        返回 [{"name", "size", "is_dir", "cid", "fid"}, ...]。
        注意: share_snap 不带 iOS 参数 (验证脚本同款)。
        115 的分享根 (cid=0) 列出的是被分享的目录本身, 要用该目录
        的 cid 再调一次才看到内容 (文件/季目录) —— 真机日志证明
        直接拿根列表当文件列表会误判 (v0.1.7 前的 bug)。"""
        resp = self._call(
            self._client.share_snap,
            {"share_code": share_code, "receive_code": receive_code,
             "cid": int(cid), "limit": int(limit)})
        data = resp.get("data", {}) if isinstance(resp, dict) else {}
        items = data.get("list", []) or []
        out = []
        for raw in items:
            fid = raw.get("fid") or 0
            out.append({
                "name": raw.get("fn") or raw.get("n") or "",
                "size": int(raw.get("fs") or raw.get("s") or 0),
                # 目录无 fid (fs_files 同款约定); 目录自身的 id 在 cid
                "is_dir": not fid,
                "cid": int(raw.get("cid") or 0),
                "fid": int(fid) if fid else 0,
            })
        return out

    def share_url(self, share_code, receive_code=""):
        """分享链接, 带提取码参数 (如 ?password=wwdc, 点开即带码)。"""
        url = "https://115.com/s/%s" % share_code
        if receive_code:
            url += "?password=%s" % urllib.parse.quote(
                str(receive_code), safe="")
        return url

    def cancel_share(self, share_code):
        # 注意: share_update 不带 iOS 参数 (验证脚本同款)
        self._call(
            self._client.share_update,
            {"share_code": share_code, "action": "delete"})

    # ---------- 扫码登录 ----------

    def qrcode_start(self, platform="web"):
        """开始扫码登录。返回 {token, uid, time, sign, qrcode_url, app}。
        token 是服务端随机串, 前端轮询时用它; uid/time/sign 存服务端内存。"""
        import p115qrcode

        token_resp = p115qrcode.qrcode_token(**self._rq())
        uid = token_resp.get("uid")
        if not uid:
            raise P115Error("获取扫码 token 失败: %s" % token_resp)
        qrcode_url = token_resp.get("qrcode") or p115qrcode.qrcode_token_url(uid)
        return {
            "uid": uid,
            "time": token_resp.get("time"),
            "sign": token_resp.get("sign"),
            "qrcode_url": qrcode_url,
            "app": platform,
        }

    def qrcode_status(self, session):
        """查询扫码状态。返回 waiting/scanned/confirmed/expired/canceled。"""
        import p115qrcode

        resp = p115qrcode.qrcode_status(
            {"uid": session["uid"], "time": session["time"],
             "sign": session["sign"]},
            **self._rq())
        status = resp.get("data", {}).get("status")
        if status is None:
            status = resp.get("status")
        mapping = {0: "waiting", 1: "scanned", 2: "confirmed",
                   -1: "expired", -2: "canceled", -99: "aborted"}
        return mapping.get(int(status), "waiting")

    def qrcode_result(self, session):
        """扫码确认后取回 Cookie 并保存。返回登录信息。"""
        import p115qrcode

        resp = p115qrcode.qrcode_result(
            session["uid"], session.get("app", "web"), **self._rq())
        cookie = self._extract_cookie(resp)
        if not cookie:
            # 只记响应结构 (键名, 不含值, 无敏感信息), 便于定位 115
            # 返回结构变化; 完整响应不记日志 (可能含 Cookie)
            keys = self._response_keys(resp)
            if self.logger:
                self.logger.error(
                    "[P115-ShareManager] 扫码登录未返回 Cookie, 响应结构: %s",
                    keys)
            raise P115Error(
                "扫码登录未返回 Cookie (响应结构: %s), 请把 MoviePilot "
                "日志里这行发给开发者" % keys)
        return self.save_cookie(cookie)

    @staticmethod
    def _response_keys(resp):
        """响应结构摘要 (只含键名, 不含值): 顶层键 + data 层键。"""
        if not isinstance(resp, dict):
            return type(resp).__name__
        top = sorted(resp.keys())
        data = resp.get("data")
        if isinstance(data, dict):
            return {"top": top, "data": sorted(data.keys())}
        return {"top": top, "data": type(data).__name__}

    @staticmethod
    def _extract_cookie(resp):
        """从 qrcode_result 响应里拼出 Cookie 字符串。

        115 返回结构不固定 (v0.1.0 只查了 data.cookie / data.cookies
        两层, 真实扫码后仍取不到 Cookie), 按优先级递归查找:
        1. 含 "UID=" 的完整 Cookie 字符串 (任意层级);
        2. 含 UID/CID/SEID/KID 任一键的 dict (任意层级, 包括 data 本身),
           拼成 "CID=..; SEID=..; KID=..; UID=.." 串;
        3. [{"name": k, "value": v}, ...] 或 ["K=V", ...] 形式的列表。
        """
        keys = ("CID", "SEID", "KID", "UID")
        found = {}

        def walk(value):
            if isinstance(value, str):
                if "UID=" in value:
                    return value
                return None
            if isinstance(value, dict):
                hit = {k: v for k, v in value.items()
                       if k in keys and v}
                if hit:
                    found.update(hit)
                for item in value.values():
                    got = walk(item)
                    if got:
                        return got
                return None
            if isinstance(value, (list, tuple)):
                pairs = {}
                for item in value:
                    if isinstance(item, dict) and "name" in item \
                            and "value" in item:
                        pairs[item["name"]] = item["value"]
                    elif isinstance(item, str) and "=" in item:
                        k, _, v = item.partition("=")
                        pairs[k.strip()] = v.strip()
                hit = {k: v for k, v in pairs.items()
                       if k in keys and v}
                if hit:
                    found.update(hit)
                for item in value:
                    got = walk(item)
                    if got:
                        return got
                return None
            return None

        direct = walk(resp)
        if direct:
            return direct
        if found:
            return "; ".join("%s=%s" % (k, found[k]) for k in keys
                             if k in found)
        return ""
