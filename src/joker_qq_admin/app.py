from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from .api import QQBotAPI
from .config import QQBotConfig
from .features.auto_reply.handler import AutoReplyHandler
from .features.blacklist.handler import BlacklistHandler
from .features.basic_commands import BasicCommandHandler
from .features.context import MessageContext
from .features.entertainment.handler import EntertainmentHandler
from .features.game_commands.handler import GameCommandHandler
from .features.identity.handler import IdentityHandler
from .features.lottery.handler import LotteryHandler
from .features.moderation.handler import ModerationHandler
from .features.music.handler import MusicHandler
from .features.scum_query.handler import ScumQueryHandler
from .features.statistics.handler import StatisticsHandler
from .features.text_to_image.handler import TextToImageHandler
from .features.welcome.handler import WelcomeHandler
from .gateway import QQBotGateway
from .storage import SQLiteStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GroupMessage:
    group_openid: str
    message_id: str
    author_openid: str
    content: str


@dataclass(frozen=True, slots=True)
class C2CMessage:
    user_openid: str
    message_id: str
    content: str


class CommandRouter:
    def __init__(self, api: QQBotAPI, config: QQBotConfig) -> None:
        self.api = api
        self.store = SQLiteStore(config.data_dir / "joker_qq_admin.sqlite3")
        self.handlers = (
            BasicCommandHandler(),
            IdentityHandler(),
            ScumQueryHandler(config.scum_relay_url, config.scum_relay_key),
            StatisticsHandler(),
            AutoReplyHandler(),
            LotteryHandler(),
            EntertainmentHandler(),
            GameCommandHandler(config.game_bridge_url, config.game_bridge_token),
            BlacklistHandler(),
            ModerationHandler(),
            MusicHandler(),
            TextToImageHandler(),
            WelcomeHandler(),
        )

    async def handle_group_message(self, message: GroupMessage) -> None:
        context = MessageContext(
            kind="group",
            scope_id=message.group_openid,
            user_id=message.author_openid,
            message_id=message.message_id,
            content=message.content,
            store=self.store,
        )
        await self._dispatch(context)

    async def handle_c2c_message(self, message: C2CMessage) -> None:
        context = MessageContext(
            kind="c2c",
            scope_id=f"c2c:{message.user_openid}",
            user_id=message.user_openid,
            message_id=message.message_id,
            content=message.content,
            store=self.store,
        )
        await self._dispatch(context)

    async def _dispatch(self, context: MessageContext) -> None:
        if context.user_id:
            context.store.record_message(context.scope_id, context.user_id)
        for handler in self.handlers:
            try:
                response = await handler.handle(context)
            except Exception:
                logger.exception(
                    "feature handler failed kind=%s scope=%s user=%s handler=%s",
                    context.kind,
                    context.scope_id,
                    context.user_id,
                    type(handler).__name__,
                )
                response = "功能执行失败，请稍后重试。"
            if not response:
                continue
            try:
                if context.is_group:
                    await self.api.send_group_message(
                        context.scope_id, response, msg_id=context.message_id
                    )
                else:
                    await self.api.send_c2c_message(
                        context.user_id, response, msg_id=context.message_id
                    )
            except Exception:
                logger.exception(
                    "official QQ reply failed kind=%s scope=%s message=%s",
                    context.kind,
                    context.scope_id,
                    context.message_id,
                )
            return

    def close(self) -> None:
        self.store.close()



class OfficialQQBotApp:
    def __init__(self, config: QQBotConfig) -> None:
        self.api = QQBotAPI(config)
        self.router = CommandRouter(self.api, config)
        self.gateway = QQBotGateway(self.api, config, self._on_event)

    async def run(self) -> None:
        try:
            await self.gateway.run_forever()
        finally:
            self.router.close()
            await self.api.close()

    async def _on_event(self, event_type: str, data: dict[str, Any]) -> None:
        if event_type in {"GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_CREATE", "GROUP_MSG_RECEIVE"}:
            author = data.get("author")
            if not isinstance(author, dict):
                author = {}
            message = GroupMessage(
                group_openid=str(data.get("group_openid", "") or "").strip(),
                message_id=str(data.get("id", "") or "").strip(),
                author_openid=str(author.get("member_openid", "") or "").strip(),
                content=str(data.get("content", "") or ""),
            )
            if message.group_openid and message.message_id and message.content:
                await self.router.handle_group_message(message)
            return

        if event_type == "C2C_MESSAGE_CREATE":
            author = data.get("author")
            if not isinstance(author, dict):
                author = {}
            message = C2CMessage(
                user_openid=str(author.get("user_openid", "") or "").strip(),
                message_id=str(data.get("id", "") or "").strip(),
                content=str(data.get("content", "") or ""),
            )
            if message.user_openid and message.message_id and message.content:
                await self.router.handle_c2c_message(message)


async def run() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config = QQBotConfig.from_env()
    logger.info("starting joker_qq_admin with official QQ bot gateway")
    await OfficialQQBotApp(config).run()

