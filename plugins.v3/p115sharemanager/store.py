"""P115-ShareManager 本地存储 (SQLite WAL)。

表:
- share_jobs: 每部剧/每季一个分享作业 (任务 + tmdbid + season_number 唯一)。
  status: watching | pending_delay | ready | copying | sharing | shared |
          done | failed | unknown
  season_number=-1 表示整剧 (按整剧完结分享模式) 或未解析出季。
- share_history: 作业事件历史 (分享/推送/删除/失败等), 用于面板和重试审计。
- meta: 键值 (schema_version 等)。

只保留成功/失败历史 (成功 90 天/失败 90 天, 见配置), watching 类的
中间态只更新作业行, 不产生历史。
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

SCHEMA_VERSION = 1

_JOB_STATUSES = (
    "watching", "pending_delay", "ready", "copying", "sharing",
    "shared", "done", "failed", "unknown",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS share_jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    tmdbid INTEGER NOT NULL,
    season_number INTEGER NOT NULL DEFAULT -1,
    show_name TEXT NOT NULL DEFAULT '',
    en_title TEXT NOT NULL DEFAULT '',
    year INTEGER NOT NULL DEFAULT 0,
    source_path TEXT NOT NULL DEFAULT '',
    source_id INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'watching',
    local_count INTEGER NOT NULL DEFAULT 0,
    tmdb_count INTEGER NOT NULL DEFAULT 0,
    tmdb_status TEXT NOT NULL DEFAULT '',
    first_completed_at REAL NOT NULL DEFAULT 0,
    eligible_at REAL NOT NULL DEFAULT 0,
    share_url TEXT NOT NULL DEFAULT '',
    share_code TEXT NOT NULL DEFAULT '',
    receive_code TEXT NOT NULL DEFAULT '',
    temp_path TEXT NOT NULL DEFAULT '',
    temp_deleted_at REAL NOT NULL DEFAULT 0,
    deleted_at REAL NOT NULL DEFAULT 0,
    retry_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0,
    UNIQUE(task_id, tmdbid, season_number)
);
CREATE TABLE IF NOT EXISTS share_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL,
    task_id TEXT NOT NULL DEFAULT '',
    event TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_jobs_task_status
    ON share_jobs(task_id, status);
CREATE INDEX IF NOT EXISTS idx_history_job
    ON share_history(job_id, created_at);
"""


class ShareStore:
    """线程安全的 SQLite 存储 (单连接 + 锁, WAL 模式)。"""

    def __init__(self, db_path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = None
        with self._lock:
            self._ensure_open()

    # ---------- 内部 ----------

    def _ensure_open(self):
        """连接被 close() 关掉后按需重开 (须在持锁时调用)。
        场景: 插件重载/保存设置时 stop_service() 关库, 但旧扫描线程
        可能还在等复制落地 (最长 600 秒), 随后 _fail_job 写库会报
        Cannot operate on a closed database (v0.1.6 前的崩溃)。
        重开后旧线程能正常记失败, 新实例用的是另一个连接 (WAL
        模式下同一文件多连接可并发), 不冲突。"""
        if self._conn is not None:
            return
        self._conn = sqlite3.connect(
            str(self._db_path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript(_SCHEMA)
        self._conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES('schema_version', ?)",
            (str(SCHEMA_VERSION),))
        self._conn.commit()

    def _row(self, row):
        return dict(row) if row is not None else None

    # ---------- 作业 ----------

    def upsert_job(self, task_id, tmdbid, season_number, **fields):
        """按 (task_id, tmdbid, season_number) 插入或更新作业行。
        返回作业 dict。"""
        now = time.time()
        with self._lock:
            self._ensure_open()
            row = self._conn.execute(
                "SELECT * FROM share_jobs WHERE task_id=? AND tmdbid=? "
                "AND season_number=?",
                (task_id, tmdbid, season_number)).fetchone()
            if row is None:
                fields.setdefault("status", "watching")
                fields["task_id"] = task_id
                fields["tmdbid"] = tmdbid
                fields["season_number"] = season_number
                fields["created_at"] = now
                fields["updated_at"] = now
                cols = ", ".join(fields.keys())
                placeholders = ", ".join("?" * len(fields))
                self._conn.execute(
                    "INSERT INTO share_jobs(%s) VALUES(%s)"
                    % (cols, placeholders), list(fields.values()))
                self._conn.commit()
            else:
                fields["updated_at"] = now
                sets = ", ".join("%s=?" % k for k in fields.keys())
                self._conn.execute(
                    "UPDATE share_jobs SET %s WHERE task_id=? AND tmdbid=? "
                    "AND season_number=?" % sets,
                    list(fields.values()) + [task_id, tmdbid, season_number])
                self._conn.commit()
            return self.get_job(task_id, tmdbid, season_number)

    def get_job(self, task_id, tmdbid, season_number):
        with self._lock:
            self._ensure_open()
            return self._row(self._conn.execute(
                "SELECT * FROM share_jobs WHERE task_id=? AND tmdbid=? "
                "AND season_number=?",
                (task_id, tmdbid, season_number)).fetchone())

    def get_job_by_id(self, job_id):
        with self._lock:
            self._ensure_open()
            return self._row(self._conn.execute(
                "SELECT * FROM share_jobs WHERE id=?", (job_id,)).fetchone())

    def update_job(self, job_id, **fields):
        fields["updated_at"] = time.time()
        with self._lock:
            self._ensure_open()
            sets = ", ".join("%s=?" % k for k in fields.keys())
            self._conn.execute(
                "UPDATE share_jobs SET %s WHERE id=?" % sets,
                list(fields.values()) + [job_id])
            self._conn.commit()
            return self.get_job_by_id(job_id)

    def list_jobs(self, task_id=None, status=None, limit=50, offset=0):
        sql = "SELECT * FROM share_jobs"
        args = []
        conds = []
        if task_id:
            conds.append("task_id=?")
            args.append(task_id)
        if status:
            conds.append("status=?")
            args.append(status)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
        args += [int(limit), int(offset)]
        with self._lock:
            self._ensure_open()
            return [self._row(r) for r in self._conn.execute(sql, args)]

    def count_jobs(self, task_id=None, status=None):
        sql = "SELECT status, COUNT(*) c FROM share_jobs"
        args = []
        if task_id:
            sql += " WHERE task_id=?"
            args.append(task_id)
        sql += " GROUP BY status"
        with self._lock:
            self._ensure_open()
            counts = {s: 0 for s in _JOB_STATUSES}
            for row in self._conn.execute(sql, args):
                counts[row["status"]] = row["c"]
            return counts

    def delete_job(self, job_id):
        with self._lock:
            self._ensure_open()
            self._conn.execute("DELETE FROM share_history WHERE job_id=?",
                               (job_id,))
            self._conn.execute("DELETE FROM share_jobs WHERE id=?", (job_id,))
            self._conn.commit()

    def purge_task(self, task_id):
        """删除一个任务的全部作业与历史 (文件本身不动)。"""
        with self._lock:
            self._ensure_open()
            self._conn.execute(
                "DELETE FROM share_history WHERE task_id=?", (task_id,))
            self._conn.execute(
                "DELETE FROM share_jobs WHERE task_id=?", (task_id,))
            self._conn.commit()

    # ---------- 历史 ----------

    def add_history(self, job_id, task_id, event, detail=""):
        with self._lock:
            self._ensure_open()
            self._conn.execute(
                "INSERT INTO share_history(job_id, task_id, event, detail, "
                "created_at) VALUES(?,?,?,?,?)",
                (job_id, task_id, event, detail, time.time()))
            self._conn.commit()

    def list_history(self, job_id=None, limit=50, offset=0):
        sql = "SELECT * FROM share_history"
        args = []
        if job_id:
            sql += " WHERE job_id=?"
            args.append(job_id)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        args += [int(limit), int(offset)]
        with self._lock:
            self._ensure_open()
            return [self._row(r) for r in self._conn.execute(sql, args)]

    def count_history(self, job_id=None):
        sql = "SELECT COUNT(*) c FROM share_history"
        args = []
        if job_id:
            sql += " WHERE job_id=?"
            args.append(job_id)
        with self._lock:
            self._ensure_open()
            return self._conn.execute(sql, args).fetchone()["c"]

    def cleanup_history(self, success_days=90, failed_days=90):
        """只清理历史表; 作业行 (含 done/failed) 保留供面板查看。"""
        now = time.time()
        with self._lock:
            self._ensure_open()
            self._conn.execute(
                "DELETE FROM share_history WHERE event='shared' AND "
                "created_at < ?",
                (now - success_days * 86400,))
            self._conn.execute(
                "DELETE FROM share_history WHERE event='failed' AND "
                "created_at < ?",
                (now - failed_days * 86400,))
            self._conn.commit()

    def close(self):
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                # 置空后下次使用由 _ensure_open() 重开 (旧扫描线程
                # 还在跑时写库不再报 closed database)
                self._conn = None
