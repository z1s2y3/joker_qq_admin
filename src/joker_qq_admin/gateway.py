from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Awaitable, Callable

import aiohttp

from .api import QQBotAPI
from .config import QQBotConfig

logger = logging.getLogger(__name__)
EventHandler = Callable[[str, dict[str, Any]], Awaitable[None]]


class QQBotGateway:
    def __init__(self, api: QQBotAPI, config: QQBotConfig, on_event: EventHandler) -> None:
        self.api = api
        self.config = config
        self.on_event = on_event
        self._sequence: int | None = None

    async def run_forever(self) -> None:
        delay = self.config.reconnect_min
        timeout = aiohttp.ClientTimeout(total=None)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            while True:
                try:
                    await self._run_once(session)
                    delay = self.config.reconnect_min
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception("official QQ bot gateway disconnected")
                await asyncio.sleep(delay)
                delay = min(self.config.reconnect_max, delay * 2)

    async def _run_once(self, session: aiohttp.ClientSession) -> None:
        url = await self.api.gateway_url()
        async with session.ws_connect(url, heartbeat=None, autoclose=False) as websocket:
            hello = await websocket.receive_json()
            if hello.get("op") != 10:
                raise RuntimeError(f"gateway did not send hello: {hello}")
            heartbeat_interval = max(1.0, float(hello["d"]["heartbeat_interval"]) / 1000)
            await websocket.send_json(self._identify_payload())
            heartbeat = asyncio.create_task(self._heartbeat(websocket, heartbeat_interval))
            try:
                async for message in websocket:
                    if message.type == aiohttp.WSMsgType.TEXT:
                        await self._handle_payload(websocket, json.loads(message.data))
                    elif message.type in {
                        aiohttp.WSMsgType.CLOSE,
                        aiohttp.WSMsgType.CLOSED,
                        aiohttp.WSMsgType.ERROR,
                    }:
                        break
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)

    def _identify_payload(self) -> dict[str, Any]:
        return {
            "op": 2,
            "d": {
                "token": "QQBot " + self._token_for_gateway,
                "intents": self.config.intents,
                "shard": [0, 1],
                "properties": {
                    "$os": "windows",
                    "$browser": "joker_qq_admin",
                    "$device": "joker_qq_admin",
                },
            },
        }

    @property
    def _token_for_gateway(self) -> str:
        token = self.api._token
        if token is None:
            raise RuntimeError("gateway identify attempted without access token")
        return token.value

    async def _heartbeat(self, websocket: aiohttp.ClientWebSocketResponse, interval: float) -> None:
        while True:
            await asyncio.sleep(interval)
            await websocket.send_json({"op": 1, "d": self._sequence})

    async def _handle_payload(
        self,
        websocket: aiohttp.ClientWebSocketResponse,
        payload: dict[str, Any],
    ) -> None:
        if payload.get("s") is not None:
            self._sequence = payload["s"]
        op = payload.get("op")
        if op == 0:
            data = payload.get("d")
            if isinstance(data, dict):
                await self.on_event(str(payload.get("t", "")), data)
        elif op == 7:
            await websocket.close()
        elif op == 9:
            raise RuntimeError("official QQ bot gateway rejected the session")

