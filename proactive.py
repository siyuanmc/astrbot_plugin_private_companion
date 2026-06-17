# -*- coding: utf-8 -*-
"""
ProactiveMixin — 从 main.py 重新拆分出的主动消息调度
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

class ProactiveMixin:
    """主动消息调度"""

    def _configured_target_ids(self) -> list[str]:
        raw = self.target_user_ids
        if isinstance(raw, str):
            parts = re.split(r"[,\s,、;；]+", raw)
        elif isinstance(raw, list):
            parts = raw
        else:
            parts = []
        ids = []
        for part in parts:
            user_id = str(part).strip()
            if user_id and user_id.isdigit() and not self._is_bot_self_user_id(user_id) and user_id not in ids:
                ids.append(user_id)
        return ids

    def _user_enabled_for_proactive(self, user_id: str, user: dict[str, Any] | None = None) -> bool:
        if not isinstance(user, dict):
            return False
        if user.get("enabled") is False or user.get("manual_disabled"):
            return False
        return self._is_target_private_user(user_id, user)

    def _private_user_role(self, user: dict[str, Any] | None, user_id: str = "") -> str:
        if not isinstance(user, dict):
            return "friend"
        role_getter = getattr(self, "_ensure_private_user_role", None)
        if callable(role_getter):
            try:
                return role_getter(str(user_id or user.get("user_id") or ""), user)
            except Exception:
                pass
        normalizer = getattr(self, "_normalize_private_user_role", None)
        role = normalizer(user.get("relationship_role")) if callable(normalizer) else str(user.get("relationship_role") or "")
        return role if role in {"owner", "friend"} else "friend"

    def _user_profile_override_int(self, user: dict[str, Any], key: str) -> int | None:
        if not isinstance(user, dict):
            return None
        raw = user.get(key)
        if raw in (None, ""):
            return None
        value = _safe_int(raw, -1)
        return value if value >= 0 else None

    def _effective_user_daily_limit(self, user: dict[str, Any]) -> int:
        override = self._user_profile_override_int(user, "proactive_daily_limit")
        if override is not None:
            return override
        max_daily_messages = self._runtime_max_daily_messages()
        if self._private_user_role(user) == "friend":
            return min(max_daily_messages, 2) if max_daily_messages > 0 else 0
        return max(0, max_daily_messages)

    def _runtime_max_daily_messages(self) -> int:
        runtime_value = _safe_int(getattr(self, "max_daily_messages", 8), 8, 0, 12)
        if runtime_value > 0:
            return runtime_value
        config = getattr(self, "config", None)
        getter = getattr(config, "get", None)
        if callable(getter):
            try:
                configured_value = _safe_int(getter("max_daily_messages", runtime_value), runtime_value, 0, 12)
                if configured_value > 0:
                    self.max_daily_messages = configured_value
                    return configured_value
            except Exception:
                pass
        return runtime_value

    def _format_daily_limit_disabled_reason(self, user: dict[str, Any]) -> str:
        override = user.get("proactive_daily_limit", -1) if isinstance(user, dict) else -1
        runtime_value = _safe_int(getattr(self, "max_daily_messages", 0), 0, 0, 12)
        config_value = runtime_value
        config = getattr(self, "config", None)
        getter = getattr(config, "get", None)
        if callable(getter):
            try:
                config_value = _safe_int(getter("max_daily_messages", runtime_value), runtime_value, 0, 12)
            except Exception:
                config_value = runtime_value
        return f"每日上限为 0（用户覆盖={override}，运行中全局={runtime_value}，配置全局={config_value}）"

    def _effective_user_idle_minutes(self, user: dict[str, Any]) -> int:
        override = self._user_profile_override_int(user, "proactive_idle_minutes")
        if override is not None:
            return override
        if self._private_user_role(user) == "friend":
            return max(self.idle_minutes, 180)
        return max(0, self.idle_minutes)

    def _effective_user_greeting_idle_minutes(self, user: dict[str, Any]) -> int:
        if self._private_user_role(user) == "friend":
            return max(self.greeting_idle_minutes, 120)
        return max(0, self.greeting_idle_minutes)

    def _effective_user_min_interval_minutes(self, user: dict[str, Any]) -> int:
        override = self._user_profile_override_int(user, "proactive_min_interval_minutes")
        if override is not None:
            return override
        if self._private_user_role(user) == "friend":
            return max(self.min_interval_minutes, 360)
        return max(0, self.min_interval_minutes)

    def _effective_user_photo_daily_limit(self, user: dict[str, Any] | None = None) -> int:
        if isinstance(user, dict):
            if self._private_user_role(user) == "friend":
                return 0
            override = self._user_profile_override_int(user, "photo_daily_limit")
            if override is not None:
                return override
        return max(0, self.photo_action_max_daily)

    def _effective_user_screen_peek_daily_limit(self, user: dict[str, Any] | None = None) -> int:
        if isinstance(user, dict):
            if self._private_user_role(user) == "friend":
                return 0
            override = self._user_profile_override_int(user, "screen_peek_daily_limit")
            if override is not None:
                return override
        return max(0, self.screen_peek_max_daily)

    def _effective_user_poke_daily_limit(self, user: dict[str, Any] | None = None) -> int:
        if isinstance(user, dict):
            override = self._user_profile_override_int(user, "poke_daily_limit")
            if override is not None:
                return override
            if self._private_user_role(user) == "friend":
                return 0
        return max(0, self.poke_action_max_times)

    def _format_private_user_boundary_hint(self, user: dict[str, Any]) -> str:
        role = self._private_user_role(user)
        labeler = getattr(self, "_private_user_role_label", None)
        label = labeler(role) if callable(labeler) else ("主人" if role == "owner" else "朋友")
        note = _single_line(user.get("proactive_boundary_note"), 180)
        if role == "owner":
            text = (
                "【当前私聊关系角色】\n"
                f"- 当前用户角色：{label}。\n"
                "- 可以延续人格中对主人的亲近、依赖和日常陪伴动机，但仍要尊重用户休息、忙碌和拒绝信号。"
            )
        else:
            text = (
                "【当前私聊关系角色】\n"
                f"- 当前用户角色：{label}。\n"
                "- 对方不是主人/恋人/专属陪伴目标。主动联系应像普通朋友：少量、具体、不过度亲密，不使用主人专属称呼、占有欲、撒娇索取或暧昧承诺。\n"
                "- 动机应以礼貌关心、共同话题、必要转告、轻分享为主；不要因为想贴近、想被哄、想确认对方在不在而频繁打扰。\n"
                "- 不给朋友使用窥屏或单独生图能力；如果出现图片分享,只能是复用已有普通图片,不要声称为朋友专门拍照、生成或观察。"
                "- 不对朋友发起本子/夹层阅读推荐、私密阅读分享、屏幕观察、群聊私下转述、私下创作分享或其他涉及隐私来源的主动。"
            )
        if note:
            text += f"\n- 用户级边界备注：{note}"
        return text

    def _friend_sensitive_proactive_reason(self, reason: Any) -> bool:
        normalized = str(reason or "").strip()
        return normalized in {
            "group_share",
            "jm_cosmos_share",
            "jm_cosmos_recommendation_request",
            "creative_share",
        }

    def _friend_sensitive_proactive_action(self, action: Any) -> bool:
        parts = {part.strip() for part in str(action or "").split("+") if part.strip()}
        return bool(parts & {"screen_peek", "jm_cosmos_read"})

    def _friend_can_receive_proactive_reason(self, user: dict[str, Any] | None, reason: Any, action: Any = "") -> bool:
        if not isinstance(user, dict) or self._private_user_role(user) != "friend":
            return True
        return not (self._friend_sensitive_proactive_reason(reason) or self._friend_sensitive_proactive_action(action))

    def _sync_configured_targets(self):
        for user_id in self._configured_target_ids():
            user = self._get_user(user_id)
            if user.get("manual_disabled"):
                self._clear_pending_proactive_plan(user)
                continue
            user["enabled"] = True
            user["target_user"] = True
            user.setdefault("nickname", self.default_nickname)
            if not user.get("umo"):
                user["umo"] = f"{self.target_platform}:FriendMessage:{user_id}"
            if self._user_enabled_for_proactive(user_id, user) and _safe_float(user.get("next_proactive_at"), 0) <= 0:
                self._schedule_next_proactive(user, now=_now_ts())

    def _prime_enabled_user_schedules(self) -> bool:
        users = self.data.get("users", {})
        if not isinstance(users, dict):
            return False
        changed = False
        now = _now_ts()
        for raw_user in users.values():
            if not isinstance(raw_user, dict):
                continue
            raw_user_id = str(raw_user.get("user_id") or "")
            if not self._user_enabled_for_proactive(raw_user_id, raw_user):
                raw_user["enabled"] = False
                self._clear_pending_proactive_plan(raw_user)
                changed = True
                continue
            if not raw_user.get("umo"):
                continue
            if _safe_float(raw_user.get("next_proactive_at"), 0) > 0:
                if self._promote_earlier_daily_greeting_event(raw_user, now=now):
                    changed = True
                continue
            self._schedule_next_proactive(raw_user, now=now)
            changed = True
        return changed

    def _is_quiet_time(self) -> bool:
        match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", self.quiet_hours)
        if not match:
            return False
        sh, sm, eh, em = [int(part) for part in match.groups()]
        start = sh * 60 + sm
        end = eh * 60 + em
        now = datetime.now()
        current = now.hour * 60 + now.minute
        if start == end:
            return True
        if start < end:
            return start <= current < end
        return current >= start or current < end

    def _reset_daily_counter_if_needed(self, user: dict[str, Any]):
        today = _today_key()
        if user.get("sent_day") != today:
            user["sent_day"] = today
            user["sent_today"] = 0
            user["proactive_daypart_day"] = today
            user["proactive_daypart_counts"] = {}
        if user.get("photo_generated_day") != today:
            user["photo_generated_day"] = today
            user["photo_generated_today"] = 0
        if user.get("screen_peek_day") != today:
            user["screen_peek_day"] = today
            user["screen_peek_today"] = 0
            user["screen_peek_last_at"] = 0
        if user.get("greeting_sent_day") != today:
            user["greeting_sent_day"] = today
            user["greetings_sent"] = []
            user["greetings_suppressed_by_inbound"] = []
        if user.get("proactive_daypart_day") != today:
            user["proactive_daypart_day"] = today
            user["proactive_daypart_counts"] = {}

    def _effective_min_interval_seconds(self, user: dict[str, Any]) -> int:
        ignored_streak = _safe_int(user.get("ignored_streak"), 0)
        multiplier = min(2.2, 1.0 + ignored_streak * 0.35)
        return int(self._effective_user_min_interval_minutes(user) * 60 * multiplier)

    def _soft_daily_target(self, user: dict[str, Any]) -> float:
        daily_limit = self._effective_user_daily_limit(user)
        if daily_limit <= 0:
            return 0.0
        state = self.data.get("daily_state", {})
        important_dates = self._get_relevant_important_dates()
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        active_conditions = state.get("conditions", []) if isinstance(state, dict) else []
        ratio = 0.68
        if energy > 80:
            ratio += 0.06
        elif energy < 40:
            ratio -= 0.02
        if isinstance(active_conditions, list) and active_conditions:
            ratio += min(0.1, len(active_conditions) * 0.03)
        if important_dates:
            ratio += 0.1 if _safe_int(important_dates[0].get("_days_until"), 0) == 0 else 0.05
        ratio = max(0.45, min(0.95, ratio))
        if daily_limit == 1:
            ratio = max(ratio, 0.75)
        return max(0.6, daily_limit * ratio)

    def _daily_intensity_factor(self, user: dict[str, Any]) -> float:
        daily_limit = self._effective_user_daily_limit(user)
        if daily_limit <= 0:
            return 0.0
        sent_today = _safe_int(user.get("sent_today"), 0)
        soft_target = self._soft_daily_target(user)
        capacity_factor = min(1.35, 0.9 + daily_limit * 0.08)
        if soft_target <= 0:
            return max(0.35, capacity_factor)
        usage = sent_today / soft_target
        if usage < 0.2:
            pressure = 1.18
        elif usage < 0.5:
            pressure = 1.03
        elif usage < 0.85:
            pressure = 0.88
        elif usage < 1.0:
            pressure = 0.72
        else:
            pressure = 0.5
        return max(0.3, min(1.4, capacity_factor * pressure))

    def _fallback_proactive_delay_hours(
        self,
        user: dict[str, Any],
        *,
        now: float | None = None,
    ) -> tuple[float, float]:
        now_dt = self._environment_fromtimestamp(now or _now_ts())
        if self._private_user_role(user) == "friend":
            spread_delay = self._friend_proactive_spread_delay_hours(user, now=now_dt.timestamp())
            if spread_delay is not None:
                return spread_delay
        sent_today = _safe_int(user.get("sent_today"), 0)
        remaining_target = max(1, math.ceil(max(0.0, self._soft_daily_target(user) - sent_today)))
        counts = self._today_proactive_daypart_counts(user)
        current_bucket = self._proactive_daypart_bucket_for_minute(now_dt.hour * 60 + now_dt.minute)
        if current_bucket == "late_night" and _safe_int(counts.get("late_night"), 0, 0) >= 1:
            return (7.5, 10.5)
        if current_bucket == "evening" and _safe_int(counts.get("evening"), 0, 0) >= 1 and remaining_target <= 2:
            return (3.0, 5.0)

        if now_dt.hour < 12:
            if remaining_target >= 4:
                return (0.45, 1.4)
            if remaining_target >= 3:
                return (0.75, 2.0)
            if remaining_target >= 2:
                return (1.0, 2.8)
            return (1.6, 4.2)
        if now_dt.hour < 18:
            if remaining_target >= 3:
                return (0.55, 1.8)
            if remaining_target >= 2:
                return (0.9, 2.6)
            return (1.8, 4.5)
        if remaining_target >= 2:
            return (0.5, 1.6)
        return (0.9, 2.4)

    def _friend_proactive_spread_delay_hours(
        self,
        user: dict[str, Any],
        *,
        now: float | None = None,
    ) -> tuple[float, float] | None:
        if self._private_user_role(user) != "friend":
            return None
        now_dt = self._environment_fromtimestamp(now or _now_ts())
        sent_today = _safe_int(user.get("sent_today"), 0)
        daily_limit = self._effective_user_daily_limit(user)
        if daily_limit <= 1 or sent_today <= 0:
            return None
        minute = now_dt.hour * 60 + now_dt.minute
        if sent_today <= 1:
            if minute < 14 * 60:
                return self._delay_hours_until_local_window(now_dt, 14 * 60, 17 * 60)
            if minute < 18 * 60:
                return self._delay_hours_until_local_window(now_dt, 19 * 60, 21 * 60 + 20)
            return (6.0, 11.0)
        if sent_today <= 2 and daily_limit >= 3:
            if minute < 18 * 60 + 30:
                return self._delay_hours_until_local_window(now_dt, 18 * 60 + 40, 21 * 60 + 20)
            return (8.0, 14.0)
        return (10.0, 18.0)

    def _delay_hours_until_local_window(
        self,
        now_dt: datetime,
        start_minute: int,
        end_minute: int,
    ) -> tuple[float, float]:
        base = datetime.combine(now_dt.date(), datetime.min.time(), tzinfo=now_dt.tzinfo)
        start_dt = base + timedelta(minutes=start_minute)
        end_dt = base + timedelta(minutes=end_minute)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)
        if end_dt <= now_dt + timedelta(minutes=20):
            start_dt += timedelta(days=1)
            end_dt += timedelta(days=1)
        start_dt = max(start_dt, now_dt + timedelta(hours=3))
        if end_dt <= start_dt:
            end_dt = start_dt + timedelta(minutes=90)
        min_hours = max(0.25, (start_dt - now_dt).total_seconds() / 3600)
        max_hours = max(min_hours + 0.5, (end_dt - now_dt).total_seconds() / 3600)
        return (min_hours, max_hours)

    def _friend_proactive_scheduled_too_early(
        self,
        user: dict[str, Any],
        scheduled_at: float,
    ) -> bool:
        if self._private_user_role(user) != "friend" or scheduled_at <= 0:
            return False
        daily_limit = self._effective_user_daily_limit(user)
        sent_today = _safe_int(user.get("sent_today"), 0)
        if daily_limit <= 1 or sent_today <= 0:
            return False
        now_dt = self._environment_now()
        scheduled_dt = self._environment_fromtimestamp(scheduled_at)
        if scheduled_dt.date() != now_dt.date():
            return False
        minute = scheduled_dt.hour * 60 + scheduled_dt.minute
        if sent_today >= 2 and daily_limit >= 3:
            return minute < 18 * 60 + 30
        if sent_today >= 1:
            return minute < 14 * 60
        return False

    def _schedule_next_proactive(
        self,
        user: dict[str, Any],
        *,
        now: float | None = None,
        delay_hours: tuple[float, float] | None = None,
    ):
        user_id = str(user.get("user_id") or user.get("id") or "")
        if not self._user_enabled_for_proactive(user_id, user):
            self._clear_pending_proactive_plan(user)
            return
        now = now or _now_ts()
        rest_until = self._user_rest_silence_until(user, now=now)
        planned_event = self._pick_best_planned_event(user, now)
        reason = (
            str(planned_event.get("reason") or "")
            if planned_event else self._choose_planned_reason()
        )
        motive = (
            _single_line(planned_event.get("motive"), 120)
            if planned_event and planned_event.get("motive")
            else ""
        )
        action = (
            str(planned_event.get("action") or "message")
            if planned_event else ""
        )
        if not action:
            if not motive:
                motive = self._choose_proactive_motive(reason, user, planned_event=planned_event)
            action = self._choose_action_for_reason(reason, user, motive=motive)
        elif not motive:
            motive = self._choose_proactive_motive(reason, user, action=action, planned_event=planned_event)
        action = self._maybe_upgrade_planned_message_action(
            action,
            reason=reason,
            user=user,
            motive=motive,
            planned_event=planned_event,
        )
        if delay_hours is None:
            delay_hours = self._fallback_proactive_delay_hours(user, now=now)
        intensity_factor = self._daily_intensity_factor(user)
        if delay_hours is not None and intensity_factor > 0:
            widen = max(0.85, min(1.8, 1.25 - intensity_factor * 0.45))
            delay_hours = (delay_hours[0] * widen, delay_hours[1] * widen)
        if planned_event:
            scheduled = self._timestamp_from_story_event(planned_event, reason)
            if scheduled <= now:
                scheduled = now + random.uniform(3, 15)
        else:
            base_time = now + random.uniform(delay_hours[0] * 3600, delay_hours[1] * 3600)
            scheduled = self._move_timestamp_into_reason_window(base_time, reason)
        timer_event = self._get_active_llm_timer(user)
        if isinstance(timer_event, dict):
            timer_scheduled = _safe_float(timer_event.get("scheduled_ts"), 0)
            if timer_scheduled > now and (scheduled <= 0 or timer_scheduled <= scheduled):
                user["next_proactive_at"] = timer_scheduled
                user["planned_proactive_reason"] = _single_line(timer_event.get("reason"), 40) or reason
                user["planned_proactive_action"] = _single_line(timer_event.get("action"), 24) or "message"
                user["planned_proactive_source"] = "timer"
                user["planned_proactive_motive"] = self._normalize_internal_motive_text(
                    _single_line(timer_event.get("motive"), 140) or motive
                )
                user["planned_proactive_topic"] = _single_line(timer_event.get("topic"), 60) or (
                    _single_line(planned_event.get("topic"), 60)
                    if isinstance(planned_event, dict)
                    else self._choose_proactive_topic(reason, user)
                )
                self._set_planned_proactive_trigger(
                    user,
                    message_id=_single_line(timer_event.get("trigger_message_id"), 120),
                    umo=_single_line(timer_event.get("trigger_umo"), 160),
                    created_at=_safe_float(timer_event.get("trigger_ts"), 0),
                )
                user["planned_event_chain"] = (
                    []
                    if self._private_user_role(user) == "friend"
                    else list(timer_event.get("chain") or [])
                    if isinstance(timer_event.get("chain"), list)
                    else []
                )
                user["planned_opener_mode"] = ""
                user["planned_followup_kind"] = ""
                user["planned_proactive_quota_exempt"] = False
                item = self._record_proactive_candidate(
                    str(user.get("user_id") or user.get("id") or ""),
                    {
                        "source": "timer",
                        "reason": user["planned_proactive_reason"],
                        "action": user["planned_proactive_action"],
                        "scheduled_ts": timer_scheduled,
                        "topic": user["planned_proactive_topic"],
                        "motive": user["planned_proactive_motive"],
                        "score": 100,
                    },
                    status="accepted",
                    note="用户预约/定时主动",
                )
                user["planned_candidate_id"] = item.get("id", "")
                return
        if rest_until > now and scheduled < rest_until:
            scheduled = rest_until + random.uniform(20 * 60, 90 * 60)
        user["next_proactive_at"] = scheduled
        user["planned_proactive_reason"] = reason
        user["planned_proactive_action"] = action
        user["planned_proactive_source"] = "event" if planned_event else "random"
        user["planned_proactive_motive"] = motive
        user["planned_proactive_topic"] = (
            _single_line(planned_event.get("topic"), 60)
            if isinstance(planned_event, dict)
            else self._choose_proactive_topic(reason, user)
        )
        self._clear_planned_proactive_trigger(user)
        user["planned_event_chain"] = (
            []
            if self._private_user_role(user) == "friend"
            else list(planned_event.get("chain") or [])
            if isinstance(planned_event, dict) and isinstance(planned_event.get("chain"), list)
            else []
        )
        user["planned_opener_mode"] = ""
        user["planned_followup_kind"] = "" if self._private_user_role(user) == "friend" else (
            "suspended_opener"
            if isinstance(planned_event, dict) and planned_event.get("_opener_followup")
            else "chain_followup"
            if isinstance(planned_event, dict) and planned_event.get("_chain_followup")
            else ""
        )
        user["planned_proactive_quota_exempt"] = bool(
            isinstance(planned_event, dict) and planned_event.get("_free_screen_peek")
        )
        item = self._record_proactive_candidate(
            str(user.get("user_id") or user.get("id") or ""),
            {
                "source": user["planned_proactive_source"],
                "reason": user["planned_proactive_reason"],
                "action": user["planned_proactive_action"],
                "scheduled_ts": user["next_proactive_at"],
                "topic": user["planned_proactive_topic"],
                "motive": user["planned_proactive_motive"],
                "score": 60 if planned_event else 42,
            },
            status="accepted",
            note="日程/随机调度",
        )
        user["planned_candidate_id"] = item.get("id", "")

    def _user_rest_silence_until(self, user: dict[str, Any], *, now: float | None = None) -> float:
        check_now = _now_ts() if now is None else now
        rest_until = _safe_float(user.get("user_rest_until"), 0)
        if rest_until <= 0:
            return 0.0
        if rest_until <= check_now:
            user["user_rest_until"] = 0
            user["user_rest_reason"] = ""
            user["user_rest_set_at"] = 0
            return 0.0
        return rest_until

    def _next_user_rest_morning_ts(self, *, now: float) -> float:
        timezone_name = _single_line(getattr(self, "environment_perception_timezone", ""), 64) or "Asia/Shanghai"
        try:
            tz = zoneinfo.ZoneInfo(timezone_name)
        except Exception:
            tz = zoneinfo.ZoneInfo("Asia/Shanghai")
        current = datetime.fromtimestamp(now, tz)
        target = current.replace(hour=8, minute=30, second=0, microsecond=0)
        if target.timestamp() <= now + 3600:
            target += timedelta(days=1)
        return max(target.timestamp(), now + 6 * 3600)

    def _detect_user_rest_silence_until(self, text: str, *, now: float | None = None) -> float:
        cleaned = _single_line(text, 260).lower()
        if not cleaned:
            return 0.0
        check_now = _now_ts() if now is None else now
        cancel_pattern = (
            r"(?:我|俺|咱|人家).{0,10}(?:醒了|起床了|睡醒了|不睡了|回来了|可以聊)"
            r"|(?:睡醒了|起床了|不睡了|可以聊了|回来了)"
        )
        if re.search(cancel_pattern, cleaned):
            return -1.0
        hard_quiet = re.search(r"(?:别|不要|先别|暂时别).{0,10}(?:打扰|吵|主动|发消息)", cleaned)
        tomorrow = re.search(r"明天再(?:聊|说|回|看)", cleaned)
        nap = re.search(r"(?:我|俺|咱|人家).{0,10}(?:午休|眯一会|歇会|躺会|休息一下|休息会)", cleaned)
        sleep = re.search(
            r"(?:晚安|睡觉去了|先睡了|去睡了|睡了哈|睡啦|我睡了|我先睡|我去睡|我困了|困死了|补觉)",
            cleaned,
        )
        rest = re.search(r"(?:我|俺|咱|人家).{0,10}(?:休息|歇一下|躺一下|缓一会)", cleaned)
        if hard_quiet or tomorrow or sleep:
            return self._next_user_rest_morning_ts(now=check_now)
        if nap:
            return check_now + 2.5 * 3600
        if rest:
            return check_now + 3.5 * 3600
        return 0.0

    def _apply_user_rest_silence_from_message(
        self,
        user: dict[str, Any],
        text: str,
        *,
        now: float | None = None,
    ) -> bool:
        check_now = _now_ts() if now is None else now
        rest_until = self._detect_user_rest_silence_until(text, now=check_now)
        if rest_until < 0:
            if _safe_float(user.get("user_rest_until"), 0) > check_now:
                user["user_rest_until"] = 0
                user["user_rest_reason"] = ""
                user["user_rest_set_at"] = 0
                logger.info("[PrivateCompanion] 用户休息静默已解除: user=%s", user.get("user_id") or user.get("id") or "")
                return True
            return False
        if rest_until <= check_now:
            return False
        user["user_rest_until"] = rest_until
        user["user_rest_reason"] = _single_line(text, 120)
        user["user_rest_set_at"] = check_now
        if str(user.get("planned_proactive_source") or "") != "timer":
            self._clear_pending_proactive_plan(user)
        logger.info(
            "[PrivateCompanion] 已记录用户休息静默: user=%s until=%s reason=%s",
            user.get("user_id") or user.get("id") or "",
            self._environment_fromtimestamp(rest_until).strftime("%m-%d %H:%M"),
            _single_line(text, 80),
        )
        return True

    def _promote_earlier_daily_greeting_event(
        self,
        user: dict[str, Any],
        *,
        now: float | None = None,
    ) -> bool:
        if not self.enable_daily_greetings:
            return False
        if str(user.get("planned_proactive_source") or "") == "timer":
            return False
        current_next = _safe_float(user.get("next_proactive_at"), 0)
        if current_next <= 0:
            return False
        now = now or _now_ts()
        event = self._pick_daily_greeting_event(user, now)
        if not isinstance(event, dict):
            return False
        reason = str(event.get("reason") or "")
        if not self._is_sticky_greeting_reason(reason):
            return False
        scheduled = self._timestamp_from_story_event(event, reason)
        if scheduled <= 0 or scheduled >= current_next - 60:
            return False
        action = str(event.get("action") or "message")
        motive = _single_line(event.get("motive"), 120) or self._choose_proactive_motive(
            reason,
            user,
            action=action,
            planned_event=event,
        )
        user["next_proactive_at"] = scheduled
        user["planned_proactive_reason"] = reason
        user["planned_proactive_action"] = action
        user["planned_proactive_source"] = "event"
        user["planned_proactive_motive"] = motive
        user["planned_proactive_topic"] = _single_line(event.get("topic"), 60)
        self._clear_planned_proactive_trigger(user)
        user["planned_event_chain"] = [] if self._private_user_role(user) == "friend" else (
            list(event.get("chain") or []) if isinstance(event.get("chain"), list) else []
        )
        user["planned_opener_mode"] = ""
        user["planned_followup_kind"] = ""
        user["planned_proactive_quota_exempt"] = bool(event.get("_free_screen_peek"))
        return True

    def _is_proactive_plan_stale(self, user: dict[str, Any], *, now: float | None = None) -> bool:
        next_at = _safe_float(user.get("next_proactive_at"), 0)
        if next_at <= 0:
            return False
        check_now = _now_ts() if now is None else now
        return check_now - next_at > self.max_proactive_plan_lag_minutes * 60

    def _clear_pending_proactive_plan(self, user: dict[str, Any]) -> None:
        user["next_proactive_at"] = 0
        user["planned_proactive_reason"] = ""
        user["planned_proactive_action"] = ""
        user["planned_proactive_source"] = ""
        user["planned_proactive_motive"] = ""
        user["planned_proactive_topic"] = ""
        user["planned_event_chain"] = []
        user["planned_opener_mode"] = ""
        user["planned_followup_kind"] = ""
        user["planned_proactive_quota_exempt"] = False
        user["planned_candidate_id"] = ""
        self._clear_planned_proactive_trigger(user)

    async def _scheduler_loop(self):
        while not self._stop_event.is_set():
            try:
                timeout = self._next_scheduler_timeout()
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=timeout
                )
            except asyncio.TimeoutError:
                await self._tick()
                for label, task_factory in (
                    ("日常状态", self._ensure_daily_state),
                    ("今日日程", self._ensure_daily_plan),
                    ("当前细化", self._ensure_detail_enhancement),
                    ("当前在线感", self._ensure_current_detail_presence_status),
                    ("日记", self._ensure_daily_diary),
                    ("创作推进", self._maybe_advance_creative_projects),
                    ("被动注入缓存", self._refresh_passive_injection_cache),
                ):
                    try:
                        await task_factory()
                    except Exception as exc:
                        logger.warning("[PrivateCompanion] 主动循环维护步骤失败,已跳过: %s error=%s", label, _single_line(exc, 160))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[PrivateCompanion] 主动消息循环异常: {e}", exc_info=True)

    async def _kick_proactive_loop_once(self) -> None:
        try:
            await self._tick()
            for label, task_factory in (
                ("日常状态", self._ensure_daily_state),
                ("今日日程", self._ensure_daily_plan),
                ("当前细化", self._ensure_detail_enhancement),
                ("当前在线感", self._ensure_current_detail_presence_status),
                ("日记", self._ensure_daily_diary),
                ("创作推进", self._maybe_advance_creative_projects),
                ("被动注入缓存", self._refresh_passive_injection_cache),
            ):
                try:
                    await task_factory()
                except Exception as exc:
                    logger.warning("[PrivateCompanion] 主动链即时维护步骤失败,已跳过: %s error=%s", label, _single_line(exc, 160))
        except Exception as e:
            logger.warning(f"[PrivateCompanion] 主动链即时唤醒失败: {e}", exc_info=True)

    def _next_scheduler_timeout(self) -> float:
        base = max(30.0, float(self.check_interval_seconds))
        now = _now_ts()
        nearest_due_in: float | None = None
        users = self.data.get("users", {})
        if isinstance(users, dict):
            for raw_user in users.values():
                if not isinstance(raw_user, dict):
                    continue
                if not raw_user.get("umo"):
                    continue
                next_at = _safe_float(raw_user.get("next_proactive_at"), 0)
                if next_at <= 0:
                    continue
                due_in = max(0.0, next_at - now)
                if nearest_due_in is None or due_in < nearest_due_in:
                    nearest_due_in = due_in

        if nearest_due_in is None:
            detail_due_in = self._next_detail_due_in_seconds(now)
            if detail_due_in is not None:
                nearest_due_in = detail_due_in
        elif self.enable_detail_enhancement:
            detail_due_in = self._next_detail_due_in_seconds(now)
            if detail_due_in is not None and detail_due_in < nearest_due_in:
                nearest_due_in = detail_due_in

        if nearest_due_in is None:
            return max(35.0, min(base, random.uniform(base * 0.55, base * 0.95)))
        if nearest_due_in <= 20:
            return max(3.0, nearest_due_in + random.uniform(0.8, 3.2))
        if nearest_due_in <= 90:
            return max(8.0, nearest_due_in * random.uniform(0.35, 0.7))
        if nearest_due_in <= 6 * 60:
            return max(20.0, min(base * 0.5, nearest_due_in * random.uniform(0.18, 0.42)))
        return max(35.0, min(base, random.uniform(base * 0.55, base * 0.95)))

