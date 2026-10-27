from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote

from api import QQBotAPI
from config import QQBotConfig
from dashboard import DashboardServer, initial_status
from features.auto_reply.handler import AutoReplyHandler
from features.authorization import AuthorizationHandler
from features.blacklist.handler import BlacklistHandler
from features.basic_commands import BasicCommandHandler
from features.context import MessageContext
from features.context import parse_scum_command
from features.entertainment.handler import EntertainmentHandler
from features.group_admins.handler import GroupAdminHandler
from features.group_info import GroupInfoHandler
from features.identity.handler import IdentityHandler
from features.join_approval import JoinApprovalHandler
from features.keyword_blacklist.handler import KeywordBlacklistHandler
from features.keyword_kick.handler import KeywordKickHandler
from features.keyword_mute.handler import KeywordMuteHandler
from features.lottery.handler import LotteryHandler
from features.moderation.handler import ModerationHandler
from features.owner_authorization import OwnerAuthorizationHandler
from features.scum_query.handler import ScumQueryHandler
from features.scheduled_messages.handler import ScheduledMessageHandler
from features.song_request.handler import SongRequestHandler
from features.statistics.handler import StatisticsHandler
from gateway import QQBotGateway
from storage import SQLiteStore

logger = logging.getLogger(__name__)
KEYWORD_ACTION_APPLIED = "__joker_keyword_action_applied__"


HANDLER_FEATURE_KEYS = {
    "ScumQueryHandler": "scum_query",
    "StatisticsHandler": "statistics",
    "AutoReplyHandler": "auto_reply",
    "LotteryHandler": "lottery",
    "EntertainmentHandler": "entertainment",
    "BlacklistHandler": "blacklist",
    "ModerationHandler": "moderation",
    "KeywordMuteHandler": "keyword_mute",
    "KeywordKickHandler": "keyword_kick",
    "KeywordBlacklistHandler": "keyword_blacklist",
    "GroupAdminHandler": "group_admins",
    "ScheduledMessageHandler": "scheduled_messages",
    "SongRequestHandler": "song_request",
    "GroupInfoHandler": "group_info",
    "JoinApprovalHandler": "join_approval",
}


@dataclass(frozen=True, slots=True)
class GroupMessage:
    group_openid: str
    message_id: str
    author_openid: str
    content: str
    mentions: tuple[dict[str, Any], ...] = ()
    author_role: str = ""


@dataclass(frozen=True, slots=True)
class C2CMessage:
    user_openid: str
    message_id: str
    content: str


class CommandRouter:
    def __init__(self, api: QQBotAPI, config: QQBotConfig, status: dict[str, Any]) -> None:
        self.api = api
        self.owner_openids = {config.owner_openid.strip()} if config.owner_openid.strip() else set()
        self.operator_openids = {
            item.strip()
            for item in (config.owner_openid, *config.admin_openids)
            if item.strip()
        }
        self.status = status
        self.bot_authorization_required = config.bot_authorization_required
        self.store = SQLiteStore(config.data_dir / "joker_qq_admin.sqlite3")
        self.store.ensure_dashboard_admin(config.admin_username, config.admin_password)
        self.handlers = (
            OwnerAuthorizationHandler(),
            AuthorizationHandler(),
            BasicCommandHandler(),
            IdentityHandler(),
            ScumQueryHandler(config.scum_relay_url, config.scum_relay_key),
            StatisticsHandler(),
            KeywordMuteHandler(api),
            KeywordKickHandler(api),
            KeywordBlacklistHandler(api),
            AutoReplyHandler(),
            LotteryHandler(),
            EntertainmentHandler(),
            GroupAdminHandler(),
            GroupInfoHandler(api),
            JoinApprovalHandler(api),
            ScheduledMessageHandler(),
            SongRequestHandler(),
            BlacklistHandler(api),
            ModerationHandler(api),
        )

    async def handle_group_message(self, message: GroupMessage) -> None:
        scope_id = self.store.resolve_group_scope(message.group_openid)
        author_role = message.author_role.casefold()
        is_owner = self._is_owner(message.author_openid)
        context = MessageContext(
            kind="group",
            scope_id=scope_id,
            user_id=message.author_openid,
            message_id=message.message_id,
            content=message.content,
            store=self.store,
            mentions=message.mentions,
            author_role=message.author_role,
            is_operator=(
                is_owner
                or message.author_openid in self.operator_openids
                or self.store.is_group_admin(scope_id, message.author_openid)
                or author_role in {"admin", "owner", "administrator"}
            ),
            is_owner=is_owner,
        )
        await self._dispatch(context)

    async def handle_c2c_message(self, message: C2CMessage) -> None:
        is_owner = self._is_owner(message.user_openid)
        context = MessageContext(
            kind="c2c",
            scope_id=f"c2c:{message.user_openid}",
            user_id=message.user_openid,
            message_id=message.message_id,
            content=message.content,
            store=self.store,
            is_operator=is_owner or message.user_openid in self.operator_openids,
            is_owner=is_owner,
        )
        await self._dispatch(context)

    async def _dispatch(self, context: MessageContext) -> None:
        parsed = parse_scum_command(context.content)
        command_name = parsed[0] if parsed else ""
        authorization_commands = {"授权", "授权状态"}
        bootstrap_commands = {"获取openid", "我的openid", "openid", "身份", "我的id", "获取id"}
        owner_card_commands = {"查看授权", "授权列表", "生成授权卡", "生成授权卡密", "删除授权卡"}
        if command_name in authorization_commands:
            pass
        elif context.is_owner and command_name in owner_card_commands:
            pass
        elif not self.store.get_setting("__global__", "bot_enabled", "1") == "1" and not context.is_owner:
            if parsed:
                await self._send_text(context, "机器人当前已关闭，请联系管理员开启。")
            return
        elif (
            self.bot_authorization_required
            and command_name not in bootstrap_commands
            and not context.is_owner
            and (not context.is_group or not self.store.group_authorized(context.scope_id))
        ):
            if parsed:
                await self._send_text(context, "当前群未授权或授权已过期。授权卡只授权当前群，不授权发送人；请在本群发送 /授权 卡密。")
            return
        if context.user_id:
            context.store.record_message(context.scope_id, context.user_id)
        if context.is_group and context.store.feature_enabled(context.scope_id, "message_records"):
            context.store.record_message_content(
                context.scope_id,
                context.message_id,
                context.user_id,
                context.content,
            )
        for handler in self.handlers:
            feature_key = HANDLER_FEATURE_KEYS.get(type(handler).__name__)
            if context.is_group and feature_key and not context.is_owner and not context.store.feature_enabled(context.scope_id, feature_key):
                continue
            try:
                response = await handler.handle(context)
            except Exception:
                self.status["last_error"] = f"{type(handler).__name__} 执行失败"
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
            if response == KEYWORD_ACTION_APPLIED:
                return
            await self._send_text(context, response)
            return

    async def _send_text(self, context: MessageContext, response: str) -> None:
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
            self.status["last_error"] = "官方 QQ 回复失败"
            logger.exception(
                "official QQ reply failed kind=%s scope=%s message=%s",
                context.kind,
                context.scope_id,
                context.message_id,
            )
        else:
            self.status["reply_count"] += 1

    def _is_owner(self, user_openid: str) -> bool:
        candidate = str(user_openid or "").strip()
        return bool(candidate) and (
            candidate in self.owner_openids
            or candidate == self.store.get_bot_owner_openid()
        )

    def close(self) -> None:
        self.store.close()



class OfficialQQBotApp:
    def __init__(self, config: QQBotConfig) -> None:
        self.status = initial_status()
        self.api = QQBotAPI(config)
        self.router = CommandRouter(self.api, config, self.status)
        self.gateway = QQBotGateway(self.api, config, self._on_event, self._on_gateway_status)
        self.dashboard = DashboardServer(config, self.router.store, self.status, self.api, self._on_event)

    async def run(self) -> None:
        scheduled_task = asyncio.create_task(self._scheduled_message_loop())
        try:
            await self.dashboard.start()
            if self.gateway.config.transport == "webhook":
                self.status["gateway_state"] = "webhook_listening"
                logger.info("official QQ webhook listening")
                await asyncio.Event().wait()
            else:
                await self.gateway.run_forever()
        finally:
            scheduled_task.cancel()
            await asyncio.gather(scheduled_task, return_exceptions=True)
            await self.dashboard.stop()
            self.router.close()
            await self.api.close()

    async def _scheduled_message_loop(self) -> None:
        while True:
            for row in self.router.store.due_scheduled_messages(int(time.time())):
                if not self.router.store.feature_enabled(row["scope_id"], "scheduled_messages"):
                    self.router.store.advance_scheduled_message(
                        row["schedule_id"], error="分群定时消息功能已关闭"
                    )
                    continue
                try:
                    await self.api.send_group_message(row["scope_id"], row["content"])
                except Exception as exc:
                    logger.warning("scheduled group message failed scope=%s: %s", row["scope_id"], type(exc).__name__)
                    self.router.store.advance_scheduled_message(
                        row["schedule_id"], error=str(exc)
                    )
                else:
                    self.router.store.advance_scheduled_message(row["schedule_id"])
            for task in self.router.store.due_scheduled_tasks(int(time.time())):
                if not self.router.store.feature_enabled(task["scope_id"], "scheduled_messages"):
                    self.router.store.complete_scheduled_task(
                        task["task_id"], error="分群定时任务功能已关闭"
                    )
                    continue
                try:
                    await self._run_scheduled_task(task)
                except Exception as exc:
                    logger.warning(
                        "scheduled group task failed scope=%s type=%s: %s",
                        task["scope_id"], task["task_type"], type(exc).__name__,
                    )
                    self.router.store.complete_scheduled_task(task["task_id"], error=str(exc))
                else:
                    self.router.store.complete_scheduled_task(task["task_id"])
            await asyncio.sleep(2)

    async def _all_regular_group_members(self, scope_id: str) -> list[str]:
        members: list[str] = []
        cursor = ""
        seen_cursors: set[str] = set()
        while True:
            payload = await self.api.get_group_members(scope_id, cursor=cursor)
            rows = payload.get("members")
            if isinstance(rows, list):
                for item in rows:
                    if not isinstance(item, dict):
                        continue
                    member_id = str(
                        item.get("member_openid") or item.get("user_openid") or item.get("openid") or ""
                    ).strip()
                    role = str(item.get("member_role", "member")).lower()
                    if (
                        member_id
                        and role not in {"owner", "admin", "administrator", "bot"}
                        and not bool(item.get("bot") or item.get("is_bot"))
                    ):
                        members.append(member_id)
            next_cursor = str(payload.get("next_cursor", "") or "").strip()
            if not next_cursor or next_cursor in seen_cursors or len(members) >= 5000:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        return list(dict.fromkeys(members))

    async def _run_scheduled_task(self, task: dict[str, Any]) -> None:
        scope_id = str(task["scope_id"])
        task_type = str(task["task_type"])
        if task_type == "broadcast":
            await self.api.send_group_message(scope_id, str(task["content"]))
            return
        if task_type == "song":
            keyword = str(task["content"]).strip()
            await self.api.send_group_message(
                scope_id,
                f"🎵 点歌：{keyword}\nhttps://music.163.com/#/search/m/?s={quote(keyword)}&type=1",
            )
            return
        member_ids = await self._all_regular_group_members(scope_id)
        if not member_ids:
            return
        operation = "add" if task_type == "mute_all" else "del"
        mute_expire_at = ""
        if operation == "add":
            seconds = max(1, int(task.get("mute_seconds") or 600))
            mute_expire_at = (
                datetime.now(timezone.utc) + timedelta(seconds=seconds)
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
        for offset in range(0, len(member_ids), 20):
            await self.api.set_group_members_mute(
                scope_id,
                member_ids[offset:offset + 20],
                operation=operation,
                mute_expire_at=mute_expire_at,
            )

    async def _on_gateway_status(self, state: str, detail: str) -> None:
        self.status["gateway_state"] = state
        self.status["last_error"] = detail if state == "error" else ""
        logger.info("official QQ gateway state=%s%s", state, f" detail={detail}" if detail else "")

    async def _on_event(self, event_type: str, data: dict[str, Any]) -> None:
        self.status["event_count"] += 1
        self.status["last_event"] = event_type
        self.status["last_event_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if event_type in {"GROUP_AT_MESSAGE_CREATE", "GROUP_MESSAGE_CREATE", "GROUP_MSG_RECEIVE"}:
            self.status["group_event_count"] += 1
            self.status["last_group_event"] = event_type
            if event_type in {"GROUP_MESSAGE_CREATE", "GROUP_MSG_RECEIVE"}:
                self.status["full_message_event_count"] += 1
            elif event_type == "GROUP_AT_MESSAGE_CREATE":
                self.status["at_message_event_count"] += 1
            author = data.get("author")
            if not isinstance(author, dict):
                author = {}
            message = GroupMessage(
                group_openid=str(
                    data.get("group_openid") or data.get("group_id") or data.get("guild_id") or ""
                ).strip(),
                message_id=str(data.get("id", "") or "").strip(),
                author_openid=str(
                    author.get("member_openid") or author.get("user_openid") or author.get("id") or ""
                ).strip(),
                content=str(data.get("content", "") or ""),
                mentions=tuple(
                    item for item in (data.get("mentions") or []) if isinstance(item, dict)
                ),
                author_role=str(
                    author.get("member_role") or author.get("role") or ""
                ).strip(),
            )
            if message.group_openid and message.message_id and message.content:
                await self.router.handle_group_message(message)
            else:
                logger.warning(
                    "ignored official group event type=%s group=%s message=%s content=%s",
                    event_type,
                    bool(message.group_openid),
                    bool(message.message_id),
                    bool(message.content),
                )
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

