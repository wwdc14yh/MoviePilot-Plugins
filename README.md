# Rclone WebDAV 增量备份（MoviePilot V3）

## 功能
- Alist WebDAV Remote → CloudDrive2 WebDAV Remote。
- 通过 `http://<rclone-host>:5572/core/command` 调用 `rclone lsjson` 和逐文件 `rclone copy`。
- SQLite 文件身份：源相对路径 + 文件大小。
- 仅当目标 stat 存在且大小一致时登记 `success`。
- 成功记录永久跳过，不检查目标是否仍存在；目标被删除不会触发重复上传。
- 文件大小变化会形成新的身份记录；同路径同大小内容变化按需求跳过。
- 可配置并发数（1～16）、Cron、RC 地址和认证。
- 任务状态 API：pending/running/success/failed；失败任务下次自动重试。

## 安装
将 `plugins.v3/rclonewebdavbackup/` 放入 MoviePilot 插件仓库的同名目录，并将 `RcloneWebdavBackup` 条目合并到 `package.v3.json`。在 V3 宿主安装/更新插件。

## Rclone RC 要求
rclone 必须启用 RC，且允许 `core/command`：
```bash
rclone rcd --rc --rc-addr 0.0.0.0:5572 --rc-user YOUR_USER --rc-pass 'YOUR_PASSWORD'
```
如果使用现有 rclone serve 进程，则启动参数至少包含 `--rc --rc-addr 0.0.0.0:5572`，并按需设置 `--rc-user/--rc-pass`。
**安全警告：** `core/command` 等同于在 rclone 进程权限下执行命令。不要将 5572 暴露到公网；建议仅绑定可信局域网、设置强密码并配置防火墙。

## Remote 和路径
Remote 名称必须已存在于 rclone 配置中，例如 `Alist:`、`CloudDrive2:`。
源目录和目标目录填写各自 Remote 内的相对路径，不要重复填写 Remote 名称。
示例：
- 源 Remote：`Alist`；源路径：`订阅/影视`
- 目标 Remote：`CloudDrive2`；目标路径：`备份/影视`

## API
基础路径：`/api/v1/plugin/RcloneWebdavBackup`
- `GET /status`：总状态和各状态数量
- `GET /tasks?page=1&page_size=100&status=failed`：任务列表
- `POST /run`：立即执行
- `POST /test`：测试 RC 连通性

插件配置页提供连接参数、Remote、路径、并发、Cron 和立即执行开关。任务列表可由详情页/自定义前端通过 `/tasks` 接口分页读取；当前版本详情页先提供状态摘要和 API 入口提示。

## 身份与边界说明
- SQLite 中 `UNIQUE(plugin_id, rel_path, size)` 是唯一键。
- 扫描仅插入未登记身份；已有 success 不会因目标缺失而重新上传。
- 同一路径不同大小会插入新版本任务。
- 相同路径和大小但内容不同无法识别，符合指定身份规则。
- 如果源文件在扫描后被修改，目标大小校验仍以扫描时记录的大小为准；失败会在下次扫描时按新大小创建任务。
- 本版本按文件调用 RC `core/command`，每个文件独立 copy；并发数控制同时执行的文件任务数。
- `verify_after_copy` 开关仅保留配置兼容，成功条件始终强制校验存在及大小，避免误记 success。
