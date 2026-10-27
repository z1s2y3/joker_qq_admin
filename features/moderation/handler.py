from __future__ import annotations

from datetime import datetime, timedelta, timezone
import re

from api import QQBotAPI, QQBotAPIError
from features.context import MessageContext, parse_command


_MENTION_PATTERN = re.compile(r"^<@!?([^>]+)>$")


class ModerationHandler:
    def __init__(self, api: QQBotAPI) -> None:
        self.api = api

    async def handle(self, context: MessageContext) -> str | None:
        parsed = parse_command(context.content)
        if parsed is None:
            return None
        name, arguments, _ = parsed

        if not context.is_group:
            return None
        if name not in {
            "禁言",
            "解禁",
            "全体禁言",
            "全体解禁",
            "踢出",
            "撤回",
            "撤回用户",
            "群禁言状态",
            "全体禁言状态",
            "群成员",
            "成员信息",
        }:
            return None
        if not context.is_operator:
            return "群管命令仅群主或管理员可用。"

        try:
            if name == "禁言":
                return await self._mute(context, arguments)
            if name == "解禁":
                return await self._unmute(context, arguments)
            if name == "全体禁言":
                return await self._mute_all(context, arguments)
            if name == "全体解禁":
                return await self._unmute_all(context)
            if name == "踢出":
                return await self._remove(context, arguments)
            if name == "撤回":
                return await self._retract(context, arguments)
            if name == "撤回用户":
                return await self._retract_user(context, arguments)
            if name in {"群禁言状态", "全体禁言状态"}:
                return await self._mute_state(context)
            if name == "群成员":
                return await self._members(context, arguments)
            if name == "成员信息":
                return await self._member_info(context, arguments)
        except QQBotAPIError as exc:
            return self._api_error(exc)
        return None

    async def _mute(self, context: MessageContext, arguments: list[str]) -> str:
        target, remaining = self._target(context, arguments)
        if not target:
            return "用法：/禁言 @成员 秒数"
        target = await self._resolve_target(context, target)
        seconds = 600
        for item in remaining:
            if item.isdigit():
                seconds = int(item)
                break
        if not 1 <= seconds <= 2_592_000:
            return "禁言时长需为 1 到 2592000 秒。"
        expire_at = (
            datetime.now(timezone.utc) + timedelta(seconds=seconds)
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        await self.api.set_group_member_mute(
            context.scope_id,
            target,
            operation="add",
            mute_expire_at=expire_at,
        )
        return f"已禁言 {await self._member_label(context, target)}，时长 {seconds} 秒。"

    async def _unmute(self, context: MessageContext, arguments: list[str]) -> str:
        target, _ = self._target(context, arguments)
        if not target:
            return "用法：/解禁 @成员"
        target = await self._resolve_target(context, target)
        await self.api.set_group_member_mute(
            context.scope_id,
            target,
            operation="del",
        )
        return f"已解除禁言：{await self._member_label(context, target)}"

    async def _mute_all(self, context: MessageContext, arguments: list[str]) -> str:
        seconds = 600
        for item in arguments:
            if item.isdigit():
                seconds = int(item)
                break
        if not 1 <= seconds <= 2_592_000:
            return "全体禁言时长需为 1 到 2592000 秒。"
        member_openids = await self._ordinary_members(context.scope_id)
        if not member_openids:
            return "未获取到可执行的普通群成员。"
        expire_at = (
            datetime.now(timezone.utc) + timedelta(seconds=seconds)
        ).isoformat(timespec="seconds").replace("+00:00", "Z")
        failed = 0
        for start in range(0, len(member_openids), 20):
            result = await self.api.set_group_members_mute(
                context.scope_id,
                member_openids[start:start + 20],
                operation="add",
                mute_expire_at=expire_at,
            )
            if isinstance(result, dict):
                failed += len(result.get("fail_openids") or [])
        message = f"已对 {len(member_openids) - failed} 名普通成员执行全体禁言，时长 {seconds} 秒。"
        return message + (f"失败 {failed} 人。" if failed else "")

    async def _unmute_all(self, context: MessageContext) -> str:
        member_openids = await self._ordinary_members(context.scope_id)
        if not member_openids:
            return "未获取到可执行的普通群成员。"
        failed = 0
        for start in range(0, len(member_openids), 20):
            result = await self.api.set_group_members_mute(
                context.scope_id,
                member_openids[start:start + 20],
                operation="del",
            )
            if isinstance(result, dict):
                failed += len(result.get("fail_openids") or [])
        message = f"已对 {len(member_openids) - failed} 名普通成员执行全体解禁。"
        return message + (f"失败 {failed} 人。" if failed else "")

    async def _ordinary_members(self, scope_id: str) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        cursor = ""
        for _ in range(50):
            data = await self.api.get_group_members(scope_id, cursor=cursor)
            members = data.get("members") if isinstance(data, dict) else []
            if not isinstance(members, list):
                break
            for member in members:
                if not isinstance(member, dict):
                    continue
                member_openid = str(member.get("member_openid") or member.get("user_openid") or "").strip()
                role = str(member.get("member_role") or "member").casefold()
                if not member_openid or member_openid in seen or role in {"owner", "admin", "administrator", "bot"}:
                    continue
                if bool(member.get("bot") or member.get("is_bot")):
                    continue
                seen.add(member_openid)
                result.append(member_openid)
            next_cursor = str(data.get("next_cursor", "") or "").strip()
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return result

    async def _remove(self, context: MessageContext, arguments: list[str]) -> str:
        target, remaining = self._target(context, arguments)
        if not target:
            return "用法：/踢出 @成员 [拉黑]"
        target = await self._resolve_target(context, target)
        label = await self._member_label(context, target)
        add_to_blacklist = any(
            item.casefold() in {"拉黑", "黑名单"} for item in remaining
        )
        if add_to_blacklist:
            await self.api.remove_group_members(
                context.scope_id,
                [target],
            )
            result = await self.api.update_group_blacklist(
                context.scope_id,
                operation="add",
                member_openids=[target],
            )
            failed = result.get("fail_openids") if isinstance(result, dict) else None
            if isinstance(failed, list) and target in {str(item) for item in failed}:
                return "已移出群聊，但未能加入官方群黑名单"
            context.store.add_blacklist(context.scope_id, target, "群内群管命令")
        else:
            await self.api.remove_group_members(context.scope_id, [target])
        suffix = "并加入黑名单" if add_to_blacklist else ""
        return f"已移出群聊：{label}{suffix}"

    async def _retract(self, context: MessageContext, arguments: list[str]) -> str:
        if not arguments:
            return "用法：/撤回 消息ID\n官方接口只能撤回机器人自己发送且不超过 2 分钟的消息。"
        await self.api.delete_group_message(context.scope_id, arguments[0])
        return "已撤回机器人消息。"

    async def _retract_user(self, context: MessageContext, arguments: list[str]) -> str:
        target, remaining = self._target(context, arguments)
        if not target:
            return "用法：/撤回用户 @成员 [条数]"
        limit = 20
        for item in remaining:
            if item.isdigit():
                limit = max(1, min(int(item), 100))
                break
        records = context.store.list_user_message_records(context.scope_id, target, limit)
        if not records:
            return "没有找到该成员近 2 分钟内可撤回的消息。"
        recalled = 0
        expired = 0
        failures: list[str] = []
        now = datetime.now(timezone.utc)
        for record in records:
            try:
                created = datetime.fromisoformat(str(record.get("created_at", "")).replace("Z", "+00:00"))
                if created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
            except ValueError:
                expired += 1
                continue
            if (now - created).total_seconds() > 120:
                expired += 1
                continue
            try:
                await self.api.delete_group_message(context.scope_id, record["message_id"])
                context.store.mark_message_recalled(context.scope_id, record["message_id"])
                recalled += 1
            except QQBotAPIError as exc:
                failures.append(str(exc))
        if not recalled and failures:
            if any("11253" in detail for detail in failures):
                return self._api_error(QQBotAPIError(failures[0]))
            return "撤回失败：" + failures[0][:180]
        message = f"已撤回该成员 {recalled} 条消息。"
        if expired:
            message += f"超时跳过 {expired} 条。"
        if failures:
            message += f"失败 {len(failures)} 条。"
        return message

    async def _mute_state(self, context: MessageContext) -> str:
        data = await self.api.get_group_mute_state(context.scope_id)
        global_rule = data.get("global_rule")
        members = data.get("members")
        members = members if isinstance(members, list) else []
        mode = ""
        if isinstance(global_rule, dict):
            mode = str(global_rule.get("mode", "") or "").strip()
        lines = [f"全员禁言：{mode or 'none'}", f"成员禁言：{len(members)} 人"]
        for member in members[:20]:
            if not isinstance(member, dict):
                continue
            label = str(member.get("username") or "成员").strip()
            expire_at = str(member.get("mute_expire_at", "") or "").strip()
            if label:
                lines.append(f"{label}：{expire_at}" if expire_at else label)
        return "\n".join(lines)

    async def _members(self, context: MessageContext, arguments: list[str]) -> str:
        cursor = arguments[0] if arguments else ""
        data = await self.api.get_group_members(context.scope_id, cursor=cursor)
        members = data.get("members")
        members = members if isinstance(members, list) else []
        if not members:
            return "没有返回群成员，或该接口尚未向此机器人开放。"
        lines = [f"群成员（本页 {len(members)} 人）"]
        for member in members[:30]:
            if not isinstance(member, dict):
                continue
            label = str(member.get("username") or "未命名成员").strip()
            role = str(member.get("member_role", "") or "").strip()
            lines.append(f"{label}（{role}）" if role else label)
        next_cursor = str(data.get("next_cursor", "") or "").strip()
        if next_cursor:
            lines.append(f"下一页：/群成员 {next_cursor}")
        return "\n".join(lines)

    async def _member_info(self, context: MessageContext, arguments: list[str]) -> str:
        target, _ = self._target(context, arguments)
        if not target:
            return "用法：/成员信息 @成员"
        data = await self.api.get_group_member(context.scope_id, target)
        username = str(data.get("username") or "成员").strip()
        role = str(data.get("member_role", "") or "").strip()
        return f"成员：{username}\n身份：{role or 'member'}"

    async def _resolve_target(self, context: MessageContext, target: str) -> str:
        candidate = str(target or "").strip()
        if not candidate.isdigit():
            return candidate
        cursor = ""
        for _ in range(50):
            data = await self.api.get_group_members(context.scope_id, cursor=cursor)
            rows = data.get("members") if isinstance(data, dict) else []
            for item in rows if isinstance(rows, list) else []:
                if not isinstance(item, dict):
                    continue
                member_openid = str(
                    item.get("member_openid") or item.get("user_openid") or item.get("openid") or ""
                ).strip()
                known_numbers = {
                    str(item.get(key, "")).strip()
                    for key in ("qq", "qq_number", "user_id", "member_id", "uin")
                    if str(item.get(key, "")).strip()
                }
                if member_openid and candidate in known_numbers:
                    return member_openid
            next_cursor = str(data.get("next_cursor", "") or "").strip()
            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return candidate

    async def _member_label(self, context: MessageContext, member_openid: str) -> str:
        try:
            data = await self.api.get_group_member(context.scope_id, member_openid)
        except QQBotAPIError:
            return member_openid
        username = str(data.get("username") or data.get("nick") or data.get("nickname") or "").strip()
        return username or member_openid

    @staticmethod
    def _target(
        context: MessageContext,
        arguments: list[str],
    ) -> tuple[str, list[str]]:
        for mention in context.mentions:
            if not isinstance(mention, dict):
                continue
            target = str(
                mention.get("member_openid") or mention.get("user_openid") or mention.get("id") or ""
            ).strip()
            if target:
                return target, [item for item in arguments if item not in {"@", target}]

        if not arguments:
            return "", []
        first = arguments[0].strip()
        matched = _MENTION_PATTERN.fullmatch(first)
        target = matched.group(1).strip() if matched else first
        return target, arguments[1:]

    @staticmethod
    def _api_error(error: QQBotAPIError) -> str:
        detail = str(error)
        if "11253" in detail:
            return "QQ 官方返回 11253：当前机器人未获该群管理接口权限/白名单。更换个人 QQ 账号不能绕过该限制，请在 QQ 机器人运营后台申请对应接口权限；无法申请时应关闭该功能。"
        if "40062003" in detail or "403" in detail:
            return "操作失败：机器人需要是群管理员，且目标不能是群主、管理员或机器人。"
        if "40064004" in detail:
            return "操作失败：只能撤回机器人自己发送且不超过 2 分钟的消息。"
        return f"官方群管接口执行失败：{detail[:180]}"
