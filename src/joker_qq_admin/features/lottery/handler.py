from __future__ import annotations

import random

from ..context import MessageContext, parse_command


class LotteryHandler:
    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, arguments, argument_text = parsed
        if name in {"发起抽奖", "开始抽奖"}:
            if not argument_text:
                return "用法：/发起抽奖 奖品 [人数]"
            winner_count = 1
            title = argument_text
            if arguments and arguments[-1].isdigit() and len(arguments) > 1:
                winner_count = int(arguments[-1])
                title = " ".join(arguments[:-1])
            lottery_id = context.store.create_lottery(context.scope_id, title, winner_count)
            return f"抽奖已开始：{title}\n编号：{lottery_id}\n发送 /参与抽奖 加入"
        if name in {"参与抽奖", "报名抽奖"}:
            lottery = context.store.open_lottery(context.scope_id)
            if lottery is None:
                return "当前没有进行中的抽奖"
            added = context.store.add_lottery_entry(int(lottery["lottery_id"]), context.user_id, context.user_id)
            return "已加入抽奖" if added else "你已经参加过这个抽奖"
        if name in {"开奖", "抽奖结果"}:
            lottery = context.store.open_lottery(context.scope_id)
            if lottery is None:
                return "当前没有进行中的抽奖"
            entries = context.store.lottery_entries(int(lottery["lottery_id"]))
            if not entries:
                return "还没有人参加抽奖"
            winners = random.sample(entries, min(int(lottery["winner_count"]), len(entries)))
            context.store.draw_lottery(int(lottery["lottery_id"]))
            return f"抽奖结果：{lottery['title']}\n中奖：" + "、".join(display for _, display in winners)
        if name in {"抽奖状态", "当前抽奖"}:
            lottery = context.store.open_lottery(context.scope_id)
            if lottery is None:
                return "当前没有进行中的抽奖"
            count = len(context.store.lottery_entries(int(lottery["lottery_id"])))
            return f"进行中：{lottery['title']}\n已报名：{count} 人\n发送 /参与抽奖 加入"
        return None
