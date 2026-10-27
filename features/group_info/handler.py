from __future__ import annotations

from api import QQBotAPI, QQBotAPIError
from features.context import MessageContext, command_is


class GroupInfoHandler:
    feature_key = "group_info"

    def __init__(self, api: QQBotAPI) -> None:
        self.api = api

    async def handle(self, context: MessageContext) -> str | None:
        if not context.is_group:
            return None
        if command_is(context.content, "/群信息", "/群资料") is not None:
            try:
                return self._format_info(await self.api.get_group_info(context.scope_id))
            except QQBotAPIError as exc:
                return self._api_error(exc)
        if command_is(context.content, "/机器人群状态", "/群内状态") is not None:
            try:
                return self._format_state(await self.api.get_group_bot_state(context.scope_id))
            except QQBotAPIError as exc:
                return self._api_error(exc)
        return None

    @staticmethod
    def _format_info(data: dict) -> str:
        tags = data.get("group_tags")
        tags_text = "、".join(str(item) for item in tags if str(item).strip()) if isinstance(tags, list) else ""
        return "\n".join(
            [
                f"群名称：{data.get('group_name') or '未知'}",
                f"群 OpenID：{data.get('group_openid') or '未知'}",
                f"群简介：{data.get('group_finger_memo') or '未设置'}",
                f"群分类：{data.get('group_class_text') or '未设置'}",
                f"群标签：{tags_text or '未设置'}",
                f"群成员数：{data.get('group_member_num', '未知')}",
            ]
        )

    @staticmethod
    def _format_state(data: dict) -> str:
        proactive = data.get("allow_proactive_msg")
        proactive_text = "是" if proactive is True else "否" if proactive is False else "未知"
        return "\n".join(
            [
                f"机器人 OpenID：{data.get('member_openid') or '未知'}",
                f"群内角色：{data.get('member_role') or '未知'}",
                f"入群时间：{data.get('joined_at') or '未知'}",
                f"主动推送：{proactive_text}",
                f"接收消息：{data.get('recv_msg_setting') or '未知'}",
            ]
        )

    @staticmethod
    def _api_error(error: QQBotAPIError) -> str:
        if "11253" in str(error):
            return "QQ 官方返回 11253：当前机器人未获官方群信息接口权限/白名单，不是授权卡或指令错误。请在 QQ 机器人运营后台申请该接口权限。"
        return f"官方群信息接口执行失败：{str(error)[:180]}"
