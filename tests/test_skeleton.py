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
        self.fail_dirs = set()
        self.restarted = []
        self.cancelled = []
        self.removed_keys = []
        # GetCopyTasks 报错模拟 (v0.7.0 需求 2): 非空时每次调用都抛错
        self.list_error = None
        self.list_calls = 0

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
        self.list_calls += 1
        if self.list_error:
            raise Cd2Error(self.list_error)
        return list(self.copy_tasks)

    def restart_copy_task(self, source_path, dest_path):
        self.restarted.append((source_path, dest_path))
        for task in self.copy_tasks:
            if (task.source_path == source_path
                    and task.dest_path == dest_path
                    and task.status == 4):
                task.status = 0
                task.errors = []

    def cancel_copy_task(self, source_path, dest_path):
        self.cancelled.append((source_path, dest_path))
        self.copy_tasks = [
            t for t in self.copy_tasks
            if not (t.source_path == source_path
                    and t.dest_path == dest_path)
        ]

    def remove_copy_tasks(self, task_keys):
        keys = set(task_keys)
        self.removed_keys.extend(sorted(keys))
        before = len(self.copy_tasks)
        self.copy_tasks = [
            t for t in self.copy_tasks
            if "%s:%s" % (t.source_path, t.dest_path) not in keys
        ]
        return before - len(self.copy_tasks)

    def get_all_tasks_count(self):
        return {"copyTaskCount": len(self.copy_tasks)}

    def close(self):
        pass

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
        if path in self.fail_dirs:
            raise Cd2Error("模拟目录列举失败: " + path)
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
            # 同步模式下 CD2 任务瞬间完成, 任务列表里留一条 Completed
            self.copy_tasks.append(cd2_mod.Cd2CopyTask(
                source_path=src_path, dest_path=dest_path, status=3,
                total_bytes=src.size, uploaded_bytes=src.size,
                total_files=1, uploaded_files=1))
            result.append(target)
        return result


def make_engine(tmp_path, fake, **overrides):
    cfg_data = {
        "enabled": True,
        "max_retries": 5,
        "tasks": [
            {"name": "默认任务", "mode": "sync",
             "source_path": "/A", "target_path": "/B"}
        ],
    }
    cfg_data.update(overrides)
    cfg = SyncConfig.from_dict(cfg_data)
    # 老测试默认不限并发 (新字段的真实默认是 1, 并发行为有专门测试覆盖)
    for t in cfg.tasks:
        t.max_concurrent_sync = 99
    store = SyncStore(Path(tmp_path) / "test.db")
    return SyncEngine(store, fake, cfg), store


def seed(fake):
    fake.add_dir("/A")
    fake.add_dir("/B")
    fake.add_file("A/movie1.mkv", size=100, check="sha1:1", fid="f1")
    fake.add_file("A/Season 1/ep1.mkv", size=200, check="sha1:2", fid="f2")
    fake.add_file("A/Season 1/ep2.mkv", size=300, check="sha1:3", fid="f3")



def test_first_run_copies_all(tmp_path):
    """新架构: 扫描轮次只提交 (状态 copying), 完成由轮询对账落地。"""
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    s = engine.run_once()
    assert (s.scanned, s.failed) == (3, 0)
    assert store.count_states().get("copying") == 3
    engine.poll_copy_tasks()
    assert store.count_states().get("done") == 3
    tasks = store.list_tasks()
    assert len(tasks) == 3 and all(t["status"] == "done" for t in tasks)
    assert "/B/Season 1/ep1.mkv" in fake.files


def test_second_run_skips_all(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    engine.poll_copy_tasks()
    calls = fake.copy_calls
    s = engine.run_once()
    assert (s.skipped, s.copied) == (3, 0)
    assert fake.copy_calls == calls


def test_changed_file_recopied(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    engine.poll_copy_tasks()
    fake.files["/A/movie1.mkv"].size = 101
    fake.files["/A/movie1.mkv"].check_value = "sha1:changed"
    calls = fake.copy_calls
    s = engine.run_once()
    assert s.skipped == 2 and fake.copy_calls == calls + 1
    engine.poll_copy_tasks()
    assert store.count_states().get("done") == 3


def test_failure_retries_then_defers(tmp_path):
    """提交期失败 (CopyFile 直接报错): 记失败并跨轮重试,
    达到 max_retries 后暂缓, 不再提交。"""
    fake = FakeCd2Client()
    seed(fake)
    fake.fail_sources.add("/A/movie1.mkv")
    engine, store = make_engine(tmp_path, fake, max_retries=2)
    s1 = engine.run_once()
    assert s1.failed == 1
    engine.poll_copy_tasks()
    assert store.count_states().get("done") == 2
    s2 = engine.run_once()
    assert s2.failed == 1
    s3 = engine.run_once()
    assert s3.deferred == 1 and s3.failed == 0


def test_missing_source_marked_gone_and_cleanup(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    engine.poll_copy_tasks()
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
    """真实 CD2 是异步复制: 扫描后只能是同步中, 轮询对账才落地完成。"""
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
    res = engine.poll_copy_tasks()
    total_verified = sum(v["verified"] for v in res.values())
    assert total_verified == 3
    assert fake.copy_calls == 3  # 没有重复提交
    assert store.count_states().get("done") == 3
    assert all(t["status"] == "done" for t in store.list_tasks())
    s3 = engine.run_once()
    assert s3.skipped == 3


def test_async_task_failed_records_failure(tmp_path):
    """远端任务失败: 对账记失败并自动重启; 重试耗尽后 (v0.7.0 需求 4)
    删除 CD2 任务与同步记录, 面板历史结为失败保留。"""
    fake = FakeCd2Client()
    seed(fake)
    fake.async_mode = True
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0,
                                max_retries=1)
    engine.run_once()
    fake.fail_tasks()
    engine.poll_copy_tasks()
    # 第 1 次失败: 记了失败 (历史行), 且已自动重启, 状态回到同步中
    assert len(fake.restarted) == 3
    assert store.count_states().get("copying") == 3
    assert any(t["status"] == "failed" for t in store.list_tasks())
    fake.fail_tasks()
    engine.poll_copy_tasks()
    # 第 2 次失败超过 max_retries=1: 不再重启; CD2 任务被删,
    # sync_state 行被删, 面板历史仍留失败行可查
    assert len(fake.restarted) == 3
    assert store.count_states().get("failed") is None
    assert store.count_states().get("copying") is None
    assert fake.copy_tasks == []
    assert len(fake.removed_keys) == 3
    assert any(t["status"] == "failed" for t in store.list_tasks())


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
    for t in cfg.tasks:
        t.max_concurrent_sync = 99
    engine = SyncEngine(store, fake, cfg)
    s = engine.run_once()
    assert s.failed == 0 and len(s.tasks) == 2
    engine.poll_copy_tasks()
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
    for t in cfg.tasks:
        t.max_concurrent_sync = 99
    engine = SyncEngine(store, fake, cfg)
    engine.run_once()
    engine.poll_copy_tasks()
    # 直接验最终状态: 源被删, 目标就位
    assert "/A/movie1.mkv" not in fake.files
    assert "/B/movie1.mkv" in fake.files
    assert "/A/Season 1" not in fake.dirs  # 空目录被清理
    assert store.count_states("mv") == {}  # 移动后状态行清除
    s2 = engine.run_once()
    assert s2.scanned == 0


def test_move_mode_async_pending_keeps_source(tmp_path):
    """异步未完成时绝不删源; 轮询对账确认完成后才删。"""
    fake = FakeCd2Client()
    seed(fake)
    fake.async_mode = True
    cfg = SyncConfig.from_dict({
        "enabled": True, "verify_wait_seconds": 0,
        "tasks": [{"id": "mv", "name": "搬运", "mode": "move",
                   "source_path": "/A", "target_path": "/B"}],
    })
    store = SyncStore(Path(tmp_path) / "test.db")
    for t in cfg.tasks:
        t.max_concurrent_sync = 99
    engine = SyncEngine(store, fake, cfg)
    s1 = engine.run_once()
    assert s1.pending == 3 and s1.moved == 0
    assert "/A/movie1.mkv" in fake.files
    engine.poll_copy_tasks()  # 远端还没完成: 不删源
    assert "/A/movie1.mkv" in fake.files
    fake.complete_tasks()
    engine.poll_copy_tasks()
    assert "/A/movie1.mkv" not in fake.files
    assert store.count_states("mv") == {}


def test_backup_mode_rename_on_change_and_no_gone(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    cfg = SyncConfig.from_dict({
        "enabled": True,
        "tasks": [{"id": "bk", "name": "备份", "mode": "backup",
                   "source_path": "/A", "target_path": "/B"}],
    })
    store = SyncStore(Path(tmp_path) / "test.db")
    for t in cfg.tasks:
        t.max_concurrent_sync = 99
    engine = SyncEngine(store, fake, cfg)
    engine.run_once()
    engine.poll_copy_tasks()
    # 源文件变化: 备份模式应以 rename 策略复制新版, 保留旧版
    fake.add_file("A/movie1.mkv", size=111, check="sha1:1b", fid="f1")
    fake.policies.clear()
    engine.run_once()
    assert "rename" in fake.policies
    engine.poll_copy_tasks()
    # 源文件消失: 备份模式不标记 gone
    del fake.files["/A/movie1.mkv"]
    s = engine.run_once()
    assert s.gone_marked == 0
    assert store.count_states("bk").get("done") == 3


def test_config_tasks_parse_no_legacy_migration(tmp_path):
    """v0.6.2 起不再做旧单任务迁移: 只有顶层路径、没有 tasks 时
    任务列表为空 (删掉最后一个任务后不能被复活成默认任务)。"""
    cfg = SyncConfig.from_dict({"source_path": "/A", "target_path": "/B"})
    assert cfg.tasks == []
    assert SyncConfig.from_dict(cfg.to_dict()).tasks == []
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
    plugin.init_plugin({"enabled": True, "tasks": [
        {"id": "t1", "name": "任务一", "mode": "sync",
         "source_path": "/A", "target_path": "/B"}]})
    assert plugin.get_state() is True
    form, defaults = plugin.get_form()
    assert defaults["copy_poll_interval_seconds"] == 10
    assert defaults["state_tombstone_days"] == 30
    assert "verify_wait_seconds" not in defaults
    assert "verify_interval_seconds" not in defaults
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
    plugin.init_plugin({"enabled": True, "tasks": [
        {"id": "t1", "name": "任务一", "mode": "sync",
         "source_path": "/A", "target_path": "/B"}]})
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
    assert plugin.plugin_version == "0.7.1"
    plugin.stop_service()



def test_excluded_file_skipped_and_listing(tmp_path):
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    engine.poll_copy_tasks()
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
    res = plugin.api_save_task(
        name="新任务", mode="backup", source_path="/C", target_path="/D",
        max_concurrent_sync=3)
    assert res["ok"] and res["created"] is True
    assert len(plugin._config.tasks) == 2
    names = [t.name for t in plugin._config.tasks]
    assert names == ["老任务", "新任务"]
    new_id = res["task"]["id"]
    assert new_id != "a1"
    assert res["task"]["max_concurrent_sync"] == 3
    # 更新: 带已有 id 应命中更新
    res2 = plugin.api_save_task(
        id=new_id, name="新任务改", mode="move",
        source_path="/C", target_path="/D")
    assert res2["ok"] and res2["created"] is False
    assert plugin._config.tasks[1].name == "新任务改"
    # 删除
    res3 = plugin.api_delete_task(task_id=new_id)
    assert res3["ok"] and len(plugin._config.tasks) == 1
    plugin.stop_service()



def test_copy_submit_deadline_becomes_pending_not_failed(tmp_path):
    """CopyFile 提交超时: 服务端可能已接单, 应转 copying 由轮询对账。"""
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
    res = engine.poll_copy_tasks()
    total_verified = sum(v["verified"] for v in res.values())
    assert total_verified == 3
    assert fake.copy_calls == 3  # 没有重复提交

def test_files_pagination_and_save_global(tmp_path):
    spec = importlib.util.spec_from_file_location(
        "plugin_main_page", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_page"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    saved = {}
    plugin.update_config = lambda cfg: saved.update(cfg) or True
    plugin.init_plugin({"enabled": True, "tasks": [
        {"id": "t1", "name": "任务一", "mode": "sync",
         "source_path": "/A", "target_path": "/B"}]})
    store = plugin._store
    for i in range(25):
        store.upsert_done(
            state_key=store_mod.state_key_of("t1", f"f{i}", f"/A/{i}.mkv"),
            task_id="t1", source_path=f"/A/{i}.mkv",
            source_file_id=f"f{i}", size=100 + i, check_value=f"h{i}",
            target_path=f"/B/{i}.mkv")
    # 分页: 第一页 10 条, 总数 25; 第三页 5 条
    p1 = plugin.api_files(task_id="t1", limit=10, offset=0)
    assert p1["total"] == 25 and len(p1["files"]) == 10
    p3 = plugin.api_files(task_id="t1", limit=10, offset=20)
    assert len(p3["files"]) == 5
    names = {r["file_name"] for r in p1["files"]}
    assert names.isdisjoint({r["file_name"] for r in p3["files"]})
    # 状态过滤分页
    pf = plugin.api_files(task_id="t1", status="failed", limit=10, offset=0)
    assert pf["total"] == 0 and pf["files"] == []
    # 全局设置: 改轮询间隔/超时, 任务列表不受影响
    res = plugin.api_save_global(copy_poll_interval_seconds=45,
                                 copy_timeout_seconds=300)
    assert res["ok"]
    assert plugin._config.copy_poll_interval_seconds == 45
    assert plugin._config.copy_timeout_seconds == 300
    assert len(plugin._config.tasks) == 1
    # /status 带全局配置
    st = plugin.api_status()
    assert st["config"]["copy_poll_interval_seconds"] == 45
    plugin.stop_service()



def test_target_moved_away_still_done_and_not_recopied(tmp_path):
    """目标文件被 MoviePilot 整理移走后: 不判失败, 也不重复复制。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    seed(fake)
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0)
    engine.run_once()
    fake.complete_tasks()
    res = engine.poll_copy_tasks()
    total_verified = sum(v["verified"] for v in res.values())
    assert total_verified == 3
    # 模拟整理: 目标文件全部移走
    for path in list(fake.files):
        if path.startswith("/B/"):
            del fake.files[path]
    s3 = engine.run_once()
    assert s3.skipped == 3 and s3.copied == 0 and s3.failed == 0
    assert fake.copy_calls == 3  # 没有陷入 "复制->被移走->再复制" 循环


def test_failed_recheck_fixed_by_completed_task(tmp_path):
    """轮询对账复检失败项: CD2 任务已完成的修正为已同步,
    包括重试次数已耗尽的项目, 且不重新提交复制。"""
    fake = FakeCd2Client()
    seed(fake)
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0)
    task_id = engine.config.tasks[0].id
    src = fake.files["/A/movie1.mkv"]
    key = store_mod.state_key_of(task_id, src.id, "/A/movie1.mkv")
    for _ in range(5):  # 失败到重试耗尽 (max_retries=5)
        store.record_failure(
            state_key=key, task_id=task_id, source_path="/A/movie1.mkv",
            source_file_id=src.id, size=src.size,
            check_value=src.check_value, target_path="/B/movie1.mkv",
            error="CD2 任务已完成, 但目标文件缺失或校验不一致")
    fake.copy_tasks.append(cd2_mod.Cd2CopyTask(
        source_path="/A/movie1.mkv", dest_path="/B", status=3,
        total_files=1, uploaded_files=1, failed_files=0))
    engine.run_once()
    res = engine.poll_copy_tasks()
    state = store.get_state(key)
    assert state["status"] == "done"
    total_verified = sum(v["verified"] for v in res.values())
    assert total_verified >= 1
    assert fake.copy_calls == 2  # 只有另外两个文件被正常复制

def test_api_signatures_fastapi_safe(tmp_path):
    """宿主把插件 API 注册为 FastAPI 路由: 端点签名里不能有
    **kwargs 或 dict 参数, 否则真实宿主会返回 422 请求参数不正确。"""
    import inspect

    spec = importlib.util.spec_from_file_location(
        "plugin_main_sig", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_sig"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    for api in plugin.get_api():
        sig = inspect.signature(api["endpoint"])
        for param in sig.parameters.values():
            assert param.kind != inspect.Parameter.VAR_KEYWORD, api["path"]
            assert param.annotation is not dict, api["path"]



def test_per_task_concurrency_limit(tmp_path):
    """每任务并发上限: 同时在传不超过 N 个; 对账完成一个, 下一轮
    扫描才补一个 (或由积压补交在对账后立即补)。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    seed(fake)
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0)
    engine.config.tasks[0].max_concurrent_sync = 1

    s1 = engine.run_once()
    assert s1.pending == 1 and fake.copy_calls == 1
    fake.complete_tasks()
    engine.poll_copy_tasks()  # 对账完成第 1 个 + 积压补交第 2 个
    assert store.count_states().get("done") == 1
    assert fake.copy_calls == 2
    fake.complete_tasks()
    engine.poll_copy_tasks()
    assert store.count_states().get("done") == 2
    assert fake.copy_calls == 3
    fake.complete_tasks()
    engine.poll_copy_tasks()
    assert store.count_states().get("done") == 3

    # 上限为 2 时, 第一轮同时进行 2 个
    fake2 = FakeCd2Client()
    fake2.async_mode = True
    seed(fake2)
    engine2, _ = make_engine(tmp_path, fake2, verify_wait_seconds=0)
    engine2.config.tasks[0].max_concurrent_sync = 2
    s = engine2.run_once()
    assert s.pending == 2 and fake2.copy_calls == 2


def test_concurrency_slot_refills_within_round(tmp_path):
    """上限 1 但文件秒传: 对账腾出名额后积压补交立即跟上,
    不用等下一轮定时扫描就能依次传完。"""
    fake = FakeCd2Client()  # 同步模式: 提交即在 CD2 端完成
    seed(fake)
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0)
    engine.config.tasks[0].max_concurrent_sync = 1
    s = engine.run_once()
    assert fake.copy_calls == 1  # 只提交了 1 个, 其余暂缓
    for _ in range(5):
        engine.poll_copy_tasks()
        if store.count_states().get("done") == 3:
            break
    assert fake.copy_calls == 3
    assert store.count_states().get("done") == 3

def test_settle_only_and_dest_fullpath_match(tmp_path):
    """快速结算: 不跑整轮也能把同步中结算为已同步;
    CD2 把 destPath 记成目标文件全路径时同样能匹配上。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    seed(fake)
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0)
    s1 = engine.run_once()
    assert s1.pending == 3
    # 第一个任务 (movie1) 的 dest 改成目标文件全路径的形态
    fake.copy_tasks[0].dest_path = "/B/movie1.mkv"
    fake.complete_tasks()
    res = engine.settle_only()
    assert fake.copy_calls == 3  # 没有重新提交
    assert store.count_states().get("done") == 3
    total_verified = sum(v["verified"] for v in res.values())
    assert total_verified == 3


def test_store_reopen_after_close(tmp_path):
    """连接被 close 后操作自动重开 (重初始化与在跑轮次并发时不报
    Cannot operate on a closed database), purge_task 连带清状态。"""
    store = store_mod.SyncStore(tmp_path / "x.db")
    store.upsert_done(
        state_key="k1", task_id="t1", source_path="/A/a.mkv",
        source_file_id="f1", size=1, check_value="h",
        target_path="/B/a.mkv")
    store.close()
    assert store.get_state("k1")["status"] == "done"
    store.upsert_copying(
        state_key="k2", task_id="t1", source_path="/A/b.mkv",
        source_file_id="f2", size=2, check_value="h2",
        target_path="/B/b.mkv")
    assert store.count_states().get("copying") == 1
    store.purge_task("t1")
    assert store.count_states() == {}
    store.close()


def test_delete_task_purges_states(tmp_path):
    """删除任务: 配置里去掉 + 状态记录连带清理, 其它任务不受影响;
    删除时正好有一轮在跑 (引擎锁被占用) 也不能失败。"""
    import threading

    spec = importlib.util.spec_from_file_location(
        "plugin_main_del", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_del"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    saved = {}
    plugin.update_config = lambda cfg: saved.update(cfg) or True
    plugin.init_plugin({"enabled": True, "tasks": [
        {"id": "t1", "name": "任务一", "mode": "sync",
         "source_path": "/A", "target_path": "/B"},
        {"id": "t2", "name": "任务二", "mode": "sync",
         "source_path": "/C", "target_path": "/D"}]})
    store = plugin._store
    for tid in ("t1", "t2"):
        store.upsert_done(
            state_key=store_mod.state_key_of(tid, "f1", "/A/a.mkv"),
            task_id=tid, source_path="/A/a.mkv", source_file_id="f1",
            size=1, check_value="h", target_path="/B/a.mkv")
    # 模拟一轮正在跑: 占住引擎锁, 删除在另一线程执行
    plugin._engine._lock.acquire()
    result = {}

    def do_delete():
        result.update(plugin.api_delete_task(task_id="t1"))

    th = threading.Thread(target=do_delete)
    th.start()
    threading.Event().wait(0.5)
    plugin._engine._lock.release()
    th.join(timeout=10)
    assert result.get("ok"), result
    assert [t.id for t in plugin._config.tasks] == ["t2"]
    assert plugin._store.count_states("t1") == {}
    assert plugin._store.count_states("t2").get("done") == 1
    plugin.stop_service()



def test_walk_skips_bad_subdir_and_root_failure(tmp_path):
    """子目录列举失败 (如 WebDAV 上游异常) 只跳过该目录, 整轮不失败,
    且不把该目录里的历史文件误标为源端消失; 根目录失败才整轮失败。"""
    fake = FakeCd2Client()
    fake.add_dir("/A")
    fake.add_dir("/A/Bad")
    fake.add_file("/A/good.mkv")
    fake.add_file("/A/Bad/x.mkv")
    fake.fail_dirs = {"/A/Bad"}
    engine, store = make_engine(tmp_path, fake)
    task_id = engine.config.tasks[0].id
    key_x = store_mod.state_key_of(task_id, "id-/A/Bad/x.mkv", "/A/Bad/x.mkv")
    store.upsert_done(
        state_key=key_x, task_id=task_id, source_path="/A/Bad/x.mkv",
        source_file_id="id-/A/Bad/x.mkv", size=100,
        check_value="sha1:aaa", target_path="/B/Bad/x.mkv")
    s = engine.run_once()
    assert s.failed == 0 and fake.copy_calls == 1
    engine.poll_copy_tasks()
    assert store.get_state(key_x)["status"] == "done"
    fake.fail_dirs = {"/A"}
    s2 = engine.run_once()
    assert s2.tasks and s2.tasks[0].get("error")

def test_debug_logging_config(tmp_path):
    cfg = SyncConfig.from_dict({"debug_logging": True})
    assert cfg.debug_logging is True
    assert cfg.to_dict()["debug_logging"] is True
    assert SyncConfig.from_dict({}).debug_logging is False


def test_poll_removes_only_own_completed_tasks(tmp_path):
    """对账完成后用 RemoveCopyTasks 只删本插件结算的那条 CD2 任务,
    CD2 里其它已完成任务 (如手动建的) 不受影响。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    seed(fake)
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0)
    engine.config.tasks[0].max_concurrent_sync = 1
    engine.run_once()
    # 一条与本插件无关的已完成任务
    fake.copy_tasks.append(cd2_mod.Cd2CopyTask(
        source_path="/X/other.mkv", dest_path="/Y", status=3,
        total_files=1, uploaded_files=1, failed_files=0))
    fake.complete_tasks()
    engine.poll_copy_tasks()
    assert store.count_states().get("done") == 1
    assert fake.removed_keys == ["/A/movie1.mkv:/B"]
    remaining = {(t.source_path, t.dest_path) for t in fake.copy_tasks}
    assert ("/X/other.mkv", "/Y") in remaining


def test_poll_failed_source_gone_deletes_record(tmp_path):
    """v0.7.1 改判: 远端失败 + 实查源文件已不存在 -> 删 CD2 任务
    与同步记录 (不再落 excluded), 面板行结为失败留原因, 不重启。
    源真没了, 后续扫描也不会再发现它。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    seed(fake)
    engine, store = make_engine(tmp_path, fake, verify_wait_seconds=0)
    engine.config.tasks[0].max_concurrent_sync = 1
    engine.run_once()
    task_id = engine.config.tasks[0].id
    key = store_mod.state_key_of(task_id, "f1", "/A/movie1.mkv")
    assert store.get_state(key)["status"] == "copying"
    del fake.files["/A/movie1.mkv"]  # 源文件被删了
    fake.fail_tasks()
    engine.poll_copy_tasks()
    assert fake.restarted == []
    # 双侧删除: 本地记录消失, CD2 任务被取消+移除, 不留 excluded
    # (轮询末尾的并发补齐会把队列里的下一个文件提交进来,
    # 所以只断言 movie1 自己的 CD2 任务已不在)
    assert store.get_state(key) is None
    assert store.list_states(status="excluded") == []
    assert all(t.source_path != "/A/movie1.mkv"
               for t in fake.copy_tasks)
    assert ("/A/movie1.mkv", "/B") in fake.cancelled
    assert "/A/movie1.mkv:/B" in fake.removed_keys
    # 面板行结为失败, 原因写明不存在 (可能为误报) + 已删除等复核
    failed_rows = [t for t in store.list_tasks()
                   if t["status"] == "failed"]
    assert len(failed_rows) == 1
    assert "源或目标不存在" in (failed_rows[0]["error"] or "")
    assert "已删除复制任务与同步记录" in (failed_rows[0]["error"] or "")
    assert "源文件不存在" in (failed_rows[0]["error"] or "")


def test_poll_interval_config_roundtrip(tmp_path):
    """新增全局配置 copy_poll_interval_seconds: 默认 10, 可保存可读回,
    save_global 接口能改 (前端全局设置用)。"""
    assert SyncConfig.from_dict({}).copy_poll_interval_seconds == 10
    cfg = SyncConfig.from_dict({"copy_poll_interval_seconds": 25})
    assert cfg.to_dict()["copy_poll_interval_seconds"] == 25

    spec = importlib.util.spec_from_file_location(
        "plugin_main_poll", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_poll"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    saved = {}
    plugin.update_config = lambda c: saved.update(c) or True
    plugin.init_plugin({"enabled": True, "tasks": []})
    res = plugin.api_save_global(copy_poll_interval_seconds=30)
    assert res["ok"] and res["config"]["copy_poll_interval_seconds"] == 30
    import datetime as _dt
    import types as _types

    class _FakeTrigger:
        def __init__(self, minutes=0, seconds=0, **kw):
            self.interval = _dt.timedelta(minutes=minutes, seconds=seconds)

    _trig = _types.ModuleType("apscheduler.triggers.interval")
    _trig.IntervalTrigger = _FakeTrigger
    sys.modules.setdefault("apscheduler", _types.ModuleType("apscheduler"))
    sys.modules["apscheduler.triggers"] = _types.ModuleType(
        "apscheduler.triggers")
    sys.modules["apscheduler.triggers.interval"] = _trig
    services = plugin.get_service()
    poll = [x for x in services if x["id"].endswith("Poll")]
    assert len(poll) == 1
    assert poll[0]["trigger"].interval.total_seconds() == 30
    plugin.stop_service()


def test_delete_task_cancels_copying_cd2_tasks(tmp_path):
    """删任务时先用 CancelCopyTask 取消它进行中的 CD2 复制任务。"""
    spec = importlib.util.spec_from_file_location(
        "plugin_main_cancel", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_cancel"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    saved = {}
    plugin.update_config = lambda c: saved.update(c) or True
    plugin.init_plugin({"enabled": True, "tasks": [
        {"id": "t1", "name": "任务一", "mode": "sync",
         "source_path": "/A", "target_path": "/B"}]})
    fake = FakeCd2Client()
    plugin._client = fake
    plugin._engine.client = fake
    plugin._store.upsert_copying(
        state_key=store_mod.state_key_of("t1", "f1", "/A/a.mkv"),
        task_id="t1", source_path="/A/a.mkv", source_file_id="f1",
        size=1, check_value="h", target_path="/B/a.mkv")
    res = plugin.api_delete_task(task_id="t1")
    assert res.get("ok"), res
    assert fake.cancelled == [("/A/a.mkv", "/B")]
    plugin.stop_service()


def test_per_task_scan_interval_services(tmp_path):
    """扫描间隔是任务配置项: 每个启用的任务注册独立的调度服务,
    间隔各读各的; 全局配置里不再有这个字段。"""
    assert "interval_minutes" not in SyncConfig.from_dict({}).to_dict()
    task = config_mod.SyncTask.from_dict(
        {"source_path": "/A", "target_path": "/B"})
    assert task.interval_minutes == 30
    task2 = config_mod.SyncTask.from_dict(
        {"source_path": "/A", "target_path": "/B", "interval_minutes": 5})
    assert task2.interval_minutes == 5
    assert task2.to_dict()["interval_minutes"] == 5

    spec = importlib.util.spec_from_file_location(
        "plugin_main_svc", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_svc"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    plugin.update_config = lambda c: True
    plugin.init_plugin({"enabled": True, "tasks": [
        {"id": "ta", "name": "甲", "mode": "sync", "source_path": "/A",
         "target_path": "/B", "interval_minutes": 15},
        {"id": "tb", "name": "乙", "mode": "sync", "source_path": "/A",
         "target_path": "/C", "interval_minutes": 60},
        {"id": "tc", "name": "丙", "mode": "sync", "source_path": "/A",
         "target_path": "/D", "enabled": False},
    ]})
    import datetime as _dt
    import types as _types

    class _FakeTrigger:
        def __init__(self, minutes=0, seconds=0, **kw):
            self.interval = _dt.timedelta(minutes=minutes, seconds=seconds)

    _trig = _types.ModuleType("apscheduler.triggers.interval")
    _trig.IntervalTrigger = _FakeTrigger
    sys.modules.setdefault("apscheduler", _types.ModuleType("apscheduler"))
    sys.modules["apscheduler.triggers"] = _types.ModuleType(
        "apscheduler.triggers")
    sys.modules["apscheduler.triggers.interval"] = _trig
    services = plugin.get_service()
    scans = {x["id"]: x for x in services if ".Sync." in x["id"]}
    assert set(scans) == {"CloudDrive2Sync.Sync.ta",
                          "CloudDrive2Sync.Sync.tb"}  # 禁用的丙没有服务
    assert scans["CloudDrive2Sync.Sync.ta"]["trigger"].interval \
        == _dt.timedelta(minutes=15)
    assert scans["CloudDrive2Sync.Sync.tb"]["kwargs"] == {"task_id": "tb"}
    # 保存任务接口能改间隔
    res = plugin.api_save_task(id="ta", name="甲", mode="sync",
                               source_path="/A", target_path="/B",
                               interval_minutes=45)
    assert res["ok"] and res["task"]["interval_minutes"] == 45
    # 回归: /status 必须把 interval_minutes 带回给前端, 否则编辑弹窗
    # 读不到已保存的值, 永远显示默认 30 (v0.6.3 的实际 bug)
    st = plugin.api_status()
    by_id = {x["id"]: x for x in st["tasks"]}
    assert by_id["ta"]["interval_minutes"] == 45
    assert by_id["tb"]["interval_minutes"] == 60
    plugin.stop_service()


def test_delete_only_task_stays_deleted(tmp_path):
    """回归: 只有一个任务时删除它, 不能被旧单任务迁移复活成默认任务。"""
    spec = importlib.util.spec_from_file_location(
        "plugin_main_del1", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_del1"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    saved = {}
    plugin.update_config = lambda c: saved.update(c) or True
    plugin.init_plugin({"enabled": True, "tasks": [
        {"id": "only", "name": "唯一任务", "mode": "sync",
         "source_path": "/WebDAV/quark/整理失败",
         "target_path": "/MoviePilot Library/Test"}]})
    assert len(plugin._config.tasks) == 1
    res = plugin.api_delete_task(task_id="only")
    assert res.get("ok"), res
    assert plugin._config.tasks == []
    assert plugin.api_status()["tasks"] == []
    # 持久化后的配置再读回来也不能复活
    assert SyncConfig.from_dict(saved).tasks == []
    plugin.stop_service()


# ---------- v0.7.0 新需求 ----------


def _backdate_submitted(store, seconds):
    """把所有 copying 记录的提交时间往前拨 (模拟宽限期已过)。"""
    with store._lock:
        store._conn.execute(
            "UPDATE sync_state SET submitted_at = submitted_at - ? "
            "WHERE status = 'copying'", (seconds,))
        store._conn.commit()


def test_poll_missing_task_deleted_after_grace(tmp_path):
    """需求 1: copying 项在 CD2 列表里查不到, 宽限内保留,
    超过 10 分钟宽限删除同步项并把面板行结为失败; done 项不动。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    task_id = engine.config.tasks[0].id
    engine.run_once()
    assert store.count_states().get("copying") == 3
    # 一条已同步记录: 对账删除绝不能碰 done
    done_key = store_mod.state_key_of(task_id, "fx", "/A/old.mkv")
    store.upsert_done(
        state_key=done_key, task_id=task_id, source_path="/A/old.mkv",
        source_file_id="fx", size=1, check_value="h",
        target_path="/B/old.mkv")
    fake.copy_tasks = []  # CD2 侧任务全部不在列表里了
    engine.poll_copy_tasks()
    # 宽限期内: 还在等, 不删
    assert store.count_states().get("copying") == 3
    _backdate_submitted(store, 601)
    engine.poll_copy_tasks()
    assert store.count_states().get("copying") is None
    assert store.get_state(done_key)["status"] == "done"
    rows = [t for t in store.list_tasks() if t["status"] == "failed"]
    assert len(rows) == 3
    assert all("CD2 任务不存在" in (t["error"] or "") for t in rows)
    # 源文件还在: 下次扫描会重新提交
    engine.run_once()
    assert store.count_states().get("copying") == 3


def test_poll_list_error_retries_then_deletes_both_sides(tmp_path):
    """需求 2: GetCopyTasks 报错 -> 单轮重试 3 次、错误经 poll_error
    暴露; 连续 3 个周期失败后按库存路径删 CD2 任务 + 本地记录。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    assert store.count_states().get("copying") == 3
    fake.list_error = "模拟 GetCopyTasks 失败"
    res = engine.poll_copy_tasks()
    assert fake.list_calls == 3  # 单轮内重试 3 次
    assert res["poll_error"]["count"] == 1
    assert engine.poll_error["count"] == 1
    # 阈值未到: 不删任何东西
    assert store.count_states().get("copying") == 3
    assert fake.cancelled == [] and fake.removed_keys == []
    engine.poll_copy_tasks()
    assert engine.poll_error["count"] == 2
    assert store.count_states().get("copying") == 3
    res = engine.poll_copy_tasks()
    assert res["deleted"] == 3
    assert store.count_states().get("copying") is None
    # 双侧都删: CD2 侧逐项 Cancel + Remove (按库存路径拼的 key)
    assert len(fake.cancelled) == 3
    assert set(fake.removed_keys) == {
        "/A/movie1.mkv:/B",
        "/A/Season 1/ep1.mkv:/B/Season 1",
        "/A/Season 1/ep2.mkv:/B/Season 1",
    }
    assert fake.copy_tasks == []
    rows = [t for t in store.list_tasks() if t["status"] == "failed"]
    assert len(rows) == 3
    assert all("持续报错" in (t["error"] or "") for t in rows)
    # 删除完成后计数清零, 不重复触发
    assert engine.poll_error is None


def test_status_includes_poll_error(tmp_path):
    """需求 2 (插件层): /status 返回 poll_error, 无错误时为 None。"""
    spec = importlib.util.spec_from_file_location(
        "plugin_main_pollerr", PLUGIN_DIR / "__init__.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["plugin_main_pollerr"] = mod
    spec.loader.exec_module(mod)
    plugin = mod.CloudDrive2Sync()
    plugin._data_path_override = str(tmp_path)
    plugin.init_plugin({"enabled": True, "tasks": [
        {"id": "t1", "name": "任务一", "mode": "sync",
         "source_path": "/A", "target_path": "/B"}]})
    assert plugin.api_status()["poll_error"] is None
    fake = FakeCd2Client()
    fake.list_error = "模拟列表接口失败"
    plugin._client = fake
    plugin._engine.client = fake
    plugin._store.upsert_copying(
        state_key=store_mod.state_key_of("t1", "f1", "/A/a.mkv"),
        task_id="t1", source_path="/A/a.mkv", source_file_id="f1",
        size=1, check_value="h", target_path="/B/a.mkv")
    plugin.run_poll()
    err = plugin.api_status()["poll_error"]
    assert err and err["count"] == 1
    assert "模拟列表接口失败" in err["error"]
    plugin.stop_service()


def test_poll_top_up_refills_slots(tmp_path):
    """需求 3 (10->8 的缩小版): 上限 3、在传 3, 完成 1 个后
    下次轮询从待提交队列补齐回 3, 不等下一轮扫描。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    fake.add_dir("/A")
    fake.add_dir("/B")
    for i in range(5):
        fake.add_file("A/f%d.mkv" % i, size=100 + i,
                      check="sha1:%d" % i, fid="f%d" % i)
    engine, store = make_engine(tmp_path, fake)
    engine.config.tasks[0].max_concurrent_sync = 3
    engine.run_once()
    assert fake.copy_calls == 3
    assert store.count_states().get("copying") == 3
    # 只完成第 1 个任务 (在传 3 -> 2)
    first = fake.copy_tasks[0]
    first.status = 3
    first.uploaded_files = first.total_files
    first.uploaded_bytes = first.total_bytes
    engine.poll_copy_tasks()
    assert store.count_states().get("done") == 1
    assert fake.copy_calls == 4  # 队列补交 1 个
    assert store.count_states().get("copying") == 3
    # 再完成 1 个 -> 再补 1 个, 队列见底
    second = [t for t in fake.copy_tasks if t.status != 3][0]
    second.status = 3
    second.uploaded_files = second.total_files
    second.uploaded_bytes = second.total_bytes
    engine.poll_copy_tasks()
    assert fake.copy_calls == 5
    assert store.count_states().get("done") == 2
    assert store.count_states().get("copying") == 3
    fake.complete_tasks()
    engine.poll_copy_tasks()
    assert store.count_states().get("done") == 5


def test_poll_early_scan_throttled_then_triggered(tmp_path):
    """需求 3: 队列空但有名额时提前扫描补新文件, 但距上次扫描
    不足 5 分钟不重复触发。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    seed(fake)
    engine, store = make_engine(tmp_path, fake)
    task_id = engine.config.tasks[0].id
    engine.config.tasks[0].max_concurrent_sync = 2
    engine.run_once()
    assert fake.copy_calls == 2  # 第 3 个在队列里
    fake.complete_tasks()
    engine.poll_copy_tasks()
    # 对账完成 2 个 + 队列补交第 3 个; 名额仍空 1 个,
    # 但刚扫描过 (<5 分钟), 不提前扫描
    assert store.count_states().get("done") == 2
    assert fake.copy_calls == 3
    # 新增一个源文件, 并把上次扫描时间拨到 5 分钟前
    fake.add_file("A/new.mkv", size=50, check="sha1:new", fid="fnew")
    engine._last_scan_at[task_id] -= 301
    fake.complete_tasks()
    engine.poll_copy_tasks()
    # 第 3 个完成结算 + 提前扫描发现新文件并提交
    assert store.count_states().get("done") == 3
    assert fake.copy_calls == 4
    assert store.count_states().get("copying") == 1


def test_stalled_failed_files_treated_as_failed(tmp_path):
    """需求 4 / S01E05: CD2 任务级状态还是已扫描 (Scanned),
    但 failed_files=1 且连续 2 个轮询无进展 -> 按失败处理
    (记失败 + RestartCopyTask), 不再无限期显示同步中。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    fake.add_dir("/A")
    fake.add_dir("/B")
    fake.add_file("A/e05.mkv", size=100, check="sha1:e05", fid="fe05")
    engine, store = make_engine(tmp_path, fake, max_retries=5)
    engine.run_once()
    assert store.count_states().get("copying") == 1
    task = fake.copy_tasks[0]
    task.status = 2  # Scanned
    task.failed_files = 1
    task.uploaded_bytes = 0
    task.uploaded_files = 0
    task.errors = ["模拟单文件失败"]
    engine.poll_copy_tasks()
    # 第 1 个无进展轮询: 还在观察, 不判失败
    assert fake.restarted == []
    assert store.count_states().get("copying") == 1
    engine.poll_copy_tasks()
    # 第 2 个无进展轮询: 判失败并已自动重启
    assert fake.restarted == [("/A/e05.mkv", "/B")]
    assert store.count_states().get("copying") == 1
    assert any(t["status"] == "failed" for t in store.list_tasks())


def test_poll_over_limit_deletes_and_rescans(tmp_path):
    """需求 4: 失败超过 max_retries -> 删 CD2 任务 + 删 sync_state 行,
    面板历史结为失败保留; 源文件还在, 下次扫描重新提交。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    fake.add_dir("/A")
    fake.add_dir("/B")
    fake.add_file("A/x.mkv", size=100, check="sha1:x", fid="fx")
    engine, store = make_engine(tmp_path, fake, max_retries=1)
    task_id = engine.config.tasks[0].id
    key = store_mod.state_key_of(task_id, "fx", "/A/x.mkv")
    engine.run_once()
    fake.fail_tasks()
    engine.poll_copy_tasks()
    assert len(fake.restarted) == 1
    assert store.get_state(key)["status"] == "copying"
    fake.fail_tasks()
    engine.poll_copy_tasks()
    # 超限: 双侧删除, 历史保留
    assert store.get_state(key) is None
    assert fake.copy_tasks == []
    assert fake.removed_keys == ["/A/x.mkv:/B"]
    assert ("/A/x.mkv", "/B") in fake.cancelled
    failed_rows = [t for t in store.list_tasks()
                   if t["status"] == "failed"]
    assert len(failed_rows) >= 1
    # 源文件还在: 下次扫描重新提交
    calls = fake.copy_calls
    engine.run_once()
    assert fake.copy_calls == calls + 1
    assert store.get_state(key)["status"] == "copying"


def test_identity_size_mismatch_not_matched(tmp_path):
    """需求 5: 单文件 CD2 任务的 total_bytes 与记录大小对不上 ->
    视为未匹配 (同路径换了文件), 不按完成结算; 过宽限后按
    查无任务删除同步项。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    fake.add_dir("/A")
    fake.add_dir("/B")
    fake.add_file("A/s.mkv", size=100, check="sha1:s", fid="fs")
    engine, store = make_engine(tmp_path, fake)
    engine.run_once()
    assert store.count_states().get("copying") == 1
    task = fake.copy_tasks[0]
    task.status = 3  # Completed, 但大小是另一个文件的
    task.total_bytes = 999
    task.uploaded_bytes = 999
    task.uploaded_files = 1
    engine.poll_copy_tasks()
    assert store.count_states().get("done") is None
    assert store.count_states().get("copying") == 1
    _backdate_submitted(store, 601)
    engine.poll_copy_tasks()
    assert store.count_states().get("copying") is None


def test_store_migration_only_done_rows(tmp_path):
    """需求 6: 老库 (v1 无 meta) 打开时先备份, 只迁 done 行到新表,
    旧表重命名 *_v1 保留, 写 schema_version=2; 重开不重复迁移;
    全新安装直接是 v2。"""
    import glob
    import sqlite3

    db_path = Path(tmp_path) / "old.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
    CREATE TABLE sync_state (
        state_key TEXT PRIMARY KEY, task_id TEXT NOT NULL DEFAULT '',
        source_path TEXT NOT NULL, source_file_id TEXT,
        size INTEGER NOT NULL DEFAULT 0, check_value TEXT,
        target_path TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'done',
        retry_count INTEGER NOT NULL DEFAULT 0,
        first_seen_at REAL NOT NULL, last_seen_at REAL NOT NULL,
        submitted_at REAL, finished_at REAL, gone_at REAL,
        last_error TEXT);
    CREATE TABLE sync_task (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id TEXT NOT NULL DEFAULT '', file_name TEXT NOT NULL,
        source_path TEXT NOT NULL, target_path TEXT NOT NULL,
        size INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'syncing', error TEXT,
        started_at REAL NOT NULL, finished_at REAL);
    """)
    now = time.time()
    state_rows = [
        ("k-done1", "t1", "/A/a.mkv", "f1", 10, "h1", "/B/a.mkv",
         "done", 0, now, now, None, now, None, None),
        ("k-done2", "t1", "/A/sub/b.mkv", "f2", 20, "h2", "/B/sub/b.mkv",
         "done", 0, now, now, None, now, None, None),
        ("k-copy", "t1", "/A/c.mkv", "f3", 30, "h3", "/B/c.mkv",
         "copying", 0, now, now, now, None, None, None),
        ("k-fail", "t1", "/A/d.mkv", "f4", 40, "h4", "/B/d.mkv",
         "failed", 3, now, now, None, None, None, "boom"),
    ]
    conn.executemany(
        "INSERT INTO sync_state VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        state_rows)
    conn.executemany(
        "INSERT INTO sync_task (task_id, file_name, source_path, "
        "target_path, size, status, error, started_at, finished_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        [("t1", "a.mkv", "/A/a.mkv", "/B/a.mkv", 10, "done", None,
          now, now),
         ("t1", "d.mkv", "/A/d.mkv", "/B/d.mkv", 40, "failed", "boom",
          now, now),
         ("t1", "c.mkv", "/A/c.mkv", "/B/c.mkv", 30, "syncing", None,
          now, None)])
    conn.commit()
    conn.close()

    store = SyncStore(db_path)
    info = store.migration_info
    assert info is not None
    assert info["state_migrated"] == 2 and info["state_dropped"] == 2
    assert info["task_migrated"] == 1 and info["task_dropped"] == 2
    # 备份文件存在
    assert glob.glob(str(db_path) + ".bak-*")
    assert Path(info["backup_path"]).exists()
    with store._lock:
        tables = {r[0] for r in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        version = store._conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()[0]
    assert "sync_state_v1" in tables and "sync_task_v1" in tables
    assert version == "2"
    # 只迁了 done 行, 且 file_name 已按源路径补好
    states = store.list_states()
    assert {s["state_key"] for s in states} == {"k-done1", "k-done2"}
    by_key = {s["state_key"]: s for s in states}
    assert by_key["k-done1"]["file_name"] == "a.mkv"
    assert by_key["k-done2"]["file_name"] == "b.mkv"
    tasks = store.list_tasks()
    assert len(tasks) == 1 and tasks[0]["status"] == "done"
    store.close()
    # 重开: 已是 v2, 不再迁移, 数据不变
    store2 = SyncStore(db_path)
    assert store2.migration_info is None
    assert store2.count_states().get("done") == 2
    store2.close()
    # 全新安装: 直接 v2 空库
    fresh = SyncStore(Path(tmp_path) / "fresh.db")
    assert fresh.migration_info is None
    assert fresh.count_states() == {}
    with fresh._lock:
        version = fresh._conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()[0]
    assert version == "2"
    fresh.close()


# ---------- v0.7.1 不存在类失败改判删除 + 存量清理 ----------


def test_poll_failed_notfound_misreport_deletes_and_rescans(tmp_path):
    """v0.7.1: 源文件实际存在且大小一致, CD2 却报 source file
    not found (误报) -> 按错误信息判为不存在类失败: 删 CD2 任务
    与同步记录 (不落 excluded), 面板结为失败; 源还在, 下一轮
    扫描重新发现并提交复核。"""
    fake = FakeCd2Client()
    fake.async_mode = True
    fake.add_dir("/A")
    fake.add_dir("/B")
    fake.add_file("A/keep.mkv", size=100, check="sha1:k", fid="fk")
    engine, store = make_engine(tmp_path, fake)
    task_id = engine.config.tasks[0].id
    key = store_mod.state_key_of(task_id, "fk", "/A/keep.mkv")
    engine.run_once()
    assert store.get_state(key)["status"] == "copying"
    # CD2 任务失败, 错误是 not found, 但源文件其实还在 (误报)
    task = fake.copy_tasks[0]
    task.status = 4
    task.errors = ["source file not found: /A/keep.mkv"]
    engine.poll_copy_tasks()
    assert fake.restarted == []
    assert store.get_state(key) is None
    assert store.list_states(status="excluded") == []
    assert fake.copy_tasks == []
    assert ("/A/keep.mkv", "/B") in fake.cancelled
    assert "/A/keep.mkv:/B" in fake.removed_keys
    failed_rows = [t for t in store.list_tasks()
                   if t["status"] == "failed"]
    assert len(failed_rows) == 1
    assert "按错误信息判断" in (failed_rows[0]["error"] or "")
    # 源文件还在: 下一轮扫描重新提交
    calls = fake.copy_calls
    engine.run_once()
    assert fake.copy_calls == calls + 1
    assert store.get_state(key)["status"] == "copying"


def test_store_cleanup_notexist_excluded_once(tmp_path):
    """v0.7.1 一次性存量清理: 打开 v2 库时删掉旧版按「不存在」
    判定落成 excluded 的行 (last_error 带 "已跳过 (" 前缀这一
    固定标记); 页面手动排除的行 (set_excluded 从不写 last_error:
    为空, 或是原始失败详情) 一律保留, 哪怕详情含 not found
    字样; meta 标记保证重复打开不重复执行。"""
    import sqlite3

    db_path = Path(tmp_path) / "v2.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(store_mod._SCHEMA)
    conn.execute(
        "INSERT INTO meta (key, value) VALUES ('schema_version', '2')")
    now = time.time()
    rows = [
        # 旧版不存在类跳过 (清理目标, 即 S04E12 那类误杀记录)
        ("k-notexist", "/A/gone.mkv", "excluded",
         "已跳过 (源或目标不存在 (按错误信息判断)): /B/gone.mkv: "
         "source file not found: /A/gone.mkv"),
        # 手动排除的已同步文件: last_error 为空 -> 保留
        ("k-manual-done", "/A/keep1.mkv", "excluded", None),
        # 手动排除的失败文件: last_error 是原始失败详情 (无前缀),
        # 含 not found 字样也保留
        ("k-manual-failed", "/A/keep2.mkv", "excluded",
         "复制失败: source file not found"),
    ]
    for key, src, status, err in rows:
        conn.execute(
            "INSERT INTO sync_state (state_key, task_id, source_path,"
            " target_path, status, first_seen_at, last_seen_at,"
            " last_error) VALUES (?,?,?,?,?,?,?,?)",
            (key, "t1", src, "/B" + src[2:], status, now, now, err))
    conn.commit()
    conn.close()

    store = SyncStore(db_path)
    assert store.notexist_cleanup_count == 1
    keys = {s["state_key"] for s in store.list_states()}
    assert keys == {"k-manual-done", "k-manual-failed"}
    with store._lock:
        marker = store._conn.execute(
            "SELECT value FROM meta WHERE key = ?",
            ("cleanup_notexist_excluded_v071",)).fetchone()
    assert marker is not None and marker[0] == "1"
    store.close()
    # 重复打开: 标记已在, 不再执行, 保留行不动, 计数为 0
    store2 = SyncStore(db_path)
    assert store2.notexist_cleanup_count == 0
    assert {s["state_key"] for s in store2.list_states()} == keys
    store2.close()
