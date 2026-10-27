# joker_qq_admin

独立的 QQ 官方机器人项目，运行在 Linux 云服务器 `/www/wwwroot/joker_qq_admin`，不修改现有 `astrbot_plugin_joker` 或 NapCat。

分群用户注册需要管理员先在控制台填写 SMTP 参数。用户填写注册卡、邮箱验证码和账号密码后才能完成注册；邮箱验证码 10 分钟有效。

管理员只需要创建“机器人授权卡”。客户用该卡完成邮箱验证注册后，先在目标群发送 `/绑定官方群 数字QQ群号`，再在用户中心输入相同的数字 QQ 群号即可绑定官方群；禁言、黑名单、专属回复和分管管理员均通过网页读取官方群成员后选择，不需要用户手动填写 OpenID。

## 当前范围

- 使用 QQ 开放平台 AppID、AppSecret 获取 Access Token。
- 支持官方 WebSocket Gateway 和 Webhook，接收群消息和 C2C 消息事件。
- 通过官方 HTTP API 发送群消息和 C2C 消息。
- 支持 `/ping`、`/官方机器人状态`、`/官方机器人帮助` 基础指令。
- 支持 SCUM 服务器绑定；`绑定id`、`解绑`、`查询在线`、`查询 关键词` 不需要斜杠即可使用，单独发送 `查询` 时返回按排名排序的前 10 个服务器。
- 支持签到、积分排行、自动回复、用户专属回复、抽奖、骰子、猜拳、随机选择和消息统计。
- 支持记录官方群 `group_openid` 与 Linux 网页数字群号的映射。
- 提供网页控制台，可查看 Gateway 状态、群组数据、功能目录，并按群修改功能开关、分群管理员、用户专属回复和定时消息。
- 每个功能放在 `features/` 下的独立目录，项目只有一个正式运行目录。
- 数据库只在 Linux 运行目录首次创建，不导入 Windows 端群组和运行数据。
- 支持官方群管理接口：禁言、解禁、踢出、拉黑、黑名单查询、成员查询和机器人消息撤回；已实现功能才会出现在功能目录和网页设置中。
- 支持官方群资料、机器人群内状态、入群申请审批和自动审批策略接口；这些接口受 QQ 开放平台账号权限限制，未开放时页面显示官方错误，不写入假数据。
- 当前不展示入群欢迎、音乐点歌、文转图等未接入官方事件或媒体服务的功能。

## 配置

首次部署时只需要在服务器环境文件中填写账号密钥。不要把真实 Token、AppSecret 或本地配置提交到 Git。

至少需要配置：

```text
QQBOT_APP_ID=你的AppID
QQBOT_APP_SECRET=你的AppSecret
QQBOT_API_BASE=https://api.bot.qq.com
QQBOT_OWNER_OPENID=你的用户openid
QQBOT_ADMIN_OPENIDS=其他管理员openid1,其他管理员openid2
JOKER_PORTAL_URL=https://web.yooyun.top
JOKER_ADMIN_USERNAME=admin
JOKER_ADMIN_PASSWORD=控制台管理员密码
JOKER_DASHBOARD_SESSION_MAX_AGE=604800
JOKER_BOT_AUTH_REQUIRED=1
```

群消息需要在 QQ 开放平台同时启用“接收所有消息”和 `GROUP_MESSAGE_CREATE` 事件。只勾选事件名称仍可能只收到 @ 消息。开启后群内指令不需要 @机器人；如果平台没有给账号开通全量消息权限，仍只能使用 @机器人触发。还需要加入服务器公网 IP 白名单，并将机器人发布到可测试的群。企业主体和个人主体可用场景、事件权限及消息限制以官方控制台为准。

群管命令示例：

```text
/禁言 @成员 600
/解禁 @成员
/踢出 @成员
/踢出 @成员 拉黑
/拉黑 成员openid
/删黑 成员openid
/查看黑名单
/群禁言状态
/群成员
/成员信息 @成员
/撤回 机器人消息ID
```

群管命令只允许 `QQBOT_OWNER_OPENID` 或 `QQBOT_ADMIN_OPENIDS` 中的用户执行。机器人本身还必须是群管理员；官方平台未开放的接口会返回不可用，不会写入假数据。

## 启动

在本项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python run.py
```

运行环境要求 Python 3.10 或更高版本。

## bbt.yooyun.top 控制台

官方机器人配置直接放在 `bbt.yooyun.top`，不依赖 `web.yooyun.top`。默认只监听服务器本机 `127.0.0.1:8080`。首次需要远程访问时，在服务器环境文件中增加：

```text
JOKER_DASHBOARD_BIND=0.0.0.0
JOKER_DASHBOARD_PORT=8080
JOKER_DASHBOARD_TOKEN=请设置一个独立的访问令牌
JOKER_ADMIN_USERNAME=admin
JOKER_ADMIN_PASSWORD=请设置管理员密码
JOKER_BOT_AUTH_REQUIRED=1
JOKER_DASHBOARD_PATH=/admin
JOKER_ADMIN_PATH=/admin
JOKER_USER_PATH=/user
JOKER_REGISTRATION_REQUIRE_EMAIL=1
```

重启服务后访问 `https://bbt.yooyun.top` 首页。管理员入口默认是 `https://bbt.yooyun.top/admin`，分群用户入口默认是 `https://bbt.yooyun.top/user`。管理员只生成“机器人授权卡”；后台可查看注册用户、用户绑定的群、编辑账号资料、停用账号、删除卡密和重置分群用户密码。

分群用户先完成邮箱验证注册并登录，再在“账号资料”兑换机器人授权卡；然后填写已由机器人记录的数字 QQ 群号绑定官方群。绑定成功后，用户只会看到自己已绑定的群，并可以配置当前选择群的基础设置、自动回复、用户专属回复、手动群管、分群管理员、黑名单、入群审核、定时任务、关键词规则和消息记录。一个官方群只允许绑定一个分群账号。

管理员和分群用户使用不同的控制台。管理员可以在“机器人与接口”“邮箱与注册”中修改全局接口、后台路径、注册邮箱要求和 SMTP 参数；分群用户注册时可填写邮箱，之后可以使用账号或邮箱登录，并只能管理自己绑定授权卡的群。邮箱字段用于登录和账号资料管理，未配置 SMTP 时不会强制发送验证码。

管理员路径可以设置为例如 `/joker-admin`，用户路径可以设置为例如 `/group-user`，修改后服务重启生效。根地址始终是首页，两个入口必须使用不同的非根路径。Nginx 需要将该域名的请求继续转发到项目监听端口。

QQ 用户授权流程：管理员生成 QQ 用户授权卡，用户在群内使用 `/获取OpenID` 查看自己的 OpenID，再使用 `/授权 卡密` 完成授权。授权卡可以限制为某个群，也可以对全部群生效。关闭机器人后，普通指令不会执行，管理员仍可从控制台重新开启。

机器人主人在管理员后台“官方机器人接口”页面设置，填写主人自己的用户 OpenID（先私聊机器人发送 `/获取OpenID`）。主人可跳过机器人授权与分群功能开关，并可使用 `/查看授权`、`/生成授权卡 [天数] [次数]`、`/删除授权卡 卡密` 管理 QQ 用户授权卡。删除授权卡会立即撤销使用该卡的网页与机器人授权。

保留访问令牌是为了服务器维护和旧部署兼容；日常使用优先使用管理员登录。不要把管理员密码、访问令牌或 AppSecret 提交到 Git。

网页版操作台地址配置为 `JOKER_PORTAL_URL=https://web.yooyun.top` 后，官方机器人控制台设置页会显示入口。两个项目仍使用各自数据库；官方群的 `group_openid` 与网页使用的数字群号需要在“绑定官方群”中映射，不能直接把两套数据目录混用。

## 官方文档

- https://github.com/tencent-connect/bot-docs
- https://q.qq.com/#/

功能迁移清单见 `features/README.md`。

本项目使用 QQ 官方机器人 Gateway 和 HTTP API，不使用 NapCat、OneBot 或 AstrBot 插件运行入口。

QQ 开放平台选择 Webhook 时，回调地址填写部署域名根地址，例如 `https://bbt.yooyun.top`。项目会自动处理回调签名校验、地址验证、事件确认和消息分发；网页控制台仍通过浏览器访问同一个地址。

