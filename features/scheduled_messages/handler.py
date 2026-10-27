from __future__ import annotations

from features.context import MessageContext, parse_command


class ScheduledMessageHandler:
    feature_key = "scheduled_messages"

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None or not context.is_group:
            return None
        name, arguments, argument_text = parsed
        if name in {"定时消息", "定时消息列表"}:
            rows = context.store.list_scheduled_messages(context.scope_id)
            if not rows:
                return "本群还没有定时消息"
            lines = ["本群定时消息"]
            for row in rows:
                minutes = max(1, int(row["interval_seconds"]) // 60)
                state = "开启" if row["enabled"] else "关闭"
                lines.append(f"{row['schedule_id']}：每 {minutes} 分钟，{state}，{row['content']}")
            return "\n".join(lines)
        if name in {"添加定时消息", "设置定时消息"}:
            if not context.is_operator:
                return "定时消息命令仅群主或管理员可用。"
            if len(arguments) < 2 or not arguments[0].isdigit():
                return "用法：/添加定时消息 分钟 消息内容"
            minutes = int(arguments[0])
            content = argument_text[len(arguments[0]):].strip()
            if not content:
                return "用法：/添加定时消息 分钟 消息内容"
            if minutes < 1 or minutes > 525600:
                return "间隔需为 1 到 525600 分钟。"
            schedule_id = context.store.create_scheduled_message(context.scope_id, content, minutes * 60)
            return f"已添加定时消息，编号：{schedule_id}，每 {minutes} 分钟发送。"
        if name in {"删除定时消息", "移除定时消息"}:
            if not context.is_operator:
                return "定时消息命令仅群主或管理员可用。"
            if not arguments or not arguments[0].isdigit():
                return "用法：/删除定时消息 编号"
            removed = context.store.delete_scheduled_message(int(arguments[0]), context.scope_id)
            return "已删除定时消息" if removed else "未找到该定时消息"
        return None
