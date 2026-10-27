from __future__ import annotations

from urllib.parse import quote

from features.context import MessageContext, parse_command


class SongRequestHandler:
    """Provide a legal search link instead of an unreliable music-card payload."""

    feature_key = "song_request"

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, _, argument_text = parsed
        if name not in {"点歌", "搜歌"}:
            return None
        keyword = argument_text.strip()
        if not keyword:
            return "用法：/点歌 歌曲名"
        return f"🎵 点歌：{keyword}\nhttps://music.163.com/#/search/m/?s={quote(keyword)}&type=1"
