from __future__ import annotations

from api import QQBotAPI, QQBotAPIError
from features.context import MessageContext, command_is


class JoinApprovalHandler:
    feature_key = "join_approval"

    def __init__(self, api: QQBotAPI) -> None:
        self.api = api

    async def handle(self, context: MessageContext) -> str | None:
        if not context.is_group:
            return None
        if command_is(context.content, "/入群申请", "/入群申请列表") is not None:
            if not context.is_operator:
                return "入群审核仅群主或管理员可用。"
            try:
                return self._format_requests(await self.api.list_join_requests(context.scope_id))
            except QQBotAPIError as exc:
                return self._api_error(exc)

        parsed = command_is(context.content, "/同意入群", "/通过入群")
        if parsed is not None:
            return await self._approve(context, parsed[0], "approve")

        parsed = command_is(context.content, "/拒绝入群", "/拒绝入群申请")
        if parsed is not None:
            return await self._approve(context, parsed[0], "decline")
        return None

    async def _approve(self, context: MessageContext, arguments: list[str], operation: str) -> str:
        if not context.is_operator:
            return "入群审核仅群主或管理员可用。"
        if len(arguments) < 2:
            verb = "同意" if operation == "approve" else "拒绝"
            return f"用法：/{verb}入群 成员OpenID 申请ID [拒绝理由]"
        member_openid, join_request_id = arguments[0], arguments[1]
        reason = " ".join(arguments[2:]) if operation == "decline" else ""
        try:
            await self.api.approve_join_request(
                context.scope_id,
                member_openid,
                operation=operation,
                join_request_id=join_request_id,
                reject_reason=reason,
            )
        except QQBotAPIError as exc:
            return self._api_error(exc)
        return "已通过入群申请。" if operation == "approve" else "已拒绝入群申请。"

    @staticmethod
    def _format_requests(data: dict) -> str:
        rows = data.get("list")
        if not isinstance(rows, list) or not rows:
            return "当前没有待处理的入群申请。"
        lines = [f"入群申请（{len(rows)} 条）"]
        for item in rows[:20]:
            if not isinstance(item, dict):
                continue
            lines.extend(
                [
                    f"昵称：{item.get('username') or '未知'}",
                    f"成员 OpenID：{item.get('member_openid') or '未知'}",
                    f"申请ID：{item.get('join_request_id') or '未知'}",
                    f"验证信息：{JoinApprovalHandler._verify_text(item.get('verify_info'))}",
                    "---",
                ]
            )
        return "\n".join(lines).rstrip("-\n")

    @staticmethod
    def _verify_text(value: object) -> str:
        if not isinstance(value, dict):
            return "无"
        message = str(value.get("verify_message") or "").strip()
        if message:
            return message
        questions = value.get("review_qa_list")
        if isinstance(questions, list) and questions:
            return "；".join(
                f"{item.get('question', '')}: {item.get('answer', '')}"
                for item in questions
                if isinstance(item, dict)
            ) or "无"
        return "无"

    @staticmethod
    def _api_error(error: QQBotAPIError) -> str:
        if "11253" in str(error):
            return "QQ 官方返回 11253：当前机器人未获入群审核接口权限/白名单，不是授权卡或指令错误。更换个人 QQ 账号不能绕过限制，请在 QQ 机器人运营后台申请权限。"
        return f"官方入群审核接口执行失败：{str(error)[:180]}"
