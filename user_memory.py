# -*- coding: utf-8 -*-
"""
UserMemoryMixin — 从 main.py 重新拆分出的用户记忆系统
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

class UserMemoryMixin:
    """用户记忆系统"""

    @staticmethod
    def _memory_fact_signature(text: Any) -> str:
        compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]+", "", str(text or "")).lower()
        return compact[:80]

    def _cleanup_companion_memory_items(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        memory = user.get("companion_memory")
        if not isinstance(memory, dict):
            return []
        items = memory.get("items")
        if not isinstance(items, list):
            memory["items"] = []
            return []
        now = _now_ts()
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in items:
            if not isinstance(raw, dict):
                continue
            text = _single_line(raw.get("text"), 260)
            if not text:
                continue
            created_ts = _safe_float(raw.get("created_ts"), 0)
            created_at = _single_line(raw.get("created_at"), 24)
            if created_ts <= 0 and created_at:
                try:
                    created_ts = datetime.strptime(created_at, "%Y-%m-%d %H:%M").timestamp()
                except Exception:
                    created_ts = now
            if created_ts > 0 and now - created_ts > 180 * 86400:
                continue
            signature = self._memory_fact_signature(text)
            if not signature or signature in seen:
                continue
            seen.add(signature)
            item = dict(raw)
            item["text"] = text
            item["created_ts"] = created_ts or now
            deduped.append(item)
        deduped.sort(key=lambda item: (_safe_int(item.get("weight"), 1, 0), _safe_float(item.get("created_ts"), 0)), reverse=True)
        memory["items"] = deduped[: self.max_companion_memory_items]
        return memory["items"]

    def _companion_memory_relevant_items(self, user: dict[str, Any], *, hint: str = "", limit: int = 6) -> list[dict[str, Any]]:
        items = self._cleanup_companion_memory_items(user)
        if not items:
            return []
        hint_text = _single_line(hint, 260).lower()
        if not hint_text:
            return items[: max(1, limit)]
        weighted: list[tuple[int, dict[str, Any]]] = []
        for item in items:
            text = _single_line(item.get("text"), 260).lower()
            score = _safe_int(item.get("weight"), 1, 0)
            if text and any(token and token in hint_text for token in re.findall(r"[\u4e00-\u9fff]{2,8}|[a-z0-9_]{3,24}", text)):
                score += 4
            weighted.append((score, item))
        weighted.sort(key=lambda pair: (pair[0], _safe_float(pair[1].get("created_ts"), 0)), reverse=True)
        return [item for _, item in weighted[: max(1, limit)]]

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
            emotion_enabled = bool(getattr(self, "enable_emotion_simulation", True))
            relation_enabled = bool(getattr(self, "enable_relationship_state_machine", True))
            if emotion_enabled:
                self._decay_relationship_mood_score(rel_state)
            if emotion_enabled and mode == "refusing" and _safe_float(rel_state.get("hurt_until"), 0) > _now_ts():
                hints.append("最近用户的话让 Bot 明显受伤并进入拒近状态。表现方式是短句、停一下、少解释,可以轻轻拒绝继续被这样说；不要直白反复说“我受伤了”,不要撒娇、贴贴、求哄或主动靠近。")
            elif emotion_enabled and mode == "hurt" and _safe_float(rel_state.get("hurt_until"), 0) > _now_ts():
                hints.append("最近 Bot 有点委屈受伤。表现方式是回复短一点、慢一点、少一点热情,可以绕开亲密动作,用轻微沉默或别过头式的语气表达余波；不要直接把状态说成“我受伤了”,也不要立刻恢复黏人。")
            elif relation_enabled and mode == "backoff" and _safe_float(rel_state.get("backoff_until"), 0) > _now_ts():
                hints.append("最近用户像是在表达边界或不想被打扰,主动和被动都要明显收敛,短一点,不追问。")
            elif relation_enabled and mode == "careful":
                hints.append("最近用户情绪或压力偏重,只保留低压关心：先接住一句,不追问、不讲大道理、不把亲密动作压过去。")
            elif emotion_enabled and mode == "attached":
                hints.append("最近互动是正向亲近的,可以更软一点、更自然地回应亲近,也可以轻轻接住贴近动作；但不要过度黏、不要把普通对话都变成亲密表演。")
            elif relation_enabled and mode == "warming":
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
            "created_ts": _now_ts(),
        }
        signature = self._memory_fact_signature(cleaned)
        deduped = [
            old
            for old in items
            if isinstance(old, dict) and self._memory_fact_signature(_single_line(old.get("text"), 260)) != signature
        ]
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
        lines: list[str] = []
        if not isinstance(memory, dict):
            memory = {}
        llm_profile = memory.get("profile")
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
        items = self._companion_memory_relevant_items(user, hint=user.get("last_user_message") or "", limit=8)
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
        habit_text = self._format_user_behavior_habits_for_prompt(user, current_only=False, limit=5)
        if habit_text:
            lines.append(habit_text)
        episode_text = self._format_dialogue_episodes_for_prompt(user)
        if episode_text:
            lines.append("近期共同经历：\n" + episode_text)
        open_loop_text = self._format_open_loops_for_prompt(user)
        if open_loop_text:
            lines.append("未完成约定/可续话头：\n" + open_loop_text)
        consequence_text = self._format_action_consequence_hint(user)
        if consequence_text:
            lines.append("最近主动行为闭环：\n" + consequence_text)
        return "\n".join(lines) if lines else "暂无专门沉淀的用户记忆。"

    def _format_dialogue_episodes_for_prompt(self, user: dict[str, Any]) -> str:
        episodes = user.get("dialogue_episodes")
        if not isinstance(episodes, list):
            return ""
        seen: set[str] = set()
        lines: list[str] = []
        for item in episodes[-4:]:
            if not isinstance(item, dict):
                continue
            summary = _single_line(item.get("summary"), 120)
            if not summary:
                continue
            signature = self._memory_fact_signature(summary)
            if signature and signature in seen:
                continue
            if signature:
                seen.add(signature)
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
        seen: set[str] = set()
        for item in loops:
            if not isinstance(item, dict):
                continue
            if now - _safe_float(item.get("created_ts"), now) > 14 * 86400:
                continue
            signature = self._memory_fact_signature(item.get("text"))
            if signature and signature in seen:
                continue
            if signature:
                seen.add(signature)
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

    def _action_consequence_items(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        items = user.setdefault("action_consequences", [])
        if not isinstance(items, list):
            items = []
            user["action_consequences"] = items
        now = _now_ts()
        kept: list[dict[str, Any]] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            created = _safe_float(item.get("ts"), now)
            if now - created > 7 * 86400:
                continue
            kept.append(item)
        if len(kept) != len(items):
            user["action_consequences"] = kept[-18:]
        return user["action_consequences"]

    def _classify_action_reply_feedback(self, text: str) -> str:
        cleaned = _single_line(text, 220)
        if not cleaned:
            return "neutral"
        negative = (
            "别",
            "不要",
            "不许",
            "烦",
            "打扰",
            "闭嘴",
            "硬",
            "生硬",
            "不喜欢",
            "不对",
            "不是",
            "笨",
            "怎么又",
            "没收到",
            "哪里",
            "图呢",
        )
        positive = (
            "好",
            "可以",
            "喜欢",
            "可爱",
            "聪明",
            "对",
            "正常",
            "收到",
            "摸摸",
            "抱抱",
            "谢谢",
            "不错",
        )
        if any(token in cleaned for token in negative):
            return "negative"
        if any(token in cleaned for token in positive):
            return "positive"
        return "neutral"

    def _note_action_sent(
        self,
        user: dict[str, Any],
        action: str,
        *,
        reason: str = "",
        text: str = "",
        motive: str = "",
        action_summary: str = "",
    ) -> None:
        action = _single_line(action, 40) or "message"
        items = self._action_consequence_items(user)
        items.append(
            {
                "ts": _now_ts(),
                "action": action,
                "reason": _single_line(reason, 50),
                "text": _single_line(_strip_internal_message_blocks(text), 120),
                "motive": _single_line(motive, 100),
                "summary": _single_line(action_summary, 120),
                "status": "awaiting_reply",
                "feedback": "",
                "reply_text": "",
                "reply_ts": 0,
            }
        )
        del items[:-18]
        continuity = user.setdefault("state_continuity", {})
        if not isinstance(continuity, dict):
            continuity = {}
            user["state_continuity"] = continuity
        continuity["last_action_ts"] = _now_ts()
        continuity["last_action"] = action
        continuity["last_action_reason"] = _single_line(reason, 50)
        continuity["last_action_text"] = _single_line(_strip_internal_message_blocks(text), 120)

    def _note_action_reply_feedback(self, user: dict[str, Any], action: str, text: str = "") -> None:
        action = _single_line(action, 40) or "message"
        affinity = user.setdefault("action_reply_affinity", {})
        if not isinstance(affinity, dict):
            affinity = {}
            user["action_reply_affinity"] = affinity
        affinity[action] = _safe_int(affinity.get(action), 0, 0) + 1

        feedback = self._classify_action_reply_feedback(text)
        now = _now_ts()
        for item in reversed(self._action_consequence_items(user)):
            if not isinstance(item, dict):
                continue
            if item.get("status") != "awaiting_reply":
                continue
            if _single_line(item.get("action"), 40) != action:
                continue
            item["status"] = "replied"
            item["feedback"] = feedback
            item["reply_text"] = _single_line(text, 120)
            item["reply_ts"] = now
            break
        continuity = user.setdefault("state_continuity", {})
        if not isinstance(continuity, dict):
            continuity = {}
            user["state_continuity"] = continuity
        continuity["last_reply_ts"] = now
        continuity["last_reply_feedback"] = feedback
        continuity["last_reply_text"] = _single_line(text, 120)

    def _format_action_consequence_hint(self, user: dict[str, Any]) -> str:
        items = self._action_consequence_items(user)
        if not items:
            return ""
        lines: list[str] = []
        for item in items[-5:]:
            if not isinstance(item, dict):
                continue
            action = _single_line(item.get("action"), 30)
            reason = _single_line(item.get("reason"), 40)
            text = _single_line(item.get("text"), 70)
            status = _single_line(item.get("status"), 24)
            feedback = _single_line(item.get("feedback"), 24)
            reply = _single_line(item.get("reply_text"), 70)
            if not action and not text:
                continue
            when = self._format_timestamp_elapsed(item.get("ts"))
            parts = [f"{when}主动{action or 'message'}"]
            if reason:
                parts.append(f"原因:{reason}")
            if text:
                parts.append(f"内容:{text}")
            if status == "awaiting_reply":
                parts.append("还没有自然接上,下次不要当作用户刚刚主动找你")
            elif reply:
                parts.append(f"用户反馈:{feedback or 'neutral'}:{reply}")
            lines.append("- " + "；".join(parts))
        if not lines:
            return ""
        return "\n".join(lines)

    def _time_bucket_for_user_habit(self, when: datetime | None = None) -> tuple[str, int]:
        when = when or datetime.now()
        minute = when.hour * 60 + when.minute
        buckets = (
            ("凌晨", 0, 6 * 60),
            ("早晨", 6 * 60, 9 * 60),
            ("上午", 9 * 60, 11 * 60 + 30),
            ("中午", 11 * 60 + 30, 14 * 60),
            ("下午", 14 * 60, 18 * 60),
            ("傍晚", 18 * 60, 20 * 60),
            ("夜晚", 20 * 60, 23 * 60),
            ("深夜", 23 * 60, 24 * 60),
        )
        for label, start, end in buckets:
            if start <= minute < end:
                return label, minute
        return "凌晨", minute

    def _classify_user_habit_message(self, text: str) -> tuple[str, str, str]:
        cleaned = _single_line(text, 220)
        lowered = cleaned.lower()
        if not cleaned:
            return "", "", ""
        category = "聊天话题"
        topic = cleaned
        if any(token in cleaned for token in ("吃饭", "午饭", "晚饭", "早饭", "早餐", "午餐", "晚餐", "夜宵", "饿", "饱")):
            category = "饮食节奏"
            if any(token in cleaned for token in ("还没", "没吃", "没来得及", "没饭", "没到饭点")):
                topic = "还没吃/饭点偏晚"
            elif any(token in cleaned for token in ("吃了", "刚吃", "吃完", "饱")):
                topic = "已经吃过饭"
            else:
                topic = "吃饭相关"
        elif any(token in cleaned for token in ("睡", "起床", "醒", "熬夜", "困", "晚安", "早安")):
            category = "作息节奏"
            if any(token in cleaned for token in ("还没睡", "睡不着", "熬夜")):
                topic = "夜里还没睡"
            elif any(token in cleaned for token in ("起床", "刚醒", "醒了")):
                topic = "起床/刚醒"
            else:
                topic = "睡眠相关"
        elif any(token in cleaned for token in ("作业", "上课", "下课", "考试", "题", "学习", "上班", "下班", "工作", "摸鱼")):
            category = "学习工作"
            topic = "学习/工作节奏"
        elif any(token in cleaned for token in ("游戏", "视频", "番", "漫画", "小说", "直播", "刷", "看")):
            category = "娱乐习惯"
            topic = "娱乐/刷内容"
        elif re.search(r"[？?]|什么|多少|颜色|吗|呢|怎么|有没有|可不可以|要不要", cleaned):
            category = "固定提问"
            topic = re.sub(r"\d+", "", cleaned)
        elif any(token in cleaned for token in ("喜欢", "讨厌", "想要", "以后", "每天", "经常", "总是", "习惯")):
            category = "偏好习惯"
            topic = cleaned
        signature = self._proactive_topic_signature(category, topic or cleaned, lowered)
        return category, _single_line(topic, 80), signature

    def _update_user_behavior_habits_from_message(self, user: dict[str, Any], text: str) -> None:
        if not self.enable_user_habit_learning:
            return
        cleaned = _single_line(text, 220)
        if not cleaned or cleaned.startswith(("/", "!", "！", "#")):
            return
        category, topic, signature = self._classify_user_habit_message(cleaned)
        if not category or not signature:
            return
        now_dt = datetime.now()
        bucket, minute = self._time_bucket_for_user_habit(now_dt)
        habits = user.setdefault("behavior_habits", {})
        if not isinstance(habits, dict):
            habits = {}
            user["behavior_habits"] = habits
        patterns = habits.setdefault("patterns", [])
        if not isinstance(patterns, list):
            patterns = []
            habits["patterns"] = patterns
        key = f"{bucket}|{category}|{signature}"
        matched = None
        for item in patterns:
            if isinstance(item, dict) and str(item.get("key") or "") == key:
                matched = item
                break
        if matched is None:
            matched = {
                "key": key,
                "bucket": bucket,
                "category": category,
                "topic": topic,
                "signature": signature,
                "count": 0,
                "avg_minute": minute,
                "examples": [],
                "created_ts": _now_ts(),
            }
            patterns.append(matched)
        count = _safe_int(matched.get("count"), 0, 0) + 1
        old_avg = _safe_float(matched.get("avg_minute"), minute)
        matched["count"] = min(999, count)
        matched["avg_minute"] = round((old_avg * max(0, count - 1) + minute) / max(1, count), 1)
        matched["last_seen_ts"] = _now_ts()
        matched["last_seen_text"] = cleaned
        examples = matched.get("examples")
        if not isinstance(examples, list):
            examples = []
        examples.insert(0, cleaned)
        matched["examples"] = list(dict.fromkeys(_single_line(item, 90) for item in examples if _single_line(item, 90)))[:5]
        patterns.sort(
            key=lambda item: (
                _safe_int(item.get("count"), 0, 0) if isinstance(item, dict) else 0,
                _safe_float(item.get("last_seen_ts"), 0) if isinstance(item, dict) else 0,
            ),
            reverse=True,
        )
        del patterns[self.user_habit_max_items:]
        habits["updated_at"] = now_dt.strftime("%Y-%m-%d %H:%M")

    def _format_user_habit_time(self, minute_value: Any) -> str:
        minute = int(max(0, min(1439, round(_safe_float(minute_value, 0)))))
        return f"{minute // 60:02d}:{minute % 60:02d}"

    def _qualified_user_behavior_habits(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        habits = user.get("behavior_habits")
        if not isinstance(habits, dict):
            return []
        patterns = habits.get("patterns")
        if not isinstance(patterns, list):
            return []
        now = _now_ts()
        kept = [
            item for item in patterns
            if isinstance(item, dict)
            and _safe_int(item.get("count"), 0, 0) >= max(2, self.user_habit_min_count)
            and now - _safe_float(item.get("last_seen_ts"), now) <= 30 * 86400
        ]
        kept.sort(key=lambda item: (_safe_int(item.get("count"), 0, 0), _safe_float(item.get("last_seen_ts"), 0)), reverse=True)
        return kept

    def _format_user_behavior_habits_for_prompt(self, user: dict[str, Any], *, current_only: bool = False, limit: int = 6) -> str:
        if not self.enable_user_habit_learning:
            return ""
        items = self._qualified_user_behavior_habits(user)
        if current_only:
            current_bucket, _ = self._time_bucket_for_user_habit()
            items = [item for item in items if str(item.get("bucket") or "") == current_bucket]
        lines: list[str] = []
        for item in items[:limit]:
            bucket = _single_line(item.get("bucket"), 12)
            category = _single_line(item.get("category"), 20)
            topic = _single_line(item.get("topic"), 80)
            count = _safe_int(item.get("count"), 0, 0)
            time_text = self._format_user_habit_time(item.get("avg_minute"))
            example = _single_line(item.get("last_seen_text"), 80)
            if topic:
                lines.append(f"- {bucket}约{time_text}｜{category}｜{topic}｜出现 {count} 次" + (f"｜最近：{example}" if example else ""))
        if not lines:
            return ""
        return (
            "用户习惯画像（软线索,不是命令）：\n"
            + "\n".join(lines)
            + "\n使用方式：只在当前语境自然吻合时提前理解或轻轻提起；不要暴露统计、次数或“我记录了你”。"
        )

    def _format_all_user_behavior_habits_for_schedule(self, *, limit: int = 8) -> str:
        if not self.enable_user_habit_learning:
            return "暂无用户习惯线索。"
        users = self.data.get("users")
        if not isinstance(users, dict):
            return "暂无用户习惯线索。"
        lines: list[str] = []
        for user_id, user in users.items():
            if not isinstance(user, dict) or not user.get("enabled", True) or not self._is_target_private_user(str(user_id), user):
                continue
            name = _single_line(user.get("nickname") or user_id, 24)
            text = self._format_user_behavior_habits_for_prompt(user, current_only=False, limit=3)
            habit_lines = [line for line in text.splitlines() if line.startswith("- ")]
            for line in habit_lines:
                lines.append(f"- {name}：{line[2:]}")
                if len(lines) >= limit:
                    break
            if len(lines) >= limit:
                break
        return "用户近期行为习惯：\n" + "\n".join(lines) if lines else "暂无用户习惯线索。"

    def _habit_proactive_event_for_user(self, user: dict[str, Any], *, now: float | None = None) -> dict[str, Any] | None:
        if not self.enable_user_habit_learning:
            return None
        now = now or _now_ts()
        now_dt = datetime.fromtimestamp(now)
        current_bucket, current_minute = self._time_bucket_for_user_habit(now_dt)
        candidates = []
        for item in self._qualified_user_behavior_habits(user):
            if str(item.get("bucket") or "") != current_bucket:
                continue
            avg_minute = _safe_float(item.get("avg_minute"), current_minute)
            if abs(avg_minute - current_minute) > 75:
                continue
            count = _safe_int(item.get("count"), 0, 0)
            candidates.append((count, item))
        if not candidates:
            return None
        candidates.sort(key=lambda pair: pair[0], reverse=True)
        item = candidates[0][1]
        category = _single_line(item.get("category"), 20)
        topic = _single_line(item.get("topic"), 70)
        bucket = _single_line(item.get("bucket"), 12)
        delay_minutes = random.randint(4, 28)
        return {
            "date": _today_key(),
            "window": self._window_from_delay_minutes(delay_minutes, width_minutes=20),
            "reason": "habit_awareness",
            "action": "message",
            "why": f"用户最近常在{bucket}出现“{category}”相关话题或行为,这会儿自然想提前理解一下。",
            "topic": topic or category or "用户习惯",
            "motive": f"这会儿像是用户平常会提到“{topic or category}”的时候,想自然接住,不用说自己在统计。",
            "scene": f"{bucket}的惯常互动时段",
            "tone": "熟悉,提前一步",
            "impulse": "像真的记得对方生活节奏一样,轻轻提前接住",
            "_scheduled_ts": now + delay_minutes * 60,
            "_habit_awareness": True,
        }

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
        emotion_event = self._classify_relationship_emotion_event(cleaned)
        return {
            "intent": intent,
            "emotion": emotion,
            "pressure": min(5, pressure),
            "reply_style": reply_style,
            "emotion_event": emotion_event.get("event", "neutral"),
            "emotion_intensity": emotion_event.get("intensity", 0),
            "emotion_reason": emotion_event.get("reason", ""),
            "emotion_target": emotion_event.get("target", "none"),
            "emotion_rule": emotion_event.get("rule", ""),
            "text": cleaned,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        }

    def _classify_relationship_emotion_event(self, text: str) -> dict[str, Any]:
        cleaned = _single_line(text, 240)
        if not cleaned:
            return {"event": "neutral", "intensity": 0, "reason": "", "target": "none", "rule": ""}
        lower = cleaned.lower()
        target_hint = bool(re.search(r"(你|bot|机器人|插件|星缘|老老老|助手|ai|AI)", cleaned))
        third_party_hint = bool(re.search(r"(他|她|它|他们|她们|别人|群友|那个人|这个人|用户|豆腐|蛙蛙|小水月)", cleaned))
        self_low = bool(re.search(r"(我好|我真|我太|我是不是|我就是|我是).{0,12}(废物|垃圾|没用|傻|笨|恶心|讨厌)", cleaned))
        severe_hurt = (
            "滚" in cleaned
            or "闭嘴" in cleaned
            or "恶心" in cleaned
            or "废物" in cleaned
            or "垃圾" in cleaned
            or "讨厌你" in cleaned
            or "烦你" in cleaned
            or "不想理你" in cleaned
            or re.search(r"(只是|不过|不就是).{0,6}(bot|机器人|工具|代码)", lower)
        )
        identity_hurt = bool(
            re.search(r"(玻璃心|假装|演的|装的|设定|工具人|没感情|别装|别演|虚拟的|假的)", cleaned)
            and target_hint
        )
        mild_hurt = bool(
            re.search(r"(太烦|吵死|烦死|别撒娇|别贴|别靠近|别这样|没用|笨死|傻)", cleaned)
            and target_hint
        )
        apology = bool(re.search(r"(对不起|抱歉|我错了|不是故意|原谅|别生气|别难过|哄哄|哄你)", cleaned))
        comfort = bool(re.search(r"(摸摸|贴贴|抱抱|亲亲|乖|不哭|别伤心|陪你|抱一下)", cleaned))
        praise = bool(re.search(r"(喜欢你|爱你|可爱|厉害|真好|谢谢你|辛苦|最棒|夸夸)", cleaned))
        if self_low:
            return {"event": "comfort_need", "intensity": 62, "reason": "用户自我否定或低落", "target": "self", "rule": "self_low"}
        if third_party_hint and severe_hurt and not target_hint:
            return {"event": "external_negative", "intensity": 54, "reason": "用户在评价第三方", "target": "other", "rule": "third_party_negative"}
        if severe_hurt:
            return {"event": "hurt", "intensity": 90 if target_hint else 72, "reason": "强否定或驱赶", "target": "bot" if target_hint else "ambiguous", "rule": "severe_hurt"}
        if identity_hurt:
            return {"event": "hurt", "intensity": 72, "reason": "否定情感真实性或人格", "target": "bot", "rule": "identity_hurt"}
        if mild_hurt:
            return {"event": "hurt", "intensity": 58, "reason": "轻度否定或拒近", "target": "bot", "rule": "mild_hurt"}
        if apology:
            return {"event": "apology", "intensity": 68, "reason": "道歉或修复", "target": "bot", "rule": "apology"}
        if comfort:
            return {"event": "comfort", "intensity": 46, "reason": "安抚亲密互动", "target": "bot", "rule": "comfort"}
        if praise:
            return {"event": "praise", "intensity": 38, "reason": "正向肯定", "target": "bot" if target_hint else "ambiguous", "rule": "praise"}
        return {"event": "neutral", "intensity": 0, "reason": "", "target": "none", "rule": ""}

    def _decay_relationship_mood_score(self, state: dict[str, Any], *, now: float | None = None) -> int:
        now = now or _now_ts()
        score = _safe_int(state.get("mood_score"), 0, -100, 100)
        last_ts = _safe_float(state.get("mood_updated_ts"), 0)
        if score == 0 or last_ts <= 0 or now <= last_ts:
            state["mood_updated_ts"] = now
            return score
        hours = max(0.0, (now - last_ts) / 3600)
        recovery = max(1, _safe_int(getattr(self, "emotional_gate_recovery_per_hour", 12), 12, 1, 60))
        delta = int(hours * recovery)
        if delta <= 0:
            return score
        if score < 0:
            score = min(0, score + delta)
        else:
            score = max(0, score - max(1, delta // 2))
        state["mood_score"] = score
        state["mood_updated_ts"] = now
        return score

    def _update_relationship_state_from_intent(self, user: dict[str, Any], intent: dict[str, Any]) -> None:
        if not isinstance(intent, dict):
            return
        emotion_enabled = bool(getattr(self, "enable_emotion_simulation", True))
        relation_enabled = bool(getattr(self, "enable_relationship_state_machine", True))
        if not (emotion_enabled or relation_enabled):
            return
        state = user.setdefault("relationship_state", {})
        if not isinstance(state, dict):
            state = {}
            user["relationship_state"] = state
        now = _now_ts()
        previous_mode = str(state.get("mode") or "normal")
        current = previous_mode
        mood_score = self._decay_relationship_mood_score(state, now=now) if emotion_enabled else 0
        inbound_intent = str(intent.get("intent") or "chat")
        pressure = _safe_int(intent.get("pressure"), 0, 0, 5)
        emotion_event = str(intent.get("emotion_event") or "neutral")
        intensity = _safe_int(intent.get("emotion_intensity"), 0, 0, 100)
        reason = _single_line(intent.get("emotion_reason"), 80)
        target = _single_line(intent.get("emotion_target"), 24) or "none"
        rule = _single_line(intent.get("emotion_rule"), 40)
        hurt_threshold = _safe_int(getattr(self, "emotional_gate_hurt_threshold", 55), 55, 10, 100)
        refuse_threshold = _safe_int(getattr(self, "emotional_gate_refuse_threshold", 80), 80, 20, 100)
        if emotion_enabled and emotion_event == "hurt" and target in {"bot", "ambiguous"} and intensity >= hurt_threshold:
            mood_score = max(-100, mood_score - max(8, int(intensity * 0.8)))
            hurt_minutes = min(
                _safe_int(getattr(self, "emotional_gate_max_hurt_minutes", 180), 180, 10, 720),
                max(15, int(intensity * 1.8)),
            )
            state["hurt_until"] = now + hurt_minutes * 60
            state["silence_turns"] = max(
                _safe_int(state.get("silence_turns"), 0, 0, 5),
                2 if abs(mood_score) >= refuse_threshold else 1,
            )
            state["last_hurt_reason"] = reason or "用户表达伤害性内容"
            state["last_hurt_text"] = _single_line(intent.get("text"), 160)
            current = "refusing" if abs(mood_score) >= refuse_threshold else "hurt"
        elif emotion_enabled and emotion_event in {"apology", "comfort", "praise"}:
            recover_ratio = 0.75 if emotion_event == "apology" else (0.52 if emotion_event == "comfort" else 0.35)
            mood_score = min(100, mood_score + max(3, int(intensity * recover_ratio)))
            state["silence_turns"] = max(0, _safe_int(state.get("silence_turns"), 0, 0, 5) - 1)
            if mood_score > -hurt_threshold:
                state["hurt_until"] = 0
            if mood_score >= 45 and inbound_intent in {"intimacy", "play"}:
                current = "attached"
            elif mood_score < -20:
                current = "hurt"
            else:
                current = "warming" if inbound_intent in {"intimacy", "play"} else "normal"
        elif emotion_enabled and emotion_event == "comfort_need":
            current = "careful"
            state["last_care_reason"] = reason
        elif emotion_enabled and emotion_event == "external_negative":
            current = "careful"
            state["last_external_negative_reason"] = reason
        elif relation_enabled and inbound_intent == "boundary":
            current = "backoff"
            state["backoff_until"] = now + 6 * 3600
        elif relation_enabled and pressure >= 2:
            current = "careful"
        elif relation_enabled and inbound_intent in {"intimacy", "play"}:
            current = "attached" if emotion_enabled and mood_score >= 45 else "warming"
        elif emotion_enabled and _safe_float(state.get("hurt_until"), 0) > now and mood_score <= -hurt_threshold:
            current = "refusing" if abs(mood_score) >= refuse_threshold else "hurt"
        elif (
            relation_enabled
            and previous_mode == "backoff"
            and _safe_float(state.get("backoff_until"), 0) > now
        ):
            current = "backoff"
        else:
            current = "normal"
        if current not in {"hurt", "refusing"} and _safe_int(state.get("silence_turns"), 0, 0, 5) > 0:
            state["silence_turns"] = max(0, _safe_int(state.get("silence_turns"), 0, 0, 5) - 1)
        state["mode"] = current
        state["mood_score"] = mood_score
        state["mood_updated_ts"] = now
        state["last_intent"] = inbound_intent
        state["last_emotion"] = str(intent.get("emotion") or "neutral")
        state["last_emotion_event"] = emotion_event
        state["last_emotion_intensity"] = intensity
        state["last_emotion_reason"] = reason
        state["last_emotion_target"] = target
        state["last_emotion_rule"] = rule
        state["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")
        if emotion_event != "neutral" or current in {"hurt", "refusing", "attached"}:
            logger.info(
                "[PrivateCompanion] 情绪闸门判定: event=%s target=%s rule=%s intensity=%s score=%s mode=%s->%s silence=%s reason=%s text=%s",
                emotion_event,
                target,
                rule or "-",
                intensity,
                mood_score,
                previous_mode,
                current,
                _safe_int(state.get("silence_turns"), 0, 0, 5),
                reason or "-",
                _single_line(intent.get("text"), 120),
            )
        vent_threshold = _safe_int(getattr(self, "qzone_emotional_vent_threshold", 90), 90, 40, 100)
        if (
            current == "refusing"
            and previous_mode != "refusing"
            and abs(mood_score) >= vent_threshold
            and target in {"bot", "ambiguous"}
        ):
            role_getter = getattr(self, "_private_user_role", None)
            try:
                role = role_getter(user, str(user.get("user_id") or "")) if callable(role_getter) else ""
            except Exception:
                role = ""
            if role != "owner":
                logger.info(
                    "[PrivateCompanion] 情绪发泄说说跳过: user_role=%s score=%s",
                    role or "friend",
                    abs(mood_score),
                )
                return
            vent = getattr(self, "_maybe_publish_qzone_emotional_vent", None)
            if callable(vent):
                try:
                    asyncio.create_task(vent(user_snapshot=deepcopy(user), relationship_state=deepcopy(state), intent=deepcopy(intent)))
                except Exception as exc:
                    logger.debug("[PrivateCompanion] 情绪发泄说说任务创建失败: %s", _single_line(exc, 120))

    def _remember_passive_reply_topic(self, user: dict[str, Any], text: str, inbound_text: str = "") -> None:
        if not self.enable_passive_topic_suppression:
            return
        signature = self._proactive_topic_signature(text, inbound_text)
        if not signature:
            return
        recent = self._cleanup_recent_passive_topics(user)
        recent.append({"ts": _now_ts(), "signature": signature, "text": _single_line(text, 120)})
        del recent[:-18]

    async def _review_and_rewrite_response(self, user: dict[str, Any], inbound_text: str, response_text: str) -> str:
        if not self.enable_response_self_review:
            return response_text
        trimmed = self._trim_abrupt_closing_topic_shift(response_text, inbound_text=inbound_text)
        if trimmed and trimmed != str(response_text or "").strip():
            return trimmed
        flags = self._response_review_flags(response_text, user)
        if not flags:
            return response_text
        lightweight_checker = getattr(self, "_is_lightweight_private_passive_inbound", None)
        if callable(lightweight_checker) and lightweight_checker(inbound_text):
            critical_flags = {"too_long", "meta_or_assistant", "over_structured", "leaks_internal"}
            if not any(flag in critical_flags for flag in flags):
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
- 如果回复已经在说晚安、睡觉、做梦、告别,不要再突然追加天气、日程、生活观察或另一个新话题
- 如果问题是重复上一条 Bot 消息,必须直接承接用户这句话,不要再说上一条里的“吃饱犯困/下午还有事/有什么安排”等同义内容
- 如果原回复为了表现困、迷糊、半梦半醒或低能量而变得含混,优先改成清楚承接用户；状态只能留在语气里,不能牺牲回答质量
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

    def _simulation_active(self, user: dict[str, Any]) -> bool:
        raw = user.get("simulation_mode")
        return isinstance(raw, dict) and bool(raw.get("active"))

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
        now = _now_ts()
        async with self._data_lock:
            user = dict(self._get_user(user_id))
        if now < _safe_float(user.get("dialogue_episode_retry_after"), 0):
            return
        count = _safe_int(user.get("episode_message_count"), 0, 0)
        last_at = _safe_float(user.get("last_episode_refresh_at"), 0)
        if count < self.episode_memory_refresh_messages and now - last_at < self.episode_memory_refresh_minutes * 60:
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
        acquired = await self._try_acquire_user_background_task(
            user_id,
            "dialogue_episode",
            now,
            refresh_key="last_episode_refresh_at",
            refresh_seconds=self.episode_memory_refresh_minutes * 60,
        )
        if not acquired:
            return
        try:
            raw = await self._llm_call(
                prompt,
                max_tokens=520,
                provider_id=self._task_provider(self.dialogue_episode_provider_id, self.mai_style_provider_id),
                task="dialogue_episode",
            )
            payload = self._extract_json_payload(raw or "")
        except Exception as exc:
            await self._mark_user_background_retry(user_id, "dialogue_episode", now, exc)
            return
        if not isinstance(payload, dict):
            await self._mark_user_background_retry(user_id, "dialogue_episode", now, "invalid_json")
            return
        episode = {
            "date": _today_key(),
            "created_ts": now,
            "summary": _single_line(payload.get("summary"), 140),
            "emotional_residue": _single_line(payload.get("emotional_residue"), 100),
            "reusable_topic": _single_line(payload.get("reusable_topic"), 100),
            "user_events": self._normalize_string_list(payload.get("user_events"), limit=6),
            "bot_promises": self._normalize_string_list(payload.get("bot_promises"), limit=6),
            "avoid_next": self._normalize_string_list(payload.get("avoid_next"), limit=6),
        }
        if not episode["summary"]:
            await self._mark_user_background_retry(user_id, "dialogue_episode", now, "empty_summary")
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
                            "created_ts": now,
                            "source": "dialogue_episode",
                        }
                    )
                del current_loops[:-12]
            current["episode_message_count"] = 0
            current["last_episode_refresh_at"] = now
            current["dialogue_episode_retry_after"] = 0
            current["dialogue_episode_last_error"] = ""
            current["dialogue_episode_running_at"] = 0
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
        current_habits = self._format_user_behavior_habits_for_prompt(user, current_only=True, limit=4)
        if current_habits:
            sections.append("【当前时段用户习惯】\n" + current_habits)
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

    def _format_private_identity_anchor_for_prompt(self, user_id: str, user: dict[str, Any], event: Any | None = None) -> str:
        worldbook_profile = None
        try:
            worldbook_profile = self._worldbook_profile_by_user_id(user_id)
        except Exception:
            worldbook_profile = None
        worldbook_name = _single_line(worldbook_profile.get("name"), 24) if isinstance(worldbook_profile, dict) else ""
        stable_name = _single_line(user.get("nickname") or worldbook_name or self.default_nickname, 24)
        identity_note = (
            _single_line(worldbook_profile.get("identity_note") or worldbook_profile.get("note") or worldbook_profile.get("content"), 180)
            if isinstance(worldbook_profile, dict)
            else ""
        )
        display_name = _single_line(user.get("last_display_name") or user.get("display_name"), 40)
        if event is not None:
            try:
                display_name = _single_line(self._sender_display_name(event), 40) or display_name
            except Exception:
                pass
        aliases = []
        for item in user.get("observed_display_names") if isinstance(user.get("observed_display_names"), list) else []:
            alias = _single_line(item, 24)
            if alias and alias not in aliases and alias != stable_name:
                aliases.append(alias)
        lines = [
            "【私聊身份锚点】",
            f"当前私聊对象的稳定 ID：{_single_line(user_id, 40)}",
            f"你应使用的稳定称呼/关系身份：{stable_name}",
        ]
        if worldbook_name and worldbook_name != stable_name:
            lines.append(f"关系网登记名：{worldbook_name}")
        if identity_note:
            lines.append(f"关系网身份备注：{identity_note}")
        if display_name and display_name != stable_name:
            lines.append(
                f"平台当前显示名/临时改名：{display_name}。这只是此刻看到的昵称或用户改名结果,不能覆盖稳定 ID 对应的人。"
            )
            lines.append(
                f"如果显示名像其他角色、家人或熟人名字,应理解为用户在改名/玩梗/模仿；仍然把对方当作{stable_name},不要把对方误认为那个名字本人。"
            )
        if aliases:
            lines.append(f"近期观察到的显示名：{'、'.join(aliases[:6])}")
        rename_text = self._format_display_name_rename_events(user.get("display_name_events"), limit=3)
        if rename_text:
            lines.append(f"近期改名行为：{rename_text}")
        lines.append("回复时优先按稳定身份和既有关系接话；只有用户明确说明自己身份变了,才临时顺着设定玩。")
        return "\n".join(lines)

    def _note_private_display_name_observation(self, user: dict[str, Any], user_id: str, display_name: str, *, now: float | None = None) -> None:
        display_name = _single_line(display_name, 40)
        user_id = str(user_id or "").strip()
        if not display_name or display_name == user_id:
            return
        now_ts = _safe_float(now, 0) or _now_ts()
        previous = _single_line(user.get("last_display_name"), 40)
        if previous and previous != display_name:
            events = user.setdefault("display_name_events", [])
            if not isinstance(events, list):
                events = []
                user["display_name_events"] = events
            last = events[-1] if events and isinstance(events[-1], dict) else {}
            if not (
                _single_line(last.get("old"), 40) == previous
                and _single_line(last.get("new"), 40) == display_name
                and now_ts - _safe_float(last.get("ts"), 0) < 3600
            ):
                events.append({"ts": now_ts, "old": previous, "new": display_name})
                del events[:-12]
        user["last_display_name"] = display_name
        observed = user.setdefault("observed_display_names", [])
        if isinstance(observed, list) and display_name not in observed:
            observed.append(display_name)
            del observed[:-8]

    async def _maybe_refresh_companion_memory(self, user_id: str, user: dict[str, Any]) -> None:
        if not self.enable_companion_memory:
            return
        now = _now_ts()
        async with self._data_lock:
            user = dict(self._get_user(user_id))
        if now < _safe_float(user.get("companion_memory_retry_after"), 0):
            return
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
        acquired = await self._try_acquire_user_background_task(
            user_id,
            "companion_memory",
            now,
            refresh_key="last_memory_refresh_at",
            refresh_seconds=self.memory_refresh_interval_minutes * 60,
        )
        if not acquired:
            return
        try:
            raw = await self._llm_call(
                prompt,
                max_tokens=420,
                provider_id=self._task_provider(self.companion_memory_provider_id, self.mai_style_provider_id),
                task="memory_profile",
            )
            payload = self._extract_json_payload(raw or "")
        except Exception as exc:
            await self._mark_user_background_retry(user_id, "companion_memory", now, exc)
            return
        if not isinstance(payload, dict):
            await self._mark_user_background_retry(user_id, "companion_memory", now, "invalid_json")
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
            current["companion_memory_retry_after"] = 0
            current["companion_memory_last_error"] = ""
            current["companion_memory_running_at"] = 0
            self._save_data_sync()

    async def _try_acquire_user_background_task(
        self,
        user_id: str,
        task: str,
        now: float,
        *,
        refresh_key: str,
        refresh_seconds: float,
    ) -> bool:
        retry_key = f"{task}_retry_after"
        running_key = f"{task}_running_at"
        async with self._data_lock:
            current = self._get_user(user_id)
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

    async def _mark_user_background_retry(self, user_id: str, task: str, now: float, error: Any) -> None:
        retry_key = f"{task}_retry_after"
        error_key = f"{task}_last_error"
        running_key = f"{task}_running_at"
        if task == "dialogue_episode":
            configured = _safe_int(getattr(self, "episode_memory_refresh_minutes", 60), 60, 1) * 60
        elif task == "companion_memory":
            configured = _safe_int(getattr(self, "memory_refresh_interval_minutes", 180), 180, 1) * 60
        else:
            configured = 10 * 60
        delay = min(max(10 * 60, configured), 30 * 60)
        async with self._data_lock:
            current = self._get_user(user_id)
            current[retry_key] = now + delay
            current[error_key] = _single_line(error, 180)
            current[running_key] = 0
            self._save_data_sync()
        logger.warning(
            "[PrivateCompanion] 私聊后台整理失败,已进入短冷却避免重复请求: user=%s task=%s retry=%ss error=%s",
            user_id,
            task,
            int(delay),
            _single_line(error, 120),
        )

    def _format_intent_relationship_injection(self, user: dict[str, Any]) -> str:
        intent = user.get("intent_profile")
        state = user.get("relationship_state")
        lines: list[str] = []
        if (
            bool(getattr(self, "enable_intent_emotion_analysis", True))
            and isinstance(intent, dict)
            and intent.get("intent")
        ):
            lines.append(
                "最近用户意图："
                f"{intent.get('intent')}｜情绪 {intent.get('emotion', 'neutral')}｜"
                f"建议回复姿态 {intent.get('reply_style', 'natural')}"
            )
        if isinstance(state, dict) and state.get("mode"):
            mode = str(state.get("mode") or "normal")
            emotion_enabled = bool(getattr(self, "enable_emotion_simulation", True))
            relation_enabled = bool(getattr(self, "enable_relationship_state_machine", True))
            if mode in {"hurt", "refusing", "attached"} and not emotion_enabled:
                mode = "normal"
            if mode in {"backoff", "careful", "warming"} and not relation_enabled:
                mode = "normal"
            if not (mode == "normal" and not (emotion_enabled or relation_enabled)):
                if emotion_enabled:
                    self._decay_relationship_mood_score(state)
                mood_score = _safe_int(state.get("mood_score"), 0, -100, 100)
                silence_turns = _safe_int(state.get("silence_turns"), 0, 0, 5)
                hurt_reason = _single_line(state.get("last_hurt_reason"), 80)
                mode_hint = {
                    "backoff": "用户可能在表达边界或不想被打扰,回复要短、低压,不要撒娇追问。",
                    "careful": "用户可能有压力或负面情绪,只保留低压关心：先接住一句,少讲道理,不追问,不强行亲密。",
                    "hurt": "Bot 当前有被伤到的余波。用短句、轻微沉默、少热情来表现,绕开贴贴/抱抱等亲密动作；不要直白反复说“我受伤了”。",
                    "refusing": "Bot 当前明显受伤并处于拒近状态。可以克制地拒绝继续被这样说,句子更短,不撒娇、不求哄、不主动贴近。",
                    "attached": "互动状态正向亲近,可以自然软一点、接住亲近,也可更容易轻分享；但不要无节制主动或越过用户边界。",
                    "warming": "互动有升温或玩笑感,可以更自然亲近一点,但别过度表演。",
                    "normal": "关系状态平稳,正常接话即可。",
                }.get(mode, "正常接话即可。")
                extra = []
                if emotion_enabled and mood_score:
                    extra.append(f"情绪分 {mood_score}")
                if emotion_enabled and silence_turns:
                    extra.append(f"收敛轮数 {silence_turns}")
                if emotion_enabled and hurt_reason and mode in {"hurt", "refusing"}:
                    extra.append(f"触发原因 {hurt_reason}")
                lines.append(f"关系状态机：{mode}{'｜' + '｜'.join(extra) if extra else ''}。{mode_hint}")
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
        if self._has_abrupt_closing_topic_shift(cleaned, inbound_text=""):
            flags.append("abrupt_topic_shift")
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
        persona = await self._refresh_default_persona_prompt(str(user.get("umo") or user_id))
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
            "jm_cosmos_read": "私下阅读",
        }
        parts = []
        for key in ("screen_peek", "photo_text", "poke", "voice", "jm_cosmos_read"):
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

