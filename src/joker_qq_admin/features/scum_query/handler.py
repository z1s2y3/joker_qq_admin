from __future__ import annotations

import aiohttp

from ..context import MessageContext, command_is, parse_command


class ScumQueryHandler:
    def __init__(self, relay_url: str, relay_key: str, timeout: float = 60.0) -> None:
        self.relay_url = relay_url.rstrip("/")
        self.relay_key = relay_key.strip()
        self.timeout = timeout

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, arguments, argument_text = parsed
        if name in {"scum帮助", "scum帮助".casefold()}:
            return "/绑定id 服务器ID\n/解绑\n/查询在线\n/查询2 关键词"
        if name in {"绑定id", "id绑定", "绑定"}:
            if not arguments or not arguments[0].isdigit():
                return "用法：/绑定id 服务器ID"
            if not context.is_group:
                return "SCUM 服务器绑定只支持群聊"
            server_id = arguments[0]
            context.store.bind_server(context.scope_id, server_id)
            return f"成功绑定服务器ID：{server_id}\n群成员可使用 /查询在线 查询状态。"
        if name == "解绑":
            if not context.is_group:
                return "SCUM 服务器绑定只支持群聊"
            return "已解绑服务器" if context.store.unbind_server(context.scope_id) else "当前没有绑定服务器"
        if name in {"查询在线", "在线查询"}:
            server_id = context.store.get_server(context.scope_id)
            if not server_id:
                return "本群还没有绑定服务器，请先使用 /绑定id 服务器ID"
            return await self._detail(server_id)
        if name in {"查询", "查询1", "查询2", "id查询", "查服"}:
            if not argument_text:
                return "用法：/查询2 关键词"
            return await self._search(argument_text)
        return None

    async def _request(self, path: str, params: dict[str, str] | None = None) -> dict:
        if not self.relay_url:
            return {"error": "未配置 SCUM_RELAY_URL"}
        headers = {"Accept": "application/json"}
        if self.relay_key:
            headers["Authorization"] = f"Bearer {self.relay_key}"
        timeout = aiohttp.ClientTimeout(total=self.timeout)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.relay_url}{path}", params=params, headers=headers) as response:
                    data = await response.json(content_type=None)
                    if response.status >= 400:
                        return {"error": str(data.get("error") or data.get("detail") or f"HTTP {response.status}")}
                    return data if isinstance(data, dict) else {"error": "中转返回格式无效"}
        except (aiohttp.ClientError, TimeoutError) as exc:
            return {"error": f"SCUM 查询失败：{type(exc).__name__}"}

    async def _search(self, keyword: str) -> str:
        data = await self._request("/api/search", {"q": keyword[:120]})
        if data.get("error"):
            return str(data["error"])
        servers = data.get("servers")
        if not isinstance(servers, list) or not servers:
            return "没有找到匹配的服务器"
        lines = [f"SCUM 查询“{keyword}”找到 {len(servers)} 个结果："]
        for index, server in enumerate(servers[:10], 1):
            if not isinstance(server, dict):
                continue
            lines.append(
                f"{index}. {server.get('id', '-')} | {server.get('name', '未命名')} | "
                f"{server.get('players', 0)}/{server.get('maxPlayers', 0)} | "
                f"{server.get('ip', '-') }:{server.get('port', '-')}"
            )
        lines.append("使用 /绑定id 服务器ID 绑定后，可用 /查询在线。")
        return "\n".join(lines)

    async def _detail(self, server_id: str) -> str:
        data = await self._request(f"/api/servers/{server_id}")
        if data.get("error"):
            return str(data["error"])
        server = data.get("server")
        if not isinstance(server, dict):
            return "SCUM 查询未返回服务器详情"
        status = str(server.get("status") or "unknown")
        status_text = {"online": "online", "offline": "offline", "dead": "dead"}.get(status, status)
        return (
            f"服务器详细信息：\nID: {server.get('id', server_id)}\n"
            f"服务器名称: {server.get('name', '未命名')}\n"
            f"在线人数: {server.get('players', 0)}/{server.get('maxPlayers', 0)}\n"
            f"IP地址: {server.get('ip', '-')}:{server.get('port', '-')}\n"
            f"状态: {status_text}"
        )
