from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any

import aiohttp

from config import QQBotConfig


class QQBotAPIError(RuntimeError):
    """Raised when the official QQ bot API rejects a request."""


@dataclass(slots=True)
class AccessToken:
    value: str
    expires_at: float


class QQBotAPI:
    def __init__(self, config: QQBotConfig) -> None:
        self.config = config
        self._token: AccessToken | None = None
        self._token_lock = asyncio.Lock()

    async def close(self) -> None:
        return None

    async def access_token(self) -> str:
        now = time.time()
        if self._token and self._token.expires_at - now > 60:
            return self._token.value

        async with self._token_lock:
            now = time.time()
            if self._token and self._token.expires_at - now > 60:
                return self._token.value
            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
            payload = {"appId": self.config.app_id, "clientSecret": self.config.app_secret}
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(self.config.token_url, json=payload) as response:
                    data = await self._read_response(response)
            token = str(data.get("access_token", "") or "").strip()
            if not token:
                raise QQBotAPIError("official QQ bot token response has no access_token")
            expires_in = max(120, int(data.get("expires_in", 7200) or 7200))
            self._token = AccessToken(token, time.time() + expires_in)
            return token

    async def gateway_url(self) -> str:
        if self.config.gateway_url:
            return self.config.gateway_url
        data = await self.request("GET", "/gateway")
        url = str(data.get("url", "") or "").strip()
        if not url:
            raise QQBotAPIError("official QQ bot gateway response has no url")
        return url

    async def send_group_message(
        self,
        group_openid: str,
        content: str,
        *,
        msg_id: str | None = None,
        msg_seq: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": content, "msg_type": 0}
        if msg_id:
            payload["msg_id"] = msg_id
        if msg_seq is not None:
            payload["msg_seq"] = msg_seq
        return await self.request("POST", f"/v2/groups/{group_openid}/messages", json=payload)

    async def send_c2c_message(
        self,
        user_openid: str,
        content: str,
        *,
        msg_id: str | None = None,
        msg_seq: int | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"content": content, "msg_type": 0}
        if msg_id:
            payload["msg_id"] = msg_id
        if msg_seq is not None:
            payload["msg_seq"] = msg_seq
        return await self.request("POST", f"/v2/users/{user_openid}/messages", json=payload)

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self.access_token()
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        headers = {"Authorization": f"QQBot {token}"}
        url = f"{self.config.api_base_url}{path}"
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.request(method, url, headers=headers, json=json) as response:
                return await self._read_response(response)

    @staticmethod
    async def _read_response(response: aiohttp.ClientResponse) -> dict[str, Any]:
        raw = await response.text()
        try:
            data = await response.json(content_type=None)
        except (TypeError, ValueError):
            data = {"raw": raw}
        if response.status >= 400:
            detail = data.get("message") or data.get("raw") or response.reason
            raise QQBotAPIError(f"HTTP {response.status}: {detail}")
        if not isinstance(data, dict):
            raise QQBotAPIError("official QQ bot API returned a non-object response")
        return data

