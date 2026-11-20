# CloudDrive2Sync

MoviePilot V3 插件：CloudDrive2 网盘 A → B 增量同步。基于 CloudDrive2 gRPC API，
复制由 CD2 服务端跨盘完成，不走本地中转，速度取决于 CD2 与网盘接口。

## 当前状态：v0.2.1

已完成：
- 远程命令 `/cd2sync`（`EventType.PluginAction`，`data.action=cd2sync_run`）：触发一次增量同步，与配置页“立即运行一次”走同一入口（宿主调度器优先，否则守护线程），不在事件回调里同步跑完整轮；未启用时只记日志。格式按官方 Plugin_Development.md §9.1 核实。
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
  （GetSubFiles / CreateFolder / CopyFile / GetCopyTasks / CloudDriveFile.fileHashes）
- 多任务（v0.3.0）：每个任务独立的源目录/目标目录/模式/同步状态；
  模式分同步（增量，源端消失按宽限处理）、备份（只增不减，源变化时目标
  保留旧版改名复制，源消失不动目标）、移动（校验完成后 DeleteFile 删源，
  未完成绝不删，删失败下轮重试，可清理源端空目录）
- Vue 联邦前端（v0.3.0）：get_render_mode 返回 ("vue", "dist/assets")，
  前端工程在仓库 frontend/（Config 任务编辑器、Page 任务总览、AppPage
  侧栏全页、Dashboard），npm run build 产物输出到 dist/assets；
  侧栏入口由 get_sidebar_nav 注册
- 异步复制校验（v0.2.0）：CopyFile 返回成功只是任务已提交，目标文件不会立即
  出现。完成判定改为看 GetCopyTasks 的 CopyTask 状态（Completed/Failed），
  提交后本轮短轮询（默认 30 秒），未完成的留到后续轮次自动结算，
  不误判失败、不重复提交；同步中超过默认 24 小时才判超时失败

记录清理规则（design-v0.1.md 第 6 点）：
- 同步状态是增量依据，源文件还在就不删；源端消失先标记 `source_gone`，
  默认宽限 30 天才删，防止按时间误删导致重复全量复制
- 任务历史：成功默认保留 30 天，失败默认保留 90 天

## 待办

- 在真实 MoviePilot V3 宿主里加载一次验证（导入路径、API 注册、服务清理）
- 确认 `clouddrive2-client` 在宿主环境的 pb2 模块路径，必要时改 `_PB2_CANDIDATES`
- CopyTask 给的是整个复制任务（源→目标目录）的字节进度，不是单文件进度；
  页面暂按文件粒度显示状态，不显示单文件百分比
- 注册远程命令 `/cd2sync`（PluginAction 事件）—— v0.2.1 已完成
- 需要实时面板时再把页面升级为 Vue 联邦组件（注意联邦 CSS 门禁）
- 插件图标 `CloudDrive2.png` 需放入插件仓库图标目录

## 本地测试

```bash
python3 -m pytest tests/
```

测试用假 CD2 客户端覆盖：首轮同步、增量跳过、失败重试与暂缓、
源端消失标记与清理。不依赖真实 CD2 / MoviePilot 宿主。
