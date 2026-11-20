"""CloudDrive2Sync 骨架测试: 假 CD2 客户端, 不依赖真实 CD2 / MoviePilot。"""
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN_DIR = ROOT / "plugins.v3" / "clouddrive2sync"
sys.path.insert(0, str(PLUGIN_DIR))


def _load(name):
    spec = importlib.util.spec_from_file_location(name, PLUGIN_DIR / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


config_mod = _load("config")
store_mod = _load("store")
cd2_mod = _load("cd2_client")
engine_mod = _load("sync_engine")

SyncConfig = config_mod.SyncConfig
SyncStore = store_mod.SyncStore
Cd2File = cd2_mod.Cd2File
Cd2Error = cd2_mod.Cd2Error
SyncEngine = engine_mod.SyncEngine


class FakeCd2Client:
    """内存版 CD2: dirs 是目录集合, files 是 path -> Cd2File。

    async_mode=True 时模拟真实 CD2 的异步复制: copy_file 只提交任务,
    目标文件不立即出现, 要等 complete_tasks() 后 CopyTask 才 Completed。
    """

    def __init__(self):
        self.dirs = set()
        self.files = {}
        self.fail_sources = set()
        self.copy_calls = 0
        self.async_mode = False
        self.copy_tasks = []
        self.deleted = []
        self.policies = []
        self.deadline_sources = set()

    def delete_file(self, path):
        self.deleted.append(path)
        if path in self.files:
            del self.files[path]
            return
        if path in self.dirs:
            self.dirs.discard(path)
            return
        raise Cd2Error("删除失败, 路径不存在: " + path)

    def get_copy_tasks(self):
        return list(self.copy_tasks)

    def complete_tasks(self):
        for task in self.copy_tasks:
            if task.status == 3:
                continue
            src = self.files[task.source_path]
            target = task.dest_path.rstrip("/") + "/" + src.name
            self.files[target] = Cd2File(
                id="copy-" + target, name=src.name, full_path=target,
                size=src.size, is_directory=False,
                check_value=src.check_value)
            task.status = 3
            task.uploaded_bytes = task.total_bytes
            task.uploaded_files = task.total_files

    def fail_tasks(self):
        for task in self.copy_tasks:
            task.status = 4
            task.errors = ["模拟任务失败"]

    def add_dir(self, path):
        self.dirs.add(path)

    def add_file(self, path, size=100, check="sha1:aaa", fid=None):
        parent, _, name = ("/" + path.strip("/")).rpartition("/")
        self.dirs.add(parent or "/")
        f = Cd2File(id=fid or ("id-" + path), name=name,
                    full_path="/" + path.strip("/"), size=size,
                    is_directory=False, check_value=check)
        self.files[f.full_path] = f
        return f

    def list_sub_files(self, path, force_refresh=False):
        if path not in self.dirs:
            raise Cd2Error("目录不存在: " + path)
        out = []
        for d in sorted(self.dirs):
            parent, _, name = d.rpartition("/")
            if d != path and (parent or "/") == path:
                out.append(Cd2File(id="dir-" + d, name=name, full_path=d,
                                   size=0, is_directory=True))
        for f in self.files.values():
            parent, _, _ = f.full_path.rpartition("/")
            if (parent or "/") == path:
                out.append(f)
        return out

    def create_folder(self, parent_path, folder_name):
        new = (parent_path.rstrip("/") + "/" + folder_name) or "/"
        self.dirs.add(new)

    def copy_file(self, source_paths, dest_path, conflict_policy="skip"):
        self.copy_calls += 1
        self.policies.append(conflict_policy)
        result = []
        for src_path in source_paths:
            if src_path in self.fail_sources:
                raise Cd2Error("模拟复制失败")
            src = self.files[src_path]
            if src_path in self.deadline_sources:
                # 模拟服务端已接单但回复超时: 任务照常建, 客户端抛超时
                self.copy_tasks.append(cd2_mod.Cd2CopyTask(
                    source_path=src_path, dest_path=dest_path, status=0,
                    total_bytes=src.size, uploaded_bytes=0,
                    total_files=1, uploaded_files=0))
                raise Cd2Error(
                    "CopyFile 失败: <_InactiveRpcError status = "
                    "StatusCode.DEADLINE_EXCEEDED details = Deadline Exceeded>"
                )
            if self.async_mode:
                self.copy_tasks.append(cd2_mod.Cd2CopyTask(
                    source_path=src_path, dest_path=dest_path, status=0,
                    total_bytes=src.size, uploaded_bytes=0,
                    total_files=1, uploaded_files=0))
                continue
            name = src.name
            target = dest_path.rstrip("/") + "/" + name
            self.files[target] = Cd2File(
                id="copy-" + target, name=name, full_path=target,
                size=src.size, is_directory=False, check_value=src.check_value)
            result.append(target)
        return result


def make_engine(tmp_path, fake, **overrides):
    cfg_data = {
        "enabled": True,
        "source_path": "/A",
        "target_path": "/B",
        "max_retries": 5,
    }
    cfg_data.update(overrides)
    cfg = SyncConfig.from_dict(cfg_data)
    store = SyncStore(Path(tmp_path) / "test.db")
    return SyncEngine(store, fake, cfg), store


def seed(fake):
    fake.add_dir("/A")
    fake.add_dir("/B")
    fake.add_file("A/movie1.mkv", size=100, check="sha1:1", fid="f1")
    fake.add_file("A/Season 1/ep1.mkv", size=200, check="sha1:2", fid="f2")
    fake.add_file("A/Season 1/ep2.mkv", size=300, check="sha1:3", fid="f3")


def test_first_run_copies_all(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    s = engine.run_once()
    assert (s.scanned, s.copied, s.failed) == (3, 3, 0)
    tasks = store.list_tasks()
    assert len(tasks) == 3 and all(t["status"] == "done" for t in tasks)
    assert "/B/Season 1/ep1.mkv" in fake.files


def test_second_run_skips_all(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    calls = fake.copy_calls
    s = engine.run_once()
    assert (s.skipped, s.copied) == (3, 0)
    assert fake.copy_calls == calls


def test_changed_file_recopied(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    fake.files["/A/movie1.mkv"].size = 101
    fake.files["/A/movie1.mkv"].check_value = "sha1:changed"
    s = engine.run_once()
    assert (s.copied, s.skipped) == (1, 2)


def test_failure_retries_then_defers(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    fake.fail_sources.add("/A/movie1.mkv")
    engine, store = make_engine(tmp_path, fake, max_retries=2)
    s1 = engine.run_once()
    assert s1.failed == 1 and s1.copied == 2
    s2 = engine.run_once()
    assert s2.failed == 1
    s3 = engine.run_once()
    assert s3.deferred == 1 and s3.failed == 0


def test_missing_source_marked_gone_and_cleanup(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    del fake.files["/A/movie1.mkv"]
    s = engine.run_once()
    assert s.gone_marked == 1
    assert store.count_states().get("source_gone") == 1
    future = time.time() + 31 * 86400
    cleaned = store.cleanup(history_retention_days=30, failed_retention_days=90,
                            state_tombstone_days=30, now=future)
    assert cleaned["states_gone"] == 1
    assert cleaned["tasks_done"] == 3


def test_run_skip_when_locked(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine._lock.acquire()
    try:
        s = engine.run_once()
    finally:
        engine._lock.release()
    assert s.skipped_run is True


def test_async_copy_pending_then_verified_next_run(tmp_path):
    """真实 CD2 是异步复制: 第一轮只能 pending, 不能误判失败。"""
    fake = FakeCd2Client()
    seed(fake)
    fake.async_mode = True
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0)
    s1 = engine.run_once()
    assert s1.failed == 0
    assert s1.copied == 0 and s1.pending == 3
    assert fake.copy_calls == 3
    assert store.count_states().get("copying") == 3
    assert all(t["status"] == "syncing" for t in store.list_tasks())
    fake.complete_tasks()
    s2 = engine.run_once()
    assert s2.verified == 3 and s2.pending == 0 and s2.failed == 0
    assert fake.copy_calls == 3  # 没有重复提交
    assert store.count_states().get("done") == 3
    assert all(t["status"] == "done" for t in store.list_tasks())
    s3 = engine.run_once()
    assert s3.skipped == 3


def test_async_task_failed_records_failure(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    fake.async_mode = True
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0)
    engine.run_once()
    fake.fail_tasks()
    s = engine.run_once()
    assert s.failed == 3
    assert store.count_states().get("failed") == 3
    assert all(t["status"] == "failed" for t in store.list_tasks())


def test_multi_task_isolation(tmp_path):
    """同一源目录配两个任务, 状态互不干扰, 各自复制一份。"""
    fake = FakeCd2Client()
    seed(fake)
    fake.add_dir("/C")
    cfg = SyncConfig.from_dict({
        "enabled": True,
        "tasks": [
            {"id": "t1", "name": "到B", "mode": "sync",
             "source_path": "/A", "target_path": "/B"},
            {"id": "t2", "name": "到C", "mode": "sync",
             "source_path": "/A", "target_path": "/C"},
        ],
    })
    store = SyncStore(Path(tmp_path) / "test.db")
    engine = SyncEngine(store, fake, cfg)
    s = engine.run_once()
    assert s.failed == 0 and len(s.tasks) == 2
    assert store.count_states("t1").get("done") == 3
    assert store.count_states("t2").get("done") == 3
    assert "/C/movie1.mkv" in fake.files
    s2 = engine.run_once(task_id="t1")
    assert len(s2.tasks) == 1 and s2.tasks[0]["task_id"] == "t1"
    assert s2.skipped == 3


def test_move_mode_deletes_source_after_verify(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    cfg = SyncConfig.from_dict({
        "enabled": True,
        "tasks": [{"id": "mv", "name": "搬运", "mode": "move",
                   "source_path": "/A", "target_path": "/B",
                   "delete_empty_dirs": True}],
    })
    store = SyncStore(Path(tmp_path) / "test.db")
    engine = SyncEngine(store, fake, cfg)
    s = engine.run_once()
    assert s.copied == 3 and s.moved == 3 and s.failed == 0
    assert "/A/movie1.mkv" not in fake.files
    assert "/B/movie1.mkv" in fake.files
    assert "/A/Season 1" not in fake.dirs  # 空目录被清理
    assert store.count_states("mv") == {}  # 移动后状态行清除
    s2 = engine.run_once()
    assert s2.scanned == 0


def test_move_mode_async_pending_keeps_source(tmp_path):
    """异步未完成时绝不删源; 完成结算后才删。"""
    fake = FakeCd2Client()
    seed(fake)
    fake.async_mode = True
    cfg = SyncConfig.from_dict({
        "enabled": True, "verify_wait_seconds": 0,
        "tasks": [{"id": "mv", "name": "搬运", "mode": "move",
                   "source_path": "/A", "target_path": "/B"}],
    })
    store = SyncStore(Path(tmp_path) / "test.db")
    engine = SyncEngine(store, fake, cfg)
    s1 = engine.run_once()
    assert s1.pending == 3 and s1.moved == 0
    assert "/A/movie1.mkv" in fake.files
    fake.complete_tasks()
    s2 = engine.run_once()
    assert s2.verified == 3 and s2.moved == 3
    assert "/A/movie1.mkv" not in fake.files


def test_backup_mode_rename_on_change_and_no_gone(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    cfg = SyncConfig.from_dict({
        "enabled": True,
        "tasks": [{"id": "bk", "name": "备份", "mode": "backup",
                   "source_path": "/A", "target_path": "/B"}],
    })
    store = SyncStore(Path(tmp_path) / "test.db")
    engine = SyncEngine(store, fake, cfg)
    engine.run_once()
    # 源文件变化: 备份模式应以 rename 策略复制新版, 保留旧版
    fake.add_file("A/movie1.mkv", size=111, check="sha1:1b", fid="f1")
    fake.policies.clear()
    engine.run_once()
    assert "rename" in fake.policies
    # 源文件消失: 备份模式不标记 gone
    del fake.files["/A/movie1.mkv"]
    s = engine.run_once()
    assert s.gone_marked == 0
    assert store.count_states("bk").get("done") == 3


def test_config_legacy_migration_and_tasks_parse(tmp_path):
    cfg = SyncConfig.from_dict({"source_path": "/A", "target_path": "/B"})
    assert len(cfg.tasks) == 1
    assert cfg.tasks[0].mode == "sync"
    assert cfg.tasks[0].source_path == "/A"
    import json as _json
    cfg2 = SyncConfig.from_dict({
        "tasks": _json.dumps([
            {"name": "x", "mode": "move", "source_path": "/S",
             "target_path": "/T"}
        ])
    })
    assert len(cfg2.tasks) == 1 and cfg2.tasks[0].mode == "move"
    assert cfg2.to_dict()["tasks"][0]["mode"] == "move"


def test_plugin_class_loads_and_form(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "plugin_main", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    plugin.init_plugin({"enabled": True, "source_path": "/A",
                        "target_path": "/B"})
    assert plugin.get_state() is True
    form, defaults = plugin.get_form()
    assert defaults["interval_minutes"] == 30
    assert defaults["state_tombstone_days"] == 30
    assert defaults["verify_wait_seconds"] == 30
    assert defaults["conflict_policy"] == "skip"
    paths = [a["path"] for a in plugin.get_api()]
    assert "/save_task" in paths and "/delete_task" in paths and "/files" in paths
    assert plugin.api_status()["states"] == {}
    page = plugin.get_page()
    assert page[0]["component"] == "VCard"
    assert page[1]["component"] == "VCard"
    assert page[1]["content"][1]["component"] == "VList"
    plugin.stop_service()
    plugin.stop_service()
    assert plugin._store is None


class _FakeEvent:
    def __init__(self, action):
        self.event_data = {"action": action}


def test_remote_command_registered(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "plugin_main_cmd", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_cmd"] = mod
    spec.loader.exec_module(mod)
    cmds = mod.CloudDrive2Sync.get_command()
    assert len(cmds) == 1
    cmd = cmds[0]
    assert cmd["cmd"] == "/cd2sync"
    assert cmd["data"] == {"action": "cd2sync_run"}
    assert cmd["desc"] and cmd["category"]


def test_remote_command_triggers_sync_and_ignores_others(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "plugin_main_cmd2", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_cmd2"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    plugin.init_plugin({"enabled": True, "source_path": "/A",
                        "target_path": "/B"})
    assert plugin.get_state() is True
    calls = []
    plugin._run_once_async = lambda: calls.append(True)
    plugin.run_command(_FakeEvent("other_action"))
    assert calls == []
    plugin.run_command(_FakeEvent("cd2sync_run"))
    assert calls == [True]
    plugin.stop_service()


def test_plugin_vue_render_mode_and_status(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "plugin_main_vue", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_vue"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    assert plugin.get_render_mode() == ("vue", "dist/assets")
    plugin.init_plugin({
        "enabled": True,
        "tasks": [{"id": "t1", "name": "任务一", "mode": "move",
                   "source_path": "/A", "target_path": "/B"}],
    })
    nav = plugin.get_sidebar_nav()
    assert nav and nav[0]["nav_key"] == "main"
    status = plugin.api_status()
    assert status["enabled"] is True
    assert status["tasks"][0]["mode"] == "move"
    assert plugin.plugin_version == "0.4.2"
    plugin.stop_service()


def test_excluded_file_skipped_and_listing(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    task_id = engine.config.tasks[0].id
    rows = store.list_states(task_id=task_id, status="done")
    assert len(rows) == 3
    assert store.sum_done_size(task_id) == 600
    key = rows[0]["state_key"]
    store.set_excluded(key)
    fake.copy_calls = 0
    s = engine.run_once()
    assert fake.copy_calls == 0  # 排除的文件不再提交, 其余走跳过
    assert store.get_state(key)["status"] == "excluded"


def test_save_and_delete_task_api(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "plugin_main_tasks", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_tasks"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    saved = {}
    plugin.update_config = lambda cfg: saved.update(cfg) or True
    plugin.init_plugin({"enabled": True, "tasks": [
        {"id": "a1", "name": "老任务", "mode": "sync",
         "source_path": "/A", "target_path": "/B"}]})
    # 新建: 不带 id, 应新增而不是替换老任务
    res = plugin.api_save_task(task={
        "name": "新任务", "mode": "backup",
        "source_path": "/C", "target_path": "/D"})
    assert res["ok"] and res["created"] is True
    assert len(plugin._config.tasks) == 2
    names = [t.name for t in plugin._config.tasks]
    assert names == ["老任务", "新任务"]
    new_id = res["task"]["id"]
    assert new_id != "a1"
    # 更新: 带已有 id 应命中更新
    res2 = plugin.api_save_task(task={
        "id": new_id, "name": "新任务改", "mode": "move",
        "source_path": "/C", "target_path": "/D"})
    assert res2["ok"] and res2["created"] is False
    assert plugin._config.tasks[1].name == "新任务改"
    # 删除
    res3 = plugin.api_delete_task(task_id=new_id)
    assert res3["ok"] and len(plugin._config.tasks) == 1
    plugin.stop_service()


def test_copy_submit_deadline_becomes_pending_not_failed(tmp_path):
    """CopyFile 提交超时: 服务端可能已接单, 应转 copying 跨轮校验。"""
    fake = FakeCd2Client()
    seed(fake)
    fake.deadline_sources = {
        "/A/movie1.mkv", "/A/Season 1/ep1.mkv", "/A/Season 1/ep2.mkv"
    }
    engine, store = make_engine(tmp_path, fake)
    s1 = engine.run_once()
    assert s1.failed == 0 and s1.pending == 3
    assert store.count_states().get("copying") == 3
    fake.complete_tasks()
    s2 = engine.run_once()
    assert s2.verified == 3 and s2.failed == 0
    assert fake.copy_calls == 3  # 没有重复提交
