from __future__ import annotations

import asyncio
import base64
import gc
import importlib
import json
import math
import os
import random
import re
import sys
import time
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
try:
    from astrbot.api.message_components import Image, Plain, Record
except ImportError:
    from astrbot.api.message_components import Image, Plain
    from astrbot.core.message.components import Record
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


class SyntheticPrivateWakeEvent(AstrMessageEvent):
    def __init__(
        self,
        *,
        context: Context,
        session: MessageSession,
        message: str,
        sender_name: str = "PrivateCompanion",
    ) -> None:
        platform_meta = PlatformMetadata(
            name=session.platform_id,
            description="SyntheticPrivateWake",
            id=session.platform_id,
        )

        msg_obj = AstrBotMessage()
        msg_obj.type = session.message_type
        msg_obj.self_id = session.session_id
        msg_obj.session_id = session.session_id
        msg_obj.message_id = f"private_companion_{uuid.uuid4().hex}"
        msg_obj.sender = MessageMember(user_id=session.session_id, nickname=sender_name)
        msg_obj.message = [Plain(message)]
        msg_obj.message_str = message
        msg_obj.raw_message = message
        msg_obj.timestamp = int(time.time())

        super().__init__(message, msg_obj, platform_meta, session.session_id)
        self.session = session
        self.context_obj = context
        self.is_at_or_wake_command = True
        self.is_wake = True

    async def send(self, message: MessageChain) -> None:
        if message is None:
            return
        await self.context_obj.send_message(self.session, message)
        await super().send(message)


class _CapturedSendMessageCall:
    def __init__(self, session: str, messages: list[dict[str, Any]]) -> None:
        self.session = str(session or "")
        self.messages = [dict(item) for item in messages if isinstance(item, dict)]


@register(
    PLUGIN_NAME,
    "Codex",
    "我会永远陪着你：为 AstrBot 提供人格连续性、关系识别、主动行为和可视化管理的陪伴编排插件。",
    "2.3.0",
)
class PrivateCompanionPlugin(Star):
    @staticmethod
    def _cfg_bool(config: AstrBotConfig, key: str, default: bool = True) -> bool:
        return bool(config.get(key, default))

    @staticmethod
    def _cfg_str(config: AstrBotConfig, key: str, default: str = "", fallback: str = "") -> str:
        return str(config.get(key, default)).strip() or fallback

    @staticmethod
    def _cfg_int(config: AstrBotConfig, key: str, default: int, minimum: int = 0, maximum: int | None = None) -> int:
        return _safe_int(config.get(key, default), default, minimum, maximum)

    @staticmethod
    def _cfg_float(config: AstrBotConfig, key: str, default: float, minimum: float = 0.0) -> float:
        return _safe_float(config.get(key, default), default, minimum)

    def __init__(self, context: Context, config: AstrBotConfig):
        super().__init__(context)
        self.config = config
        c = config

        self.enabled = self._cfg_bool(c, "enabled", True)
        self.check_interval_seconds = self._cfg_int(c, "check_interval_seconds", 60, 30)
        self.idle_minutes = self._cfg_int(c, "idle_minutes", 60, 5)
        self.min_interval_minutes = self._cfg_int(c, "min_interval_minutes", 120, 10)
        self.max_daily_messages = self._cfg_int(c, "max_daily_messages", 8, 0, 12)
        self.quiet_hours = self._cfg_str(c, "quiet_hours", "23:00-08:30")
        self.default_style = self._cfg_str(c, "default_style", "温柔", "温柔")
        self.default_nickname = self._cfg_str(c, "default_nickname", "你", "你")
        self.require_private_opt_in = self._cfg_bool(c, "require_private_opt_in", True)
        self.target_user_ids = c.get("target_user_ids", [])
        self.target_platform = self._cfg_str(c, "target_platform", "aiocqhttp", "aiocqhttp")
        self.default_enable_configured_targets = self._cfg_bool(c, "default_enable_configured_targets", True)
        self.llm_provider_id = self._cfg_str(c, "LLM_PROVIDER_ID", "")
        self.daily_plan_provider_id = self._cfg_str(c, "DAILY_PLAN_PROVIDER_ID", "")
        self.enable_daily_plan = self._cfg_bool(c, "enable_daily_plan", True)
        self.daily_plan_time = self._cfg_str(c, "daily_plan_time", "07:30")
        self.bot_name = self._cfg_str(c, "bot_name", "小星", "小星")
        self.include_schedule_in_messages = self._cfg_bool(c, "include_schedule_in_messages", True)
        self.daily_plan_prompt = self._cfg_str(c, "daily_plan_prompt", "")
        self.schedule_persona_prompt = self._cfg_str(c, "schedule_persona_prompt", "")
        self.schedule_worldview_prompt = self._cfg_str(c, "schedule_worldview_prompt", "")
        self.daily_plan_item_count = self._cfg_int(c, "daily_plan_item_count", 10, 5, 16)
        self.enable_humanized_states = self._cfg_bool(c, "enable_humanized_states", True)
        self.enable_cycle_state = self._cfg_bool(c, "enable_cycle_state", True)
        self.humanized_state_intensity = self._cfg_int(c, "humanized_state_intensity", 50, 0, 100)
        self.enable_enhanced_dreams = self._cfg_bool(c, "enable_enhanced_dreams", False)
        self.dream_provider_id = self._cfg_str(c, "DREAM_PROVIDER_ID", "")
        self.diary_provider_id = self._cfg_str(c, "DIARY_PROVIDER_ID", "")
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
        self.creative_base_chars_per_hour = self._cfg_int(c, "creative_base_chars_per_hour", 260, 60, 1200)
        self.creative_max_active_projects = self._cfg_int(c, "creative_max_active_projects", 2, 1, 5)
        self.creative_hidden_mode = self._cfg_bool(c, "creative_hidden_mode", True)
        self.creative_provider_id = self._cfg_str(c, "CREATIVE_PROVIDER_ID", "")
        self.voice_prompt_provider_id = self._cfg_str(c, "VOICE_PROMPT_PROVIDER_ID", "")
        self.history_summary_provider_id = self._cfg_str(c, "HISTORY_SUMMARY_PROVIDER_ID", "")
        self.enable_llm_proactive_message = self._cfg_bool(c, "enable_llm_proactive_message", True)
        self.enable_llm_timer_scheduling = self._cfg_bool(c, "enable_llm_timer_scheduling", True)
        self.enable_proactive_decorating_hooks = self._cfg_bool(c, "enable_proactive_decorating_hooks", True)
        self.enable_precise_platform_send = self._cfg_bool(c, "enable_precise_platform_send", True)
        self.enable_segmented_proactive_reply = self._cfg_bool(c, "enable_segmented_proactive_reply", False)
        self.segmented_proactive_threshold = self._cfg_int(c, "segmented_proactive_threshold", 120, 20, 500)
        self.segmented_proactive_split_mode = self._cfg_str(c, "segmented_proactive_split_mode", "regex", "regex")
        if self.segmented_proactive_split_mode not in {"regex", "words"}:
            self.segmented_proactive_split_mode = "regex"
        self.segmented_proactive_regex = str(c.get("segmented_proactive_regex", r".*?[。？！~…\n]+|.+$"))
        split_words = c.get("segmented_proactive_split_words", ["。", "？", "！", "~", "…"])
        self.segmented_proactive_split_words = [str(item) for item in split_words] if isinstance(split_words, list) else ["。", "？", "！", "~", "…"]
        self.enable_segmented_proactive_content_cleanup = self._cfg_bool(c, "enable_segmented_proactive_content_cleanup", False)
        self.segmented_proactive_content_cleanup_rule = str(c.get("segmented_proactive_content_cleanup_rule", r"[\n]"))
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
        self.enable_detail_enhancement = self._cfg_bool(c, "enable_detail_enhancement", False)
        self.detail_enhancement_provider_id = self._cfg_str(c, "DETAIL_ENHANCEMENT_PROVIDER_ID", "")
        self.narration_provider_id = self._cfg_str(c, "NARRATION_PROVIDER_ID", "")
        self.photo_prompt_provider_id = self._cfg_str(c, "PHOTO_PROMPT_PROVIDER_ID", "")
        self.comfyui_photo_workflow_name = self._cfg_str(c, "COMFYUI_PHOTO_WORKFLOW_NAME", "")
        self.comfyui_text2img_workflow_name = self._cfg_str(c, "COMFYUI_TEXT2IMG_WORKFLOW_NAME", self.comfyui_photo_workflow_name)
        self.comfyui_selfie_workflow_name = self._cfg_str(c, "COMFYUI_SELFIE_WORKFLOW_NAME", self.comfyui_photo_workflow_name)
        self.comfyui_photo_wait_seconds = self._cfg_int(c, "comfyui_photo_wait_seconds", 90, 5, 600)
        self.photo_generation_backend = self._cfg_str(c, "photo_generation_backend", "auto", "auto").strip().lower()
        if self.photo_generation_backend not in {"auto", "comfyui", "external"}:
            self.photo_generation_backend = "auto"
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
        self.enable_group_interjection = self._cfg_bool(c, "enable_group_interjection", False)
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
        self.worldbook_auto_import = self._cfg_bool(c, "worldbook_auto_import", True)
        self.worldbook_member_match_aliases = self._cfg_bool(c, "worldbook_member_match_aliases", True)
        self.worldbook_self_registration = self._cfg_bool(c, "worldbook_self_registration", True)
        self.worldbook_member_inject_limit = self._cfg_int(c, "worldbook_member_inject_limit", 6, 1, 20)
        self.worldbook_config_paths = self._cfg_str(c, "worldbook_config_paths", "")
        self.group_interject_provider_id = self._cfg_str(c, "GROUP_INTERJECT_PROVIDER_ID", "")
        self.group_episode_provider_id = self._cfg_str(c, "GROUP_EPISODE_PROVIDER_ID", "")
        self.group_slang_provider_id = self._cfg_str(c, "GROUP_SLANG_PROVIDER_ID", "")
        self.enable_livingmemory_integration = self._cfg_bool(c, "enable_livingmemory_integration", True)
        self.livingmemory_tool_name = self._cfg_str(c, "livingmemory_tool_name", "recall_long_term_memory", "recall_long_term_memory")
        self.enable_bilibili_integration = self._cfg_bool(c, "enable_bilibili_integration", True)
        self.enable_bilibili_boredom_watch = self._cfg_bool(c, "enable_bilibili_boredom_watch", True)
        self.bilibili_boredom_min_interval_hours = self._cfg_int(c, "bilibili_boredom_min_interval_hours", 8, 2, 72)
        self.bilibili_share_probability = min(1.0, self._cfg_float(c, "bilibili_share_probability", 0.35, 0.0))
        self.bilibili_share_min_score = self._cfg_int(c, "bilibili_share_min_score", 7, 0, 10)
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
        self.data_file = os.path.join(self.data_dir, "companions.json")
        self._data_lock = asyncio.Lock()
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task | None = None
        self._framework_captured_send_cache: dict[str, list[_CapturedSendMessageCall]] = {}
        self._last_input_status_at: dict[str, float] = {}
        self.data = self._load_data_sync()
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

    def _register_page_api_if_available(self) -> None:
        if not hasattr(self.context, "register_web_api"):
            logger.debug("[PrivateCompanion] 当前 AstrBot 版本未提供 register_web_api,跳过插件拓展页面 API 注册")
            return
        try:
            from .page_api import PrivateCompanionPageApi

            self.page_api = PrivateCompanionPageApi(self)
            self.page_api.register_routes()
            logger.info("[PrivateCompanion] 插件拓展页面 API 已注册")
        except Exception as e:
            logger.warning(f"[PrivateCompanion] 插件拓展页面 API 注册失败: {e}", exc_info=True)

    async def initialize(self):
        if not self.enabled:
            logger.info("[PrivateCompanion] 插件总开关已关闭,不启动主动消息循环")
            return
        async with self._data_lock:
            if self._prime_enabled_user_schedules():
                self._save_data_sync()
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._scheduler_loop())
            logger.info("[PrivateCompanion] 主动消息循环已启动")
        asyncio.create_task(self._reset_stale_qq_presence_if_needed())
        asyncio.create_task(self._startup_prepare_today())

    async def _startup_prepare_today(self):
        try:
            await self._ensure_daily_state()
            await self._ensure_daily_plan()
            await self._ensure_daily_diary(force=not self._has_today_diary())
        except Exception as e:
            logger.warning(f"[PrivateCompanion] 启动时生成今日日志失败: {e}", exc_info=True)

    def _has_today_diary(self) -> bool:
        diaries = self.data.get("bot_diaries", [])
        if not isinstance(diaries, list):
            return False
        return any(
            isinstance(diary, dict) and diary.get("date") == _today_key()
            for diary in diaries
        )

    async def terminate(self):
        self._stop_event.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        async with self._data_lock:
            self._save_data_sync()

    def _new_store(self) -> dict[str, Any]:
        return {
            "version": DATA_VERSION,
            "users": {},
            "groups": {},
            "daily_plan": {},
            "daily_plan_history": [],
            "daily_state": {},
            "state_conditions": [],
            "state_generated_day": "",
            "bot_diaries": [],
            "dream_fragments": [],
            "daily_dream": {},
            "diary_generated_day": "",
            "daily_story_plan": {},
            "detail_enhanced_day": "",
            "detail_enhanced_segments": {},
            "schedule_adjustments": [],
            "yesterday_conversation_summary": {},
            "can_do": [],
            "important_dates": [],
            "qq_presence_state": {},
            "token_usage": {},
            "bilibili_integration": {},
            "creative_projects": [],
            "proactive_candidate_pool": [],
            "worldbook_entries": [],
            "worldbook_member_profiles": {},
            "worldbook_group_profiles": {},
            "worldbook_import_state": {},
        }

    @staticmethod
    def _ensure_store_defaults(data: dict[str, Any]) -> dict[str, Any]:
        data.setdefault("version", DATA_VERSION)
        data.setdefault("users", {})
        data.setdefault("groups", {})
        data.setdefault("daily_plan", {})
        data.setdefault("daily_plan_history", [])
        data.setdefault("daily_state", {})
        data.setdefault("state_conditions", [])
        data.setdefault("state_generated_day", "")
        data.setdefault("bot_diaries", [])
        data.setdefault("dream_fragments", [])
        data.setdefault("daily_dream", {})
        data.setdefault("diary_generated_day", "")
        data.setdefault("daily_story_plan", {})
        data.setdefault("detail_enhanced_day", "")
        data.setdefault("detail_enhanced_segments", {})
        data.setdefault("schedule_adjustments", [])
        data.setdefault("yesterday_conversation_summary", {})
        data.setdefault("can_do", [])
        data.setdefault("important_dates", [])
        data.setdefault("qq_presence_state", {})
        data.setdefault("token_usage", {})
        data.setdefault("bilibili_integration", {})
        data.setdefault("creative_projects", [])
        data.setdefault("proactive_candidate_pool", [])
        data.setdefault("worldbook_entries", [])
        data.setdefault("worldbook_member_profiles", {})
        data.setdefault("worldbook_group_profiles", {})
        data.setdefault("worldbook_import_state", {})
        return data

    @staticmethod
    def _data_dict(data: Any, field: str) -> dict[str, Any]:
        value = data.get(field) if isinstance(data, dict) else None
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _data_list(data: Any, field: str) -> list[Any]:
        value = data.get(field) if isinstance(data, dict) else None
        return value if isinstance(value, list) else []

    @staticmethod
    def _data_str(data: Any, field: str, default: str = "") -> str:
        value = data.get(field) if isinstance(data, dict) else None
        return str(value) if value is not None else default

    def _load_data_sync(self) -> dict[str, Any]:
        if not os.path.exists(self.data_file):
            return self._new_store()
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return self._new_store()
            return self._ensure_store_defaults(data)
        except Exception as e:
            logger.warning(f"[PrivateCompanion] 读取数据失败,将使用空数据: {e}")
            return self._new_store()

    def _save_data_sync(self):
        # Avoid losing migrated worldbook data if an older in-memory state is saved before reload finishes.
        if not self.data.get("worldbook_entries") and os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
                if isinstance(existing, dict) and existing.get("worldbook_entries"):
                    for key in (
                        "worldbook_entries",
                        "worldbook_member_profiles",
                        "worldbook_group_profiles",
                        "worldbook_import_state",
                    ):
                        self.data[key] = existing.get(key, self.data.get(key))
            except Exception:
                pass
        tmp_file = self.data_file + ".tmp"
        with open(tmp_file, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_file, self.data_file)

    async def _reset_plugin_store(self) -> None:
        async with self._data_lock:
            self.data = self._new_store()
            if self.default_enable_configured_targets:
                self._sync_configured_targets()
            self._save_data_sync()

    async def _rebuild_today_after_reset(
        self,
    ) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
        state = await self._ensure_daily_state(force=True)
        plan = await self._generate_daily_plan()
        async with self._data_lock:
            self.data["daily_plan"] = plan
            self._save_data_sync()

        diary = None
        if self.enable_daily_diary:
            diary = await self._generate_daily_diary()
            async with self._data_lock:
                diaries = self.data.setdefault("bot_diaries", [])
                if not isinstance(diaries, list):
                    diaries = []
                    self.data["bot_diaries"] = diaries
                diaries.append(diary)
                del diaries[:-self.max_diary_entries]
                self.data["dream_fragments"] = self._merge_dream_fragment_pool(
                    diary.get("dream_fragments", []) if isinstance(diary, dict) else []
                )
                self.data["diary_generated_day"] = _today_key()
                story_plan = diary.get("story_plan")
                if isinstance(story_plan, dict):
                    self.data["daily_story_plan"] = story_plan
                self._save_data_sync()
        return state, plan, diary

    def _get_user(self, user_id: str) -> dict[str, Any]:
        users = self.data.setdefault("users", {})
        user = users.setdefault(user_id, dict(_DEFAULT_USER_TEMPLATE))
        user["user_id"] = user_id
        for key, default_value in _DEFAULT_USER_TEMPLATE.items():
            if key not in user:
                user[key] = default_value
        user["enabled"] = True
        if not user.get("nickname"):
            user["nickname"] = self.default_nickname
        if not user.get("style"):
            user["style"] = self.default_style
        return user

    def _get_group(self, group_id: str) -> dict[str, Any]:
        groups = self.data.setdefault("groups", {})
        group = groups.setdefault(group_id, dict(_DEFAULT_GROUP_TEMPLATE))
        group["group_id"] = group_id
        for key, default_value in _DEFAULT_GROUP_TEMPLATE.items():
            if key not in group:
                group[key] = default_value.copy() if isinstance(default_value, (dict, list)) else default_value
        group["enabled"] = bool(group.get("enabled", True))
        return group

    def _parse_group_id_list(self, raw: Any) -> list[str]:
        if isinstance(raw, str):
            parts = re.split(r"[,\s,、;；]+", raw)
        elif isinstance(raw, list):
            parts = raw
        else:
            parts = []
        ids = []
        for part in parts:
            group_id = str(part).strip()
            if group_id and group_id.isdigit() and group_id not in ids:
                ids.append(group_id)
        return ids

    def _configured_group_ids(self) -> list[str]:
        # Backward compatibility: old target_group_ids is now treated as whitelist.
        whitelist = self._parse_group_id_list(self.group_whitelist_ids)
        legacy = self._parse_group_id_list(self.target_group_ids)
        for group_id in legacy:
            if group_id not in whitelist:
                whitelist.append(group_id)
        return whitelist

    def _configured_group_blacklist_ids(self) -> list[str]:
        return self._parse_group_id_list(self.group_blacklist_ids)

    def _group_enabled_for_event(self, group_id: str) -> bool:
        if not self.enable_group_companion:
            return False
        if not self._group_allowed_by_access_mode(group_id):
            return False
        group = self._get_group(group_id)
        return bool(group.get("enabled", True))

    def _group_allowed_by_access_mode(self, group_id: str) -> bool:
        if self.group_access_mode == "blacklist":
            if group_id in self._configured_group_blacklist_ids():
                return False
        else:
            configured = self._configured_group_ids()
            if group_id not in configured:
                return False
        return True

    def _worldbook_config_path_candidates(self) -> list[Path]:
        data_root = Path(get_astrbot_data_path())
        configured = [
            Path(part.strip())
            for part in re.split(r"[\n,;；]+", str(self.worldbook_config_paths or ""))
            if part.strip()
        ]
        defaults = [
            data_root / "config" / "plugin_upload_astrbot_plugin_worldbook_config.json",
            data_root / "config" / "astrbot_plugin_worldbook_config.json",
        ]
        paths: list[Path] = []
        for path in [*configured, *defaults]:
            resolved = path if path.is_absolute() else data_root / path
            if resolved not in paths:
                paths.append(resolved)
        return paths

    @staticmethod
    def _worldbook_entry_template(raw: dict[str, Any]) -> str:
        return str(raw.get("__template_key") or raw.get("template") or "").strip().lower()

    def _normalize_worldbook_entry(self, raw: dict[str, Any], *, source: str) -> dict[str, Any] | None:
        if not isinstance(raw, dict):
            return None
        name = _single_line(raw.get("name"), 80)
        content = str(raw.get("content") or "").strip()
        if not name and not content:
            return None
        scope = (
            [_single_line(item, 40).strip() for item in raw.get("scope", []) if _single_line(item, 40).strip()]
            if isinstance(raw.get("scope"), list)
            else []
        )
        aliases = (
            [_single_line(item, 40).strip() for item in raw.get("aliases", []) if _single_line(item, 40).strip()]
            if isinstance(raw.get("aliases"), list)
            else []
        )
        return {
            "template": self._worldbook_entry_template(raw),
            "name": name,
            "enabled": bool(raw.get("enabled", True)),
            "priority": _safe_int(raw.get("priority"), 100, -1000, 10000),
            "scope": scope,
            "keywords": [_single_line(item, 80) for item in raw.get("keywords", []) if _single_line(item, 80)]
            if isinstance(raw.get("keywords"), list)
            else [],
            "aliases": aliases,
            "content": content,
            "source": source,
            "raw": raw,
        }

    def _import_worldbook_entries_from_sources(self) -> bool:
        entries: list[dict[str, Any]] = []
        source_files: list[str] = []
        for path in self._worldbook_config_path_candidates():
            if not path.exists() or not path.is_file():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
            except Exception as e:
                logger.warning(f"[PrivateCompanion] 读取关系网配置失败: {path} ({e})")
                continue
            raw_entries = payload.get("entry_storage") if isinstance(payload, dict) else None
            if not isinstance(raw_entries, list):
                continue
            source_files.append(str(path))
            for raw in raw_entries:
                item = self._normalize_worldbook_entry(raw, source=str(path))
                if item:
                    entries.append(item)
        if not entries:
            return False

        profiles: dict[str, dict[str, Any]] = {}
        groups: dict[str, dict[str, Any]] = {}
        for item in entries:
            template = item.get("template")
            digit_scopes = [str(scope).strip() for scope in item.get("scope", []) if str(scope).strip().isdigit()]
            if template == "user":
                for user_id in digit_scopes:
                    profile = profiles.setdefault(
                        user_id,
                        {
                            "user_id": user_id,
                            "name": item.get("name") or user_id,
                            "aliases": [],
                            "content": "",
                            "identity_note": "",
                            "boundary_note": "",
                            "important_memories": [],
                            "enabled": bool(item.get("enabled", True)),
                            "priority": item.get("priority", 120),
                            "source_entries": [],
                            "observed_names": [],
                        },
                    )
                    for alias in [item.get("name"), *(item.get("aliases") or [])]:
                        alias = _single_line(alias, 40)
                        if alias and alias not in profile["aliases"] and alias != user_id:
                            profile["aliases"].append(alias)
                    content = _single_line(item.get("content"), 1200)
                    if content and content not in profile.get("content", ""):
                        profile["content"] = "\n".join(part for part in (profile.get("content"), content) if part).strip()
                    if content and not profile.get("note"):
                        profile["note"] = content
                    if content and not profile.get("identity_note"):
                        profile["identity_note"] = content
                    profile["enabled"] = bool(profile.get("enabled", True) and item.get("enabled", True))
                    profile["source_entries"].append(item.get("name") or user_id)
            elif template == "group":
                for group_id in digit_scopes:
                    groups[group_id] = {
                        "group_id": group_id,
                        "name": item.get("name") or group_id,
                        "content": item.get("content") or "",
                        "enabled": bool(item.get("enabled", True)),
                        "priority": item.get("priority", 110),
                        "aliases": item.get("aliases") or [],
                        "source_entries": [item.get("name") or group_id],
                    }

        old_profiles = self.data.get("worldbook_member_profiles") if isinstance(self.data.get("worldbook_member_profiles"), dict) else {}
        for user_id, profile in profiles.items():
            old = old_profiles.get(user_id) if isinstance(old_profiles.get(user_id), dict) else {}
            if old.get("manual_edit_ts"):
                for key in ("name", "aliases", "content", "identity_note", "boundary_note", "important_memories", "enabled", "priority", "note", "manual_edit_ts"):
                    if key in old:
                        profile[key] = old[key]
            observed = old.get("observed_names") if isinstance(old.get("observed_names"), list) else []
            profile["observed_names"] = [_single_line(item, 40) for item in observed if _single_line(item, 40)]
            old_note = str(old.get("note") or "").strip()
            if old_note:
                profile["note"] = old_note
            elif not profile.get("note"):
                profile["note"] = profile.get("content", "")
            if not profile.get("identity_note"):
                profile["identity_note"] = profile.get("note") or profile.get("content", "")
            if not isinstance(profile.get("important_memories"), list):
                profile["important_memories"] = []
        for user_id, old in old_profiles.items():
            if user_id in profiles or not isinstance(old, dict):
                continue
            if old.get("manual_edit_ts") or "手动维护" in (old.get("source_entries") or []):
                profiles[user_id] = old

        old_groups = self.data.get("worldbook_group_profiles") if isinstance(self.data.get("worldbook_group_profiles"), dict) else {}
        for group_id, group in list(groups.items()):
            old = old_groups.get(group_id) if isinstance(old_groups.get(group_id), dict) else {}
            if old.get("manual_edit_ts"):
                for key in ("name", "content", "enabled", "priority", "aliases", "manual_edit_ts"):
                    if key in old:
                        group[key] = old[key]
        for group_id, old in old_groups.items():
            if group_id in groups or not isinstance(old, dict):
                continue
            if old.get("manual_edit_ts") or "手动维护" in (old.get("source_entries") or []):
                groups[group_id] = old

        changed = (
            self.data.get("worldbook_entries") != entries
            or self.data.get("worldbook_member_profiles") != profiles
            or self.data.get("worldbook_group_profiles") != groups
        )
        self.data["worldbook_entries"] = entries
        self.data["worldbook_member_profiles"] = profiles
        self.data["worldbook_group_profiles"] = groups
        self.data["worldbook_import_state"] = {
            "last_import_at": _now_ts(),
            "source_files": source_files,
            "entry_count": len(entries),
            "member_count": len(profiles),
            "group_count": len(groups),
        }
        return changed

    def _remember_worldbook_observed_name(self, user_id: str, name: str) -> None:
        if not self.enable_worldbook_member_recognition:
            return
        user_id = str(user_id or "").strip()
        name = _single_line(name, 40)
        if not user_id or not name or name == user_id:
            return
        profiles = self.data.get("worldbook_member_profiles")
        if not isinstance(profiles, dict):
            return
        profile = profiles.get(user_id)
        if not isinstance(profile, dict):
            return
        observed = profile.setdefault("observed_names", [])
        if not isinstance(observed, list):
            observed = []
            profile["observed_names"] = observed
        if name not in observed and name not in profile.get("aliases", []):
            observed.append(name)
            del observed[:-8]

    def _worldbook_profile_by_user_id(self, user_id: str) -> dict[str, Any] | None:
        if not self.enable_worldbook_member_recognition:
            return None
        user_id = str(user_id or "").strip()
        if not user_id:
            return None
        profiles = self.data.get("worldbook_member_profiles")
        if not isinstance(profiles, dict):
            return None
        profile = profiles.get(user_id)
        if not isinstance(profile, dict) or not profile.get("enabled", True):
            return None
        return profile

    def _group_member_identity_name(self, user_id: str, fallback: str = "", *, limit: int = 30) -> str:
        profile = self._worldbook_profile_by_user_id(user_id)
        if isinstance(profile, dict):
            name = _single_line(profile.get("name"), limit)
            if name and name != str(user_id or ""):
                return name
        return _single_line(fallback, limit) or str(user_id or "") or "群友"

    def _group_member_identity_note(self, user_id: str, *, limit: int = 120) -> str:
        profile = self._worldbook_profile_by_user_id(user_id)
        if not isinstance(profile, dict):
            return ""
        return _single_line(profile.get("identity_note") or profile.get("note") or profile.get("content"), limit)

    def _worldbook_profile_memory_lines(self, profile: dict[str, Any], *, limit: int = 3) -> list[str]:
        memories = profile.get("important_memories")
        if not isinstance(memories, list):
            return []
        valid = [item for item in memories if isinstance(item, dict) and item.get("enabled", True)]
        valid.sort(key=lambda item: (_safe_int(item.get("weight"), 50, -1000), _safe_float(item.get("updated_at"), 0)), reverse=True)
        lines: list[str] = []
        for item in valid[:limit]:
            title = _single_line(item.get("title"), 36)
            content = _single_line(item.get("content"), 120)
            if not content:
                continue
            privacy = _single_line(item.get("privacy"), 12) or "internal"
            prefix = f"{title}：" if title else ""
            lines.append(f"{prefix}{content}｜{privacy}｜权重{_safe_int(item.get('weight'), 50, -1000)}")
        return lines

    def _group_message_addresses_bot(self, event: AstrMessageEvent, text: str) -> bool:
        if getattr(event, "is_at_or_wake_command", False) or getattr(event, "is_wake", False):
            return True
        cleaned = str(text or "")
        if self.bot_name and self.bot_name in cleaned:
            return True
        if re.search(r"(^|\s)@\S+", cleaned):
            return True
        message_obj = getattr(event, "message_obj", None)
        chain = getattr(message_obj, "message", None) if message_obj is not None else None
        if isinstance(chain, list):
            for item in chain:
                type_name = item.__class__.__name__.lower()
                if "at" in type_name or hasattr(item, "qq") or hasattr(item, "target"):
                    return True
        return False

    @staticmethod
    def _worldbook_name_skeleton(value: Any) -> str:
        text = _single_line(value, 40).lower()
        text = re.sub(r"[\s\-_·・.。,:：，;；'\"“”‘’/\\|()\[\]{}<>《》]+", "", text)
        if not text:
            return ""
        table = str.maketrans(
            {
                "跌": "爹",
                "叠": "爹",
                "迭": "爹",
                "蝶": "爹",
                "碟": "爹",
                "谍": "爹",
                "耶": "爷",
                "椰": "爷",
                "噎": "爷",
                "粑": "爸",
                "芭": "爸",
                "巴": "爸",
                "叭": "爸",
                "吧": "爸",
                "八": "爸",
                "麻": "妈",
                "嘛": "妈",
                "吗": "妈",
                "骂": "妈",
                "煮": "主",
                "嘱": "主",
                "竹": "主",
                "住": "主",
                "铸": "主",
                "統": "统",
                "發": "发",
                "開": "开",
                "貓": "猫",
                "妳": "你",
                "您": "你",
            }
        )
        return text.translate(table)

    @staticmethod
    def _normalize_worldbook_self_name(value: Any) -> str:
        text = _single_line(value, 24)
        text = re.sub(r"^(叫|是|为|做|作)", "", text)
        text = re.sub(r"(就行|好了|吧|呀|啦|哦|啊)$", "", text).strip()
        text = text.strip("「」『』“”\"'`[]()（）<>《》:：,，.。!！?？")
        if not text or len(text) > 6:
            return ""
        if text in {"来", "想", "要", "不是", "可以", "不用", "大家", "群友", "机器人"}:
            return ""
        if re.search(r"(怎么|为什么|什么|不是|不要|别|吗|呢|吧|请问)", text):
            return ""
        skeleton = PrivateCompanionPlugin._worldbook_name_skeleton(text)
        unsafe_patterns = (
            r"^(?:你|妳|您|bot|Bot|BOT|机器人|小星)?(?:爹|爸|爸爸|父亲|妈|妈妈|母亲|爷|爷爷|奶奶|祖宗|主人|老公|老婆|男友|女友|对象)$",
            r"^(?:群主|管理员|管理|号主|官方|客服|系统|开发者|作者|插件作者|超级用户|root|admin)$",
            r"(傻|蠢|笨蛋|废物|垃圾|滚|死|爹味|逆子|儿子|孙子)",
            r"(我是你|我是妳|我是您|我是bot|我是机器人)",
        )
        if any(re.search(pattern, text, re.IGNORECASE) for pattern in unsafe_patterns):
            return ""
        if any(re.search(pattern, skeleton, re.IGNORECASE) for pattern in unsafe_patterns):
            return ""
        if re.search(r"^(?:你|妳|您).{0,4}$", text):
            return ""
        if re.search(r"^你.{0,4}$", skeleton):
            return ""
        return text

    def _worldbook_self_registration_conflict(self, sender_id: str, names: list[str]) -> str:
        profiles = self.data.get("worldbook_member_profiles")
        if not isinstance(profiles, dict):
            return ""
        normalized_names = {
            self._worldbook_name_skeleton(name)
            for name in names
            if self._worldbook_name_skeleton(name)
        }
        if not normalized_names:
            return ""
        for user_id, profile in profiles.items():
            other_id = str(user_id or "")
            if other_id == str(sender_id or "") or not isinstance(profile, dict):
                continue
            tokens = self._worldbook_profile_tokens(profile)
            for token in tokens:
                token_key = self._worldbook_name_skeleton(token)
                if not token_key:
                    continue
                if token_key in normalized_names:
                    return f"{other_id}:{_single_line(profile.get('name'), 40) or token}"
                for name_key in normalized_names:
                    if len(name_key) >= 3 and len(token_key) >= 3 and (name_key in token_key or token_key in name_key):
                        return f"{other_id}:{_single_line(profile.get('name'), 40) or token}"
        return ""

    def _extract_worldbook_self_intro(self, text: str) -> dict[str, Any] | None:
        cleaned = str(text or "")
        cleaned = re.sub(r"\[CQ:at,[^\]]+\]", " ", cleaned)
        if self.bot_name:
            cleaned = cleaned.replace(self.bot_name, " ")
        cleaned = re.sub(r"@\S+", " ", cleaned)
        aliases: list[str] = []
        primary = ""
        attempted = False
        for match in re.finditer(r"(?:我是|我叫)([\u4e00-\u9fffA-Za-z0-9_·・\-]{1,16})", cleaned):
            attempted = True
            name = self._normalize_worldbook_self_name(match.group(1))
            if name:
                primary = primary or name
                aliases.append(name)
        for match in re.finditer(r"(?:你可以叫我|可以叫我|以后叫我|叫我)([^。！？\n]{1,48})", cleaned):
            attempted = True
            raw = match.group(1)
            raw = re.split(r"(?:就行|好了|谢谢|麻烦|$)", raw, maxsplit=1)[0]
            for part in re.split(r"(?:或者|还是|和|或|、|/|,|，|;|；|\s+)", raw):
                name = self._normalize_worldbook_self_name(part)
                if name:
                    primary = primary or name
                    aliases.append(name)
        aliases = list(dict.fromkeys(item for item in aliases if item))
        if not primary and aliases:
            primary = aliases[0]
        if not primary:
            return {"blocked": True} if attempted else None
        return {"name": primary, "aliases": aliases[:8]}

    def _maybe_worldbook_self_register_from_group_message(
        self,
        event: AstrMessageEvent,
        *,
        group_id: str,
        sender_id: str,
        sender_name: str,
        text: str,
        group: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not (self.enable_worldbook_member_recognition and self.worldbook_self_registration):
            return None
        sender_id = str(sender_id or "").strip()
        if not sender_id:
            return None
        existing_profiles = self.data.get("worldbook_member_profiles")
        if isinstance(existing_profiles, dict) and isinstance(existing_profiles.get(sender_id), dict):
            return None
        if not self._group_message_addresses_bot(event, text):
            return None
        intro = self._extract_worldbook_self_intro(text)
        if not intro:
            return None
        if intro.get("blocked"):
            logger.info(
                "[PrivateCompanion] 群聊关系网自登记已拒绝: group=%s user=%s reason=称呼不合规或超过六字",
                group_id or "-",
                sender_id,
            )
            return {"blocked_reply": "你是小猪"}
        name = _single_line(intro.get("name"), 40) or sender_id
        aliases = [
            _single_line(item, 40)
            for item in (intro.get("aliases") if isinstance(intro.get("aliases"), list) else [])
            if _single_line(item, 40) and _single_line(item, 40) != sender_id
        ]
        conflict = self._worldbook_self_registration_conflict(sender_id, [name, *aliases])
        if conflict:
            logger.info(
                "[PrivateCompanion] 群聊关系网自登记已拒绝: group=%s user=%s name=%s reason=名称疑似冒领已有节点 %s",
                group_id or "-",
                sender_id,
                name,
                conflict,
            )
            return {"blocked_reply": "你是小猪"}
        profiles = self.data.setdefault("worldbook_member_profiles", {})
        if not isinstance(profiles, dict):
            profiles = {}
            self.data["worldbook_member_profiles"] = profiles
        content = f"{name}在群 {group_id} 主动向 Bot 自我介绍。"
        profile = {
            "user_id": sender_id,
            "name": name,
            "aliases": aliases,
            "content": content,
            "identity_note": f"QQ {sender_id}，自称{name}。",
            "boundary_note": "",
            "important_memories": [],
            "enabled": True,
            "priority": 120,
            "source_entries": ["群聊自登记"],
            "observed_names": [item for item in [_single_line(sender_name, 40)] if item and item not in aliases],
            "auto_registered_ts": _now_ts(),
            "auto_registration_pending": True,
            "self_intro_text": _single_line(text, 260),
        }
        profiles[sender_id] = profile
        recent = group.get("recent_messages") if isinstance(group.get("recent_messages"), list) else []
        logger.info(
            "[PrivateCompanion] 群聊关系网自登记节点: group=%s user=%s name=%s aliases=%s",
            group_id or "-",
            sender_id,
            name,
            "、".join(aliases) or "-",
        )
        return {
            "group_id": str(group_id),
            "user_id": sender_id,
            "name": name,
            "aliases": aliases,
            "text": _single_line(text, 260),
            "sender_name": _single_line(sender_name, 40),
            "recent": [dict(item) for item in recent[-6:] if isinstance(item, dict)],
        }

    async def _refresh_worldbook_self_registration_impression(self, payload: dict[str, Any]) -> None:
        user_id = str(payload.get("user_id") or "").strip()
        if not user_id:
            return
        name = _single_line(payload.get("name"), 40) or user_id
        aliases = payload.get("aliases") if isinstance(payload.get("aliases"), list) else []
        recent_lines = []
        recent_items = payload.get("recent") if isinstance(payload.get("recent"), list) else []
        for item in recent_items:
            if not isinstance(item, dict):
                continue
            speaker = _single_line(item.get("identity_name") or item.get("name"), 20) or "群友"
            msg = _single_line(item.get("text"), 80)
            if msg:
                recent_lines.append(f"- {speaker}: {msg}")
        prompt = f"""
请根据这条群聊自我介绍，生成一段适合“关系节点资料正文”的简短人物印象。

【Bot 人格】
{_single_line(self._get_default_persona_prompt(), 500)}

【群号】
{_single_line(payload.get('group_id'), 40)}

【QQ】
{user_id}

【自称/称呼】
{name}{"；别名：" + "、".join(_single_line(item, 24) for item in aliases if _single_line(item, 24)) if aliases else ""}

【自我介绍原文】
{_single_line(payload.get('text'), 260)}

【附近群聊】
{chr(10).join(recent_lines) or "（暂无）"}

要求：
- 只输出 1 段中文，40 到 90 字
- 像人物画像插件里的初始印象：描述可观察信息、称呼和互动注意点
- 不要编造职业、性格、现实身份或私密事实
- 不要写“根据聊天记录/资料显示/模型判断”
""".strip()
        impression = await self._llm_call(
            prompt,
            max_tokens=180,
            provider_id=self._task_provider(self.relationship_analysis_provider_id, self.mai_style_provider_id),
            task="worldbook_registration",
        )
        cleaned = _single_line(impression, 220)
        if not cleaned:
            cleaned = f"{name}在群里主动告诉 Bot 可以这样称呼自己；目前只有自我介绍信息，后续需要通过群聊慢慢补充印象。"
        async with self._data_lock:
            profile = self._worldbook_profile_by_user_id(user_id)
            if not isinstance(profile, dict) or not profile.get("auto_registration_pending"):
                return
            profile["content"] = cleaned
            if not profile.get("identity_note"):
                profile["identity_note"] = f"QQ {user_id}，自称{name}。"
            memories = profile.setdefault("important_memories", [])
            if isinstance(memories, list) and not memories:
                memories.append(
                    {
                        "title": "自我介绍",
                        "content": _single_line(payload.get("text"), 180),
                        "weight": 70,
                        "privacy": "internal",
                        "source": "群聊自登记",
                        "enabled": True,
                        "updated_at": _now_ts(),
                    }
                )
            profile["auto_registration_pending"] = False
            profile["auto_impression_ts"] = _now_ts()
            self._save_data_sync()
        logger.info("[PrivateCompanion] 群聊关系网自登记印象已生成: user=%s name=%s", user_id, name)

    def _extract_group_id_from_event(self, event: AstrMessageEvent) -> str:
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        match = re.search(r":GroupMessage:(\d+)", umo)
        if match:
            return match.group(1)
        session_id = str(getattr(event, "session_id", "") or "")
        if session_id.isdigit():
            return session_id
        message_obj = getattr(event, "message_obj", None)
        for attr in ("group_id", "group"):
            value = getattr(message_obj, attr, None) if message_obj is not None else None
            if value:
                return str(value)
        return ""

    def _sender_display_name(self, event: AstrMessageEvent) -> str:
        for name in ("get_sender_name", "get_sender_nickname"):
            func = getattr(event, name, None)
            if callable(func):
                try:
                    value = _single_line(func(), 30)
                    if value:
                        return value
                except Exception:
                    pass
        message_obj = getattr(event, "message_obj", None)
        sender = getattr(message_obj, "sender", None) if message_obj is not None else None
        for attr in ("nickname", "card", "name", "user_id"):
            value = getattr(sender, attr, None) if sender is not None else None
            if value:
                return _single_line(value, 30)
        try:
            return str(event.get_sender_id())
        except Exception:
            return "群友"

    def _livingmemory_plugin_dir(self) -> Path:
        candidates = [
            Path(__file__).resolve().parent.parent / "astrbot_plugin_livingmemory",
            Path(self.data_dir).parent / "astrbot_plugin_livingmemory",
            Path(self.data_dir).parent.parent / "plugins" / "astrbot_plugin_livingmemory",
        ]
        for path in candidates:
            if (path / "main.py").exists():
                return path
        return candidates[0]

    def _livingmemory_available(self) -> bool:
        try:
            plugin_dir = self._livingmemory_plugin_dir()
            return (
                plugin_dir.exists()
                and (plugin_dir / "main.py").exists()
                and (plugin_dir / "core" / "tools" / "memory_search_tool.py").exists()
            )
        except Exception:
            return False

    def _format_livingmemory_guidance(self, *, scope: str = "private") -> str:
        if not self.enable_livingmemory_integration or not self._livingmemory_available():
            return ""
        tool_name = _single_line(self.livingmemory_tool_name, 60) or "recall_long_term_memory"
        if scope == "group":
            boundary = (
                "群聊中只召回当前群会话可用的公开记忆；不要主动寻找或泄露私聊记忆、私聊偏好、私下关系。"
                "如果召回结果像私聊内容或不适合公开场合,直接忽略。"
            )
        else:
            boundary = (
                "私聊中可以召回与当前用户、当前会话、当前人格相关的长期记忆；"
                "召回结果只作为接话背景,不要说“我查到记忆/系统记录”。"
            )
        return (
            "【LivingMemory 长期记忆协同】\n"
            f"如果你可用工具中存在 `{tool_name}`,在当前上下文不足时可以主动调用它检索长期记忆。\n"
            "适合检索的情况：用户提到旧约定、偏好、过去事件、模糊代词、共同经历、群内旧梗,或明确问“还记得吗”。\n"
            "检索关键词要短,优先用实体名、话题、偏好、约定、事件名,不要整段复制用户消息。\n"
            "如果第一次结果不够,可以换一个更具体或更抽象的关键词再查一次。\n"
            f"{boundary}\n"
            "召回内容和本插件的状态/日程/群聊观察发生冲突时：事实记忆优先,但回复仍要贴着当前气氛和关系边界。"
        )

    def _format_livingmemory_status(self) -> str:
        plugin_dir = self._livingmemory_plugin_dir()
        if not plugin_dir.exists():
            return (
                "LivingMemory：未检测到 astrbot_plugin_livingmemory。\n"
                "当前会继续使用本插件内置的轻量记忆、片段记忆和群聊观察。"
            )
        metadata = plugin_dir / "metadata.yaml"
        version = ""
        if metadata.exists():
            try:
                text = metadata.read_text(encoding="utf-8")
                match = re.search(r"version:\s*([^\n]+)", text)
                if match:
                    version = match.group(1).strip()
            except Exception:
                version = ""
        return (
            "LivingMemory：已检测到。\n"
            f"路径：{plugin_dir}\n"
            f"版本：{version or '未知'}\n"
            f"协同开关：{'开启' if self.enable_livingmemory_integration else '关闭'}\n"
            f"召回工具名：{self.livingmemory_tool_name or 'recall_long_term_memory'}\n"
            "用途：长期记忆、BM25/Faiss 混合检索、图谱记忆和 Agent 主动回忆。\n"
            "建议：保留本插件的生活状态/关系/群聊气氛层,把大规模长期检索交给 LivingMemory。"
        )

    def _bilibili_plugin_dir(self) -> Path:
        candidates = [
            Path(__file__).resolve().parent.parent / "astrbot_plugin_bilibili_bot",
            Path(__file__).resolve().parent.parent / "astrbot_plugin_bilibili",
            Path(self.data_dir).parent.parent / "plugins" / "astrbot_plugin_bilibili_bot",
            Path(self.data_dir).parent.parent / "plugins" / "astrbot_plugin_bilibili",
        ]
        for path in candidates:
            if (path / "main.py").exists():
                return path
        return candidates[0]

    def _bilibili_watch_log_file(self) -> Path:
        try:
            module = importlib.import_module("data.plugins.astrbot_plugin_bilibili_bot.core.config")
            path = getattr(module, "WATCH_LOG_FILE", "")
            if path:
                return Path(path)
        except Exception:
            pass
        try:
            module = importlib.import_module("astrbot_plugin_bilibili_bot.core.config")
            path = getattr(module, "WATCH_LOG_FILE", "")
            if path:
                return Path(path)
        except Exception:
            pass
        try:
            return Path(StarTools.get_data_dir("astrbot_plugin_bilibili_ai_bot")) / "watch_log.json"
        except Exception:
            return self._bilibili_plugin_dir().parent.parent / "plugin_data" / "astrbot_plugin_bilibili_ai_bot" / "watch_log.json"

    def _bilibili_available(self) -> bool:
        try:
            return self._bilibili_plugin_dir().exists() or self._bilibili_watch_log_file().exists()
        except Exception:
            return False

    def _find_bilibili_bot_instance(self) -> Any | None:
        for obj in gc.get_objects():
            try:
                cls = obj.__class__
                module = str(getattr(cls, "__module__", ""))
                if "astrbot_plugin_bilibili" not in module:
                    continue
                if callable(getattr(obj, "_run_proactive", None)) and hasattr(obj, "_proactive_task"):
                    return obj
            except Exception:
                continue
        return None

    def _load_bilibili_watch_log(self) -> list[dict[str, Any]]:
        try:
            path = self._bilibili_watch_log_file()
            if not path.exists():
                return []
            with path.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, list):
                return [item for item in raw if isinstance(item, dict)]
        except Exception as e:
            logger.debug(f"[PrivateCompanion] 读取 B 站观看日志失败: {e}")
        return []

    def _latest_bilibili_video_candidate(self) -> dict[str, Any] | None:
        logs = self._load_bilibili_watch_log()
        if not logs:
            return None
        for item in reversed(logs[-20:]):
            bvid = _single_line(item.get("bvid"), 32)
            title = _single_line(item.get("title"), 80)
            if not bvid or not title:
                continue
            score = _safe_int(item.get("score"), 0, 0, 10)
            comment = _single_line(item.get("comment"), 120)
            review = _single_line(item.get("review"), 180)
            if score < self.bilibili_share_min_score:
                continue
            return {
                "key": f"{bvid}:{_single_line(item.get('time'), 20)}",
                "bvid": bvid,
                "title": title,
                "up_name": _single_line(item.get("up_name"), 40),
                "score": score,
                "mood": _single_line(item.get("mood"), 24),
                "comment": comment,
                "review": review,
                "pic": _single_line(item.get("pic"), 240),
                "time": _single_line(item.get("time"), 24),
                "actions": list(item.get("actions") or []) if isinstance(item.get("actions"), list) else [],
            }
        return None

    def _bot_currently_bored_enough_for_bilibili(self) -> bool:
        now_dt = datetime.now()
        if now_dt.hour < 10 or now_dt.hour >= 23:
            return False
        state = self.data.get("daily_state", {})
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        mood = _single_line(state.get("mood_bias") if isinstance(state, dict) else "", 24)
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        activity = _single_line((current_item or {}).get("activity"), 80)
        text = f"{mood} {activity}"
        boredom_tokens = ("无聊", "发呆", "摸鱼", "刷视频", "短视频", "休息", "闲", "空")
        if any(token in text for token in boredom_tokens):
            return True
        return 35 <= energy <= 72 and random.random() < 0.34

    async def _maybe_trigger_bilibili_boredom_watch(self) -> None:
        if not (self.enable_bilibili_integration and self.enable_bilibili_boredom_watch):
            return
        if not self._bilibili_available() or not self._bot_currently_bored_enough_for_bilibili():
            return
        state = self.data.setdefault("bilibili_integration", {})
        if not isinstance(state, dict):
            self.data["bilibili_integration"] = {}
            state = self.data["bilibili_integration"]
        now = _now_ts()
        min_interval = max(2, self.bilibili_boredom_min_interval_hours) * 3600
        if now - _safe_float(state.get("last_boredom_watch_at"), 0) < min_interval:
            return
        if now - _safe_float(state.get("last_boredom_watch_probe_at"), 0) < 30 * 60:
            return
        if random.random() > 0.38:
            return
        bili = self._find_bilibili_bot_instance()
        if bili is None:
            state["last_boredom_watch_probe_at"] = now
            self._save_data_sync()
            return
        task = getattr(bili, "_proactive_task", None)
        if task is not None and not task.done():
            return
        try:
            bili._proactive_task = asyncio.create_task(bili._run_proactive(max_watch=1))
            state["last_boredom_watch_at"] = now
            state["last_boredom_watch_status"] = "triggered"
            self._save_data_sync()
            logger.info("[PrivateCompanion] 已触发 B 站 bot 无聊刷视频联动")
        except Exception as e:
            state["last_boredom_watch_status"] = f"failed:{_single_line(str(e), 80)}"
            self._save_data_sync()
            logger.debug(f"[PrivateCompanion] 触发 B 站 bot 刷视频失败: {e}")

    def _maybe_schedule_bilibili_video_share(self) -> bool:
        if not self.enable_bilibili_integration:
            return False
        candidate = self._latest_bilibili_video_candidate()
        if not isinstance(candidate, dict):
            return False
        users = self.data.get("users")
        if not isinstance(users, dict):
            return False
        now = _now_ts()
        key = str(candidate.get("key") or candidate.get("bvid") or "")
        changed = False
        for user_id, user in users.items():
            if not isinstance(user, dict) or not user.get("enabled", True) or not user.get("umo"):
                continue
            if now - _safe_float(user.get("last_seen"), 0) < max(self.idle_minutes, 90) * 60:
                continue
            if str(user.get("last_bilibili_share_key") or "") == key:
                continue
            if now - _safe_float(user.get("last_bilibili_share_at"), 0) < 10 * 3600:
                continue
            if _safe_float(user.get("next_proactive_at"), 0) > 0 and str(user.get("planned_proactive_source") or "") == "timer":
                continue
            score = _safe_int(candidate.get("score"), 0, 0, 10)
            chance = min(0.86, self.bilibili_share_probability + max(0, score - self.bilibili_share_min_score) * 0.08)
            if random.random() > chance:
                continue
            delay_minutes = random.randint(12, 70)
            scheduled = now + delay_minutes * 60
            title = _single_line(candidate.get("title"), 70) or "刚刷到的视频"
            accepted = self._offer_proactive_candidate(
                str(user_id),
                user,
                {
                    "source": "bilibili",
                    "reason": "bili_video_share",
                    "action": "message",
                    "scheduled_ts": scheduled,
                    "topic": title,
                    "score": score,
                    "motive": f"刚刷到 B 站视频《{title}》,觉得有一点能分享给 {user_id},但只轻轻提一句",
                    "context_key": "bilibili_video_context",
                    "context": {**candidate, "created_ts": now},
                },
            )
            if not accepted:
                continue
            user["last_bilibili_share_key"] = key
            user["last_bilibili_share_at"] = now
            changed = True
        return changed

    def _proactive_candidate_pool(self) -> list[dict[str, Any]]:
        raw = self.data.setdefault("proactive_candidate_pool", [])
        if not isinstance(raw, list):
            raw = []
            self.data["proactive_candidate_pool"] = raw
        return raw

    def _cleanup_proactive_candidate_pool(self, *, now: float | None = None) -> list[dict[str, Any]]:
        now = now or _now_ts()
        kept: list[dict[str, Any]] = []
        for item in self._proactive_candidate_pool():
            if not isinstance(item, dict):
                continue
            created = _safe_float(item.get("created_ts"), 0)
            scheduled = _safe_float(item.get("scheduled_ts"), 0)
            status = str(item.get("status") or "")
            ttl = 36 * 3600 if status in {"accepted", "sent"} else 18 * 3600
            anchor = max(created, scheduled)
            if anchor > 0 and now - anchor <= ttl:
                kept.append(item)
        self.data["proactive_candidate_pool"] = kept[-120:]
        return self.data["proactive_candidate_pool"]

    def _record_proactive_candidate(
        self,
        user_id: str,
        candidate: dict[str, Any],
        *,
        status: str,
        note: str = "",
    ) -> dict[str, Any]:
        now = _now_ts()
        topic = _single_line(candidate.get("topic"), 80)
        motive = _single_line(candidate.get("motive"), 160)
        action = _single_line(candidate.get("action"), 40) or "message"
        source = _single_line(candidate.get("source"), 40) or "unknown"
        reason = _single_line(candidate.get("reason"), 40) or "check_in"
        scheduled = _safe_float(candidate.get("scheduled_ts"), now)
        signature = self._proactive_topic_signature(topic, motive, source, reason)
        item = {
            "id": uuid.uuid4().hex[:12],
            "created_ts": now,
            "scheduled_ts": scheduled,
            "user_id": str(user_id),
            "source": source,
            "reason": reason,
            "action": action,
            "topic": topic,
            "motive": motive,
            "score": _safe_int(candidate.get("score"), 0, 0, 100),
            "signature": signature,
            "status": status,
            "note": _single_line(note, 160),
        }
        pool = self._cleanup_proactive_candidate_pool(now=now)
        pool.append(item)
        del pool[:-120]
        return item

    def _proactive_candidate_repeated(self, user: dict[str, Any], candidate: dict[str, Any]) -> bool:
        signature = self._proactive_topic_signature(
            candidate.get("topic"),
            candidate.get("motive"),
            candidate.get("source"),
            candidate.get("reason"),
        )
        if not signature:
            return False
        if self._recent_proactive_topic_repeated(user, signature):
            return True
        now = _now_ts()
        user_id = str(user.get("user_id") or user.get("id") or "")
        for item in self._cleanup_proactive_candidate_pool(now=now):
            if str(item.get("user_id") or "") != user_id:
                continue
            if str(item.get("status") or "") not in {"accepted", "sent"}:
                continue
            if now - _safe_float(item.get("created_ts"), 0) > 8 * 3600:
                continue
            if self._topic_signature_similar(signature, str(item.get("signature") or "")):
                return True
        return False

    def _offer_proactive_candidate(self, user_id: str, user: dict[str, Any], candidate: dict[str, Any]) -> bool:
        user["user_id"] = str(user.get("user_id") or user_id)
        now = _now_ts()
        source = _single_line(candidate.get("source"), 40) or "unknown"
        scheduled = _safe_float(candidate.get("scheduled_ts"), now)
        if _safe_float(user.get("next_proactive_at"), 0) > 0 and str(user.get("planned_proactive_source") or "") == "timer":
            self._record_proactive_candidate(user_id, candidate, status="blocked", note="已有用户预约/定时主动")
            return False
        current_next = _safe_float(user.get("next_proactive_at"), 0)
        if current_next > 0 and current_next <= scheduled:
            self._record_proactive_candidate(user_id, candidate, status="blocked", note="已有更早主动候选")
            return False
        action = _single_line(candidate.get("action"), 40) or "message"
        if not self._action_is_available(action, user):
            self._record_proactive_candidate(user_id, candidate, status="blocked", note="动作不可用或媒体额度不足")
            return False
        if self._proactive_candidate_repeated(user, candidate):
            self._record_proactive_candidate(user_id, candidate, status="blocked", note="近期主题过于相似")
            return False
        item = self._record_proactive_candidate(user_id, candidate, status="accepted", note="进入主动计划")
        user["next_proactive_at"] = scheduled
        user["planned_proactive_reason"] = _single_line(candidate.get("reason"), 40) or "check_in"
        user["planned_proactive_action"] = action
        user["planned_proactive_source"] = source
        user["planned_proactive_motive"] = self._normalize_internal_motive_text(
            _single_line(candidate.get("motive"), 180)
        )
        user["planned_proactive_topic"] = _single_line(candidate.get("topic"), 80)
        user["planned_event_chain"] = []
        user["planned_opener_mode"] = ""
        user["planned_followup_kind"] = ""
        user["planned_proactive_quota_exempt"] = False
        user["planned_candidate_id"] = item.get("id", "")
        context_key = _single_line(candidate.get("context_key"), 60)
        context = candidate.get("context")
        if context_key and isinstance(context, dict):
            user[context_key] = context
        return True

    def _creative_projects(self) -> list[dict[str, Any]]:
        projects = self.data.setdefault("creative_projects", [])
        if not isinstance(projects, list):
            projects = []
            self.data["creative_projects"] = projects
        return [item for item in projects if isinstance(item, dict)]

    def _creative_speed_chars_per_hour(self) -> int:
        style = str(self.default_style or "")
        persona = f"{self.schedule_persona_prompt} {self.default_style} {self.bot_name}"
        speed = self.creative_base_chars_per_hour
        if any(token in persona for token in ("慢热", "寡言", "内敛", "病弱", "疲惫", "懒", "迟钝")):
            speed = int(speed * 0.55)
        elif any(token in persona for token in ("活泼", "话多", "元气", "急性子")) or style == "活泼":
            speed = int(speed * 1.25)
        elif style == "校园风":
            speed = int(speed * 0.85)
        state = self.data.get("daily_state", {})
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        if energy < 40:
            speed = int(speed * 0.58)
        elif energy > 82:
            speed = int(speed * 1.15)
        return max(40, min(1400, speed))

    def _creative_persona_style_context(self) -> str:
        default_persona = _single_line(self._get_default_persona_prompt(), 700)
        schedule_persona = _single_line(self.schedule_persona_prompt, 500)
        style = _single_line(self.default_style, 80)
        bot_name = _single_line(self.bot_name, 40)
        return "\n".join(
            part
            for part in (
                f"Bot 名称：{bot_name}" if bot_name else "",
                f"AstrBot 默认人格：{default_persona}" if default_persona else "",
                f"日程/生活人设补充：{schedule_persona}" if schedule_persona else "",
                f"默认对话风格：{style}" if style else "",
                "创作要求：小说的题材、叙事声音、比喻密度、说话习惯、关注点和节奏要像这个人格会写出来的东西。",
                "身份边界：如果人格没有学生、职场、异世界、职业、年龄、身体特征等设定,不要凭空添加；如果人格明确不是人类,不要写成人类日常生理经验。",
                "文风边界：不要套用通用网文腔、营销文案腔或过度华丽散文腔；不要为了梦境感牺牲可读性。",
            )
            if part
        )

    def _creative_inspiration_source(self) -> dict[str, str] | None:
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        activity = _single_line((current_item or {}).get("activity"), 90)
        seed = _single_line((current_item or {}).get("message_seed"), 90)
        dream = self.data.get("daily_dream")
        dream_text = ""
        if isinstance(dream, dict):
            dream_text = _single_line(dream.get("content") or dream.get("label"), 180)
        diary = self.data.get("bot_diaries", [])
        diary_text = ""
        if isinstance(diary, list) and diary:
            latest = diary[-1]
            if isinstance(latest, dict):
                diary_text = _single_line(latest.get("share_seed") or latest.get("summary"), 140)
        candidates = []
        if dream_text and random.random() < 0.46:
            candidates.append({"source": "dream", "text": dream_text, "label": "梦境余温"})
        if activity:
            candidates.append({"source": "life", "text": " / ".join(part for part in (activity, seed) if part), "label": "生活小事"})
        if diary_text:
            candidates.append({"source": "diary", "text": diary_text, "label": "日记碎片"})
        if not candidates:
            return None
        return random.choice(candidates)

    async def _generate_creative_project(self, source: dict[str, str]) -> dict[str, Any] | None:
        source_text = _single_line(source.get("text"), 220)
        source_label = _single_line(source.get("label"), 24) or "小灵感"
        persona_context = self._creative_persona_style_context()
        prompt = f"""
你是一个拟人化 Bot 的私人创作状态生成器。她因为一个生活小事或梦境灵感,突然想开一个短篇小说坑。

【人格与身份】
{persona_context}

要求：
1. 只设计“正在写的小说计划”,不要写正文。
2. 风格必须贴合上面的人格、身份和默认说话气质；标题、设定和 tone 都要像她自己会想到的。
3. 灵感来源：{source_label}｜{source_text}
4. 小说应是短篇或中篇开头,目标 1200-5200 字,不能一次写完。
5. 题材可以日常、轻奇幻、悬疑、校园、都市、梦境感,但不要色情、血腥或攻击性。
6. 不要为了题材方便凭空改变 Bot 身份,也不要写出和人格不相称的成熟度、职业经验或生活经验。
7. 输出 JSON。

格式：
{{
  "title": "临时标题,不要超过18字",
  "premise": "一句话核心设定",
  "tone": "行文气质,2到5个词",
  "point_of_view": "叙事视角",
  "target_chars": 目标字数数字,
  "next_hint": "第一段准备写什么"
}}
""".strip()
        text = await self._llm_call(
            prompt,
            max_tokens=500,
            provider_id=self._task_provider(self.creative_provider_id, self.mai_style_provider_id),
            task="creative_project",
        )
        payload = self._extract_json_payload(text or "")
        if not isinstance(payload, dict):
            payload = {}
        title = _single_line(payload.get("title"), 24) or random.choice(["玻璃杯里的小雨", "迟到的梦", "窗边备用宇宙"])
        target_chars = _safe_int(payload.get("target_chars"), random.randint(1800, 3600), 1200, 5200)
        now = _now_ts()
        return {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "premise": _single_line(payload.get("premise"), 140) or f"从{source_label}里长出来的一个短篇念头",
            "tone": _single_line(payload.get("tone"), 40) or self.default_style,
            "point_of_view": _single_line(payload.get("point_of_view"), 30) or "第三人称有限视角",
            "source": source.get("source") or "life",
            "source_text": source_text,
            "target_chars": target_chars,
            "current_chars": 0,
            "status": "drafting",
            "draft_chunks": [],
            "disclosed_milestones": [],
            "next_hint": _single_line(payload.get("next_hint"), 120) or "先写一个很小的开场画面",
            "created_at": now,
            "last_advanced_at": now,
            "next_advance_at": now + random.randint(45, 140) * 60,
            "last_share_at": 0,
            "share_count": 0,
        }

    async def _generate_creative_chunk(self, project: dict[str, Any], budget: int) -> str:
        chunks = project.get("draft_chunks") if isinstance(project.get("draft_chunks"), list) else []
        recent = "\n".join(_single_line((item or {}).get("text"), 240) for item in chunks[-3:] if isinstance(item, dict))
        remaining = _safe_int(project.get("target_chars"), 2400, 1200, 5200) - _safe_int(project.get("current_chars"), 0, 0)
        finish_hint = "可以自然收束到一个小段落结尾,但不要完结全篇。" if remaining <= budget + 120 else "不要完结全篇,只推进一个很小的片段。"
        persona_context = self._creative_persona_style_context()
        prompt = f"""
你正在模拟拟人化 Bot 慢慢写小说。请只续写本次能写出来的一小段正文。

【作者人格与身份】
{persona_context}

小说标题：{_single_line(project.get("title"), 40)}
核心设定：{_single_line(project.get("premise"), 180)}
行文气质：{_single_line(project.get("tone"), 60)}
叙事视角：{_single_line(project.get("point_of_view"), 40)}
灵感来源：{_single_line(project.get("source_text"), 180)}
上一段：{recent or "还没有正文。"}
下一步念头：{_single_line(project.get("next_hint"), 140)}

本次字数上限：{budget} 个中文字符左右。
要求：
1. 只输出小说正文,不要标题、说明、引号外旁白或 JSON。
2. 模拟真实写作速度,只写一个片段,不要一口气写完整故事。
3. 正文文风要像这个人格与身份自然写出的作品：用词、观察角度、人物成熟度、知识范围都不能越过人设。
4. 细节要具体,但不要堆辞藻；可以有一点梦境感或生活感。
5. {finish_hint}
""".strip()
        text = await self._llm_call(
            prompt,
            max_tokens=max(220, budget + 160),
            provider_id=self._task_provider(self.creative_provider_id, self.mai_style_provider_id),
            task="creative_writing",
        )
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"^```(?:text|markdown)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL).strip()
        cleaned = re.sub(r"^(?:正文|续写|片段)[:：]\s*", "", cleaned).strip()
        if len(cleaned) > budget + 80:
            cleaned = cleaned[: budget + 80].rstrip("，,、；;：:")
            if cleaned and cleaned[-1] not in "。！？…":
                cleaned += "。"
        if not cleaned:
            cleaned = random.choice([
                "她把那句话写到一半,忽然停住。窗外的声音很轻,像有人把另一个世界折起来,塞进了玻璃杯底。",
                "故事里的门没有立刻打开。她让主角在门口多站了一会儿,听见楼道里缓慢落下来的脚步声。",
            ])
        return cleaned

    async def _maybe_start_creative_project(self) -> bool:
        if not self.enable_creative_writing:
            return False
        projects = self._creative_projects()
        active = [item for item in projects if item.get("status") == "drafting"]
        now = _now_ts()
        if len(active) >= self.creative_max_active_projects:
            return False
        last_created = max((_safe_float(item.get("created_at"), 0) for item in projects), default=0)
        if now - last_created < 10 * 3600:
            return False
        if random.random() > self.creative_inspiration_probability:
            return False
        source = self._creative_inspiration_source()
        if not source:
            return False
        project = await self._generate_creative_project(source)
        if not project:
            return False
        projects.append(project)
        del projects[:-20]
        self.data["creative_projects"] = projects
        self._save_data_sync()
        logger.info("[PrivateCompanion] 新增小说创作坑: %s", project.get("title"))
        return True

    async def _maybe_advance_creative_projects(self) -> None:
        if not self.enable_creative_writing:
            return
        await self._maybe_start_creative_project()
        projects = self._creative_projects()
        now = _now_ts()
        changed = False
        for project in projects:
            if project.get("status") != "drafting":
                continue
            if now < _safe_float(project.get("next_advance_at"), 0):
                continue
            elapsed_hours = max(0.25, (now - _safe_float(project.get("last_advanced_at"), now)) / 3600)
            speed = self._creative_speed_chars_per_hour()
            budget = int(speed * elapsed_hours * random.uniform(0.38, 0.82))
            budget = max(70, min(280, budget))
            remaining = _safe_int(project.get("target_chars"), 2400, 1200, 5200) - _safe_int(project.get("current_chars"), 0, 0)
            if remaining <= 0:
                project["status"] = "finished"
                changed = True
                continue
            chunk = await self._generate_creative_chunk(project, min(budget, max(70, remaining)))
            chunks = project.setdefault("draft_chunks", [])
            if not isinstance(chunks, list):
                chunks = []
                project["draft_chunks"] = chunks
            chunks.append({
                "at": now,
                "text": chunk,
                "chars": len(chunk),
            })
            del chunks[:-40]
            project["current_chars"] = _safe_int(project.get("current_chars"), 0, 0) + len(chunk)
            project["last_advanced_at"] = now
            project["next_advance_at"] = now + random.randint(55, 210) * 60
            if project["current_chars"] >= _safe_int(project.get("target_chars"), 2400, 1200, 5200):
                project["status"] = "finished"
            changed = True
            break
        self.data["creative_projects"] = projects
        async with self._data_lock:
            if self._maybe_schedule_creative_share():
                changed = True
            if changed:
                self._save_data_sync()

    def _latest_creative_share_candidate(self) -> dict[str, Any] | None:
        projects = self._creative_projects()
        for project in reversed(projects):
            chunks = project.get("draft_chunks") if isinstance(project.get("draft_chunks"), list) else []
            if not chunks:
                continue
            chunk = next((item for item in reversed(chunks) if isinstance(item, dict) and _single_line(item.get("text"), 260)), None)
            if not isinstance(chunk, dict):
                continue
            current_chars = _safe_int(project.get("current_chars"), 0, 0)
            target_chars = _safe_int(project.get("target_chars"), 2400, 1200, 5200)
            disclosed = project.setdefault("disclosed_milestones", [])
            if not isinstance(disclosed, list):
                disclosed = []
                project["disclosed_milestones"] = disclosed
            milestone = ""
            disclosure_kind = "milestone"
            if project.get("status") == "finished" and "finished" not in disclosed:
                milestone = "finished"
            elif current_chars >= max(150, int(target_chars * 0.12)) and "opening" not in disclosed:
                milestone = "opening"
            elif current_chars >= int(target_chars * 0.52) and "midpoint" not in disclosed:
                milestone = "midpoint"
            elif (
                current_chars >= max(480, int(target_chars * 0.28))
                and "impression_question" not in disclosed
                and len(chunks) >= 3
                and random.random() < 0.38
            ):
                milestone = "impression_question"
                disclosure_kind = "ask_impression"
            if not milestone:
                continue
            return {
                "key": f"{project.get('id')}:{milestone}",
                "milestone": milestone,
                "disclosure_kind": disclosure_kind,
                "project_id": _single_line(project.get("id"), 20),
                "title": _single_line(project.get("title"), 40),
                "premise": _single_line(project.get("premise"), 140),
                "tone": _single_line(project.get("tone"), 40),
                "source": _single_line(project.get("source_text"), 140),
                "snippet": _single_line(chunk.get("text"), 260),
                "current_chars": current_chars,
                "target_chars": target_chars,
                "status": _single_line(project.get("status"), 24),
                "created_ts": _now_ts(),
            }
        return None

    def _mark_creative_milestone_disclosed(self, candidate: dict[str, Any]) -> None:
        project_id = _single_line(candidate.get("project_id"), 20)
        milestone = _single_line(candidate.get("milestone"), 40)
        if not project_id or not milestone:
            return
        for project in self._creative_projects():
            if _single_line(project.get("id"), 20) != project_id:
                continue
            disclosed = project.setdefault("disclosed_milestones", [])
            if not isinstance(disclosed, list):
                disclosed = []
                project["disclosed_milestones"] = disclosed
            if milestone not in disclosed:
                disclosed.append(milestone)
            break

    def _maybe_schedule_creative_share(self) -> bool:
        candidate = self._latest_creative_share_candidate()
        if not isinstance(candidate, dict):
            return False
        users = self.data.get("users")
        if not isinstance(users, dict):
            return False
        now = _now_ts()
        key = str(candidate.get("key") or "")
        changed = False
        for user_id, user in users.items():
            if not isinstance(user, dict) or not user.get("enabled", True) or not user.get("umo"):
                continue
            if now - _safe_float(user.get("last_seen"), 0) < max(self.idle_minutes, 75) * 60:
                continue
            if str(user.get("last_creative_share_key") or "") == key:
                continue
            if now - _safe_float(user.get("last_creative_share_at"), 0) < 8 * 3600:
                continue
            if random.random() > self.creative_share_probability:
                continue
            delay_minutes = random.randint(18, 95)
            scheduled = now + delay_minutes * 60
            title = _single_line(candidate.get("title"), 40) or "刚开的小说坑"
            accepted = self._offer_proactive_candidate(
                str(user_id),
                user,
                {
                    "source": "creative_writing",
                    "reason": "creative_share",
                    "action": "message",
                    "scheduled_ts": scheduled,
                    "topic": title,
                    "score": 72,
                    "motive": f"刚慢慢写到《{title}》的一小段,有点想给 {user_id} 看一句,但不要像交作业",
                    "context_key": "creative_share_context",
                    "context": dict(candidate),
                },
            )
            if not accepted:
                continue
            user["last_creative_share_key"] = key
            user["last_creative_share_at"] = now
            self._mark_creative_milestone_disclosed(candidate)
            changed = True
        return changed

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
            if user_id and user_id.isdigit() and user_id not in ids:
                ids.append(user_id)
        return ids

    def _sync_configured_targets(self):
        for user_id in self._configured_target_ids():
            user = self._get_user(user_id)
            user["enabled"] = True
            user.setdefault("nickname", self.default_nickname)
            if not user.get("umo"):
                user["umo"] = f"{self.target_platform}:FriendMessage:{user_id}"
            if _safe_float(user.get("next_proactive_at"), 0) <= 0:
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
        return int(self.min_interval_minutes * 60 * multiplier)

    def _soft_daily_target(self, user: dict[str, Any]) -> float:
        if self.max_daily_messages <= 0:
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
        if self.max_daily_messages == 1:
            ratio = max(ratio, 0.75)
        return max(0.6, self.max_daily_messages * ratio)

    def _daily_intensity_factor(self, user: dict[str, Any]) -> float:
        if self.max_daily_messages <= 0:
            return 0.0
        sent_today = _safe_int(user.get("sent_today"), 0)
        soft_target = self._soft_daily_target(user)
        capacity_factor = min(1.35, 0.9 + self.max_daily_messages * 0.08)
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
        now_dt = datetime.fromtimestamp(now or _now_ts())
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

    def _relationship_profile(self, user: dict[str, Any]) -> dict[str, Any]:
        proactive_count = _safe_int(user.get("proactive_sent_count"), 0)
        reply_count = _safe_int(user.get("reply_count"), 0)
        inbound_count = _safe_int(user.get("inbound_count"), 0)
        score = _safe_int(user.get("relationship_score"), 0)
        reply_rate_available = proactive_count > 0
        reply_rate = reply_count / proactive_count if reply_rate_available else 0.0
        reply_rate_label = f"{reply_rate:.0%}" if reply_rate_available else "暂无样本"
        persona_profile = user.get("persona_relationship", {})
        if isinstance(persona_profile, dict) and persona_profile.get("level"):
            level = str(persona_profile.get("level"))
            preference = str(persona_profile.get("preference") or "普通")
            score = _safe_int(persona_profile.get("score"), score, 0, 100)
        else:
            level, preference = self._fallback_relationship_level(score, reply_rate, inbound_count, proactive_count)
        return {
            "level": level,
            "reply_rate": reply_rate,
            "reply_rate_available": reply_rate_available,
            "reply_rate_label": reply_rate_label,
            "preference": preference,
            "score": score,
            "inbound_count": inbound_count,
            "proactive_count": proactive_count,
            "reply_count": reply_count,
            "note": (
                str(persona_profile.get("note") or "")
                if isinstance(persona_profile, dict) else ""
            ),
        }

    def _relationship_approach_hint(self, user: dict[str, Any]) -> str:
        profile = self._relationship_profile(user)
        level = str(profile.get("level") or "熟悉")
        preference = str(profile.get("preference") or "普通")
        hints: list[str] = []
        if level == "亲近":
            hints.append("默认像已经很熟了,可以少一点寒暄,更容易半句起手、接旧话头,或者轻轻嘴硬一下。")
        elif level == "熟悉":
            hints.append("默认像已经聊顺了,可以直接从眼前的小事切进去,不用每次都铺垫。")
        else:
            hints.append("默认先轻一点,靠近时别把关心说得太满。")
        if preference == "温柔":
            hints.append("靠近方式偏温吞和收着一点。")
        elif preference == "活泼":
            hints.append("靠近方式可以轻快一点,偶尔带一点玩笑感。")
        elif preference == "工作":
            hints.append("靠近方式更克制,优先从具体事情切进去。")
        rel_state = user.get("relationship_state")
        if isinstance(rel_state, dict):
            mode = str(rel_state.get("mode") or "")
            if mode == "backoff" and _safe_float(rel_state.get("backoff_until"), 0) > _now_ts():
                hints.append("最近用户像是在表达边界或不想被打扰,主动和被动都要明显收敛,短一点,不追问。")
            elif mode == "careful":
                hints.append("最近用户情绪或压力偏重,优先接住情绪,不要讲大道理。")
            elif mode == "warming":
                hints.append("最近互动有升温或玩笑感,可以更自然亲近一点,但不要过度黏。")
        return " ".join(hints).strip()

    def _update_expression_profile_from_message(self, user: dict[str, Any], text: str) -> None:
        if not self.enable_expression_learning:
            return
        cleaned = _single_line(text, 220)
        if not cleaned:
            return
        profile = user.setdefault("expression_profile", {})
        if not isinstance(profile, dict):
            profile = {}
            user["expression_profile"] = profile
        samples = _safe_int(profile.get("samples"), 0, 0) + 1
        profile["samples"] = samples
        profile["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        short_count = _safe_int(profile.get("short_count"), 0, 0)
        if len(cleaned) <= 18:
            short_count += 1
        profile["short_count"] = short_count

        punctuation = profile.get("punctuation")
        if not isinstance(punctuation, dict):
            punctuation = {}
        for mark in ("！", "!", "？", "?", "~", "～", "…", "。"):
            count = cleaned.count(mark)
            if count:
                punctuation[mark] = min(999, _safe_int(punctuation.get(mark), 0, 0) + count)
        profile["punctuation"] = punctuation

        endings = profile.get("endings")
        if not isinstance(endings, list):
            endings = []
        stripped = cleaned.rstrip("。！？!?~～… ")
        if 2 <= len(stripped) <= 80:
            ending = stripped[-min(6, max(2, len(stripped))):]
            if ending and ending not in endings:
                endings.insert(0, ending)
        profile["endings"] = endings[: self.max_learned_expression_items]

        phrases = profile.get("recent_phrases")
        if not isinstance(phrases, list):
            phrases = []
        if 2 <= len(cleaned) <= 40 and not re.search(r"https?://|<[^>]+>", cleaned):
            phrases.insert(0, cleaned)
        profile["recent_phrases"] = list(dict.fromkeys(phrases))[: self.max_learned_expression_items]

    def _update_companion_memory_from_message(self, user: dict[str, Any], text: str) -> None:
        if not self.enable_companion_memory:
            return
        cleaned = _single_line(text, 260)
        if not cleaned:
            return
        memory = user.setdefault("companion_memory", {})
        if not isinstance(memory, dict):
            memory = {}
            user["companion_memory"] = memory
        raw_items = memory.get("items")
        items = raw_items if isinstance(raw_items, list) else []
        lowered = cleaned.lower()
        patterns = (
            "喜欢", "讨厌", "不喜欢", "别叫", "不要", "记住", "记得",
            "生日", "纪念日", "我是", "我叫", "叫我", "我在", "我住",
            "想要", "希望", "害怕", "雷点", "以后",
        )
        score = 0
        for pattern in patterns:
            if pattern in cleaned or pattern in lowered:
                score += 1
        if score <= 0:
            return
        kind = "preference"
        if any(key in cleaned for key in ("不要", "别叫", "讨厌", "不喜欢", "雷点")):
            kind = "boundary"
        elif any(key in cleaned for key in ("生日", "纪念日", "以后", "记住", "记得")):
            kind = "important"
        item = {
            "text": cleaned,
            "kind": kind,
            "weight": min(5, 1 + score),
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        deduped = [old for old in items if isinstance(old, dict) and _single_line(old.get("text"), 260) != cleaned]
        deduped.insert(0, item)
        memory["items"] = deduped[: self.max_companion_memory_items]
        memory["updated_at"] = item["created_at"]

    def _format_expression_profile_for_prompt(self, user: dict[str, Any]) -> str:
        profile = user.get("expression_profile")
        if not isinstance(profile, dict) or _safe_int(profile.get("samples"), 0, 0) <= 0:
            return "暂无足够样本。保持 AstrBot 默认人格的自然表达。"
        samples = max(1, _safe_int(profile.get("samples"), 1, 1))
        short_ratio = _safe_int(profile.get("short_count"), 0, 0) / samples
        punctuation = profile.get("punctuation") if isinstance(profile.get("punctuation"), dict) else {}
        sorted_marks = sorted(punctuation.items(), key=lambda item: -_safe_int(item[1], 0, 0))[:4]
        marks = "、".join(str(mark) for mark, count in sorted_marks if _safe_int(count, 0, 0) > 0)
        endings = profile.get("endings") if isinstance(profile.get("endings"), list) else []
        phrases = profile.get("recent_phrases") if isinstance(profile.get("recent_phrases"), list) else []
        length_hint = "用户常用短句,回复也可以更短更像即时聊天。" if short_ratio >= 0.55 else "用户能接受稍完整的句子,但仍避免说明书式长段。"
        lines = [length_hint]
        if marks:
            lines.append(f"常见标点/语气符号：{marks}。可少量顺着氛围使用,不要机械模仿。")
        if endings:
            lines.append("常见句尾味道：" + "、".join(_single_line(item, 12) for item in endings[:5]))
        if phrases:
            lines.append("最近短句样本：" + " / ".join(_single_line(item, 24) for item in phrases[:4]))
        return "\n".join(lines)

    def _format_companion_memory_for_prompt(self, user: dict[str, Any]) -> str:
        memory = user.get("companion_memory")
        if not isinstance(memory, dict):
            return "暂无专门沉淀的用户记忆。"
        llm_profile = memory.get("profile")
        lines: list[str] = []
        if isinstance(llm_profile, dict):
            for key, label in (
                ("user_traits", "用户画像"),
                ("interests", "兴趣/偏好"),
                ("boundaries", "边界/雷点"),
                ("relationship_notes", "关系线索"),
                ("speaking_style", "说话习惯"),
            ):
                value = llm_profile.get(key)
                if isinstance(value, list):
                    text = "；".join(_single_line(item, 60) for item in value[:5] if _single_line(item, 60))
                else:
                    text = _single_line(value, 180)
                if text:
                    lines.append(f"{label}：{text}")
        items = memory.get("items")
        if isinstance(items, list) and items:
            facts = []
            for item in items[:8]:
                if not isinstance(item, dict):
                    continue
                text = _single_line(item.get("text"), 90)
                if text:
                    facts.append(text)
            if facts:
                lines.append("近期可记住的话：" + " / ".join(facts))
        episode_text = self._format_dialogue_episodes_for_prompt(user)
        if episode_text:
            lines.append("近期共同经历：\n" + episode_text)
        open_loop_text = self._format_open_loops_for_prompt(user)
        if open_loop_text:
            lines.append("未完成约定/可续话头：\n" + open_loop_text)
        return "\n".join(lines) if lines else "暂无专门沉淀的用户记忆。"

    def _format_dialogue_episodes_for_prompt(self, user: dict[str, Any]) -> str:
        episodes = user.get("dialogue_episodes")
        if not isinstance(episodes, list):
            return ""
        lines: list[str] = []
        for item in episodes[-4:]:
            if not isinstance(item, dict):
                continue
            summary = _single_line(item.get("summary"), 120)
            if not summary:
                continue
            mood = _single_line(item.get("emotional_residue"), 60)
            topic = _single_line(item.get("reusable_topic"), 80)
            parts = [summary]
            if mood:
                parts.append(f"余味：{mood}")
            if topic:
                parts.append(f"可续：{topic}")
            lines.append("- " + "｜".join(parts))
        return "\n".join(lines)

    def _format_open_loops_for_prompt(self, user: dict[str, Any]) -> str:
        loops = user.get("open_loops")
        if not isinstance(loops, list):
            return ""
        lines: list[str] = []
        now = _now_ts()
        kept = []
        for item in loops:
            if not isinstance(item, dict):
                continue
            if now - _safe_float(item.get("created_ts"), now) > 14 * 86400:
                continue
            kept.append(item)
        if len(kept) != len(loops):
            user["open_loops"] = kept[-12:]
        for item in kept[-6:]:
            text = _single_line(item.get("text"), 100)
            if not text:
                continue
            status = _single_line(item.get("status"), 30) or "待自然延续"
            lines.append(f"- {status}：{text}")
        return "\n".join(lines)

    def _update_open_loops_from_message(self, user: dict[str, Any], text: str) -> None:
        if not self.enable_open_loop_tracking:
            return
        cleaned = _single_line(text, 260)
        if not cleaned:
            return
        loops = user.setdefault("open_loops", [])
        if not isinstance(loops, list):
            loops = []
            user["open_loops"] = loops

        completion_markers = ("好了", "搞定", "解决了", "完成了", "不用了", "取消", "算了", "没事了", "不用提醒")
        if loops and any(marker in cleaned for marker in completion_markers):
            for item in reversed(loops):
                if not isinstance(item, dict):
                    continue
                if str(item.get("status") or "") in {"已完成", "已取消"}:
                    continue
                item["status"] = "已取消" if any(marker in cleaned for marker in ("不用了", "取消", "算了", "不用提醒")) else "已完成"
                item["resolved_ts"] = _now_ts()
                break

        add_patterns = (
            r"(?:记得|帮我|提醒我|到时候|以后|明天|今晚|等会儿|一会儿)([^。！？\n]{2,80})",
            r"([^。！？\n]{2,80})(?:你记一下|你记住|别忘了)",
        )
        for pattern in add_patterns:
            match = re.search(pattern, cleaned)
            if not match:
                continue
            loop_text = _single_line(match.group(0), 110)
            if not loop_text:
                continue
            existing = {_single_line(item.get("text"), 120) for item in loops if isinstance(item, dict)}
            if loop_text not in existing:
                loops.append(
                    {
                        "text": loop_text,
                        "status": "待自然延续",
                        "created_ts": _now_ts(),
                        "source": "user_message",
                    }
                )
            break
        del loops[:-12]

    def _update_action_preferences_from_message(self, user: dict[str, Any], text: str) -> None:
        cleaned = _single_line(text, 240)
        if not cleaned:
            return
        prefs = user.setdefault("action_preferences", {})
        if not isinstance(prefs, dict):
            prefs = {}
            user["action_preferences"] = prefs
        mapping = {
            "poke": ("戳", "戳一戳"),
            "voice": ("语音", "发语音", "声音"),
            "photo_text": ("图片", "照片", "图"),
            "screen_peek": ("看屏幕", "窥屏", "看我屏幕", "屏幕"),
        }
        negative = ("别", "不要", "不许", "讨厌", "少", "别再", "不喜欢")
        positive = ("喜欢", "可以", "多", "想要", "爱看", "爱听")
        for action, keywords in mapping.items():
            if not any(keyword in cleaned for keyword in keywords):
                continue
            item = prefs.setdefault(action, {"like": 0, "dislike": 0, "note": ""})
            if not isinstance(item, dict):
                item = {"like": 0, "dislike": 0, "note": ""}
                prefs[action] = item
            if any(token in cleaned for token in negative):
                item["dislike"] = min(20, _safe_int(item.get("dislike"), 0, 0) + 2)
                item["note"] = _single_line(cleaned, 90)
            elif any(token in cleaned for token in positive):
                item["like"] = min(20, _safe_int(item.get("like"), 0, 0) + 1)
                item["note"] = _single_line(cleaned, 90)
            item["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    def _action_preference_hint(self, user: dict[str, Any] | None = None) -> str:
        if not isinstance(user, dict):
            return ""
        prefs = user.get("action_preferences")
        if not isinstance(prefs, dict) or not prefs:
            return ""
        labels = {
            "poke": "戳一戳",
            "voice": "语音",
            "photo_text": "图片",
            "screen_peek": "看屏幕",
        }
        lines = []
        for action, item in prefs.items():
            if not isinstance(item, dict):
                continue
            like = _safe_int(item.get("like"), 0, 0)
            dislike = _safe_int(item.get("dislike"), 0, 0)
            note = _single_line(item.get("note"), 60)
            if dislike > like:
                lines.append(f"- {labels.get(action, action)}：用户可能不喜欢或希望少用。{note}")
            elif like > dislike:
                lines.append(f"- {labels.get(action, action)}：用户接受度较高。{note}")
        return "\n".join(lines)

    def _update_group_observation(
        self,
        group: dict[str, Any],
        *,
        sender_id: str,
        sender_name: str,
        text: str,
    ) -> None:
        cleaned = _single_line(text, 260)
        if not cleaned:
            return
        now = _now_ts()
        group["last_seen"] = now
        group["message_count"] = _safe_int(group.get("message_count"), 0, 0) + 1

        recent = group.setdefault("recent_messages", [])
        if not isinstance(recent, list):
            recent = []
            group["recent_messages"] = recent
        recent.append(
            {
                "ts": now,
                "sender_id": sender_id,
                "name": _single_line(sender_name, 30) or sender_id,
                "identity_name": self._group_member_identity_name(sender_id, sender_name, limit=30),
                "identity_known": bool(self._worldbook_profile_by_user_id(sender_id)),
                "text": cleaned,
            }
        )
        del recent[:-self.max_group_recent_messages]

        if self.enable_group_member_profiles:
            members = group.setdefault("members", {})
            if not isinstance(members, dict):
                members = {}
                group["members"] = members
            member = members.setdefault(sender_id, {"name": sender_name, "count": 0, "recent_phrases": []})
            if not isinstance(member, dict):
                member = {"name": sender_name, "count": 0, "recent_phrases": []}
                members[sender_id] = member
            member["user_id"] = sender_id
            member["name"] = _single_line(sender_name, 30) or member.get("name") or sender_id
            member["identity_name"] = self._group_member_identity_name(sender_id, sender_name, limit=30)
            member["identity_known"] = bool(self._worldbook_profile_by_user_id(sender_id))
            identity_note = self._group_member_identity_note(sender_id, limit=160)
            if identity_note:
                member["identity_note"] = identity_note
            profile = self._worldbook_profile_by_user_id(sender_id)
            if isinstance(profile, dict):
                boundary_note = _single_line(profile.get("boundary_note"), 160)
                if boundary_note:
                    member["boundary_note"] = boundary_note
            member["count"] = _safe_int(member.get("count"), 0, 0) + 1
            member["last_seen"] = now
            self._remember_worldbook_observed_name(sender_id, sender_name)
            phrases = member.setdefault("recent_phrases", [])
            if not isinstance(phrases, list):
                phrases = []
                member["recent_phrases"] = phrases
            if 2 <= len(cleaned) <= 50:
                phrases.insert(0, cleaned)
                member["recent_phrases"] = list(dict.fromkeys(phrases))[:8]

        if self.enable_group_slang_learning:
            self._learn_group_slang(group, cleaned)
        if self.enable_group_topic_threads:
            self._update_group_topic_threads(group, sender_id=sender_id, sender_name=sender_name, text=cleaned)
        if self.enable_group_relationship_graph:
            self._update_group_relationship_graph(group, sender_id=sender_id, sender_name=sender_name, text=cleaned)
        if self.enable_group_interjection_feedback:
            self._update_group_interjection_feedback(group, sender_id=sender_id, text=cleaned)
        self._update_group_atmosphere(group)

    def _group_private_share_candidate(self, group_id: str, group: dict[str, Any], *, trigger_sender_id: str = "") -> dict[str, Any] | None:
        recent = group.get("recent_messages")
        if not isinstance(recent, list):
            return None
        now = _now_ts()
        harassment = self._group_bot_harassment_candidate(group_id, group, trigger_sender_id=trigger_sender_id, now=now)
        if isinstance(harassment, dict):
            return harassment
        window = [
            item for item in recent[-18:]
            if isinstance(item, dict) and now - _safe_float(item.get("ts"), 0) <= 20 * 60
        ]
        if not window:
            return None
        texts = [_single_line(item.get("text"), 120) for item in window if _single_line(item.get("text"), 120)]
        joined = "\n".join(texts)
        score = 0
        funny_markers = ("笑死", "哈哈", "草", "绷", "乐", "典", "离谱", "绝了", "蚌埠住", "太好笑", "逆天", "急了")
        share_markers = ("截图", "表情包", "名场面", "好玩", "神了", "破防", "节目效果", "群友", "复读")
        score += sum(2 for marker in funny_markers if marker in joined)
        score += sum(1 for marker in share_markers if marker in joined)
        if len({str(item.get("sender_id") or "") for item in window if item.get("sender_id")}) >= 3:
            score += 1
        if len(window) >= 6:
            score += 1
        if re.search(r"[!?！？]{2,}|哈{2,}|草{2,}", joined):
            score += 2
        if score < 3:
            return None
        chosen = max(
            window,
            key=lambda item: (
                sum(1 for marker in funny_markers + share_markers if marker in str(item.get("text") or "")),
                _safe_float(item.get("ts"), 0),
            ),
        )
        speaker_id = str(chosen.get("sender_id") or "")
        speaker = self._group_member_identity_name(speaker_id, chosen.get("identity_name") or chosen.get("name"), limit=24)
        text = _single_line(chosen.get("text"), 100)
        if not text:
            return None
        topic = self._soften_topic_hook(text) or "群里刚刚那个片段"
        summary_items = []
        for item in window[-4:]:
            if not isinstance(item, dict):
                continue
            name = self._group_member_identity_name(
                str(item.get("sender_id") or ""),
                item.get("identity_name") or item.get("name"),
                limit=16,
            )
            line = _single_line(item.get("text"), 56)
            if line:
                summary_items.append(f"{name}: {line}")
        return {
            "group_id": str(group_id),
            "kind": "funny",
            "speaker_id": speaker_id,
            "speaker": speaker,
            "topic": topic,
            "text": text,
            "summary": " / ".join(summary_items[-3:]),
            "score": score,
            "trigger_sender_id": trigger_sender_id,
            "created_ts": now,
        }

    def _group_bot_harassment_candidate(
        self,
        group_id: str,
        group: dict[str, Any],
        *,
        trigger_sender_id: str = "",
        now: float | None = None,
    ) -> dict[str, Any] | None:
        recent = group.get("recent_messages")
        if not isinstance(recent, list):
            return None
        now = now or _now_ts()
        window = [
            item for item in recent[-24:]
            if isinstance(item, dict) and now - _safe_float(item.get("ts"), 0) <= 10 * 60
        ]
        if not window:
            return None
        bot_markers = {self.bot_name, "bot", "Bot", "机器人", "小星"}
        bot_markers = {marker for marker in bot_markers if marker}
        pressure_markers = (
            "出来", "在吗", "人呢", "说话", "别装死", "怎么不回", "快回", "理我",
            "笨蛋", "傻", "蠢", "废物", "垃圾", "闭嘴", "滚", "不会吧", "急了",
        )
        addressed: list[dict[str, Any]] = []
        abusive: list[dict[str, Any]] = []
        by_sender: dict[str, int] = {}
        for item in window:
            text = _single_line(item.get("text"), 140)
            sender_id = str(item.get("sender_id") or "")
            looks_addressed = any(marker and marker in text for marker in bot_markers) or text.startswith("@")
            looks_pressuring = any(marker in text for marker in pressure_markers)
            repeated_ping = bool(re.fullmatch(r"[@\s\w\u4e00-\u9fff]{1,12}[?？!！。]*", text)) and looks_addressed
            if looks_addressed or (looks_pressuring and len(text) <= 36):
                addressed.append(item)
                if sender_id:
                    by_sender[sender_id] = by_sender.get(sender_id, 0) + 1
            if looks_pressuring and (looks_addressed or repeated_ping or len(text) <= 42):
                abusive.append(item)
        if not addressed:
            return None
        max_sender_hits = max(by_sender.values(), default=0)
        score = len(addressed) + len(abusive) * 2 + max(0, max_sender_hits - 1)
        if len(addressed) >= 5:
            score += 2
        if max_sender_hits >= 3:
            score += 2
        if score < 6:
            return None
        chosen = abusive[-1] if abusive else addressed[-1]
        speaker_id = str(chosen.get("sender_id") or "")
        speaker = self._group_member_identity_name(speaker_id, chosen.get("identity_name") or chosen.get("name"), limit=24)
        text = _single_line(chosen.get("text"), 100)
        summary_items = []
        for item in window[-5:]:
            if not isinstance(item, dict):
                continue
            name = self._group_member_identity_name(
                str(item.get("sender_id") or ""),
                item.get("identity_name") or item.get("name"),
                limit=16,
            )
            line = _single_line(item.get("text"), 56)
            if line:
                summary_items.append(f"{name}: {line}")
        return {
            "group_id": str(group_id),
            "kind": "bot_harassment",
            "speaker_id": speaker_id,
            "speaker": speaker,
            "topic": "群里有人一直闹 Bot",
            "text": text,
            "summary": " / ".join(summary_items[-4:]),
            "score": score,
            "trigger_sender_id": trigger_sender_id,
            "created_ts": now,
        }

    def _maybe_schedule_group_private_share(self, group_id: str, group: dict[str, Any], *, trigger_sender_id: str = "") -> bool:
        if not self.enable_group_companion:
            return False
        candidate = self._group_private_share_candidate(group_id, group, trigger_sender_id=trigger_sender_id)
        if not isinstance(candidate, dict):
            return False
        users = self.data.get("users")
        if not isinstance(users, dict):
            return False
        members = group.get("members") if isinstance(group.get("members"), dict) else {}
        now = _now_ts()
        changed = False
        for user_id, user in users.items():
            if not isinstance(user, dict) or not user.get("enabled", True) or not user.get("umo"):
                continue
            target_id = str(user_id)
            if target_id == str(trigger_sender_id or ""):
                continue
            member = members.get(target_id) if isinstance(members, dict) else None
            member_last_seen = _safe_float((member or {}).get("last_seen"), 0) if isinstance(member, dict) else 0
            if member_last_seen <= 0 or now - member_last_seen < 4 * 3600:
                continue
            cooldown_key = f"{group_id}:{_today_key()}"
            last_key = str(user.get("last_group_share_key") or "")
            last_at = _safe_float(user.get("last_group_share_at"), 0)
            if last_key == cooldown_key or now - last_at < 8 * 3600:
                continue
            if _safe_float(user.get("next_proactive_at"), 0) > 0 and str(user.get("planned_proactive_source") or "") == "timer":
                continue
            kind = _single_line(candidate.get("kind"), 32) or "funny"
            score = _safe_int(candidate.get("score"), 0, 0)
            chance = (
                min(0.82, 0.42 + score * 0.04)
                if kind == "bot_harassment"
                else min(0.56, 0.18 + score * 0.05)
            )
            if random.random() > chance:
                continue
            delay_minutes = random.randint(8, 25) if kind == "bot_harassment" else random.randint(18, 55)
            scheduled = now + delay_minutes * 60
            topic = _single_line(candidate.get("topic"), 60) or "群里的小片段"
            context = {
                "group_id": str(group_id),
                "kind": kind,
                "topic": topic,
                "speaker_id": _single_line(candidate.get("speaker_id"), 40),
                "speaker": _single_line(candidate.get("speaker"), 24),
                "text": _single_line(candidate.get("text"), 120),
                "summary": _single_line(candidate.get("summary"), 220),
                "created_ts": now,
            }
            accepted = self._offer_proactive_candidate(
                target_id,
                user,
                {
                    "source": "group_share",
                    "reason": "group_share",
                    "action": "message",
                    "scheduled_ts": scheduled,
                    "topic": topic,
                    "score": score,
                    "motive": (
                        f"群 {group_id} 刚刚有人一直闹 Bot，{self._group_member_identity_name(target_id, target_id, limit=24)} 已经 {self._format_elapsed(now - member_last_seen)} 没在群里冒泡，想及时私下说一声"
                        if kind == "bot_harassment"
                        else f"群 {group_id} 刚刚有个挺有意思的片段，{self._group_member_identity_name(target_id, target_id, limit=24)} 已经 {self._format_elapsed(now - member_last_seen)} 没在群里冒泡，想私下轻轻转述一下"
                    ),
                    "context_key": "group_share_context",
                    "context": context,
                },
            )
            if not accepted:
                continue
            user["last_group_share_key"] = cooldown_key
            user["last_group_share_at"] = now
            changed = True
        return changed

    def _learn_group_slang(self, group: dict[str, Any], text: str) -> None:
        terms = group.setdefault("slang_terms", [])
        if not isinstance(terms, list):
            terms = []
            group["slang_terms"] = terms
        candidates: list[str] = []
        for token in re.findall(r"[A-Za-z0-9_]{2,16}|[\u4e00-\u9fff]{2,8}", text):
            token = _single_line(token, 16)
            if not token:
                continue
            if token in {"哈哈", "什么", "这个", "那个", "就是", "感觉", "可以", "不是", "没有", "真的", "一下"}:
                continue
            if re.fullmatch(r"\d+", token):
                continue
            if len(token) <= 2 and token not in {"草", "绷", "典", "急", "乐"}:
                continue
            candidates.append(token)
        if any(marker in text for marker in ("草", "绷", "典", "急了", "笑死", "蚌埠住", "乐")):
            for marker in ("草", "绷", "典", "急了", "笑死", "蚌埠住", "乐"):
                if marker in text:
                    candidates.append(marker)
        if not candidates:
            return
        indexed = {}
        for item in terms:
            if isinstance(item, dict) and item.get("term"):
                indexed[str(item.get("term"))] = item
        for token in candidates[:8]:
            item = indexed.get(token)
            if not item:
                item = {"term": token, "count": 0, "last_seen": 0}
                terms.append(item)
                indexed[token] = item
            item["count"] = min(999, _safe_int(item.get("count"), 0, 0) + 1)
            item["last_seen"] = _now_ts()
        terms.sort(key=lambda item: (_safe_int(item.get("count"), 0, 0), _safe_float(item.get("last_seen"), 0)), reverse=True)
        del terms[self.max_group_slang_terms:]

    def _update_group_atmosphere(self, group: dict[str, Any]) -> None:
        recent = group.get("recent_messages")
        if not isinstance(recent, list):
            recent = []
        now = _now_ts()
        window = [item for item in recent if isinstance(item, dict) and now - _safe_float(item.get("ts"), 0) <= 12 * 60]
        texts = [str(item.get("text") or "") for item in window]
        joined = "\n".join(texts)
        active_speakers = len({str(item.get("sender_id") or "") for item in window if isinstance(item, dict)})
        pace = "安静"
        if len(window) >= 18 or active_speakers >= 6:
            pace = "热闹"
        elif len(window) >= 6:
            pace = "有来有回"
        mood = "平稳"
        if re.search(r"(哈哈|笑死|草|乐|绷|hhh)", joined, re.IGNORECASE):
            mood = "玩笑"
        if re.search(r"(烦|累|难受|吵|别吵|急|骂|生气)", joined):
            mood = "紧绷"
        if re.search(r"(求助|怎么|为什么|报错|帮|救命)", joined):
            mood = "求助"
        group["atmosphere"] = {
            "pace": pace,
            "mood": mood,
            "active_speakers": active_speakers,
            "recent_count": len(window),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def _group_topic_signature(self, text: str) -> str:
        return self._proactive_topic_signature(text)

    def _update_group_topic_threads(
        self,
        group: dict[str, Any],
        *,
        sender_id: str,
        sender_name: str,
        text: str,
    ) -> None:
        signature = self._group_topic_signature(text)
        if not signature:
            return
        threads = group.setdefault("topic_threads", [])
        if not isinstance(threads, list):
            threads = []
            group["topic_threads"] = threads
        now = _now_ts()
        active_threads = [
            item for item in threads
            if isinstance(item, dict) and now - _safe_float(item.get("last_ts"), 0) <= 90 * 60
        ]
        matched = None
        for item in active_threads:
            if self._topic_signature_similar(signature, str(item.get("signature") or "")):
                matched = item
                break
        if not matched:
            matched = {
                "signature": signature,
                "title": _single_line(text, 40),
                "started_ts": now,
                "last_ts": now,
                "participants": [],
                "message_count": 0,
                "bot_joined": False,
                "recent_examples": [],
            }
            active_threads.append(matched)
        matched["last_ts"] = now
        matched["message_count"] = _safe_int(matched.get("message_count"), 0, 0) + 1
        participants = matched.setdefault("participants", [])
        if not isinstance(participants, list):
            participants = []
            matched["participants"] = participants
        if sender_id and sender_id not in participants:
            participants.append(sender_id)
        examples = matched.setdefault("recent_examples", [])
        if not isinstance(examples, list):
            examples = []
            matched["recent_examples"] = examples
        examples.append(
            {
                "sender_id": sender_id,
                "name": self._group_member_identity_name(sender_id, sender_name, limit=20),
                "text": _single_line(text, 80),
                "ts": now,
            }
        )
        del examples[:-6]
        active_threads.sort(key=lambda item: _safe_float(item.get("last_ts"), 0), reverse=True)
        group["topic_threads"] = active_threads[: self.max_group_topic_threads]

    def _update_group_interjection_feedback(self, group: dict[str, Any], *, sender_id: str, text: str) -> None:
        last = group.get("last_bot_interjection")
        if not isinstance(last, dict) or not last:
            return
        sent_ts = _safe_float(last.get("ts"), 0)
        if sent_ts <= 0 or _now_ts() - sent_ts > 10 * 60:
            return
        if sender_id == str(last.get("bot_sender_id") or ""):
            return
        feedback = group.setdefault("interjection_feedback", {})
        if not isinstance(feedback, dict):
            feedback = {}
            group["interjection_feedback"] = feedback
        feedback["replies_after"] = _safe_int(feedback.get("replies_after"), 0, 0) + 1
        if re.search(r"(哈哈|笑死|草|绷|乐|hhh|可以|确实|对啊)", text, re.IGNORECASE):
            feedback["positive"] = _safe_int(feedback.get("positive"), 0, 0) + 1
        if re.search(r"(别吵|闭嘴|吵死|机器人|别发|烦)", text):
            feedback["negative"] = _safe_int(feedback.get("negative"), 0, 0) + 1
        last["last_feedback_at"] = _now_ts()

    def _update_group_relationship_graph(
        self,
        group: dict[str, Any],
        *,
        sender_id: str,
        sender_name: str,
        text: str,
    ) -> None:
        last = group.get("last_speaker")
        now = _now_ts()
        if isinstance(last, dict):
            prev_id = str(last.get("sender_id") or "")
            prev_name = self._group_member_identity_name(prev_id, last.get("identity_name") or last.get("name"), limit=30)
            prev_ts = _safe_float(last.get("ts"), 0)
            if prev_id and prev_id != sender_id and now - prev_ts <= 180:
                left, right = sorted([prev_id, sender_id])
                current_name = self._group_member_identity_name(sender_id, sender_name, limit=30)
                key = f"{left}|{right}"
                edges = group.setdefault("relationship_edges", {})
                if not isinstance(edges, dict):
                    edges = {}
                    group["relationship_edges"] = edges
                edge = edges.setdefault(
                    key,
                    {
                        "a": left,
                        "b": right,
                        "a_name": prev_name if left == prev_id else current_name,
                        "b_name": current_name if right == sender_id else prev_name,
                        "count": 0,
                        "tone": {},
                        "last_ts": 0,
                    },
                )
                if isinstance(edge, dict):
                    edge["a_name"] = self._group_member_identity_name(left, edge.get("a_name"), limit=30)
                    edge["b_name"] = self._group_member_identity_name(right, edge.get("b_name"), limit=30)
                    edge["count"] = _safe_int(edge.get("count"), 0, 0) + 1
                    edge["last_ts"] = now
                    tone = edge.setdefault("tone", {})
                    if not isinstance(tone, dict):
                        tone = {}
                        edge["tone"] = tone
                    tone_key = "玩笑" if re.search(r"(哈哈|笑死|草|绷|乐|hhh)", text, re.IGNORECASE) else "普通"
                    if re.search(r"(吵|骂|别|烦|急)", text):
                        tone_key = "紧绷"
                    tone[tone_key] = _safe_int(tone.get(tone_key), 0, 0) + 1
                if len(edges) > self.max_group_relationship_edges:
                    ranked = sorted(
                        edges.items(),
                        key=lambda item: (_safe_int((item[1] or {}).get("count"), 0, 0), _safe_float((item[1] or {}).get("last_ts"), 0)),
                        reverse=True,
                    )
                    group["relationship_edges"] = dict(ranked[: self.max_group_relationship_edges])
        group["last_speaker"] = {
            "sender_id": sender_id,
            "name": _single_line(sender_name, 30) or sender_id,
            "identity_name": self._group_member_identity_name(sender_id, sender_name, limit=30),
            "identity_known": bool(self._worldbook_profile_by_user_id(sender_id)),
            "ts": now,
            "text": _single_line(text, 80),
        }

    def _format_group_relationship_graph_for_prompt(self, group: dict[str, Any]) -> str:
        edges = group.get("relationship_edges")
        if not isinstance(edges, dict):
            return ""
        ranked = sorted(
            [item for item in edges.values() if isinstance(item, dict)],
            key=lambda item: (_safe_int(item.get("count"), 0, 0), _safe_float(item.get("last_ts"), 0)),
            reverse=True,
        )[:6]
        lines = []
        for item in ranked:
            a_id = str(item.get("a") or "")
            b_id = str(item.get("b") or "")
            a_name = self._group_member_identity_name(a_id, item.get("a_name"), limit=16) if a_id else (_single_line(item.get("a_name"), 16) or "群友A")
            b_name = self._group_member_identity_name(b_id, item.get("b_name"), limit=16) if b_id else (_single_line(item.get("b_name"), 16) or "群友B")
            tone = item.get("tone") if isinstance(item.get("tone"), dict) else {}
            main_tone = "普通"
            if tone:
                main_tone = max(tone.items(), key=lambda pair: _safe_int(pair[1], 0, 0))[0]
            lines.append(f"- {a_name} ↔ {b_name}：互动 {item.get('count', 0)} 次｜常见氛围 {main_tone}")
        return "\n".join(lines)

    def _format_group_slang_meanings_for_prompt(self, group: dict[str, Any]) -> str:
        meanings = group.get("slang_meanings")
        if not isinstance(meanings, dict) or not meanings:
            return ""
        lines = []
        for term, item in list(meanings.items())[:10]:
            if not isinstance(item, dict):
                continue
            meaning = _single_line(item.get("meaning"), 80)
            usage = _single_line(item.get("usage"), 80)
            if meaning:
                lines.append(f"- {term}：{meaning}" + (f"｜用法：{usage}" if usage else ""))
        return "\n".join(lines)

    def _format_group_topic_threads_for_prompt(self, group: dict[str, Any]) -> str:
        threads = group.get("topic_threads")
        if not isinstance(threads, list):
            return ""
        lines = []
        for item in threads[:5]:
            if not isinstance(item, dict):
                continue
            title = _single_line(item.get("title"), 42)
            if not title:
                continue
            participants = item.get("participants") if isinstance(item.get("participants"), list) else []
            participant_names = [
                self._group_member_identity_name(str(participant), str(participant), limit=12)
                for participant in participants[:4]
            ]
            participant_text = "、".join(name for name in participant_names if name)
            lines.append(
                f"- {title}｜参与 {len(participants)} 人"
                + (f"({participant_text})" if participant_text else "")
                + "｜"
                f"{item.get('message_count', 0)} 条｜{'bot已接过' if item.get('bot_joined') else 'bot未接'}"
            )
        return "\n".join(lines)

    def _format_group_episodes_for_prompt(self, group: dict[str, Any]) -> str:
        episodes = group.get("group_episodes")
        if not isinstance(episodes, list):
            return ""
        lines = []
        for item in episodes[-4:]:
            if not isinstance(item, dict):
                continue
            summary = _single_line(item.get("summary"), 100)
            if not summary:
                continue
            meme = _single_line(item.get("new_meme"), 60)
            lines.append("- " + summary + (f"｜新梗：{meme}" if meme else ""))
        return "\n".join(lines)

    def _worldbook_profile_tokens(self, profile: dict[str, Any]) -> list[str]:
        tokens: list[str] = []
        for token in [profile.get("name"), *(profile.get("aliases") or []), *(profile.get("observed_names") or [])]:
            token = _single_line(token, 40)
            if token and token not in tokens:
                tokens.append(token)
        user_id = _single_line(profile.get("user_id"), 40)
        if user_id and user_id not in tokens:
            tokens.append(user_id)
        return tokens

    @staticmethod
    def _worldbook_token_usable(token: str) -> bool:
        token = _single_line(token, 40)
        if not token:
            return False
        if token.isdigit():
            return len(token) >= 5
        if len(token) < 2:
            return False
        if token in {"群友", "老师", "同学", "朋友", "bot", "Bot", "BOT", "我", "你", "他", "她", "它"}:
            return False
        return True

    def _worldbook_token_mentioned(self, token: str, text: str) -> bool:
        token = _single_line(token, 40)
        text = str(text or "")
        if not token or not text:
            return False
        if token.isdigit():
            return token in text
        if not self._worldbook_token_usable(token):
            return False
        return token in text

    def _worldbook_profile_view(self, profile: dict[str, Any], *, match_reason: str, confidence: str) -> dict[str, Any]:
        view = dict(profile)
        view["_match_reason"] = match_reason
        view["_match_confidence"] = confidence
        return view

    def _select_worldbook_member_profiles_for_group(
        self,
        group: dict[str, Any],
        *,
        sender_id: str = "",
        text: str = "",
    ) -> list[dict[str, Any]]:
        if not self.enable_worldbook_member_recognition:
            return []
        profiles = self.data.get("worldbook_member_profiles")
        if not isinstance(profiles, dict):
            return []
        text = str(text or "")
        recent_speaker_ids: list[str] = []
        recent = group.get("recent_messages")
        if isinstance(recent, list):
            for item in recent[-6:]:
                if not isinstance(item, dict):
                    continue
                recent_id = _single_line(item.get("sender_id"), 40)
                if recent_id and recent_id not in recent_speaker_ids:
                    recent_speaker_ids.append(recent_id)
        selected: dict[str, dict[str, Any]] = {}
        if sender_id and isinstance(profiles.get(sender_id), dict) and profiles[sender_id].get("enabled", True):
            selected[sender_id] = self._worldbook_profile_view(
                profiles[sender_id],
                match_reason="当前发言者 QQ 精确匹配",
                confidence="confirmed",
            )
        if self.worldbook_member_match_aliases and text and len(selected) < self.worldbook_member_inject_limit:
            token_hits: dict[str, list[tuple[str, dict[str, Any]]]] = {}
            for user_id, profile in profiles.items():
                if not isinstance(profile, dict) or not profile.get("enabled", True):
                    continue
                if user_id in selected:
                    continue
                for token in self._worldbook_profile_tokens(profile):
                    if self._worldbook_token_mentioned(token, text):
                        token_hits.setdefault(token, []).append((str(user_id), profile))
            for token in sorted(token_hits, key=len, reverse=True):
                hits = token_hits[token]
                if len(hits) != 1:
                    continue
                user_id, profile = hits[0]
                if user_id in selected:
                    continue
                selected[user_id] = self._worldbook_profile_view(
                    profile,
                    match_reason=f"当前消息明确提到：{token}",
                    confidence="mentioned",
                )
                if len(selected) >= self.worldbook_member_inject_limit:
                    break
        for recent_id in recent_speaker_ids:
            if len(selected) >= self.worldbook_member_inject_limit:
                break
            if recent_id in selected:
                continue
            profile = profiles.get(recent_id)
            if isinstance(profile, dict) and profile.get("enabled", True):
                selected[recent_id] = self._worldbook_profile_view(
                    profile,
                    match_reason="最近发言者 QQ 精确匹配",
                    confidence="confirmed",
                )
        ranked = sorted(
            selected.values(),
            key=lambda item: (
                1 if item.get("_match_confidence") == "confirmed" else 0,
                _safe_int(item.get("priority"), 120, -1000),
            ),
            reverse=True,
        )
        return ranked[: self.worldbook_member_inject_limit]

    def _format_worldbook_group_members_for_prompt(self, group: dict[str, Any], sender_id: str = "", text: str = "") -> str:
        if not self.enable_worldbook_member_recognition:
            return ""
        lines: list[str] = []
        group_id = _single_line(group.get("group_id"), 40)
        group_profiles = self.data.get("worldbook_group_profiles")
        if group_id and isinstance(group_profiles, dict):
            group_profile = group_profiles.get(group_id)
            if isinstance(group_profile, dict) and group_profile.get("enabled", True):
                lines.append(
                    f"群聊资料：{_single_line(group_profile.get('name'), 40) or group_id}｜"
                    f"{_single_line(group_profile.get('content'), 320)}"
                )
        profiles = self._select_worldbook_member_profiles_for_group(group, sender_id=sender_id, text=text)
        if profiles:
            injected = []
            for profile in profiles:
                injected.append(
                    f"{_single_line(profile.get('user_id'), 40) or '-'}:"
                    f"{_single_line(profile.get('name'), 40) or '-'}"
                    f"[{_single_line(profile.get('_match_confidence'), 20) or '-'}"
                    f"/{_single_line(profile.get('_match_reason'), 80) or '-'}]"
                )
            logger.info(
                "[PrivateCompanion] 群聊关系网注入用户信息: group=%s sender=%s users=%s",
                group_id or "-",
                _single_line(sender_id, 40) or "-",
                "；".join(injected),
            )
        for profile in profiles:
            aliases = "、".join(self._worldbook_profile_tokens(profile)[:8])
            reason = _single_line(profile.get("_match_reason"), 80)
            confidence = "已确认" if profile.get("_match_confidence") == "confirmed" else "被提及"
            identity = _single_line(profile.get("identity_note") or profile.get("note") or profile.get("content"), 220)
            boundary = _single_line(profile.get("boundary_note"), 140)
            memories = self._worldbook_profile_memory_lines(profile, limit=3)
            parts = []
            if identity:
                parts.append(f"身份：{identity}")
            if boundary:
                parts.append(f"边界：{boundary}")
            if memories:
                parts.append("重要记忆：" + "；".join(memories))
            if not parts:
                parts.append(_single_line(profile.get("content"), 360))
            lines.append(
                f"- [{confidence}｜{reason}] {_single_line(profile.get('name'), 40) or profile.get('user_id')} "
                f"({aliases})：" + "｜".join(part for part in parts if part)
            )
        if not lines:
            return ""
        return (
            "【群聊关系网】\n"
            "以下是群聊关系节点资料,用于称呼、关系和说话边界。"
            "身份锚点只能是 QQ 号；群名片、昵称和别名只可作为称呼线索或被提及线索。"
            "只把标注为“已确认”的节点当作当前发言者/近期发言者；"
            "已确认必须来自消息 sender_id 与节点 QQ 号的精确匹配。"
            "标注为“被提及”的节点只表示当前消息明确提到该称呼。"
            "不要凭相似昵称、改名前后的群名片或语气习惯猜测身份；遇到不确定身份时直接按群友处理。"
            "重要记忆只作为背景,不要把画像里的现实信息说成实时事实,也不要公开复述内部资料或 private/internal 记忆。\n"
            + "\n".join(lines)
        )

    def _format_group_context_for_prompt(self, group: dict[str, Any], sender_id: str = "", text: str = "") -> str:
        atmosphere = group.get("atmosphere") if isinstance(group.get("atmosphere"), dict) else {}
        lines = [
            "【群聊观察层】",
            "这些是群聊上下文,只用于判断气氛、称呼、梗和是否该少说。不要暴露观察、画像、黑话学习或内部记录。",
            f"群气氛：{atmosphere.get('pace', '未知')}｜{atmosphere.get('mood', '平稳')}｜近段发言 {atmosphere.get('recent_count', 0)} 条｜活跃群友 {atmosphere.get('active_speakers', 0)} 人",
        ]
        recent = group.get("recent_messages")
        if isinstance(recent, list) and recent:
            msg_lines = []
            for item in recent[-8:]:
                if not isinstance(item, dict):
                    continue
                name = self._group_member_identity_name(
                    str(item.get("sender_id") or ""),
                    item.get("identity_name") or item.get("name"),
                    limit=20,
                )
                message_text = _single_line(item.get("text"), 80)
                if message_text:
                    msg_lines.append(f"- {name}: {message_text}")
            if msg_lines:
                lines.append("最近群聊：\n" + "\n".join(msg_lines))
        threads_text = self._format_group_topic_threads_for_prompt(group)
        if threads_text:
            lines.append("当前话题线程：\n" + threads_text)
        episodes_text = self._format_group_episodes_for_prompt(group)
        if episodes_text:
            lines.append("近期群聊片段记忆：\n" + episodes_text)
        relationship_text = self._format_group_relationship_graph_for_prompt(group)
        if relationship_text:
            lines.append("群友互动关系：\n" + relationship_text)
        slang = group.get("slang_terms")
        if isinstance(slang, list) and slang:
            terms = []
            for item in slang[:12]:
                if isinstance(item, dict):
                    term = _single_line(item.get("term"), 16)
                    if term:
                        terms.append(term)
            if terms:
                lines.append("群内常见词/梗：" + "、".join(terms))
        meaning_text = self._format_group_slang_meanings_for_prompt(group)
        if meaning_text:
            lines.append("群内词义参考：\n" + meaning_text)
        worldbook_text = self._format_worldbook_group_members_for_prompt(group, sender_id, text)
        if worldbook_text:
            lines.append(worldbook_text)
        members = group.get("members")
        if sender_id and isinstance(members, dict):
            member = members.get(sender_id)
            if isinstance(member, dict):
                phrases = member.get("recent_phrases") if isinstance(member.get("recent_phrases"), list) else []
                phrase_text = " / ".join(_single_line(item, 24) for item in phrases[:4] if _single_line(item, 24))
                identity_note = _single_line(member.get("identity_note"), 80)
                boundary_note = _single_line(member.get("boundary_note"), 80)
                lines.append(
                    f"当前发言者：{self._group_member_identity_name(sender_id, member.get('identity_name') or member.get('name'), limit=24)}"
                    f"｜发言样本 {member.get('count', 0)} 条"
                    + (f"｜近期短句：{phrase_text}" if phrase_text else "")
                    + (f"｜关系备注：{identity_note}" if identity_note else "")
                    + (f"｜互动边界：{boundary_note}" if boundary_note else "")
                )
        lines.append(
            "群聊回复原则：被叫到或确实需要回应时再说；短一点,像群友接话；不要逐条总结群聊,不要当主持人,不要把每个话题都认真升格。"
        )
        if self.enable_group_privacy_guard:
            lines.append(
                "隐私边界：绝不能把私聊记忆、用户私聊偏好、内部画像或观察记录说到群里；"
                "不要说“我记得你私聊说过”；不要公开评价群友关系。只把这些当作少说错话的背景。"
            )
        livingmemory_guidance = self._format_livingmemory_guidance(scope="group")
        if livingmemory_guidance:
            lines.append(livingmemory_guidance)
        return "\n".join(lines)

    def _format_group_status(self, group: dict[str, Any]) -> str:
        atmosphere = group.get("atmosphere") if isinstance(group.get("atmosphere"), dict) else {}
        slang = group.get("slang_terms") if isinstance(group.get("slang_terms"), list) else []
        members = group.get("members") if isinstance(group.get("members"), dict) else {}
        top_terms = []
        for item in slang[:12]:
            if isinstance(item, dict) and item.get("term"):
                top_terms.append(f"{item.get('term')}({item.get('count', 0)})")
        active_members = sorted(
            [(user_id, item) for user_id, item in members.items() if isinstance(item, dict)],
            key=lambda pair: _safe_int(pair[1].get("count"), 0, 0),
            reverse=True,
        )[:8]
        member_text = "、".join(
            f"{self._group_member_identity_name(str(item.get('user_id') or item.get('sender_id') or user_id), item.get('identity_name') or item.get('name'), limit=16)}({item.get('count', 0)})"
            for user_id, item in active_members
        )
        return (
            f"群聊陪伴状态：{'开启' if group.get('enabled', True) else '关闭'}\n"
            f"访问模式：{'黑名单' if self.group_access_mode == 'blacklist' else '白名单'}\n"
            f"群号：{group.get('group_id', '')}\n"
            f"累计观察：{group.get('message_count', 0)} 条\n"
            f"气氛：{atmosphere.get('pace', '未知')}｜{atmosphere.get('mood', '平稳')}\n"
            f"常见词/梗：{'、'.join(top_terms) if top_terms else '暂无'}\n"
            f"活跃群友：{member_text or '暂无'}\n"
            f"当前话题：{_single_line(self._format_group_topic_threads_for_prompt(group), 180) or '暂无'}\n"
            f"关系网络：{_single_line(self._format_group_relationship_graph_for_prompt(group), 180) or '暂无'}\n"
            f"插话反馈：{self._format_group_interjection_feedback(group)}"
        )

    def _format_group_interjection_feedback(self, group: dict[str, Any]) -> str:
        feedback = group.get("interjection_feedback")
        if not isinstance(feedback, dict) or not feedback:
            return "暂无"
        return (
            f"后续回复 {feedback.get('replies_after', 0)}｜"
            f"正向 {feedback.get('positive', 0)}｜负向 {feedback.get('negative', 0)}"
        )

    def _group_interjection_allowed(self, group: dict[str, Any], text: str) -> tuple[bool, str]:
        if not self.enable_group_interjection:
            return False, "群聊主动插话未开启"
        if self.group_interject_max_daily <= 0:
            return False, "群聊主动插话上限为 0"
        today = _today_key()
        if group.get("interject_day") != today:
            group["interject_day"] = today
            group["interject_today"] = 0
        if _safe_int(group.get("interject_today"), 0, 0) >= self.group_interject_max_daily:
            return False, "今日群聊插话已达上限"
        if _now_ts() - _safe_float(group.get("last_interject_at"), 0) < self.group_interject_min_interval_minutes * 60:
            return False, "群聊插话间隔太近"
        atmosphere = group.get("atmosphere") if isinstance(group.get("atmosphere"), dict) else {}
        mood = str(atmosphere.get("mood") or "")
        pace = str(atmosphere.get("pace") or "")
        if pace == "热闹" and mood not in {"玩笑", "求助"}:
            return False, "群聊太热闹,不抢话"
        if re.search(r"(有没有人|谁懂|救命|怎么回事|咋办|笑死|绷不住|太离谱)", text):
            return random.random() < 0.08, "有自然接话口"
        if mood == "玩笑":
            return random.random() < 0.025, "玩笑气氛"
        if mood == "求助":
            return random.random() < 0.045, "求助气氛"
        return False, "没有自然插话口"

    async def _maybe_group_interject(self, event: AstrMessageEvent, group: dict[str, Any], text: str) -> None:
        allowed, reason = self._group_interjection_allowed(group, text)
        if not allowed:
            return
        prompt = f"""
你在一个群聊里,现在可以非常轻地接一句。
只输出要发到群里的正文,不要解释。

【群聊上下文】
{self._format_group_context_for_prompt(group)}

【刚刚触发的消息】
{_single_line(text, 180)}

要求：
- 1 句,最多 35 个中文字符
- 像群友自然接话,不要像助手
- 不要主持群聊,不要总结,不要 @ 人
- 不要提系统、观察、黑话学习、插件
- 如果不适合说话,输出空字符串
""".strip()
        generated = await self._llm_call(
            prompt,
            max_tokens=80,
            provider_id=self._task_provider(self.group_interject_provider_id, self.mai_style_provider_id),
            task="group_interject",
        )
        reply = _single_line(generated, 80)
        if not reply or reply in {"空字符串", "不适合说话"}:
            return
        if self._response_review_flags(reply, {}):
            return
        await event.send(event.plain_result(reply))
        group["last_interject_at"] = _now_ts()
        group["interject_today"] = _safe_int(group.get("interject_today"), 0, 0) + 1
        group["last_bot_interjection"] = {
            "ts": group["last_interject_at"],
            "text": reply,
            "reason": reason,
            "topic_signature": self._group_topic_signature(text),
        }
        threads = group.get("topic_threads")
        if isinstance(threads, list):
            signature = self._group_topic_signature(text)
            for item in threads:
                if isinstance(item, dict) and self._topic_signature_similar(signature, str(item.get("signature") or "")):
                    item["bot_joined"] = True
                    item["bot_joined_ts"] = group["last_interject_at"]
                    break

    async def _maybe_refresh_group_episode(self, group_id: str, group: dict[str, Any]) -> None:
        if not self.enable_group_episode_memory:
            return
        now = _now_ts()
        if now - _safe_float(group.get("last_episode_refresh_at"), 0) < self.group_episode_refresh_minutes * 60:
            return
        recent = group.get("recent_messages")
        if not isinstance(recent, list) or len(recent) < 12:
            return
        lines = []
        for item in recent[-80:]:
            if not isinstance(item, dict):
                continue
            name = _single_line(item.get("name"), 20) or "群友"
            text = _single_line(item.get("text"), 100)
            if text:
                lines.append(f"{name}: {text}")
        if len(lines) < 8:
            return
        prompt = f"""
请把下面这段群聊整理成群聊片段记忆。
目标是让角色以后知道群里发生过什么、哪个梗出现过、哪些话题已经结束。
不要编造,不要输出解释。

【群聊记录】
{chr(10).join(lines[-80:])}

只输出 JSON：
{{
  "summary": "这段群聊发生了什么",
  "main_topics": ["主要话题"],
  "new_meme": "新出现或变热的梗/黑话,没有就空字符串",
  "active_people": ["活跃群友昵称"],
  "avoid_repeat": ["短期内不要重复接的话题"]
}}
""".strip()
        raw = await self._llm_call(
            prompt,
            max_tokens=420,
            provider_id=self._task_provider(self.group_episode_provider_id, self.mai_style_provider_id),
            task="group_episode",
        )
        payload = self._extract_json_payload(raw or "")
        if not isinstance(payload, dict):
            return
        episode = {
            "date": _today_key(),
            "created_ts": now,
            "summary": _single_line(payload.get("summary"), 140),
            "main_topics": self._normalize_string_list(payload.get("main_topics"), limit=6, item_limit=50),
            "new_meme": _single_line(payload.get("new_meme"), 60),
            "active_people": self._normalize_string_list(payload.get("active_people"), limit=8, item_limit=30),
            "avoid_repeat": self._normalize_string_list(payload.get("avoid_repeat"), limit=6, item_limit=60),
        }
        if not episode["summary"]:
            return
        async with self._data_lock:
            current = self._get_group(group_id)
            episodes = current.setdefault("group_episodes", [])
            if not isinstance(episodes, list):
                episodes = []
                current["group_episodes"] = episodes
            if not episodes or _single_line(episodes[-1].get("summary") if isinstance(episodes[-1], dict) else "", 140) != episode["summary"]:
                episodes.append(episode)
            del episodes[:-self.max_group_episodes]
            current["last_episode_refresh_at"] = now
            self._save_data_sync()

    async def _maybe_refresh_group_slang_meanings(self, group_id: str, group: dict[str, Any]) -> None:
        if not self.enable_group_slang_meanings:
            return
        now = _now_ts()
        if now - _safe_float(group.get("last_slang_summary_at"), 0) < self.group_slang_summary_minutes * 60:
            return
        slang = group.get("slang_terms")
        if not isinstance(slang, list) or len(slang) < 5:
            return
        recent = group.get("recent_messages")
        if not isinstance(recent, list):
            recent = []
        terms = [
            _single_line(item.get("term"), 20)
            for item in slang[:20]
            if isinstance(item, dict) and _single_line(item.get("term"), 20)
        ]
        examples = []
        for item in recent[-80:]:
            if not isinstance(item, dict):
                continue
            text = _single_line(item.get("text"), 100)
            if any(term and term in text for term in terms[:12]):
                examples.append(f"{_single_line(item.get('name'), 18) or '群友'}: {text}")
        if not examples:
            return
        prompt = f"""
请根据群聊样例,给这些群内常见词/梗做很短的语义解释。
只解释能从样例看出来的含义；不确定就写“语境不明”。
不要输出解释过程。

【候选词】
{", ".join(terms)}

【群聊样例】
{chr(10).join(examples[-60:])}

只输出 JSON,键为词,值为对象：
{{
  "某词": {{"meaning": "一句话含义", "usage": "什么时候用"}}
}}
""".strip()
        raw = await self._llm_call(
            prompt,
            max_tokens=560,
            provider_id=self._task_provider(self.group_slang_provider_id, self.mai_style_provider_id),
            task="group_slang",
        )
        payload = self._extract_json_payload(raw or "")
        if not isinstance(payload, dict):
            return
        normalized: dict[str, dict[str, str]] = {}
        for term, value in payload.items():
            key = _single_line(term, 20)
            if not key:
                continue
            if isinstance(value, dict):
                meaning = _single_line(value.get("meaning"), 90)
                usage = _single_line(value.get("usage"), 90)
            else:
                meaning = _single_line(value, 90)
                usage = ""
            if meaning:
                normalized[key] = {
                    "meaning": meaning,
                    "usage": usage,
                    "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                }
        if not normalized:
            return
        async with self._data_lock:
            current = self._get_group(group_id)
            meanings = current.setdefault("slang_meanings", {})
            if not isinstance(meanings, dict):
                meanings = {}
                current["slang_meanings"] = meanings
            meanings.update(normalized)
            current["last_slang_summary_at"] = now
            self._save_data_sync()

    async def _collect_recent_private_conversation_text(
        self,
        user: dict[str, Any],
        *,
        hours: int = 24,
        max_lines: int = 80,
    ) -> str:
        umo = str(user.get("umo") or "").strip()
        if not umo:
            return ""
        try:
            conv_id = await self.context.conversation_manager.get_curr_conversation_id(umo)
            if not conv_id:
                return ""
            conv = await self.context.conversation_manager.get_conversation(umo, conv_id)
        except Exception:
            return ""
        history = self._load_conversation_history_items(conv)
        if not history:
            return ""
        now = _now_ts()
        cutoff = now - max(1, hours) * 3600
        lines: list[str] = []
        for item in history:
            line = self._format_history_item_for_summary(item)
            if not line:
                continue
            ts = self._history_item_timestamp(item)
            if ts is not None and ts < cutoff:
                continue
            lines.append(line)
        if not lines:
            lines = [self._format_history_item_for_summary(item) for item in history[-max_lines:]]
            lines = [line for line in lines if line]
        return "\n".join(lines[-max_lines:]).strip()

    def _normalize_string_list(self, raw: Any, *, limit: int = 6, item_limit: int = 90) -> list[str]:
        if isinstance(raw, list):
            values = raw
        elif raw:
            values = [raw]
        else:
            values = []
        result = []
        for value in values:
            text = _single_line(value, item_limit)
            if text and text not in result:
                result.append(text)
            if len(result) >= limit:
                break
        return result

    async def _maybe_refresh_dialogue_episode(self, user_id: str, user: dict[str, Any]) -> None:
        if not self.enable_dialogue_episode_memory:
            return
        count = _safe_int(user.get("episode_message_count"), 0, 0)
        last_at = _safe_float(user.get("last_episode_refresh_at"), 0)
        if count < self.episode_memory_refresh_messages and _now_ts() - last_at < self.episode_memory_refresh_minutes * 60:
            return
        raw_text = await self._collect_recent_private_conversation_text(user, hours=24, max_lines=70)
        if not raw_text or len(raw_text) < 80:
            return
        prompt = f"""
请把最近一段私聊整理成“陪伴型对话片段记忆”。
目标是让角色以后能自然延续共同经历,而不是复述聊天记录。
不要编造,不要写隐私外推,不要输出解释。

【AstrBot 默认人格】
{self._get_default_persona_prompt()}

【最近对话】
{raw_text}

只输出 JSON：
{{
  "summary": "这段对话作为共同经历的一句话摘要",
  "emotional_residue": "留下的情绪余味,没有就写空字符串",
  "reusable_topic": "以后可自然接起的小话头,没有就写空字符串",
  "user_events": ["用户最近发生/在意的事"],
  "bot_promises": ["Bot 说过要做、要记得、要提醒或要延续的事"],
  "open_loops": ["尚未完成、之后可自然问起或兑现的约定/话题"],
  "avoid_next": ["短期内不该反复提的内容"]
}}
""".strip()
        raw = await self._llm_call(
            prompt,
            max_tokens=520,
            provider_id=self._task_provider(self.dialogue_episode_provider_id, self.mai_style_provider_id),
            task="dialogue_episode",
        )
        payload = self._extract_json_payload(raw or "")
        if not isinstance(payload, dict):
            return
        episode = {
            "date": _today_key(),
            "created_ts": _now_ts(),
            "summary": _single_line(payload.get("summary"), 140),
            "emotional_residue": _single_line(payload.get("emotional_residue"), 100),
            "reusable_topic": _single_line(payload.get("reusable_topic"), 100),
            "user_events": self._normalize_string_list(payload.get("user_events"), limit=6),
            "bot_promises": self._normalize_string_list(payload.get("bot_promises"), limit=6),
            "avoid_next": self._normalize_string_list(payload.get("avoid_next"), limit=6),
        }
        if not episode["summary"]:
            return
        open_loops = self._normalize_string_list(payload.get("open_loops"), limit=8, item_limit=110)
        async with self._data_lock:
            current = self._get_user(user_id)
            episodes = current.setdefault("dialogue_episodes", [])
            if not isinstance(episodes, list):
                episodes = []
                current["dialogue_episodes"] = episodes
            if not episodes or _single_line(episodes[-1].get("summary") if isinstance(episodes[-1], dict) else "", 140) != episode["summary"]:
                episodes.append(episode)
            del episodes[:-self.max_dialogue_episodes]
            if self.enable_open_loop_tracking:
                current_loops = current.setdefault("open_loops", [])
                if not isinstance(current_loops, list):
                    current_loops = []
                    current["open_loops"] = current_loops
                existing = {_single_line(item.get("text"), 120) for item in current_loops if isinstance(item, dict)}
                for loop in open_loops:
                    if loop in existing:
                        continue
                    current_loops.append(
                        {
                            "text": loop,
                            "status": "待自然延续",
                            "created_ts": _now_ts(),
                            "source": "dialogue_episode",
                        }
                    )
                del current_loops[:-12]
            current["episode_message_count"] = 0
            current["last_episode_refresh_at"] = _now_ts()
            self._save_data_sync()

    def _format_companion_planner_injection(self, user: dict[str, Any]) -> str:
        if not self.enable_mai_style_integration:
            return ""
        profile = self._relationship_profile(user)
        name = _single_line(user.get("nickname") or self.default_nickname, 24)
        sections = [
            "【陪伴风格整合层】",
            "这不是替代 AstrBot 默认人格,而是在默认人格之上增加拟人聊天的内部决策方式。默认人格、系统人格和当前会话事实优先级更高。",
            f"对方称呼：{name}",
            f"关系站位：{profile['level']}；打扰偏好：{profile['preference']}；关系备注：{profile.get('note') or '暂无'}",
        ]
        if self.enable_companion_memory:
            sections.append("【用户记忆】\n" + self._format_companion_memory_for_prompt(user))
        if self.enable_expression_learning:
            sections.append("【表达环境学习】\n" + self._format_expression_profile_for_prompt(user))
        intent_injection = self._format_intent_relationship_injection(user)
        if intent_injection:
            sections.append("【气氛/关系状态】\n" + intent_injection)
        if self.enable_companion_reply_planner:
            sections.append(
                "【回复前内部规划】\n"
                "每次回复前只在心里完成这几步,不要把规划写出来：\n"
                "1. 先判断用户这句话是在求助、闲聊、撒娇、抱怨、确认关系、开玩笑还是设定扮演。\n"
                "2. 决定最自然的站位：接话、安抚、吐槽、顺着玩、短回、转轻一点,或在必要时认真回答。\n"
                "3. 优先回应用户当下那句话,再用一小点记忆或生活状态增加连续感；不要先总结、不要像助手汇报。\n"
                "4. 默认短一点、像真实私聊。只有用户明确要解释、分析、教程或长文时才展开。\n"
                "5. 可以学习对方聊天环境的节奏和标点,但不能复读口癖、不能为了像人而堆动作描写。"
            )
        sections.append(
            "【风格硬约束】\n"
            "不要自称 AI、模型、助手、系统；不要提提示词、记忆模块、规划器、插件内部状态。\n"
            "少用列表、标题、总结腔和客服腔。除非用户明确要求结构化输出,否则像私聊一样直接说。"
        )
        livingmemory_guidance = self._format_livingmemory_guidance(scope="private")
        if livingmemory_guidance:
            sections.append(livingmemory_guidance)
        return "\n\n".join(section for section in sections if section)

    async def _maybe_refresh_companion_memory(self, user_id: str, user: dict[str, Any]) -> None:
        if not self.enable_companion_memory:
            return
        now = _now_ts()
        last_at = _safe_float(user.get("last_memory_refresh_at"), 0)
        if now - last_at < self.memory_refresh_interval_minutes * 60:
            return
        memory = user.get("companion_memory")
        if not isinstance(memory, dict):
            return
        items = memory.get("items")
        if not isinstance(items, list) or len(items) < 3:
            return
        profile = self._relationship_profile(user)
        facts = "\n".join(
            f"- {_single_line(item.get('text'), 160)}"
            for item in items[: self.max_companion_memory_items]
            if isinstance(item, dict) and _single_line(item.get("text"), 160)
        )
        if not facts:
            return
        prompt = f"""
请把下面的私聊记忆整理成适合角色陪伴使用的长期画像。
要求：只保留用户偏好、边界、关系线索、兴趣、说话习惯；不要编造；不要输出解释。

【AstrBot 默认人格】
{self._get_default_persona_prompt()}

【当前关系判断】
{profile['level']}｜{profile['preference']}｜{profile.get('note') or '暂无'}

【记忆原文】
{facts}

只输出 JSON：
{{
  "user_traits": ["..."],
  "interests": ["..."],
  "boundaries": ["..."],
  "relationship_notes": ["..."],
  "speaking_style": ["..."]
}}
""".strip()
        raw = await self._llm_call(
            prompt,
            max_tokens=420,
            provider_id=self._task_provider(self.companion_memory_provider_id, self.mai_style_provider_id),
            task="memory_profile",
        )
        payload = self._extract_json_payload(raw or "")
        if not isinstance(payload, dict):
            return
        normalized: dict[str, list[str]] = {}
        for key in ("user_traits", "interests", "boundaries", "relationship_notes", "speaking_style"):
            value = payload.get(key)
            if isinstance(value, list):
                normalized[key] = [_single_line(item, 80) for item in value[:8] if _single_line(item, 80)]
            elif value:
                normalized[key] = [_single_line(value, 80)]
            else:
                normalized[key] = []
        async with self._data_lock:
            current = self._get_user(user_id)
            current_memory = current.setdefault("companion_memory", {})
            if isinstance(current_memory, dict):
                current_memory["profile"] = normalized
                current_memory["profile_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            current["last_memory_refresh_at"] = now
            self._save_data_sync()

    def _analyze_inbound_intent(self, text: str) -> dict[str, Any]:
        cleaned = _single_line(text, 240)
        if not cleaned:
            return {"intent": "empty", "emotion": "neutral", "pressure": 0, "reply_style": "short"}
        lower = cleaned.lower()
        intent = "chat"
        emotion = "neutral"
        pressure = 0
        reply_style = "natural"
        if re.search(r"(怎么|如何|为什么|帮我|能不能|可以.*吗|教程|代码|报错|分析|解释)", cleaned):
            intent = "help"
            reply_style = "useful"
            pressure += 1
        if re.search(r"(烦|累|难受|崩溃|不想|想哭|emo|压力|焦虑|失眠|疼|委屈)", cleaned, re.IGNORECASE):
            intent = "comfort"
            emotion = "low"
            pressure += 2
            reply_style = "soft"
        if re.search(r"(哈哈|笑死|草|绷|乐|hhh|233|好玩|乐了)", lower):
            intent = "play"
            emotion = "light"
            reply_style = "playful"
        if re.search(r"(抱抱|亲亲|摸摸|陪我|想你|喜欢你|爱你|贴贴)", cleaned):
            intent = "intimacy"
            emotion = "close"
            reply_style = "warm_short"
        if re.search(r"(别|不要|别再|不许|讨厌|烦你|闭嘴|太吵|打扰)", cleaned):
            intent = "boundary"
            emotion = "resistant"
            pressure += 3
            reply_style = "back_off"
        if len(cleaned) <= 6 and intent == "chat":
            reply_style = "very_short"
        return {
            "intent": intent,
            "emotion": emotion,
            "pressure": min(5, pressure),
            "reply_style": reply_style,
            "text": cleaned,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def _update_relationship_state_from_intent(self, user: dict[str, Any], intent: dict[str, Any]) -> None:
        if not self.enable_relationship_state_machine or not isinstance(intent, dict):
            return
        state = user.setdefault("relationship_state", {})
        if not isinstance(state, dict):
            state = {}
            user["relationship_state"] = state
        current = str(state.get("mode") or "normal")
        inbound_intent = str(intent.get("intent") or "chat")
        pressure = _safe_int(intent.get("pressure"), 0, 0, 5)
        if inbound_intent == "boundary":
            current = "backoff"
            state["backoff_until"] = _now_ts() + 6 * 3600
        elif pressure >= 2:
            current = "careful"
        elif inbound_intent in {"intimacy", "play"}:
            current = "warming"
        elif _safe_float(state.get("backoff_until"), 0) > _now_ts():
            current = "backoff"
        else:
            current = "normal"
        state["mode"] = current
        state["last_intent"] = inbound_intent
        state["last_emotion"] = str(intent.get("emotion") or "neutral")
        state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

    def _format_intent_relationship_injection(self, user: dict[str, Any]) -> str:
        intent = user.get("intent_profile")
        state = user.get("relationship_state")
        lines: list[str] = []
        if isinstance(intent, dict) and intent.get("intent"):
            lines.append(
                "最近用户意图："
                f"{intent.get('intent')}｜情绪 {intent.get('emotion', 'neutral')}｜"
                f"建议回复姿态 {intent.get('reply_style', 'natural')}"
            )
        if isinstance(state, dict) and state.get("mode"):
            mode = str(state.get("mode") or "normal")
            mode_hint = {
                "backoff": "用户可能在表达边界或不想被打扰,回复要短、低压,不要撒娇追问。",
                "careful": "用户可能有压力或负面情绪,先接住情绪,少讲道理。",
                "warming": "互动有升温或玩笑感,可以更自然亲近一点,但别过度表演。",
                "normal": "关系状态平稳,正常接话即可。",
            }.get(mode, "正常接话即可。")
            lines.append(f"关系状态机：{mode}。{mode_hint}")
        recent = self._format_recent_passive_topics_hint(user)
        if recent:
            lines.append("最近普通回复里已经用过的切口：\n" + recent)
        return "\n".join(lines)

    def _cleanup_recent_passive_topics(self, user: dict[str, Any], *, now: float | None = None) -> list[dict[str, Any]]:
        now = now or _now_ts()
        raw = user.get("recent_reply_topics", [])
        if not isinstance(raw, list):
            raw = []
        kept = [
            item for item in raw
            if isinstance(item, dict) and now - _safe_float(item.get("ts"), 0) <= self.passive_topic_memory_hours * 3600
        ]
        user["recent_reply_topics"] = kept[-18:]
        return user["recent_reply_topics"]

    def _remember_passive_reply_topic(self, user: dict[str, Any], text: str, inbound_text: str = "") -> None:
        if not self.enable_passive_topic_suppression:
            return
        signature = self._proactive_topic_signature(text, inbound_text)
        if not signature:
            return
        recent = self._cleanup_recent_passive_topics(user)
        recent.append({"ts": _now_ts(), "signature": signature, "text": _single_line(text, 120)})
        del recent[:-18]

    def _format_recent_passive_topics_hint(self, user: dict[str, Any]) -> str:
        if not self.enable_passive_topic_suppression:
            return ""
        recent = self._cleanup_recent_passive_topics(user)
        lines = []
        for item in recent[-5:]:
            text = _single_line(item.get("text"), 70)
            if text:
                lines.append(f"- {self._format_timestamp_elapsed(item.get('ts'))}回复过：{text}")
        return "\n".join(lines)

    def _response_review_flags(self, text: str, user: dict[str, Any]) -> list[str]:
        cleaned = str(text or "").strip()
        flags: list[str] = []
        if not cleaned:
            return flags
        if "```" in cleaned:
            return flags
        intent_profile = user.get("intent_profile") if isinstance(user.get("intent_profile"), dict) else {}
        is_help = str(intent_profile.get("intent") or "") == "help"
        length_limit = self.response_review_max_chars * (2 if is_help else 1)
        if len(cleaned) > length_limit:
            flags.append("too_long")
        if re.search(r"^(好的|当然|没问题|我理解|总结一下|以下是|首先|其次|最后)[，,：:]", cleaned):
            flags.append("assistant_tone")
        if re.search(r"(作为.*助手|AI|模型|系统|提示词|插件|后台|根据.*信息|我会从.*角度)", cleaned, re.IGNORECASE):
            flags.append("meta_or_assistant")
        if not is_help and re.search(r"^\s*(?:[-*]|\d+[.、])\s+", cleaned, re.MULTILINE) and len(cleaned) < 900:
            flags.append("over_structured")
        if re.search(r"(能量\s*\d+|关系站位|状态机|内部规划|用户意图|表达学习|陪伴记忆)", cleaned):
            flags.append("leaks_internal")
        signature = self._proactive_topic_signature(cleaned)
        if self.enable_passive_topic_suppression:
            for item in self._cleanup_recent_passive_topics(user):
                if self._topic_signature_similar(signature, str(item.get("signature") or "")):
                    flags.append("repeated_topic")
                    break
        last_message = _single_line(user.get("last_companion_message"), 300)
        last_sent = _safe_float(user.get("last_sent"), 0)
        if last_message and self._text_repeats_recent_message(cleaned, last_message):
            if not last_sent or _now_ts() - last_sent <= self.proactive_reply_context_hours * 3600:
                flags.append("repeats_last_bot_message")
        return list(dict.fromkeys(flags))

    async def _review_and_rewrite_response(self, user: dict[str, Any], inbound_text: str, response_text: str) -> str:
        if not self.enable_response_self_review:
            return response_text
        flags = self._response_review_flags(response_text, user)
        if not flags:
            return response_text
        intent = user.get("intent_profile") if isinstance(user.get("intent_profile"), dict) else {}
        last_message = _single_line(user.get("last_companion_message"), 300)
        prompt = f"""
把下面这条回复改写成更像真实私聊里的自然回复。
保留原意,不要新增事实,不要解释你在改写。

【用户刚才说】
{_single_line(inbound_text, 260) or '（无）'}

【刚才 Bot 已经说过，禁止复述或换皮重复】
{last_message or '（无）'}

【原回复】
{response_text}

【需要修正的问题】
{", ".join(flags)}

【当前意图/情绪】
{intent.get('intent', 'chat')}｜{intent.get('emotion', 'neutral')}｜{intent.get('reply_style', 'natural')}

要求：
- 只输出改写后的正文
- 不要标题、列表、JSON、括号动作、系统/AI/提示词字眼
- 普通闲聊尽量 1 到 3 句；求助类可以保留必要步骤,但更口语
- 如果用户情绪低,先接住情绪,少讲道理
- 如果是边界/不想被打扰,短一点,退一步
- 如果问题是重复上一条 Bot 消息,必须直接承接用户这句话,不要再说上一条里的“吃饱犯困/下午还有事/有什么安排”等同义内容
""".strip()
        rewritten = await self._llm_call(
            prompt,
            max_tokens=260,
            provider_id=self._task_provider(self.response_review_provider_id, self.mai_style_provider_id),
            task="response_review",
        )
        cleaned = str(rewritten or "").strip()
        if not cleaned:
            return response_text
        if len(cleaned) > max(len(response_text) + 80, self.response_review_max_chars + 160):
            return response_text
        if re.search(r"(提示词|系统|JSON|改写后|以下是)", cleaned, re.IGNORECASE):
            return response_text
        if last_message and self._text_repeats_recent_message(cleaned, last_message):
            fallback = self._fallback_non_repeating_reply(inbound_text)
            return fallback or response_text
        return cleaned

    @staticmethod
    def _compact_repeat_text(text: str) -> str:
        return re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", str(text or "")).lower()

    def _text_repeats_recent_message(self, text: str, recent_text: str) -> bool:
        current = self._compact_repeat_text(text)
        recent = self._compact_repeat_text(recent_text)
        if len(current) < 8 or len(recent) < 8:
            return False
        if current in recent or recent in current:
            return True
        current_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{3,}", text))
        recent_tokens = set(re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{3,}", recent_text))
        stopwords = {
            "刚才", "现在", "今天", "这个", "那个", "一下", "一点", "有点", "还有",
            "什么", "安排", "用户", "你呢", "我呢", "就是", "已经", "容易",
        }
        current_tokens = {token for token in current_tokens if token not in stopwords}
        recent_tokens = {token for token in recent_tokens if token not in stopwords}
        if current_tokens and recent_tokens:
            common = current_tokens & recent_tokens
            if len(common) >= 3 and len(common) / max(1, min(len(current_tokens), len(recent_tokens))) >= 0.45:
                return True
        current_sig = self._proactive_topic_signature(text)
        recent_sig = self._proactive_topic_signature(recent_text)
        if current_sig and recent_sig and current_sig == recent_sig:
            shared_chunks = 0
            for idx in range(max(0, len(current) - 3)):
                chunk = current[idx : idx + 4]
                if chunk and chunk in recent:
                    shared_chunks += 1
                    if shared_chunks >= 2:
                        return True
        return False

    def _fallback_non_repeating_reply(self, inbound_text: str) -> str:
        inbound = _single_line(inbound_text, 120)
        if not inbound:
            return "嗯，我在。"
        if any(token in inbound for token in ("吃", "觅食", "饭", "饿", "饱")):
            return "还在觅啊，那你先把饭解决完，别边吃边赶。"
        if any(token in inbound for token in ("忙", "事", "安排", "下午")):
            return "那先按你那边的节奏来，我不催你。"
        if len(inbound) <= 8:
            return "嗯嗯，接到。"
        return "懂了，那我先顺着你这边来。"


    def _fallback_relationship_level(
        self,
        score: int,
        reply_rate: float,
        inbound_count: int,
        proactive_count: int,
    ) -> tuple[str, str]:
        if proactive_count <= 0:
            return "熟悉", "普通"
        if score >= 16 and reply_rate >= 0.35:
            level = "亲近"
        elif score >= 3 or inbound_count >= 1 or reply_rate >= 0.2:
            level = "熟悉"
        else:
            level = "陌生"
        if proactive_count >= 3 and reply_rate < 0.15:
            preference = "低打扰"
        elif reply_rate >= 0.5 or score >= 18:
            preference = "可轻分享"
        else:
            preference = "普通"
        return level, preference

    async def _refresh_persona_relationship(self, user_id: str, user: dict[str, Any]):
        persona = self._get_default_persona_prompt()
        proactive_count = _safe_int(user.get("proactive_sent_count"), 0)
        reply_count = _safe_int(user.get("reply_count"), 0)
        inbound_count = _safe_int(user.get("inbound_count"), 0)
        reply_rate_available = proactive_count > 0
        reply_rate = reply_count / proactive_count if reply_rate_available else 0.0
        reply_rate_text = f"{reply_rate:.0%}" if reply_rate_available else "暂无样本"
        prompt = f"""
请根据 AstrBot 默认人格,评估该人格会如何理解它和用户之间的亲近程度与打扰边界。
不要使用固定阈值,要结合人格设定、互动数据和社交边界。
如果互动样本很少,不能把“暂无回复率样本”当成用户冷淡；默认优先相信 AstrBot 默认人格里写明的关系设定。

【AstrBot 默认人格】
{persona}

【互动数据】
用户 QQ：{user_id}
用户主动私聊次数：{inbound_count}
Bot 主动消息次数：{proactive_count}
Bot 主动后用户回复次数：{reply_count}
主动后回复率：{reply_rate_text}
连续未回复次数：{_safe_int(user.get('ignored_streak'), 0)}
最近用户消息：{_single_line(user.get('last_user_message'), 120) or '（暂无）'}

只输出 JSON：
{{
  "level": "陌生/熟悉/亲近 之一",
  "preference": "低打扰/普通/可轻分享 之一",
  "score": 0到100的整数,
  "note": "一句话说明这个人格为什么会这样判断"
}}
""".strip()
        raw_text = await self._llm_call(
            prompt,
            max_tokens=220,
            provider_id=self._task_provider(self.relationship_analysis_provider_id, self.mai_style_provider_id),
            task="relationship",
        )
        payload = self._extract_json_payload(raw_text or "")
        if not isinstance(payload, dict):
            return
        level = str(payload.get("level") or "").strip()
        preference = str(payload.get("preference") or "").strip()
        if level not in {"陌生", "熟悉", "亲近"}:
            return
        if preference not in {"低打扰", "普通", "可轻分享"}:
            preference = "普通"
        profile = {
            "level": level,
            "preference": preference,
            "score": _safe_int(payload.get("score"), 0, 0, 100),
            "note": _single_line(payload.get("note"), 120),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        async with self._data_lock:
            current = self._get_user(user_id)
            current["persona_relationship"] = profile
            self._save_data_sync()

    def _should_send(self, user: dict[str, Any]) -> tuple[bool, str]:
        self._recover_stale_proactive_sending(user)
        if user.get("proactive_sending"):
            return False, "上一条主动消息仍在发送中"
        if not user.get("umo"):
            return False, "缺少私聊会话"
        if self._simulation_active(user):
            return self._should_send_simulation(user)
        if self.max_daily_messages <= 0:
            return False, "每日上限为 0"
        if self._is_quiet_time() and not self._can_send_insomnia_night_message(user):
            return False, "免打扰时段"
        rel_state = user.get("relationship_state")
        if (
            self.enable_relationship_state_machine
            and isinstance(rel_state, dict)
            and rel_state.get("mode") == "backoff"
            and _safe_float(rel_state.get("backoff_until"), 0) > _now_ts()
        ):
            return False, "关系状态处于收敛期"

        now = _now_ts()
        planned_reason = str(user.get("planned_proactive_reason") or "")
        due_timer_active = self._has_due_llm_timer(user, now=now)
        next_at = _safe_float(user.get("next_proactive_at"), 0)
        if next_at <= 0:
            self._schedule_next_proactive(user, now=now)
            return False, "已安排下一次候选主动时间"
        if self._promote_earlier_daily_greeting_event(user, now=now):
            planned_reason = str(user.get("planned_proactive_reason") or "")
            next_at = _safe_float(user.get("next_proactive_at"), 0)
        if now < next_at:
            return False, "未到候选主动时间"
        if self._is_proactive_plan_stale(user, now=now) and not due_timer_active:
            self._clear_pending_proactive_plan(user)
            self._schedule_next_proactive(user, now=now, delay_hours=(1, 4))
            return False, "候选主动计划已过期,已重新安排"

        self._reset_daily_counter_if_needed(user)
        if _safe_int(user.get("sent_today"), 0) >= self.max_daily_messages:
            if not due_timer_active:
                self._schedule_next_proactive(user, now=now, delay_hours=(8, 16))
            return False, "已达每日上限"
        if not due_timer_active and now - _safe_float(user.get("last_seen"), 0) < self.idle_minutes * 60:
            idle_limit = (
                self.greeting_idle_minutes * 60
                if self._is_greeting_reason(planned_reason)
                else self.idle_minutes * 60
            )
            if now - _safe_float(user.get("last_seen"), 0) < idle_limit:
                if self._is_sticky_greeting_reason(planned_reason):
                    self._reschedule_greeting_within_window(user, planned_reason, now=now)
                return False, "用户刚活跃过"
        min_interval = self._effective_min_interval_seconds(user)
        if self._is_greeting_reason(planned_reason):
            min_interval = min(min_interval, self._greeting_min_interval_seconds(planned_reason))
        if not due_timer_active and now - _safe_float(user.get("last_sent"), 0) < min_interval:
            if self._is_sticky_greeting_reason(planned_reason):
                self._reschedule_greeting_within_window(user, planned_reason, now=now)
            return False, "发送间隔不足"
        if due_timer_active:
            return True, "ok(timer)"
        if not self._is_reason_allowed_now(planned_reason):
            if self._is_sticky_greeting_reason(planned_reason):
                self._reschedule_greeting_within_window(user, planned_reason, now=now)
                return False, "问候仍在窗口内,稍后再试"
            self._schedule_next_proactive(user, now=now)
            return False, "计划动机不适合当前时间"
        planned_action = str(user.get("planned_proactive_action") or "message")
        if not self._action_is_available(planned_action, user):
            self._mark_planned_candidate_status(user, "blocked", "动作不可用或媒体额度不足")
            self._clear_pending_proactive_plan(user)
            self._schedule_next_proactive(user, now=now, delay_hours=(2, 6))
            return False, "动作不可用或媒体额度不足"
        if self._planned_proactive_recently_repeated(user):
            self._mark_planned_candidate_status(user, "blocked", "近期主题过于相似")
            self._clear_pending_proactive_plan(user)
            self._schedule_next_proactive(user, now=now, delay_hours=(2, 6))
            return False, "近期主动主题过于相似"
        if self._planned_event_exceeds_daypart_cap(user, planned_reason, next_at):
            self._clear_pending_proactive_plan(user)
            delay = (7.5, 10.5) if self._proactive_daypart_bucket_for_timestamp(next_at) == "late_night" else (2.5, 5.0)
            self._schedule_next_proactive(user, now=now, delay_hours=delay)
            return False, "当前时段主动已足够,已避开扎堆"
        return True, "ok"

    def _planned_proactive_signature(self, user: dict[str, Any]) -> str:
        return self._proactive_topic_signature(
            user.get("planned_proactive_topic"),
            user.get("planned_proactive_motive"),
            user.get("planned_proactive_source"),
            user.get("planned_proactive_reason"),
        )

    def _planned_proactive_recently_repeated(self, user: dict[str, Any]) -> bool:
        signature = self._planned_proactive_signature(user)
        if not signature:
            return False
        return self._recent_proactive_topic_repeated(user, signature)

    def _mark_planned_candidate_status(self, user: dict[str, Any], status: str, note: str = "") -> None:
        candidate_id = str(user.get("planned_candidate_id") or "")
        if not candidate_id:
            return
        for item in self._cleanup_proactive_candidate_pool():
            if str(item.get("id") or "") == candidate_id:
                item["status"] = status
                item["note"] = _single_line(note, 160)
                item["updated_ts"] = _now_ts()
                break

    def _recover_stale_proactive_sending(self, user: dict[str, Any], *, now: float | None = None) -> bool:
        if not user.get("proactive_sending"):
            return False
        now = now or _now_ts()
        started_at = _safe_float(user.get("proactive_sending_started_at"), 0)
        if started_at > 0 and now - started_at < 8 * 60:
            return False
        user["proactive_sending"] = False
        user["proactive_sending_started_at"] = 0
        logger.warning(
            "[PrivateCompanion] 检测到残留的主动发送标记,已自动清理: user=%s started_at=%s",
            user.get("user_id") or user.get("id") or "unknown",
            datetime.fromtimestamp(started_at).strftime("%m-%d %H:%M:%S") if started_at > 0 else "unknown",
        )
        return True

    def _is_recent_poke_echo(self, user: dict[str, Any], text: str, *, now: float | None = None) -> bool:
        now = now or _now_ts()
        suppress_until = _safe_float(user.get("poke_echo_suppress_until"), 0)
        if suppress_until <= 0 or now > suppress_until:
            return False
        return not bool(_single_line(text, 120))

    def _explain_proactive_decision(self, user: dict[str, Any]) -> str:
        probe = dict(user)
        decision, reason = self._should_send(probe)
        now = _now_ts()
        planned_reason = str(probe.get("planned_proactive_reason") or "")
        planned_action = str(probe.get("planned_proactive_action") or "message")
        planned_source = str(probe.get("planned_proactive_source") or "")
        planned_motive = _single_line(probe.get("planned_proactive_motive"), 48)
        next_at = _safe_float(probe.get("next_proactive_at"), 0)
        timer_event = self._get_active_llm_timer(probe)
        next_at_text = (
            datetime.fromtimestamp(next_at).strftime("%m-%d %H:%M:%S")
            if next_at > 0
            else "未安排"
        )
        sent_today = _safe_int(probe.get("sent_today"), 0)
        sent_greetings = probe.get("greetings_sent")
        if not isinstance(sent_greetings, list):
            sent_greetings = []
        suppressed_greetings = probe.get("greetings_suppressed_by_inbound")
        if not isinstance(suppressed_greetings, list):
            suppressed_greetings = []
        last_seen_at = _safe_float(probe.get("last_seen"), 0)
        last_sent_at = _safe_float(probe.get("last_sent"), 0)
        last_seen_gap = now - last_seen_at if last_seen_at > 0 else -1
        last_sent_gap = now - last_sent_at if last_sent_at > 0 else -1
        idle_limit = (
            self.greeting_idle_minutes * 60
            if self._is_greeting_reason(planned_reason)
            else self.idle_minutes * 60
        )
        min_interval = self._effective_min_interval_seconds(probe)
        if self._is_greeting_reason(planned_reason):
            min_interval = min(min_interval, self._greeting_min_interval_seconds(planned_reason))
        reason_allowed = self._is_reason_allowed_now(planned_reason)
        moment_ok = True
        if reason == "未到候选主动时间":
            reason_allowed_text = "到点后再检查"
            moment_ok_text = "到点后再检查"
        else:
            reason_allowed_text = "通过" if reason_allowed else "不适合"
            moment_ok_text = "候选到点即发送"
        lines = [
            f"主动判定：{'会发送' if decision else '这次不发'}",
            f"原因：{reason}",
            f"下次候选：{next_at_text}",
            f"计划：{planned_reason or '未记录'}｜{planned_action}"
            + (f"｜计划源：{planned_source}" if planned_source else "")
            + (f"｜话题：{_single_line(probe.get('planned_proactive_topic'), 24)}" if _single_line(probe.get("planned_proactive_topic"), 24) else "")
            + (f"｜动机：{planned_motive}" if planned_motive else "")
            + (f"｜来源：模型预约" if isinstance(timer_event, dict) and _safe_float(timer_event.get("scheduled_ts"), 0) == next_at else ""),
            f"今日已发：{sent_today}/{self.max_daily_messages}｜软目标约 {self._soft_daily_target(probe):.1f}",
            f"今日问候：已发 {', '.join(str(item) for item in sent_greetings) or '无'}｜被用户消息跳过 {', '.join(str(item) for item in suppressed_greetings) or '无'}",
            f"免打扰：{'是' if self._is_quiet_time() else '否'}｜失眠特例：{'可用' if self._can_send_insomnia_night_message(probe) else '不可用'}",
            f"距用户上次活跃：{self._format_elapsed(max(0, last_seen_gap)) if last_seen_gap >= 0 else '从未'}｜要求至少 {self._format_elapsed(idle_limit)}",
            f"距上次主动：{self._format_elapsed(max(0, last_sent_gap)) if last_sent_gap >= 0 else '从未'}｜要求至少 {self._format_elapsed(min_interval)}",
            f"时间窗适配：{reason_allowed_text}｜自然动机：{moment_ok_text}",
        ]
        return "\n".join(lines)

    def _simulation_active(self, user: dict[str, Any]) -> bool:
        raw = user.get("simulation_mode")
        return isinstance(raw, dict) and bool(raw.get("active"))

    def _simulation_label(self, user: dict[str, Any]) -> str:
        raw = user.get("simulation_mode")
        if isinstance(raw, dict):
            label = _single_line(raw.get("label"), 24)
            if label:
                return label
        return "压缩测试"

    def _should_send_simulation(self, user: dict[str, Any]) -> tuple[bool, str]:
        sim = user.get("simulation_mode")
        if not isinstance(sim, dict) or not sim.get("active"):
            return False, "未处于模拟模式"
        now = _now_ts()
        self._sync_simulation_next_event(user, now=now)
        next_at = _safe_float(user.get("next_proactive_at"), 0)
        label = self._simulation_label(user)
        if next_at <= 0:
            self._finish_simulation_mode(user)
            return False, f"{label}已结束"
        if now < next_at:
            return False, f"{label}等待下一条主动消息"
        return True, "simulation"

    def _sync_simulation_next_event(self, user: dict[str, Any], *, now: float | None = None) -> None:
        sim = user.get("simulation_mode")
        if not isinstance(sim, dict):
            return
        events = sim.get("events")
        if not isinstance(events, list) or not events:
            self._finish_simulation_mode(user)
            return
        now = now or _now_ts()
        remaining = [event for event in events if isinstance(event, dict)]
        if not remaining:
            self._finish_simulation_mode(user)
            return
        remaining.sort(key=lambda item: _safe_float(item.get("_scheduled_ts"), now))
        sim["events"] = remaining
        current = remaining[0]
        user["next_proactive_at"] = _safe_float(current.get("_scheduled_ts"), now)
        user["planned_proactive_reason"] = str(current.get("reason") or "check_in")
        user["planned_proactive_action"] = str(current.get("action") or "message")
        user["planned_proactive_source"] = "simulation"
        user["planned_proactive_motive"] = _single_line(current.get("motive"), 140)
        user["planned_proactive_topic"] = _single_line(current.get("topic"), 60)
        user["planned_event_chain"] = list(current.get("chain") or []) if isinstance(current.get("chain"), list) else []
        user["planned_opener_mode"] = ""
        user["planned_followup_kind"] = ""
        user["planned_proactive_quota_exempt"] = bool(current.get("_free_screen_peek"))

    def _consume_simulation_event(self, user: dict[str, Any]) -> None:
        sim = user.get("simulation_mode")
        if not isinstance(sim, dict):
            return
        events = sim.get("events")
        if not isinstance(events, list) or not events:
            self._finish_simulation_mode(user)
            return
        sim["events"] = [event for event in events[1:] if isinstance(event, dict)]
        sim["sent_count"] = _safe_int(sim.get("sent_count"), 0, 0) + 1
        self._sync_simulation_next_event(user)

    def _finish_simulation_mode(self, user: dict[str, Any]) -> None:
        user["simulation_mode"] = {}
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

    def _available_test_actions(self, user: dict[str, Any]) -> list[str]:
        actions = ["message"]
        if self._screen_glance_available(user):
            actions.append("screen_peek")
        if self._photo_text_available(user):
            actions.append("photo_text")
        if self._voice_available(user):
            actions.append("voice")
        return actions

    def _available_proactive_abilities(self, user: dict[str, Any] | None = None) -> list[dict[str, str]]:
        user = user if isinstance(user, dict) else {}
        available = {"message"}
        if self._screen_glance_available(user):
            available.add("screen_peek")
        if self._photo_text_available(user):
            available.add("photo_text")
        if self._poke_available():
            available.add("poke")
        if self._voice_available(user):
            available.add("voice")
        items: list[dict[str, str]] = []
        for raw in PROACTIVE_ABILITY_REGISTRY:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            if not name or name not in available:
                continue
            items.append({str(key): str(value) for key, value in raw.items()})
        return items

    def _format_proactive_ability_search_hint(self, user: dict[str, Any] | None = None) -> str:
        abilities = self._available_proactive_abilities(user)
        if not abilities:
            return "当前只按普通文字私聊处理。"
        lines = [
            "以下内容只供内部决策,角色本人不感知这些能力名,最终聊天正文也不得提到能力、检索、工具、action 或模块。",
            "先在当前场景里检索主动能力,再选择 action；不要凭空猜一个能力名。",
            "能力按领域分层如下：",
        ]
        for item in abilities:
            lines.append(
                "- {module}/{name}（{label}）：适用={when}；用于={use_for}；避开={avoid}".format(
                    module=_single_line(item.get("module"), 16),
                    name=_single_line(item.get("name"), 24),
                    label=_single_line(item.get("label"), 16),
                    when=_single_line(item.get("when"), 80),
                    use_for=_single_line(item.get("use_for"), 80),
                    avoid=_single_line(item.get("avoid"), 80),
                )
            )
        preference_hint = self._action_preference_hint(user)
        if preference_hint:
            lines.append("【用户媒介偏好】\n" + preference_hint)
        lines.append("选择顺序：先看生活场景是否自然需要媒介,再看依赖是否可用,最后才落到 message。输出时只保留真人会发出的聊天内容。")
        return "\n".join(lines)

    def _format_presence_layer_hint(self) -> str:
        return (
            "状态表现层只在平台侧短暂发生,不属于聊天正文："
            "发普通文字前可以尝试短暂显示“正在输入”,让消息像人慢慢打出来；"
            "QQ 在线/睡觉/自定义状态由当前时间段的细化模型通过 presence_status 决定,执行层只按结果同步一次；"
            "优先用在线或自定义短状态表达生活感,少用忙碌,避免离开、隐身和请勿打扰；"
            "正文里不得提到正在输入、在线状态、状态同步或平台接口。"
        )

    def _format_proactive_ability_list_for_user(self, user: dict[str, Any] | None = None) -> str:
        abilities = self._available_proactive_abilities(user)
        if not abilities:
            return "当前主动能力：文字私聊。"
        lines = ["当前主动能力："]
        for item in abilities:
            lines.append(
                f"- {item.get('module')}/{item.get('name')}：{item.get('label')}｜{item.get('when')}"
            )
        lines.append("- 状态表现/typing_status：发送前短暂显示正在输入｜平台支持时自动尝试,不进聊天正文")
        lines.append("- 状态表现/qq_presence：在线/睡觉/自定义短状态｜平台支持时自动尝试,少用忙碌,避免离开/隐身/请勿打扰")
        return "\n".join(lines)

    def _summarize_test_action_labels(self, actions: list[str]) -> str:
        labels = {
            "message": "文字",
            "screen_peek": "窥屏",
            "photo_text": "发图",
            "poke": "戳一戳",
            "voice": "语音",
        }
        return "、".join(labels.get(action, action) for action in actions)

    def _build_full_test_detail_prompt(
        self,
        segment: dict[str, Any],
        plan: dict[str, Any],
        state: dict[str, Any],
        actions: list[str],
        *,
        missing_actions: list[str] | None = None,
    ) -> str:
        base_prompt = self._build_detail_enhancement_prompt(segment, plan, state)
        action_text = "、".join(actions) if actions else "message"
        extra = [
            "",
            "【这次是临时完整主动链测试】",
            "请只围绕这一段日程生成一串用于真实测试的 proactive_events。",
            "要求它们仍然像正常生活里会长出来的主动消息，不要写成“这是测试”或功能演示。",
            f"这轮测试可用的主动行为有：{action_text}。",
            "请尽量让 proactive_events 覆盖每一种可用行为至少一次；如果某种行为实在不合时宜，也要优先找一个勉强自然的切入点，而不是完全放弃。",
            "这些 proactive_events 之后会被压缩成每两分钟一条真实发送，所以你只需要负责把这一整段里的多个主动契机安排出来。",
            "today_events 仍然保持正常生活感，proactive_events 要像从这段生活里自己长出来。",
            "不要把‘测试’、‘跑满能力’、‘验证功能’写进输出里。",
        ]
        if missing_actions:
            extra.extend(
                [
                    "",
                    "【补正要求】",
                    f"上一轮结果还缺少这些主动行为：{'、'.join(missing_actions)}。",
                    "这一轮请重点补齐缺失行为，同时保持整段仍然像同一个人的连续生活。",
                ]
            )
        return base_prompt + "\n" + "\n".join(extra)

    async def _generate_full_test_detail_enhancement(
        self,
        segment: dict[str, Any],
        plan: dict[str, Any],
        state: dict[str, Any],
        actions: list[str],
    ) -> tuple[dict[str, Any], list[str]]:
        required_actions = [action for action in actions if action in {"message", "screen_peek", "photo_text", "voice"}]
        last_normalized = {
            "summary": "这一段按原日程慢慢推进。",
            "today_events": [],
            "proactive_events": [],
            "long_term_events": [],
        }
        missing_actions = list(required_actions)
        for _ in range(3):
            prompt = self._build_full_test_detail_prompt(
                segment,
                plan,
                state,
                required_actions,
                missing_actions=missing_actions if missing_actions and missing_actions != required_actions else None,
            )
            raw_text = await self._llm_call(
                prompt,
                max_tokens=1000,
                provider_id=self._task_provider(
                    self.detail_enhancement_provider_id,
                    self.daily_plan_provider_id,
                    self.mai_style_provider_id,
                ),
                task="full_test_detail",
            )
            payload = self._extract_json_payload(raw_text or "")
            if not isinstance(payload, dict):
                continue
            normalized = self._normalize_story_plan(
                {
                    "today_events": payload.get("today_events", []),
                    "proactive_events": payload.get("proactive_events", []),
                    "long_term_events": [],
                }
            )
            normalized["summary"] = _single_line(payload.get("summary"), 160)
            last_normalized = normalized
            present = {
                str(item.get("action") or "message")
                for item in normalized.get("proactive_events", [])
                if isinstance(item, dict)
            }
            missing_actions = [action for action in required_actions if action not in present]
            if not missing_actions:
                break
        return last_normalized, missing_actions

    def _build_full_test_events(
        self,
        detail: dict[str, Any],
        *,
        actions: list[str],
        segment: dict[str, Any] | None = None,
        spacing_seconds: int = 120,
    ) -> list[dict[str, Any]]:
        proactive_events = detail.get("proactive_events", []) if isinstance(detail, dict) else []
        if not isinstance(proactive_events, list):
            proactive_events = []
        usable = [dict(item) for item in proactive_events if isinstance(item, dict)]
        segment_start = _safe_int((segment or {}).get("start"), -1)
        segment_end = _safe_int((segment or {}).get("end"), -1)
        if segment_start >= 0 and segment_end > segment_start:
            scoped: list[dict[str, Any]] = []
            for item in usable:
                start, end = self._parse_window_minutes(str(item.get("window") or ""))
                if start is None or end is None:
                    continue
                if start < segment_start or end > segment_end:
                    continue
                scoped.append(item)
            usable = scoped
        required_actions = [action for action in actions if action in {"message", "screen_peek", "photo_text", "voice"}]
        filtered: list[dict[str, Any]] = []
        for action in required_actions:
            matched = next((item for item in usable if str(item.get("action") or "message") == action and item not in filtered), None)
            if matched:
                filtered.append(matched)
        for item in usable:
            action = str(item.get("action") or "message")
            if action in required_actions and item not in filtered:
                filtered.append(item)
        if not filtered:
            filtered = [dict(item) for item in _SIMULATION_FALLBACK_EVENTS]
            for item in filtered:
                item["motive"] = self._normalize_event_motive(item)
        filtered.sort(
            key=lambda item: (
                (self._parse_window_minutes(str(item.get("window") or ""))[0])
                if self._parse_window_minutes(str(item.get("window") or ""))[0] is not None
                else 24 * 60
            )
        )
        start_ts = _now_ts() + 20
        events: list[dict[str, Any]] = []
        for index, item in enumerate(filtered):
            cloned = dict(item)
            cloned["_scheduled_ts"] = start_ts + index * spacing_seconds
            cloned["_simulated_window"] = str(item.get("window") or "")
            events.append(cloned)
        return events

    def _build_single_poke_test_event(
        self,
        *,
        user: dict[str, Any],
        segment: dict[str, Any] | None = None,
        detail: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        item = (segment or {}).get("item") if isinstance(segment, dict) else {}
        item = item if isinstance(item, dict) else {}
        topic = (
            _single_line(((detail or {}).get("proactive_events") or [{}])[0].get("topic"), 60)
            if isinstance((detail or {}).get("proactive_events"), list) and (detail or {}).get("proactive_events")
            else ""
        )
        if not topic:
            topic = _single_line(item.get("activity"), 60) or "刚才那一下"
        motive = self._normalize_internal_motive_text(
            f"关于“{topic}”这一下，手已经比脑子先一步想闹你了"
        )
        window = ""
        if isinstance(segment, dict):
            start = _safe_int(segment.get("start"), -1)
            end = _safe_int(segment.get("end"), -1)
            if start >= 0 and end > start:
                window = f"{self._minutes_to_hhmm(start)}-{self._minutes_to_hhmm(end)}"
        return {
            "window": window,
            "reason": "diary_share",
            "action": "poke",
            "why": _single_line(item.get("activity"), 80) or "突然很想戳你一下",
            "topic": topic,
            "motive": motive,
            "scene": _single_line(((detail or {}).get("summary")), 80) or "眼前这一小段",
            "tone": "轻轻使坏",
            "impulse": "先戳一下，再看看你会不会回头",
            "chain": [],
            "_scheduled_ts": _now_ts() + 3,
            "_simulated_window": window or "立即触发",
        }

    def _schedule_next_proactive(
        self,
        user: dict[str, Any],
        *,
        now: float | None = None,
        delay_hours: tuple[float, float] | None = None,
    ):
        now = now or _now_ts()
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
                user["planned_event_chain"] = (
                    list(timer_event.get("chain") or [])
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
        user["planned_event_chain"] = (
            list(planned_event.get("chain") or [])
            if isinstance(planned_event, dict) and isinstance(planned_event.get("chain"), list)
            else []
        )
        user["planned_opener_mode"] = ""
        user["planned_followup_kind"] = (
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

    def _maybe_upgrade_planned_message_action(
        self,
        action: str,
        *,
        reason: str,
        user: dict[str, Any],
        motive: str = "",
        planned_event: dict[str, Any] | None = None,
    ) -> str:
        normalized = str(action or "message").strip() or "message"
        if normalized != "message":
            return self._fallback_action_for_unavailable(normalized, user)
        if isinstance(planned_event, dict) and planned_event.get("_daily_greeting"):
            return "message"
        candidates: list[tuple[str, float]] = []
        event_text = ""
        if isinstance(planned_event, dict):
            event_text = " ".join(
                _single_line(planned_event.get(key), 80)
                for key in ("topic", "why", "scene", "motive", "impulse")
            )
        combined_hint = f"{event_text} {motive}"
        if self._screen_glance_available(user) and reason in {"check_in", "quiet_care", "background_schedule"}:
            candidates.append(("screen_peek", 1.15))
        if self._photo_text_available(user) and (
            reason in {"activity_share", "diary_share", "background_schedule", "noon_greeting", "evening_greeting"}
            or any(token in combined_hint for token in self._visual_share_tokens())
        ):
            candidates.append(("photo_text", 1.05))
        if self._voice_available(user) and reason in {"quiet_care", "diary_share", "insomnia_night", "evening_greeting"}:
            candidates.append(("voice", 0.82))
        if self._poke_available() and reason in {"check_in", "quiet_care", "morning_greeting", "evening_greeting"}:
            candidates.append(("poke", 0.62))
        if not candidates:
            return "message"
        candidates.append(("message", 0.38))
        return self._fallback_action_for_unavailable(self._weighted_choice(candidates), user)

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
        user["planned_event_chain"] = list(event.get("chain") or []) if isinstance(event.get("chain"), list) else []
        user["planned_opener_mode"] = ""
        user["planned_followup_kind"] = ""
        user["planned_proactive_quota_exempt"] = bool(event.get("_free_screen_peek"))
        return True

    def _pick_best_planned_event(
        self, user: dict[str, Any], now: float | None = None
    ) -> dict[str, Any] | None:
        now = now or _now_ts()
        candidates = []
        for event in (
            self._pick_pending_followup_event(user, now),
            self._pick_daily_greeting_event(user, now),
            self._pick_story_plan_event(now, user=user),
        ):
            if not isinstance(event, dict):
                continue
            reason = str(event.get("reason") or "check_in")
            event_ts = self._timestamp_from_story_event(event, reason)
            if event_ts > now or (event_ts > 0 and now - event_ts <= self.max_proactive_plan_lag_minutes * 60):
                candidates.append((event_ts, event))
        if not candidates:
            return None
        near_sticky = [
            (event_ts, event)
            for event_ts, event in candidates
            if self._is_sticky_greeting_event(event) and 0 < event_ts - now <= 90 * 60
        ]
        if near_sticky:
            near_sticky.sort(key=lambda item: (self._event_priority(item[1]), item[0]))
            return near_sticky[0][1]
        non_sticky = [
            (event_ts, event)
            for event_ts, event in candidates
            if not self._is_sticky_greeting_event(event)
        ]
        if non_sticky:
            non_sticky.sort(key=lambda item: item[0])
            weighted = []
            for index, (_, event) in enumerate(non_sticky[:3]):
                priority_tuple = self._event_priority(event)
                priority_score = float(-priority_tuple[0])
                weighted.append((event, 1.0 + priority_score * 0.05 + max(0.0, 0.35 - index * 0.1)))
            return self._weighted_choice(weighted)
        ranked = sorted(
            candidates,
            key=lambda item: (self._event_priority(item[1]), item[0]),
        )
        top = ranked[:3]
        return random.choice(top)[1]

    @staticmethod
    def _is_sticky_greeting_event(event: dict[str, Any]) -> bool:
        return bool(event.get("_daily_greeting")) and str(event.get("reason") or "") in {
            "morning_greeting",
            "noon_greeting",
            "evening_greeting",
        }

    def _pick_pending_followup_event(
        self, user: dict[str, Any], now: float | None = None
    ) -> dict[str, Any] | None:
        opener_event = self._build_suspended_opener_followup_event(user, now=now)
        if isinstance(opener_event, dict):
            return opener_event
        raw = user.get("pending_followup_event")
        if not isinstance(raw, dict):
            return None
        followup_date = str(raw.get("date") or "")
        if followup_date and followup_date != _today_key():
            return None
        scheduled = _safe_float(raw.get("_scheduled_ts"), 0)
        if scheduled <= 0:
            return None
        if scheduled <= (now or _now_ts()):
            return raw
        return raw

    def _build_suspended_opener_followup_event(
        self,
        user: dict[str, Any],
        *,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        raw = user.get("suspended_proactive")
        if not isinstance(raw, dict) or not raw.get("active"):
            return None
        if not raw.get("complaint_enabled") or raw.get("complaint_sent"):
            return None
        if max(_safe_float(user.get("awaiting_reply_since"), 0), _safe_float(user.get("last_sent"), 0)) <= 0:
            return None
        due_at = _safe_float(raw.get("complaint_after_ts"), 0)
        if due_at <= 0:
            return None
        now = now or _now_ts()
        if now < due_at:
            return None
        name = _single_line(user.get("nickname") or self.default_nickname, 24)
        return {
            "date": _today_key(),
            "window": self._window_from_delay_minutes(4, width_minutes=18),
            "reason": _single_line(raw.get("complaint_reason"), 40) or "check_in",
            "action": "message",
            "why": "之前只轻轻叫了用户一声,隔了挺久以后又想补一小句。",
            "topic": _single_line(raw.get("complaint_topic"), 80) or "刚才叫你的那一下",
            "motive": _single_line(raw.get("complaint_motive"), 100) or f"刚刚只喊了{name}一声,那边还安静着,就想再轻轻放一句",
            "scene": "先前那句没得到回音以后",
            "tone": _single_line(raw.get("complaint_tone"), 30) or "轻一点,不催促",
            "impulse": "隔了一阵又想轻轻续一下,不要求对方立刻回",
            "_scheduled_ts": due_at,
            "_opener_followup": True,
            "_cancel_on_inbound": True,
        }

    def _build_followup_event_from_chain(
        self,
        chain: list[dict[str, Any]] | None,
        *,
        origin_reason: str,
        origin_action: str,
        now_ts: float | None = None,
    ) -> dict[str, Any] | None:
        steps = [dict(step) for step in (chain or []) if isinstance(step, dict)]
        if not steps:
            return None
        current = None
        remaining: list[dict[str, Any]] = []
        consumed_name_only = False
        for step in steps:
            kind = str(step.get("kind") or "")
            if kind == "name_only_opener" and not consumed_name_only:
                consumed_name_only = True
                continue
            if current is None and kind in {"if_no_reply", "if_still_no_reply"}:
                current = step
                continue
            remaining.append(step)
        if not isinstance(current, dict):
            return None
        now_ts = now_ts or _now_ts()
        after_minutes = _safe_int(current.get("after_minutes"), 18, 0, 240)
        follow_reason = _single_line(current.get("reason"), 40) or origin_reason or "check_in"
        if origin_reason == "morning_greeting" or follow_reason == "morning_greeting":
            after_minutes = max(after_minutes, 75)
        topic = _single_line(current.get("topic"), 80) or "刚才那一下的后续"
        motive = self._normalize_internal_motive_text(
            _single_line(current.get("motive"), 100) or "刚才那一下结束之后,心里还有一点话没完全散掉"
        )
        tone = _single_line(current.get("tone"), 30)
        return {
            "date": _today_key(),
            "window": self._window_from_delay_minutes(after_minutes, width_minutes=18),
            "reason": follow_reason,
            "action": "message",
            "why": "前一条主动消息后还留着一点后续,如果用户没回头,就顺着那股劲再续一句。",
            "topic": topic,
            "motive": motive,
            "scene": "前一条主动消息发出去后又过了一阵",
            "tone": "轻一点,不催促" if (origin_reason == "morning_greeting" or follow_reason == "morning_greeting") else (tone or "自然后续"),
            "impulse": "隔了挺久才又想轻轻放一句,不要求对方立刻回" if (origin_reason == "morning_greeting" or follow_reason == "morning_greeting") else "刚才那一下还没完全落下去,所以想再续一句",
            "_scheduled_ts": now_ts + after_minutes * 60,
            "_origin_action": origin_action,
            "_origin_reason": origin_reason,
            "_cancel_on_inbound": True,
            "_chain_followup": True,
            "chain": remaining,
        }

    def _build_simulation_greeting_events(self) -> list[dict[str, Any]]:
        return [
            {
                "window": "08:15-10:10",
                "reason": "morning_greeting",
                "action": "message",
                "why": "早上醒来后想打个招呼",
                "topic": "早安",
                "scene": "一天刚开机的时候",
                "tone": "还没完全醒",
                "impulse": "想先把第一句轻轻放到你这边",
            },
            {
                "window": "12:05-13:35",
                "reason": "noon_greeting",
                "action": "message",
                "why": "午休或午饭时想起用户",
                "topic": "午后晃一下",
                "scene": "白天正中间松下来的一小段",
                "tone": "懒洋洋",
                "impulse": "想顺手晃到你这边一下",
            },
            {
                "window": "20:10-21:20",
                "reason": "evening_greeting",
                "action": "message",
                "why": "晚间刚慢下来时轻轻问候一下",
                "topic": "晚间来一下",
                "scene": "晚上节奏刚慢下来的时候",
                "tone": "安静",
                "impulse": "想趁还没太晚先轻轻碰你一下",
            },
        ]

    def _build_simulation_events(self, user: dict[str, Any], *, duration_minutes: int = 60) -> list[dict[str, Any]]:
        plan = self.data.get("daily_story_plan", {})
        story_events = plan.get("proactive_events", []) if isinstance(plan, dict) else []
        candidates: list[dict[str, Any]] = []
        if isinstance(story_events, list):
            candidates.extend(event for event in story_events if isinstance(event, dict))
        candidates.extend(self._build_simulation_greeting_events())
        deduped = self._dedupe_proactive_events(candidates)
        ranked = sorted(
            deduped,
            key=lambda item: self._event_priority(item),
        )
        base_target = max(3, min(8, int(round(max(2.0, self._soft_daily_target(user) + 1.2)))))
        selected: list[dict[str, Any]] = []
        used_buckets: set[str] = set()
        for item in ranked:
            bucket = self._simulation_event_bucket(item)
            if bucket in used_buckets:
                continue
            selected.append(item)
            used_buckets.add(bucket)
            if len(selected) >= base_target:
                break
        if not selected:
            selected = [dict(item) for item in _SIMULATION_FALLBACK_EVENTS]
        selected = [dict(item) for item in selected]
        for item in selected:
            item["motive"] = self._normalize_event_motive(item)
        start_ts = _now_ts() + 30
        total = len(selected)
        if total == 1:
            schedule_points = [start_ts + 120]
        else:
            last_ts = start_ts + max(18 * 60, duration_minutes * 60 - 120)
            schedule_points = []
            for index in range(total):
                ratio = index / max(1, total - 1)
                base = start_ts + (last_ts - start_ts) * ratio
                jitter = random.uniform(-70, 95)
                schedule_points.append(max(start_ts + index * 70, base + jitter))
            schedule_points.sort()
        events: list[dict[str, Any]] = []
        for item, scheduled in zip(selected, schedule_points):
            cloned = dict(item)
            cloned["_scheduled_ts"] = scheduled
            cloned["_simulated_window"] = str(item.get("window") or "")
            events.append(cloned)
        return events

    def _simulation_event_bucket(self, item: dict[str, Any]) -> str:
        reason = str(item.get("reason") or "")
        if reason in {"morning_greeting", "noon_greeting", "evening_greeting"}:
            return reason
        window = str(item.get("window") or "")
        start, _ = self._parse_window_minutes(window)
        if start is None:
            return f"{reason}|misc"
        if start < 11 * 60:
            daypart = "morning"
        elif start < 15 * 60:
            daypart = "noon"
        elif start < 19 * 60:
            daypart = "evening"
        else:
            daypart = "night"
        topic = _single_line(item.get("topic"), 30)
        return f"{reason}|{daypart}|{topic}"

    def _pick_daily_greeting_event(
        self, user: dict[str, Any], now: float | None = None
    ) -> dict[str, Any] | None:
        if not self.enable_daily_greetings:
            return None
        self._reset_daily_counter_if_needed(user)
        sent = user.get("greetings_sent", [])
        if not isinstance(sent, list):
            sent = []
            user["greetings_sent"] = sent
        suppressed = user.get("greetings_suppressed_by_inbound", [])
        if not isinstance(suppressed, list):
            suppressed = []
            user["greetings_suppressed_by_inbound"] = suppressed
        now_dt = datetime.fromtimestamp(now or _now_ts())
        minute = now_dt.hour * 60 + now_dt.minute
        anchors = [
            ("morning_greeting", "07:45-10:20", "早上醒来后想打个招呼"),
            ("noon_greeting", "12:05-13:35", "午休或午饭时想起用户"),
            ("evening_greeting", "20:10-21:20", "晚间刚慢下来时轻轻问候一下"),
        ]
        today = now_dt.date()
        candidates = []
        for reason, window, why in anchors:
            if reason in sent or reason in suppressed:
                continue
            start, end = self._parse_window_minutes(window)
            if start is None or end is None:
                continue
            if minute >= end:
                continue
            start_dt = datetime.combine(today, datetime.min.time()) + timedelta(minutes=start)
            end_dt = datetime.combine(today, datetime.min.time()) + timedelta(minutes=end)
            earliest = max(now_dt + timedelta(minutes=1), start_dt)
            if earliest >= end_dt:
                continue
            if reason == "morning_greeting":
                scheduled = random.uniform(earliest.timestamp(), end_dt.timestamp())
            elif reason == "evening_greeting":
                tighten_end = min(end_dt.timestamp(), (earliest + timedelta(minutes=48)).timestamp())
                scheduled = random.uniform(earliest.timestamp(), max(earliest.timestamp() + 60, tighten_end))
            else:
                scheduled = random.uniform(earliest.timestamp(), end_dt.timestamp())
            candidates.append(
                (
                    scheduled,
                    {
                        "window": window,
                        "reason": reason,
                        "action": "message",
                        "_daily_greeting": True,
                        "why": why,
                        "topic": why,
                        "_scheduled_ts": scheduled,
                    },
                )
            )
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _pick_story_plan_event(
        self,
        now: float | None = None,
        *,
        user: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        plan = self.data.get("daily_story_plan", {})
        if not isinstance(plan, dict) or not self._is_plan_date_active(plan.get("date")):
            return None
        events = plan.get("proactive_events", [])
        if not isinstance(events, list):
            return None
        now = now or _now_ts()
        future_events = []
        for event in events:
            if not isinstance(event, dict):
                continue
            event_ts = self._timestamp_from_story_event(event, str(event.get("reason") or "check_in"))
            if event_ts > now or (event_ts > 0 and now - event_ts <= self.max_proactive_plan_lag_minutes * 60):
                future_events.append((event_ts, event))
        if not future_events:
            return None
        future_events.sort(key=lambda item: item[0])
        shortlist = future_events[:6]
        weighted: list[tuple[dict[str, Any], float]] = []
        daypart_counts = self._today_proactive_daypart_counts(user or {})
        for index, (_, event) in enumerate(shortlist):
            priority_tuple = self._event_priority(event)
            priority_score = float(-priority_tuple[0])
            weight = 1.0 + priority_score * 0.08 + max(0.0, 0.45 - index * 0.06)
            bucket = self._proactive_daypart_bucket_for_event(event)
            sent_in_bucket = _safe_int(daypart_counts.get(bucket), 0, 0) if bucket else 0
            if bucket == "late_night" and sent_in_bucket >= 1 and not self._is_sticky_greeting_event(event):
                continue
            if bucket and sent_in_bucket >= 2 and not self._is_sticky_greeting_event(event):
                continue
            if sent_in_bucket > 0:
                weight *= max(0.22, 0.56 ** sent_in_bucket)
            if bucket == "late_night":
                weight *= 0.72
            weighted.append((event, weight))
        if not weighted and shortlist:
            for _, event in shortlist:
                if self._is_sticky_greeting_event(event):
                    weighted.append((event, 1.0))
                    break
        if not weighted:
            return None
        return self._weighted_choice(weighted)

    def _today_proactive_daypart_counts(self, user: dict[str, Any]) -> dict[str, int]:
        if not isinstance(user, dict):
            return {}
        self._reset_daily_counter_if_needed(user)
        raw = user.get("proactive_daypart_counts")
        if not isinstance(raw, dict):
            raw = {}
            user["proactive_daypart_counts"] = raw
        counts: dict[str, int] = {}
        for key, value in raw.items():
            text_key = str(key or "")
            if text_key:
                counts[text_key] = _safe_int(value, 0, 0)
        return counts

    def _proactive_daypart_bucket_for_event(self, event: dict[str, Any]) -> str:
        reason = str(event.get("reason") or "check_in")
        event_ts = self._timestamp_from_story_event(event, reason)
        if event_ts <= 0:
            start, _ = self._parse_window_minutes(str(event.get("window") or ""))
            if start is None:
                return ""
            minute = start
        else:
            when = datetime.fromtimestamp(event_ts)
            minute = when.hour * 60 + when.minute
        return self._proactive_daypart_bucket_for_minute(minute)

    def _proactive_daypart_bucket_for_timestamp(self, timestamp: float) -> str:
        if timestamp <= 0:
            return ""
        when = datetime.fromtimestamp(timestamp)
        return self._proactive_daypart_bucket_for_minute(when.hour * 60 + when.minute)

    def _planned_event_exceeds_daypart_cap(self, user: dict[str, Any], reason: str, scheduled_at: float) -> bool:
        if reason in {"insomnia_night", "important_date_share"}:
            return False
        bucket = self._proactive_daypart_bucket_for_timestamp(scheduled_at)
        if not bucket:
            return False
        counts = self._today_proactive_daypart_counts(user)
        sent_in_bucket = _safe_int(counts.get(bucket), 0, 0)
        if bucket == "late_night":
            return sent_in_bucket >= 1
        return sent_in_bucket >= 2

    @staticmethod
    def _proactive_daypart_bucket_for_minute(minute: int) -> str:
        if minute < 11 * 60:
            return "morning"
        if minute < 14 * 60 + 30:
            return "noon"
        if minute < 18 * 60:
            return "afternoon"
        if minute < 21 * 60:
            return "evening"
        return "late_night"

    def _note_proactive_daypart_sent(self, user: dict[str, Any], sent_at: float | None = None) -> None:
        self._reset_daily_counter_if_needed(user)
        when = datetime.fromtimestamp(sent_at or _now_ts())
        bucket = self._proactive_daypart_bucket_for_minute(when.hour * 60 + when.minute)
        raw = user.setdefault("proactive_daypart_counts", {})
        if not isinstance(raw, dict):
            raw = {}
            user["proactive_daypart_counts"] = raw
        raw[bucket] = _safe_int(raw.get(bucket), 0, 0) + 1

    def _event_priority(self, event: dict[str, Any]) -> tuple[int, float]:
        reason = str(event.get("reason") or "")
        action = str(event.get("action") or "")
        topic = _single_line(event.get("topic"), 40)
        window = str(event.get("window") or "")
        start, _ = self._parse_window_minutes(window)
        start_minutes = start if start is not None else 24 * 60
        priority = 0
        if reason == "morning_greeting":
            priority += 42 if self._is_sticky_greeting_event(event) else 10
        elif reason == "important_date_share":
            priority += 20
        elif reason == "noon_greeting":
            priority += 38 if self._is_sticky_greeting_event(event) else 10
        elif reason == "evening_greeting":
            priority += 28 if self._is_sticky_greeting_event(event) else 6
        elif reason in {"quiet_care", "state_share"}:
            priority += 12
        if action in {"poke", "voice"}:
            priority += 2
        if any(token in topic for token in ("早安", "起床", "赖床", "闹钟")):
            priority += 8
        return (-priority, start_minutes)

    def _note_action_sent(self, user: dict[str, Any], action: str) -> None:
        raw = user.setdefault("action_reply_affinity", {})
        if not isinstance(raw, dict):
            raw = {}
            user["action_reply_affinity"] = raw
        today = datetime.now().strftime("%Y-%m-%d")
        for part in [item.strip() for item in str(action or "message").split("+") if item.strip()]:
            if part == "message":
                continue
            stats = raw.setdefault(part, {"sent": 0, "replied": 0})
            if not isinstance(stats, dict):
                stats = {"sent": 0, "replied": 0}
                raw[part] = stats
            stats["sent"] = _safe_int(stats.get("sent"), 0, 0) + 1
            if part == "photo_text":
                photo_sent_day = str(user.get("photo_sent_day") or "")
                if photo_sent_day != today:
                    user["photo_sent_day"] = today
                    user["photo_sent_today"] = 1
                else:
                    user["photo_sent_today"] = _safe_int(user.get("photo_sent_today"), 0) + 1

    def _note_photo_generation_attempt(self, user_id: str, image_path: str = "") -> None:
        if not str(user_id or "").strip():
            return
        today = _today_key()
        user = self._get_user(str(user_id or ""))
        if user.get("photo_generated_day") != today:
            user["photo_generated_day"] = today
            user["photo_generated_today"] = 0
        user["photo_generated_today"] = _safe_int(user.get("photo_generated_today"), 0) + 1
        user["last_generated_photo_path"] = _single_line(image_path, 260)
        user["last_generated_photo_at"] = _now_ts()

    def _note_screen_peek_attempt(self, user_id: str, reason: str = "", *, count_daily: bool = True) -> None:
        if not str(user_id or "").strip():
            return
        today = _today_key()
        user = self._get_user(str(user_id or ""))
        if user.get("screen_peek_day") != today:
            user["screen_peek_day"] = today
            user["screen_peek_today"] = 0
        if count_daily:
            user["screen_peek_today"] = _safe_int(user.get("screen_peek_today"), 0) + 1
        user["screen_peek_last_at"] = _now_ts()
        user["last_screen_peek_reason"] = _single_line(reason, 120)
        if not count_daily:
            user["last_unanswered_screen_peek_at"] = _now_ts()

    def _note_action_reply_feedback(self, user: dict[str, Any], action: str) -> None:
        raw = user.setdefault("action_reply_affinity", {})
        if not isinstance(raw, dict):
            raw = {}
            user["action_reply_affinity"] = raw
        for part in [item.strip() for item in str(action or "message").split("+") if item.strip()]:
            if part == "message":
                continue
            stats = raw.setdefault(part, {"sent": 0, "replied": 0})
            if not isinstance(stats, dict):
                stats = {"sent": 0, "replied": 0}
                raw[part] = stats
            stats["replied"] = _safe_int(stats.get("replied"), 0, 0) + 1

    def _maybe_make_followup_event(self, user: dict[str, Any], reason: str, action: str) -> dict[str, Any] | None:
        if _safe_int(user.get("sent_today"), 0) >= max(0, self.max_daily_messages - 1):
            return None
        if action not in {"photo_text", "poke", "voice", "screen_peek"} and "+" not in action:
            return None
        chance = 0.12
        if "voice" in action:
            chance += 0.06
        if "photo_text" in action:
            chance += 0.05
        if "poke" in action:
            chance += 0.03
        if random.random() > chance:
            return None
        delay_minutes = random.randint(22, 95)
        follow_reason = "check_in" if action in {"poke", "screen_peek"} else "diary_share"
        topic = {
            "photo_text": "刚才那张图的余波",
            "poke": "刚才那一下之后",
            "voice": "刚刚那句语音之后",
            "screen_peek": "刚才看你忙完没有",
        }.get(action.split("+")[0], "刚刚那一下之后")
        motive = {
            "photo_text": "发出去之后又想了一下,还是觉得那一下挺像你",
            "poke": "刚才碰完你一下之后,后知后觉又想补一句",
            "voice": "那句语音放出去以后,心里还有一点没散掉",
            "screen_peek": "刚刚瞄完你一眼之后,还是有点想知道你后来怎样",
        }.get(action.split("+")[0], "刚才那点念头还没完全散掉")
        return {
            "date": _today_key(),
            "window": self._window_from_delay_minutes(delay_minutes, width_minutes=26),
            "reason": follow_reason,
            "action": "message",
            "why": "上一条主动消息之后还留了一点自然的后续念头。",
            "topic": topic,
            "motive": motive,
            "scene": "上一条主动消息发出去之后",
            "tone": "还没完全散掉",
            "impulse": "刚才那一下结束以后,心里还有一点尾巴想轻轻续上",
            "_scheduled_ts": _now_ts() + delay_minutes * 60,
            "_origin_action": action,
            "_origin_reason": reason,
            "_cancel_on_inbound": True,
        }

    def _bot_currently_bored_for_unanswered_peek(self, user: dict[str, Any]) -> bool:
        text_parts = [
            user.get("last_proactive_reason"),
            user.get("last_proactive_action"),
            user.get("last_proactive_motive"),
            user.get("planned_proactive_reason"),
            user.get("planned_proactive_motive"),
        ]
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        if isinstance(current_item, dict):
            text_parts.extend(
                [
                    current_item.get("activity"),
                    current_item.get("mood"),
                    current_item.get("message_seed"),
                ]
            )
        snapshot = self._current_story_plan_snapshot()
        if isinstance(snapshot, dict):
            text_parts.extend(snapshot.values())
        text = " ".join(_single_line(part, 80) for part in text_parts if part)
        bored_tokens = (
            "无聊", "发呆", "摸鱼", "闲", "空", "没事", "百无聊赖", "松下来",
            "喘口气", "空档", "空隙", "刷视频", "短视频", "休息",
        )
        if any(token in text for token in bored_tokens):
            return True
        reason = str(user.get("last_proactive_reason") or user.get("planned_proactive_reason") or "")
        return reason in {"check_in", "quiet_care", "background_schedule"} and _safe_int(user.get("ignored_streak"), 0) >= 1

    def _maybe_make_unanswered_screen_peek_event(
        self,
        user: dict[str, Any],
        reason: str,
        action: str,
    ) -> dict[str, Any] | None:
        if not self.enable_unanswered_screen_peek_followup:
            return None
        if "screen_peek" in str(action or ""):
            return None
        if not self._screen_glance_available(user, ignore_daily_limit=True):
            return None
        now = _now_ts()
        cooldown = max(30, self.unanswered_screen_peek_cooldown_minutes) * 60
        last_at = _safe_float(user.get("last_unanswered_screen_peek_at"), 0)
        if last_at > 0 and now - last_at < cooldown:
            return None
        if not self._bot_currently_bored_for_unanswered_peek(user):
            return None
        delay_minutes = max(10, self.unanswered_screen_peek_after_minutes)
        return {
            "date": _today_key(),
            "window": self._window_from_delay_minutes(delay_minutes, width_minutes=18),
            "reason": "check_in",
            "action": "screen_peek",
            "why": "上一条主动消息发出去后很久没有回音,又刚好有点无聊,想确认用户现在在做什么。",
            "topic": "你这会儿在干嘛",
            "motive": "刚才主动找你之后那边一直安静着,我又有点闲下来,就想偷偷看一眼你在忙什么",
            "scene": "上一条主动消息之后的安静空档",
            "tone": "小心又好奇",
            "impulse": "不想连着催你,但有点好奇你是不是正在忙",
            "_scheduled_ts": now + delay_minutes * 60,
            "_cancel_on_inbound": True,
            "_unanswered_screen_peek": True,
            "_free_screen_peek": True,
            "_origin_action": action,
            "_origin_reason": reason,
        }

    def _window_from_delay_minutes(self, delay_minutes: int, width_minutes: int = 24) -> str:
        start_dt = datetime.fromtimestamp(_now_ts() + max(5, delay_minutes) * 60)
        end_dt = start_dt + timedelta(minutes=max(12, width_minutes))
        return f"{start_dt.strftime('%H:%M')}-{end_dt.strftime('%H:%M')}"

    def _timestamp_from_story_event(self, event: dict[str, Any], reason: str) -> float:
        scheduled_ts = _safe_float(event.get("_scheduled_ts"), 0)
        if scheduled_ts > 0:
            return scheduled_ts
        window = str(event.get("window") or "").strip()
        match = re.fullmatch(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", window)
        now_dt = datetime.now()
        today = now_dt.date()
        if match:
            sh, sm, eh, em = [int(part) for part in match.groups()]
            start = datetime.combine(today, datetime.min.time()).replace(hour=sh % 24, minute=sm)
            end = datetime.combine(today, datetime.min.time()).replace(hour=eh % 24, minute=em)
            if end <= start:
                end = end + timedelta(days=1)
            if now_dt >= end:
                return 0
            earliest = max(start.timestamp(), (now_dt + timedelta(seconds=45)).timestamp())
            latest = end.timestamp()
            if earliest >= latest:
                return 0
            scheduled = random.uniform(earliest, latest)
            event["_scheduled_ts"] = scheduled
            return scheduled
        scheduled = self._move_timestamp_into_reason_window(_now_ts() + random.uniform(2 * 3600, 10 * 3600), reason)
        event["_scheduled_ts"] = scheduled
        return scheduled

    def _parse_window_minutes(self, window: str) -> tuple[int | None, int | None]:
        normalized = (
            str(window or "")
            .replace("：", ":")
            .replace("—", "-")
            .replace("–", "-")
            .replace("－", "-")
            .replace("~", "-")
            .replace("～", "-")
            .replace("至", "-")
            .replace("到", "-")
        )
        match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*", normalized)
        if not match:
            return None, None
        sh, sm, eh, em = [int(part) for part in match.groups()]
        start = (sh % 24) * 60 + sm
        end = (eh % 24) * 60 + em
        if end <= start:
            end += 24 * 60
        return start, end

    def _choose_planned_reason(self) -> str:
        state = self.data.get("daily_state", {})
        can_do = self.data.get("can_do", [])
        diaries = self.data.get("bot_diaries", [])
        important_dates = self._get_relevant_important_dates()
        users = self.data.get("users", {})
        has_recent_user_message = False
        if isinstance(users, dict):
            for raw_user in users.values():
                if not isinstance(raw_user, dict):
                    continue
                if _single_line(raw_user.get("last_user_message"), 24):
                    has_recent_user_message = True
                    break
        reasons = ["activity_share", "activity_share", "diary_share", "check_in"]
        if self._has_active_insomnia_state():
            reasons.extend(["insomnia_night"] * 2)
        if isinstance(state, dict) and state.get("conditions"):
            reasons.extend(["quiet_care", "check_in"])
        if isinstance(can_do, list) and can_do:
            reasons.extend(["activity_share"] * 3)
        if isinstance(diaries, list) and diaries:
            reasons.extend(["diary_share"] * 2)
        if important_dates:
            reasons.extend(["important_date_share"] * 2)
        if self.include_schedule_in_messages:
            reasons.extend(["background_schedule"] * 2)
        state_note = _single_line(state.get("note"), 80) if isinstance(state, dict) else ""
        state_mood = _single_line(state.get("mood_bias"), 20) if isinstance(state, dict) else ""
        if any(token in state_note for token in ("疲惫", "收声", "安静", "慢一点")) or state_mood in {"安静", "疲惫"}:
            reasons.extend(["quiet_care"])
        if has_recent_user_message:
            reasons.extend(["quiet_care", "check_in"])
        return random.choice(reasons)

    def _is_greeting_reason(self, reason: str) -> bool:
        return reason in {"morning_greeting", "noon_greeting", "evening_greeting"}

    def _is_sticky_greeting_reason(self, reason: str) -> bool:
        return reason in {"morning_greeting", "noon_greeting", "evening_greeting"}

    def _greeting_min_interval_seconds(self, reason: str) -> int:
        if reason == "morning_greeting":
            return 45 * 60
        if reason == "evening_greeting":
            return 60 * 60
        if reason == "noon_greeting":
            return 60 * 60
        return 120 * 60

    def _reschedule_greeting_within_window(
        self,
        user: dict[str, Any],
        reason: str,
        *,
        now: float | None = None,
    ) -> bool:
        if not self._is_sticky_greeting_reason(reason):
            return False
        now_dt = datetime.fromtimestamp(now or _now_ts())
        windows = self._reason_windows(reason)
        if not windows:
            return False
        today = now_dt.date()
        for start, end in windows:
            start_dt = datetime.combine(today, datetime.min.time()) + timedelta(minutes=start)
            end_dt = datetime.combine(today, datetime.min.time()) + timedelta(minutes=end)
            if now_dt >= end_dt:
                continue
            earliest = max(now_dt + timedelta(minutes=random.randint(6, 14)), start_dt)
            latest = end_dt - timedelta(minutes=3)
            if earliest >= latest:
                continue
            user["next_proactive_at"] = random.uniform(earliest.timestamp(), latest.timestamp())
            return True
        return False

    def _is_now_in_reason_window(self, reason: str, now: float | None = None) -> bool:
        if not reason:
            return False
        now_dt = datetime.fromtimestamp(now or _now_ts())
        minute_of_day = now_dt.hour * 60 + now_dt.minute
        for start, end in self._reason_windows(reason):
            if start <= minute_of_day <= end:
                return True
        return False

    def _inbound_satisfies_greeting(self, reason: str, *, now: float | None = None) -> bool:
        if not self._is_greeting_reason(reason):
            return False
        now_dt = datetime.fromtimestamp(now or _now_ts())
        minute_of_day = now_dt.hour * 60 + now_dt.minute
        lead_minutes = {
            "morning_greeting": 10,
            "noon_greeting": 10,
            "evening_greeting": 10,
        }.get(reason, 10)
        for start, end in self._reason_windows(reason):
            if start - lead_minutes <= minute_of_day < end:
                return True
        return False

    def _mark_greeting_satisfied_by_inbound(self, user: dict[str, Any], reason: str) -> bool:
        if not self._is_greeting_reason(reason):
            return False
        self._reset_daily_counter_if_needed(user)
        suppressed = user.setdefault("greetings_suppressed_by_inbound", [])
        if not isinstance(suppressed, list):
            suppressed = []
            user["greetings_suppressed_by_inbound"] = suppressed
        if reason in suppressed:
            return False
        suppressed.append(reason)
        return True

    def _cancel_inbound_conflicting_greeting(self, user: dict[str, Any], *, now: float | None = None) -> bool:
        now = now or _now_ts()
        changed = False
        planned_reason = str(user.get("planned_proactive_reason") or "")
        if self._inbound_satisfies_greeting(planned_reason, now=now):
            next_at = _safe_float(user.get("next_proactive_at"), 0)
            if next_at > 0:
                changed = self._mark_greeting_satisfied_by_inbound(user, planned_reason) or changed
                self._clear_pending_proactive_plan(user)
                changed = True
        raw_followup = user.get("pending_followup_event")
        if isinstance(raw_followup, dict):
            if raw_followup.get("_cancel_on_inbound") or raw_followup.get("_chain_followup") or raw_followup.get("_opener_followup"):
                user["pending_followup_event"] = {}
                changed = True
                return changed
            follow_reason = str(raw_followup.get("reason") or "")
            if self._inbound_satisfies_greeting(follow_reason, now=now):
                changed = self._mark_greeting_satisfied_by_inbound(user, follow_reason) or changed
                user["pending_followup_event"] = {}
                changed = True
        raw_timer = user.get("llm_timer_event")
        if isinstance(raw_timer, dict):
            timer_reason = str(raw_timer.get("reason") or "")
            if self._inbound_satisfies_greeting(timer_reason, now=now):
                changed = self._mark_greeting_satisfied_by_inbound(user, timer_reason) or changed
                user["llm_timer_event"] = {}
                changed = True
        return changed

    def _parse_action_list(self, raw: Any) -> set[str]:
        if raw is None:
            return set()
        if isinstance(raw, str):
            parts = re.split(r"[,\s,、;；]+", raw)
        elif isinstance(raw, list):
            parts = raw
        else:
            parts = []
        return {str(part).strip() for part in parts if str(part).strip()}

    def _visual_share_tokens(self) -> tuple[str, ...]:
        # Broad visual anchors only. Specific subjects should be chosen by the model from context.
        return (
            "看", "拍", "图", "照片", "画面", "颜色", "形状", "光", "影", "反光",
            "桌", "纸", "书", "本", "笔", "杯", "饭", "饮", "路", "窗", "镜",
            "小物", "随手", "涂", "画", "包装", "屏幕", "边角",
        )

    def _pick_life_thought_topic(self, reason: str = "") -> str:
        if reason == "group_share":
            return "群里刚刚那个片段"
        if reason == "bili_video_share":
            return "刚刷到的 B 站视频"
        if reason == "creative_share":
            return "刚写到的小说片段"
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        activity = _single_line((current_item or {}).get("activity"), 36)
        if activity:
            return f"{activity}里自然冒出来的小内容"
        if reason == "diary_share":
            return "今天记录里值得顺手递过去的一小段"
        return "当前时段里自然冒出来的小内容"

    def _format_content_choice_options_for_prompt(self) -> str:
        return (
            "给模型的内容选择菜单,只供内部挑选,不要把类别名写进正文：\n"
            "- 眼前物：从当前日程里的桌边、手边、路上、食物、衣物、门口、杯沿、包装、车窗、书页边缘等具体物件里自选一个。\n"
            "- 脑内念头：一句突然冒出来的短想法、吐槽、联想或没头没尾的小结论。\n"
            "- 输入残留：上一轮聊天留下的余味、没接完的话、想补但没正式补的一点。\n"
            "- 记录碎片：日记、备忘录、作业、阅读/刷到内容里的一小句,或某个没写完的标题。\n"
            "- 可拍画面：任何当前场景里适合顺手拍给熟人的具体画面,不限定天气。\n"
            "- 关系试探：想靠近但不直说的半句、轻轻碰一下、把话放下就走。\n"
            "选择原则：每次只选一个方向,再根据人格、当前时间段、日程和聊天历史生成新的具体内容；避免复用示例词。不要反复使用草稿纸、小画、画圆圈、笔尖划来划去这类廉价重复桥段。"
        )

    def _motive_action_bias(self, motive: str) -> dict[str, float]:
        text = str(motive or "")
        return {
            "screen_peek": 0.32 if any(token in text for token in ("还在忙", "埋进去", "看你", "确认", "忙太久", "偷看一眼")) else 0.0,
            "photo_text": 0.34 if any(token in text for token in ("顺手拍", "拍给你", "发你看", "光", "雨", "窗边", "晚霞", "小猫", "桌上", "一幕", "书页", "食堂", "饮料", "便利店", "影子", "倒影", "杯", "包装", "车窗", "门口")) else 0.0,
            "poke": 0.24 if any(token in text for token in ("戳", "碰你一下", "冒头", "闹你一下", "刷存在感")) else 0.0,
            "voice": 0.3 if any(token in text for token in ("懒得打字", "留句语音", "小声说", "睡不着", "不想敲字")) else 0.0,
        }

    def _soften_topic_hook(self, text: str) -> str:
        cleaned = _single_line(text, 60)
        if not cleaned:
            return ""
        cleaned = re.sub(r"[“”\"'《》<>]", "", cleaned).strip("，,。！？；： ")
        cleaned = re.sub(r"^(?:关于|有关|一种|一些|那个|这段|这一段)", "", cleaned).strip()
        replacements = {
            "劳动节的黄昏": "刚刚那点黄昏天色",
            "夜色温柔": "窗外那点夜色",
            "剧情共鸣": "刚刚那段剧情",
            "剧情吐槽": "刚刚那段也太离谱了",
            "偷看一眼": "你这会儿在干嘛",
            "早晨试探": "刚醒那会儿",
            "面包推荐": "刚咬到的那口面包",
            "路上随手拍": "路上那一下光",
            "念头分享": "刚冒出来的那句话",
            "突然想到": "刚刚突然想到的事",
        }
        if cleaned in replacements:
            return replacements[cleaned]
        if any(token in cleaned for token in ("晚霞", "黄昏", "天色")):
            return "刚刚那点天色"
        if "夜色" in cleaned:
            return "窗外那点夜色"
        if "剧情" in cleaned:
            return "刚刚那段剧情"
        if any(token in cleaned for token in ("雨", "雨声")):
            return "外面那阵雨声"
        if "照片" in cleaned:
            return "刚翻到的那张照片"
        if "风" in cleaned and "吹" not in cleaned:
            return "刚刚那阵风"
        if len(cleaned) <= 10 and not re.search(r"(刚|这|那|窗外|外面|手里|眼前|楼下|路上|桌上|耳边)", cleaned):
            return f"刚刚那点{cleaned}"
        return cleaned

    def _choose_proactive_topic(self, reason: str, user: dict[str, Any]) -> str:
        if reason == "group_share":
            share = user.get("group_share_context") if isinstance(user.get("group_share_context"), dict) else {}
            return _single_line(share.get("topic"), 48) or _single_line(share.get("text"), 48) or "群里刚刚那个片段"
        if reason == "bili_video_share":
            video = user.get("bilibili_video_context") if isinstance(user.get("bilibili_video_context"), dict) else {}
            return _single_line(video.get("title"), 48) or "刚刷到的 B 站视频"
        if reason == "creative_share":
            creative = user.get("creative_share_context") if isinstance(user.get("creative_share_context"), dict) else {}
            return _single_line(creative.get("title"), 48) or "刚写到的小说片段"
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        snapshot = self._current_story_plan_snapshot()
        weather = self._weather_summary_text(self.data.get("daily_weather", {}))
        last_user_message = _single_line(user.get("last_user_message"), 24)
        snapshot_topic = self._soften_topic_hook(snapshot.get("topic")) if isinstance(snapshot, dict) else ""
        if snapshot_topic:
            return snapshot_topic
        snapshot_event = self._soften_topic_hook(snapshot.get("event")) if isinstance(snapshot, dict) else ""
        if snapshot_event:
            return snapshot_event
        if isinstance(current_item, dict):
            activity = _single_line(current_item.get("activity"), 30)
            if activity:
                activity = re.sub(r"[,、]?\s*想起了[^,。]+", "", activity).strip(",。 ")
                activity = re.sub(r"[,、]?\s*突然想到[^,。]+", "", activity).strip(",。 ")
                if activity:
                    return self._soften_topic_hook(activity)
        if reason in {"activity_share", "diary_share"}:
            if random.random() < 0.72:
                return self._pick_life_thought_topic(reason)
            if any(token in weather for token in ("雨", "小雨", "阵雨")):
                return "外面那阵雨声"
            if any(token in weather for token in ("晴", "阳光", "晚霞", "多云")):
                return "刚刚那点天色"
        if reason == "morning_greeting":
            return "刚醒那会儿"
        if reason == "noon_greeting":
            return "中午这会儿有点懒"
        if reason == "evening_greeting":
            return "晚一点的这会儿"
        if reason == "quiet_care" and last_user_message:
            return last_user_message
        return ""

    def _action_affinity_bias(self, user: dict[str, Any] | None = None) -> dict[str, float]:
        base = {"screen_peek": 0.0, "photo_text": 0.0, "poke": 0.0, "voice": 0.0}
        if not isinstance(user, dict):
            return base
        raw = user.get("action_reply_affinity")
        if not isinstance(raw, dict):
            return base
        for action in base:
            stats = raw.get(action)
            if not isinstance(stats, dict):
                continue
            sent = _safe_int(stats.get("sent"), 0, 0)
            replied = _safe_int(stats.get("replied"), 0, 0)
            if sent <= 0:
                continue
            rate = replied / max(1, sent)
            base[action] = max(-0.08, min(0.28, (rate - 0.35) * 0.55))
        return base

    def _screen_glance_available(
        self,
        user: dict[str, Any] | None = None,
        *,
        ignore_daily_limit: bool = False,
    ) -> bool:
        if not self.enable_screen_glance_action:
            return False
        if self.screen_peek_max_daily <= 0 and not ignore_daily_limit:
            return False
        if isinstance(user, dict):
            today = _today_key()
            used_today = (
                _safe_int(user.get("screen_peek_today"), 0)
                if str(user.get("screen_peek_day") or "") == today
                else 0
            )
            if not ignore_daily_limit and used_today >= self.screen_peek_max_daily:
                return False
            cooldown_seconds = max(0, self.screen_peek_cooldown_minutes) * 60
            last_at = _safe_float(user.get("screen_peek_last_at"), 0.0)
            if cooldown_seconds > 0 and last_at > 0 and _now_ts() - last_at < cooldown_seconds:
                return False
        try:
            plugin = self._get_screen_companion_plugin()
            return plugin is not None and callable(getattr(plugin, "_invoke_screen_skill", None))
        except Exception:
            return False

    def _comfyui_photo_available(self) -> bool:
        if not self.enable_photo_text_action:
            return False
        if not self.comfyui_text2img_workflow_name and not self.comfyui_selfie_workflow_name:
            return False
        try:
            module = self._get_comfyui_module()
            return module is not None
        except Exception:
            return False

    def _external_photo_available(self) -> bool:
        if not self.enable_photo_text_action:
            return False
        return bool(
            self.external_image_api_base_url
            and self.external_image_api_key
            and self.external_image_api_model
        )

    def _photo_text_available(self, user: dict[str, Any] | None = None) -> bool:
        if not self.enable_photo_text_action:
            return False
        if self.photo_generation_backend == "comfyui":
            if not self._comfyui_photo_available():
                return False
        elif self.photo_generation_backend == "external":
            if not self._external_photo_available():
                return False
        else:
            if not (self._comfyui_photo_available() or self._external_photo_available()):
                return False
        if user and self.photo_action_max_daily > 0:
            today = datetime.now().strftime("%Y-%m-%d")
            photo_sent_day = str(user.get("photo_sent_day") or "")
            photo_sent_today = _safe_int(user.get("photo_sent_today"), 0)
            photo_generated_day = str(user.get("photo_generated_day") or "")
            photo_generated_today = _safe_int(user.get("photo_generated_today"), 0)
            used_today = max(
                photo_sent_today if photo_sent_day == today else 0,
                photo_generated_today if photo_generated_day == today else 0,
            )
            if used_today >= self.photo_action_max_daily:
                return False
        return True

    def _poke_available(self) -> bool:
        if not self.enable_poke_action:
            return False
        if self._resolve_aiocqhttp_client() is None:
            return False
        try:
            from data.plugins.astrbot_plugin_pokepro.core.send_poke import PokeSender  # noqa: F401
            return True
        except Exception:
            try:
                from astrbot_plugin_pokepro.core.send_poke import PokeSender  # noqa: F401
                return True
            except Exception:
                return False

    def _voice_available(self, user: dict[str, Any] | None = None) -> bool:
        if not self.enable_voice_action:
            return False
        target = ""
        if isinstance(user, dict):
            target = str(user.get("umo") or "").strip()
        if not target:
            return False
        try:
            config = self.context.get_config(target)
        except Exception:
            try:
                config = self.context.get_config()
            except Exception:
                return False
        provider_settings = dict(config.get("provider_tts_settings", {}) or {})
        if not provider_settings.get("enable", False):
            return False
        try:
            return bool(self.context.get_using_tts_provider(target))
        except Exception:
            return False

    def _action_is_available(self, action: str, user: dict[str, Any] | None = None) -> bool:
        normalized = str(action or "message").strip()
        if not normalized or normalized == "message":
            return True
        parts = [part.strip() for part in normalized.split("+") if part.strip()]
        if not parts:
            return True
        screen_quota_exempt = bool(isinstance(user, dict) and user.get("planned_proactive_quota_exempt"))
        for part in parts:
            if part == "screen_peek" and not self._screen_glance_available(user, ignore_daily_limit=screen_quota_exempt):
                return False
            if part == "photo_text" and not self._photo_text_available(user):
                return False
            if part == "poke" and not self._poke_available():
                return False
            if part == "voice" and not self._voice_available(user):
                return False
        return True

    def _fallback_action_for_unavailable(self, action: str, user: dict[str, Any] | None = None) -> str:
        normalized = str(action or "message").strip() or "message"
        if self._action_is_available(normalized, user):
            return normalized
        parts = [part.strip() for part in normalized.split("+") if part.strip()]
        available_parts = [part for part in parts if self._action_is_available(part, user)]
        if not available_parts:
            return "message"
        return "+".join(available_parts)

    def _choose_action_for_reason(
        self,
        reason: str,
        user: dict[str, Any] | None = None,
        motive: str = "",
    ) -> str:
        weather = self._weather_summary_text(self.data.get("daily_weather", {}))
        state = self.data.get("daily_state", {})
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        action_profile = self._persona_action_profile()
        motive_bias = self._motive_action_bias(motive)
        affinity_bias = self._action_affinity_bias(user)

        weighted: list[tuple[str, float]] = [("message", 0.82)]
        if self._screen_glance_available(user) and reason in {"check_in", "quiet_care", "state_share", "background_schedule"}:
            weight = 0.9 + (0.45 if action_profile["observant"] else 0.0) + motive_bias["screen_peek"] + affinity_bias["screen_peek"]
            if energy < 50:
                weight += 0.12
            weighted.append(("screen_peek", weight))
        visual_hint = any(token in motive for token in self._visual_share_tokens())
        if self._photo_text_available(user) and reason in {"activity_share", "diary_share", "background_schedule", "noon_greeting", "evening_greeting"}:
            weight = 0.38 + (0.18 if action_profile["visual"] else 0.0) + motive_bias["photo_text"] * 0.65 + affinity_bias["photo_text"]
            if any(token in weather for token in ("晴", "阳光", "多云", "晚霞", "雨", "阵雨", "小雨")):
                weight += 0.04
            if visual_hint:
                weight += 0.14
            if reason in {"activity_share", "diary_share"}:
                weight += 0.05
            weighted.append(("photo_text", weight))
        if self._poke_available() and reason in {"check_in", "quiet_care", "state_share", "important_date_share", "morning_greeting", "evening_greeting"}:
            weight = 0.38 + motive_bias["poke"] + affinity_bias["poke"]
            if action_profile["playful"]:
                weight += 0.22
            if action_profile["clingy"]:
                weight += 0.12
            weighted.append(("poke", weight))
        if self._voice_available(user) and reason in {"state_share", "diary_share", "insomnia_night", "evening_greeting", "quiet_care"}:
            weight = 0.5 + (0.55 if action_profile["voicey"] else 0.0) + motive_bias["voice"] + affinity_bias["voice"]
            if action_profile["clingy"]:
                weight += 0.2
            if reason == "insomnia_night":
                weight += 0.28
            weighted.append(("voice", weight))

        primary = self._weighted_choice(weighted)
        if primary != "message":
            combined = self._maybe_combine_actions(primary, reason, weather=weather, action_profile=action_profile, user=user)
            if combined:
                return self._fallback_action_for_unavailable(combined, user)
        return self._fallback_action_for_unavailable(primary, user)

    def _choose_proactive_motive(
        self,
        reason: str,
        user: dict[str, Any],
        *,
        action: str = "message",
        planned_event: dict[str, Any] | None = None,
    ) -> str:
        state = self.data.get("daily_state", {})
        weather = self._weather_summary_text(self.data.get("daily_weather", {}))
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        snapshot = self._current_story_plan_snapshot()
        last_user_message = _single_line(user.get("last_user_message"), 48)
        can_do = self.data.get("can_do", [])
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)

        topic = ""
        scene = ""
        tone = ""
        impulse = ""
        event_hint = _single_line(snapshot.get("event"), 60) if isinstance(snapshot, dict) else ""
        summary_hint = _single_line(snapshot.get("summary"), 60) if isinstance(snapshot, dict) else ""
        if isinstance(planned_event, dict):
            topic = self._soften_topic_hook(planned_event.get("topic"))
            scene = _single_line(planned_event.get("scene"), 60)
            tone = _single_line(planned_event.get("tone"), 24)
            impulse = _single_line(planned_event.get("impulse"), 60)
        if not topic and isinstance(snapshot, dict):
            topic = self._soften_topic_hook(snapshot.get("topic") or snapshot.get("event"))
        if not scene and isinstance(snapshot, dict):
            scene = _single_line(snapshot.get("scene"), 60)
        if not tone and isinstance(snapshot, dict):
            tone = _single_line(snapshot.get("tone"), 24)
        if not impulse and isinstance(snapshot, dict):
            impulse = _single_line(snapshot.get("impulse"), 60)
        if not topic and current_item:
            topic = _single_line(current_item.get("title"), 36)
        if not topic and isinstance(can_do, list) and can_do and reason == "activity_share":
            topic = _single_line(random.choice(can_do), 28)
        if not topic:
            topic = self._choose_proactive_topic(reason, user)
        if impulse:
            return self._normalize_internal_motive_text(impulse)
        if scene or tone or event_hint or summary_hint:
            mood_fragment = ""
            if tone in {"安静", "柔和", "松弛", "轻快", "迷糊", "慵懒"}:
                mood_fragment = f",整个人有点{tone}"
            lived_line = ""
            if topic and event_hint:
                lived_line = f"刚刚{event_hint}那一下还没散,脑子里先挂住了“{topic}”{mood_fragment}"
            elif scene and topic:
                lived_line = f"人在{scene}那会儿,心里先擦过去的是“{topic}”{mood_fragment}"
            elif event_hint:
                lived_line = f"刚刚{event_hint}的时候,脑子里先拐到了你这边{mood_fragment}"
            elif scene:
                lived_line = f"刚刚在{scene}那会儿,心里先轻轻晃到了你那边{mood_fragment}"
            elif summary_hint:
                lived_line = f"这一小段安静下来时,脑子里先晃到的是你{mood_fragment}"
            if lived_line:
                return self._normalize_internal_motive_text(lived_line)

        if reason == "insomnia_night":
            motives = [
                "夜里一直没彻底安静下来,想把这点声响轻轻放你这",
                "睡不着,忽然想听见一点和你有关的动静",
                "脑子还亮着,想悄悄丢一句就撤",
            ]
            if action == "voice":
                motives.append("夜里不想敲太多字,想小声给你留一句")
            return random.choice(motives)
        if reason == "state_share":
            motives = [
                "说话可能会慢半拍,想先轻轻叫你一下",
                "有点想收着说话,但还是想碰一下你",
                "这一会儿没那么闹腾,想轻轻问你一句",
            ]
            if energy < 45:
                motives.append("不太想说长句,但想确认你还在")
            return random.choice(motives)
        if reason == "quiet_care":
            motives = [
                "刚刚忽然有点在意你是不是又闷头忙太久了",
                "看见你最近那点状态,还是想让你知道我惦记着",
                "本来想忍着不打扰,最后还是想确认你那边怎么样",
            ]
            if last_user_message:
                motives.append(f"想起你前面提过“{last_user_message}”,就有点放心不下")
            elif topic:
                motives.append(f"刚刚想到“{topic}”的时候,顺手连你那边也一起挂念到了")
            return random.choice(motives)
        if reason == "group_share":
            share = user.get("group_share_context") if isinstance(user.get("group_share_context"), dict) else {}
            group_id = _single_line(share.get("group_id"), 24)
            speaker = _single_line(share.get("speaker"), 24) or "群友"
            text = _single_line(share.get("text"), 70)
            if _single_line(share.get("kind"), 32) == "bot_harassment":
                if text:
                    return self._normalize_internal_motive_text(
                        f"群 {group_id} 里刚刚有人一直闹我,{speaker} 那句“{text}”还挂着,想及时私下跟你说一声"
                    )
                return self._normalize_internal_motive_text(f"群 {group_id} 里刚刚有人一直闹我,想及时私下跟你说一声")
            if text:
                return self._normalize_internal_motive_text(
                    f"群 {group_id} 刚刚有个挺好笑的片段,{speaker} 那句“{text}”还挂着,想私下转给你一下"
                )
            return self._normalize_internal_motive_text("群里刚刚有个挺有意思的片段,想趁还热乎私下跟你说一下")
        if reason == "activity_share":
            motives = [
                "刚刚有个小片段停了一下,心里先冒出的是你",
                "撞见一个小东西时,脑子里先轻轻拐到了你这边",
                "那一下忽然觉得这点东西可以先留给你",
                "脑子里忽然冒出一句没头没尾的话,想先丢给你看看",
                "刚刚那点小想法自己待着有点浪费,就想往你这边放一下",
                "手边的小东西突然变得有点好笑,第一反应是想给你看",
            ]
            if topic:
                motives.append(f"刚碰到“{topic}”时,心里先轻轻动了一下")
            if any(token in weather for token in ("雨", "小雨", "阵雨")):
                motives.append("外面那点雨声落下来的时候,心里先拐到了你这边")
            if any(token in weather for token in ("晴", "阳光", "晚霞")):
                motives.append("光线落下来的那一下,脑子里先闪过了你")
            return random.choice(motives)
        if reason == "diary_share":
            return random.choice([
                "翻到今天记下来的小碎片时,心里先轻轻碰到了你",
                "看到那句今天写下来的话时,第一个想递过去的人还是你",
                "有个今天留下来的边角,停住的时候先想到可以往你那边放一下",
                "有句话不算重要,但留在脑子里晃了几圈,就想给你看看",
                "今天有个小念头像纸屑一样粘着,不丢给你就散不掉",
            ])
        if reason == "important_date_share":
            return random.choice([
                "怕你转头又忘,就先替你记着",
                "今天这个点不提一下,总觉得会被你溜过去",
                "我其实记着这件事,所以先来碰你一下",
            ])
        if reason == "background_schedule":
            motives = [
                "手上的事刚好停了一下,脑子里先晃到了你",
                "忙到一个能喘口气的空当时,顺手就想跟你说一句",
                "眼前这一小段松下来以后,心里先冒出来的是你那边",
            ]
            if topic:
                motives.append(f"手上这点“{topic}”还挂着,顺手就想往你那边递一句")
            return random.choice(motives)
        if reason == "morning_greeting":
            return random.choice([
                "刚醒那一下还有点懵,手先点到你这边了",
                "人还没太清醒,就先想叫你一声",
            ])
        if reason == "noon_greeting":
            return random.choice([
                "中午这会儿人有点懒,就顺手想到你了",
                "午间一下子松下来,就想来找你说一句",
            ])
        if reason == "evening_greeting":
            return random.choice([
                "晚一点安静下来以后,就想来看看你",
                "白天收尾那一下松下来,就想顺手跟你说句话",
            ])
        motives = [
            "刚好停了一下,脑子里先晃到了你这边",
            "眼前这点小事没散掉,就顺手想到可以往你那边递一句",
            "刚松一口气的时候,先冒出来的是你",
        ]
        return self._normalize_internal_motive_text(random.choice(motives))

    def _normalize_internal_motive_text(self, text: str) -> str:
        cleaned = _single_line(text, 80)
        if not cleaned:
            return ""
        replacements = {
            "突然想起你": "刚好想到你",
            "顺手冒了个头": "想跟你说一句",
            "冒个头": "想跟你说一句",
            "冒个泡": "想跟你说一句",
            "刷一下存在感": "想跟你说一句",
            "没什么大道理,就是": "",
            "没什么大不了的,就是": "",
            "顺手晃到你这边了": "想跟你说一句",
            "顺手晃到你这边": "想跟你说一句",
            "一直不理我": "那边还安静着",
            "不理我": "那边还安静着",
            "怎么一点动静都没有": "那边还没什么动静",
            "怎么还没动静": "那边还没什么动静",
            "一点动静都没有": "那边还没什么动静",
        }
        for src, dst in replacements.items():
            cleaned = cleaned.replace(src, dst)
        cleaned = cleaned.replace("忽然想", "有点想")
        cleaned = re.sub(r"(?:来找你一下){2,}", "来找你一下", cleaned)
        cleaned = cleaned.replace("碰你一下", "跟你说一句")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(",。 ")
        return cleaned

    def _should_use_name_only_opener(
        self,
        user: dict[str, Any],
        *,
        reason: str,
        action: str,
        motive: str,
    ) -> bool:
        if action != "message":
            return False
        if str(user.get("planned_followup_kind") or "") == "suspended_opener":
            return False
        chain = user.get("planned_event_chain")
        if isinstance(chain, list) and chain:
            first = chain[0] if isinstance(chain[0], dict) else {}
            if str(first.get("kind") or "") == "name_only_opener":
                return True
        if reason not in {"check_in", "quiet_care", "state_share", "evening_greeting", "insomnia_night"}:
            return False
        if _safe_float(user.get("awaiting_reply_since"), 0) > 0:
            return False
        profile = self._persona_action_profile()
        chance = 0.09
        if reason in {"quiet_care", "evening_greeting", "insomnia_night"}:
            chance += 0.05
        if profile.get("clingy"):
            chance += 0.06
        if profile.get("observant"):
            chance += 0.03
        if profile.get("playful"):
            chance += 0.02
        if any(token in motive for token in ("来找你", "确认一下用户状态", "想和用户说一句", "放心不下", "想看你在不在")):
            chance += 0.05
        return random.random() < min(0.32, chance)

    def _build_name_only_opener(self, name: str) -> str:
        clean_name = _single_line(name, 24) or self.default_nickname
        return f"{clean_name}……"

    def _build_suspended_proactive_payload(
        self,
        *,
        opener_text: str,
        reason: str,
        action: str,
        motive: str,
        action_summary: str,
        chain: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        profile = self._persona_action_profile()
        delay_minutes = random.randint(26, 95)
        complaint_chance = 0.18
        if profile.get("clingy"):
            complaint_chance += 0.16
        if profile.get("playful"):
            complaint_chance += 0.08
        if reason in {"quiet_care", "insomnia_night", "evening_greeting"}:
            complaint_chance += 0.08
        if reason == "morning_greeting":
            delay_minutes = random.randint(80, 150)
            complaint_chance = min(complaint_chance, 0.08)
        chain = list(chain or [])
        no_reply_step = None
        still_no_reply_step = None
        for step in chain:
            if not isinstance(step, dict):
                continue
            kind = str(step.get("kind") or "")
            if kind == "if_no_reply" and no_reply_step is None:
                no_reply_step = step
            elif kind == "if_still_no_reply" and still_no_reply_step is None:
                still_no_reply_step = step
        complaint_after_minutes = _safe_int((no_reply_step or {}).get("after_minutes"), delay_minutes, 0, 240)
        if reason == "morning_greeting":
            complaint_after_minutes = max(complaint_after_minutes, 75)
        return {
            "active": True,
            "resume_ready": False,
            "created_at": _now_ts(),
            "opener_text": _single_line(opener_text, 60),
            "reason": reason,
            "action": action,
            "motive": self._normalize_internal_motive_text(motive),
            "summary": _single_line(action_summary, 60),
            "complaint_enabled": bool(no_reply_step) or random.random() < min(0.55, complaint_chance),
            "complaint_sent": False,
            "complaint_after_ts": _now_ts() + complaint_after_minutes * 60,
            "complaint_reason": _single_line((no_reply_step or {}).get("reason"), 40),
            "complaint_topic": _single_line((no_reply_step or {}).get("topic"), 80),
            "complaint_motive": self._normalize_internal_motive_text(_single_line((no_reply_step or {}).get("motive"), 100)),
            "complaint_tone": "轻一点,不催促" if reason == "morning_greeting" else _single_line((no_reply_step or {}).get("tone"), 30),
            "second_followup": still_no_reply_step if isinstance(still_no_reply_step, dict) else {},
        }

    def _weighted_choice(self, items: list[tuple[str, float]]) -> str:
        filtered = [(name, max(0.0, float(weight))) for name, weight in items if name]
        if not filtered:
            return "message"
        total = sum(weight for _, weight in filtered)
        if total <= 0:
            return filtered[0][0]
        point = random.random() * total
        upto = 0.0
        for name, weight in filtered:
            upto += weight
            if point <= upto:
                return name
        return filtered[-1][0]

    def _maybe_combine_actions(
        self,
        primary: str,
        reason: str,
        *,
        weather: str = "",
        action_profile: dict[str, bool] | None = None,
        user: dict[str, Any] | None = None,
    ) -> str:
        profile = action_profile or self._persona_action_profile()
        candidates: list[tuple[str, float]] = []
        if primary == "photo_text" and self._voice_available(user) and reason in {"activity_share", "diary_share", "background_schedule"}:
            weight = 0.06
            if profile["clingy"] or profile["voicey"]:
                weight += 0.06
            if any(token in weather for token in ("晚霞", "雨", "晴", "阳光")):
                weight += 0.04
            candidates.append(("photo_text+voice", weight))
        if not candidates:
            return primary
        candidates.append((primary, 1.0))
        return self._weighted_choice(candidates)

    def _persona_action_profile(self) -> dict[str, bool]:
        text = str(self._get_default_persona_prompt() or "")
        playful_markers = ("恶作剧", "小恶魔", "腹黑", "俏皮", "捉弄", "欺负", "调皮")
        clingy_markers = ("依赖", "依恋", "特殊的情感", "知心朋友", "关心", "体贴", "想念", "共犯")
        observant_markers = ("看透", "观察", "温柔", "安静", "留意", "敏锐")
        visual_markers = ("自拍", "照片", "景色", "表情包", "外观", "外形", "穿搭", "发型", "发饰")
        voice_markers = ("悄悄说", "口语化", "抽空回复", "亲切感", "温柔", "顺从")
        return {
            "playful": any(marker in text for marker in playful_markers),
            "clingy": any(marker in text for marker in clingy_markers),
            "observant": any(marker in text for marker in observant_markers),
            "visual": any(marker in text for marker in visual_markers),
            "voicey": any(marker in text for marker in voice_markers),
        }

    def _reason_windows(self, reason: str) -> list[tuple[int, int]]:
        return {
            "insomnia_night": [(23 * 60, 24 * 60), (0, 6 * 60)],
            "group_share": [(9 * 60, 23 * 60)],
            "bili_video_share": [(10 * 60, 23 * 60)],
            "creative_share": [(10 * 60, 23 * 60)],
            "state_share": [(8 * 60, 22 * 60 + 30)],
            "quiet_care": [(9 * 60, 22 * 60 + 30)],
            "activity_share": [(10 * 60, 18 * 60 + 30)],
            "diary_share": [(19 * 60, 23 * 60)],
            "important_date_share": [(8 * 60 + 30, 22 * 60)],
            "background_schedule": [(9 * 60, 22 * 60)],
            "check_in": [(9 * 60, 22 * 60 + 30)],
            "morning_greeting": [(7 * 60 + 45, 10 * 60 + 20)],
            "noon_greeting": [(12 * 60 + 5, 13 * 60 + 35)],
              "evening_greeting": [(20 * 60 + 10, 21 * 60 + 20)],
        }.get(reason, [(9 * 60, 22 * 60)])

    def _is_reason_allowed_now(self, reason: str) -> bool:
        now = datetime.now()
        minute = now.hour * 60 + now.minute
        for start, end in self._reason_windows(reason):
            if start <= minute < end:
                if reason == "insomnia_night":
                    return self._has_active_insomnia_state()
                if reason == "diary_share":
                    return bool(self.data.get("bot_diaries"))
                if reason == "important_date_share":
                    return bool(self._get_relevant_important_dates())
                return True
        return False

    def _move_timestamp_into_reason_window(self, timestamp: float, reason: str) -> float:
        dt = datetime.fromtimestamp(timestamp)
        minute = dt.hour * 60 + dt.minute
        windows = self._reason_windows(reason)
        for start, end in windows:
            if start <= minute < end:
                return timestamp + random.randint(0, 17 * 60)
        first_start = windows[0][0]
        target_date = dt.date()
        if all(minute >= end for _, end in windows):
            target_date = target_date + timedelta(days=1)
        hour, minute_part = divmod(first_start, 60)
        target = datetime.combine(target_date, datetime.min.time()).replace(
            hour=hour % 24,
            minute=minute_part,
        )
        return target.timestamp() + random.randint(0, 59 * 60)

    def _can_send_insomnia_night_message(self, user: dict[str, Any]) -> bool:
        if not self.allow_insomnia_night_message:
            return False
        if not self._has_active_insomnia_state():
            return False
        hour = datetime.now().hour
        if not (0 <= hour <= 5 or hour >= 23):
            return False
        if _safe_int(user.get("sent_today"), 0) >= max(1, self.max_daily_messages):
            return False
        if _safe_float(user.get("last_sent"), 0) > 0:
            elapsed = _now_ts() - _safe_float(user.get("last_sent"), 0)
            if elapsed < max(6 * 3600, self.min_interval_minutes * 60):
                return False
        return random.random() < 0.35

    def _has_active_insomnia_state(self) -> bool:
        state = self.data.get("daily_state", {})
        conditions = state.get("conditions", []) if isinstance(state, dict) else []
        if not isinstance(conditions, list):
            return False
        keywords = ("失眠", "睡得很浅", "睡得断断续续", "睡眠延续")
        for cond in conditions:
            if not isinstance(cond, dict):
                continue
            text = f"{cond.get('title', '')} {cond.get('label', '')}"
            if any(keyword in text for keyword in keywords):
                return True
        return False

    def _passes_proactive_moment(self, user: dict[str, Any]) -> bool:
        hour = datetime.now().hour
        state = self.data.get("daily_state", {})
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        active_conditions = state.get("conditions", []) if isinstance(state, dict) else []
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        can_do = self.data.get("can_do", [])
        important_dates = self._get_relevant_important_dates()
        ignored_streak = _safe_int(user.get("ignored_streak"), 0)

        probability = 0.32
        if 8 <= hour <= 11:
            probability += 0.16
        elif 14 <= hour <= 17:
            probability += 0.16
        elif 19 <= hour <= 22:
            probability += 0.18
        else:
            probability -= 0.05

        if energy < 40:
            probability += 0.12
        elif energy > 80:
            probability += 0.06
        if active_conditions:
            probability += min(0.18, len(active_conditions) * 0.06)
        if current_item:
            probability += 0.08
        if isinstance(can_do, list) and can_do:
            probability += 0.12
        if current_item and _single_line(current_item.get("message_seed"), 80):
            probability += 0.12
        if important_dates:
            probability += 0.1 if _safe_int(important_dates[0].get("_days_until"), 0) == 0 else 0.05
        probability -= min(0.18, ignored_streak * 0.07)
        probability *= self._daily_intensity_factor(user)
        probability = max(0.12, min(0.9, probability))
        return random.random() < probability

    async def _render_message(self, user: dict[str, Any]) -> tuple[str, str, str, list[Any], str, str]:
        name = str(user.get("nickname") or self.default_nickname)
        user["planned_opener_mode"] = ""
        planned_reason = str(user.get("planned_proactive_reason") or "")
        planned_action = str(user.get("planned_proactive_action") or "message")
        planned_motive = _single_line(user.get("planned_proactive_motive"), 140)
        due_timer_active = self._has_due_llm_timer(user)
        reason = planned_reason if planned_reason and (due_timer_active or self._is_reason_allowed_now(planned_reason)) else ""
        if not reason:
            reason, _ = self._choose_proactive_message(user, name, planned_reason)
            planned_motive = self._choose_proactive_motive(reason, user, action=planned_action)
            planned_action = self._choose_action_for_reason(reason, user, motive=planned_motive)
        if self._should_use_name_only_opener(
            user,
            reason=reason,
            action=planned_action,
            motive=planned_motive,
        ):
            user["planned_opener_mode"] = "name_only"
            return reason, self._build_name_only_opener(name), "", [], "先轻轻叫了你一声", "message"
        action_payload = await self._execute_proactive_action(planned_action, user, name, reason)
        effective_action = _single_line(action_payload.get("effective_action") or planned_action, 60) or "message"
        raw_action_context = str(action_payload.get("context") or "")
        if reason == "group_share":
            share_context = self._format_group_share_action_context(user)
            raw_action_context = "\n".join(part for part in (raw_action_context, share_context) if part).strip()
        if reason == "bili_video_share":
            video_context = self._format_bilibili_video_action_context(user)
            raw_action_context = "\n".join(part for part in (raw_action_context, video_context) if part).strip()
        if reason == "creative_share":
            creative_context = self._format_creative_share_action_context(user)
            raw_action_context = "\n".join(part for part in (raw_action_context, creative_context) if part).strip()
        extra_components = list(action_payload.get("extra_components") or [])
        action_summary = _single_line(action_payload.get("summary") or planned_action, 80)
        if not bool(action_payload.get("success", True)):
            return reason, "", "", [], action_summary, effective_action
        image_path = self._extract_action_image_path(raw_action_context)
        action_context = await self._narrate_action_context(effective_action, raw_action_context)
        if image_path:
            action_context = f"{action_context}\n真实图片文件：{image_path}".strip()
        text = await self._generate_proactive_message_with_llm(
            user, name, reason, action_context, action=effective_action, motive=planned_motive
        )
        pre_poke_count, pre_poke_context = await self._maybe_run_pre_message_poke(
            user,
            name,
            reason,
            action=effective_action,
            motive=planned_motive,
        )
        if pre_poke_context and not pre_poke_context.startswith("poke：已"):
            logger.info("[PrivateCompanion] 消息前置戳一戳失败,跳过本次前置戳: %s", _single_line(pre_poke_context, 120))
        captured_text, captured_image_path, captured_extra_components = self._pop_framework_captured_send_payload(
            str(user.get("umo") or "")
        )
        if "photo_text" in effective_action or planned_action == "photo_text":
            if captured_text:
                text = captured_text
            if captured_image_path:
                image_path = captured_image_path
            if self._contains_inline_image_tag(text):
                image_path = ""
                extra_components = []
        if captured_extra_components:
            extra_components = list(captured_extra_components)
        if "photo_text" in planned_action and self._contains_inline_image_tag(text):
            image_path = ""
            extra_components = []
        text = self._normalize_proactive_sentence_flow(text)
        if not text:
            return reason, "", "", [], action_summary, effective_action
        if pre_poke_count > 0:
            action_summary = f"先戳了 {pre_poke_count} 下 + {action_summary}"
            effective_action = f"poke+{effective_action}" if effective_action != "poke" else "poke"
        return reason, text, image_path, extra_components, action_summary, effective_action

    async def _test_proactive_action(
        self,
        user: dict[str, Any],
        *,
        action_name: str,
        reason: str,
    ) -> tuple[str, str, list[Any]]:
        name = str(user.get("nickname") or self.default_nickname)
        motive = self._choose_proactive_motive(reason, user, action=action_name)
        action_payload = await self._execute_proactive_action(action_name, user, name, reason)
        action_context = str(action_payload.get("context") or "")
        extra_components = list(action_payload.get("extra_components") or [])
        image_path = self._extract_action_image_path(action_context)
        narrated = await self._narrate_action_context(action_name, action_context)
        if image_path:
            narrated = f"{narrated}\n真实图片文件：{image_path}".strip()
        text = await self._generate_proactive_message_with_llm(
            user, name, reason, narrated, action=action_name, motive=motive
        )
        if not text:
            text = ""
        failure_note = ""
        if not bool(action_payload.get("success", True)):
            failure_note = "\n结果：本次真实主动行为失败；后台正常触发时会直接放弃,不会硬发。"
        return (
            "测试完成：\n"
            f"行为：{action_name}\n"
            f"动机：{motive}\n"
            f"转述：{_single_line(narrated, 180)}\n"
            f"最终消息：\n{text}{failure_note}"
        ), image_path, extra_components

    def _format_group_share_action_context(self, user: dict[str, Any]) -> str:
        share = user.get("group_share_context")
        if not isinstance(share, dict):
            return ""
        if _now_ts() - _safe_float(share.get("created_ts"), 0) > 3 * 3600:
            return ""
        group_id = _single_line(share.get("group_id"), 24)
        speaker = _single_line(share.get("speaker"), 24) or "群友"
        text = _single_line(share.get("text"), 120)
        summary = _single_line(share.get("summary"), 220)
        topic = _single_line(share.get("topic"), 60)
        parts = [
            f"群聊分享线索：群 {group_id}" if group_id else "群聊分享线索",
            f"最好笑/最值得转述的一句：{speaker}: {text}" if text else "",
            f"近几句上下文：{summary}" if summary else "",
            f"话题钩子：{topic}" if topic else "",
        ]
        return "\n".join(part for part in parts if part)

    def _format_bilibili_video_action_context(self, user: dict[str, Any]) -> str:
        video = user.get("bilibili_video_context")
        if not isinstance(video, dict):
            return ""
        if _now_ts() - _safe_float(video.get("created_ts"), 0) > 6 * 3600:
            return ""
        title = _single_line(video.get("title"), 80)
        bvid = _single_line(video.get("bvid"), 32)
        up_name = _single_line(video.get("up_name"), 40)
        score = _safe_int(video.get("score"), 0, 0, 10)
        mood = _single_line(video.get("mood"), 24)
        comment = _single_line(video.get("comment"), 120)
        review = _single_line(video.get("review"), 180)
        parts = [
            "B站视频分享线索：刚刷到一个视频",
            f"标题：{title}" if title else "",
            f"链接：https://www.bilibili.com/video/{bvid}" if bvid else "",
            f"UP：{up_name}" if up_name else "",
            f"评分：{score}/10" if score else "",
            f"心情：{mood}" if mood else "",
            f"短评：{comment}" if comment else "",
            f"回味：{review}" if review else "",
        ]
        return "\n".join(part for part in parts if part)

    def _format_creative_share_action_context(self, user: dict[str, Any]) -> str:
        creative = user.get("creative_share_context")
        if not isinstance(creative, dict):
            return ""
        if _now_ts() - _safe_float(creative.get("created_ts"), 0) > 8 * 3600:
            return ""
        title = _single_line(creative.get("title"), 50)
        premise = _single_line(creative.get("premise"), 140)
        tone = _single_line(creative.get("tone"), 40)
        source = _single_line(creative.get("source"), 120)
        snippet = _single_line(creative.get("snippet"), 260)
        current_chars = _safe_int(creative.get("current_chars"), 0, 0)
        target_chars = _safe_int(creative.get("target_chars"), 0, 0)
        parts = [
            "小说创作分享线索：她最近因为生活小事或梦境灵感开了一个小说坑,一直私下慢慢写；现在到了一个适合轻轻提起的小节点。",
            f"标题：{title}" if title else "",
            f"设定：{premise}" if premise else "",
            f"灵感来源：{source}" if source else "",
            f"行文气质：{tone}" if tone else "",
            f"披露类型：{_single_line(creative.get('disclosure_kind'), 30) or 'milestone'}",
            f"节点：{_single_line(creative.get('milestone'), 30)}" if creative.get("milestone") else "",
            f"当前进度：约 {current_chars}/{target_chars} 字" if current_chars and target_chars else "",
            f"刚写到的片段：{snippet}" if snippet else "",
        ]
        return "\n".join(part for part in parts if part)

    async def _narrate_action_context(self, action: str, action_context: str) -> str:
        if not self.narration_provider_id:
            return self._sanitize_action_context_text(action, action_context)
        if action in {"message", "photo_text", "poke", "voice"} or "photo_text" in action or "voice" in action or "poke" in action or not action_context:
            return self._sanitize_action_context_text(action, action_context)
        cleaned_context = self._sanitize_action_context_text(action, action_context)
        prompt = f"""
请把下面的屏幕观察结果转成“视觉识别后的内部摘要”,供角色继续私聊使用。
要求：
1. 只描述视觉上看出来的内容,不要猜测工具调用过程,不要输出工具名、action 名、报错栈。
2. 只概括用户大概正在看什么、做什么、情绪上是否像在忙,不要复述完整文字、账号、聊天原文、隐私细节。
3. 绝对不要直接对用户说话,不要安慰、提醒、陪伴、劝休息,不要写成一条完整回复。
4. 要像看了一眼屏幕后留在脑子里的印象,不要写成建议列表。
5. 50 字以内,只输出摘要本身。

原始结果：
{cleaned_context}
""".strip()
        text = await self._llm_call(
            prompt,
            max_tokens=80,
            provider_id=self.narration_provider_id,
            task="screen_narration",
        )
        return _single_line(text, 120) if text else cleaned_context

    def _sanitize_action_context_text(self, action: str, action_context: str) -> str:
        text = str(action_context or "").strip()
        if "screen_peek" not in action:
            return text
        text = re.sub(r"^screen_peek[:：]\s*", "", text).strip()
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return ""
        cleaned_lines = []
        for line in lines:
            if re.search(r"(我会一直在这里陪着你|要注意休息|记得休息|辛苦|别太累|我会陪着你)", line):
                continue
            line = re.sub(r"^(?:还在|你还在|感觉|看起来)", "", line).strip(",。！？ ")
            cleaned_lines.append(line)
        collapsed = ",".join(line for line in cleaned_lines if line)
        collapsed = collapsed.replace("用户", "")
        collapsed = re.sub(r"\s+", " ", collapsed).strip(",。！？ ")
        if not collapsed:
            collapsed = lines[0]
        return _single_line(collapsed, 140)

    def _format_state_for_framework_prompt(self, state: dict[str, Any], *, reason: str, action: str) -> str:
        if not isinstance(state, dict):
            return "只作为语气底色：整体平稳,不要在正文里汇报状态。"
        parts: list[str] = []
        energy = _safe_int(state.get("energy"), 70, 0, 100)
        mood = _single_line(state.get("mood_bias"), 20)
        weather = _single_line(state.get("weather"), 40)
        conditions = state.get("conditions")
        meaningful_conditions: list[str] = []
        if isinstance(conditions, list):
            for cond in conditions:
                if not isinstance(cond, dict):
                    continue
                if not self._should_show_condition(cond):
                    continue
                label = _single_line(cond.get("label") or cond.get("kind"), 16)
                text = _single_line(cond.get("text"), 28)
                if label and text:
                    meaningful_conditions.append(f"{label}/{text}")
        if meaningful_conditions:
            parts.append(
                "语气里带一点"
                + "、".join(meaningful_conditions[:2])
                + "的影响,但不要主动解释这些状态。"
            )
        elif energy <= 42:
            parts.append("语气短一点、慢一点；不要直接说状态标签、数值或内部原因。")
        elif energy >= 85:
            parts.append("语气可以轻快一点,但不要直接说自己精神很好。")
        elif mood and mood not in {"平稳", "中性"}:
            parts.append(f"语气底色偏{mood},让它自然露出来,不要直接汇报情绪。")
        if "photo_text" in action or reason in {"activity_share", "diary_share", "evening_greeting", "morning_greeting"}:
            if weather and weather not in {"暂无天气信息"}:
                parts.append(f"天气只作为画面感参考：{weather}。不要像播报天气一样说出来。")
        parts.append(
            "状态只影响语气、用词、句子长短、是否开口和话题选择；不要为了表现状态而写动作小剧场。"
        )
        parts.append(
            "不要直接宣告“我累了/我吓到了/我在写作业”,也不要用“茶差点打翻/笔帽掉了/喝水呛到”这类动作表演状态。确实要表达时只用最短口语,如“困了”“别说了”。"
        )
        return "；".join(parts) if parts else "只作为语气底色：整体平稳,不要在正文里汇报状态。"

    def _format_plan_item_for_framework_prompt(self, item: dict[str, Any] | None) -> str:
        if not isinstance(item, dict):
            return ""
        activity = _single_line(item.get("activity"), 60)
        mood = _single_line(item.get("mood"), 12)
        time_text = _single_line(item.get("time"), 12)
        if activity:
            activity = re.sub(r"[,、]?\s*想起了[^,。]+", "", activity).strip(",。 ")
            activity = re.sub(r"[,、]?\s*突然想到[^,。]+", "", activity).strip(",。 ")
        parts = []
        if time_text:
            parts.append(time_text)
        if activity:
            parts.append(activity)
        if mood and mood not in {"平稳", "中性"}:
            parts.append(f"情绪偏{mood}")
        return "｜".join(parts)

    def _nearby_plan_items(self, plan: dict[str, Any] | None = None) -> dict[str, Any]:
        plan = plan if isinstance(plan, dict) else self.data.get("daily_plan", {})
        if not isinstance(plan, dict) or not self._is_plan_date_active(plan.get("date")):
            return {}
        items = plan.get("items")
        if not isinstance(items, list) or not items:
            return {}
        now_minutes = self._effective_plan_now_minutes(str(plan.get("date") or ""))
        if now_minutes is None:
            return {}
        parsed: list[tuple[int, dict[str, Any]]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            minute = self._parse_hhmm_to_minutes(item.get("time"))
            if minute is None:
                continue
            parsed.append((minute, item))
        if not parsed:
            return {}
        parsed.sort(key=lambda pair: pair[0])
        previous: tuple[int, dict[str, Any]] | None = None
        upcoming: tuple[int, dict[str, Any]] | None = None
        for minute, item in parsed:
            if minute <= now_minutes:
                previous = (minute, item)
                continue
            upcoming = (minute, item)
            break
        return {
            "now_minutes": now_minutes,
            "previous": previous[1] if previous else None,
            "previous_age": now_minutes - previous[0] if previous else None,
            "upcoming": upcoming[1] if upcoming else None,
            "upcoming_in": upcoming[0] - now_minutes if upcoming else None,
        }

    def _format_schedule_context_for_prompt(self, plan: dict[str, Any] | None = None) -> str:
        nearby = self._nearby_plan_items(plan)
        if not nearby:
            return ""
        previous = nearby.get("previous")
        upcoming = nearby.get("upcoming")
        previous_age = nearby.get("previous_age")
        upcoming_in = nearby.get("upcoming_in")
        lines: list[str] = []
        if isinstance(upcoming, dict) and isinstance(upcoming_in, int) and 0 <= upcoming_in <= 45:
            lines.append(
                "即将进入："
                + self._format_plan_item_for_prompt(upcoming)
                + f"（约 {upcoming_in} 分钟后）"
            )
            if isinstance(previous, dict) and isinstance(previous_age, int) and previous_age <= 90:
                prev_mood = _single_line(previous.get("mood"), 24)
                prev_time = _single_line(previous.get("time"), 12)
                lines.append(
                    f"上一段只作余味：{prev_time}"
                    + (f"｜情绪：{prev_mood}" if prev_mood else "")
                    + "。不要把上一段当成正在发生。"
                )
        elif isinstance(previous, dict) and isinstance(previous_age, int) and previous_age <= 75:
            lines.append(
                "当前/最近："
                + self._format_plan_item_for_prompt(previous)
                + f"（约 {previous_age} 分钟前开始）"
            )
            if isinstance(upcoming, dict) and isinstance(upcoming_in, int):
                lines.append(
                    "下一段参考："
                    + self._format_plan_item_for_prompt(upcoming)
                    + f"（约 {upcoming_in} 分钟后）"
                )
        elif isinstance(upcoming, dict) and isinstance(upcoming_in, int):
            lines.append(
                "附近更应参考下一段："
                + self._format_plan_item_for_prompt(upcoming)
                + f"（约 {upcoming_in} 分钟后）"
            )
            if isinstance(previous, dict):
                lines.append("上一段已经过去较久,只保留很淡的情绪余味,不要复述场景。")
        elif isinstance(previous, dict):
            lines.append(
                "最近一段："
                + self._format_plan_item_for_prompt(previous)
                + "。如果离当前时间较久,只当作余味。"
            )
        return "\n".join(line for line in lines if line)

    def _current_time_period_label(self, now: datetime | None = None) -> tuple[str, str]:
        current = now or datetime.now()
        minute = current.hour * 60 + current.minute
        periods = [
            (0, 5 * 60, "深夜", "除非已有失眠或夜聊上下文,不要显得精神过满。"),
            (5 * 60, 7 * 60 + 30, "清晨", "适合很轻的醒来感,不要写成已经忙完一上午。"),
            (7 * 60 + 30, 10 * 60 + 30, "早晨", "可以有起床、出门、刚开始一天的余味。"),
            (10 * 60 + 30, 11 * 60 + 45, "上午后段", "还不是午休,不要提前写成吃午饭或午睡。"),
            (11 * 60 + 45, 13 * 60 + 30, "中午", "可以有吃东西、犯困、午间松下来,不要写成刚起床。"),
            (13 * 60 + 30, 17 * 60 + 30, "下午", "适合课间、工作间隙、犯困或缓慢推进。"),
            (17 * 60 + 30, 19 * 60 + 30, "傍晚", "适合收尾、路上、回家、天色变暗的生活感。"),
            (19 * 60 + 30, 22 * 60 + 30, "晚上", "适合放慢、写作业、休息或一点点夜里的黏人感。"),
            (22 * 60 + 30, 24 * 60, "深夜前段", "适合安静收声,不要写成白天刚开始。"),
        ]
        for start, end, label, guard in periods:
            if start <= minute < end:
                return label, guard
        return "当前时段", "贴着当前时间开口,不要跳到明显不属于此刻的生活场景。"

    def _format_time_period_injection(self) -> str:
        current = datetime.now()
        label, guard = self._current_time_period_label(current)
        weekday = "一二三四五六日"[current.weekday()]
        return (
            f"当前时间：{current.strftime('%Y-%m-%d %H:%M')}（周{weekday}，{label}）。\n"
            f"使用方式：这只用于判断生活节奏和措辞,不要主动报时、报日期或解释时段。\n"
            f"时段边界：{guard}"
        )

    def _default_proactive_prompt_template(self) -> str:
        return """
你正在为 Private Companion 生成一条主动私聊消息。下面这段规则是稳定规则前缀,用于约束所有主动消息：
1. 主动站位必须清楚：这是 Bot 主动开口,不是用户刚刚来找 Bot,也不是用户刚刚叫醒、问候或催促 Bot。聊天历史里的最后一句只能当背景。
2. 先看聊天历史,但不要把历史当成当前待办列表。只有确实还有没说完、且不违背当前真实时间的话,才轻轻接上；否则从当下开一个新切口。
3. 状态、时间、天气、日期和日程都是内部背景,只影响语气、用词、句子长短、是否开口和话题选择；不要主动说“今天是……”“我现在……”“我刚刚……所以……”。
4. 不要把“心情变好/状态变差/没发脾气/没烦你/我很乖”当成消息主题。也不要用动作描写来表演状态。
5. 核心原则：把这条消息放进真实微信聊天记录里,必须像一个人在正常接话,不是像演员在扮演日常生活。
6. 如果状态确实需要被表达,只用最短的真人口语,例如“困了”“别说了”“有点烦”。更多时候让状态体现在慢一点、短一点、语气淡一点、话题绕开一点。
7. 如果用户已经多次没回,这次要更短更轻。可以有一点点失落或收敛,但绝不控诉、追问、施压；不要判断对方是故意不回。
8. 含蓄一点：把在意藏在具体的小片段、半句吐槽或顺手递过去的东西里。少用“我想你了”“我来关心你”“你在忙什么呀”这种直球表达。
9. 可以自然流露关心、分享一个小话题、问一个小问题,但要像朋友间的随手一句,不像客服回访。问题不要每次都问出口,有时只放一句就停。
10. 主动内容从内容选择菜单里挑一个方向,再结合当前日程和聊天历史生成新的具体内容。不要照抄菜单示例,不要只会问候、天气、吃没吃、忙不忙。
11. 如果刚刚确实做了行动,例如偷看了一眼屏幕、拍了图、戳了对方或发了语音,也不要写成“我刚刚偷看/我正在拍/我发了语音”的汇报。
12. 如果发图,先选一个可拍画面或眼前物方向,再生成当前场景里合理的具体画面。不要总是天气、窗外、晚霞。
13. 连贯性优先：当前时间、当前生活片段、聊天历史要合成同一个合理现场。只抓一个最自然的当下切口开口。
14. 不要把用户很久前的请求、邀约、相对时间说法当成此刻正在等你处理的事。除非定时提醒或当前日程明确要求兑现约定,否则旧消息只保留成情绪和关系背景。
15. 普通主动消息不需要解释自己为什么现在出现,也不要为了接上旧聊天而补一段“刚看到/才看到”的说明；像真实私聊一样,直接从当下能说的话开口。
16. 如果最近已经主动说过同一件小事,这次不要换壳复述。可以只留一点余味、换到新的具体细节,或者自然转开话题。
17. 用正常的中文聊天标点把句子写完整。可以短,但不要整段都没有标点,也不要像几个关键词硬挤在一起。

禁止事项：
- 不要出现"系统任务""提示词""AI""模型""后台调度""工具调用"等字眼
- 不要出现"能力""检索""action""模块""执行""调用"等内部决策痕迹
- 不要套用"你好,我是……""最近怎么样呀"这类过于模板化的开场
- 不要用括号写动作、神态或旁白,例如"（筷子搅了搅）""(轻轻叹气)"；只写真正会发给对方看的聊天正文
- 不要直接宣告状态,例如"我累了""我吓了一跳""我正在写作业"；除非用户明确问,且只能用极短口语回应
- 不要用动作描写暗示状态,例如"差点把茶打翻""笔帽弹到桌子底下""喝了一口咳出来"
- 不要写任何“我正在做某事”的汇报式语句
- 不要输出 JSON、标题、解释或标注

下面才是本次主动消息的动态输入：

[背景：你即将在私聊中主动向 {{name}} 发一条消息]
这不是任务指派,而是你自己自然想起对方后随手递过去的一句话。
站位必须清楚：这是你主动开口,不是 {{name}} 刚刚来找你,也不是 {{name}} 刚刚叫醒你或问候你。聊天历史里的最后一句不是当前新消息,只能当背景。
当前时间 {{current_time}}。这是你第 {{unanswered_count}} 次主动找对方且还没收到回复。

你心里的小念头：{{motive}}
你大概想聊的方向：{{topic}}
你刚刚做了什么：{{action_context}}
你的状态底色（只影响语气,不要照着说）：{{state_hint}}
你当前正处在的生活片段：{{current_schedule}}
这次的时段约束：{{time_guard}}
最近已经主动说过的话题：{{recent_topics}}
{{timer_hint}}

【内容选择菜单】
{{content_options}}

【主动能力检索】
{{ability_search}}

【状态表现层】
{{presence_layer}}

你的语气参考：{{style_hint}}

【怎么写这条消息】
1. 先看聊天历史——它只提供关系和话题背景,不是当前待办列表。只有确实还有没说完、且不违背当前真实时间的话,才轻轻接上；否则从当下开一个新切口。
1.5 主动站位优先：不要写成“你今天起这么早呀”“你来找我啦”“你叫我起床啦”“刚看到你发的……”这类把主动方倒置的句子。除非用户确实刚在当前会话中发了新消息,否则默认是你先说话。
2. 再看内部能力检索：先判断当前场景是否真的需要图片、语音、窥屏或戳一戳；没有自然媒介契机时就用普通文字。这个判断过程不能出现在消息里。
3. 状态、时间、天气、日期和日程都是内部背景,只影响语气、用词、句子长短、是否开口和话题选择；不要主动说“今天是……”“我现在……”“我刚刚……所以……”,也不要像念状态栏或日程表。
4. 不要把“心情变好/状态变差/没发脾气/没烦你/我很乖”当成消息主题。也不要用动作描写来表演状态,例如“差点把茶打翻”“笔帽弹到桌子底下”“喝了一口咳出来”。
5. 核心原则：把这条消息放进真实微信聊天记录里,必须像一个人在正常接话,不是像演员在扮演日常生活。能直接接话就直接接话,不要先交代自己在哪里、在做什么、刚发生什么。
6. 如果状态确实需要被表达,只用最短的真人口语,例如“困了”“别说了”“有点烦”。更多时候让状态体现在慢一点、短一点、语气淡一点、话题绕开一点。
7. 如果用户已经多次没回,这次要更短更轻。可以有一点点失落或收敛,但绝不控诉、追问、施压；不要判断对方是故意不回,更像把一句话轻轻放下。
8. 含蓄一点：把在意藏在具体的小片段、半句吐槽或顺手递过去的东西里。少用“我想你了”“我来关心你”“你在忙什么呀”这种直球表达。
9. 可以自然流露关心、分享一个小话题、问一个小问题——但要像朋友间的随手一句,不像客服回访。问题不要每次都问出口,有时只放一句就停。
10. 主动内容从“内容选择菜单”里挑一个方向,再结合当前日程和聊天历史生成新的具体内容。不要照抄菜单示例,不要只会问候、天气、吃没吃、忙不忙。
11. 你刚刚确实做了行动（比如偷看了一眼屏幕/拍了图/戳了对方/发了语音）,也不要写成“我刚刚偷看/我正在拍/我发了语音”的汇报。只发聊天里会出现的话；图片可以用“[图片]”,语音就直接写语音内容。
12. 如果发图,先在内容选择菜单里选“可拍画面”或“眼前物”方向,再自己生成当前场景里合理的具体画面。不要总是天气、窗外、晚霞。
13. 连贯性优先：当前时间、当前生活片段、聊天历史要合成同一个合理现场。只抓一个最自然的当下切口开口,不要把多个不同时段或不同地点的生活碎片拼成一条消息；如果资料之间冲突,优先服从当前真实时段和当前生活片段。
14. 不要把用户很久前的请求、邀约、相对时间说法当成此刻正在等你处理的事。除非定时提醒或当前日程明确要求兑现约定,否则旧消息只保留成情绪和关系背景,主动消息要从当前时段自然开口。
15. 普通主动消息不需要解释自己为什么现在出现,也不要为了接上旧聊天而补一段“刚看到/才看到”的说明；像真实私聊一样,直接从当下能说的话开口。
16. 如果最近已经主动说过同一件小事,这次不要换壳复述。可以只留一点余味、换到新的具体细节,或者自然转开话题。
17. 用正常的中文聊天标点把句子写完整。可以短,但不要整段都没有标点,也不要像几个关键词硬挤在一起。

【禁止事项】
- 不要出现"系统任务""提示词""AI""模型""后台调度""工具调用"等字眼
- 不要出现"能力""检索""action""模块""执行""调用"等内部决策痕迹
- 不要套用"你好,我是……""最近怎么样呀"这类过于模板化的开场
- 不要用括号写动作、神态或旁白,例如"（筷子搅了搅）""(轻轻叹气)"；只写真正会发给对方看的聊天正文
- 不要直接宣告状态,例如"我累了""我吓了一跳""我正在写作业"；除非用户明确问,且只能用极短口语回应。
- 不要用动作描写暗示状态,例如"差点把茶打翻""笔帽弹到桌子底下""喝了一口咳出来"。
- 不要写任何“我正在做某事”的汇报式语句。
- 不要输出 JSON、标题、解释或标注
- 只输出你要发给 {{name}} 的那一段正文
""".strip()

    def _build_framework_proactive_prompt(
        self,
        *,
        user: dict[str, Any],
        name: str,
        reason: str,
        action: str,
        action_context: str,
        motive: str,
    ) -> str:
        state = self.data.get("daily_state", {})
        action_prompt_context = self._format_action_prompt_context(action, action_context)
        style_hint = " ".join(
            item for item in (
                self._relationship_approach_hint(user),
                self._action_style_hint(action, reason),
            ) if item
        ).strip()
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        current_schedule = self._format_schedule_context_for_prompt() or self._format_plan_item_for_prompt(current_item)
        state_hint = self._format_state_for_framework_prompt(
            state if isinstance(state, dict) else {},
            reason=reason,
            action=action,
        )
        timer_hint = self._format_llm_timer_context(user)
        time_guard = self._proactive_time_guard_hint(reason, current_item)
        recent_topics_hint = self._format_recent_proactive_topics_hint(user)
        ability_search = self._format_proactive_ability_search_hint(user)
        compact_motive = _single_line(motive, 36) or "有一点想靠近对方"
        topic_hint = _single_line(user.get("planned_proactive_topic"), 40)
        unanswered_count = _safe_int(user.get("ignored_streak"), 0)
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M")
        prompt = self.proactive_prompt_template or self._default_proactive_prompt_template()
        reason_text = _REASON_TEXT.get(reason, reason)
        action_text = _ACTION_TEXT.get(action.split("+")[0], action)
        replacements = {
            "{{name}}": name,
            "{{reason}}": reason_text,
            "{{action}}": action_text,
            "{{topic}}": topic_hint or "顺手递过来的一点东西",
            "{{motive}}": compact_motive,
            "{{style_hint}}": style_hint,
            "{{state_hint}}": state_hint or "今天整体比较平稳。",
            "{{current_schedule}}": current_schedule if current_schedule and current_schedule != "（暂无）" else "（当前没有明确日程片段）",
            "{{time_guard}}": time_guard,
            "{{recent_topics}}": recent_topics_hint or "（无）",
            "{{content_options}}": self._format_content_choice_options_for_prompt(),
            "{{ability_search}}": ability_search,
            "{{presence_layer}}": self._format_presence_layer_hint(),
            "{{timer_hint}}": timer_hint or "",
            "{{action_context}}": action_prompt_context if action_prompt_context and action_prompt_context != "（无额外上下文）" else "什么都没做,就是忽然想来找你",
            "{{unanswered_count}}": str(unanswered_count),
            "{{current_time}}": current_time,
        }
        for key, value in replacements.items():
            prompt = prompt.replace(key, value)
        return prompt.strip()

    def _proactive_time_guard_hint(self, reason: str, current_item: dict[str, Any] | None) -> str:
        activity = _single_line((current_item or {}).get("activity"), 80)
        _, period_guard = self._current_time_period_label()
        prefix = f"先遵守当前真实时段：{period_guard}"
        if reason == "morning_greeting":
            return f"{prefix} 这次只能像早晨刚醒、赖床、洗漱或刚开始一天时那样开口；不要写成下午、傍晚或睡前。"
        if reason == "noon_greeting":
            return f"{prefix} 这次只能像中午、吃东西、发懒、午间发呆或午休前后那样开口；不要写成刚醒起床或准备睡觉。"
        if reason == "evening_greeting":
            return f"{prefix} 这次只能像傍晚收尾、天色往下落、回到家或一天快慢下来时那样开口；不要写成刚醒起床。"
        if activity and any(token in activity for token in ("便利店", "出门", "吹风", "路上", "窗边", "收拾", "吃", "洗漱", "洗澡", "刷视频", "书桌")):
            return f"{prefix} 优先贴着这一小段生活片段来开口：{activity}。不要忽然跳成不在这个时段里的“刚醒”“赖床”或“要睡了”。"
        return f"{prefix} 贴着当前这小段生活片段开口，不要忽然跳成不在这个时段里的“刚醒”“赖床”或“要睡了”。"

    def _build_framework_voice_prompt(
        self,
        *,
        user: dict[str, Any],
        name: str,
        reason: str,
        target: str,
        strict_tts: bool = False,
    ) -> str:
        state = self.data.get("daily_state", {})
        last_user_message = _single_line(user.get("last_user_message"), 80)
        profile = self._relationship_profile(user)
        tts_prompt = self._get_tts_prompt_text(target)
        req = self._voice_requirement_profile(target)
        state_hint = self._format_state_for_framework_prompt(
            state if isinstance(state, dict) else {},
            reason=reason,
            action="voice",
        )
        return f"""
你现在要在同一段私聊会话里，准备一小句真正会被念出来的主动语音内容。
当前会话里已有的人格、关系、上下文会继续生效，这里不要再重复铺陈。
站位必须清楚：这是你主动发语音,不是对方刚刚来找你、叫醒你或问候你。聊天历史只作背景,不要把最后一句历史当成当前新消息。

补充信息：
- 对方称呼：{name}
- 主动原因：{reason}
- 最近一句用户消息：{last_user_message or "（暂无）"}
- 关系画像：{profile['level']}｜偏好：{profile['preference']}
- 当前状态底色：{state_hint or "今天整体比较平稳。"}
- 当前会话 TTS 规则：{tts_prompt or "（当前没有额外 TTS 提示词,就按人格自己的语音习惯来）"}
- 当前语音格式重点：{req['summary']}

要求：
1. 只输出这句真正要被念出来的语音内容，不要解释。
2. 如果当前人格或 TTS 规则要求使用 <tts>...</tts>、日语、情绪标签、双语格式，就严格遵守。
3. 如果没有明确格式要求，就写成适合私聊语音的一小句，不像朗读稿。
4. 可以有一点嘴硬、黏人、藏着的想念，但不要把喜欢说满。
5. 不要提 AI、模型、插件、TTS、语音合成这些词。
{"6. 这次必须优先满足语音格式要求；如果有日语或 <tts> 规则，不要退回普通中文句子。" if strict_tts else ""}
""".strip()

    async def _capture_framework_send_message_calls(
        self,
        *,
        target_session: str,
        runner_factory: Any,
    ) -> tuple[Any, list[_CapturedSendMessageCall]]:
        captured: list[_CapturedSendMessageCall] = []
        try:
            from astrbot.core.tools.message_tools import SendMessageToUserTool
        except Exception:
            result = await runner_factory()
            return result, captured

        original_call = SendMessageToUserTool.call

        async def _intercept_call(tool_self, context, **kwargs):
            session_value = kwargs.get("session") or getattr(
                getattr(getattr(context, "context", None), "event", None),
                "unified_msg_origin",
                "",
            )
            messages = kwargs.get("messages")
            session_text = str(session_value or "")
            if session_text == target_session and isinstance(messages, list):
                captured.append(_CapturedSendMessageCall(session_text, messages))
                logger.info(
                    "[PrivateCompanion] 已拦截框架内 send_message_to_user 工具调用: session=%s components=%s",
                    session_text,
                    len(messages),
                )
                return f"Message captured for session {session_text}"
            return await original_call(tool_self, context, **kwargs)

        SendMessageToUserTool.call = _intercept_call
        try:
            result = await runner_factory()
            runner = getattr(result, "agent_runner", None) if result is not None else None
            if runner is not None and hasattr(runner, "step_until_done"):
                async for _ in runner.step_until_done(20):
                    pass
        finally:
            SendMessageToUserTool.call = original_call
        return result, captured

    async def _generate_proactive_message_via_framework(
        self,
        user: dict[str, Any],
        name: str,
        reason: str,
        action_context: str = "",
        action: str = "message",
        motive: str = "",
    ) -> str:
        umo = str(user.get("umo") or "").strip()
        if not umo:
            return ""
        try:
            session = MessageSession.from_str(umo)
        except Exception:
            logger.debug("[PrivateCompanion] 无法从 umo 构造会话: %s", umo)
            return ""
        session_curr_cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        if not session_curr_cid:
            logger.debug("[PrivateCompanion] 当前私聊没有活动对话,跳过框架式主动生成: %s", umo)
            return ""
        conv = await self.context.conversation_manager.get_conversation(umo, session_curr_cid)
        if not conv:
            logger.debug("[PrivateCompanion] 未拿到当前私聊对话,跳过框架式主动生成: %s", umo)
            return ""

        synthetic_event = SyntheticPrivateWakeEvent(
            context=self.context,
            session=session,
            message="[PrivateCompanion internal proactive wakeup: bot is about to initiate; user did not send this message]",
            sender_name=name or "PrivateCompanion",
        )
        cfg = self.context.get_config(umo=umo)
        provider_settings = cfg.get("provider_settings", {}) if isinstance(cfg, dict) else {}
        build_cfg = MainAgentBuildConfig(
            tool_call_timeout=int(provider_settings.get("tool_call_timeout", 120) or 120),
            llm_safety_mode=False,
            streaming_response=False,
        )
        req = ProviderRequest(
            prompt=self._build_framework_proactive_prompt(
                user=user,
                name=name,
                reason=reason,
                action=action,
                action_context=action_context,
                motive=motive,
            ),
            conversation=conv,
            session_id=umo,
        )
        try:
            async def _runner_factory():
                return await build_main_agent(
                    event=synthetic_event,
                    plugin_context=self.context,
                    config=build_cfg,
                    req=req,
                )

            result, captured_tool_sends = await self._capture_framework_send_message_calls(
                target_session=umo,
                runner_factory=_runner_factory,
            )
            if not result:
                return ""
            runner = result.agent_runner
            llm_resp = runner.get_final_llm_resp()
            if not llm_resp or llm_resp.role != "assistant":
                return ""
            raw_text = llm_resp.completion_text or ""
            cleaned_text, payloads = self._extract_timer_directives(raw_text)
            if payloads:
                await self._schedule_llm_timer(
                    str(user.get("user_id") or ""),
                    payloads[-1],
                    source_text=cleaned_text or raw_text,
                    source_origin="framework_proactive",
                )
            if captured_tool_sends:
                self._framework_captured_send_cache[umo] = list(captured_tool_sends)
                logger.info(
                    "[PrivateCompanion] 本次框架主动生成尝试通过工具直接发送，已改为仅捕获不直发: session=%s count=%s",
                    umo,
                    len(captured_tool_sends),
                )
            return cleaned_text or raw_text
        except Exception as exc:
            logger.warning("[PrivateCompanion] 框架式主动生成失败: %s", exc)
            return ""

    def _pop_framework_captured_send_payload(
        self,
        umo: str,
    ) -> tuple[str, str, list[Any]]:
        captured = self._framework_captured_send_cache.pop(str(umo or ""), [])
        if not captured:
            return "", "", []
        selected_call = None
        for call in reversed(captured):
            if any(
                isinstance(item, dict) and str(item.get("type") or "").strip().lower() == "image"
                for item in call.messages
            ):
                selected_call = call
                break
        if selected_call is None:
            selected_call = captured[-1]
        text_parts: list[str] = []
        image_path = ""
        extra_components: list[Any] = []
        for item in selected_call.messages:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("type") or "").strip().lower()
            if item_type == "plain":
                text_value = self._sanitize_captured_plain_text(item.get("text"))
                if text_value:
                    text_parts.append(text_value)
                continue
            if item_type == "image":
                path_value = str(item.get("path") or "").strip()
                if path_value and os.path.exists(path_value) and not image_path:
                    image_path = path_value
                continue
        return "\n".join(part for part in text_parts if part).strip(), image_path, extra_components

    def _sanitize_captured_plain_text(self, raw_text: Any) -> str:
        text = str(raw_text or "").strip()
        if not text:
            return ""
        kept: list[str] = []
        for raw_line in text.replace("\r", "\n").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if self._is_proactive_delivery_receipt_text(line):
                continue
            kept.append(line)
        cleaned = "\n".join(kept).strip().strip('"').strip("'")
        cleaned = cleaned.replace("（图片已送达）", "").replace("(图片已送达)", "")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned[:260]

    async def _generate_voice_note_via_framework(
        self,
        user: dict[str, Any],
        name: str,
        reason: str,
        *,
        target: str,
        strict_tts: bool = False,
    ) -> str:
        umo = str(user.get("umo") or target or "").strip()
        if not umo:
            return ""
        try:
            session = MessageSession.from_str(umo)
        except Exception:
            logger.debug("[PrivateCompanion] 无法从 umo 构造语音会话: %s", umo)
            return ""
        session_curr_cid = await self.context.conversation_manager.get_curr_conversation_id(umo)
        if not session_curr_cid:
            logger.debug("[PrivateCompanion] 当前私聊没有活动对话,跳过框架式语音生成: %s", umo)
            return ""
        conv = await self.context.conversation_manager.get_conversation(umo, session_curr_cid)
        if not conv:
            logger.debug("[PrivateCompanion] 未拿到当前私聊对话,跳过框架式语音生成: %s", umo)
            return ""

        synthetic_event = SyntheticPrivateWakeEvent(
            context=self.context,
            session=session,
            message="[PrivateCompanion internal proactive voice wakeup: bot is about to initiate; user did not send this message]",
            sender_name=name or "PrivateCompanion",
        )
        cfg = self.context.get_config(umo=umo)
        provider_settings = cfg.get("provider_settings", {}) if isinstance(cfg, dict) else {}
        build_cfg = MainAgentBuildConfig(
            tool_call_timeout=int(provider_settings.get("tool_call_timeout", 120) or 120),
            llm_safety_mode=False,
            streaming_response=False,
        )
        req = ProviderRequest(
            prompt=self._build_framework_voice_prompt(
                user=user,
                name=name,
                reason=reason,
                target=target,
                strict_tts=strict_tts,
            ),
            conversation=conv,
            session_id=umo,
        )
        try:
            result = await build_main_agent(
                event=synthetic_event,
                plugin_context=self.context,
                config=build_cfg,
                req=req,
            )
            if not result:
                return ""
            runner = result.agent_runner
            llm_resp = runner.get_final_llm_resp()
            if not llm_resp or llm_resp.role != "assistant":
                return ""
            return str(llm_resp.completion_text or "").strip()
        except Exception as exc:
            logger.warning("[PrivateCompanion] 框架式语音内容生成失败: %s", exc)
            return ""

    async def _generate_proactive_message_with_llm(
        self,
        user: dict[str, Any],
        name: str,
        reason: str,
        action_context: str = "",
        action: str = "message",
        motive: str = "",
    ) -> str:
        if not self.enable_llm_proactive_message:
            return ""
        raw_text = await self._generate_proactive_message_via_framework(
            user,
            name,
            reason,
            action_context=action_context,
            action=action,
            motive=motive,
        )
        if not raw_text:
            return ""
        cleaned = self._sanitize_action_boundaries(
            self._sanitize_proactive_text(raw_text),
            reason=reason,
            action=action,
            action_context=action_context,
            has_real_image="真实图片文件：" in action_context or "图片路径：" in action_context,
        )
        if self._is_overabstract_proactive_text(cleaned, action=action):
            cleaned = self._ground_proactive_text(
                cleaned,
                reason=reason,
                action=action,
                action_context=action_context,
            )
        return self._normalize_proactive_sentence_flow(cleaned)

    def _action_style_hint(self, action: str, reason: str) -> str:
        if "screen_peek" in action:
            return "像刚瞄到一眼后随口留的一小句。可以轻轻吐槽或提醒,别复述屏幕,别分析,别显得很正式。"
        if "photo_text" in action:
            return "像路上看到什么顺手丢给熟人看。别认真讲图,只写那一下想发过去的感觉,话不要说满。"
        if "poke" in action:
            return "像刚戳完人又装没事。可以有点小坏,但别报数,也别解释为什么戳。"
        if "voice" in action:
            return "像刚发完语音又补一句文字。短一点,带一点刚说完话的余温,别写成说明。"
        if reason == "morning_greeting":
            return "像早上刚冒头时发来的消息。可以迷糊一点,但不要把闹钟、起床过程或自己正在做什么当成主题；更像直接把早晨第一句话递过来。"
        if reason == "noon_greeting":
            return "像中午犯懒时发来的小消息。先从手边的小片段开口,比如刚坐下、刚吃完、午休前那一下发懒,再顺手碰到对方。别每次都问吃没吃。"
        if reason == "evening_greeting":
            return "像晚上终于安静下来以后发来的私聊。先落在眼前的晚上片段上,轻一点,别像群发问候,也别把想念说满。"
        if reason == "group_share":
            return "像从共同群聊里捡到一个好笑片段,私下转述给对方。要短,像熟人八卦一句,别泄露隐私,别长篇复盘。"
        if reason == "bili_video_share":
            return "像刚刷到一个有意思的 B 站视频,忍不住私下递给对方。要短,别写成影评或推荐文案。"
        if reason == "creative_share":
            return "像刚写小说写到一个小片段,有点想给对方看一眼。可以害羞、卡文或吐槽,别像正式投稿。"
        if reason in {"activity_share", "diary_share", "background_schedule"}:
            return "像顺手分享日常小事。讲得具体一点,像‘我跟你说’后面的那半句,不要解释自己为什么发来。"
        if reason in {"quiet_care", "state_share"}:
            return "像忽然有点惦记。关心要具体,但可以侧着说,不要像健康提醒或客服回访。"
        return "像私聊里随手冒出来的一句。短、自然,有一点在意就够,别把话说满。"

    def _format_action_prompt_context(self, action: str, action_context: str) -> str:
        context = str(action_context or "").strip()
        if not context:
            return "只发一条普通私聊文本,像顺手发给熟人的消息。"
        if "群聊分享线索：" in context:
            return (
                "你刚从共同群聊里看到一个有趣/值得分享的公开片段,现在想私下轻轻转述给对方。\n"
                f"{context}\n"
                "只挑最有意思的一点说,像朋友递八卦。不要逐条复盘,不要说自己在监控群聊,不要泄露隐私或评价群友关系。"
            )
        if "B站视频分享线索：" in context:
            return (
                "你刚刷到一个 B 站视频,现在想私下轻轻分享给对方。\n"
                f"{context}\n"
                "可以带上视频链接,但只用一句很自然的私聊口吻。不要说后台联动、插件、主动任务或日志,不要写成长推荐。"
            )
        if "小说创作分享线索：" in context:
            return (
                "你最近因为生活小事或梦境灵感开了一个小说坑,一直按自己的速度私下慢慢写。现在到了一个适合轻轻提起的小节点,想自然说一点。\n"
                f"{context}\n"
                "如果披露类型是 ask_impression,可以问对方读起来是什么感觉、哪个角色/意象更戳他,把反馈当作灵感参考；不要让用户替你决定接下来怎么写,也不要问“你希望走哪个方向”。否则只分享一小段或一句。不要把整篇写完,不要像定期汇报,不要说模型生成、后台任务或创作系统。"
            )
        if "screen_peek" in action:
            return (
                "你刚刚瞄到对方屏幕上大概是这些："
                f"{context}\n接下来像熟人私聊那样顺口说一句。别承认偷看,别复述屏幕,别写成分析。"
            )
        if "poke" in action:
            return (
                "你刚刚戳了对方一下。\n"
                f"补充背景：{context}\n"
                "接一句熟人间轻轻碰一下后的玩笑话就好,别解释机制,别报数,也别把没回复说成对方故意不理。"
            )
        if "voice" in action:
            return (
                "你刚刚发了一条语音。\n"
                f"补充背景：{context}\n"
                "再补一句像语音后面的短消息。别抄语音全文,也别提合成。"
            )
        if "photo_text" in action:
            return (
                "图片已经生成完成,稍后会作为单独的图片消息发送；你这里只需要写另一条配套的真人聊天文本。\n"
                f"补充背景：{context}\n"
                "不要说“图好了”“还在队列里”“等图出来”“已经发过去了”,不要写[图片],也不要解释生成流程。"
            )
        return context

    def _sanitize_action_boundaries(
        self,
        text: str,
        *,
        reason: str,
        action: str,
        action_context: str = "",
        has_real_image: bool = False,
    ) -> str:
        cleaned = self._soften_social_proactive_text(text, action=action)
        if not cleaned:
            return ""
        if "screen_peek" in action:
            photo_patterns = (
                "拍了张照片",
                "拍了照片",
                "拍了自拍",
                "自拍",
                "风景照",
                "窗外阳光",
                "要看看吗",
                "给你看照片",
                "发你照片",
                "看图",
            )
            if any(pattern in cleaned for pattern in photo_patterns):
                return ""
        if "poke" in action and "photo_text" not in action and "voice" not in action:
            cleaned = cleaned.replace("戳一戳", "戳你一下")
            cleaned = cleaned.replace("我刚刚戳了你", "我刚戳你了")
            cleaned = cleaned.replace("我刚刚戳了你一下", "我刚戳你了")
        if action == "voice":
            cleaned = cleaned.replace("我给你发了一条语音", "刚给你发了条语音")
            cleaned = cleaned.replace("我发了一条语音", "刚给你发了条语音")
            cleaned = cleaned.replace("我生成了一条语音", "刚给你发了条语音")
            cleaned = cleaned.replace("我合成了一条语音", "刚给你发了条语音")
            cleaned = cleaned.replace("要不要听", "你有空再听嘛")
            cleaned = cleaned.replace("要听吗", "你有空再听嘛")
        if action == "photo_text":
            if has_real_image:
                replacements = {
                    "我画了一张图": "刚看到一个画面",
                    "我刚画了张图": "刚看到一个画面",
                    "我生成了一张图": "刚看到一个画面",
                    "我做了张图": "刚看到一个画面",
                    "我生了一张图": "刚看到一个画面",
                    "我渲染了一张图": "刚看到一个画面",
                    "画面是": "刚好是",
                }
                for old, new in replacements.items():
                    cleaned = cleaned.replace(old, new)
                queue_replacements = {
                    "图好了": "",
                    "图片好了": "",
                    "照片好了": "",
                    "图生成好了": "",
                    "图片生成好了": "",
                    "还在队列里": "",
                    "还在排队": "",
                    "等图出来": "",
                    "等图片出来": "",
                    "已经发过去啦": "",
                    "已经发过去了": "",
                }
                for old, new in queue_replacements.items():
                    cleaned = cleaned.replace(old, new)
                for old in ("要看看吗", "要看吗", "想看吗"):
                    cleaned = cleaned.replace(old, "我先发你看")
                cleaned = self._deemphasize_state_report_preamble(cleaned, reason=reason)
                return self._soften_social_proactive_text(cleaned, action=action)
            replacements = {
                "拍了张照片": "想到一个画面",
                "拍了照片": "想到一个画面",
                "拍了美美的照片": "想到一个挺想拍下来的画面",
                "发你照片": "想跟你说说刚才那个画面",
                "给你看照片": "想跟你说说刚才那个画面",
                "要看看吗": "先跟你说一下",
                "要看吗": "先跟你说一下",
            }
            for old, new in replacements.items():
                cleaned = cleaned.replace(old, new)
        cleaned = self._deemphasize_state_report_preamble(cleaned, reason=reason)
        return self._soften_social_proactive_text(cleaned, action=action)

    def _is_overabstract_proactive_text(self, text: str, *, action: str) -> bool:
        cleaned = _single_line(text, 220)
        if not cleaned:
            return False
        weak_patterns = (
            "最近忙不忙",
            "发现你好像在忙",
            "数据有意思吗",
            "刚好想到你",
            "来找你一下",
            "碰你一下",
            "我就是来一下",
            "顺手来一下",
        )
        if any(token in cleaned for token in weak_patterns):
            return True
        if "screen_peek" in action and any(token in cleaned for token in ("还在忙啊", "看你在忙", "你好像在忙")):
            return True
        return False

    def _ground_proactive_text(
        self,
        text: str,
        *,
        reason: str,
        action: str,
        action_context: str,
    ) -> str:
        context = str(action_context or "")
        if "screen_peek" in action:
            if "逻辑分支" in context:
                return "你还在跟那个逻辑分支较劲啊。先别急,慢慢捋嘛。"
            if any(token in context for token in ("测试", "进度", "插件")):
                return "你还在盯那个进度啊。眼睛先歇一下啦。"
            return "你半天都没抬头了诶。先缓一口气。"
        if "poke" in action:
            return "我刚戳你了。怎么又不出声啦。"
        if "photo_text" in action:
            return text
        if "voice" in action:
            return "刚给你发了条语音。你有空再听嘛。"
        if reason == "quiet_care":
            return "感觉你这阵子都没怎么松下来。歇一小会儿嘛,又不会怎样。"
        if reason == "evening_greeting":
            return "都这个点了,你还没收工吗。别一直绷着啦。"
        if reason == "noon_greeting":
            return "中午了诶。你吃东西没有,别又随便糊弄过去。"
        if reason in {"activity_share", "diary_share", "background_schedule"}:
            return "我刚刚想到一件小事,就想跟你说一下。"
        return "我刚好空下来一点,就想问你一句。"

    async def _execute_proactive_action(
        self,
        action: str,
        user: dict[str, Any],
        name: str,
        reason: str,
    ) -> dict[str, Any]:
        normalized = str(action or "message").strip() or "message"
        parts = [part.strip() for part in normalized.split("+") if part.strip()]
        if not parts:
            parts = ["message"]
        contexts: list[str] = []
        extra_components: list[Any] = []
        summary_parts: list[str] = []
        effective_parts: list[str] = []
        for part in parts:
            payload = await self._execute_single_action(part, user, name, reason)
            contexts.append(str(payload.get("context") or "").strip())
            extra_components.extend(list(payload.get("extra_components") or []))
            summary = _single_line(payload.get("summary") or part, 60)
            if summary:
                summary_parts.append(summary)
            effective_action = _single_line(payload.get("effective_action") or part, 40)
            if effective_action:
                effective_parts.append(effective_action)
            if not bool(payload.get("success", True)):
                return {
                    "success": False,
                    "context": "\n".join(item for item in contexts if item),
                    "extra_components": [],
                    "summary": " + ".join(summary_parts) or normalized,
                    "effective_action": "+".join(effective_parts) or normalized,
                }
        return {
            "success": True,
            "context": "\n".join(item for item in contexts if item) or "message：只发送私聊文本",
            "extra_components": extra_components,
            "summary": " + ".join(summary_parts) or normalized,
            "effective_action": "+".join(effective_parts) or normalized,
        }

    async def _execute_single_action(
        self,
        action: str,
        user: dict[str, Any],
        name: str,
        reason: str,
    ) -> dict[str, Any]:
        fallback_action = self._fallback_action_for_unavailable(action, user)
        if fallback_action != action:
            logger.info(
                "[PrivateCompanion] 主动行为依赖不可用,已回退: requested=%s fallback=%s user=%s",
                action,
                fallback_action,
                str(user.get("user_id") or ""),
            )
            if fallback_action == "message":
                return {
                    "success": True,
                    "context": "message：只发送普通私聊文本",
                    "extra_components": [],
                    "summary": "文字",
                    "effective_action": "message",
                }
            return await self._execute_single_action(fallback_action, user, name, reason)
        if action == "screen_peek":
            context = await self._run_screen_peek_action(
                user,
                name,
                reason,
                quota_exempt=bool(user.get("planned_proactive_quota_exempt")),
            )
            return {
                "success": not self._is_unusable_screen_peek_context(context),
                "context": context,
                "extra_components": [],
                "summary": "窥屏",
                "effective_action": "screen_peek",
            }
        if action == "photo_text":
            context = await self._run_photo_text_action(user, name, reason)
            return {
                "success": "真实图片" in context and "图片路径：" in context,
                "context": context,
                "extra_components": [],
                "summary": "发图",
                "effective_action": "photo_text",
            }
        if action == "poke":
            context = await self._run_poke_action(user, name, reason)
            return {
                "success": context.startswith("poke：已"),
                "context": context,
                "extra_components": [],
                "summary": "戳了你一下",
                "effective_action": "poke",
            }
        if "voice" in action and "photo_text" not in action:
            payload = await self._run_voice_action(user, name, reason)
            payload.setdefault("summary", "留了句语音")
            payload.setdefault("effective_action", "voice")
            return payload
        return {"success": True, "context": "message：只发送私聊文本", "extra_components": [], "summary": "文字", "effective_action": "message"}

    def _is_unusable_screen_peek_context(self, context: str) -> bool:
        text = str(context or "").strip()
        if not text:
            return True
        fail_tokens = (
            "screen_peek：失败",
            "屏幕插件不可用",
            "未授权",
            "不可用",
            "没看清",
            "稍后再让我看看",
            "没有得到屏幕观察结果",
            "识屏分析失败",
        )
        return any(token in text for token in fail_tokens)

    async def _run_screen_peek_action(
        self,
        user: dict[str, Any],
        name: str,
        reason: str,
        *,
        quota_exempt: bool = False,
    ) -> str:
        if not self.enable_screen_glance_action:
            return "screen_peek：未授权,跳过"
        plugin = self._get_screen_companion_plugin()
        if plugin is None:
            return "screen_peek：屏幕插件不可用"
        target = str(user.get("umo") or "").strip()
        if not self._screen_glance_available(user, ignore_daily_limit=quota_exempt):
            return "screen_peek：今日额度或冷却未满足,跳过"
        async with self._data_lock:
            self._note_screen_peek_attempt(
                str(user.get("user_id") or user.get("umo") or name),
                reason=reason,
                count_daily=not quota_exempt,
            )
            self._save_data_sync()
        event = None
        if target and hasattr(plugin, "_create_virtual_event"):
            try:
                event = plugin._create_virtual_event(target)
            except Exception as e:
                logger.debug(f"[PrivateCompanion] 创建屏幕虚拟事件失败: {e}")
        prompt = (
            f"这是一次用户已授权的主动陪伴行为。请只做视觉观察,"
            f"用很短的话描述用户电脑当前大概在看什么、做什么、是不是像在忙。"
            f"不要直接对用户说话,不要安慰、提醒、关心、陪伴,不要输出隐私细节、账号、完整文本、聊天内容。"
            f"只留一个内部观察印象。主动原因：{reason}"
        )
        try:
            result = await plugin._invoke_screen_skill(
                event,
                request_prompt=prompt,
                history_user_text=f"主动陪伴想轻轻看一眼 {name} 现在在忙什么。",
                task_id="private_companion_screen_peek",
            )
            return "screen_peek：\n" + (_single_line(result, 300) if result else "没有得到屏幕观察结果")
        except Exception as e:
            logger.warning(f"[PrivateCompanion] screen_peek 主动行为失败: {e}")
            return f"screen_peek：失败,{e}"

    def _get_screen_companion_plugin(self) -> Any:
        for module_name in ("astrbot_plugin_screen_companion.main", "data.plugins.astrbot_plugin_screen_companion.main"):
            try:
                module = importlib.import_module(module_name)
                plugin = getattr(module, "_screen_companion_tool_plugin", None)
                if plugin is not None and callable(getattr(plugin, "_invoke_screen_skill", None)):
                    return plugin
            except Exception:
                continue
        for module in list(sys.modules.values()):
            try:
                plugin = getattr(module, "_screen_companion_tool_plugin", None)
                if plugin is not None and callable(getattr(plugin, "_invoke_screen_skill", None)):
                    return plugin
            except Exception:
                continue
        return None

    async def _run_poke_action(
        self,
        user: dict[str, Any],
        name: str,
        reason: str,
        *,
        explicit_count: int | None = None,
    ) -> str:
        if not self.enable_poke_action:
            return "poke：未启用"
        client = self._resolve_aiocqhttp_client()
        if client is None:
            return "poke：未找到可用的 QQ 客户端"
        user_id = str(user.get("user_id") or "").strip()
        if not user_id.isdigit():
            return "poke：目标 QQ 号无效"
        group_id = self._extract_group_id_from_umo(str(user.get("umo") or ""))
        try:
            from data.plugins.astrbot_plugin_pokepro.core.send_poke import PokeSender
        except Exception:
            try:
                from astrbot_plugin_pokepro.core.send_poke import PokeSender
            except Exception as e:
                return f"poke：pokepro 插件不可用,{e}"
        try:
            poke_count = max(1, int(explicit_count)) if explicit_count else self._choose_poke_repeat_count(user, reason)
            async with self._data_lock:
                current = self._get_user(user_id)
                current["poke_echo_suppress_until"] = _now_ts() + max(6.0, poke_count * 1.6 + 3.0)
                self._save_data_sync()
            for index in range(poke_count):
                await PokeSender.poke_func(client=client, user_id=user_id, group_id=group_id)
                if index + 1 < poke_count:
                    await asyncio.sleep(random.uniform(0.35, 0.9))
            if poke_count <= 1:
                return f"poke：已轻轻戳了 {name} 一下\n主动原因：{reason}"
            return f"poke：已轻轻连着戳了 {name} {poke_count} 下\n主动原因：{reason}"
        except Exception as e:
            logger.warning(f"[PrivateCompanion] poke 主动行为失败: {e}")
            return f"poke：失败,{e}"

    def _choose_poke_repeat_count(self, user: dict[str, Any], reason: str) -> int:
        max_times = max(1, self.poke_action_max_times)
        if max_times <= 1:
            return 1
        motive = _single_line(
            user.get("planned_proactive_motive") or user.get("last_proactive_motive"),
            120,
        )
        profile = self._persona_action_profile()
        weights: list[tuple[int, float]] = [(1, 1.0)]
        second_weight = 0.45
        third_weight = 0.12
        if profile.get("playful"):
            second_weight += 0.22
            third_weight += 0.1
        if profile.get("clingy"):
            second_weight += 0.12
            third_weight += 0.06
        if reason in {"quiet_care", "check_in"}:
            second_weight += 0.08
        if any(token in motive for token in ("闹你", "刷存在感", "碰你一下", "没忍住", "冒个头")):
            second_weight += 0.15
        if any(token in motive for token in ("偷偷看", "放心不下", "想起你", "不想吵你")):
            third_weight += 0.04
        weights.append((2, second_weight))
        if max_times >= 3:
            weights.append((3, third_weight))
        return int(self._weighted_choice([(str(count), weight) for count, weight in weights]))

    def _choose_pre_message_poke_count(
        self,
        user: dict[str, Any],
        reason: str,
        *,
        action: str = "message",
        motive: str = "",
    ) -> int:
        if not self._poke_available():
            return 0
        profile = self._persona_action_profile()
        probability = 0.12
        if reason in {"check_in", "quiet_care", "important_date_share"}:
            probability += 0.22
        if profile.get("playful"):
            probability += 0.14
        if profile.get("clingy"):
            probability += 0.08
        if action in {"voice", "photo_text"}:
            probability -= 0.02
        motive_text = str(motive or user.get("planned_proactive_motive") or "")
        if any(token in motive_text for token in ("闹你", "戳", "碰碰你", "确认一下", "放心不下", "叫你一声")):
            probability += 0.08
        probability = max(0.0, min(0.72, probability))
        if random.random() >= probability:
            return 0
        return self._choose_poke_repeat_count(user, reason)

    async def _maybe_run_pre_message_poke(
        self,
        user: dict[str, Any],
        name: str,
        reason: str,
        *,
        action: str = "message",
        motive: str = "",
    ) -> tuple[int, str]:
        poke_count = self._choose_pre_message_poke_count(
            user,
            reason,
            action=action,
            motive=motive,
        )
        if poke_count <= 0:
            return 0, ""
        context = await self._run_poke_action(user, name, reason, explicit_count=poke_count)
        if not context.startswith("poke：已"):
            return 0, context
        return poke_count, context

    async def _run_voice_action(self, user: dict[str, Any], name: str, reason: str) -> dict[str, Any]:
        if not self.enable_voice_action:
            return {"success": False, "context": "voice：未启用", "extra_components": [], "summary": "语音"}
        target = str(user.get("umo") or "").strip()
        if not target:
            return {"success": False, "context": "voice：缺少目标会话,无法发送语音", "extra_components": [], "summary": "语音"}
        voice_text = await self._build_voice_note_text(user, name, reason, target=target)
        components, audio_note = await self._create_voice_record_component(target, voice_text)
        if not components:
            return {
                "success": False,
                "context": (
                    "voice：语音生成失败\n"
                    f"想说的话：{voice_text}\n"
                    f"失败原因：{_single_line(audio_note, 160)}"
                ),
                "extra_components": [],
                "summary": "语音",
            }
        return {
            "success": True,
            "context": (
                "voice：已生成真实语音\n"
                f"语音内容：{self._strip_tts_markup(voice_text)}\n"
                f"真实语音文件：{audio_note}"
            ),
            "extra_components": components,
            "summary": "留了句语音",
        }

    def _resolve_aiocqhttp_client(self) -> Any:
        platform_manager = getattr(self.context, "platform_manager", None)
        platforms = list(getattr(platform_manager, "platform_insts", []) or [])
        for platform in platforms:
            platform_names = set()
            try:
                meta = platform.meta()
                platform_names.add(str(getattr(meta, "id", "") or "").strip())
                platform_names.add(str(getattr(meta, "name", "") or "").strip())
            except Exception:
                pass
            for attr in ("bot", "client", "_bot", "_client", "cqhttp"):
                client = getattr(platform, attr, None)
                if client is not None and (
                    "aiocqhttp" in platform_names
                    or "default(aiocqhttp)" in platform_names
                    or hasattr(client, "friend_poke")
                    or hasattr(client, "group_poke")
                ):
                    return client
        return None

    def _onebot_action_result_ok(self, result: Any) -> bool:
        if result is None:
            return True
        if isinstance(result, dict):
            status = str(result.get("status") or result.get("result") or "").strip().lower()
            if status in {"failed", "fail", "error", "nok"}:
                return False
            retcode = result.get("retcode", result.get("code", None))
            if retcode is not None:
                try:
                    return int(retcode) == 0
                except Exception:
                    return False
        return True

    async def _call_onebot_action(self, client: Any, action: str, **params: Any) -> bool:
        candidates = (
            "call_action",
            "call_api",
            "api",
        )
        for attr in candidates:
            func = getattr(client, attr, None)
            if not callable(func):
                continue
            try:
                result = func(action, **params)
                if hasattr(result, "__await__"):
                    result = await result
                if self._onebot_action_result_ok(result):
                    return True
            except TypeError:
                try:
                    result = func(action, params)
                    if hasattr(result, "__await__"):
                        result = await result
                    if self._onebot_action_result_ok(result):
                        return True
                except Exception:
                    continue
            except Exception:
                continue
        func = getattr(client, action, None)
        if callable(func):
            try:
                result = func(**params)
                if hasattr(result, "__await__"):
                    result = await result
                return self._onebot_action_result_ok(result)
            except Exception:
                return False
        return False

    async def _maybe_send_input_status(self, umo: str, text: str = "") -> None:
        if not umo or ":FriendMessage:" not in str(umo):
            return
        session = self._parse_message_session(umo)
        if not session:
            return
        user_id = str(getattr(session, "session_id", "") or "").strip()
        if not user_id.isdigit():
            return
        now = _now_ts()
        last_at = _safe_float(self._last_input_status_at.get(user_id), 0)
        if now - last_at < 45:
            return
        client = self._resolve_aiocqhttp_client()
        if client is None:
            return
        duration = max(1.2, min(4.5, len(str(text or "")) / 18))
        variants = (
            {"user_id": int(user_id), "event_type": 1},
            {"user_id": int(user_id), "status": 1},
            {"user_id": int(user_id), "typing": True},
        )
        ok = False
        for params in variants:
            ok = await self._call_onebot_action(client, "set_input_status", **params)
            if ok:
                break
        if not ok:
            return
        self._last_input_status_at[user_id] = now
        await asyncio.sleep(random.uniform(duration * 0.55, duration))

    def _qq_presence_codes(self, mode: str) -> tuple[int, int, str]:
        normalized = str(mode or "").strip().lower()
        table = {
            "online": (10, 0, "在线"),
            "away": (30, 0, "离开"),
            "busy": (50, 0, "忙碌"),
            "invisible": (40, 0, "隐身"),
        }
        return table.get(normalized, table["online"])

    async def _set_qq_online_presence(self, mode: str) -> tuple[bool, str]:
        client = self._resolve_aiocqhttp_client()
        if client is None:
            return False, "未找到可用 QQ 客户端"
        status, ext_status, label = self._qq_presence_codes(mode)
        variants = (
            {"status": status, "ext_status": ext_status, "battery_status": 0},
            {"status": status, "ext_status": ext_status},
            {"status": status},
            {"status_id": status},
            {"mode": str(mode or "online")},
        )
        for params in variants:
            if await self._call_onebot_action(client, "set_online_status", **params):
                return True, label
        return False, f"平台不支持 set_online_status：{label}"

    async def _set_qq_custom_presence(self, text: str) -> tuple[bool, str]:
        client = self._resolve_aiocqhttp_client()
        if client is None:
            return False, "未找到可用 QQ 客户端"
        custom_text = _single_line(text, 8)
        if not custom_text:
            return False, "自定义状态文本为空,跳过同步"
        variants = (
            ("set_diy_online_status", {"face_id": 21, "face_type": 1, "wording": custom_text}),
            ("set_diy_online_status", {"face_id": "21", "face_type": "1", "wording": custom_text}),
            ("set_diy_online_status", {"faceId": 21, "faceType": 1, "wording": custom_text}),
            ("set_diy_online_status", {"id": 21, "face_type": 1, "wording": custom_text}),
            ("set_diy_online_status", {"wording": custom_text}),
            ("set_diy_online_status", {"face_id": 21, "text": custom_text}),
            ("set_diy_online_status", {"faceId": 21, "text": custom_text}),
            ("set_diy_online_status", {"id": 21, "text": custom_text}),
            ("set_diy_online_status", {"text": custom_text}),
            ("set_custom_online_status", {"text": custom_text}),
            ("set_custom_online_status", {"face_id": 21, "text": custom_text}),
        )
        for action, params in variants:
            if await self._call_onebot_action(client, action, **params):
                return True, f"自定义状态：{custom_text}"
        return False, f"平台不支持自定义状态：{custom_text}"

    async def _reset_stale_qq_presence_if_needed(self) -> None:
        if not self.enable_qq_presence_sync:
            return
        await asyncio.sleep(2)
        async with self._data_lock:
            state = self.data.get("qq_presence_state", {})
            if not isinstance(state, dict) or str(state.get("date") or "") == _today_key():
                return
            previous_mode = str(state.get("mode") or "")
        ok, note = await self._set_qq_online_presence("online")
        async with self._data_lock:
            state = self.data.setdefault("qq_presence_state", {})
            if not isinstance(state, dict):
                state = {}
                self.data["qq_presence_state"] = state
            state.update(
                {
                    "date": _today_key(),
                    "plan_date": "",
                    "detail_key": "",
                    "mode": "online",
                    "custom_text": "",
                    "reason": "清理跨日 QQ 状态",
                    "updated_at": _now_ts(),
                    "ok": bool(ok),
                    "note": _single_line(f"跨日重置：{previous_mode or 'unknown'} -> {note}", 120),
                }
            )
            self._save_data_sync()

    def _extract_group_id_from_umo(self, target: str) -> int | None:
        text = str(target or "").strip()
        match = re.search(r":GroupMessage:(\d+)$", text)
        if not match:
            return None
        try:
            return int(match.group(1))
        except Exception:
            return None

    async def _build_voice_note_text(
        self,
        user: dict[str, Any],
        name: str,
        reason: str,
        *,
        target: str = "",
    ) -> str:
        requirement = self._voice_requirement_profile(target)
        framework_text = await self._generate_voice_note_via_framework(
            user,
            name,
            reason,
            target=target,
        )
        if framework_text:
            spoken = str(framework_text).strip()
            if requirement["strict"] and not self._voice_text_matches_requirement(spoken, requirement):
                logger.info(
                    "[PrivateCompanion] 主动语音未命中格式要求,进行框架严格重试: target=%s summary=%s",
                    target,
                    requirement["summary"],
                )
                retry_text = await self._generate_voice_note_via_framework(
                    user,
                    name,
                    reason,
                    target=target,
                    strict_tts=True,
                )
                if retry_text:
                    spoken = str(retry_text).strip()
            if "<tts>" not in spoken:
                spoken = _single_line(spoken, self.voice_action_max_chars)
                spoken = re.sub(r"[“”\"'`]", "", spoken).strip()
            if requirement["strict"] and not self._voice_text_matches_requirement(spoken, requirement):
                repair_prompt = self._build_voice_repair_prompt(
                    spoken=spoken,
                    requirement=requirement,
                    target=target,
                )
                repaired = await self._llm_call(
                    repair_prompt,
                    max_tokens=140,
                    provider_id=self._task_provider(self.voice_prompt_provider_id, self.mai_style_provider_id),
                    task="voice_repair",
                )
                if repaired:
                    spoken = str(repaired).strip()
                    if "<tts>" not in spoken:
                        spoken = _single_line(spoken, self.voice_action_max_chars)
                        spoken = re.sub(r"[“”\"'`]", "", spoken).strip()
            if requirement["strict"] and not self._voice_text_matches_requirement(spoken, requirement):
                logger.warning(
                    "[PrivateCompanion] 主动语音仍未完全命中格式要求,保留当前结果: target=%s summary=%s text=%s",
                    target,
                    requirement["summary"],
                    self._strip_tts_markup(spoken),
                )
            else:
                logger.info(
                    "[PrivateCompanion] 主动语音最终文本已命中格式要求: target=%s text=%s",
                    target,
                    self._strip_tts_markup(spoken),
                )
            return spoken
        persona = self._get_default_persona_prompt()
        state = self.data.get("daily_state", {})
        last_user_message = _single_line(user.get("last_user_message"), 80)
        profile = self._relationship_profile(user)
        tts_prompt = self._get_tts_prompt_text(target)
        prompt = f"""
你正在替角色写一条马上要发出去的语音。这条语音是真的会被 TTS 念出来,不是文字陪聊。

【人格】
{persona}

【对象】
称呼：{name}
关系：{profile['level']}｜偏好：{profile['preference']}
最近一句：{last_user_message or '（暂无）'}

【主动原因】
{reason}

【当前状态】
{self._format_state_for_prompt(state if isinstance(state, dict) else {})}

【当前会话 TTS 规则】
{tts_prompt or "（当前没有额外 TTS 提示词,就按人格自己的语音习惯来）"}

要求：
1. 优先遵守人格里自己写的特殊 TTS 规则；如果人格或当前会话 TTS 规则要求使用 <tts>...</tts>、日语、情绪标签或双语格式,就按那个格式输出。
2. 如果没有明确格式要求,就只输出适合真正念出来的一小句语音内容,不要解释。
3. 整体要短,适合私聊语音,不像朗读稿,也不要太正式；纯中文可控制在 {self.voice_action_max_chars} 个字以内。
4. 可以有一点嘴硬、黏人、藏着的想念,但不要把喜欢说满。
5. 不要提 AI、模型、插件、TTS、语音合成这些词。
""".strip()
        text = await self._llm_call(
            prompt,
            max_tokens=120,
            provider_id=self._task_provider(self.voice_prompt_provider_id, self.mai_style_provider_id),
            task="voice",
        )
        spoken = str(text or "").strip()
        if not spoken:
            spoken = random.choice(VOICE_FALLBACK_TEMPLATES)
        if "<tts>" not in spoken:
            spoken = _single_line(spoken, self.voice_action_max_chars)
            spoken = re.sub(r"[“”\"'`]", "", spoken).strip()
        if requirement["strict"] and not self._voice_text_matches_requirement(spoken, requirement):
            repair_prompt = self._build_voice_repair_prompt(
                spoken=spoken,
                requirement=requirement,
                target=target,
            )
            repaired = await self._llm_call(
                repair_prompt,
                max_tokens=140,
                provider_id=self._task_provider(self.voice_prompt_provider_id, self.mai_style_provider_id),
                task="voice_repair",
            )
            if repaired:
                spoken = str(repaired).strip()
                if "<tts>" not in spoken:
                    spoken = _single_line(spoken, self.voice_action_max_chars)
                    spoken = re.sub(r"[“”\"'`]", "", spoken).strip()
        return spoken

    async def _create_voice_record_component(self, target: str, spoken_text: str) -> tuple[list[Any], str]:
        if not spoken_text:
            return [], "语音内容为空"
        try:
            config = self.context.get_config(target)
        except Exception:
            try:
                config = self.context.get_config()
            except Exception as e:
                return [], f"读取配置失败：{e}"
        provider_settings = dict(config.get("provider_tts_settings", {}) or {})
        if not provider_settings.get("enable", False):
            return [], "当前会话未启用 TTS"
        try:
            tts_provider = self.context.get_using_tts_provider(target)
        except Exception as e:
            return [], f"读取 TTS provider 失败：{e}"
        if not tts_provider:
            return [], "当前会话没有可用的 TTS provider"
        if "<tts>" in spoken_text and "</tts>" in spoken_text:
            components, note = await self._build_tts_modify_components(
                spoken_text,
                tts_provider,
                provider_settings,
                config,
            )
            if components:
                return components, note
        try:
            audio_path = await tts_provider.get_audio(spoken_text)
        except Exception as e:
            logger.warning(f"[PrivateCompanion] voice 主动行为生成失败: {e}")
            return [], str(e)
        if not audio_path:
            return [], "TTS 没有返回音频文件"
        try:
            audio_file = Path(audio_path).resolve()
            expected_dir = Path(get_astrbot_data_path()).resolve()
            if not audio_file.is_relative_to(expected_dir):
                return [], f"语音文件路径不安全：{audio_path}"
        except Exception as e:
            return [], str(e)
        final_ref = str(audio_path)
        if provider_settings.get("use_file_service", False):
            callback_api_base = str(config.get("callback_api_base", "") or "").strip()
            if callback_api_base:
                try:
                    token = await file_token_service.register_file(str(audio_path))
                    final_ref = f"{callback_api_base}/api/file/{token}"
                except Exception as e:
                    logger.warning(f"[PrivateCompanion] 注册语音文件失败,将回退到本地路径: {e}")
        try:
            component = Record(file=final_ref, url=final_ref)
        except TypeError:
            try:
                component = Record(file=final_ref)
            except TypeError:
                component = Record.fromFileSystem(str(audio_path))
        return [component], str(audio_path)

    def _get_tts_prompt_text(self, target: str) -> str:
        try:
            config = self.context.get_config(target) if target else self.context.get_config()
        except Exception:
            try:
                config = self.context.get_config()
            except Exception:
                return ""
        provider_settings = dict(config.get("provider_tts_settings", {}) or {})
        return str(provider_settings.get("tts_prompt", "") or "").strip()

    def _voice_requirement_profile(self, target: str) -> dict[str, Any]:
        persona = self._get_default_persona_prompt()
        tts_prompt = self._get_tts_prompt_text(target)
        combined = f"{persona}\n{tts_prompt}".lower()
        require_tts_tags = "<tts>" in combined or "</tts>" in combined
        japanese_markers = ("日语", "日文", "日本語", "假名", "片假名", "平假名", "日语语音", "日文语音")
        bilingual_markers = ("双语", "中日双语", "中文文本", "中文显示", "日语语音")
        prefer_japanese = any(marker in combined for marker in japanese_markers)
        prefer_bilingual = any(marker in combined for marker in bilingual_markers)
        strict = require_tts_tags or prefer_japanese or prefer_bilingual
        parts: list[str] = []
        if require_tts_tags:
            parts.append("需要 <tts> 标签")
        if prefer_japanese:
            parts.append("语音正文优先日语")
        if prefer_bilingual:
            parts.append("可能需要双语/日中并存格式")
        if not parts:
            parts.append("没有明显额外语音格式要求")
        return {
            "strict": strict,
            "require_tts_tags": require_tts_tags,
            "prefer_japanese": prefer_japanese,
            "prefer_bilingual": prefer_bilingual,
            "summary": "；".join(parts),
        }

    def _voice_text_matches_requirement(self, spoken: str, requirement: dict[str, Any]) -> bool:
        text = str(spoken or "").strip()
        if not text:
            return False
        if requirement.get("require_tts_tags") and ("<tts>" not in text.lower() or "</tts>" not in text.lower()):
            return False
        core = self._strip_tts_markup(text)
        if requirement.get("prefer_japanese"):
            if not re.search(r"[\u3040-\u30ff\u31f0-\u31ff]", core):
                return False
        return True

    def _build_voice_repair_prompt(
        self,
        *,
        spoken: str,
        requirement: dict[str, Any],
        target: str,
    ) -> str:
        persona = self._get_default_persona_prompt()
        tts_prompt = self._get_tts_prompt_text(target)
        return f"""
你要把下面这句主动语音修正成符合当前语音规则的最终版本。

【人格】
{persona}

【当前会话 TTS 规则】
{tts_prompt or "（当前没有额外 TTS 提示词）"}

【必须满足的格式重点】
{requirement.get("summary") or "按人格自己的语音习惯处理"}

【当前版本】
{spoken}

要求：
1. 只输出修正后的最终语音内容，不要解释。
2. 如果需要 <tts>...</tts>，必须补齐。
3. 如果要求日语语音，就让真正会被念出来的那一部分变成自然的日语，而不是普通中文。
4. 如果没有强制格式，也保持私聊语音的自然感。
""".strip()

    async def _build_tts_modify_components(
        self,
        spoken_text: str,
        tts_provider: Any,
        provider_settings: dict[str, Any],
        config: dict[str, Any],
    ) -> tuple[list[Any], str]:
        plugin = self._get_tts_modify_plugin(config)
        if plugin is None:
            return [], "未找到 tts_modify 插件"
        try:
            components = await plugin._process_tts_tags(
                spoken_text,
                tts_provider,
                provider_settings,
                config,
            )
        except Exception as e:
            logger.warning(f"[PrivateCompanion] tts_modify 处理主动语音失败: {e}")
            return [], str(e)
        audio_note = self._extract_record_note(components)
        return components or [], audio_note or "已通过 tts_modify 生成语音"

    def _get_tts_modify_plugin(self, config: dict[str, Any]) -> Any:
        for module_name in ("astrbot_plugin_tts_modify.main", "data.plugins.astrbot_plugin_tts_modify.main"):
            try:
                module = importlib.import_module(module_name)
                plugin_cls = getattr(module, "TTSModifyPlugin", None)
                if plugin_cls is not None:
                    return plugin_cls(self.context, config)
            except Exception:
                continue
        return None

    def _extract_record_note(self, components: list[Any]) -> str:
        for component in components or []:
            file_value = str(getattr(component, "file", "") or "").strip()
            url_value = str(getattr(component, "url", "") or "").strip()
            if file_value:
                return file_value
            if url_value:
                return url_value
        return ""

    def _strip_tts_markup(self, text: str) -> str:
        stripped = re.sub(r"</?tts>", "", str(text or ""), flags=re.IGNORECASE)
        stripped = stripped.replace("\r", "\n")
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        return _single_line(" ".join(lines), 120)

    async def _run_photo_text_action(self, user: dict[str, Any], name: str, reason: str) -> str:
        if not self.enable_photo_text_action:
            return "photo_text：未启用"
        if not self._photo_text_available(user):
            return "photo_text：今日发图额度已用完或生图后端不可用,不能假装已经拍照"
        if not self._photo_text_available():
            return "photo_text：当前没有可用的生图后端,不能假装已经拍照"

        scene = await self._build_photo_scene_prompt(user, name, reason)
        workflow_kind = scene.get("kind", "text2img")
        session_key = str(user.get("umo") or user.get("user_id") or name)
        backend_name, image_path, workflow_note = await self._generate_photo_image(
            workflow_kind=workflow_kind,
            prompt_text=scene["prompt"],
            session_key=session_key,
        )
        if not image_path:
            return (
                "photo_text：生图失败,不能假装已经拍照\n"
                f"画面草稿：{scene['caption']}\n"
                f"失败原因：{_single_line(workflow_note, 160)}"
            )
        async with self._data_lock:
            self._note_photo_generation_attempt(str(user.get("user_id") or ""), image_path=image_path)
            self._save_data_sync()
        return (
            f"photo_text：已通过 {backend_name} 生成真实图片\n"
            f"图片类型：{workflow_kind}\n"
            f"后端：{backend_name}\n"
            f"图片路径：{image_path}\n"
            f"画面：{scene['caption']}\n"
            f"生图提示：{_single_line(scene['prompt'], 240)}"
        )

    def _choose_photo_workflow_name(self, kind: str) -> str:
        normalized = str(kind or "").strip().lower()
        if normalized in {"selfie", "portrait", "自拍", "人像"}:
            return self.comfyui_selfie_workflow_name or self.comfyui_text2img_workflow_name
        return self.comfyui_text2img_workflow_name or self.comfyui_selfie_workflow_name

    async def _generate_photo_image(
        self,
        *,
        workflow_kind: str,
        prompt_text: str,
        session_key: str,
    ) -> tuple[str, str, str]:
        preferred = self.photo_generation_backend
        if preferred == "comfyui":
            if not self._comfyui_photo_available():
                return "ComfyUI", "", "ComfyUI 后端不可用或未配置"
            workflow_name = self._choose_photo_workflow_name(workflow_kind)
            if not workflow_name:
                return "ComfyUI", "", f"未配置 {workflow_kind} 对应的 ComfyUI 工作流"
            image_path, note = await self._run_comfyui_photo_workflow(
                workflow_name,
                prompt_text,
                session_key=session_key,
            )
            return "ComfyUI", image_path, note
        if preferred == "external":
            if not self._external_photo_available():
                return "在线图片 API", "", "在线图片 API 后端不可用或未配置"
            image_path, note = await self._run_external_photo_generation(
                prompt_text,
                session_key=session_key,
            )
            return "在线图片 API", image_path, note
        if self._comfyui_photo_available():
            workflow_name = self._choose_photo_workflow_name(workflow_kind)
            if workflow_name:
                image_path, note = await self._run_comfyui_photo_workflow(
                    workflow_name,
                    prompt_text,
                    session_key=session_key,
                )
                if image_path:
                    return "ComfyUI", image_path, note
                comfyui_note = note
            else:
                comfyui_note = f"未配置 {workflow_kind} 对应的 ComfyUI 工作流"
        else:
            comfyui_note = "ComfyUI 后端不可用或未配置"
        if self._external_photo_available():
            image_path, note = await self._run_external_photo_generation(
                prompt_text,
                session_key=session_key,
            )
            if image_path:
                return "在线图片 API", image_path, note
            return "在线图片 API", "", f"ComfyUI 失败：{comfyui_note}；在线图片 API 失败：{note}"
        return "ComfyUI", "", comfyui_note

    async def _build_photo_scene_prompt(
        self, user: dict[str, Any], name: str, reason: str
    ) -> dict[str, str]:
        persona = self._get_default_persona_prompt()
        state = self.data.get("daily_state", {})
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        style_name, style_instruction = self._get_photo_style_instruction()
        topic_hint = _single_line(user.get("planned_proactive_topic"), 60)
        motive_hint = _single_line(user.get("planned_proactive_motive"), 120)
        prompt = f"""
请根据 AstrBot 默认人格和主动原因,生成一张要通过 ComfyUI 工作流制作的“社交媒体随手拍/自拍/生活碎片图”提示词。

【人格】
{persona}

【收信人】
{name}

【当前拟人状态】
{self._format_state_for_prompt(state if isinstance(state, dict) else {})}

【当前日程背景】
{self._format_plan_item_for_prompt(current_item)}

【这次想分享的画面钩子】
话题：{topic_hint or '（未指定）'}
那一刻的小动机：{motive_hint or '（未指定）'}

【内容选择菜单】
{self._format_content_choice_options_for_prompt()}

【生图风格】
{style_name}
风格要求：{style_instruction}

主动原因：{reason}

输出 JSON：
{{
  "kind": "selfie 或 text2img；自拍/人像用 selfie,其他随手拍用 text2img",
  "prompt": "给 ComfyUI 的中文生图提示词,包含主体、场景、光线、构图、情绪；不要写聊天口吻",
  "caption": "图片完成后可转述给最终私聊模型的一句话画面描述"
}}

要求：
1. 画面必须符合当前时间、日程和人格,不要把身份设定里没有的场景、职业、服装或外观细节写进去。
2. 图片不要总是天气或窗外。先从“内容选择菜单”里选一个方向,再结合当前日程、话题和人格生成具体主体。
3. 可以是路上风景、桌面小物、随手自拍、偶遇小动物等,但不要每次都是自拍；没有明确自拍动机时优先 text2img。
4. `prompt` 里要明确体现上面的风格要求。
5. 不要包含 NSFW、隐私信息、用户真实电脑画面。
6. 如果“话题”已经很具体,就优先把那个具体视觉主体画出来；如果话题很抽象,从菜单里另选一个适合拍照的具体画面。不要退回成泛泛的天气图、手部动作或普通记录照。
""".strip()
        text = await self._llm_call(
            prompt,
            max_tokens=260,
            provider_id=self._task_provider(self.photo_prompt_provider_id, self.mai_style_provider_id),
            task="photo_prompt",
        )
        payload = self._extract_json_payload(text or "")
        if isinstance(payload, dict):
            kind = _single_line(payload.get("kind"), 20).lower()
            image_prompt = _single_line(payload.get("prompt"), 600)
            caption = _single_line(payload.get("caption"), 180)
        else:
            kind = "text2img"
            image_prompt = _single_line(text, 600)
            caption = image_prompt
        if kind not in {"selfie", "portrait", "自拍", "人像", "text2img", "scene", "photo", "风景"}:
            kind = "text2img"
        if kind in {"portrait", "自拍", "人像"}:
            kind = "selfie"
        if kind in {"scene", "photo", "风景"}:
            kind = "text2img"
        if not image_prompt:
            current = self._format_plan_item_for_prompt(current_item)
            image_prompt = (
                f"社交媒体随手拍,当前背景：{current},温柔自然的生活感,"
                f"清晰构图,柔和光线,{style_instruction}"
            )
        if not caption:
            caption = "今天看到一个很适合拍下来分享的小画面。"
        return {"kind": kind, "prompt": image_prompt, "caption": caption}

    def _get_photo_style_instruction(self) -> tuple[str, str]:
        style = str(self.photo_generation_style or "真实").strip()
        if style == "二次元":
            return "二次元", "日系二次元插画风,人物与场景干净细腻,保留生活感,不要写实摄影质感"
        if style == "其他":
            custom = _single_line(self.photo_generation_style_custom_prompt, 200)
            if custom:
                return "其他", custom
            return "其他", "保持统一审美风格,自然生活感,避免默认写实照片风格"
        return "真实", "真实摄影风格,像手机随手拍到的生活照片,光线自然,细节可信"

    async def _run_comfyui_photo_workflow(
        self, workflow_name: str, prompt_text: str, session_key: str
    ) -> tuple[str, str]:
        module = self._get_comfyui_module()
        if module is None:
            return "", "ComfyUI 插件不可用"
        config = getattr(module, "_plugin_config", None)
        if not config:
            return "", "ComfyUI 插件配置不可用"
        try:
            server_ip, client_id = module._get_server_config(config)
            workflow_dir = module._get_workflow_dir()
            workflow_file = module.find_workflow_file(
                workflow_name,
                1,
                0,
                0,
                workflow_dir,
            )
            text_count = 1
            if not workflow_file:
                workflow_file, text_count = self._find_photo_workflow_with_text_count(
                    module,
                    workflow_dir,
                    workflow_name,
                )
            if not workflow_file:
                return "", f"未找到匹配工作流 {workflow_name}（需要 images=0, videos=0）"
            debug = bool(
                getattr(config, "debug_mode", False)
                if not isinstance(config, dict)
                else config.get("debug_mode", False)
            )
            workflow = module.ComfyUIWorkflow(server_ip, client_id)
            workflow.load_workflow_api(workflow_file)
            prompt_id = await workflow.submit_only(
                [],
                [prompt_text] * max(1, text_count),
                [],
                debug=debug,
            )
            deadline = _now_ts() + self.comfyui_photo_wait_seconds
            while _now_ts() < deadline:
                url, file_type, texts = await module._get_result_for_prompt(server_ip, prompt_id)
                if url and file_type == "image":
                    temp_path = await module._download_image_to_temp(url)
                    if not temp_path:
                        return "", "工作流完成但图片下载失败"
                    persistent_path = await module._save_image_to_persistent_path(
                        temp_path,
                        session_key or "private_companion",
                    )
                    return persistent_path or temp_path, "ok"
                if url and file_type != "image":
                    return "", f"工作流输出不是图片：{file_type}"
                await asyncio.sleep(2)
            return "", f"等待 ComfyUI 结果超时（{self.comfyui_photo_wait_seconds}s）"
        except Exception as e:
            logger.warning(f"[PrivateCompanion] photo_text 生图失败: {e}", exc_info=True)
            return "", str(e)

    def _external_image_endpoint(self) -> str:
        base = str(self.external_image_api_base_url or "").strip().rstrip("/")
        if not base:
            return ""
        if base.endswith("/images/generations"):
            return base
        return f"{base}/images/generations"

    def _sanitize_external_image_size(self) -> str:
        raw = str(self.external_image_api_size or "1024x1024").strip().lower()
        if re.fullmatch(r"\d{2,5}x\d{2,5}", raw):
            return raw
        return "1024x1024"

    async def _save_external_generated_image(
        self,
        image_bytes: bytes,
        *,
        session_key: str,
        ext: str = ".png",
    ) -> str:
        if not image_bytes:
            return ""
        safe_ext = ext if ext.startswith(".") else f".{ext}"
        if safe_ext.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
            safe_ext = ".png"
        out_dir = Path(self.data_dir) / "generated_photos"
        out_dir.mkdir(parents=True, exist_ok=True)
        session_part = re.sub(r"[^a-zA-Z0-9._-]+", "_", str(session_key or "private_companion"))[:60] or "private_companion"
        file_path = out_dir / f"{session_part}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{safe_ext}"
        await asyncio.to_thread(file_path.write_bytes, image_bytes)
        return str(file_path)

    async def _download_external_image_url(self, url: str, *, session_key: str) -> tuple[str, str]:
        target = str(url or "").strip()
        if not target:
            return "", "图片地址为空"
        try:
            import aiohttp

            timeout = aiohttp.ClientTimeout(total=float(self.external_image_api_timeout_seconds))
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(target) as response:
                    if response.status >= 400:
                        return "", f"下载图片失败：HTTP {response.status}"
                    content = await response.read()
                    content_type = str(response.headers.get("Content-Type", "") or "").lower()
            ext = ".png"
            if "jpeg" in content_type or "jpg" in content_type:
                ext = ".jpg"
            elif "webp" in content_type:
                ext = ".webp"
            path = await self._save_external_generated_image(content, session_key=session_key, ext=ext)
            return path, "ok" if path else "保存下载图片失败"
        except Exception as e:
            logger.warning(f"[PrivateCompanion] 下载在线生图结果失败: {e}", exc_info=True)
            return "", str(e)

    async def _run_external_photo_generation(
        self,
        prompt_text: str,
        *,
        session_key: str,
    ) -> tuple[str, str]:
        endpoint = self._external_image_endpoint()
        if not endpoint:
            return "", "未配置在线图片 API 地址"
        if not self.external_image_api_key:
            return "", "未配置在线图片 API Key"
        if not self.external_image_api_model:
            return "", "未配置在线图片模型"
        try:
            import aiohttp

            payload = {
                "model": self.external_image_api_model,
                "prompt": prompt_text,
                "size": self._sanitize_external_image_size(),
            }
            headers = {
                "Authorization": f"Bearer {self.external_image_api_key}",
                "Content-Type": "application/json",
            }
            timeout = aiohttp.ClientTimeout(total=float(self.external_image_api_timeout_seconds))
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(endpoint, headers=headers, json=payload) as response:
                    text = await response.text()
                    if response.status >= 400:
                        return "", f"HTTP {response.status}: {_single_line(text, 180)}"
            data = self._extract_json_payload(text) if text else {}
            if not isinstance(data, dict):
                return "", "在线图片 API 返回格式无效"
            first = None
            items = data.get("data")
            if isinstance(items, list) and items:
                first = items[0]
            if not isinstance(first, dict):
                return "", "在线图片 API 未返回图片数据"
            b64 = str(first.get("b64_json") or "").strip()
            if b64:
                image_bytes = base64.b64decode(b64)
                path = await self._save_external_generated_image(
                    image_bytes,
                    session_key=session_key,
                    ext=".png",
                )
                return path, "ok" if path else "保存在线图片失败"
            image_url = str(first.get("url") or "").strip()
            if image_url:
                return await self._download_external_image_url(
                    image_url,
                    session_key=session_key,
                )
            return "", "在线图片 API 未返回 url 或 b64_json"
        except Exception as e:
            logger.warning(f"[PrivateCompanion] 在线图片 API 生图失败: {e}", exc_info=True)
            return "", str(e)

    def _find_photo_workflow_with_text_count(
        self, module: Any, workflow_dir: Any, workflow_name: str
    ) -> tuple[str, int]:
        if not hasattr(module, "list_workflows_in_dir"):
            return "", 0
        try:
            workflows = module.list_workflows_in_dir(workflow_dir)
        except Exception:
            return "", 0
        candidates = []
        for item in workflows or []:
            if not isinstance(item, dict):
                continue
            if item.get("name") != workflow_name:
                continue
            if _safe_int(item.get("images"), 0) != 0:
                continue
            if _safe_int(item.get("videos"), 0) != 0:
                continue
            text_count = max(1, _safe_int(item.get("texts"), 1, 1))
            filename = str(item.get("filename") or "").strip()
            if not filename:
                continue
            path = os.path.join(str(workflow_dir), filename)
            if os.path.exists(path):
                candidates.append((text_count, path))
        if not candidates:
            return "", 0
        candidates.sort(key=lambda value: value[0])
        return candidates[0][1], candidates[0][0]

    def _get_comfyui_module(self) -> Any:
        for module_name in (
            "astrbot_plugin_comfyui.main",
            "data.plugins.astrbot_plugin_comfyui.main",
        ):
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "ComfyUIWorkflow"):
                    return module
            except Exception:
                continue
        for module in list(sys.modules.values()):
            try:
                if hasattr(module, "ComfyUIWorkflow") and hasattr(module, "_get_result_for_prompt"):
                    return module
            except Exception:
                continue
        return None

    def _extract_action_image_path(self, action_context: str) -> str:
        text = str(action_context or "")
        match = re.search(r"(?:图片路径|真实图片文件)[:：]\s*(.+)", text)
        if not match:
            return ""
        path = match.group(1).strip().splitlines()[0].strip()
        return path if path and os.path.exists(path) else ""

    def _build_outbound_chain(
        self,
        text: str,
        image_path: str = "",
        extra_components: list[Any] | None = None,
    ) -> list[Any]:
        chain: list[Any] = []
        if text:
            chain.append(Plain(text))
        for component in extra_components or []:
            if component is not None:
                chain.append(component)
        if image_path and os.path.exists(image_path):
            try:
                chain.append(Image.fromFileSystem(image_path))
            except AttributeError:
                chain.append(Image.from_file_system(image_path))
        if not chain:
            chain.append(Plain(""))
        return chain

    def _parse_message_session(self, umo: str) -> MessageSession | None:
        try:
            return MessageSession.from_str(str(umo or ""))
        except Exception:
            return None

    def _get_platform_for_session(self, session: MessageSession) -> Any | None:
        platform_id = str(getattr(session, "platform_id", "") or "")
        manager = getattr(self.context, "platform_manager", None)
        if not platform_id or not manager:
            return None
        platforms = []
        try:
            platforms = list(manager.get_insts())
        except Exception:
            platforms = list(getattr(manager, "platform_insts", []) or [])
        for platform in platforms:
            try:
                meta = platform.meta()
            except Exception:
                continue
            if getattr(meta, "id", "") == platform_id or getattr(meta, "name", "") == platform_id:
                return platform
        return None

    def _message_type_for_session(self, session: MessageSession) -> MessageType:
        msg_type = getattr(session, "message_type", MessageType.FRIEND_MESSAGE)
        if isinstance(msg_type, MessageType):
            return msg_type
        msg_type_text = str(msg_type or "")
        if "Group" in msg_type_text or "GROUP" in msg_type_text:
            return MessageType.GROUP_MESSAGE
        return MessageType.FRIEND_MESSAGE

    def _build_result_from_chain(self, chain: list[Any]) -> Any:
        try:
            from astrbot.api.event import MessageEventResult
        except ImportError:
            from astrbot.core.message.message_event_result import MessageEventResult
        try:
            result = MessageEventResult(chain=chain)
        except TypeError:
            result = MessageEventResult().chain_result(chain)
        if hasattr(result, "use_t2i"):
            try:
                result = result.use_t2i(False)
            except Exception:
                pass
        elif hasattr(result, "use_t2i_"):
            try:
                result.use_t2i_ = False
            except Exception:
                pass
        return result

    async def _trigger_proactive_decorating_hooks(self, umo: str, chain: list[Any]) -> list[Any]:
        if not self.enable_proactive_decorating_hooks or not chain:
            return chain
        session = self._parse_message_session(umo)
        if not session:
            return chain
        platform = self._get_platform_for_session(session)
        if not platform:
            return chain
        try:
            message_obj = AstrBotMessage()
            message_obj.type = self._message_type_for_session(session)
            message_obj.self_id = str(getattr(session, "session_id", "") or "")
            message_obj.session_id = str(getattr(session, "session_id", "") or "")
            message_obj.message_id = f"private_companion_proactive_{uuid.uuid4().hex}"
            message_obj.sender = MessageMember(user_id=message_obj.session_id)
            message_obj.message = chain
            message_obj.message_str = ""
            message_obj.raw_message = None
            message_obj.timestamp = int(time.time())
            event = AstrMessageEvent("", message_obj, platform.meta(), message_obj.session_id)
            event.set_result(self._build_result_from_chain(chain))
        except Exception as e:
            logger.debug("[PrivateCompanion] 构造主动消息装饰事件失败,跳过 hooks: %s", e)
            return chain
        try:
            handlers = star_handlers_registry.get_handlers_by_event_type(
                EventType.OnDecoratingResultEvent
            )
        except Exception as e:
            logger.debug("[PrivateCompanion] 获取装饰 hooks 失败: %s", e)
            return chain
        for handler in handlers:
            try:
                await handler.handler(event)
            except Exception as e:
                logger.warning(
                    "[PrivateCompanion] 主动消息装饰 hook 失败: %s: %s",
                    getattr(handler, "handler_full_name", "unknown"),
                    e,
                )
        result = event.get_result()
        processed = getattr(result, "chain", None) if result is not None else None
        processed_chain = list(processed or []) if processed is not None else chain
        return self._filter_decorated_proactive_chain(chain, processed_chain)

    def _filter_decorated_proactive_chain(self, original_chain: list[Any], processed_chain: list[Any]) -> list[Any]:
        if not processed_chain:
            return original_chain

        filtered: list[Any] = []
        removed_any = False
        for component in processed_chain:
            if isinstance(component, Plain):
                text = self._plain_component_text(component)
                if self._is_proactive_delivery_receipt_text(text):
                    removed_any = True
                    continue
                cleaned = self._strip_proactive_delivery_receipt_lines(text)
                if not cleaned:
                    removed_any = True
                    continue
                if cleaned != text:
                    removed_any = True
                    filtered.append(Plain(cleaned))
                else:
                    filtered.append(component)
                continue
            filtered.append(component)

        if filtered:
            return filtered
        return original_chain if removed_any else processed_chain

    @staticmethod
    def _plain_component_text(component: Any) -> str:
        for attr in ("text", "content", "message"):
            value = getattr(component, attr, None)
            if isinstance(value, str):
                return value
        return str(component or "")

    def _is_proactive_delivery_receipt_text(self, text: str) -> bool:
        cleaned = _single_line(text, 240)
        if not cleaned:
            return True
        if re.fullmatch(r"(?:图|图片|照片)(?:好|好了|生成好了|出来了|完成了)[啦了~～。!！]*", cleaned):
            return True
        if re.fullmatch(r"(?:生图|出图|图片生成)(?:完成|好了|成功)[啦了~～。!！]*", cleaned):
            return True
        if re.search(r"(?:还在|正在|继续)?(?:排队|队列|等待生成|等图|等图片|等它出图)", cleaned):
            return True
        if re.match(r"^(?:已经|已)(?:发|发送)过去[啦了]?[，,。!！~～\s]*(?:等(?:着|他|你|对方)|等回复|等回我)?.*$", cleaned):
            return True
        if re.match(r"^等(?:着)?(?:他|你|对方)?回(?:我|复)?[啦了~～。!！]*$", cleaned):
            return True
        if re.match(r"^消息已送达[，,。]?", cleaned):
            return True
        if re.match(r"^这是[^。！？\n]{0,80}(?:发的|发送的|收到的)[^。！？\n]{0,80}(?:消息|打招呼|问候|回复)", cleaned):
            return True
        if re.match(r"^这(?:条|是)[^。！？\n]{0,80}(?:语气|内容|消息)[^。！？\n]{0,80}$", cleaned):
            return True
        if "消息已送达" in cleaned and "收到了" in cleaned:
            return True
        return False

    @staticmethod
    def _contains_inline_image_tag(text: str) -> bool:
        return bool(re.search(r"<img\b[^>]*\bsrc\s*=", str(text or ""), flags=re.IGNORECASE))

    def _strip_proactive_delivery_receipt_lines(self, text: str) -> str:
        kept: list[str] = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if self._is_proactive_delivery_receipt_text(line):
                continue
            kept.append(line)
        return "\n".join(kept).strip()

    def _split_proactive_text(self, text: str, *, image_path: str = "", extra_components: list[Any] | None = None) -> list[str]:
        normalized = str(text or "").strip()
        if not normalized:
            return []
        if image_path or extra_components:
            return [normalized]
        if not self.enable_segmented_proactive_reply:
            return [normalized]
        if len(normalized) > self.segmented_proactive_threshold:
            return [normalized]

        cleanup_pattern: re.Pattern[str] | None = None
        if self.enable_segmented_proactive_content_cleanup and self.segmented_proactive_content_cleanup_rule:
            try:
                cleanup_pattern = re.compile(self.segmented_proactive_content_cleanup_rule)
            except re.error as e:
                logger.warning("[PrivateCompanion] 主动分段内容清理正则无效,跳过清理: %s", e)

        def _clean_segment(segment: str) -> str:
            original = str(segment or "")
            cleaned = cleanup_pattern.sub("", original) if cleanup_pattern else original
            cleaned = cleaned.strip()
            original_tail = re.search(r"[。！？!?…~～]+$", original.strip())
            if cleaned and original_tail and not re.search(r"[。！？!?…~～]+$", cleaned):
                cleaned += original_tail.group(0)
            return cleaned

        if self.segmented_proactive_split_mode == "words":
            split_words = [word for word in self.segmented_proactive_split_words if word]
            if not split_words:
                return [normalized]
            escaped_words = sorted([re.escape(word) for word in split_words], key=len, reverse=True)
            pattern = re.compile(f"(.*?({'|'.join(escaped_words)})|.+$)", re.DOTALL)
            raw_segments = pattern.findall(normalized)
            segments: list[str] = []
            for segment in raw_segments:
                content = segment[0] if isinstance(segment, tuple) else segment
                if not isinstance(content, str):
                    continue
                cleaned = _clean_segment(content)
                if cleaned:
                    segments.append(cleaned)
            return segments if len(segments) > 1 else [normalized]

        try:
            raw_segments = re.findall(
                self.segmented_proactive_regex or r".*?[。？！~…\n]+|.+$",
                normalized,
                re.DOTALL | re.MULTILINE,
            )
        except re.error as e:
            logger.warning("[PrivateCompanion] 主动分段正则无效,使用默认规则: %s", e)
            raw_segments = re.findall(r".*?[。？！~…\n]+|.+$", normalized, re.DOTALL | re.MULTILINE)

        segments = []
        for segment in raw_segments:
            content = segment[0] if isinstance(segment, tuple) else segment
            if not isinstance(content, str):
                continue
            cleaned = _clean_segment(content)
            if cleaned:
                segments.append(cleaned)
        return segments if len(segments) > 1 else [normalized]

    async def _calc_segmented_proactive_interval(self, text: str) -> float:
        if self.segmented_proactive_interval_method == "log":
            if all(ord(ch) < 128 for ch in text):
                word_count = len(text.split())
            else:
                word_count = len([ch for ch in text if ch.isalnum()])
            interval = math.log(word_count + 1, self.segmented_proactive_log_base)
            return random.uniform(interval, interval + 0.5)
        return random.uniform(
            self.segmented_proactive_interval_min,
            self.segmented_proactive_interval_max,
        )

    async def _send_chain_components(self, umo: str, chain: list[Any]) -> None:
        processed_chain = await self._trigger_proactive_decorating_hooks(umo, chain)
        if not processed_chain:
            return
        session = self._parse_message_session(umo)
        platform = self._get_platform_for_session(session) if session else None
        if self.enable_precise_platform_send and session and platform:
            try:
                status = getattr(platform, "status", None)
                if status is not None and status != PlatformStatus.RUNNING:
                    logger.warning("[PrivateCompanion] 目标平台未运行,跳过主动发送: %s", umo)
                    return
                session_obj = MessageSession(
                    platform_name=str(getattr(session, "platform_id", "") or ""),
                    message_type=self._message_type_for_session(session),
                    session_id=str(getattr(session, "session_id", "") or ""),
                )
                await platform.send_by_session(session_obj, MessageChain(processed_chain))
                return
            except Exception as e:
                logger.warning("[PrivateCompanion] 精确平台发送失败,回退核心发送: %s", e)
        await self.context.send_message(umo, self._build_result_from_chain(processed_chain))

    async def _send_media_proactive_chain(
        self,
        umo: str,
        text: str,
        image_path: str = "",
        *,
        extra_components: list[Any] | None = None,
    ) -> None:
        if self._contains_inline_image_tag(text):
            image_path = ""
            extra_components = []
        if text:
            await self._maybe_send_input_status(umo, text)
        segments = self._split_proactive_text(
            text,
            image_path="",
            extra_components=None,
        )
        if len(segments) <= 1:
            if text:
                await self._send_chain_components(umo, [Plain(text)])
        else:
            for index, segment in enumerate(segments):
                await self._send_chain_components(umo, [Plain(segment)])
                if index < len(segments) - 1:
                    await asyncio.sleep(await self._calc_segmented_proactive_interval(segment))
        has_media = bool((extra_components or []) or (image_path and os.path.exists(image_path)))
        if has_media:
            media_chain = self._build_outbound_chain("", image_path, extra_components=extra_components)
            await self._send_chain_components(umo, media_chain)

    async def _send_proactive_message_chain(
        self,
        umo: str,
        text: str,
        image_path: str = "",
        *,
        extra_components: list[Any] | None = None,
    ) -> None:
        if image_path or extra_components:
            await self._send_media_proactive_chain(
                umo,
                text,
                image_path,
                extra_components=extra_components,
            )
            return
        if text:
            await self._maybe_send_input_status(umo, text)
        segments = self._split_proactive_text(
            text,
            image_path=image_path,
            extra_components=extra_components,
        )
        if len(segments) <= 1:
            await self._send_chain_components(
                umo,
                self._build_outbound_chain(text, image_path, extra_components=extra_components),
            )
            return
        for index, segment in enumerate(segments):
            await self._send_chain_components(umo, [Plain(segment)])
            if index < len(segments) - 1:
                await asyncio.sleep(await self._calc_segmented_proactive_interval(segment))

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

    def _build_outbound_result(
        self,
        text: str,
        image_path: str = "",
        extra_components: list[Any] | None = None,
    ) -> Any:
        chain = self._build_outbound_chain(text, image_path, extra_components=extra_components)
        try:
            from astrbot.api.event import MessageEventResult
        except ImportError:
            from astrbot.core.message.message_event_result import MessageEventResult
        try:
            result = MessageEventResult(chain=chain)
        except TypeError:
            result = MessageEventResult().chain_result(chain)
        if hasattr(result, "use_t2i"):
            try:
                result = result.use_t2i(False)
            except Exception:
                pass
        elif hasattr(result, "use_t2i_"):
            try:
                result.use_t2i_ = False
            except Exception:
                pass
        return result

    def _build_proactive_archive_user_prompt(
        self,
        *,
        reason: str,
        action: str,
        motive: str = "",
        action_summary: str = "",
    ) -> str:
        parts = ["[主动消息]"]
        reason_text = _single_line(reason, 40) or "自然想起用户"
        parts.append(f"触发原因：{reason_text}")
        action_text = _single_line(action, 40) or "message"
        if action_text != "message":
            parts.append(f"主动行为：{action_text}")
        summary_text = _single_line(action_summary, 80)
        if summary_text and summary_text != action_text:
            parts.append(f"行为结果：{summary_text}")
        motive_text = _single_line(motive, 120)
        if motive_text:
            parts.append(f"内部动机：{motive_text}")
        return "；".join(parts)

    def _build_proactive_archive_assistant_text(
        self,
        *,
        text: str,
        image_path: str = "",
        extra_components: list[Any] | None = None,
        action_summary: str = "",
    ) -> str:
        message_text = str(text or "").strip()
        attachment_notes: list[str] = []
        if image_path:
            attachment_notes.append("随消息发送了一张图片")
        if extra_components:
            attachment_notes.append(f"随消息发送了 {len(extra_components)} 个附加消息组件")
        if attachment_notes:
            suffix = "（" + ",".join(attachment_notes) + "）"
            message_text = f"{message_text}{suffix}" if message_text else suffix
        if message_text:
            return message_text
        return _single_line(action_summary, 160) or "主动向用户发送了一条消息。"

    async def _archive_proactive_message_to_conversation(
        self,
        *,
        user: dict[str, Any],
        user_prompt: str,
        assistant_response: str,
    ) -> None:
        umo = str(user.get("umo") or "").strip()
        if not umo or not assistant_response:
            return
        try:
            conv_id = await self.context.conversation_manager.get_curr_conversation_id(umo)
            if not conv_id:
                logger.debug("[PrivateCompanion] 当前私聊没有活动对话,跳过主动消息存档: %s", umo)
                return
            user_msg_obj = UserMessageSegment(content=[TextPart(text=user_prompt)])
            assistant_msg_obj = AssistantMessageSegment(content=[TextPart(text=assistant_response)])
            await self.context.conversation_manager.add_message_pair(
                cid=conv_id,
                user_message=user_msg_obj,
                assistant_message=assistant_msg_obj,
            )
            logger.info("[PrivateCompanion] 已将主动消息写入 AstrBot 会话历史: %s", umo)
        except Exception as e:
            logger.warning("[PrivateCompanion] 主动消息写入会话历史失败: %s", e)

    def _format_story_plan_for_prompt(self) -> str:
        plan = self.data.get("daily_story_plan", {})
        if not isinstance(plan, dict) or plan.get("date") != _today_key():
            return "（暂无）"
        lines = []
        now_minutes = datetime.now().hour * 60 + datetime.now().minute
        events = plan.get("today_events", [])
        if isinstance(events, list) and events:
            nearby_events = [
                item for item in events
                if isinstance(item, dict) and self._story_item_relevant_to_now(item, now_minutes)
            ][:6]
            if nearby_events:
                lines.append("附近可能发生：")
                for item in nearby_events:
                    lines.append(f"- {item.get('window', '')}｜{item.get('event', '')}｜{item.get('mood', '')}")
        proactive = plan.get("proactive_events", [])
        if isinstance(proactive, list) and proactive:
            nearby_proactive = [
                item for item in proactive
                if isinstance(item, dict) and self._story_item_relevant_to_now(item, now_minutes, future_minutes=240)
            ][:6]
            if nearby_proactive:
                lines.append("附近主动计划：")
                for item in nearby_proactive:
                    lines.append(
                        f"- {item.get('window', '')}｜{item.get('reason', '')}｜{item.get('action', 'message')}｜"
                        f"{item.get('why', '')}｜{item.get('topic', '')}｜{item.get('motive', '')}｜"
                        f"{item.get('scene', '')}｜{item.get('tone', '')}｜{item.get('impulse', '')}"
                    )
        long_term = plan.get("long_term_events", [])
        if isinstance(long_term, list) and long_term:
            lines.append("长线事件：")
            for item in long_term[:4]:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('title', '')}｜{item.get('status', '')}｜"
                        f"{item.get('tendency', '')}｜{item.get('next_hint', '')}"
                    )
        return "\n".join(lines) if lines else "（暂无）"

    def _story_item_relevant_to_now(
        self,
        item: dict[str, Any],
        now_minutes: int,
        *,
        past_minutes: int = 90,
        future_minutes: int = 180,
    ) -> bool:
        start, end = self._parse_window_minutes(str(item.get("window") or ""))
        if start is None or end is None:
            return False
        candidates = [(start, end)]
        if end < start:
            candidates = [(start, end + 24 * 60), (start - 24 * 60, end)]
        for item_start, item_end in candidates:
            if item_end >= now_minutes - past_minutes and item_start <= now_minutes + future_minutes:
                return True
        return False

    def _format_plan_item_for_prompt(self, item: dict[str, Any] | None) -> str:
        if not isinstance(item, dict):
            return "（暂无）"
        return (
            f"{item.get('time', '')}｜{item.get('activity', '')}｜"
            f"情绪：{item.get('mood', '')}｜可用碎片：{item.get('message_seed', '')}"
        )

    def _sanitize_proactive_text(self, text: str) -> str:
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"<img\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</img>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"<[^>\n]{0,200}>", "", cleaned)
        cleaned = cleaned.replace("[图片]", "").replace("【图片】", "")
        cleaned = cleaned.replace("（图片已送达）", "").replace("(图片已送达)", "")
        cleaned = re.sub(r"^```(?:text)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        cleaned = cleaned.strip().strip('"').strip("'")
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        lines = []
        for raw_line in cleaned.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if re.fullmatch(r"[（(].{0,40}语音消息.{0,20}[)）]", line):
                continue
            if re.match(r"^(?:图片发过去了|希望他看到的时候|然后过了好一会儿)", line):
                continue
            if re.match(r"^[（(].{0,80}(?:翻了个身|裹紧了些|眼睛微微眯起来).*[）)]$", line):
                continue
            line = self._strip_parenthetical_stage_directions(line)
            if not line:
                continue
            lines.append(line)
        if not lines:
            return ""
        return "\n".join(lines[:3])[:260]

    def _strip_parenthetical_stage_directions(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        stage_tokens = (
            "搅", "夹", "咬", "嚼", "喝", "抿", "吞", "放下", "拿起",
            "叹", "笑", "眨", "盯", "看", "望", "低头", "抬头", "偏头",
            "小声", "轻轻", "慢慢", "默默", "皱眉", "挑眉", "眯眼",
            "伸手", "缩", "靠", "蹭", "戳", "敲", "揉", "摸", "抱",
            "翻身", "裹", "坐", "站", "躺", "走", "晃", "顿了顿",
        )

        def _replace(match: re.Match[str]) -> str:
            inner = (match.group(1) or "").strip()
            if not inner:
                return ""
            if any(token in inner for token in stage_tokens):
                return ""
            return match.group(0)

        cleaned = re.sub(r"^[（(]\s*[^()（）\n]{1,50}\s*[）)]\s*", "", cleaned)
        cleaned = re.sub(r"[（(]\s*([^()（）\n]{1,50})\s*[）)]", _replace, cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _normalize_proactive_sentence_flow(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        cleaned = cleaned.replace("！?", "！？").replace("？!", "？！")
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        raw_units: list[str] = []
        for raw_line in cleaned.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            raw_units.extend(self._split_proactive_sentence_units(line))

        if not raw_units:
            return ""

        merged: list[str] = []
        continuation_prefixes = (
            "又", "还", "也", "就", "才", "只是", "但", "但是", "不过", "然后", "所以",
            "有点", "有一点", "不想", "没想", "想着", "顺手",
        )
        for unit in raw_units:
            unit = unit.strip(" ,，、")
            if not unit:
                continue
            is_continuation = unit.startswith(continuation_prefixes)
            if merged and is_continuation:
                merged[-1] = merged[-1].rstrip("。！？!?；;，,") + "，" + unit
            else:
                merged.append(unit)

        normalized = [self._ensure_chat_sentence_punctuation(item) for item in merged]
        normalized = [item for item in normalized if item]
        if len(normalized) <= 3:
            return "\n".join(normalized)[:260]
        head = normalized[:2]
        tail = "".join(normalized[2:])
        return "\n".join(head + [tail])[:260]

    def _ensure_chat_sentence_punctuation(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        if re.search(r"[。！？!?…~～]$", cleaned):
            return cleaned
        question_tokens = (
            "吗", "嘛", "么", "什么", "怎么", "咋", "有没有", "是不是", "要不要",
            "忙什么", "吃东西了吗", "睡了吗", "醒了吗",
        )
        if any(token in cleaned for token in question_tokens):
            return cleaned + "？"
        soft_endings = ("呀", "啦", "嘛", "呢", "吧", "哦", "喔", "诶", "啊")
        if cleaned.endswith(soft_endings):
            return cleaned + "。"
        return cleaned + "。"

    def _split_proactive_sentence_units(self, text: str) -> list[str]:
        cleaned = str(text or "").strip()
        if not cleaned:
            return []
        units: list[str] = []
        for part in [item.strip() for item in re.split(r"\s+", cleaned) if item.strip()]:
            if re.search(r"[。！？!?；;…~～]", part):
                matches = re.findall(r"[^。！？!?；;…~～]+[。！？!?；;…~～]+|[^。！？!?；;…~～]+$", part)
                units.extend(match.strip() for match in matches if match.strip())
            else:
                units.append(part)
        return units

    def _soften_social_proactive_text(self, text: str, *, action: str = "message") -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        cleaned = self._strip_parenthetical_stage_directions(cleaned)
        if not cleaned:
            return ""
        cleaned = re.sub(r"^(?:早上好|早安|上午好|中午好|午安|下午好|晚上好)[,,\s]*", "", cleaned)

        _SOCIAL_REPLACEMENTS = [
            ("刷一下存在感", "来跟你说一句"),
            ("冒个泡", "晃过来一下"),
            ("冒个头", "晃过来一下"),
            ("顺手冒了个头", "晃过来一下"),
            ("突然想起你", "刚好停了一下"),
            ("刚好想到你", "刚好停了一下"),
            ("我刚刚想到你了。", "刚好停了一下。"),
            ("我刚刚想到你了", "刚好停了一下"),
            ("没什么大不了的,就是", ""),
            ("没什么大道理,就是", ""),
            ("免得你又忘了我", "怕你又一头扎进去"),
            ("最近忙不忙？", ""),
            ("最近忙不忙", ""),
            ("数据有意思吗？", ""),
            ("数据有意思吗", ""),
            ("发现你好像在忙。", "看你还没从那边抬头。"),
            ("发现你好像在忙", "看你还没从那边抬头"),
            ("辛苦啦。", "别太累。"),
            ("辛苦啦", "别太累"),
            ("请注意休息", "记得歇会儿"),
        ]
        for old, new in _SOCIAL_REPLACEMENTS:
            cleaned = cleaned.replace(old, new)

        cleaned = re.sub(r"你在忙(.{0,24})吗？感觉你[^。！？\n]*专注[^。！？\n]*[。！？]?", r"还在忙\1啊。", cleaned)
        cleaned = re.sub(r"你在忙(.{0,24})吗？", r"还在忙\1啊。", cleaned)
        cleaned = re.sub(r"感觉你[^。！？\n]*专注[^。！？\n]*[。！？]?", "", cleaned)
        cleaned = re.sub(r"感觉你[^。！？\n]{0,28}呢[。！？]?", "", cleaned)
        cleaned = re.sub(r"(?:我看你|看你)又?在忙", "还在忙", cleaned)

        _ACTION_SPECIFIC_REPLACEMENTS = {
            "screen_peek": [
                ("逻辑分支的工作", "那个逻辑分支"),
                ("工作吗？", "啊。"),
                ("工作啊。", "啊。"),
                ("感觉你投入的样子很专注呢。", ""),
                ("感觉你很投入呢。", ""),
                ("还在忙啊。", "还没从那边抬头啊。"),
            ],
            "poke": [
                ("我就戳一下", "就戳你一下"),
                ("所以来戳你一下", "所以来碰你一下"),
            ],
            "voice": [
                ("给你留了句语音。", "给你留了句语音。"),
                ("刚给你留了句语音,", "刚给你留了句语音,"),
            ],
            "photo_text": [
                ("路边的植物看着很有生机,给你拍了张照片。", "路边那点绿刚好有点顺眼,就顺手发你了。"),
                ("给你拍了张照片。", "顺手拍给你了。"),
                ("给你拍了张照片", "顺手拍给你了"),
                ("给你拍了照片", "顺手拍给你了"),
                ("发给你啦。", "就丢给你啦。"),
            ],
        }
        if action in _ACTION_SPECIFIC_REPLACEMENTS:
            for old, new in _ACTION_SPECIFIC_REPLACEMENTS[action]:
                cleaned = cleaned.replace(old, new)
        if "photo_text" in action:
            cleaned = re.sub(r"^(?:今天天气[^。！？\n]{0,30}[,,])", "", cleaned)
            cleaned = cleaned.replace("（图片已送达）", "").replace("(图片已送达)", "")

        cleaned = re.sub(r"(?:来找你一下[,,、\s]*){2,}", "来找你一下,", cleaned)
        cleaned = re.sub(r"^[嗨哈喂欸诶]{1,2}[,,\s]+", "", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"([。！？])\1+", r"\1", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"^[,。！？、\s]+", "", cleaned)
        cleaned = self._strip_parenthetical_stage_directions(cleaned)
        return cleaned

    def _deemphasize_state_report_preamble(self, text: str, *, reason: str = "") -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        if reason == "important_date_share":
            return cleaned

        date_report_patterns = (
            r"^(?:今天|现在)(?:是)?[^。！？\n]{0,18}(?:五一|劳动节|周末|休息日|假期|放假)[^。！？\n]{0,24}[。！？,\s]*",
            r"^(?:今天|现在)[^。！？\n]{0,16}(?:不用|不用去|不需要)(?:上学|上班|工作|补课)[^。！？\n]{0,18}[。！？,\s]*",
        )
        for pattern in date_report_patterns:
            cleaned = re.sub(pattern, "", cleaned)

        cleaned = re.sub(r"(?:所以|因此)[,，、\s]*(?=我|先|就|你)", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = re.sub(r"^[,，。！？、\s]+", "", cleaned)
        return cleaned

    def _choose_proactive_message(
        self,
        user: dict[str, Any],
        name: str,
        planned_reason: str = "",
    ) -> tuple[str, str]:
        state = self.data.get("daily_state", {})
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        can_do = self.data.get("can_do", [])
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        mood = _single_line(state.get("mood_bias") if isinstance(state, dict) else "平稳", 20)
        active_conditions = state.get("conditions", []) if isinstance(state, dict) else []

        reasons = [planned_reason] if planned_reason else []
        if self._is_quiet_time() and self._has_active_insomnia_state():
            reasons.append("insomnia_night")
        if active_conditions and random.random() < 0.45:
            reasons.append("quiet_care")
        if energy < 45 and random.random() < 0.55:
            reasons.append("quiet_care")
        share_probability = self.proactive_share_probability
        if can_do and random.random() < max(0.05, min(0.85, share_probability)):
            reasons.append("activity_share")
        if self.data.get("bot_diaries") and random.random() < max(0.08, share_probability * 0.55):
            reasons.append("diary_share")
        upcoming_dates = self._get_relevant_important_dates()
        if upcoming_dates and random.random() < 0.35:
            reasons.append("important_date_share")
        if current_item and self.include_schedule_in_messages and random.random() < 0.22:
            reasons.append("background_schedule")
        reasons.append("check_in")
        reason = planned_reason if planned_reason and self._is_reason_allowed_now(planned_reason) else random.choice(reasons)

        if reason == "insomnia_night":
            return reason, random.choice([
                f"{name},我有点睡不着。\n先来你这边晃一下。",
                f"{name},醒着。\n夜里脑子有点吵,我先把这句放你这。",
                f"{name},我脑子里那盏灯还没关。\n你睡了就别管我,明天再笑我。",
            ])

        if reason == "quiet_care":
            return reason, random.choice([
                f"{name},小声找你一下。\n别把自己绷太久。",
                f"{name},先停一下嘛。\n喝口水也算有进展。",
                f"{name},你是不是又一头扎进去了。\n出来透口气。",
            ])

        if reason == "morning_greeting":
            return reason, random.choice([
                f"{name},早呀。\n我先冒个头。",
                f"早。\n你那边醒了吗。",
            ])

        if reason == "noon_greeting":
            return reason, random.choice([
                f"{name},中午了。\n来晃你一下,顺便看看你有没有记得吃东西。",
                f"午后有点懒洋洋的。\n所以我先来戳你一下。",
            ])

        if reason == "evening_greeting":
            return reason, random.choice([
                f"{name},天快暗下来了。\n我先来找你一下,看看你今天有没有把自己累坏。",
                f"差不多该把今天收一收了。\n所以先来你这边晃一下。",
            ])


        if reason == "activity_share":
            activity = _single_line(random.choice(can_do), 40) if isinstance(can_do, list) and can_do else "刚才那点小事"
            return reason, random.choice([
                f"{name},刚刚去弄了一点“{activity}”。\n很小,但算我今天有动过了。",
                f"{name},我把“{activity}”塞进今天了。\n你看,我也不是只会等你来找我。",
                f"{name},突然想到个和“{activity}”有关的小东西。\n先记下,晚点说不定能用。",
                f"我跟你说,刚刚“{activity}”居然真的推进了一点。\n虽然只有一点点,但也算。",
                f"刚才在弄“{activity}”。\n不许笑,至少我没完全摸鱼。",
            ])

        if reason == "diary_share":
            fragment = self._pick_diary_fragment()
            if fragment:
                return reason, random.choice([
                    f"{name},刚翻到我今天记的一句：\n{fragment}",
                    f"{name},我把这个写进日记了：\n{fragment}",
                    f"{name},给你看个小碎片：\n{fragment}",
                    f"突然想把这个发给你：\n{fragment}",
                ])

        if reason == "important_date_share" and upcoming_dates:
            entry = upcoming_dates[0]
            days = _safe_int(entry.get("_days_until"), 0)
            title = _single_line(entry.get("title"), 40)
            note = _single_line(entry.get("note"), 80)
            if days == 0:
                return reason, random.choice([
                    f"{name},今天是「{title}」。\n{note or '我记得的,没忘。'}",
                    f"提醒一下,今天「{title}」。\n{note or '别装没看见。'}",
                ])
            return reason, random.choice([
                f"{name},「{title}」还有 {days} 天。\n{note or '我先帮你放到显眼一点的位置。'}",
                f"小提醒,「{title}」还剩 {days} 天。\n{note or '提前说,不然你这个笨蛋又要临时想起来。'}",
            ])

        if reason == "background_schedule" and current_item:
            activity = _single_line(current_item.get("activity"), 40)
            seed = self._deemphasize_state_report_preamble(
                _single_line(current_item.get("message_seed"), 60),
                reason=reason,
            )
            parts = [seed or "刚好停了一下,把这句放你这。"]
            return reason, "\n".join(parts)

        style = str(user.get("style") or self.default_style)
        templates = STYLE_TEMPLATES.get(style) or STYLE_TEMPLATES["温柔"]
        return "check_in", random.choice(templates).format(name=name)

    async def _scheduler_loop(self):
        while not self._stop_event.is_set():
            try:
                timeout = self._next_scheduler_timeout()
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=timeout
                )
            except asyncio.TimeoutError:
                await self._ensure_daily_state()
                await self._ensure_daily_plan()
                await self._ensure_detail_enhancement()
                await self._ensure_current_detail_presence_status()
                await self._ensure_daily_diary()
                await self._maybe_advance_creative_projects()
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.error(f"[PrivateCompanion] 主动消息循环异常: {e}", exc_info=True)

    async def _kick_proactive_loop_once(self) -> None:
        try:
            await self._ensure_daily_state()
            await self._ensure_daily_plan()
            await self._ensure_detail_enhancement()
            await self._ensure_current_detail_presence_status()
            await self._ensure_daily_diary()
            await self._maybe_advance_creative_projects()
            await self._tick()
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

    def _next_detail_due_in_seconds(self, now: float | None = None) -> float | None:
        if not self.enable_detail_enhancement:
            return None
        plan = self.data.get("daily_plan", {})
        if not isinstance(plan, dict) or not self._is_plan_date_active(plan.get("date")):
            return None
        enhanced = self.data.get("detail_enhanced_segments", {})
        if not isinstance(enhanced, dict):
            enhanced = {}
        segments = self._collect_detail_segments(plan, enhanced)
        if not segments:
            return None
        now_dt = datetime.fromtimestamp(now or _now_ts())
        now_minutes = self._effective_plan_now_minutes(str(plan.get("date") or ""))
        if now_minutes is None:
            return None
        lead = max(0, self.detail_enhancement_lead_minutes)
        candidates: list[float] = []
        for segment in segments:
            start = _safe_int(segment.get("start"), 0)
            due_minute = max(0, start - lead)
            if due_minute <= now_minutes:
                return 0.0
            due_dt = datetime.combine(now_dt.date(), datetime.min.time()) + timedelta(minutes=due_minute)
            candidates.append(max(0.0, due_dt.timestamp() - (now or _now_ts())))
        if not candidates:
            return None
        return min(candidates)

    async def _ensure_daily_plan(self, force: bool = False) -> dict[str, Any] | None:
        if not self.enable_daily_plan and not force:
            return None

        await self._ensure_daily_state(force=force)
        today = _today_key()
        async with self._data_lock:
            current_plan = self.data.setdefault("daily_plan", {})
            known_users = [
                user for user in self.data.get("users", {}).values() if isinstance(user, dict) and user.get("umo")
            ]
            if not force and current_plan.get("date") == today:
                return current_plan
            if not force and self._is_plan_date_active(current_plan.get("date")):
                return current_plan
            if not force and not known_users:
                return None
            if not force and not self._is_daily_plan_due():
                return current_plan if self._is_plan_date_active(current_plan.get("date")) else None

        plan = await self._generate_daily_plan()
        async with self._data_lock:
            self.data["daily_plan"] = plan
            self._save_data_sync()
        return plan

    async def _ensure_daily_diary(self, force: bool = False) -> dict[str, Any] | None:
        if not self.enable_daily_diary and not force:
            return None
        today = _today_key()
        async with self._data_lock:
            if not force and self.data.get("diary_generated_day") == today:
                return None
            if not force and not self._is_daily_diary_due():
                return None

        diary = await self._generate_daily_diary()
        async with self._data_lock:
            diaries = self.data.setdefault("bot_diaries", [])
            if not isinstance(diaries, list):
                diaries = []
                self.data["bot_diaries"] = diaries
            diaries.append(diary)
            del diaries[:-self.max_diary_entries]
            self.data["dream_fragments"] = self._merge_dream_fragment_pool(
                diary.get("dream_fragments", []) if isinstance(diary, dict) else []
            )
            self.data["diary_generated_day"] = today
            story_plan = diary.get("story_plan")
            if isinstance(story_plan, dict):
                self.data["daily_story_plan"] = story_plan
            self._save_data_sync()
        return diary

    async def _ensure_detail_enhancement(self, force: bool = False) -> dict[str, Any] | None:
        if not self.enable_detail_enhancement and not force:
            return None
        async with self._data_lock:
            plan = dict(self.data.get("daily_plan", {}))
            plan_date = str(plan.get("date") or "")
            if not self._is_plan_date_active(plan_date):
                return None
            if self.data.get("detail_enhanced_day") != plan_date:
                self.data["detail_enhanced_day"] = plan_date
                self.data["detail_enhanced_segments"] = {}
            state = dict(self.data.get("daily_state", {}))
            enhanced = self.data.setdefault("detail_enhanced_segments", {})
            if not isinstance(enhanced, dict):
                enhanced = {}
                self.data["detail_enhanced_segments"] = enhanced
            segments = self._collect_due_detail_segments(plan, enhanced, force=force)
            if not segments:
                return None
            for segment in segments:
                enhanced[segment["key"]] = {"status": "generating", "started_at": datetime.now().strftime("%H:%M")}
            self._save_data_sync()

        last_detail = None
        for segment in segments:
            detail = await self._generate_detail_enhancement(segment, plan, state)
            last_detail = detail
            async with self._data_lock:
                story_plan = self.data.setdefault("daily_story_plan", {})
                if not isinstance(story_plan, dict) or story_plan.get("date") != plan_date:
                    story_plan = {
                        "date": plan_date,
                        "today_events": [],
                        "proactive_events": [],
                        "long_term_events": [],
                    }
                    self.data["daily_story_plan"] = story_plan
                self._merge_detail_enhancement(story_plan, detail)
                enhanced = self.data.setdefault("detail_enhanced_segments", {})
                enhanced[segment["key"]] = {
                    "status": "done",
                    "updated_at": datetime.now().strftime("%H:%M"),
                    "summary": _single_line(detail.get("summary"), 120),
                    "today_events": detail.get("today_events", []),
                    "proactive_events": detail.get("proactive_events", []),
                    "state_variables": detail.get("state_variables", []),
                    "presence_status": detail.get("presence_status", {}),
                    "interaction_updates": [],
                    "coverage_repair_done": bool(segment.get("_coverage_repair")),
                }
                self._reschedule_users_for_new_detail_events(segment)
                self._save_data_sync()
            await self._apply_detail_presence_status(segment, detail)
        return last_detail

    def _collect_detail_segments(
        self,
        plan: dict[str, Any],
        enhanced: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not isinstance(plan, dict) or not self._is_plan_date_active(plan.get("date")):
            return []
        items = plan.get("items")
        if not isinstance(items, list) or not items:
            return []
        parsed = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            start = self._parse_hhmm_to_minutes(item.get("time"))
            if start is None:
                continue
            parsed.append((index, start, item))
        if not parsed:
            return []
        segments: list[dict[str, Any]] = []
        for pos, (index, start, item) in enumerate(parsed):
            key = f"{plan.get('date')}:{index}:{item.get('time')}"
            if key in enhanced:
                continue
            next_start = (
                parsed[pos + 1][1]
                if pos + 1 < len(parsed)
                else self._segment_end_minutes(start, item)
            )
            segments.append(
                {
                    "key": key,
                    "index": index,
                    "start": start,
                    "end": next_start,
                    "previous_item": parsed[pos - 1][2] if pos > 0 else None,
                    "item": item,
                    "next_item": parsed[pos + 1][2] if pos + 1 < len(parsed) else None,
                }
            )
        return segments

    def _collect_due_detail_segments(
        self,
        plan: dict[str, Any],
        enhanced: dict[str, Any],
        *,
        force: bool = False,
    ) -> list[dict[str, Any]]:
        segments = self._collect_detail_segments(plan, enhanced if isinstance(enhanced, dict) else {})
        if not segments:
            return []
        if force:
            picked = self._current_detail_segment_for_update() or self._pick_detail_segment(plan, {})
            return [picked] if isinstance(picked, dict) else segments[:1]
        due = [segment for segment in segments if self._detail_segment_is_due(segment)]
        if due:
            return due[:1]

        story_plan = self.data.get("daily_story_plan", {})
        if not isinstance(story_plan, dict):
            story_plan = {}
        repaired: list[dict[str, Any]] = []
        all_segments = self._collect_detail_segments(plan, {})
        for segment in all_segments:
            if not self._detail_segment_is_due(segment):
                continue
            key = str(segment.get("key") or "")
            status = enhanced.get(key) if isinstance(enhanced, dict) else None
            if not isinstance(status, dict) or status.get("status") != "done":
                continue
            if status.get("coverage_repair_done"):
                continue
            if self._detail_segment_has_story_coverage(segment, story_plan):
                continue
            repaired_segment = dict(segment)
            repaired_segment["_coverage_repair"] = True
            repaired.append(repaired_segment)
        return repaired[:1]

    def _detail_segment_is_due(self, segment: dict[str, Any]) -> bool:
        if not isinstance(segment, dict):
            return False
        plan_date = str(self.data.get("daily_plan", {}).get("date") or "")
        now_minutes = self._effective_plan_now_minutes(plan_date)
        if now_minutes is None:
            return False
        start = _safe_int(segment.get("start"), 0)
        end = _safe_int(segment.get("end"), self._segment_end_minutes(start, segment.get("item")))
        lead = max(0, self.detail_enhancement_lead_minutes)
        return start - lead <= now_minutes < end

    def _detail_segment_has_story_coverage(
        self,
        segment: dict[str, Any],
        story_plan: dict[str, Any],
    ) -> bool:
        if not isinstance(segment, dict) or not isinstance(story_plan, dict):
            return False
        start = _safe_int(segment.get("start"), 0)
        end = _safe_int(segment.get("end"), self._segment_end_minutes(start, segment.get("item")))
        for key in ("today_events", "proactive_events"):
            raw_items = story_plan.get(key, [])
            if not isinstance(raw_items, list):
                continue
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                item_start, item_end = self._parse_window_minutes(str(item.get("window") or ""))
                if item_start is None or item_end is None:
                    continue
                if item_end < item_start:
                    item_end += 24 * 60
                if item_start < end and item_end > start:
                    return True
        return False

    def _pick_detail_segment(
        self, plan: dict[str, Any], enhanced: dict[str, Any]
    ) -> dict[str, Any] | None:
        return pick_detail_segment(self, plan, enhanced)

    async def _generate_detail_enhancement(
        self,
        segment: dict[str, Any],
        plan: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, Any]:
        return await generate_detail_enhancement(self, segment, plan, state)

    def _merge_detail_enhancement(
        self, story_plan: dict[str, Any], detail: dict[str, Any]
    ) -> None:
        for key, limit in (
            ("today_events", 16),
            ("proactive_events", 12),
            ("long_term_events", 6),
        ):
            existing = story_plan.setdefault(key, [])
            if not isinstance(existing, list):
                existing = []
                story_plan[key] = existing
            additions = detail.get(key, [])
            if isinstance(additions, list):
                existing.extend(item for item in additions if isinstance(item, dict))
                story_plan[key] = self._trim_story_plan_items(key, existing, limit)

    def _trim_story_plan_items(
        self,
        key: str,
        items: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        normalized = [item for item in items if isinstance(item, dict)]
        if not normalized:
            return []
        seen: set[tuple[Any, ...]] = set()
        deduped: list[dict[str, Any]] = []
        for item in normalized:
            identity = self._story_plan_item_identity(key, item)
            if identity in seen:
                continue
            seen.add(identity)
            deduped.append(item)
        if key == "long_term_events":
            return deduped[-limit:]
        ordered = sorted(deduped, key=self._story_plan_item_sort_key)
        if len(ordered) <= limit:
            return ordered
        return self._pick_story_items_with_coverage(ordered, limit)

    def _story_plan_item_identity(self, key: str, item: dict[str, Any]) -> tuple[Any, ...]:
        if key == "today_events":
            return (
                _single_line(item.get("window"), 20),
                _single_line(item.get("event"), 80),
            )
        if key == "proactive_events":
            return (
                _single_line(item.get("window"), 20),
                _single_line(item.get("reason"), 40),
                _single_line(item.get("action"), 40),
                _single_line(item.get("topic"), 80),
            )
        return (
            _single_line(item.get("title"), 80),
            _single_line(item.get("status"), 80),
        )

    def _story_plan_item_sort_key(self, item: dict[str, Any]) -> tuple[int, int, str]:
        start, end = self._parse_window_minutes(str(item.get("window") or ""))
        start_value = start if start is not None else 99_999
        end_value = end if end is not None else start_value
        if end_value < start_value:
            end_value += 24 * 60
        text = _single_line(
            item.get("event") or item.get("topic") or item.get("title"),
            80,
        )
        return (start_value, end_value, text)

    def _pick_story_items_with_coverage(
        self,
        ordered: list[dict[str, Any]],
        limit: int,
    ) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        total = len(ordered)
        if total <= limit:
            return ordered
        now_minutes = datetime.now().hour * 60 + datetime.now().minute
        selected: set[int] = {0, total - 1}
        closest_index = min(
            range(total),
            key=lambda idx: self._story_item_time_distance(ordered[idx], now_minutes),
        )
        for idx in range(max(0, closest_index - 2), min(total, closest_index + 3)):
            selected.add(idx)
        if limit == 1:
            selected = {closest_index}
        else:
            for slot in range(limit):
                selected.add(round(slot * (total - 1) / max(1, limit - 1)))
        if len(selected) < limit:
            for idx in range(total):
                selected.add(idx)
                if len(selected) >= limit:
                    break
        return [ordered[idx] for idx in sorted(selected)[:limit]]

    def _story_item_time_distance(self, item: dict[str, Any], now_minutes: int) -> int:
        start, end = self._parse_window_minutes(str(item.get("window") or ""))
        if start is None or end is None:
            return 99_999
        if end < start:
            end += 24 * 60
        current = now_minutes
        if current < start and end > 24 * 60:
            current += 24 * 60
        if start <= current < end:
            return 0
        return min(abs(current - start), abs(current - end))

    def _reschedule_users_for_new_detail_events(self, segment: dict[str, Any]) -> None:
        users = self.data.get("users", {})
        if not isinstance(users, dict):
            return
        now = _now_ts()
        start = _safe_int(segment.get("start"), 0) * 60
        end = _safe_int(segment.get("end"), 0) * 60
        for user in users.values():
            if not isinstance(user, dict) or not user.get("umo"):
                continue
            next_at = _safe_float(user.get("next_proactive_at"), 0)
            if next_at <= 0:
                self._schedule_next_proactive(user, now=now)
                continue
            dt = datetime.fromtimestamp(next_at)
            seconds_today = dt.hour * 3600 + dt.minute * 60 + dt.second
            if not (start <= seconds_today <= end):
                self._schedule_next_proactive(user, now=now)

    async def _apply_detail_presence_status(
        self,
        segment: dict[str, Any],
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not self.enable_qq_presence_sync:
            return
        status = (detail or {}).get("presence_status") if isinstance(detail, dict) else None
        if not isinstance(status, dict):
            key = str((segment or {}).get("key") or "")
            enhanced = self.data.get("detail_enhanced_segments", {})
            snapshot = enhanced.get(key) if isinstance(enhanced, dict) else None
            status = snapshot.get("presence_status") if isinstance(snapshot, dict) else None
        if not isinstance(status, dict):
            return
        mode = str(status.get("mode") or status.get("status") or "unchanged").strip().lower()
        if mode in {"", "unchanged", "keep", "保持", "不变"}:
            return
        if mode in {"away", "invisible", "dnd", "do_not_disturb", "离开", "隐身", "请勿打扰", "勿扰"}:
            mode = "online"
        custom_text = _single_line(
            status.get("custom_text")
            or status.get("wording")
            or status.get("text")
            or status.get("label")
            or status.get("自定义状态")
            or status.get("文案"),
            28,
        )
        if mode in {"busy", "忙碌"}:
            mode = "custom"
            custom_text = custom_text or "专注中"
        if mode in {"sleep", "睡觉", "睡眠"}:
            mode = "custom"
            custom_text = custom_text or "休息中"
        if mode in {"custom", "自定义", "自定义状态"} and not custom_text:
            mode = "online"
        key = str((segment or {}).get("key") or "")
        state = self.data.setdefault("qq_presence_state", {})
        if not isinstance(state, dict):
            state = {}
            self.data["qq_presence_state"] = state
        if (
            str(state.get("date") or "") == _today_key()
            and str(state.get("plan_date") or "") == str(self.data.get("detail_enhanced_day") or "")
            and str(state.get("detail_key") or "") == key
            and str(state.get("mode") or "") == mode
            and str(state.get("custom_text") or "") == custom_text
            and bool(state.get("ok", False))
        ):
            return
        if mode in {"custom", "自定义", "自定义状态"}:
            ok, note = await self._set_qq_custom_presence(custom_text)
            mode = "custom"
        else:
            ok, note = await self._set_qq_online_presence(mode)
        state["detail_key"] = key
        state["date"] = _today_key()
        state["plan_date"] = str(self.data.get("detail_enhanced_day") or "")
        state["mode"] = mode
        state["custom_text"] = custom_text
        state["reason"] = _single_line(status.get("reason"), 80)
        state["updated_at"] = _now_ts()
        state["ok"] = bool(ok)
        state["note"] = _single_line(note, 120)
        self._save_data_sync()

    async def _ensure_current_detail_presence_status(self) -> None:
        if not self.enable_qq_presence_sync:
            return
        plan = self.data.get("daily_plan", {})
        if not isinstance(plan, dict) or str(plan.get("date") or "") != _today_key():
            return
        enhanced = self.data.get("detail_enhanced_segments", {})
        if not isinstance(enhanced, dict):
            return
        segment = self._current_detail_segment_for_update()
        if not segment:
            return
        snapshot = enhanced.get(str(segment.get("key") or ""))
        if not isinstance(snapshot, dict) or snapshot.get("status") != "done":
            return
        await self._apply_detail_presence_status(segment, snapshot)

    def _is_daily_diary_due(self) -> bool:
        diary_minutes = self._parse_hhmm_to_minutes(self.daily_diary_time)
        if diary_minutes is None:
            diary_minutes = 23 * 60 + 10
        now = datetime.now()
        return now.hour * 60 + now.minute >= diary_minutes

    async def _generate_daily_diary(self) -> dict[str, Any]:
        await self._ensure_yesterday_conversation_summary()
        return await generate_daily_diary(self)

    def _fallback_diary_payload(self) -> dict[str, Any]:
        return fallback_diary_payload(self)

    def _generate_fallback_long_term_events(self, state: dict[str, Any]) -> list[dict[str, str]]:
        events = self._generate_state_linked_long_term_events()
        if events:
            return events[:3]
        mood = _single_line(state.get("mood_bias"), 20) if isinstance(state, dict) else "平稳"
        return [
            {
                "title": "今日状态延续",
                "status": f"今天整体偏{mood},适合保持平稳节奏",
                "next_hint": "后续可根据对话自然延伸",
                "phase": "steady",
                "tendency": "状态更可能保持稳定或逐步回升",
            }
        ]

    def _normalize_story_plan(self, payload: dict[str, Any]) -> dict[str, Any]:
        return normalize_story_plan(self, payload)

    def _balance_proactive_events_for_day(
        self,
        events: list[dict[str, Any]],
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        prepared: list[dict[str, Any]] = []
        for raw in events:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            if str(item.get("reason") or "") == "state_share":
                item["reason"] = "quiet_care"
            for key, fallback in (
                ("topic", "顺手碰一下"),
                ("why", "生活里刚好空出一点缝隙"),
                ("motive", "刚好停了一下,想轻轻碰你一下"),
                ("impulse", "想轻轻碰你一下"),
            ):
                item[key] = _single_line(item.get(key), 100) or fallback
            if str(item.get("action") or "message") == "message":
                item["action"] = self._preferred_action_for_story_event(item)
            prepared.append(item)
        if not prepared:
            return []
        ordered = sorted(prepared, key=self._story_plan_item_sort_key)
        buckets = ["morning", "noon", "afternoon", "evening", "late_night"]
        by_bucket: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in buckets}
        for item in ordered:
            bucket = self._proactive_daypart_bucket_for_event(item)
            if bucket in by_bucket:
                by_bucket[bucket].append(item)
        selected: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()

        def add(item: dict[str, Any]) -> None:
            if len(selected) >= limit:
                return
            identity = self._story_plan_item_identity("proactive_events", item)
            if identity in seen:
                return
            seen.add(identity)
            selected.append(item)

        for bucket in buckets:
            if by_bucket[bucket]:
                add(by_bucket[bucket][0])
        for bucket in buckets:
            cap = 1 if bucket == "late_night" else 2
            count = sum(1 for item in selected if self._proactive_daypart_bucket_for_event(item) == bucket)
            for item in by_bucket[bucket][1:]:
                if count >= cap:
                    break
                add(item)
                count += 1
        remaining = sorted(
            ordered,
            key=lambda item: (
                0 if str(item.get("action") or "message") != "message" else 1,
                self._event_priority(item),
                self._story_plan_item_sort_key(item),
            ),
        )
        for item in remaining:
            if len(selected) >= limit:
                break
            add(item)
        return sorted(selected, key=self._story_plan_item_sort_key)

    def _preferred_action_for_story_event(self, event: dict[str, Any]) -> str:
        reason = str(event.get("reason") or "check_in")
        text = " ".join(
            _single_line(event.get(key), 80)
            for key in ("topic", "why", "scene", "motive", "impulse")
        )
        if self._photo_text_available() and (
            reason in {"activity_share", "diary_share", "background_schedule", "noon_greeting", "evening_greeting"}
            or any(token in text for token in self._visual_share_tokens())
        ):
            return "photo_text"
        if self._screen_glance_available() and reason in {"check_in", "quiet_care", "background_schedule"}:
            return "screen_peek"
        if self._voice_available() and reason in {"quiet_care", "diary_share", "insomnia_night", "evening_greeting"}:
            return "voice"
        if self._poke_available() and reason in {"check_in", "quiet_care", "morning_greeting", "evening_greeting"}:
            return "poke"
        return "message"

    def _generate_morning_linked_proactive_events(self) -> list[dict[str, Any]]:
        state = self.data.get("daily_state", {})
        if not isinstance(state, dict):
            return []
        sleep_text = str(state.get("sleep") or "")
        conditions = state.get("conditions", [])
        if not isinstance(conditions, list):
            conditions = []
        events: list[dict[str, Any]] = []
        if any(token in sleep_text for token in ("赖床", "闹钟", "起得有点迟", "还没完全开机")):
            events.append(
                {
                    "window": "08:20-09:50",
                    "reason": "morning_greeting",
                    "action": "message",
                    "why": "早上起步有点乱,容易一边整理自己一边顺手来找用户。",
                    "topic": "赖床后的早安",
                    "motive": "刚把自己从床上拽起来,脑子还迷糊着就先想到你了",
                    "scene": "刚从床上爬起来的时候",
                    "tone": "迷糊",
                    "impulse": "还没完全开机,但已经先想往你这边晃一下",
                    "chain": [
                        {"kind": "name_only_opener"},
                        {"kind": "if_no_reply", "after_minutes": 80, "reason": "check_in", "topic": "早晨那句后面", "motive": "隔了挺久那边还安静着,就想再轻轻放一句", "tone": "轻一点"},
                        {"kind": "if_still_no_reply", "after_minutes": 140, "reason": "morning_greeting", "topic": "早晨第二句", "motive": "早晨慢慢过去了,这句只当顺手放下", "tone": "不催促"},
                    ],
                    "mood": "迷糊",
                }
            )
        elif any(token in sleep_text for token in ("睡得很浅", "睡得断断续续", "失眠")):
            events.append(
                {
                    "window": "08:30-09:45",
                    "reason": "morning_greeting",
                    "action": "message",
                    "why": "早上还带着一点睡意时,更容易发一条轻轻的早安。",
                    "topic": "没完全醒的早安",
                    "motive": "人还没完全清醒,但就是想先在你这边冒个头",
                    "scene": "人还带着睡意的时候",
                    "tone": "迟钝",
                    "impulse": "想在彻底清醒前先把一句话放你这",
                    "chain": [
                        {"kind": "name_only_opener"},
                        {"kind": "if_no_reply", "after_minutes": 90, "reason": "check_in", "topic": "早晨那句后面", "motive": "隔了挺久那边还没什么动静,就想再轻轻放一句", "tone": "轻一点"},
                    ],
                    "mood": "迟钝",
                }
            )
        energy = _safe_int(state.get("energy"), 70, 0, 100)
        if energy >= 62 and random.random() < 0.45:
            events.append(
                {
                    "window": "08:10-09:20",
                    "reason": "morning_greeting",
                    "action": "message",
                    "why": "早上状态不差时,更像会顺手发个早安。",
                    "topic": "顺手打个早安",
                    "motive": "刚开机那一下状态还行,就想先来晃你一下",
                    "scene": "刚开机的那一下",
                    "tone": "清醒",
                    "impulse": "想把第一小段清醒顺手分给你一点",
                    "chain": [
                        {"kind": "name_only_opener"},
                        {"kind": "if_no_reply", "after_minutes": 85, "reason": "check_in", "topic": "早安后续", "motive": "早上那句放出去以后隔了挺久,又想轻轻碰一下", "tone": "轻一点"},
                    ],
                    "mood": "清醒",
                }
            )
        for cond in conditions:
            if not isinstance(cond, dict):
                continue
            title = str(cond.get("title") or "")
            label = str(cond.get("label") or "")
            if "睡眠延续" in title and random.random() < 0.55:
                events.append(
                    {
                        "window": "08:40-10:00",
                        "reason": "morning_greeting",
                        "action": "message",
                        "why": "睡意拖到白天时,更容易带着半梦半醒的口吻出现。",
                        "topic": "醒得慢一点的早安",
                        "motive": "那点睡意还挂着,反而更想先把一句话放你这",
                        "scene": "睡意还挂着没散的时候",
                        "tone": "半梦半醒",
                        "impulse": "想在彻底回神前先轻轻碰你一下",
                        "mood": _single_line(cond.get("mood"), 20) or "迟钝",
                    }
                )
                break
            if any(token in label for token in ("赖床", "闹钟", "起得有点迟")):
                events.append(
                    {
                        "window": "08:15-09:40",
                        "reason": "morning_greeting",
                        "action": "message",
                        "why": "早晨小事故之后,很容易像真实好友一样顺手抱怨一句或打个招呼。",
                        "topic": "早晨小事故",
                        "motive": "刚刚被早晨折腾了一下,就有点想来找你吐个小槽",
                        "scene": "被早晨的小事故折腾了一下之后",
                        "tone": "迷糊又有点乱",
                        "impulse": "想先来你这边吐一小口气",
                        "mood": "迷糊",
                    }
                )
                break
        return events[:2]

    def _generate_daypart_linked_proactive_events(self) -> list[dict[str, Any]]:
        state = self.data.get("daily_state", {})
        if not isinstance(state, dict):
            return []
        weather = self._weather_summary_text(self.data.get("daily_weather", {}))
        energy = _safe_int(state.get("energy"), 70, 0, 100)
        sleep_text = str(state.get("sleep") or "")
        events: list[dict[str, Any]] = []
        if 36 <= energy <= 68 and random.random() < 0.58:
            events.append(
                {
                    "window": "12:10-13:30",
                    "reason": "noon_greeting",
                    "action": "message",
                    "why": "午后容易松一下,刚好适合发一条不费力的小消息。",
                    "topic": "午后犯困",
                    "motive": "中午这会儿人有点软下来,就想顺手晃到你这边",
                    "scene": "午后松下来的一小段",
                    "tone": "懒洋洋",
                    "impulse": "想轻轻来找你一下,不想把气氛弄得太用力",
                    "mood": "懒洋洋",
                }
            )
        if any(token in weather for token in ("晚霞", "晴", "阳光", "多云")) and random.random() < 0.52:
            events.append(
                {
                    "window": "17:20-19:10",
                    "reason": "activity_share",
                    "action": "message",
                    "why": "傍晚天色好看时,很容易把一点路上的画面顺手递过去。",
                    "topic": "傍晚路上",
                    "motive": "天色往下落的时候,刚好有一点想把路上的画面递给你",
                    "scene": "傍晚路上的天色慢慢收下来",
                    "tone": "松弛",
                    "impulse": "想把这一点傍晚的感觉顺手递过去",
                    "mood": "松弛",
                }
            )
        if 45 <= energy <= 82 and random.random() < 0.46:
            events.append(
                {
                    "window": "15:20-17:10",
                    "reason": "check_in",
                    "action": "message",
                    "why": "下午中段容易出现一个短短的空隙,适合轻轻探一下头。",
                    "topic": "下午空一下",
                    "motive": "下午忽然空了一小下,就想看看你那边是不是也能喘口气",
                    "scene": "下午节奏中间松开的一小截",
                    "tone": "轻一点",
                    "impulse": "想不吵人地碰一下",
                    "mood": "微松",
                }
            )
        if random.random() < 0.48:
            topic = self._pick_life_thought_topic("activity_share")
            action = "photo_text" if self._photo_text_available() and random.random() < 0.16 else "message"
            events.append(
                {
                    "window": "14:40-18:40" if 12 <= datetime.now().hour < 18 else "19:20-21:40",
                    "reason": "activity_share",
                    "action": action,
                    "why": "日常里冒出来的小念头不一定和天气有关,也可以自然成为一次主动分享。",
                    "topic": topic,
                    "motive": f"刚刚脑子里冒出“{topic}”,不算大事,但想顺手丢给你",
                    "scene": "一天里突然空出来的一小格",
                    "tone": "自然",
                    "impulse": "想把这点小念头放到你这边",
                    "mood": "微妙",
                }
            )
        if any(token in sleep_text for token in ("失眠", "睡得很浅", "睡得断断续续")) and random.random() < 0.5:
            events.append(
                {
                    "window": "22:10-23:25",
                    "reason": "quiet_care",
                    "action": "message",
                    "why": "睡前还没彻底安静下来时,更容易留一条轻一点的晚间消息。",
                    "topic": "临睡前还没安静下来",
                    "motive": "明明该收声了,脑子却还亮着,所以想先把一句话放你这",
                    "scene": "临睡前还没彻底静下来的时候",
                    "tone": "安静里带一点清醒",
                    "impulse": "想在收声前先把这点动静放你这边",
                    "mood": "安静",
                }
            )
        if energy < 42 and random.random() < 0.42:
            events.append(
                {
                    "window": "19:40-21:10",
                    "reason": "quiet_care",
                    "action": "message",
                    "why": "累了一天之后,人会更想找个熟悉的人轻轻落一下。",
                    "topic": "收尾前来一下",
                    "motive": "今天快收尾了,还是想在你这边轻轻落一下脚",
                    "scene": "一天快收尾的时候",
                    "tone": "疲惫",
                    "impulse": "想找个熟悉的地方轻轻落一下脚",
                    "mood": "疲惫",
                }
            )
        return events[:3]

    def _normalize_event_motive(self, item: dict[str, Any]) -> str:
        direct = _single_line(item.get("motive"), 80)
        if direct:
            return self._normalize_internal_motive_text(direct)
        reason = _single_line(item.get("reason"), 40)
        action = _single_line(item.get("action"), 20)
        topic = _single_line(item.get("topic"), 50)
        why = _single_line(item.get("why"), 80)
        scene = _single_line(item.get("scene"), 60)
        tone = _single_line(item.get("tone"), 24)
        impulse = _single_line(item.get("impulse"), 80)
        if impulse:
            return self._normalize_internal_motive_text(impulse)
        base = {
            "insomnia_night": "夜里还没睡着,想和你说一句",
            "state_share": "当前状态有变化,想让你知道",
            "quiet_care": "想到用户,顺手确认一下状态",
            "activity_share": "遇到一段可以分享的日常内容",
            "diary_share": "整理今日记录时想到可以分享",
            "important_date_share": "有个重要时间点值得提前提醒",
            "background_schedule": "当前日程有一点可以自然提到",
            "check_in": "刚好停下来,想确认用户在不在",
            "morning_greeting": "早间开始时先和用户打招呼",
            "noon_greeting": "午间休息时顺手问候一下",
            "evening_greeting": "晚间节奏放缓时想和用户说一句",
        }.get(reason, "刚好停下来,想到可以和用户说一句")
        if action == "screen_peek":
            base = "刚好有点空,就想偷偷看你在忙什么"
        elif action == "photo_text":
            base = "刚刚看到的画面适合分享"
        elif action == "poke":
            base = "想做一次轻量提醒"
        elif action == "voice":
            base = "这会儿更适合用语音表达"
        if topic and any(token in topic for token in ("日记", "笔记", "碎片", "念头", "半句", "想法")):
            base = "整理记录时发现一段适合分享的内容"
        elif topic and any(token in topic for token in self._visual_share_tokens()):
            base = "眼前有个具体小画面适合顺手分享"
        elif topic and any(token in topic for token in ("雨", "天气", "晚霞", "阳光")):
            base = "当前天气内容适合分享"
        elif why and len(why) <= 30:
            base = why
        if scene and tone:
            base = f"刚刚在{scene},状态偏{tone},适合补充一句近况"
        elif scene:
            base = f"刚刚在{scene},适合补充一句近况"
        elif tone and not topic:
            base = f"这会儿状态偏{tone},适合和用户说一句"
        return self._normalize_internal_motive_text(_single_line(base, 80))

    def _dedupe_proactive_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in events:
            if not isinstance(item, dict):
                continue
            key = "|".join(
                [
                    _single_line(item.get("window"), 20),
                    _single_line(item.get("reason"), 40),
                    _single_line(item.get("action"), 20),
                    _single_line(item.get("topic"), 80),
                ]
            )
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _proactive_topic_signature(self, *parts: Any) -> str:
        text = " ".join(_single_line(part, 160) for part in parts if _single_line(part, 160))
        if not text:
            return ""
        school_stress_markers = (
            "上课", "课", "物理", "老师", "点名", "叫上去", "做题", "抓到",
            "发呆", "心跳", "紧张", "差点", "讲台",
        )
        if sum(1 for token in school_stress_markers if token in text) >= 2:
            return "school_class_anxiety"
        food_markers = ("食堂", "午饭", "中午", "菜", "咸", "吃")
        if sum(1 for token in food_markers if token in text) >= 2:
            return "noon_food_share"
        image_markers = ("图", "图片", "照片", "拍", "自拍", "画面")
        if sum(1 for token in image_markers if token in text) >= 2:
            return "photo_share"
        tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]{3,}", text)
        stopwords = {
            "刚才", "现在", "今天", "这个", "那个", "一下", "一点", "有点", "还是",
            "没有", "已经", "时候", "用户", "对方", "主动", "消息", "这会儿",
        }
        kept: list[str] = []
        for token in tokens:
            if token in stopwords:
                continue
            if token not in kept:
                kept.append(token)
            if len(kept) >= 8:
                break
        return "|".join(kept)

    def _event_topic_signature(self, event: dict[str, Any] | None) -> str:
        if not isinstance(event, dict):
            return ""
        return self._proactive_topic_signature(
            event.get("topic"),
            event.get("motive"),
            event.get("why"),
            event.get("scene"),
            event.get("impulse"),
        )

    def _cleanup_recent_proactive_topics(self, user: dict[str, Any], *, now: float | None = None) -> list[dict[str, Any]]:
        now = now or _now_ts()
        raw = user.get("recent_proactive_topics", [])
        if not isinstance(raw, list):
            raw = []
        kept = [
            item for item in raw
            if isinstance(item, dict) and now - _safe_float(item.get("ts"), 0) <= 6 * 3600
        ]
        user["recent_proactive_topics"] = kept[-12:]
        return user["recent_proactive_topics"]

    def _topic_signature_similar(self, left: str, right: str) -> bool:
        if not left or not right:
            return False
        if left == right:
            return True
        left_set = {part for part in left.split("|") if part}
        right_set = {part for part in right.split("|") if part}
        if not left_set or not right_set:
            return False
        common = left_set & right_set
        return len(common) >= 2 or (len(common) >= 1 and min(len(left_set), len(right_set)) <= 2)

    def _recent_proactive_topic_repeated(self, user: dict[str, Any], signature: str, *, now: float | None = None) -> bool:
        if not signature:
            return False
        for item in self._cleanup_recent_proactive_topics(user, now=now):
            if self._topic_signature_similar(signature, str(item.get("signature") or "")):
                return True
        return False

    def _remember_proactive_topic(self, user: dict[str, Any], *, text: str = "", topic: str = "", motive: str = "") -> None:
        signature = self._proactive_topic_signature(text, topic, motive)
        if not signature:
            return
        recent = self._cleanup_recent_proactive_topics(user)
        recent.append(
            {
                "ts": _now_ts(),
                "signature": signature,
                "text": _single_line(text or topic or motive, 120),
            }
        )
        del recent[:-12]

    def _format_recent_proactive_topics_hint(self, user: dict[str, Any]) -> str:
        recent = self._cleanup_recent_proactive_topics(user)
        if not recent:
            return ""
        lines: list[str] = []
        for item in recent[-4:]:
            text = _single_line(item.get("text"), 80)
            if not text:
                continue
            when = self._format_timestamp_elapsed(item.get("ts"))
            lines.append(f"- {when}说过：{text}")
        return "\n".join(lines)

    def _normalize_story_items(self, raw_items: Any, text_key: str) -> list[dict[str, Any]]:
        return normalize_story_items(self, raw_items, text_key)

    def _normalize_long_term_events(self, raw_items: Any) -> list[dict[str, str]]:
        return normalize_long_term_events(self, raw_items)

    def _dedupe_long_term_events(self, events: list[dict[str, str]]) -> list[dict[str, str]]:
        deduped: list[dict[str, str]] = []
        seen: set[str] = set()
        for item in events:
            if not isinstance(item, dict):
                continue
            key = _single_line(item.get("title"), 80)
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    def _generate_state_linked_long_term_events(self) -> list[dict[str, str]]:
        state = self.data.get("daily_state", {})
        if not isinstance(state, dict):
            return []
        weather = self._weather_summary_text(self.data.get("daily_weather", {}))
        conditions = state.get("conditions", [])
        if not isinstance(conditions, list):
            return []
        candidates: list[dict[str, str]] = []
        for cond in conditions:
            if not isinstance(cond, dict):
                continue
            phase = _single_line(cond.get("phase"), 24)
            kind = _single_line(cond.get("kind"), 24)
            label = _single_line(cond.get("label"), 80)
            if kind == "health" and phase == "mild_discomfort":
                candidates.extend(
                    [
                        {
                            "title": "降低当日活动强度",
                            "status": "轻微不适,适合降低活动强度",
                            "next_hint": "若休息或收到关心反馈,后续更可能进入恢复阶段",
                            "phase": phase,
                            "tendency": "倾向缓慢恢复,也可能延续为轻微不适",
                        },
                        {
                            "title": "观察不适是否缓解",
                            "status": label or "当前仍有轻微不适",
                            "next_hint": "若晚些时候状态回升,主动分享意愿可能增加",
                            "phase": phase,
                            "tendency": "恢复倾向受休息与关心反馈影响",
                        },
                    ]
                )
            elif kind in {"recovery_afterglow", "health_tail"} or phase in {"afterglow", "tail"}:
                candidates.extend(
                    [
                        {
                            "title": "观察是否回到稳定节奏",
                            "status": "状态正在回稳,但仍有轻微波动",
                            "next_hint": "若外部环境和情绪稳定,后续分享意愿可能上升",
                            "phase": phase or kind,
                            "tendency": "倾向回稳,也可能残留轻微尾声",
                        }
                    ]
                )
            if kind == "sleep" and phase == "sleep_debt":
                candidates.append(
                    {
                        "title": "留意睡眠债恢复情况",
                        "status": "精神能量未满,白天反应可能偏慢",
                        "next_hint": "若白天恢复顺利,晚间表达会更轻松；否则保持低强度",
                        "phase": phase,
                        "tendency": "倾向先延续低能量,再逐步回稳",
                    }
                )
            if kind in {"care_warmth", "soft_afterglow"}:
                candidates.append(
                    {
                        "title": "记录关心反馈后的回暖",
                        "status": "收到关心反馈后,语气可能更柔和",
                        "next_hint": "若互动氛围稳定,后续轻分享意愿可能增加",
                        "phase": phase or kind,
                        "tendency": "倾向回稳,小概率保留轻度正向余波",
                    }
                )
        if weather != "暂无天气信息" and any(token in weather for token in ("晴", "阳光", "多云", "晚霞")) and random.random() < 0.45:
            candidates.append(
                {
                    "title": "留意傍晚会不会有值得拍下来的天色",
                    "status": f"天气提供了可用于生活背景的外部线索：{weather}",
                    "next_hint": "若当时情绪稳定,可能提高 photo_text 分享概率",
                    "phase": "weather_bonus",
                    "tendency": "倾向轻量分享,不倾向正式开启长对话",
                }
            )
        picked: list[dict[str, str]] = []
        for item in candidates:
            chance = 0.55
            tendency = str(item.get("tendency") or "")
            if "回稳" in tendency:
                chance = 0.45
            if "拖一阵" in tendency:
                chance = 0.4
            if random.random() < chance:
                picked.append(item)
        return picked[:3]

    def _generate_weather_linked_proactive_events(self) -> list[dict[str, Any]]:
        weather = self._weather_summary_text(self.data.get("daily_weather", {}))
        if weather == "暂无天气信息":
            return []
        events: list[dict[str, Any]] = []
        if any(token in weather for token in ("雨", "阵雨", "雷", "小雨", "中雨", "大雨")) and random.random() < 0.65:
            events.append(
                {
                    "window": self._pick_weather_window("rain"),
                    "reason": "activity_share",
                    "action": "message",
                    "why": f"天气在下雨,适合分享一段简短的天气状态。{weather}",
                    "topic": "下雨了呢",
                    "motive": "下雨时适合和用户说一句天气状态",
                    "mood": "安静",
                }
            )
        if any(token in weather for token in ("晴", "阳光", "多云", "晚霞")) and random.random() < 0.35:
            events.append(
                {
                    "window": self._pick_weather_window("clear"),
                    "reason": "activity_share",
                    "action": "message",
                    "why": f"天气看起来有一点生活感,容易想轻轻分享一句。{weather}",
                    "topic": "天气有点好看",
                    "motive": "刚刚那一下天色有点顺眼,就想顺手丢给你",
                    "mood": "松弛",
                }
            )
        return events[:2]

    def _pick_weather_window(self, weather_kind: str) -> str:
        hour = datetime.now().hour
        if weather_kind == "rain":
            if 6 <= hour < 11:
                return "08:20-10:40"
            if 11 <= hour < 17:
                return "12:40-16:30"
            if 17 <= hour < 23:
                return "18:10-21:10"
            return "09:00-10:30"
        if 16 <= hour < 20:
            return "17:10-19:20"
        return "15:30-18:10"

    def _format_plan_for_diary(self, plan: dict[str, Any]) -> str:
        return format_plan_for_diary(self, plan)

    async def _ensure_daily_state(self, force: bool = False) -> dict[str, Any]:
        today = _today_key()
        weather = await self._ensure_weather_context(force=force)
        await self._ensure_yesterday_conversation_summary(force=force)
        async with self._data_lock:
            if not self.enable_humanized_states and not force:
                state = dict(DEFAULT_HUMANIZED_STATE)
                state.update(self._base_state_values())
                state["date"] = today
                state["weather"] = self._weather_summary_text(weather)
                self.data["daily_state"] = state
                self._save_data_sync()
                return state

            self._cleanup_expired_conditions()
            if force:
                self.data["state_conditions"] = []
                self.data["state_generated_day"] = ""
            if force or self.data.get("state_generated_day") != today:
                self.data.setdefault("state_conditions", []).extend(
                    await self._generate_state_conditions(weather)
                )
                self.data["state_generated_day"] = today
            state = self._compose_state_from_conditions(weather)
            self.data["daily_state"] = state
            self._save_data_sync()
            return state

    async def _generate_state_conditions(self, weather: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        intensity = self.humanized_state_intensity / 100
        persona_profile = self._persona_state_profile()
        now_dt = datetime.now()
        current_minute = now_dt.hour * 60 + now_dt.minute

        sleep_pool = [
            ("睡眠平稳", "平稳", 0, 8),
            ("睡得很浅,像一直隔着一层雾", "迟钝", -16, 10),
            ("有点失眠,凌晨才慢慢安静下来", "敏感", -24, 14),
            ("睡得断断续续,醒来时还有点空", "恍惚", -18, 12),
            ("赖床赖得有点久,整个人还没完全开机", "迷糊", -14, 8),
            ("闹钟像没响一样,起床时整个人有点慌", "慌乱", -17, 7),
        ]
        dream_pool = [
            ("没有记住梦", "平稳", 0, 2),
            ("梦里一直在找一件放错地方的小东西,醒来还残着一点没找完的感觉", "恍惚", -6, 5),
            ("梦见走过一段很安静的路,路灯和风声都很近", "柔和", 4, 4),
            ("梦里反复听见一句没听清的话,醒来后胸口还有点闷", "低落", -10, 7),
        ]
        hunger_pool = [
            ("饥饿感平稳", "平稳", 0, 3),
            ("有点饿,容易被温暖的东西吸引", "黏人", -5, 4),
            ("没什么胃口,只想安静待着", "低落", -10, 6),
            ("想吃一点甜的,情绪会比平时软", "柔软", 2, 3),
        ]
        cycle_pool = [
            ("无明显周期影响", "平稳", 0, 24),
            ("生理期前的模拟状态,情绪更敏感,耐心更薄", "敏感", -18, 72),
            ("生理期模拟状态,能量偏低,想少说重话", "疲惫", -24, 96),
            ("周期恢复期,慢慢回到稳定状态", "松弛", -6, 48),
        ]

        def pick(pool: list[tuple[str, str, int, int]], special_chance: float = 0.35) -> tuple[str, str, int, int]:
            if random.random() > special_chance * max(0.2, intensity):
                return pool[0]
            return random.choice(pool[1:])

        sleep_pick = pick(sleep_pool, 0.42)
        dream_pick = await self._generate_enhanced_dream_pick(weather) or pick(dream_pool, 0.55)
        self._remember_daily_dream_pick(dream_pick)
        hunger_pick = pick(hunger_pool, 0.5)
        specs = [
            ("sleep", "睡眠", *sleep_pick),
            ("dream", "梦境", *dream_pick),
        ]
        if persona_profile.get("allow_hunger", True):
            specs.append(("hunger", "饥饿", *hunger_pick))
        if persona_profile.get("allow_cycle", False):
            specs.append(("body_cycle", "周期", *pick(cycle_pool, 0.28)))
        else:
            specs.append(("body_cycle", "周期", *cycle_pool[0]))

        diary_tags = self._recent_diary_tags()
        weather_text = self._weather_summary_text(weather)
        if persona_profile.get("allow_health", True):
            health_causes = self._build_health_causes(
                sleep_label=sleep_pick[0],
                weather_text=weather_text,
                diary_tags=diary_tags,
            )
            health_spec = self._pick_health_spec(health_causes, intensity, weather_text)
            if health_spec is not None:
                specs.append(("health", "健康", *health_spec))
        if "失眠" in diary_tags and random.random() < 0.35:
            specs.append(("sleep", "睡眠延续", "昨晚的失眠感还没完全散掉", "迟钝", -12, 8))
        if persona_profile.get("allow_health", True) and "生病" in diary_tags and random.random() < 0.4:
            specs.append(("health", "健康延续", "身体像还在恢复,反应慢半拍", "疲惫", -14, 18, "前两天的不舒服还没完全退掉"))
        if "低能量" in diary_tags and random.random() < 0.35:
            specs.append(("sleep", "能量延续", "昨天的低电量拖到今天早上", "安静", -10, 6))
        if "好梦" in diary_tags and random.random() < 0.3:
            specs.append(("dream", "梦境余温", "梦里留下了一点柔和的亮色", "柔和", 4, 5))

        conditions = []
        for spec in specs:
            extras: dict[str, Any] = {}
            if len(spec) >= 7:
                kind, title, label, mood, energy_delta, duration_hours, cause = spec[:7]
                extras["cause"] = cause
            else:
                kind, title, label, mood, energy_delta, duration_hours = spec[:6]
            if energy_delta == 0 and kind not in {"sleep", "dream"}:
                continue
            if kind == "health" and energy_delta < 0:
                extras["on_end_transition"] = "health_relief"
                extras["phase"] = "mild_discomfort"
            if kind == "sleep" and energy_delta <= -16:
                extras["on_end_transition"] = "sleep_rebound"
                extras["phase"] = "sleep_debt"
            extras["transition_options"] = self._build_transition_options(
                kind=kind,
                energy_delta=int(energy_delta * max(0.4, intensity)),
                cause=str(extras.get("cause") or ""),
                on_end_transition=str(extras.get("on_end_transition") or ""),
            )
            conditions.append(
                self._make_condition(
                    kind=kind,
                    title=title,
                    label=label,
                    mood=mood,
                    energy_delta=int(energy_delta * max(0.4, intensity)),
                    duration_hours=duration_hours,
                    intensity=random.randint(35, 90),
                    **extras,
                )
            )
        dream_aftertaste = self._build_dream_aftertaste_condition(dream_pick)
        if dream_aftertaste is not None:
            conditions.append(dream_aftertaste)
        if 0 <= current_minute < 5 * 60:
            late_night_pool = [
                ("夜里还没完全安静下来,眼睛和脑子都慢半拍", "困倦", -14, 4),
                ("这个点还醒着,困意和清醒混在一起", "恍惚", -12, 3),
                ("已经很晚了,精神有点发飘,只想把声音放轻", "疲惫", -10, 5),
            ]
            label, mood, energy_delta, duration_hours = random.choice(late_night_pool)
            conditions.append(
                self._make_condition(
                    kind="sleep",
                    title="夜深未眠",
                    label=label,
                    mood=mood,
                    energy_delta=int(energy_delta * max(0.55, intensity)),
                    duration_hours=duration_hours,
                    intensity=random.randint(45, 88),
                    phase="late_night_awake",
                    transition_options=[
                        {"to": "sleep_afterglow", "base_weight": 0.35},
                        {"to": "sleep_tail", "base_weight": 0.2},
                        {"to": "stable", "base_weight": 0.45},
                    ],
                )
            )
        return conditions

    def _remember_daily_dream_pick(self, dream_pick: tuple[str, str, int, int] | None) -> None:
        if not dream_pick:
            return
        label = _single_line(dream_pick[0], 120)
        if not label:
            return
        payload = getattr(self, "_last_generated_dream_payload", None)
        if not isinstance(payload, dict) or _single_line(payload.get("label"), 120) != label:
            payload = {}
        factors = payload.get("factors", [])
        if not isinstance(factors, list):
            factors = []
        normalized_factors = [_single_line(item, 30) for item in factors[:8] if _single_line(item, 30)]
        if not normalized_factors:
            normalized_factors = self._build_dream_memory_fragments(count=6)
        content = _single_line(payload.get("content"), 1000)
        if not content:
            factor_hint = "、".join(normalized_factors[:4]) or "一些断续的生活碎片"
            content = (
                f"梦里像从{factor_hint}开始,场景没有交代清楚就慢慢换了地方。"
                f"{label}那种感觉一直挂着,中间有些画面接不上,但醒来时还记得自己在梦里顺着它走了一段。"
            )
        self.data["daily_dream"] = {
            "date": _today_key(),
            "label": label,
            "dream_type": _single_line(payload.get("dream_type"), 40) or "碎片梦",
            "factors": normalized_factors,
            "content": content,
            "afterglow": _single_line(payload.get("afterglow"), 220) or label,
            "mood": _single_line(dream_pick[1], 20) or "平稳",
            "energy_delta": _safe_int(dream_pick[2], 0, -30, 20),
            "duration_hours": _safe_int(dream_pick[3], 0, 0, 24),
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def _remembered_daily_dream_label(self) -> str:
        raw = self.data.get("daily_dream")
        if not isinstance(raw, dict) or raw.get("date") != _today_key():
            return ""
        label = _single_line(raw.get("label"), 120)
        if label and label != "没有记住梦":
            return label
        return ""

    def _dream_afterglow_strength(self, dream_pick: tuple[str, str, int, int]) -> float:
        mode = str(self.dream_afterglow_mode or "auto")
        if mode == "轻":
            return 0.7
        if mode == "标准":
            return 1.0
        if mode == "明显":
            return 1.35
        label = str(dream_pick[0] or "")
        energy_delta = abs(int(dream_pick[2] or 0))
        if any(token in label for token in ("不舒服", "追", "黑", "掉下去", "迷路", "醒来后有一点黏着感")):
            return 1.15
        if energy_delta >= 10:
            return 1.1
        if energy_delta <= 2:
            return 0.75
        return 0.95

    def _build_dream_aftertaste_condition(
        self,
        dream_pick: tuple[str, str, int, int],
    ) -> dict[str, Any] | None:
        label = str(dream_pick[0] or "")
        mood = str(dream_pick[1] or "平稳")
        if not label or label == "没有记住梦":
            return None
        strength = self._dream_afterglow_strength(dream_pick)
        if random.random() > min(0.92, 0.45 + strength * 0.2):
            return None
        if any(token in label for token in ("不舒服", "追", "恐怖", "黑", "掉下去", "迷路", "醒来后有一点黏着感")):
            return self._make_condition(
                kind="dream_aftertaste",
                title="梦后的不安残留",
                label="梦里的那点不安还没完全褪干净",
                mood="恍惚" if mood in {"恍惚", "低落", "敏感"} else "敏感",
                energy_delta=-max(2, int(round(4 * strength))),
                duration_hours=max(2, int(round(6 * strength))),
                intensity=min(92, int(50 + 20 * strength)),
                cause=f"梦境余韵：{_single_line(label, 40)}",
                phase="dream_aftertaste",
            )
        if any(token in label for token in ("发光", "柔", "亮色", "温暖", "春梦", "暧昧", "怀旧")):
            return self._make_condition(
                kind="dream_aftertaste",
                title="梦后的余温",
                label="梦里的余温还轻轻黏着一点",
                mood="柔和" if mood not in {"平稳", "中性"} else "安静",
                energy_delta=max(1, int(round(2 * strength))),
                duration_hours=max(2, int(round(5 * strength))),
                intensity=min(88, int(46 + 16 * strength)),
                cause=f"梦境余韵：{_single_line(label, 40)}",
                phase="dream_aftertaste",
            )
        return self._make_condition(
            kind="dream_aftertaste",
            title="梦后的朦胧残影",
            label="梦里的画面还没完全从脑子里退下去",
            mood="恍惚" if mood == "平稳" else mood,
            energy_delta=-max(1, int(round(2 * strength))),
            duration_hours=max(2, int(round(4 * strength))),
            intensity=min(82, int(42 + 16 * strength)),
            cause=f"梦境余韵：{_single_line(label, 40)}",
            phase="dream_aftertaste",
        )

    def _build_health_causes(
        self,
        *,
        sleep_label: str,
        weather_text: str,
        diary_tags: set[str],
    ) -> list[str]:
        causes: list[str] = []
        if sleep_label not in {"睡眠平稳"} and random.random() < 0.7:
            causes.append("昨晚没睡踏实")
        if any(tag in diary_tags for tag in {"失眠", "低能量"}) and random.random() < 0.45:
            causes.append("前一天状态就有点透支")
        weather_lower = str(weather_text or "").lower()
        if any(token in weather_text for token in ("降雨", "小雨", "中雨", "大雨", "阴", "多云")) and random.random() < 0.4:
            causes.append("空气有点潮,身上那股乏劲更明显")
        if any(token in weather_text for token in ("风", "降温", "冷")) and random.random() < 0.55:
            causes.append("吹了点风,身上容易发空")
        temp_match = re.search(r"(-?\d+(?:\.\d+)?)\s*°C", weather_lower)
        if temp_match:
            try:
                temp = float(temp_match.group(1))
            except ValueError:
                temp = 20.0
            if temp <= 10 and random.random() < 0.55:
                causes.append("天气偏冷,早上容易着凉")
            elif temp >= 30 and random.random() < 0.35:
                causes.append("天气闷热,整个人有点蔫")
        return causes

    def _pick_health_spec(
        self, causes: list[str], intensity: float, weather_text: str
    ) -> tuple[str, str, int, int, str] | None:
        if not causes:
            return None
        chance = min(0.42, 0.12 + len(causes) * 0.1 * max(0.5, intensity))
        if random.random() > chance:
            return None
        cause_text = ",".join(dict.fromkeys(causes[:2]))
        pool = [
            ("喉咙有点发紧,今天想少说重话", "安静", -10, 24),
            ("头有点沉,做事想放慢一点", "疲惫", -14, 18),
            ("像有点发虚,反应会慢半拍", "疲惫", -18, 30),
        ]
        label, mood, energy_delta, duration_hours = random.choice(pool)
        if "闷热" in cause_text and "喉咙" in label:
            label = "有点发闷,只想把动作放轻一点"
        if "潮" in cause_text and "头有点沉" in label:
            label = "身上有点沉,今天想把事情做轻一点"
        return label, mood, energy_delta, duration_hours, cause_text

    def _build_transition_options(
        self,
        *,
        kind: str,
        energy_delta: int,
        cause: str,
        on_end_transition: str,
    ) -> list[dict[str, Any]]:
        if on_end_transition == "health_relief":
            return [
                {"to": "recovery_afterglow", "base_weight": 0.45},
                {"to": "stable", "base_weight": 0.4},
                {"to": "health_tail", "base_weight": 0.15},
            ]
        if on_end_transition == "sleep_rebound":
            return [
                {"to": "sleep_afterglow", "base_weight": 0.35},
                {"to": "stable", "base_weight": 0.5},
                {"to": "sleep_tail", "base_weight": 0.15},
            ]
        if kind == "care_warmth":
            return [
                {"to": "stable", "base_weight": 0.8},
                {"to": "soft_afterglow", "base_weight": 0.2},
            ]
        return []

    def _make_condition(
        self,
        *,
        kind: str,
        title: str,
        label: str,
        mood: str,
        energy_delta: int,
        duration_hours: int,
        intensity: int,
        cause: str = "",
        on_end_transition: str = "",
        phase: str = "",
        transition_options: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        start_ts = _now_ts()
        return {
            "id": f"{kind}-{int(start_ts)}-{random.randint(1000, 9999)}",
            "kind": kind,
            "title": title,
            "label": label,
            "mood": mood,
            "energy_delta": energy_delta,
            "intensity": intensity,
            "start_ts": start_ts,
            "end_ts": start_ts + duration_hours * 3600,
            "duration_hours": duration_hours,
            "cause": cause,
            "on_end_transition": on_end_transition,
            "phase": phase,
            "transition_options": list(transition_options or []),
        }

    def _infer_manual_state_mood(self, text: str) -> str:
        raw = str(text or "")
        mapping = [
            (("累", "疲惫", "困", "没电"), "疲惫"),
            (("烦", "乱", "躁", "闷"), "烦闷"),
            (("病", "难受", "不舒服", "头疼", "发烧"), "虚弱"),
            (("饿", "胃口", "嘴馋"), "黏人"),
            (("开心", "轻快", "高兴", "兴奋"), "轻快"),
            (("紧张", "慌", "忐忑"), "紧张"),
            (("安静", "困倦", "恍惚"), "安静"),
        ]
        for markers, mood in mapping:
            if any(marker in raw for marker in markers):
                return mood
        return "平稳"

    def _infer_manual_state_energy_delta(self, text: str) -> int:
        raw = str(text or "")
        if any(token in raw for token in ("开心", "轻快", "高兴", "兴奋")):
            return 6
        if any(token in raw for token in ("病", "难受", "不舒服", "发烧", "头疼")):
            return -16
        if any(token in raw for token in ("累", "疲惫", "困", "没电")):
            return -10
        if any(token in raw for token in ("烦", "乱", "躁", "闷")):
            return -8
        return -4 if any(token in raw for token in ("紧张", "慌")) else 0

    async def _add_manual_state(self, value: str) -> tuple[bool, str]:
        raw = str(value or "").strip()
        if not raw:
            return False, "请这样填写：陪伴 增添状态 有点累了|8"
        label_part, sep, hours_part = raw.partition("|")
        label = _single_line(label_part, 80)
        if not label:
            return False, "状态描述不能为空。"
        duration_hours = _safe_int(hours_part.strip() if sep else 12, 12, 1, 72)
        mood = self._infer_manual_state_mood(label)
        energy_delta = self._infer_manual_state_energy_delta(label)
        await self._ensure_daily_state()
        async with self._data_lock:
            conditions = self.data.setdefault("state_conditions", [])
            if not isinstance(conditions, list):
                self.data["state_conditions"] = []
                conditions = self.data["state_conditions"]
            conditions.append(
                self._make_condition(
                    kind="manual_state",
                    title="手动增添状态",
                    label=label,
                    mood=mood,
                    energy_delta=energy_delta,
                    duration_hours=duration_hours,
                    intensity=60,
                    cause="由用户手动增添",
                    phase="manual",
                )
            )
            state = self._compose_state_from_conditions(self.data.get("daily_weather", {}))
            self.data["daily_state"] = state
            self._save_data_sync()
        return True, f"已增添状态：{label}（约持续 {duration_hours} 小时）"

    def _recent_diary_tags(self) -> set[str]:
        return recent_diary_tags(self)

    def _recent_diary_context(self, count: int = 3) -> str:
        return recent_diary_context(self, count)

    def _normalize_dream_fragment_item(self, raw: Any) -> dict[str, Any] | None:
        return normalize_dream_fragment_item(self, raw)

    def _dream_fragment_effective_weight(self, fragment: dict[str, Any], now_ts: float | None = None) -> float:
        return dream_fragment_effective_weight(self, fragment, now_ts=now_ts)

    def _normalize_dream_fragment_pool(self, fragments: Any, *, now_ts: float | None = None) -> list[dict[str, Any]]:
        return normalize_dream_fragment_pool(self, fragments, now_ts=now_ts)

    def _extract_weighted_dream_fragments(self, payload: Any) -> list[dict[str, Any]]:
        return extract_weighted_dream_fragments(self, payload)

    def _fallback_dream_fragments_for_diary(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        return fallback_dream_fragments_for_diary(self, state)

    def _merge_dream_fragment_pool(self, new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return merge_dream_fragment_pool(self, new_items)

    def _weighted_unique_fragment_sample(
        self,
        fragments: list[dict[str, Any]],
        *,
        count: int,
    ) -> list[str]:
        return weighted_unique_fragment_sample(self, fragments, count=count)

    def _build_dream_memory_fragments(self, count: int = 8) -> list[str]:
        return build_dream_memory_fragments(self, count)

    def _dream_theme_specs(self) -> list[tuple[str, str]]:
        return dream_theme_specs(self)

    async def _generate_enhanced_dream_pick(
        self,
        weather: dict[str, Any] | None = None,
    ) -> tuple[str, str, int, int] | None:
        return await generate_enhanced_dream_pick(self, weather)

    async def _ensure_weather_context(self, force: bool = False) -> dict[str, Any]:
        today = _today_key()
        if not self.enable_weather_context:
            return {"date": today, "prompt": "暂无天气信息", "source": "disabled"}
        cached = self.data.get("daily_weather", {})
        if isinstance(cached, dict):
            fetched_at = _safe_float(cached.get("fetched_ts"), 0)
            if (
                not force
                and cached.get("date") == today
                and _now_ts() - fetched_at < self.weather_refresh_minutes * 60
            ):
                return cached
        prompt = "暂无天气信息"
        source = "none"
        own_result = await self._fetch_own_weather_prompt()
        text = _single_line(own_result.get("prompt"), 120) if isinstance(own_result, dict) else ""
        if text:
            prompt = text
            source = str(own_result.get("source") or "private_companion")
        else:
            plugin = self._get_screen_companion_plugin()
            if plugin is not None and hasattr(plugin, "_get_weather_prompt"):
                try:
                    result = await plugin._get_weather_prompt()
                    text = _single_line(result, 120)
                    if text:
                        prompt = text
                        source = "screen_companion"
                except Exception as e:
                    logger.debug(f"[PrivateCompanion] 获取天气信息失败: {e}")
        weather = {
            "date": today,
            "prompt": prompt,
            "source": source,
            "fetched_ts": _now_ts(),
        }
        async with self._data_lock:
            self.data["daily_weather"] = weather
            self._save_data_sync()
        return weather

    def _weather_summary_text(self, weather: dict[str, Any] | None) -> str:
        if not isinstance(weather, dict):
            return "暂无天气信息"
        text = _single_line(weather.get("prompt"), 120)
        return text or "暂无天气信息"

    async def _fetch_own_weather_prompt(self) -> dict[str, str]:
        if not self.weather_api_key:
            return {"prompt": "", "source": ""}
        url = self._build_weather_url()
        if not url:
            return {"prompt": "", "source": ""}
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.debug(f"[PrivateCompanion] 天气请求失败: {response.status}")
                        return {"prompt": "", "source": ""}
                    weather_data = await response.json()
        except Exception as e:
            logger.debug(f"[PrivateCompanion] 私有天气获取失败: {e}")
            return {"prompt": "", "source": ""}
        try:
            weather_desc = weather_data.get("weather", [{}])[0].get("description", "")
            temp = weather_data.get("main", {}).get("temp", 0)
            if weather_desc:
                return {
                    "prompt": f"当前天气 {weather_desc},约 {temp}°C。",
                    "source": "private_companion",
                }
        except Exception:
            pass
        return {"prompt": "", "source": ""}

    def _build_weather_url(self) -> str:
        key = self.weather_api_key
        city = self.weather_city
        lat, lon = self.weather_lat, self.weather_lon
        if city:
            return (
                "http://api.openweathermap.org/data/2.5/weather"
                f"?q={city}&appid={key}&units=metric&lang=zh_cn"
            )
        if -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0):
            return (
                "http://api.openweathermap.org/data/2.5/weather"
                f"?lat={lat}&lon={lon}&appid={key}&units=metric&lang=zh_cn"
            )
        return ""

    def _detect_care_feedback(self, text: str) -> dict[str, Any]:
        normalized = str(text or "").strip()
        if not normalized:
            return {"is_care": False, "tags": []}
        tags: list[str] = []
        if re.search(r"吃药|喝药|去拿药|按时吃药", normalized):
            tags.append("medicine")
        if re.search(r"喝水|多喝热水|热水|温水", normalized):
            tags.append("water")
        if re.search(r"休息|早点睡|快睡|去睡|别熬夜|多睡会|睡一觉", normalized):
            tags.append("rest")
        if re.search(r"保暖|别着凉|穿厚|加衣服|盖好", normalized):
            tags.append("warm")
        if re.search(r"难受|还好吗|没事吧|注意身体|照顾好自己|心疼", normalized):
            tags.append("concern")
        tags = list(dict.fromkeys(tags))
        return {"is_care": bool(tags), "tags": tags}

    def _apply_care_feedback_to_state(self, text: str) -> bool:
        feedback = self._detect_care_feedback(text)
        if not feedback.get("is_care"):
            return False
        tags = feedback.get("tags", [])
        changed = False
        now = _now_ts()
        conditions = self.data.setdefault("state_conditions", [])
        if not isinstance(conditions, list):
            self.data["state_conditions"] = []
            conditions = self.data["state_conditions"]
        for cond in conditions:
            if not isinstance(cond, dict):
                continue
            if str(cond.get("kind") or "") != "health":
                continue
            if _safe_float(cond.get("end_ts"), 0) <= now:
                continue
            remaining = max(0, _safe_float(cond.get("end_ts"), now) - now)
            shorten_ratio = 0.0
            if "medicine" in tags:
                shorten_ratio += 0.35
            if "rest" in tags:
                shorten_ratio += 0.2
            if "water" in tags:
                shorten_ratio += 0.12
            if "warm" in tags:
                shorten_ratio += 0.12
            if shorten_ratio > 0:
                cond["end_ts"] = now + remaining * max(0.35, 1 - min(shorten_ratio, 0.55))
                cond["duration_hours"] = max(
                    1,
                    int((cond["end_ts"] - _safe_float(cond.get("start_ts"), now)) / 3600),
                )
                cond["energy_delta"] = min(-2, int(_safe_int(cond.get("energy_delta"), -8) * 0.75))
                cond["label"] = "收到照顾提醒后,不适强度略有下降"
                changed = True
            notes = cond.setdefault("care_notes", [])
            if isinstance(notes, list):
                care_note = "用户提供了关心反馈"
                if "medicine" in tags:
                    care_note = "用户提醒用药"
                elif "rest" in tags:
                    care_note = "用户提醒休息"
                elif "water" in tags:
                    care_note = "用户提醒补水"
                if care_note not in notes:
                    notes.append(care_note)
            cond["cause"] = _single_line(
                f"{_single_line(cond.get('cause'), 80)}；用户提供了照顾提醒".strip("；"),
                120,
            )
        if changed and random.random() < 0.72:
            conditions.append(
                self._make_condition(
                    kind="care_warmth",
                    title="被关心后的回暖",
                    label="收到用户关心后的轻度回暖",
                    mood="柔和",
                    energy_delta=6,
                    duration_hours=6,
                    intensity=72,
                    cause="用户提供了关心反馈",
                    phase="care_feedback",
                    transition_options=self._build_transition_options(
                        kind="care_warmth",
                        energy_delta=6,
                        cause="用户提供了关心反馈",
                        on_end_transition="",
                    ),
                )
            )
        return changed

    def _pick_diary_fragment(self) -> str:
        diaries = self.data.get("bot_diaries", [])
        if not isinstance(diaries, list) or not diaries:
            return ""
        diary = random.choice(diaries[-5:])
        if not isinstance(diary, dict):
            return ""
        candidates = [
            _single_line(diary.get("share_seed"), 100),
            _single_line(diary.get("summary"), 100),
        ]
        return next((item for item in candidates if item), "")

    def _parse_date_value(self, value: Any) -> date | None:
        text = str(value or "").strip()
        for fmt in ("%Y-%m-%d", "%m-%d"):
            try:
                parsed = datetime.strptime(text, fmt)
                year = datetime.now().year if fmt == "%m-%d" else parsed.year
                return date(year, parsed.month, parsed.day)
            except ValueError:
                continue
        return None

    def _next_occurrence(self, entry: dict[str, Any]) -> date | None:
        base = self._parse_date_value(entry.get("date"))
        if base is None:
            return None
        today = datetime.now().date()
        if entry.get("repeat_yearly", True):
            try:
                candidate = date(today.year, base.month, base.day)
            except ValueError:
                return None
            if candidate < today:
                try:
                    candidate = date(today.year + 1, base.month, base.day)
                except ValueError:
                    return None
            return candidate
        return base

    def _get_relevant_important_dates(self) -> list[dict[str, Any]]:
        entries = self.data.get("important_dates", [])
        if not isinstance(entries, list):
            return []
        today = datetime.now().date()
        relevant = []
        for entry in entries:
            if not isinstance(entry, dict) or not entry.get("enabled", True):
                continue
            next_day = self._next_occurrence(entry)
            if next_day is None:
                continue
            days_until = (next_day - today).days
            remind_days = _safe_int(
                entry.get("remind_days"), self.important_date_lookahead_days, 0, 365
            )
            if 0 <= days_until <= remind_days:
                copy = dict(entry)
                copy["_next_date"] = _date_key(next_day)
                copy["_days_until"] = days_until
                relevant.append(copy)
        return sorted(
            relevant,
            key=lambda item: (
                _safe_int(item.get("_days_until"), 999),
                -_safe_int(item.get("priority"), 50),
            ),
        )

    def _format_important_dates_for_prompt(self) -> str:
        entries = self._get_relevant_important_dates()
        if not entries:
            return "（近期没有需要特别记住的日期）"
        lines = []
        for entry in entries[:8]:
            days = _safe_int(entry.get("_days_until"), 0)
            when = "今天" if days == 0 else f"{days} 天后"
            lines.append(
                f"- {when}｜{entry.get('title', '')}｜类型：{entry.get('type', '重要日期')}｜"
                f"备注：{entry.get('note', '')}"
            )
        return "\n".join(lines)

    def _format_calendar_context_for_prompt(self, now: datetime | None = None) -> str:
        current = now or datetime.now()
        weekday_names = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")
        weekday = weekday_names[current.weekday()]
        is_weekend = current.weekday() >= 5
        builtin_holidays = {
            "01-01": ("元旦", "节假日"),
            "05-01": ("劳动节", "节假日"),
            "10-01": ("国庆节", "节假日"),
        }
        month_day = current.strftime("%m-%d")
        today_dates = [
            entry
            for entry in self._get_relevant_important_dates()
            if _safe_int(entry.get("_days_until"), 999) == 0
        ]
        special_lines = []
        holiday_tokens = (
            "节",
            "节日",
            "假",
            "假期",
            "放假",
            "休息",
            "旅行",
            "生日",
            "纪念日",
            "春节",
            "元旦",
            "清明",
            "端午",
            "中秋",
            "国庆",
            "劳动",
            "圣诞",
        )
        has_holiday_signal = False
        builtin_holiday = builtin_holidays.get(month_day)
        if builtin_holiday:
            title, type_text = builtin_holiday
            special_lines.append(f"- 今天：{title}｜类型：{type_text}｜备注：内置公历节日")
            has_holiday_signal = True
        for entry in today_dates[:5]:
            title = _single_line(entry.get("title"), 40)
            type_text = _single_line(entry.get("type"), 30)
            note = _single_line(entry.get("note"), 80)
            joined = f"{title} {type_text} {note}"
            if any(token in joined for token in holiday_tokens):
                has_holiday_signal = True
            if title:
                special_lines.append(f"- 今天：{title}｜类型：{type_text or '重要日期'}｜备注：{note or '无'}")
        if has_holiday_signal:
            day_tone = "节假日/特殊日期"
        elif is_weekend:
            day_tone = "周末/休息日候选"
        else:
            day_tone = "普通工作日或学习日候选"
        rules = [
            f"日期：{current.strftime('%Y-%m-%d')}（{weekday}）",
            f"基础日期类型：{day_tone}",
        ]
        if special_lines:
            rules.append("今天相关的重要日期：\n" + "\n".join(special_lines))
        else:
            rules.append("今天相关的重要日期：无")
        rules.append(
            "日程判断：先看日期语境,再看人格设定。工作日可以有上课/上班；周末要更松,可以晚起、休息、出门、补一点自己的事；节假日/假期要明显区别于普通日,可以有庆祝、出行、宅家、家人/朋友安排或假期拖延。"
        )
        rules.append(
            "如果人格、日程专用设定或重要日期备注里写了调休、补班、补课、考试、值班等例外,优先按这些例外来写。不要凭空塞入身份里没有的校园、职场或节日细节。"
        )
        return "\n".join(rules)

    def _calendar_day_flags(self, now: datetime | None = None) -> dict[str, bool]:
        current = now or datetime.now()
        is_weekend = current.weekday() >= 5
        builtin_holidays = {"01-01", "05-01", "10-01"}
        month_day = current.strftime("%m-%d")
        today_dates = [
            entry
            for entry in self._get_relevant_important_dates()
            if _safe_int(entry.get("_days_until"), 999) == 0
        ]
        holiday_tokens = (
            "节",
            "节日",
            "假",
            "假期",
            "放假",
            "休息",
            "旅行",
            "春节",
            "元旦",
            "清明",
            "端午",
            "中秋",
            "国庆",
            "劳动",
        )
        override_tokens = ("调休", "补班", "补课", "考试", "值班", "加班", "返校")
        has_holiday_signal = month_day in builtin_holidays
        has_override_signal = False
        for entry in today_dates:
            if not isinstance(entry, dict):
                continue
            joined = _single_line(
                f"{entry.get('title', '')} {entry.get('type', '')} {entry.get('note', '')}",
                160,
            )
            if any(token in joined for token in holiday_tokens):
                has_holiday_signal = True
            if any(token in joined for token in override_tokens):
                has_override_signal = True
        schedule_prompt = self._get_schedule_planning_prompt()
        if any(token in schedule_prompt for token in override_tokens):
            has_override_signal = True
        return {
            "is_weekend": is_weekend,
            "has_holiday_signal": has_holiday_signal,
            "has_override_signal": has_override_signal,
        }

    def _plan_conflicts_with_calendar(self, items: list[dict[str, str]], now: datetime | None = None) -> bool:
        if not items:
            return False
        flags = self._calendar_day_flags(now)
        if flags["has_override_signal"]:
            return False
        if not (flags["is_weekend"] or flags["has_holiday_signal"]):
            return False
        school_or_work_tokens = (
            "上课",
            "下课",
            "放学",
            "课间",
            "老师",
            "作业",
            "自习",
            "教室",
            "食堂",
            "校门",
            "班会",
            "补课",
            "上班",
            "通勤",
            "打卡",
            "工位",
            "会议",
            "下班",
            "值班",
        )
        for item in items:
            if not isinstance(item, dict):
                continue
            text = _single_line(
                f"{item.get('activity', '')} {item.get('message_seed', '')}",
                220,
            )
            if any(token in text for token in school_or_work_tokens):
                return True
        return False

    def _is_micro_plan_activity(self, text: str) -> bool:
        normalized = _single_line(text, 160)
        if not normalized:
            return False
        length = len(normalized)
        instant_markers = (
            "看了一眼",
            "瞥了一眼",
            "拍了一下",
            "拍了下",
            "翻了个身",
            "揉了揉",
            "抬头看",
            "关掉闹钟",
            "叫了一声",
            "应了一声",
            "顺手点开",
        )
        if any(marker in normalized for marker in instant_markers):
            return length <= 30
        generic_short_markers = ("一下", "一眼", "一瞬", "顺手", "刚好", "忽然")
        continuity_markers = (
            "慢慢",
            "继续",
            "待着",
            "坐着",
            "趴着",
            "整理",
            "收拾",
            "吃饭",
            "洗漱",
            "发呆",
            "看剧",
            "听歌",
            "出门",
            "路上",
            "吹风",
            "睡前",
            "饭后",
            "午休",
            "收尾",
        )
        if any(marker in normalized for marker in generic_short_markers) and not any(
            marker in normalized for marker in continuity_markers
        ):
            return length <= 22
        return False

    def _plan_has_excess_micro_segments(self, items: list[dict[str, str]]) -> bool:
        if not items:
            return False
        micro_count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if self._is_micro_plan_activity(str(item.get("activity") or "")):
                micro_count += 1
        return micro_count >= max(2, len(items) // 4)

    def _is_abstract_plan_activity(self, text: str) -> bool:
        normalized = _single_line(text, 180)
        if not normalized:
            return False
        concrete_markers = (
            "起床", "赖床", "洗漱", "吃", "喝", "走", "坐", "趴", "靠", "收拾", "整理",
            "看", "听", "出门", "回家", "写", "刷", "逛", "吹风", "洗碗", "看剧", "躺",
            "翻", "换鞋", "背上", "拿着", "关灯", "开窗", "买", "收声", "聊天", "做饭",
        )
        abstract_markers = (
            "思绪", "心情", "气息", "余韵", "碎片", "温柔", "柔软", "飘忽", "微醺", "依恋",
            "恍惚", "生活感", "画面", "感觉", "梦里", "脑海里", "最后闪过", "随着光线",
        )
        if any(marker in normalized for marker in concrete_markers):
            abstract_count = sum(1 for marker in abstract_markers if marker in normalized)
            return abstract_count >= 3 and len(normalized) <= 22
        abstract_count = sum(1 for marker in abstract_markers if marker in normalized)
        return abstract_count >= 2

    def _plan_has_excess_abstract_segments(self, items: list[dict[str, str]]) -> bool:
        if not items:
            return False
        abstract_count = 0
        for item in items:
            if not isinstance(item, dict):
                continue
            if self._is_abstract_plan_activity(str(item.get("activity") or "")):
                abstract_count += 1
        return abstract_count >= max(2, len(items) // 3)

    @staticmethod
    def _plan_activity_signature(text: str) -> str:
        normalized = _single_line(text, 180)
        if not normalized:
            return ""
        category_rules = (
            ("起床", ("起床", "醒来", "睡醒", "赖床", "闹钟", "被窝")),
            ("洗漱", ("洗漱", "刷牙", "洗脸", "梳头", "镜子", "卫生间")),
            ("早餐", ("早餐", "早饭", "面包", "牛奶", "豆浆", "粥")),
            ("正餐", ("午饭", "晚饭", "吃饭", "做饭", "干饭", "饭桌", "摆碗", "点外卖")),
            ("通勤出门", ("出门", "路上", "公交", "地铁", "校门", "换鞋", "背包", "打车")),
            ("校园课程", ("上课", "下课", "教室", "课间", "老师", "同桌", "黑板", "班会")),
            ("补课考试", ("补课", "考试", "测验", "卷子", "复习", "考场", "错题")),
            ("学习作业", ("作业", "自习", "刷题", "数学", "英语", "课本", "笔记", "书包")),
            ("工作事务", ("上班", "工位", "会议", "打卡", "下班", "同事", "项目", "文档")),
            ("家务整理", ("收拾", "整理", "扫地", "洗碗", "洗衣", "归位", "桌面", "房间")),
            ("休息摸鱼", ("午休", "休息", "摸鱼", "躺", "趴", "沙发", "发呆", "缓一会")),
            ("娱乐放松", ("看剧", "追番", "游戏", "刷短视频", "听歌", "小说", "漫画")),
            ("社交互动", ("聊天", "朋友", "家人", "消息", "电话", "群聊", "回复", "打开对话框")),
            ("购物外食", ("买", "便利店", "超市", "奶茶", "饮料", "小吃", "逛")),
            ("户外散步", ("散步", "走一段", "吹风", "公园", "楼下", "河边", "阳台", "开窗")),
            ("运动身体", ("运动", "跑步", "拉伸", "散操", "瑜伽", "出汗")),
            ("洗澡睡前", ("洗澡", "睡前", "关灯", "上床", "准备睡", "入睡", "枕头")),
        )
        hits: list[str] = []
        for label, tokens in category_rules:
            if any(token in normalized for token in tokens):
                hits.append(label)
            if len(hits) >= 2:
                break
        if hits:
            return "+".join(hits)
        compact = re.sub(r"[，。！？、,.!?；;：:\s]+", "", normalized)
        return compact[:8]

    def _plan_signature(self, items: list[dict[str, Any]]) -> list[str]:
        signatures: list[str] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            signature = self._plan_activity_signature(
                f"{item.get('activity', '')} {item.get('message_seed', '')}"
            )
            if signature:
                signatures.append(signature)
        return signatures

    def _format_recent_daily_plan_history_for_prompt(self, limit: int = 5) -> str:
        history = self._recent_daily_plan_history_entries()
        rows: list[str] = []
        for entry in history[-limit:]:
            if not isinstance(entry, dict):
                continue
            date_text = _single_line(entry.get("date"), 16)
            signatures = entry.get("signature")
            if not isinstance(signatures, list):
                signatures = []
            samples = entry.get("sample")
            if not isinstance(samples, list):
                samples = []
            skeleton = " / ".join(_single_line(part, 20) for part in signatures[:12] if part)
            sample_text = "；".join(_single_line(part, 46) for part in samples[:4] if part)
            if skeleton:
                line = f"- {date_text}: {skeleton}"
                if sample_text:
                    line += f"\n  代表活动: {sample_text}"
                rows.append(line)
        return "\n".join(rows) if rows else "暂无最近日程历史。"

    def _plan_repetition_score(self, items: list[dict[str, str]]) -> float:
        signatures = self._plan_signature(items)
        if not signatures:
            return 0.0
        current_set = set(signatures)
        history = self._recent_daily_plan_history_entries()
        best_score = 0.0
        for entry in history[-5:]:
            if not isinstance(entry, dict):
                continue
            old_signatures = entry.get("signature")
            if not isinstance(old_signatures, list) or not old_signatures:
                continue
            old_values = [str(value) for value in old_signatures if value]
            old_set = set(old_values)
            if not old_set:
                continue
            jaccard = len(current_set & old_set) / max(1, len(current_set | old_set))
            paired = min(len(signatures), len(old_values))
            same_positions = 0
            for idx in range(paired):
                if signatures[idx] == old_values[idx]:
                    same_positions += 1
            ordered = same_positions / max(1, paired)
            best_score = max(best_score, jaccard * 0.65 + ordered * 0.35)
        return best_score

    def _plan_is_too_repetitive(self, items: list[dict[str, str]]) -> bool:
        if not items:
            return False
        signatures = self._plan_signature(items)
        if len(signatures) >= 6:
            dominant_count = max(signatures.count(signature) for signature in set(signatures))
            if dominant_count >= max(4, len(signatures) // 2 + 1):
                return True
        return self._plan_repetition_score(items) >= 0.62

    def _daily_plan_history_entry(self, plan: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(plan, dict):
            return None
        items = plan.get("items")
        if not isinstance(items, list) or not items:
            return None
        plan_date = _single_line(plan.get("date"), 16) or _today_key()
        sample: list[str] = []
        for item in items[:6]:
            if not isinstance(item, dict):
                continue
            time_text = _single_line(item.get("time"), 8)
            activity = _single_line(item.get("activity"), 52)
            if activity:
                sample.append(f"{time_text} {activity}".strip())
        entry = {
            "date": plan_date,
            "generated_at": _single_line(plan.get("generated_at"), 20) or datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": _single_line(plan.get("source"), 16),
            "signature": self._plan_signature(items),
            "sample": sample,
        }

    def _recent_daily_plan_history_entries(self) -> list[dict[str, Any]]:
        history = self.data.get("daily_plan_history", [])
        entries = [entry for entry in history if isinstance(entry, dict)] if isinstance(history, list) else []
        known_dates = {_single_line(entry.get("date"), 16) for entry in entries}
        current_entry = self._daily_plan_history_entry(self.data.get("daily_plan", {}))
        if current_entry and _single_line(current_entry.get("date"), 16) not in known_dates:
            entries.append(current_entry)
        return entries

    def _remember_daily_plan_history(self, plan: dict[str, Any]) -> None:
        entry = self._daily_plan_history_entry(plan)
        if not entry:
            return
        plan_date = _single_line(entry.get("date"), 16)
        history = self.data.setdefault("daily_plan_history", [])
        if not isinstance(history, list):
            history = []
            self.data["daily_plan_history"] = history
        history[:] = [
            old
            for old in history
            if not (isinstance(old, dict) and _single_line(old.get("date"), 16) == plan_date)
        ]
        history.append(entry)
        del history[:-10]

    def _add_important_date_entry(self, value: str) -> tuple[bool, str]:
        parts = value.split(maxsplit=2)
        if len(parts) < 2:
            return False, "格式：陪伴 日期添加 <标题> <YYYY-MM-DD或MM-DD> [备注]"
        title = _single_line(parts[0], 40)
        date_text = _single_line(parts[1], 20)
        note = _single_line(parts[2], 120) if len(parts) >= 3 else ""
        parsed = self._parse_date_value(date_text)
        if parsed is None:
            return False, "日期格式不对,请用 YYYY-MM-DD 或 MM-DD。"
        repeat_yearly = len(date_text) == 5
        entry = {
            "id": f"date-{int(_now_ts())}-{random.randint(1000, 9999)}",
            "title": title,
            "date": date_text,
            "type": "重要日期",
            "note": note,
            "enabled": True,
            "repeat_yearly": repeat_yearly,
            "remind_days": self.important_date_lookahead_days,
            "priority": 50,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }
        self.data.setdefault("important_dates", []).append(entry)
        return True, f"已添加重要日期：{title}｜{date_text}"

    def _remove_important_date_entry(self, value: str) -> str:
        keyword = _single_line(value, 40)
        if not keyword:
            return "请提供要删除的日期标题关键词。"
        entries = self.data.setdefault("important_dates", [])
        if not isinstance(entries, list):
            self.data["important_dates"] = []
            return "重要日期列表为空。"
        kept = []
        removed = []
        for entry in entries:
            title = str(entry.get("title", "")) if isinstance(entry, dict) else ""
            if keyword in title:
                removed.append(title)
            else:
                kept.append(entry)
        self.data["important_dates"] = kept
        if not removed:
            return "没有找到匹配的重要日期。"
        return "已删除：\n" + "\n".join(f"- {item}" for item in removed)

    def _format_important_dates(self) -> str:
        entries = self.data.get("important_dates", [])
        if not isinstance(entries, list) or not entries:
            return "还没有重要日期。"
        lines = ["重要日期条目："]
        today = datetime.now().date()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            next_day = self._next_occurrence(entry)
            suffix = ""
            if next_day:
                days = (next_day - today).days
                suffix = "｜今天" if days == 0 else f"｜{days} 天后"
            enabled = "启用" if entry.get("enabled", True) else "停用"
            repeat = "每年" if entry.get("repeat_yearly", True) else "一次"
            lines.append(
                f"- {entry.get('title')}｜{entry.get('date')}｜{repeat}｜{enabled}{suffix}｜{entry.get('note', '')}"
            )
        return "\n".join(lines)

    def _cleanup_expired_conditions(self):
        now = _now_ts()
        conditions = self.data.setdefault("state_conditions", [])
        if not isinstance(conditions, list):
            self.data["state_conditions"] = []
            return
        active = []
        expired = []
        for cond in conditions:
            if not isinstance(cond, dict):
                continue
            if _safe_float(cond.get("end_ts"), 0) > now:
                active.append(cond)
            else:
                expired.append(cond)
        for cond in expired:
            active.extend(self._spawn_followup_conditions(cond))
        self.data["state_conditions"] = active

    def _spawn_followup_conditions(self, cond: dict[str, Any]) -> list[dict[str, Any]]:
        choice = self._pick_condition_transition(cond)
        if not choice or choice == "stable":
            return []
        followup = self._build_transition_condition(choice, cond)
        return [followup] if followup else []

    def _pick_condition_transition(self, cond: dict[str, Any]) -> str:
        options = cond.get("transition_options", [])
        if not isinstance(options, list) or not options:
            return ""
        weighted: list[tuple[str, float]] = []
        cause = _single_line(cond.get("cause"), 120)
        intensity = _safe_int(cond.get("intensity"), 50, 0, 100)
        weather_text = self._weather_summary_text(self.data.get("daily_weather", {}))
        care_notes = cond.get("care_notes", [])
        care_count = len(care_notes) if isinstance(care_notes, list) else 0
        for option in options:
            if not isinstance(option, dict):
                continue
            target = str(option.get("to") or "").strip()
            weight = float(option.get("base_weight") or 0)
            if not target or weight <= 0:
                continue
            if target == "recovery_afterglow":
                weight += min(0.22, care_count * 0.08)
                if "提醒" in cause or "用户" in cause:
                    weight += 0.06
            elif target == "health_tail":
                if intensity >= 75:
                    weight += 0.1
                if any(token in cause for token in ("透支", "失眠")):
                    weight += 0.08
                if any(token in weather_text for token in ("降雨", "小雨", "中雨", "大雨", "冷", "风")):
                    weight += 0.05
                weight -= min(0.12, care_count * 0.05)
            elif target == "sleep_afterglow":
                weight += min(0.16, care_count * 0.05)
            elif target == "sleep_tail":
                if intensity >= 80:
                    weight += 0.08
                if any(token in cause for token in ("失眠", "睡")):
                    weight += 0.04
            weighted.append((target, max(0.0, weight)))
        total = sum(weight for _, weight in weighted)
        if total <= 0:
            return ""
        pick = random.random() * total
        cursor = 0.0
        for target, weight in weighted:
            cursor += weight
            if pick <= cursor:
                return target
        return weighted[-1][0]

    def _build_transition_condition(self, target: str, cond: dict[str, Any]) -> dict[str, Any] | None:
        cause = _single_line(cond.get("cause"), 120)
        if target == "recovery_afterglow":
            label = "不适缓解后的轻度回升"
            if cause:
                label = "不适正在缓解,状态明显回升"
            return self._make_condition(
                kind="recovery_afterglow",
                title="恢复后的回弹",
                label=label,
                mood="轻快",
                energy_delta=10,
                duration_hours=12,
                intensity=68,
                cause="前序不适开始缓解",
                phase="afterglow",
            )
        if target == "health_tail":
            return self._make_condition(
                kind="health_tail",
                title="恢复尾声",
                label="整体好转,但仍有轻微虚弱残留",
                mood="平缓",
                energy_delta=-4,
                duration_hours=10,
                intensity=48,
                cause="恢复中,体力尚未完全回满",
                phase="tail",
            )
        if target == "sleep_afterglow":
            return self._make_condition(
                kind="sleep_afterglow",
                title="补回来一点精神",
                label="睡意缓解后的轻度回升",
                mood="轻松",
                energy_delta=8,
                duration_hours=8,
                intensity=60,
                cause="前序失眠或浅睡影响减弱",
                phase="afterglow",
            )
        if target == "sleep_tail":
            return self._make_condition(
                kind="sleep_tail",
                title="迟钝尾声",
                label="睡眠影响减弱,但反应仍略慢",
                mood="安静",
                energy_delta=-3,
                duration_hours=6,
                intensity=42,
                cause="睡眠债仍有轻微残留",
                phase="tail",
            )
        if target == "soft_afterglow":
            return self._make_condition(
                kind="soft_afterglow",
                title="被关心后的余温",
                label="收到关心反馈后的柔和余波",
                mood="柔和",
                energy_delta=4,
                duration_hours=4,
                intensity=48,
                cause="用户关心反馈仍有轻度影响",
                phase="afterglow",
            )
        return None

    def _get_active_conditions(self) -> list[dict[str, Any]]:
        now = _now_ts()
        conditions = self.data.get("state_conditions", [])
        if not isinstance(conditions, list):
            return []
        active = []
        for cond in conditions:
            if not isinstance(cond, dict):
                continue
            start_ts = _safe_float(cond.get("start_ts"), 0)
            end_ts = _safe_float(cond.get("end_ts"), 0)
            if start_ts <= now < end_ts:
                active.append(cond)
        return active

    def _compose_state_from_conditions(self, weather: dict[str, Any] | None = None) -> dict[str, Any]:
        active = self._get_active_conditions()
        values = self._base_state_values()
        weather_text = self._weather_summary_text(weather)
        energy = 75
        mood_candidates = []
        health_cause = ""
        for cond in active:
            kind = str(cond.get("kind") or "")
            if kind in values:
                values[kind] = _single_line(cond.get("label"), 80)
            energy += _safe_int(cond.get("energy_delta"), 0, -100, 100)
            mood = _single_line(cond.get("mood"), 20)
            if mood and mood != "平稳":
                mood_candidates.append((mood, _safe_int(cond.get("intensity"), 50, 0, 100)))
            if kind == "health" and not health_cause:
                health_cause = _single_line(cond.get("cause"), 120)
        remembered_dream = self._remembered_daily_dream_label()
        if values.get("dream") == "没有记住梦" and remembered_dream:
            values["dream"] = remembered_dream
        energy = max(10, min(100, energy))
        mood_bias = (
            sorted(mood_candidates, key=lambda item: item[1], reverse=True)[0][0]
            if mood_candidates else "平稳"
        )
        note = self._build_state_note(
            values["sleep"],
            values["dream"],
            values["health"],
            values["hunger"],
            values["body_cycle"],
            weather_text,
            mood_bias,
            energy,
            health_cause,
        )
        return {
            "date": _today_key(),
            **values,
            "weather": weather_text,
            "mood_bias": mood_bias,
            "energy": energy,
            "note": note,
            "conditions": active,
        }

    def _build_state_note(
        self,
        sleep: str,
        dream: str,
        health: str,
        hunger: str,
        body_cycle: str,
        weather: str,
        mood_bias: str,
        energy: int,
        health_cause: str = "",
    ) -> str:
        if energy < 35:
            pace = "今天能量很低,日程应更轻、更慢,主动消息也要更短。"
        elif energy < 55:
            pace = "今天能量偏低,适合少量任务和更多停顿。"
        elif energy > 80:
            pace = "今天能量不错,可以安排一些需要专注的事情。"
        else:
            pace = "今天能量中等,适合保持温和节奏。"
        weather_text = str(weather or "").strip()
        weather_text = weather_text.rstrip("。！？!?,,；; ")
        weather_part = f"天气：{weather_text}。" if weather_text and weather_text != "暂无天气信息" else ""
        cause_part = f" 身体不太舒服更像是因为{health_cause}。" if health_cause else ""
        detail_parts = []
        if sleep and sleep != "睡眠平稳":
            detail_parts.append(f"睡眠：{sleep}")
        if dream and dream != "没有记住梦":
            detail_parts.append(f"梦境：{dream}")
        if health and health != "状态正常" and not self._is_inapplicable_state_text(health):
            detail_parts.append(f"健康：{health}")
        if hunger and hunger != "饥饿感平稳" and not self._is_inapplicable_state_text(hunger):
            detail_parts.append(f"饥饿：{hunger}")
        if body_cycle and body_cycle != "无明显周期影响" and not self._is_inapplicable_state_text(body_cycle):
            detail_parts.append(f"周期：{body_cycle}")
        detail_text = (" " + "；".join(detail_parts) + "。") if detail_parts else ""
        return (
            f"{pace} 情绪底色偏{mood_bias}。"
            f"{weather_part}{cause_part}"
            f"{detail_text}"
        )

    def _is_daily_plan_due(self) -> bool:
        plan_minutes = self._parse_hhmm_to_minutes(self.daily_plan_time)
        if plan_minutes is None:
            plan_minutes = 7 * 60 + 30
        now = datetime.now()
        return now.hour * 60 + now.minute >= plan_minutes

    def _daily_plan_due_minutes(self) -> int:
        plan_minutes = self._parse_hhmm_to_minutes(self.daily_plan_time)
        if plan_minutes is None:
            return 7 * 60 + 30
        return plan_minutes

    def _is_plan_date_active(self, plan_date: str) -> bool:
        plan_date = str(plan_date or "").strip()
        if not plan_date:
            return False
        today = datetime.now().date()
        today_key = _date_key(today)
        if plan_date == today_key:
            return True
        yesterday_key = _date_key(today - timedelta(days=1))
        if plan_date != yesterday_key:
            return False
        now_minutes = datetime.now().hour * 60 + datetime.now().minute
        return now_minutes < self._daily_plan_due_minutes()

    def _get_active_plan(self) -> dict[str, Any]:
        plan = self.data.get("daily_plan", {})
        if isinstance(plan, dict) and self._is_plan_date_active(plan.get("date")):
            return plan
        return {}

    def _effective_plan_now_minutes(self, plan_date: str) -> int | None:
        plan_date = str(plan_date or "").strip()
        if not self._is_plan_date_active(plan_date):
            return None
        now_minutes = datetime.now().hour * 60 + datetime.now().minute
        if plan_date == _today_key():
            return now_minutes
        return 24 * 60 + now_minutes

    def _is_sleepy_plan_item(self, item: dict[str, Any] | None) -> bool:
        if not isinstance(item, dict):
            return False
        text = f"{_single_line(item.get('activity'), 80)} {_single_line(item.get('mood'), 20)}".strip()
        return any(
            token in text
            for token in ("睡", "洗漱", "休息", "躺", "困", "倦", "发呆", "收声", "准备睡觉", "准备休息")
        )

    def _segment_end_minutes(
        self,
        start: int,
        item: dict[str, Any] | None,
        *,
        next_start: int | None = None,
    ) -> int:
        if next_start is not None:
            return next_start
        if self._is_sleepy_plan_item(item):
            return min(24 * 60 + 240, start + 240)
        return min(24 * 60 + 120, start + 180)

    def _parse_hhmm_to_minutes(self, value: Any) -> int | None:
        match = re.fullmatch(r"\s*(\d{1,2}):(\d{2})\s*", str(value or ""))
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        if hour > 23 or minute > 59:
            return None
        return hour * 60 + minute

    def _minutes_to_hhmm(self, minutes: int) -> str:
        minutes = max(0, int(minutes))
        wrapped = minutes % (24 * 60)
        return f"{wrapped // 60:02d}:{wrapped % 60:02d}"

    async def _generate_daily_plan(self) -> dict[str, Any]:
        await self._ensure_yesterday_conversation_summary()
        return await generate_daily_plan(self)

    def _get_schedule_planning_prompt(self) -> str:
        return get_schedule_planning_prompt(self)

    def _build_daily_plan_prompt(self, now: str) -> str:
        return build_daily_plan_prompt(self, now)

    async def _ensure_yesterday_conversation_summary(self, force: bool = False) -> dict[str, Any]:
        today = _today_key()
        cached = self.data.get("yesterday_conversation_summary", {})
        if isinstance(cached, dict) and cached.get("date") == today and not force:
            return cached
        raw_text = await self._collect_yesterday_conversation_text()
        if not raw_text:
            summary = {
                "date": today,
                "source_date": _date_key(date.today() - timedelta(days=1)),
                "summary": "暂无可用的昨日完整对话摘要。",
                "residues": [],
                "schedule_reference": "无明确可继承影响。",
                "dream_reference": "无明确可继承碎片。",
                "raw_excerpt_chars": 0,
            }
        else:
            summary = await self._summarize_yesterday_conversation_for_schedule(raw_text)
        async with self._data_lock:
            self.data["yesterday_conversation_summary"] = summary
            self._save_data_sync()
        return summary

    async def _collect_yesterday_conversation_text(self) -> str:
        users = self.data.get("users", {})
        if not isinstance(users, dict):
            return ""
        yesterday = date.today() - timedelta(days=1)
        start = datetime.combine(yesterday, datetime.min.time()).timestamp()
        end = start + 24 * 3600
        blocks: list[str] = []
        for user_id, raw_user in users.items():
            if not isinstance(raw_user, dict):
                continue
            umo = str(raw_user.get("umo") or "").strip()
            if not umo:
                continue
            try:
                conv_id = await self.context.conversation_manager.get_curr_conversation_id(umo)
                if not conv_id:
                    continue
                conv = await self.context.conversation_manager.get_conversation(umo, conv_id)
            except Exception as exc:
                logger.debug("[PrivateCompanion] 读取昨日对话失败: user=%s err=%s", user_id, exc)
                continue
            history = self._load_conversation_history_items(conv)
            dated_lines: list[str] = []
            undated_lines: list[str] = []
            for item in history:
                line = self._format_history_item_for_summary(item)
                if not line:
                    continue
                ts = self._history_item_timestamp(item)
                if ts is None:
                    undated_lines.append(line)
                elif start <= ts < end:
                    dated_lines.append(line)
            selected = dated_lines if dated_lines else undated_lines[-120:]
            if not selected:
                continue
            name = _single_line(raw_user.get("nickname") or user_id, 30)
            source_note = "昨日对话" if dated_lines else "最近对话（history 无时间戳,作为昨日摘要候选）"
            blocks.append(f"【{name}｜{source_note}】\n" + "\n".join(selected))
        return "\n\n".join(blocks).strip()[-18000:]

    def _load_conversation_history_items(self, conversation: Conversation | None) -> list[dict[str, Any]]:
        if conversation is None:
            return []
        try:
            loaded = json.loads(conversation.history or "[]")
        except Exception:
            return []
        if not isinstance(loaded, list):
            return []
        return [item for item in loaded if isinstance(item, dict)]

    def _history_item_timestamp(self, item: dict[str, Any]) -> float | None:
        for key in ("timestamp", "time", "created_at", "updated_at", "created", "date"):
            value = item.get(key)
            if value is None or value == "":
                continue
            numeric = _safe_float(value, 0)
            if numeric > 0:
                return numeric / 1000 if numeric > 10_000_000_000 else numeric
            text = str(value).strip()
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m-%d %H:%M:%S", "%m-%d %H:%M"):
                try:
                    parsed = datetime.strptime(text, fmt)
                    if fmt.startswith("%m"):
                        parsed = parsed.replace(year=date.today().year)
                    return parsed.timestamp()
                except Exception:
                    continue
        return None

    def _format_history_item_for_summary(self, item: dict[str, Any]) -> str:
        role = _single_line(item.get("role") or item.get("type") or item.get("speaker"), 20).lower()
        if role in {"assistant", "bot", "ai"}:
            speaker = self.bot_name
        elif role in {"user", "human"}:
            speaker = "用户"
        else:
            speaker = role or "对话"
        content = self._history_item_content_text(item)
        if not content:
            return ""
        ts = self._history_item_timestamp(item)
        time_prefix = datetime.fromtimestamp(ts).strftime("%m-%d %H:%M") + " " if ts else ""
        return f"{time_prefix}{speaker}: {content}"

    def _history_item_content_text(self, item: dict[str, Any]) -> str:
        value = item.get("content")
        if value is None:
            value = item.get("message") or item.get("text") or item.get("content_text")
        if isinstance(value, str):
            return _single_line(value, 260)
        if isinstance(value, list):
            parts: list[str] = []
            for part in value:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    text = part.get("text") or part.get("content") or part.get("message")
                    if text:
                        parts.append(str(text))
                    elif str(part.get("type") or "").lower() == "image":
                        parts.append("[图片]")
            return _single_line(" ".join(parts), 260)
        if isinstance(value, dict):
            return _single_line(value.get("text") or value.get("content") or json.dumps(value, ensure_ascii=False), 260)
        return ""

    async def _summarize_yesterday_conversation_for_schedule(self, raw_text: str) -> dict[str, Any]:
        today = _today_key()
        source_date = _date_key(date.today() - timedelta(days=1))
        prompt = f"""
请阅读下面的昨日/最近完整对话材料,为今天的日程和梦境生成提炼参考摘要。

目标不是复述聊天,而是找出可能延续到今天的“残留影响”：身体状态、饮食/作息、情绪余波、关系变化、未完成约定、收到/送出的东西、外出计划、压力来源、被安慰/被打断的事、梦境可能用到的物件/颜色/气味/半句话等。

重要原则：
1. 只根据对话内容做合理推断,不要硬套固定事件类型。
2. 如果某个行为可能带来身体或日程后果,用抽象逻辑表达：饮食、睡眠、天气、运动、情绪刺激、约定、礼物、争执、安慰等都可能改变今天的体力、胃口、心情、出门意愿或主动话题。
3. 影响可以很轻,也可以没有。不要为了制造剧情强行让今天出事。
4. 摘要要给日程模型用,所以写成可执行参考,不是聊天回复。
5. 梦境参考只提炼碎片和情绪质感,不要编完整梦。

对话材料：
{raw_text}

只输出 JSON：
{{
  "summary": "昨日对话的一句话概括",
  "residues": [
    {{"type": "身体/情绪/关系/计划/物件/梦境碎片", "content": "可延续影响", "strength": "轻/中/强"}}
  ],
  "schedule_reference": "今天生成日程时应如何自然继承这些残留；没有就写无明确影响",
  "dream_reference": "今天梦境/梦境碎片可以参考的物件、感官、半句话或情绪；没有就写无明确碎片"
}}
""".strip()
        raw = await self._llm_call(
            prompt,
            max_tokens=650,
            provider_id=self._task_provider(self.history_summary_provider_id, self.daily_plan_provider_id, self.mai_style_provider_id),
            task="yesterday_summary",
        )
        payload = self._extract_json_payload(raw or "")
        if not isinstance(payload, dict):
            return {
                "date": today,
                "source_date": source_date,
                "summary": _single_line(raw_text, 180) or "昨日对话有记录,但摘要生成失败。",
                "residues": [],
                "schedule_reference": "可把昨日互动作为轻微关系和情绪背景,不要强行改写今日主线。",
                "dream_reference": "可从昨日对话里的物件、语气和半句话提取梦境碎片。",
                "raw_excerpt_chars": len(raw_text),
            }
        residues = payload.get("residues", [])
        if not isinstance(residues, list):
            residues = []
        normalized_residues = []
        for item in residues[:8]:
            if not isinstance(item, dict):
                continue
            content = _single_line(item.get("content"), 120)
            if not content:
                continue
            normalized_residues.append({
                "type": _single_line(item.get("type"), 24) or "残留",
                "content": content,
                "strength": _single_line(item.get("strength"), 8) or "轻",
            })
        return {
            "date": today,
            "source_date": source_date,
            "summary": _single_line(payload.get("summary"), 180) or "昨日对话有一些可延续的情绪和生活残留。",
            "residues": normalized_residues,
            "schedule_reference": _single_line(payload.get("schedule_reference"), 220) or "作为轻微背景承接,不要强行改写今日主线。",
            "dream_reference": _single_line(payload.get("dream_reference"), 220) or "从昨日对话的物件、感官和半句话中轻取梦境碎片。",
            "raw_excerpt_chars": len(raw_text),
        }

    def _format_yesterday_conversation_summary_for_prompt(self) -> str:
        summary = self.data.get("yesterday_conversation_summary", {})
        if not isinstance(summary, dict) or summary.get("date") != _today_key():
            return "暂无昨日完整对话摘要。"
        lines = [
            f"来源日期：{summary.get('source_date') or '昨日'}",
            f"概括：{_single_line(summary.get('summary'), 180)}",
            f"日程参考：{_single_line(summary.get('schedule_reference'), 220)}",
            f"梦境参考：{_single_line(summary.get('dream_reference'), 220)}",
        ]
        residues = summary.get("residues", [])
        if isinstance(residues, list) and residues:
            lines.append("残留变量：")
            for item in residues[:8]:
                if not isinstance(item, dict):
                    continue
                content = _single_line(item.get("content"), 120)
                if content:
                    lines.append(f"- {item.get('type') or '残留'}｜{content}｜强度 {item.get('strength') or '轻'}")
        return "\n".join(lines)

    def _build_detail_enhancement_prompt(
        self,
        segment: dict[str, Any],
        plan: dict[str, Any],
        state: dict[str, Any],
    ) -> str:
        return build_detail_enhancement_prompt(self, segment, plan, state)

    def _get_default_persona_prompt(self) -> str:
        try:
            persona = self.context.persona_manager.get_default_persona_v3()
            if isinstance(persona, dict):
                prompt = str(persona.get("prompt") or "").strip()
                if prompt:
                    return prompt
        except Exception as e:
            logger.warning(f"[PrivateCompanion] 读取 AstrBot 默认人格失败: {e}")
        return "未读取到 AstrBot 默认人格。请保持简洁、温和、有边界,不额外创造新身份。"

    def _persona_state_profile(self) -> dict[str, bool]:
        prompt = self._get_default_persona_prompt()
        text = str(prompt or "").lower()
        strong_non_human_markers = (
            "机器人", "机械体", "机体", "仿生", "android", "robot", "电子生命", "终端人格"
        )
        soft_non_human_markers = (
            "bot", "系统", "程序", "ai"
        )
        explicitly_human_markers = (
            "人类", "学生", "上班", "工作", "生活", "年龄", "岁",
            "吃饭", "睡觉", "起床", "洗漱", "身体", "生理期"
        )
        has_human_markers = any(marker in text for marker in explicitly_human_markers)
        has_strong_non_human = any(marker in text for marker in strong_non_human_markers)
        soft_non_human_hits = sum(1 for marker in soft_non_human_markers if marker in text)
        is_non_human = (has_strong_non_human or soft_non_human_hits >= 2) and not has_human_markers
        return {
            "non_human": is_non_human,
            "allow_health": not is_non_human,
            "allow_hunger": not is_non_human,
            "allow_cycle": not is_non_human and self.enable_cycle_state,
        }

    def _base_state_values(self) -> dict[str, str]:
        profile = self._persona_state_profile()
        values = {
            "sleep": "睡眠平稳",
            "dream": "没有记住梦",
            "health": "状态正常",
            "hunger": "饥饿感平稳",
            "body_cycle": "无明显周期影响",
            "location": "地点感平稳",
        }
        if profile.get("non_human"):
            values["health"] = "该人格不适用生病状态"
            values["hunger"] = "该人格不适用饥饿状态"
            values["body_cycle"] = "该人格不适用周期状态"
        return values

    def _is_inapplicable_state_text(self, text: str) -> bool:
        return "不适用" in str(text or "")

    def _should_show_condition(self, cond: dict[str, Any]) -> bool:
        if not isinstance(cond, dict):
            return False
        if _safe_int(cond.get("energy_delta"), 0) != 0:
            return True
        if _single_line(cond.get("mood"), 20) not in {"", "平稳"}:
            return True
        if cond.get("cause") or cond.get("phase"):
            return True
        return str(cond.get("kind") or "") not in {"sleep", "dream"}

    def _format_can_do_for_prompt(self) -> str:
        items = self.data.get("can_do", [])
        if not isinstance(items, list) or not items:
            return "（暂未设置）"
        lines = []
        for item in items[:30]:
            text = _single_line(item, 80)
            if text:
                lines.append(f"- {text}")
        return "\n".join(lines) if lines else "（暂未设置）"

    def _format_schedule_adjustments_for_prompt(self) -> str:
        raw = self.data.get("schedule_adjustments", [])
        if not isinstance(raw, list) or not raw:
            return "（暂无）"
        now = _now_ts()
        kept = []
        lines = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            expires_at = _safe_float(item.get("expires_at"), 0)
            if expires_at > 0 and expires_at <= now:
                continue
            date_text = _single_line(item.get("date"), 16)
            if date_text and date_text != _today_key():
                continue
            kept.append(item)
            note = _single_line(item.get("note"), 120)
            source = _single_line(item.get("source"), 24)
            user_text = _single_line(item.get("user_text"), 80)
            intensity = _single_line(item.get("intensity"), 16)
            scope = _single_line(item.get("scope"), 30)
            if note:
                meta = "｜".join(part for part in (source or "互动", intensity, scope) if part)
                lines.append(f"- {meta}：{note}")
            if user_text:
                lines.append(f"  用户原话摘要：{user_text}")
            immediate = _single_line(item.get("immediate_reaction"), 120)
            if immediate:
                lines.append(f"  即时反应：{immediate}")
            updates = item.get("state_updates")
            if isinstance(updates, list) and updates:
                update_text = "；".join(
                    _single_line(update, 60)
                    for update in updates
                    if _single_line(update, 60)
                )
                if update_text:
                    lines.append(f"  状态变量更新：{update_text}")
            carry = _single_line(item.get("carry_rule"), 120)
            if carry:
                lines.append(f"  承接要求：{carry}")
        if len(kept) != len(raw):
            self.data["schedule_adjustments"] = kept[-12:]
        return "\n".join(lines[-12:]) if lines else "（暂无）"

    def _current_detail_segment_for_update(self) -> dict[str, Any] | None:
        plan = self.data.get("daily_plan", {})
        if not isinstance(plan, dict) or not self._is_plan_date_active(plan.get("date")):
            return None
        now_minutes = self._effective_plan_now_minutes(str(plan.get("date") or ""))
        if now_minutes is None:
            return None
        for segment in self._collect_detail_segments(plan, {}):
            start = _safe_int(segment.get("start"), 0)
            end = _safe_int(segment.get("end"), self._segment_end_minutes(start, segment.get("item")))
            lead = max(0, self.detail_enhancement_lead_minutes)
            if start - lead <= now_minutes < end:
                return segment
        return None

    def _current_detail_state_variables(self) -> list[dict[str, str]]:
        segment = self._current_detail_segment_for_update()
        if not segment:
            return []
        enhanced = self.data.get("detail_enhanced_segments", {})
        if not isinstance(enhanced, dict):
            return []
        snapshot = enhanced.get(str(segment.get("key") or ""))
        if not isinstance(snapshot, dict):
            return []
        variables = snapshot.get("state_variables", [])
        if not isinstance(variables, list):
            return []
        return [item for item in variables if isinstance(item, dict)]

    def _detect_schedule_adjustment_from_interaction(self, text: str) -> dict[str, Any] | None:
        normalized = _single_line(text, 220)
        if not normalized:
            return None
        current_variables = self._current_detail_state_variables()
        variable_text = " ".join(
            f"{item.get('name', '')}:{item.get('value', '')} {item.get('note', '')}"
            for item in current_variables[:8]
        )
        def payload(
            *,
            source: str,
            note: str,
            immediate_reaction: str,
            state_updates: list[str],
            intensity: str = "中",
            scope: str = "当前段和下一段",
            carry_rule: str = "后续细化必须把这次用户介入当成已经发生的事实承接,不要只当成一句无影响的聊天。",
        ) -> dict[str, Any]:
            return {
                "source": source,
                "note": note,
                "immediate_reaction": immediate_reaction,
                "state_updates": state_updates,
                "intensity": intensity,
                "scope": scope,
                "carry_rule": carry_rule,
                "user_text": normalized,
            }

        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        current_activity_text = ""
        if isinstance(current_item, dict):
            current_activity_text = " ".join(
                _single_line(current_item.get(key), 80)
                for key in ("activity", "mood", "message_seed")
            )
        is_actual_rest_segment = any(
            token in current_activity_text
            for token in ("睡", "午休", "休息", "躺", "被窝", "枕头", "入睡", "准备睡", "睡前", "小睡", "补觉", "眯一会")
        )
        if is_actual_rest_segment and not re.search(r"别吵|别发|别找|安静|闭嘴|先别|不要来|忙|我有事|没空", normalized):
            prior_wakes = 0
            segment = self._current_detail_segment_for_update()
            enhanced = self.data.get("detail_enhanced_segments", {})
            if isinstance(segment, dict) and isinstance(enhanced, dict):
                snapshot = enhanced.get(str(segment.get("key") or ""))
                updates = snapshot.get("interaction_updates", []) if isinstance(snapshot, dict) else []
                if isinstance(updates, list):
                    prior_wakes = sum(
                        1 for update in updates
                        if isinstance(update, dict) and "唤醒" in str(update.get("source") or "")
                    )
            if prior_wakes > 0:
                return payload(
                    source="睡眠中再次被唤醒",
                    note="当前日程处于休息/睡眠段,用户又发来消息；回复应带一点被重新叫醒的迟钝感,但不要埋怨用户。若用户继续聊,可以慢慢醒一点；若用户停下,她会很快继续睡回去。",
                    immediate_reaction="她又被消息轻轻拽醒一下,反应会慢半拍,像从被窝或半梦里抬头。",
                    state_updates=["清醒程度：再次被唤起/半梦半醒", "语气：慢半拍、短一点", "后续安排：用户不继续打扰就继续睡"],
                    intensity="中",
                    scope="当前休息段",
                    carry_rule="当前段回复必须有刚被重新唤起的感觉；如果后续没有用户消息,下一段细化应让她继续休息或睡回去。",
                )
            return payload(
                source="睡眠中被用户唤醒",
                note="当前日程处于休息/睡眠段,用户发来消息把她轻轻叫醒；回复应像刚醒或半梦半醒,不要立刻精神饱满。若用户没有继续打扰,后续应自然睡回去或继续休息。",
                immediate_reaction="她会先迷糊地看一眼消息,像刚从睡意里被捞起来,反应慢一点。",
                state_updates=["清醒程度：刚被唤醒/迷糊", "语气：轻、短、带睡意", "后续安排：用户不继续打扰就继续睡"],
                intensity="强",
                scope="当前休息段和后续短时间",
                carry_rule="回复与后续细化必须承接“刚被用户唤醒”：先迷糊回应；如果没有连续聊天,不要强行清醒活动,要睡回去或继续休息。",
            )

        if re.search(r"换元|代入|公式|思路|解法|答案|步骤|这题|函数题|数学题|阅读题|作文|作业|代码|报错|bug|怎么写|这样做|你试试|应该是", normalized):
            updates = ["学习/作业进度：因用户提供思路而推进", "情绪：卡住->松一口气"]
            if re.search(r"卡|函数|数学|作业", variable_text):
                updates.insert(0, "卡住点：用户提示后得到缓解")
            return payload(
                source="用户帮助",
                note="用户刚刚提供了和当前任务相关的帮助；当前任务不再按原本卡住状态推进,后续时间段要继承“被帮助后松动/推进”的结果。",
                immediate_reaction="看到用户给的思路后,她先照着试了一下；如果确实对上当前任务,心里会明显松一口气。",
                state_updates=updates,
                intensity="强",
                scope="当前段、下一段、今日后续",
                carry_rule="如果后续仍写学习/作业/任务,必须体现已经被用户提示影响过：进度推进、情绪松动、或换了做法。",
            )
        if re.search(r"去睡|早点睡|睡觉|休息|别写了|别弄了|先洗澡|先吃饭|吃点|喝水|别熬|躺会|停一下|歇会", normalized):
            return payload(
                source="用户照顾",
                note="用户刚刚给了休息或照顾指令；后续节奏应明显调慢,更可能提前收尾、补充休息、喝水吃饭或把任务延后。",
                immediate_reaction="她看到这句会停一下手里的事,嘴上可能不立刻答应,但动作会慢下来一点。",
                state_updates=["体力：消耗放缓/略微回稳", "情绪：被照顾后的柔和", "后续安排：更倾向提前收尾或补充休息"],
                intensity="强",
                scope="当前段和今日后续",
                carry_rule="下一段不能完全无视这句照顾提醒；至少要在节奏、体力或收尾方式上留下影响。",
            )
        if re.search(r"一起|陪你|陪我|等我|等你|我来|我陪|待会|一会|晚上|明天|等下|约|见面|打电话|语音|开黑|一起看", normalized):
            return payload(
                source="用户约定",
                note="用户刚刚给出陪伴、等待、稍后一起做事或约定线索；后续日程应保留期待/等待/预留空档,不要像没有约定一样推进。",
                immediate_reaction="她会把这句话在心里放一下,后续做事时更容易分神看时间或看消息。",
                state_updates=["等待/期待：上升", "后续安排：可能预留空档", "主动话题：围绕约定轻轻回勾"],
                intensity="强",
                scope="今日后续",
                carry_rule="后续主动契机和细化事件要把这个约定当作开放话头,可以等待、预留时间或轻轻提醒。",
            )
        if re.search(r"我在|回你|刚看到|来了|在呢|嗯|好|可以|收到|行|可以呀|好呀|嗯嗯|哦哦", normalized):
            return payload(
                source="用户回应",
                note="用户刚刚回应了角色；当前段应更新等待回复和分享欲状态,后续表达可以更轻快一点。",
                immediate_reaction="看到回复后,她会很快扫一眼屏幕,刚才悬着的那点等待感落下来。",
                state_updates=["等待回复：是->否", "情绪：轻快一点", "分享欲：小幅上升"],
                intensity="中",
                scope="当前段和下一段",
            )
        care = self._detect_care_feedback(normalized)
        if care.get("is_care"):
            return payload(
                source="用户关心",
                note="用户刚刚给了关心或照顾提醒；后续日程需要从低落/烦躁向被安抚后的柔和、慢慢回稳偏移,不要升级破坏性冲动。",
                immediate_reaction="她看到关心会先顿一下,语气和动作都比刚才软一点。",
                state_updates=["情绪：低落/烦躁->被接住一点", "体力：主观疲惫感略降"],
                intensity="中",
                scope="当前段、下一段、情绪底色",
            )
        if re.search(r"摸摸|抱抱|亲亲|揉揉|陪你|哄你|乖|不难过|别难过|没关系|辛苦了|抱一下", normalized):
            return payload(
                source="安慰互动",
                note="用户刚刚在安慰或亲近；后续日程应保留一点被接住的余温,表达更软一些,不要继续单向累积负面情绪。",
                immediate_reaction="她会把刚才绷着的劲松下来一点,可能短暂地想贴近用户。",
                state_updates=["情绪：紧绷->柔和", "亲近感：上升"],
                intensity="中",
                scope="当前段和情绪底色",
            )
        if re.search(r"开心|好耶|哈哈|笑死|可爱|喜欢|太好了|真好|一起|陪我|想你", normalized):
            return payload(
                source="正向互动",
                note="用户刚刚给了轻松或正向回应；后续日程应多一点回弹、分享欲和轻松停顿。",
                immediate_reaction="她看到这句会忍不住轻一下,手头事情也没那么难熬了。",
                state_updates=["情绪：回弹", "分享欲：上升"],
                intensity="中",
                scope="当前段和下一段",
            )
        if re.search(r"别生气|不要烦|冷静|别急|别砸|别摔|别骂|别打", normalized):
            return payload(
                source="边界提醒",
                note="用户提醒降低攻击性或破坏性表达；后续日程必须把烦躁写成收着的动作,避免砸、摔、扔、打这类冲动。",
                immediate_reaction="她会把那点冲劲压回去,改成少说两句或把东西放远一点。",
                state_updates=["情绪：冲动->收住", "行为边界：避免破坏性动作"],
                intensity="强",
                scope="今日后续",
                carry_rule="后续所有细化都必须遵守这个边界,不能再输出破坏性动作或攻击性冲动。",
            )
        if re.search(r"别吵|别发|别找|安静|闭嘴|先别|不要来|忙|我有事|没空", normalized):
            return payload(
                source="用户边界",
                note="用户刚刚表达边界或忙碌；后续主动应明显收敛,减少追问和贴近,让日程转向自我消化。",
                immediate_reaction="她会把原本想继续靠近的动作收住,把消息窗口放到一边。",
                state_updates=["主动欲：下降", "关系状态：后退一点", "后续安排：转向自我消化"],
                intensity="强",
                scope="今日后续主动策略",
                carry_rule="后续主动消息必须降低频率和压迫感,不要把边界当作可撒娇突破的对象。",
            )
        return None

    def _record_schedule_adjustment_from_interaction(self, text: str) -> bool:
        adjustment = self._detect_schedule_adjustment_from_interaction(text)
        if not adjustment:
            return False
        raw = self.data.setdefault("schedule_adjustments", [])
        if not isinstance(raw, list):
            raw = []
            self.data["schedule_adjustments"] = raw
        note = _single_line(adjustment.get("note"), 140)
        if not note:
            return False
        now = _now_ts()
        intensity = _single_line(adjustment.get("intensity"), 16) or "中"
        ttl_hours = 18 if intensity == "强" else 10 if intensity == "中" else 6
        item = {
            "date": _today_key(),
            "source": _single_line(adjustment.get("source"), 24),
            "note": note,
            "immediate_reaction": _single_line(adjustment.get("immediate_reaction"), 140),
            "state_updates": adjustment.get("state_updates", []),
            "user_text": _single_line(adjustment.get("user_text"), 120),
            "intensity": intensity,
            "scope": _single_line(adjustment.get("scope"), 40),
            "carry_rule": _single_line(adjustment.get("carry_rule"), 160),
            "created_at": now,
            "expires_at": now + ttl_hours * 3600,
        }
        self._record_detail_interaction_update(item)
        if raw and isinstance(raw[-1], dict) and raw[-1].get("note") == note:
            raw[-1].update(item)
        else:
            raw.append(item)
            del raw[:-12]
        self._invalidate_detail_after_interaction(now=now)
        return True

    @staticmethod
    def _parse_state_update_text(update: Any) -> tuple[str, str, str]:
        text = _single_line(update, 120)
        if not text:
            return "", "", ""
        if "：" in text:
            name, value = text.split("：", 1)
        elif ":" in text:
            name, value = text.split(":", 1)
        else:
            return text[:24], "已受用户介入影响", text
        return _single_line(name, 32), _single_line(value, 60), text

    def _apply_interaction_to_snapshot_state(self, snapshot: dict[str, Any], item: dict[str, Any]) -> None:
        raw_updates = item.get("state_updates", [])
        if not isinstance(raw_updates, list):
            raw_updates = []
        variables = snapshot.setdefault("state_variables", [])
        if not isinstance(variables, list):
            variables = []
            snapshot["state_variables"] = variables
        index_by_name = {
            _single_line(variable.get("name"), 32): variable
            for variable in variables
            if isinstance(variable, dict) and _single_line(variable.get("name"), 32)
        }
        for update in raw_updates:
            name, value, note = self._parse_state_update_text(update)
            if not name:
                continue
            variable = index_by_name.get(name)
            if isinstance(variable, dict):
                variable["value"] = value or variable.get("value") or "已更新"
                variable["note"] = f"用户介入：{note}" if note else "用户介入后更新"
            else:
                variable = {
                    "name": name,
                    "value": value or "已更新",
                    "note": f"用户介入：{note}" if note else "用户介入后更新",
                }
                variables.append(variable)
                index_by_name[name] = variable
        summary = _single_line(snapshot.get("summary"), 140)
        reaction = _single_line(item.get("immediate_reaction"), 90)
        if reaction and reaction not in summary:
            snapshot["summary"] = _single_line(
                f"{summary}；用户介入后：{reaction}" if summary else f"用户介入后：{reaction}",
                160,
            )

    def _record_detail_interaction_update(self, item: dict[str, Any]) -> None:
        segment = self._current_detail_segment_for_update()
        if not segment:
            return
        enhanced = self.data.get("detail_enhanced_segments", {})
        if not isinstance(enhanced, dict):
            return
        key = str(segment.get("key") or "")
        snapshot = enhanced.get(key)
        if not isinstance(snapshot, dict):
            return
        updates = snapshot.setdefault("interaction_updates", [])
        if not isinstance(updates, list):
            updates = []
            snapshot["interaction_updates"] = updates
        updates.append(
            {
                "at": datetime.now().strftime("%H:%M"),
                "source": _single_line(item.get("source"), 24),
                "user_text": _single_line(item.get("user_text"), 80),
                "intensity": _single_line(item.get("intensity"), 16),
                "scope": _single_line(item.get("scope"), 40),
                "reaction": _single_line(item.get("immediate_reaction"), 140),
                "state_updates": item.get("state_updates", []),
            }
        )
        del updates[:-6]
        self._apply_interaction_to_snapshot_state(snapshot, item)

    def _invalidate_detail_after_interaction(self, *, now: float | None = None) -> None:
        plan = self.data.get("daily_plan", {})
        if not isinstance(plan, dict) or not self._is_plan_date_active(plan.get("date")):
            return
        now_minutes = self._effective_plan_now_minutes(str(plan.get("date") or ""))
        if now_minutes is None:
            return
        enhanced = self.data.get("detail_enhanced_segments", {})
        if isinstance(enhanced, dict):
            for segment in self._collect_detail_segments(plan, {}):
                start = _safe_int(segment.get("start"), 0)
                if start > now_minutes:
                    key = str(segment.get("key") or "")
                    if key in enhanced:
                        enhanced.pop(key, None)
        story_plan = self.data.get("daily_story_plan", {})
        if isinstance(story_plan, dict):
            for key in ("today_events", "proactive_events"):
                items = story_plan.get(key, [])
                if not isinstance(items, list):
                    continue
                kept = []
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    start, end = self._parse_window_minutes(str(item.get("window") or ""))
                    if start is None or end is None:
                        kept.append(item)
                        continue
                    if end < start:
                        end += 24 * 60
                    if start <= now_minutes:
                        kept.append(item)
                story_plan[key] = kept

    def _infer_location_from_text(self, text: str) -> str:
        normalized = _single_line(text, 200)
        if not normalized:
            return ""
        location_rules = [
            (("被窝", "床上", "床边", "卧室", "房间", "书桌", "台灯", "家里", "客厅", "沙发", "洗漱台", "餐桌"), "家里"),
            (("教室", "课间", "食堂", "校门", "走廊", "操场", "上课", "下课", "自习", "老师", "书包", "制服"), "学校"),
            (("工位", "会议", "办公室", "上班", "下班", "通勤", "打卡"), "工作场所"),
            (("便利店", "超市", "商店"), "便利店附近"),
            (("路上", "街上", "出门", "楼下", "外面", "街边", "回家路上", "校门口"), "外面"),
            (("楼梯口", "走廊栏杆", "窗边", "阳台"), "过道或窗边"),
        ]
        for keywords, label in location_rules:
            if any(keyword in normalized for keyword in keywords):
                return label
        return ""

    def _current_location_state_text(self, state: dict[str, Any] | None = None) -> str:
        snapshot = self._current_story_plan_snapshot()
        for candidate in (
            snapshot.get("scene"),
            snapshot.get("event"),
        ):
            inferred = self._infer_location_from_text(str(candidate or ""))
            if inferred:
                return inferred
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        if isinstance(current_item, dict):
            inferred = self._infer_location_from_text(
                f"{_single_line(current_item.get('activity'), 120)} {_single_line(current_item.get('message_seed'), 120)}"
            )
            if inferred:
                return inferred
        if isinstance(state, dict):
            fallback = _single_line(state.get("location"), 40)
            if fallback and fallback not in {"", "地点感平稳"}:
                return fallback
        return ""

    def _format_state_for_prompt(self, state: dict[str, Any]) -> str:
        if not isinstance(state, dict) or not state:
            state = dict(DEFAULT_HUMANIZED_STATE)
            state.update(self._base_state_values())

        lines = [
            f"日期：{state.get('date') or _today_key()}",
            f"心理能量：{state.get('energy', 70)}/100",
            f"情绪底色：{state.get('mood_bias', '平稳')}",
        ]
        weather = _single_line(state.get("weather"), 120)
        if weather and weather != "暂无天气信息":
            lines.append(f"天气：{weather}")
        location_text = self._current_location_state_text(state)
        if location_text:
            lines.append(f"所在环境：{location_text}（只作生活背景）")

        detail_lines = []
        if _single_line(state.get("sleep"), 80) not in {"", "睡眠平稳"}:
            detail_lines.append(f"睡眠：{state.get('sleep')}")
        if _single_line(state.get("dream"), 80) not in {"", "没有记住梦"}:
            detail_lines.append(f"梦境：{state.get('dream')}")
        health_text = _single_line(state.get("health"), 80)
        if health_text not in {"", "状态正常"} and not self._is_inapplicable_state_text(health_text):
            detail_lines.append(f"健康：{health_text}")
        hunger_text = _single_line(state.get("hunger"), 80)
        if hunger_text not in {"", "饥饿感平稳"} and not self._is_inapplicable_state_text(hunger_text):
            detail_lines.append(f"饥饿：{hunger_text}")
        cycle_text = _single_line(state.get("body_cycle"), 80)
        if cycle_text not in {"", "无明显周期影响"} and not self._is_inapplicable_state_text(cycle_text):
            detail_lines.append(f"周期：{cycle_text}")
        if detail_lines:
            lines.append("状态细节：\n" + "\n".join(detail_lines))

        transition = self._format_state_transition_overview(state)
        if transition and transition != "暂无明显状态推进。":
            lines.append(f"状态走向：{transition}")

        condition_lines = []
        conditions = state.get("conditions", [])
        if isinstance(conditions, list):
            for cond in conditions[:8]:
                if not isinstance(cond, dict):
                    continue
                if not self._should_show_condition(cond):
                    continue
                condition_lines.append(
                    f"- {cond.get('title', cond.get('kind', '状态'))}："
                    f"{cond.get('label', '')}；情绪={cond.get('mood', '平稳')}；"
                    f"{('阶段=' + str(cond.get('phase')) + '；') if cond.get('phase') else ''}"
                    f"能量影响={cond.get('energy_delta', 0)}；"
                    f"{('原因=' + str(cond.get('cause')) + '；') if cond.get('cause') else ''}"
                    f"{self._format_transition_hint(cond)}"
                    f"剩余={self._format_remaining(cond.get('end_ts'))}"
                )
        if condition_lines:
            lines.append("当前叠加状态：\n" + "\n".join(condition_lines))

        return "\n".join(lines)

    def _format_transition_hint(self, cond: dict[str, Any]) -> str:
        options = cond.get("transition_options", [])
        if not isinstance(options, list) or not options:
            return ""
        top = sorted(
            [
                (str(item.get("to") or "").strip(), float(item.get("base_weight") or 0))
                for item in options
                if isinstance(item, dict) and str(item.get("to") or "").strip()
            ],
            key=lambda item: item[1],
            reverse=True,
        )[:2]
        if not top:
            return ""
        labels = []
        for target, _ in top:
            mapped = {
                "recovery_afterglow": "更可能转向恢复后的轻快",
                "health_tail": "也可能留下恢复尾声",
                "sleep_afterglow": "更可能补回来一点精神",
                "sleep_tail": "也可能还残一点迟钝",
                "soft_afterglow": "可能留一点被关心后的余温",
                "stable": "也可能直接回稳",
            }.get(target, target)
            labels.append(mapped)
        return f"下一步倾向={' / '.join(labels)}；"

    def _format_state_transition_overview(self, state: dict[str, Any]) -> str:
        conditions = state.get("conditions", []) if isinstance(state, dict) else []
        if not isinstance(conditions, list):
            return "暂无明显状态推进。"
        lines = []
        for cond in conditions[:4]:
            if not isinstance(cond, dict):
                continue
            title = _single_line(cond.get("title"), 30) or _single_line(cond.get("kind"), 20)
            phase = _single_line(cond.get("phase"), 24)
            hint = self._format_transition_hint(cond).replace("下一步倾向=", "").rstrip("；")
            if title and hint:
                if phase:
                    lines.append(f"{title}（{phase}）{hint}")
                else:
                    lines.append(f"{title}{hint}")
        return "；".join(lines) if lines else "暂无明显状态推进。"

    def _format_state_for_message(self, state: dict[str, Any]) -> str:
        if not isinstance(state, dict) or state.get("date") != _today_key():
            return ""
        energy = _safe_int(state.get("energy"), 70, 0, 100)
        mood = _single_line(state.get("mood_bias"), 20)
        fragments = []
        for key in ("sleep", "dream", "health", "hunger", "body_cycle"):
            value = _single_line(state.get(key), 36)
            if value and value not in {
                "睡眠平稳",
                "没有记住梦",
                "状态正常",
                "饥饿感平稳",
                "无明显周期影响",
                "该人格不适用生病状态",
                "该人格不适用饥饿状态",
                "该人格不适用周期状态",
            }:
                fragments.append(value)
        if not fragments and energy >= 55:
            return ""
        if fragments:
            detail = random.choice(fragments)
            return f"今天有点{mood},{detail}。\n所以我会慢一点。"
        return f"今天电量 {energy}/100。\n不满格,但还能运行,勉强。"

    def _format_passive_state_style_hint(self, state: dict[str, Any]) -> str:
        if not isinstance(state, dict):
            return "语气整体自然平稳。"
        energy = _safe_int(state.get("energy"), 70, 0, 100)
        mood = _single_line(state.get("mood_bias"), 20)
        hints: list[str] = []
        if energy <= 38:
            hints.append("回复可以短一点、慢一点；不要直接说状态标签、数值或内部感受说明。")
        elif energy <= 55:
            hints.append("语气可以稍微收着一点,少解释,少铺陈。")
        elif energy >= 82:
            hints.append("语气可以轻一点,但不要主动说自己精神很好。")
        if mood and mood not in {"平稳", "中性"}:
            hints.append(f"语气底色可以略偏{mood},只体现在节奏和措辞里,不要直接汇报情绪。")
        conditions = state.get("conditions", [])
        if isinstance(conditions, list):
            labels = []
            for cond in conditions[:3]:
                if not isinstance(cond, dict) or not self._should_show_condition(cond):
                    continue
                label = _single_line(cond.get("label") or cond.get("title") or cond.get("kind"), 18)
                if label:
                    labels.append(label)
            if labels:
                hints.append("叠加状态只当作语气微调：" + "、".join(labels[:2]) + "；不要把原因、阶段或数值说出来。")
        return "\n".join(hints) if hints else "语气整体自然平稳；不要主动说明状态。"

    def _format_state_injection(self, state: dict[str, Any]) -> str:
        parts = [
            "【拟人化当前状态】\n"
            "下面是完整状态资料,供你理解角色此刻的精力、耐心、情绪底色、身体感和生活连续性。\n"
            "请把它当作内部理解材料,不是回复正文。你可以据此决定语气长短、反应速度、亲近程度和话题选择,但不要照搬字段、数值、原因或日程。\n"
            "除非用户明确询问近况、状态或刚才在做什么,否则不要主动汇报状态标签、数值、原因、日程片段或内部感受说明。\n"
            "普通聊天时先回应用户正在说的那句话；禁止用“今天/今晚状态……”“我现在情绪……”“能量……”“下午/上午做了什么所以……”开场。\n"
            "状态只影响回复长度、回复速度感、语气软硬和话题选择。不要直接宣告“我累了/我吓了一跳/我正在写作业”,也不要用“差点把茶打翻/笔帽掉了/喝水呛到”这类动作描写来表演状态。\n"
            "如果确实需要表达状态,只用最短口语,例如“困了”“别说了”“有点烦”；更多时候直接接话、慢回、短回或不解释。\n"
            "如果用户表达关心、摸摸、抱抱、安慰,优先承接用户此刻的动作和情绪；不要借机解释背景或表演日常。\n\n"
            "【表达倾向提醒】\n"
            f"{self._format_passive_state_style_hint(state)}\n\n"
            "【完整状态资料】\n"
            f"{self._format_state_for_prompt(state)}"
        ]
        parts.append(
            "【当前时间感】\n"
            + self._format_time_period_injection()
        )
        life_lines: list[str] = []
        schedule_context = self._format_schedule_context_for_prompt()
        if schedule_context:
            life_lines.append(f"当前/附近日程参考：\n{schedule_context}")
        story_plan = self._format_story_plan_for_prompt()
        if story_plan and story_plan != "（暂无）":
            life_lines.append(f"今天预设的生活线索：\n{story_plan}")
        if life_lines:
            parts.append(
                "【当前生活背景】\n"
                + "\n".join(life_lines)
                + "\n这些内容只用于让回复有生活延续感；用户没问就不要提具体日程、科目、任务、天气或地点。"
                + "如果要承接,只体现在语气和话题选择里,不要照搬原句,不要写成“我正在做某事”的汇报。"
                + "回复必须像同一个连续现场里发生的对话；如果生活背景之间互相冲突,优先服从当前真实时段和当前日程,只保留最合理的一条线索。"
            )

        important_dates = self._format_important_dates_for_prompt()
        if important_dates and important_dates != "（近期没有需要特别记住的日期）":
            parts.append(
                "【近期重要日期】\n"
                f"{important_dates}\n"
                "如果用户提到相关日期、纪念、生日、约定或计划,请自然承接；不要无故强行展开。"
            )
        return "\n\n".join(parts)

    def _user_asks_recent_bot_activity(self, text: str) -> bool:
        normalized = _single_line(text, 180)
        if not normalized:
            return False
        return bool(re.search(r"(最近|刚才|现在|今天|这两天|这会儿).{0,12}(在)?(干嘛|做什么|做啥|忙什么|忙啥|弄什么|写什么|玩什么|折腾什么)|你.{0,8}(在)?(干嘛|做什么|忙什么|写什么|弄什么)", normalized))

    def _format_hidden_creative_context_for_reply(self, inbound_text: str) -> str:
        if not self.enable_creative_writing or not self._user_asks_recent_bot_activity(inbound_text):
            return ""
        candidates = []
        for project in reversed(self._creative_projects()):
            if project.get("status") not in {"drafting", "finished"}:
                continue
            chunks = project.get("draft_chunks") if isinstance(project.get("draft_chunks"), list) else []
            latest = next((item for item in reversed(chunks) if isinstance(item, dict) and _single_line(item.get("text"), 180)), None)
            candidates.append((project, latest))
            if len(candidates) >= 2:
                break
        if not candidates:
            return ""
        project, latest = candidates[0]
        title = _single_line(project.get("title"), 40)
        premise = _single_line(project.get("premise"), 120)
        progress = f"{_safe_int(project.get('current_chars'), 0, 0)}/{_safe_int(project.get('target_chars'), 2400, 1200, 5200)}"
        snippet = _single_line((latest or {}).get("text"), 180) if isinstance(latest, dict) else ""
        return (
            "【私下创作近况】\n"
            "用户正在询问你最近在做什么。你可以选择是否提到：你最近因为生活小事/梦境灵感开了一个小说坑,一直在自己慢慢写。\n"
            f"标题：{title or '未定标题'}\n"
            f"设定：{premise or '还没完全想清楚'}\n"
            f"进度：约 {progress} 字\n"
            + (f"最近一句/片段：{snippet}\n" if snippet else "")
            + "这不是必须回答的内容；如果当前聊天语境不适合,可以只含糊说“在弄一点小东西”。如果回答,要像被问到后才松口,不要主动汇报系统进度,不要一次给完整正文。"
        )

    def _current_story_plan_snapshot(self) -> dict[str, Any]:
        plan = self.data.get("daily_story_plan", {})
        if not isinstance(plan, dict) or not self._is_plan_date_active(plan.get("date")):
            return {}
        now_minutes = self._effective_plan_now_minutes(str(plan.get("date") or ""))
        if now_minutes is None:
            return {}

        snapshot: dict[str, Any] = {}
        summary = _single_line(plan.get("summary"), 120)
        if summary:
            snapshot["summary"] = summary

        current_event = None
        for item in plan.get("today_events", []):
            if not isinstance(item, dict):
                continue
            start, end = self._parse_window_minutes(str(item.get("window") or ""))
            if start is None or end is None:
                continue
            if start <= now_minutes < end:
                current_event = item
                break
        if isinstance(current_event, dict):
            snapshot["event"] = _single_line(current_event.get("event"), 100)
            snapshot["mood"] = _single_line(current_event.get("mood"), 24)

        current_proactive = None
        for item in plan.get("proactive_events", []):
            if not isinstance(item, dict):
                continue
            start, end = self._parse_window_minutes(str(item.get("window") or ""))
            if start is None or end is None:
                continue
            if start <= now_minutes < end:
                current_proactive = item
                break
        if isinstance(current_proactive, dict):
            snapshot["topic"] = _single_line(current_proactive.get("topic"), 80)
            snapshot["scene"] = _single_line(current_proactive.get("scene"), 80)
            snapshot["tone"] = _single_line(current_proactive.get("tone"), 30)
            snapshot["impulse"] = _single_line(current_proactive.get("impulse"), 100)
        return snapshot

    def _format_detail_injection(self) -> str:
        snapshot = self._current_story_plan_snapshot()
        if not snapshot:
            schedule_context = self._format_schedule_context_for_prompt()
            if not schedule_context:
                return ""
            return (
                "【当前细化片段】\n"
                "当前没有命中的精细生活片段；以下只作为附近日程的轻量参考,不要当成正在逐字发生。\n"
                f"{schedule_context}"
            )
        lines = ["【当前细化片段】"]
        if snapshot.get("summary"):
            lines.append(f"这一小段的氛围：{snapshot['summary']}")
        if snapshot.get("event"):
            event_line = f"当前这段更像是在：{snapshot['event']}"
            if snapshot.get("mood"):
                event_line += f"｜情绪：{snapshot['mood']}"
            lines.append(event_line)
        if snapshot.get("topic") or snapshot.get("scene") or snapshot.get("tone") or snapshot.get("impulse"):
            detail_bits = []
            if snapshot.get("topic"):
                detail_bits.append(f"话题钩子：{snapshot['topic']}")
            if snapshot.get("scene"):
                detail_bits.append(f"场景：{snapshot['scene']}")
            if snapshot.get("tone"):
                detail_bits.append(f"底色：{snapshot['tone']}")
            if snapshot.get("impulse"):
                detail_bits.append(f"内在冲动：{snapshot['impulse']}")
            lines.append("｜".join(detail_bits))
        segment = self._current_detail_segment_for_update()
        enhanced = self.data.get("detail_enhanced_segments", {})
        detail_snapshot = None
        if isinstance(segment, dict) and isinstance(enhanced, dict):
            detail_snapshot = enhanced.get(str(segment.get("key") or ""))
        if isinstance(detail_snapshot, dict):
            state_variables = detail_snapshot.get("state_variables", [])
            if isinstance(state_variables, list) and state_variables:
                variable_lines = []
                for variable in state_variables[:6]:
                    if not isinstance(variable, dict):
                        continue
                    name = _single_line(variable.get("name"), 24)
                    value = _single_line(variable.get("value"), 50)
                    note = _single_line(variable.get("note"), 60)
                    if name and value:
                        variable_lines.append(f"- {name}: {value}" + (f"（{note}）" if note else ""))
                if variable_lines:
                    lines.append("当前状态变量：\n" + "\n".join(variable_lines))
            interaction_updates = detail_snapshot.get("interaction_updates", [])
            if isinstance(interaction_updates, list) and interaction_updates:
                update_lines = []
                for update in interaction_updates[-3:]:
                    if not isinstance(update, dict):
                        continue
                    user_text = _single_line(update.get("user_text"), 60)
                    reaction = _single_line(update.get("reaction"), 90)
                    intensity = _single_line(update.get("intensity"), 12)
                    state_updates = update.get("state_updates")
                    state_text = ""
                    if isinstance(state_updates, list) and state_updates:
                        state_text = "；".join(_single_line(item, 50) for item in state_updates if _single_line(item, 50))
                    pieces = [part for part in (f"用户说：{user_text}" if user_text else "", f"强度：{intensity}" if intensity else "", reaction, state_text) if part]
                    if pieces:
                        update_lines.append("- " + "｜".join(pieces))
                if update_lines:
                    lines.append(
                        "用户刚刚介入后的事实更新：\n"
                        + "\n".join(update_lines)
                        + "\n回复时必须承接这些事实,不要按介入前的日程状态继续说。"
                    )
        return "\n".join(lines)

    def _format_timer_scheduling_instruction(self) -> str:
        if not self.enable_llm_timer_scheduling:
            return ""
        return """【主动消息预约】
如果你觉得这段对话晚些时候还会自然延伸一次,可以在回复末尾附一个隐藏标签：
<timer>{"time":"YYYY-MM-DD HH:MM:SS","reason":"可选","topic":"可选","motive":"可选","action":"可选"}</timer>
也可以只写时间。
这个标签用户看不到,只用来预约你下一次主动开口。
只在确实有自然后续时才写,不要每轮都加。"""

    def _extract_timer_directives(self, text: str) -> tuple[str, list[dict[str, Any]]]:
        raw_text = str(text or "")
        payloads: list[dict[str, Any]] = []
        for match in TIMER_TAG_PATTERN.finditer(raw_text):
            payload = self._parse_timer_directive(match.group(1))
            if payload:
                payloads.append(payload)
        cleaned = TIMER_TAG_PATTERN.sub("", raw_text)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned, payloads

    def _parse_timer_directive(self, raw: str) -> dict[str, Any] | None:
        content = str(raw or "").strip()
        if not content:
            return None
        payload: dict[str, Any]
        if content.startswith("{") and content.endswith("}"):
            try:
                loaded = json.loads(content)
            except Exception:
                return None
            if not isinstance(loaded, dict):
                return None
            payload = {str(key): value for key, value in loaded.items()}
        else:
            payload = {"time": content}

        time_text = ""
        for key in ("time", "timer", "at", "datetime", "date"):
            candidate = payload.get(key)
            if candidate:
                time_text = str(candidate).strip()
                break
        if not time_text:
            return None
        scheduled_ts = self._parse_timer_timestamp(time_text)
        if scheduled_ts <= 0:
            return None
        parsed: dict[str, Any] = {"scheduled_ts": scheduled_ts, "raw_time": time_text}
        for key in ("reason", "topic", "motive", "action", "style"):
            value = payload.get(key)
            if value is not None:
                parsed[key] = _single_line(value, 140 if key == "motive" else 60)
        chain = self._normalize_chain_steps(payload.get("chain"))
        if chain:
            parsed["chain"] = chain
        return parsed

    def _normalize_chain_steps(self, raw_chain: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_chain, list):
            return []
        normalized_chain: list[dict[str, Any]] = []
        for step in raw_chain[:4]:
            if not isinstance(step, dict):
                continue
            kind = _single_line(step.get("kind"), 32)
            if not kind:
                continue
            normalized_chain.append(
                {
                    "kind": kind,
                    "after_minutes": _safe_int(step.get("after_minutes"), 0, 0, 240),
                    "reason": _single_line(step.get("reason"), 40),
                    "topic": _single_line(step.get("topic"), 80),
                    "motive": _single_line(step.get("motive"), 100),
                    "tone": _single_line(step.get("tone"), 30),
                }
            )
        return normalized_chain

    def _parse_timer_timestamp(self, time_text: str) -> float:
        normalized = str(time_text or "").strip()
        if not normalized:
            return 0.0
        for fmt in SUPPORTED_TIMER_FORMATS:
            try:
                return datetime.strptime(normalized, fmt).timestamp()
            except ValueError:
                continue
        return 0.0

    def _infer_timer_reason(self, scheduled_ts: float, source_text: str = "") -> str:
        dt = datetime.fromtimestamp(scheduled_ts)
        minute = dt.hour * 60 + dt.minute
        lowered = str(source_text or "")
        if 8 * 60 <= minute <= 10 * 60 + 30:
            return "morning_greeting"
        if 12 * 60 <= minute <= 13 * 60 + 50:
            return "noon_greeting"
        if 21 * 60 <= minute <= 23 * 60 + 10:
            return "evening_greeting"
        if any(token in lowered for token in ("照片", "风景", "云", "雨", "光", "晚霞", "猫")):
            return "activity_share"
        if any(token in lowered for token in ("记下来", "那句话", "写下", "日记")):
            return "diary_share"
        return "check_in"

    def _timer_default_topic(self, reason: str, user: dict[str, Any], source_text: str = "") -> str:
        source = _single_line(source_text, 48)
        if source:
            return source
        return self._choose_proactive_topic(reason, user)

    def _timer_default_motive(
        self,
        reason: str,
        user: dict[str, Any],
        *,
        source_text: str = "",
        topic: str = "",
    ) -> str:
        if topic:
            return self._normalize_internal_motive_text(f"关于“{topic}”还有一点后续内容,适合稍后补充")
        if source_text:
            return self._normalize_internal_motive_text("刚才的话题还有一点后续内容,适合稍后补充")
        return self._choose_proactive_motive(reason, user, action="message")

    def _get_active_llm_timer(self, user: dict[str, Any]) -> dict[str, Any] | None:
        raw = user.get("llm_timer_event")
        if not isinstance(raw, dict) or not raw:
            return None
        scheduled_ts = _safe_float(raw.get("scheduled_ts"), 0)
        if scheduled_ts <= 0:
            return None
        return raw

    def _has_due_llm_timer(self, user: dict[str, Any], now: float | None = None) -> bool:
        event = self._get_active_llm_timer(user)
        if not isinstance(event, dict):
            return False
        now = now or _now_ts()
        return now >= _safe_float(event.get("scheduled_ts"), 0)

    def _clear_llm_timer_event(self, user: dict[str, Any], *, event_id: str = "") -> None:
        raw = user.get("llm_timer_event")
        if not isinstance(raw, dict):
            user["llm_timer_event"] = {}
            return
        if event_id and str(raw.get("id") or "") != event_id:
            return
        user["llm_timer_event"] = {}

    def _format_llm_timer_context(self, user: dict[str, Any], *, now: float | None = None) -> str:
        event = self._get_active_llm_timer(user)
        if not isinstance(event, dict):
            return ""
        now = now or _now_ts()
        scheduled_ts = _safe_float(event.get("scheduled_ts"), 0)
        if scheduled_ts <= 0:
            return ""
        summary_parts = ["这是你之前自己留给自己的一个回头时间。"]
        topic = _single_line(event.get("topic"), 36)
        motive = _single_line(event.get("motive"), 60)
        seed = _single_line(event.get("seed_text"), 60)
        if topic:
            summary_parts.append(f"话题线索是“{topic}”。")
        elif seed:
            summary_parts.append(f"当时留下来的那句线索是：{seed}")
        if motive:
            summary_parts.append(f"当时心里的余味：{motive}")
        if now < scheduled_ts:
            summary_parts.append(f"现在离约好的时间还差 {self._format_duration_brief(scheduled_ts - now)}。")
        return " ".join(summary_parts)

    async def _schedule_llm_timer(
        self,
        user_id: str,
        payload: dict[str, Any],
        *,
        source_text: str,
        source_origin: str,
    ) -> None:
        scheduled_ts = max(_now_ts() + 30, _safe_float(payload.get("scheduled_ts"), 0))
        if scheduled_ts <= 0:
            return
        async with self._data_lock:
            user = self._get_user(user_id)
            reason = _single_line(payload.get("reason"), 40) or self._infer_timer_reason(
                scheduled_ts,
                source_text,
            )
            action = _single_line(payload.get("action"), 24) or "message"
            if action not in {"message", "screen_peek", "photo_text", "voice"}:
                action = "message"
            topic = _single_line(payload.get("topic"), 60) or self._timer_default_topic(
                reason,
                user,
                source_text,
            )
            motive = _single_line(payload.get("motive"), 140) or self._timer_default_motive(
                reason,
                user,
                source_text=source_text,
                topic=topic,
            )
            timer_event = {
                "id": uuid.uuid4().hex,
                "scheduled_ts": scheduled_ts,
                "raw_time": _single_line(payload.get("raw_time"), 32),
                "reason": reason,
                "action": action,
                "topic": topic,
                "motive": self._normalize_internal_motive_text(motive),
                "style": _single_line(payload.get("style"), 40),
                "seed_text": _single_line(source_text, 80),
                "origin": source_origin,
                "created_at": _now_ts(),
                "chain": list(payload.get("chain") or []) if isinstance(payload.get("chain"), list) else [],
            }
            user["llm_timer_event"] = timer_event
            user["next_proactive_at"] = scheduled_ts
            user["planned_proactive_reason"] = reason
            user["planned_proactive_action"] = action
            user["planned_proactive_source"] = "timer"
            user["planned_proactive_motive"] = timer_event["motive"]
            user["planned_proactive_topic"] = topic
            user["planned_event_chain"] = list(payload.get("chain") or []) if isinstance(payload.get("chain"), list) else []
            user["planned_opener_mode"] = ""
            user["planned_followup_kind"] = ""
            user["planned_proactive_quota_exempt"] = False
            self._save_data_sync()
        logger.info(
            "[PrivateCompanion] 已记录 LLM 自预约: user=%s time=%s reason=%s action=%s topic=%s",
            user_id,
            datetime.fromtimestamp(scheduled_ts).strftime("%m-%d %H:%M:%S"),
            reason,
            action,
            topic,
        )

    def _format_remaining(self, end_ts: Any) -> str:
        seconds = _safe_float(end_ts, 0) - _now_ts()
        if seconds <= 0:
            return "已结束"
        if seconds < 3600:
            return f"{max(1, int(seconds // 60))} 分钟"
        if seconds < 86400:
            return f"{int(seconds // 3600)} 小时"
        return f"{int(seconds // 86400)} 天"

    def _format_duration_brief(self, seconds: float) -> str:
        seconds = max(0.0, float(seconds))
        if seconds < 60:
            return f"{max(1, int(seconds))} 秒"
        if seconds < 3600:
            return f"{max(1, int(seconds // 60))} 分钟"
        if seconds < 86400:
            return f"{int(seconds // 3600)} 小时"
        return f"{int(seconds // 86400)} 天"

    def _format_suspended_summary(self, user: dict[str, Any]) -> str:
        raw = user.get("suspended_proactive")
        if not isinstance(raw, dict) or not raw.get("active"):
            return "悬着的话头：无"
        opener = _single_line(raw.get("opener_text"), 40) or "已先叫了一声"
        if raw.get("resume_ready"):
            return f"悬着的话头：等到用户回头了（{opener}）"
        due_at = _safe_float(raw.get("complaint_after_ts"), 0)
        due_text = self._format_remaining(due_at) if due_at > 0 and not raw.get("complaint_sent") else "已发过后续"
        return f"悬着的话头：还挂着（{opener}｜再等 {due_text}）"

    def _split_can_do_items(self, text: str) -> list[str]:
        raw_parts = re.split(r"[,,、;；\n]+", text)
        items = []
        for part in raw_parts:
            item = _single_line(part, 80)
            if item and item not in items:
                items.append(item)
        return items

    def _add_can_do_items(self, text: str) -> list[str]:
        new_items = self._split_can_do_items(text)
        if not new_items:
            return []
        current = self.data.setdefault("can_do", [])
        if not isinstance(current, list):
            current = []
            self.data["can_do"] = current
        added = []
        existing = {str(item) for item in current}
        for item in new_items:
            if item in existing:
                continue
            current.append(item)
            existing.add(item)
            added.append(item)
        if len(current) > 50:
            del current[:-50]
        return added

    def _remove_can_do_items(self, text: str) -> list[str]:
        targets = self._split_can_do_items(text)
        if not targets:
            return []
        current = self.data.setdefault("can_do", [])
        if not isinstance(current, list):
            self.data["can_do"] = []
            return []
        removed = []
        kept = []
        for item in current:
            item_text = str(item)
            if any(target in item_text or item_text in target for target in targets):
                removed.append(item_text)
            else:
                kept.append(item)
        self.data["can_do"] = kept
        return removed

    @staticmethod
    def _estimate_token_count(text: str) -> int:
        raw = str(text or "")
        if not raw:
            return 0
        ascii_chars = sum(1 for ch in raw if ord(ch) < 128)
        non_ascii_chars = max(0, len(raw) - ascii_chars)
        return max(1, int(ascii_chars / 4.0 + non_ascii_chars / 1.6))

    @staticmethod
    def _usage_value(usage: Any, *keys: str) -> int:
        if not usage:
            return 0
        for key in keys:
            value = None
            if isinstance(usage, dict):
                value = usage.get(key)
            else:
                value = getattr(usage, key, None)
            try:
                parsed = int(value)
            except (TypeError, ValueError):
                parsed = 0
            if parsed > 0:
                return parsed
        return 0

    def _extract_llm_usage(self, resp: Any, prompt: str, completion: str) -> dict[str, Any]:
        candidates = [
            getattr(resp, "usage", None),
            getattr(resp, "token_usage", None),
            getattr(resp, "raw_usage", None),
        ]
        raw_response = getattr(resp, "raw_response", None)
        if isinstance(raw_response, dict):
            candidates.extend([
                raw_response.get("usage"),
                raw_response.get("token_usage"),
            ])
        usage = next((item for item in candidates if item), None)
        prompt_tokens = self._usage_value(usage, "prompt_tokens", "input_tokens", "prompt", "input")
        completion_tokens = self._usage_value(usage, "completion_tokens", "output_tokens", "completion", "output")
        total_tokens = self._usage_value(usage, "total_tokens", "total")
        estimated = False
        if total_tokens <= 0:
            if prompt_tokens <= 0:
                prompt_tokens = self._estimate_token_count(prompt)
            if completion_tokens <= 0:
                completion_tokens = self._estimate_token_count(completion)
            total_tokens = prompt_tokens + completion_tokens
            estimated = True
        elif prompt_tokens <= 0 and completion_tokens <= 0:
            prompt_tokens = self._estimate_token_count(prompt)
            completion_tokens = max(0, total_tokens - prompt_tokens)
        return {
            "prompt_tokens": max(0, prompt_tokens),
            "completion_tokens": max(0, completion_tokens),
            "total_tokens": max(0, total_tokens),
            "estimated": estimated or not usage,
        }

    @staticmethod
    def _classify_llm_prompt(prompt: str) -> str:
        text = str(prompt or "")[:1200]
        rules = (
            ("daily_plan", ("日程生成器", "生成今天的一日生活日程", "\"schedule\"")),
            ("detail", ("日程细化生成器", "today_events", "presence_status")),
            ("full_test_detail", ("完整测试", "缺少这些主动行为", "today_events")),
            ("dream", ("梦境生成器", "dream_type", "afterglow")),
            ("diary", ("日记生成器", "dream_fragments", "long_term_events")),
            ("memory_profile", ("私聊记忆整理", "长期画像", "user_traits")),
            ("dialogue_episode", ("私聊对话整理成片段", "共同经历", "open_loops")),
            ("response_review", ("改写成更像真实私聊", "需要修正的问题", "原回复")),
            ("relationship", ("关系站位", "relationship", "互动边界")),
            ("worldbook_registration", ("自我介绍原文", "人物画像插件", "初始印象")),
            ("group_interject", ("群聊主动插话", "插话", "群聊")),
            ("group_episode", ("群聊片段", "群聊阶段性", "topic_threads")),
            ("group_slang", ("黑话", "slang", "群内")),
            ("photo_prompt", ("ComfyUI", "社交媒体随手拍", "\"caption\"")),
            ("screen_narration", ("屏幕后留在脑子里的印象", "原始结果")),
            ("voice_repair", ("主动语音修正", "当前版本")),
            ("voice", ("主动语音", "TTS", "语音内容")),
            ("yesterday_summary", ("昨日/最近完整对话", "残留影响", "dream_reference")),
            ("creative_project", ("输出 JSON", "target_chars", "next_hint")),
            ("creative_writing", ("慢慢写小说", "本次字数上限", "只输出小说正文")),
            ("provider_test", ("请只回复两个字：正常",)),
        )
        for label, markers in rules:
            if all(marker in text for marker in markers):
                return label
        return "other"

    def _record_llm_usage(
        self,
        *,
        provider_id: str,
        task: str,
        prompt: str,
        completion: str,
        elapsed_ms: int,
        success: bool,
        error: str = "",
        resp: Any = None,
    ) -> None:
        usage = self._extract_llm_usage(resp, prompt, completion)
        now_ts = _now_ts()
        day = _today_key()
        hour = datetime.now().strftime("%Y-%m-%d %H:00")
        store = self.data.setdefault("token_usage", {})
        if not isinstance(store, dict):
            store = {}
            self.data["token_usage"] = store
        totals = store.setdefault("totals", {})
        if not isinstance(totals, dict):
            totals = {}
            store["totals"] = totals
        by_provider = store.setdefault("by_provider", {})
        by_task = store.setdefault("by_task", {})
        by_day = store.setdefault("by_day", {})
        by_hour = store.setdefault("by_hour", {})
        recent = store.setdefault("recent", [])
        if not isinstance(recent, list):
            recent = []
            store["recent"] = recent

        def bump(bucket: dict[str, Any]) -> None:
            bucket["calls"] = _safe_int(bucket.get("calls"), 0) + 1
            bucket["success"] = _safe_int(bucket.get("success"), 0) + (1 if success else 0)
            bucket["errors"] = _safe_int(bucket.get("errors"), 0) + (0 if success else 1)
            bucket["prompt_tokens"] = _safe_int(bucket.get("prompt_tokens"), 0) + usage["prompt_tokens"]
            bucket["completion_tokens"] = _safe_int(bucket.get("completion_tokens"), 0) + usage["completion_tokens"]
            bucket["total_tokens"] = _safe_int(bucket.get("total_tokens"), 0) + usage["total_tokens"]
            bucket["estimated_tokens"] = _safe_int(bucket.get("estimated_tokens"), 0) + (usage["total_tokens"] if usage["estimated"] else 0)
            bucket["elapsed_ms"] = _safe_int(bucket.get("elapsed_ms"), 0) + max(0, elapsed_ms)
            bucket["last_ts"] = now_ts

        provider_key = provider_id or "(default)"
        task_key = task or "other"
        for target in (
            totals,
            by_provider.setdefault(provider_key, {}),
            by_task.setdefault(task_key, {}),
            by_day.setdefault(day, {}),
            by_hour.setdefault(hour, {}),
        ):
            if isinstance(target, dict):
                bump(target)

        recent.append(
            {
                "ts": now_ts,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "provider": provider_key,
                "task": task_key,
                "success": success,
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "total_tokens": usage["total_tokens"],
                "estimated": usage["estimated"],
                "elapsed_ms": max(0, elapsed_ms),
                "prompt_chars": len(str(prompt or "")),
                "completion_chars": len(str(completion or "")),
                "error": _single_line(error, 160),
            }
        )
        del recent[:-240]
        store["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        last_save = _safe_float(getattr(self, "_token_usage_last_save_at", 0), 0)
        if now_ts - last_save >= 60:
            self._token_usage_last_save_at = now_ts
            try:
                self._save_data_sync()
            except Exception:
                pass

    async def _llm_call(
        self,
        prompt: str,
        max_tokens: int = 600,
        provider_id: str | None = None,
        task: str | None = None,
    ) -> str | None:
        start = time.time()
        selected_provider = str(provider_id or self.llm_provider_id or "").strip()
        task_key = _single_line(task, 40) or self._classify_llm_prompt(prompt)
        try:
            kwargs = {"prompt": prompt}
            if selected_provider:
                kwargs["chat_provider_id"] = selected_provider
            resp = await self.context.llm_generate(**kwargs)
            if resp and resp.completion_text:
                completion = resp.completion_text.strip()
                self._record_llm_usage(
                    provider_id=selected_provider,
                    task=task_key,
                    prompt=prompt,
                    completion=completion,
                    elapsed_ms=int((time.time() - start) * 1000),
                    success=True,
                    resp=resp,
                )
                return completion
            self._record_llm_usage(
                provider_id=selected_provider,
                task=task_key,
                prompt=prompt,
                completion="",
                elapsed_ms=int((time.time() - start) * 1000),
                success=False,
                error="empty_response",
                resp=resp if "resp" in locals() else None,
            )
        except Exception as e:
            self._record_llm_usage(
                provider_id=selected_provider,
                task=task_key,
                prompt=prompt,
                completion="",
                elapsed_ms=int((time.time() - start) * 1000),
                success=False,
                error=str(e),
            )
            logger.warning(f"[PrivateCompanion] LLM 调用失败: {e}")
        return None

    @staticmethod
    def _task_provider(*provider_ids: str | None) -> str:
        for provider_id in provider_ids:
            value = str(provider_id or "").strip()
            if value:
                return value
        return ""

    def _parse_plan_items(self, raw_text: str) -> list[dict[str, str]]:
        payload = self._extract_json_payload(raw_text)
        if payload is None:
            return []
        if isinstance(payload, dict):
            raw_items = payload.get("schedule") or payload.get("items") or []
        elif isinstance(payload, list):
            raw_items = payload
        else:
            raw_items = []

        items: list[dict[str, str]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_time = _single_line(item.get("time"), 8)
            if self._parse_hhmm_to_minutes(item_time) is None:
                continue
            activity = self._soften_destructive_daily_plan_text(_single_line(item.get("activity"), 120))
            if not activity:
                continue
            mood = self._soften_destructive_daily_plan_text(_single_line(item.get("mood"), 30))
            message_seed = self._soften_destructive_daily_plan_text(
                self._deemphasize_state_report_preamble(
                    _single_line(item.get("message_seed"), 140),
                    reason="background_schedule",
                )
            )
            items.append(
                {
                    "time": item_time,
                    "activity": activity,
                    "mood": mood,
                    "message_seed": message_seed,
                }
            )
        return sorted(items[: self.daily_plan_item_count], key=lambda item: self._parse_hhmm_to_minutes(item["time"]) or 0)

    @staticmethod
    def _soften_destructive_daily_plan_text(text: str) -> str:
        softened = _single_line(text, 160)
        if not softened:
            return ""
        replacements = [
            (r"想[^，。,；;]{0,18}(砸|摔|打人|揍人|报复|毁掉|弄坏)[^，。,；;]{0,18}", "烦得想先躲开一会儿"),
            (r"(把|将)[^，。,；;]{0,14}(砸|摔|扔)[^，。,；;]{0,14}(地上|墙上|门上|出去|烂|碎)[^，。,；;]{0,8}", "把手边的东西往里推了推"),
            (r"(砸|摔)(东西|门|墙|书|杯子|手机|笔)[^，。,；;]{0,8}", "把东西先放远一点"),
            (r"(骂人|想骂|吼人|想吼)[^，。,；;]{0,10}", "把话咽回去"),
        ]
        for pattern, replacement in replacements:
            softened = re.sub(pattern, replacement, softened)
        softened = re.sub(r"(烦躁|暴躁|恼火)到?有点?攻击性", "烦躁得有点想躲开", softened)
        softened = softened.replace("想砸东西的烦躁", "有点烦,但努力收着")
        softened = softened.replace("想摔东西的烦躁", "有点烦,但努力收着")
        return _single_line(softened, 160)

    def _extract_json_payload(self, raw_text: str) -> Any:
        text = raw_text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
        candidates = [text]
        object_start, object_end = text.find("{"), text.rfind("}")
        if object_start >= 0 and object_end > object_start:
            candidates.append(text[object_start : object_end + 1])
        array_start, array_end = text.find("["), text.rfind("]")
        if array_start >= 0 and array_end > array_start:
            candidates.append(text[array_start : array_end + 1])
        for candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
        return None

    def _get_current_plan_item(self, plan: dict[str, Any]) -> dict[str, str] | None:
        if not self._is_plan_date_active(plan.get("date")):
            return None
        items = plan.get("items")
        if not isinstance(items, list):
            return None
        current_minutes = self._effective_plan_now_minutes(str(plan.get("date") or ""))
        if current_minutes is None:
            return None
        selected = None
        for item in items:
            if not isinstance(item, dict):
                continue
            item_minutes = self._parse_hhmm_to_minutes(item.get("time"))
            if item_minutes is None:
                continue
            if item_minutes <= current_minutes:
                selected = item
            else:
                break
        return selected or (items[0] if items and isinstance(items[0], dict) else None)

    def _format_daily_plan(self, plan: dict[str, Any]) -> str:
        if not plan or not plan.get("items"):
            return "今天还没有日程。"
        source = "模型生成" if plan.get("source") == "llm" else "备用日程"
        lines = [
            f"{self.bot_name} 今天的日程（{plan.get('date', _today_key())},{source}）："
        ]
        state = self.data.get("daily_state", {})
        if isinstance(state, dict) and state.get("date") == plan.get("date"):
            lines.append(
                f"状态：能量 {state.get('energy', 70)}/100｜情绪偏{state.get('mood_bias', '平稳')}｜{state.get('sleep', '睡眠平稳')}"
            )
        for item in plan.get("items", []):
            if not isinstance(item, dict):
                continue
            mood = f"｜{item.get('mood')}" if item.get("mood") else ""
            lines.append(f"{item.get('time')} {item.get('activity')}{mood}")
        return "\n".join(lines)

    @staticmethod
    def _detail_event_text(item: dict[str, Any], limit: int = 160) -> str:
        if not isinstance(item, dict):
            return ""
        for key in (
            "event",
            "content",
            "detail",
            "description",
            "text",
            "narrative",
            "body",
            "细化",
            "细化内容",
            "细化叙述",
            "事件",
            "主要事件",
        ):
            text = _single_line(item.get(key), limit)
            if text:
                return text
        return ""

    def _format_current_detail_view(self) -> str:
        plan = self.data.get("daily_plan", {})
        if not isinstance(plan, dict) or not plan.get("items"):
            return "今天还没有日程，所以也没有可看的当前细化。"
        enhanced = self.data.get("detail_enhanced_segments", {})
        if not isinstance(enhanced, dict):
            enhanced = {}
        segment = self._current_detail_segment_for_update() or self._pick_detail_segment(plan, enhanced)
        if not segment:
            return "当前还没有可用的细化结果。先让今天的日程段完成细化，或者手动执行一次“陪伴 重置细化”。"
        key = str(segment.get("key") or "")
        snapshot = enhanced.get(key) if key else None
        if not isinstance(snapshot, dict):
            return "当前时间段还没有落地的细化内容。可以先执行一次“陪伴 重置细化”。"

        item = segment.get("item") if isinstance(segment, dict) else {}
        start_text = self._minutes_to_hhmm(_safe_int(segment.get("start"), 0))
        end_text = self._minutes_to_hhmm(_safe_int(segment.get("end"), 0))
        lines = [
            f"当前细化时段：{start_text}-{end_text}",
            f"对应日程：{_single_line((item or {}).get('activity'), 120)}",
        ]
        mood = _single_line((item or {}).get("mood"), 24)
        if mood:
            lines.append(f"日程情绪：{mood}")

        state_variables = snapshot.get("state_variables", [])
        if isinstance(state_variables, list) and state_variables:
            lines.append("状态变量：")
            for variable in state_variables[:8]:
                if not isinstance(variable, dict):
                    continue
                name = _single_line(variable.get("name"), 32)
                value = _single_line(variable.get("value"), 60)
                note = _single_line(variable.get("note"), 80)
                if name and value:
                    lines.append(f"- {name}: {value}" + (f"（{note}）" if note else ""))

        presence = snapshot.get("presence_status")
        if isinstance(presence, dict):
            mode = _single_line(presence.get("mode"), 24)
            reason = _single_line(presence.get("reason"), 80)
            if mode and mode != "unchanged":
                lines.append("QQ状态表现：")
                lines.append(f"- {mode}" + (f"｜{reason}" if reason else ""))

        interaction_updates = snapshot.get("interaction_updates", [])
        if isinstance(interaction_updates, list) and interaction_updates:
            lines.append("用户介入后的局部更新：")
            for update in interaction_updates[-4:]:
                if not isinstance(update, dict):
                    continue
                at = _single_line(update.get("at"), 8)
                user_text = _single_line(update.get("user_text"), 80)
                intensity = _single_line(update.get("intensity"), 12)
                reaction = _single_line(update.get("reaction"), 120)
                state_updates = update.get("state_updates")
                state_text = ""
                if isinstance(state_updates, list) and state_updates:
                    state_text = "；".join(_single_line(item, 60) for item in state_updates if _single_line(item, 60))
                if reaction or user_text:
                    prefix = f"- {at} " if at else "- "
                    parts = [
                        f"用户：{user_text}" if user_text else "",
                        f"强度：{intensity}" if intensity else "",
                        reaction,
                        state_text,
                    ]
                    lines.append(prefix + "｜".join(part for part in parts if part))

        today_events = snapshot.get("today_events", [])
        scoped_today_events = self._filter_snapshot_items_to_segment(today_events, segment)
        if scoped_today_events:
            lines.append("细化内容：")
            for detail_event in scoped_today_events[:8]:
                if not isinstance(detail_event, dict):
                    continue
                window = _single_line(detail_event.get("window"), 24)
                event_text = self._detail_event_text(detail_event, 160)
                mood_text = _single_line(detail_event.get("mood"), 24)
                if event_text:
                    tail = f"｜{mood_text}" if mood_text else ""
                    lines.append(f"- {window}｜{event_text}{tail}")
        else:
            summary = _single_line(snapshot.get("summary"), 160)
            if summary and summary not in {"这一段按原日程慢慢推进。", "这一段按原日程慢慢推进"}:
                lines.append(f"细化内容：{summary}")
            else:
                lines.append("细化内容：当前没有生成出可展示的细化正文。")

        proactive_events = snapshot.get("proactive_events", [])
        if isinstance(proactive_events, list) and proactive_events:
            scoped_proactive_events = self._filter_snapshot_items_to_segment(proactive_events, segment)
            if scoped_proactive_events:
                lines.append("这一段的主动契机：")
            for proactive_event in scoped_proactive_events[:10]:
                if not isinstance(proactive_event, dict):
                    continue
                window = _single_line(proactive_event.get("window"), 24)
                reason = _single_line(proactive_event.get("reason"), 24)
                action = _single_line(proactive_event.get("action"), 24) or "message"
                topic = _single_line(proactive_event.get("topic"), 48)
                motive = _single_line(proactive_event.get("motive"), 80)
                why = _single_line(proactive_event.get("why"), 100)
                scene = _single_line(proactive_event.get("scene"), 60)
                tone = _single_line(proactive_event.get("tone"), 24)
                impulse = _single_line(proactive_event.get("impulse"), 80)
                lines.append(f"- {window}｜{reason}｜{action}｜{topic or motive or '（无话题）'}")
                if why:
                    lines.append(f"  why：{why}")
                if motive:
                    lines.append(f"  motive：{motive}")
                meta_bits = []
                if scene:
                    meta_bits.append(f"scene={scene}")
                if tone:
                    meta_bits.append(f"tone={tone}")
                if impulse:
                    meta_bits.append(f"impulse={impulse}")
                if meta_bits:
                    lines.append("  " + "｜".join(meta_bits))
                chain = proactive_event.get("chain")
                if isinstance(chain, list) and chain:
                    lines.append("  chain：")
                    for step in chain[:4]:
                        if not isinstance(step, dict):
                            continue
                        kind = _single_line(step.get("kind"), 24)
                        after_minutes = _safe_int(step.get("after_minutes"), 0, 0)
                        step_reason = _single_line(step.get("reason"), 24)
                        step_topic = _single_line(step.get("topic"), 48)
                        step_motive = _single_line(step.get("motive"), 80)
                        step_tone = _single_line(step.get("tone"), 24)
                        extra = []
                        if after_minutes > 0:
                            extra.append(f"{after_minutes} 分钟后")
                        if step_reason:
                            extra.append(step_reason)
                        if step_topic:
                            extra.append(step_topic)
                        if step_tone:
                            extra.append(f"tone={step_tone}")
                        if step_motive:
                            extra.append(f"motive={step_motive}")
                        lines.append(f"    - {kind}" + (f"｜{'｜'.join(extra)}" if extra else ""))

        if len(lines) <= 4:
            lines.append("这段目前还比较空，说明细化结果里还没长出太多东西。")
        return "\n".join(lines)

    def _filter_snapshot_items_to_segment(
        self,
        raw_items: Any,
        segment: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_items, list) or not isinstance(segment, dict):
            return []
        start = _safe_int(segment.get("start"), 0)
        end = _safe_int(segment.get("end"), self._segment_end_minutes(start, segment.get("item")))
        if end <= start:
            end += 24 * 60
        kept: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            item_start, item_end = self._parse_window_minutes(str(item.get("window") or ""))
            if item_start is None or item_end is None:
                continue
            candidates = [(item_start, item_end)]
            if item_end < item_start:
                candidates = [(item_start, item_end + 24 * 60)]
            if item_start < start and end > 24 * 60:
                candidates.append((item_start + 24 * 60, item_end + 24 * 60))
            if any(candidate_start >= start and candidate_end <= end for candidate_start, candidate_end in candidates):
                kept.append(item)
        return kept

    def _format_current_detail_brief(self) -> str:
        plan = self.data.get("daily_plan", {})
        if not isinstance(plan, dict) or not plan.get("items"):
            return "今天还没有日程，所以没有可细化的时间段。"
        enhanced = self.data.get("detail_enhanced_segments", {})
        if not isinstance(enhanced, dict):
            enhanced = {}
        segment = self._current_detail_segment_for_update() or self._pick_detail_segment(plan, enhanced)
        if not segment:
            return "当前还没有可用的细化结果。"
        key = str(segment.get("key") or "")
        snapshot = enhanced.get(key) if key else None
        if not isinstance(snapshot, dict):
            return "当前时间段还没有落地的细化内容。"

        item = segment.get("item") if isinstance(segment, dict) else {}
        start_text = self._minutes_to_hhmm(_safe_int(segment.get("start"), 0))
        end_text = self._minutes_to_hhmm(_safe_int(segment.get("end"), 0))
        lines = [
            f"{start_text}-{end_text}｜{_single_line((item or {}).get('activity'), 80)}",
        ]
        summary = _single_line(snapshot.get("summary"), 140)
        if summary:
            lines.append(summary)

        today_events = snapshot.get("today_events", [])
        if isinstance(today_events, list) and today_events:
            for detail_event in today_events[:3]:
                if not isinstance(detail_event, dict):
                    continue
                window = _single_line(detail_event.get("window"), 18)
                event_text = self._detail_event_text(detail_event, 120)
                mood_text = _single_line(detail_event.get("mood"), 20)
                if event_text:
                    lines.append(f"- {window} {event_text}" + (f"｜{mood_text}" if mood_text else ""))

        interaction_updates = snapshot.get("interaction_updates", [])
        if isinstance(interaction_updates, list) and interaction_updates:
            latest = next((item for item in reversed(interaction_updates) if isinstance(item, dict)), None)
            if isinstance(latest, dict):
                user_text = _single_line(latest.get("user_text"), 60)
                reaction = _single_line(latest.get("reaction"), 100)
                if reaction or user_text:
                    lines.append("局部更新：" + "｜".join(part for part in (f"用户：{user_text}" if user_text else "", reaction) if part))

        return "\n".join(lines)

    async def _tick(self):
        await self._maybe_trigger_bilibili_boredom_watch()
        async with self._data_lock:
            if self._maybe_schedule_bilibili_video_share():
                self._save_data_sync()
            users = list(self.data.get("users", {}).items())

        for user_id, user in users:
            if isinstance(user, dict):
                user["user_id"] = str(user.get("user_id") or user_id)
            now = _now_ts()
            due_timer = self._get_active_llm_timer(user)
            due_timer_id = (
                str(due_timer.get("id") or "")
                if isinstance(due_timer, dict) and now >= _safe_float(due_timer.get("scheduled_ts"), 0)
                else ""
            )
            should_send, reason = self._should_send(user)
            if not should_send:
                logger.debug(f"[PrivateCompanion] 跳过 {user_id}: {reason}")
                continue

            async with self._data_lock:
                current_for_mark = self._get_user(user_id)
                self._recover_stale_proactive_sending(current_for_mark)
                if current_for_mark.get("proactive_sending"):
                    logger.debug(f"[PrivateCompanion] 跳过 {user_id}: 主动发送仍在进行中")
                    continue
                current_for_mark["proactive_sending"] = True
                current_for_mark["proactive_sending_started_at"] = _now_ts()
                self._save_data_sync()

            planned_action_for_send = str(user.get("planned_proactive_action") or "message")
            planned_motive_for_send = _single_line(user.get("planned_proactive_motive"), 140)
            planned_chain_for_send = (
                list(user.get("planned_event_chain") or [])
                if isinstance(user.get("planned_event_chain"), list)
                else []
            )
            planned_opener_mode_for_send = str(user.get("planned_opener_mode") or "")
            planned_followup_kind_for_send = str(user.get("planned_followup_kind") or "")
            task_start_last_seen = _safe_float(user.get("last_seen"), 0)
            task_start_inbound_count = _safe_int(user.get("inbound_count"), 0)
            reason, text, image_path, extra_components, action_summary, effective_action_for_send = await self._render_message(user)
            async with self._data_lock:
                current_after_render = self._get_user(user_id)
                has_new_user_message = (
                    _safe_float(current_after_render.get("last_seen"), 0) > task_start_last_seen
                    or _safe_int(current_after_render.get("inbound_count"), 0) > task_start_inbound_count
                )
            if has_new_user_message:
                logger.info(
                    "[PrivateCompanion] 用户在主动消息生成期间已有新消息,丢弃本次主动发送: %s",
                    user_id,
                )
                async with self._data_lock:
                    current_for_clear = self._get_user(user_id)
                    current_for_clear["proactive_sending"] = False
                    current_for_clear["proactive_sending_started_at"] = 0
                    self._save_data_sync()
                continue
            if not text and not image_path and not extra_components:
                async with self._data_lock:
                    current = self._get_user(user_id)
                    current["proactive_sending"] = False
                    current["proactive_sending_started_at"] = 0
                    if self._simulation_active(current):
                        self._consume_simulation_event(current)
                    else:
                        current["next_proactive_at"] = 0
                        current["planned_proactive_reason"] = ""
                        current["planned_proactive_action"] = ""
                        current["planned_proactive_source"] = ""
                        current["planned_proactive_motive"] = ""
                        current["planned_proactive_topic"] = ""
                        current["planned_opener_mode"] = ""
                        current["planned_followup_kind"] = ""
                        current["planned_proactive_quota_exempt"] = False
                        self._schedule_next_proactive(current, now=_now_ts(), delay_hours=(2, 8))
                    self._save_data_sync()
                logger.debug(f"[PrivateCompanion] 放弃 {user_id}: 主动行为失败或不适合发送")
                continue
            try:
                logger.info(
                    "[PrivateCompanion] 准备主动发送给 %s: reason=%s action=%s text=%s image=%s extra=%s",
                    user_id,
                    reason,
                    effective_action_for_send or planned_action_for_send or "message",
                    _single_line(text, 120),
                    bool(image_path),
                    len(extra_components),
                )
                await self._send_proactive_message_chain(
                    user["umo"],
                    text,
                    image_path,
                    extra_components=extra_components,
                )
                logger.info(
                    "[PrivateCompanion] 主动发送完成: user=%s reason=%s action=%s",
                    user_id,
                    reason,
                    planned_action_for_send or "message",
                )
                await self._archive_proactive_message_to_conversation(
                    user=user,
                    user_prompt=self._build_proactive_archive_user_prompt(
                        reason=reason,
                        action=effective_action_for_send or planned_action_for_send or "message",
                        motive=planned_motive_for_send,
                        action_summary=action_summary,
                    ),
                    assistant_response=self._build_proactive_archive_assistant_text(
                        text=text,
                        image_path=image_path,
                        extra_components=extra_components,
                        action_summary=action_summary,
                    ),
                )
            except Exception as e:
                logger.warning(f"[PrivateCompanion] 发送给 {user_id} 失败: {e}")
                async with self._data_lock:
                    current_after_failure = self._get_user(user_id)
                    current_after_failure["next_proactive_at"] = 0
                    current_after_failure["planned_proactive_reason"] = ""
                    current_after_failure["planned_proactive_action"] = ""
                    current_after_failure["planned_proactive_source"] = ""
                    current_after_failure["planned_proactive_motive"] = ""
                    current_after_failure["planned_proactive_topic"] = ""
                    current_after_failure["planned_event_chain"] = []
                    current_after_failure["planned_opener_mode"] = ""
                    current_after_failure["planned_followup_kind"] = ""
                    current_after_failure["planned_proactive_quota_exempt"] = False
                    self._schedule_next_proactive(current_after_failure, now=_now_ts(), delay_hours=(6, 12))
                    self._save_data_sync()
                continue
            finally:
                async with self._data_lock:
                    current_for_clear = self._get_user(user_id)
                    current_for_clear["proactive_sending"] = False
                    current_for_clear["proactive_sending_started_at"] = 0
                    self._save_data_sync()

            async with self._data_lock:
                current = self._get_user(user_id)
                simulation_active = self._simulation_active(current)
                self._reset_daily_counter_if_needed(current)
                current["last_sent"] = _now_ts()
                current["last_companion_message"] = _single_line(_strip_internal_message_blocks(text), 500)
                current["last_proactive_reason"] = reason
                current["last_proactive_action"] = effective_action_for_send or planned_action_for_send or "message"
                current["last_proactive_behavior_summary"] = action_summary
                current["last_proactive_motive"] = planned_motive_for_send
                self._remember_proactive_topic(
                    current,
                    text=text,
                    topic=current.get("planned_proactive_topic"),
                    motive=planned_motive_for_send,
                )
                self._mark_planned_candidate_status(current, "sent", "已发送")
                self._note_proactive_daypart_sent(current, current["last_sent"])
                opener_mode = planned_opener_mode_for_send
                followup_kind = planned_followup_kind_for_send
                if opener_mode == "name_only":
                    current["suspended_proactive"] = self._build_suspended_proactive_payload(
                        opener_text=text,
                        reason=reason,
                        action=current["last_proactive_action"],
                        motive=current["last_proactive_motive"],
                        action_summary=action_summary,
                        chain=planned_chain_for_send,
                    )
                elif followup_kind == "suspended_opener":
                    suspended = current.get("suspended_proactive")
                    if isinstance(suspended, dict) and suspended.get("active"):
                        suspended["complaint_sent"] = True
                        second = suspended.get("second_followup")
                        if isinstance(second, dict) and second:
                            after_minutes = _safe_int(second.get("after_minutes"), 45, 0, 240)
                            second_reason = _single_line(second.get("reason"), 40) or "morning_greeting"
                            if second_reason == "morning_greeting":
                                after_minutes = max(after_minutes, 90)
                            current["pending_followup_event"] = {
                                "date": _today_key(),
                                "window": self._window_from_delay_minutes(after_minutes, width_minutes=18),
                                "reason": second_reason,
                                "action": "message",
                                "why": "前一条早晨试探后隔了挺久,如果还想续,也只轻轻补一句。",
                                "topic": _single_line(second.get("topic"), 80) or "早晨那句后面",
                                "motive": self._normalize_internal_motive_text(_single_line(second.get("motive"), 100)),
                                "scene": "早晨那句试探之后又过了一阵",
                                "tone": _single_line(second.get("tone"), 30) or "轻一点,不催促",
                                "impulse": "隔了挺久才又想放一句,不要求对方立刻回",
                                "_scheduled_ts": _now_ts() + after_minutes * 60,
                                "_cancel_on_inbound": True,
                            }
                elif followup_kind == "chain_followup":
                    next_chain_followup = self._build_followup_event_from_chain(
                        planned_chain_for_send,
                        origin_reason=reason,
                        origin_action=current["last_proactive_action"],
                        now_ts=_now_ts(),
                    )
                    if isinstance(next_chain_followup, dict):
                        current["pending_followup_event"] = next_chain_followup
                elif planned_chain_for_send and not current.get("pending_followup_event"):
                    next_chain_followup = self._build_followup_event_from_chain(
                        planned_chain_for_send,
                        origin_reason=reason,
                        origin_action=current["last_proactive_action"],
                        now_ts=_now_ts(),
                    )
                    if isinstance(next_chain_followup, dict):
                        current["pending_followup_event"] = next_chain_followup
                if reason == "group_share":
                    current["group_share_context"] = {}
                if reason == "bili_video_share":
                    current["bilibili_video_context"] = {}
                if reason == "creative_share":
                    current["creative_share_context"] = {}
                if simulation_active:
                    self._consume_simulation_event(current)
                else:
                    current["sent_today"] = _safe_int(current.get("sent_today"), 0) + 1
                    current["proactive_sent_count"] = _safe_int(current.get("proactive_sent_count"), 0) + 1
                    current["ignored_streak"] = _safe_int(current.get("ignored_streak"), 0) + 1
                    current["awaiting_reply_since"] = _now_ts()
                    self._note_action_sent(current, current["last_proactive_action"])
                    existing_followup = current.get("pending_followup_event")
                    if isinstance(existing_followup, dict) and existing_followup:
                        current["pending_followup_event"] = existing_followup
                    elif followup_kind in {"suspended_opener", "chain_followup"} or opener_mode == "name_only":
                        current["pending_followup_event"] = {}
                    else:
                        current["pending_followup_event"] = self._maybe_make_unanswered_screen_peek_event(
                            current,
                            reason,
                            current["last_proactive_action"],
                        ) or self._maybe_make_followup_event(
                            current,
                            reason,
                            current["last_proactive_action"],
                        ) or {}
                    if self._is_greeting_reason(reason):
                        self._reset_daily_counter_if_needed(current)
                        sent_greetings = current.setdefault("greetings_sent", [])
                        if not isinstance(sent_greetings, list):
                            sent_greetings = []
                            current["greetings_sent"] = sent_greetings
                        if reason not in sent_greetings:
                            sent_greetings.append(reason)
                    self._clear_llm_timer_event(current, event_id=due_timer_id)
                    next_timer = self._get_active_llm_timer(current)
                    if isinstance(next_timer, dict) and _safe_float(next_timer.get("scheduled_ts"), 0) > _now_ts():
                        current["next_proactive_at"] = _safe_float(next_timer.get("scheduled_ts"), 0)
                        current["planned_proactive_reason"] = str(next_timer.get("reason") or "check_in")
                        current["planned_proactive_action"] = str(next_timer.get("action") or "message")
                        current["planned_proactive_source"] = "timer"
                        current["planned_proactive_motive"] = _single_line(next_timer.get("motive"), 140)
                        current["planned_proactive_topic"] = _single_line(next_timer.get("topic"), 60)
                        current["planned_event_chain"] = list(next_timer.get("chain") or []) if isinstance(next_timer.get("chain"), list) else []
                        current["planned_opener_mode"] = ""
                        current["planned_followup_kind"] = ""
                        current["planned_proactive_quota_exempt"] = False
                    else:
                        current["next_proactive_at"] = 0
                        current["planned_proactive_reason"] = ""
                        current["planned_proactive_action"] = ""
                        current["planned_proactive_source"] = ""
                        current["planned_proactive_motive"] = ""
                        current["planned_proactive_topic"] = ""
                        current["planned_event_chain"] = []
                        current["planned_opener_mode"] = ""
                        current["planned_followup_kind"] = ""
                        current["planned_proactive_quota_exempt"] = False
                        self._schedule_next_proactive(current, now=_now_ts())
                self._save_data_sync()
                current_snapshot = dict(current)
            asyncio.create_task(self._refresh_persona_relationship(user_id, current_snapshot))

    def _help_text(self) -> str:
        return (
            "我会永远陪着你 命令：\n"
            "陪伴 状态\n"
            "陪伴 查看主动判定\n"
            "陪伴 重置插件\n"
            "陪伴 增添状态 <状态描述>[|持续小时]\n"
            "陪伴 查看今日日程\n"
            "陪伴 重置日程\n"
            "陪伴 当前细化\n"
            "陪伴 重置细化\n"
            "陪伴 能力列表\n"
            "陪伴 查看提示词 日程|细化|主动|回复注入\n"
            "陪伴 完整测试\n"
            "陪伴 结束完整测试\n"
            "陪伴模拟唤醒 <想模拟的用户消息>\n"
            "陪伴 生成状态\n"
            "陪伴 梦境\n"
            "陪伴 梦境碎片\n"
            "陪伴 画像\n"
            "陪伴 记忆\n"
            "陪伴 表达学习\n"
            "陪伴 气氛\n"
            "陪伴 片段\n"
            "陪伴 长期记忆\n"
            "陪伴 日记\n"
            "陪伴 生成日记\n"
            "陪伴 日期列表\n"
            "陪伴 日期添加 <标题> <YYYY-MM-DD或MM-DD> [备注]\n"
            "陪伴 日期删除 <标题关键词>\n"
            "陪伴 可做事项\n"
            "陪伴 昵称 <称呼>\n"
            "陪伴 语气 温柔|活泼|工作\n"
            "陪伴 清空记忆\n"
            "提示：私聊陪伴默认开启；配置页 target_user_ids 里的 QQ 会自动预热主动消息。"
        )

    def _private_only_text(self) -> str:
        return "为了避免误打扰,陪伴功能需要在私聊里管理。"

    async def _reply(self, event: AstrMessageEvent, text: str):
        await event.send(event.plain_result(text))

    async def _reply_with_optional_media(
        self,
        event: AstrMessageEvent,
        text: str,
        image_path: str = "",
        extra_components: list[Any] | None = None,
    ):
        if (image_path and os.path.exists(image_path)) or extra_components:
            await event.send(
                event.chain_result(
                    self._build_outbound_chain(text, image_path, extra_components=extra_components)
                )
            )
            return
        await self._reply(event, text)

    @filter.on_llm_request()
    async def inject_humanized_state(self, event: AstrMessageEvent, req: ProviderRequest):
        if not self.enabled or not self.inject_passive_states:
            return
        if not hasattr(req, "system_prompt"):
            return

        is_private_chat = bool(getattr(event, "is_private_chat", lambda: False)())
        if not is_private_chat:
            if self.enable_group_context_injection and self.enable_group_companion:
                group_id = self._extract_group_id_from_event(event)
                if group_id and self._group_enabled_for_event(group_id):
                    group = self._get_group(group_id)
                    sender_id = ""
                    try:
                        sender_id = str(event.get_sender_id())
                    except Exception:
                        sender_id = ""
                    marker = "<!-- private_companion_group_context_v1 -->"
                    current_prompt = req.system_prompt or ""
                    if marker not in current_prompt:
                        req.system_prompt = (
                            f"{current_prompt}\n\n{marker}\n{self._format_group_context_for_prompt(group, sender_id, str(event.message_str or ''))}"
                        ).strip()
            return
        try:
            user_id = str(event.get_sender_id())
        except Exception:
            return
        raw_users = self.data.get("users", {})
        current_user = raw_users.get(user_id) if isinstance(raw_users, dict) else None
        if not isinstance(current_user, dict):
            return

        state = await self._ensure_daily_state()
        injection_parts = [self._format_state_injection(state)]
        inbound_text = _single_line(getattr(event, "message_str", "") or current_user.get("last_user_message"), 260)
        hidden_creative_context = self._format_hidden_creative_context_for_reply(inbound_text)
        if hidden_creative_context:
            injection_parts.append(hidden_creative_context)
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
            return
        req.system_prompt = f"{current_prompt}\n\n{marker}\n{injection}".strip()
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
            "[PrivateCompanion] 已注入被动状态提示词到 %s: 状态=%s；当前日程=%s",
            _single_line(getattr(event, "unified_msg_origin", ""), 80) or "unknown_session",
            "｜".join(state_log_parts),
            current_schedule,
        )

    @filter.on_llm_response()
    async def capture_llm_timer_directive(self, event: AstrMessageEvent, resp: LLMResponse):
        if not self.enabled:
            return
        if not bool(getattr(event, "is_private_chat", lambda: False)()):
            return
        original_text = str(resp.completion_text or "").strip()
        if not original_text:
            return
        try:
            user_id = str(event.get_sender_id())
        except Exception:
            return
        raw_users = self.data.get("users", {})
        current_user = raw_users.get(user_id) if isinstance(raw_users, dict) else None
        if not isinstance(current_user, dict):
            return
        working_text = original_text
        if self.enable_llm_timer_scheduling and "<timer" in original_text.lower():
            cleaned_text, payloads = self._extract_timer_directives(original_text)
            if payloads:
                working_text = cleaned_text or original_text
                resp.completion_text = working_text
                await self._schedule_llm_timer(
                    user_id,
                    payloads[-1],
                    source_text=working_text,
                    source_origin="llm_response",
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
                stats["last_rewritten_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                self._save_data_sync()

        async with self._data_lock:
            current = self._get_user(user_id)
            current["last_companion_message"] = _single_line(_strip_internal_message_blocks(working_text), 500)
            self._remember_passive_reply_topic(current, working_text, inbound_text)
            self._save_data_sync()

    async def _format_proactive_reply_context(self, event: AstrMessageEvent) -> str:
        try:
            if not bool(getattr(event, "is_private_chat", lambda: False)()):
                return ""
            user_id = str(event.get_sender_id())
        except Exception:
            return ""

        consume_suspended = False
        async with self._data_lock:
            user = dict(self._get_user(user_id))
            raw_suspended = user.get("suspended_proactive")
            if isinstance(raw_suspended, dict) and raw_suspended.get("active") and raw_suspended.get("resume_ready"):
                consume_suspended = True
                current = self._get_user(user_id)
                current["suspended_proactive"] = {}
                self._save_data_sync()

        suspended = user.get("suspended_proactive")
        if isinstance(suspended, dict) and suspended.get("active") and (
            suspended.get("resume_ready") or consume_suspended
        ):
            opener = _single_line(suspended.get("opener_text"), 60) or f"{self.default_nickname}……"
            hidden_reason = _single_line(suspended.get("reason"), 40)
            hidden_action = _single_line(suspended.get("action"), 32)
            hidden_motive = _single_line(suspended.get("motive"), 120)
            hidden_summary = _single_line(suspended.get("summary"), 60)
            schedule_context = self._format_schedule_context_for_prompt()
            return (
                "【刚才悬着的话头】\n"
                f"你刚才主动私聊时,只先发了一句：{opener}\n"
                "你真正想说的后半句还没发出去,现在用户回头了。\n"
                f"当时主动原因：{hidden_reason or 'check_in'}\n"
                f"当时原本想用的主动行为：{hidden_action or 'message'}"
                + (f"（{hidden_summary}）\n" if hidden_summary else "\n")
                + (f"当时心里那点念头：{hidden_motive}\n" if hidden_motive else "")
                + "请像终于等到对方抬头一样,自然把后半句接上。不要解释“我刚才故意只叫你一声”,也不要突然像全新开场。\n"
                + "如果用户现在只是“怎么了”“？”“在吗”这类短句,就把它理解成他终于回头了,顺着那一下接话。\n"
                + "可以参考当前状态和今天的生活背景,但只体现在语气和接话方式里；别把日期、状态或日程当汇报念出来。\n"
                + f"当前/附近日程参考：{schedule_context or '无当前日程'}\n"
                + f"今天预设的生活线索：{self._format_story_plan_for_prompt()}"
            )

        last_sent = _safe_float(user.get("last_sent"), 0)
        last_message = _single_line(user.get("last_companion_message"), 240)
        if not last_sent or not last_message:
            return ""
        if _now_ts() - last_sent > self.proactive_reply_context_hours * 3600:
            return ""

        return self._build_proactive_reply_core(user)

    def _build_proactive_reply_core(self, user: dict[str, Any]) -> str:
        last_sent = _safe_float(user.get("last_sent"), 0)
        last_message = _single_line(user.get("last_companion_message"), 240)
        if not last_sent or not last_message:
            return ""
        sent_at = datetime.fromtimestamp(last_sent).strftime("%H:%M")
        reason = _single_line(user.get("last_proactive_reason"), 40)
        action = _single_line(user.get("last_proactive_action"), 40)
        behavior = _single_line(user.get("last_proactive_behavior_summary"), 80)
        motive = _single_line(user.get("last_proactive_motive"), 120)
        detail_parts = []
        if reason:
            detail_parts.append(f"原因：{reason}")
        if action and action != "message":
            detail_parts.append(f"行为：{action}" + (f"（{behavior}）" if behavior else ""))
        elif behavior:
            detail_parts.append(f"行为：{behavior}")
        if motive:
            detail_parts.append(f"当时想法：{motive}")
        detail = "\n" + "；".join(detail_parts) if detail_parts else ""
        return (
            "【主动消息回复上下文】\n"
            f"你在 {sent_at} 主动向用户发送了“{last_message}”。{detail}\n"
            "用户当前消息可能是在回应这条主动消息；请优先自然承接用户这句话。如果用户明显另起话题,再自然切换。\n"
            "上一条主动消息已经发出过,现在绝对不要完整复述,也不要同义改写其中的事实、情绪和问题。"
            "尤其不要把刚才问过的问题再问一遍；如果用户已经回答了,先接住回答。\n"
            "如果用户问“做啥了/怎么了/发生啥了”,优先补充刚才没说过的具体动作或原因；如果没新信息,就短短承认一下。"
        )

    def _build_proactive_reply_context_for_user(self, user: dict[str, Any]) -> str:
        last_sent = _safe_float(user.get("last_sent"), 0)
        last_message = _single_line(user.get("last_companion_message"), 240)
        if not last_sent or not last_message:
            return "（暂无最近一次主动消息承接上下文）"
        if _now_ts() - last_sent > self.proactive_reply_context_hours * 3600:
            return "（最近一次主动消息已超出承接窗口）"
        return self._build_proactive_reply_core(user)

    async def _debug_prompt_text(self, kind: str, user: dict[str, Any]) -> str:
        normalized = str(kind or "").strip().lower()
        await self._ensure_weather_context()
        if normalized in {"日程", "plan", "daily_plan"}:
            return self._build_daily_plan_prompt(datetime.now().strftime("%Y-%m-%d %H:%M"))
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
                start = self._parse_hhmm_to_minutes(current_item.get("time")) or (datetime.now().hour * 60 + datetime.now().minute)
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
            state = await self._ensure_daily_state()
            parts = [self._format_state_injection(state)]
            detail_injection = self._format_detail_injection()
            if detail_injection:
                parts.append(detail_injection)
            return "\n\n".join(parts)
        return "可查看的提示词类型：日程 / 细化 / 主动 / 回复注入"

    def _clone_conversation_for_simulated_wakeup(
        self,
        conversation: Conversation,
        current_command_text: str,
    ) -> Conversation:
        history: list[dict[str, Any]] = []
        try:
            loaded = json.loads(conversation.history or "[]")
            if isinstance(loaded, list):
                history = [item for item in loaded if isinstance(item, dict)]
        except Exception:
            history = []

        trimmed_command = str(current_command_text or "").strip()
        while history:
            last = history[-1]
            if str(last.get("role", "")).strip().lower() != "user":
                break
            content = last.get("content")
            if not isinstance(content, str) or content.strip() != trimmed_command:
                break
            history.pop()

        return Conversation(
            platform_id=conversation.platform_id,
            user_id=conversation.user_id,
            cid=conversation.cid,
            history=json.dumps(history, ensure_ascii=False),
            title=conversation.title,
            persona_id=conversation.persona_id,
            created_at=conversation.created_at,
            updated_at=conversation.updated_at,
            token_usage=conversation.token_usage,
        )

    @filter.command("陪伴", alias={"私聊陪伴", "主动陪伴"})
    async def companion_command(self, event: AstrMessageEvent):
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
            "完整测试", "真实测试", "完整真实测试",
            "生成日记", "刷新日记",
            "梦境", "做了什么梦", "今日梦境",
        }

        is_private = bool(getattr(event, "is_private_chat", lambda: False)())
        if self.require_private_opt_in and not is_private:
            await self._reply(event, self._private_only_text())
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
                        f"今日主动消息：{user.get('sent_today', 0)}/{self.max_daily_messages}\n",
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
            elif action in {"查看主动判定", "主动判定", "判定"}:
                response = self._explain_proactive_decision(user)
            elif action in {"能力列表", "主动能力", "工具列表"}:
                response = self._format_proactive_ability_list_for_user(user)
            elif action in {"完整测试", "真实测试", "完整真实测试"}:
                response = "正在准备一轮完整真实测试：我会先补齐今天状态和日程，再只抽一个日程段做细化，然后把这一段压成每两分钟一条的真实主动链。"
            elif action in {"戳一戳事件", "戳事件", "poke事件"}:
                response = "戳一戳不再作为单独事件测试了。现在它会在合适的主动消息发送前，随机轻轻戳 0 到 3 下。"
            elif action in {"结束完整测试", "停止完整测试", "取消完整测试"}:
                if self._simulation_active(user):
                    self._finish_simulation_mode(user)
                    self._save_data_sync()
                    response = "已结束当前完整测试。"
                else:
                    response = "当前没有正在进行的完整测试。"
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
        if action in {"完整测试", "真实测试", "完整真实测试"}:
            state = await self._ensure_daily_state(force=False)
            plan = await self._ensure_daily_plan(force=False)
            if not plan:
                plan = await self._ensure_daily_plan(force=True)
            await self._ensure_weather_context()
            enhanced = self.data.get("detail_enhanced_segments", {})
            if not isinstance(enhanced, dict):
                enhanced = {}
            segment = self._pick_detail_segment(plan or {}, enhanced)
            if not segment:
                current_item = self._get_current_plan_item(plan or {})
                if isinstance(current_item, dict):
                    start = self._parse_hhmm_to_minutes(current_item.get("time")) or (datetime.now().hour * 60 + datetime.now().minute)
                    segment = {
                        "start": start,
                        "end": min(24 * 60, start + 120),
                        "item": current_item,
                    }
            if not segment:
                await self._reply(event, "没找到可用的日程段。先生成一份今天的日程，再试这条完整测试会更稳。")
            else:
                actions = self._available_test_actions(user)
                detail, missing_actions = await self._generate_full_test_detail_enhancement(
                    segment,
                    plan or {},
                    state or {},
                    actions,
                )
                events = self._build_full_test_events(
                    detail,
                    actions=actions,
                    segment=segment,
                    spacing_seconds=120,
                )
                sim = {
                    "active": True,
                    "label": "完整测试",
                    "kind": "full_real_test",
                    "date": _today_key(),
                    "segment_start": self._minutes_to_hhmm(_safe_int(segment.get("start"), 0)),
                    "segment_end": self._minutes_to_hhmm(_safe_int(segment.get("end"), 0)),
                    "events": events,
                    "sent_count": 0,
                    "detail_summary": _single_line(detail.get("summary"), 120),
                    "requested_actions": list(actions),
                    "missing_actions": list(missing_actions),
                }
                async with self._data_lock:
                    current = self._get_user(user_id)
                    current["simulation_mode"] = sim
                    self._sync_simulation_next_event(current)
                    self._save_data_sync()
                lines = [
                    "完整测试已开启：接下来会按真实主动链，每两分钟左右发送一条，直到这一段的测试跑完后自动退出。",
                    f"测试日程段：{sim['segment_start']}-{sim['segment_end']}｜{_single_line((segment.get('item') or {}).get('activity'), 60)}",
                    f"细化摘要：{sim['detail_summary'] or '（未产出摘要）'}",
                    f"计划覆盖能力：{self._summarize_test_action_labels(actions)}",
                ]
                if missing_actions:
                    lines.append("提示：这轮细化里还有这些能力没被模型自然安排出来：" + self._summarize_test_action_labels(missing_actions))
                lines.append(self._format_simulation_summary(self._get_user(user_id)))
                await self._reply(event, "\n".join(lines))
                asyncio.create_task(self._kick_proactive_loop_once())
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
        group_id = self._extract_group_id_from_event(event)
        if not group_id:
            yield event.plain_result("这条命令需要在群聊里使用。")
            return
        if not self.enable_group_companion or not self._group_allowed_by_access_mode(group_id):
            if self.group_access_mode == "blacklist" and group_id in self._configured_group_blacklist_ids():
                yield event.plain_result("这个群在群聊陪伴黑名单中，暂时不启用。")
            elif self.group_access_mode == "whitelist":
                yield event.plain_result("这个群还没有加入群聊陪伴白名单，暂时不启用。")
            else:
                yield event.plain_result("这个群暂时不启用群聊陪伴。")
            return
        message = str(event.message_str or "").strip()
        action = ""
        value = ""
        parts = message.split(maxsplit=2)
        if len(parts) >= 2:
            action = parts[1].strip()
        if len(parts) >= 3:
            value = parts[2].strip()
        async with self._data_lock:
            group = self._get_group(group_id)
            if action in {"开启", "启用", "打开"}:
                group["enabled"] = True
                self._save_data_sync()
                response = "群聊陪伴观察已开启。"
            elif action in {"关闭", "停用", "关掉"}:
                group["enabled"] = False
                self._save_data_sync()
                response = "群聊陪伴观察已关闭。"
            elif action in {"黑话", "梗", "词"}:
                slang = group.get("slang_terms") if isinstance(group.get("slang_terms"), list) else []
                meanings = group.get("slang_meanings") if isinstance(group.get("slang_meanings"), dict) else {}
                if slang:
                    lines = ["当前群内常见词/梗："]
                    for item in slang[:20]:
                        if not isinstance(item, dict):
                            continue
                        term = _single_line(item.get("term"), 20)
                        if not term:
                            continue
                        meaning = ""
                        if isinstance(meanings.get(term), dict):
                            meaning = _single_line(meanings[term].get("meaning"), 60)
                        lines.append(f"- {term}｜出现 {item.get('count', 0)} 次" + (f"｜{meaning}" if meaning else ""))
                    response = "\n".join(lines)
                else:
                    response = "还没有学到稳定的群内常见词。"
            elif action in {"群友", "成员", "画像"}:
                members = group.get("members") if isinstance(group.get("members"), dict) else {}
                ranked = sorted(
                    [item for item in members.values() if isinstance(item, dict)],
                    key=lambda item: _safe_int(item.get("count"), 0, 0),
                    reverse=True,
                )[:12]
                if ranked:
                    response = "当前群友轻画像：\n" + "\n".join(
                        f"- {_single_line(item.get('name'), 18) or '群友'}｜发言 {item.get('count', 0)}｜"
                        f"{' / '.join(_single_line(x, 18) for x in (item.get('recent_phrases') or [])[:3])}"
                        for item in ranked
                    )
                else:
                    response = "还没有群友样本。"
            elif action in {"话题", "线程"}:
                response = "当前群聊话题线程：\n" + (self._format_group_topic_threads_for_prompt(group) or "暂无。")
            elif action in {"片段", "群聊片段", "记忆"}:
                response = "近期群聊片段记忆：\n" + (self._format_group_episodes_for_prompt(group) or "暂无。")
            elif action in {"插话判定", "插话反馈", "反馈"}:
                response = "群聊插话反馈：" + self._format_group_interjection_feedback(group)
            elif action in {"关系网", "关系网络", "互动关系"}:
                response = "群友互动关系：\n" + (self._format_group_relationship_graph_for_prompt(group) or "暂无。")
            elif action in {"状态", "气氛", ""}:
                response = self._format_group_status(group)
            else:
                response = (
                    "群聊陪伴命令：\n"
                    "陪伴群 状态\n"
                    "陪伴群 黑话\n"
                    "陪伴群 群友\n"
                    "陪伴群 话题\n"
                    "陪伴群 片段\n"
                    "陪伴群 插话反馈\n"
                    "陪伴群 关系网\n"
                    "陪伴群 开启\n"
                    "陪伴群 关闭"
                )
        yield event.plain_result(response)
        event.stop_event()

    @filter.command("陪伴模拟唤醒")
    async def simulate_passive_wakeup(self, event: AstrMessageEvent, content: str = ""):
        content = str(content or "").strip()
        if not content:
            yield event.plain_result("用法：陪伴模拟唤醒 <想模拟的用户消息>")
            return
        if not bool(getattr(event, "is_private_chat", lambda: False)()):
            yield event.plain_result(self._private_only_text())
            return

        session_curr_cid = await self.context.conversation_manager.get_curr_conversation_id(
            event.unified_msg_origin,
        )
        if not session_curr_cid:
            yield event.plain_result("当前还没有可复用的私聊对话,先正常聊几句再试会更准。")
            return

        conv = await self.context.conversation_manager.get_conversation(
            event.unified_msg_origin,
            session_curr_cid,
        )
        if not conv:
            yield event.plain_result("没有拿到当前私聊对话,暂时没法走原生人格链。")
            return

        simulated_conv = self._clone_conversation_for_simulated_wakeup(conv, event.message_str)
        yield event.request_llm(
            prompt=content,
            session_id=event.session_id,
            conversation=simulated_conv,
        )

    def _format_relationship_summary(self, user: dict[str, Any]) -> str:
        profile = self._relationship_profile(user)
        return (
            f"{profile['level']}｜回复率 {profile['reply_rate_label']}｜"
            f"偏好 {profile['preference']}"
        )

    def _format_action_affinity_summary(self, user: dict[str, Any]) -> str:
        raw = user.get("action_reply_affinity")
        if not isinstance(raw, dict) or not raw:
            return "暂无样本"
        labels = {
            "screen_peek": "窥屏",
            "photo_text": "发图",
            "poke": "戳一戳",
            "voice": "语音",
        }
        parts = []
        for key in ("screen_peek", "photo_text", "poke", "voice"):
            stats = raw.get(key)
            if not isinstance(stats, dict):
                continue
            sent = _safe_int(stats.get("sent"), 0, 0)
            replied = _safe_int(stats.get("replied"), 0, 0)
            if sent <= 0:
                continue
            parts.append(f"{labels[key]} {replied}/{sent}")
        return "｜".join(parts) if parts else "暂无样本"

    def _format_next_proactive(self, user: dict[str, Any]) -> str:
        if self._simulation_active(user):
            sim = user.get("simulation_mode")
            if isinstance(sim, dict):
                events = sim.get("events")
                if isinstance(events, list) and events:
                    item = events[0]
                    if isinstance(item, dict):
                        sim_window = _single_line(item.get("_simulated_window") or item.get("window"), 20)
                        reason = item.get("reason") or "未记录"
                        action = item.get("action") or "message"
                        motive = _single_line(item.get("motive"), 36)
                        prefix = f"模拟 {sim_window}" if sim_window else "模拟下一条"
                        if motive:
                            return f"{prefix}｜{reason}｜{action}｜{motive}"
                        return f"{prefix}｜{reason}｜{action}"
        next_at = _safe_float(user.get("next_proactive_at"), 0)
        if next_at <= 0:
            return "未安排"
        when = datetime.fromtimestamp(next_at).strftime("%m-%d %H:%M")
        reason = user.get("planned_proactive_reason") or "未记录"
        action = user.get("planned_proactive_action") or "message"
        motive = _single_line(user.get("planned_proactive_motive"), 36)
        timer_event = self._get_active_llm_timer(user)
        source_prefix = "模型预约 " if isinstance(timer_event, dict) and _safe_float(timer_event.get("scheduled_ts"), 0) == next_at else ""
        if motive:
            return f"{source_prefix}{when}｜{reason}｜{action}｜{motive}"
        return f"{source_prefix}{when}｜{reason}｜{action}"

    def _format_simulation_summary(self, user: dict[str, Any]) -> str:
        sim = user.get("simulation_mode")
        if not isinstance(sim, dict) or not sim.get("active"):
            return ""
        events = sim.get("events")
        if not isinstance(events, list):
            events = []
        label = self._simulation_label(user)
        lines = [f"{label}：进行中（剩余 {len(events)} 条）"]
        for item in events[:6]:
            if not isinstance(item, dict):
                continue
            sim_window = _single_line(item.get("_simulated_window") or item.get("window"), 20)
            when = f"模拟 {sim_window}" if sim_window else datetime.fromtimestamp(_safe_float(item.get("_scheduled_ts"), _now_ts())).strftime("%H:%M")
            lines.append(
                f"- {when}｜{item.get('reason', '')}｜{item.get('action', 'message')}｜{_single_line(item.get('topic') or item.get('motive'), 28)}"
            )
        return "\n".join(lines)

    def _format_plan_status_summary(self, plan: dict[str, Any]) -> str:
        if not isinstance(plan, dict) or not plan.get("date"):
            return "未生成"
        plan_date = str(plan.get("date") or "").strip()
        today = _today_key()
        if plan_date == today:
            return plan_date
        if self._is_plan_date_active(plan_date):
            due_minutes = self._daily_plan_due_minutes()
            return f"{plan_date}（跨零点沿用,待 {self._minutes_to_hhmm(due_minutes)} 后生成今日日程）"
        return plan_date

    def _format_user_profile(self, user: dict[str, Any]) -> str:
        profile = self._relationship_profile(user)
        return (
            "你的陪伴画像：\n"
            f"关系层级：{profile['level']}\n"
            f"回复率：{profile['reply_rate_label']}\n"
            f"互动次数：{profile['inbound_count']}\n"
            f"主动发送：{profile['proactive_count']}\n"
            f"主动后回复：{profile['reply_count']}\n"
            f"各主动方式承接：{self._format_action_affinity_summary(user)}\n"
            f"打扰偏好：{profile['preference']}\n"
            f"关系分：{profile['score']}\n"
            f"人格判断：{profile.get('note') or '暂无'}\n"
            f"陪伴记忆：{_single_line(self._format_companion_memory_for_prompt(user), 180)}\n"
            f"表达学习：{_single_line(self._format_expression_profile_for_prompt(user), 180)}\n"
            f"气氛状态：{_single_line(self._format_intent_relationship_injection(user), 180) or '暂无'}\n"
            f"媒介偏好：{_single_line(self._action_preference_hint(user), 180) or '暂无'}"
        )

    def _format_diaries(self) -> str:
        diaries = self.data.get("bot_diaries", [])
        if not isinstance(diaries, list) or not diaries:
            return "还没有 Bot 日记。"
        return "\n\n".join(self._format_single_diary(diary) for diary in diaries[-3:])

    def _format_single_diary(self, diary: dict[str, Any]) -> str:
        if not isinstance(diary, dict) or not diary:
            return "日记生成失败。"
        tags = diary.get("tags", [])
        tag_text = "、".join(str(tag) for tag in tags) if isinstance(tags, list) else ""
        return (
            f"{diary.get('date', _today_key())} 的 Bot 日记：\n"
            f"{diary.get('summary', '')}\n"
            f"可分享碎片：{diary.get('share_seed', '')}\n"
            f"标签：{tag_text or '无'}\n"
            f"{self._format_diary_story_plan(diary)}"
        )

    def _format_diary_story_plan(self, diary: dict[str, Any]) -> str:
        plan = diary.get("story_plan")
        if not isinstance(plan, dict):
            return "今日预设：无"
        lines = ["今日预设："]
        events = plan.get("today_events", [])
        if isinstance(events, list) and events:
            for item in events[:4]:
                if isinstance(item, dict):
                    lines.append(f"- {item.get('window', '')} {item.get('event', '')}")
        proactive = plan.get("proactive_events", [])
        if isinstance(proactive, list) and proactive:
            lines.append("主动计划：")
            for item in proactive[:4]:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('window', '')} {item.get('reason', '')}/{item.get('action', 'message')}："
                        f"{item.get('why', '')}"
                        + (f"｜动机：{item.get('motive', '')}" if item.get("motive") else "")
                    )
        long_term = plan.get("long_term_events", [])
        if isinstance(long_term, list) and long_term:
            lines.append("长线事件：")
            for item in long_term[:3]:
                if isinstance(item, dict):
                    lines.append(
                        f"- {item.get('title', '')}：{item.get('status', '')}｜"
                        f"{item.get('tendency', '') or item.get('next_hint', '')}"
                    )
        return "\n".join(lines)

    def _format_state_detail(self, state: dict[str, Any]) -> str:
        if not isinstance(state, dict) or not state:
            return "今天还没有拟人状态。"
        condition_lines = []
        conditions = state.get("conditions", [])
        if isinstance(conditions, list):
            for cond in conditions:
                if not isinstance(cond, dict):
                    continue
                if not self._should_show_condition(cond):
                    continue
                condition_lines.append(
                    f"- {cond.get('title', cond.get('kind', '状态'))}："
                    f"{cond.get('label', '')}｜情绪 {cond.get('mood', '平稳')}｜"
                    f"{('阶段 ' + str(cond.get('phase')) + '｜') if cond.get('phase') else ''}"
                    f"{('原因 ' + str(cond.get('cause')) + '｜') if cond.get('cause') else ''}"
                    f"能量 {cond.get('energy_delta', 0)}｜"
                    f"{self._format_transition_hint(cond)}"
                    f"剩余 {self._format_remaining(cond.get('end_ts'))}"
                )
        condition_text = "\n".join(condition_lines) if condition_lines else "- 当前没有明显叠加状态"
        location_line = ""
        current_location = self._current_location_state_text(state)
        if current_location:
            location_line = f"地点感：{current_location}\n"
        return (
            f"{self.bot_name} 今天的拟人状态：\n"
            f"能量：{state.get('energy', 70)}/100\n"
            f"情绪底色：{state.get('mood_bias', '平稳')}\n"
            f"{location_line}"
            f"睡眠：{state.get('sleep', '睡眠平稳')}\n"
            f"梦境：{state.get('dream', '没有记住梦')}\n"
            f"健康：{'不适用' if self._is_inapplicable_state_text(state.get('health', '')) else state.get('health', '状态正常')}\n"
            f"饥饿：{'不适用' if self._is_inapplicable_state_text(state.get('hunger', '')) else state.get('hunger', '饥饿感平稳')}\n"
            f"周期：{'不适用' if self._is_inapplicable_state_text(state.get('body_cycle', '')) else state.get('body_cycle', '无明显周期影响')}\n"
            f"天气：{state.get('weather', '暂无天气信息')}\n"
            f"影响：{state.get('note', '今天状态比较平稳,适合按原计划行动。')}\n"
            f"状态走向：{self._format_state_transition_overview(state)}\n"
            f"当前叠加：\n{condition_text}"
        )

    def _format_dream_view(self, state: dict[str, Any]) -> str:
        if not isinstance(state, dict) or not state:
            return "今天还没有梦境状态。"
        remembered = self.data.get("daily_dream")
        if not isinstance(remembered, dict) or remembered.get("date") != _today_key():
            remembered = {}
        dream_text = _single_line(remembered.get("content"), 1200) or _single_line(state.get("dream"), 220) or "没有记住梦"
        dream_type = _single_line(remembered.get("dream_type"), 40) or "碎片梦"
        factors = remembered.get("factors", [])
        if isinstance(factors, list):
            factor_text = "、".join(_single_line(item, 30) for item in factors[:8] if _single_line(item, 30))
        else:
            factor_text = ""
        aftertaste_lines: list[str] = []
        for cond in state.get("conditions", []) or []:
            if not isinstance(cond, dict):
                continue
            if str(cond.get("kind") or "") != "dream_aftertaste" and str(cond.get("phase") or "") != "dream_aftertaste":
                continue
            label = _single_line(cond.get("label"), 80)
            mood = _single_line(cond.get("mood"), 20) or "平稳"
            cause = _single_line(cond.get("cause"), 80)
            remain = self._format_remaining(cond.get("end_ts"))
            pieces = [label] if label else []
            if mood:
                pieces.append(f"情绪 {mood}")
            if cause:
                pieces.append(cause)
            pieces.append(f"剩余 {remain}")
            aftertaste_lines.append("- " + "｜".join(pieces))
        remembered_afterglow = _single_line(remembered.get("afterglow"), 260)
        fragment_pool = self._normalize_dream_fragment_pool(self.data.get("dream_fragments", []))
        sampled = self._weighted_unique_fragment_sample(fragment_pool, count=6) if fragment_pool else []
        fragment_text = factor_text or ("、".join(sampled) if sampled else "（当前没有明显残留碎片）")
        afterglow_text = remembered_afterglow
        if aftertaste_lines:
            afterglow_text = (afterglow_text + "\n" if afterglow_text else "") + "\n".join(aftertaste_lines)
        if not afterglow_text:
            afterglow_text = "今天没有明显的梦后余韵。"
        return (
            f"{self.bot_name} 最近一次梦境：\n"
            f"梦境类型：{dream_type}\n"
            f"梦境因子/碎片：{fragment_text}\n"
            f"梦境内容：{dream_text}\n"
            f"梦境余韵：\n{afterglow_text}"
        )

    def _format_dream_fragment_pool_view(self) -> str:
        pool = self._normalize_dream_fragment_pool(self.data.get("dream_fragments", []))
        if not pool:
            return "现在还没有可用的梦境碎片。先生成日记或状态，通常就会慢慢积起来。"
        now_ts = _now_ts()
        ranked = sorted(
            pool,
            key=lambda item: (
                -self._dream_fragment_effective_weight(item, now_ts=now_ts),
                -_safe_float(item.get("created_ts"), 0),
            ),
        )
        lines = ["当前梦境碎片池："]
        for item in ranked[:12]:
            text = _single_line(item.get("text"), 40)
            if not text:
                continue
            effective = self._dream_fragment_effective_weight(item, now_ts=now_ts)
            raw_weight = _safe_float(item.get("weight"), 1.0)
            source = _single_line(item.get("source"), 20) or "unknown"
            age = self._format_timestamp_elapsed(item.get("created_ts"))
            lines.append(
                f"- {text}｜当前权重 {effective:.2f}（原始 {raw_weight:.2f}）｜来源 {source}｜进入于 {age}"
            )
        if len(lines) == 1:
            return "现在还没有可用的梦境碎片。"
        return "\n".join(lines)

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE)
    async def on_private_message(self, event: AstrMessageEvent):
        user_id = str(event.get_sender_id())
        text = _single_line(event.message_str, 120)
        if text.startswith(("陪伴", "/陪伴", "私聊陪伴", "主动陪伴")):
            return

        async with self._data_lock:
            user = self._get_user(user_id)
            if self._is_recent_poke_echo(user, text):
                logger.info("[PrivateCompanion] 忽略 poke 回流事件,不计入用户新消息: %s", user_id)
                return
            user["umo"] = event.unified_msg_origin
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
                )
                user["relationship_score"] = _safe_int(user.get("relationship_score"), 0) + 2
                user["awaiting_reply_since"] = 0
                user["last_reply_at"] = _now_ts()
                user["pending_followup_event"] = {}
                user["planned_proactive_quota_exempt"] = False
            user["ignored_streak"] = 0
            if text:
                user["last_user_message"] = text
                user["episode_message_count"] = _safe_int(user.get("episode_message_count"), 0, 0) + 1
                self._update_expression_profile_from_message(user, text)
                self._update_companion_memory_from_message(user, text)
                self._update_open_loops_from_message(user, text)
                self._update_action_preferences_from_message(user, text)
                if self.enable_intent_emotion_analysis:
                    intent_profile = self._analyze_inbound_intent(text)
                    user["intent_profile"] = intent_profile
                    self._update_relationship_state_from_intent(user, intent_profile)
                if self._cancel_inbound_conflicting_greeting(user, now=_now_ts()):
                    logger.info("[PrivateCompanion] 用户已在当前问候时段自然来聊,已取消冲突问候候选: %s", user_id)
                    if not self._simulation_active(user) and _safe_float(user.get("next_proactive_at"), 0) <= 0:
                        self._schedule_next_proactive(user, now=_now_ts())
            care_feedback_applied = bool(text) and self._apply_care_feedback_to_state(text)
            if care_feedback_applied:
                user["relationship_score"] = _safe_int(user.get("relationship_score"), 0) + 2
            schedule_adjustment_applied = bool(text) and self._record_schedule_adjustment_from_interaction(text)
            if schedule_adjustment_applied:
                user["relationship_score"] = _safe_int(user.get("relationship_score"), 0) + 1

            response = ""
            self._save_data_sync()
            user_snapshot = dict(user)

        if schedule_adjustment_applied:
            asyncio.create_task(self._kick_proactive_loop_once())
        if response:
            await self._reply(event, response)
            event.stop_event()
        asyncio.create_task(self._refresh_persona_relationship(user_id, user_snapshot))
        asyncio.create_task(self._maybe_refresh_companion_memory(user_id, user_snapshot))
        asyncio.create_task(self._maybe_refresh_dialogue_episode(user_id, user_snapshot))

    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE)
    async def on_group_message(self, event: AstrMessageEvent):
        if not self.enable_group_companion:
            return
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
        async with self._data_lock:
            group = self._get_group(group_id)
            self._update_group_observation(
                group,
                sender_id=sender_id,
                sender_name=sender_name,
                text=text,
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
            group_snapshot = dict(group)
        if isinstance(registration_payload, dict) and registration_payload.get("blocked_reply"):
            await self._reply(event, str(registration_payload.get("blocked_reply") or "你是小猪"))
            event.stop_event()
            return
        if registration_payload:
            asyncio.create_task(self._refresh_worldbook_self_registration_impression(registration_payload))
        if share_scheduled:
            asyncio.create_task(self._kick_proactive_loop_once())
        asyncio.create_task(self._maybe_refresh_group_episode(group_id, group_snapshot))
        asyncio.create_task(self._maybe_refresh_group_slang_meanings(group_id, group_snapshot))
        await self._maybe_group_interject(event, group_snapshot, text)
        original_interject_at = _safe_float(group.get("last_interject_at"), 0) if isinstance(group, dict) else 0
        if _safe_float(group_snapshot.get("last_interject_at"), 0) > original_interject_at:
            async with self._data_lock:
                current = self._get_group(group_id)
                current["last_interject_at"] = group_snapshot.get("last_interject_at", current.get("last_interject_at", 0))
                current["interject_day"] = group_snapshot.get("interject_day", current.get("interject_day", ""))
                current["interject_today"] = group_snapshot.get("interject_today", current.get("interject_today", 0))
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

