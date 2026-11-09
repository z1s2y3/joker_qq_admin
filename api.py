from __future__ import annotations

import asyncio
from dataclasses import dataclass
import time
from typing import Any
from urllib.parse import quote

import aiohttp

from config import QQBotConfig


class QQBotAPIError(RuntimeError):
    """Raised when the official QQ bot API rejects a request."""

    def __init__(
        self,
        message: str,
        *,
        status: int | None = None,
        code: str = "",
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.retry_after = retry_after


@dataclass(slots=True)
class AccessToken:
    value: str
    expires_at: float


class QQBotAPI:
    _RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}
    _MAX_READ_ATTEMPTS = 3

    def __init__(self, config: QQBotConfig) -> None:
        self.config = config
        self._token: AccessToken | None = None
        self._token_lock = asyncio.Lock()
        self._session: aiohttp.ClientSession | None = None
        self._session_lock = asyncio.Lock()

    async def close(self) -> None:
        session = self._session
        self._session = None
        if session is not None and not session.closed:
            await session.close()

    async def _get_session(self) -> aiohttp.ClientSession:
        session = self._session
        if session is not None and not session.closed:
            return session
        async with self._session_lock:
            session = self._session
            if session is not None and not session.closed:
                return session
            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
            connector = aiohttp.TCPConnector(
                limit=32,
                limit_per_host=16,
                ttl_dns_cache=300,
                enable_cleanup_closed=True,
            )
            self._session = aiohttp.ClientSession(timeout=timeout, connector=connector)
            return self._session

    async def access_token(self) -> str:
        now = time.time()
        if self._token and self._token.expires_at - now > 60:
            return self._token.value

        async with self._token_lock:
            now = time.time()
            if self._token and self._token.expires_at - now > 60:
                return self._token.value
            payload = {"appId": self.config.app_id, "clientSecret": self.config.app_secret}
            session = await self._get_session()
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
        return await self.request("POST", f"/v2/groups/{quote(group_openid, safe='')}/messages", json=payload)

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
        return await self.request("POST", f"/v2/users/{quote(user_openid, safe='')}/messages", json=payload)

    async def set_group_member_mute(
        self,
        group_openid: str,
        member_openid: str,
        *,
        operation: str,
        mute_expire_at: str = "",
    ) -> dict[str, Any]:
        return await self.set_group_members_mute(
            group_openid,
            [member_openid],
            operation=operation,
            mute_expire_at=mute_expire_at,
        )

    async def set_group_members_mute(
        self,
        group_openid: str,
        member_openids: list[str],
        *,
        operation: str,
        mute_expire_at: str = "",
    ) -> dict[str, Any]:
        members: list[dict[str, Any]] = []
        for member_openid in member_openids[:20]:
            member: dict[str, Any] = {
                "op": operation,
                "member_openid": member_openid,
            }
            if mute_expire_at:
                member["mute_expire_at"] = mute_expire_at
            members.append(member)
        if not members:
            return {}
        path = f"/v2/groups/{quote(group_openid, safe='')}/restrict_chat_setting"
        try:
            return await self.request("POST", path, json={"members": members})
        except QQBotAPIError as bulk_error:
            if len(members) <= 1:
                raise
            semaphore = asyncio.Semaphore(4)

            async def apply_single(member: dict[str, Any]) -> tuple[str, bool]:
                member_openid = str(member["member_openid"])
                async with semaphore:
                    try:
                        await self.request("POST", path, json={"members": [member]})
                    except QQBotAPIError:
                        return member_openid, False
                    return member_openid, True

            results = await asyncio.gather(*(apply_single(member) for member in members))
            success_openids = [member_openid for member_openid, ok in results if ok]
            failed_openids = [member_openid for member_openid, ok in results if not ok]
            if not success_openids:
                raise bulk_error
            return {
                "success_openids": success_openids,
                "fail_openids": failed_openids,
                "fallback": "single_member",
            }

    async def get_group_mute_state(self, group_openid: str) -> dict[str, Any]:
        return await self.request(
            "GET",
            f"/v2/groups/{quote(group_openid, safe='')}/restrict_chat_setting",
        )

    async def get_group_info(self, group_openid: str) -> dict[str, Any]:
        return await self.request("GET", f"/v2/groups/{quote(group_openid, safe='')}/info")

    async def get_group_bot_state(self, group_openid: str) -> dict[str, Any]:
        return await self.request("GET", f"/v2/groups/{quote(group_openid, safe='')}/bot_state")

    async def list_join_requests(
        self, group_openid: str, *, cursor: str = "", limit: int = 50
    ) -> dict[str, Any]:
        params = {"limit": str(max(1, min(int(limit), 50)))}
        if cursor:
            params["cursor"] = cursor
        return await self.request(
            "GET",
            f"/v2/groups/{quote(group_openid, safe='')}/join_request_list",
            params=params,
        )

    async def approve_join_request(
        self,
        group_openid: str,
        member_openid: str,
        *,
        operation: str,
        join_request_id: str = "",
        reject_reason: str = "",
        add_to_member_blacklist: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"op": operation}
        if join_request_id:
            payload["join_request_id"] = join_request_id
        if reject_reason:
            payload["reject_reason"] = reject_reason
        if operation == "decline":
            payload["add_to_member_blacklist"] = bool(add_to_member_blacklist)
        return await self.request(
            "POST",
            f"/v2/groups/{quote(group_openid, safe='')}/approval_join_request/{quote(member_openid, safe='')}",
            json=payload,
        )

    async def remove_group_members(
        self,
        group_openid: str,
        member_openids: list[str],
        *,
        add_to_member_blacklist: bool = False,
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/v2/groups/{quote(group_openid, safe='')}/batch_remove_members",
            json={
                "member_openids": member_openids[:20],
                "add_to_member_blacklist": add_to_member_blacklist,
            },
        )

    async def get_group_members(
        self,
        group_openid: str,
        *,
        cursor: str = "",
    ) -> dict[str, Any]:
        params = {"cursor": cursor} if cursor else None
        return await self.request(
            "GET",
            f"/v2/groups/{quote(group_openid, safe='')}/members",
            params=params,
        )

    async def get_group_member(
        self,
        group_openid: str,
        member_openid: str,
    ) -> dict[str, Any]:
        return await self.request(
            "GET",
            f"/v2/groups/{quote(group_openid, safe='')}/members/{quote(member_openid, safe='')}",
        )

    async def update_group_blacklist(
        self,
        group_openid: str,
        *,
        operation: str,
        member_openids: list[str],
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/v2/groups/{quote(group_openid, safe='')}/member_blacklist",
            json={"op": operation, "member_openids": member_openids[:20]},
        )

    async def get_group_blacklist(
        self, group_openid: str, *, cursor: str = "", limit: int = 100
    ) -> dict[str, Any]:
        params = {"limit": str(max(1, min(int(limit), 100)))}
        if cursor:
            params["cursor"] = cursor
        return await self.request(
            "GET",
            f"/v2/groups/{quote(group_openid, safe='')}/member_blacklist",
            params=params,
        )

    async def list_join_approval_strategies(
        self, *, cursor: str = "", limit: int = 50
    ) -> dict[str, Any]:
        params = {"limit": str(max(1, min(int(limit), 50)))}
        if cursor:
            params["cursor"] = cursor
        return await self.request("GET", "/v2/groups/join_approval_strategy", params=params)

    async def create_join_approval_strategy(
        self,
        *,
        group_openids: list[str] | None = None,
        group_ids: list[str] | None = None,
        is_enable: str = "on",
        expire_at: str = "",
        remark: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"is_enable": is_enable}
        if group_openids:
            payload["group_openids"] = group_openids[:100]
        elif group_ids:
            payload["group_ids"] = group_ids[:100]
        else:
            raise QQBotAPIError("join approval strategy requires group_openids or group_ids")
        if expire_at:
            payload["expire_at"] = expire_at
        if remark:
            payload["remark"] = remark[:255]
        return await self.request("POST", "/v2/groups/join_approval_strategy", json=payload)

    async def update_join_approval_strategy(
        self,
        strategy_id: str,
        *,
        is_enable: str = "",
        expire_at: str = "",
        group_operation: str = "",
        group_openids: list[str] | None = None,
        group_ids: list[str] | None = None,
        remark: str = "",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if is_enable:
            payload["is_enable"] = is_enable
        if expire_at:
            payload["expire_at"] = expire_at
        if group_operation:
            group_action: dict[str, Any] = {"op": group_operation}
            if group_openids:
                group_action["group_openids"] = group_openids[:100]
            elif group_ids:
                group_action["group_ids"] = group_ids[:100]
            payload["group_action"] = group_action
        if remark:
            payload["remark"] = remark[:255]
        return await self.request(
            "PATCH",
            f"/v2/groups/join_approval_strategy/{quote(strategy_id, safe='')}",
            json=payload,
        )

    async def delete_join_approval_strategy(self, strategy_id: str) -> dict[str, Any]:
        return await self.request(
            "DELETE", f"/v2/groups/join_approval_strategy/{quote(strategy_id, safe='')}"
        )

    async def execute_join_approval_strategy(self, strategy_id: str) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/v2/groups/join_approval_strategy/{quote(strategy_id, safe='')}/execute",
            json={},
        )

    async def update_join_approval_whitelist(
        self,
        strategy_id: str,
        *,
        operation: str,
        whitelist_users: list[str],
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"/v2/groups/join_approval_strategy/{quote(strategy_id, safe='')}/whitelist_users",
            json={"op": operation, "whitelist_users": [str(item) for item in whitelist_users[:10000]]},
        )

    async def delete_group_message(
        self,
        group_openid: str,
        message_id: str,
    ) -> dict[str, Any]:
        return await self.request(
            "DELETE",
            f"/v2/groups/{quote(group_openid, safe='')}/messages/{quote(message_id, safe='')}",
        )

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.config.api_base_url}{path}"
        method = method.upper()
        retry_safe = method in {"GET", "DELETE"}
        max_attempts = self._MAX_READ_ATTEMPTS if retry_safe else 2
        for attempt in range(max_attempts):
            try:
                token = await self.access_token()
                headers = {"Authorization": f"QQBot {token}"}
                session = await self._get_session()
                async with session.request(
                    method,
                    url,
                    headers=headers,
                    json=json,
                    params=params,
                ) as response:
                    return await self._read_response(response)
            except QQBotAPIError as exc:
                if exc.status == 401 and attempt == 0:
                    async with self._token_lock:
                        self._token = None
                    continue
                if not retry_safe or attempt >= max_attempts - 1:
                    raise
                if exc.status not in self._RETRYABLE_STATUSES:
                    raise
                await asyncio.sleep(self._retry_delay(exc, attempt))
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                if not retry_safe or attempt >= max_attempts - 1:
                    raise QQBotAPIError(
                        f"official QQ bot request failed: {type(exc).__name__}"
                    ) from exc
                await asyncio.sleep(0.5 * (attempt + 1))
        raise QQBotAPIError("official QQ bot request exhausted retries")

    @staticmethod
    def _retry_delay(error: QQBotAPIError, attempt: int) -> float:
        if error.retry_after is not None:
            return max(0.2, min(error.retry_after, 10.0))
        return min(5.0, 0.5 * (attempt + 1))

    @staticmethod
    async def _read_response(response: aiohttp.ClientResponse) -> dict[str, Any]:
        raw = await response.text()
        try:
            data = await response.json(content_type=None)
        except (TypeError, ValueError):
            data = {"raw": raw}
        if response.status >= 400:
            code = data.get("code") or data.get("err_code") or data.get("retcode")
            detail = data.get("message") or data.get("msg") or data.get("raw") or response.reason
            suffix = f" ({code})" if code else ""
            retry_after: float | None = None
            raw_retry_after = response.headers.get("Retry-After", "")
            if raw_retry_after:
                try:
                    retry_after = float(raw_retry_after)
                except ValueError:
                    retry_after = None
            raise QQBotAPIError(
                f"HTTP {response.status}{suffix}: {detail}",
                status=response.status,
                code=str(code or ""),
                retry_after=retry_after,
            )
        if not isinstance(data, dict):
            raise QQBotAPIError("official QQ bot API returned a non-object response")
        return data

