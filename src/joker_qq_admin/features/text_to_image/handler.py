from __future__ import annotations

from ..context import MessageContext, parse_command


class TextToImageHandler:
    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, _, _ = parsed
        if name in {"文转图", "图转文"}:
            return "当前官方机器人实例未配置媒体上传服务，暂不能处理图片转换。"
        return None
