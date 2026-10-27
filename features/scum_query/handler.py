from __future__ import annotations

from typing import Any

import aiohttp

from features.context import MessageContext, parse_scum_command


COUNTRY_CODES = {
    "CN": "中国",
    "CHINA": "中国",
    "US": "美国",
    "USA": "美国",
    "JP": "日本",
    "JAPAN": "日本",
    "KR": "韩国",
    "KOREA": "韩国",
    "HK": "香港",
    "TW": "台湾",
    "SG": "新加坡",
    "TH": "泰国",
    "RU": "俄罗斯",
    "GB": "英国",
    "UK": "英国",
    "DE": "德国",
    "GERMANY": "德国",
    "FR": "法国",
    "FRANCE": "法国",
    "CA": "加拿大",
    "EU": "欧洲",
    "EUROPE": "欧洲",
    "ID": "印度尼西亚",
    "INDONESIA": "印度尼西亚",
    "PH": "菲律宾",
    "PHILIPPINES": "菲律宾",
    "IN": "印度",
    "INDIA": "印度",
    "AU": "澳大利亚",
    "AUSTRALIA": "澳大利亚",
    "NZ": "新西兰",
    "NEW ZEALAND": "新西兰",
    "MY": "马来西亚",
    "MALAYSIA": "马来西亚",
    "VN": "越南",
    "VIETNAM": "越南",
    "THAILAND": "泰国",
    "RUSSIA": "俄罗斯",
    "UNITED STATES": "美国",
    "UNITED KINGDOM": "英国",
}


class ScumQueryHandler:
    def __init__(self, relay_url: str, relay_key: str, timeout: float = 60.0) -> None:
        self.relay_url = relay_url.rstrip("/")
        self.relay_key = relay_key.strip()
        self.timeout = timeout

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_scum_command(context.content)
        if parsed is None:
            return None
        name, arguments, argument_text = parsed
        if name in {"scum帮助", "scum帮助".casefold()}:
            return "绑定id 服务器ID\n解绑\n查询在线\n查询 关键词"
        if name in {"绑定id", "id绑定", "绑定"}:
            if not arguments or not arguments[0].isdigit():
                return "用法：绑定id 服务器ID"
            if not context.is_group:
                return "SCUM 服务器绑定只支持群聊"
            server_id = arguments[0]
            context.store.bind_server(context.scope_id, server_id)
            return f"成功绑定服务器ID：{server_id}\n群成员可直接使用 查询在线 查询状态。"
        if name == "解绑":
            if not context.is_group:
                return "SCUM 服务器绑定只支持群聊"
            return "已解绑服务器" if context.store.unbind_server(context.scope_id) else "当前没有绑定服务器"
        if name in {"查询在线", "在线查询"}:
            server_id = context.store.get_server(context.scope_id)
            if not server_id:
                return "本群还没有绑定服务器，请先使用 绑定id 服务器ID"
            return await self._detail(server_id)
        if name in {"查询", "查询1", "查询2", "id查询", "查服"}:
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
        keyword = keyword.strip()
        top_rank = not keyword
        params = {"q": "all" if top_rank else keyword[:120]}
        if top_rank:
            params["limit"] = "100"
        data = await self._request("/api/search", params)
        if data.get("error"):
            return str(data["error"])
        servers = data.get("servers")
        if not isinstance(servers, list) or not servers:
            return "没有找到可用的 SCUM 服务器"
        valid_servers = [server for server in servers if isinstance(server, dict)]
        if not valid_servers:
            return "没有找到可用的 SCUM 服务器"
        if top_rank:
            valid_servers.sort(key=self._rank_value)
            lines = ["SCUM 排名前 10 的服务器："]
        else:
            lines = [f"SCUM 查询“{keyword}”找到 {len(valid_servers)} 个结果："]
        for index, server in enumerate(valid_servers[:10], 1):
            lines.append(self._format_server(server, index=index))
        lines.extend(["-----------------------------------------------", "使用 绑定id 服务器ID 绑定后，可用 查询在线。"])
        return "\n".join(lines)

    @classmethod
    def _rank_value(cls, server: dict[str, Any]) -> int:
        raw_rank = cls._pick(server, "rank", "ranking", "position")
        value = str(raw_rank or "").strip().lstrip("#").replace(",", "")
        try:
            return int(value)
        except (TypeError, ValueError):
            return 10**9

    async def _detail(self, server_id: str) -> str:
        data = await self._request(f"/api/servers/{server_id}")
        if data.get("error"):
            return str(data["error"])
        server = data.get("server")
        if not isinstance(server, dict):
            return "SCUM 查询未返回服务器详情"
        return self._format_server(server, fallback_id=server_id, detail=True)

    @staticmethod
    def _clean_text(value: object, limit: int = 256) -> str:
        text = str(value if value is not None else "未知")
        text = "".join(" " if ord(char) < 32 or ord(char) == 127 else char for char in text)
        return text.strip()[:limit] or "未知"

    @staticmethod
    def _pick(mapping: object, *keys: str, default: object = None) -> object:
        if not isinstance(mapping, dict):
            return default
        for key in keys:
            value = mapping.get(key)
            if value is not None and value != "":
                return value
        return default

    @classmethod
    def _format_server(
        cls,
        server: dict[str, Any],
        *,
        index: int | None = None,
        fallback_id: str | None = None,
        detail: bool = False,
    ) -> str:
        server_id = cls._pick(server, "id", "serverId", "server_id", default=fallback_id or "未知")
        name = cls._pick(server, "name", "serverName", "server_name", default="未知")
        players = cls._pick(server, "players", "playerCount", "player_count")
        maximum = cls._pick(server, "maxPlayers", "max_players", "maxPlayerCount")
        ip = cls._pick(server, "ip", "host", "address")
        port = cls._pick(server, "port", "serverPort", "server_port")
        country = cls._pick(
            server,
            "region",
            "country",
            "countryCode",
            "country_code",
        )
        if isinstance(country, str):
            country = COUNTRY_CODES.get(country.upper(), country)

        raw_status = cls._pick(server, "status", "state")
        status = cls._clean_text(raw_status)
        normalized_status = str(raw_status or "").strip().lower()
        power_status = cls._pick(
            server,
            "power_status",
            "powerStatus",
            "isPoweredOn",
            "is_powered_on",
        )
        if power_status is None:
            if normalized_status in {"online", "on", "true", "1", "在线"}:
                running = "是"
            elif normalized_status in {"offline", "dead", "off", "false", "0", "离线"}:
                running = "否"
            else:
                running = "未知"
        else:
            normalized_power = str(power_status).strip().lower()
            if normalized_power in {"on", "online", "true", "1", "yes", "是"}:
                running = "是"
            elif normalized_power in {"off", "offline", "dead", "false", "0", "no", "否"}:
                running = "否"
            else:
                running = cls._clean_text(power_status, 32)

        address = "未知"
        if ip is not None:
            address = cls._clean_text(ip, 128)
            if port is not None:
                address = f"{address}:{cls._clean_text(port, 16)}"

        header = "服务器详细信息：" if detail else f"{index}. SCUM 服务器"
        lines = [
            f"{header}\n"
            f"ID: {cls._clean_text(server_id, 64)}\n"
            f"服务器名称: {cls._clean_text(name, 128)}\n"
            f"在线人数: {cls._clean_text(players, 32)}/{cls._clean_text(maximum, 32)}\n"
            f"IP地址: {address}\n"
            f"状态: {status}\n"
            f"地区: {cls._clean_text(country, 64)}\n"
            f"是否开机: {running}"
        ]

        rank = cls._pick(server, "rank", "ranking", "position")
        if rank is not None:
            rank_text = cls._clean_text(rank, 32)
            lines.append(f"排名: {rank_text if rank_text.startswith('#') else f'#{rank_text}'}")

        version = cls._pick(server, "version", "gameVersion", "game_version")
        if version is not None:
            lines.append(f"版本: {cls._clean_text(version, 64)}")

        game_time = cls._pick(
            server,
            "gameTime",
            "game_time",
            "serverTime",
            "server_time",
            "inGameTime",
            "in_game_time",
            "time",
            "updatedAt",
            "updated_at",
            "lastUpdated",
        )
        if game_time is not None:
            lines.append(f"游戏时间: {cls._clean_text(game_time, 64)}")
        return "\n".join(lines)
