from __future__ import annotations

from features.context import MessageContext, clean_content, parse_command


class AutoReplyHandler:
    feature_key = "auto_reply"

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed:
            name, arguments, argument_text = parsed
            if name in {"添加回复", "设置回复", "添加精准回复", "添加模糊回复"}:
                if not context.is_operator:
                    return "自动回复设置仅群主或管理员可用。"
                if len(arguments) < 2:
                    return "用法：/添加回复 关键词 回复内容"
                trigger = arguments[0]
                response = argument_text[len(trigger):].strip()
                match_mode = "fuzzy" if name == "添加模糊回复" else "exact"
                context.store.save_reply(context.scope_id, trigger, response, match_mode)
                return f"已保存{'模糊' if match_mode == 'fuzzy' else '精准'}回复：{trigger}"
            if name in {"删除回复", "移除回复"}:
                if not context.is_operator:
                    return "自动回复设置仅群主或管理员可用。"
                if not arguments:
                    return "用法：/删除回复 关键词"
                removed = context.store.delete_reply(context.scope_id, arguments[0])
                return "已删除回复" if removed else "未找到该关键词"
            if name in {"查看回复", "回复列表"}:
                if not context.is_operator:
                    return "自动回复设置仅群主或管理员可用。"
                rows = context.store.list_replies(context.scope_id)
                if not rows:
                    return "暂无自动回复"
                return "自动回复\n" + "\n".join(
                    f"{'模糊' if mode == 'fuzzy' else '精准'} / {trigger}：{response}"
                    for trigger, response, _, mode in rows
                )
            if name in {"添加专属回复", "设置专属回复"}:
                if not context.store.feature_enabled(context.scope_id, "user_replies"):
                    return None
                if len(arguments) < 3:
                    return "用法：/添加专属回复 @成员 关键词 回复内容"
                target = self._target_user(context, arguments[0])
                trigger = arguments[1]
                response = argument_text.split(maxsplit=2)[2] if len(argument_text.split(maxsplit=2)) == 3 else ""
                if not target or not response:
                    return "用法：/添加专属回复 @成员 关键词 回复内容"
                if not context.is_operator:
                    return "专属回复命令仅群主或管理员可用。"
                context.store.save_user_reply(context.scope_id, target, trigger, response)
                return f"已保存 {target} 的专属回复：{trigger}"
            if name in {"删除专属回复", "移除专属回复"}:
                if not context.store.feature_enabled(context.scope_id, "user_replies"):
                    return None
                if len(arguments) < 2:
                    return "用法：/删除专属回复 @成员 关键词"
                if not context.is_operator:
                    return "专属回复命令仅群主或管理员可用。"
                target = self._target_user(context, arguments[0])
                removed = context.store.delete_user_reply(context.scope_id, target, arguments[1])
                return "已删除专属回复" if removed else "未找到该专属回复"
            if name in {"查看专属回复", "专属回复列表"}:
                if not context.store.feature_enabled(context.scope_id, "user_replies"):
                    return None
                if not context.is_operator:
                    return "专属回复命令仅群主或管理员可用。"
                rows = context.store.list_user_replies(context.scope_id)
                if not rows:
                    return "暂无专属回复"
                return "专属回复\n" + "\n".join(
                    f"{row['user_id']} / {row['trigger']}：{row['response']}" for row in rows
                )
            if name in {"开启自动回复", "启用自动回复"}:
                if not context.is_operator:
                    return "自动回复设置仅群主或管理员可用。"
                context.store.set_setting(context.scope_id, "auto_reply_enabled", "1")
                return "自动回复已开启"
            if name in {"关闭自动回复", "停用自动回复"}:
                if not context.is_operator:
                    return "自动回复设置仅群主或管理员可用。"
                context.store.set_setting(context.scope_id, "auto_reply_enabled", "0")
                return "自动回复已关闭"
            return None

        if context.store.get_setting(context.scope_id, "auto_reply_enabled", "1") != "1":
            return None
        trigger = clean_content(context.content)
        user_response = None
        if context.store.feature_enabled(context.scope_id, "user_replies"):
            user_response = context.store.find_user_reply(context.scope_id, context.user_id, trigger)
        return user_response or context.store.find_reply(context.scope_id, trigger)

    @staticmethod
    def _target_user(context: MessageContext, value: str) -> str:
        for mention in context.mentions:
            if not isinstance(mention, dict):
                continue
            target = str(
                mention.get("member_openid") or mention.get("user_openid") or mention.get("id") or ""
            ).strip()
            if target:
                return target
        return value.strip().strip("<@!>")
