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
                "/我的ID\n"
                "/签到、/排行榜、/群统计\n"
                "/绑定id、/查询在线、/查询2 关键词\n"
                "/添加回复、/查看回复\n"
                "/骰子、/猜拳、/随机\n"
                "/发起抽奖、/参与抽奖、/开奖"
            )
        return None

