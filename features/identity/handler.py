from __future__ import annotations

from features.context import MessageContext, command_is


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
            return (
                f"已记录 QQ 群号：{arguments[0]}\n"
                "现在可在网站用户中心填写同一个 QQ 群号完成绑定。"
            )

        if command_is(context.content, "/查看官方群绑定", "/群号绑定") is not None:
            bound = context.store.get_official_group_binding(context.scope_id)
            return f"当前映射群号：{bound}" if bound else "当前没有映射数字QQ群号"

        if command_is(
            context.content,
            "/我的ID",
            "/获取ID",
            "/获取OpenID",
            "/我的OpenID",
            "/官方群OpenID",
            "/群OpenID",
            "/openid",
            "/身份",
        ) is None:
            return None
        if context.is_group:
            return (
                f"当前 QQ 群的官方群 OpenID：{context.scope_id}\n"
                f"你的用户 OpenID：{context.user_id}\n"
                "网页绑定优先使用数字 QQ 群号：先发送 /绑定官方群 数字QQ群号，再在网站填写同一群号。"
            )
        return f"私聊 OpenID：{context.scope_id}\n你的用户 OpenID：{context.user_id}"
