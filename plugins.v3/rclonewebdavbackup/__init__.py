"""
MoviePilot V3 - Rclone WebDAV 增量备份插件

使用 rclone RC core/command 执行逐文件 copy，以 SQLite 记录路径+大小身份。
"""
from __future__ import annotations

import json
import logging
import os
import posixpath
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from apscheduler.triggers.cron import CronTrigger
from app.sdk.plugin import _PluginBase

try:
    from app.sdk.logging import logger
except Exception:
    logger = logging.getLogger(__name__)


class RcloneWebdavBackup(_PluginBase):
    plugin_name = "Rclone WebDAV 增量备份"
    plugin_desc = "通过 rclone RC 将 Alist WebDAV 增量备份到 CloudDrive2，并使用 SQLite 保存备份历史。"
    plugin_icon = "Moviepilot_A.png"
    plugin_version = "1.0.3"
    plugin_author = "OpenAI"
    author_url = "https://github.com/"
    plugin_config_prefix = "rclonewebdavbackup_"
    plugin_order = 50
    auth_level = 1

    def __init__(self):
        super().__init__()
        self._enabled = False
        self._config: dict[str, Any] = {}
        self._stop_event = threading.Event()
        self._run_lock = threading.Lock()
        self._worker_lock = threading.Lock()
        self._worker: threading.Thread | None = None
        self._db_path: Path | None = None
        self._last_summary: dict[str, Any] = {}
        self._runtime_status = "idle"

    @staticmethod
    def _now() -> str:
        return datetime.now().astimezone().isoformat(timespec="seconds")

    def init_plugin(self, config: dict | None = None) -> None:
        self._stop_event.set()
        self._stop_event = threading.Event()
        self._config = dict(config or {})
        self._enabled = bool(self._config.get("enabled", False))
        self._config.setdefault("rc_url", "http://0.0.0.0:0")
        self._config.setdefault("source_remote", "demo2")
        self._config.setdefault("destination_remote", "demo")
        self._config.setdefault("source_path", "")
        self._config.setdefault("destination_path", "")
        self._config.setdefault("concurrency", 4)
        self._config.setdefault("cron", "*/30 * * * *")
        self._config.setdefault("rc_timeout", 60)
        self._config.setdefault("rc_user", "")
        self._config.setdefault("rc_password", "")
        self._config.setdefault("onlyonce", False)

        data_dir = Path(self.get_data_path())
        data_dir.mkdir(parents=True, exist_ok=True)
        self._db_path = data_dir / "backup.sqlite3"
        self._ensure_db()

        if self._enabled and self._config.get("onlyonce"):
            self._start_worker()
            self._config["onlyonce"] = False
            self.update_config(self._config)

    def get_state(self) -> bool:
        return self._enabled

    def get_form(self) -> tuple[list[dict], dict[str, Any]]:
        return [
            {
                "component": "VForm",
                "content": [
                    {"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}},
                    {"component": "VTextField", "props": {"model": "rc_url", "label": "Rclone RC 地址", "hint": "例如 http://192.168.2.2:5572"}},
                    {"component": "VTextField", "props": {"model": "rc_user", "label": "RC 用户名（可选）"}},
                    {"component": "VTextField", "props": {"model": "rc_password", "label": "RC 密码（可选）", "type": "password"}},
                    {"component": "VTextField", "props": {"model": "source_remote", "label": "源 Remote 名称", "placeholder": "Alist"}},
                    {"component": "VTextField", "props": {"model": "source_path", "label": "源目录", "hint": "Remote 内相对路径；留空表示根目录"}},
                    {"component": "VTextField", "props": {"model": "destination_remote", "label": "目标 Remote 名称", "placeholder": "CloudDrive2"}},
                    {"component": "VTextField", "props": {"model": "destination_path", "label": "目标目录", "hint": "Remote 内相对路径；留空表示根目录"}},
                    {"component": "VSlider", "props": {"model": "concurrency", "label": "并发文件数", "min": 1, "max": 16, "step": 1}},
                    {"component": "VTextField", "props": {"model": "cron", "label": "Cron 表达式", "hint": "默认每 30 分钟：*/30 * * * *"}},
                    {"component": "VTextField", "props": {"model": "rc_timeout", "label": "RC 请求超时（秒）", "type": "number"}},
                    {"component": "VSwitch", "props": {"model": "onlyonce", "label": "保存后立即执行一次"}},
                ],
            }
        ], {
            "enabled": False, "rc_url": "http://0.0.0.0:0",
            "rc_user": "", "rc_password": "", "source_remote": "demo2",
            "source_path": "", "destination_remote": "demo",
            "destination_path": "", "concurrency": 4, "cron": "*/30 * * * *",
            "rc_timeout": 60, "onlyonce": False,
        }

    def get_page(self) -> list[dict]:
        status = self._status_payload()
        return [
            {"component": "VAlert", "props": {
                "type": "info", "variant": "tonal",
                "text": (
                    f"运行状态：{status['status']}；最近一次统计："
                    f"扫描 {status['summary'].get('scanned', 0)}，"
                    f"成功 {status['summary'].get('success', 0)}，"
                    f"失败 {status['summary'].get('failed', 0)}。"
                    "完整任务列表、分页和实时状态可通过插件 API /tasks 查询。"
                )
            }},
            {"component": "VAlert", "props": {
                "type": "warning", "variant": "tonal",
                "text": "注意：RC core/command 等同于以 rclone 进程权限执行命令。请仅允许可信局域网访问 5572，并配置 RC 用户名和密码。"
            }},
        ]

    def get_api(self) -> list[dict]:
        return [
            {"path": "/status", "endpoint": self.api_status, "methods": ["GET"], "auth": "bear", "summary": "获取备份运行状态"},
            {"path": "/tasks", "endpoint": self.api_tasks, "methods": ["GET"], "auth": "bear", "summary": "查询备份文件任务"},
            {"path": "/run", "endpoint": self.api_run, "methods": ["POST"], "auth": "bear", "summary": "立即启动备份"},
            {"path": "/test", "endpoint": self.api_test, "methods": ["POST"], "auth": "bear", "summary": "测试 Rclone RC 连接"},
        ]

    def get_service(self) -> list[dict]:
        if not self._enabled:
            return []
        cron_expr = str(self._config.get("cron") or "*/30 * * * *")
        try:
            trigger = CronTrigger.from_crontab(cron_expr)
        except Exception as err:
            logger.error(f"[RcloneWebdavBackup] Cron 表达式无效：{err}")
            return []
        return [{
            "id": f"{self.__class__.__name__}.Backup",
            "name": "Rclone WebDAV 增量备份",
            "trigger": trigger,
            "func": self._start_worker,
            "kwargs": {},
        }]

    def stop_service(self) -> None:
        self._stop_event.set()
        self._enabled = False
        worker = self._worker
        if worker and worker.is_alive() and worker is not threading.current_thread():
            worker.join(timeout=3)

    # -------------------------- SQLite --------------------------

    def _connect(self) -> sqlite3.Connection:
        if not self._db_path:
            raise RuntimeError("数据库尚未初始化")
        conn = sqlite3.connect(str(self._db_path), timeout=30, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _ensure_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backup_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plugin_id TEXT NOT NULL,
                    rel_path TEXT NOT NULL,
                    size INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    backup_time TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(plugin_id, rel_path, size)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_rclone_backup_status
                ON backup_tasks(plugin_id, status, id)
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backup_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    plugin_id TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    status TEXT NOT NULL,
                    scanned INTEGER DEFAULT 0,
                    skipped INTEGER DEFAULT 0,
                    success INTEGER DEFAULT 0,
                    failed INTEGER DEFAULT 0,
                    message TEXT
                )
            """)

    def _plugin_id(self) -> str:
        return self.__class__.__name__

    def _reset_interrupted(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE backup_tasks SET status='pending', error='上次运行中断，等待重试', updated_at=? "
                "WHERE plugin_id=? AND status='running'",
                (self._now(), self._plugin_id()),
            )

    def _insert_scan(self, files: list[dict]) -> tuple[int, int, int, list[dict]]:
        scanned, inserted, skipped = len(files), 0, 0
        pending = []
        seen_ids = set()
        now = self._now()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for item in files:
                rel = self._clean_rel(item.get("Path", ""))
                if not rel or rel == ".":
                    continue
                size = int(item.get("Size", -1))
                if size < 0:
                    continue
                existing = conn.execute("""
                    SELECT id, size, status, attempts FROM backup_tasks
                    WHERE plugin_id=? AND rel_path=? ORDER BY id
                """, (self._plugin_id(), rel)).fetchall()
                row = next((record for record in existing if record["size"] == size), None)
                if row is None and existing:
                    row = existing[-1]
                    conn.execute("""
                        DELETE FROM backup_tasks
                        WHERE plugin_id=? AND rel_path=? AND id!=?
                    """, (self._plugin_id(), rel, row["id"]))
                    conn.execute("""
                        UPDATE backup_tasks
                        SET size=?, status='pending', backup_time=NULL, attempts=0,
                            error=NULL, created_at=?, updated_at=?
                        WHERE id=? AND plugin_id=?
                    """, (size, now, now, row["id"], self._plugin_id()))
                    inserted += 1
                elif row is None:
                    cur = conn.execute("""
                        INSERT INTO backup_tasks
                        (plugin_id, rel_path, size, status, created_at, updated_at)
                        VALUES (?, ?, ?, 'pending', ?, ?)
                    """, (self._plugin_id(), rel, size, now, now))
                    inserted += cur.rowcount
                    row = conn.execute("""
                        SELECT id, size, status, attempts FROM backup_tasks
                        WHERE id=? AND plugin_id=?
                    """, (cur.lastrowid, self._plugin_id())).fetchone()
                else:
                    conn.execute("""
                        DELETE FROM backup_tasks
                        WHERE plugin_id=? AND rel_path=? AND id!=?
                    """, (self._plugin_id(), rel, row["id"]))
                row = conn.execute("""
                    SELECT id, rel_path, size, status, attempts FROM backup_tasks
                    WHERE id=? AND plugin_id=?
                """, (row["id"], self._plugin_id())).fetchone()
                if row["status"] == "success":
                    skipped += 1
                elif row["id"] not in seen_ids:
                    pending.append(dict(row))
                    seen_ids.add(row["id"])
        return scanned, inserted, skipped, pending

    @staticmethod
    def _clean_rel(value: str) -> str:
        value = str(value or "").replace("\\", "/").lstrip("/")
        normalized = posixpath.normpath(value)
        if normalized in ("", "."):
            return ""
        if normalized == ".." or normalized.startswith("../"):
            raise ValueError(f"非法相对路径：{value}")
        return normalized

    def _claim_task(self, task_id: int) -> bool:
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("""
                UPDATE backup_tasks
                SET status='running', attempts=attempts+1, error=NULL, updated_at=?
                WHERE id=? AND plugin_id=? AND status IN ('pending', 'failed')
            """, (self._now(), task_id, self._plugin_id()))
            return cur.rowcount == 1

    def _set_task(self, task_id: int, status: str, error: str | None = None) -> None:
        with self._connect() as conn:
            if status == "success":
                conn.execute("""
                    UPDATE backup_tasks SET status='success', backup_time=?, error=NULL, updated_at=?
                    WHERE id=? AND plugin_id=?
                """, (self._now(), self._now(), task_id, self._plugin_id()))
            else:
                conn.execute("""
                    UPDATE backup_tasks SET status=?, error=?, updated_at=?
                    WHERE id=? AND plugin_id=?
                """, (status, (error or "")[:2000], self._now(), task_id, self._plugin_id()))

    # -------------------------- Rclone RC --------------------------

    def _rc_url(self, endpoint: str) -> str:
        root = str(self._config.get("rc_url") or "").strip().rstrip("/")
        if not root:
            raise RuntimeError("未配置 Rclone RC 地址")
        return f"{root}/{endpoint.lstrip('/')}"

    def _rc(self, endpoint: str, payload: dict | None = None, timeout: int | None = None) -> dict:
        data = json.dumps(payload or {}).encode("utf-8")
        req = urllib.request.Request(
            self._rc_url(endpoint), data=data, method="POST",
            headers={"Content-Type": "application/json"},
        )
        user = str(self._config.get("rc_user") or "")
        password = str(self._config.get("rc_password") or "")
        if user or password:
            token = (user + ":" + password).encode("utf-8")
            import base64
            req.add_header("Authorization", "Basic " + base64.b64encode(token).decode("ascii"))
        try:
            with urllib.request.urlopen(
                req, timeout=timeout or int(self._config.get("rc_timeout") or 60)
            ) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8") or "{}")
        except urllib.error.HTTPError as err:
            body = err.read().decode("utf-8", "replace")
            raise RuntimeError(f"Rclone RC HTTP {err.code}: {body[:1000]}") from err
        except Exception as err:
            raise RuntimeError(f"Rclone RC 请求失败：{err}") from err

    def _remote_root(self, remote: str, path: str) -> str:
        remote = str(remote or "").strip().rstrip(":")
        if not remote or any(c in remote for c in "/\\\\"):
            raise ValueError("Remote 名称不能为空，且不能包含斜杠")
        path = self._clean_rel(path)
        return f"{remote}:{path}" if path else f"{remote}:"

    def _list_source(self) -> list[dict]:
        source = self._remote_root(
            self._config.get("source_remote"), self._config.get("source_path", "")
        )
        result = self._rc("operations/list", {
            "fs": source,
            "remote": "",
            "opt": {"recurse": True, "filesOnly": True},
        }, timeout=max(int(self._config.get("rc_timeout") or 60), 300))
        entries = result.get("list")
        if not isinstance(entries, list):
            raise RuntimeError("operations/list 未返回有效文件列表")

        files = []
        for item in entries:
            if not isinstance(item, dict) or item.get("IsDir") is True:
                continue
            path, size = item.get("Path"), item.get("Size")
            if (not isinstance(path, str) or not path
                    or isinstance(size, bool) or not isinstance(size, (int, float))
                    or size < 0):
                continue
            rel = self._clean_rel(path)
            if rel:
                files.append({"Path": rel, "Size": int(size)})
        files.sort(key=lambda item: item["Path"])
        return files

    def _copy_file(self, task: dict, run_id: int | None = None) -> None:
        rel = self._clean_rel(task["rel_path"])
        source_root = self._remote_root(self._config.get("source_remote"), self._config.get("source_path", ""))
        destination_root = self._remote_root(self._config.get("destination_remote"), self._config.get("destination_path", ""))
        source_file = source_root.rstrip("/") + "/" + rel
        parent = posixpath.dirname(rel)
        destination_dir = destination_root.rstrip("/")
        if parent:
            destination_dir += "/" + parent

        args = [
            source_file, destination_dir,
            "--retries=2", "--low-level-retries=5",
            "--stats=0", "--log-level=ERROR",
        ]
        log_context = (
            f"run={run_id or '-'} task={task['id']} path={rel!r} "
            f"size={task['size']}B attempt={task.get('attempts', 0)}"
        )
        logger.info(
            f"[RcloneWebdavBackup] {log_context} 开始 copy：{source_file} -> {destination_dir}"
        )
        copy_started = time.monotonic()
        result = self._rc("core/command", {
            "command": "copy",
            "arg": args,
            "opt": {},
            "_async": True,
            "returnType": "COMBINED_OUTPUT",
        }, timeout=int(self._config.get("rc_timeout") or 60))
        if not isinstance(result, dict):
            raise RuntimeError("rclone copy 返回结构异常")
        job_id = result.get("jobid")
        if result.get("error"):
            raise RuntimeError(f"rclone copy 失败：{str(result['error'])[:300]}")
        logger.info(
            f"[RcloneWebdavBackup] {log_context} copy 已提交"
            + (f"，jobid={job_id}" if job_id else "（同步返回）")
        )
        if job_id:
            while not self._stop_event.is_set():
                state = self._rc("job/status", {"jobid": job_id})
                if not isinstance(state, dict):
                    raise RuntimeError("rclone copy 任务状态返回结构异常")
                if state.get("error"):
                    raise RuntimeError(f"rclone copy 失败：{str(state['error'])[:300]}")
                if state.get("finished"):
                    if state.get("success") is not True:
                        raise RuntimeError(f"rclone copy 失败：{state.get('error') or state}")
                    break
                time.sleep(1)
            else:
                raise RuntimeError("插件停止，copy 任务未完成")
        logger.info(
            f"[RcloneWebdavBackup] {log_context} copy 完成，"
            f"耗时 {time.monotonic() - copy_started:.1f}s"
        )

        stat_started = time.monotonic()
        logger.info(f"[RcloneWebdavBackup] {log_context} 开始校验目标：{destination_root}/{rel}")
        stat = self._rc(
            "operations/stat",
            {"fs": destination_root, "remote": rel},
            timeout=min(int(self._config.get("rc_timeout") or 60), 60),
        )
        if isinstance(stat, dict) and stat.get("error"):
            raise RuntimeError(f"目标文件 stat 失败：{str(stat['error'])[:300]}")
        stat_item = stat.get("item") if isinstance(stat, dict) else None
        if not isinstance(stat_item, dict):
            raise RuntimeError("目标文件 stat 未返回有效 item，未登记成功")
        target_size = stat_item.get("Size")
        if isinstance(target_size, bool) or not isinstance(target_size, (int, float)):
            raise RuntimeError("目标文件 stat 未返回有效 Size，未登记成功")
        if int(target_size) != int(task["size"]):
            raise RuntimeError(
                f"目标大小校验失败：源 {task['size']} 字节，目标 {int(target_size)} 字节"
            )
        logger.info(
            f"[RcloneWebdavBackup] {log_context} 目标校验通过："
            f"{int(target_size)}B，耗时 {time.monotonic() - stat_started:.1f}s"
        )
    # -------------------------- Worker --------------------------

    def _start_worker(self) -> bool:
        if not self._enabled or self._stop_event.is_set():
            return False
        with self._worker_lock:
            if self._worker and self._worker.is_alive():
                logger.info("[RcloneWebdavBackup] 上一次备份仍在运行，本次触发跳过")
                return False
            self._worker = threading.Thread(
                target=self._run_backup, name=f"{self._plugin_id()}-worker", daemon=True
            )
            self._worker.start()
            return True

    def _run_backup(self) -> None:
        if not self._run_lock.acquire(blocking=False):
            return
        run_id = None
        started = self._now()
        run_started = time.monotonic()
        summary = {"scanned": 0, "inserted": 0, "skipped": 0, "success": 0, "failed": 0}
        self._runtime_status = "running"
        self._last_summary = dict(summary)
        try:
            with self._connect() as conn:
                cur = conn.execute("""
                    INSERT INTO backup_runs(plugin_id, started_at, status)
                    VALUES (?, ?, 'running')
                """, (self._plugin_id(), started))
                run_id = cur.lastrowid

            source = self._remote_root(
                self._config.get("source_remote"), self._config.get("source_path", "")
            )
            destination = self._remote_root(
                self._config.get("destination_remote"), self._config.get("destination_path", "")
            )
            workers = max(1, min(16, int(self._config.get("concurrency") or 4)))
            logger.info(
                f"[RcloneWebdavBackup] run={run_id} 开始备份："
                f"{source} -> {destination}，并发={workers}"
            )
            self._reset_interrupted()
            logger.info(f"[RcloneWebdavBackup] run={run_id} 开始扫描源文件")
            files = self._list_source()
            scanned, inserted, skipped, pending = self._insert_scan(files)
            summary["scanned"], summary["inserted"] = scanned, inserted
            summary["skipped"] = skipped
            self._last_summary = dict(summary)
            logger.info(
                f"[RcloneWebdavBackup] run={run_id} 扫描完成："
                f"发现={scanned} 新增或待处理={len(pending)} "
                f"已成功跳过={skipped} 新建或变更={inserted}"
            )

            def process_one(task: dict) -> tuple[bool, str]:
                if self._stop_event.is_set():
                    logger.warning(
                        f"[RcloneWebdavBackup] run={run_id} task={task['id']} "
                        f"path={task['rel_path']!r} 插件停止，未开始处理"
                    )
                    return False, "插件停止"
                task_started = time.monotonic()
                task["attempts"] = task.get("attempts", 0) + 1
                try:
                    self._copy_file(task, run_id)
                    self._set_task(task["id"], "success")
                    logger.info(
                        f"[RcloneWebdavBackup] run={run_id} task={task['id']} "
                        f"path={task['rel_path']!r} size={task['size']}B "
                        f"attempt={task['attempts']} 备份成功，"
                        f"总耗时 {time.monotonic() - task_started:.1f}s"
                    )
                    return True, ""
                except Exception as err:
                    safe_error = f"{type(err).__name__}: {err}"
                    self._set_task(task["id"], "failed", safe_error)
                    logger.exception(
                        f"[RcloneWebdavBackup] run={run_id} task={task['id']} "
                        f"path={task['rel_path']!r} size={task['size']}B "
                        f"attempt={task['attempts']} 备份失败，"
                        f"耗时 {time.monotonic() - task_started:.1f}s：{safe_error}"
                    )
                    return False, safe_error

            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="rclone-copy") as pool:
                futures = set()
                pending_tasks = iter(pending)
                exhausted = False
                while not self._stop_event.is_set():
                    while len(futures) < workers and not exhausted:
                        try:
                            task = next(pending_tasks)
                        except StopIteration:
                            exhausted = True
                            break
                        if not self._claim_task(task["id"]):
                            continue
                        futures.add(pool.submit(process_one, task))
                    if not futures:
                        break
                    done = next(as_completed(futures))
                    futures.remove(done)
                    ok, _ = done.result()
                    summary["success" if ok else "failed"] += 1
                    self._last_summary = dict(summary)
                    completed = summary["success"] + summary["failed"]
                    logger.info(
                        f"[RcloneWebdavBackup] run={run_id} 进度 "
                        f"{completed}/{len(pending)}：成功={summary['success']} "
                        f"失败={summary['failed']} 跳过={summary['skipped']}"
                    )

            self._runtime_status = "stopped" if self._stop_event.is_set() else "idle"
            message = "任务已停止" if self._stop_event.is_set() else "备份执行完成"
            run_status = "stopped" if self._stop_event.is_set() else "finished"
            logger.info(
                f"[RcloneWebdavBackup] run={run_id} {message}："
                f"扫描={summary['scanned']} 跳过={summary['skipped']} "
                f"成功={summary['success']} 失败={summary['failed']}，"
                f"总耗时 {time.monotonic() - run_started:.1f}s"
            )
        except Exception as err:
            logger.exception(
                f"[RcloneWebdavBackup] run={run_id or '-'} 备份运行异常："
                f"{type(err).__name__}: {err}"
            )
            message = str(err)
            run_status = "failed"
            self._runtime_status = "error"
        finally:
            self._last_summary = dict(summary)
            if run_id is not None:
                with self._connect() as conn:
                    conn.execute("""
                        UPDATE backup_runs SET finished_at=?, status=?, scanned=?, skipped=?,
                        success=?, failed=?, message=? WHERE id=? AND plugin_id=?
                    """, (
                        self._now(), locals().get("run_status", "failed"),
                        summary["scanned"], summary["skipped"], summary["success"],
                        summary["failed"], locals().get("message", ""), run_id, self._plugin_id()
                    ))
            self._run_lock.release()

    # -------------------------- API / UI data --------------------------

    def _status_payload(self) -> dict:
        counts = {"pending": 0, "running": 0, "success": 0, "failed": 0}
        if self._db_path and self._db_path.exists():
            with self._connect() as conn:
                rows = conn.execute("""
                    SELECT status, COUNT(*) AS total FROM backup_tasks
                    WHERE plugin_id=? GROUP BY status
                """, (self._plugin_id(),)).fetchall()
                counts.update({row["status"]: row["total"] for row in rows})
        return {
            "enabled": self._enabled,
            "status": self._runtime_status,
            "counts": counts,
            "summary": self._last_summary,
            "source": self._config.get("source_remote", ""),
            "destination": self._config.get("destination_remote", ""),
            "updated_at": self._now(),
        }

    def api_status(self):
        return self._status_payload()

    def api_tasks(self, page: int = 1, page_size: int = 100, status: str | None = None):
        page = max(1, int(page or 1))
        page_size = max(1, min(500, int(page_size or 100)))
        where = "plugin_id=?"
        params: list[Any] = [self._plugin_id()]
        if status in ("pending", "running", "success", "failed"):
            where += " AND status=?"
            params.append(status)
        offset = (page - 1) * page_size
        with self._connect() as conn:
            total = conn.execute(
                f"SELECT COUNT(*) FROM backup_tasks WHERE {where}", params
            ).fetchone()[0]
            rows = conn.execute(f"""
                SELECT id, rel_path, size, status, backup_time, attempts, error, updated_at
                FROM backup_tasks WHERE {where}
                ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'failed' THEN 1
                    WHEN 'pending' THEN 2 ELSE 3 END, id DESC
                LIMIT ? OFFSET ?
            """, params + [page_size, offset]).fetchall()
        return {
            "page": page, "page_size": page_size, "total": total,
            "items": [dict(row) for row in rows],
            "status": self._status_payload(),
        }

    def api_run(self):
        started = self._start_worker()
        return {"success": started, "message": "备份任务已启动" if started else "插件未启用或任务正在运行"}

    def api_test(self):
        try:
            result = self._rc("rc/noop", {"plugin": self._plugin_id()})
            return {"success": True, "message": "Rclone RC 连接正常", "result": result}
        except Exception as err:
            return {"success": False, "message": str(err)}
