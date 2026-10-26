from __future__ import annotations

from ..context import MessageContext, parse_command


class WelcomeHandler:
    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, _, _ = parsed
        if name in {"开启欢迎", "关闭欢迎", "设置欢迎", "欢迎设置", "入群欢迎"}:
            return "当前官方 QQ 机器人实例未收到可用的入群事件，欢迎语未执行。"
        return None
