"""同步状态持久化: SQLite (WAL) , 文件放在插件数据目录下, 不写源码目录。

两类记录分开清理 (见 design-v0.1.md 第 6 点):
- sync_state: 增量跳过的依据, 源文件还在就不能按时间删;
  源端消失的先标记 source_gone, 过宽限期才删。
- sync_task: 前端面板的历史, 成功/失败分别按保留天数清理。
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sync_state (
    state_key     TEXT PRIMARY KEY,
    task_id       TEXT NOT NULL DEFAULT '',
    source_path   TEXT NOT NULL,
    source_file_id TEXT,
    size          INTEGER NOT NULL DEFAULT 0,
    check_value   TEXT,
    target_path   TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'done',
    retry_count   INTEGER NOT NULL DEFAULT 0,
    first_seen_at REAL NOT NULL,
    last_seen_at  REAL NOT NULL,
    submitted_at  REAL,
    finished_at   REAL,
    gone_at       REAL,
    last_error    TEXT
);
CREATE INDEX IF NOT EXISTS idx_sync_state_status ON sync_state(status);

CREATE TABLE IF NOT EXISTS sync_task (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id       TEXT NOT NULL DEFAULT '',
    file_name     TEXT NOT NULL,
    source_path   TEXT NOT NULL,
    target_path   TEXT NOT NULL,
    size          INTEGER NOT NULL DEFAULT 0,
    status        TEXT NOT NULL DEFAULT 'syncing',
    error         TEXT,
    started_at    REAL NOT NULL,
    finished_at   REAL
);
CREATE INDEX IF NOT EXISTS idx_sync_task_started ON sync_task(started_at);
"""


def state_key_of(task_id, source_file_id, source_path):
    """增量唯一键: 任务内唯一 = task_id + (CD2 文件 ID, 没有时退回路径)。

    多任务下同一文件可以被不同任务各同步一份, 状态互不干扰。
    """
    base = source_file_id if source_file_id else "path:" + source_path
    return "%s|%s" % (task_id or "", base)


class SyncStore:
    """线程安全的 SQLite 存储 (插件进程内单例使用)。"""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(_SCHEMA)
            # 旧库补列 (可重复执行): v0.1 无 submitted_at, v0.2 无 task_id
            for table, column, ddl in (
                ("sync_state", "submitted_at",
                 "ALTER TABLE sync_state ADD COLUMN submitted_at REAL"),
                ("sync_state", "task_id",
                 "ALTER TABLE sync_state ADD COLUMN task_id TEXT NOT NULL DEFAULT ''"),
                ("sync_task", "task_id",
                 "ALTER TABLE sync_task ADD COLUMN task_id TEXT NOT NULL DEFAULT ''"),
            ):
                cols = [
                    r[1]
                    for r in self._conn.execute(
                        "PRAGMA table_info(%s)" % table
                    ).fetchall()
                ]
                if column not in cols:
                    self._conn.execute(ddl)
            self._conn.commit()

    def close(self):
        with self._lock:
            self._conn.close()

    # ---------- sync_state ----------

    def get_state(self, state_key):
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sync_state WHERE state_key = ?", (state_key,)
            ).fetchone()
        return dict(row) if row else None

    def upsert_done(self, *, state_key, source_path, source_file_id, size,
                    check_value, target_path, task_id="", now=None):
        now = now if now is not None else time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sync_state
                    (state_key, task_id, source_path, source_file_id, size,
                     check_value, target_path, status, retry_count,
                     first_seen_at, last_seen_at, finished_at, gone_at,
                     last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'done', 0, ?, ?, ?, NULL, NULL)
                ON CONFLICT(state_key) DO UPDATE SET
                    source_path = excluded.source_path,
                    size = excluded.size,
                    check_value = excluded.check_value,
                    target_path = excluded.target_path,
                    status = 'done',
                    retry_count = 0,
                    last_seen_at = excluded.last_seen_at,
                    submitted_at = NULL,
                    finished_at = excluded.finished_at,
                    gone_at = NULL,
                    last_error = NULL
                """,
                (state_key, task_id, source_path, source_file_id, size,
                 check_value, target_path, now, now, now),
            )
            self._conn.commit()

    def upsert_copying(self, *, state_key, source_path, source_file_id, size,
                       check_value, target_path, task_id="", now=None):
        """记录已提交 CD2 异步复制、尚未校验完成的状态。

        重复提交同一文件时保留最早的 submitted_at, 超时判断以它为准。
        """
        now = now if now is not None else time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sync_state
                    (state_key, task_id, source_path, source_file_id, size,
                     check_value, target_path, status, retry_count,
                     first_seen_at, last_seen_at, submitted_at, finished_at,
                     gone_at, last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'copying', 0, ?, ?, ?, NULL, NULL, NULL)
                ON CONFLICT(state_key) DO UPDATE SET
                    source_path = excluded.source_path,
                    size = excluded.size,
                    check_value = excluded.check_value,
                    target_path = excluded.target_path,
                    status = 'copying',
                    last_seen_at = excluded.last_seen_at,
                    submitted_at = COALESCE(sync_state.submitted_at,
                                            excluded.submitted_at),
                    finished_at = NULL,
                    gone_at = NULL,
                    last_error = NULL
                """,
                (state_key, task_id, source_path, source_file_id, size,
                 check_value, target_path, now, now, now),
            )
            self._conn.commit()

    def list_states_by_status(self, status, task_id=None):
        with self._lock:
            if task_id is None:
                rows = self._conn.execute(
                    "SELECT * FROM sync_state WHERE status = ?", (status,)
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM sync_state WHERE status = ? AND task_id = ?",
                    (status, task_id),
                ).fetchall()
        return [dict(r) for r in rows]

    def delete_state(self, state_key):
        with self._lock:
            self._conn.execute(
                "DELETE FROM sync_state WHERE state_key = ?", (state_key,)
            )
            self._conn.commit()

    def set_excluded(self, state_key, now=None):
        """把某个文件标记为 excluded: 该任务以后不再同步它。"""
        now = now if now is not None else time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE sync_state SET status = 'excluded', last_seen_at = ? "
                "WHERE state_key = ?",
                (now, state_key),
            )
            self._conn.commit()

    def list_states(self, task_id=None, status=None, limit=200, offset=0):
        """按任务 (可再按状态) 列出文件级状态, 最近更新的在前。支持分页。"""
        sql = "SELECT * FROM sync_state"
        conds, params = [], []
        if task_id is not None:
            conds.append("task_id = ?")
            params.append(task_id)
        if status:
            conds.append("status = ?")
            params.append(status)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        sql += " ORDER BY last_seen_at DESC LIMIT ? OFFSET ?"
        params.append(int(limit))
        params.append(int(offset))
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def count_states_filtered(self, task_id=None, status=None):
        """与 list_states 同条件的总数, 给前端分页用。"""
        sql = "SELECT COUNT(*) FROM sync_state"
        conds, params = [], []
        if task_id is not None:
            conds.append("task_id = ?")
            params.append(task_id)
        if status:
            conds.append("status = ?")
            params.append(status)
        if conds:
            sql += " WHERE " + " AND ".join(conds)
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
        return int(row[0] or 0)

    def sum_done_size(self, task_id=None):
        with self._lock:
            if task_id is None:
                row = self._conn.execute(
                    "SELECT COALESCE(SUM(size), 0) FROM sync_state "
                    "WHERE status = 'done'"
                ).fetchone()
            else:
                row = self._conn.execute(
                    "SELECT COALESCE(SUM(size), 0) FROM sync_state "
                    "WHERE status = 'done' AND task_id = ?",
                    (task_id,),
                ).fetchone()
        return int(row[0] or 0)

    def record_failure(self, *, state_key, source_path, source_file_id, size,
                       check_value, target_path, error, task_id="", now=None):
        now = now if now is not None else time.time()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sync_state
                    (state_key, task_id, source_path, source_file_id, size,
                     check_value, target_path, status, retry_count,
                     first_seen_at, last_seen_at, finished_at, gone_at,
                     last_error)
                VALUES (?, ?, ?, ?, ?, ?, ?, 'failed', 1, ?, ?, NULL, NULL, ?)
                ON CONFLICT(state_key) DO UPDATE SET
                    status = 'failed',
                    retry_count = sync_state.retry_count + 1,
                    last_seen_at = excluded.last_seen_at,
                    last_error = excluded.last_error
                """,
                (state_key, task_id, source_path, source_file_id, size,
                 check_value, target_path, now, now, error),
            )
            self._conn.commit()

    def touch_seen(self, state_key, now=None):
        now = now if now is not None else time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE sync_state SET last_seen_at = ? WHERE state_key = ?",
                (now, state_key),
            )
            self._conn.commit()

    def mark_missing_as_gone(self, seen_keys, task_id=None, now=None):
        """本轮没见到的 done/failed 记录标记 source_gone, 返回标记条数。"""
        now = now if now is not None else time.time()
        with self._lock:
            if task_id is None:
                rows = self._conn.execute(
                    "SELECT state_key FROM sync_state "
                    "WHERE status IN ('done', 'failed')"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT state_key FROM sync_state "
                    "WHERE status IN ('done', 'failed') AND task_id = ?",
                    (task_id,),
                ).fetchall()
            missing = [r[0] for r in rows if r[0] not in seen_keys]
            for key in missing:
                self._conn.execute(
                    "UPDATE sync_state SET status = 'source_gone', gone_at = ? "
                    "WHERE state_key = ?",
                    (now, key),
                )
            self._conn.commit()
        return len(missing)

    # ---------- sync_task (面板历史) ----------

    def begin_task(self, *, file_name, source_path, target_path, size,
                   task_id="", now=None):
        now = now if now is not None else time.time()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO sync_task (task_id, file_name, source_path, "
                "target_path, size, status, started_at) "
                "VALUES (?, ?, ?, ?, ?, 'syncing', ?)",
                (task_id, file_name, source_path, target_path, size, now),
            )
            self._conn.commit()
            return cur.lastrowid

    def finish_task(self, task_id, status, error=None, now=None):
        now = now if now is not None else time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE sync_task SET status = ?, error = ?, finished_at = ? "
                "WHERE id = ?",
                (status, error, now, task_id),
            )
            self._conn.commit()

    def finish_open_task(self, source_path, status, error=None, task_id=None,
                         now=None):
        """把某个源文件还处于 syncing 的面板任务结掉 (跨轮校验完成时用)。"""
        now = now if now is not None else time.time()
        with self._lock:
            if task_id is None:
                self._conn.execute(
                    "UPDATE sync_task SET status = ?, error = ?, "
                    "finished_at = ? WHERE source_path = ? "
                    "AND status = 'syncing'",
                    (status, error, now, source_path),
                )
            else:
                self._conn.execute(
                    "UPDATE sync_task SET status = ?, error = ?, "
                    "finished_at = ? WHERE source_path = ? "
                    "AND task_id = ? AND status = 'syncing'",
                    (status, error, now, source_path, task_id),
                )
            self._conn.commit()

    def list_tasks(self, limit=50, task_id=None):
        with self._lock:
            if task_id is None:
                rows = self._conn.execute(
                    "SELECT * FROM sync_task ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM sync_task WHERE task_id = ? "
                    "ORDER BY id DESC LIMIT ?",
                    (task_id, limit),
                ).fetchall()
        return [dict(r) for r in rows]

    def count_states(self, task_id=None):
        with self._lock:
            if task_id is None:
                rows = self._conn.execute(
                    "SELECT status, COUNT(*) AS n FROM sync_state "
                    "GROUP BY status"
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT status, COUNT(*) AS n FROM sync_state "
                    "WHERE task_id = ? GROUP BY status",
                    (task_id,),
                ).fetchall()
        return {r[0]: r[1] for r in rows}

    # ---------- 清理 ----------

    def cleanup(self, *, history_retention_days, failed_retention_days,
                state_tombstone_days, now=None):
        """按 design-v0.1 的规则清理, 返回各类删除条数。"""
        now = now if now is not None else time.time()
        day = 86400.0
        result = {"tasks_done": 0, "tasks_failed": 0, "states_gone": 0}
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM sync_task WHERE status = 'done' "
                "AND finished_at IS NOT NULL AND finished_at < ?",
                (now - history_retention_days * day,),
            )
            result["tasks_done"] = cur.rowcount
            cur = self._conn.execute(
                "DELETE FROM sync_task WHERE status = 'failed' "
                "AND finished_at IS NOT NULL AND finished_at < ?",
                (now - failed_retention_days * day,),
            )
            result["tasks_failed"] = cur.rowcount
            cur = self._conn.execute(
                "DELETE FROM sync_state WHERE status = 'source_gone' "
                "AND gone_at IS NOT NULL AND gone_at < ?",
                (now - state_tombstone_days * day,),
            )
            result["states_gone"] = cur.rowcount
            self._conn.commit()
            if sum(result.values()):
                self._conn.execute("VACUUM")
        return result
