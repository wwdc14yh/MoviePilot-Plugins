# CloudDrive2Sync

MoviePilot V3 插件：CloudDrive2 网盘 A → B 增量同步。基于 CloudDrive2 gRPC API，
复制由 CD2 服务端跨盘完成，不走本地中转，速度取决于 CD2 与网盘接口。

## 当前状态：骨架 v0.1.0

已完成：
- V3 生命周期：`init_plugin` / `get_state` / `stop_service`（可重复调用、释放连接）
- 定时服务走宿主 `get_service()`（间隔触发），立即运行走 `add_plugin_once_job()`，
  不自建调度器
- 配置表单（Vuetify JSON）：CD2 地址 / Token、源目录、目标目录、轮询间隔、
  三个清理天数、最大重试、立即运行一次
- 任务页面（最小版 `VList`）：文件名、状态（同步中 / 完成 / 失败）、大小、目标路径
- API（auth=bear）：`POST /run_once`、`GET /tasks`、`GET /status`
- 同步引擎：BFS 拉源目录 → 对比状态库 → CopyFile → 目标端复查（哈希优先，size 兜底）
  → 写状态；运行中自动跳过本轮
- 状态库：SQLite WAL，放在插件数据目录（`get_data_path()/clouddrive2sync.db`），
  不写源码目录
- CD2 客户端：RPC 与字段已对官方 `clouddrive.proto`（v1.2.0-beta）核实
  （GetSubFiles / CreateFolder / CopyFile / CloudDriveFile.fileHashes）

记录清理规则（design-v0.1.md 第 6 点）：
- 同步状态是增量依据，源文件还在就不删；源端消失先标记 `source_gone`，
  默认宽限 30 天才删，防止按时间误删导致重复全量复制
- 任务历史：成功默认保留 30 天，失败默认保留 90 天

## 待办

- 在真实 MoviePilot V3 宿主里加载一次验证（导入路径、API 注册、服务清理）
- 确认 `clouddrive2-client` 在宿主环境的 pb2 模块路径，必要时改 `_PB2_CANDIDATES`
- CopyFile 是同步返回结果，没有任务进度接口：页面暂不显示百分比进度，
  后续若要做截图那种进度条，需要再找 CD2 的传输任务 API
- 注册远程命令 `/cd2sync`（PluginAction 事件）
- 需要实时面板时再把页面升级为 Vue 联邦组件（注意联邦 CSS 门禁）
- 插件图标 `CloudDrive2.png` 需放入插件仓库图标目录

## 本地测试

```bash
python3 -m pytest tests/
```

测试用假 CD2 客户端覆盖：首轮同步、增量跳过、失败重试与暂缓、
源端消失标记与清理。不依赖真实 CD2 / MoviePilot 宿主。
