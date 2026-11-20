# CloudDrive2Sync 设计修订 v0.1
# 插件 ID: CloudDrive2Sync, 目录: plugins.v3/clouddrive2sync/, 主类在 __init__.py
# package.v3.json 版本必须与 plugin_version 一致

## 结论先行 - 第 6 点: 记录清理不能按时间一刀切
sync_record 同时承担两个职责, 必须拆开:
1. sync_state (增量依据): 只要源文件还在, 就不能删。
   按时间删 (如 30 天) 会导致下一轮查不到记录, 把已同步文件当新文件重复复制。
   清理规则: 每轮对账时, 源端已消失的记录标记 source_gone,
   保留 30 天宽限 (防改名/移动/CD2 缓存抖动误判), 到期才删。
2. sync_task (前端面板历史, 截图那样的列表): 可以按时间清。
   默认: 成功保留 30 天, 失败保留 90 天 (要留时间排查/重试)。
   清理任务每天跑一次 (跟随同步轮询, 24h 节流), 清完执行 VACUUM。

可配置项 (默认值):
- history_retention_days = 30
- failed_retention_days = 90
- state_tombstone_days = 30

记录量估算: 每条约 200-500 字节, 1 万文件约几 MB, 清理主要是为了
面板可读性和查询速度, 不是数据库大小本身。

## 表结构要点
唯一键不要只用路径, 用 source_file_id + size (+ hash)。
字段: source_path, source_file_id, size, check_value (优先 CD2 服务端哈希, size 兜底),
target_path, status (pending/syncing/done/failed/source_gone),
retry_count, first_seen_at, last_seen_at, finished_at, last_error

## 按 MoviePilot V3 规范修正的三处
1. 调度: 不要自建 apscheduler。周期任务用 get_service() 注册,
   立即执行一次用宿主 add_plugin_once_job(), stop_service() 释放。
2. 数据库: 不要把 sqlite 文件写进插件源码目录 (更新会被替换)。
   优先用插件自有表 (app.db Base + db_query/db_update, 表名带插件前缀,
   按 plugin_id 过滤); 坚持独立 sqlite 时, 文件必须放在 get_data_path() 下。
   Hu 的 MoviePilot 用的是 PostgreSQL, 自有表方案会自动适配, 独立 sqlite 也能跑但要自己处理锁。
3. 前端: 第一版建议先用 Vuetify JSON 的 get_page() 做任务列表,
   不上 Vue 联邦, 省掉构建和 CSS 污染门禁; 需要实时进度条再升级 Vue。

## 待核实 (写代码前必须确认)
- CD2 proto 里跨盘复制到底是哪个 RPC: 速查表里有 GetSubFiles (流式,
  ListSubFileRequest: path/forceRefresh) 和 MoveFile (theFilePaths/destPath/
  conflictPolicy/moveAcrossClouds), 没有明确的 CopyFile。
  要对着 clouddrive.proto 全量方法清单确认复制接口和它的冲突策略。
- CD2 复制是同步返回还是异步任务: 决定面板进度能不能显示真实百分比。
  如果接口不给进度, 状态只能显示 同步中 (不带百分比), 不能假造进度。
  截图里的 27%/23% 那种进度, 要有任务 API 支撑才做得出。
- 校验: 优先用 CD2 返回的服务端哈希查重, size 相同不等于文件相同,
  size 只能兜底。

## 同步流程 (修订版)
轮询触发 -> 拿运行锁, 已在运行则跳过本轮
-> GetSubFiles(forceRefresh=False) 递归拉源目录
-> 对每个文件: 按 file_id+size+hash 查 sync_state
   命中且 target 端复查存在且 check 通过 -> 跳过, 更新 last_seen_at
   未命中/校验失败 -> 调用 CD2 复制到目标目录 (先建目标子目录)
   -> 复查目标文件 size/hash -> 写 state=done, task=成功
   失败 -> task=失败, retry_count+1, 下一轮重试 (建议上限 5 次后降频)
-> 对账清理: 本轮没见到的 state 标记 source_gone (不立即删)
-> 节流清理历史 + tombstone 到期记录
