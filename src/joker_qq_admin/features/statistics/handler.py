from __future__ import annotations

from ..context import MessageContext, command_is


class StatisticsHandler:
    async def handle(self, context: MessageContext) -> str | None:
        matched = command_is(
            context.content,
            "/签到",
            "/签到状态",
            "/我的信息",
            "/个人信息",
            "/排行榜",
            "/积分排行",
            "/群统计",
            "/群数据",
        )
        if matched is None:
            return None
        parsed_name = context.content.lstrip()[1:].split(maxsplit=1)[0].casefold()
        if parsed_name == "签到":
            result = context.store.check_in(context.scope_id, context.user_id)
            if not result["created"]:
                return f"今天已经签到，连续签到 {result['streak']} 天，获得 {result['points']} 分"
            return f"签到成功，连续签到 {result['streak']} 天，获得 {result['points']} 分"
        if parsed_name in {"签到状态", "我的签到"}:
            history = context.store.checkin_history(context.scope_id, context.user_id, 1)
            if not history:
                return "还没有签到记录"
            row = history[0]
            return f"最近签到：{row['day']}\n连续签到：{row['streak']} 天\n本次积分：{row['points']}"
        if parsed_name in {"排行榜", "积分排行"}:
            ranking = context.store.points_ranking(context.scope_id)
            if not ranking:
                return "暂无积分记录"
            lines = ["积分排行"]
            lines.extend(f"{index}. {user_id}：{points} 分" for index, (user_id, points) in enumerate(ranking, 1))
            return "\n".join(lines)
        if parsed_name in {"群统计", "群数据"}:
            return f"群消息数：{context.store.group_message_count(context.scope_id)}"
        count = context.store.user_message_count(context.scope_id, context.user_id)
        points = sum(int(row["points"]) for row in context.store.checkin_history(context.scope_id, context.user_id, 365))
        return f"用户 openid：{context.user_id}\n发言数：{count}\n签到积分：{points}"
