from __future__ import annotations

import re

from features.context import MessageContext, parse_command


_MENTION_PATTERN = re.compile(r"^<@!?([^>]+)>$")


class GroupAdminHandler:
    feature_key = "group_admins"

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None or not context.is_group:
            return None
        name, arguments, argument_text = parsed
        if name in {"分管管理员", "群管理员"}:
            rows = context.store.list_group_admins(context.scope_id)
            if not rows:
                return "本群还没有分管管理员"
            return "本群分管管理员\n" + "\n".join(
                f"{row['display_name']}：{row['user_id']}" for row in rows
            )
        if name not in {"添加分管", "删除分管"}:
            return None
        if not context.is_operator:
            return "分管管理员命令仅群主或管理员可用。"
        target, display_name = self._target(context, arguments, argument_text)
        if not target:
            return f"用法：/{name} @成员"
        if name == "添加分管":
            context.store.add_group_admin(context.scope_id, target, display_name or target)
            return f"已添加分管管理员：{display_name or target}"
        return "已删除分管管理员" if context.store.remove_group_admin(context.scope_id, target) else "该成员不是分管管理员"

    @staticmethod
    def _target(
        context: MessageContext,
        arguments: list[str],
        argument_text: str,
    ) -> tuple[str, str]:
        for mention in context.mentions:
            if not isinstance(mention, dict):
                continue
            target = str(
                mention.get("member_openid") or mention.get("user_openid") or mention.get("id") or ""
            ).strip()
            if target:
                first = arguments[0] if arguments else ""
                return target, argument_text[len(first):].strip()
        if not arguments:
            return "", ""
        first = arguments[0].strip()
        matched = _MENTION_PATTERN.fullmatch(first)
        target = matched.group(1).strip() if matched else first
        return target, argument_text[len(first):].strip()
