from __future__ import annotations

from ..context import MessageContext, parse_command


class BlacklistHandler:
    """Persistent blacklist records.

    Actual kick/ban actions are intentionally separate because the official
    bot must expose and authorize the corresponding group-management API.
    """

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, arguments, argument_text = parsed
        if name in {"拉黑", "加入黑名单"}:
            if not arguments:
                return "用法：/拉黑 用户openid [原因]"
            user_id = arguments[0]
            reason = argument_text[len(user_id):].strip()
            context.store.add_blacklist(context.scope_id, user_id, reason)
            return f"已记录黑名单：{user_id}"
        if name in {"删黑", "移出黑名单"}:
            if not arguments:
                return "用法：/删黑 用户openid"
            removed = context.store.remove_blacklist(context.scope_id, arguments[0])
            return "已移出黑名单" if removed else "该用户不在黑名单中"
        if name in {"查看黑名单", "黑名单"}:
            rows = context.store.list_blacklist(context.scope_id)
            if not rows:
                return "当前黑名单为空"
            lines = ["黑名单"]
            lines.extend(
                f"{user_id}：{reason or '未填写原因'}"
                for user_id, reason in rows
            )
            return "\n".join(lines)
        if name == "清空黑名单":
            count = context.store.clear_blacklist(context.scope_id)
            return f"已清空黑名单，共 {count} 条"
        return None
