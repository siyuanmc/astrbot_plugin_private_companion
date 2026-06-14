# -*- coding: utf-8 -*-
"""
ProactiveEngineMixin — 主动行为候选、决策、计划事件与动作选择
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




class ProactiveEngineMixin:
    """主动行为候选、决策、计划事件与动作选择"""

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
        signature = self._proactive_topic_signature(topic, motive)
        pool = self._cleanup_proactive_candidate_pool(now=now)
        if status in {"blocked", "accepted"}:
            for existing in reversed(pool):
                if not isinstance(existing, dict):
                    continue
                if str(existing.get("status") or "") != status:
                    continue
                if str(existing.get("user_id") or "") != str(user_id):
                    continue
                if status == "accepted" and str(existing.get("id") or "") == str(candidate.get("id") or ""):
                    continue
                if not self._topic_signature_similar(signature, str(existing.get("signature") or "")):
                    continue
                if now - _safe_float(existing.get("last_seen_ts") or existing.get("created_ts"), 0) > 18 * 3600:
                    continue
                existing["repeat_count"] = _safe_int(existing.get("repeat_count"), 1, 1) + 1
                existing["last_seen_ts"] = now
                existing["scheduled_ts"] = max(_safe_float(existing.get("scheduled_ts"), scheduled), scheduled)
                existing["topic"] = topic or _single_line(existing.get("topic"), 80)
                existing["motive"] = motive or _single_line(existing.get("motive"), 160)
                existing["score"] = max(_safe_int(existing.get("score"), 0, 0, 100), _safe_int(candidate.get("score"), 0, 0, 100))
                return existing
        item = {
            "id": uuid.uuid4().hex[:12],
            "created_ts": now,
            "last_seen_ts": now,
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
            "repeat_count": 1,
        }
        pool.append(item)
        del pool[:-120]
        return item

    def _proactive_candidate_repeated(self, user: dict[str, Any], candidate: dict[str, Any]) -> bool:
        signature = self._proactive_topic_signature(
            candidate.get("topic"),
            candidate.get("motive"),
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
        rest_until = self._user_rest_silence_until(user, now=now)
        if rest_until > now and scheduled < rest_until and source != "timer":
            self._record_proactive_candidate(user_id, candidate, status="blocked", note="用户明确休息中")
            return False
        if not self._user_enabled_for_proactive(str(user_id), user):
            self._clear_pending_proactive_plan(user)
            return False
        timer_event = self._get_active_llm_timer(user)
        timer_scheduled = _safe_float(timer_event.get("scheduled_ts"), 0) if isinstance(timer_event, dict) else 0.0
        if timer_scheduled > now and scheduled < timer_scheduled:
            if self._in_llm_timer_silence_window(user, now=now):
                self._remember_silenced_candidate_for_timer(user, candidate, now=now)
            self._record_proactive_candidate(user_id, candidate, status="blocked", note="已有用户预约/定时主动")
            return False
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
        self._clear_planned_proactive_trigger(user)
        user["planned_proactive_quota_exempt"] = False
        user["planned_candidate_id"] = item.get("id", "")
        self._set_planned_proactive_trigger(
            user,
            message_id=self._candidate_trigger_message_id(candidate),
            umo=_single_line(candidate.get("trigger_umo") or candidate.get("umo"), 160),
            created_at=_safe_float(candidate.get("trigger_ts") or candidate.get("created_ts"), 0),
        )
        context_key = _single_line(candidate.get("context_key"), 60)
        context = candidate.get("context")
        if context_key and isinstance(context, dict):
            user[context_key] = context
        return True

    def _llm_timer_pre_silence_seconds(self) -> float:
        return max(0.0, float(getattr(self, "timer_pre_silence_minutes", 20) or 0) * 60.0)

    def _upcoming_llm_timer_ts(self, user: dict[str, Any], *, now: float | None = None) -> float:
        event = self._get_active_llm_timer(user)
        if not isinstance(event, dict):
            return 0.0
        scheduled_ts = _safe_float(event.get("scheduled_ts"), 0)
        check_now = _now_ts() if now is None else now
        return scheduled_ts if scheduled_ts > check_now else 0.0

    def _in_llm_timer_pre_silence_window(self, user: dict[str, Any], *, now: float | None = None) -> bool:
        lead = self._llm_timer_pre_silence_seconds()
        if lead <= 0:
            return False
        check_now = _now_ts() if now is None else now
        timer_ts = self._upcoming_llm_timer_ts(user, now=check_now)
        return timer_ts > 0 and 0 < timer_ts - check_now <= lead

    def _in_llm_timer_silence_window(self, user: dict[str, Any], *, now: float | None = None) -> bool:
        event = self._get_active_llm_timer(user)
        if not isinstance(event, dict):
            return False
        check_now = _now_ts() if now is None else now
        scheduled_ts = _safe_float(event.get("scheduled_ts"), 0)
        if scheduled_ts <= check_now:
            return False
        if bool(event.get("silence_until_due")):
            return True
        return self._in_llm_timer_pre_silence_window(user, now=check_now)

    def _remember_silenced_plan_for_timer(self, user: dict[str, Any], *, now: float | None = None) -> None:
        event = self._get_active_llm_timer(user)
        if not isinstance(event, dict):
            return
        planned_source = str(user.get("planned_proactive_source") or "")
        if planned_source == "timer":
            return
        topic = _single_line(user.get("planned_proactive_topic"), 80)
        motive = _single_line(user.get("planned_proactive_motive"), 160)
        reason = _single_line(user.get("planned_proactive_reason"), 40)
        action = _single_line(user.get("planned_proactive_action"), 32)
        if not any((topic, motive, reason)):
            return
        existing = event.get("deferred_context")
        if isinstance(existing, dict) and existing:
            return
        event["deferred_context"] = {
            "created_at": now or _now_ts(),
            "reason": reason,
            "action": action,
            "topic": topic,
            "motive": self._normalize_internal_motive_text(motive),
            "source": planned_source,
        }

    def _remember_silenced_candidate_for_timer(
        self,
        user: dict[str, Any],
        candidate: dict[str, Any],
        *,
        now: float | None = None,
    ) -> None:
        event = self._get_active_llm_timer(user)
        if not isinstance(event, dict):
            return
        existing = event.get("deferred_context")
        if isinstance(existing, dict) and existing:
            return
        topic = _single_line(candidate.get("topic"), 80)
        motive = _single_line(candidate.get("motive"), 160)
        reason = _single_line(candidate.get("reason"), 40)
        action = _single_line(candidate.get("action"), 32)
        if not any((topic, motive, reason)):
            return
        event["deferred_context"] = {
            "created_at": now or _now_ts(),
            "reason": reason,
            "action": action,
            "topic": topic,
            "motive": self._normalize_internal_motive_text(motive),
            "source": _single_line(candidate.get("source"), 40),
        }

    def _promote_due_llm_timer_plan(self, user: dict[str, Any], *, now: float | None = None) -> bool:
        event = self._get_active_llm_timer(user)
        if not isinstance(event, dict):
            return False
        check_now = _now_ts() if now is None else now
        scheduled_ts = _safe_float(event.get("scheduled_ts"), 0)
        if scheduled_ts <= 0 or scheduled_ts > check_now:
            return False
        user["next_proactive_at"] = scheduled_ts
        user["planned_proactive_reason"] = _single_line(event.get("reason"), 40) or "check_in"
        user["planned_proactive_action"] = _single_line(event.get("action"), 24) or "message"
        user["planned_proactive_source"] = "timer"
        user["planned_proactive_motive"] = self._normalize_internal_motive_text(_single_line(event.get("motive"), 140))
        user["planned_proactive_topic"] = _single_line(event.get("topic"), 60)
        user["planned_event_chain"] = list(event.get("chain") or []) if isinstance(event.get("chain"), list) else []
        user["planned_opener_mode"] = ""
        user["planned_followup_kind"] = ""
        user["planned_proactive_quota_exempt"] = False
        self._set_planned_proactive_trigger(
            user,
            message_id=_single_line(event.get("trigger_message_id"), 120),
            umo=_single_line(event.get("trigger_umo"), 160),
            created_at=_safe_float(event.get("trigger_ts"), 0),
        )
        return True

    def _promote_upcoming_llm_timer_plan(self, user: dict[str, Any], *, now: float | None = None) -> bool:
        event = self._get_active_llm_timer(user)
        if not isinstance(event, dict):
            return False
        check_now = _now_ts() if now is None else now
        scheduled_ts = _safe_float(event.get("scheduled_ts"), 0)
        if scheduled_ts <= check_now:
            return False
        user["next_proactive_at"] = scheduled_ts
        user["planned_proactive_reason"] = _single_line(event.get("reason"), 40) or "check_in"
        user["planned_proactive_action"] = _single_line(event.get("action"), 24) or "message"
        user["planned_proactive_source"] = "timer"
        user["planned_proactive_motive"] = self._normalize_internal_motive_text(_single_line(event.get("motive"), 140))
        user["planned_proactive_topic"] = _single_line(event.get("topic"), 60)
        user["planned_event_chain"] = list(event.get("chain") or []) if isinstance(event.get("chain"), list) else []
        user["planned_opener_mode"] = ""
        user["planned_followup_kind"] = ""
        user["planned_proactive_quota_exempt"] = False
        self._set_planned_proactive_trigger(
            user,
            message_id=_single_line(event.get("trigger_message_id"), 120),
            umo=_single_line(event.get("trigger_umo"), 160),
            created_at=_safe_float(event.get("trigger_ts"), 0),
        )
        return True

    def _should_send(self, user: dict[str, Any]) -> tuple[bool, str]:
        self._recover_stale_proactive_sending(user)
        user_id = str(user.get("user_id") or user.get("id") or "")
        if not self._user_enabled_for_proactive(user_id, user):
            self._clear_pending_proactive_plan(user)
            return False, "私聊对象未启用"
        if user.get("proactive_sending"):
            return False, "上一条主动消息仍在发送中"
        if not user.get("umo"):
            return False, "缺少私聊会话"
        if self._simulation_active(user):
            return self._should_send_simulation(user)
        if self.max_daily_messages <= 0:
            return False, "每日上限为 0"
        now = _now_ts()
        due_timer_active = self._has_due_llm_timer(user, now=now)
        if (
            self._user_rest_silence_until(user, now=now) > now
            and not due_timer_active
            and str(user.get("planned_proactive_source") or "") != "timer"
        ):
            return False, "用户明确休息中"
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

        planned_reason = str(user.get("planned_proactive_reason") or "")
        if due_timer_active and str(user.get("planned_proactive_source") or "") != "timer":
            self._promote_due_llm_timer_plan(user, now=now)
            planned_reason = str(user.get("planned_proactive_reason") or "")
        next_at = _safe_float(user.get("next_proactive_at"), 0)
        if next_at <= 0:
            self._schedule_next_proactive(user, now=now)
            return False, "已安排下一次候选主动时间"
        if self._promote_earlier_daily_greeting_event(user, now=now):
            planned_reason = str(user.get("planned_proactive_reason") or "")
            next_at = _safe_float(user.get("next_proactive_at"), 0)
        if (
            not due_timer_active
            and str(user.get("planned_proactive_source") or "") != "timer"
            and self._in_llm_timer_silence_window(user, now=now)
        ):
            self._remember_silenced_plan_for_timer(user, now=now)
            self._promote_upcoming_llm_timer_plan(user, now=now)
            return False, "用户预约静默窗口"
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
            load_defer_note = self._photo_text_load_defer_note(planned_action)
            if load_defer_note:
                self._defer_planned_photo_text_for_load(user, now=now, note=load_defer_note)
                return False, load_defer_note
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
        if self._jm_cosmos_read_available(user):
            actions.append("jm_cosmos_read")
        actions.extend(f"external:{item['name']}" for item in self._available_external_proactive_abilities(user) if item.get("name"))
        return actions

    @staticmethod
    def _normalize_external_ability_name(value: Any) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9_.:-]+", "_", text)
        return text[:64].strip("_")

    def _external_ability_store(self) -> dict[str, Any]:
        if not isinstance(getattr(self, "data", None), dict):
            self.data = {}
        store = self.data.setdefault("external_proactive_abilities", {})
        if not isinstance(store, dict):
            store = {}
            self.data["external_proactive_abilities"] = store
        return store

    def register_external_proactive_ability(self, spec: dict[str, Any]) -> bool:
        if not isinstance(spec, dict):
            return False
        name = self._normalize_external_ability_name(spec.get("name"))
        executor = spec.get("executor")
        if not name or not callable(executor):
            logger.warning("[PrivateCompanion] 外部主动能力注册失败: name/executor 无效")
            return False
        default_config = spec.get("default_config") if isinstance(spec.get("default_config"), dict) else {}
        config_schema = spec.get("config_schema") if isinstance(spec.get("config_schema"), dict) else {}
        meta = {
            "name": name,
            "module": _single_line(spec.get("module"), 24) or "外部主动能力",
            "label": _single_line(spec.get("label"), 32) or name,
            "description": _single_line(spec.get("description"), 160),
            "when": _single_line(spec.get("when"), 120) or "外部插件认为合适的场景",
            "use_for": _single_line(spec.get("use_for"), 120) or _single_line(spec.get("description"), 120),
            "avoid": _single_line(spec.get("avoid"), 120) or "不要暴露插件调用过程,不要硬触发",
            "default_enabled": bool(spec.get("default_enabled", False)),
            "share_probability": max(0.0, min(1.0, _safe_float(spec.get("share_probability"), _safe_float(default_config.get("share_probability"), 0.12)))),
            "min_interval_hours": max(0.0, _safe_float(spec.get("min_interval_hours"), _safe_float(default_config.get("min_interval_hours"), 12))),
            "config_schema": deepcopy(config_schema),
            "default_config": deepcopy(default_config),
        }
        self._external_proactive_abilities[name] = {**meta, "executor": executor}
        try:
            store = self._external_ability_store()
            item = store.get(name) if isinstance(store.get(name), dict) else {}
            config = item.get("config") if isinstance(item.get("config"), dict) else {}
            merged_config = {**default_config, **config}
            item.update({
                "name": name,
                "module": meta["module"],
                "label": meta["label"],
                "description": meta["description"],
                "when": meta["when"],
                "use_for": meta["use_for"],
                "avoid": meta["avoid"],
                "enabled": bool(item.get("enabled", meta["default_enabled"])),
                "share_probability": _safe_float(item.get("share_probability"), meta["share_probability"], 0.0),
                "min_interval_hours": _safe_float(item.get("min_interval_hours"), meta["min_interval_hours"], 0.0),
                "config": merged_config,
                "config_schema": deepcopy(config_schema),
                "registered": True,
                "updated_ts": _now_ts(),
            })
            store[name] = item
            self._save_data_sync()
        except Exception as exc:
            logger.debug("[PrivateCompanion] 外部主动能力状态保存失败: %s", exc)
        logger.info("[PrivateCompanion] 已注册外部主动能力: %s", name)
        return True

    def unregister_external_proactive_ability(self, name: str) -> bool:
        normalized = self._normalize_external_ability_name(name)
        removed = self._external_proactive_abilities.pop(normalized, None) is not None
        try:
            store = self._external_ability_store()
            item = store.get(normalized)
            if isinstance(item, dict):
                item["registered"] = False
                item["updated_ts"] = _now_ts()
                self._save_data_sync()
        except Exception:
            pass
        return removed

    def external_proactive_abilities(self) -> list[dict[str, Any]]:
        store = self.data.get("external_proactive_abilities") if isinstance(getattr(self, "data", None), dict) else {}
        if not isinstance(store, dict):
            store = {}
        names = sorted(set(store.keys()) | set(self._external_proactive_abilities.keys()))
        items: list[dict[str, Any]] = []
        for name in names:
            runtime = self._external_proactive_abilities.get(name, {})
            stored = store.get(name) if isinstance(store.get(name), dict) else {}
            merged = {**{k: v for k, v in runtime.items() if k != "executor"}, **stored}
            merged["name"] = name
            merged["available"] = callable(runtime.get("executor"))
            merged["registered"] = bool(runtime)
            merged["enabled"] = bool(merged.get("enabled", merged.get("default_enabled", False)))
            merged["share_probability"] = max(0.0, min(1.0, _safe_float(merged.get("share_probability"), 0.0)))
            merged["min_interval_hours"] = max(0.0, _safe_float(merged.get("min_interval_hours"), 0.0))
            items.append(merged)
        return items

    def _external_ability_config(self, name: str) -> dict[str, Any]:
        store = self.data.get("external_proactive_abilities") if isinstance(self.data.get("external_proactive_abilities"), dict) else {}
        item = store.get(name) if isinstance(store.get(name), dict) else {}
        config = item.get("config") if isinstance(item.get("config"), dict) else {}
        return dict(config)

    def _external_ability_enabled(self, name: str) -> bool:
        item = next((entry for entry in self.external_proactive_abilities() if entry.get("name") == name), None)
        if not isinstance(item, dict):
            return False
        return bool(item.get("enabled") and item.get("available"))

    def _available_external_proactive_abilities(self, user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        now = _now_ts()
        items: list[dict[str, Any]] = []
        for item in self.external_proactive_abilities():
            name = str(item.get("name") or "")
            if not name or not item.get("enabled") or not item.get("available"):
                continue
            last = _safe_float(item.get("last_executed_ts"), 0)
            cooldown = _safe_float(item.get("min_interval_hours"), 0) * 3600
            if cooldown > 0 and last > 0 and now - last < cooldown:
                continue
            items.append(item)
        return items

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
        if self._jm_cosmos_read_available(user):
            available.add("jm_cosmos_read")
        items: list[dict[str, str]] = []
        for raw in PROACTIVE_ABILITY_REGISTRY:
            if not isinstance(raw, dict):
                continue
            name = str(raw.get("name") or "").strip()
            if not name or name not in available:
                continue
            items.append({str(key): str(value) for key, value in raw.items()})
        for raw in self._available_external_proactive_abilities(user):
            name = str(raw.get("name") or "").strip()
            if not name:
                continue
            items.append(
                {
                    "module": _single_line(raw.get("module"), 24) or "外部主动能力",
                    "name": f"external:{name}",
                    "label": _single_line(raw.get("label"), 32) or name,
                    "when": _single_line(raw.get("when"), 120) or "外部插件认为合适时",
                    "use_for": _single_line(raw.get("use_for"), 120) or _single_line(raw.get("description"), 120),
                    "avoid": _single_line(raw.get("avoid"), 120) or "不要暴露插件调用过程",
                }
            )
        return items

    def _format_proactive_ability_search_hint(self, user: dict[str, Any] | None = None) -> str:
        abilities = self._available_proactive_abilities(user)
        if not abilities:
            return "当前只按普通文字私聊处理。"
        terms = self._worldview_terms()
        lines = [
            "以下内容只供内部决策,角色本人不感知这些能力名,最终聊天正文也不得提到能力、检索、工具、action 或模块。",
            "先在当前场景里检索主动能力,再选择 action；不要凭空猜一个能力名。",
            "能力按领域分层如下：",
        ]
        for item in abilities:
            name = _single_line(item.get("name"), 24)
            label = _single_line(item.get("label"), 16)
            when = _single_line(item.get("when"), 80)
            use_for = _single_line(item.get("use_for"), 80)
            avoid = _single_line(item.get("avoid"), 80)
            if name == "screen_peek":
                label = f"观察{terms['screen']}"
                when = when.replace("轻窥屏", f"看一眼{terms['screen']}").replace("探头一下", "轻轻确认一下")
                avoid = avoid.replace("屏幕", terms["screen"]).replace("偷看", "后台过程")
            elif name == "jm_cosmos_read":
                label = terms["private_reading"]
                when = f"有空、无聊或夜里自己想给{terms['bookshelf']}{terms['secret_drawer']}添一点阅读内容"
                use_for = "内部阅读、低频形成读后印象,是否提起交给人格"
            elif name == "photo_text" and terms.get("mode") in {"fantasy", "sci_fi"}:
                label = "画面加一句话"
            lines.append(
                "- {module}/{name}（{label}）：适用={when}；用于={use_for}；避开={avoid}".format(
                    module=_single_line(item.get("module"), 16),
                    name=name,
                    label=label,
                    when=when,
                    use_for=use_for,
                    avoid=avoid,
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
        terms = self._worldview_terms()
        lines = ["当前主动能力："]
        for item in abilities:
            name = str(item.get("name") or "")
            label = item.get("label")
            when = item.get("when")
            if name == "screen_peek":
                label = f"观察{terms['screen']}"
            elif name == "jm_cosmos_read":
                label = terms["private_reading"]
            lines.append(
                f"- {item.get('module')}/{name}：{label}｜{when}"
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
            "jm_cosmos_read": "私下阅读",
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
        required_actions = [action for action in actions if action in {"message", "screen_peek", "photo_text", "voice", "jm_cosmos_read"}]
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
        required_actions = [action for action in actions if action in {"message", "screen_peek", "photo_text", "voice", "jm_cosmos_read"}]
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

    def _pick_best_planned_event(
        self, user: dict[str, Any], now: float | None = None
    ) -> dict[str, Any] | None:
        now = now or _now_ts()
        candidates = []
        for event in (
            self._pick_pending_followup_event(user, now),
            self._pick_daily_greeting_event(user, now),
            self._habit_proactive_event_for_user(user, now=now),
            self._pick_state_need_event(user, now=now),
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

    def _pick_state_need_event(
        self,
        user: dict[str, Any],
        *,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        now = now or _now_ts()
        state = self.data.get("daily_state", {})
        if not isinstance(state, dict) or state.get("date") != _today_key():
            return None
        hunger_text = _single_line(state.get("hunger"), 80)
        if hunger_text in {"", "饥饿感平稳", "该人格不适用饥饿状态"}:
            return None
        if _safe_float(user.get("last_food_prompt_at"), 0) + 5 * 3600 > now:
            return None
        if _safe_float(user.get("last_food_feedback_at"), 0) + 2 * 3600 > now:
            return None
        active_hunger = None
        for cond in self._get_active_conditions():
            if isinstance(cond, dict) and str(cond.get("kind") or "") == "hunger":
                active_hunger = cond
                break
        if not isinstance(active_hunger, dict):
            return None
        started = _safe_float(active_hunger.get("start_ts"), now)
        if now - started < 25 * 60:
            return None
        minute = datetime.fromtimestamp(now).hour * 60 + datetime.fromtimestamp(now).minute
        if not (10 * 60 + 30 <= minute <= 21 * 60 + 40):
            return None
        intensity = max(0.0, min(1.0, self.humanized_state_intensity / 100))
        chance = 0.18 + 0.32 * intensity
        if random.random() > chance:
            return None
        delay_minutes = random.randint(4, 12) if now - started >= 55 * 60 else random.randint(12, 32)
        scheduled = now + delay_minutes * 60
        phase = _single_line(active_hunger.get("phase"), 24)
        topic = "吃点什么"
        if phase == "afternoon":
            topic = "下午想吃点甜的"
        elif phase == "late_snack":
            topic = "夜里要不要吃点东西"
        elif phase in {"lunch", "dinner"}:
            topic = "这一顿吃什么"
        return {
            "date": _today_key(),
            "window": self._window_from_delay_minutes(delay_minutes, width_minutes=18),
            "reason": "state_share",
            "action": "message",
            "why": "当前饥饿状态已经持续了一会儿,自然想把吃什么这件小事丢给用户一起决定。",
            "topic": topic,
            "motive": self._normalize_internal_motive_text(
                f"{hunger_text}已经挂了一会儿,不是汇报状态,只是自然想问问用户会选什么吃的"
            ),
            "scene": "饭点或嘴馋的小空档",
            "tone": "自然、轻一点",
            "impulse": "想问一句吃什么,看用户会不会顺手给个主意",
            "_scheduled_ts": scheduled,
            "_state_need": "hunger",
        }

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
        now = now or _now_ts()
        if self._in_llm_timer_silence_window(user, now=now):
            return None
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
        if scheduled <= now:
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

    @staticmethod
    def _parse_json_object(raw: Any) -> dict[str, Any] | None:
        text = str(raw or "").strip()
        if not text:
            return None
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I | re.S).strip()
        candidates = [text]
        match = re.search(r"\{.*\}", text, flags=re.S)
        if match:
            candidates.append(match.group(0))
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except Exception:
                continue
            if isinstance(parsed, dict):
                return parsed
        return None

    def _visual_share_tokens(self) -> tuple[str, ...]:
        # Broad visual anchors only. Specific subjects should be chosen by the model from context.
        return (
            "看", "拍", "图", "照片", "画面", "颜色", "形状", "光", "影", "反光",
            "桌", "纸", "书", "本", "笔", "杯", "饭", "饮", "路", "窗", "镜",
            "小物", "随手", "涂", "画", "包装", "屏幕", "边角",
        )

    def _pick_life_thought_topic(self, reason: str = "") -> str:
        terms = self._worldview_terms()
        if reason == "group_share":
            return f"{terms['group_chat']}里刚刚那个片段"
        if reason == "bili_video_share":
            return f"刚看到的{terms['video']}"
        if reason == "news_share":
            return "刚看到的一条新闻"
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
        terms = self._worldview_terms()
        if terms.get("mode") == "fantasy":
            object_examples = "营火边、行囊、靴扣、地图角、药草包、酒馆杯沿、委托纸、斗篷边、旅店窗、书页边缘"
            record_examples = "旅记、委托备忘、魔法笔记、读到的藏书里的一小句,或某个没写完的标题"
            photo_examples = "适合用水晶映像或随手画面递给熟人的具体场景"
        elif terms.get("mode") == "sci_fi":
            object_examples = "终端边、舱窗、随身包、杯沿、数据板、照明条、维修工具、航行日志、制服边角、资料页边缘"
            record_examples = "航行日志、终端备忘、读到的资料/影像流里的一小句,或某个没写完的标题"
            photo_examples = "适合用终端快照递给熟人的具体画面"
        else:
            object_examples = "桌边、手边、路上、食物、衣物、门口、杯沿、包装、车窗、书页边缘"
            record_examples = "日记、备忘录、作业、阅读/刷到内容里的一小句,或某个没写完的标题"
            photo_examples = "任何当前场景里适合顺手拍给熟人的具体画面"
        return (
            "给模型的内容选择菜单,只供内部挑选,不要把类别名写进正文：\n"
            f"- 眼前物：从当前{terms['schedule']}里的{object_examples}等具体物件里自选一个。\n"
            "- 脑内念头：一句突然冒出来的短想法、吐槽、联想或没头没尾的小结论。\n"
            "- 输入残留：上一轮聊天留下的余味、没接完的话、想补但没正式补的一点。\n"
            f"- 记录碎片：{record_examples}。\n"
            f"- 可拍画面：{photo_examples},不限定天气。\n"
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
        if reason == "news_share":
            news = user.get("news_context") if isinstance(user.get("news_context"), dict) else {}
            return _single_line(news.get("topic") or news.get("headline"), 48) or "刚看到的一条新闻"
        if reason == "web_exploration_share":
            exploration = user.get("web_exploration_context") if isinstance(user.get("web_exploration_context"), dict) else {}
            return _single_line(exploration.get("topic") or exploration.get("query"), 48) or "刚查到的新东西"
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

    def _sdgen_photo_available(self) -> bool:
        if not self.enable_photo_text_action:
            return False
        try:
            getter = getattr(getattr(self, "context", None), "get_registered_star", None)
            if callable(getter):
                for name in ("SDGen", "astrbot_plugin_sdgen"):
                    plugin = getter(name)
                    if plugin is not None and callable(getattr(plugin, "_call_t2i_api", None)):
                        return True
        except Exception:
            pass
        for obj in gc.get_objects():
            try:
                cls = obj.__class__
                module = str(getattr(cls, "__module__", ""))
                if "astrbot_plugin_sdgen" not in module:
                    continue
                if callable(getattr(obj, "_call_t2i_api", None)):
                    return True
            except Exception:
                continue
        return False

    def _local_photo_generation_load_state(self, *, force_refresh: bool = False) -> dict[str, Any]:
        now = _now_ts()
        if not self.enable_local_photo_load_guard:
            return {"enabled": False, "busy": False, "reason": "负载保护未启用", "sampled_at": now}
        cached = getattr(self, "_local_photo_load_cache", {}) if isinstance(getattr(self, "_local_photo_load_cache", {}), dict) else {}
        if cached and not force_refresh and now - _safe_float(cached.get("sampled_at"), 0) < 20:
            return dict(cached)
        state: dict[str, Any] = {
            "enabled": True,
            "available": False,
            "busy": False,
            "cpu_percent": 0.0,
            "memory_percent": 0.0,
            "reason": "",
            "sampled_at": now,
        }
        try:
            psutil = importlib.import_module("psutil")
            cpu_percent = float(psutil.cpu_percent(interval=0.05))
            memory_percent = float(getattr(psutil.virtual_memory(), "percent", 0.0) or 0.0)
            state.update(
                {
                    "available": True,
                    "cpu_percent": round(cpu_percent, 1),
                    "memory_percent": round(memory_percent, 1),
                }
            )
            reasons = []
            if cpu_percent >= self.local_photo_cpu_busy_percent:
                reasons.append(f"CPU {cpu_percent:.0f}%")
            if memory_percent >= self.local_photo_memory_busy_percent:
                reasons.append(f"内存 {memory_percent:.0f}%")
            state["busy"] = bool(reasons)
            state["reason"] = "、".join(reasons) if reasons else "负载正常"
        except Exception as exc:
            state["reason"] = f"无法读取系统负载:{exc.__class__.__name__}"
        self._local_photo_load_cache = dict(state)
        return state

    def _local_photo_generation_busy_state(self, *, force_refresh: bool = False) -> dict[str, Any] | None:
        state = self._local_photo_generation_load_state(force_refresh=force_refresh)
        if bool(state.get("enabled")) and bool(state.get("available")) and bool(state.get("busy")):
            return state
        return None

    def _action_has_photo_text(self, action: str) -> bool:
        return "photo_text" in {part.strip() for part in str(action or "").split("+") if part.strip()}

    def _photo_text_load_defer_note(self, action: str = "photo_text", *, force_refresh: bool = False) -> str:
        if not self._action_has_photo_text(action):
            return ""
        if self._daily_token_soft_limit_should_defer("photo_prompt"):
            return (
                "每日 Token 软限额已暂缓主动生图"
                f"（今日已用约 {self._today_llm_token_total()} Token；软限额 {self.daily_token_soft_limit}）"
            )
        if self.photo_generation_backend == "external":
            return ""
        if self.photo_generation_backend == "sdgen":
            local_available = self._sdgen_photo_available()
        else:
            local_available = self._comfyui_photo_available() or (
                self.photo_generation_backend == "auto" and self._sdgen_photo_available()
            )
        if not local_available:
            return ""
        state = self._local_photo_generation_busy_state(force_refresh=force_refresh)
        if not state:
            return ""
        if self.photo_generation_backend == "auto" and self._external_photo_available():
            return ""
        return (
            "电脑高负荷,已延后本地生图"
            f"（{state.get('reason') or '负载偏高'}；{self.local_photo_defer_minutes} 分钟后重试）"
        )

    def _defer_planned_photo_text_for_load(self, user: dict[str, Any], *, now: float, note: str) -> None:
        delay_seconds = max(60, int(self.local_photo_defer_minutes) * 60)
        jitter_seconds = random.uniform(0, min(300, delay_seconds * 0.2))
        user["next_proactive_at"] = now + delay_seconds + jitter_seconds
        user["proactive_sending"] = False
        user["proactive_sending_started_at"] = 0
        self._mark_planned_candidate_status(user, "accepted", note)

    def _photo_text_available(self, user: dict[str, Any] | None = None) -> bool:
        if not self.enable_photo_text_action:
            return False
        if self._daily_token_soft_limit_should_defer("photo_prompt"):
            return False
        if self.photo_generation_backend == "comfyui":
            if not self._comfyui_photo_available():
                return False
            if self._local_photo_generation_busy_state():
                return False
        elif self.photo_generation_backend == "sdgen":
            if not self._sdgen_photo_available():
                return False
            if self._local_photo_generation_busy_state():
                return False
        elif self.photo_generation_backend == "external":
            if not self._external_photo_available():
                return False
        else:
            comfyui_available = self._comfyui_photo_available() and not self._local_photo_generation_busy_state()
            sdgen_available = self._sdgen_photo_available() and not self._local_photo_generation_busy_state()
            if not (comfyui_available or sdgen_available or self._external_photo_available()):
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
            if part == "jm_cosmos_read" and not self._jm_cosmos_read_available(user):
                return False
            if part.startswith("external:") and not self._external_ability_enabled(part.split(":", 1)[1]):
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
        for ability in self._available_external_proactive_abilities(user):
            ability_name = str(ability.get("name") or "")
            if not ability_name:
                continue
            probability = max(0.0, min(1.0, _safe_float(ability.get("share_probability"), 0.0)))
            if probability <= 0:
                continue
            when_text = " ".join(str(ability.get(key) or "") for key in ("when", "use_for", "description"))
            weight = max(0.02, probability) * 0.9
            if reason in {"activity_share", "diary_share", "background_schedule", "state_share", "quiet_care"}:
                weight += probability * 0.35
            if motive and any(token and token in motive for token in re.split(r"[\s,，、/]+", when_text)[:16]):
                weight += probability * 0.25
            weighted.append((f"external:{ability_name}", weight))

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
                        f"共同群 {group_id} 里有点闹腾,{speaker} 那句“{text}”还挺扎眼,但只想很轻地跟你提一下"
                    )
                return self._normalize_internal_motive_text(f"共同群 {group_id} 里有点闹腾,只想很轻地跟你提一下")
            if text:
                return self._normalize_internal_motive_text(
                    f"共同群 {group_id} 里有个小转折,{speaker} 那句“{text}”还留着点余味,想顺手给你递一下"
                )
            return self._normalize_internal_motive_text("共同群里有个小片段还有点余味,想顺手给你递一下")
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
            "news_share": [(8 * 60, 23 * 60)],
            "web_exploration_share": [(9 * 60, 23 * 60)],
            "jm_cosmos_recommendation_request": [(10 * 60, 23 * 60)],
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
        if reason == "news_share":
            news_context = self._format_news_action_context(user)
            raw_action_context = "\n".join(part for part in (raw_action_context, news_context) if part).strip()
        if reason == "web_exploration_share":
            exploration_context = self._format_web_exploration_action_context(user)
            raw_action_context = "\n".join(part for part in (raw_action_context, exploration_context) if part).strip()
        if reason == "jm_cosmos_share":
            jm_context = self._format_jm_cosmos_action_context(user)
            raw_action_context = "\n".join(part for part in (raw_action_context, jm_context) if part).strip()
        if reason == "jm_cosmos_recommendation_request":
            ask_context = user.get("jm_cosmos_recommendation_context") if isinstance(user.get("jm_cosmos_recommendation_context"), dict) else {}
            ask_text = _single_line(ask_context.get("hint"), 160) or "想向用户问有没有好看的本子或漫画推荐。"
            raw_action_context = "\n".join(part for part in (raw_action_context, f"夹层阅读推荐征求：{ask_text}") if part).strip()
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

