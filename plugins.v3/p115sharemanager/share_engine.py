"""P115-ShareManager 分享引擎 (见 design-v0.2 §2/§3/§5)。

流程 (每轮扫描, 每任务):
1. 列监听路径下的剧目录 -> 解析 {tmdbid-xxx} -> TMDB 查剧/季信息;
2. 按完结检查规则判完结:
   - season (默认): 某季 115 集号集合 == TMDB 该季已播集号集合即完结该季;
   - show (严格): 整剧 status=Ended 且全部已播季都对上才整剧完结;
3. 完结后进入延迟 (TMDB 最后一集播出日 + delay_hours, 防洗板);
4. 到期分享: 复核 -> 复制到 115 临时路径 (英文重命名) -> 等复制落地
   -> 创建分享 -> 设长期 + 固定码 -> share_snap 回读校验 -> TG 推送
   -> 等 60 秒删临时 -> 立即删源文件夹 (进回收站)。
失败不删任何东西 (临时/源都保留), 作业记 failed, 重试从断点续做:
- 分享已建但推送失败 -> 重试只重做推送及后续步骤。

安全红线: 删源只发生在分享已创建且回读校验通过之后; 临时删除
经 share_snap 验证不影响已分享内容 (2026-11-24 真实账号验证)。
"""
from __future__ import annotations

import re
import threading
import time
from datetime import date

try:
    from .p115_client import P115Error
    from .tmdb import TmdbError, aired_episodes, season_last_air_date
except ImportError:  # 直接以顶层模块加载时
    from p115_client import P115Error
    from tmdb import TmdbError, aired_episodes, season_last_air_date

VIDEO_EXTS = {".mkv", ".mp4", ".ts", ".mov", ".avi", ".rmvb", ".wmv",
              ".flv", ".m2ts", ".mpg", ".mpeg"}
TMDBID_RE = re.compile(r"\{tmdbid-(\d+)\}|\[tmdbid=(\d+)\]")
SEASON_DIR_RE = re.compile(r"^Season\s+(\d+)$", re.IGNORECASE)
EPISODE_RE = re.compile(r"[Ss](\d+)[Ee](\d+)")
YEAR_RE = re.compile(r"\((\d{4})\)|\[(\d{4})\]")
CJK_RE = re.compile(r"[\u2e80-\u9fff]")

# 分享成功后删临时前的等待 (P115-Share 同值 60 秒)
TEMP_DELETE_DELAY_SECONDS = 60
# 复制落地等待上限
COPY_WAIT_TIMEOUT = 600


def _season_no_of(name):
    """目录名里的季号 (Season 02 / season 2 等都算 2); 不是季目录返回 None。"""
    match = SEASON_DIR_RE.match(name or "")
    return int(match.group(1)) if match else None


def _is_video(name):
    lower = name.lower()
    if "sample" in lower:
        return False
    return any(lower.endswith(ext) for ext in VIDEO_EXTS)


def _parse_episode(name):
    match = EPISODE_RE.search(name)
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def _to_pinyin(name):
    """中文名 -> 拼音 (宝珠 -> BaoZhu)。无 pypinyin 时返回 ''。"""
    try:
        from pypinyin import Style, lazy_pinyin
    except Exception:
        return ""
    parts = lazy_pinyin(name, style=Style.NORMAL)
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def _rename_file_name(orig, en_title, zh_title):
    """按 TMDB 英文名重命名文件: 只换开头的中文剧名, 保留 SxxExx 后的后缀。

    例: 塔尔萨之王 (2022) [tmdbid=153312].S03E01.mkv
        -> Tulsa King.2022.S03E01.mkv
    已是英文名 (不含中文前缀) 的文件原样返回。
    """
    if not orig:
        return orig
    if zh_title and orig.startswith(zh_title):
        rest = orig[len(zh_title):]
        # rest 形如 " (2022) [tmdbid=153312].S03E01.mkv"
        return _rebuild_name(en_title, rest)
    match = EPISODE_RE.search(orig)
    if not match:
        return orig
    head = orig[:match.start()].rstrip(" .-_")
    if not CJK_RE.search(head):
        return orig
    # head 含中文 (如 "塔尔萨之王 (2022) [tmdbid=153312]."):
    # 年份取自 head, 后缀从 SxxExx 起
    year_match = YEAR_RE.search(head)
    year = (year_match.group(1) or year_match.group(2)) if year_match else ""
    suffix = orig[match.start():]
    if year:
        return "%s.%s.%s" % (en_title, year, suffix)
    return "%s.%s" % (en_title, suffix)


def _rebuild_name(en_title, rest):
    """en_title + 年份 (若 rest 里有) + 从 SxxExx 起的后缀。"""
    year = ""
    year_match = YEAR_RE.search(rest)
    if year_match:
        year = year_match.group(1) or year_match.group(2)
    ep_match = EPISODE_RE.search(rest)
    if not ep_match:
        return en_title + rest
    suffix = rest[ep_match.start():]
    if year:
        return "%s.%s.%s" % (en_title, year, suffix)
    return "%s.%s" % (en_title, suffix)


def _english_show_dir_name(en_title, year, tmdbid):
    if year:
        return "%s (%s) {tmdbid-%s}" % (en_title, year, tmdbid)
    return "%s {tmdbid-%s}" % (en_title, tmdbid)


class ShareSummary(dict):
    """一轮扫描的汇总 (dict 子类, 便于直接返回给 API)。"""


class ShareEngine:
    """扫描 + 分享引擎。client/tmdb/config/store 由 __init__ 注入;
    notify(title, text, poster_url) -> (ok, error) 由插件注入 (TG 推送)。"""

    def __init__(self, store, client, config, tmdb, logger=None,
                 notify=None):
        self.store = store
        self.client = client
        self.config = config
        self.tmdb = tmdb
        self.logger = logger
        self.notify = notify
        self._lock = threading.RLock()
        self._stop = False
        self.last_error = None
        self._last_share_at = 0.0  # 上一次创建分享的单调时间 (0 = 尚未分享)

    def request_stop(self):
        self._stop = True

    # ---------- 日志 ----------

    def _log(self, level, msg, *args):
        if self.logger:
            getattr(self.logger, level, self.logger.info)(
                "[P115-ShareManager] " + msg, *args)

    # ---------- 入口 ----------

    def run_once(self, task_id=None):
        """跑一轮扫描 (全部任务或指定任务)。返回汇总 dict。"""
        if self._lock.acquire(blocking=False) is False:
            return {"skipped_run": True, "reason": "上一轮还在跑"}
        try:
            summary = ShareSummary(
                scanned_shows=0, completed=0, shared=0, failed=0,
                unknown=0, skipped=0)
            tasks = self.config.tasks
            if task_id:
                tasks = [t for t in tasks if t.id == task_id]
            for task in tasks:
                if not task.enabled:
                    continue
                try:
                    self._scan_task(task, summary)
                except P115Error as exc:
                    summary["failed"] += 1
                    summary["error"] = str(exc)
                    self.last_error = str(exc)
                    self._log("error", "任务 %s 扫描失败: %s",
                              task.name, exc)
                except Exception as exc:  # noqa: BLE001
                    summary["failed"] += 1
                    summary["error"] = str(exc)
                    # exception 级带完整堆栈, 便于排查 (如 fs_getid
                    # 这类方法名写错, 光看异常信息看不出调用链)
                    self._log("exception", "任务 %s 扫描异常: %s",
                              task.name, exc)
            try:
                self.store.cleanup_history(
                    self.config.history_retention_days,
                    self.config.failed_retention_days)
            except Exception:
                pass
            return dict(summary)
        finally:
            self._lock.release()

    # ---------- 扫描 ----------

    def _scan_task(self, task, summary):
        if self.client is None or not self.client.is_logged_in():
            raise P115Error("115 未登录, 请先扫码或粘贴 Cookie 登录")
        watch_cid = self.client.getid(task.watch_path)
        shows = [i for i in self.client.list_dir(watch_cid) if i["is_dir"]]
        self._log("info", "任务 %s 开始扫描: %s (cid=%s) 下 %d 个剧目录",
                  task.name, task.watch_path, watch_cid, len(shows))
        for show in shows:
            if self._stop:
                break
            summary["scanned_shows"] += 1
            self._scan_show(task, show, summary)

    def _scan_show(self, task, show, summary):
        tmdbid = self._parse_tmdbid(show["name"])
        show_name = show["name"]
        year = self._parse_year(show_name)
        if tmdbid is None:
            tmdbid = self._search_tmdbid(show_name, year)
        if tmdbid is None:
            summary["unknown"] += 1
            self._log("warning", "剧 %s 解析不出 tmdbid, 跳过", show_name)
            return
        try:
            info, _via = self.tmdb.get_show(tmdbid)
        except TmdbError as exc:
            summary["unknown"] += 1
            self._log("warning", "TMDB 查不到 tmdbid=%s (%s): %s",
                      tmdbid, show_name, exc)
            return
        en_title = (info.get("en_title") or info.get("original_name")
                    or "").strip()
        if not en_title or CJK_RE.search(en_title):
            # TMDB 无英文名 (或英文名本身含中文) -> 拼音兜底
            zh_name = show_name.split("(")[0].strip()
            en_title = _to_pinyin(zh_name)
        if not en_title:
            summary["unknown"] += 1
            self._log("warning", "剧 %s 无英文名且拼音库缺失, 跳过",
                      show_name)
            return
        tmdb_status = info.get("status") or ""
        poster = info.get("poster_path") or ""
        poster_url = ("https://image.tmdb.org/t/p/w500%s" % poster
                      if poster else "")
        items = self.client.list_dir(show["cid"])
        season_dirs = {}
        loose_files = []
        for item in items:
            match = SEASON_DIR_RE.match(item["name"])
            if item["is_dir"] and match:
                season_dirs[int(match.group(1))] = item
            elif not item["is_dir"] and _is_video(item["name"]):
                loose_files.append(item)
        # 无 Season 子目录的剧: 按文件里的 SxxExx 分组
        if not season_dirs and loose_files:
            groups = {}
            for f in loose_files:
                parsed = _parse_episode(f["name"])
                if parsed:
                    groups.setdefault(parsed[0], []).append(f)
            for season_no, files in groups.items():
                self._judge_season_unit(
                    task, show, tmdbid, season_no, files, info, en_title,
                    tmdb_status, poster_url, summary)
            return
        if self.config.completion_rule == "show":
            self._judge_show_unit(
                task, show, tmdbid, season_dirs, info, en_title,
                tmdb_status, poster_url, summary)
        else:
            for season_no, sdir in sorted(season_dirs.items()):
                files = [i for i in self.client.list_dir(sdir["cid"])
                         if not i["is_dir"] and _is_video(i["name"])]
                self._judge_season_unit(
                    task, show, tmdbid, season_no, files, info, en_title,
                    tmdb_status, poster_url, summary,
                    season_dir=sdir)

    def _judge_season_unit(self, task, show, tmdbid, season_no, files,
                           info, en_title, tmdb_status, poster_url,
                           summary, season_dir=None):
        """按季完结分享: 该季集号集合 == TMDB 已播集号集合即完结。"""
        local_set, unparsed = self._local_episodes(files)
        try:
            season_detail, _ = self.tmdb.get_season(tmdbid, season_no)
        except TmdbError as exc:
            self._log("warning", "TMDB 查不到 tmdbid=%s S%02d: %s",
                      tmdbid, season_no, exc)
            return
        aired = set(aired_episodes(season_detail))
        tmdb_count = len(aired)
        # source_id 记分享单元的目录 id (Season 目录; 无 Season 子目录
        # 的剧记剧目录, 删源时只删该季文件, 见 _delete_source)
        source_id = (season_dir["cid"] if season_dir else show["cid"])
        job = self.store.upsert_job(
            task.id, tmdbid, season_no,
            show_name=show["name"], en_title=en_title,
            year=self._parse_year(show["name"]),
            source_path="%s/%s" % (task.watch_path, show["name"]),
            source_id=source_id,
            local_count=len(local_set), tmdb_count=tmdb_count,
            tmdb_status=tmdb_status)
        completed = bool(aired) and local_set == aired and not unparsed
        missing = sorted(aired - local_set)
        self._log("info", "%s S%02d: 本地 %d 集 / TMDB 已播 %d 集, "
                  "缺 %s%s, %s",
                  show["name"], season_no, len(local_set), tmdb_count,
                  missing if missing else "无",
                  (" 未解析 %d 个文件" % unparsed) if unparsed else "",
                  "完结" if completed else "未完结")
        if not completed:
            if job["status"] == "pending_delay":
                # TMDB 补集等导致不再完结 -> 回退 watching, 重新计时
                self.store.update_job(job["id"], status="watching",
                                      first_completed_at=0, eligible_at=0)
            return
        summary["completed"] += 1
        self._maybe_share(
            task, job, summary, en_title, tmdbid,
            last_air=season_last_air_date(season_detail),
            poster_url=poster_url,
            unit={"season_number": season_no,
                  "source_dir": season_dir,
                  "files": files,
                  "season_detail": season_detail})

    def _judge_show_unit(self, task, show, tmdbid, season_dirs, info,
                         en_title, tmdb_status, poster_url, summary):
        """按整剧完结分享: status=Ended 且全部已播季都对上。"""
        if tmdb_status != "Ended":
            return
        all_complete = True
        total_local = 0
        total_tmdb = 0
        for season_no, sdir in sorted(season_dirs.items()):
            files = [i for i in self.client.list_dir(sdir["cid"])
                     if not i["is_dir"] and _is_video(i["name"])]
            local_set, unparsed = self._local_episodes(files)
            try:
                season_detail, _ = self.tmdb.get_season(tmdbid, season_no)
            except TmdbError:
                all_complete = False
                continue
            aired = set(aired_episodes(season_detail))
            total_local += len(local_set)
            total_tmdb += len(aired)
            if not aired or local_set != aired or unparsed:
                all_complete = False
        if not all_complete or not total_tmdb:
            self._log("info", "%s: 整剧未完结 (status=%s 本地 %d / TMDB %d)",
                      show["name"], tmdb_status, total_local, total_tmdb)
            return
        self._log("info", "%s: 整剧完结 (status=%s 本地 %d / TMDB %d)",
                  show["name"], tmdb_status, total_local, total_tmdb)
        job = self.store.upsert_job(
            task.id, tmdbid, -1,
            show_name=show["name"], en_title=en_title,
            year=self._parse_year(show["name"]),
            source_path="%s/%s" % (task.watch_path, show["name"]),
            source_id=show["cid"],
            local_count=total_local, tmdb_count=total_tmdb,
            tmdb_status=tmdb_status)
        summary["completed"] += 1
        self._maybe_share(
            task, job, summary, en_title, tmdbid,
            last_air=info.get("last_air_date") or "",
            poster_url=poster_url,
            unit={"season_number": -1, "source_dir": show,
                  "files": [], "season_detail": None})

    def _maybe_share(self, task, job, summary, en_title, tmdbid,
                     last_air, poster_url, unit):
        """完结 -> 延迟计时 -> 到期分享。"""
        now = time.time()
        delay = task.effective_delay_hours(self.config.delay_hours)
        if job["status"] in ("copying", "sharing", "shared"):
            # 上一轮中断在分享中途的作业, 本轮续做
            self._share_job(task, job, unit, en_title, tmdbid,
                            poster_url, summary)
            return
        if job["status"] == "failed" and job.get("share_code"):
            # 分享已建但推送/清理失败 -> 续做
            self._share_job(task, job, unit, en_title, tmdbid,
                            poster_url, summary)
            return
        first = job.get("first_completed_at") or 0
        if not first:
            first = now
            self.store.update_job(job["id"], first_completed_at=first)
        anchor = first
        if last_air:
            try:
                anchor = max(
                    anchor,
                    time.mktime(time.strptime(last_air, "%Y-%m-%d")))
            except Exception:
                pass
        eligible = anchor + delay * 3600
        if job.get("status") != "pending_delay" or (
                job.get("eligible_at") or 0) != eligible:
            self.store.update_job(job["id"], status="pending_delay",
                                  eligible_at=eligible)
        if eligible <= now:
            self._log("info", "%s (季 %s) 延迟已到, 开始分享",
                      job.get("show_name"), job["season_number"])
            self.store.update_job(job["id"], status="ready")
            self._share_job(task, job, unit, en_title, tmdbid,
                            poster_url, summary)
        else:
            self._log("info", "%s (季 %s) 完结待分享: 延迟 %d 小时, "
                      "到 %s 后分享",
                      job.get("show_name"), job["season_number"], delay,
                      time.strftime("%Y-%m-%d %H:%M",
                                    time.localtime(eligible)))

    # ---------- 分享 ----------

    def share_now(self, job_id, skip_delay=False):
        """手动立即分享 (忽略延迟计时, 其余流程与自动一致)。"""
        job = self.store.get_job_by_id(job_id)
        if not job:
            return {"ok": False, "error": "作业不存在"}
        if job["status"] == "done":
            return {"ok": False, "error": "已分享过, 无需重复"}
        task = self.config.get_task(job["task_id"])
        if not task:
            return {"ok": False, "error": "任务不存在"}
        summary = ShareSummary(shared=0, failed=0)
        try:
            unit = self._load_unit(task, job)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        if skip_delay:
            self.store.update_job(job["id"], status="ready")
        self._share_job(task, job, unit, job["en_title"], job["tmdbid"],
                        "", summary)
        job = self.store.get_job_by_id(job_id)
        return {"ok": job["status"] == "done", "status": job["status"],
                "share_url": job.get("share_url") or "",
                "error": job.get("last_error") or ""}

    def retry_job(self, job_id):
        """重试失败作业: 清失败标记, 从断点续做 (分享已建则只重做
        推送及后续步骤)。"""
        job = self.store.get_job_by_id(job_id)
        if not job:
            return {"ok": False, "error": "作业不存在"}
        if job["status"] == "done":
            return {"ok": False, "error": "已完成, 无需重试"}
        if job["status"] in ("copying", "sharing"):
            return {"ok": False, "error": "正在分享中, 请稍后再试"}
        self.store.update_job(job["id"], last_error="",
                              retry_count=job.get("retry_count", 0) + 1)
        return self.share_now(job_id, skip_delay=True)

    def _load_unit(self, task, job):
        """按作业行重建分享单元 (手动分享/重试时用)。"""
        show = {"cid": job["source_id"], "name": job["show_name"]}
        if job["season_number"] == -1:
            return {"season_number": -1, "source_dir": show,
                    "files": [], "season_detail": None}
        items = self.client.list_dir(job["source_id"])
        season_dir = None
        for item in items:
            match = SEASON_DIR_RE.match(item["name"])
            if item["is_dir"] and match and int(match.group(1)) == (
                    job["season_number"]):
                season_dir = item
                break
        if season_dir is None:
            # 无 Season 子目录的剧: 文件直接在剧目录下
            files = [i for i in items
                     if not i["is_dir"] and _is_video(i["name"])]
            return {"season_number": job["season_number"],
                    "source_dir": show, "files": files,
                    "season_detail": None}
        files = [i for i in self.client.list_dir(season_dir["cid"])
                 if not i["is_dir"] and _is_video(i["name"])]
        return {"season_number": job["season_number"],
                "source_dir": season_dir, "files": files,
                "season_detail": None}

    def _share_job(self, task, job, unit, en_title, tmdbid, poster_url,
                   summary):
        """分享一个作业 (含断点续做)。失败不删任何东西。"""
        job_id = job["id"]
        try:
            self._share_job_inner(task, job, unit, en_title, tmdbid,
                                  poster_url, summary)
        except P115Error as exc:
            self._fail_job(job_id, str(exc), summary)
        except Exception as exc:  # noqa: BLE001
            self._fail_job(job_id, str(exc), summary)

    def _fail_job(self, job_id, error, summary):
        # 记失败本身绝不能再抛错: 否则原始错误 (如复制超时) 会被
        # 记库失败掩盖, 扫描报一个误导性的 "Cannot operate on a
        # closed database" (v0.1.6 前的崩溃)。
        try:
            job = self.store.get_job_by_id(job_id)
        except Exception as exc:  # noqa: BLE001
            self._log("error", "作业 %s 记失败时读库失败 (原错误: %s; "
                      "读库错误: %s)", job_id, error, exc)
            job = None
        if not job:
            if summary is not None:
                summary["failed"] = summary.get("failed", 0) + 1
            return
        try:
            self.store.update_job(
                job_id, status="failed", last_error=error,
                retry_count=job.get("retry_count", 0) + 1)
            self.store.add_history(job_id, job["task_id"], "failed", error)
        except Exception as exc:  # noqa: BLE001
            self._log("error", "作业 %s 记失败时写库失败 (原错误: %s; "
                      "写库错误: %s)", job.get("show_name"), error, exc)
        if summary is not None:
            summary["failed"] = summary.get("failed", 0) + 1
        self._log("error", "作业 %s 分享失败: %s",
                  job.get("show_name"), error)

    def _check_stop(self):
        """收到停止信号 (插件重载/保存设置/禁用) 时立即抛错退出,
        别等满复制超时。断点续做设计保证新实例会接着做。"""
        if self._stop:
            raise P115Error("扫描已停止 (插件重载或被禁用)")

    def _share_job_inner(self, task, job, unit, en_title, tmdbid,
                         poster_url, summary):
        job_id = job["id"]
        season_no = job["season_number"]
        is_whole_show = season_no == -1
        self._log("info", "开始分享: %s (季 %s) 作业 %s",
                  job.get("show_name"), season_no, job_id)
        self._check_stop()
        # 1) 复核: 分享前再查一次 TMDB + 115, 防止本轮内数据已变
        if not job.get("share_code"):
            self._log("info", "复核中: %s", job.get("show_name"))
            ok, reason = self._reverify(task, job, unit)
            if not ok:
                self._log("info", "复核不通过, 退回监听: %s", reason)
                self.store.update_job(
                    job_id, status="watching", first_completed_at=0,
                    eligible_at=0, last_error=reason)
                return
            self._log("info", "复核通过: %s", job.get("show_name"))
        # 2) 复制到临时路径 (英文重命名)
        if not job.get("temp_path"):
            self._check_stop()
            self.store.update_job(job_id, status="copying")
            temp_show_dir = self._copy_to_temp(
                task, job, unit, en_title, tmdbid)
            self.store.update_job(job_id, temp_path=temp_show_dir)
        else:
            temp_show_dir = job["temp_path"]
        # 3) 创建分享 + 长期 + 固定码
        if not job.get("share_code"):
            self._check_stop()
            self.store.update_job(job_id, status="sharing")
            share_code, share_url = self._create_share(
                task, job, unit, temp_show_dir)
            self.store.update_job(job_id, status="shared",
                                  share_code=share_code,
                                  share_url=share_url,
                                  receive_code=self.config.receive_code)
            self.store.add_history(job_id, task.id, "shared", share_url)
        # 4) TG 推送
        job = self.store.get_job_by_id(job_id)
        ok, err = self._push_tg(task, job, en_title, poster_url)
        if not ok:
            raise P115Error("TG 推送失败: %s" % err)
        self.store.add_history(job_id, task.id, "pushed",
                               job.get("share_url") or "")
        # 5) 等 60 秒删临时 (已验证不影响已分享内容)
        self._check_stop()
        time.sleep(TEMP_DELETE_DELAY_SECONDS)
        self._check_stop()
        try:
            self.client.delete([self._temp_show_cid(temp_show_dir)])
        except P115Error as exc:
            self._log("warning", "删除临时目录失败 (不影响分享): %s", exc)
        self.store.update_job(job_id,
                              temp_deleted_at=time.time())
        # 6) 分享后删源 (进回收站): 按季删 Season 目录, 整剧删剧目录,
        #    无 Season 子目录的剧只删该季的文件 (绝不能删整剧目录)。
        #    可配置关闭 (全局 delete_source, 任务可覆盖): 关闭时只记
        #    完成、源文件不动; 临时目录上面第 5 步照常删 (那是插件
        #    自己的 staging 区, 与源无关)
        if task.effective_delete_source(self.config.delete_source):
            self._check_stop()
            self._delete_source(task, job, unit)
            deleted_at = time.time()
        else:
            self._log("info", "作业 %s 分享完成, 按配置保留源文件",
                      job.get("show_name"))
            deleted_at = 0
        self.store.update_job(job_id, status="done",
                              deleted_at=deleted_at, last_error="")
        self.store.add_history(job_id, task.id, "done",
                               job.get("share_url") or "")
        if summary is not None:
            summary["shared"] = summary.get("shared", 0) + 1
        self._log("info", "作业 %s 分享完成: %s",
                  job.get("show_name"), job.get("share_url"))

    def _delete_source(self, task, job, unit):
        """删源: 按季删 Season 目录, 整剧删剧目录, 无 Season 子目录
        的剧只删该季的文件。"""
        if job["season_number"] == -1:
            self.client.delete([int(job["source_id"])])
            return
        source_dir = unit.get("source_dir") or {}
        name = source_dir.get("name") or ""
        if SEASON_DIR_RE.match(name):
            self.client.delete([int(source_dir["cid"])])
            return
        files = unit.get("files") or []
        fids = [int(f["fid"]) for f in files if f.get("fid")]
        if fids:
            self.client.delete(fids)

    def _temp_show_cid(self, temp_show_dir):
        return self.client.getid(temp_show_dir)

    def _reverify(self, task, job, unit):
        """分享前复核: TMDB 仍完结 + 115 源文件仍在且集数一致。"""
        try:
            info, _ = self.tmdb.get_show(job["tmdbid"])
        except TmdbError as exc:
            return False, "复核 TMDB 失败: %s" % exc
        if self.config.completion_rule == "show":
            if info.get("status") != "Ended":
                return False, "复核: 整剧未 Ended, 退回监听"
            return True, ""
        season_no = job["season_number"]
        try:
            season_detail, _ = self.tmdb.get_season(job["tmdbid"],
                                                     season_no)
        except TmdbError as exc:
            return False, "复核 TMDB 季失败: %s" % exc
        aired = set(aired_episodes(season_detail))
        files = unit.get("files") or []
        if not files:
            # 重新列源目录
            src = unit.get("source_dir") or {}
            try:
                items = self.client.list_dir(src.get("cid") or
                                             job["source_id"])
            except P115Error as exc:
                return False, "复核 115 源目录失败: %s" % exc
            files = [i for i in items
                     if not i["is_dir"] and _is_video(i["name"])]
        local_set, unparsed = self._local_episodes(files)
        if not aired or local_set != aired or unparsed:
            return False, "复核: 集数已变 (本地 %d 集 / TMDB %d 集), 退回监听" % (
                len(local_set), len(aired))
        return True, ""

    def _copy_to_temp(self, task, job, unit, en_title, tmdbid):
        """复制到临时路径并英文重命名。返回临时剧目录路径。"""
        year = job.get("year") or 0
        temp_root_cid = self.client.ensure_dir(self.config.temp_path)
        en_show_name = _english_show_dir_name(en_title, year, tmdbid)
        temp_show_path = "%s/%s" % (self.config.temp_path, en_show_name)
        # 暂存目录是插件自己的 staging 区: 失败重跑前先清掉残留,
        # 避免同名目录复制时合并/改名导致校验对不上
        try:
            stale_cid = self.client.getid(temp_show_path)
            self.client.delete([stale_cid])
        except Exception:
            # 暂存目录不存在是正常情况, 其它错误也先放过 (后续步骤会报错)
            pass
        temp_show_cid = self.client.ensure_dir(temp_show_path)
        source_dir = unit.get("source_dir") or {}
        source_cid = source_dir.get("cid") or job["source_id"]
        is_whole_show = job["season_number"] == -1
        if is_whole_show:
            # 整剧: 复制整剧目录到临时根, 再改名剧目录 + 各季内文件
            self._log("info", "开始复制整剧到临时路径: %s",
                      job["show_name"])
            resp = self.client.copy([int(source_cid)], temp_root_cid)
            self._log("info", "复制请求已提交 (state=%s), 等待落地: %s",
                      resp.get("state") if isinstance(resp, dict) else "?",
                      job["show_name"])
            # 整剧复制的落地判定: 临时根下出现中文剧名目录
            if not self._wait_dir(temp_root_cid, job["show_name"]):
                raise P115Error("复制到临时路径超时 (整剧)")
            copied_cid = self.client.getid(
                "%s/%s" % (self.config.temp_path, job["show_name"]))
            self.client.rename(copied_cid, en_show_name)
            self._rename_tree(copied_cid, en_title, job["show_name"])
        else:
            # 按季: 复制 Season N 目录到临时剧目录, 再改名季内文件
            season_name = "Season %d" % job["season_number"]
            files = unit.get("files") or []
            self._log("info", "开始复制 %s 到临时路径 (%d 个文件)",
                      season_name, len(files))
            resp = self.client.copy([int(source_cid)], temp_show_cid)
            self._log("info", "复制请求已提交 (state=%s), 等待落地: %s",
                      resp.get("state") if isinstance(resp, dict) else "?",
                      season_name)
            expect = {f["name"]: f["size"] for f in files}
            copied_season_cid = self._wait_season_copy(
                temp_show_cid, season_name, expect)
            self._rename_files(copied_season_cid, files, en_title,
                               job["show_name"])
        return temp_show_path

    def _wait_dir(self, parent_cid, dir_name, timeout=COPY_WAIT_TIMEOUT):
        """等 parent 下出现指定子目录。每 30 秒记一条等待进度
        (含实际已有的目录名, 便于定位复制落到了哪)。
        收到停止信号立即抛错退出, 不等满超时。"""
        start = time.time()
        deadline = start + timeout
        last_log = start
        while time.time() < deadline:
            self._check_stop()
            try:
                items = self.client.list_dir(parent_cid)
            except P115Error:
                items = []
            if any(i["is_dir"] and i["name"] == dir_name for i in items):
                return True
            now = time.time()
            if now - last_log >= 30:
                last_log = now
                have = [i["name"] for i in items if i["is_dir"]]
                self._log("info", "复制等待中: 已等 %d 秒, 未见目录 %s, "
                          "现有目录: %s",
                          int(now - start), dir_name, have)
            time.sleep(5)
        return False

    def _wait_season_copy(self, temp_show_cid, season_name, expect,
                          timeout=COPY_WAIT_TIMEOUT):
        """等 Season N 目录复制落地且文件齐全。返回季目录 cid。
        季目录按季号匹配 (源目录可能是 Season 02 / season 2 等写法,
        复制后保留原名, 按精确名 "Season 2" 等不到会误报超时)。
        每 30 秒记一条等待进度 (含临时目录下实际有的目录名)。
        收到停止信号立即抛错退出, 不等满超时。"""
        want_no = _season_no_of(season_name)
        start = time.time()
        deadline = start + timeout
        last_log = start
        while time.time() < deadline:
            self._check_stop()
            try:
                items = self.client.list_dir(temp_show_cid)
            except P115Error:
                items = []
            season = next(
                (i for i in items
                 if i["is_dir"] and (
                     _season_no_of(i["name"]) == want_no
                     if want_no is not None
                     else i["name"] == season_name)),
                None)
            if season is not None:
                files = self.client.list_dir(season["cid"])
                current = {i["name"]: i["size"] for i in files
                           if not i["is_dir"]}
                ok = True
                landed = 0
                for name, size in expect.items():
                    got = current.get(name)
                    if got is None or abs(got - size) > max(1, size * 0.002):
                        ok = False
                    else:
                        landed += 1
                if ok:
                    return season["cid"]
                now = time.time()
                if now - last_log >= 30:
                    last_log = now
                    self._log("info", "复制等待中: %s (实际目录名 %s) "
                              "已等 %d 秒, 已落地 %d/%d 个文件",
                              season_name, season["name"],
                              int(now - start), landed, len(expect))
            else:
                now = time.time()
                if now - last_log >= 30:
                    last_log = now
                    have = [i["name"] for i in items if i["is_dir"]]
                    self._log("info", "复制等待中: %s 已等 %d 秒, "
                              "未见该季目录, 现有目录: %s",
                              season_name, int(now - start), have)
            time.sleep(5)
        raise P115Error("复制到临时路径超时 (%s)" % season_name)

    def _rename_files(self, dir_cid, source_files, en_title, zh_title):
        """重命名目录内文件 (只换中文剧名前缀)。"""
        pairs = []
        for f in source_files:
            new_name = _rename_file_name(f["name"], en_title, zh_title)
            if new_name != f["name"]:
                pairs.append((f["fid"], new_name))
        if pairs:
            self.client.rename_many(pairs)

    def _rename_tree(self, show_cid, en_title, zh_title):
        """整剧: 递归重命名各季目录下的视频文件。"""
        for item in self.client.list_dir(show_cid):
            if not item["is_dir"]:
                continue
            files = [i for i in self.client.list_dir(item["cid"])
                     if not i["is_dir"] and _is_video(i["name"])]
            self._rename_files(item["cid"], files, en_title, zh_title)

    def _snap_with_retry(self, share_code, receive_code, cid=0,
                         attempts=4, interval=5):
        """回读分享内某目录, 新分享可能要几秒才可读: 空结果重试。
        attempts 次都空才返回空列表 (由调用方判失败)。"""
        last = []
        for i in range(attempts):
            last = self.client.share_snap(
                share_code, receive_code, cid=cid)
            if last:
                return last
            if i < attempts - 1:
                time.sleep(interval)
        return last

    def _wait_share_interval(self):
        """批量分享时两次创建分享之间留间隔, 避免连续请求触发
        115 风控。首个分享不等待; 间隔从上一次 create_share
        起算 (成功与否都算, 失败的分享也会触发下一次的等待)。
        正常流程里两次分享之间本来就有 60 秒删临时目录的等待,
        这里主要兜底校验失败等快路径 (实测失败分享曾 7 秒连发)。
        等待按 1 秒分片, 便于响应停止信号。"""
        interval = float(getattr(self.config, "share_interval_seconds", 0)
                         or 0)
        if interval <= 0 or not self._last_share_at:
            return
        remain = interval - (time.monotonic() - self._last_share_at)
        if remain > 0:
            self._log("info", "批量分享间隔: 等待 %.0f 秒再创建下一个分享",
                      remain)
        while remain > 0:
            self._check_stop()
            step = min(1.0, remain)
            time.sleep(step)
            remain -= step

    def _snap_child_dir(self, share_code, receive_code, parent_cid,
                        name=None, season_no=None):
        """在分享内某目录下找一个子目录 (按名或季号), 返回该子目录
        的 snap 条目, 找不到返回 None。"""
        items = self._snap_with_retry(
            share_code, receive_code, cid=int(parent_cid))
        for item in items:
            if not item["is_dir"]:
                continue
            if name is not None and item["name"] == name:
                return item
            if season_no is not None and \
                    _season_no_of(item["name"]) == season_no:
                return item
        return None

    def _create_share(self, task, job, unit, temp_show_path):
        """创建分享并设长期 + 固定码, share_snap 回读校验。
        返回 (share_code, share_url)。
        分享目标一律是临时剧目录, 分享结构为
        剧名目录/Season x/文件 (季分享也不例外, 否则接收方看不到剧名)。
        注意: share_snap 的根 (cid=0) 列出的是被分享的目录本身,
        要钻进去逐层核对: 根 -> 剧目录 -> (季: Season 目录 -> 文件;
        整剧: 季目录名)。"""
        unit_cid = self.client.getid(temp_show_path)
        root_name = _english_show_dir_name(
            job["en_title"], job.get("year") or 0, job["tmdbid"])
        self._wait_share_interval()
        share_code, _receive = self.client.create_share([unit_cid])
        self._last_share_at = time.monotonic()
        resp = self.client.set_share_longterm(
            share_code, self.config.receive_code)
        ex_time = resp.get("data", {}).get("share_ex_time") \
            if isinstance(resp, dict) else None
        if ex_time not in (None, -1):
            self._log("warning", "分享 %s 长期设置返回 ex_time=%s",
                      share_code, ex_time)
        # 回读校验: 先读根 (应为剧目录本身; 新分享可能要几秒
        # 才可读, 空结果重试), 再逐层钻进去核对内容
        root = self._snap_with_retry(share_code, self.config.receive_code)
        show_dir = next(
            (i for i in root if i["is_dir"] and (
                int(i.get("cid") or 0) == int(unit_cid)
                or i["name"] == root_name)),
            None)
        if show_dir is None:
            self.client.cancel_share(share_code)
            raise P115Error(
                "分享回读校验失败: 分享根目录未见剧目录 %s, 根内容 %s"
                % (root_name, sorted(i["name"] for i in root)))
        show_cid = int(show_dir.get("cid") or unit_cid)
        if job["season_number"] == -1:
            # 整剧: 剧目录下应为各季目录
            inner = self._snap_with_retry(
                share_code, self.config.receive_code, cid=show_cid)
            snap_names = {i["name"] for i in inner if i["is_dir"]}
            expect_names = {
                i["name"] for i in self.client.list_dir(unit_cid)
                if i["is_dir"]}
        else:
            # 按季: 剧目录 -> Season 目录 -> 重命名后的文件
            season_dir = self._snap_child_dir(
                share_code, self.config.receive_code, show_cid,
                season_no=job["season_number"])
            if season_dir is None:
                self.client.cancel_share(share_code)
                raise P115Error(
                    "分享回读校验失败: 剧目录下未见 Season %d 目录"
                    % job["season_number"])
            inner = self._snap_with_retry(
                share_code, self.config.receive_code,
                cid=int(season_dir.get("cid") or 0))
            snap_names = {i["name"] for i in inner if not i["is_dir"]}
            files = unit.get("files") or []
            expect_names = {
                _rename_file_name(f["name"], job["en_title"],
                                  job["show_name"])
                for f in files}
        if snap_names != expect_names:
            self.client.cancel_share(share_code)
            raise P115Error(
                "分享回读校验失败: 分享内 %s, 预期 %s"
                % (sorted(snap_names), sorted(expect_names)))
        return share_code, self.client.share_url(
            share_code, self.config.receive_code)

    def _push_tg(self, task, job, en_title, poster_url):
        """TG 推送。返回 (ok, error)。未配 TG 时跳过 (视为成功)。"""
        if not self.config.tg_enabled:
            return True, ""
        if not self.config.tg_channel_chat_id:
            return True, ""
        if self.notify is None:
            return False, "未注入 TG 推送回调"
        season_no = job["season_number"]
        if season_no == -1:
            title = "115 分享 · %s" % en_title
            body = "%s\n整剧共 %d 集\n分享链接: %s\n提取码: %s\n有效期: 长期" % (
                job.get("show_name") or en_title,
                job.get("tmdb_count") or 0,
                job.get("share_url") or "",
                self.config.receive_code)
        else:
            title = "115 分享 · %s S%02d" % (en_title, season_no)
            body = "%s 第 %d 季 (共 %d 集)\n分享链接: %s\n提取码: %s\n有效期: 长期" % (
                job.get("show_name") or en_title,
                season_no,
                job.get("tmdb_count") or 0,
                job.get("share_url") or "",
                self.config.receive_code)
        try:
            ok, err = self.notify(title, body, poster_url)
            return bool(ok), err or ""
        except Exception as exc:  # noqa: BLE001
            return False, str(exc)

    # ---------- 工具 ----------

    @staticmethod
    def _parse_tmdbid(name):
        match = TMDBID_RE.search(name)
        if not match:
            return None
        return int(match.group(1) or match.group(2))

    @staticmethod
    def _parse_year(name):
        match = YEAR_RE.search(name)
        if not match:
            return 0
        return int(match.group(1) or match.group(2))

    def _search_tmdbid(self, show_name, year):
        zh_name = show_name.split("(")[0].strip()
        if not zh_name:
            return None
        try:
            return self.tmdb.search_tv(zh_name, year or None)
        except TmdbError as exc:
            self._log("warning", "TMDB 搜剧失败 %s: %s", zh_name, exc)
            return None

    @staticmethod
    def _local_episodes(files):
        """本地集号集合 + 是否有无法解析的视频文件。"""
        episodes = set()
        unparsed = False
        for f in files:
            parsed = _parse_episode(f["name"])
            if parsed is None:
                unparsed = True
            else:
                episodes.add(parsed[1])
        return episodes, unparsed
