# joker_qq_admin

独立的 QQ 官方机器人项目，运行在 Linux 云服务器 `/www/wwwroot/joker_qq_admin`，不修改现有 `astrbot_plugin_joker` 或 NapCat。

## 当前范围

- 使用 QQ 开放平台 AppID、AppSecret 获取 Access Token。
- 连接官方 WebSocket Gateway，接收群消息和 C2C 消息事件。
- 通过官方 HTTP API 发送群消息和 C2C 消息。
- 支持 `/ping`、`/官方机器人状态`、`/官方机器人帮助` 基础指令。
- 支持 SCUM 服务器绑定、在线查询和 `/查询2 关键词` 搜索。
- 支持签到、积分排行、自动回复、抽奖、骰子、猜拳、随机选择和消息统计。
- 支持记录官方群 `group_openid` 与 Linux 网页数字群号的映射。
- 提供网页控制台，可查看 Gateway 状态、群组数据、功能目录并维护自动回复。
- 每个功能放在 `features/` 下的独立目录，项目只有一个正式运行目录。
- 数据库只在 Linux 运行目录首次创建，不导入 Windows 端群组和运行数据。
- 音乐媒体、图片转换、禁言、踢出、撤回、称号和点赞不会伪装成功；没有对应官方能力时会明确提示未执行。

## 配置

首次部署时只需要在服务器环境文件中填写账号密钥。不要把真实 Token、AppSecret 或本地配置提交到 Git。

至少需要配置：

```text
QQBOT_APP_ID=你的AppID
QQBOT_APP_SECRET=你的AppSecret
```

群消息需要在 QQ 开放平台启用对应事件权限、加入服务器公网 IP 白名单，并将机器人发布到可测试的群。企业主体和个人主体可用场景、事件权限及消息限制以官方控制台为准。

## 启动

在本项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python run.py
```

运行环境要求 Python 3.10 或更高版本。

## 网页控制台

默认只监听服务器本机 `127.0.0.1:8080`。首次需要远程访问时，在服务器环境文件中增加：

```text
JOKER_DASHBOARD_BIND=0.0.0.0
JOKER_DASHBOARD_PORT=8080
JOKER_DASHBOARD_TOKEN=请设置一个独立的访问令牌
```

重启服务后访问 `http://服务器IP:8080/?token=访问令牌`。进入“设置”页面后，AppID、AppSecret、SCUM 配置、监听地址、端口和访问令牌都可以在网页中修改；保存后机器人会自动重载，不需要再手动编辑配置文件。不要把访问令牌提交到 Git。

## 官方文档

- https://github.com/tencent-connect/bot-docs
- https://q.qq.com/#/

功能迁移清单见 `features/README.md`。

本项目使用 QQ 官方机器人 Gateway 和 HTTP API，不使用 NapCat、OneBot 或 AstrBot 插件运行入口。

