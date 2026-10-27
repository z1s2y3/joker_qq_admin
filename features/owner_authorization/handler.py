from __future__ import annotations

from datetime import datetime, timezone

from features.context import MessageContext, command_is


class OwnerAuthorizationHandler:
    """Owner-only card issuance and authorization inspection commands."""

    async def handle(self, context: MessageContext) -> str | None:
        commands = (
            command_is(context.content, "/查看授权", "/授权列表"),
            command_is(context.content, "/生成授权卡", "/生成授权卡密"),
            command_is(context.content, "/删除授权卡"),
        )
        if not any(command is not None for command in commands):
            return None
        if not context.is_owner:
            return "仅机器人主人可使用授权管理命令。"

        if commands[0] is not None:
            return self._format_authorizations(context)

        if commands[1] is not None:
            arguments, _ = commands[1]
            try:
                days = int(arguments[0]) if arguments else 30
                code = context.store.create_access_card("bot", max_uses=1, days=days)
            except (TypeError, ValueError):
                return "用法：/生成授权卡 [有效天数]"
            return f"已生成群授权卡：{code}\n有效期：{days} 天；每张卡只能授权一个群。"

        arguments, _ = commands[2]
        if not arguments:
            return "用法：/删除授权卡 卡密"
        if not context.store.delete_access_card(arguments[0]):
            return "未找到该授权卡。"
        return "授权卡已删除，使用该卡的网页和机器人授权已同步撤销。"

    @staticmethod
    def _format_authorizations(context: MessageContext) -> str:
        now = int(datetime.now(timezone.utc).timestamp())
        cards = [
            item for item in context.store.list_access_cards()
            if item["kind"] in {"bot", "license", "portal", "group"}
            and item["enabled"] and item["expires_at"] > now
        ]
        authorizations = [
            item for item in context.store.list_group_authorizations()
            if item["enabled"] and (not item["expires_at"] or item["expires_at"] > now)
        ]
        group_names = {
            str(item["scope_id"]): str(item.get("numeric_group_id") or "")
            for item in context.store.list_scopes()
        }
        unused_cards = [item for item in cards if item["used_count"] == 0]
        lines = []
        if context.is_group:
            current_group_id = context.store.get_official_group_binding(context.scope_id)
            current_status = context.store.group_authorization_status(context.scope_id)
            current_label = f"QQ 群 {current_group_id}" if current_group_id else "当前群"
            if current_status and current_status["enabled"]:
                current_expires = datetime.fromtimestamp(current_status["expires_at"], timezone.utc).strftime("%Y-%m-%d %H:%M") if current_status["expires_at"] else "永久"
                lines.append(f"本群 {current_label}｜已授权｜到期：{current_expires}")
            else:
                lines.append(f"本群 {current_label}｜未授权")
        lines.extend([f"可用群授权卡：{len(unused_cards)} 张", f"当前已授权群：{len(authorizations)} 个"])
        for item in cards[:10]:
            expires = datetime.fromtimestamp(item["expires_at"], timezone.utc).strftime("%Y-%m-%d")
            state = "未使用" if item["used_count"] == 0 else "已绑定群"
            lines.append(f"{item['card_code']}｜{state}｜至 {expires}")
        if len(cards) > 10:
            lines.append("其余授权卡请在后台查看。")
        for item in authorizations[:10]:
            expires = datetime.fromtimestamp(item["expires_at"], timezone.utc).strftime("%Y-%m-%d %H:%M") if item["expires_at"] else "永久"
            group_name = item.get("numeric_group_id") or group_names.get(item["scope_id"]) or item["scope_id"]
            lines.append(f"群 {group_name}｜已授权｜到期：{expires}")
        return "\n".join(lines)
