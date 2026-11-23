# MoviePilot 插件仓库（个人）

MoviePilot V3 个人插件仓库，包含两个插件：

| 插件 | ID | 版本 | 说明 |
|---|---|---|---|
| CloudDrive2 网盘增量同步 | `CloudDrive2Sync` | 0.7.1 | 多任务 CloudDrive2 A盘→B盘增量同步，基于 CD2 gRPC API，Vue 前端 |
| 磁盘清理（目录限额版） | `DiskCleanerDirLimit` | 3.1.1 | 基于逗猫 DiskCleaner v3.0.1 修改，新增按下载目录大小上限精确清理 |

## 使用方法

在 MoviePilot 中添加本仓库地址到插件仓库设置，刷新后即可在插件市场中看到并安装这两个插件。

## 磁盘清理（目录限额版）说明

- 与市场版 `DiskCleaner` 是不同 ID，可共存安装，但**不要同时启用**两个清理插件，避免重复删种。
- 配置不继承市场版（配置前缀 `diskcleanerdirlimit_`），需重新配置。
- 目录上限模式：触发流程选「2. 下载器优先」，打开下载目录告警，方式选「按下载目录大小上限」，阈值如 `100G`。
  插件汇总全部本地下载目录的实际大小，超限后按**下载完成时间从早到晚**、直接经下载器删种删文件，
  每删一个重新统计，回到上限以内立即停止。详细说明见 `plugins.v3/diskcleanerdirlimit/DIRSIZE.md`。
- 上游原版：https://github.com/baozaodetudou/MoviePilot-Plugins （DiskCleaner by 逗猫），本版仅作个人使用修改。
