from __future__ import annotations

import re

from api import QQBotAPI, QQBotAPIError
from features.context import MessageContext, parse_command


class BlacklistHandler:
    def __init__(self, api: QQBotAPI) -> None:
        self.api = api

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, arguments, argument_text = parsed
        if name in {"拉黑", "加入黑名单"}:
            if not arguments:
                return "用法：/拉黑 @成员 [原因]"
            if not context.is_group:
                return "黑名单命令只支持群聊"
            if not context.is_operator:
                return "群管命令仅群主或管理员可用。"
            user_id, reason = self._target(context, arguments, argument_text)
            if not user_id:
                return "用法：/拉黑 @成员 [原因]"
            try:
                await self.api.remove_group_members(
                    context.scope_id,
                    [user_id],
                )
                result = await self.api.update_group_blacklist(
                    context.scope_id,
                    operation="add",
                    member_openids=[user_id],
                )
            except QQBotAPIError as exc:
                return self._api_error(exc)
            failed = self._failed_ids(result)
            if failed:
                return f"已移出群聊，但加入黑名单失败：{', '.join(failed)}"
            context.store.add_blacklist(context.scope_id, user_id, reason)
            return "已移出群聊并加入黑名单"
        if name in {"删黑", "移出黑名单"}:
            if not arguments:
                return "请在网页群管理后台的黑名单页面解除成员黑名单"
            if not context.is_group:
                return "黑名单命令只支持群聊"
            if not context.is_operator:
                return "群管命令仅群主或管理员可用。"
            user_id, _ = self._target(context, arguments, argument_text)
            if not user_id:
                return "用法：/删黑 @成员"
            try:
                result = await self.api.update_group_blacklist(
                    context.scope_id,
                    operation="del",
                    member_openids=[user_id],
                )
            except QQBotAPIError as exc:
                return self._api_error(exc)
            failed = self._failed_ids(result)
            if failed:
                return f"官方接口未移出：{', '.join(failed)}"
            context.store.remove_blacklist(context.scope_id, user_id)
            return "已移出黑名单"
        if name in {"查看黑名单", "黑名单"}:
            if not context.is_group:
                return "黑名单命令只支持群聊"
            try:
                rows = await self._all_blacklist_ids(context.scope_id)
            except QQBotAPIError as exc:
                return self._api_error(exc)
            if not rows:
                return "当前黑名单为空"
            return f"当前黑名单共有 {len(rows)} 名成员，请在网页群管理后台查看和解除。"
        if name == "清空黑名单":
            if not context.is_group:
                return "黑名单命令只支持群聊"
            if not context.is_operator:
                return "群管命令仅群主或管理员可用。"
            try:
                ids = await self._all_blacklist_ids(context.scope_id)
                for start in range(0, len(ids), 20):
                    await self.api.update_group_blacklist(
                        context.scope_id,
                        operation="del",
                        member_openids=ids[start : start + 20],
                    )
            except QQBotAPIError as exc:
                return self._api_error(exc)
            count = context.store.clear_blacklist(context.scope_id)
            return f"已清空黑名单，共 {len(ids) or count} 条"
        return None

    @staticmethod
    def _blacklist_ids(payload: dict) -> list[str]:
        raw = payload.get("member_openids")
        if not isinstance(raw, list):
            raw = payload.get("members")
        if not isinstance(raw, list):
            raw = payload.get("blacklist")
        if not isinstance(raw, list):
            raw = payload.get("users")
        result: list[str] = []
        for item in raw if isinstance(raw, list) else []:
            if isinstance(item, dict):
                value = item.get("member_openid") or item.get("openid") or item.get("user_openid")
            else:
                value = item
            value = str(value or "").strip()
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _target(
        context: MessageContext,
        arguments: list[str],
        argument_text: str,
    ) -> tuple[str, str]:
        for mention in context.mentions:
            if not isinstance(mention, dict):
                continue
            target = str(
                mention.get("member_openid") or mention.get("user_openid") or mention.get("id") or ""
            ).strip()
            if target:
                first = arguments[0] if arguments else ""
                reason = argument_text[len(first):].strip() if first else argument_text
                return target, reason
        if not arguments:
            return "", ""
        first = arguments[0].strip()
        matched = re.fullmatch(r"<@!?([^>]+)>", first)
        target = matched.group(1).strip() if matched else first
        return target, argument_text[len(first):].strip()

    @staticmethod
    def _failed_ids(payload: dict) -> list[str]:
        raw = payload.get("fail_openids") or payload.get("add_to_member_blacklist_fail_openids")
        return [str(item).strip() for item in raw if str(item).strip()] if isinstance(raw, list) else []

    async def _all_blacklist_ids(self, group_openid: str) -> list[str]:
        cursor = ""
        result_ids: list[str] = []
        for _ in range(100):
            payload = await self.api.get_group_blacklist(group_openid, cursor=cursor)
            for user_id in self._blacklist_ids(payload):
                if user_id not in result_ids:
                    result_ids.append(user_id)
            cursor = str(payload.get("next_cursor", "") or "").strip()
            if not cursor:
                break
        return result_ids

    @staticmethod
    def _api_error(error: QQBotAPIError) -> str:
        detail = str(error)
        if "11253" in detail:
            return "QQ 官方返回 11253：当前机器人未获群黑名单接口权限/白名单，不是授权卡或指令错误。请在 QQ 机器人运营后台申请该接口权限。"
        if "40062003" in detail or "403" in detail:
            return "操作失败：机器人需要是群管理员。"
        return f"官方黑名单接口执行失败：{detail[:180]}"
