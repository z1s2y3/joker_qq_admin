from __future__ import annotations

from api import QQBotAPI, QQBotAPIError
from features.context import MessageContext, clean_content


class KeywordBlacklistHandler:
    """Remove and blacklist the message author for a configured keyword."""

    feature_key = "keyword_blacklist"

    def __init__(self, api: QQBotAPI) -> None:
        self.api = api

    async def handle(self, context: MessageContext) -> str | None:
        if not context.is_group or context.is_operator or not context.user_id:
            return None
        content = clean_content(context.content)
        if not content or content.startswith("/"):
            return None
        for rule in context.store.list_keyword_rules(context.scope_id, "blacklist"):
            if not rule["enabled"] or rule["trigger"] not in content:
                continue
            try:
                await self.api.remove_group_members(
                    context.scope_id,
                    [context.user_id],
                )
                result = await self.api.update_group_blacklist(
                    context.scope_id,
                    operation="add",
                    member_openids=[context.user_id],
                )
                failed = result.get("fail_openids") if isinstance(result, dict) else None
                if isinstance(failed, list) and context.user_id in {str(item) for item in failed}:
                    return "关键词黑名单执行失败：成员已移出，但未能加入官方群黑名单"
                context.store.add_blacklist(context.scope_id, context.user_id, f"关键词：{rule['trigger']}")
            except QQBotAPIError as exc:
                return f"关键词黑名单执行失败：{exc}"
            return "__joker_keyword_action_applied__"
        return None
