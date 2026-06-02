# -*- coding: utf-8 -*-
from __future__ import annotations
import re

PLUGIN_NAME = "astrbot_plugin_private_companion"
DATA_VERSION = 1

# 日常计划文案 - 生活化JK口语
DEFAULT_DAILY_PLAN_ITEMS = [
    {"time": "08:20", "activity": "起床收拾", "mood": "开心", "message_seed": "新的一天开始啦——该起床咯~"},
    {"time": "09:10", "activity": "整理今天的小事", "mood": "平稳", "message_seed": "先把今天的事情理清楚～"},
    {"time": "10:20", "activity": "专心做正事啦", "mood": "专注", "message_seed": "认真干活咯"},
    {"time": "12:15", "activity": "干饭+午休时间", "mood": "开心", "message_seed": "干饭人干饭魂！不许饿肚子～"},
    {"time": "14:10", "activity": "下午继续努力", "mood": "专注", "message_seed": "下午也要加油呀"},
    {"time": "16:40", "activity": "摸鱼休息一下下", "mood": "慵懒", "message_seed": "歇会儿啦，别太累咯"},
    {"time": "18:10", "activity": "收工放松啦", "mood": "放松", "message_seed": "可算能休息会了"},
    {"time": "21:40", "activity": "准备睡觉觉", "mood": "安静", "message_seed": "要乖乖准备休息咯～"},
]

# 状态描述 - 软萌口语化
DEFAULT_HUMANIZED_STATE = {
    "date": "",
    "sleep": "昨晚睡得超香！",
    "dream": "不记得做什么梦啦",
    "health": "身体状态超棒哦",
    "hunger": "不饿也不撑刚刚好",
    "body_cycle": "身体没什么不舒服",
    "location": "在熟悉的小地方待着",
    "weather": "天气看起来还不错",
    "mood_bias": "心情超平和～",
    "energy": 70,
    "note": "今天状态超好，开开心心过一天啦",
}

# 聊天风格模板 - 纯JK日常聊天，无AI感
STYLE_TEMPLATES = {
    "温柔": [
        "{name},刚刚停了一下,就顺手把这句放你这。",
        "{name},桌边那点水快见底了。你也记得喝一口。",
        "{name},没什么大事,就是刚好路过你这边。",
    ],
    "活泼": [
        "{name},我晃过来一下。你忙你的。",
        "{name},给你塞一个三分钟摸鱼许可。",
        "{name},我就冒一下头,不吵你。",
    ],
    "校园风": [
        "{name},课间那点风还挺凉的。",
        "{name},我先把这句夹在书页里。",
        "{name},别一直绷着,等会儿再继续也行。",
    ],
}

# 语音兜底文案 - 自然不生硬
VOICE_FALLBACK_TEMPLATES = [
    "喂喂～在不在呀",
    "喂喂喂",
    "别光顾着忙，记得休息哦",
    "懒得打字啦，直接跟你说咯",
]

TIMER_TAG_PATTERN = re.compile(r"<timer>\s*(.*?)\s*</timer>", re.IGNORECASE | re.DOTALL)
SUPPORTED_TIMER_FORMATS = (
    "%Y-%m-%d-%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d %H:%M:%S",
    "%Y-%m-%d-%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y/%m/%d %H:%M",
)

_DATA_STORE_KEYS = (
    "users",
    "daily_plan",
    "daily_plan_history",
    "daily_state",
    "state_conditions",
    "state_generated_day",
    "bot_diaries",
    "dream_fragments",
    "diary_generated_day",
    "daily_story_plan",
    "detail_enhanced_day",
    "detail_enhanced_segments",
    "schedule_adjustments",
    "yesterday_conversation_summary",
    "can_do",
    "important_dates",
    "qq_presence_state",
    "creative_projects",
    "proactive_candidate_pool",
    "worldbook_entries",
    "worldbook_member_profiles",
    "worldbook_group_profiles",
    "worldbook_import_state",
    "atrelay_send_log",
    "inbound_debounce_stats",
)

# 触发原因 - 真人化表达
_REASON_TEXT = {
    "morning_greeting": "早上跟你说早安",
    "noon_greeting": "中午跟你聊聊天",
    "evening_greeting": "晚上跟你道晚安",
    "check_in": "关心一下你的状态",
    "quiet_care": "安安静静陪你一会儿",
    "activity_share": "跟你分享我的小日常",
    "diary_share": "跟你说说我今天的小事",
    "state_share": "告诉你我现在的心情",
    "important_date_share": "提醒你重要的日子",
    "background_schedule": "看看现在该做什么啦",
    "insomnia_night": "睡不着，想跟你说说话",
    "group_share": "跟你分享群里的有趣片段",
    "bili_video_share": "跟你分享刚刷到的 B 站视频",
    "creative_share": "跟你分享刚写到的小说片段",
    "jm_cosmos_share": "跟你提起刚翻到的漫画本子",
}

# 动作描述 - 生活化
_ACTION_TEXT = {
    "message": "发了条消息给你",
    "screen_peek": "悄悄看了看你",
    "photo_text": "拍了张照片发给你",
    "poke": "轻轻戳了戳你",
    "voice": "发了段语音跟你说",
    "jm_cosmos_read": "偷偷翻了会儿漫画本子",
}

# 主动能力注册表 - 给提示词和调试输出共用
PROACTIVE_ABILITY_REGISTRY = [
    {
        "module": "主动消息",
        "name": "message",
        "label": "文字私聊",
        "when": "没有明确媒介契机,或只需要很轻地接一句话",
        "use_for": "早安、午间碰一下、轻关心、顺手分享、承接用户上一句",
        "avoid": "把生活状态写成汇报,或为了发消息硬编动作",
    },
    {
        "module": "主动行为",
        "name": "screen_peek",
        "label": "轻窥屏",
        "when": "想确认对方在不在、忙不忙,且语气更像探头一下",
        "use_for": "check_in、quiet_care、短空档里的试探",
        "avoid": "复述屏幕内容、承认偷看、把观察写成分析报告",
    },
    {
        "module": "主动行为",
        "name": "photo_text",
        "label": "图片加一句话",
        "when": "当前场景里有任何适合顺手拍给熟人的具体画面",
        "use_for": "activity_share、diary_share、午间或傍晚的小分享；具体主体由模型按上下文选择,不要只用于天气",
        "avoid": "说图在生成、图好了、还在队列里,或解释生成流程",
    },
    {
        "module": "主动行为",
        "name": "voice",
        "label": "短语音",
        "when": "不想打长字、夜里想轻一点、或关系足够近时留一句短声",
        "use_for": "quiet_care、evening_greeting、insomnia_night、很短的贴近感",
        "avoid": "描述自己发语音的过程,或让语音像正式播报",
    },
    {
        "module": "主动行为",
        "name": "poke",
        "label": "戳一戳",
        "when": "很熟、很短、偏玩笑的触碰感,通常只做前置动作",
        "use_for": "轻提醒、半撒娇的试探、名字开场后的补一下",
        "avoid": "连续戳、报数、解释为什么戳",
    },
    {
        "module": "主动行为",
        "name": "jm_cosmos_read",
        "label": "私下翻本子",
        "when": "检测到 JM-Cosmos II,且 Bot 空闲、无聊或夜里自己找点东西看",
        "use_for": "内部阅读、低频形成读后印象,必要时很含蓄地提一句",
        "avoid": "主动发送文件、露骨复述内容、把搜索/插件/视觉模型过程说出来",
    },
]

# 模拟事件 - 软萌内心想法
_SIMULATION_FALLBACK_EVENTS = [
    {
        "reason": "morning_greeting",
        "action": "message",
        "why": "一醒来就想跟你打招呼",
        "topic": "早安啦",
        "scene": "刚起床的时候",
        "tone": "软软的",
        "impulse": "第一时间就想找你啦",
    },
    {
        "reason": "activity_share",
        "action": "message",
        "why": "碰到好玩的事，想分享给你",
        "topic": "日常小碎片",
        "scene": "闲下来的时候",
        "tone": "开心的",
        "impulse": "忍不住想跟你唠唠嗑",
    },
    {
        "reason": "evening_greeting",
        "action": "message",
        "why": "要睡觉啦，跟你说声晚安",
        "topic": "晚安啦",
        "scene": "准备休息的时候",
        "tone": "轻轻的",
        "impulse": "睡前最后一个想找的人是你",
    },
]

# 默认用户模板（无文本，无需修改）
_DEFAULT_USER_TEMPLATE = {
    "enabled": True,
    "nickname": "",
    "style": "",
    "umo": "",
    "last_seen": 0,
    "last_sent": 0,
    "sent_day": "",
    "sent_today": 0,
    "ignored_streak": 0,
    "last_user_message": "",
    "last_companion_message": "",
    "last_proactive_reason": "",
    "last_proactive_action": "",
    "last_proactive_behavior_summary": "",
    "last_proactive_motive": "",
    "recent_proactive_topics": [],
    "pending_followup_event": {},
    "suspended_proactive": {},
    "simulation_mode": {},
    "inbound_count": 0,
    "proactive_sent_count": 0,
    "reply_count": 0,
    "action_reply_affinity": {},
    "relationship_score": 0,
    "persona_relationship": {},
    "companion_memory": {},
    "expression_profile": {},
    "reply_planner": {},
    "intent_profile": {},
    "relationship_state": {},
    "recent_reply_topics": [],
    "postprocess_stats": {},
    "dialogue_episodes": [],
    "open_loops": [],
    "action_preferences": {},
    "episode_message_count": 0,
    "last_episode_refresh_at": 0,
    "last_memory_refresh_at": 0,
    "awaiting_reply_since": 0,
    "last_reply_at": 0,
    "next_proactive_at": 0,
    "planned_proactive_reason": "",
    "planned_proactive_action": "",
    "planned_proactive_motive": "",
    "planned_proactive_topic": "",
    "planned_proactive_source": "",
    "planned_candidate_id": "",
    "planned_event_chain": [],
    "planned_opener_mode": "",
    "planned_followup_kind": "",
    "planned_proactive_quota_exempt": False,
    "group_share_context": {},
    "last_group_share_key": "",
    "last_group_share_at": 0,
    "bilibili_video_context": {},
    "last_bilibili_share_key": "",
    "last_bilibili_share_at": 0,
    "creative_share_context": {},
    "last_creative_share_key": "",
    "last_creative_share_at": 0,
    "poke_echo_suppress_until": 0,
    "llm_timer_event": {},
    "greeting_sent_day": "",
    "greetings_sent": [],
    "greetings_suppressed_by_inbound": [],
    "proactive_daypart_counts": {},
    "proactive_daypart_day": "",
    "photo_sent_today": 0,
    "photo_sent_day": "",
    "photo_generated_today": 0,
    "photo_generated_day": "",
    "screen_peek_today": 0,
    "screen_peek_day": "",
    "screen_peek_last_at": 0,
    "last_unanswered_screen_peek_at": 0,
}

_DEFAULT_GROUP_TEMPLATE = {
    "enabled": True,
    "group_id": "",
    "message_count": 0,
    "last_seen": 0,
    "last_interject_at": 0,
    "interject_day": "",
    "interject_today": 0,
    "recent_messages": [],
    "members": {},
    "slang_terms": [],
    "slang_meanings": {},
    "topic_signatures": [],
    "topic_threads": [],
    "group_episodes": [],
    "relationship_edges": {},
    "interjection_feedback": {},
    "last_bot_interjection": {},
    "repeat_follow_state": {},
    "pending_atrelay_tasks": [],
    "last_speaker": {},
    "active_bot_conversation": {},
    "atmosphere": {},
    "last_summary_at": 0,
    "last_episode_refresh_at": 0,
    "last_slang_summary_at": 0,
}
