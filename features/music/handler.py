from __future__ import annotations

from features.context import MessageContext, parse_command


class MusicHandler:
    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, _, _ = parsed
        if name in {"点歌", "选歌", "音乐"}:
            return "音乐搜索尚未配置官方媒体服务；当前官方机器人只启用文本功能。"
        return None
