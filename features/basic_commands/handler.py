from __future__ import annotations

from features.context import MessageContext, command_is


class BasicCommandHandler:
    async def handle(self, context: MessageContext) -> str | None:
        if command_is(context.content, "/ping") is not None:
            return "pong"
        if command_is(context.content, "/官方机器人状态", "/qq机器人状态") is not None:
            return "官方 QQ 机器人已连接"
        if command_is(context.content, "/官方机器人帮助", "/qq机器人帮助", "/功能") is not None:
            return (
                "/ping\n"
                "/官方机器人状态\n"
                "/获取OpenID（查看自己的用户 OpenID）\n"
                "/签到、/排行榜、/群统计\n"
                "绑定id、解绑、查询（排名前10）、查询在线、查询 关键词\n"
                "/添加回复、/查看回复、/添加专属回复\n"
                "/骰子、/猜拳、/随机\n"
                "/发起抽奖、/参与抽奖、/开奖\n"
                "/禁言 @成员 秒数、/解禁 @成员\n"
                "/踢出 @成员、/踢出 @成员 拉黑\n"
                "/拉黑 成员openid、/删黑 成员openid、/查看黑名单\n"
                "/全体禁言 秒数、/全体解禁、/群禁言状态、/全体禁言状态、/群成员、/成员信息 @成员\n"
                "/群信息、/机器人群状态\n"
                "/入群申请、/同意入群 成员OpenID 申请ID、/拒绝入群 成员OpenID 申请ID 理由\n"
                "/撤回 机器人消息ID、/撤回用户 @成员 [条数]\n"
                "/分管管理员、/添加分管 @成员、/删除分管 @成员\n"
                "/添加定时消息 分钟 消息内容、/定时消息列表、/删除定时消息 编号"
            )
        return None

