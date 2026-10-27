from __future__ import annotations

from datetime import datetime

from features.context import MessageContext, command_is


class AuthorizationHandler:
    """Handles authorization at the official group level."""

    async def handle(self, context: MessageContext) -> str | None:
        matched = command_is(context.content, "/授权")
        if matched is not None:
            if not context.is_group:
                return "请在需要使用机器人的官方群内发送：/授权 卡密。"
            arguments, _ = matched
            if not arguments:
                return "用法：/授权 卡密\n每张授权卡只能绑定一个官方群。"
            result = context.store.claim_group_authorization(context.scope_id, arguments[0])
            if not result:
                return "授权失败：卡密无效、已过期或使用次数已用完。"
            if result.get("error"):
                return f"授权失败：{result['error']}。"
            if result.get("already_authorized"):
                return self._status_message(context, result["expires_at"], already=True)
            return self._status_message(context, result["expires_at"], already=False)

        if command_is(context.content, "/授权状态") is not None:
            if not context.is_group:
                return "请在官方群内使用 /授权状态 查看该群授权。"
            status = context.store.group_authorization_status(context.scope_id)
            if not status:
                return f"{self._group_label(context)}未授权，请在本群发送 /授权 卡密。"
            if not status["enabled"]:
                return f"{self._group_label(context)}授权已过期或已停用，请使用新授权卡续期。"
            return self._status_message(context, status["expires_at"], already=True)
        return None

    @staticmethod
    def _group_label(context: MessageContext) -> str:
        numeric_group_id = context.store.get_official_group_binding(context.scope_id)
        return f"当前群（QQ 群 {numeric_group_id}）" if numeric_group_id else "当前群"

    @classmethod
    def _status_message(cls, context: MessageContext, expires_at: int, *, already: bool) -> str:
        prefix = f"{cls._group_label(context)}已授权，无需重复使用卡密。" if already else f"授权成功：已授权{cls._group_label(context)}。"
        if expires_at:
            expires = datetime.fromtimestamp(int(expires_at)).strftime("%Y-%m-%d %H:%M")
            return f"{prefix}\n到期时间：{expires}\n授权仅对当前群生效，不会授权发送人账号。"
        return f"{prefix}\n授权仅对当前群生效，不会授权发送人账号。"
