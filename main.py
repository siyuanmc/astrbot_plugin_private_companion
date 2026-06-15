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
from .helpers import (
    _date_key,
    _now_ts,
    _safe_float,
    _safe_int,
    _set_today_key_timezone,
    _single_line,
    _strip_internal_message_blocks,
    _strip_outbound_control_blocks,
    _today_key,
)
from .forward_message import ForwardMessageMixin
from .private_image import PrivateImageMixin
from .qzone_integration import QzoneMixin
from .token_budget import TokenBudgetMixin
from .worldbook import WorldbookMixin
from .user_memory import UserMemoryMixin
from .creative import CreativeMixin
from .proactive import ProactiveMixin
from .group_wakeup import GroupWakeupMixin
from .group_observation import GroupObservationMixin
from .event_dispatch import EventDispatchMixin
from .private_reading import PrivateReadingMixin
from .news_exploration import NewsExplorationMixin
from .core_store import CoreStoreMixin
from .integration_status import IntegrationStatusMixin
from .astrbot_knowledge import AstrBotKnowledgeMixin
from .atrelay import AtRelayMixin
from .proactive_engine import ProactiveEngineMixin
from .proactive_message import ProactiveMessageMixin
from .daily_state import DailyStateMixin
from .state_views import StateViewsMixin
from .interaction_utils import InteractionUtilsMixin
from .llm_tool_actions import LlmToolActionsMixin
from .command_handlers import CommandHandlersMixin
from .tts_enhancement import TtsEnhancementMixin
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

_private_companion_plugin: Any | None = None

DEFAULT_AI_DAILY_MORNING_UID = "3706929260006322"
DEFAULT_AI_DAILY_JUYA_UID = "285286947"
DEFAULT_AI_DAILY_SOURCES = "\n".join(
    [
        f"AI日报|橘鸦Juya|{DEFAULT_AI_DAILY_JUYA_UID}|日报 早报|23:00",
        f"AI早报|黑鸦Heya|{DEFAULT_AI_DAILY_MORNING_UID}|早报 日报|12:00",
    ]
)

DEFAULT_NEWS_SOURCES = "\n".join(
    [
        "BBC中文|https://feeds.bbci.co.uk/zhongwen/simp/rss.xml",
        "Google新闻中文|https://news.google.com/rss?hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "Solidot|https://www.solidot.org/index.rss",
        "Hacker News|https://hnrss.org/frontpage",
        "MIT Technology Review|https://www.technologyreview.com/feed/",
        "Ars Technica|https://feeds.arstechnica.com/arstechnica/index",
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


def get_private_companion_api() -> Any | None:
    plugin = _private_companion_plugin
    if plugin is None:
        return None
    return getattr(plugin, "extension_api", None)


class PrivateCompanionExtensionAPI:
    """Lightweight integration API for external AstrBot plugins."""

    def __init__(self, plugin: "PrivateCompanionPlugin") -> None:
        self._plugin = plugin

    def register_proactive_ability(self, spec: dict[str, Any]) -> bool:
        return self._plugin.register_external_proactive_ability(spec)

    def unregister_proactive_ability(self, name: str) -> bool:
        return self._plugin.unregister_external_proactive_ability(name)

    def list_proactive_abilities(self) -> list[dict[str, Any]]:
        return self._plugin.external_proactive_abilities()

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


@register(
    PLUGIN_NAME,
    "Codex",
    "我会永远陪着你：为 AstrBot 提供人格连续性、关系识别、主动行为和可视化管理的陪伴编排插件。",
    "3.8.0",
)
class PrivateCompanionPlugin(CoreStoreMixin, AstrBotKnowledgeMixin, IntegrationStatusMixin, PrivateImageMixin, ForwardMessageMixin, QzoneMixin, TokenBudgetMixin, WorldbookMixin, UserMemoryMixin, CreativeMixin, ProactiveMixin, ProactiveEngineMixin, ProactiveMessageMixin, DailyStateMixin, StateViewsMixin, InteractionUtilsMixin, LlmToolActionsMixin, CommandHandlersMixin, TtsEnhancementMixin, GroupWakeupMixin, GroupObservationMixin, EventDispatchMixin, PrivateReadingMixin, NewsExplorationMixin, AtRelayMixin, Star):
    @staticmethod
    def _cfg_bool(config: AstrBotConfig, key: str, default: bool = True) -> bool:
        value = config.get(key, default)
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"true", "1", "yes", "on", "启用", "开启"}:
                return True
            if text in {"false", "0", "no", "off", "disabled", "停用", "关闭"}:
                return False
        return bool(value)

    @staticmethod
    def _cfg_str(config: AstrBotConfig, key: str, default: str = "", fallback: str = "") -> str:
        return str(config.get(key, default)).strip() or fallback

    @staticmethod
    def _cfg_int(config: AstrBotConfig, key: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
        return _safe_int(config.get(key, default), default, minimum, maximum)

    @staticmethod
    def _cfg_float(config: AstrBotConfig, key: str, default: float, minimum: float = 0.0) -> float:
        return _safe_float(config.get(key, default), default, minimum)

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

    def _clear_user_rest_pending_plan_fallback(self, user: dict[str, Any]) -> None:
        for key, value in (
            ("next_proactive_at", 0),
            ("planned_proactive_reason", ""),
            ("planned_proactive_action", ""),
            ("planned_proactive_source", ""),
            ("planned_proactive_motive", ""),
            ("planned_proactive_topic", ""),
            ("planned_event_chain", []),
            ("planned_opener_mode", ""),
            ("planned_followup_kind", ""),
            ("planned_proactive_quota_exempt", False),
            ("planned_candidate_id", ""),
        ):
            user[key] = value
        clear_trigger = getattr(self, "_clear_planned_proactive_trigger", None)
        if callable(clear_trigger):
            try:
                clear_trigger(user)
            except Exception:
                pass

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
            self._clear_user_rest_pending_plan_fallback(user)
        logger.info(
            "[PrivateCompanion] 已记录用户休息静默: user=%s until=%s reason=%s",
            user.get("user_id") or user.get("id") or "",
            self._environment_fromtimestamp(rest_until).strftime("%m-%d %H:%M"),
            _single_line(text, 80),
        )
        return True

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        global _private_companion_plugin
        _private_companion_plugin = self
        self.extension_api = PrivateCompanionExtensionAPI(self)
        self._external_proactive_abilities: dict[str, dict[str, Any]] = {}
        self.config = config
        c = config

        self.enabled = self._cfg_bool(c, "enabled", True)
        self.check_interval_seconds = self._cfg_int(c, "check_interval_seconds", 60, 30)
        self.idle_minutes = self._cfg_int(c, "idle_minutes", 60, 5)
        self.min_interval_minutes = self._cfg_int(c, "min_interval_minutes", 120, 10)
        self.timer_pre_silence_minutes = self._cfg_int(c, "timer_pre_silence_minutes", 20, 0, 240)
        self.max_daily_messages = self._cfg_int(c, "max_daily_messages", 8, 0, 12)
        self.inbound_message_debounce_seconds = self._cfg_float(c, "inbound_message_debounce_seconds", 3.0, 0.0)
        self.enable_recall_enhancement = self._cfg_bool(c, "enable_recall_enhancement", True)
        self.enable_recall_cancel_reply = self._cfg_bool(c, "enable_recall_cancel_reply", self.enable_recall_enhancement)
        self.enable_recall_message_cache = self._cfg_bool(c, "enable_recall_message_cache", True)
        self.enable_recall_transcribe_command = self._cfg_bool(c, "enable_recall_transcribe_command", True)
        self.recall_message_cache_ttl_seconds = self._cfg_float(c, "recall_message_cache_ttl_seconds", 600.0, 60.0)
        self.recall_message_cache_max_items = self._cfg_int(c, "recall_message_cache_max_items", 300, 0, 3000)
        self.recall_message_cache_text_chars = self._cfg_int(c, "recall_message_cache_text_chars", 500, 80, 2000)
        self.recall_cancel_reply_ttl_seconds = self.recall_message_cache_ttl_seconds
        self.enable_forbidden_word_recall = self._cfg_bool(c, "enable_forbidden_word_recall", False)
        self.recall_forbidden_words = self._parse_text_list_config(c.get("recall_forbidden_words", []), limit=300)
        self.recall_forbidden_word_case_sensitive = self._cfg_bool(c, "recall_forbidden_word_case_sensitive", False)
        self.recall_forbidden_scope = self._cfg_str(c, "recall_forbidden_scope", "bot_and_group", "bot_and_group").lower()
        if self.recall_forbidden_scope not in {"bot_only", "group_only", "bot_and_group"}:
            self.recall_forbidden_scope = "bot_and_group"
        self._recalled_message_ids: dict[str, dict[str, Any]] = {}
        self._recall_message_cache: dict[str, dict[str, Any]] = {}
        self.enable_message_debounce = self._cfg_bool(
            c,
            "enable_message_debounce",
            self._cfg_bool(c, "enable_semantic_message_debounce", True),
        )
        self.enable_semantic_message_debounce = self.enable_message_debounce
        legacy_semantic_debounce_seconds = self._cfg_float(c, "semantic_message_debounce_seconds", 8.0, 0.0)
        self.text_message_debounce_seconds = self._cfg_float(c, "text_message_debounce_seconds", 0.0, 0.0)
        self.image_message_debounce_seconds = self._cfg_float(c, "image_message_debounce_seconds", legacy_semantic_debounce_seconds, 0.0)
        self.forward_message_debounce_seconds = self._cfg_float(c, "forward_message_debounce_seconds", 0.0, 0.0)
        self.semantic_message_debounce_seconds = legacy_semantic_debounce_seconds
        self.private_image_vision_wait_seconds = self._cfg_float(c, "private_image_vision_wait_seconds", 30.0, 0.0)
        self.enable_private_image_self_recognition = self._cfg_bool(c, "enable_private_image_self_recognition", True)
        self.enable_private_image_vision_cache = self._cfg_bool(c, "enable_private_image_vision_cache", True)
        self.private_image_vision_cache_max_items = self._cfg_int(c, "private_image_vision_cache_max_items", 300, 0, 3000)
        self.enable_private_image_gif_enhancement = self._cfg_bool(c, "enable_private_image_gif_enhancement", True)
        self.private_image_gif_max_frames = self._cfg_int(c, "private_image_gif_max_frames", 4, 1, 8)
        self.enable_group_conversation_followup = self._cfg_bool(c, "enable_group_conversation_followup", True)
        self.group_conversation_followup_seconds = self._cfg_int(c, "group_conversation_followup_seconds", 120, 0, 600)
        self.group_conversation_followup_max_turns = self._cfg_int(c, "group_conversation_followup_max_turns", 1, 0, 10)
        self.quiet_hours = self._cfg_str(c, "quiet_hours", "23:00-08:30")
        self.default_style = self._cfg_str(c, "default_style", "温柔", "温柔")
        self.worldview_adaptation_mode = self._cfg_str(c, "worldview_adaptation_mode", "auto", "auto")
        if self.worldview_adaptation_mode not in {"auto", "modern", "fantasy", "sci_fi", "custom", "off"}:
            self.worldview_adaptation_mode = "auto"
        self.worldview_adaptation_prompt = self._cfg_str(c, "worldview_adaptation_prompt", "")
        self.default_nickname = self._cfg_str(c, "default_nickname", "你", "你")
        self.require_private_opt_in = self._cfg_bool(c, "require_private_opt_in", True)
        self.target_user_ids = c.get("target_user_ids", [])
        self.private_user_aliases = self._parse_private_user_aliases(c.get("private_user_aliases", ""))
        self._load_tts_enhancement_config(c)
        self.target_platform = self._cfg_str(c, "target_platform", "aiocqhttp", "aiocqhttp")
        self.default_enable_configured_targets = self._cfg_bool(c, "default_enable_configured_targets", True)
        self.enable_environment_perception = self._cfg_bool(c, "enable_environment_perception", True)
        timezone_default = self._cfg_str(c, "timezone", "Asia/Shanghai", "Asia/Shanghai")
        self.environment_perception_timezone = self._cfg_str(
            c,
            "environment_perception_timezone",
            timezone_default,
            "Asia/Shanghai",
        )
        _set_today_key_timezone(self.environment_perception_timezone)
        self.enable_holiday_perception = self._cfg_bool(c, "enable_holiday_perception", True)
        self.holiday_country = self._cfg_str(c, "holiday_country", "CN", "CN").upper()
        self.enable_platform_perception = self._cfg_bool(c, "enable_platform_perception", True)
        self.enable_model_perception = self._cfg_bool(c, "enable_model_perception", True)
        self.enable_lunar_perception = self._cfg_bool(c, "enable_lunar_perception", True)
        self.enable_solar_term_perception = self._cfg_bool(c, "enable_solar_term_perception", True)
        self.enable_almanac_perception = self._cfg_bool(c, "enable_almanac_perception", False)
        self.llm_provider_id = self._cfg_str(c, "LLM_PROVIDER_ID", "")
        self.daily_token_limit = self._cfg_int(c, "daily_token_limit", 1_000_000, 0)
        legacy_soft_enabled = self._cfg_bool(c, "enable_maintenance_token_saver", True)
        legacy_soft_limit = self._cfg_int(c, "maintenance_token_soft_limit", 800_000, 0)
        self.enable_daily_token_soft_limit = self._cfg_bool(c, "enable_daily_token_soft_limit", legacy_soft_enabled)
        self.daily_token_soft_limit = self._cfg_int(c, "daily_token_soft_limit", legacy_soft_limit, 0)
        self.enable_maintenance_token_saver = self.enable_daily_token_soft_limit
        self.maintenance_token_soft_limit = self.daily_token_soft_limit
        self.daily_plan_provider_id = self._cfg_str(c, "DAILY_PLAN_PROVIDER_ID", "")
        self.enable_daily_plan = self._cfg_bool(c, "enable_daily_plan", True)
        self.daily_plan_time = self._cfg_str(c, "daily_plan_time", "07:30")
        self.bot_name = self._cfg_str(c, "bot_name", "小星", "小星")
        self.include_schedule_in_messages = self._cfg_bool(c, "include_schedule_in_messages", True)
        self.daily_plan_prompt = self._cfg_str(c, "daily_plan_prompt", "")
        self.plugin_specific_persona_id = self._cfg_str(c, "plugin_specific_persona_id", "")
        self.schedule_persona_prompt = self._cfg_str(c, "schedule_persona_prompt", "")
        self.schedule_worldview_prompt = self._cfg_str(c, "schedule_worldview_prompt", "")
        self.roleplay_user_profile_prompt = self._cfg_str(c, "roleplay_user_profile_prompt", "")
        self.roleplay_knowledge_source_ids = self._normalize_roleplay_knowledge_source_ids(
            c.get("roleplay_knowledge_source_ids", [])
        )
        self.private_image_self_recognition_hint = self._cfg_str(c, "private_image_self_recognition_hint", "")
        self.daily_plan_item_count = self._cfg_int(c, "daily_plan_item_count", 10, 5, 16)
        self.enable_humanized_states = self._cfg_bool(c, "enable_humanized_states", True)
        self.enable_cycle_state = self._cfg_bool(c, "enable_cycle_state", True)
        self.humanized_state_intensity = self._cfg_int(c, "humanized_state_intensity", 50, 0, 100)
        self.enable_enhanced_dreams = self._cfg_bool(c, "enable_enhanced_dreams", False)
        self.dream_diary_provider_id = self._cfg_str(
            c,
            "DREAM_DIARY_PROVIDER_ID",
            self._cfg_str(c, "DREAM_PROVIDER_ID", self._cfg_str(c, "DIARY_PROVIDER_ID", "")),
        )
        self.dream_provider_id = self.dream_diary_provider_id
        self.diary_provider_id = self.dream_diary_provider_id
        self.dream_afterglow_mode = self._cfg_str(c, "dream_afterglow_mode", "auto", "auto")
        if self.dream_afterglow_mode not in {"auto", "轻", "标准", "明显"}:
            self.dream_afterglow_mode = "auto"
        self.enable_mixed_dream_themes = self._cfg_bool(c, "enable_mixed_dream_themes", True)
        self.enable_intimate_dream_theme = self._cfg_bool(c, "enable_intimate_dream_theme", False)
        self.dream_theme_candidates = self._cfg_str(
            c,
            "dream_theme_candidates",
            "温柔日常,奇幻,恐怖,追逐,悬疑,荒诞,怀旧,暧昧春梦",
        )
        self.inject_passive_states = self._cfg_bool(c, "inject_passive_states", True)
        self.proactive_share_probability = self._cfg_int(c, "proactive_share_probability", 45, 0, 100) / 100
        self.enable_daily_greetings = self._cfg_bool(c, "enable_daily_greetings", True)
        self.greeting_idle_minutes = self._cfg_int(c, "greeting_idle_minutes", 30, 0, 240)
        self.allow_insomnia_night_message = self._cfg_bool(c, "allow_insomnia_night_message", True)
        self.proactive_reply_context_hours = self._cfg_int(c, "proactive_reply_context_hours", 12, 1, 72)
        self.enable_creative_writing = self._cfg_bool(c, "enable_creative_writing", True)
        self.creative_inspiration_probability = min(1.0, self._cfg_float(c, "creative_inspiration_probability", 0.20, 0.0))
        self.creative_share_probability = min(1.0, self._cfg_float(c, "creative_share_probability", 0.28, 0.0))
        self.creative_chars_per_session = self._cfg_int(
            c,
            "creative_chars_per_session",
            self._cfg_int(c, "creative_base_chars_per_hour", 220, 60, 1200),
            60,
            1200,
        )
        self.creative_base_chars_per_hour = self.creative_chars_per_session
        self.creative_max_active_projects = self._cfg_int(c, "creative_max_active_projects", 2, 1, 5)
        self.creative_hidden_mode = self._cfg_bool(c, "creative_hidden_mode", True)
        self.creative_provider_id = self._cfg_str(c, "CREATIVE_PROVIDER_ID", "")
        self.voice_prompt_provider_id = self._cfg_str(c, "VOICE_PROMPT_PROVIDER_ID", "")
        self.history_summary_provider_id = self._cfg_str(c, "HISTORY_SUMMARY_PROVIDER_ID", "")
        self.enable_llm_proactive_message = self._cfg_bool(c, "enable_llm_proactive_message", True)
        self.enable_llm_timer_scheduling = self._cfg_bool(c, "enable_llm_timer_scheduling", True)
        self.enable_proactive_decorating_hooks = self._cfg_bool(c, "enable_proactive_decorating_hooks", True)
        self.enable_precise_platform_send = self._cfg_bool(c, "enable_precise_platform_send", True)
        self.enable_proactive_quote_trigger_message = self._cfg_bool(c, "enable_proactive_quote_trigger_message", False)
        self.enable_segmented_proactive_reply = self._cfg_bool(c, "enable_segmented_proactive_reply", False)
        self.segmented_proactive_scope = self._cfg_str(c, "segmented_proactive_scope", "proactive_only", "proactive_only")
        if self.segmented_proactive_scope not in {"proactive_only", "all_llm"}:
            self.segmented_proactive_scope = "proactive_only"
        self.segmented_proactive_threshold = self._cfg_int(c, "segmented_proactive_threshold", 500, 20, 500)
        self.segmented_proactive_min_segment_chars = self._cfg_int(c, "segmented_proactive_min_segment_chars", 8, 1, 40)
        self.segmented_proactive_max_segments = self._cfg_int(c, "segmented_proactive_max_segments", 3, 1, 8)
        self.segmented_proactive_split_mode = self._cfg_str(c, "segmented_proactive_split_mode", "regex", "regex")
        if self.segmented_proactive_split_mode not in {"regex", "words"}:
            self.segmented_proactive_split_mode = "regex"
        self.segmented_proactive_regex = str(c.get("segmented_proactive_regex", r".*?[。？！~…\n]+|.+$"))
        split_words = c.get("segmented_proactive_split_words", ["。", "？", "！", "~", "…", "“"])
        self.segmented_proactive_split_words = [str(item) for item in split_words] if isinstance(split_words, list) else ["。", "？", "！", "~", "…", "“"]
        self.enable_segmented_proactive_content_cleanup = self._cfg_bool(c, "enable_segmented_proactive_content_cleanup", False)
        self.segmented_proactive_content_cleanup_scope = self._cfg_str(c, "segmented_proactive_content_cleanup_scope", "all", "all")
        if self.segmented_proactive_content_cleanup_scope not in {"all", "trailing"}:
            self.segmented_proactive_content_cleanup_scope = "all"
        self.segmented_proactive_content_cleanup_rule = str(c.get("segmented_proactive_content_cleanup_rule", r"[\n]"))
        cleanup_words = c.get("segmented_proactive_content_cleanup_words", ["\n"])
        self.segmented_proactive_content_cleanup_words = (
            [str(item) for item in cleanup_words if str(item) != ""]
            if isinstance(cleanup_words, list)
            else ["\n"]
        )
        self.segmented_proactive_interval_method = self._cfg_str(c, "segmented_proactive_interval_method", "log", "log")
        if self.segmented_proactive_interval_method not in {"random", "log"}:
            self.segmented_proactive_interval_method = "log"
        self.segmented_proactive_interval_min = self._cfg_float(c, "segmented_proactive_interval_min", 1.5, 0.1)
        self.segmented_proactive_interval_max = self._cfg_float(c, "segmented_proactive_interval_max", 3.5, 0.1)
        self.segmented_proactive_log_base = self._cfg_float(c, "segmented_proactive_log_base", 1.8, 1.1)
        if self.segmented_proactive_interval_max < self.segmented_proactive_interval_min:
            self.segmented_proactive_interval_max = self.segmented_proactive_interval_min
        self.proactive_prompt_template = self._cfg_str(c, "proactive_prompt_template", "")
        self.max_proactive_plan_lag_minutes = self._cfg_int(c, "max_proactive_plan_lag_minutes", 180, 5, 1440)
        self._recent_inbound_message_debounce: dict[str, float] = {}
        self._semantic_message_buffers: dict[str, dict[str, Any]] = {}
        self.enable_detail_enhancement = self._cfg_bool(c, "enable_detail_enhancement", False)
        self.detail_enhancement_provider_id = self._cfg_str(c, "DETAIL_ENHANCEMENT_PROVIDER_ID", "")
        self.narration_provider_id = self._cfg_str(c, "NARRATION_PROVIDER_ID", "")
        self.photo_prompt_provider_id = self._cfg_str(c, "PHOTO_PROMPT_PROVIDER_ID", "")
        self.comfyui_photo_workflow_name = self._cfg_str(c, "COMFYUI_PHOTO_WORKFLOW_NAME", "")
        self.comfyui_text2img_workflow_name = self._cfg_str(c, "COMFYUI_TEXT2IMG_WORKFLOW_NAME", self.comfyui_photo_workflow_name)
        self.comfyui_selfie_workflow_name = self._cfg_str(c, "COMFYUI_SELFIE_WORKFLOW_NAME", self.comfyui_photo_workflow_name)
        self.comfyui_photo_wait_seconds = self._cfg_int(c, "comfyui_photo_wait_seconds", 90, 5, 600)
        self.photo_generation_backend = self._cfg_str(c, "photo_generation_backend", "auto", "auto").strip().lower()
        if self.photo_generation_backend not in {"auto", "comfyui", "sdgen", "external"}:
            self.photo_generation_backend = "auto"
        self.enable_local_photo_load_guard = self._cfg_bool(c, "enable_local_photo_load_guard", True)
        self.local_photo_cpu_busy_percent = self._cfg_int(c, "local_photo_cpu_busy_percent", 85, 1, 100)
        self.local_photo_memory_busy_percent = self._cfg_int(c, "local_photo_memory_busy_percent", 88, 1, 100)
        self.local_photo_defer_minutes = self._cfg_int(c, "local_photo_defer_minutes", 30, 1, 240)
        self._local_photo_load_cache: dict[str, Any] = {}
        self.external_image_api_base_url = self._cfg_str(c, "EXTERNAL_IMAGE_API_BASE_URL", "")
        self.external_image_api_key = self._cfg_str(c, "EXTERNAL_IMAGE_API_KEY", "")
        self.external_image_api_model = self._cfg_str(c, "EXTERNAL_IMAGE_API_MODEL", "")
        self.external_image_api_size = self._cfg_str(c, "external_image_api_size", "1024x1024", "1024x1024")
        self.external_image_api_timeout_seconds = self._cfg_int(c, "external_image_api_timeout_seconds", 180, 20, 600)
        self.photo_generation_style = self._cfg_str(c, "photo_generation_style", "真实", "真实")
        self.photo_generation_style_custom_prompt = self._cfg_str(c, "photo_generation_style_custom_prompt", "")
        self.enable_weather_context = self._cfg_bool(c, "enable_weather_context", True)
        self.weather_api_key = self._cfg_str(c, "weather_api_key", "")
        self.weather_city = self._cfg_str(c, "weather_city", "")
        self.weather_lat = self._cfg_float(c, "weather_lat", 0.0, -90.0)
        self.weather_lon = self._cfg_float(c, "weather_lon", 0.0, -180.0)
        self.weather_refresh_minutes = self._cfg_int(c, "weather_refresh_minutes", 90, 10, 720)
        self.enable_yesterday_screen_diary_context = self._cfg_bool(c, "enable_yesterday_screen_diary_context", True)
        self.screen_diary_context_max_chars = self._cfg_int(c, "screen_diary_context_max_chars", 700, 200, 1600)
        self.detail_enhancement_lead_minutes = self._cfg_int(c, "detail_enhancement_lead_minutes", 3, 0, 180)
        self.enable_daily_diary = self._cfg_bool(c, "enable_daily_diary", True)
        self.daily_diary_time = self._cfg_str(c, "daily_diary_time", "23:10")
        self.max_diary_entries = self._cfg_int(c, "max_diary_entries", 14, 1, 60)
        self.important_date_lookahead_days = self._cfg_int(c, "important_date_lookahead_days", 7, 0, 60)
        legacy_actions = self._parse_action_list(c.get("enabled_proactive_actions", None))
        legacy_photo_enabled = "photo_text" in legacy_actions if legacy_actions else True
        legacy_screen_enabled = "screen_peek" in legacy_actions if legacy_actions else False
        legacy_poke_enabled = "poke" in legacy_actions if legacy_actions else False
        legacy_voice_enabled = "voice" in legacy_actions if legacy_actions else False
        self.enable_photo_text_action = self._cfg_bool(
            c, "enable_photo_text_action", bool(c.get("allow_photo_text_action", legacy_photo_enabled))
        )
        self.enable_screen_glance_action = self._cfg_bool(
            c, "enable_screen_glance_action", bool(c.get("allow_screen_peek_action", legacy_screen_enabled))
        )
        self.enable_poke_action = self._cfg_bool(
            c, "enable_poke_action", bool(c.get("allow_poke_action", legacy_poke_enabled))
        )
        self.enable_voice_action = self._cfg_bool(
            c, "enable_voice_action", bool(c.get("allow_voice_action", legacy_voice_enabled))
        )
        self.enable_qq_presence_sync = self._cfg_bool(c, "enable_qq_presence_sync", True)
        self.poke_action_max_times = self._cfg_int(c, "poke_action_max_times", 1, 1, 3)
        self.voice_action_max_chars = self._cfg_int(c, "voice_action_max_chars", 30, 6, 80)
        self.photo_action_max_daily = self._cfg_int(c, "photo_action_max_daily", 1, 0, 5)
        self.screen_peek_max_daily = self._cfg_int(c, "screen_peek_max_daily", 1, 0, 5)
        self.screen_peek_cooldown_minutes = self._cfg_int(c, "screen_peek_cooldown_minutes", 240, 0, 1440)
        self.enable_unanswered_screen_peek_followup = self._cfg_bool(c, "enable_unanswered_screen_peek_followup", True)
        self.unanswered_screen_peek_after_minutes = self._cfg_int(c, "unanswered_screen_peek_after_minutes", 45, 10, 240)
        self.unanswered_screen_peek_cooldown_minutes = self._cfg_int(c, "unanswered_screen_peek_cooldown_minutes", 180, 30, 1440)
        self.enable_mai_style_integration = self._cfg_bool(c, "enable_mai_style_integration", True)
        self.enable_companion_memory = self._cfg_bool(c, "enable_companion_memory", True)
        self.enable_expression_learning = self._cfg_bool(c, "enable_expression_learning", True)
        self.enable_companion_reply_planner = self._cfg_bool(c, "enable_companion_reply_planner", True)
        self.enable_intent_emotion_analysis = self._cfg_bool(c, "enable_intent_emotion_analysis", True)
        self.enable_response_self_review = self._cfg_bool(c, "enable_response_self_review", True)
        self.enable_passive_topic_suppression = self._cfg_bool(c, "enable_passive_topic_suppression", True)
        self.enable_relationship_state_machine = self._cfg_bool(c, "enable_relationship_state_machine", True)
        self.enable_dialogue_episode_memory = self._cfg_bool(c, "enable_dialogue_episode_memory", True)
        self.enable_open_loop_tracking = self._cfg_bool(c, "enable_open_loop_tracking", True)
        self.enable_user_habit_learning = self._cfg_bool(c, "enable_user_habit_learning", True)
        self.user_habit_min_count = self._cfg_int(c, "user_habit_min_count", 3, 2, 20)
        self.user_habit_max_items = self._cfg_int(c, "user_habit_max_items", 24, 8, 80)
        self.enable_skill_growth_simulation = self._cfg_bool(c, "enable_skill_growth_simulation", True)
        self.skill_growth_rate = self._cfg_float(c, "skill_growth_rate", 1.0, 0.1)
        self.skill_growth_custom_skills = self._cfg_str(c, "skill_growth_custom_skills", "")
        self.enable_skill_growth_schedule_influence = self._cfg_bool(c, "enable_skill_growth_schedule_influence", True)
        self.skill_growth_schedule_influence_strength = max(0.0, min(1.0, self._cfg_float(c, "skill_growth_schedule_influence_strength", 0.35, 0.0)))
        self.memory_refresh_interval_minutes = self._cfg_int(c, "memory_refresh_interval_minutes", 360, 30, 4320)
        self.max_companion_memory_items = self._cfg_int(c, "max_companion_memory_items", 36, 8, 120)
        self.max_learned_expression_items = self._cfg_int(c, "max_learned_expression_items", 18, 4, 60)
        self.mai_style_provider_id = self._cfg_str(c, "MAI_STYLE_PROVIDER_ID", "")
        self.companion_memory_provider_id = self._cfg_str(c, "COMPANION_MEMORY_PROVIDER_ID", "")
        self.dialogue_episode_provider_id = self._cfg_str(c, "DIALOGUE_EPISODE_PROVIDER_ID", "")
        self.relationship_analysis_provider_id = self._cfg_str(c, "RELATIONSHIP_ANALYSIS_PROVIDER_ID", "")
        self.response_review_provider_id = self._cfg_str(c, "RESPONSE_REVIEW_PROVIDER_ID", "")
        self.response_review_max_chars = self._cfg_int(c, "response_review_max_chars", 260, 80, 900)
        self.passive_topic_memory_hours = self._cfg_int(c, "passive_topic_memory_hours", 8, 1, 72)
        self.episode_memory_refresh_messages = self._cfg_int(c, "episode_memory_refresh_messages", 8, 3, 40)
        self.episode_memory_refresh_minutes = self._cfg_int(c, "episode_memory_refresh_minutes", 90, 15, 1440)
        self.max_dialogue_episodes = self._cfg_int(c, "max_dialogue_episodes", 12, 3, 40)
        self.enable_group_companion = self._cfg_bool(c, "enable_group_companion", True)
        self.group_access_mode = self._cfg_str(c, "group_access_mode", "whitelist", "whitelist").lower()
        if self.group_access_mode not in {"whitelist", "blacklist"}:
            self.group_access_mode = "whitelist"
        self.target_group_ids = c.get("target_group_ids", [])
        self.group_whitelist_ids = c.get("group_whitelist_ids", self.target_group_ids)
        self.group_blacklist_ids = c.get("group_blacklist_ids", [])
        self.require_target_group = self._cfg_bool(c, "require_target_group", True)
        self.enable_group_slang_learning = self._cfg_bool(c, "enable_group_slang_learning", True)
        self.enable_group_member_profiles = self._cfg_bool(c, "enable_group_member_profiles", True)
        self.enable_group_context_injection = self._cfg_bool(c, "enable_group_context_injection", True)
        self.enable_group_persona_denoise = self._cfg_bool(c, "enable_group_persona_denoise", True)
        self.enable_forward_message_adaptation = self._cfg_bool(c, "enable_forward_message_adaptation", True)
        self.forward_message_mode = self._cfg_str(c, "forward_message_mode", "inject", "inject").lower()
        if self.forward_message_mode in {"注入", "injection"}:
            self.forward_message_mode = "inject"
        elif self.forward_message_mode in {"转述", "summary", "summarize", "narrate", "relay"}:
            self.forward_message_mode = "transcribe"
        elif self.forward_message_mode not in {"inject", "transcribe"}:
            self.forward_message_mode = "inject"
        self.forward_message_provider_id = self._cfg_str(c, "FORWARD_MESSAGE_PROVIDER_ID", "")
        self.forward_message_max_messages = self._cfg_int(c, "forward_message_max_messages", 80, 5, 300)
        self.forward_message_max_chars = self._cfg_int(c, "forward_message_max_chars", 5000, 800, 20000)
        self.forward_message_parse_nested = self._cfg_bool(c, "forward_message_parse_nested", True)
        self.forward_message_image_vision = self._cfg_bool(c, "forward_message_image_vision", True)
        self.forward_message_image_limit = self._cfg_int(c, "forward_message_image_limit", 4, 0, 12)
        self.forward_message_image_vision_timeout_seconds = self._cfg_float(c, "forward_message_image_vision_timeout_seconds", 6.0, 0.0)
        self.enable_group_scene_awareness = self._cfg_bool(c, "enable_group_scene_awareness", True)
        self.group_scene_recent_limit = self._cfg_int(c, "group_scene_recent_limit", 5, 2, 12)
        self.enable_group_reality_promise_guard = self._cfg_bool(c, "enable_group_reality_promise_guard", True)
        self.enable_group_wakeup_enhancement = self._cfg_bool(c, "enable_group_wakeup_enhancement", True)
        self.group_wakeup_direct_words = self._parse_text_list_config(c.get("group_wakeup_direct_words", []))
        self.group_wakeup_context_words = self._parse_text_list_config(
            c.get("group_wakeup_context_words", ["机器人", "bot"])
        )
        if self.group_wakeup_context_words == ["有人叫你", "提到你", "说到你", "机器人", "AI"]:
            self.group_wakeup_context_words = ["机器人", "bot"]
        self.group_wakeup_interest_keywords = self._parse_text_list_config(c.get("group_wakeup_interest_keywords", []))
        self.group_wakeup_interest_probability = self._cfg_int(c, "group_wakeup_interest_probability", 18, 0, 100) / 100
        self.group_wakeup_cooldown_seconds = self._cfg_int(c, "group_wakeup_cooldown_seconds", 90, 0, 3600)
        self.group_wakeup_generated_keyword_limit = self._cfg_int(c, "group_wakeup_generated_keyword_limit", 24, 4, 80)
        self.group_wakeup_topic_interest_max_boost = self._cfg_int(c, "group_wakeup_topic_interest_max_boost", 45, 0, 150) / 100
        self.group_wakeup_debounce_pending_penalty = self._cfg_int(c, "group_wakeup_debounce_pending_penalty", 65, 0, 100) / 100
        self.group_wakeup_fatigue_limit = self._cfg_int(c, "group_wakeup_fatigue_limit", 5, 1, 20)
        self.group_wakeup_fatigue_decay_minutes = self._cfg_int(c, "group_wakeup_fatigue_decay_minutes", 90, 5, 720)
        self.group_wakeup_log_limit = self._cfg_int(c, "group_wakeup_log_limit", 80, 10, 300)
        self.enable_group_high_intensity_mode = self._cfg_bool(c, "enable_group_high_intensity_mode", True)
        self.group_high_intensity_wakeup_window_seconds = self._cfg_int(c, "group_high_intensity_wakeup_window_seconds", 60, 15, 600)
        self.group_high_intensity_wakeup_threshold = self._cfg_int(c, "group_high_intensity_wakeup_threshold", 3, 2, 20)
        self.group_high_intensity_cooldown_seconds = self._cfg_int(c, "group_high_intensity_cooldown_seconds", 150, 30, 1800)
        self.group_high_intensity_merge_seconds = self._cfg_int(c, "group_high_intensity_merge_seconds", 8, 1, 30)
        self.enable_group_interjection = self._cfg_bool(c, "enable_group_interjection", False)
        self.enable_group_repeat_follow = self._cfg_bool(c, "enable_group_repeat_follow", True)
        self.group_repeat_follow_probability = self._cfg_int(c, "group_repeat_follow_probability", 18, 0, 100) / 100
        self.group_repeat_interrupt_probability = self._cfg_int(c, "group_repeat_interrupt_probability", 10, 0, 100) / 100
        self.group_repeat_interrupt_probability_step = self._cfg_int(c, "group_repeat_interrupt_probability_step", 12, 0, 100) / 100
        self.group_repeat_interrupt_text = self._cfg_str(c, "group_repeat_interrupt_text", "禁止复读", "禁止复读")
        self.group_repeat_interrupt_image_path = self._cfg_str(c, "group_repeat_interrupt_image_path", "")
        self.group_interject_min_interval_minutes = self._cfg_int(c, "group_interject_min_interval_minutes", 180, 10, 1440)
        self.group_interject_max_daily = self._cfg_int(c, "group_interject_max_daily", 2, 0, 12)
        self.max_group_recent_messages = self._cfg_int(c, "max_group_recent_messages", 80, 20, 300)
        self.max_group_slang_terms = self._cfg_int(c, "max_group_slang_terms", 40, 8, 160)
        self.enable_group_topic_threads = self._cfg_bool(c, "enable_group_topic_threads", True)
        self.enable_group_episode_memory = self._cfg_bool(c, "enable_group_episode_memory", True)
        self.enable_group_interjection_feedback = self._cfg_bool(c, "enable_group_interjection_feedback", True)
        self.enable_group_slang_meanings = self._cfg_bool(c, "enable_group_slang_meanings", True)
        self.enable_group_relationship_graph = self._cfg_bool(c, "enable_group_relationship_graph", True)
        self.enable_group_privacy_guard = self._cfg_bool(c, "enable_group_privacy_guard", True)
        self.enable_worldbook_member_recognition = self._cfg_bool(c, "enable_worldbook_member_recognition", True)
        self.enable_atrelay_tools = self._cfg_bool(c, "enable_atrelay_tools", True)
        self.atrelay_require_worldbook_first = self._cfg_bool(c, "atrelay_require_worldbook_first", True)
        self.atrelay_member_cache_minutes = self._cfg_int(c, "atrelay_member_cache_minutes", 60, 1, 1440)
        self.atrelay_sensitive_confirm = self._cfg_bool(c, "atrelay_sensitive_confirm", True)
        self.atrelay_default_relay_style = self._cfg_str(c, "atrelay_default_relay_style", "persona", "persona")
        self.atrelay_multi_target_limit = self._cfg_int(c, "atrelay_multi_target_limit", 5, 1, 20)
        self.worldbook_auto_import = self._cfg_bool(c, "worldbook_auto_import", True)
        self.worldbook_member_match_aliases = self._cfg_bool(c, "worldbook_member_match_aliases", True)
        self.worldbook_self_registration = self._cfg_bool(c, "worldbook_self_registration", True)
        self.worldbook_auto_pending_observations = self._cfg_bool(c, "worldbook_auto_pending_observations", True)
        self.worldbook_member_inject_limit = self._cfg_int(c, "worldbook_member_inject_limit", 6, 1, 20)
        self.worldbook_config_paths = self._cfg_str(c, "worldbook_config_paths", "")
        self.group_interject_provider_id = self._cfg_str(c, "GROUP_INTERJECT_PROVIDER_ID", "")
        self.group_episode_provider_id = self._cfg_str(c, "GROUP_EPISODE_PROVIDER_ID", "")
        self.group_slang_provider_id = self._cfg_str(c, "GROUP_SLANG_PROVIDER_ID", "")
        self.group_followup_judge_provider_id = self._cfg_str(c, "GROUP_FOLLOWUP_JUDGE_PROVIDER_ID", "")
        self.enable_livingmemory_integration = self._cfg_bool(c, "enable_livingmemory_integration", True)
        self.livingmemory_tool_name = self._cfg_str(c, "livingmemory_tool_name", "recall_long_term_memory", "recall_long_term_memory")
        self.enable_bilibili_integration = self._cfg_bool(c, "enable_bilibili_integration", True)
        self.enable_bilibili_boredom_watch = self._cfg_bool(c, "enable_bilibili_boredom_watch", True)
        self.bilibili_boredom_min_interval_hours = self._cfg_int(c, "bilibili_boredom_min_interval_hours", 8, 2, 72)
        self.bilibili_share_probability = min(1.0, self._cfg_float(c, "bilibili_share_probability", 0.35, 0.0))
        self.bilibili_share_min_score = self._cfg_int(c, "bilibili_share_min_score", 7, 0, 10)
        self.enable_news_integration = self._cfg_bool(c, "enable_news_integration", False)
        self.enable_news_boredom_read = self._cfg_bool(c, "enable_news_boredom_read", True)
        self.enable_news_daily_hot_read = self._cfg_bool(c, "enable_news_daily_hot_read", self._cfg_bool(c, "enable_hot_trend_sources", True))
        self.news_min_interval_hours = self._cfg_int(c, "news_min_interval_hours", 6, 1, 72)
        self.news_share_probability = min(1.0, self._cfg_float(c, "news_share_probability", 0.22, 0.0))
        self.enable_external_event_self_link = self._cfg_bool(c, "enable_external_event_self_link", True)
        self.external_event_self_link_probability = min(1.0, self._cfg_float(c, "external_event_self_link_probability", 0.62, 0.0))
        self.external_event_self_link_cooldown_hours = self._cfg_int(c, "external_event_self_link_cooldown_hours", 12, 1, 168)
        self.news_max_items_per_source = self._cfg_int(c, "news_max_items_per_source", 5, 1, 20)
        self.news_hot_sources = self._cfg_str(c, "news_hot_sources", self._cfg_str(c, "hot_trend_sources", "weibo,hackernews"))
        self.news_hot_max_items = self._cfg_int(c, "news_hot_max_items", self._cfg_int(c, "hot_trend_max_items", 12, 3, 30), 3, 30)
        self.enable_ai_daily_watch = self._cfg_bool(c, "enable_ai_daily_watch", True)
        self.ai_daily_sources = self._cfg_str(c, "ai_daily_sources", DEFAULT_AI_DAILY_SOURCES)
        self.ai_daily_source_uid = re.sub(r"\D+", "", self._cfg_str(c, "ai_daily_source_uid", "285286947")) or "285286947"
        self.ai_daily_check_window = self._cfg_str(c, "ai_daily_check_window", "07:30-12:30")
        self.ai_daily_check_interval_minutes = self._cfg_int(c, "ai_daily_check_interval_minutes", 40, 10, 240)
        self.ai_daily_prefer_text_version = self._cfg_bool(c, "ai_daily_prefer_text_version", True)
        self.news_sources = self._cfg_str(
            c,
            "news_sources",
            DEFAULT_NEWS_SOURCES,
        )
        if str(self.news_sources or "").strip() in {LEGACY_DEFAULT_NEWS_SOURCES, PREVIOUS_TECH_DEFAULT_NEWS_SOURCES}:
            self.news_sources = DEFAULT_NEWS_SOURCES
        self.news_provider_id = self._cfg_str(c, "NEWS_PROVIDER_ID", "")
        self.enable_web_exploration = self._cfg_bool(c, "enable_web_exploration", False)
        self.enable_web_exploration_boredom_search = self._cfg_bool(c, "enable_web_exploration_boredom_search", True)
        self.web_exploration_min_interval_hours = self._cfg_int(c, "web_exploration_min_interval_hours", 8, 1, 168)
        self.web_exploration_share_probability = min(1.0, self._cfg_float(c, "web_exploration_share_probability", 0.18, 0.0))
        self.web_exploration_max_results = self._cfg_int(c, "web_exploration_max_results", 6, 3, 20)
        self.web_exploration_interests = self._cfg_str(
            c,
            "web_exploration_interests",
            "按 Bot 人格自行决定；可偏向最近聊天、日程、人设兴趣、作品、技术、生活小知识、流行梗、时讯、新鲜事物。",
        )
        self.web_exploration_provider_id = self._cfg_str(c, "WEB_EXPLORATION_PROVIDER_ID", "")
        self.enable_qzone_integration = self._cfg_bool(c, "enable_qzone_integration", True)
        self.qzone_cookie = self._cfg_str(c, "QZONE_COOKIE", "")
        self.enable_qzone_life_publish = self._cfg_bool(c, "enable_qzone_life_publish", False)
        self.qzone_life_publish_min_interval_hours = self._cfg_int(c, "qzone_life_publish_min_interval_hours", 24, 4, 168)
        self.qzone_life_publish_probability = min(1.0, self._cfg_float(c, "qzone_life_publish_probability", 0.18, 0.0))
        self.enable_jm_cosmos_integration = self._cfg_bool(
            c,
            "enable_private_reading_integration",
            self._cfg_bool(c, "enable_jm_cosmos_integration", False),
        )
        self.enable_jm_cosmos_boredom_read = self._cfg_bool(
            c,
            "enable_private_reading_boredom_read",
            self._cfg_bool(c, "enable_jm_cosmos_boredom_read", False),
        )
        self.enable_private_reading_ask_recommendation = self._cfg_bool(
            c,
            "enable_private_reading_ask_recommendation",
            False,
        )
        self.jm_cosmos_min_interval_hours = self._cfg_int(
            c,
            "private_reading_min_interval_hours",
            self._cfg_int(c, "jm_cosmos_min_interval_hours", 18, 4, 168),
            4,
            168,
        )
        self.jm_cosmos_max_photo_count = self._cfg_int(
            c,
            "private_reading_max_photo_count",
            self._cfg_int(c, "jm_cosmos_max_photo_count", 60, 8, 120),
            8,
            120,
        )
        self.jm_cosmos_share_probability = min(
            1.0,
            self._cfg_float(
                c,
                "private_reading_share_probability",
                self._cfg_float(c, "jm_cosmos_share_probability", 0.18, 0.0),
                0.0,
            ),
        )
        self.private_reading_ask_probability = min(
            1.0,
            self._cfg_float(c, "private_reading_ask_probability", 0.16, 0.0),
        )
        self.enable_private_reading_preference_influence = self._cfg_bool(
            c,
            "enable_private_reading_preference_influence",
            True,
        )
        self.private_reading_preference_min_ratings = self._cfg_int(
            c,
            "private_reading_preference_min_ratings",
            5,
            1,
            30,
        )
        self.private_reading_preference_max_terms = self._cfg_int(
            c,
            "private_reading_preference_max_terms",
            8,
            2,
            20,
        )
        self.jm_cosmos_default_keywords = self._cfg_str(
            c,
            "private_reading_default_keywords",
            self._cfg_str(c, "jm_cosmos_default_keywords", "纯爱,恋爱,同人"),
        )
        self.private_reading_blocked_tags = self._cfg_str(
            c,
            "private_reading_blocked_tags",
            self._cfg_str(c, "jm_cosmos_blocked_tags", "連載中,長篇,青年漫"),
        )
        self.plugin_vision_provider_id = self._cfg_str(c, "PLUGIN_VISION_PROVIDER_ID", "")
        self.jm_cosmos_vision_provider_id = self._cfg_str(
            c,
            "PRIVATE_READING_VISION_PROVIDER_ID",
            self._cfg_str(c, "JM_COSMOS_VISION_PROVIDER_ID", ""),
        )
        if isinstance(c, dict):
            legacy_private_reading_keys = {
                "enable_jm_cosmos_integration": "enable_private_reading_integration",
                "enable_jm_cosmos_boredom_read": "enable_private_reading_boredom_read",
                "jm_cosmos_min_interval_hours": "private_reading_min_interval_hours",
                "jm_cosmos_max_photo_count": "private_reading_max_photo_count",
                "jm_cosmos_share_probability": "private_reading_share_probability",
                "jm_cosmos_default_keywords": "private_reading_default_keywords",
                "jm_cosmos_blocked_tags": "private_reading_blocked_tags",
                "JM_COSMOS_VISION_PROVIDER_ID": "PRIVATE_READING_VISION_PROVIDER_ID",
            }
            for old_key, new_key in legacy_private_reading_keys.items():
                if old_key in c:
                    if new_key not in c:
                        c[new_key] = c.get(old_key)
                    c.pop(old_key, None)
        self.group_episode_refresh_minutes = self._cfg_int(c, "group_episode_refresh_minutes", 180, 30, 1440)
        self.group_slang_summary_minutes = self._cfg_int(c, "group_slang_summary_minutes", 360, 60, 2880)
        self.max_group_topic_threads = self._cfg_int(c, "max_group_topic_threads", 12, 3, 40)
        self.max_group_episodes = self._cfg_int(c, "max_group_episodes", 10, 3, 40)
        self.max_group_relationship_edges = self._cfg_int(c, "max_group_relationship_edges", 80, 10, 300)
        # Backward-compatible aliases for stored daily plans and older code paths.
        self.allow_photo_text_action = self.enable_photo_text_action
        self.allow_screen_peek_action = self.enable_screen_glance_action
        self.allow_poke_action = self.enable_poke_action
        self.allow_voice_action = self.enable_voice_action

        self.data_dir = StarTools.get_data_dir(PLUGIN_NAME)
        os.makedirs(self.data_dir, exist_ok=True)
        self._patch_livingmemory_processor_compat()
        self._disable_integrated_features_when_external_plugins_present()
        self.data_file = os.path.join(self.data_dir, "companions.json")
        self._data_lock = asyncio.Lock()
        self._conversation_db_lock = asyncio.Lock()
        self._framework_agent_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._default_persona_prompt_cache = ""
        self._default_persona_prompt_cache_at = 0.0
        self._default_persona_prompt_cache_umo = ""
        self._default_persona_prompt_cache_persona_id = ""
        self._default_persona_prompt_refresh_task: asyncio.Task | None = None
        self._passive_light_injection_cache: dict[str, Any] = {}
        self._data_save_task: asyncio.Task | None = None
        self._data_save_dirty = False
        self._framework_captured_send_cache: dict[str, list[Any]] = {}
        self._last_input_status_at: dict[str, float] = {}
        self._passive_input_status_tasks: dict[str, asyncio.Task] = {}
        self._recent_inbound_activity_by_scope: dict[str, dict[str, Any]] = {}
        self.data = self._load_data_sync()
        self._apply_tts_runtime_overrides()
        if self._merge_private_user_alias_records():
            self._save_data_sync()
        if self._cleanup_all_group_slang_terms():
            self._save_data_sync()
        if self.worldbook_auto_import:
            try:
                if self._import_worldbook_entries_from_sources():
                    self._save_data_sync()
            except Exception as e:
                logger.warning(f"[PrivateCompanion] 刷新关系网失败: {e}", exc_info=True)
        if self.default_enable_configured_targets:
            self._sync_configured_targets()
            self._save_data_sync()
        self.page_api = None
        self._register_page_api_if_available()

    async def initialize(self):
        if not self.enabled:
            logger.info("[PrivateCompanion] 插件总开关已关闭,不启动主动消息循环")
            return
        self._schedule_default_persona_prompt_refresh()
        async with self._data_lock:
            if self._prime_enabled_user_schedules():
                self._save_data_sync()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._scheduler_loop())
            logger.info("[PrivateCompanion] 主动消息循环已启动")
        asyncio.create_task(self._reset_stale_qq_presence_if_needed())
        asyncio.create_task(self._startup_prepare_today())
        asyncio.create_task(self._refresh_passive_injection_cache())

    async def terminate(self):
        global _private_companion_plugin
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        for task in list(self._passive_input_status_tasks.values()):
            if isinstance(task, asyncio.Task) and not task.done():
                task.cancel()
        self._passive_input_status_tasks.clear()
        save_task = getattr(self, "_data_save_task", None)
        if isinstance(save_task, asyncio.Task) and not save_task.done():
            save_task.cancel()
            try:
                await save_task
            except asyncio.CancelledError:
                pass
        async with self._data_lock:
            self._save_data_sync()
        if _private_companion_plugin is self:
            _private_companion_plugin = None

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def observe_recall_enhancement_events(self, event: AstrMessageEvent):
        """记录普通消息和 QQ/OneBot 撤回事件，用于撤回增强。"""
        if not self.enabled:
            return
        self._note_inbound_activity_for_scope(event)
        if not self.enable_recall_enhancement:
            return
        raw = self._event_raw_payload(event)
        if raw.get("post_type") == "notice":
            notice_type = str(raw.get("notice_type") or "").strip()
            if notice_type not in {"friend_recall", "group_recall"}:
                return
            message_id = _single_line(raw.get("message_id") or raw.get("msg_id"), 120)
            if not message_id:
                return
            scope = _single_line(
                (f"group:{raw.get('group_id')}" if raw.get("group_id") else "")
                or (f"private:{raw.get('user_id')}" if raw.get("user_id") else "")
                or getattr(event, "unified_msg_origin", ""),
                160,
            )
            self._record_recalled_message_id(message_id, scope=scope, notice_type=notice_type)
            if notice_type == "friend_recall":
                recall_user_id = _single_line(raw.get("user_id"), 80)
                if recall_user_id:
                    self._stop_passive_input_status_loop(recall_user_id)
                    logger.info(
                        "[PrivateCompanion] 用户撤回消息，已停止私聊输入状态: user=%s message_id=%s",
                        recall_user_id,
                        message_id,
                    )
            logger.info(
                "[PrivateCompanion] 已记录消息撤回: notice=%s scope=%s message_id=%s",
                notice_type,
                scope or "-",
                message_id,
            )
            return

        self._cache_message_for_recall(event)
        if not self.enable_forbidden_word_recall or not self._forbidden_recall_words():
            return
        message_id = self._event_message_id(event)
        if not message_id:
            return
        is_group = bool(self._extract_group_id_from_event(event))
        is_self = self._event_sender_id(event) and self._event_sender_id(event) == self._event_self_id(event)
        scope = self.recall_forbidden_scope
        if scope == "bot_only" and not is_self:
            return
        if scope == "group_only" and not is_group:
            return
        if scope == "bot_and_group" and not (is_self or is_group):
            return
        text = self._event_text_for_recall_cache(event, limit=2000)
        hit = self._forbidden_recall_hit(text)
        if not hit:
            return
        ok = await self._try_delete_message(event, message_id, reason=f"forbidden:{hit}")
        logger.info(
            "[PrivateCompanion] 违禁词撤回检查命中: scope=%s self=%s group=%s ok=%s word=%s message_id=%s",
            scope,
            is_self,
            is_group,
            ok,
            _single_line(hit, 40),
            message_id,
        )

    @filter.on_decorating_result()
    async def stop_passive_input_status_before_private_send(self, event: AstrMessageEvent):
        """私聊 LLM 回复进入发送前阶段时停止持续输入状态。"""
        if not self.enabled:
            return
        if not bool(getattr(event, "is_private_chat", lambda: False)()):
            return
        self._stop_passive_input_status_loop(event)

    @filter.on_decorating_result()
    async def strip_outbound_control_blocks_before_send(self, event: AstrMessageEvent):
        """发送前兜底清理内部控制块，避免 timer/TTSBLOCK 泄漏到聊天。"""
        if not self.enabled:
            return
        result = event.get_result()
        chain = list(getattr(result, "chain", []) or []) if result is not None else []
        if not chain:
            return
        changed = False
        for comp in chain:
            if not isinstance(comp, Plain):
                continue
            original = str(getattr(comp, "text", "") or "")
            cleaned = _strip_outbound_control_blocks(original)
            if cleaned != original:
                changed = True
                try:
                    comp.text = cleaned
                except Exception:
                    pass
        if changed:
            logger.warning(
                "[PrivateCompanion] 发送前已清理内部控制标签: session=%s",
                _single_line(getattr(event, "unified_msg_origin", ""), 120) or "unknown",
            )

    @filter.on_decorating_result()
    async def cancel_reply_if_trigger_recalled_before_send(self, event: AstrMessageEvent):
        """若触发/唤醒消息在回复发出前被撤回，则静默取消本次回复。"""
        if not self.enabled:
            return
        recalled_message_id = await self._should_cancel_reply_for_missing_or_recalled_trigger(event)
        if not recalled_message_id:
            return
        logger.info(
            "[PrivateCompanion] 触发消息已撤回或发送前不可见，取消本次发送: session=%s message_id=%s",
            _single_line(getattr(event, "unified_msg_origin", ""), 120) or "unknown",
            recalled_message_id,
        )
        empty_result = self._build_result_from_chain([])
        try:
            empty_result.stop_event()
        except Exception:
            pass
        event.set_result(empty_result)
        event.stop_event()

    @filter.on_decorating_result()
    async def suppress_forbidden_outbound_before_send(self, event: AstrMessageEvent):
        """自己的待发送消息命中违禁词时，优先在发送前拦截。"""
        if not self.enabled:
            return
        if not self.enable_recall_enhancement or not self.enable_forbidden_word_recall:
            return
        if not self._forbidden_recall_words():
            return
        result = event.get_result()
        chain = list(getattr(result, "chain", []) or []) if result is not None else []
        if not chain:
            return
        text = self._chain_text_for_forbidden_recall(chain)
        hit = self._forbidden_recall_hit(text)
        if not hit:
            return
        logger.warning(
            "[PrivateCompanion] 待发送消息命中违禁词，已拦截发送: word=%s session=%s",
            _single_line(hit, 40),
            _single_line(getattr(event, "unified_msg_origin", ""), 120) or "unknown",
        )
        empty_result = self._build_result_from_chain([])
        try:
            empty_result.stop_event()
        except Exception:
            pass
        event.set_result(empty_result)
        event.stop_event()

    @filter.on_decorating_result()
    async def suppress_framework_error_leak_before_send(self, event: AstrMessageEvent):
        """避免 AstrBot/Core 的技术错误兜底文本直接发进聊天。"""
        if not self.enabled:
            return
        result = event.get_result()
        chain = list(getattr(result, "chain", []) or []) if result is not None else []
        if not chain or any(not isinstance(comp, Plain) for comp in chain):
            return
        text = "\n".join(str(getattr(comp, "text", "") or "") for comp in chain).strip()
        compact = text.lower()
        error_markers = (
            "error occurred while processing agent request",
            "all chat models failed",
            "sqlite3.operationalerror",
            "database is locked",
            "sqlalche.me/e/20/e3q8",
            "model do not support image input",
            "image_url",
            "invalidparameter",
        )
        if not any(marker in compact for marker in error_markers):
            return
        logger.warning(
            "[PrivateCompanion] 已拦截框架错误文本外发: session=%s preview=%s",
            _single_line(getattr(event, "unified_msg_origin", ""), 120) or "unknown",
            _single_line(text, 180),
        )
        empty_result = self._build_result_from_chain([])
        try:
            empty_result.stop_event()
        except Exception:
            pass
        event.set_result(empty_result)
        event.stop_event()

    @filter.on_decorating_result()
    async def apply_tts_enhancement_before_send_hook(self, event: AstrMessageEvent):
        """发送前处理 TTS强化标签和自动语音转换。"""
        await self.apply_tts_enhancement_before_send(event)

    @filter.on_decorating_result()
    async def strip_group_internal_identity_anchors(self, event: AstrMessageEvent):
        """发送前清理群聊内部身份锚点，避免调试标记泄露到回复。"""
        if not self.enabled:
            return
        if not self.enable_group_companion:
            return
        if not self._extract_group_id_from_event(event):
            return
        result = event.get_result()
        chain = list(getattr(result, "chain", []) or []) if result is not None else []
        if not chain:
            return
        for comp in chain:
            if not isinstance(comp, Plain):
                continue
            original = str(getattr(comp, "text", "") or "")
            cleaned = self._strip_internal_identity_anchors(original)
            if cleaned != original:
                try:
                    comp.text = cleaned
                except Exception:
                    pass

    @filter.on_decorating_result()
    async def suppress_group_silent_control_reply(self, event: AstrMessageEvent):
        """模型输出“不回复”控制语时静默吞掉，避免把内部判断发到群里。"""
        if not self.enabled:
            return
        if not self.enable_group_companion:
            return
        if not self._extract_group_id_from_event(event):
            return
        result = event.get_result()
        chain = list(getattr(result, "chain", []) or []) if result is not None else []
        if not chain or any(not isinstance(comp, Plain) for comp in chain):
            return
        text = "".join(str(getattr(comp, "text", "") or "") for comp in chain).strip()
        if not self._is_silent_control_reply_text(text):
            return
        logger.info("[PrivateCompanion] 已静默吞掉群聊不回复控制语: %s", _single_line(text, 120))
        empty_result = self._build_result_from_chain([])
        try:
            empty_result.stop_event()
        except Exception:
            pass
        event.set_result(empty_result)
        event.stop_event()

    @filter.on_decorating_result()
    async def apply_segmented_llm_reply_scope(self, event: AstrMessageEvent):
        """按回复范围与分段策略整理 LLM 输出，减少长回复和误引用。"""
        if not self.enabled:
            return
        if not self.enable_segmented_proactive_reply:
            return
        if self.segmented_proactive_scope != "all_llm":
            return
        result = event.get_result()
        if result is None or not result.chain or not result.is_llm_result():
            return
        if getattr(result, "use_t2i_", None) or getattr(result, "use_markdown_", None):
            return
        if str(event.get_platform_name() or "") in {"qq_official", "weixin_official_account", "dingtalk"}:
            return
        chain = list(result.chain or [])
        if not chain or any(not isinstance(comp, Plain) for comp in chain):
            return
        text = "".join(str(getattr(comp, "text", "") or "") for comp in chain).strip()
        if not text:
            return
        segments = self._split_proactive_text(text)
        if len(segments) <= 1:
            cleaned_text = segments[0] if segments else ""
            if cleaned_text and cleaned_text != text:
                quote_message_id = self._group_current_reply_quote_message_id(event)
                event.set_result(self._build_result_from_chain(self._with_optional_reply([Plain(cleaned_text)], quote_message_id)))
            return
        logger.debug("[PrivateCompanion] 按插件规则分段 LLM 回复: %s -> %s 段", len(text), len(segments))
        logger.info(
            "[PrivateCompanion] 按插件规则分段 LLM 回复: segments=%s first=%s full=%s",
            len(segments),
            _single_line(segments[0], 120),
            _single_line(text, 420),
        )
        quote_message_id = self._group_current_reply_quote_message_id(event)
        first_chain = self._with_optional_reply([Plain(segments[0])], quote_message_id)
        event.set_result(self._build_result_from_chain(first_chain))
        if len(segments) > 1:
            asyncio.create_task(
                self._send_segmented_llm_reply_remainder(
                    event,
                    segments[1:],
                    previous_segment=segments[0],
                    source="decorating_result",
                )
            )

    async def _send_segmented_llm_reply_remainder(
        self,
        event: AstrMessageEvent,
        segments: list[str],
        *,
        previous_segment: str = "",
        source: str = "",
    ) -> None:
        """后台补发被动分段的剩余片段，避免阻塞主链首包。"""
        prev = previous_segment
        total = len([item for item in segments if str(item or "").strip()])
        sent_index = 0
        scope = self._event_scope_key(event)
        started_at = _now_ts()
        for segment in segments:
            segment = str(segment or "").strip()
            if not segment:
                continue
            sent_index += 1
            try:
                wait_for = prev or segment
                delay = await self._calc_segmented_proactive_interval(wait_for)
                if delay > 0:
                    await asyncio.sleep(delay)
                if self._scope_has_new_inbound_activity(scope, started_at, ignore_self=True):
                    logger.info(
                        "[PrivateCompanion] 会话已有新消息，停止发送分段剩余片段: source=%s scope=%s sent=%s/%s",
                        source or "unknown",
                        scope or "unknown",
                        max(0, sent_index - 1),
                        total,
                    )
                    return
                recalled_message_id = await self._should_cancel_reply_for_missing_or_recalled_trigger(event)
                if recalled_message_id:
                    logger.info(
                        "[PrivateCompanion] 触发消息已撤回或发送前不可见，停止发送分段剩余片段: source=%s message_id=%s sent=%s/%s",
                        source or "unknown",
                        recalled_message_id,
                        max(0, sent_index - 1),
                        total,
                    )
                    return
                sent_tts_chain = False
                normalized_segment = segment
                normalizer = getattr(self, "_normalize_tts_tags", None)
                if callable(normalizer) and re.search(r"</?t{2,}s\b", normalized_segment, flags=re.IGNORECASE):
                    try:
                        normalized_segment = str(normalizer(normalized_segment) or normalized_segment).strip()
                    except Exception:
                        pass
                if (
                    bool(getattr(self, "enable_tts_enhancement", False))
                    and re.search(r"<tts\b[^>]*>.*?</tts>", normalized_segment, flags=re.IGNORECASE | re.DOTALL)
                ):
                        processor = getattr(self, "_process_tts_tags", None)
                        if callable(processor):
                            fallback_plain = re.sub(r"</?t{2,}s\b[^>]*>", "", normalized_segment, flags=re.IGNORECASE).strip()
                            chain = await processor(normalized_segment, event, fallback_plain=fallback_plain)
                            if chain:
                                hit = self._forbidden_recall_hit(self._chain_text_for_forbidden_recall(chain))
                                if hit:
                                    logger.warning("[PrivateCompanion] 分段 TTS 剩余片段命中违禁词，停止发送: word=%s", _single_line(hit, 40))
                                    return
                                try:
                                    await event.send(event.chain_result(chain))
                                except Exception:
                                    await event.send(self._build_result_from_chain(chain))
                                sent_tts_chain = True
                if not sent_tts_chain:
                    outbound = re.sub(r"</?t{2,}s\b[^>]*>", "", normalized_segment, flags=re.IGNORECASE).strip() or segment
                    hit = self._forbidden_recall_hit(outbound)
                    if hit:
                        logger.warning("[PrivateCompanion] 分段剩余片段命中违禁词，停止发送: word=%s", _single_line(hit, 40))
                        return
                    await event.send(event.plain_result(outbound))
                logger.info(
                    "[PrivateCompanion] 分段 LLM 剩余片段已发送: source=%s index=%s/%s preview=%s",
                    source or "unknown",
                    sent_index,
                    total,
                    _single_line(segment, 120),
                )
                prev = segment
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "[PrivateCompanion] 分段 LLM 剩余片段发送失败: source=%s error=%s",
                    source or "unknown",
                    _single_line(exc, 160),
                    exc_info=True,
                )
                return

    @filter.on_decorating_result()
    async def attach_group_reply_quote(self, event: AstrMessageEvent):
        """群聊回复发送前自动补引用，保持上下文对齐。"""
        if not self.enabled:
            return
        quote_message_id = self._group_current_reply_quote_message_id(event)
        if not quote_message_id:
            return
        result = event.get_result()
        if result is None:
            return
        try:
            if hasattr(result, "is_llm_result") and not result.is_llm_result():
                return
        except Exception:
            pass
        chain = list(getattr(result, "chain", []) or [])
        if not chain or self._chain_has_reply_component(chain):
            return
        quoted_chain = self._with_optional_reply(chain, quote_message_id)
        if quoted_chain == chain:
            return
        try:
            result.chain = quoted_chain
        except Exception:
            event.set_result(self._build_result_from_chain(quoted_chain))


    @filter.llm_tool(name="pc_qzone_view_feed")
    async def pc_qzone_view_feed(self, event: AstrMessageEvent, user_id: str = "", pos: int = 0, like: bool = False, reply: bool = False) -> str:
        """查看某位用户 QQ 空间说说,可按需点赞或评论。"""
        return await self._pc_qzone_view_feed_impl(event, user_id=user_id, pos=pos, like=like, reply=reply)

    @filter.llm_tool(name="pc_qzone_publish_feed")
    async def pc_qzone_publish_feed(self, event: AstrMessageEvent, text: str = "", **kwargs) -> str:
        """发布一条 QQ 空间说说。必须通过 text 参数传入最终正文。

        Args:
            text(string): 要发布到 QQ 空间的说说正文。
            use_latest_draft(boolean): 可选，是否使用最近生成的生活草稿。
        """
        return await self._pc_qzone_publish_feed_impl(event, text, **kwargs)

    @filter.llm_tool(name="pc_get_group_id_by_name")
    async def pc_get_group_id_by_name(self, event: AstrMessageEvent, **kwargs) -> str:
        """按群名关键词查询机器人已加入的群号。

        Args:
            group_name(string): 群名关键词或群号。
        """
        return await self._pc_get_group_id_by_name_impl(event, **kwargs)

    @filter.llm_tool(name="pc_get_user_id_by_name")
    async def pc_get_user_id_by_name(self, event: AstrMessageEvent, **kwargs) -> str:
        """按关系网名称、别名、群名片或昵称解析群友 QQ。

        Args:
            group_id(string): 目标群号；私聊中可填写要查询的群号。
            nickname(string): 关系网名称、别名、群名片、昵称或 QQ。
        """
        return await self._pc_get_user_id_by_name_impl(event, **kwargs)

    @filter.llm_tool(name="pc_get_specified_group_members")
    async def pc_get_specified_group_members(self, event: AstrMessageEvent, **kwargs) -> str:
        """查询指定群成员,并标记是否已在关系网中登记。

        Args:
            group_id(string): 目标群号。
            keyword(string): 可选筛选关键词、昵称、群名片或 QQ。
        """
        return await self._pc_get_specified_group_members_impl(event, **kwargs)

    @filter.llm_tool(name="pc_relay_message")
    async def pc_relay_message(self, event: AstrMessageEvent, **kwargs) -> str:
        """统一转述入口：把用户明确要求转发/转述/提醒的话发送到群聊或私聊。

        Args:
            destination(string): group/private/auto。发群填 group, 私聊填 private, 不确定填 auto。
            group_hint(string): 群号或群名。群聊转私聊时可用于按群成员名解析 QQ。
            recipient_hint(string): 收件人 QQ、关系网名称、别名、群名片或昵称。
            message(string): 最终要发送的内容。
            at_recipient(boolean): 发到群时是否 @ recipient_hint。
            relay_mode(string): persona/soft/original。默认 persona。
            sensitive_confirmed(boolean): 敏感内容是否已获得用户确认。
            delay_until_recipient_seen(boolean): 是否等目标群友在群里出现后再转述。
            expire_hours(number): 延迟转述有效小时数。
        """
        return await self._pc_relay_message_impl(event, **kwargs)

    @filter.llm_tool(name="pc_send_to_group")
    async def pc_send_to_group(self, event: AstrMessageEvent, **kwargs) -> str:
        """向指定群聊发送消息,可按 QQ/关系网名称/别名/群名片 @ 群友。

        Args:
            group_id(string): 目标群号。
            message(string): 最终要发送的转述文本。
            at_user(string): 可选,要 @ 的 QQ、关系网名称、别名、群名片或昵称。
            relay_mode(string): persona/soft/original。
            sensitive_confirmed(boolean): 敏感内容是否已获得用户确认。
        """
        return await self._pc_send_to_group_impl(event, **kwargs)

    @filter.llm_tool(name="pc_send_to_private_user")
    async def pc_send_to_private_user(self, event: AstrMessageEvent, **kwargs) -> str:
        """向指定 QQ 用户发送私聊消息。

        Args:
            user_id(string): 目标 QQ。
            message(string): 最终要发送的转述文本。
            relay_mode(string): persona/soft/original。
            sensitive_confirmed(boolean): 敏感内容是否已获得用户确认。
        """
        return await self._pc_send_to_private_user_impl(event, **kwargs)

    @filter.llm_tool(name="pc_send_to_groups")
    async def pc_send_to_groups(self, event: AstrMessageEvent, **kwargs) -> str:
        """向多个群发送同一条通知。

        Args:
            group_ids(string): 目标群号,可用逗号、空格或换行分隔。
            message(string): 最终要发送的转述文本。
            at_user(string): 可选,要 @ 的 QQ、关系网名称、别名、群名片或昵称。
            relay_mode(string): persona/soft/original。
            sensitive_confirmed(boolean): 敏感内容是否已获得用户确认。
        """
        return await self._pc_send_to_groups_impl(event, **kwargs)

    @filter.llm_tool(name="pc_send_to_private_users")
    async def pc_send_to_private_users(self, event: AstrMessageEvent, **kwargs) -> str:
        """向多个 QQ 用户发送同一条私聊转述。

        Args:
            user_ids(string): 目标 QQ,可用逗号、空格或换行分隔。
            message(string): 最终要发送的转述文本。
            relay_mode(string): persona/soft/original。
            sensitive_confirmed(boolean): 敏感内容是否已获得用户确认。
        """
        return await self._pc_send_to_private_users_impl(event, **kwargs)

    @filter.llm_tool(name="pc_schedule_group_relay")
    async def pc_schedule_group_relay(self, event: AstrMessageEvent, **kwargs) -> str:
        """挂起一条群聊转述,等目标用户在群里发言后自动 @ 并转述。

        Args:
            group_id(string): 目标群号。
            at_user(string): 目标 QQ、关系网名称、别名、群名片或昵称。
            message(string): 最终要发送的转述文本。
            relay_mode(string): persona/soft/original。
            sensitive_confirmed(boolean): 敏感内容是否已获得用户确认。
            expire_hours(number): 挂起有效小时数。
        """
        return await self._pc_schedule_group_relay_impl(event, **kwargs)

    async def _append_environment_perception_to_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        marker = "<!-- private_companion_environment_v1 -->"
        current_prompt = req.system_prompt or ""
        if marker in current_prompt:
            return
        environment_injection = await self._format_environment_perception(event)
        if environment_injection:
            req.system_prompt = f"{current_prompt}\n\n{marker}\n{environment_injection}".strip()

    async def _append_capability_boundary_to_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        marker = "<!-- private_companion_capability_boundary_v1 -->"
        current_prompt = req.system_prompt or ""
        if marker in current_prompt:
            return
        boundary = (
            "【能力边界】\n"
            "你不能假装自己能影响现实、网络、游戏房间、他人设备或用户身体动作。"
            "没有可用工具且没有实际执行结果时,不要承诺“我这就拉你/我帮你操作/我已经处理/我去修/我给你弄好”。"
            "遇到拉人、开房间、修网、重启、登录、下载、现实代办等请求,只能自然说明自己做不到实际操作,可以提醒、陪用户确认、建议对方找能操作的人,或在确有工具时调用工具后再描述结果。"
        )
        req.system_prompt = f"{current_prompt}\n\n{marker}\n{boundary}".strip()

    async def _append_conditional_tool_instructions_to_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        message_text = str(getattr(event, "message_str", "") or "")
        current_prompt = req.system_prompt or ""
        atrelay_instruction = self._atrelay_tool_instruction()
        if atrelay_instruction and "<!-- private_companion_atrelay_tools_v1 -->" not in current_prompt:
            if any(token in message_text for token in ("发到", "发给", "告诉", "转告", "通知", "私聊", "@", "艾特", "群友", "群里", "群聊", "出现", "冒泡", "上线")):
                current_prompt = f"{current_prompt}\n\n<!-- private_companion_atrelay_tools_v1 -->\n{atrelay_instruction}".strip()
                req.system_prompt = current_prompt
        qzone_instruction = self._qzone_tool_instruction()
        current_prompt = req.system_prompt or ""
        if qzone_instruction and "<!-- private_companion_qzone_tools_v1 -->" not in current_prompt:
            if any(token in message_text for token in ("说说", "空间", "QQ空间", "动态", "点赞", "评论")):
                current_prompt = f"{current_prompt}\n\n<!-- private_companion_qzone_tools_v1 -->\n{qzone_instruction}".strip()
                req.system_prompt = current_prompt

    def _is_lightweight_private_passive_inbound(self, text: str) -> bool:
        cleaned = _single_line(text, 80)
        if not cleaned:
            return False
        if len(cleaned) > 18:
            return False
        heavy_tokens = (
            "图片", "看图", "照片", "语音", "引用", "转发", "聊天记录",
            "帮我", "怎么", "为什么", "是什么", "怎么办", "分析", "解释", "总结",
            "日程", "状态", "近况", "在干嘛", "做什么", "忙什么",
            "书柜", "夹层", "本子", "新闻", "说说", "空间", "发给", "转告", "@",
        )
        return not any(token in cleaned for token in heavy_tokens)

    def _format_group_persona_denoise_prompt(self, event: AstrMessageEvent | None = None) -> str:
        if not bool(getattr(self, "enable_group_persona_denoise", True)):
            return ""
        scene = getattr(event, "private_companion_group_scene", None) if event is not None else None
        trigger = _single_line(scene.get("trigger"), 40) if isinstance(scene, dict) else ""
        high_intensity = getattr(event, "private_companion_group_high_intensity", None) if event is not None else None
        high_active = isinstance(high_intensity, dict) and bool(high_intensity.get("active"))
        lines = [
            "【群聊人格降噪】",
            "这是群聊，不是私聊。优先回答当前被问到的事或接住当前话题，少用亲密私聊腔。",
            "状态、日程、情绪、关系画像只作为语气背景，除非别人明确问，否则不要主动报告能量、天气、日程、心情或插件状态。",
            "不要为了表现人格而硬插动作描写、撒娇、长解释或关系总结；一句能说清就一句。",
            "如果只是被轻轻提到或话题不需要你，宁可短、轻、贴当前梗，不要扩写成主动陪伴消息。",
        ]
        if trigger:
            lines.append(f"本轮触发：{trigger}。只按这个触发强度回应，不要擅自升级亲密度或话题范围。")
        if high_active:
            lines.append("群里刚才较密集，回复要更像收口：集中一个重点，避免逐条点名回应。")
        return "\n".join(lines)

    def _append_group_persona_denoise_to_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        if not bool(getattr(self, "enable_group_companion", True)):
            return
        group_id = self._extract_group_id_from_event(event)
        if not group_id or not self._group_enabled_for_event(group_id):
            return
        denoise_text = self._format_group_persona_denoise_prompt(event)
        if not denoise_text:
            return
        marker = "<!-- private_companion_group_persona_denoise_v1 -->"
        current_prompt = req.system_prompt or ""
        if marker in current_prompt:
            return
        req.system_prompt = f"{current_prompt}\n\n{marker}\n{denoise_text}".strip()

    def _append_non_target_private_identity_guard_to_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        marker = "<!-- private_companion_non_target_private_guard_v1 -->"
        current_prompt = req.system_prompt or ""
        if marker in current_prompt:
            return
        try:
            user_id = str(event.get_sender_id())
        except Exception:
            user_id = ""
        user_id = _single_line(user_id, 40)
        if not user_id or self._is_bot_self_user_id(user_id):
            return
        raw_users = self.data.get("users", {})
        current_user = raw_users.get(user_id) if isinstance(raw_users, dict) else None
        if self._is_target_private_user(user_id, current_user if isinstance(current_user, dict) else None):
            return
        display_name = ""
        try:
            display_name = _single_line(self._sender_display_name(event), 40)
        except Exception:
            display_name = ""
        lines = [
            "【私聊身份防串】",
            f"当前私聊对象稳定 ID：{user_id}",
            "这个用户不是插件配置的目标陪伴用户/主用户。",
            "如果基础人格里包含“主人”“恋人”“专属称呼”或只属于主用户的关系设定,不要套用到当前私聊对象身上。",
            "可以保留人格的通用说话风格,但关系身份、亲密度、记忆和承诺必须按当前用户重新判断。",
            "除非当前用户明确提出角色扮演或临时设定,否则不要把对方当成主人、恋人或目标陪伴对象。",
        ]
        if display_name and display_name != user_id:
            lines.append(f"平台当前显示名：{display_name}。显示名只作称呼线索,不能覆盖稳定 ID。")
        profile = None
        try:
            profile = self._worldbook_profile_by_user_id(user_id)
        except Exception:
            profile = None
        if isinstance(profile, dict) and profile.get("enabled", True):
            name = _single_line(profile.get("name"), 40)
            gender = _single_line(profile.get("gender"), 40)
            identity = _single_line(profile.get("identity_note") or profile.get("note") or profile.get("content"), 220)
            boundary = _single_line(profile.get("boundary_note"), 140)
            aliases = []
            for item in profile.get("aliases") if isinstance(profile.get("aliases"), list) else []:
                alias = _single_line(item, 24)
                if alias and alias != user_id and alias not in aliases:
                    aliases.append(alias)
            lines.append("【当前用户关系网资料】")
            lines.append("以下资料来自当前私聊 QQ 号的精确匹配,只用于识别当前用户,不能外推到主用户。")
            if name and name != user_id:
                lines.append(f"登记名：{name}")
            if gender:
                lines.append(f"性别：{gender}")
            if aliases:
                lines.append(f"可用称呼线索：{'、'.join(aliases[:6])}")
            if identity:
                lines.append(f"身份备注：{identity}")
            if boundary:
                lines.append(f"互动边界：{boundary}")
            lines.append("即使此用户资料中有亲昵称呼,也必须服从上面的防串规则：不要把目标陪伴用户的专属关系套给 TA。")
        req.system_prompt = f"{current_prompt}\n\n{marker}\n{chr(10).join(lines)}".strip()

    @filter.on_llm_request()
    async def inject_humanized_state(self, event: AstrMessageEvent, req: ProviderRequest):
        """LLM 请求前注入陪伴状态、群聊上下文、工具边界和合并消息阅读上下文。"""
        if not self.enabled:
            return
        if not hasattr(req, "system_prompt"):
            return
        self._remember_external_llm_request_for_token_stats(event, req)
        if (
            bool(getattr(event, "private_companion_deferred_private_image_only", False))
            and not bool(getattr(event, "private_companion_deferred_private_image_only_ready", False))
        ):
            for attr in ("image_urls", "images"):
                existing = getattr(req, attr, None)
                if existing:
                    try:
                        setattr(req, attr, [])
                    except Exception:
                        pass
        await self.apply_tts_enhancement_request(event, req)
        await self._append_forward_message_context_to_request(event, req)
        is_private_chat = bool(getattr(event, "is_private_chat", lambda: False)())
        if not is_private_chat and self.enable_group_reality_promise_guard:
            await self._append_capability_boundary_to_request(event, req)
        if not is_private_chat:
            await self._mark_group_conversation_from_llm_request(event)
            self._append_group_persona_denoise_to_request(event, req)
        else:
            self._append_non_target_private_identity_guard_to_request(event, req)
        if not self.inject_passive_states:
            await self._append_conditional_tool_instructions_to_request(event, req)
            await self._append_environment_perception_to_request(event, req)
            return

        if not is_private_chat:
            group_id = self._extract_group_id_from_event(event) if self.enable_group_companion else ""
            group: dict[str, Any] | None = None
            sender_id = ""
            if group_id and self._group_enabled_for_event(group_id):
                try:
                    sender_id = str(event.get_sender_id())
                except Exception:
                    sender_id = ""
                group = self._get_group(group_id)
            if self.enable_group_context_injection and self.enable_group_companion:
                if group_id and self._group_enabled_for_event(group_id):
                    if not isinstance(group, dict):
                        group = self._get_group(group_id)
                    text_for_mark = _single_line(
                        getattr(event, "private_companion_group_text", "") or getattr(event, "message_str", ""),
                        260,
                    )
                    marker = "<!-- private_companion_group_context_v1 -->"
                    current_prompt = req.system_prompt or ""
                    if marker not in current_prompt:
                        combined_text = await self._consume_semantic_message_buffer_for_event(event, private_chat=False)
                        extra = ""
                        if combined_text:
                            high_intensity = getattr(event, "private_companion_group_high_intensity", None)
                            if isinstance(high_intensity, dict) and high_intensity.get("active"):
                                extra = (
                                    "\n\n【本轮高强度合并消息】\n"
                                    "群里刚刚短时间内多次叫到你,下面这些消息已合并为同一轮处理。请集中回应共同重点,不要逐条分别回复,也不要扩展太多旁支：\n"
                                    f"{combined_text}"
                                )
                            else:
                                extra = (
                                    "\n\n【本轮用户连续补充】\n"
                                    "用户刚刚在短时间内连续补充了几句,请把它们当作同一轮完整发言理解,不要逐条回复：\n"
                                    f"{combined_text}"
                                )
                        wakeup_effect = getattr(event, "private_companion_group_wakeup_state_effect", None)
                        wakeup_state_text = ""
                        if isinstance(wakeup_effect, dict) and wakeup_effect:
                            try:
                                state = await self._ensure_daily_state()
                            except Exception:
                                state = self.data.get("daily_state", {})
                            wakeup_state_text = "\n\n" + self._format_group_wakeup_humanized_prompt(wakeup_effect, state)
                        if self._user_asks_recalled_messages(text_for_mark):
                            recall_context = self._format_recalled_messages_for_natural_query(event, limit=5)
                            if recall_context:
                                extra = f"{extra}\n\n{recall_context}" if extra else f"\n\n{recall_context}"
                        req.system_prompt = (
                            f"{current_prompt}\n\n{marker}\n{self._format_group_context_for_prompt(group, sender_id, str(event.message_str or ''))}{wakeup_state_text}{extra}"
                        ).strip()
            group_recall_text = _single_line(
                getattr(event, "private_companion_group_text", "") or getattr(event, "message_str", ""),
                260,
            )
            recall_marker = "<!-- private_companion_recall_query_v1 -->"
            if self._user_asks_recalled_messages(group_recall_text) and recall_marker not in (req.system_prompt or ""):
                recall_context = self._format_recalled_messages_for_natural_query(event, limit=5)
                if recall_context:
                    req.system_prompt = f"{req.system_prompt or ''}\n\n{recall_marker}\n{recall_context}".strip()
            await self._append_conditional_tool_instructions_to_request(event, req)
            await self._append_environment_perception_to_request(event, req)
            return
        try:
            user_id = str(event.get_sender_id())
        except Exception:
            return
        raw_users = self.data.get("users", {})
        current_user = raw_users.get(user_id) if isinstance(raw_users, dict) else None
        if not isinstance(current_user, dict):
            return
        if not self._is_target_private_user(user_id, current_user) or not current_user.get("enabled", True):
            return
        self._start_passive_input_status_loop(event, user_id)

        state = await self._ensure_daily_state(skip_conversation_summary=True, passive_fast=True)
        inbound_text = _single_line(getattr(event, "message_str", "") or current_user.get("last_user_message"), 260)
        lightweight_passive = self._is_lightweight_private_passive_inbound(inbound_text)
        injection_parts = []
        if lightweight_passive:
            injection_parts.append(self._prepared_lightweight_state_injection(state))
        else:
            injection_parts.append(self._format_state_injection(state))
            worldview_context = self._format_worldview_adaptation_prompt()
            if worldview_context:
                injection_parts.append(worldview_context)
        identity_anchor = self._format_private_identity_anchor_for_prompt(user_id, current_user, event)
        if identity_anchor:
            injection_parts.append(identity_anchor)
        buffered_image_context = self._take_buffered_private_image_context_for_event(event)
        buffered_images = (
            [str(item) for item in buffered_image_context.get("images", []) if str(item or "").strip()]
            if isinstance(buffered_image_context, dict)
            else []
        )
        buffered_image_vision = (
            _single_line(buffered_image_context.get("vision_text"), 600)
            if isinstance(buffered_image_context, dict)
            else ""
        )
        delayed_image_vision = _single_line(getattr(event, "private_companion_delayed_image_vision_text", ""), 600)
        if delayed_image_vision and not buffered_image_vision:
            buffered_image_vision = delayed_image_vision
        delayed_image_sources = getattr(event, "private_companion_delayed_image_sources", [])
        if not buffered_images and isinstance(delayed_image_sources, list):
            buffered_images = [str(item) for item in delayed_image_sources[:4] if str(item or "").strip()]
        buffered_image_mode = _single_line(buffered_image_context.get("image_mode"), 20) if isinstance(buffered_image_context, dict) else ""
        delayed_image_mode = _single_line(getattr(event, "private_companion_delayed_image_mode", ""), 20)
        if not buffered_image_mode and delayed_image_mode:
            buffered_image_mode = delayed_image_mode
        vision_task = buffered_image_context.get("vision_task") if isinstance(buffered_image_context, dict) else None
        if not buffered_image_vision and isinstance(vision_task, asyncio.Task):
            try:
                buffered_image_vision = _single_line(await asyncio.wait_for(asyncio.shield(vision_task), timeout=2.5), 600)
            except asyncio.TimeoutError:
                logger.info("[PrivateCompanion] 私聊图片视觉转述仍在进行,本轮先注入路径兜底")
            except Exception as exc:
                logger.info("[PrivateCompanion] 私聊图片视觉转述获取失败: %s", _single_line(exc, 120))
        buffered_images_include_gif = (
            bool(getattr(self, "enable_private_image_gif_enhancement", True))
            and self._private_image_sources_include_gif(buffered_images)
            if buffered_images
            else False
        )
        if (
            buffered_images
            and not buffered_image_vision
            and (
                buffered_images_include_gif
                or (buffered_image_mode == "direct" and not self._event_main_provider_supports_image(event))
            )
        ):
            buffered_image_vision = _single_line(
                await self._transcribe_private_inbound_images(
                    buffered_images,
                    umo=str(getattr(event, "unified_msg_origin", "") or ""),
                ),
                600,
            )
        combined_text = ""
        if not lightweight_passive or buffered_images:
            combined_text = await self._consume_semantic_message_buffer_for_event(event, private_chat=True)
        if combined_text:
            injection_parts.append(
                "【本轮用户连续补充】\n"
                "用户刚刚在短时间内连续补充了几句,请把它们当作同一轮完整发言理解,不要逐条回复,也不要表现得像用户重复催促：\n"
                f"{combined_text}"
            )
            inbound_text = _single_line(combined_text.replace("\n", " "), 260)
        if self._user_asks_recalled_messages(inbound_text):
            injection_parts.append(self._format_recalled_messages_for_natural_query(event, limit=5))
        if buffered_images and buffered_image_vision and self._private_image_user_has_specific_vision_request(inbound_text):
            contextual_vision = _single_line(
                await self._transcribe_private_inbound_images(
                    buffered_images,
                    umo=str(getattr(event, "unified_msg_origin", "") or ""),
                    user_text=inbound_text,
                    force_contextual=True,
                ),
                600,
            )
            if contextual_vision:
                buffered_image_vision = contextual_vision
        if buffered_images:
            direct_image_mounted = False
            if buffered_image_mode == "direct" and self._event_main_provider_supports_image(event) and not buffered_images_include_gif:
                image_refs: list[str] = []
                for image_ref in buffered_images[:4]:
                    for request_ref in self._private_image_sources_for_astrbot_request([image_ref]):
                        if request_ref not in image_refs:
                            image_refs.append(request_ref)
                if not image_refs:
                    logger.info(
                        "[PrivateCompanion] 私聊延迟图片无模型可读源,跳过直接挂图: user=%s images=%s",
                        user_id,
                        len(buffered_images),
                    )
                    buffered_image_mode = "caption"
                else:
                    existing = getattr(req, "image_urls", None)
                    if not isinstance(existing, list):
                        existing = []
                    for image_ref in image_refs:
                        if image_ref not in existing:
                            existing.append(image_ref)
                    req.image_urls = existing
                    logger.info(
                        "[PrivateCompanion] 私聊延迟图片已挂回视觉主模型: user=%s images=%s mounted=%s",
                        user_id,
                        len(buffered_images),
                        len(image_refs),
                    )
                    injection_parts.append(
                        "【本轮延迟图片】\n"
                        "用户刚刚先单独发了一张图片,随后补充了文字。图片已随本轮请求一起交给当前视觉主模型；"
                        "请同时理解画面内容和用户借图表达的情绪/态度/疑问/梗。图片类型只决定回复组织顺序，不代表可以弱化另一项。"
                        "如果用户在问图里是什么,请先回答画面内容,再结合表达意图。不要提插件或处理过程。"
                        f"{self._private_image_identity_disambiguation_instruction()}"
                    )
                    direct_image_mounted = True
            if not direct_image_mounted and buffered_image_vision:
                intent_line = self._private_image_intent_line(buffered_image_vision)
                ownership_line = self._private_image_ownership_line(buffered_image_vision)
                reply_objective = self._private_image_reply_objective(ownership_line, vision_text=buffered_image_vision, user_text=inbound_text)
                logger.info(
                    "[PrivateCompanion] 私聊延迟图片已注入视觉摘要: user=%s chars=%s intent=%s ownership=%s objective=%s preview=%s",
                    user_id,
                    len(buffered_image_vision),
                    intent_line or "无",
                    ownership_line or "无",
                    _single_line(reply_objective, 120),
                    _single_line(buffered_image_vision, 220),
                )
                image_context_intro = (
                    "用户刚刚只发了一张图片,没有继续补充文字。"
                    if bool(getattr(event, "private_companion_deferred_private_image_only_ready", False))
                    else "用户刚刚先单独发了一张图片,随后补充了文字。"
                )
                injection_parts.append(
                    "【本轮延迟图片】\n"
                    f"{image_context_intro}下面是视觉模型对刚才那张图的内部摘要；"
                    "这是当前这张图片的可靠内容摘要；即使当前主模型不能直接识图,也请按此摘要理解,不要回答“没看到图”或要求重发。"
                    "请同时利用“可见内容”和“图像表达意图”；图片类型只影响回复组织顺序,不允许丢掉另一项。"
                    "如果用户问图里是什么,必须先回答画面内容,再结合表达意图；不要提模型、插件或路径。"
                    f"{self._private_image_identity_disambiguation_instruction()}\n"
                    f"{reply_objective}\n"
                    f"{buffered_image_vision}"
                )
            else:
                image_context_intro = (
                    "用户刚刚只发了一张图片,没有继续补充文字。"
                    if bool(getattr(event, "private_companion_deferred_private_image_only_ready", False))
                    else "用户刚刚先单独发了一张图片,随后补充了文字。"
                )
                injection_parts.append(
                    "【本轮延迟图片】\n"
                    f"{image_context_intro}图片已暂存,但视觉转述暂时不可用；"
                    "如果用户问的是图片内容,请自然说明自己这边暂时没看清,不要编造画面。\n"
                    + "\n".join(f"- {path}" for path in buffered_images)
                )
        elif bool(getattr(event, "private_companion_deferred_private_image_only_ready", False)):
            if buffered_image_vision:
                injection_parts.append(
                    "【本轮延迟图片】\n"
                    "用户刚刚只发了一张图片,没有继续补充文字。下面是视觉模型对那张图的内部摘要；"
                    "这是当前这张图片的可靠内容摘要；即使当前主模型不能直接识图,也请按此摘要理解,不要回答“没看到图”或要求重发。"
                    "请自然回应图片内容,不要提模型、插件或处理过程。\n"
                    f"{buffered_image_vision}"
                )
            else:
                injection_parts.append(
                    "【本轮延迟图片】\n"
                    "用户刚刚只发了一张图片,没有继续补充文字。当前没有拿到可用图片内容；"
                    "请不要沉默,也不要编造画面,可以自然地表示这边暂时没看清并等用户补一句。"
                )
        reply_image_sources: list[str] = []
        reply_image_prompt_anchor = ""
        if not buffered_images and not bool(getattr(event, "private_companion_deferred_private_image_only_ready", False)):
            reply_image_sources = await self._find_reply_image_sources_for_event(event)
            if reply_image_sources:
                reply_image_vision = _single_line(
                    await self._transcribe_private_inbound_images(
                        reply_image_sources,
                        umo=str(getattr(event, "unified_msg_origin", "") or ""),
                        user_text=inbound_text,
                        force_contextual=self._private_image_user_has_specific_vision_request(inbound_text),
                    ),
                    600,
                )
                if reply_image_vision:
                    intent_line = self._private_image_intent_line(reply_image_vision)
                    ownership_line = self._private_image_ownership_line(reply_image_vision)
                    reply_objective = self._private_image_reply_objective(ownership_line, vision_text=reply_image_vision, user_text=inbound_text)
                    logger.info(
                        "[PrivateCompanion] 私聊引用图片已注入视觉摘要: user=%s images=%s intent=%s ownership=%s objective=%s preview=%s",
                        user_id,
                        len(reply_image_sources),
                        intent_line or "无",
                        ownership_line or "无",
                        _single_line(reply_objective, 120),
                        _single_line(reply_image_vision, 220),
                    )
                    reply_image_prompt_anchor = (
                        "【当前引用图片锚点】\n"
                        f"用户本轮是在问被引用图片：{inbound_text or '（空）'}。\n"
                        "下面摘要只属于这一次被引用的图片。请把它当作当前问题的主要依据，忽略历史里其他图片、旧表情包、旧 TTS 文本或上一轮回复内容。\n"
                        "请同时利用当前引用图片的可见内容和表达意图。"
                        "如果用户问“图里是什么/这是什么/图里有啥”，请基于摘要直接概括当前引用图片的画面类型、可见主体和表达意图；"
                        "涉及露骨内容时只做概括描述，不复述露骨台词，不展开色情细节。\n"
                        f"{reply_objective}\n"
                        f"{reply_image_vision}"
                    )
                    injection_parts.insert(
                        0,
                        "【本轮引用图片】\n"
                        f"用户这轮引用/回复了一张图片,并发送文字：{inbound_text or '（空）'}。\n"
                        "下面是视觉模型对被引用图片的内部摘要。请优先回答用户当前这句文字针对引用图片提出的问题；"
                        "不要把历史记忆里的旧图片、旧声音、旧 TTS、旧表情包或上一轮回复当成当前引用目标。"
                        "如果用户问图里是什么,必须基于本摘要直接回答当前引用图片内容,不要只泛泛反问来源。\n"
                        f"{self._private_image_identity_disambiguation_instruction()}\n"
                        f"{reply_objective}\n"
                        f"{reply_image_vision}"
                    )
                    image_keys = self._private_image_cache_image_keys(reply_image_sources)
                    if image_keys:
                        try:
                            async with self._data_lock:
                                user = self._get_user(user_id)
                                user["last_private_image_vision_feedback_target"] = {
                                    "ts": _now_ts(),
                                    "image_keys": image_keys,
                                    "vision_text": _single_line(reply_image_vision, 600),
                                    "reply": "",
                                    "ownership": ownership_line,
                                    "intent": intent_line,
                                    "source": "reply_image",
                                }
                                self._save_data_sync()
                        except Exception as exc:
                            logger.debug("[PrivateCompanion] 私聊引用图片视觉反馈目标记录失败: %s", exc)
                    try:
                        setattr(event, "private_companion_reply_image_vision_text", _single_line(reply_image_vision, 600))
                        setattr(event, "private_companion_reply_image_user_text", inbound_text)
                        setattr(
                            event,
                            "private_companion_reply_image_content_question",
                            self._private_image_user_asks_content(inbound_text),
                        )
                    except Exception:
                        pass
                else:
                    injection_parts.append(
                        "【本轮引用图片】\n"
                        f"用户这轮引用/回复了一张图片,并发送文字：{inbound_text or '（空）'}。"
                        "当前未能拿到可用视觉摘要；如果用户问的是引用图片内容,请自然说明这边暂时没看清,不要编造。"
                    )
        if reply_image_prompt_anchor:
            try:
                current_req_prompt = str(getattr(req, "prompt", "") or "")
                if "<!-- private_companion_reply_image_anchor_v1 -->" not in current_req_prompt:
                    req.prompt = (
                        f"{current_req_prompt}\n\n"
                        "<!-- private_companion_reply_image_anchor_v1 -->\n"
                        f"{reply_image_prompt_anchor}"
                    ).strip()
            except Exception as exc:
                logger.debug("[PrivateCompanion] 私聊引用图片 prompt 锚点写入失败: %s", exc)
        if not lightweight_passive:
            hidden_creative_context = self._format_hidden_creative_context_for_reply(inbound_text)
            if hidden_creative_context:
                injection_parts.append(hidden_creative_context)
            bookshelf_secret_context = await self._format_bookshelf_secret_for_prompt(inbound_text, current_user)
            if bookshelf_secret_context:
                injection_parts.append(bookshelf_secret_context)
            bookshelf_reading_context = self._format_bookshelf_reading_context_for_reply(inbound_text, current_user)
            if bookshelf_reading_context:
                injection_parts.append(bookshelf_reading_context)
            private_preference_context = self._format_private_reading_preference_influence_for_reply(inbound_text, current_user)
            if private_preference_context:
                injection_parts.append(private_preference_context)
            news_context = self._format_recent_news_context_for_reply(inbound_text)
            if news_context:
                injection_parts.append(news_context)
            skill_context = self._format_skill_growth_for_prompt()
            if skill_context:
                injection_parts.append(skill_context)
            companion_injection = self._format_companion_planner_injection(current_user)
            if companion_injection:
                injection_parts.append(companion_injection)
            is_wake_event = bool(getattr(event, "is_wake", False)) or bool(
                getattr(event, "is_at_or_wake_command", False)
            )
            if is_private_chat and not is_wake_event:
                proactive_context = await self._format_proactive_reply_context(event)
                if proactive_context:
                    injection_parts.append(proactive_context)
            detail_injection = self._format_detail_injection()
            if detail_injection:
                injection_parts.append(detail_injection)
            if self.enable_llm_timer_scheduling and is_private_chat:
                try:
                    user_id = str(event.get_sender_id())
                except Exception:
                    user_id = ""
                if user_id:
                    async with self._data_lock:
                        enabled = bool(self._get_user(user_id).get("enabled"))
                    if enabled:
                        injection_parts.append(self._format_timer_scheduling_instruction())
        injection = "\n\n".join(injection_parts)
        marker = "<!-- private_companion_state_v1 -->"
        current_prompt = req.system_prompt or ""
        if marker in current_prompt:
            await self._append_conditional_tool_instructions_to_request(event, req)
            if not lightweight_passive:
                await self._append_environment_perception_to_request(event, req)
            return
        req.system_prompt = f"{current_prompt}\n\n{marker}\n{injection}".strip()
        await self._append_conditional_tool_instructions_to_request(event, req)
        if not lightweight_passive:
            await self._append_environment_perception_to_request(event, req)
        state_log_parts = [
            f"心理能量={state.get('energy', 70)}/100",
            f"情绪底色={state.get('mood_bias', '平稳')}",
        ]
        weather = _single_line(state.get("weather"), 80)
        if weather and weather != "暂无天气信息":
            state_log_parts.append(f"天气={weather}")
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        current_schedule = self._format_plan_item_for_prompt(current_item) or "无当前日程"
        logger.info(
            "[PrivateCompanion] 已注入被动状态提示词到 %s: mode=%s chars=%s 状态=%s；当前日程=%s",
            _single_line(getattr(event, "unified_msg_origin", ""), 80) or "unknown_session",
            "light" if lightweight_passive else "full",
            len(injection),
            "｜".join(state_log_parts),
            current_schedule,
        )

    @filter.on_llm_response()
    async def normalize_tts_enhancement_response(self, event: AstrMessageEvent, resp: LLMResponse):
        """规范化 TTS 标签错拼，避免 <ttts> 等内容漏到发送链路。"""
        await self.protect_tts_enhancement_response_blocks(event, resp)

    @filter.on_llm_response()
    async def record_external_llm_token_usage(self, event: AstrMessageEvent, resp: LLMResponse):
        """统计非插件内部调用的 AstrBot 主回复 Token，单独展示且不计入插件限额。"""
        if not self.enabled:
            return
        prompt = str(getattr(event, "private_companion_external_token_prompt", "") or "")
        started = _safe_float(getattr(event, "private_companion_external_token_start", 0), 0)
        completion = str(getattr(resp, "completion_text", "") or "")
        if not prompt and not completion and resp is None:
            return
        try:
            task = "astrbot_private_reply" if bool(getattr(event, "is_private_chat", lambda: False)()) else "astrbot_group_reply"
        except Exception:
            task = "astrbot_reply"
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        provider_id = self._provider_id_from_llm_response(resp) or self._default_chat_provider_id(umo)
        self._record_external_llm_usage(
            provider_id=provider_id,
            task=task,
            prompt=prompt,
            completion=completion,
            elapsed_ms=int(max(0.0, time.time() - started) * 1000) if started > 0 else 0,
            success=bool(completion),
            error="" if completion else "empty_response",
            resp=resp,
        )

    @filter.on_llm_response()
    async def capture_llm_timer_directive(self, event: AstrMessageEvent, resp: LLMResponse):
        """LLM 回复后捕获定时/状态指令，并做私聊回复审校。"""
        if not self.enabled:
            return
        if not bool(getattr(event, "is_private_chat", lambda: False)()):
            return
        original_text = str(resp.completion_text or "").strip()
        if not original_text:
            self._stop_passive_input_status_loop(event)
            return
        try:
            user_id = str(event.get_sender_id())
        except Exception:
            self._stop_passive_input_status_loop(event)
            return
        raw_users = self.data.get("users", {})
        current_user = raw_users.get(user_id) if isinstance(raw_users, dict) else None
        if not isinstance(current_user, dict):
            self._stop_passive_input_status_loop(event)
            return
        working_text = original_text
        reply_image_vision = _single_line(getattr(event, "private_companion_reply_image_vision_text", ""), 600)
        reply_image_user_text = _single_line(
            getattr(event, "private_companion_reply_image_user_text", "") or current_user.get("last_user_message"),
            260,
        )
        if (
            reply_image_vision
            and bool(getattr(event, "private_companion_reply_image_content_question", False))
            and self._private_image_reply_misses_content_question(working_text)
        ):
            corrected = self._private_image_content_answer_from_vision(
                reply_image_vision,
                user_text=reply_image_user_text,
            )
            if corrected:
                logger.info(
                    "[PrivateCompanion] 私聊引用图片回复疑似被历史话题污染,已按视觉摘要纠偏: user=%s before=%s after=%s",
                    user_id,
                    _single_line(working_text, 120),
                    _single_line(corrected, 160),
                )
                working_text = corrected
                resp.completion_text = corrected
        if self.enable_llm_timer_scheduling and "<timer" in original_text.lower():
            cleaned_text, payloads = self._extract_timer_directives(original_text)
            if cleaned_text != original_text:
                working_text = cleaned_text
                resp.completion_text = working_text
            if payloads:
                await self._schedule_llm_timer(
                    user_id,
                    payloads[-1],
                    source_text=working_text,
                    source_origin="llm_response",
                    trigger_message_id=self._event_message_id(event),
                    trigger_umo=str(getattr(event, "unified_msg_origin", "") or ""),
                )

        inbound_text = _single_line(current_user.get("last_user_message"), 260)
        reviewed_text = await self._review_and_rewrite_response(current_user, inbound_text, working_text)
        if reviewed_text != working_text:
            resp.completion_text = reviewed_text
            working_text = reviewed_text
            async with self._data_lock:
                current = self._get_user(user_id)
                stats = current.setdefault("postprocess_stats", {})
                if not isinstance(stats, dict):
                    stats = {}
                    current["postprocess_stats"] = stats
                stats["rewritten"] = _safe_int(stats.get("rewritten"), 0, 0) + 1
                stats["last_rewritten_at"] = self._environment_now().strftime("%Y-%m-%d %H:%M")
                self._save_data_sync()

        async with self._data_lock:
            current = self._get_user(user_id)
            current["last_companion_message"] = _single_line(_strip_internal_message_blocks(working_text), 500)
            self._remember_passive_reply_topic(current, working_text, inbound_text)
            self._save_data_sync()

    async def _debug_prompt_text(self, kind: str, user: dict[str, Any]) -> str:
        normalized = str(kind or "").strip().lower()
        await self._ensure_weather_context()
        if normalized in {"日程", "plan", "daily_plan"}:
            return self._build_daily_plan_prompt(self._environment_now().strftime("%Y-%m-%d %H:%M"))
        if normalized in {"细化", "detail", "enhancement"}:
            plan = dict(self.data.get("daily_plan", {}))
            state = dict(self.data.get("daily_state", {}))
            enhanced = self.data.get("detail_enhanced_segments", {})
            if not isinstance(enhanced, dict):
                enhanced = {}
            segment = self._current_detail_segment_for_update() or self._pick_detail_segment(plan, enhanced)
            if not segment:
                current_item = self._get_current_plan_item(plan)
                if not isinstance(current_item, dict):
                    return "当前没有可用于细化的日程段。先生成日程,并等到某个时间段临近,或让当天有当前日程项。"
                start = self._parse_hhmm_to_minutes(current_item.get("time")) or self._environment_now_minutes()
                segment = {
                    "start": start,
                    "end": min(24 * 60, start + 120),
                    "item": current_item,
                }
            return self._build_detail_enhancement_prompt(segment, plan, state)
        if normalized in {"主动", "proactive"}:
            name = str(user.get("nickname") or self.default_nickname)
            planned_reason = str(user.get("planned_proactive_reason") or "")
            planned_action = str(user.get("planned_proactive_action") or "message")
            planned_motive = _single_line(user.get("planned_proactive_motive"), 140)
            reason = planned_reason if planned_reason and self._is_reason_allowed_now(planned_reason) else ""
            if not reason:
                reason, _ = self._choose_proactive_message(user, name, planned_reason)
                planned_motive = self._choose_proactive_motive(reason, user, action=planned_action)
            planned_topic = _single_line(user.get("planned_proactive_topic"), 48)
            framework_prompt = self._build_framework_proactive_prompt(
                user=user,
                name=name,
                reason=reason,
                action=planned_action,
                action_context="（调试预览：这里会放工具结果或观察结果）",
                motive=planned_motive,
            )
            return (
                "【说明】\n"
                "当前主动消息已改为走 AstrBot 框架唤醒链。\n"
                "人格、历史对话和会话上下文不再在这里手工重复拼接,而是由框架根据当前 conversation 自动注入。\n\n"
                + (f"【内部话题钩子】\n{planned_topic}\n\n" if planned_topic else "")
                + "【送入框架的任务提示】\n"
                f"{framework_prompt}"
            )
        if normalized in {"回复注入", "reply", "injection"}:
            await self._refresh_default_persona_prompt(getattr(event, "unified_msg_origin", "") or "")
            state = await self._ensure_daily_state()
            parts = [self._format_state_injection(state)]
            detail_injection = self._format_detail_injection()
            if detail_injection:
                parts.append(detail_injection)
            return "\n\n".join(parts)
        return "可查看的提示词类型：日程 / 细化 / 主动 / 回复注入"

    @filter.command("陪伴", alias={"私聊陪伴", "主动陪伴"})
    async def companion_command(self, event: AstrMessageEvent):
        """管理私聊陪伴状态、日程、记忆、风格、重要日期和可选外部动作。"""
        self._qzone_note_event_bot(event)
        raw_text = str(event.message_str or "")
        args = raw_text.replace("\u3000", " ").split(maxsplit=2)
        action = args[1].strip() if len(args) >= 2 else "帮助"
        value = args[2].strip() if len(args) >= 3 else ""
        response_image_path = ""
        response_extra_components: list[Any] = []
        deferred_actions = {
            "重置插件", "重置", "全部重置",
            "查看提示词", "提示词", "prompt",
            "重置细化",
            "重置日程",
            "生成状态", "刷新状态", "重生状态",
            "增添状态", "添加状态",
            "生成日记", "刷新日记",
            "梦境", "做了什么梦", "今日梦境",
            "重置夹层密码", "重设夹层密码", "重新生成夹层密码", "重置书柜密码", "重设书柜密码", "重新生成书柜密码",
            "发说说", "发QQ空间", "发布说说", "空间发布", "发布空间",
            "测试说说链路", "测试空间发布", "测试QQ空间发布", "测试qzone发布",
            "新闻", "今日新闻", "AI新闻", "ai新闻", "AI早报", "ai早报", "早报",
            "TTS语种", "tts语种", "语音语种", "TTS", "tts",
        }

        is_private = bool(getattr(event, "is_private_chat", lambda: False)())
        if self.require_private_opt_in and not is_private:
            await self._reply(event, self._private_only_text())
            event.stop_event()
            return

        management_actions = {
            "重置插件", "重置", "全部重置",
            "查看提示词", "提示词", "prompt",
            "重置细化", "重置日程",
            "生成状态", "刷新状态", "重生状态",
            "增添状态", "添加状态",
            "生成日记", "刷新日记",
            "重置夹层密码", "重设夹层密码", "重新生成夹层密码", "重置书柜密码", "重设书柜密码", "重新生成书柜密码",
            "发说说", "发QQ空间", "发布说说", "空间发布", "发布空间",
            "测试说说链路", "测试空间发布", "测试QQ空间发布", "测试qzone发布",
            "新闻", "今日新闻", "AI新闻", "ai新闻", "AI早报", "ai早报", "早报",
            "TTS语种", "tts语种", "语音语种", "TTS", "tts",
            "撤回消息", "防撤回", "转述撤回", "撤回转述",
            "日期添加", "添加日期", "重要日期添加",
            "日期删除", "删除日期", "重要日期删除",
            "清空记忆", "忘记我",
        }
        if action in management_actions and not self._can_manage_private_companion(event):
            await self._reply(event, self._management_denied_text())
            event.stop_event()
            return

        user_id = str(event.get_sender_id())
        async with self._data_lock:
            user = self._get_user(user_id)
            user["umo"] = event.unified_msg_origin

            if action in {"状态", "status"}:
                self._reset_daily_counter_if_needed(user)
                last_seen = self._format_timestamp_elapsed(user.get("last_seen"))
                last_sent = self._format_timestamp_elapsed(user.get("last_sent"))
                plan = self.data.get("daily_plan", {})
                plan_text = self._format_plan_status_summary(plan if isinstance(plan, dict) else {})
                state = self.data.get("daily_state", {})
                state_text = (
                    f"{state.get('date')}｜能量 {state.get('energy', 70)}/100｜情绪偏{state.get('mood_bias', '平稳')}"
                    if state else "未生成"
                )
                simulation_text = self._format_simulation_summary(user)
                response = "".join(
                    [
                        "运行模式：默认开启\n",
                        f"称呼：{user.get('nickname') or self.default_nickname}\n",
                        f"语气：{user.get('style') or self.default_style}\n",
                        f"日程：{plan_text}\n",
                        f"拟人状态：{state_text}\n",
                        f"关系角色：{self._private_user_role_label(self._private_user_role(user, user_id))}\n",
                        f"今日主动消息：{user.get('sent_today', 0)}/{self._effective_user_daily_limit(user)}\n",
                        f"今日软目标：约 {self._soft_daily_target(user):.1f} 条\n",
                        f"免打扰：{self.quiet_hours}\n",
                        f"上次活跃：{last_seen}\n",
                        f"上次主动：{last_sent}\n",
                        f"下次候选：{self._format_next_proactive(user)}\n",
                        f"{simulation_text}\n" if simulation_text else "",
                        f"{self._format_suspended_summary(user)}\n",
                        f"主动方式承接：{self._format_action_affinity_summary(user)}\n",
                        f"关系：{self._format_relationship_summary(user)}",
                    ]
                )
            elif action in {"撤回消息", "防撤回", "转述撤回", "撤回转述"}:
                if not self.enable_recall_enhancement or not self.enable_recall_transcribe_command:
                    response = "撤回消息转述没有开启。"
                else:
                    response = self._format_recalled_messages_for_event(event, limit=5)
            elif action in {"TTS语种", "tts语种", "语音语种", "TTS", "tts"}:
                tts_value = value
                if action in {"TTS", "tts"}:
                    tts_parts = value.split(maxsplit=1)
                    if tts_parts and tts_parts[0].strip().lower() in {"语种", "语言", "language", "lang"}:
                        tts_value = tts_parts[1].strip() if len(tts_parts) >= 2 else ""
                response = self._set_tts_voice_language_from_command(tts_value)
            elif action in {"查看主动判定", "主动判定", "判定"}:
                response = self._explain_proactive_decision(user)
            elif action in {"能力列表", "主动能力", "工具列表"}:
                response = self._format_proactive_ability_list_for_user(user)
            elif action in {"重置插件", "重置", "全部重置"}:
                response = "正在清空插件状态,并重新生成今天的状态和日程。"
            elif action in {"查看提示词", "提示词", "prompt"}:
                response = "正在整理当前这层提示词。"
            elif action in {"重置细化"}:
                response = "正在生成当前时间段细化。"
            elif action in {"增添状态", "添加状态"}:
                response = "正在把这个状态加进去。"
            elif action in {"当前细化", "查看当前细化"}:
                response = self._format_current_detail_view()
            elif action in {"查看今日日程"}:
                plan = self.data.get("daily_plan", {})
                response = self._format_daily_plan(plan)
            elif action in {"重置日程"}:
                response = "正在生成今天的日程,我先把今天怎么过想清楚。"
            elif action in {"生成状态", "刷新状态", "重生状态"}:
                response = "正在刷新今天的拟人状态。"
            elif action in {"梦境", "做了什么梦", "今日梦境"}:
                state = self.data.get("daily_state", {})
                response = self._format_dream_view(state if isinstance(state, dict) else {})
            elif action in {"梦境碎片", "梦碎片", "碎片梦境"}:
                response = self._format_dream_fragment_pool_view()
            elif action in {"画像", "关系", "回复率"}:
                response = self._format_user_profile(user)
            elif action in {"记忆", "陪伴记忆"}:
                response = "当前陪伴记忆：\n" + self._format_companion_memory_for_prompt(user)
            elif action in {"表达学习", "说话风格", "口癖"}:
                response = "当前表达学习：\n" + self._format_expression_profile_for_prompt(user)
            elif action in {"气氛", "意图", "关系状态"}:
                response = "当前气氛判断：\n" + (self._format_intent_relationship_injection(user) or "暂无样本。")
            elif action in {"片段", "对话片段", "共同经历", "未完成"}:
                episode_text = self._format_dialogue_episodes_for_prompt(user) or "暂无对话片段记忆。"
                loop_text = self._format_open_loops_for_prompt(user) or "暂无未完成约定。"
                response = f"当前对话片段：\n{episode_text}\n\n未完成约定/可续话头：\n{loop_text}"
            elif action in {"长期记忆", "livingmemory", "lmem", "向量记忆"}:
                response = self._format_livingmemory_status()
            elif action in {"日记", "bot日记", "小记"}:
                response = self._format_diaries()
            elif action in {"书柜密码", "夹层密码", "抽屉密码", "书柜暗格"}:
                response = "这个要直接问我本人。她会不会说、怎么说,要看当时的人格和心情。"
            elif action in {"重置夹层密码", "重设夹层密码", "重新生成夹层密码", "重置书柜密码", "重设书柜密码", "重新生成书柜密码"}:
                secret = self.data.setdefault("bookshelf_secret", {})
                if not isinstance(secret, dict):
                    secret = {}
                    self.data["bookshelf_secret"] = secret
                secret.pop("password", None)
                secret["reset_at"] = _now_ts()
                await self._ensure_bookshelf_password_async()
                self._save_data_sync()
                response = "已重新设置书柜夹层密码。"
            elif action in {"发说说", "发QQ空间", "发布说说", "空间发布", "发布空间"}:
                response = "正在发布 QQ 空间说说。"
            elif action in {"测试说说链路", "测试空间发布", "测试QQ空间发布", "测试qzone发布"}:
                response = "正在模拟 QQ 空间发布链路。"
            elif action in {"新闻", "今日新闻", "AI新闻", "ai新闻", "AI早报", "ai早报", "早报"}:
                response = "正在读今天的新闻源。"
            elif action in {"生成日记", "刷新日记"}:
                response = "正在写今天的日记。"
            elif action in {"日期列表", "重要日期", "日期"}:
                response = self._format_important_dates()
            elif action in {"日期添加", "添加日期", "重要日期添加"}:
                ok, response = self._add_important_date_entry(value)
                if ok:
                    self._save_data_sync()
            elif action in {"日期删除", "删除日期", "重要日期删除"}:
                response = self._remove_important_date_entry(value)
                self._save_data_sync()
            elif action in {"可做事项", "能做什么"}:
                items = self.data.get("can_do", [])
                if items:
                    response = "我现在可以安排进日程的事：\n" + "\n".join(f"- {_single_line(item, 80)}" for item in items)
                else:
                    response = "还没有可做事项。"
            elif action in {"昵称", "称呼"}:
                if not value:
                    response = "请这样设置：陪伴 昵称 <你喜欢的称呼>"
                else:
                    user["nickname"] = _single_line(value, 24)
                    self._save_data_sync()
                    response = f"记住了,以后我会叫你：{user['nickname']}"
            elif action in {"语气", "风格"}:
                if value not in STYLE_TEMPLATES:
                    response = "可选语气：温柔、活泼、工作"
                else:
                    user["style"] = value
                    self._save_data_sync()
                    response = f"语气已切换为：{value}"
            elif action in {"清空记忆", "忘记我"}:
                self.data.setdefault("users", {}).pop(user_id, None)
                self._save_data_sync()
                response = "已清空你的陪伴设置和轻量记忆。"
            else:
                response = self._help_text()

        if action not in deferred_actions:
            await self._reply_with_optional_media(
                event,
                response,
                response_image_path,
                extra_components=response_extra_components,
            )
        if action in {"发说说", "发QQ空间", "发布说说", "空间发布", "发布空间"}:
            if not value:
                await self._reply(event, "请这样使用：陪伴 发说说 <正文>\n这是公开发布动作，正文不能为空。")
                event.stop_event()
                return
            await self._reply(event, response)
            result = await self._publish_qzone_text(value, event)
            if result.get("success"):
                await self._reply(
                    event,
                    "QQ 空间说说已发布。\n"
                    f"QQ：{result.get('uin') or '未知'}\n"
                    f"tid：{result.get('tid') or '未知'}\n"
                    f"正文：{_single_line(result.get('text'), 160)}",
                )
            else:
                await self._reply(event, f"发布失败：{_single_line(result.get('message'), 180)}")
            event.stop_event()
            return
        if action in {"测试说说链路", "测试空间发布", "测试QQ空间发布", "测试qzone发布"}:
            await self._reply(event, response)
            await self._reply(event, await self._test_qzone_publish_tool_chain(event))
            event.stop_event()
            return
        if action in {"新闻", "今日新闻", "AI新闻", "ai新闻", "AI早报", "ai早报", "早报"}:
            await self._reply(event, response)
            await self._perform_news_reading(reason="user_query", allow_share=False, force=True)
            await self._reply(event, self._format_news_digest_for_command())
            event.stop_event()
            return
        if action in {"重置夹层密码", "重设夹层密码", "重新生成夹层密码", "重置书柜密码", "重设书柜密码", "重新生成书柜密码"}:
            await self._reply(event, response)
        if action in {"重置插件", "重置", "全部重置"}:
            await self._reset_plugin_store()
            state, plan, _ = await self._rebuild_today_after_reset()
            await self._reply(
                event,
                "插件状态已清空并重建。\n"
                + self._format_state_detail(state)
                + "\n\n"
                + self._format_daily_plan(plan or {}),
            )
        if action in {"重置日程"}:
            plan = await self._ensure_daily_plan(force=True)
            async with self._data_lock:
                self.data["detail_enhanced_day"] = str((plan or {}).get("date") or _today_key())
                self.data["detail_enhanced_segments"] = {}
                self.data["daily_story_plan"] = {}
                self._save_data_sync()
            await self._reply(event, self._format_daily_plan(plan or {}))
        if action in {"生成状态", "刷新状态", "重生状态"}:
            state = await self._ensure_daily_state(force=True)
            async with self._data_lock:
                self.data["daily_plan"] = {}
                self._save_data_sync()
            await self._reply(
                event,
                self._format_state_detail(state)
                + "\n今天的日程已清空,下次生成日程会按这个状态重新安排。",
            )
        if action in {"增添状态", "添加状态"}:
            ok, message = await self._add_manual_state(value)
            if ok:
                async with self._data_lock:
                    self.data["daily_plan"] = {}
                    state = dict(self.data.get("daily_state", {}))
                    self._save_data_sync()
                await self._reply(
                    event,
                    message
                    + "\n"
                    + self._format_state_detail(state)
                    + "\n今天的日程已清空,下次生成日程会按这个状态重新安排。",
                )
            else:
                await self._reply(event, message)
        if action in {"查看提示词", "提示词", "prompt"}:
            prompt_text = await self._debug_prompt_text(value or "主动", user)
            await self._reply(event, prompt_text)
        if action in {"重置细化"}:
            plan = await self._ensure_daily_plan(force=False)
            if not plan:
                plan = await self._ensure_daily_plan(force=True)
            await self._ensure_detail_enhancement(force=False)
            detail_text = self._format_current_detail_view()
            if any(
                marker in detail_text
                for marker in (
                    "还没有",
                    "没有落地",
                    "没有生成出可展示",
                    "当前时间段还没有",
                )
            ):
                await self._ensure_detail_enhancement(force=True)
                detail_text = self._format_current_detail_view()
            await self._reply(event, detail_text)
        if action in {"生成日记", "刷新日记"}:
            diary = await self._ensure_daily_diary(force=True)
            await self._reply(event, self._format_single_diary(diary or {}))
        if action in {"梦境", "做了什么梦", "今日梦境"}:
            state = await self._ensure_daily_state(force=False)
            if not state:
                state = await self._ensure_daily_state(force=True)
                await self._reply(event, self._format_dream_view(state or {}))
        event.stop_event()

    @filter.command("陪伴群", alias={"群陪伴", "群聊陪伴"})
    async def group_companion_command(self, event: AstrMessageEvent):
        """管理群聊陪伴状态、群友画像、群内常见词、话题线程和关系网。"""
        self._qzone_note_event_bot(event)
        async for result in self._group_companion_command_impl(event):
            yield result

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def on_private_message(self, event: AstrMessageEvent):
        """记录私聊互动、图片防抖、用户画像和主动陪伴反馈。"""
        self._qzone_note_event_bot(event)
        received_ts = _now_ts()
        user_id = str(event.get_sender_id())
        self_id = self._event_self_id(event)
        if user_id and self_id and user_id == self_id:
            logger.info("[PrivateCompanion] 忽略 Bot 自己的私聊回流事件: user=%s", user_id)
            return
        sender_display_name = _single_line(self._sender_display_name(event), 40)
        text = _single_line(event.message_str, 120)
        if text.startswith(("陪伴", "/陪伴", "私聊陪伴", "主动陪伴")):
            return
        receipt_text = _single_line(event.message_str, 800)
        if receipt_text and await self._maybe_handle_atrelay_private_receipt_reply(event, user_id, sender_display_name, receipt_text):
            return
        forward_only_prompt = ""
        if self.enable_forward_message_adaptation and not text:
            try:
                forward_id, forward_payload = await self._find_forward_descriptor_for_event(event)
            except Exception as exc:
                forward_id, forward_payload = "", {}
                logger.info("[PrivateCompanion] 私聊合并消息预解析失败: user=%s error=%s", user_id, _single_line(exc, 120))
            if forward_id or forward_payload:
                forward_only_prompt = "我转发了一段聊天记录,你看看里面在说什么。"
                text = forward_only_prompt
                try:
                    event.message_str = forward_only_prompt
                    message_obj = getattr(event, "message_obj", None)
                    if message_obj is not None:
                        setattr(message_obj, "message_str", forward_only_prompt)
                except Exception:
                    pass
                logger.info(
                    "[PrivateCompanion] 私聊纯合并消息已补触发文本: user=%s id=%s inline=%s",
                    user_id,
                    _single_line(forward_id, 40) or "inline",
                    bool(forward_payload),
                )

        raw_users = self.data.get("users", {})
        fast_user = raw_users.get(user_id) if isinstance(raw_users, dict) else None
        fast_target_user = isinstance(fast_user, dict) and self._is_target_private_user(user_id, fast_user) and bool(fast_user.get("enabled", True))
        if (
            fast_target_user
            and text
            and not forward_only_prompt
            and self._is_lightweight_private_passive_inbound(text)
            and not self._is_private_image_only_message(event, text)
        ):
            if self._is_recent_poke_echo(fast_user, text):
                logger.info("[PrivateCompanion] 忽略 poke 回流事件,不计入用户新消息: %s", user_id)
                return
            if self._is_duplicate_inbound_message(event, scope=f"private:{user_id}", sender_id=user_id, text=text):
                return
            fast_user["umo"] = event.unified_msg_origin
            self._note_private_display_name_observation(fast_user, user_id, sender_display_name, now=received_ts)
            fast_user["last_seen"] = received_ts
            fast_user["last_user_message"] = text
            self._apply_user_rest_silence_from_message(fast_user, text, now=received_ts)
            fast_user["inbound_count"] = _safe_int(fast_user.get("inbound_count"), 0) + 1
            fast_user["relationship_score"] = _safe_int(fast_user.get("relationship_score"), 0) + 1
            fast_user["episode_message_count"] = _safe_int(fast_user.get("episode_message_count"), 0, 0) + 1
            if _safe_float(fast_user.get("awaiting_reply_since"), 0) > 0:
                fast_user["reply_count"] = _safe_int(fast_user.get("reply_count"), 0) + 1
                self._note_action_reply_feedback(
                    fast_user,
                    str(fast_user.get("last_proactive_action") or "message"),
                    text,
                )
                fast_user["relationship_score"] = _safe_int(fast_user.get("relationship_score"), 0) + 2
                fast_user["awaiting_reply_since"] = 0
                fast_user["last_reply_at"] = received_ts
                fast_user["pending_followup_event"] = {}
                fast_user["planned_proactive_quota_exempt"] = False
            fast_user["ignored_streak"] = 0
            if self._apply_interaction_warmth_to_state(text, fast_user):
                fast_user["relationship_score"] = _safe_int(fast_user.get("relationship_score"), 0) + 1
            self._schedule_data_save()
            return

        async with self._data_lock:
            user = self._get_user(user_id)
            is_target_user = self._is_target_private_user(user_id, user) and bool(user.get("enabled", True))
            if self._is_recent_poke_echo(user, text):
                logger.info("[PrivateCompanion] 忽略 poke 回流事件,不计入用户新消息: %s", user_id)
                return
            if self._is_duplicate_inbound_message(event, scope=f"private:{user_id}", sender_id=user_id, text=text):
                self._schedule_data_save()
                return
            if is_target_user and forward_only_prompt:
                key = self._semantic_buffer_key(f"private:{user_id}", user_id)
                if self._note_semantic_message_buffer(
                    key,
                    text,
                    now=received_ts,
                    wait_seconds=self._message_debounce_seconds("forward"),
                ):
                    self._schedule_data_save()
                    event.stop_event()
                    return
            private_image_enhancement_enabled = (
                bool(getattr(self, "enable_message_debounce", getattr(self, "enable_semantic_message_debounce", True)))
                and self._message_debounce_seconds("image") > 0
            )
            private_image_only = (
                is_target_user
                and private_image_enhancement_enabled
                and self._is_private_image_only_message(event, text)
            )
            if private_image_only:
                setattr(event, "private_companion_deferred_private_image_only", True)
                key = self._semantic_buffer_key(f"private:{user_id}", user_id)
                self._note_semantic_message_buffer(
                    key,
                    "用户刚刚先单独发送了一张图片,可能马上会补充说明。",
                    now=received_ts,
                    wait_seconds=self._message_debounce_seconds("image"),
                )
                buffers = getattr(self, "_semantic_message_buffers", None)
                if isinstance(buffers, dict) and isinstance(buffers.get(key), dict):
                    persisted_images = await self._persist_private_inbound_images(event, user_id)
                    has_model_usable_image = any(self._private_image_source_to_model_url(source) for source in persisted_images)
                    if not persisted_images or not has_model_usable_image:
                        buffers.pop(key, None)
                        setattr(event, "private_companion_deferred_private_image_only", False)
                        logger.info(
                            "[PrivateCompanion] 私聊单图未解析到可用图片源,放行原始事件: user=%s sources=%s",
                            user_id,
                            len(persisted_images),
                        )
                        self._schedule_data_save()
                        return
                    buffers[key]["images"] = persisted_images
                    buffers[key]["original_event"] = event
                    has_dynamic_gif_sources = (
                        bool(getattr(self, "enable_private_image_gif_enhancement", True))
                        and self._private_image_sources_include_gif(persisted_images)
                    )
                    direct_image_mode = (
                        bool(persisted_images)
                        and self._event_main_provider_supports_image(event)
                        and not has_dynamic_gif_sources
                    )
                    buffers[key]["image_mode"] = "direct" if direct_image_mode else "caption"
                    if persisted_images and not direct_image_mode:
                        buffers[key]["vision_task"] = asyncio.create_task(
                            self._transcribe_private_inbound_images(
                                persisted_images,
                                umo=str(getattr(event, "unified_msg_origin", "") or ""),
                            )
                        )
                    logger.info(
                        "[PrivateCompanion] 私聊单图已进入防抖缓冲: user=%s images=%s mode=%s vision=%s",
                        user_id,
                        len(persisted_images),
                        "direct" if direct_image_mode else "caption",
                        bool(persisted_images) and not direct_image_mode,
                    )
                    asyncio.create_task(self._finalize_private_image_buffer_after_wait(key, user_id, received_ts))
                self._schedule_data_save()
                event.stop_event()
                return
            elif is_target_user and not forward_only_prompt:
                key = self._semantic_buffer_key(f"private:{user_id}", user_id)
                buffers = getattr(self, "_semantic_message_buffers", None)
                existing_buffer = buffers.get(key) if isinstance(buffers, dict) else None
                buffered_images = (
                    isinstance(existing_buffer, dict)
                    and isinstance(existing_buffer.get("images"), list)
                    and bool(existing_buffer.get("images"))
                    and _now_ts() - _safe_float(existing_buffer.get("first_ts"), 0) <= max(
                        45.0,
                        self._message_debounce_seconds("image") + 30.0,
                    )
                )
                if buffered_images:
                    messages = existing_buffer.setdefault("messages", [])
                    if not isinstance(messages, list):
                        messages = []
                        existing_buffer["messages"] = messages
                    cleaned_text = _single_line(text, 260)
                    if cleaned_text and cleaned_text not in [_single_line(item.get("text"), 260) for item in messages if isinstance(item, dict)]:
                        messages.append({"ts": _now_ts(), "text": cleaned_text, "sender_name": ""})
                    existing_buffer["updated_ts"] = _now_ts()
                elif self._note_semantic_message_buffer(key, text, wait_seconds=self._message_debounce_seconds("text")):
                    self._schedule_data_save()
                    event.stop_event()
                    return
            user["umo"] = event.unified_msg_origin
            self._note_private_display_name_observation(user, user_id, sender_display_name, now=received_ts)
            if not is_target_user:
                user["enabled"] = False
                user["next_proactive_at"] = 0
                user["planned_proactive_reason"] = ""
                user["planned_proactive_action"] = ""
                user["planned_proactive_source"] = ""
                user["planned_proactive_motive"] = ""
                user["planned_proactive_topic"] = ""
            user["last_seen"] = _now_ts()
            if text:
                user["inbound_count"] = _safe_int(user.get("inbound_count"), 0) + 1
            user["relationship_score"] = _safe_int(user.get("relationship_score"), 0) + 1
            suspended = user.get("suspended_proactive")
            if (
                isinstance(suspended, dict)
                and suspended.get("active")
                and _now_ts() - _safe_float(suspended.get("created_at"), 0) <= self.proactive_reply_context_hours * 3600
            ):
                suspended["resume_ready"] = True
                suspended["complaint_enabled"] = False
                suspended["complaint_sent"] = True
                suspended["second_followup"] = {}
                user["pending_followup_event"] = {}
                user["planned_proactive_quota_exempt"] = False
            if _safe_float(user.get("awaiting_reply_since"), 0) > 0:
                user["reply_count"] = _safe_int(user.get("reply_count"), 0) + 1
                self._note_action_reply_feedback(
                    user,
                    str(user.get("last_proactive_action") or "message"),
                    text,
                )
                user["relationship_score"] = _safe_int(user.get("relationship_score"), 0) + 2
                user["awaiting_reply_since"] = 0
                user["last_reply_at"] = _now_ts()
                user["pending_followup_event"] = {}
                user["planned_proactive_quota_exempt"] = False
            user["ignored_streak"] = 0
            if text:
                user["last_user_message"] = text
                self._apply_user_rest_silence_from_message(user, text, now=received_ts)
                self._apply_private_image_vision_negative_feedback(user, text)
                user["episode_message_count"] = _safe_int(user.get("episode_message_count"), 0, 0) + 1
                self._update_expression_profile_from_message(user, text)
                self._update_companion_memory_from_message(user, text)
                self._update_open_loops_from_message(user, text)
                self._update_action_preferences_from_message(user, text)
                self._update_user_behavior_habits_from_message(user, text)
                if self.enable_intent_emotion_analysis:
                    intent_profile = self._analyze_inbound_intent(text)
                    user["intent_profile"] = intent_profile
                    self._update_relationship_state_from_intent(user, intent_profile)
                if is_target_user and self._cancel_inbound_conflicting_greeting(user, now=_now_ts()):
                    logger.info("[PrivateCompanion] 用户已在当前问候时段自然来聊,已取消冲突问候候选: %s", user_id)
                    if not self._simulation_active(user) and _safe_float(user.get("next_proactive_at"), 0) <= 0:
                        self._schedule_next_proactive(user, now=_now_ts())
            food_feedback = self._detect_food_feedback(text) if text else {"is_food": False}
            food_feedback_applied = bool(text) and self._apply_food_feedback_to_state(text)
            if food_feedback.get("is_food"):
                user["last_food_feedback_at"] = _now_ts()
                user["last_food_feedback_text"] = _single_line(text, 120)
            care_feedback_applied = bool(text) and self._apply_care_feedback_to_state(text)
            if care_feedback_applied:
                user["relationship_score"] = _safe_int(user.get("relationship_score"), 0) + 2
            interaction_warmth_applied = bool(text) and is_target_user and self._apply_interaction_warmth_to_state(text, user)
            if interaction_warmth_applied:
                user["relationship_score"] = _safe_int(user.get("relationship_score"), 0) + 1
            schedule_adjustment_applied = bool(text) and self._record_schedule_adjustment_from_interaction(text)
            if schedule_adjustment_applied:
                user["relationship_score"] = _safe_int(user.get("relationship_score"), 0) + 1
            if food_feedback_applied:
                user["relationship_score"] = _safe_int(user.get("relationship_score"), 0) + 1

            response = ""
            self._schedule_data_save()
            user_snapshot = dict(user)

        if is_target_user and schedule_adjustment_applied:
            asyncio.create_task(self._kick_proactive_loop_once())
        if response:
            await self._reply(event, response)
            event.stop_event()
        if is_target_user:
            asyncio.create_task(self._refresh_persona_relationship(user_id, user_snapshot))
            asyncio.create_task(self._maybe_refresh_companion_memory(user_id, user_snapshot))
            asyncio.create_task(self._maybe_refresh_dialogue_episode(user_id, user_snapshot))

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        """观察群聊消息，维护群上下文并判断是否自然唤醒 Bot。"""
        self._qzone_note_event_bot(event)
        if not self.enable_group_companion:
            return
        received_ts = _now_ts()
        text = _single_line(event.message_str, 260)
        if not text:
            return
        if text.startswith(("陪伴群", "/陪伴群", "群陪伴", "群聊陪伴")):
            return
        group_id = self._extract_group_id_from_event(event)
        if not group_id or not self._group_enabled_for_event(group_id):
            return
        try:
            sender_id = str(event.get_sender_id())
        except Exception:
            sender_id = ""
        sender_name = self._sender_display_name(event)
        registration_payload = None
        continuation: bool | None = False
        resting_mention_notice = ""
        scene: dict[str, Any] = {}
        wakeup_state_effect: dict[str, Any] = {}
        group_for_judge: dict[str, Any] = {}
        active_for_judge: dict[str, Any] = {}
        high_intensity_state: dict[str, Any] = {}
        group_snapshot_high_intensity: dict[str, Any] = {}
        async with self._data_lock:
            if self._is_duplicate_inbound_message(event, scope=f"group:{group_id}", sender_id=sender_id, text=text):
                self._save_data_sync()
                return
            group = self._get_group(group_id)
            _, resting_mention_notice = self._group_resting_mention_notice(
                event,
                group,
                sender_id=sender_id,
                now=received_ts,
            )
            if resting_mention_notice:
                self._save_data_sync()
            scene = self._infer_group_scene(event, group, sender_id=sender_id, sender_name=sender_name, text=text)
            if resting_mention_notice:
                continuation = True
                scene.update(
                    {
                        "trigger": "group_wakeup_resting_mention",
                        "talking_to": "bot",
                        "talking_to_name": "你",
                        "reason": "mentioned_resting_user",
                        "wakeup_word": "@休息用户",
                        "wakeup_strength": "strong",
                        "wakeup_strength_label": "明确需要你接话",
                        "wakeup_instruction": (
                            f"群友刚刚 @ 了一个已明确在休息的用户（内部提示：{resting_mention_notice}）。请用当前人格自然提醒发起 @ 的群友晚点再叫他；"
                            "语气柔和、像群友接话，不要像系统通知；不要私聊或 @ 休息用户，不要泄露具体休息截止时间或私聊原因。"
                        ),
                    }
                )
            high_intensity_state = self._group_high_intensity_state(group)
            if not resting_mention_notice:
                continuation = await self._group_message_is_bot_continuation(
                    group,
                    sender_id,
                    sender_name,
                    scene,
                    text,
                    allow_llm=False,
                )
            if continuation is None:
                if high_intensity_state.get("active"):
                    continuation = False
                else:
                    group_for_judge = deepcopy(group)
                active_for_judge = deepcopy(self._group_active_conversation(group))

        if continuation is None:
            judged = await self._group_followup_llm_judge(
                group_for_judge,
                sender_id=sender_id,
                sender_name=sender_name,
                text=text,
                active=active_for_judge,
                scene=scene,
            )
            continuation = bool(judged) if judged is not None else False

        async with self._data_lock:
            group = self._get_group(group_id)
            scene = self._infer_group_scene(event, group, sender_id=sender_id, sender_name=sender_name, text=text)
            if resting_mention_notice:
                setattr(event, "is_at_or_wake_command", True)
                setattr(event, "is_wake", True)
                scene.update(
                    {
                        "trigger": "group_wakeup_resting_mention",
                        "talking_to": "bot",
                        "talking_to_name": "你",
                        "reason": "mentioned_resting_user",
                        "wakeup_word": "@休息用户",
                        "wakeup_strength": "strong",
                        "wakeup_strength_label": "明确需要你接话",
                        "wakeup_fatigue": {},
                        "wakeup_instruction": (
                            f"群友刚刚 @ 了一个已明确在休息的用户（内部提示：{resting_mention_notice}）。请用当前人格自然提醒发起 @ 的群友晚点再叫他；"
                            "语气柔和、像群友接话，不要像系统通知；不要私聊或 @ 休息用户，不要泄露具体休息截止时间或私聊原因。"
                        ),
                    }
                )
            elif continuation:
                setattr(event, "is_at_or_wake_command", True)
                setattr(event, "is_wake", True)
                scene.update({"trigger": "bot_conversation_followup", "talking_to": "bot", "talking_to_name": "你", "reason": "contextual_followup_after_bot_wake"})
            elif self.enable_group_wakeup_enhancement and str(scene.get("trigger") or "") == "mention_bot_name":
                setattr(event, "is_at_or_wake_command", True)
                setattr(event, "is_wake", True)
                strength = self._group_wakeup_strength("direct_word", group, scene)
                fatigue = self._bump_group_wakeup_fatigue(group, "direct_word")
                scene.update(
                    {
                        "trigger": "group_wakeup_direct_word",
                        "talking_to": "bot",
                        "talking_to_name": "你",
                        "reason": "direct_wakeup_word",
                        "wakeup_word": _single_line(self.bot_name, 60),
                        "wakeup_strength": strength,
                        "wakeup_strength_label": self._group_wakeup_strength_label(strength),
                        "wakeup_fatigue": dict(fatigue),
                        "wakeup_instruction": "群友提到了你的名字；这不一定是正式提问,要像群聊里被自然叫到一样接话。",
                    }
                )
                group["last_group_wakeup_at"] = _now_ts()
                group["last_group_wakeup"] = {
                    "ts": _now_ts(),
                    "type": "direct_word",
                    "word": _single_line(self.bot_name, 60),
                    "strength": strength,
                    "strength_label": self._group_wakeup_strength_label(strength),
                    "fatigue": dict(fatigue),
                    "sender_id": sender_id,
                    "sender_name": _single_line(sender_name, 40),
                    "text": _single_line(text, 120),
                }
                wakeup_state_effect = self._apply_group_wakeup_to_humanized_state(scene, text)
                self._record_group_wakeup_log(
                    group,
                    scene=scene,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    text=text,
                    wakeup=group["last_group_wakeup"],
                    result="woke",
                    strength=strength,
                    fatigue=fatigue,
                    note=_single_line(scene.get("wakeup_instruction"), 180),
                )
            else:
                wakeup = self._evaluate_group_wakeup(
                    group,
                    scene=scene,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    text=text,
                    group_id=group_id,
                )
                if wakeup:
                    setattr(event, "is_at_or_wake_command", True)
                    setattr(event, "is_wake", True)
                    strength = _single_line(wakeup.get("strength"), 24) or self._group_wakeup_strength(str(wakeup.get("type") or ""), group, scene)
                    fatigue = self._bump_group_wakeup_fatigue(group, str(wakeup.get("type") or ""))
                    scene.update(
                        {
                            "trigger": f"group_wakeup_{wakeup.get('type')}",
                            "talking_to": "bot",
                            "talking_to_name": "你",
                            "reason": _single_line(wakeup.get("reason"), 60),
                            "wakeup_word": _single_line(wakeup.get("word"), 60),
                            "wakeup_strength": strength,
                            "wakeup_strength_label": self._group_wakeup_strength_label(strength),
                            "wakeup_fatigue": dict(fatigue),
                            "wakeup_instruction": _single_line(wakeup.get("instruction"), 180),
                            "wakeup_topic_weight": wakeup.get("topic_weight") if isinstance(wakeup.get("topic_weight"), dict) else {},
                        }
                    )
                    group["last_group_wakeup_at"] = _now_ts()
                    group["last_group_wakeup"] = {
                        "ts": _now_ts(),
                        "type": _single_line(wakeup.get("type"), 40),
                        "word": _single_line(wakeup.get("word"), 60),
                        "strength": strength,
                        "strength_label": self._group_wakeup_strength_label(strength),
                        "fatigue": dict(fatigue),
                        "probability": wakeup.get("probability"),
                        "topic_weight": wakeup.get("topic_weight") if isinstance(wakeup.get("topic_weight"), dict) else {},
                        "sender_id": sender_id,
                        "sender_name": _single_line(sender_name, 40),
                        "text": _single_line(text, 120),
                    }
                    wakeup_state_effect = self._apply_group_wakeup_to_humanized_state(scene, text)
                    self._record_group_wakeup_log(
                        group,
                        scene=scene,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        text=text,
                        wakeup=group["last_group_wakeup"],
                        result="woke",
                        strength=strength,
                        fatigue=fatigue,
                        note=_single_line(wakeup.get("instruction"), 180),
                    )
                    logger.info(
                        "[PrivateCompanion] 群聊增强唤醒命中: group=%s sender=%s type=%s word=%s strength=%s fatigue=%s",
                        group_id,
                        sender_id,
                        wakeup.get("type"),
                        wakeup.get("word"),
                        strength,
                        fatigue.get("label"),
                    )
            talking_to_bot = str(scene.get("talking_to") or "") == "bot"
            if (
                not talking_to_bot
                and
                str(scene.get("talking_to") or "") not in {"group", ""}
                and str(self._group_active_conversation(group).get("sender_id") or "") != str(sender_id or "")
            ):
                self._mark_group_bot_conversation(group, sender_id, sender_name, active=False)
            scene_trigger = str(scene.get("trigger") or "")
            if talking_to_bot and scene_trigger in {"at_bot", "reply_bot"}:
                strength = self._group_wakeup_strength("direct_word", group, scene)
                fatigue = self._bump_group_wakeup_fatigue(group, "direct_word")
                scene.setdefault("wakeup_strength", strength)
                scene.setdefault("wakeup_strength_label", self._group_wakeup_strength_label(strength))
                scene["wakeup_fatigue"] = dict(fatigue)
                group["last_group_wakeup_at"] = _now_ts()
                group["last_group_wakeup"] = {
                    "ts": _now_ts(),
                    "type": "direct_word",
                    "word": "@" if scene_trigger == "at_bot" else "reply",
                    "strength": strength,
                    "strength_label": self._group_wakeup_strength_label(strength),
                    "fatigue": dict(fatigue),
                    "sender_id": sender_id,
                    "sender_name": _single_line(sender_name, 40),
                    "text": _single_line(text, 120),
                }
                self._record_group_wakeup_log(
                    group,
                    scene=scene,
                    sender_id=sender_id,
                    sender_name=sender_name,
                    text=text,
                    wakeup=group["last_group_wakeup"],
                    result="woke",
                    strength=strength,
                    fatigue=fatigue,
                    note="群友明确 @ 或引用了 Bot。",
                )
            high_intensity_state = self._group_high_intensity_state(group)
            if high_intensity_state.get("active"):
                setattr(event, "private_companion_group_high_intensity", dict(high_intensity_state))
            setattr(event, "private_companion_group_scene", dict(scene))
            setattr(event, "private_companion_group_sender_name", sender_name)
            setattr(event, "private_companion_group_text", text)
            setattr(event, "private_companion_group_contextual_followup", bool(continuation))
            if wakeup_state_effect:
                setattr(event, "private_companion_group_wakeup_state_effect", dict(wakeup_state_effect))
            if high_intensity_state.get("active") and talking_to_bot:
                high_key = self._group_high_intensity_buffer_key(group_id)
                if self._note_semantic_message_buffer(
                    high_key,
                    text,
                    sender_name=sender_name,
                    wait_seconds=self._group_high_intensity_merge_wait_seconds(),
                    force=True,
                ):
                    self._update_group_observation(
                        group,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        text=text,
                        group_id=group_id,
                        scene=scene,
                        message_id=self._event_message_id(event),
                    )
                    self._save_data_sync()
                    logger.info(
                        "[PrivateCompanion] 群聊高强度消息已合并等待: group=%s sender=%s recent_wakeups=%s wait=%ss text=%s",
                        group_id,
                        sender_id,
                        high_intensity_state.get("recent_wakeups"),
                        self._group_high_intensity_merge_wait_seconds(),
                        _single_line(text, 80),
                    )
                    event.stop_event()
                    return
            if (
                talking_to_bot
                and not high_intensity_state.get("active")
                and self._note_semantic_message_buffer(
                    self._semantic_buffer_key(f"group:{group_id}", sender_id),
                    text,
                    sender_name=sender_name,
                )
            ):
                self._save_data_sync()
                event.stop_event()
                return
            self._update_group_observation(
                group,
                sender_id=sender_id,
                sender_name=sender_name,
                text=text,
                group_id=group_id,
                scene=scene,
                message_id=self._event_message_id(event),
            )
            registration_payload = self._maybe_worldbook_self_register_from_group_message(
                event,
                group_id=group_id,
                sender_id=sender_id,
                sender_name=sender_name,
                text=text,
                group=group,
            )
            share_scheduled = self._maybe_schedule_group_private_share(group_id, group, trigger_sender_id=sender_id)
            self._save_data_sync()
            group_snapshot = deepcopy(group)
            group_snapshot_high_intensity = dict(high_intensity_state)
        await self._dispatch_due_atrelay_tasks(event, group_id, sender_id)
        if isinstance(registration_payload, dict) and registration_payload.get("blocked_reply"):
            await self._reply(event, str(registration_payload.get("blocked_reply") or "你是小猪"))
            event.stop_event()
            return
        if isinstance(registration_payload, dict) and registration_payload.get("confirm_reply"):
            await self._reply(event, str(registration_payload.get("confirm_reply") or ""))
            if not registration_payload.get("user_id"):
                event.stop_event()
                return
        if registration_payload and registration_payload.get("user_id"):
            asyncio.create_task(self._refresh_worldbook_self_registration_impression(registration_payload))
        if share_scheduled:
            asyncio.create_task(self._kick_proactive_loop_once())
        if not group_snapshot_high_intensity.get("active"):
            asyncio.create_task(self._maybe_refresh_group_episode(group_id, group_snapshot))
            asyncio.create_task(self._maybe_refresh_group_slang_meanings(group_id, group_snapshot))
            await self._maybe_group_interject(event, group_snapshot, text)
        else:
            logger.info(
                "[PrivateCompanion] 群聊高强度收口生效: group=%s recent_wakeups=%s threshold=%s reason=%s merge_wait=%ss skip=followup-refresh/interject",
                group_id,
                group_snapshot_high_intensity.get("recent_wakeups"),
                group_snapshot_high_intensity.get("threshold"),
                group_snapshot_high_intensity.get("reason"),
                self._group_high_intensity_merge_wait_seconds(),
            )
        original_interject_at = _safe_float(group.get("last_interject_at"), 0) if isinstance(group, dict) else 0
        repeat_state_changed = group_snapshot.get("repeat_follow_state") != (
            group.get("repeat_follow_state") if isinstance(group, dict) else {}
        )
        if _safe_float(group_snapshot.get("last_interject_at"), 0) > original_interject_at or repeat_state_changed:
            async with self._data_lock:
                current = self._get_group(group_id)
                current["last_interject_at"] = group_snapshot.get("last_interject_at", current.get("last_interject_at", 0))
                current["interject_day"] = group_snapshot.get("interject_day", current.get("interject_day", ""))
                current["interject_today"] = group_snapshot.get("interject_today", current.get("interject_today", 0))
                current["last_bot_interjection"] = group_snapshot.get("last_bot_interjection", current.get("last_bot_interjection", {}))
                current["repeat_follow_state"] = group_snapshot.get("repeat_follow_state", current.get("repeat_follow_state", {}))
                self._save_data_sync()

    def _format_timestamp_elapsed(self, timestamp: Any) -> str:
        ts = _safe_float(timestamp, 0)
        if ts <= 0:
            return "从未"
        seconds = max(0, _now_ts() - ts)
        return self._format_elapsed(seconds)

    def _format_elapsed(self, seconds: float) -> str:
        if seconds < 5:
            return "刚刚"
        if seconds < 60:
            return f"{int(seconds)} 秒前"
        if seconds < 3600:
            return f"{int(seconds // 60)} 分钟前"
        if seconds < 86400:
            return f"{int(seconds // 3600)} 小时前"
        return f"{int(seconds // 86400)} 天前"

