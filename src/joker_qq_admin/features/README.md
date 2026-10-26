# 功能目录

每个功能使用独立目录，功能之间只通过官方消息接口、身份映射和统一配置交互。

| 目录 | 当前状态 | 说明 |
| --- | --- | --- |
| `basic_commands` | 已实现 | 基础指令、状态和功能菜单。 |
| `identity` | 已实现 | 显示官方 openid，并可将 `group_openid` 映射到 Linux 网页使用的数字群号。 |
| `scum_query` | 已实现 | `/绑定id`、`/查询在线`、`/查询2 关键词`，调用 Linux SCUM 中转。 |
| `statistics` | 已实现 | 签到、积分、排行和群统计，数据保存在 Linux SQLite。 |
| `auto_reply` | 已实现 | 添加、删除、查看和开关文字回复。 |
| `lottery` | 已实现 | 发起、报名、开奖和状态查询。 |
| `entertainment` | 已实现 | 骰子、猜拳、随机选择和时间。 |
| `music` | 受限 | 保留指令入口，媒体服务未配置时提示未执行。 |
| `text_to_image` | 受限 | 保留指令入口，需配置媒体上传服务。 |
| `game_commands` | 受限 | 可通过 `JOKER_GAME_BRIDGE_URL` 对接 Linux 游戏执行桥。 |
| `blacklist` | 已实现 | 黑名单记录维护；自动踢出仍需官方群管权限。 |
| `moderation` | 暂不执行 | 禁言、踢出、撤回、称号和点赞未配置可确认的官方接口。 |
| `welcome` | 暂不可保证 | 不作为官方机器人第一阶段功能。 |
| `scheduled_messages` | 不启用 | 官方机器人不能按 NapCat 方式无事件定时主动发送。 |

所有可写数据都在 Linux 的 `JOKER_QQ_DATA_DIR` 下创建。部署脚本只复制程序，不复制 Windows 数据；Linux 网页或其他管理端若要修改这些数据，应使用同一数据目录或后续接入统一数据 API。当前项目不会自动读取 Windows 端 `sql/`、`data/` 或插件配置；官方群的 openid 与网页数字群号需要先手动映射。

