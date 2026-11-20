"""CloudDrive2 gRPC 客户端适配层。

RPC 和字段均已对着官方 clouddrive.proto (v1.2.0-beta) 核实:
- GetSubFiles(ListSubFileRequest{path, forceRefresh}) -> stream SubFilesReply
- CreateFolder(CreateFolderRequest{parentPath, folderName}) -> CreateFolderResult
- CopyFile(CopyFileRequest{theFilePaths[], destPath, conflictPolicy,
  handleConflictRecursively}) -> FileOperationResult{success, errorMessage,
  resultFilePaths}
- CloudDriveFile{id, name, fullPathName, size, isDirectory, fileHashes}
  fileHashes 的 HashType: Unknown=0, Md5=1, Sha1=2, PikPakSha1=3
- GetCopyTasks(Empty) -> GetCopyTaskResult{copyTasks}: CopyFile 是异步的,
  返回 success 只代表任务已提交; 完成/失败看 CopyTask.status
  (Pending=0, Scanning=1, Scanned=2, Completed=3, Failed=4),
  进度看 uploadedBytes/totalBytes。

生成的 pb2 存根不在本仓库: 运行时从以下模块路径依次尝试导入,
都找不到时抛 Cd2DependencyError 并说明怎么生成/安装。
"""
from __future__ import annotations

from dataclasses import dataclass, field

_PB2_CANDIDATES = (
    ("clouddrive_pb2", "clouddrive_pb2_grpc"),
    ("clouddrive2_client.proto.clouddrive_pb2",
     "clouddrive2_client.proto.clouddrive_pb2_grpc"),
    ("clouddrive2_client.clouddrive_pb2",
     "clouddrive2_client.clouddrive_pb2_grpc"),
)

_CONFLICT_POLICIES = {"overwrite": 0, "rename": 1, "skip": 2}
_HASH_PRIORITY = ((2, "sha1"), (1, "md5"), (3, "pikpak_sha1"))

# CopyTask.TaskStatus (clouddrive.proto): 复制是异步任务, CopyFile 返回成功
# 只代表任务已提交, 真正完成要看这里的状态变成 Completed。
_COPY_TASK_STATUS = {
    0: "Pending",
    1: "Scanning",
    2: "Scanned",
    3: "Completed",
    4: "Failed",
}


class Cd2Error(Exception):
    """CD2 调用失败 (业务错误或传输错误)。"""


class Cd2DependencyError(Cd2Error):
    """缺少 grpc / pb2 存根依赖。"""


@dataclass
class Cd2File:
    """引擎使用的统一文件模型, 与具体 pb2 类型解耦。"""

    id: str = ""
    name: str = ""
    full_path: str = ""
    size: int = 0
    is_directory: bool = False
    check_value: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Cd2CopyTask:
    """CD2 异步复制任务 (GetCopyTasks 返回的 CopyTask)。"""

    source_path: str = ""
    dest_path: str = ""
    status: int = 0
    task_mode: int = 0
    total_files: int = 0
    uploaded_files: int = 0
    failed_files: int = 0
    total_bytes: int = 0
    uploaded_bytes: int = 0
    paused: bool = False
    errors: list = field(default_factory=list)
    start_time: float = 0.0

    @property
    def status_name(self):
        return _COPY_TASK_STATUS.get(int(self.status), "Unknown")

    @property
    def is_completed(self):
        return self.status_name == "Completed"

    @property
    def is_failed(self):
        return self.status_name == "Failed"

    @property
    def progress(self):
        """0-100 的字节进度; 总量未知时返回 None。"""
        if self.total_bytes:
            return min(100, int(self.uploaded_bytes * 100 / self.total_bytes))
        if self.total_files:
            return min(100, int(self.uploaded_files * 100 / self.total_files))
        return None


def pick_check_value(file_hashes):
    """从 CD2 fileHashes 里按 sha1 > md5 > pikpak_sha1 选一个校验值。

    返回形如 'sha1:xxxx' 的字符串; 没有哈希时返回空串 (引擎会退回比 size)。
    """
    if not file_hashes:
        return ""
    try:
        items = dict(file_hashes)
    except Exception:
        return ""
    for code, label in _HASH_PRIORITY:
        value = items.get(code) or items.get(str(code))
        if value:
            return label + ":" + str(value)
    for value in items.values():
        if value:
            return "hash:" + str(value)
    return ""


def parent_and_name(path):
    path = "/" + str(path).strip("/")
    parent, _, name = path.rpartition("/")
    return parent or "/", name


class Cd2GrpcClient:
    """基于官方 proto 存根的真实客户端 (延迟连接)。"""

    def __init__(self, address, token="", timeout=60, copy_timeout=180):
        self.address = address
        self.token = token or ""
        self.timeout = timeout
        # CopyFile 是服务端提交操作: 跨盘时 CD2 要建任务/谈秒传,
        # 经常超过普通 RPC 的超时, 单独给长一点
        self.copy_timeout = copy_timeout
        self._channel = None
        self._stub = None
        self._pb2 = None

    # ---------- 连接 ----------

    def _connect(self):
        if self._stub is not None:
            return
        try:
            import grpc
        except Exception as exc:
            raise Cd2DependencyError(
                "缺少 grpcio, 请在插件 pyproject.toml 依赖中安装"
            ) from exc
        pb2 = pb2_grpc = None
        last_exc = None
        for mod_pb2, mod_grpc in _PB2_CANDIDATES:
            try:
                pb2 = __import__(mod_pb2, fromlist=["*"])
                pb2_grpc = __import__(mod_grpc, fromlist=["*"])
                break
            except Exception as exc:  # 试下一个候选路径
                last_exc = exc
                pb2 = pb2_grpc = None
        if pb2 is None:
            raise Cd2DependencyError(
                "找不到 clouddrive pb2 存根: 请 pip install clouddrive2-client, "
                "或用 grpc_tools.protoc 从官方 clouddrive.proto 生成存根后放入插件目录"
            ) from last_exc
        self._pb2 = pb2
        self._channel = grpc.insecure_channel(self.address)
        self._stub = pb2_grpc.CloudDriveFileSrvStub(self._channel)

    def _metadata(self):
        if self.token:
            return (("authorization", "Bearer " + self.token),)
        return ()

    def close(self):
        if self._channel is not None:
            try:
                self._channel.close()
            finally:
                self._channel = None
                self._stub = None

    # ---------- 转换 ----------

    @staticmethod
    def _convert(raw):
        return Cd2File(
            id=str(getattr(raw, "id", "") or ""),
            name=str(getattr(raw, "name", "") or ""),
            full_path=str(getattr(raw, "fullPathName", "") or ""),
            size=int(getattr(raw, "size", 0) or 0),
            is_directory=bool(getattr(raw, "isDirectory", False)),
            check_value=pick_check_value(getattr(raw, "fileHashes", None)),
        )

    # ---------- 业务方法 (引擎只依赖这四个) ----------

    def list_sub_files(self, path, force_refresh=False):
        self._connect()
        request = self._pb2.ListSubFileRequest(
            path=path, forceRefresh=bool(force_refresh)
        )
        files = []
        try:
            for reply in self._stub.GetSubFiles(
                request, metadata=self._metadata(), timeout=self.timeout
            ):
                for raw in reply.subFiles:
                    files.append(self._convert(raw))
        except Exception as exc:
            raise Cd2Error("GetSubFiles " + str(path) + " 失败: " + str(exc)) from exc
        return files

    def find_file_by_path(self, path):
        """按完整路径查单个文件; 查不到返回 None。

        引擎的目标端复查优先用 list_sub_files, 这里只作辅助。
        """
        self._connect()
        parent, _ = parent_and_name(path)
        request = self._pb2.FindFileByPathRequest(parentPath=parent, path=path)
        try:
            raw = self._stub.FindFileByPath(
                request, metadata=self._metadata(), timeout=self.timeout
            )
        except Exception:
            return None
        if raw is None or not (getattr(raw, "fullPathName", "") or getattr(raw, "id", "")):
            return None
        return self._convert(raw)

    def create_folder(self, parent_path, folder_name):
        self._connect()
        request = self._pb2.CreateFolderRequest(
            parentPath=parent_path, folderName=folder_name
        )
        try:
            reply = self._stub.CreateFolder(
                request, metadata=self._metadata(), timeout=self.timeout
            )
        except Exception as exc:
            raise Cd2Error("CreateFolder 失败: " + str(exc)) from exc
        result = getattr(reply, "result", None)
        if result is not None and not getattr(result, "success", True):
            raise Cd2Error(
                "CreateFolder 失败: " + str(getattr(result, "errorMessage", ""))
            )

    def copy_file(self, source_paths, dest_path, conflict_policy="skip"):
        """跨盘复制: CD2 服务端完成, 不走本地中转。返回目标路径列表。"""
        self._connect()
        policy = _CONFLICT_POLICIES.get(str(conflict_policy).lower(), 2)
        request = self._pb2.CopyFileRequest(
            theFilePaths=list(source_paths),
            destPath=dest_path,
            conflictPolicy=policy,
        )
        try:
            reply = self._stub.CopyFile(
                request, metadata=self._metadata(), timeout=self.copy_timeout
            )
        except Exception as exc:
            raise Cd2Error("CopyFile 失败: " + str(exc)) from exc
        if not getattr(reply, "success", False):
            raise Cd2Error(
                "CopyFile 失败: " + str(getattr(reply, "errorMessage", "未知错误"))
            )
        return list(getattr(reply, "resultFilePaths", []) or [])

    def delete_file(self, path):
        """删除单个文件/空目录 (移动模式校验完成后删源用)。

        RPC: DeleteFile(FileRequest{path}) -> FileOperationResult
        普通删除 (进回收站/可恢复), 不用 DeleteFilePermanently。
        """
        self._connect()
        request = self._pb2.FileRequest(path=path)
        try:
            reply = self._stub.DeleteFile(
                request, metadata=self._metadata(), timeout=self.timeout
            )
        except Exception as exc:
            raise Cd2Error("DeleteFile 失败: " + str(exc)) from exc
        if not getattr(reply, "success", False):
            raise Cd2Error(
                "DeleteFile 失败: " + str(getattr(reply, "errorMessage", "未知错误"))
            )

    def get_copy_tasks(self):
        """拉取 CD2 全部复制任务 (异步复制的完成状态以此为准)。

        RPC: GetCopyTasks(google.protobuf.Empty) -> GetCopyTaskResult{copyTasks}
        CopyTask 关键字段: sourcePath, destPath, status, totalBytes,
        uploadedBytes, totalFiles, uploadedFiles, failedFiles, errors。
        """
        self._connect()
        try:
            from google.protobuf import empty_pb2

            request = empty_pb2.Empty()
        except Exception:
            request = None
        try:
            if request is not None:
                reply = self._stub.GetCopyTasks(
                    request, metadata=self._metadata(), timeout=self.timeout
                )
            else:
                reply = self._stub.GetCopyTasks(
                    metadata=self._metadata(), timeout=self.timeout
                )
        except Exception as exc:
            raise Cd2Error("GetCopyTasks 失败: " + str(exc)) from exc
        tasks = []
        for raw in getattr(reply, "copyTasks", []) or []:
            errors = []
            for err in getattr(raw, "errors", []) or []:
                msg = getattr(err, "message", "") or str(err)
                if msg:
                    errors.append(str(msg))
            start_ts = getattr(raw, "startTime", None)
            start_time = 0.0
            if start_ts is not None:
                try:
                    start_time = float(start_ts.ToDatetime().timestamp())
                except Exception:
                    start_time = float(getattr(start_ts, "seconds", 0) or 0)
            tasks.append(
                Cd2CopyTask(
                    source_path=str(getattr(raw, "sourcePath", "") or ""),
                    dest_path=str(getattr(raw, "destPath", "") or ""),
                    status=int(getattr(raw, "status", 0) or 0),
                    task_mode=int(getattr(raw, "taskMode", 0) or 0),
                    total_files=int(getattr(raw, "totalFiles", 0) or 0),
                    uploaded_files=int(getattr(raw, "uploadedFiles", 0) or 0),
                    failed_files=int(getattr(raw, "failedFiles", 0) or 0),
                    total_bytes=int(getattr(raw, "totalBytes", 0) or 0),
                    uploaded_bytes=int(getattr(raw, "uploadedBytes", 0) or 0),
                    paused=bool(getattr(raw, "paused", False)),
                    errors=errors,
                    start_time=start_time,
                )
            )
        return tasks
