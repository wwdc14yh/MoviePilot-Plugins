# MoviePilot 插件仓库（个人）

MoviePilot V3 个人插件仓库，包含三个插件：

| 插件 | ID | 版本 | 说明 |
|---|---|---|---|
| CloudDrive2 网盘增量同步 | `CloudDrive2Sync` | 0.7.2 | 多任务 CloudDrive2 A盘→B盘增量同步，基于 CD2 gRPC API，Vue 前端 |
| 磁盘清理（目录限额版） | `DiskCleanerDirLimit` | 3.1.1 | 基于逗猫 DiskCleaner v3.0.1 修改，新增按下载目录大小上限精确清理 |
| 115 剧集分享管家 | `P115-ShareManager` | 0.1.10 | 监听 115 剧目录，TMDB 判完结后自动分享到 TG 频道 |

## 使用方法

在 MoviePilot 中添加本仓库地址到插件仓库设置，刷新后即可在插件市场中看到并安装这三个插件。

## 115 剧集分享管家说明

- 多任务监听 115 剧目录，按 TMDB 判断按季/整剧完结（完结后默认延迟 48 小时分享，防洗板）。
- 完结后复制到 115 临时路径、按 TMDB 英文名重命名，创建长期分享（固定提取码 `wwdc`），`share_snap` 回读校验后推送到 TG 频道。
- 分享后按配置删除或保留源文件（全局开关 + 每任务覆盖）；临时目录分享后删除。
- 115 登录支持多平台扫码（web / iOS / Android / iPad / TV / 微信小程序）或手动粘贴 Cookie；批量分享有间隔配置（默认 60 秒），防连续请求触发风控。详细说明见 `plugins.v3/p115sharemanager/README.md`。

## 磁盘清理（目录限额版）说明

- 与市场版 `DiskCleaner` 是不同 ID，可共存安装，但**不要同时启用**两个清理插件，避免重复删种。
- 配置不继承市场版（配置前缀 `diskcleanerdirlimit_`），需重新配置。
- 目录上限模式：触发流程选「2. 下载器优先」，打开下载目录告警，方式选「按下载目录大小上限」，阈值如 `100G`。
  插件汇总全部本地下载目录的实际大小，超限后按**下载完成时间从早到晚**、直接经下载器删种删文件，
  每删一个重新统计，回到上限以内立即停止。详细说明见 `plugins.v3/diskcleanerdirlimit/DIRSIZE.md`。
- 上游原版：https://github.com/baozaodetudou/MoviePilot-Plugins （DiskCleaner by 逗猫），本版仅作个人使用修改。
