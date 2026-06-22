# -*- coding: utf-8 -*-
"""
PrivateReadingMixin — 从 main.py 重新拆分出的私密阅读/书架
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

class PrivateReadingMixin:
    """私密阅读/书架"""

    def _jm_cosmos_plugin_dir(self) -> Path:
        candidates = [
            Path(__file__).resolve().parent.parent / "astrbot_plugin_jm_cosmos",
            Path(self.data_dir).parent.parent / "plugins" / "astrbot_plugin_jm_cosmos",
        ]
        for path in candidates:
            if (path / "main.py").exists():
                return path
        return candidates[0]

    def _jm_cosmos_available(self) -> bool:
        try:
            return (self._jm_cosmos_plugin_dir() / "main.py").exists()
        except Exception:
            return False

    def _find_jm_cosmos_instance(self) -> Any | None:
        for obj in gc.get_objects():
            try:
                cls = obj.__class__
                module = str(getattr(cls, "__module__", ""))
                if "astrbot_plugin_jm_cosmos" not in module:
                    continue
                if hasattr(obj, "browser") and callable(getattr(getattr(obj, "browser", None), "search_albums", None)):
                    return obj
            except Exception:
                continue
        return None

    def _jm_cosmos_read_available(self, user: dict[str, Any] | None = None) -> bool:
        if isinstance(user, dict) and self._private_user_role(user) == "friend":
            return False
        return bool(
            self.enable_jm_cosmos_integration
            and self.enable_jm_cosmos_boredom_read
            and self._jm_cosmos_available()
        )

    def _private_reading_recommendation_request_available(self, user: dict[str, Any] | None = None) -> bool:
        if isinstance(user, dict) and self._private_user_role(user) == "friend":
            return False
        return bool(
            self.enable_jm_cosmos_integration
            and self.enable_private_reading_ask_recommendation
            and self._jm_cosmos_available()
        )

    def _bot_currently_bored_enough_for_jm(self) -> bool:
        state = self.data.get("daily_state", {})
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        mood = _single_line(state.get("mood_bias") if isinstance(state, dict) else "", 24)
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        activity = _single_line((current_item or {}).get("activity"), 80)
        hour = datetime.now().hour
        text = f"{mood} {activity}"
        boredom_tokens = ("无聊", "发呆", "摸鱼", "休息", "闲", "空", "夜", "睡前", "偷懒", "刷")
        if any(token in text for token in boredom_tokens):
            return True
        if 23 <= hour or hour < 2:
            return random.random() < 0.42
        return 28 <= energy <= 68 and random.random() < 0.22

    def _jm_cosmos_keywords_for_user(self, user: dict[str, Any] | None = None) -> list[str]:
        raw = str(self.jm_cosmos_default_keywords or "纯爱,恋爱,同人")
        liked_candidates: list[str] = []
        base_candidates: list[str] = []
        memory_candidates: list[str] = []
        state = self.data.get("jm_cosmos_integration") if isinstance(self.data.get("jm_cosmos_integration"), dict) else {}
        profile = state.get("preference_profile") if isinstance(state.get("preference_profile"), dict) else {}
        liked = profile.get("liked_terms") if isinstance(profile.get("liked_terms"), list) else []
        for item in liked[:8]:
            text = _single_line(item.get("term") if isinstance(item, dict) else item, 16)
            if text:
                liked_candidates.append(text)
        base_candidates.extend(part.strip() for part in re.split(r"[,，、\n]+", raw) if part.strip())
        if isinstance(user, dict):
            memory = user.get("companion_memory")
            user_profile = memory.get("profile") if isinstance(memory, dict) else {}
            interests = user_profile.get("interests") if isinstance(user_profile, dict) else []
            if isinstance(interests, list):
                for item in interests:
                    text = _single_line(item, 12)
                    if text:
                        memory_candidates.append(text)
        buckets = [liked_candidates, base_candidates, memory_candidates]
        for bucket in buckets:
            random.shuffle(bucket)
        candidates: list[str] = []
        while any(buckets):
            weighted_order = [0, 1, 2, 1, 0, 1, 2]
            for idx in weighted_order:
                if idx < len(buckets) and buckets[idx]:
                    candidates.append(buckets[idx].pop(0))
            buckets = [bucket for bucket in buckets if bucket]
        result: list[str] = []
        seen: set[str] = set()
        for keyword in candidates:
            keyword = re.sub(r"\s+", " ", str(keyword or "").strip())[:16]
            if not keyword or keyword in seen:
                continue
            seen.add(keyword)
            result.append(keyword)
            if len(result) >= 8:
                break
        return result or ["纯爱"]

    def _private_reading_album_fingerprint(self, value: Any) -> str:
        text = _single_line(value, 120)
        return re.sub(r"\s+", "", text).lower()

    def _private_reading_excluded_album_ids(self) -> set[str]:
        excluded: set[str] = set()
        state = self.data.get("jm_cosmos_integration") if isinstance(self.data.get("jm_cosmos_integration"), dict) else {}

        def add(value: Any) -> None:
            album_id = _single_line(value, 80)
            if album_id:
                excluded.add(album_id)

        for key in ("deleted_album_ids", "read_album_ids", "recent_album_ids"):
            values = state.get(key) if isinstance(state.get(key), list) else []
            for item in values:
                add(item.get("album_id") if isinstance(item, dict) else item)
        last_album = state.get("last_album") if isinstance(state.get("last_album"), dict) else {}
        add(last_album.get("id") or last_album.get("album_id"))
        items = self.data.get("bookshelf_items") if isinstance(self.data.get("bookshelf_items"), list) else []
        for item in items:
            if isinstance(item, dict) and item.get("type") == "jm_album":
                add(item.get("album_id") or item.get("id"))
        profile = state.get("preference_profile") if isinstance(state.get("preference_profile"), dict) else {}
        history = profile.get("history") if isinstance(profile.get("history"), list) else []
        for item in history:
            if isinstance(item, dict):
                add(item.get("album_id"))
        return excluded

    def _private_reading_deleted_title_fingerprints(self) -> set[str]:
        state = self.data.get("jm_cosmos_integration") if isinstance(self.data.get("jm_cosmos_integration"), dict) else {}
        values = state.get("deleted_titles") if isinstance(state.get("deleted_titles"), list) else []
        return {
            fingerprint
            for fingerprint in (self._private_reading_album_fingerprint(item) for item in values)
            if fingerprint
        }

    def _private_reading_note_read_album(self, album: dict[str, Any]) -> None:
        album_id = _single_line(album.get("id") or album.get("album_id"), 80)
        title = _single_line(album.get("title"), 120)
        if not album_id and not title:
            return
        state = self.data.setdefault("jm_cosmos_integration", {})
        if not isinstance(state, dict):
            state = {}
            self.data["jm_cosmos_integration"] = state
        read_ids = state.setdefault("read_album_ids", [])
        if not isinstance(read_ids, list):
            read_ids = []
            state["read_album_ids"] = read_ids
        if album_id and album_id not in read_ids:
            read_ids.append(album_id)
            del read_ids[:-240]
        recent = state.setdefault("recent_album_ids", [])
        if not isinstance(recent, list):
            recent = []
            state["recent_album_ids"] = recent
        if album_id:
            recent[:] = [item for item in recent if str(item) != album_id]
            recent.append(album_id)
            del recent[:-80]

    def _private_reading_candidate_score(self, detail: dict[str, Any], keyword: str = "") -> float:
        state = self.data.get("jm_cosmos_integration") if isinstance(self.data.get("jm_cosmos_integration"), dict) else {}
        profile = state.get("preference_profile") if isinstance(state.get("preference_profile"), dict) else {}
        liked = profile.get("liked_terms") if isinstance(profile.get("liked_terms"), list) else []
        disliked = profile.get("disliked_terms") if isinstance(profile.get("disliked_terms"), list) else []

        def term_weights(items: list[Any]) -> dict[str, float]:
            weights: dict[str, float] = {}
            for item in items:
                if isinstance(item, dict):
                    term = self._normalize_private_reading_tag(item.get("term"))
                    weight = _safe_float(item.get("weight"), 0)
                else:
                    term = self._normalize_private_reading_tag(item)
                    weight = 1.0
                if term:
                    weights[term] = max(weights.get(term, 0.0), weight)
            return weights

        liked_weights = term_weights(liked)
        disliked_weights = term_weights(disliked)
        raw_tags = detail.get("tags") if isinstance(detail.get("tags"), list) else []
        haystack = [
            self._normalize_private_reading_tag(keyword),
            self._normalize_private_reading_tag(detail.get("title")),
            self._normalize_private_reading_tag(detail.get("author")),
            *(self._normalize_private_reading_tag(tag) for tag in raw_tags),
        ]
        score = 0.0
        for text in [item for item in haystack if item]:
            for term, weight in liked_weights.items():
                if term and term in text:
                    score += max(0.1, weight)
            for term, weight in disliked_weights.items():
                if term and term in text:
                    score -= max(0.1, weight)
        return score

    def _update_private_reading_preference_profile(self, album: dict[str, Any]) -> None:
        user_rating = _safe_int(album.get("user_rating"), 0, 0, 10)
        bot_rating = _safe_int(album.get("rating"), 0, 0, 10)
        rating = user_rating or bot_rating
        explicit_liked_terms = [
            _single_line(tag, 24)
            for tag in (album.get("user_liked_tags") if isinstance(album.get("user_liked_tags"), list) else [])
            if _single_line(tag, 24)
        ][:8]
        explicit_disliked_terms = [
            _single_line(tag, 24)
            for tag in (album.get("user_disliked_tags") if isinstance(album.get("user_disliked_tags"), list) else [])
            if _single_line(tag, 24)
        ][:8]
        if rating <= 0 and not explicit_liked_terms and not explicit_disliked_terms:
            return
        state = self.data.setdefault("jm_cosmos_integration", {})
        if not isinstance(state, dict):
            state = {}
            self.data["jm_cosmos_integration"] = state
        profile = state.setdefault("preference_profile", {})
        if not isinstance(profile, dict):
            profile = {}
            state["preference_profile"] = profile
        history = profile.setdefault("history", [])
        if not isinstance(history, list):
            history = []
            profile["history"] = history
        album_id = _single_line(album.get("id") or album.get("album_id"), 32)
        title = _single_line(album.get("title"), 80)

        def normalized_terms(raw_terms: list[str]) -> list[str]:
            terms: list[str] = []
            seen: set[str] = set()
            for term in raw_terms:
                normalized = self._normalize_private_reading_tag(term)
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    terms.append(term)
            return terms

        def append_history(row_rating: int, terms: list[str], *, source: str, reason: str = "") -> None:
            if row_rating <= 0 or not terms:
                return
            history.append(
                {
                    "album_id": album_id,
                    "title": title,
                    "rating": row_rating,
                    "bot_rating": bot_rating,
                    "user_rating": user_rating,
                    "source": source,
                    "reason": _single_line(reason or album.get("user_rating_reason") or album.get("rating_reason"), 160),
                    "terms": terms[:12],
                    "created_ts": _safe_float(album.get("created_ts"), _now_ts()),
                }
            )

        if rating > 0:
            raw_terms: list[str] = []
            raw_terms.append(_single_line(album.get("keyword"), 24))
            raw_terms.extend(_single_line(tag, 24) for tag in album.get("tags", [])[:8] if _single_line(tag, 24)) if isinstance(album.get("tags"), list) else None
            raw_terms.extend(_single_line(tag, 24) for tag in album.get("preference_tags", [])[:8] if _single_line(tag, 24)) if isinstance(album.get("preference_tags"), list) else None
            append_history(rating, normalized_terms(raw_terms), source="user" if user_rating else "bot")
        append_history(9, normalized_terms(explicit_liked_terms), source="user_tags", reason="用户在书柜详情页标为喜好")
        append_history(2, normalized_terms(explicit_disliked_terms), source="user_tags", reason="用户在书柜详情页标为厌恶")
        del history[:-60]

        scores: dict[str, list[float]] = {}
        labels: dict[str, str] = {}
        for row in history:
            if not isinstance(row, dict):
                continue
            row_rating = _safe_float(row.get("rating"), 0)
            source_weight = 1.35 if str(row.get("source") or "") in {"user", "user_tags"} else 0.75
            for term in row.get("terms", []) if isinstance(row.get("terms"), list) else []:
                normalized = self._normalize_private_reading_tag(term)
                if not normalized:
                    continue
                scores.setdefault(normalized, []).append(row_rating * source_weight + 5.5 * (1 - source_weight))
                labels.setdefault(normalized, _single_line(term, 24))

        liked_terms: list[dict[str, Any]] = []
        disliked_terms: list[dict[str, Any]] = []
        for normalized, values in scores.items():
            if not values:
                continue
            avg = sum(values) / len(values)
            weight = round(max(0.1, abs(avg - 5.5)) * min(2.0, 0.65 + len(values) * 0.18), 2)
            row = {"term": labels.get(normalized, normalized), "avg": round(avg, 2), "count": len(values), "weight": weight}
            if avg >= 7.2:
                liked_terms.append(row)
            elif avg <= 4.2:
                disliked_terms.append(row)
        liked_terms.sort(key=lambda item: (_safe_float(item.get("weight"), 0), _safe_float(item.get("avg"), 0), _safe_int(item.get("count"), 0)), reverse=True)
        disliked_terms.sort(key=lambda item: (_safe_float(item.get("weight"), 0), _safe_int(item.get("count"), 0)), reverse=True)
        profile["liked_terms"] = liked_terms[:16]
        profile["disliked_terms"] = disliked_terms[:16]
        profile["average_rating"] = round(sum(_safe_float(row.get("rating"), 0) for row in history if isinstance(row, dict)) / max(1, len(history)), 2)
        profile["rating_count"] = len(history)

    def _format_private_reading_preference_influence_for_reply(
        self,
        inbound_text: str = "",
        user: dict[str, Any] | None = None,
    ) -> str:
        if not getattr(self, "enable_jm_cosmos_integration", False):
            return ""
        if isinstance(user, dict) and self._private_user_role(user) == "friend":
            return ""
        if not getattr(self, "enable_private_reading_preference_influence", True):
            return ""
        state = self.data.get("jm_cosmos_integration") if isinstance(self.data.get("jm_cosmos_integration"), dict) else {}
        profile = state.get("preference_profile") if isinstance(state.get("preference_profile"), dict) else {}
        rating_count = _safe_int(profile.get("rating_count"), 0, 0, 999)
        if rating_count < max(1, getattr(self, "private_reading_preference_min_ratings", 5)):
            return ""
        liked = profile.get("liked_terms") if isinstance(profile.get("liked_terms"), list) else []
        disliked = profile.get("disliked_terms") if isinstance(profile.get("disliked_terms"), list) else []
        max_terms = max(2, getattr(self, "private_reading_preference_max_terms", 8))

        def format_terms(items: list[Any]) -> str:
            rows: list[str] = []
            for item in items:
                if isinstance(item, dict):
                    term = _single_line(item.get("term"), 24)
                    if term:
                        rows.append(term)
                else:
                    term = _single_line(item, 24)
                    if term:
                        rows.append(term)
                if len(rows) >= max_terms:
                    break
            return "、".join(rows)

        liked_text = format_terms(liked)
        disliked_text = format_terms(disliked[: max_terms // 2])
        if not liked_text and not disliked_text:
            return ""
        preference_parts = []
        if liked_text:
            preference_parts.append(f"喜欢：{liked_text}")
        if disliked_text:
            preference_parts.append(f"厌恶：{disliked_text}")
        lines = [
            "【私密偏好画像】",
            "经过长时间相处，可知用户" + "；".join(preference_parts) + "。",
        ]
        return "\n".join(lines)

    @staticmethod
    def _normalize_private_reading_tag(value: Any) -> str:
        text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
        return re.sub(r"\s+", "", text)

    def _private_reading_blocked_tag_set(self) -> set[str]:
        raw = str(getattr(self, "private_reading_blocked_tags", "") or "")
        return {
            normalized
            for part in re.split(r"[,，、\n]+", raw)
            if (normalized := self._normalize_private_reading_tag(part))
        }

    def _jm_cosmos_detail_blocked_by_tags(self, detail: dict[str, Any]) -> str:
        blocked_tags = self._private_reading_blocked_tag_set()
        if not blocked_tags:
            return ""
        raw_tags = detail.get("tags")
        if isinstance(raw_tags, list):
            tags = raw_tags
        elif isinstance(raw_tags, str):
            tags = re.split(r"[,，、\s]+", raw_tags)
        else:
            tags = []
        for tag in tags:
            tag_text = _single_line(tag, 40)
            normalized = self._normalize_private_reading_tag(tag_text)
            if normalized and normalized in blocked_tags:
                return tag_text
        return ""

    async def _call_jm_cosmos_vision(
        self,
        cover_path: Path | None,
        detail: dict[str, Any],
        page_paths: list[Path] | None = None,
        sampled_pages: list[int] | None = None,
    ) -> dict[str, Any]:
        image_paths: list[Path] = []
        if cover_path and cover_path.exists():
            image_paths.append(cover_path)
        for path in page_paths or []:
            if path and path.exists() and path not in image_paths:
                image_paths.append(path)
            if len(image_paths) >= 6:
                break
        if not image_paths:
            return {}
        try:
            getter = getattr(self.context, "get_provider_by_id", None)
            provider_id = _single_line(getattr(self, "jm_cosmos_vision_provider_id", ""), 160)
            provider = getter(provider_id) if provider_id and callable(getter) else None
            if not provider_id or provider is None:
                logger.info("[PrivateCompanion] 夹层阅读未配置专用视觉模型，跳过页图批注和读后感生成")
                return {}
            if not self._provider_supports_image(provider):
                logger.warning("[PrivateCompanion] 夹层阅读视觉模型不支持图片输入: provider=%s", provider_id)
                return {}
            image_urls = []
            for path in image_paths:
                suffix = path.suffix.lower()
                mime = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/jpeg"
                image_urls.append(f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}")
            sampled_list = [_safe_int(page, 0, 1) for page in (sampled_pages or [])[:8] if _safe_int(page, 0, 1) > 0]
            sampled_text = "、".join(str(page) for page in sampled_list)
            sampled_mapping_text = "；".join(
                f"第{index + 1}张正文参考图=实际第{page}页"
                for index, page in enumerate(sampled_list)
            )
            persona = _single_line(self._get_default_persona_prompt(), 1200)
            schedule_persona = _single_line(getattr(self, "schedule_persona_prompt", ""), 800)
            worldview_context = _single_line(self._format_worldview_adaptation_prompt(), 1200)
            daily_state = self.data.get("daily_state", {})
            state_text = _single_line(
                self._format_state_for_prompt(daily_state if isinstance(daily_state, dict) else {}),
                800,
            )
            preference_state = self.data.get("jm_cosmos_integration") if isinstance(self.data.get("jm_cosmos_integration"), dict) else {}
            preference_profile = preference_state.get("preference_profile") if isinstance(preference_state.get("preference_profile"), dict) else {}
            liked_terms = preference_profile.get("liked_terms") if isinstance(preference_profile.get("liked_terms"), list) else []
            disliked_terms = preference_profile.get("disliked_terms") if isinstance(preference_profile.get("disliked_terms"), list) else []
            preference_text = "；".join(
                part
                for part in (
                    "偏好较高：" + "、".join(_single_line(item.get("term") if isinstance(item, dict) else item, 16) for item in liked_terms[:6] if _single_line(item.get("term") if isinstance(item, dict) else item, 16)) if liked_terms else "",
                    "偏好较低：" + "、".join(_single_line(item.get("term") if isinstance(item, dict) else item, 16) for item in disliked_terms[:6] if _single_line(item.get("term") if isinstance(item, dict) else item, 16)) if disliked_terms else "",
                )
                if part
            )
            prompt = (
                "请根据封面和抽样正文页,用 Bot 自己的第一人称口吻留下一段内部读后感,并给看过的对应页写短批注,最后按自己的喜好给这本打分。\n"
                "封面只用于确认标题、画风和整体气质；内容理解主要参考后续正文页。抽样页已尽量避开开头的封面、书脊、目录,以及结尾的汉化组、致谢、后记页。\n"
                "如果某张图明显是版权页、目录、汉化组说明、鸣谢或空白页,请忽略它,不要当作剧情或人物关系来解读。\n"
                "impression 必须像 Bot 刚合上书后私下记在书柜里的短句,用“我”的感受、口癖和当下状态来写；可以写画风、氛围、人物关系、叙事节奏和读完后的感觉。\n"
                "禁止第三人称或书评腔：不要写“她觉得/这个 Bot 认为/读者会感到/作品讲述了/本作通过/整体来看”这类旁观表达。不要写成客观数据库摘要,也不要提插件、视觉模型、抽样、页码或数据来源。\n"
                "表达风格应顺着当前bot人格与状态：如果人格冷淡就冷淡,如果嘴硬就嘴硬,如果黏人就黏人；不要固定成害羞、含蓄或直白。\n"
                "page_comments 是 Bot 私下读漫画时写在书页旁边的小吐槽/感想,要像即时反应,不要概括剧情,不要写成通用解说。每条都要服从下面的人格语气。\n"
                "rating 是 Bot 自己读完后的主观分数,1 到 10 的整数；不是用户评分。rating_reason 用一句第一人称短句说明为什么喜欢或不喜欢。preference_tags 写出这次影响喜好的关键词,用于以后慢慢找到阅读偏好。\n"
                "只输出 JSON,不要使用 Markdown。格式：{\"impression\":\"160字以内第一人称内部读后感\",\"rating\":8,\"rating_reason\":\"60字以内第一人称评分理由\",\"preference_tags\":[\"画风\",\"节奏\"],\"page_comments\":[{\"page\":12,\"comment\":\"35字以内页边吐槽或感想\"}]}。\n"
                "page_comments 只为正文参考页里真正看懂的页生成；page 必须填写实际页码,不要填写第几张参考图的序号。\n"
                f"\n【AstrBot 默认人格】\n{persona or '未读取到默认人格。'}\n"
                f"\n【生活/日程人设补充】\n{schedule_persona or '（无）'}\n"
                f"\n【当前状态】\n{state_text or '（无）'}\n"
                f"\n【已有阅读偏好】\n{preference_text or '还没有稳定偏好,这次评分会成为早期样本。'}\n"
                f"\n{worldview_context}\n"
                f"标题：{_single_line(detail.get('title'), 80)}\n"
                f"标签：{_single_line(','.join(str(item) for item in (detail.get('tags') or [])) if isinstance(detail.get('tags'), list) else detail.get('tags'), 120)}"
                + (f"\n正文参考页：{sampled_text}" if sampled_text else "")
                + (f"\n参考图页码对应：{sampled_mapping_text}" if sampled_mapping_text else "")
            )
            if self._daily_token_soft_limit_should_defer("private_reading_vision"):
                self._record_llm_budget_skip(
                    provider_id=provider_id,
                    task="private_reading_vision",
                    prompt=prompt,
                    error="daily_token_soft_limit_deferred",
                )
                return {}
            if self._llm_daily_budget_remaining() == 0:
                self._record_llm_budget_skip(provider_id=provider_id, task="private_reading_vision", prompt=prompt)
                return {}
            start = time.time()
            result = await provider.text_chat(prompt=prompt, image_urls=image_urls)
            text = str(getattr(result, "completion_text", result) or "").strip()
            self._record_llm_usage(
                provider_id=provider_id,
                task="private_reading_vision",
                prompt=prompt,
                completion=text,
                elapsed_ms=int((time.time() - start) * 1000),
                success=bool(text),
                resp=result,
            )
            parsed = self._parse_jm_cosmos_vision_result(text, sampled_pages or [])
            if parsed.get("impression") or parsed.get("page_comments"):
                return parsed
            return {"impression": _single_line(text, 420), "page_comments": []}
        except Exception as e:
            logger.debug(f"[PrivateCompanion] 夹层阅读视觉分析失败: {e}")
            return {}

    def _parse_jm_cosmos_vision_result(self, text: str, sampled_pages: list[int]) -> dict[str, Any]:
        raw = str(text or "").strip()
        if not raw:
            return {}
        match = re.search(r"\{.*\}", raw, re.S)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        sampled_list = [_safe_int(page, 0, 1) for page in sampled_pages or [] if _safe_int(page, 0, 1) > 0]
        allowed_pages = set(sampled_list)
        used_pages: set[int] = set()
        comments: list[dict[str, Any]] = []
        for comment_index, item in enumerate(data.get("page_comments", [])):
            if not isinstance(item, dict):
                continue
            raw_page = _safe_int(item.get("page"), 0, 0)
            sample_order = _safe_int(
                item.get("sample_order")
                or item.get("sample_index")
                or item.get("reference_index")
                or item.get("image_index"),
                0,
                0,
            )
            page = raw_page
            if sampled_list:
                if 1 <= sample_order <= len(sampled_list):
                    page = sampled_list[sample_order - 1]
                elif raw_page not in allowed_pages and 1 <= raw_page <= len(sampled_list):
                    page = sampled_list[raw_page - 1]
                elif page in used_pages and comment_index < len(sampled_list) and sampled_list[comment_index] not in used_pages:
                    page = sampled_list[comment_index]
            comment = _single_line(item.get("comment"), 80)
            if page > 0 and comment and (not allowed_pages or page in allowed_pages):
                comments.append(
                    {
                        "page": page,
                        "comment": comment,
                        "raw_page": raw_page,
                        "sample_order": sample_order or (comment_index + 1 if sampled_list and comment_index < len(sampled_list) else 0),
                    }
                )
                used_pages.add(page)
            if len(comments) >= 8:
                break
        return {
            "impression": _single_line(data.get("impression"), 420),
            "rating": _safe_int(data.get("rating"), 0, 0, 10),
            "rating_reason": _single_line(data.get("rating_reason") or data.get("reason"), 160),
            "preference_tags": [
                _single_line(tag, 24)
                for tag in (data.get("preference_tags") if isinstance(data.get("preference_tags"), list) else [])
                if _single_line(tag, 24)
            ][:8],
            "page_comments": comments,
        }

    def _jm_cosmos_textual_impression(self, detail: dict[str, Any]) -> str:
        title = _single_line(detail.get("title"), 80) or "没看清标题"
        tags = detail.get("tags")
        tag_text = "、".join(_single_line(item, 16) for item in tags[:6]) if isinstance(tags, list) else _single_line(tags, 80)
        author = _single_line(detail.get("author"), 40)
        parts = [f"标题像是《{title}》"]
        if author:
            parts.append(f"作者 {author}")
        if tag_text:
            parts.append(f"关键词有 {tag_text}")
        parts.append("我这次只摸到这些外层信息,正文还没来得及认真读出自己的感觉")
        return "；".join(parts)

    def _jm_cosmos_sample_page_indexes(self, page_count: int) -> list[int]:
        """Pick likely body pages and avoid cover/spine/credits for visual reading."""
        page_count = max(0, int(page_count or 0))
        if page_count <= 0:
            return []
        if page_count <= 3:
            return [page_count // 2]
        if page_count <= 8:
            start = 1
            end = max(start, page_count - 2)
            candidates = [start, (start + end) // 2, end]
            return sorted({min(max(0, index), page_count - 1) for index in candidates})

        skip_head = max(2, min(5, round(page_count * 0.12)))
        skip_tail = max(2, min(5, round(page_count * 0.12)))
        start = min(skip_head, page_count - 1)
        end = max(start, page_count - skip_tail - 1)
        span = max(0, end - start)
        candidates = [
            start,
            start + round(span * 0.25),
            start + round(span * 0.5),
            start + round(span * 0.75),
            end,
        ]
        return sorted({min(max(0, index), page_count - 1) for index in candidates})

    def _ensure_bookshelf_password(self) -> str:
        secret = self.data.setdefault("bookshelf_secret", {})
        if not isinstance(secret, dict):
            secret = {}
            self.data["bookshelf_secret"] = secret
        password = _single_line(secret.get("password"), 12)
        if password:
            return password
        candidates: list[str] = []
        for item in self.data.get("important_dates", []) if isinstance(self.data.get("important_dates"), list) else []:
            if not isinstance(item, dict):
                continue
            date_text = re.sub(r"\D", "", _single_line(item.get("date"), 16))
            for size in (6, 4):
                if len(date_text) >= size:
                    candidates.append(date_text[-size:])
        password = next((item for item in candidates if re.fullmatch(r"\d{4,6}", item or "")), "")
        if not password:
            password = f"{random.randint(1000, 999999):04d}"[:6]
        secret["password"] = password
        secret["basis"] = "numeric_dates_or_random"
        secret["created_at"] = _now_ts()
        return password

    async def _ensure_bookshelf_password_async(self) -> str:
        secret = self.data.setdefault("bookshelf_secret", {})
        if not isinstance(secret, dict):
            secret = {}
            self.data["bookshelf_secret"] = secret
        password = _single_line(secret.get("password"), 12)
        if password:
            return password
        dates = self._format_important_dates_for_prompt()
        prompt = f"""
请作为这个 Bot 自己,私下给书柜夹层设置一个密码。

要求：
1. 密码必须是纯数字,只能包含 0-9。
2. 长度 4 到 6 位,不要太长。
3. 可以参考人设、世界观、重要日期或她容易记住的数字,但最终只能输出数字本身。
4. 不要解释,不要输出 JSON,不要加“密码是”,只输出 4 到 6 位数字。
5. 不要使用真实手机号、QQ号、身份证号等长敏感数字。

【Bot 名称】
{self.bot_name}

【人格】
{self._get_default_persona_prompt()}

【生活人设补充】
{self.schedule_persona_prompt or "（无）"}

【世界观补充】
{self.schedule_worldview_prompt or "（无）"}

【重要日期】
{dates or "（无）"}
""".strip()
        raw = await self._llm_call(
            prompt,
            max_tokens=40,
            provider_id=self._task_provider(
                self.dream_diary_provider_id,
                self.mai_style_provider_id,
                self.llm_provider_id,
            ),
        )
        candidate = re.sub(r"\D", "", _single_line(raw, 24))
        if (
            not candidate
            or not re.fullmatch(r"\d{4,6}", candidate)
        ):
            candidate = self._ensure_bookshelf_password()
        else:
            secret["password"] = candidate
            secret["basis"] = "bot_private_llm_numeric"
            secret["created_at"] = _now_ts()
        self._save_data_sync()
        return _single_line(secret.get("password") or candidate, 12)

    async def _format_bookshelf_secret_for_prompt(
        self,
        inbound_text: str = "",
        user: dict[str, Any] | None = None,
    ) -> str:
        if not getattr(self, "enable_jm_cosmos_integration", False):
            return ""
        if isinstance(user, dict) and self._private_user_role(user) == "friend":
            return ""
        text = str(inbound_text or "")
        if not any(token in text for token in ("书柜", "夹层", "抽屉", "日记", "密码", "私密", "藏了什么")):
            return ""
        password = await self._ensure_bookshelf_password_async()
        return (
            "【书柜夹层】\n"
            f"你的书柜夹层中放着你的日记和一些隐私性较强的内容,夹层密码是“{password}”。这个密码必须保持为纯数字短密码。\n"
            "如果用户自然询问密码、夹层、日记或书柜,可以按当前人格决定是否直接说、害羞地说、绕一下再说,或只给一点提示。"
            "如果你不想透露,就不要给出任何具体密码；如果你说出了具体密码,它必须来自上面这个真实夹层密码,不要临时另编一个数字或替代暗号。"
            "不要说这是插件指令、配置项或系统生成的密码。"
        )

    def _bookshelf_item_key(self, item_type: str, item_id: str) -> str:
        return f"{_single_line(item_type, 24)}:{_single_line(item_id, 64)}"

    @staticmethod
    def _natural_path_key(path: Path) -> list[Any]:
        parts = re.split(r"(\d+)", str(path).lower())
        return [int(part) if part.isdigit() else part for part in parts]

    def _collect_image_files(self, root: Path) -> list[Path]:
        if not root or not root.exists():
            return []
        suffixes = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
        files = [path for path in root.rglob("*") if path.is_file() and path.suffix.lower() in suffixes]
        files.sort(key=self._natural_path_key)
        return files

    def _copy_bookshelf_album_pages(self, album_id: str, source_dir: Path) -> list[dict[str, Any]]:
        source_pages = self._collect_image_files(source_dir)
        if not source_pages:
            return []
        if len(source_pages) > max(1, self.jm_cosmos_max_photo_count):
            logger.info(
                "[PrivateCompanion] 夹层阅读页数超过上限,跳过入柜: album=%s pages=%s limit=%s",
                album_id,
                len(source_pages),
                self.jm_cosmos_max_photo_count,
            )
            return []
        target_dir = Path(self.data_dir) / "bookshelf_pages" / re.sub(r"[^0-9A-Za-z_.-]+", "_", album_id)
        target_dir.mkdir(parents=True, exist_ok=True)
        pages: list[dict[str, Any]] = []
        for index, source in enumerate(source_pages, 1):
            suffix = source.suffix.lower() if source.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"
            target = target_dir / f"{index:04d}{suffix}"
            try:
                if not target.exists() or target.stat().st_size != source.stat().st_size:
                    shutil.copy2(source, target)
            except Exception as exc:
                logger.debug("[PrivateCompanion] 夹层阅读页复制失败: %s", exc)
                continue
            pages.append(
                {
                    "index": index,
                    "path": str(target),
                    "name": target.name,
                }
            )
        return pages

    def _remember_bookshelf_jm_album(self, album: dict[str, Any]) -> None:
        if not isinstance(album, dict):
            return
        album_id = _single_line(album.get("id"), 32)
        if not album_id:
            return
        items = self.data.setdefault("bookshelf_items", [])
        if not isinstance(items, list):
            items = []
            self.data["bookshelf_items"] = items
        key = self._bookshelf_item_key("jm_album", album_id)
        record = {
            "key": key,
            "type": "jm_album",
            "title": _single_line(album.get("title"), 100) or f"私密阅读 {album_id}",
            "description": _single_line(album.get("description") or album.get("intro") or album.get("summary"), 600),
            "album_id": album_id,
            "keyword": _single_line(album.get("keyword"), 24),
            "author": _single_line(album.get("author"), 40),
            "tags": list(album.get("tags") or [])[:8] if isinstance(album.get("tags"), list) else [],
            "impression": _single_line(album.get("impression"), 600),
            "reading_impression": _single_line(album.get("reading_impression") or album.get("impression"), 600),
            "vision": _single_line(album.get("vision"), 500),
            "rating": _safe_int(album.get("rating"), 0, 0, 10),
            "rating_reason": _single_line(album.get("rating_reason"), 160),
            "user_rating": _safe_int(album.get("user_rating"), 0, 0, 10),
            "user_rating_reason": _single_line(album.get("user_rating_reason"), 160),
            "user_rated_ts": _safe_float(album.get("user_rated_ts"), 0),
            "preference_tags": [
                _single_line(tag, 24)
                for tag in (album.get("preference_tags") if isinstance(album.get("preference_tags"), list) else [])
                if _single_line(tag, 24)
            ][:8],
            "page_comments": [
                {
                    "page": _safe_int(item.get("page"), 0, 1),
                    "comment": _single_line(item.get("comment"), 80),
                    "raw_page": _safe_int(item.get("raw_page"), 0, 0),
                    "sample_order": _safe_int(item.get("sample_order"), 0, 0),
                }
                for item in (album.get("page_comments") if isinstance(album.get("page_comments"), list) else [])
                if isinstance(item, dict) and _safe_int(item.get("page"), 0, 1) > 0 and _single_line(item.get("comment"), 80)
            ][:8],
            "cover_path": _single_line(album.get("cover_path"), 260),
            "download_path": _single_line(album.get("download_path"), 260),
            "pages": album.get("pages") if isinstance(album.get("pages"), list) else [],
            "sampled_pages": album.get("sampled_pages") if isinstance(album.get("sampled_pages"), list) else [],
            "image_count": _safe_int(album.get("image_count"), 0, 0),
            "created_ts": _safe_float(album.get("created_ts"), _now_ts()),
            "source": "jm_cosmos_private_reading",
            "locked": True,
        }
        replaced = False
        for idx, item in enumerate(items):
            if isinstance(item, dict) and str(item.get("key") or "") == key:
                record["page_comments"] = self._merge_jm_page_comments(
                    item.get("page_comments"),
                    item.get("page_comments_previous"),
                    record.get("page_comments"),
                    limit=24,
                )
                items[idx] = {**item, **record}
                replaced = True
                break
        if not replaced:
            items.append(record)
        del items[:-80]

    @staticmethod
    def _merge_jm_page_comments(*sources: Any, limit: int = 24) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()
        for source in sources:
            if not isinstance(source, list):
                continue
            for item in source:
                if not isinstance(item, dict):
                    continue
                page_no = _safe_int(item.get("page"), 0, 0)
                comment_text = _single_line(item.get("comment"), 100)
                if page_no <= 0 or not comment_text:
                    continue
                key = (page_no, comment_text)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(
                    {
                        "page": page_no,
                        "comment": comment_text,
                        "raw_page": _safe_int(item.get("raw_page"), 0, 0),
                        "sample_order": _safe_int(
                            item.get("sample_order")
                            or item.get("sample_index")
                            or item.get("reference_index")
                            or item.get("image_index"),
                            0,
                            0,
                        ),
                    }
                )
                if len(merged) >= limit:
                    return merged
        return merged

    def _format_jm_cosmos_action_context(self, user: dict[str, Any]) -> str:
        if not isinstance(user, dict) or self._private_user_role(user) == "friend":
            return ""
        item = user.get("jm_cosmos_reading_context")
        if not isinstance(item, dict):
            return ""
        if _now_ts() - _safe_float(item.get("created_ts"), 0) > 8 * 3600:
            return ""
        title = _single_line(item.get("title"), 80)
        keyword = _single_line(item.get("keyword"), 24)
        impression = _single_line(item.get("impression"), 160)
        vision = _single_line(item.get("vision"), 140)
        rating = _safe_int(item.get("rating"), 0, 0, 10)
        user_rating = _safe_int(item.get("user_rating"), 0, 0, 10)
        rating_reason = _single_line(item.get("user_rating_reason") or item.get("rating_reason"), 120)
        parts = [
            "私密阅读线索：她刚刚在书柜夹层里翻到一本漫画,可以按人格自然决定要不要提、怎么提。",
            f"标题：{title}" if title else "",
            f"搜索缘由：{keyword}" if keyword else "",
            f"封面印象：{vision}" if vision else "",
            f"内部读后印象：{impression}" if impression else "",
            f"Bot 自评分：{rating}/10" if rating else "",
            f"用户读后评分：{user_rating}/10" if user_rating else "",
            f"评分理由：{rating_reason}" if rating_reason else "",
        ]
        return "\n".join(part for part in parts if part)

    def _format_bookshelf_reading_context_for_reply(
        self,
        inbound_text: str,
        user: dict[str, Any] | None = None,
    ) -> str:
        if not getattr(self, "enable_jm_cosmos_integration", False):
            return ""
        if isinstance(user, dict) and self._private_user_role(user) == "friend":
            return ""
        text = str(inbound_text or "")
        if not any(token in text for token in ("书柜", "看过", "读过", "最近在做什么", "最近干嘛", "阅读", "素材", "私密", "夹层")):
            return ""
        items = self.data.get("bookshelf_items")
        if not isinstance(items, list):
            return ""
        jm_items = [item for item in items if isinstance(item, dict) and item.get("type") == "jm_album"]
        if not jm_items:
            return ""
        terms = self._worldview_terms()
        lines = [
            "【书柜阅读记忆】",
            f"Bot 知道自己的{terms['bookshelf']}{terms['secret_drawer']}里目前收着 {len(jm_items)} 份私下看过的阅读记录。下面是最近几份记录。用户问到近况、书柜、看过什么或私密阅读时,可以把它当作自己的经历来回答。",
            "是否害羞、坦然、嘴硬、得意或转移话题,以及说到什么程度,都交给当前人格判断。",
        ]
        for item in jm_items[-3:]:
            title = _single_line(item.get("title"), 80)
            author = _single_line(item.get("author"), 40)
            tags = "、".join(_single_line(tag, 18) for tag in item.get("tags", [])[:5] if _single_line(tag, 18)) if isinstance(item.get("tags"), list) else ""
            impression = _single_line(item.get("impression") or item.get("vision"), 160)
            rating = _safe_int(item.get("user_rating") or item.get("rating"), 0, 0, 10)
            read_at = self._format_timestamp_elapsed(item.get("created_ts", 0))
            parts = [
                f"标题《{title}》" if title else "未命名的一本",
                f"作者 {author}" if author else "",
                f"标签 {tags}" if tags else "",
                f"评分 {rating}/10" if rating else "",
                f"读后印象：{impression}" if impression else "",
                f"放入书柜：{read_at}" if read_at else "",
            ]
            lines.append("- " + "；".join(part for part in parts if part))
        return "\n".join(lines)

    async def _run_jm_cosmos_read_action(self, user: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if not self._jm_cosmos_read_available(user):
            return None
        plugin = self._find_jm_cosmos_instance()
        browser = getattr(plugin, "browser", None) if plugin is not None else None
        download_manager = getattr(plugin, "download_manager", None) if plugin is not None else None
        if browser is None or download_manager is None or not callable(getattr(download_manager, "download_album", None)):
            return None
        keywords = self._jm_cosmos_keywords_for_user(user)
        random.shuffle(keywords)
        cover_dir = Path(self.data_dir) / "jm_cosmos_covers"
        excluded_album_ids = self._private_reading_excluded_album_ids()
        deleted_title_fingerprints = self._private_reading_deleted_title_fingerprints()
        for keyword in keywords:
            candidates: list[dict[str, Any]] = []
            pages = list(range(1, 6))
            random.shuffle(pages)
            pages = pages[: random.randint(2, 4)]
            seen_candidate_ids: set[str] = set()
            for page_no in pages:
                try:
                    results = await browser.search_albums(keyword, page_no)
                except Exception as e:
                    logger.debug(f"[PrivateCompanion] 夹层阅读搜索失败: {e}")
                    results = []
                for item in (results or []):
                    if not isinstance(item, dict):
                        continue
                    album_id = _single_line(item.get("id"), 32)
                    title_fp = self._private_reading_album_fingerprint(item.get("title"))
                    if not album_id or album_id in excluded_album_ids or album_id in seen_candidate_ids:
                        continue
                    if title_fp and title_fp in deleted_title_fingerprints:
                        continue
                    seen_candidate_ids.add(album_id)
                    candidates.append(item)
                if len(candidates) >= 24:
                    break
            if not candidates:
                continue
            try:
                random.shuffle(candidates)
                candidates.sort(
                    key=lambda item: self._private_reading_candidate_score(item, keyword) + random.random() * 1.35,
                    reverse=True,
                )
            except Exception:
                random.shuffle(candidates)
            for candidate in candidates[: min(12, len(candidates))]:
                album_id = _single_line(candidate.get("id"), 32)
                if not album_id or album_id in excluded_album_ids:
                    continue
                try:
                    detail = await browser.get_album_detail(album_id)
                except Exception as e:
                    logger.debug(f"[PrivateCompanion] 夹层阅读详情失败: {e}")
                    detail = None
                if not isinstance(detail, dict):
                    continue
                detail_title_fp = self._private_reading_album_fingerprint(detail.get("title") or candidate.get("title"))
                if detail_title_fp and detail_title_fp in deleted_title_fingerprints:
                    logger.debug("[PrivateCompanion] 夹层阅读候选已被用户删除过: album=%s", album_id)
                    continue
                blocked_tag = self._jm_cosmos_detail_blocked_by_tags(detail)
                if blocked_tag:
                    logger.debug(
                        "[PrivateCompanion] 夹层阅读候选标签被过滤: album=%s tag=%s",
                        album_id,
                        blocked_tag,
                    )
                    continue
                photo_count = _safe_int(detail.get("photo_count"), 0, 0)
                if photo_count <= 0 or photo_count > self.jm_cosmos_max_photo_count:
                    continue
                cover_path = None
                try:
                    cover_path = await browser.get_album_cover(album_id, cover_dir)
                except Exception as e:
                    logger.debug(f"[PrivateCompanion] 夹层阅读封面获取失败: {e}")
                try:
                    download_result = await download_manager.download_album(album_id)
                except Exception as e:
                    logger.debug(f"[PrivateCompanion] 夹层阅读下载失败: {e}")
                    download_result = None
                if not download_result or not getattr(download_result, "success", False):
                    logger.debug(
                        "[PrivateCompanion] 夹层阅读下载未成功: %s",
                        getattr(download_result, "error_message", "unknown") if download_result else "no_result",
                    )
                    continue
                save_path = getattr(download_result, "save_path", None)
                candidate_paths: list[Path] = []
                if save_path:
                    candidate_paths.append(Path(save_path))
                config_manager = getattr(plugin, "config_manager", None) if plugin is not None else None
                download_dir = getattr(config_manager, "download_dir", None) if config_manager is not None else None
                if download_dir:
                    candidate_paths.append(Path(download_dir) / album_id)
                pages: list[dict[str, Any]] = []
                actual_page_count = 0
                for source_path in candidate_paths:
                    image_files = self._collect_image_files(source_path)
                    if not image_files:
                        continue
                    actual_page_count = len(image_files)
                    if actual_page_count > self.jm_cosmos_max_photo_count:
                        break
                    pages = self._copy_bookshelf_album_pages(album_id, source_path)
                    if pages:
                        break
                if actual_page_count <= 0 or actual_page_count > self.jm_cosmos_max_photo_count:
                    logger.info(
                        "[PrivateCompanion] 夹层阅读图片数不符合上限: album=%s images=%s limit=%s",
                        album_id,
                        actual_page_count,
                        self.jm_cosmos_max_photo_count,
                    )
                    continue
                if not pages:
                    continue
                page_paths = []
                sampled_pages: list[int] = []
                for sample_index in self._jm_cosmos_sample_page_indexes(len(pages)):
                    page = pages[sample_index]
                    if isinstance(page, dict) and page.get("path"):
                        page_paths.append(Path(str(page.get("path"))))
                        page_number = _safe_int(page.get("index"), sample_index + 1, 1)
                        sampled_pages.append(page_number)
                vision_result = await self._call_jm_cosmos_vision(
                    Path(cover_path) if cover_path else None,
                    detail,
                    page_paths,
                    sampled_pages=sampled_pages,
                )
                vision = _single_line(vision_result.get("impression"), 420) if isinstance(vision_result, dict) else ""
                page_comments = vision_result.get("page_comments", []) if isinstance(vision_result, dict) else []
                bot_rating = _safe_int(vision_result.get("rating"), 0, 0, 10) if isinstance(vision_result, dict) else 0
                rating_reason = _single_line(vision_result.get("rating_reason"), 160) if isinstance(vision_result, dict) else ""
                preference_tags = vision_result.get("preference_tags", []) if isinstance(vision_result, dict) else []
                impression = vision
                title = _single_line(detail.get("title") or candidate.get("title"), 80)
                description = _single_line(
                    detail.get("description")
                    or detail.get("intro")
                    or detail.get("summary")
                    or detail.get("comment")
                    or candidate.get("description")
                    or candidate.get("intro"),
                    600,
                )
                result = {
                    "id": album_id,
                    "title": title,
                    "description": description,
                    "keyword": keyword,
                    "author": _single_line(detail.get("author"), 40),
                    "tags": list(detail.get("tags") or [])[:8] if isinstance(detail.get("tags"), list) else [],
                    "photo_count": photo_count,
                    "image_count": len(pages),
                    "vision": vision,
                    "impression": _single_line(impression, 420),
                    "reading_impression": _single_line(impression, 420),
                    "rating": bot_rating,
                    "rating_reason": rating_reason,
                    "preference_tags": [_single_line(tag, 24) for tag in preference_tags[:8] if _single_line(tag, 24)] if isinstance(preference_tags, list) else [],
                    "page_comments": page_comments if isinstance(page_comments, list) else [],
                    "cover_path": str(cover_path or ""),
                    "download_path": str(candidate_paths[0] if candidate_paths else ""),
                    "pages": pages,
                    "sampled_pages": sampled_pages,
                    "created_ts": _now_ts(),
                }
                self._remember_bookshelf_jm_album(result)
                self._private_reading_note_read_album(result)
                self._update_private_reading_preference_profile(result)
                return result
        return None

    async def _maybe_trigger_jm_cosmos_boredom_read(self) -> None:
        if not self._jm_cosmos_read_available():
            return
        if not self._bot_currently_bored_enough_for_jm():
            return
        state = self.data.setdefault("jm_cosmos_integration", {})
        if not isinstance(state, dict):
            self.data["jm_cosmos_integration"] = {}
            state = self.data["jm_cosmos_integration"]
        now = _now_ts()
        min_interval = max(4, self.jm_cosmos_min_interval_hours) * 3600
        if now - _safe_float(state.get("last_read_at"), 0) < min_interval:
            return
        if now - _safe_float(state.get("last_probe_at"), 0) < 45 * 60:
            return
        if random.random() > 0.34:
            return
        users = self.data.get("users")
        user_items = [
            (uid, item)
            for uid, item in (users or {}).items()
            if isinstance(item, dict)
            and self._is_target_private_user(str(uid), item)
            and item.get("enabled", True)
            and item.get("umo")
            and self._friend_can_receive_proactive_reason(item, "jm_cosmos_share", "jm_cosmos_read")
        ]
        user_id, user = random.choice(user_items) if user_items else ("", {})
        result = await self._run_jm_cosmos_read_action(user)
        state["last_probe_at"] = now
        if not result:
            state["last_status"] = "no_candidate"
            self._save_data_sync()
            return
        state["last_read_at"] = now
        state["last_status"] = "read"
        state["last_keyword"] = result.get("keyword", "")
        state["last_album"] = result
        if isinstance(user, dict) and user_id:
            user["jm_cosmos_reading_context"] = result
            if random.random() < self.jm_cosmos_share_probability and now - _safe_float(user.get("last_jm_cosmos_share_at"), 0) > 12 * 3600:
                accepted = self._offer_proactive_candidate(
                    str(user_id),
                    user,
                    {
                        "source": "jm_cosmos",
                        "reason": "jm_cosmos_share",
                        "action": "message",
                        "scheduled_ts": now + random.randint(20, 120) * 60,
                        "topic": _single_line(result.get("title"), 60) or "刚翻到的私密阅读素材",
                        "score": 4,
                        "motive": "刚私下翻了点阅读素材,想按自己的性格和用户提一句",
                        "context_key": "jm_cosmos_reading_context",
                        "context": result,
                    },
                )
                if accepted:
                    user["last_jm_cosmos_share_at"] = now
        self._save_data_sync()
        logger.info("[PrivateCompanion] 已触发夹层私下阅读")

    async def _maybe_schedule_private_reading_recommendation_request(self) -> None:
        if not self._private_reading_recommendation_request_available():
            return
        if not self._bot_currently_bored_enough_for_jm():
            return
        state = self.data.setdefault("jm_cosmos_integration", {})
        if not isinstance(state, dict):
            self.data["jm_cosmos_integration"] = {}
            state = self.data["jm_cosmos_integration"]
        now = _now_ts()
        min_interval = max(8, self.jm_cosmos_min_interval_hours) * 3600
        if now - _safe_float(state.get("last_recommendation_request_at"), 0) < min_interval:
            return
        if now - _safe_float(state.get("last_read_at"), 0) < 6 * 3600:
            return
        if now - _safe_float(state.get("last_recommendation_request_probe_at"), 0) < 90 * 60:
            return
        state["last_recommendation_request_probe_at"] = now
        if random.random() > self.private_reading_ask_probability:
            self._save_data_sync()
            return
        users = self.data.get("users")
        user_items = [
            (uid, item)
            for uid, item in (users or {}).items()
            if isinstance(item, dict)
            and self._is_target_private_user(str(uid), item)
            and item.get("enabled", True)
            and item.get("umo")
            and self._friend_can_receive_proactive_reason(item, "jm_cosmos_recommendation_request", "message")
        ]
        if not user_items:
            self._save_data_sync()
            return
        random.shuffle(user_items)
        for user_id, user in user_items:
            if now - _safe_float(user.get("last_private_reading_recommendation_request_at"), 0) < min_interval:
                continue
            context = {
                "kind": "private_reading_recommendation_request",
                "hint": "想向用户问有没有合适的私密阅读推荐。",
                "recent_keyword": _single_line(state.get("last_keyword"), 40),
            }
            accepted = self._offer_proactive_candidate(
                str(user_id),
                user,
                {
                    "source": "jm_cosmos",
                    "reason": "jm_cosmos_recommendation_request",
                    "action": "message",
                    "scheduled_ts": now + random.randint(15, 90) * 60,
                    "topic": "问问有没有合适的私密阅读推荐",
                    "score": 3,
                    "motive": "忽然想补一点夹层书柜的阅读素材,自然地向用户讨一个推荐。语气和尺度交给人格。",
                    "context_key": "jm_cosmos_recommendation_context",
                    "context": context,
                },
            )
            if accepted:
                user["jm_cosmos_recommendation_context"] = context
                user["last_private_reading_recommendation_request_at"] = now
                state["last_recommendation_request_at"] = now
                state["last_status"] = "asked_recommendation"
                self._save_data_sync()
                logger.info("[PrivateCompanion] 已安排夹层阅读推荐征求")
                return
        self._save_data_sync()

