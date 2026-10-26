from __future__ import annotations

from ..context import MessageContext, parse_command


class ModerationHandler:
    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, _, _ = parsed
        if name in {"禁言", "解禁", "踢出", "撤回", "点赞", "赞我", "自动授予称号"}:
            return "当前官方 QQ 机器人接口未向此实例提供该群管操作，未执行。"
        return None
