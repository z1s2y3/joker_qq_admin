from __future__ import annotations

from datetime import datetime, timedelta, timezone

from api import QQBotAPI, QQBotAPIError
from features.context import MessageContext, clean_content


class KeywordMuteHandler:
    """Apply one independent keyword-mute rule to the message author."""

    feature_key = "keyword_mute"

    def __init__(self, api: QQBotAPI) -> None:
        self.api = api

    async def handle(self, context: MessageContext) -> str | None:
        if not context.is_group or context.is_operator or not context.user_id:
            return None
        content = clean_content(context.content)
        if not content or content.startswith("/"):
            return None
        for rule in context.store.list_keyword_rules(context.scope_id, "mute"):
            if not rule["enabled"] or rule["trigger"] not in content:
                continue
            expire_at = (
                datetime.now(timezone.utc)
                + timedelta(seconds=int(rule.get("duration_seconds") or 600))
            ).isoformat(timespec="seconds").replace("+00:00", "Z")
            try:
                await self.api.set_group_member_mute(
                    context.scope_id,
                    context.user_id,
                    operation="add",
                    mute_expire_at=expire_at,
                )
            except QQBotAPIError as exc:
                return f"关键词禁言执行失败：{exc}"
            return "__joker_keyword_action_applied__"
        return None
