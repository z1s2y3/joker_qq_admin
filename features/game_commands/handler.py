from __future__ import annotations

import aiohttp

from features.context import MessageContext, parse_command


class GameCommandHandler:
    def __init__(self, bridge_url: str, bridge_token: str, timeout: float = 30.0) -> None:
        self.bridge_url = bridge_url.rstrip("/")
        self.bridge_token = bridge_token.strip()
        self.timeout = timeout

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, _, argument_text = parsed
        if name in {"游戏帮助", "游戏指令"}:
            return "/游戏帮助\n/游戏 指令内容"
        if name != "游戏":
            return None
        if not argument_text:
            return "用法：/游戏 指令内容"
        if not self.bridge_url:
            return "游戏执行桥接服务未配置。"
        headers = {"Content-Type": "application/json"}
        if self.bridge_token:
            headers["Authorization"] = f"Bearer {self.bridge_token}"
        payload = {
            "scope_id": context.scope_id,
            "user_id": context.user_id,
            "command": argument_text,
        }
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(f"{self.bridge_url}/command", json=payload, headers=headers) as response:
                    data = await response.json(content_type=None)
                    if response.status >= 400:
                        return str(data.get("detail") or data.get("error") or f"游戏执行失败 HTTP {response.status}")
                    return str(data.get("message") or data.get("result") or "游戏指令已提交")
        except (aiohttp.ClientError, TimeoutError):
            return "游戏执行桥接服务暂时不可用。"
