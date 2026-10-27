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
    FeatureSpec("user_replies", "用户专属回复", "auto_reply", "implemented", "群消息事件 + SQLite", "按群和用户保存独立的关键词回复。"),
    FeatureSpec("lottery", "抽奖", "lottery", "implemented", "群消息事件 + SQLite", "支持发起、报名、开奖和状态查询。"),
    FeatureSpec("entertainment", "娱乐", "entertainment", "implemented", "群消息事件", "支持骰子、猜拳、随机选择和时间。"),
    FeatureSpec("blacklist", "黑名单", "blacklist", "implemented", "群黑名单 API + SQLite", "支持加入、移出、查询和清空黑名单，并保留黑名单记录。"),
    FeatureSpec("moderation", "群管理", "moderation", "implemented", "官方群管理 API", "支持禁言、解禁、踢出、撤回、成员查询和禁言状态。"),
    FeatureSpec("keyword_mute", "关键词禁言", "keyword_mute", "implemented", "群消息事件 + 禁言 API", "命中独立关键词规则后禁言发言成员。"),
    FeatureSpec("keyword_kick", "关键词踢出", "keyword_kick", "implemented", "群消息事件 + 移除成员 API", "命中独立关键词规则后移出发言成员。"),
    FeatureSpec("keyword_blacklist", "关键词黑名单", "keyword_blacklist", "implemented", "群消息事件 + 黑名单 API", "命中独立关键词规则后移出并加入官方黑名单。"),
    FeatureSpec("group_info", "群信息", "group_info", "limited", "获取群基本信息、机器人群内状态", "官方接口存在白名单限制；有权限时支持群资料和机器人接收消息状态查询。"),
    FeatureSpec("join_approval", "入群审核", "join_approval", "limited", "入群申请、入群审批、自动审批策略", "支持拉取申请、通过、拒绝和策略管理；是否可用由官方账号权限决定。"),
    FeatureSpec("group_admins", "分群管理员", "group_admins", "implemented", "官方 openid + SQLite", "每个群独立维护分管管理员。"),
    FeatureSpec("message_records", "群消息记录", "message_records", "implemented", "群消息事件 + SQLite", "按群保存收到的文字消息，可在网页查看。"),
    FeatureSpec("scheduled_messages", "定时任务", "scheduled_messages", "implemented", "官方群消息 API + SQLite", "按群创建一次性播报、全体禁言、全体解禁或点歌搜索任务。"),
    FeatureSpec("song_request", "点歌", "song_request", "implemented", "官方群消息 + 音乐搜索链接", "支持 /点歌 歌曲名，并返回可打开的歌曲搜索链接。"),
    FeatureSpec("group_settings", "群设置", "dashboard", "implemented", "网页控制台 + SQLite", "每个群独立设置功能开关、自动回复、SCUM 和消息记录。"),
)


FEATURES_BY_KEY = {feature.key: feature for feature in FEATURES}


def features_by_status(status: FeatureStatus) -> tuple[FeatureSpec, ...]:
    return tuple(feature for feature in FEATURES if feature.status == status)

