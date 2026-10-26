from __future__ import annotations

from ..context import MessageContext, command_is


class IdentityHandler:
    async def handle(self, context: MessageContext) -> str | None:
        binding = command_is(context.content, "/绑定官方群", "/绑定群号")
        if binding is not None:
            if not context.is_group:
                return "官方群绑定只支持群聊"
            arguments, _ = binding
            if not arguments or not arguments[0].isdigit():
                return "用法：/绑定官方群 数字QQ群号"
            context.store.bind_official_group(context.scope_id, arguments[0])
            return f"已记录官方群映射：{arguments[0]}"

        if command_is(context.content, "/查看官方群绑定", "/群号绑定") is not None:
            bound = context.store.get_official_group_binding(context.scope_id)
            return f"当前映射群号：{bound}" if bound else "当前没有映射数字QQ群号"

        if command_is(context.content, "/我的ID", "/openid", "/身份") is None:
            return None
        scope_label = "群" if context.is_group else "私聊"
        return f"{scope_label} openid：{context.scope_id}\n用户 openid：{context.user_id}"
