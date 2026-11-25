"""TMDB 查询 (见 design-v0.2 §5)。

优先走宿主自带 TMDB (self.chain.tmdb_info, 用宿主已配好的 TMDB,
无需单独配 key); 宿主查不到且配置了 tmdb_api_key 时, 走直连
api.themoviedb.org/3 兜底 (与 P115-Share 的 tmdb_service 同形)。

宿主 tmdb_info 返回字段 (实测结构, 见 design-v0.1 §5):
- status: Ended / Returning Series / ...
- seasons: [{season_number, episode_count, air_date, ...}]
- en_title / original_name / poster_path / last_air_date
- season 详情: episodes: [{episode_number, air_date, ...}]

直连 API 返回字段:
- /tv/{id}: status, number_of_seasons, seasons[{season_number,
  episode_count, air_date}], name, original_name, poster_path,
  last_air_date
- /tv/{id}/season/{n}: episodes[{episode_number, air_date, name}]
"""
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from datetime import date


class TmdbError(Exception):
    """TMDB 查询失败。"""


def today_str():
    return date.today().isoformat()


class TmdbClient:
    """宿主优先、直连兜底的 TMDB 客户端。"""

    def __init__(self, chain=None, api_key="", api_domain="api.themoviedb.org/3",
                 language="zh-CN", logger=None, proxy_url=""):
        self.chain = chain
        self.api_key = (api_key or "").strip()
        self.api_domain = (api_domain or "api.themoviedb.org/3").strip()
        self.language = language or "zh-CN"
        self.logger = logger
        # HTTP 代理 (配置 proxy_url, 如 http://192.168.2.2:7890):
        # 只给 TMDB 直连兜底用; 115 网盘调用不走代理; 宿主 TMDB
        # 走宿主自己的网络, 也不走这里的代理。
        self.proxy_url = (proxy_url or "").strip()

    def set_proxy(self, proxy_url):
        """设置/清除 TMDB 直连代理 (保存设置后即时生效)。"""
        self.proxy_url = (proxy_url or "").strip()

    # ---------- 宿主 ----------

    def _host_show(self, tmdbid):
        if self.chain is None:
            return None
        tmdb_info = getattr(self.chain, "tmdb_info", None)
        if not callable(tmdb_info):
            return None
        try:
            from app.schemas.types import MediaType
        except Exception:
            MediaType = None  # 本地测试: 传字符串亦可
        try:
            if MediaType is not None:
                return tmdb_info(tmdbid=tmdbid, mtype=MediaType.TV)
            return tmdb_info(tmdbid=tmdbid, mtype="tv")
        except Exception as exc:
            if self.logger:
                self.logger.warning(
                    "[P115-ShareManager] 宿主 TMDB 查询失败: %s", exc)
            return None

    def _host_season(self, tmdbid, season_number):
        if self.chain is None:
            return None
        tmdb_info = getattr(self.chain, "tmdb_info", None)
        if not callable(tmdb_info):
            return None
        try:
            from app.schemas.types import MediaType
        except Exception:
            MediaType = None
        try:
            if MediaType is not None:
                return tmdb_info(tmdbid=tmdbid, mtype=MediaType.TV,
                                 season=season_number)
            return tmdb_info(tmdbid=tmdbid, mtype="tv",
                             season=season_number)
        except Exception as exc:
            if self.logger:
                self.logger.warning(
                    "[P115-ShareManager] 宿主 TMDB 季查询失败: %s", exc)
            return None

    # ---------- 直连 ----------

    def _direct_get(self, path, params=None):
        if not self.api_key:
            raise TmdbError("未配置 TMDB API Key, 无法直连查询")
        query = {"api_key": self.api_key, "language": self.language}
        query.update(params or {})
        url = "https://%s%s?%s" % (
            self.api_domain.strip("/"), path,
            urllib.parse.urlencode(query))
        req = urllib.request.Request(url, headers={
            "User-Agent": "P115-ShareManager/0.1"})
        try:
            if self.proxy_url:
                # 直连兜底走代理 (显式 ProxyHandler; 默认 urlopen
                # 只读环境变量, 不读插件配置)
                opener = urllib.request.build_opener(
                    urllib.request.ProxyHandler(
                        {"http": self.proxy_url,
                         "https": self.proxy_url}))
                with opener.open(req, timeout=15) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:
            raise TmdbError("TMDB 直连查询失败: %s" % exc)

    # ---------- 对外 ----------

    def get_show(self, tmdbid):
        """返回 (info_dict, via) , via 为 'host' 或 'direct'。
        两边都查不到时抛 TmdbError。"""
        info = self._host_show(tmdbid)
        if info:
            return info, "host"
        if self.api_key:
            info = self._direct_get("/tv/%s" % tmdbid)
            if info:
                return info, "direct"
        raise TmdbError("TMDB 查不到 tmdbid=%s 的剧集" % tmdbid)

    def get_season(self, tmdbid, season_number):
        """返回 (season_dict, via)。season_dict 含 episodes 列表
        (episode_number + air_date)。"""
        info = self._host_season(tmdbid, season_number)
        if info and info.get("episodes") is not None:
            return info, "host"
        if self.api_key:
            info = self._direct_get(
                "/tv/%s/season/%s" % (tmdbid, season_number))
            if info:
                return info, "direct"
        raise TmdbError("TMDB 查不到 tmdbid=%s 第 %s 季"
                        % (tmdbid, season_number))

    def search_tv(self, title, year=None):
        """按名搜剧 (仅直连 API, 需 tmdb_api_key)。返回首个结果的 id,
        搜不到返回 None。"""
        if not self.api_key:
            return None
        params = {"query": title}
        if year:
            params["first_air_date_year"] = year
        data = self._direct_get("/search/tv", params)
        results = data.get("results") or []
        if not results:
            return None
        return results[0].get("id")


def aired_episodes(season_detail):
    """已播集号集合: episodes 里 air_date <= 今天的集。
    若无 episodes 字段, 回退用 episode_count (集号 1..N, 仅当
    该季 air_date 已过时才算已播)。"""
    today = today_str()
    episodes = season_detail.get("episodes") or []
    if episodes:
        # air_date 为空表示播出日未知, 不能算已播
        return sorted(
            int(e["episode_number"])
            for e in episodes
            if e.get("episode_number") is not None
            and e.get("air_date") and e["air_date"] <= today)
    count = int(season_detail.get("episode_count") or 0)
    air_date = season_detail.get("air_date") or ""
    if count and (not air_date or air_date <= today):
        return list(range(1, count + 1))
    return []


def season_last_air_date(season_detail):
    """该季最后一集的播出日期 (无 episodes 时用季 air_date)。"""
    episodes = season_detail.get("episodes") or []
    dates = [e.get("air_date") for e in episodes if e.get("air_date")]
    if dates:
        return max(dates)
    return season_detail.get("air_date") or ""
