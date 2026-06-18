# -*- coding: utf-8 -*-
"""
GroupObservationMixin — 从 main.py 重新拆分出的群聊观察
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

class GroupObservationMixin:
    """群聊观察"""

    def _update_group_observation(
        self,
        group: dict[str, Any],
        *,
        sender_id: str,
        sender_name: str,
        text: str,
        group_id: str = "",
        scene: dict[str, Any] | None = None,
        message_id: str = "",
    ) -> None:
        cleaned = _single_line(text, 260)
        if not cleaned:
            return
        now = _now_ts()
        group["group_id"] = str(group_id or group.get("group_id") or group.get("id") or "")
        group["last_seen"] = now
        group["message_count"] = _safe_int(group.get("message_count"), 0, 0) + 1

        recent = group.setdefault("recent_messages", [])
        if not isinstance(recent, list):
            recent = []
            group["recent_messages"] = recent
        record = {
            "ts": now,
            "sender_id": sender_id,
            "name": _single_line(sender_name, 30) or sender_id,
            "identity_name": self._group_member_identity_name(sender_id, sender_name, limit=30),
            "identity_known": bool(self._worldbook_profile_by_user_id(sender_id)),
            "text": cleaned,
            "message_id": _single_line(message_id, 120),
        }
        if isinstance(scene, dict):
            record.update({
                "talking_to": _single_line(scene.get("talking_to"), 40) or "group",
                "talking_to_name": _single_line(scene.get("talking_to_name"), 80),
                "scene_trigger": _single_line(scene.get("trigger"), 40),
                "scene_reason": _single_line(scene.get("reason"), 60),
                "wakeup_word": _single_line(scene.get("wakeup_word"), 60),
                "wakeup_strength": _single_line(scene.get("wakeup_strength"), 24),
                "wakeup_strength_label": _single_line(scene.get("wakeup_strength_label"), 24),
                "wakeup_instruction": _single_line(scene.get("wakeup_instruction"), 180),
                "wakeup_topic_weight": scene.get("wakeup_topic_weight") if isinstance(scene.get("wakeup_topic_weight"), dict) else {},
                "reply_to_id": _single_line(scene.get("reply_to_id"), 40),
                "at_targets": scene.get("at_targets") if isinstance(scene.get("at_targets"), list) else [],
            })
        recent.append(record)
        del recent[:-self.max_group_recent_messages]
        self._record_user_recent_group_message_from_observation(
            group_id=str(group_id or group.get("group_id") or ""),
            sender_id=sender_id,
            sender_name=sender_name,
            text=cleaned,
            scene=scene,
            message_id=message_id,
            ts=now,
        )

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
            display_name = _single_line(sender_name, 30) or sender_id
            previous_display_name = _single_line(member.get("name"), 30)
            if previous_display_name and display_name and previous_display_name != display_name:
                events = member.setdefault("display_name_events", [])
                if not isinstance(events, list):
                    events = []
                    member["display_name_events"] = events
                last = events[-1] if events and isinstance(events[-1], dict) else {}
                if not (
                    _single_line(last.get("old"), 30) == previous_display_name
                    and _single_line(last.get("new"), 30) == display_name
                    and now - _safe_float(last.get("ts"), 0) < 3600
                ):
                    events.append({"ts": now, "old": previous_display_name, "new": display_name})
                    del events[:-12]
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
            self._maybe_add_worldbook_pending_observation(
                sender_id=sender_id,
                sender_name=sender_name,
                group_id=str(group.get("group_id") or group.get("id") or ""),
                text=cleaned,
                now=now,
            )

        if self.enable_group_slang_learning:
            self._learn_group_nickname_correction(group, cleaned)
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
            item for item in recent[-60:]
            if isinstance(item, dict) and now - _safe_float(item.get("ts"), 0) <= 75 * 60
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
        active_speakers = len({str(item.get("sender_id") or "") for item in window if item.get("sender_id")})
        topic_threads = group.get("topic_threads") if isinstance(group.get("topic_threads"), list) else []
        active_threads = [
            item for item in topic_threads
            if isinstance(item, dict)
            and now - _safe_float(item.get("last_ts"), 0) <= 75 * 60
            and _safe_int(item.get("message_count"), 0, 0) >= 3
        ]
        best_thread = None
        if active_threads:
            best_thread = max(
                active_threads,
                key=lambda item: (
                    _safe_int(item.get("message_count"), 0, 0)
                    + min(4, len(item.get("participants") if isinstance(item.get("participants"), list) else []))
                    + sum(
                        1
                        for example in (item.get("recent_examples") if isinstance(item.get("recent_examples"), list) else [])
                        if any(marker in str((example or {}).get("text") or "") for marker in funny_markers + share_markers)
                    ),
                    _safe_float(item.get("last_ts"), 0),
                ),
            )
            score += min(5, _safe_int(best_thread.get("message_count"), 0, 0) // 2)
            participants = best_thread.get("participants") if isinstance(best_thread.get("participants"), list) else []
            if len(participants) >= 2:
                score += 2
        if active_speakers >= 4:
            score += 1
        if active_speakers < 2:
            return None
        if score < 6:
            return None
        examples = best_thread.get("recent_examples") if isinstance(best_thread, dict) and isinstance(best_thread.get("recent_examples"), list) else []
        candidate_lines = examples[-6:] if examples else window[-8:]
        chosen = max(
            candidate_lines,
            key=lambda item: (
                sum(1 for marker in funny_markers + share_markers if marker in str(item.get("text") or "")),
                _safe_float(item.get("ts"), 0),
            ),
        )
        speaker_id = str(chosen.get("sender_id") or "")
        speaker = self._group_member_identity_label(speaker_id, chosen.get("identity_name") or chosen.get("name"), limit=24)
        text = _single_line(chosen.get("text"), 100)
        if not text:
            return None
        topic_title = _single_line(best_thread.get("title"), 60) if isinstance(best_thread, dict) else ""
        topic = self._soften_topic_hook(topic_title or text) or "群里刚刚那段话题"
        summary_items = []
        for item in candidate_lines[-6:]:
            if not isinstance(item, dict):
                continue
            name = self._group_member_identity_label(
                str(item.get("sender_id") or ""),
                item.get("identity_name") or item.get("name"),
                limit=16,
            )
            line = _single_line(item.get("text"), 56)
            if line:
                summary_items.append(f"{name}: {line}")
        participant_ids = []
        if isinstance(best_thread, dict) and isinstance(best_thread.get("participants"), list):
            participant_ids = [str(item) for item in best_thread.get("participants", []) if str(item)]
        if not participant_ids:
            participant_ids = list(dict.fromkeys(str(item.get("sender_id") or "") for item in window if isinstance(item, dict) and item.get("sender_id")))[:8]
        participant_names = []
        members = group.get("members") if isinstance(group.get("members"), dict) else {}
        for participant_id in participant_ids[:8]:
            member = members.get(participant_id) if isinstance(members, dict) else None
            name_hint = member.get("identity_name") or member.get("name") if isinstance(member, dict) else participant_id
            participant_names.append(self._group_member_identity_label(participant_id, name_hint, limit=16))
        duration_minutes = max(1, int((max(_safe_float(item.get("ts"), now) for item in window if isinstance(item, dict)) - min(_safe_float(item.get("ts"), now) for item in window if isinstance(item, dict))) / 60))
        topic_summary = (
            f"这不是单独一句话,而是群里约 {duration_minutes} 分钟里围绕“{topic}”滚起来的一段话题；"
            f"参与者约 {len(participant_names) or active_speakers} 人"
            + (f"（{ '、'.join(participant_names[:5])}）" if participant_names else "")
            + f", 中间最适合转述的点是：{text}"
        )
        return {
            "group_id": str(group_id),
            "kind": "funny",
            "speaker_id": speaker_id,
            "speaker": speaker,
            "topic": topic,
            "text": text,
            "summary": " / ".join(summary_items[-5:]),
            "topic_summary": _single_line(topic_summary, 260),
            "participants": participant_names[:8],
            "window_minutes": duration_minutes,
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
        speaker = self._group_member_identity_label(speaker_id, chosen.get("identity_name") or chosen.get("name"), limit=24)
        text = _single_line(chosen.get("text"), 100)
        summary_items = []
        for item in window[-5:]:
            if not isinstance(item, dict):
                continue
            name = self._group_member_identity_label(
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
            if not self._friend_can_receive_proactive_reason(user, "group_share", "message"):
                continue
            target_id = str(user_id)
            if target_id == str(trigger_sender_id or ""):
                continue
            member = members.get(target_id) if isinstance(members, dict) else None
            member_last_seen = _safe_float((member or {}).get("last_seen"), 0) if isinstance(member, dict) else 0
            if member_last_seen <= 0 or now - member_last_seen < 8 * 3600:
                continue
            cooldown_key = f"group_share:{_today_key()}"
            last_key = str(user.get("last_group_share_key") or "")
            last_at = _safe_float(user.get("last_group_share_at"), 0)
            if last_key == cooldown_key or now - last_at < 18 * 3600:
                continue
            if _safe_float(user.get("next_proactive_at"), 0) > 0 and str(user.get("planned_proactive_source") or "") == "timer":
                continue
            kind = _single_line(candidate.get("kind"), 32) or "funny"
            score = _safe_int(candidate.get("score"), 0, 0)
            chance = (
                min(0.48, 0.20 + score * 0.025)
                if kind == "bot_harassment"
                else min(0.26, 0.06 + score * 0.025)
            )
            if random.random() > chance:
                continue
            delay_minutes = random.randint(18, 45) if kind == "bot_harassment" else random.randint(45, 120)
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
                "topic_summary": _single_line(candidate.get("topic_summary"), 260),
                "participants": candidate.get("participants") if isinstance(candidate.get("participants"), list) else [],
                "window_minutes": _safe_int(candidate.get("window_minutes"), 0, 0),
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
        self._cleanup_group_slang_terms(group)
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
            if self._looks_like_group_member_name(group, token):
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

    def _learn_group_nickname_correction(self, group: dict[str, Any], text: str) -> None:
        cleaned = _single_line(text, 180)
        if not cleaned:
            return
        cleaned = re.sub(r"\[CQ:at,qq=\d+(?:,[^\]]*)?\]", "", cleaned)
        token = r"[\u4e00-\u9fffA-Za-z0-9_]{2,16}"
        updates: dict[str, dict[str, str]] = {}
        negatives: dict[str, list[str]] = {}

        for match in re.finditer(rf"(?P<nick>{token})(?:是|就是)(?P<owner>{token})(?:的)?(?:外号|昵称|别称)?", cleaned):
            nick = _single_line(match.group("nick"), 20)
            owner = _single_line(match.group("owner"), 20)
            if not nick or not owner or nick == owner:
                continue
            owner_label = self._group_member_identity_label_for_token(group, owner)
            if not owner_label:
                continue
            updates[nick] = {
                "meaning": f"{owner_label} 的外号/称呼",
                "usage": "称呼该群友时使用；身份以 QQ 锚点为准",
            }
            suffix = cleaned[match.end(): match.end() + 24]
            neg_match = re.match(rf"(?:不是|不等于|并不是)(?P<owner>{token})", suffix)
            if neg_match:
                negative_owner = _single_line(neg_match.group("owner"), 20)
                if negative_owner and negative_owner != owner:
                    negative_label = self._group_member_identity_label_for_token(group, negative_owner) or negative_owner
                    negatives.setdefault(nick, []).append(negative_label)

        for match in re.finditer(rf"(?P<owner>{token})(?:的)?(?:外号|昵称|别称)(?:是|叫)(?P<nick>{token})", cleaned):
            owner = _single_line(match.group("owner"), 20)
            nick = _single_line(match.group("nick"), 20)
            if not nick or not owner or nick == owner:
                continue
            owner_label = self._group_member_identity_label_for_token(group, owner)
            if not owner_label:
                continue
            updates[nick] = {
                "meaning": f"{owner_label} 的外号/称呼",
                "usage": "称呼该群友时使用；身份以 QQ 锚点为准",
            }

        for match in re.finditer(rf"(?P<nick>{token})(?:不是|不等于|并不是)(?P<owner>{token})", cleaned):
            nick = _single_line(match.group("nick"), 20)
            owner = _single_line(match.group("owner"), 20)
            if nick and owner and nick != owner:
                if nick not in updates and self._group_member_identity_label_for_token(group, nick):
                    continue
                owner_label = self._group_member_identity_label_for_token(group, owner) or owner
                negatives.setdefault(nick, []).append(owner_label)

        if not updates and not negatives:
            return
        meanings = group.setdefault("slang_meanings", {})
        if not isinstance(meanings, dict):
            meanings = {}
            group["slang_meanings"] = meanings
        now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
        for nick, payload in updates.items():
            existing = meanings.get(nick) if isinstance(meanings.get(nick), dict) else {}
            negative_values = list(negatives.get(nick) or [])
            existing_negative = existing.get("not_owner") if isinstance(existing, dict) else ""
            if existing_negative:
                negative_values.extend([item for item in re.split(r"[、,，;；]+", str(existing_negative)) if item])
            meanings[nick] = {
                "meaning": payload["meaning"],
                "usage": payload["usage"],
                "not_owner": "、".join(dict.fromkeys(negative_values)),
                "source": "explicit_correction",
                "evidence": cleaned,
                "updated_at": now_text,
            }
        for nick, negative_values in negatives.items():
            if nick in updates:
                continue
            existing = meanings.get(nick) if isinstance(meanings.get(nick), dict) else {}
            merged = []
            if isinstance(existing, dict) and existing.get("not_owner"):
                merged.extend([item for item in re.split(r"[、,，;；]+", str(existing.get("not_owner") or "")) if item])
            merged.extend(negative_values)
            meanings[nick] = {
                "meaning": _single_line(existing.get("meaning"), 90) if isinstance(existing, dict) else "外号归属被纠正，具体对象未确认",
                "usage": _single_line(existing.get("usage"), 90) if isinstance(existing, dict) else "遇到该称呼时不要猜归属",
                "not_owner": "、".join(dict.fromkeys(merged)),
                "source": "explicit_correction",
                "evidence": cleaned,
                "updated_at": now_text,
            }

    def _group_member_name_tokens(self, group: dict[str, Any]) -> set[str]:
        tokens: set[str] = set()

        def add(value: Any) -> None:
            text = _single_line(value, 40)
            if not text or text.isdigit():
                return
            tokens.add(text)
            compact = re.sub(r"\s+", "", text)
            if compact:
                tokens.add(compact)

        members = group.get("members") if isinstance(group.get("members"), dict) else {}
        for user_id, member in members.items():
            if not isinstance(member, dict):
                continue
            add(member.get("name"))
            add(member.get("identity_name"))
            add(member.get("display_name"))
            add(member.get("nickname"))
            add(member.get("card"))
            profile = self._worldbook_profile_by_user_id(str(user_id))
            if isinstance(profile, dict):
                add(profile.get("name"))
                for key in ("aliases", "observed_names"):
                    raw = profile.get(key)
                    if isinstance(raw, list):
                        for item in raw:
                            add(item)
        return tokens

    def _cleanup_group_slang_terms(self, group: dict[str, Any]) -> bool:
        terms = group.get("slang_terms")
        if not isinstance(terms, list):
            return False
        now = _now_ts()
        kept: list[Any] = []
        removed: set[str] = set()
        for item in terms:
            term = _single_line(item.get("term") if isinstance(item, dict) else item, 40)
            meanings = group.get("slang_meanings")
            meaning_item = meanings.get(term) if isinstance(meanings, dict) else None
            if isinstance(meaning_item, dict) and meaning_item.get("source") == "explicit_correction":
                kept.append(item)
                continue
            if isinstance(item, dict):
                count = _safe_int(item.get("count"), 0, 0)
                last_seen = _safe_float(item.get("last_seen"), 0)
                if last_seen > 0:
                    age_days = max(0.0, (now - last_seen) / 86400.0)
                    if age_days >= 21 and count <= 2:
                        removed.add(term)
                        continue
                    if age_days >= 45 and count <= 5:
                        removed.add(term)
                        continue
            if term and self._looks_like_group_member_name(group, term):
                removed.add(term)
                continue
            kept.append(item)
        if len(kept) == len(terms):
            return False
        group["slang_terms"] = kept
        meanings = group.get("slang_meanings")
        if isinstance(meanings, dict):
            for term in removed:
                meanings.pop(term, None)
        return True

    def _cleanup_group_members(self, group: dict[str, Any], *, now: float | None = None) -> bool:
        members = group.get("members")
        if not isinstance(members, dict):
            return False
        now = _now_ts() if now is None else now
        changed = False
        for user_id, member in list(members.items()):
            if not isinstance(member, dict):
                members.pop(user_id, None)
                changed = True
                continue
            last_seen = _safe_float(member.get("last_seen"), 0)
            if last_seen > 0 and now - last_seen > 90 * 86400 and _safe_int(member.get("count"), 0, 0) <= 2:
                members.pop(user_id, None)
                changed = True
                continue
            phrases = member.get("recent_phrases")
            if isinstance(phrases, list):
                deduped: list[str] = []
                for item in phrases:
                    text = _single_line(item, 40)
                    if text and text not in deduped:
                        deduped.append(text)
                if deduped != phrases:
                    member["recent_phrases"] = deduped[:8]
                    changed = True
        return changed

    def _cleanup_group_relationship_edges(self, group: dict[str, Any], *, now: float | None = None) -> bool:
        edges = group.get("relationship_edges")
        if not isinstance(edges, dict):
            return False
        now = _now_ts() if now is None else now
        changed = False
        for key, item in list(edges.items()):
            if not isinstance(item, dict):
                edges.pop(key, None)
                changed = True
                continue
            last_seen = _safe_float(item.get("last_seen") or item.get("updated_ts"), 0)
            weight = _safe_int(item.get("count"), 0, 0)
            if last_seen > 0 and now - last_seen > 60 * 86400 and weight <= 2:
                edges.pop(key, None)
                changed = True
        return changed

    def _cleanup_all_group_slang_terms(self) -> bool:
        groups = self.data.get("groups") if isinstance(getattr(self, "data", None), dict) else {}
        if not isinstance(groups, dict):
            return False
        changed = False
        for group in groups.values():
            if isinstance(group, dict) and self._cleanup_group_slang_terms(group):
                changed = True
        return changed

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
            a_name = self._group_member_identity_label(a_id, item.get("a_name"), limit=16) if a_id else (_single_line(item.get("a_name"), 16) or "群友A")
            b_name = self._group_member_identity_label(b_id, item.get("b_name"), limit=16) if b_id else (_single_line(item.get("b_name"), 16) or "群友B")
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
            not_owner = _single_line(item.get("not_owner"), 80)
            confidence = min(1.0, _safe_float(item.get("confidence"), 1.0, 0.0))
            if self._is_uncertain_group_slang_meaning(meaning, usage) or confidence < 0.55:
                continue
            if meaning:
                source = _single_line(item.get("source"), 30)
                lines.append(
                    f"- {term}：{meaning}"
                    + (f"｜不是：{not_owner}" if not_owner else "")
                    + (f"｜用法：{usage}" if usage else "")
                    + ("｜显式纠正" if source == "explicit_correction" else "")
                )
        return "\n".join(lines)

    def _is_uncertain_group_slang_meaning(self, meaning: str = "", usage: str = "") -> bool:
        text = _single_line(f"{meaning} {usage}", 180)
        if not text:
            return True
        uncertain_markers = (
            "语境不明", "上下文不明", "含义不明", "无法判断", "不能判断", "暂不确定",
            "不确定", "不清楚", "看不出", "未看出", "无法确定", "可能是", "大概是",
            "也许是", "疑似", "需要更多上下文", "需要结合上下文",
        )
        return any(marker in text for marker in uncertain_markers)

    def _prune_uncertain_group_slang_meanings(self, group: dict[str, Any]) -> int:
        meanings = group.get("slang_meanings")
        if not isinstance(meanings, dict):
            return 0
        removed = 0
        for term, item in list(meanings.items()):
            if not isinstance(item, dict):
                continue
            if item.get("source") == "explicit_correction":
                continue
            confidence = min(1.0, _safe_float(item.get("confidence"), 1.0, 0.0))
            if confidence < 0.55 or self._is_uncertain_group_slang_meaning(item.get("meaning"), item.get("usage")):
                meanings.pop(term, None)
                removed += 1
        return removed

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
                self._group_member_identity_label(str(participant), str(participant), limit=12)
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

    def _format_group_context_for_prompt(self, group: dict[str, Any], sender_id: str = "", text: str = "") -> str:
        atmosphere = group.get("atmosphere") if isinstance(group.get("atmosphere"), dict) else {}
        lines = [
            "【群聊观察层】",
            "这些是群聊上下文,只用于判断气氛、称呼、梗和是否该少说。不要暴露观察、画像、黑话学习或内部记录。",
            "身份防串规则：最近群聊中的方括号 QQ 是内部身份锚点；同名、相似外号或群名片变化都不能跨 QQ 合并。回复时不要主动说出 QQ 标签。",
            f"群气氛：{atmosphere.get('pace', '未知')}｜{atmosphere.get('mood', '平稳')}｜近段发言 {atmosphere.get('recent_count', 0)} 条｜活跃群友 {atmosphere.get('active_speakers', 0)} 人",
        ]
        intensity = self._group_high_intensity_state(group, mutate=False)
        if intensity.get("active"):
            lines.append(
                "当前群聊负载：高强度收口。短时间内 Bot 被频繁叫到；多条消息会被合并为同一轮处理。请集中回应共同重点,回复更短、更直接,不要逐条扩展。"
            )
        scene_text = self._format_group_scene_awareness_for_prompt(group, sender_id, text)
        if scene_text:
            lines.append(scene_text)
        recent = group.get("recent_messages")
        if isinstance(recent, list) and recent:
            msg_lines = []
            for item in recent[-8:]:
                if not isinstance(item, dict):
                    continue
                name = self._group_member_identity_label(
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
                display_name = _single_line(member.get("name"), 40)
                anchor_note = self._group_member_identity_anchor_note(sender_id, display_name, limit=120)
                rename_text = self._format_display_name_rename_events(member.get("display_name_events"), limit=3)
                lines.append(
                    f"当前发言者：{self._group_member_identity_label(sender_id, member.get('identity_name') or member.get('name'), limit=24)}"
                    f"｜发言样本 {member.get('count', 0)} 条"
                    + (f"｜近期短句：{phrase_text}" if phrase_text else "")
                    + (f"｜关系备注：{identity_note}" if identity_note else "")
                    + (f"｜互动边界：{boundary_note}" if boundary_note else "")
                    + (f"｜近期改名：{rename_text}" if rename_text else "")
                    + (f"｜{anchor_note}" if anchor_note else "")
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

    def _format_group_scene_awareness_for_prompt(self, group: dict[str, Any], sender_id: str = "", text: str = "") -> str:
        if not self.enable_group_scene_awareness:
            return ""
        recent = group.get("recent_messages") if isinstance(group.get("recent_messages"), list) else []
        current = None
        sender_id = str(sender_id or "").strip()
        cleaned = _single_line(text, 260)
        for item in reversed(recent):
            if not isinstance(item, dict):
                continue
            if sender_id and str(item.get("sender_id") or "") != sender_id:
                continue
            if cleaned and _single_line(item.get("text"), 260) != cleaned:
                continue
            current = item
            break
        if not isinstance(current, dict):
            current = recent[-1] if recent and isinstance(recent[-1], dict) else None
        if not isinstance(current, dict):
            return ""
        current_sender_id = str(current.get("sender_id") or "")
        current_display_name = _single_line(current.get("name"), 40)
        sender_name = self._group_member_identity_label(current_sender_id, current.get("identity_name") or current.get("name"), limit=40)
        anchor_note = self._group_member_identity_anchor_note(current_sender_id, current_display_name, limit=120)
        current_member = None
        members = group.get("members") if isinstance(group.get("members"), dict) else {}
        if current_sender_id and isinstance(members, dict):
            current_member = members.get(current_sender_id)
        rename_text = self._format_display_name_rename_events(
            current_member.get("display_name_events") if isinstance(current_member, dict) else None,
            limit=3,
        )
        scene = {
            "talking_to": current.get("talking_to") or "group",
            "talking_to_name": current.get("talking_to_name") or "",
            "trigger": current.get("scene_trigger") or "group_message",
            "reason": current.get("scene_reason") or "",
            "wakeup_instruction": current.get("wakeup_instruction") or "",
            "wakeup_word": current.get("wakeup_word") or "",
            "wakeup_strength_label": current.get("wakeup_strength_label") or "",
            "wakeup_topic_weight": current.get("wakeup_topic_weight") if isinstance(current.get("wakeup_topic_weight"), dict) else {},
        }
        lines = [
            "<conversation_scene>",
            f'  <trigger type="{_single_line(scene.get("trigger"), 40)}">{_single_line(scene.get("reason"), 80) or "group_message"}</trigger>',
            "  <current_message>",
            f"    <sender>{sender_name}</sender>",
            f"    <display_name>{current_display_name}</display_name>" if current_display_name else "",
            f"    <recent_rename>{rename_text}</recent_rename>" if rename_text else "",
            f"    <identity_note>{anchor_note}</identity_note>" if anchor_note else "",
            f"    <talking_to>{self._scene_talking_to_text(scene)}</talking_to>",
            f"    <content>{_single_line(current.get('text'), 100)}</content>",
            "  </current_message>",
            f"  <instruction>{self._scene_instruction_text(scene)}</instruction>",
        ]
        wakeup_instruction = _single_line(scene.get("wakeup_instruction"), 180)
        if wakeup_instruction:
            strength_label = _single_line(scene.get("wakeup_strength_label"), 24)
            attrs = f'word="{_single_line(scene.get("wakeup_word"), 40)}"'
            if strength_label:
                attrs += f' strength="{strength_label}"'
            lines.append(f"  <wakeup_note {attrs}>{wakeup_instruction}</wakeup_note>")
        topic_weight = scene.get("wakeup_topic_weight") if isinstance(scene.get("wakeup_topic_weight"), dict) else {}
        if str(scene.get("trigger") or "") == "group_wakeup_interest":
            reason = _single_line(topic_weight.get("reason"), 80)
            recent_texts = topic_weight.get("recent_texts") if isinstance(topic_weight.get("recent_texts"), list) else []
            topic_texts = topic_weight.get("topic_texts") if isinstance(topic_weight.get("topic_texts"), list) else []
            context_lines = [
                "  <interest_context>",
                f"    <focus>{_single_line(scene.get('wakeup_word'), 60)}</focus>",
            ]
            if reason:
                context_lines.append(f"    <why>{reason}</why>")
            samples = [
                _single_line(item, 90)
                for item in list(topic_texts)[-3:] + list(recent_texts)[-3:]
                if _single_line(item, 90)
            ]
            if samples:
                context_lines.append("    <topic_samples>")
                for sample in list(dict.fromkeys(samples))[:5]:
                    context_lines.append(f"      <s>{sample}</s>")
                context_lines.append("    </topic_samples>")
            context_lines.append("    <reply_rule>这是被当前话题勾起的轻接话；优先承接这些话题样本里的内容,不要只抓最后一句玩梗或转成惩罚/禁言梗。</reply_rule>")
            context_lines.append("  </interest_context>")
            lines.extend(context_lines)
        flow_lines: list[str] = []
        for item in recent[-max(2, self.group_scene_recent_limit):]:
            if not isinstance(item, dict):
                continue
            name = self._group_member_identity_label(str(item.get("sender_id") or ""), item.get("identity_name") or item.get("name"), limit=24)
            item_scene = {
                "talking_to": item.get("talking_to") or "group",
                "talking_to_name": item.get("talking_to_name") or "",
            }
            flow_lines.append(
                f"    <m>{name} → {self._scene_talking_to_text(item_scene)}: {_single_line(item.get('text'), 40)}</m>"
            )
        if flow_lines:
            lines.append("  <recent_flow>")
            lines.extend(flow_lines)
            lines.append("  </recent_flow>")
        participants = []
        for item in recent[-12:]:
            if not isinstance(item, dict):
                continue
            name = self._group_member_identity_label(str(item.get("sender_id") or ""), item.get("identity_name") or item.get("name"), limit=20)
            if name and name not in participants:
                participants.append(name)
        if len(participants) > 1:
            lines.append(f"  <participants>{'、'.join(participants[:6])}</participants>")
        lines.append("</conversation_scene>")
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

    def _clean_group_interjection_reply(self, value: Any) -> str:
        text = _single_line(value, 80)
        text = re.sub(r"^```(?:text)?|```$", "", text).strip()
        text = text.strip("\"'“”‘’` ")
        if not text or text in {"空字符串", "不适合说话", "不说", "不回复", "无"}:
            return ""
        if re.fullmatch(r"[.。…~～\s\"'“”‘’`-]{1,12}", text):
            return ""
        return text

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
        recent = group.get("recent_messages") if isinstance(group.get("recent_messages"), list) else []
        current = recent[-1] if recent and isinstance(recent[-1], dict) else {}
        talking_to = str(current.get("talking_to") or "group") if isinstance(current, dict) else "group"
        if talking_to not in {"", "group", "bot"}:
            return False, "当前更像群友之间的一对一对话"
        if re.search(r"^\s*(?:@|回复|引用)", text):
            return False, "当前消息有明确对话对象"
        if re.search(r"(别插|别接|别吵|别回|闭嘴|别打断)", text):
            return False, "群友表达了不希望被打断"
        atmosphere = group.get("atmosphere") if isinstance(group.get("atmosphere"), dict) else {}
        mood = str(atmosphere.get("mood") or "")
        pace = str(atmosphere.get("pace") or "")
        if pace == "热闹" and mood not in {"玩笑", "求助"}:
            return False, "群聊太热闹,不抢话"
        if re.search(r"(有没有人|谁懂|救命|怎么回事|咋办)", text):
            return random.random() < 0.055, "有开放式接话口"
        if re.search(r"(笑死|绷不住|太离谱)", text):
            return random.random() < (0.018 if mood == "玩笑" else 0.008), "玩笑反应口"
        if mood == "玩笑":
            return random.random() < 0.015, "玩笑气氛"
        if mood == "求助":
            return random.random() < 0.035, "求助气氛"
        return False, "没有自然插话口"

    def _group_repeat_signature(self, text: str) -> str:
        cleaned = self._compact_repeat_text(text)
        cleaned = re.sub(r"[!！?？。.,，~～…]+$", "", cleaned).strip()
        return cleaned

    def _format_group_share_action_context(self, user: dict[str, Any]) -> str:
        share = user.get("group_share_context")
        if not isinstance(share, dict):
            return ""
        if _now_ts() - _safe_float(share.get("created_ts"), 0) > 3 * 3600:
            return ""
        group_id = _single_line(share.get("group_id"), 24)
        speaker = _single_line(share.get("speaker"), 64) or "群友"
        text = _single_line(share.get("text"), 120)
        summary = _single_line(share.get("summary"), 220)
        topic_summary = _single_line(share.get("topic_summary"), 260)
        topic = _single_line(share.get("topic"), 60)
        participants = share.get("participants") if isinstance(share.get("participants"), list) else []
        participant_text = "、".join(_single_line(item, 64) for item in participants[:6] if _single_line(item, 64))
        window_minutes = _safe_int(share.get("window_minutes"), 0, 0)
        parts = [
            f"群聊分享线索：群 {group_id}" if group_id else "群聊分享线索",
            f"时间窗：最近约 {window_minutes} 分钟的一段群聊" if window_minutes else "",
            f"参与者：{participant_text}" if participant_text else "",
            "身份锚点：[QQ:...] 只用于内部区分群友,不要写进最终私聊消息。" if participant_text or speaker else "",
            f"这段话题发生了什么：{topic_summary}" if topic_summary else "",
            f"代表性片段：{speaker}: {text}" if text else "",
            f"话题推进样本：{summary}" if summary else "",
            f"话题钩子：{topic}" if topic else "",
        ]
        return "\n".join(part for part in parts if part)

    def _group_share_send_block_reason(self, user_id: str, user: dict[str, Any], *, now: float | None = None) -> str:
        if str(user.get("planned_proactive_reason") or "") != "group_share":
            return ""
        share = user.get("group_share_context")
        if not isinstance(share, dict):
            return "群聊分享上下文已失效"
        check_now = _now_ts() if now is None else now
        created_ts = _safe_float(share.get("created_ts"), 0)
        if created_ts <= 0 or check_now - created_ts > 3 * 3600:
            return "群聊分享候选已过期"
        group_id = _single_line(share.get("group_id"), 40)
        if not group_id:
            return "群聊分享缺少群号"
        groups = self.data.get("groups")
        group = groups.get(group_id) if isinstance(groups, dict) else None
        if not isinstance(group, dict):
            return "群聊记录不存在"
        members = group.get("members") if isinstance(group.get("members"), dict) else {}
        member = members.get(str(user_id)) if isinstance(members, dict) else None
        member_last_seen = _safe_float((member or {}).get("last_seen"), 0) if isinstance(member, dict) else 0
        if member_last_seen > created_ts:
            return f"用户已在群 {group_id} 重新发言（{self._format_elapsed(check_now - member_last_seen)}前）"
        if member_last_seen > 0 and check_now - member_last_seen < 8 * 3600:
            return f"用户距上次群发言不足 8 小时（{self._format_elapsed(check_now - member_last_seen)}前）"
        return ""

    def _format_group_wakeup_humanized_prompt(self, effect: dict[str, Any] | None, state: dict[str, Any] | None = None) -> str:
        if not isinstance(effect, dict) or not effect:
            return ""
        state = state if isinstance(state, dict) else self.data.get("daily_state", {})
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        mood = _single_line(state.get("mood_bias"), 40) if isinstance(state, dict) else "平稳"
        runtime = state.get("sleep_runtime") if isinstance(state, dict) and isinstance(state.get("sleep_runtime"), dict) else {}
        phase = _single_line(runtime.get("label") or runtime.get("phase"), 40)
        updates = effect.get("updates") if isinstance(effect.get("updates"), list) else []
        update_text = "；".join(_single_line(item, 60) for item in updates if _single_line(item, 60))
        strength_label = _single_line(effect.get("strength_label"), 24)
        fatigue = effect.get("fatigue") if isinstance(effect.get("fatigue"), dict) else {}
        fatigue_label = _single_line(fatigue.get("label"), 20)
        fatigue_line = f"唤醒疲劳：{fatigue_label}（{_safe_float(fatigue.get('value'), 0.0, 0.0):.1f}/{_safe_int(fatigue.get('limit'), 0, 0)}）\n" if fatigue_label else ""
        return (
            "【群聊唤醒与当前状态】\n"
            f"当前状态：能量 {energy}/100｜情绪底色 {mood}" + (f"｜睡眠阶段 {phase}" if phase else "") + "\n"
            + (f"唤醒强度：{strength_label}\n" if strength_label else "")
            + fatigue_line
            + f"唤醒影响：{_single_line(effect.get('note'), 220)}\n"
            + (f"状态变化：{update_text}\n" if update_text else "")
            + "回复要求：把这当作真实状态反应来写,不要说关键词、概率、插件、触发规则；在群聊里短一点,像被自然叫到或被话题吸引。"
        )


    def _maybe_add_worldbook_pending_observation(
        self,
        *,
        sender_id: str,
        sender_name: str,
        group_id: str,
        text: str,
        now: float | None = None,
    ) -> None:
        if not (
            self.enable_worldbook_member_recognition
            and self.enable_group_member_profiles
            and getattr(self, "worldbook_auto_pending_observations", True)
        ):
            return
        user_id = str(sender_id or "").strip()
        if not user_id:
            return
        profiles = self.data.get("worldbook_member_profiles")
        if not isinstance(profiles, dict):
            return
        profile = profiles.get(user_id)
        if not isinstance(profile, dict) or profile.get("enabled", True) is False:
            return
        signal = self._worldbook_pending_observation_signal(text)
        if not signal:
            return
        cleaned = signal["evidence"]
        now = now or _now_ts()
        last_at = _safe_float(profile.get("last_pending_observation_at"), 0)
        if last_at and now - last_at < 12 * 3600:
            return
        pending = profile.setdefault("pending_observations", [])
        if not isinstance(pending, list):
            pending = []
            profile["pending_observations"] = pending
        evidence = cleaned
        evidence_key = self._worldbook_pending_observation_key(evidence)
        for item in pending:
            if not isinstance(item, dict):
                continue
            existing_key = self._worldbook_pending_observation_key(item.get("evidence") or item.get("content"))
            if existing_key and (existing_key == evidence_key or existing_key in evidence_key or evidence_key in existing_key):
                item["count"] = _safe_int(item.get("count"), 1, 1) + 1
                item["updated_at"] = now
                profile["last_pending_observation_at"] = now
                return
        identity_name = _single_line(profile.get("name") or sender_name or user_id, 40)
        pending.insert(
            0,
            {
                "id": uuid.uuid4().hex[:12],
                "title": signal["title"],
                "content": f"{identity_name} 在群聊中提到或表现出：{evidence}",
                "evidence": evidence,
                "group_id": _single_line(group_id, 40),
                "source": "group_observation",
                "weight": signal["weight"],
                "count": 1,
                "created_at": now,
                "updated_at": now,
            },
        )
        del pending[5:]
        profile["last_pending_observation_at"] = now

    def _worldbook_pending_observation_signal(self, text: str) -> dict[str, Any] | None:
        cleaned = _single_line(text, 140)
        if not (6 <= len(cleaned) <= 100):
            return None
        if cleaned.startswith(("/", "!", "！", "#")) or re.fullmatch(r"[\W_]+", cleaned):
            return None
        if re.search(r"(https?://|www\.|BV[0-9A-Za-z]{8,}|av\d{4,}|\[图片\]|\[语音\]|\[转发消息\])", cleaned, re.I):
            return None
        if re.search(r"(我是|你可以叫我|我是你|你爹|你爸|我是.*主人)", cleaned):
            return None
        if re.search(r"(?<!不要)(?<!别)(?<!不准)叫我", cleaned):
            return None
        if re.search(r"(胖次|内裤|脱下来|给你看|生理需求|起飞|开导|涩涩|色色)", cleaned):
            return None
        if re.fullmatch(r"(今天的?|明天的?|昨天的?|解决了|怎么做呢|好+|嗯+|啊+|草+|笑死|笨蛋|入土|入机)", cleaned):
            return None
        if re.search(r"[?？]$", cleaned) and re.search(r"(你|他|她|它|大家|有人|谁|什么|怎么|为啥|为什么)", cleaned):
            return None

        strong_patterns: tuple[tuple[str, int, str], ...] = (
            ("偏好/厌恶", 50, r"(喜欢|爱吃|爱看|爱玩|推|厨|不喜欢|讨厌|反感|雷|雷点|受不了|不能接受|不吃|过敏)"),
            ("互动边界", 55, r"(不要叫|别叫|不要提|别提|不想聊|不接受|介意|边界|底线|触雷|会破防)"),
            ("长期习惯", 45, r"(习惯|总是|经常|一直|长期|每天|常常|固定|作息|失眠|熬夜|早睡|晚睡)"),
            ("近期计划", 42, r"(最近在|正在|准备|打算|计划|以后想|想要|要开始|在学|学.*中|练.*中|项目|稿子|作业|考试|上课|上班|下班)"),
            ("重要状态", 45, r"(压力很大|压力大|焦虑|难过|生气|开心|累死|很累|困死|生病|发烧|住院|搬家|入职|离职|毕业)"),
        )
        for title, weight, pattern in strong_patterns:
            if re.search(pattern, cleaned):
                if re.search(r"^(今天|明天|昨天)[，,。 ]*(还行|一般|没啥|没事|解决了)?$", cleaned):
                    return None
                return {"title": title, "weight": weight, "evidence": cleaned}
        return None

    @staticmethod
    def _worldbook_pending_observation_key(value: Any) -> str:
        text = _single_line(value, 120).lower()
        text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text)
        return text[:80]

    def _looks_like_group_member_name(self, group: dict[str, Any], token: str) -> bool:
        token = _single_line(token, 40)
        if not token:
            return False
        normalized = re.sub(r"\s+", "", token)
        name_tokens = self._group_member_name_tokens(group)
        if token in name_tokens or normalized in name_tokens:
            return True
        if len(normalized) >= 3:
            for name in name_tokens:
                compact_name = re.sub(r"\s+", "", name)
                if compact_name and (normalized == compact_name or normalized in compact_name or compact_name in normalized):
                    return True
        return False

    def _update_group_repeat_follow_state(self, group: dict[str, Any], text: str, sender_id: str = "") -> dict[str, str]:
        if not self.enable_group_repeat_follow:
            return {}
        cleaned = _single_line(text, 80)
        signature = self._group_repeat_signature(cleaned)
        if len(signature) < 1 or len(signature) > 30:
            group["repeat_follow_state"] = {}
            return {}
        now = _now_ts()
        sender_key = _single_line(sender_id, 64) or "unknown"
        count_distinct_users = bool(getattr(self, "group_repeat_count_distinct_users_only", False))
        state = group.get("repeat_follow_state")
        if not isinstance(state, dict):
            state = {}
        if signature and signature == str(state.get("signature") or "") and now - _safe_float(state.get("last_ts"), 0) <= 120:
            senders = state.get("senders") if isinstance(state.get("senders"), list) else []
            sender_is_new = sender_key not in senders
            if sender_is_new:
                senders.append(sender_key)
            state["senders"] = senders[-20:]
            state["count"] = _safe_int(state.get("count"), 1, 1) + 1
            state["distinct_count"] = len(set(state["senders"]))
            state["last_sender_id"] = sender_key
            state["last_ts"] = now
            state["text"] = cleaned
        else:
            state = {
                "signature": signature,
                "text": cleaned,
                "count": 1,
                "distinct_count": 1,
                "senders": [sender_key],
                "last_sender_id": sender_key,
                "first_ts": now,
                "last_ts": now,
                "acted": False,
                "follow_probability": max(0.0, self.group_repeat_follow_probability),
                "interrupt_probability": max(0.0, self.group_repeat_interrupt_probability),
            }
            sender_is_new = True
        group["repeat_follow_state"] = state
        count = _safe_int(state.get("distinct_count" if count_distinct_users else "count"), 1, 1)
        trigger_threshold = max(3, _safe_int(getattr(self, "group_repeat_trigger_threshold", 4), 4, 3))
        if count < trigger_threshold or bool(state.get("acted")) or bool(state.get("followed")):
            return {}
        today = _today_key()
        if group.get("interject_day") != today:
            group["interject_day"] = today
            group["interject_today"] = 0
        if self.group_interject_max_daily <= 0:
            return {}
        if _safe_int(group.get("interject_today"), 0, 0) >= self.group_interject_max_daily:
            return {}
        follow_probability = min(0.85, _safe_float(state.get("follow_probability"), self.group_repeat_follow_probability))
        interrupt_probability = min(0.85, _safe_float(state.get("interrupt_probability"), self.group_repeat_interrupt_probability))
        total_probability = min(0.95, follow_probability + interrupt_probability)
        roll = random.random()
        if roll >= total_probability:
            if count_distinct_users and not sender_is_new:
                return {}
            step = max(0.0, self.group_repeat_interrupt_probability_step)
            state["follow_probability"] = min(0.85, follow_probability + step)
            state["interrupt_probability"] = min(0.85, interrupt_probability + step)
            return {}
        state["acted"] = True
        state["acted_ts"] = now
        action = "interrupt" if roll < interrupt_probability else "follow"
        if action == "interrupt":
            image_path = str(self.group_repeat_interrupt_image_path or "").strip()
            if image_path and not os.path.exists(image_path):
                image_path = ""
            text_reply = _single_line(self.group_repeat_interrupt_text, 80) or "禁止复读"
            return {"action": "interrupt", "text": "" if image_path else text_reply, "image_path": image_path}
        return {"action": "follow", "text": cleaned, "image_path": ""}

    async def _maybe_group_interject(self, event: AstrMessageEvent, group: dict[str, Any], text: str) -> None:
        try:
            sender_id = str(event.get_sender_id())
        except Exception:
            sender_id = ""
        repeat_action = self._update_group_repeat_follow_state(group, text, sender_id=sender_id)
        if repeat_action:
            repeat_reply = _single_line(repeat_action.get("text"), 80)
            image_path = str(repeat_action.get("image_path") or "")
            await self._reply_with_optional_media(event, repeat_reply, image_path=image_path, quote_message_id="")
            now = _now_ts()
            group["last_interject_at"] = now
            group["interject_today"] = _safe_int(group.get("interject_today"), 0, 0) + 1
            group["last_bot_interjection"] = {
                "ts": now,
                "text": repeat_reply,
                "reason": "群聊复读打断" if repeat_action.get("action") == "interrupt" else "群聊复读跟读",
                "has_image": bool(image_path),
                "topic_signature": self._group_topic_signature(text),
            }
            return
        quote_message_id = self._event_message_id(event) if getattr(self, "enable_proactive_quote_trigger_message", False) else ""
        allowed, reason = self._group_interjection_allowed(group, text)
        if not allowed:
            return
        prompt = f"""
你在一个群聊里,系统认为现在也许可以非常轻地接一句,但你必须先判断这句会不会显得硬插话。
只输出要发到群里的正文,不要解释。

【群聊上下文】
{self._format_group_context_for_prompt(group)}

【刚刚触发的消息】
{_single_line(text, 180)}

要求：
- 如果这像群友之间的一对一、已经有人在自然接话、你这句没有新增价值,输出空字符串
- 宁可不说,不要为了存在感插话
- 1 句,最多 35 个中文字符
- 像群友自然接话,不要像助手
- 只顺着当前话题轻轻补一句,不要开新话题,不要把自己变成中心
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
        reply = self._clean_group_interjection_reply(generated)
        if not reply:
            return
        if self._response_review_flags(reply, {}):
            return
        if quote_message_id:
            await event.send(event.chain_result(self._with_optional_reply([Plain(reply)], quote_message_id)))
        else:
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
        async with self._data_lock:
            group = deepcopy(self._get_group(group_id))
        if now - _safe_float(group.get("last_episode_refresh_at"), 0) < self.group_episode_refresh_minutes * 60:
            return
        if now < _safe_float(group.get("group_episode_retry_after"), 0):
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
        acquired = await self._try_acquire_group_background_task(
            group_id,
            "group_episode",
            now,
            refresh_key="last_episode_refresh_at",
            refresh_seconds=self.group_episode_refresh_minutes * 60,
        )
        if not acquired:
            return
        try:
            raw = await self._llm_call(
                prompt,
                max_tokens=420,
                provider_id=self._task_provider(self.group_episode_provider_id, self.mai_style_provider_id),
                task="group_episode",
            )
            payload = self._extract_json_payload(raw or "")
        except Exception as exc:
            await self._mark_group_background_retry(group_id, "group_episode", now, exc)
            return
        if not isinstance(payload, dict):
            await self._mark_group_background_retry(group_id, "group_episode", now, "invalid_json")
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
            await self._mark_group_background_retry(group_id, "group_episode", now, "empty_summary")
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
            current["group_episode_retry_after"] = 0
            current["group_episode_last_error"] = ""
            current["group_episode_running_at"] = 0
            self._save_data_sync()

    async def _maybe_refresh_group_slang_meanings(self, group_id: str, group: dict[str, Any]) -> None:
        if not self.enable_group_slang_meanings:
            return
        now = _now_ts()
        async with self._data_lock:
            group = deepcopy(self._get_group(group_id))
        if now - _safe_float(group.get("last_slang_summary_at"), 0) < self.group_slang_summary_minutes * 60:
            return
        if now < _safe_float(group.get("group_slang_retry_after"), 0):
            return
        slang = group.get("slang_terms")
        if not isinstance(slang, list) or len(slang) < 5:
            return
        if self._cleanup_group_slang_terms(group):
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
        web_evidence = await self._collect_group_slang_web_evidence(group_id, terms, examples)
        web_evidence_block = (
            "【联网参考】\n"
            "下面是可选外部搜索摘要。它只能作为辅助证据,不能覆盖群聊样例；只有外部解释与本群样例能对应时才可采纳。"
            "如果外部结果像百科、广告、无关网页、同词异义或无法匹配本群用法,请忽略。\n"
            f"{web_evidence}\n"
            if web_evidence
            else ""
        )
        prompt = f"""
请根据群聊样例,给这些群内常见词/梗做很短的语义解释。这是一个“黑话解释”专门任务。
只解释能从样例明确看出来的含义；证据不足、只是普通词、只是人名/群名片、只是口头语、含义不稳定时,直接不要输出这个词。
如果提供了联网参考,还要判断外部解释与本群样例的匹配程度；外部解释不匹配本群用法时必须以群聊样例为准。
不要写“语境不明”“可能是”“不确定”等模糊解释；低置信度宁可省略。
不要输出解释过程。

【候选词】
{", ".join(terms)}

【群聊样例】
{chr(10).join(examples[-60:])}

{web_evidence_block}

只输出 JSON,键为词,值为对象：
{{
  "某词": {{
    "meaning": "一句话含义,必须是从样例能看出的稳定含义",
    "usage": "什么时候用,不确定就不要输出该词",
    "type": "外号|事件代称|梗|口头禅|调侃|称赞|辱骂|其他",
    "confidence": 0.0到1.0的小数,
    "evidence": "最能说明含义的一条短样例",
    "web_match": 0.0到1.0的小数,没有联网参考或不匹配就填0,
    "web_evidence": "联网参考中最相关的一句,没有就空字符串"
  }}
}}

入库标准：只输出 confidence >= 0.65 的词。无法达到就省略。
""".strip()
        acquired = await self._try_acquire_group_background_task(
            group_id,
            "group_slang",
            now,
            refresh_key="last_slang_summary_at",
            refresh_seconds=self.group_slang_summary_minutes * 60,
        )
        if not acquired:
            return
        try:
            raw = await self._llm_call(
                prompt,
                max_tokens=560,
                provider_id=self._task_provider(self.group_slang_provider_id, self.mai_style_provider_id),
                task="group_slang",
            )
            payload = self._extract_json_payload(raw or "")
        except Exception as exc:
            await self._mark_group_background_retry(group_id, "group_slang", now, exc)
            return
        if not isinstance(payload, dict):
            await self._mark_group_background_retry(group_id, "group_slang", now, "invalid_json")
            return
        normalized: dict[str, dict[str, str]] = {}
        for term, value in payload.items():
            key = _single_line(term, 20)
            if not key:
                continue
            if isinstance(value, dict):
                meaning = _single_line(value.get("meaning"), 90)
                usage = _single_line(value.get("usage"), 90)
                slang_type = _single_line(value.get("type"), 24)
                evidence = _single_line(value.get("evidence"), 120)
                web_match = min(1.0, _safe_float(value.get("web_match"), 0.0, 0.0))
                web_hit = _single_line(value.get("web_evidence"), 140)
                confidence = min(1.0, _safe_float(value.get("confidence"), 0.0, 0.0))
            else:
                meaning = _single_line(value, 90)
                usage = ""
                slang_type = ""
                evidence = ""
                web_match = 0.0
                web_hit = ""
                confidence = 0.0
            if not meaning or confidence < 0.65 or self._is_uncertain_group_slang_meaning(meaning, usage):
                continue
            normalized[key] = {
                "meaning": meaning,
                "usage": usage,
                "type": slang_type,
                "confidence": f"{confidence:.2f}",
                "evidence": evidence,
                "web_match": f"{web_match:.2f}" if web_match > 0 else "",
                "web_evidence": web_hit,
                "source": "llm_slang",
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            }
        async with self._data_lock:
            current = self._get_group(group_id)
            removed_uncertain = self._prune_uncertain_group_slang_meanings(current)
            meanings = current.setdefault("slang_meanings", {})
            if not isinstance(meanings, dict):
                meanings = {}
                current["slang_meanings"] = meanings
            for term, payload in normalized.items():
                existing = meanings.get(term)
                if isinstance(existing, dict) and existing.get("source") == "explicit_correction":
                    continue
                meanings[term] = payload
            current["last_slang_summary_at"] = now
            current["group_slang_retry_after"] = 0
            current["group_slang_last_error"] = ""
            current["group_slang_running_at"] = 0
            if removed_uncertain:
                logger.info("[PrivateCompanion] 已清理低置信度群黑话释义: group=%s removed=%s", group_id, removed_uncertain)
            self._save_data_sync()

    async def _try_acquire_group_background_task(
        self,
        group_id: str,
        task: str,
        now: float,
        *,
        refresh_key: str,
        refresh_seconds: float,
    ) -> bool:
        retry_key = f"{task}_retry_after"
        running_key = f"{task}_running_at"
        async with self._data_lock:
            current = self._get_group(group_id)
            if now - _safe_float(current.get(refresh_key), 0) < max(0.0, float(refresh_seconds)):
                return False
            if now < _safe_float(current.get(retry_key), 0):
                return False
            running_at = _safe_float(current.get(running_key), 0)
            if running_at > 0 and now - running_at < 10 * 60:
                return False
            current[running_key] = now
            self._save_data_sync()
        return True

    async def _mark_group_background_retry(self, group_id: str, task: str, now: float, error: Any) -> None:
        retry_key = f"{task}_retry_after"
        error_key = f"{task}_last_error"
        running_key = f"{task}_running_at"
        delay = 10 * 60
        if task == "group_episode":
            delay = min(max(10 * 60, _safe_int(getattr(self, "group_episode_refresh_minutes", 60), 60, 1) * 60), 30 * 60)
        elif task == "group_slang":
            delay = min(max(10 * 60, _safe_int(getattr(self, "group_slang_summary_minutes", 360), 360, 1) * 60), 30 * 60)
        async with self._data_lock:
            current = self._get_group(group_id)
            current[retry_key] = now + delay
            current[error_key] = _single_line(error, 180)
            current[running_key] = 0
            self._save_data_sync()
        logger.warning(
            "[PrivateCompanion] 群聊后台整理失败,已进入短冷却避免重复请求: group=%s task=%s retry=%ss error=%s",
            group_id,
            task,
            int(delay),
            _single_line(error, 120),
        )

    async def _collect_group_slang_web_evidence(self, group_id: str, terms: list[str], examples: list[str]) -> str:
        if not bool(getattr(self, "enable_group_slang_web_search", False)):
            return ""
        picker = getattr(self, "_pick_available_web_search_umo", None)
        searcher = getattr(self, "_run_astrbot_web_search", None)
        if not callable(picker) or not callable(searcher):
            return ""
        search_umo = picker()
        if not search_umo:
            return ""
        term_limit = max(1, min(12, _safe_int(getattr(self, "group_slang_web_search_terms", 4), 4, 1, 12)))
        result_limit = max(1, min(5, _safe_int(getattr(self, "group_slang_web_search_results", 2), 2, 1, 5)))
        picked_terms: list[str] = []
        for term in terms:
            clean = _single_line(term, 20)
            if not clean or clean in picked_terms:
                continue
            if len(clean) <= 1:
                continue
            picked_terms.append(clean)
            if len(picked_terms) >= term_limit:
                break
        if not picked_terms:
            return ""
        lines: list[str] = []
        for term in picked_terms:
            query = f"{term} 网络用语 梗 黑话 含义"
            try:
                results = await searcher(query, umo=search_umo, topic="general")
            except Exception as exc:
                logger.debug("[PrivateCompanion] 群黑话联网参考搜索失败: group=%s term=%s err=%s", group_id, term, _single_line(exc, 120))
                continue
            hits = []
            for item in results[:result_limit]:
                if not isinstance(item, dict):
                    continue
                title = _single_line(item.get("title"), 80)
                snippet = _single_line(item.get("snippet"), 180)
                if not title and not snippet:
                    continue
                hits.append(f"- {title}: {snippet}".strip())
            if hits:
                lines.append(f"{term}:\n" + "\n".join(hits))
        if lines:
            logger.info("[PrivateCompanion] 群黑话联网参考已收集: group=%s terms=%s", group_id, len(lines))
        return "\n".join(lines)[:1800]

