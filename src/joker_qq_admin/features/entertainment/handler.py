from __future__ import annotations

from datetime import datetime
import random

from ..context import MessageContext, parse_command


class EntertainmentHandler:
    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, arguments, argument_text = parsed
        if name in {"骰子", "摇骰子"}:
            sides = int(arguments[0]) if arguments and arguments[0].isdigit() else 6
            sides = max(2, min(sides, 100))
            return f"🎲 d{sides}：{random.randint(1, sides)}"
        if name == "猜拳":
            choices = ("石头", "剪刀", "布")
            return f"你出什么我不知道，机器人出：{random.choice(choices)}"
        if name in {"随机", "随机选择"}:
            if not arguments:
                return "用法：/随机 选项1 选项2 ..."
            return f"随机结果：{random.choice(arguments)}"
        if name in {"当前时间", "时间"}:
            return datetime.now().astimezone().strftime("当前时间：%Y-%m-%d %H:%M:%S")
        if name in {"小游戏", "娱乐帮助", "娱乐"}:
            return "/骰子 [面数]\n/猜拳\n/随机 选项1 选项2\n/当前时间"
        return None
