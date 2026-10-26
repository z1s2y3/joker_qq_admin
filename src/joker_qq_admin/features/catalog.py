from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


FeatureStatus = Literal["implemented", "migrate", "limited", "blocked", "infrastructure"]


@dataclass(frozen=True, slots=True)
class FeatureSpec:
    key: str
    label: str
    folder: str
    status: FeatureStatus
    official_api: str
    note: str


FEATURES: tuple[FeatureSpec, ...] = (
    FeatureSpec("basic_commands", "基础指令", "basic_commands", "implemented", "群消息、C2C 消息", "当前项目已实现 ping、状态和帮助。"),
    FeatureSpec("identity", "身份映射", "identity", "implemented", "group_openid、user_openid", "显示官方 openid，替代旧版数字群号和 QQ 号绑定。"),
    FeatureSpec("scum_query", "SCUM 查询", "scum_query", "implemented", "文本消息 + SCUM 中转", "支持绑定服务器、在线查询和关键词查询。"),
    FeatureSpec("statistics", "签到统计", "statistics", "implemented", "文本消息 + SQLite", "支持签到、积分、排行和群统计。"),
    FeatureSpec("auto_reply", "自动回复", "auto_reply", "implemented", "群消息事件 + SQLite", "支持添加、删除、查看和开关回复。"),
    FeatureSpec("lottery", "抽奖", "lottery", "implemented", "群消息事件 + SQLite", "支持发起、报名、开奖和状态查询。"),
    FeatureSpec("entertainment", "娱乐", "entertainment", "implemented", "群消息事件", "支持骰子、猜拳、随机选择和时间。"),
    FeatureSpec("music", "音乐", "music", "limited", "消息 API + 媒体消息", "保留指令入口，未配置媒体服务时明确提示。"),
    FeatureSpec("text_to_image", "文转图", "text_to_image", "limited", "媒体消息", "保留指令入口，需另配图片上传服务。"),
    FeatureSpec("game_commands", "游戏指令", "game_commands", "limited", "外部执行桥", "通过 JOKER_GAME_BRIDGE_URL 对接现有游戏执行端。"),
    FeatureSpec("blacklist", "黑名单", "blacklist", "implemented", "消息事件 + SQLite", "支持黑名单数据维护，自动踢出仍取决于官方群管权限。"),
    FeatureSpec("moderation", "群管理", "moderation", "blocked", "官方群管理 API", "当前实例未配置可确认的禁言、踢出、撤回、称号和点赞接口。"),
    FeatureSpec("welcome", "入群欢迎", "welcome", "blocked", "官方事件权限", "官方文档当前不保证入群欢迎语能力。"),
    FeatureSpec("scheduled_messages", "定时消息", "scheduled_messages", "blocked", "主动消息策略", "官方机器人不能按 NapCat 方式无事件定时发送，因此不启用。"),
)


FEATURES_BY_KEY = {feature.key: feature for feature in FEATURES}


def features_by_status(status: FeatureStatus) -> tuple[FeatureSpec, ...]:
    return tuple(feature for feature in FEATURES if feature.status == status)

