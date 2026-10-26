from __future__ import annotations

from features.context import MessageContext, clean_content, parse_command


class AutoReplyHandler:
    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed:
            name, arguments, argument_text = parsed
            if name in {"添加回复", "设置回复"}:
                if len(arguments) < 2:
                    return "用法：/添加回复 关键词 回复内容"
                trigger = arguments[0]
                response = argument_text[len(trigger):].strip()
                context.store.save_reply(context.scope_id, trigger, response)
                return f"已保存回复：{trigger}"
            if name in {"删除回复", "移除回复"}:
                if not arguments:
                    return "用法：/删除回复 关键词"
                removed = context.store.delete_reply(context.scope_id, arguments[0])
                return "已删除回复" if removed else "未找到该关键词"
            if name in {"查看回复", "回复列表"}:
                rows = context.store.list_replies(context.scope_id)
                if not rows:
                    return "暂无自动回复"
                return "自动回复\n" + "\n".join(f"{trigger}：{response}" for trigger, response, _ in rows)
            if name in {"开启自动回复", "启用自动回复"}:
                context.store.set_setting(context.scope_id, "auto_reply_enabled", "1")
                return "自动回复已开启"
            if name in {"关闭自动回复", "停用自动回复"}:
                context.store.set_setting(context.scope_id, "auto_reply_enabled", "0")
                return "自动回复已关闭"
            return None

        if context.store.get_setting(context.scope_id, "auto_reply_enabled", "1") != "1":
            return None
        return context.store.find_reply(context.scope_id, clean_content(context.content))
