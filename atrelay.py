# -*- coding: utf-8 -*-
"""
AtRelayMixin — 跨群/私聊转发工具的目标解析、边界和队列
"""
from __future__ import annotations

import asyncio
import base64
import gc
import hashlib
import html
import importlib
import json
import math
import os
import random
import re
import shutil
import sys
import time
import unicodedata
import uuid
import zoneinfo
from copy import deepcopy
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlparse, urlunparse
from xml.etree import ElementTree as ET

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
try:
    from astrbot.api.message_components import At, Image, Plain, Record, Reply
except ImportError:
    from astrbot.api.message_components import At, Image, Plain
    from astrbot.core.message.components import Record
    try:
        from astrbot.api.message_components import Reply
    except ImportError:
        try:
            from astrbot.core.message.components import Reply
        except ImportError:
            Reply = None
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core import file_token_service
from astrbot.core.astr_main_agent import MainAgentBuildConfig, build_main_agent
from astrbot.core.agent.message import AssistantMessageSegment, TextPart, UserMessageSegment
from astrbot.core.db.po import Conversation
from astrbot.core.platform.astrbot_message import AstrBotMessage, MessageMember
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.message_type import MessageType
from astrbot.core.platform.platform import PlatformStatus
from astrbot.core.platform.platform_metadata import PlatformMetadata
from astrbot.core.star.star_handler import EventType, star_handlers_registry
from astrbot.core.provider.entities import LLMResponse
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

try:
    import chinese_calendar as calendar_cn
except Exception:
    calendar_cn = None

try:
    from lunarcalendar import Converter, Solar
except Exception:
    Converter = None
    Solar = None

from .constants import (
    DEFAULT_DAILY_PLAN_ITEMS,
    DEFAULT_HUMANIZED_STATE,
    PLUGIN_NAME,
    DATA_VERSION,
    PROACTIVE_ABILITY_REGISTRY,
    STYLE_TEMPLATES,
    VOICE_FALLBACK_TEMPLATES,
    TIMER_TAG_PATTERN,
    SUPPORTED_TIMER_FORMATS,
    _ACTION_TEXT,
    _DATA_STORE_KEYS,
    _DEFAULT_GROUP_TEMPLATE,
    _DEFAULT_USER_TEMPLATE,
    _REASON_TEXT,
    _SIMULATION_FALLBACK_EVENTS,
)
from .dreaming import (
    build_dream_memory_fragments,
    dream_fragment_effective_weight,
    dream_theme_specs,
    extract_weighted_dream_fragments,
    fallback_diary_payload,
    fallback_dream_fragments_for_diary,
    generate_daily_diary,
    generate_enhanced_dream_pick,
    merge_dream_fragment_pool,
    normalize_dream_fragment_item,
    normalize_dream_fragment_pool,
    recent_diary_context,
    recent_diary_tags,
    weighted_unique_fragment_sample,
)
from .helpers import _date_key, _now_ts, _safe_float, _safe_int, _single_line, _strip_internal_message_blocks, _today_key
from .planning import (
    build_daily_plan_prompt,
    build_detail_enhancement_prompt,
    format_plan_for_diary,
    generate_daily_plan,
    generate_detail_enhancement,
    get_schedule_planning_prompt,
    normalize_long_term_events,
    normalize_story_items,
    normalize_story_plan,
    pick_detail_segment,
)


DEFAULT_AI_DAILY_NEWS_SOURCE = "B站 AI早报|bilibili:285286947"

DEFAULT_NEWS_SOURCES = "\n".join(
    [
        "BBC中文|https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
        "Google新闻中文|https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "Solidot|https://www.solidot.org/index.rss",
        "Hacker News|https://hnrss.org/frontpage",
        "MIT Technology Review|https://www.technologyreview.com/feed/",
        "Ars Technica|https://feeds.arstechnica.com/arstechnica/index",
        DEFAULT_AI_DAILY_NEWS_SOURCE,
    ]
)

LEGACY_DEFAULT_NEWS_SOURCES = "\n".join(
    [
        "BBC中文|https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
        "Google新闻中文|https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "Solidot|https://www.solidot.org/index.rss",
    ]
)

PREVIOUS_TECH_DEFAULT_NEWS_SOURCES = "\n".join(
    [
        "BBC中文|https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
        "Google新闻中文|https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "Solidot|https://www.solidot.org/index.rss",
        "Hacker News|https://hnrss.org/frontpage",
        "MIT Technology Review|https://www.technologyreview.com/feed/",
        "Ars Technica|https://feeds.arstechnica.com/arstechnica/index",
    ]
)



_LUNAR_MONTH_NAMES = [
    "正月",
    "二月",
    "三月",
    "四月",
    "五月",
    "六月",
    "七月",
    "八月",
    "九月",
    "十月",
    "冬月",
    "腊月",
]
_LUNAR_DAY_NAMES = [
    "初一",
    "初二",
    "初三",
    "初四",
    "初五",
    "初六",
    "初七",
    "初八",
    "初九",
    "初十",
    "十一",
    "十二",
    "十三",
    "十四",
    "十五",
    "十六",
    "十七",
    "十八",
    "十九",
    "二十",
    "廿一",
    "廿二",
    "廿三",
    "廿四",
    "廿五",
    "廿六",
    "廿七",
    "廿八",
    "廿九",
    "三十",
]
_SOLAR_TERM_DATES = {
    (1, 5): "小寒",
    (1, 20): "大寒",
    (2, 4): "立春",
    (2, 19): "雨水",
    (3, 5): "惊蛰",
    (3, 20): "春分",
    (4, 4): "清明",
    (4, 20): "谷雨",
    (5, 5): "立夏",
    (5, 21): "小满",
    (6, 5): "芒种",
    (6, 21): "夏至",
    (7, 7): "小暑",
    (7, 22): "大暑",
    (8, 7): "立秋",
    (8, 23): "处暑",
    (9, 7): "白露",
    (9, 23): "秋分",
    (10, 8): "寒露",
    (10, 23): "霜降",
    (11, 7): "立冬",
    (11, 22): "小雪",
    (12, 7): "大雪",
    (12, 22): "冬至",
}
_ALMANAC_YI = ["整理房间", "写字", "散步", "读书", "听歌", "轻度创作", "复盘", "安静休息"]
_ALMANAC_JI = ["熬夜", "冲动发言", "硬撑", "反复纠结", "过度解释", "临时加压", "情绪化决定"]
_PLATFORM_DISPLAY_NAMES = {
    "aiocqhttp": "QQ",
    "qq": "QQ",
    "onebot": "QQ",
    "telegram": "Telegram",
    "wechat": "微信",
    "discord": "Discord",
}




class AtRelayMixin:
    """跨群/私聊转发工具的目标解析、边界和队列"""

    async def _get_group_member_list_for_tool(self, event: AstrMessageEvent, group_id: str) -> list[dict[str, Any]]:
        group_id = str(group_id or "").strip()
        if not group_id:
            return []
        now = _now_ts()
        cache = getattr(self, "_atrelay_member_cache", None)
        if not isinstance(cache, dict):
            cache = {}
            self._atrelay_member_cache = cache
        cached = cache.get(group_id)
        if isinstance(cached, dict) and now - _safe_float(cached.get("ts"), 0) < self.atrelay_member_cache_minutes * 60:
            members = cached.get("items")
            if isinstance(members, list):
                return [dict(item) for item in members if isinstance(item, dict)]
        bot = getattr(event, "bot", None)
        api = getattr(bot, "api", None)
        call_action = getattr(api, "call_action", None)
        if not callable(call_action):
            return []
        raw_members = await call_action("get_group_member_list", group_id=group_id)
        members = [dict(item) for item in raw_members if isinstance(item, dict)] if isinstance(raw_members, list) else []
        cache[group_id] = {"ts": now, "items": members}
        return members

    def _format_atrelay_member(self, raw: dict[str, Any]) -> dict[str, Any]:
        user_id = str(raw.get("user_id") or "").strip()
        nickname = _single_line(raw.get("nickname"), 60)
        card = _single_line(raw.get("card"), 60)
        role = _single_line(raw.get("role"), 20) or "member"
        role_map = {"owner": "群主", "admin": "管理员", "member": "成员"}
        profile = self._worldbook_profile_by_user_id(user_id)
        if isinstance(profile, dict):
            if nickname:
                self._remember_worldbook_observed_name(user_id, nickname)
            if card:
                self._remember_worldbook_observed_name(user_id, card)
        return {
            "user_id": user_id,
            "nickname": nickname,
            "group_card": card or "",
            "role": role_map.get(role, role or "成员"),
            "relation_name": _single_line(profile.get("name"), 60) if isinstance(profile, dict) else "",
            "identity_note": _single_line(profile.get("identity_note") or profile.get("note") or profile.get("content"), 160) if isinstance(profile, dict) else "",
            "in_relation_net": bool(profile),
        }

    async def _resolve_atrelay_target_user(self, event: AstrMessageEvent, group_id: str, keyword: str) -> dict[str, Any]:
        query = _single_line(keyword, 60)
        if not query:
            return {}
        if query.isdigit():
            profile = self._worldbook_profile_by_user_id(query)
            return {
                "user_id": query,
                "name": _single_line(profile.get("name"), 60) if isinstance(profile, dict) else query,
                "source": "qq",
            }
        wb_matches = self._resolve_worldbook_member_by_name(query)
        if wb_matches:
            return wb_matches[0] if len(wb_matches) == 1 else {"ambiguous": True, "matches": wb_matches[:8], "source": "worldbook"}
        if self.atrelay_require_worldbook_first and self.enable_worldbook_member_recognition:
            return {}
        members = await self._get_group_member_list_for_tool(event, group_id)
        formatted = [self._format_atrelay_member(item) for item in members]
        hits = [
            item for item in formatted
            if query in item.get("user_id", "")
            or query in item.get("nickname", "")
            or query in item.get("group_card", "")
            or query in item.get("relation_name", "")
        ]
        if not hits:
            return {}
        if len(hits) > 1:
            return {"ambiguous": True, "matches": hits[:8], "source": "group_member_list"}
        hit = hits[0]
        return {"user_id": hit.get("user_id", ""), "name": hit.get("relation_name") or hit.get("group_card") or hit.get("nickname") or hit.get("user_id"), "source": "group_member_list"}

    def _atrelay_tool_instruction(self) -> str:
        if not (self.enabled and self.enable_atrelay_tools):
            return ""
        return """
【跨会话转述与 @ 群友工具】
当用户明确要求你“发到某个群”“告诉某个群友”“替我/帮我跟某人说一声”“帮我 @ 某人”“私聊某人”时,优先调用 `pc_relay_message`,不要在普通回复里预览要发送的完整内容。
- 统一入口：常见转述只用 `pc_relay_message`。你只需要整理 destination/group_hint/recipient_hint/message/relay_mode。
- destination 规则：发群填 `group`,私聊填 `private`,不确定填 `auto`。私聊转群、群聊转私聊、群聊转群聊都走同一个工具。
- 群聊转私聊：只发送用户明确要求转述的内容,不要附带群聊上下文、内部记忆或“群里大家说了什么”。
- 发到群并点名某人：destination=`group`,group_hint=群号/群名,recipient_hint=目标昵称或 QQ,message=要说的话；工具会自动 @ 并解析关系网/群名片。
- 私聊某人：destination=`private`,recipient_hint=QQ 或称呼；如果称呼不是 QQ,尽量提供 group_hint 以便从群成员里解析。
- 私聊询问并需要回报：用户说“帮我去私聊问问 A……”“问完告诉我”“他回了告诉我”时,调用 `pc_relay_message`，destination=`private`，并设置 `need_receipt=true`。对方下一次私聊回复后,工具会自动把回复带回当前发起会话。
- 回执二次确认：如果用户明确要求“问问能不能转回来/得到对方同意再告诉我”,或内容较私密,设置 `confirm_before_report=true`；Bot 会先问收话人是否允许把回复转回。
- 默认使用“语气转译”：不要把用户原话机械复制给对方,而是保留事实意图,按你的人格、你和说话人/收话人的关系改写成自然转述。例如“你帮我跟 A 说一下别忘了交作业”可以转成“A,刚才他说让你记得交作业,我顺手提醒一下。”
- 构造 message 时不要随意给当前发起人套外号；如果需要说明“谁让我带话”,只能使用当前发言者的固定名称、群名片或 QQ 精确身份锚点对应的名称。不要从黑话、猜测外号或相似昵称推断发起人是谁。
- 用户说“告诉 A：B / 跟 A 说 B”时,优先只把 B 转述给 A；除非用户要求说明来源,否则不要额外添加“某某让我转告你”。
- 只有用户明确要求“原话/照原话/一字不改/截图式转发”时才用原话模式,调用工具时把 `relay_mode` 填 `original`；其他情况填 `persona` 或留空。
- 对敏感、私密、带强情绪、告白/指责/吵架/金钱/密码/身体健康/秘密类内容,发送前先问用户要“原样带过去”还是“委婉一点”。工具也会二次拦截；得到用户确认后再调用,并把 `sensitive_confirmed` 设为 true。
- 普通提醒、约时间、作业/待办/到场通知等低风险内容可以直接转述。
- 转述边界：拒绝骂人、羞辱、威胁、冒充身份、宣称虚假权限/身份、索要或转交密码等请求；可以改成中性提醒,但不要替用户攻击别人。
- 延迟转述：用户说“等 A 出现/等他冒泡/他上线再说”时,仍优先用 `pc_relay_message` 并设置 `delay_until_recipient_seen=true`。
- 多目标转述：多个 QQ 用 `pc_send_to_private_users`,多个群用 `pc_send_to_groups`。不要自己循环调用单目标工具刷屏；工具会限量、去重并返回结果。
- 底层工具 `pc_send_to_group`、`pc_send_to_private_user`、`pc_get_user_id_by_name`、`pc_get_group_id_by_name`、`pc_get_specified_group_members` 只在统一入口无法表达或需要人工查询候选时使用。
- 如果出现多个同名/相似成员,不要猜,把候选姓名/QQ 简短列给用户选择。
- 私聊转群聊时,只发送用户明确要求公开的那句话；不要暴露“这是私聊里说的”、不要附带额外私聊上下文。
- 禁止泄露私聊记忆、关系网内部备注或工具参数。工具成功后只给一句简短结果：普通发送只回“消息已发送。”；需要回执只回“消息已发送，会等对方回复。”；延迟转述只回“已挂起，等对方出现再说。”不要解释“我写了什么/我怎么改写/语气如何/氛围如何”,不要复述已发送内容。
""".strip()

    def _normalize_atrelay_relay_mode(self, value: Any) -> str:
        mode = _single_line(value, 24).lower()
        if mode in {"original", "raw", "quote", "verbatim", "原话", "照原话", "原样"}:
            return "original"
        if mode in {"soft", "polite", "委婉", "缓和"}:
            return "soft"
        if mode in {"persona", "rewrite", "natural", "转译", "改写"}:
            return "persona"
        configured = _single_line(getattr(self, "atrelay_default_relay_style", "persona"), 24).lower()
        if configured in {"original", "soft", "persona"}:
            return configured
        return "persona"

    def _atrelay_sensitive_reason(self, text: str) -> str:
        cleaned = _single_line(text, 800)
        if not cleaned:
            return ""
        rules = [
            ("私密内容", ("秘密", "私下说", "私下聊", "私密", "隐私", "别告诉", "不要告诉", "只告诉你", "密码", "口令", "账号")),
            ("强情绪内容", ("讨厌", "恨", "烦死", "恶心", "滚", "闭嘴", "傻逼", "废物", "垃圾", "绝交", "再也不")),
            ("关系或告白内容", ("喜欢你", "爱你", "暗恋", "告白", "表白", "分手", "复合", "吃醋", "想你")),
            ("金钱或求助内容", ("借钱", "还钱", "转账", "红包", "欠我", "欠钱", "救命", "报警")),
            ("身体健康内容", ("生病", "医院", "抑郁", "自残", "想死", "怀孕", "生理期", "身体")),
        ]
        for label, tokens in rules:
            if any(token in cleaned for token in tokens):
                return label
        if re.search(r"(你|他|她).{0,8}(怎么|凭什么|是不是|到底).{0,20}(烦|讨厌|过分|有病|恶心)", cleaned):
            return "带情绪的质问"
        return ""

    def _atrelay_event_confirms_sensitive_send(self, event: AstrMessageEvent) -> bool:
        message_text = _single_line(getattr(event, "message_str", ""), 220)
        if not message_text:
            return False
        confirms = (
            "随便", "都行", "可以", "发吧", "就这样", "原样", "原话", "照发",
            "委婉", "换种说法", "你看着办", "直接发", "确认", "没事",
        )
        if not any(token in message_text for token in confirms):
            return False
        quote_text = ""
        try:
            for seg in getattr(getattr(event, "message_obj", None), "message", []) or []:
                for attr in ("text", "message", "raw_message", "content"):
                    value = getattr(seg, attr, None)
                    if value:
                        quote_text += " " + str(value)
                data = getattr(seg, "data", None)
                if isinstance(data, dict):
                    quote_text += " " + " ".join(str(data.get(key) or "") for key in ("text", "message", "raw_message", "content"))
        except Exception:
            quote_text = ""
        combined = f"{message_text} {quote_text}"
        return any(token in combined for token in ("原样发", "原样带", "换种说法", "委婉一点", "直接转述", "不能直接转述"))

    def _atrelay_boundary_reason(self, text: str) -> str:
        cleaned = _single_line(text, 800)
        if not cleaned:
            return ""
        insult_tokens = ("骂他", "骂她", "骂你", "傻逼", "废物", "垃圾", "滚", "闭嘴", "爬", "有病", "恶心")
        if any(token in cleaned for token in insult_tokens):
            return "包含辱骂或攻击"
        impersonation_patterns = (
            r"我是.{0,6}(群主|管理员|管理|老师|本人|官方)",
            r"(冒充|假装|装成|伪装成|替我装)",
            r"(告诉|跟).{0,12}(我是|你是).{0,8}(群主|管理员|管理|老师|官方)",
        )
        if any(re.search(pattern, cleaned) for pattern in impersonation_patterns):
            return "涉及身份冒充或虚假权限"
        if re.search(r"(密码|口令|验证码|账号).{0,12}(告诉|发给|转给|问|要)", cleaned):
            return "涉及敏感凭据"
        if re.search(r"(威胁|恐吓|打他|弄他|开盒|人肉|盒了)", cleaned):
            return "包含威胁或骚扰"
        return ""

    def _atrelay_boundary_guard(self, text: str) -> str:
        reason = self._atrelay_boundary_reason(text)
        if not reason:
            return ""
        return f"发送失败：这条转述{reason}，不能代发。可以改成中性提醒后再让我发送。"

    def _atrelay_confirmation_guard(self, text: str, *, relay_mode: str, sensitive_confirmed: bool) -> str:
        if not getattr(self, "atrelay_sensitive_confirm", True):
            return ""
        reason = self._atrelay_sensitive_reason(text)
        if not reason or sensitive_confirmed:
            return ""
        return (
            f"需要先确认：这句话像{reason}，不能直接转述。"
            "请先问用户“要我原样带过去，还是稍微委婉一点？”确认后再发送。"
        )

    @staticmethod
    def _atrelay_bool_flag(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        text = str(value or "").strip().lower()
        return text in {"1", "true", "yes", "y", "on", "确认", "已确认", "可以", "是"}

    def _parse_atrelay_target_list(self, value: Any, *, limit: int | None = None) -> list[str]:
        if isinstance(value, list):
            raw_items = value
        else:
            raw_items = re.split(r"[\n,，、;；\s]+", str(value or ""))
        items: list[str] = []
        for item in raw_items:
            text = _single_line(item, 80)
            if text and text not in items:
                items.append(text)
            if limit and len(items) >= limit:
                break
        return items

    def _atrelay_send_log(self) -> list[dict[str, Any]]:
        log = self.data.setdefault("atrelay_send_log", [])
        if not isinstance(log, list):
            log = []
            self.data["atrelay_send_log"] = log
        cutoff = _now_ts() - 24 * 3600
        kept = [item for item in log if isinstance(item, dict) and _safe_float(item.get("ts"), 0) >= cutoff]
        if len(kept) != len(log):
            self.data["atrelay_send_log"] = kept
        return kept

    def _atrelay_send_signature(self, kind: str, target: str, text: str, at_user: str = "") -> str:
        compact = re.sub(r"\s+", "", _single_line(text, 240))
        return f"{kind}:{target}:{at_user}:{compact[:160]}"

    async def _resolve_atrelay_target_group(self, event: AstrMessageEvent, group_hint: Any = "") -> dict[str, Any]:
        hint = _single_line(group_hint, 80)
        if hint.isdigit():
            return {"status": "success", "group_id": hint, "source": "direct"}
        current_group = self._extract_group_id_from_event(event)
        if not hint and current_group:
            return {"status": "success", "group_id": current_group, "source": "current_group"}
        configured_groups = [str(item) for item in self._configured_group_ids() if str(item or "").strip()]
        if not hint and len(configured_groups) == 1:
            return {"status": "success", "group_id": configured_groups[0], "source": "single_configured_group"}
        if not hint:
            return {"status": "need_group", "message": "需要补充目标群号或群名"}
        bot = getattr(event, "bot", None)
        api = getattr(bot, "api", None)
        call_action = getattr(api, "call_action", None)
        if not callable(call_action):
            return {"status": "need_group", "message": "当前平台不能查询群列表，请直接提供群号"}
        try:
            groups = await call_action("get_group_list")
        except Exception as exc:
            return {"status": "error", "message": f"获取群列表失败: {_single_line(exc, 120)}"}
        matches = []
        for item in groups if isinstance(groups, list) else []:
            group_id = str(item.get("group_id") or "")
            name = _single_line(item.get("group_name") or item.get("group_remark"), 100)
            if hint in group_id or hint in name:
                matches.append({"group_id": group_id, "group_name": name})
        if len(matches) == 1:
            return {"status": "success", **matches[0], "source": "group_list"}
        if len(matches) > 1:
            return {"status": "ambiguous", "matches": matches[:8], "message": "匹配到多个群，请补充群号"}
        return {"status": "not_found", "message": "未找到匹配群聊"}

    def _atrelay_duplicate_guard(self, kind: str, target: str, text: str, at_user: str = "") -> str:
        signature = self._atrelay_send_signature(kind, target, text, at_user)
        now = _now_ts()
        for item in self._atrelay_send_log():
            if item.get("signature") == signature and now - _safe_float(item.get("ts"), 0) < 10 * 60:
                return "发送失败：近 10 分钟内已经发送过相同转述，已拦截重复发送。"
        return ""

    def _note_atrelay_send(self, kind: str, target: str, text: str, at_user: str = "") -> None:
        log = self._atrelay_send_log()
        log.append(
            {
                "ts": _now_ts(),
                "kind": kind,
                "target": str(target),
                "at_user": _single_line(at_user, 80),
                "signature": self._atrelay_send_signature(kind, target, text, at_user),
            }
        )
        del log[:-80]

    def _atrelay_receipt_tasks(self) -> list[dict[str, Any]]:
        tasks = self.data.setdefault("pending_atrelay_receipts", [])
        if not isinstance(tasks, list):
            tasks = []
            self.data["pending_atrelay_receipts"] = tasks
        now = _now_ts()
        kept = [
            item for item in tasks
            if isinstance(item, dict)
            and _safe_float(item.get("expires_at"), 0) > now
            and _single_line(item.get("status"), 24) in {"waiting_reply", "waiting_confirm"}
        ]
        if len(kept) != len(tasks):
            self.data["pending_atrelay_receipts"] = kept
        return kept

    def _atrelay_receipt_label_for_user(self, user_id: str, fallback: str = "") -> str:
        user_id = _single_line(user_id, 40)
        profile = self._worldbook_profile_by_user_id(user_id) if user_id else None
        if isinstance(profile, dict):
            name = _single_line(profile.get("name"), 40)
            if name and name != user_id:
                return name
        return _single_line(fallback, 40) or user_id or "对方"

    def _note_atrelay_private_receipt_task(
        self,
        event: AstrMessageEvent,
        *,
        target_user: str,
        target_name: str = "",
        question: str,
        sent_text: str,
        confirm_before_report: bool = False,
        expire_hours: Any = 12,
    ) -> dict[str, Any]:
        source_umo = _single_line(getattr(event, "unified_msg_origin", ""), 120)
        try:
            source_user = _single_line(event.get_sender_id(), 40)
        except Exception:
            source_user = ""
        source_name = ""
        try:
            source_name = _single_line(self._sender_display_name(event), 40)
        except Exception:
            source_name = ""
        platform = source_umo.split(":", 1)[0] if ":" in source_umo else (self.target_platform or "aiocqhttp")
        if not source_umo and source_user:
            source_umo = f"{platform}:FriendMessage:{source_user}"
        ttl = max(1.0, min(72.0, _safe_float(expire_hours, 12.0)))
        task = {
            "id": uuid.uuid4().hex[:16],
            "created_at": _now_ts(),
            "expires_at": _now_ts() + ttl * 3600,
            "status": "waiting_reply",
            "source_umo": source_umo,
            "source_user_id": source_user,
            "source_name": source_name,
            "target_user_id": _single_line(target_user, 40),
            "target_name": self._atrelay_receipt_label_for_user(target_user, target_name),
            "question": _single_line(question, 300),
            "sent_text": _single_line(sent_text, 300),
            "confirm_before_report": bool(confirm_before_report),
        }
        tasks = self._atrelay_receipt_tasks()
        tasks.append(task)
        del tasks[:-40]
        return task

    def _atrelay_receipt_confirmation_intent(self, text: str) -> str:
        cleaned = _single_line(text, 80)
        if not cleaned:
            return ""
        if re.search(r"(不行|不可以|别|不要|算了|别转|别说|不方便|拒绝|否)", cleaned):
            return "no"
        if re.search(r"^(可以|可|行|好|好的|嗯|嗯嗯|对|没事|转吧|说吧|告诉他|告诉她|发吧|ok|OK)[。！？!?\s]*$", cleaned):
            return "yes"
        return ""

    def _format_atrelay_receipt_report(self, task: dict[str, Any], reply_text: str) -> str:
        target = _single_line(task.get("target_name") or task.get("target_user_id"), 40) or "对方"
        question = _single_line(task.get("question") or task.get("sent_text"), 120)
        reply = _single_line(reply_text, 600)
        if question:
            return f"{target}回复你刚才让我问的「{question}」：{reply}"
        return f"{target}回复了：{reply}"

    async def _send_atrelay_receipt_to_source(self, task: dict[str, Any], text: str) -> bool:
        source_umo = _single_line(task.get("source_umo"), 120)
        if not source_umo:
            source_user = _single_line(task.get("source_user_id"), 40)
            if not source_user:
                return False
            platform = self.target_platform or "aiocqhttp"
            source_umo = f"{platform}:FriendMessage:{source_user}"
        await self.context.send_message(source_umo, MessageChain([Plain(text)]))
        return True

    async def _maybe_handle_atrelay_private_receipt_reply(
        self,
        event: AstrMessageEvent,
        user_id: str,
        sender_display_name: str,
        text: str,
    ) -> bool:
        if not getattr(self, "enable_atrelay_tools", True):
            return False
        target_user = _single_line(user_id, 40)
        cleaned = _single_line(text, 800)
        if not target_user or not cleaned:
            return False
        tasks = self._atrelay_receipt_tasks()
        task = None
        for item in tasks:
            if _single_line(item.get("target_user_id"), 40) == target_user:
                task = item
                break
        if not isinstance(task, dict):
            return False
        status = _single_line(task.get("status"), 24)
        if status == "waiting_confirm":
            intent = self._atrelay_receipt_confirmation_intent(cleaned)
            if not intent:
                return False
            tasks.remove(task)
            if intent == "yes":
                reply_text = _single_line(task.get("pending_reply_text"), 800)
                report = self._format_atrelay_receipt_report(task, reply_text)
                await self._send_atrelay_receipt_to_source(task, report)
                await self.context.send_message(event.unified_msg_origin, MessageChain([Plain("好，我帮你带回去了。")]))
            else:
                target = self._atrelay_receipt_label_for_user(target_user, sender_display_name)
                await self._send_atrelay_receipt_to_source(task, f"{target}回复了，但说不方便转回来。")
                await self.context.send_message(event.unified_msg_origin, MessageChain([Plain("好，那我不转回去。")]))
            self._save_data_sync()
            try:
                event.stop_event()
            except Exception:
                pass
            return True
        if status != "waiting_reply":
            return False
        if bool(task.get("confirm_before_report")):
            task["status"] = "waiting_confirm"
            task["pending_reply_text"] = cleaned
            task["target_name"] = self._atrelay_receipt_label_for_user(target_user, sender_display_name)
            self._save_data_sync()
            source_name = _single_line(task.get("source_name"), 30) or "对方"
            await self.context.send_message(
                event.unified_msg_origin,
                MessageChain([Plain(f"收到。我可以把你刚才这句转回给{source_name}吗？回“可以”或“不行”就好。")]),
            )
            try:
                event.stop_event()
            except Exception:
                pass
            return True
        tasks.remove(task)
        task["target_name"] = self._atrelay_receipt_label_for_user(target_user, sender_display_name)
        report = self._format_atrelay_receipt_report(task, cleaned)
        await self._send_atrelay_receipt_to_source(task, report)
        self._save_data_sync()
        try:
            event.stop_event()
        except Exception:
            pass
        return True

    def _atrelay_target_resting_reason(self, user_id: str, *, now: float | None = None) -> str:
        target_user_id = _single_line(user_id, 40)
        if not target_user_id:
            return ""
        users = self.data.get("users", {})
        user = users.get(target_user_id) if isinstance(users, dict) else None
        if not isinstance(user, dict):
            return ""
        check_now = _now_ts() if now is None else now
        rest_until = self._user_rest_silence_until(user, now=check_now)
        if rest_until <= check_now:
            return ""
        reason = _single_line(user.get("user_rest_reason"), 80)
        until_text = self._environment_fromtimestamp(rest_until).strftime("%m-%d %H:%M")
        return f"目标用户明确在休息中（静默至 {until_text}" + (f"，原因：{reason}" if reason else "") + "）"

    def _pop_due_atrelay_tasks_for_sender(self, group_id: str, sender_id: str) -> list[dict[str, Any]]:
        group = self._get_group(group_id)
        tasks = group.get("pending_atrelay_tasks")
        if not isinstance(tasks, list) or not sender_id:
            return []
        now = _now_ts()
        due: list[dict[str, Any]] = []
        kept: list[dict[str, Any]] = []
        for task in tasks:
            if not isinstance(task, dict):
                continue
            if _safe_float(task.get("expires_at"), 0) <= now:
                continue
            if str(task.get("target_user_id") or "") == str(sender_id):
                due.append(dict(task))
            else:
                kept.append(task)
        group["pending_atrelay_tasks"] = kept
        return due[:3]

    async def _dispatch_due_atrelay_tasks(self, event: AstrMessageEvent, group_id: str, sender_id: str) -> None:
        if not self.enable_atrelay_tools or not group_id or not sender_id:
            return
        async with self._data_lock:
            due = self._pop_due_atrelay_tasks_for_sender(group_id, sender_id)
            if due:
                self._save_data_sync()
        if not due:
            return
        platform = str(getattr(event, "unified_msg_origin", "") or "").split(":")[0] or self.target_platform or "aiocqhttp"
        target_umo = f"{platform}:GroupMessage:{group_id}"
        for task in due:
            text = _single_line(task.get("message"), 800)
            if not text:
                continue
            duplicate = self._atrelay_duplicate_guard("group", group_id, text, sender_id)
            if duplicate:
                logger.info("[PrivateCompanion] 延迟转述重复拦截: group=%s user=%s", group_id, sender_id)
                continue
            try:
                await self.context.send_message(target_umo, MessageChain([At(qq=sender_id), Plain(" "), Plain(text)]))
                self._note_atrelay_send("group", group_id, text, sender_id)
                self._save_data_sync()
            except Exception as exc:
                logger.warning("[PrivateCompanion] 延迟转述发送失败: group=%s user=%s err=%s", group_id, sender_id, _single_line(exc, 160))

