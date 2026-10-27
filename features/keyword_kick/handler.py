from __future__ import annotations

from api import QQBotAPI, QQBotAPIError
from features.context import MessageContext, clean_content


class KeywordKickHandler:
    """Remove the message author when a configured keyword is received."""

    feature_key = "keyword_kick"

    def __init__(self, api: QQBotAPI) -> None:
        self.api = api

    async def handle(self, context: MessageContext) -> str | None:
        if not context.is_group or context.is_operator or not context.user_id:
            return None
        content = clean_content(context.content)
        if not content or content.startswith("/"):
            return None
        for rule in context.store.list_keyword_rules(context.scope_id, "kick"):
            if not rule["enabled"] or rule["trigger"] not in content:
                continue
            try:
                await self.api.remove_group_members(
                    context.scope_id,
                    [context.user_id],
                    add_to_member_blacklist=False,
                )
            except QQBotAPIError as exc:
                return f"关键词踢出执行失败：{exc}"
            return "__joker_keyword_action_applied__"
        return None
