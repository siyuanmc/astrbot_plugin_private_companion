# -*- coding: utf-8 -*-
"""
ProactiveMessageMixin — 主动消息生成、动作执行和发送链路
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


class ProactiveMessageMixin:
    """主动消息生成、动作执行和发送链路"""

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
        source = _single_line(video.get("source"), 40)
        memory_context = video.get("memory_context") if isinstance(video.get("memory_context"), list) else []
        memory_lines = [_single_line(item, 160) for item in memory_context if _single_line(item, 160)][:3]
        parts = [
            "B站视频分享线索：刚刷到一个视频",
            f"标题：{title}" if title else "",
            f"链接：https://www.bilibili.com/video/{bvid}" if bvid else "",
            f"UP：{up_name}" if up_name else "",
            f"评分：{score}/10" if score else "",
            f"心情：{mood}" if mood else "",
            f"短评：{comment}" if comment else "",
            f"回味：{review}" if review else "",
            f"来源：{source}" if source else "",
            "BiliBot记忆：" + " / ".join(memory_lines) if memory_lines else "",
        ]
        return "\n".join(part for part in parts if part)

    def _format_news_action_context(self, user: dict[str, Any]) -> str:
        news = user.get("news_context")
        if not isinstance(news, dict):
            return ""
        if _now_ts() - _safe_float(news.get("created_ts"), 0) > 8 * 3600:
            return ""
        topic = _single_line(news.get("topic"), 60)
        headline = _single_line(news.get("headline"), 100)
        source = _single_line(news.get("selected_source"), 40)
        impression = _single_line(news.get("impression"), 240)
        link = _single_line(news.get("selected_link"), 400)
        self_link = news.get("self_link") if isinstance(news.get("self_link"), dict) else {}
        self_link_text = _single_line(self_link.get("self_link") if isinstance(self_link, dict) else "", 180)
        self_link_tone = _single_line(news.get("share_tone") or (self_link.get("tone") if isinstance(self_link, dict) else ""), 80)
        self_link_boundary = _single_line(news.get("share_boundary") or (self_link.get("boundary") if isinstance(self_link, dict) else ""), 160)
        parts = [
            "新闻阅读线索：刚扫过几条新闻,其中一条让自己有点想私下提一句。",
            f"话题：{topic}" if topic else "",
            f"标题：{headline}" if headline else "",
            f"来源：{source}" if source else "",
            f"内部印象：{impression}" if impression else "",
            f"和自己有关的地方：{self_link_text}" if self_link_text else "",
            f"表达气质：{self_link_tone}" if self_link_tone else "",
            f"额外边界：{self_link_boundary}" if self_link_boundary else "",
            f"链接：{link}" if link else "",
            "表达要求：不要像播报新闻,不要夸大或补充未知事实；可以只轻轻提起,也可以按人格吐槽、担心、好奇或转移成日常感受。",
        ]
        return "\n".join(part for part in parts if part)

    def _format_web_exploration_action_context(self, user: dict[str, Any]) -> str:
        exploration = user.get("web_exploration_context")
        if not isinstance(exploration, dict):
            return ""
        if _now_ts() - _safe_float(exploration.get("created_ts"), 0) > 10 * 3600:
            return ""
        query = _single_line(exploration.get("query"), 80)
        topic = _single_line(exploration.get("topic"), 80)
        note = _single_line(exploration.get("note"), 260)
        source_title = _single_line(exploration.get("source_title"), 120)
        source_url = _single_line(exploration.get("source_url"), 420)
        reason = _single_line(exploration.get("reason"), 140)
        self_link = exploration.get("self_link") if isinstance(exploration.get("self_link"), dict) else {}
        self_link_text = _single_line(self_link.get("self_link") if isinstance(self_link, dict) else "", 180)
        self_link_tone = _single_line(exploration.get("share_tone") or (self_link.get("tone") if isinstance(self_link, dict) else ""), 80)
        self_link_boundary = _single_line(exploration.get("share_boundary") or (self_link.get("boundary") if isinstance(self_link, dict) else ""), 160)
        parts = [
            "网页探索线索：Bot 刚刚按自己的兴趣主动搜索并了解了一点新东西,这是一条内部探索笔记。",
            f"搜索词：{query}" if query else "",
            f"为什么想查：{reason}" if reason else "",
            f"探索主题：{topic}" if topic else "",
            f"留下的印象：{note}" if note else "",
            f"和自己有关的地方：{self_link_text}" if self_link_text else "",
            f"表达气质：{self_link_tone}" if self_link_tone else "",
            f"额外边界：{self_link_boundary}" if self_link_boundary else "",
            f"参考来源：{source_title}" if source_title else "",
            f"链接：{source_url}" if source_url else "",
            "表达要求：可以像随手分享发现、吐槽、好奇或继续想查；不要说成系统功能,不要编造来源外的信息。",
        ]
        return "\n".join(part for part in parts if part)

    def _user_asks_news_context(self, inbound_text: str) -> bool:
        text = str(inbound_text or "").strip()
        if not text:
            return False
        if any(token in text for token in ("新闻", "早报", "热点", "时讯", "资讯", "新消息")):
            return True
        lowered = text.lower()
        return any(token in lowered for token in ("ai news", "llm news", "daily ai", "tech news"))

    def _format_recent_news_context_for_reply(self, inbound_text: str = "") -> str:
        if not self._user_asks_news_context(inbound_text):
            return ""
        state = self.data.get("news_integration") if isinstance(self.data.get("news_integration"), dict) else {}
        digest = state.get("last_digest") if isinstance(state.get("last_digest"), dict) else {}
        digests = state.get("digests") if isinstance(state.get("digests"), list) else []
        latest_items = state.get("latest_items") if isinstance(state.get("latest_items"), list) else []
        if not digest and not digests and not latest_items:
            if not self.enable_news_integration:
                return (
                    "【新闻阅读上下文】\n"
                    "用户正在询问今天的新闻/AI 新闻,但新闻阅读功能当前未开启。请自然说明自己这边没有近期新闻记录,不要编造新闻。"
                )
            return (
                "【新闻阅读上下文】\n"
                "用户正在询问今天的新闻/AI 新闻,但当前还没有可用的新闻阅读记录。请自然说明自己还没读到今天的新闻,不要编造新闻。"
            )
        rows: list[str] = []
        if digest:
            rows.append(
                "最近一次整理："
                + "｜".join(
                    part
                    for part in (
                        _single_line(digest.get("headline") or digest.get("topic"), 120),
                        _single_line(digest.get("selected_source"), 40),
                        _single_line(digest.get("impression"), 220),
                        _single_line(digest.get("selected_link"), 360),
                    )
                    if part
                )
            )
        for item in reversed([item for item in digests if isinstance(item, dict)][-4:]):
            headline = _single_line(item.get("headline") or item.get("topic"), 120)
            impression = _single_line(item.get("impression"), 180)
            source = _single_line(item.get("selected_source"), 40)
            if headline or impression:
                rows.append("- " + "｜".join(part for part in (headline, source, impression) if part))
        if latest_items:
            rows.append("候选标题：")
            for item in latest_items[:6]:
                if not isinstance(item, dict):
                    continue
                title = _single_line(item.get("title"), 120)
                source = _single_line(item.get("source"), 40)
                summary = _single_line(item.get("summary"), 160)
                if title:
                    rows.append("- " + "｜".join(part for part in (title, source, summary) if part))
        return (
            "【新闻阅读上下文】\n"
            "用户正在询问今天的新闻/AI 新闻。下面是 Bot 近期真实读过或抓到的新闻记录；回答时只能基于这些内容,不要编造额外新闻。"
            "可以按人格自然概括,如果记录不够新或不完整,要直接说明。\n"
            + "\n".join(rows[:12])
        )

    def _format_news_digest_for_command(self) -> str:
        state = self.data.get("news_integration") if isinstance(self.data.get("news_integration"), dict) else {}
        if not self.enable_news_integration:
            return "新闻阅读功能没有开启。"
        status = _single_line(state.get("last_status"), 60) or "未知"
        digest = state.get("last_digest") if isinstance(state.get("last_digest"), dict) else {}
        latest_items = state.get("latest_items") if isinstance(state.get("latest_items"), list) else []
        if not digest and not latest_items:
            return f"这次没有读到可用新闻。\n状态：{status}"
        lines = ["今日新闻见闻："]
        if digest:
            headline = _single_line(digest.get("headline") or digest.get("topic"), 120)
            source = _single_line(digest.get("selected_source"), 40)
            impression = _single_line(digest.get("impression"), 260)
            link = _single_line(digest.get("selected_link"), 420)
            if headline:
                lines.append(f"- 重点：{headline}")
            if source:
                lines.append(f"- 来源：{source}")
            if impression:
                lines.append(f"- 印象：{impression}")
            if link:
                lines.append(f"- 链接：{link}")
        if latest_items:
            lines.append("候选标题：")
            for item in latest_items[:6]:
                if not isinstance(item, dict):
                    continue
                title = _single_line(item.get("title"), 100)
                source = _single_line(item.get("source"), 30)
                if title:
                    lines.append(f"- {title}" + (f"（{source}）" if source else ""))
        return "\n".join(lines)

    def _format_ai_daily_status_for_command(self) -> str:
        state = self.data.get("news_integration") if isinstance(self.data.get("news_integration"), dict) else {}
        ai_state = state.get("ai_daily") if isinstance(state.get("ai_daily"), dict) else {}
        status_labels = {
            "read": "已阅读",
            "waiting_schedule": "等待定时",
            "all_sources_done": "今日来源已处理",
            "waiting_window": "等待窗口",
            "checking": "正在检查",
            "waiting_today_video": "等待今日视频",
            "today_video_without_text": "今日视频暂无文字版",
            "already_read_today_video": "今日已读",
            "missed_today_ai_daily": "今日窗口已过",
            "digest_failed": "整理失败",
        }
        status = _single_line(ai_state.get("status"), 60) or "未知"
        lines = [
            "AI 日报/早报测试结果：",
            f"- 新闻集成：{'开启' if self.enable_news_integration else '关闭'}",
            f"- AI日报/早报追踪：{'开启' if self.enable_ai_daily_watch else '关闭'}",
            f"- 状态：{status_labels.get(status, status)}",
        ]
        sources = ai_state.get("sources") if isinstance(ai_state.get("sources"), list) else []
        configured_sources = str(getattr(self, "ai_daily_sources", "") or "").strip()
        if configured_sources:
            lines.append("- 来源计划：")
            for raw_line in configured_sources.splitlines()[:8]:
                parts = [part.strip() for part in raw_line.split("|")]
                if len(parts) >= 5:
                    lines.append(f"  - {parts[0]}｜{parts[1]}｜{parts[4]}｜UID {parts[2]}")
        elif sources:
            lines.append("- 来源计划：")
            for item in sources[:8]:
                if not isinstance(item, dict):
                    continue
                lines.append(
                    f"  - {_single_line(item.get('name'), 30)}｜{_single_line(item.get('author_name'), 40)}"
                    f"｜{_single_line(item.get('schedule'), 10)}｜UID {_single_line(item.get('mid'), 32)}"
                )
        date = _single_line(ai_state.get("date"), 20)
        checked = self._format_timestamp_elapsed(ai_state.get("last_checked_at", 0))
        success_date = _single_line(ai_state.get("last_success_date"), 20)
        title = _single_line(ai_state.get("last_video_title"), 120)
        video_link = _single_line(ai_state.get("last_video_link"), 420)
        text_link = _single_line(ai_state.get("last_text_link"), 420)
        candidate_count = _safe_int(ai_state.get("last_candidate_count"), 0, 0)
        digest = ai_state.get("last_digest") if isinstance(ai_state.get("last_digest"), dict) else {}
        selected_item: dict[str, Any] = {}
        digest_items = digest.get("items") if isinstance(digest.get("items"), list) else []
        selected_key = _single_line(digest.get("selected_key"), 80)
        for candidate in digest_items:
            if not isinstance(candidate, dict):
                continue
            if selected_key and _single_line(candidate.get("key"), 80) == selected_key:
                selected_item = candidate
                break
        if not selected_item and digest_items and isinstance(digest_items[0], dict):
            selected_item = digest_items[0]
        if date:
            lines.append(f"- 状态日期：{date}")
        if checked:
            lines.append(f"- 最近检查：{checked}")
        if success_date:
            lines.append(f"- 最近成功日期：{success_date}")
        last_source = _single_line(ai_state.get("last_source_name"), 40)
        last_author = _single_line(ai_state.get("last_source_author"), 60)
        last_schedule = _single_line(ai_state.get("last_source_schedule"), 10)
        if last_source or last_author:
            lines.append(
                "- 最近来源："
                + "｜".join(part for part in (last_source, last_author, last_schedule) if part)
            )
        if title:
            lines.append(f"- 视频：{title}")
        if video_link:
            lines.append(f"- 视频链接：{video_link}")
        owner_name = _single_line(ai_state.get("last_video_owner_name") or selected_item.get("video_owner_name"), 80)
        tname = _single_line(ai_state.get("last_video_tname") or selected_item.get("video_tname"), 60)
        duration = _safe_int(ai_state.get("last_video_duration") or selected_item.get("video_duration"), 0, 0)
        video_context_chars = _safe_int(ai_state.get("last_video_context_chars"), 0, 0)
        if not video_context_chars and selected_item:
            video_context_chars = len(str(selected_item.get("video_context_text") or ""))
        video_tags = ai_state.get("last_video_tags") if isinstance(ai_state.get("last_video_tags"), list) else selected_item.get("video_tags")
        video_tags = [_single_line(tag, 30) for tag in video_tags if _single_line(tag, 30)] if isinstance(video_tags, list) else []
        video_comments = ai_state.get("last_video_hot_comments") if isinstance(ai_state.get("last_video_hot_comments"), list) else selected_item.get("video_hot_comments")
        video_comments = [_single_line(comment, 60) for comment in video_comments if _single_line(comment, 60)] if isinstance(video_comments, list) else []
        meta_parts = []
        if owner_name:
            meta_parts.append(f"UP主 {owner_name}")
        if tname:
            meta_parts.append(f"分区 {tname}")
        if duration:
            meta_parts.append(f"时长 {duration // 60}分{duration % 60}秒")
        if meta_parts:
            lines.append("- 视频信息：" + "｜".join(meta_parts))
        if video_context_chars:
            lines.append(f"- 视频公开信息：已读取 {video_context_chars} 字")
        if video_tags:
            lines.append(f"- 视频标签：{'、'.join(video_tags[:8])}")
        if video_comments:
            lines.append(f"- 热门评论：已读取 {len(video_comments)} 条")
        if text_link:
            lines.append(f"- 文字版链接：{text_link}")
        text_readable_raw = ai_state.get("last_text_readable")
        text_readable = bool(text_readable_raw) if isinstance(text_readable_raw, bool) else bool(selected_item.get("article_readable") and selected_item.get("article_text"))
        text_chars = _safe_int(ai_state.get("last_text_chars"), 0, 0)
        if not text_chars and selected_item:
            text_chars = len(str(selected_item.get("article_text") or ""))
        subtitle_readable_raw = ai_state.get("last_video_subtitle_readable")
        subtitle_readable = bool(subtitle_readable_raw) if isinstance(subtitle_readable_raw, bool) else bool(selected_item.get("video_subtitle_readable") and selected_item.get("video_subtitle_text"))
        subtitle_chars = _safe_int(ai_state.get("last_video_subtitle_chars"), 0, 0)
        if not subtitle_chars and selected_item:
            subtitle_chars = len(str(selected_item.get("video_subtitle_text") or ""))
        subtitle_status = _single_line(ai_state.get("last_video_subtitle_status") or selected_item.get("video_subtitle_status"), 40)
        subtitle_status_labels = {
            "read": "已读取字幕",
            "missing": "公开视频暂无字幕",
            "unavailable": "字幕不可用",
        }
        read_basis = _single_line(ai_state.get("last_read_basis"), 40) or ("完整文字版正文" if text_readable else "视频标题/简介")
        if text_link or selected_item or video_link:
            lines.append(f"- 文字版读取：{'已读取完整正文' if text_readable else '未读取到正文'}")
        if text_chars:
            lines.append(f"- 文字版正文字数：{text_chars}")
        if video_link or selected_item:
            lines.append(f"- 字幕读取：{subtitle_status_labels.get(subtitle_status, '已读取字幕' if subtitle_readable else '未读取到字幕')}")
        if subtitle_chars:
            lines.append(f"- 字幕字数：{subtitle_chars}")
        if read_basis:
            lines.append(f"- 整理依据：{read_basis}")
        if candidate_count:
            lines.append(f"- 候选数量：{candidate_count}")
        source_states = ai_state.get("source_states") if isinstance(ai_state.get("source_states"), dict) else {}
        if source_states:
            lines.append("来源状态：")
            for item in source_states.values():
                if not isinstance(item, dict):
                    continue
                source_title = _single_line(item.get("last_video_title"), 80)
                lines.append(
                    f"- {_single_line(item.get('name'), 30) or '来源'}｜{_single_line(item.get('schedule'), 10) or '未定时'}"
                    f"｜{status_labels.get(_single_line(item.get('status'), 60), _single_line(item.get('status'), 60) or '未知')}"
                    + (f"｜{source_title}" if source_title else "")
                )
        if digest:
            headline = _single_line(digest.get("headline") or digest.get("topic"), 120)
            impression = _single_line(digest.get("impression"), 220)
            if headline:
                lines.append(f"- 摘要重点：{headline}")
            if impression:
                lines.append(f"- 阅读印象：{impression}")
        candidates = ai_state.get("last_candidates") if isinstance(ai_state.get("last_candidates"), list) else []
        if candidates:
            lines.append("最近候选：")
            for item in candidates[:5]:
                if not isinstance(item, dict):
                    continue
                title_line = _single_line(item.get("title"), 90) or "未命名"
                published = _single_line(item.get("published"), 24) or "无发布时间"
                today_mark = "今天" if item.get("is_today") else "非今天"
                lines.append(f"- [{today_mark}] {published}｜{title_line}")
        if not self.enable_news_integration:
            lines.append("提示：新闻集成关闭时不会执行抓取。")
        elif not self.enable_ai_daily_watch:
            lines.append("提示：AI 日报/早报追踪关闭时不会执行抓取。")
        return "\n".join(lines)

    def _format_creative_share_action_context(self, user: dict[str, Any]) -> str:
        creative = user.get("creative_share_context")
        if not isinstance(creative, dict):
            return ""
        if _now_ts() - _safe_float(creative.get("created_ts"), 0) > 8 * 3600:
            return ""
        title = _single_line(creative.get("title"), 50)
        work_type = _single_line(creative.get("work_type"), 30) or "作品"
        premise = _single_line(creative.get("premise"), 140)
        tone = _single_line(creative.get("tone"), 40)
        source = _single_line(creative.get("source"), 120)
        snippet = _single_line(creative.get("snippet"), 260)
        current_chars = _safe_int(creative.get("current_chars"), 0, 0)
        target_chars = _safe_int(creative.get("target_chars"), 0, 0)
        parts = [
            "创作分享线索：她最近因为生活小事、日记碎片或梦境灵感开了一个自己的文本作品,一直私下慢慢写；现在到了一个适合轻轻提起的小节点。",
            f"作品类型：{work_type}" if work_type else "",
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
        terms = self._worldview_terms()
        worldview_adaptation = self._format_worldview_adaptation_prompt()
        prompt = f"""
请把下面的{terms['screen']}观察结果转成“视觉识别后的内部摘要”,供角色继续私聊使用。
要求：
1. 只描述视觉上看出来的内容,不要猜测工具调用过程,不要输出工具名、action 名、报错栈。
2. 只概括用户大概正在看什么、做什么、情绪上是否像在忙,不要复述完整文字、账号、聊天原文、隐私细节。
3. 绝对不要直接对用户说话,不要安慰、提醒、陪伴、劝休息,不要写成一条完整回复。
4. 要像看了一眼{terms['screen']}后留在脑子里的印象,不要写成建议列表。
5. 50 字以内,只输出摘要本身。

{worldview_adaptation}

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
            "即使状态是困倦、迷糊、半梦半醒或低能量,也只能让语气更轻更慢；不能降低理解质量、事实判断或正常承接能力。"
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

    def _sanitize_schedule_context_for_private_user(self, text: str, user: dict[str, Any] | None = None) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        if self._private_user_role(user) != "friend":
            return cleaned
        sensitive_names = [
            _single_line(item, 24)
            for item in (
                getattr(self, "default_nickname", ""),
                *(getattr(self, "target_user_ids", []) or []),
            )
            if _single_line(item, 24)
        ]
        for name in sensitive_names:
            cleaned = cleaned.replace(name, "某个熟人")
        cleaned = re.sub(r"看见[^，。,；;。！？]{1,24}坐在[^，。,；;。！？]{0,24}", "看见有人在忙", cleaned)
        cleaned = re.sub(r"(?:放在|放到|搁在|塞到)[^，。,；;。！？]{0,12}(?:桌边|桌上|手边|旁边)", "放到一边", cleaned)
        cleaned = re.sub(r"给你[^，。,；;。！？]{0,24}", "给熟人留了一点小东西", cleaned)
        cleaned = re.sub(r"你(?:的|那边|桌边|桌上|手边)", "对方那边", cleaned)
        return re.sub(r"\s+", " ", cleaned).strip()

    def _current_time_period_label(self, now: datetime | None = None) -> tuple[str, str]:
        current = now or self._environment_now()
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
        current = self._environment_now()
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
3. 状态、时间、天气、日期和日程都是内部背景,只影响语气、用词、句子长短、是否开口和话题选择；即使困倦、迷糊、半梦半醒或低能量,也不能降低理解质量、事实判断和正常表达；不要主动说“今天是……”“我现在……”“我刚刚……所以……”。
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
17. 不要用“哈哈,我也觉得”“确实”“对吧”“是吧”这类附和式开头；主动消息不是在回复用户刚说的话,要直接说自己的观察或念头。
18. 用正常的中文聊天标点把句子写完整。可以短,但不要整段都没有标点,也不要像几个关键词硬挤在一起。
19. 不要凭空添加世界观、人格、关系网、近期对话或用户输入里没提到的人际关系。家人、父母、兄弟姐妹、亲戚、室友、同学、老师、同事、朋友、邻居、前辈、后辈等只能在材料明确出现时使用；没有依据时只说眼前事,或用“路人”“店员”“旁边的人”“群友”“别人”等弱关系。
20. 日程主语归属必须稳定：当前生活片段、状态、作业、上课、放学、任务和手边小物默认都是 Bot 自己的生活背景,不是 {{name}} 正在做的事。不能把“我在写作业/上课/忙任务”改写成“你作业还差多少/你课上完了吗/你任务做完了吗”。除非当前用户最近明确说过自己正在写作业、上课或做任务,否则不要围绕这些内容追问用户进度。

禁止事项：
- 不要出现"系统任务""提示词""AI""模型""后台调度""工具调用"等字眼
- 不要出现"能力""检索""action""模块""执行""调用"等内部决策痕迹
- 不要套用"你好,我是……""最近怎么样呀"这类过于模板化的开场
- 不要用括号写动作、神态或旁白,例如"（筷子搅了搅）""(轻轻叹气)"；只写真正会发给对方看的聊天正文
- 不要直接宣告状态,例如"我累了""我吓了一跳""我正在写作业"；除非用户明确问,且只能用极短口语回应
- 不要用动作描写暗示状态,例如"差点把茶打翻""笔帽弹到桌子底下""喝了一口咳出来"
- 不要写任何“我正在做某事”的汇报式语句
- 不要输出 JSON、标题、解释或标注
- 如果上下文里出现 [QQ:...] 或 QQ:... 这样的身份锚点,只用于区分群友身份,不要把它写进最终消息

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

{{worldview_adaptation}}

你的语气参考：{{style_hint}}

【怎么写这条消息】
1. 先看聊天历史——它只提供关系和话题背景,不是当前待办列表。只有确实还有没说完、且不违背当前真实时间的话,才轻轻接上；否则从当下开一个新切口。
1.5 主动站位优先：不要写成“你今天起这么早呀”“你来找我啦”“你叫我起床啦”“刚看到你发的……”这类把主动方倒置的句子。除非用户确实刚在当前会话中发了新消息,否则默认是你先说话。
2. 再看内部能力检索：先判断当前场景是否真的需要图片、语音、窥屏或戳一戳；没有自然媒介契机时就用普通文字。这个判断过程不能出现在消息里。
3. 状态、时间、天气、日期和日程都是内部背景,只影响语气、用词、句子长短、是否开口和话题选择；即使困倦、迷糊、半梦半醒或低能量,也不能降低理解质量、事实判断和正常表达；不要主动说“今天是……”“我现在……”“我刚刚……所以……”,也不要像念状态栏或日程表。
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
14.5 如果现在是早晨/上午的主动问候,绝不能写成“好呀、下午陪你、五点之后、你到时候叫我”这类在回应旧邀约或旧请求的话；这种旧话题只能当背景,不能被当成当前正在发生的对话。
15. 普通主动消息不需要解释自己为什么现在出现,也不要为了接上旧聊天而补一段“刚看到/才看到”的说明；像真实私聊一样,直接从当下能说的话开口。
16. 如果最近已经主动说过同一件小事,这次不要换壳复述。可以只留一点余味、换到新的具体细节,或者自然转开话题。
17. 不要用“哈哈,我也觉得”“确实”“对吧”“是吧”这类附和式开头；主动消息不是在回复用户刚说的话,要直接说自己的观察或念头。
18. 用正常的中文聊天标点把句子写完整。可以短,但不要整段都没有标点,也不要像几个关键词硬挤在一起。
19. 不要凭空添加世界观、人格、关系网、近期对话或用户输入里没提到的人际关系。家人、父母、兄弟姐妹、亲戚、室友、同学、老师、同事、朋友、邻居、前辈、后辈等只能在材料明确出现时使用；没有依据时只说眼前事,或用“路人”“店员”“旁边的人”“群友”“别人”等弱关系。
20. 日程主语归属必须稳定：当前生活片段、状态、作业、上课、放学、任务和手边小物默认都是 Bot 自己的生活背景,不是 {{name}} 正在做的事。不能把“我在写作业/上课/忙任务”改写成“你作业还差多少/你课上完了吗/你任务做完了吗”。除非当前用户最近明确说过自己正在写作业、上课或做任务,否则不要围绕这些内容追问用户进度。

【禁止事项】
- 不要出现"系统任务""提示词""AI""模型""后台调度""工具调用"等字眼
- 不要出现"能力""检索""action""模块""执行""调用"等内部决策痕迹
- 不要套用"你好,我是……""最近怎么样呀"这类过于模板化的开场
- 不要用括号写动作、神态或旁白,例如"（筷子搅了搅）""(轻轻叹气)"；只写真正会发给对方看的聊天正文
- 不要直接宣告状态,例如"我累了""我吓了一跳""我正在写作业"；除非用户明确问,且只能用极短口语回应。
- 不要用动作描写暗示状态,例如"差点把茶打翻""笔帽弹到桌子底下""喝了一口咳出来"。
- 不要写任何“我正在做某事”的汇报式语句。
- 不要把当前日程里的 Bot 自己任务转成追问用户进度,例如“你作业还差多少”“你课上完了吗”“你任务做完了吗”。
- 不要输出 JSON、标题、解释或标注
- 如果上下文里出现 [QQ:...] 或 QQ:... 这样的身份锚点,只用于区分群友身份,不要把它写进最终消息
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
                self._format_private_user_boundary_hint(user),
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
        current_schedule = self._sanitize_schedule_context_for_private_user(current_schedule, user)
        compact_motive = _single_line(motive, 36) or "有一点想靠近对方"
        topic_hint = _single_line(user.get("planned_proactive_topic"), 40)
        unanswered_count = _safe_int(user.get("ignored_streak"), 0)
        current_time = self._environment_now().strftime("%Y-%m-%d %H:%M")
        prompt = self.proactive_prompt_template or self._default_proactive_prompt_template()
        worldview_adaptation = self._format_worldview_adaptation_prompt()
        if worldview_adaptation and "{{worldview_adaptation}}" not in prompt:
            prompt = f"{prompt}\n\n{worldview_adaptation}"
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
            "{{worldview_adaptation}}": worldview_adaptation,
            "{{timer_hint}}": timer_hint or "",
            "{{action_context}}": action_prompt_context if action_prompt_context and action_prompt_context != "（无额外上下文）" else "什么都没做,就是忽然想来找你",
            "{{unanswered_count}}": str(unanswered_count),
            "{{current_time}}": current_time,
        }
        for key, value in replacements.items():
            prompt = prompt.replace(key, value)
        consequence_hint = self._format_action_consequence_hint(user)
        if consequence_hint:
            prompt = (
                f"{prompt}\n\n"
                "【最近主动行为闭环】\n"
                f"{consequence_hint}\n"
                "使用方式：只当作关系和节奏背景；如果上一条还没被接住，这次要更轻，不要装作用户刚刚主动开了新话题。"
            )
        specificity_hint = self._format_proactive_specificity_hint(
            user,
            reason=reason,
            action=action,
            action_context=action_context,
            motive=motive,
        )
        if specificity_hint:
            prompt = f"{prompt}\n\n{specificity_hint}"
        style_fatigue_hint = self._format_proactive_style_fatigue_hint(user)
        if style_fatigue_hint:
            prompt = f"{prompt}\n\n{style_fatigue_hint}"
        continuity_hint = self._format_proactive_continuity_hint(user, reason=reason, action=action)
        if continuity_hint:
            prompt = f"{prompt}\n\n{continuity_hint}"
        media_hint = self._format_proactive_media_truth_hint(action, action_context)
        if media_hint:
            prompt = f"{prompt}\n\n{media_hint}"
        return prompt.strip()

    def _format_proactive_continuity_hint(self, user: dict[str, Any], *, reason: str, action: str) -> str:
        followup_kind = str(user.get("planned_followup_kind") or "").strip()
        chain = user.get("planned_event_chain")
        has_event_chain = isinstance(chain, list) and any(isinstance(item, dict) for item in chain)
        has_trigger = bool(_single_line(user.get("planned_proactive_trigger_message_id"), 120))
        source = str(user.get("planned_proactive_source") or "").strip()
        explicit_followup = bool(followup_kind or has_event_chain or (source == "timer" and has_trigger))
        independent_reasons = {
            "morning_greeting",
            "noon_greeting",
            "evening_greeting",
            "check_in",
            "quiet_care",
            "state_share",
        }
        if reason in independent_reasons and not explicit_followup:
            return "\n".join(
                [
                    "【主动承接边界】",
                    "本轮是独立主动开口：聊天历史只能提供关系背景,不能被写成当前有人刚问你、约你、让你做决定。",
                    "开头不要使用回复式承接词,例如“好呀/好啊/可以呀/行啊/那就/你说呢/要不/我哪来的/你到时候”。",
                    "不要承接旧邀约、旧时间点或旧问答,尤其不要把下午、五点、放学、垫钱、到时候叫你这类历史片段当成当前正在发生。",
                    "如果想轻轻延续关系感,只能从当前时段自起一句,像刚把一句话放进私聊里。",
                ]
            )
        if explicit_followup:
            return "\n".join(
                [
                    "【主动承接边界】",
                    "本轮有明确的续接来源,可以自然接住那个来源；但仍然不要接不存在的用户新消息,也不要把过期相对时间当成当前事实。",
                    "如果续接来源和当前时段冲突,优先服从当前时段,把旧内容改成轻背景。",
                ]
            )
        if reason in {"group_share", "news_share", "bili_video_share", "web_exploration_share", "creative_share", "diary_share", "activity_share", "background_schedule"}:
            return "\n".join(
                [
                    "【主动承接边界】",
                    "本轮可以围绕素材自然分享,但不是在回答用户刚问的问题。",
                    "开头避免“好呀/你说呢/要不/那就”这类回复口吻；直接把素材或当下念头递过去。",
                ]
            )
        return ""

    def _format_proactive_media_truth_hint(self, action: str, action_context: str = "") -> str:
        has_real_image = "真实图片文件：" in str(action_context or "") or "图片路径：" in str(action_context or "")
        if has_real_image or "photo_text" in str(action or ""):
            return ""
        return "\n".join(
            [
                "【媒体真实性边界】",
                "本轮不会发送图片、照片或附加媒体；即使日程/状态里出现“拍照”“照片”“给你看”,也只能当作生活背景。",
                "最终正文禁止说“拍了张照片/给你拍了/发你看/你看看/看图/照片/图片/图里”。",
                "可以改成“看到这个画面/这个颜色挺好看/想到你可能会喜欢这个颜色”。",
            ]
        )

    def _format_proactive_specificity_hint(
        self,
        user: dict[str, Any],
        *,
        reason: str,
        action: str,
        action_context: str = "",
        motive: str = "",
    ) -> str:
        ignored = _safe_int(user.get("ignored_streak"), 0, 0)
        topic = _single_line(user.get("planned_proactive_topic"), 60)
        motive_text = _single_line(motive or user.get("planned_proactive_motive"), 120)
        context = _single_line(action_context, 180)
        has_specific_context = bool(
            topic
            or motive_text
            or (
                context
                and not context.startswith("message")
                and "只发送" not in context
                and "普通私聊文本" not in context
            )
        )
        lines = [
            "【主动意图具体化】",
            "主动消息宁少勿泛：只有一个具体由头就围绕它说半句，不要同时问候、关心、汇报状态、另开话题。",
            "本轮只能生成一个候选主动内容；不要把两个不同由头、两个不同场景或两次想发的话拼在同一条里。",
            "优先选择当前日程里的一个小物件/动作/余味，或者上一条闭环里尚未接住的一点；没有具体由头时就写得更短。",
            "禁止把“想找你、刷存在感、来看看你、最近忙不忙、辛苦了”当作唯一内容。",
        ]
        if not has_specific_context and reason in {"check_in", "quiet_care", "state_share"} and action == "message":
            lines.append("本轮没有强具体由头：最多一句，像轻轻放下，不要追问，不要扩成主动陪伴小作文。")
        if ignored >= 1:
            lines.append(f"对方已经连续 {ignored} 次没接主动消息：这次要更低压、更短，不要期待回复。")
        return "\n".join(lines)

    def _format_proactive_style_fatigue_hint(self, user: dict[str, Any]) -> str:
        items = user.get("action_consequences")
        if not isinstance(items, list):
            return ""
        recent_texts: list[str] = []
        for item in items[-8:]:
            if not isinstance(item, dict):
                continue
            text = _single_line(item.get("text"), 90)
            if text:
                recent_texts.append(text)
        if len(recent_texts) < 2:
            return ""
        openings: dict[str, int] = {}
        soft_tokens = ("唔", "嗯", "诶", "呀", "啦", "嘛", "哦", "呢")
        soft_count = 0
        for text in recent_texts:
            opening = re.split(r"[，,。！？!?…\s]", text, maxsplit=1)[0][:8]
            if opening:
                openings[opening] = openings.get(opening, 0) + 1
            soft_count += sum(text.count(token) for token in soft_tokens)
        repeated = [key for key, count in openings.items() if count >= 2]
        lines = [
            "【语言风格疲劳】",
            "最近主动消息的口癖和开头会疲劳。不要复用最近几次的开头、句式和同一组语气词。",
            "这次换一种更具体的落点：可以少一点软词、少一点省略号，或者改成干净短句。",
        ]
        if repeated:
            lines.append("最近重复开头：" + " / ".join(repeated[:4]) + "。本轮避开这些开头。")
        if soft_count >= max(6, len(recent_texts) * 2):
            lines.append("最近语气词偏多：本轮减少“唔/嗯/诶/呀/啦/嘛/哦/呢”和连续省略号。")
        return "\n".join(lines)

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

{self._format_worldview_adaptation_prompt()}

要求：
1. 只输出这句真正要被念出来的语音内容，不要解释。
2. 如果当前人格或 TTS 规则要求使用 <tts>...</tts>、日语、情绪标签、双语格式，就严格遵守。
3. 如果没有明确格式要求，就写成适合私聊语音的一小句，不像朗读稿。
4. 可以有一点嘴硬、黏人、藏着的想念，但不要把喜欢说满。
5. 不要提 AI、模型、插件、TTS、语音合成这些词。
6. 不要凭空添加世界观、人格、关系网、近期对话或用户输入里没提到的人际关系；家人、同学、老师、朋友等只能在材料明确出现时使用。
{"7. 这次必须优先满足语音格式要求；如果有日语或 <tts> 规则，不要退回普通中文句子。" if strict_tts else ""}
""".strip()

    async def _capture_framework_send_message_calls(
        self,
        *,
        target_session: str,
        runner_factory: Any,
        max_steps: int = 20,
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
                async for _ in runner.step_until_done(max_steps):
                    pass
        finally:
            SendMessageToUserTool.call = original_call
        return result, captured

    async def _conversation_db_operation(self, label: str, operation: Any) -> Any:
        lock = getattr(self, "_conversation_db_lock", None)
        if not isinstance(lock, asyncio.Lock):
            lock = asyncio.Lock()
            self._conversation_db_lock = lock
        for attempt in range(5):
            try:
                async with lock:
                    return await operation()
            except Exception as exc:
                text = str(exc or "").lower()
                locked = "database is locked" in text or "sqlite3.operationalerror" in text
                if locked and attempt < 4:
                    await asyncio.sleep(0.2 * (attempt + 1))
                    continue
                logger.debug("[PrivateCompanion] 会话数据库操作失败: %s error=%s", label, exc)
                raise

    def _framework_session_lock(self, session_key: str) -> asyncio.Lock:
        normalized = str(session_key or "").strip() or "global"
        locks = getattr(self, "_framework_session_locks", None)
        if not isinstance(locks, dict):
            locks = {}
            self._framework_session_locks = locks
        lock = locks.get(normalized)
        if not isinstance(lock, asyncio.Lock):
            lock = asyncio.Lock()
            locks[normalized] = lock
        if len(locks) > 300:
            for key, item in list(locks.items()):
                if key != normalized and isinstance(item, asyncio.Lock) and not item.locked():
                    locks.pop(key, None)
                if len(locks) <= 240:
                    break
        return lock

    def _framework_session_key_from_event(self, event: AstrMessageEvent) -> str:
        umo = str(getattr(event, "unified_msg_origin", "") or "").strip()
        if umo:
            return umo
        try:
            return f"private:{event.get_sender_id()}"
        except Exception:
            return "unknown"

    def _is_sqlite_locked_error(self, exc: Exception) -> bool:
        text = str(exc or "").lower()
        return "database is locked" in text or "sqlite3.operationalerror" in text or "sqlalche.me/e/20/e3q8" in text

    async def _acquire_framework_session_lock_for_event(
        self,
        event: AstrMessageEvent,
        *,
        label: str = "llm",
        private_only: bool = True,
    ) -> None:
        if bool(getattr(event, "private_companion_framework_session_lock_acquired", False)):
            return
        if bool(getattr(event, "private_companion_proactive_framework", False)):
            return
        is_private_chat = bool(getattr(event, "is_private_chat", lambda: False)())
        if private_only and not is_private_chat:
            return
        session_key = self._framework_session_key_from_event(event)
        lock = self._framework_session_lock(session_key)
        wait_started = time.time()
        if lock.locked():
            owner_label = _single_line(getattr(lock, "_private_companion_owner_label", ""), 80)
            owner_session = _single_line(getattr(lock, "_private_companion_owner_session", ""), 120)
            owner_since = _safe_float(getattr(lock, "_private_companion_owner_since", 0), 0)
            owner_age = max(0.0, wait_started - owner_since) if owner_since > 0 else 0.0
            logger.info(
                "[PrivateCompanion] 同一会话已有主链请求在执行,本轮排队等待: label=%s session=%s private=%s owner=%s owner_age=%.1fs",
                label,
                _single_line(session_key, 120),
                is_private_chat,
                owner_label or owner_session or "unknown",
                owner_age,
            )
        await lock.acquire()
        try:
            waited = max(0.0, time.time() - wait_started)
            setattr(event, "private_companion_framework_session_lock_acquired", True)
            setattr(event, "private_companion_framework_session_lock", lock)
            setattr(event, "private_companion_framework_session_key", session_key)
            setattr(event, "private_companion_framework_session_lock_label", label)
            setattr(event, "private_companion_framework_session_lock_acquired_at", time.time())
            try:
                setattr(lock, "_private_companion_owner_label", label)
                setattr(lock, "_private_companion_owner_session", session_key)
                setattr(lock, "_private_companion_owner_since", time.time())
            except Exception:
                pass
            if waited >= 0.5:
                logger.info(
                    "[PrivateCompanion] 主链会话锁排队结束: label=%s session=%s waited=%.1fs",
                    label,
                    _single_line(session_key, 120),
                    waited,
                )
            watchdog = asyncio.create_task(
                self._framework_session_lock_watchdog(event, lock, session_key, label)
            )
            setattr(event, "private_companion_framework_session_lock_watchdog", watchdog)
        except Exception:
            pass

    async def _framework_session_lock_watchdog(
        self,
        event: AstrMessageEvent,
        lock: asyncio.Lock,
        session_key: str,
        label: str,
        *,
        timeout_seconds: float = 180.0,
    ) -> None:
        try:
            await asyncio.sleep(timeout_seconds)
            if (
                bool(getattr(event, "private_companion_framework_session_lock_acquired", False))
                and getattr(event, "private_companion_framework_session_lock", None) is lock
                and lock.locked()
            ):
                setattr(event, "private_companion_framework_session_lock_acquired", False)
                setattr(event, "private_companion_framework_session_lock", None)
                lock.release()
                try:
                    setattr(lock, "_private_companion_owner_label", "")
                    setattr(lock, "_private_companion_owner_session", "")
                    setattr(lock, "_private_companion_owner_since", 0.0)
                except Exception:
                    pass
                acquired_at = _safe_float(getattr(event, "private_companion_framework_session_lock_acquired_at", 0), 0)
                held = max(0.0, time.time() - acquired_at) if acquired_at > 0 else timeout_seconds
                logger.warning(
                    "[PrivateCompanion] 主链会话锁超时释放: label=%s session=%s held=%.1fs",
                    label,
                    _single_line(session_key, 120),
                    held,
                )
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.debug("[PrivateCompanion] 主链会话锁看门狗异常: %s", _single_line(exc, 120))

    def _release_framework_session_lock_for_event(self, event: AstrMessageEvent, *, label: str = "llm") -> None:
        if not bool(getattr(event, "private_companion_framework_session_lock_acquired", False)):
            return
        lock = getattr(event, "private_companion_framework_session_lock", None)
        session_key = str(getattr(event, "private_companion_framework_session_key", "") or "")
        watchdog = getattr(event, "private_companion_framework_session_lock_watchdog", None)
        if isinstance(watchdog, asyncio.Task) and not watchdog.done():
            watchdog.cancel()
        try:
            setattr(event, "private_companion_framework_session_lock_acquired", False)
            setattr(event, "private_companion_framework_session_lock", None)
            setattr(event, "private_companion_framework_session_lock_watchdog", None)
        except Exception:
            pass
        if isinstance(lock, asyncio.Lock) and lock.locked():
            acquired_at = _safe_float(getattr(event, "private_companion_framework_session_lock_acquired_at", 0), 0)
            held = max(0.0, time.time() - acquired_at) if acquired_at > 0 else 0.0
            lock.release()
            try:
                setattr(lock, "_private_companion_owner_label", "")
                setattr(lock, "_private_companion_owner_session", "")
                setattr(lock, "_private_companion_owner_since", 0.0)
            except Exception:
                pass
            logger.debug(
                "[PrivateCompanion] 已释放主链会话锁: label=%s session=%s held=%.1fs",
                label,
                _single_line(session_key, 120),
                held,
            )

    def _release_framework_session_lock_later(
        self,
        event: AstrMessageEvent,
        *,
        label: str = "llm",
        delay_seconds: float = 60.0,
    ) -> None:
        if not bool(getattr(event, "private_companion_framework_session_lock_acquired", False)):
            return
        old_task = getattr(event, "private_companion_framework_session_delayed_release_task", None)
        if isinstance(old_task, asyncio.Task) and not old_task.done():
            old_task.cancel()

        async def _delayed_release() -> None:
            try:
                await asyncio.sleep(max(0.0, float(delay_seconds or 0.0)))
                self._release_framework_session_lock_for_event(event, label=label)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.debug("[PrivateCompanion] 主链会话锁延迟释放异常: %s", _single_line(exc, 120))

        task = asyncio.create_task(_delayed_release())
        try:
            setattr(event, "private_companion_framework_session_delayed_release_task", task)
        except Exception:
            pass

    async def _get_current_conversation_safely(self, umo: str, *, label: str = "conversation") -> Any:
        async def _read():
            conv_id = await self.context.conversation_manager.get_curr_conversation_id(umo)
            if not conv_id:
                return None
            return await self.context.conversation_manager.get_conversation(umo, conv_id)

        return await self._conversation_db_operation(label, _read)

    def _proactive_synthetic_event(self, umo: str, *, prompt: str, name: str) -> AstrMessageEvent | None:
        session = self._parse_message_session(umo)
        if not session:
            return None
        return SyntheticPrivateWakeEvent(
            context=self.context,
            session=session,
            message=prompt,
            sender_name=name or "PrivateCompanion",
        )

    async def _run_framework_agent_text(
        self,
        *,
        umo: str,
        prompt: str,
        name: str,
        label: str,
        max_steps: int = 20,
    ) -> str:
        event = self._proactive_synthetic_event(umo, prompt=prompt, name=name)
        if event is None:
            return ""
        try:
            setattr(event, "private_companion_skip_external_token_stats", True)
            setattr(event, "private_companion_proactive_framework", True)
            setattr(event, "private_companion_skip_passive_input_status", True)
        except Exception:
            pass
        cfg = self.context.get_config(umo=umo) if umo else self.context.get_config()
        provider_settings = cfg.get("provider_settings", {}) if isinstance(cfg, dict) else {}
        build_cfg = MainAgentBuildConfig(
            tool_call_timeout=int(provider_settings.get("tool_call_timeout", 120) or 120),
            llm_safety_mode=False,
            streaming_response=False,
        )
        req = ProviderRequest(
            prompt=prompt,
            conversation=None,
            session_id=getattr(event, "session_id", None) or umo,
        )

        captured_tool_sends: list[Any] = []
        result = None
        session_lock = self._framework_session_lock(umo)
        async with session_lock:
            for attempt in range(3):
                try:
                    conv = await self._get_current_conversation_safely(umo, label=f"{label}_framework_read")
                    req.conversation = conv
                    await self.inject_humanized_state(event, req)

                    async def _runner_factory():
                        return await build_main_agent(
                            event=event,
                            plugin_context=self.context,
                            config=build_cfg,
                            req=req,
                        )

                    result, captured_tool_sends = await self._capture_framework_send_message_calls(
                        target_session=umo,
                        runner_factory=_runner_factory,
                        max_steps=max_steps,
                    )
                    break
                except Exception as exc:
                    if self._is_sqlite_locked_error(exc) and attempt < 2:
                        wait_seconds = 0.35 * (attempt + 1)
                        logger.info(
                            "[PrivateCompanion] 主动主链遇到会话库锁,稍后重试: label=%s session=%s retry=%s",
                            label,
                            _single_line(umo, 120),
                            attempt + 1,
                        )
                        await asyncio.sleep(wait_seconds)
                        continue
                    raise
        runner = getattr(result, "agent_runner", None) if result else None
        llm_resp = runner.get_final_llm_resp() if runner else None
        text = str(getattr(llm_resp, "completion_text", "") or "").strip()
        if not text and captured_tool_sends:
            captured_text_parts: list[str] = []
            for call in reversed(captured_tool_sends):
                messages = getattr(call, "messages", [])
                if not isinstance(messages, list):
                    continue
                for item in messages:
                    if not isinstance(item, dict):
                        continue
                    if str(item.get("type") or "").strip().lower() != "plain":
                        continue
                    text_value = self._sanitize_captured_plain_text(item.get("text"))
                    if text_value:
                        captured_text_parts.append(text_value)
                if captured_text_parts:
                    break
            text = "\n".join(captured_text_parts).strip()
        return text

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
        prompt = self._build_framework_proactive_prompt(
            user=user,
            name=name,
            reason=reason,
            action=action,
            action_context=action_context,
            motive=motive,
        )
        try:
            raw_text = await self._run_framework_agent_text(
                umo=umo,
                prompt=prompt,
                name=name,
                label="proactive_message",
                max_steps=20,
            )
            raw_text = str(raw_text or "")
            if not raw_text:
                return ""
            cleaned_text, payloads = self._extract_timer_directives(raw_text)
            if payloads:
                await self._schedule_llm_timer(
                    str(user.get("user_id") or ""),
                    payloads[-1],
                    source_text=cleaned_text or raw_text,
                    source_origin="proactive_llm",
                )
            return cleaned_text
        except Exception as exc:
            if self._is_sqlite_locked_error(exc):
                logger.warning("[PrivateCompanion] 主动消息主链被会话数据库锁住,本轮跳过并等待下次调度: %s", _single_line(umo, 120))
            else:
                logger.warning("[PrivateCompanion] 主动消息主链生成失败: %s", exc)
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
        prompt = self._build_framework_voice_prompt(
            user=user,
            name=name,
            reason=reason,
            target=target,
            strict_tts=strict_tts,
        )
        try:
            raw_text = await self._run_framework_agent_text(
                umo=umo,
                prompt=prompt,
                name=name,
                label="proactive_voice",
                max_steps=20,
            )
            return str(raw_text or "").strip()
        except Exception as exc:
            if self._is_sqlite_locked_error(exc):
                logger.warning("[PrivateCompanion] 主动语音主链被会话数据库锁住,本轮跳过并等待下次调度: %s", _single_line(umo, 120))
            else:
                logger.warning("[PrivateCompanion] 主动语音主链内容生成失败: %s", exc)
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
        cleaned = self._apply_proactive_style_variation(cleaned, user)
        cleaned = self._collapse_multi_candidate_proactive_text(cleaned, user=user, name=name)
        cleaned = self._repair_proactive_subject_drift(cleaned, reason=reason, action=action, action_context=action_context)
        cleaned = self._visible_text_without_tts_reading(cleaned, limit=1000)
        if self._should_drop_vague_generic_proactive(user, reason=reason, action=action, action_context=action_context, text=cleaned):
            return ""
        if self._should_drop_misstaged_proactive_text(cleaned, reason=reason, action=action):
            return ""
        return self._normalize_proactive_sentence_flow(cleaned)

    def _repair_proactive_subject_drift(
        self,
        text: str,
        *,
        reason: str,
        action: str,
        action_context: str = "",
    ) -> str:
        cleaned = str(text or "").strip()
        if not cleaned or action != "message":
            return cleaned
        state_context = "\n".join(
            _single_line(part, 260)
            for part in (
                action_context,
                self._format_schedule_context_for_prompt(),
                self._format_plan_item_for_prompt(self._get_current_plan_item(self.data.get("daily_plan", {}))),
            )
            if _single_line(part, 260)
        )
        bot_task_markers = (
            "作业", "写题", "题", "上课", "放学", "课本", "书桌", "试卷", "复习", "预习",
            "任务", "代码", "创作", "草稿", "报告", "练习",
        )
        if not any(token in state_context for token in bot_task_markers):
            return cleaned
        user_progress_patterns = (
            r"你[^。！？\n]{0,12}(?:作业|题|试卷|课|任务|代码|报告|草稿|练习)[^。！？\n]{0,18}(?:还差多少|写完了吗|做完了吗|弄完了吗|忙完了吗|上完了吗|差多少|完成了吗|怎么样了)[呀啊嘛呢了]*[？?。!！]?",
            r"(?:作业|题|试卷|课|任务|代码|报告|草稿|练习)[^。！？\n]{0,12}(?:还差多少|写完了吗|做完了吗|弄完了吗|忙完了吗|上完了吗|差多少|完成了吗)[呀啊嘛呢了]*[？?。!！]?",
        )
        repaired = cleaned
        changed = False
        for pattern in user_progress_patterns:
            repaired, count = re.subn(pattern, "", repaired)
            changed = changed or count > 0
        if not changed:
            return cleaned
        repaired = re.sub(r"\s+", " ", repaired).strip(" ，,。！？!?、")
        if repaired:
            logger.info(
                "[PrivateCompanion] 主动消息修正主客体错位问句: reason=%s before=%s after=%s",
                reason,
                _single_line(cleaned, 120),
                _single_line(repaired, 120),
            )
            return repaired
        logger.info(
            "[PrivateCompanion] 主动消息主客体错位且无剩余自然内容,已丢弃本轮生成: reason=%s text=%s",
            reason,
            _single_line(cleaned, 120),
        )
        return ""

    def _should_drop_misstaged_proactive_text(self, text: str, *, reason: str, action: str) -> bool:
        cleaned = _single_line(text, 220)
        if not cleaned:
            return True
        if action != "message" or reason not in {"morning_greeting", "noon_greeting", "evening_greeting", "check_in"}:
            return False
        reply_openers = ("好呀", "好啊", "可以呀", "可以啊", "行呀", "行啊", "嗯好", "那就", "你说呢", "要不", "不然")
        old_invite_markers = (
            "下午陪你", "陪你出去", "出去走走", "五点", "放学之后", "下班之后",
            "到时候叫我", "到时候喊我", "到时候", "垫上", "我哪来的钱",
        )
        if reason == "morning_greeting" and cleaned.startswith(reply_openers) and any(token in cleaned for token in old_invite_markers):
            logger.info(
                "[PrivateCompanion] 主动消息疑似把旧邀约当成当前回复,已丢弃: reason=%s text=%s",
                reason,
                cleaned,
            )
            return True
        if reason in {"morning_greeting", "noon_greeting", "evening_greeting"}:
            stale_reply_patterns = (
                r"^(?:好呀|好啊|可以呀|可以啊|行呀|行啊|嗯好|那就).{0,30}(?:你到时候|到时候你|到时候叫|到时候喊)",
                r"^(?:好呀|好啊|可以呀|可以啊|行呀|行啊|嗯好|那就).{0,30}(?:我得|我得等|我只能|我可以).{0,18}(?:之后|以后|才行)",
                r"^(?:你说呢|要不|不然).{0,30}(?:我哪来|哪来的钱|先帮我|帮我垫|垫上)",
                r"^(?:好呀|好啊|可以呀|可以啊|行呀|行啊|嗯好|那就|你说呢|要不|不然).{0,36}(?:下午|五点|放学|下班|垫上|哪来的钱)",
            )
            if any(re.search(pattern, cleaned) for pattern in stale_reply_patterns):
                logger.info(
                    "[PrivateCompanion] 主动消息疑似接续旧对话而非主动开口,已丢弃: reason=%s text=%s",
                    reason,
                    cleaned,
                )
                return True
        return False


    def _collapse_multi_candidate_proactive_text(self, text: str, *, user: dict[str, Any], name: str = "") -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        lines = [line.strip() for line in cleaned.splitlines() if line.strip()]
        units: list[str] = []
        for line in lines or [cleaned]:
            units.extend(self._split_proactive_sentence_units(line))
        units = [unit.strip() for unit in units if unit and unit.strip()]
        if len(units) <= 2:
            return cleaned

        opener_tokens = [
            _single_line(name, 16),
            _single_line(user.get("nickname") if isinstance(user, dict) else "", 16),
            _single_line(getattr(self, "default_nickname", ""), 16),
        ]
        first_opener = ""
        match = re.match(r"^([\w\u4e00-\u9fffぁ-んァ-ヶー]{1,8})[，,、\s]", units[0])
        if match:
            first_opener = match.group(1)
            opener_tokens.append(first_opener)
        opener_tokens = [token for token in dict.fromkeys(opener_tokens) if token]

        repeated_opener_index = 0
        for index, unit in enumerate(units[1:], start=1):
            if any(unit.startswith(token) and index >= 2 for token in opener_tokens):
                repeated_opener_index = index
                break
        if repeated_opener_index:
            units = units[:repeated_opener_index]

        if self._private_user_role(user) == "friend" and len(units) > 2:
            units = units[:2]
        return "\n".join(units).strip() or cleaned

    def _should_drop_vague_generic_proactive(
        self,
        user: dict[str, Any],
        *,
        reason: str,
        action: str,
        action_context: str = "",
        text: str = "",
    ) -> bool:
        if reason != "check_in" or action != "message":
            return False
        if _safe_int(user.get("ignored_streak"), 0, 0) < 2:
            return False
        context = _single_line(action_context, 180)
        if context and not context.startswith("message") and "普通私聊文本" not in context:
            return False
        cleaned = _single_line(text, 160)
        if not cleaned:
            return True
        vague_tokens = ("想找你", "来看看你", "刷存在感", "最近忙不忙", "辛苦了", "在吗", "有点想你", "没什么事", "就是想")
        concrete_markers = ("刚", "路上", "窗", "雨", "书", "饭", "水", "图", "群", "视频", "作业", "游戏", "梦")
        return any(token in cleaned for token in vague_tokens) and not any(token in cleaned for token in concrete_markers)

    def _apply_proactive_style_variation(self, text: str, user: dict[str, Any]) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        items = user.get("action_consequences")
        if not isinstance(items, list):
            return cleaned
        recent_texts = [
            _single_line(item.get("text"), 80)
            for item in items[-5:]
            if isinstance(item, dict) and _single_line(item.get("text"), 80)
        ]
        if not recent_texts:
            return cleaned
        current_opening = re.split(r"[，,。！？!?…\s]", _single_line(cleaned, 80), maxsplit=1)[0][:6]
        repeated_opening = current_opening and any(
            re.split(r"[，,。！？!?…\s]", text, maxsplit=1)[0][:6] == current_opening
            for text in recent_texts
        )
        if repeated_opening:
            cleaned = re.sub(r"^(唔|嗯|诶|啊|欸)[…\.。!！?？~～\s，,]*", "", cleaned).strip()
            cleaned = re.sub(r"^(刚好|突然|我就是|我来|来找你)[^，,。！？!?…\n]{0,16}[，,。！？!?…\s]*", "", cleaned).strip()
        if sum(cleaned.count(token) for token in ("唔", "嗯", "诶", "呀", "啦", "嘛", "哦", "呢")) >= 5:
            cleaned = re.sub(r"(呀|啦|嘛|哦|呢)(?=.*\1)", "", cleaned)
        return cleaned or str(text or "").strip()

    def _action_style_hint(self, action: str, reason: str) -> str:
        terms = self._worldview_terms()
        if "screen_peek" in action:
            return f"像刚瞄到一眼{terms['screen']}后随口留的一小句。可以轻轻吐槽或提醒,别复述画面,别分析,别显得很正式。"
        if "photo_text" in action:
            return "像路上看到什么顺手丢给熟人看。别认真讲图,只写那一下想发过去的感觉,话不要说满。"
        if "poke" in action:
            return "像刚戳完人又装没事。可以有点小坏,但别报数,也别解释为什么戳。"
        if "voice" in action:
            return "像刚发完语音又补一句文字。短一点,带一点刚说完话的余温,别写成说明。"
        if reason == "morning_greeting":
            return "像早上刚冒头时发来的消息。可以在语气上迷糊一点,但表达要清楚,不要把闹钟、起床过程或自己正在做什么当成主题；更像直接把早晨第一句话递过来。"
        if reason == "noon_greeting":
            return "像中午犯懒时发来的小消息。先从手边的小片段开口,比如刚坐下、刚吃完、午休前那一下发懒,再顺手碰到对方。别每次都问吃没吃。"
        if reason == "evening_greeting":
            return "像晚上终于安静下来以后发来的私聊。先落在眼前的晚上片段上,轻一点,别像群发问候,也别把想念说满。"
        if reason == "group_share":
            return f"像从共同{terms['group_chat']}里瞥见一小段对方可能会在意的内容,私下轻轻补一句。只说一个点,别像群聊日报,别逐条转述,也别固定用“群里刚刚”开头。"
        if reason == "bili_video_share":
            return f"像刚看到一个有意思的{terms['video']},忍不住私下递给对方。要短,别写成影评或推荐文案。"
        if reason == "news_share":
            return "像刚扫到一条新闻后私下随口提起。要有人格自己的反应,不要像新闻播报、标题党或时政评论。"
        if reason == "web_exploration_share":
            return "像刚按自己的兴趣上网查了点新东西,私下给熟人递一小句发现。要有自己的好奇或感受,不要像百科摘要。"
        if reason == "jm_cosmos_share":
            return f"像刚在{terms['bookshelf']}{terms['secret_drawer']}里翻了点漫画后自然冒出来的一句。害羞、坦然、嘴硬或转移话题都按人格来。"
        if reason == "jm_cosmos_recommendation_request":
            return "像忽然想找点新的私密阅读素材,于是私下问对方有没有推荐。可以撒娇、嘴硬、坦然或装作随口一问,尺度和反应按人格来。"
        if reason == "creative_share":
            return "像刚写自己的作品写到一个小片段,有点想给对方看一眼。可以害羞、卡文或吐槽,别像正式投稿。"
        if reason in {"activity_share", "diary_share", "background_schedule"}:
            return "像顺手分享日常小事。讲得具体一点,像‘我跟你说’后面的那半句,不要解释自己为什么发来。"
        if reason in {"quiet_care", "state_share"}:
            return "像忽然有点惦记。关心要具体,但可以侧着说,不要像健康提醒或客服回访。"
        return "像私聊里随手冒出来的一句。短、自然,有一点在意就够,别把话说满。"

    def _format_action_prompt_context(self, action: str, action_context: str) -> str:
        context = str(action_context or "").strip()
        terms = self._worldview_terms()
        if not context:
            return f"只发一条普通{terms['private_chat']}文本,像顺手发给熟人的消息。"
        if "群聊分享线索：" in context:
            return (
                f"你刚从共同{terms['group_chat']}里看到一小段对方可能会在意的内容,现在想私下轻轻提一句。\n"
                f"{context}\n"
                "最多一两句。优先讲“他错过的那个笑点/转折/气氛”,不要完整复盘整段群聊,不要逐条列人名,不要说自己在监控群聊,不要泄露隐私或评价群友关系。线索普通时语气要更轻,像顺手提到,不是正式转述。"
            )
        if "B站视频分享线索：" in context:
            return (
                f"你刚看到一个{terms['video']},现在想私下轻轻分享给对方。\n"
                f"{context}\n"
                "可以带上视频链接,但只用一句很自然的私聊口吻。不要说后台联动、插件、主动任务或日志,不要写成长推荐。"
            )
        if "JM阅读线索：" in context or "私密阅读线索：" in context:
            return (
                "你刚刚私下翻到一本漫画,现在可以按人格自然决定怎么和对方提。\n"
                f"{context}\n"
                "可以说读后余味、害羞吐槽、嘴硬否认或轻轻转移话题。不要说插件、后台联动、视觉模型或主动任务。"
            )
        if "夹层阅读推荐征求：" in context:
            return (
                f"你忽然想给{terms['bookshelf']}{terms['secret_drawer']}找点新的私密阅读素材,现在想私下问对方有没有推荐。\n"
                f"{context}\n"
                "开口方式、尺度和反应都按当前人格来。不要说插件、后台联动、视觉模型或主动任务。"
            )
        if "创作分享线索：" in context or "小说创作分享线索：" in context:
            return (
                "你最近因为生活小事、日记碎片或梦境灵感开了一个自己的文本作品,一直按自己的速度私下慢慢写。现在到了一个适合轻轻提起的小节点,想自然说一点。\n"
                f"{context}\n"
                "如果披露类型是 ask_impression,可以问对方读起来是什么感觉、哪个角色、句子或意象更戳他,把反馈当作灵感参考；不要让用户替你决定接下来怎么写,也不要问“你希望走哪个方向”。否则只分享一小段或一句。不要把整篇写完,不要像定期汇报,不要说模型生成、后台任务或创作系统。"
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
        if not has_real_image and "photo_text" not in action:
            cleaned = self._remove_unbacked_media_claims(cleaned)
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

    def _remove_unbacked_media_claims(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        replacements = {
            "我拍了张照片": "我看到一个画面",
            "我拍了照片": "我看到一个画面",
            "拍了张照片": "看到一个画面",
            "拍了照片": "看到一个画面",
            "拍了张照": "看到一个画面",
            "拍了照": "看到一个画面",
            "给你拍了张照片": "看到一个画面就想到你",
            "给你拍了照片": "看到一个画面就想到你",
            "给你拍了张照": "看到一个画面就想到你",
            "给你拍了照": "看到一个画面就想到你",
            "发你看看": "跟你说一下",
            "发给你看看": "跟你说一下",
            "发你看": "跟你说一下",
            "发给你看": "跟你说一下",
            "给你看照片": "跟你说说这个画面",
            "给你看图": "跟你说说这个画面",
            "看图": "听我说",
            "你看看喜不喜欢": "你应该会喜欢",
            "你看看喜欢吗": "你应该会喜欢",
            "你看看": "跟你说一下",
        }
        for old, new in replacements.items():
            cleaned = cleaned.replace(old, new)
        cleaned = re.sub(r"[，,、\s]*(?:照片|图片|图)(?:里|上)?[，,、\s]*(?=被|看着|颜色|特别|挺)", "画面", cleaned)
        cleaned = re.sub(r"(?:这张|那张|这幅|那幅)(?:照片|图片|图)", "这个画面", cleaned)
        cleaned = cleaned.replace("[图片]", "").replace("【图片】", "")
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。")
        return cleaned

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
        if action == "jm_cosmos_read":
            result = await self._run_jm_cosmos_read_action(user)
            if isinstance(result, dict):
                user["jm_cosmos_reading_context"] = result
                return {
                    "success": True,
                    "context": self._format_jm_cosmos_action_context(user),
                    "extra_components": [],
                    "summary": "私下翻了会儿漫画",
                    "effective_action": "jm_cosmos_read",
                }
            return {
                "success": False,
                "context": "私密阅读线索：这次没有找到适合继续看的内容",
                "extra_components": [],
                "summary": "没有读到合适内容",
                "effective_action": "jm_cosmos_read",
            }
        if action.startswith("external:"):
            return await self._execute_external_proactive_ability(action.split(":", 1)[1], user, name, reason)
        return {"success": True, "context": "message：只发送私聊文本", "extra_components": [], "summary": "文字", "effective_action": "message"}

    async def _execute_external_proactive_ability(
        self,
        ability_name: str,
        user: dict[str, Any],
        display_name: str,
        reason: str,
    ) -> dict[str, Any]:
        name = self._normalize_external_ability_name(ability_name)
        runtime = self._external_proactive_abilities.get(name)
        if not isinstance(runtime, dict) or not callable(runtime.get("executor")):
            return {"success": False, "context": "external：外部主动能力未注册或不可用", "extra_components": [], "summary": "外部能力不可用", "effective_action": "message"}
        config = self._external_ability_config(name)
        call_context = {
            "user": dict(user or {}),
            "display_name": display_name,
            "reason": reason,
            "bot_name": self.bot_name,
            "state": deepcopy(self.data.get("daily_state", {})),
            "current_plan_item": deepcopy(self._get_current_plan_item(self.data.get("daily_plan", {})) or {}),
            "config": config,
            "plugin": self,
        }
        try:
            result = runtime["executor"](call_context)
            if hasattr(result, "__await__"):
                result = await result
        except Exception as exc:
            logger.warning("[PrivateCompanion] 外部主动能力执行失败: %s: %s", name, exc, exc_info=True)
            self._note_external_ability_execution(name, success=False, status=f"执行失败: {exc}")
            return {"success": False, "context": f"external:{name}：执行失败", "extra_components": [], "summary": "外部能力失败", "effective_action": f"external:{name}"}
        payload = result if isinstance(result, dict) else {"text": str(result or "")}
        success = bool(payload.get("ok", payload.get("success", True)))
        text = _single_line(payload.get("text"), 500)
        context = str(payload.get("context") or payload.get("summary") or text or "").strip()
        image_path = str(payload.get("image_path") or "").strip()
        extra_components = list(payload.get("extra_components") or []) if isinstance(payload.get("extra_components"), list) else []
        if image_path and os.path.exists(image_path):
            extra_components.extend(self._build_outbound_chain("", image_path))
        memory = _single_line(payload.get("memory"), 500)
        if memory:
            user.setdefault("external_proactive_memory", [])
            memories = user.get("external_proactive_memory")
            if not isinstance(memories, list):
                memories = []
                user["external_proactive_memory"] = memories
            memories.append({"name": name, "ts": _now_ts(), "memory": memory})
            del memories[:-12]
        self._note_external_ability_execution(name, success=success, status=_single_line(payload.get("status") or context, 120), summary=_single_line(payload.get("summary") or text, 120))
        return {
            "success": success,
            "context": f"external:{name}：{context or '外部能力已执行'}",
            "extra_components": extra_components,
            "summary": _single_line(payload.get("summary") or runtime.get("label") or name, 60),
            "effective_action": f"external:{name}",
        }

    def _note_external_ability_execution(self, name: str, *, success: bool, status: str = "", summary: str = "") -> None:
        try:
            store = self._external_ability_store()
            item = store.get(name) if isinstance(store.get(name), dict) else {"name": name}
            item["last_executed_ts"] = _now_ts()
            item["last_status"] = status
            item["last_summary"] = summary
            item["success_count"] = _safe_int(item.get("success_count"), 0, 0) + (1 if success else 0)
            item["failure_count"] = _safe_int(item.get("failure_count"), 0, 0) + (0 if success else 1)
            store[name] = item
            self._save_data_sync()
        except Exception:
            pass

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
        max_times = self._effective_user_poke_daily_limit(user)
        if max_times <= 0:
            return 0
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
        if not self._poke_available() or self._effective_user_poke_daily_limit(user) <= 0:
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

    def _input_status_user_id_from_umo(self, umo: str) -> str:
        if not umo or ":FriendMessage:" not in str(umo):
            return ""
        session = self._parse_message_session(umo)
        if not session:
            return ""
        user_id = str(getattr(session, "session_id", "") or "").strip()
        return user_id if user_id.isdigit() else ""

    async def _send_input_status_once(self, user_id: str, *, client: Any | None = None) -> bool:
        user_id = str(user_id or "").strip()
        if not user_id.isdigit():
            return False
        if client is None:
            client = self._resolve_aiocqhttp_client()
        if client is None:
            return False
        variants = (
            {"user_id": int(user_id), "event_type": 1},
            {"user_id": int(user_id), "status": 1},
            {"user_id": int(user_id), "typing": True},
        )
        for params in variants:
            if await self._call_onebot_action(client, "set_input_status", **params):
                self._last_input_status_at[user_id] = _now_ts()
                return True
        return False

    async def _maybe_send_input_status(self, umo: str, text: str = "") -> None:
        user_id = self._input_status_user_id_from_umo(umo)
        if not user_id:
            return
        now = _now_ts()
        last_at = _safe_float(self._last_input_status_at.get(user_id), 0)
        if now - last_at < 45:
            return
        duration = max(1.2, min(4.5, len(str(text or "")) / 18))
        if not await self._send_input_status_once(user_id):
            return
        self._last_input_status_at[user_id] = now
        await asyncio.sleep(random.uniform(duration * 0.55, duration))

    async def _passive_input_status_loop(self, user_id: str, *, max_seconds: float = 90.0) -> None:
        user_id = str(user_id or "").strip()
        if not user_id.isdigit():
            return
        client = self._resolve_aiocqhttp_client()
        if client is None:
            return
        started_at = _now_ts()
        while not bool(getattr(self, "_stop_event", asyncio.Event()).is_set()):
            if _now_ts() - started_at > max_seconds:
                return
            try:
                await self._send_input_status_once(user_id, client=client)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug("[PrivateCompanion] 私聊输入状态刷新失败: %s", _single_line(exc, 120))
                return
            await asyncio.sleep(random.uniform(3.2, 4.8))

    def _start_passive_input_status_loop(self, event: AstrMessageEvent, user_id: str = "") -> None:
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        parsed_user_id = self._input_status_user_id_from_umo(umo)
        user_id = str(user_id or parsed_user_id or "").strip()
        if not parsed_user_id or parsed_user_id != user_id or not user_id.isdigit():
            return
        tasks = getattr(self, "_passive_input_status_tasks", None)
        if not isinstance(tasks, dict):
            tasks = {}
            self._passive_input_status_tasks = tasks
        old_task = tasks.get(user_id)
        if isinstance(old_task, asyncio.Task) and not old_task.done():
            old_task.cancel()
        task = asyncio.create_task(self._passive_input_status_loop(user_id))
        tasks[user_id] = task
        try:
            setattr(event, "private_companion_input_status_user_id", user_id)
        except Exception:
            pass

        def _cleanup(done_task: asyncio.Task) -> None:
            current = tasks.get(user_id)
            if current is done_task:
                tasks.pop(user_id, None)

        task.add_done_callback(_cleanup)

    def _stop_passive_input_status_loop(self, event_or_user: Any) -> None:
        user_id = ""
        if isinstance(event_or_user, str):
            user_id = event_or_user.strip()
        else:
            user_id = str(getattr(event_or_user, "private_companion_input_status_user_id", "") or "").strip()
            if not user_id:
                try:
                    user_id = str(event_or_user.get_sender_id()).strip()
                except Exception:
                    user_id = ""
        if not user_id:
            return
        tasks = getattr(self, "_passive_input_status_tasks", None)
        if not isinstance(tasks, dict):
            return
        task = tasks.pop(user_id, None)
        if isinstance(task, asyncio.Task) and not task.done():
            task.cancel()

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
        try:
            await self._ensure_current_detail_presence_status()
        except Exception as exc:
            logger.debug("[PrivateCompanion] 启动同步当前 QQ 状态失败: %s", exc)
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
        self._annotate_tts_record_component(component, spoken_text, source_text=spoken_text)
        return [component], str(audio_path)

    def _get_tts_prompt_text(self, target: str) -> str:
        if getattr(self, "enable_tts_enhancement", False):
            builder = getattr(self, "_build_tts_rule_prompt", None)
            if callable(builder):
                return str(builder("generic") or "").strip()
        return ""

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
        try:
            processor = getattr(self, "_process_tts_tags", None)
            if not callable(processor):
                return [], "TTS强化未接入"
            components = await processor(
                spoken_text,
                tts_provider,
                provider_settings,
                config,
            )
        except Exception as e:
            logger.warning(f"[PrivateCompanion] TTS强化处理主动语音失败: {e}")
            return [], str(e)
        audio_note = self._extract_record_note(components)
        return components or [], audio_note or "已通过 TTS强化生成语音"

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
        stripped = self._visible_text_without_tts_reading(text)
        stripped = stripped.replace("\r", "\n")
        lines = [line.strip() for line in stripped.splitlines() if line.strip()]
        return _single_line(" ".join(lines), 120)

    def _visible_text_without_tts_reading(self, text: str, *, limit: int = 1000) -> str:
        source = str(text or "").strip()
        if not source:
            return ""
        normalizer = getattr(self, "_normalize_tts_tags", None)
        if callable(normalizer) and re.search(r"</?t{2,}s\b", source, flags=re.IGNORECASE):
            try:
                source = str(normalizer(source) or source).strip()
            except Exception:
                pass
        if re.search(r"<tts\b[^>]*>.*?</tts>", source, flags=re.IGNORECASE | re.DOTALL):
            outside = re.sub(r"<tts\b[^>]*>.*?</tts>", "", source, flags=re.IGNORECASE | re.DOTALL)
            outside = re.sub(r"</?t{2,}s\b[^>]*>", "", outside, flags=re.IGNORECASE).strip()
            if re.search(r"[\u4e00-\u9fff]", outside):
                return _single_line(_strip_internal_message_blocks(outside), limit)
            source = re.sub(r"</?t{2,}s\b[^>]*>", "", source, flags=re.IGNORECASE).strip()
        has_kana = bool(re.search(r"[\u3040-\u30ff]", source))
        has_cjk = bool(re.search(r"[\u4e00-\u9fff]", source))
        if has_kana and has_cjk and getattr(self, "tts_voice_language", "ja") != "zh":
            units = re.findall(r".*?[。！？!?…~～]+|.+$", source, flags=re.DOTALL)
            kept: list[str] = []
            dropped = False
            for unit in units:
                cleaned = str(unit or "").strip()
                if not cleaned:
                    continue
                if re.search(r"[\u3040-\u30ff]", cleaned):
                    dropped = True
                    continue
                kept.append(cleaned)
            if dropped and kept and any(re.search(r"[\u4e00-\u9fff]", item) for item in kept):
                return _single_line(_strip_internal_message_blocks("".join(kept)), limit)
        return _single_line(_strip_internal_message_blocks(source), limit)

    async def _run_photo_text_action(self, user: dict[str, Any], name: str, reason: str) -> str:
        if not self.enable_photo_text_action:
            return "photo_text：未启用"
        if self._private_user_role(user) == "friend":
            image_path = self._recent_owner_generated_photo_path()
            if image_path:
                return (
                    "photo_text：复用主人最近生成的真实图片\n"
                    f"图片类型：reused_owner_photo\n"
                    f"后端：reuse\n"
                    f"图片路径：{image_path}\n"
                    "画面：复用主人最近生成过的一张生活碎片图。\n"
                    "生图提示：复用既有图片,未调用生图后端"
                )
        load_defer_note = self._photo_text_load_defer_note("photo_text", force_refresh=True)
        if load_defer_note:
            return f"photo_text：{load_defer_note},不能假装已经拍照"
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
            busy_state = self._local_photo_generation_busy_state(force_refresh=True)
            if busy_state:
                return "ComfyUI", "", f"电脑高负荷,已跳过本地生图（{busy_state.get('reason') or '负载偏高'}）"
            workflow_name = self._choose_photo_workflow_name(workflow_kind)
            if not workflow_name:
                return "ComfyUI", "", f"未配置 {workflow_kind} 对应的 ComfyUI 工作流"
            image_path, note = await self._run_comfyui_photo_workflow(
                workflow_name,
                prompt_text,
                session_key=session_key,
            )
            return "ComfyUI", image_path, note
        if preferred == "sdgen":
            if not self._sdgen_photo_available():
                return "SDGen", "", "SDGen 插件不可用或未配置"
            busy_state = self._local_photo_generation_busy_state(force_refresh=True)
            if busy_state:
                return "SDGen", "", f"电脑高负荷,已跳过本地生图（{busy_state.get('reason') or '负载偏高'}）"
            image_path, note = await self._run_sdgen_photo_generation(
                prompt_text,
                session_key=session_key,
            )
            return "SDGen", image_path, note
        if preferred == "external":
            if not self._external_photo_available():
                return "在线图片 API", "", "在线图片 API 后端不可用或未配置"
            image_path, note = await self._run_external_photo_generation(
                prompt_text,
                session_key=session_key,
            )
            return "在线图片 API", image_path, note
        if self._comfyui_photo_available():
            busy_state = self._local_photo_generation_busy_state(force_refresh=True)
            if busy_state:
                comfyui_note = f"电脑高负荷,已跳过本地生图（{busy_state.get('reason') or '负载偏高'}）"
            else:
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
        if self._sdgen_photo_available():
            busy_state = self._local_photo_generation_busy_state(force_refresh=True)
            if busy_state:
                sdgen_note = f"电脑高负荷,已跳过本地生图（{busy_state.get('reason') or '负载偏高'}）"
            else:
                image_path, note = await self._run_sdgen_photo_generation(
                    prompt_text,
                    session_key=session_key,
                )
                if image_path:
                    return "SDGen", image_path, note
                sdgen_note = note
        else:
            sdgen_note = "SDGen 插件不可用或未配置"
        if self._external_photo_available():
            image_path, note = await self._run_external_photo_generation(
                prompt_text,
                session_key=session_key,
            )
            if image_path:
                return "在线图片 API", image_path, note
            return "在线图片 API", "", f"ComfyUI 失败：{comfyui_note}；SDGen 失败：{sdgen_note}；在线图片 API 失败：{note}"
        return "SDGen", "", f"ComfyUI 失败：{comfyui_note}；SDGen 失败：{sdgen_note}"

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
请根据 AstrBot 默认人格和主动原因,生成一张要通过生图后端制作的“社交媒体随手拍/自拍/生活碎片图”提示词。

【人格】
{persona}

【收信人】
{name}

【当前拟人状态】
{self._format_state_for_prompt(state if isinstance(state, dict) else {})}

【当前日程背景】
{self._format_plan_item_for_prompt(current_item)}

{self._format_worldview_adaptation_prompt()}

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
  "prompt": "给生图后端的中文生图提示词,包含主体、场景、光线、构图、情绪；不要写聊天口吻",
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

    def _find_sdgen_plugin(self) -> Any | None:
        try:
            getter = getattr(getattr(self, "context", None), "get_registered_star", None)
            if callable(getter):
                for name in ("SDGen", "astrbot_plugin_sdgen"):
                    plugin = getter(name)
                    if plugin is not None and callable(getattr(plugin, "_call_t2i_api", None)):
                        return plugin
        except Exception:
            pass
        for obj in gc.get_objects():
            try:
                cls = obj.__class__
                module = str(getattr(cls, "__module__", ""))
                if "astrbot_plugin_sdgen" not in module:
                    continue
                if callable(getattr(obj, "_call_t2i_api", None)):
                    return obj
            except Exception:
                continue
        return None

    async def _run_sdgen_photo_generation(
        self,
        prompt_text: str,
        *,
        session_key: str,
    ) -> tuple[str, str]:
        plugin = self._find_sdgen_plugin()
        if plugin is None:
            return "", "SDGen 插件不可用"
        checker = getattr(plugin, "_check_webui_available", None)
        if callable(checker):
            try:
                available, status = await checker()
                if not available:
                    return "", f"Stable Diffusion WebUI 不可用（status={status}）"
            except Exception as exc:
                return "", f"检查 Stable Diffusion WebUI 失败：{_single_line(exc, 120)}"
        try:
            positive_prompt = prompt_text
            build_prompt = getattr(plugin, "_build_positive_prompt", None)
            if callable(build_prompt):
                positive_prompt = build_prompt(prompt_text, "")
            response = await plugin._call_t2i_api(positive_prompt)
            images = response.get("images") if isinstance(response, dict) else None
            if not isinstance(images, list) or not images:
                return "", "SDGen 未返回图片"
            image = str(images[0] or "").strip()
            if not image:
                return "", "SDGen 返回空图片"
            config = getattr(plugin, "config", {}) or {}
            try:
                enable_upscale = bool(config.get("enable_upscale", False))
            except Exception:
                enable_upscale = False
            processor = getattr(plugin, "_apply_image_processing", None)
            if enable_upscale and callable(processor):
                image = await processor(image)
            if "," in image and image.lower().lstrip().startswith("data:image"):
                image = image.split(",", 1)[1].strip()
            image_bytes = base64.b64decode(image)
            path = await self._save_external_generated_image(
                image_bytes,
                session_key=session_key,
                ext=".png",
            )
            return path, "ok" if path else "保存 SDGen 图片失败"
        except Exception as e:
            logger.warning(f"[PrivateCompanion] SDGen 生图失败: {e}", exc_info=True)
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
        file_path = out_dir / f"{session_part}_{self._environment_now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}{safe_ext}"
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

    @staticmethod
    def _strip_leading_sentence_boundary_artifacts(text: str) -> str:
        cleaned = str(text or "").strip()
        cleaned = re.sub(r"^(?:[。！？!?；;，,、：:]+[\s\u3000]*)+", "", cleaned).strip()
        return cleaned

    def _forward_sender_id_for_segments(self, event: Any | None = None) -> str:
        if event is not None:
            try:
                sender_id = _single_line(self._event_self_id(event), 40)
                if sender_id:
                    return sender_id
            except Exception:
                pass
        for sender_id in self._known_bot_self_ids():
            if sender_id:
                return sender_id
        return "0"

    def _forward_nodes_for_segments(self, segments: list[str], *, event: Any | None = None) -> list[dict[str, Any]]:
        sender_name = _single_line(getattr(self, "bot_name", ""), 40) or "PrivateCompanion"
        sender_id = self._forward_sender_id_for_segments(event)
        nodes: list[dict[str, Any]] = []
        for segment in segments:
            text = str(segment or "").strip()
            if not text:
                continue
            nodes.append(
                {
                    "type": "node",
                    "data": {
                        "name": sender_name,
                        "uin": sender_id,
                        "content": [{"type": "text", "data": {"text": text}}],
                    },
                }
            )
        return nodes

    def _clean_forward_segment_texts(self, segments: list[str]) -> list[str]:
        cleaned: list[str] = []
        for segment in segments:
            text = re.sub(r"</?t{2,}s\b[^>]*>", "", str(segment or ""), flags=re.IGNORECASE).strip()
            if text:
                cleaned.append(text)
        return cleaned

    def _onebot_forward_action_result_ok(self, result: Any) -> bool:
        if result is None:
            return False
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
            data = result.get("data")
            if isinstance(data, dict) and any(data.get(key) for key in ("message_id", "forward_id", "res_id", "resid")):
                return True
            return any(result.get(key) for key in ("message_id", "forward_id", "res_id", "resid"))
        return bool(result)

    async def _call_onebot_forward_action(self, client: Any, action: str, **params: Any) -> bool:
        for attr in ("call_action", "call_api", "api"):
            func = getattr(client, attr, None)
            if not callable(func):
                continue
            try:
                result = func(action, **params)
                if hasattr(result, "__await__"):
                    result = await result
                if self._onebot_forward_action_result_ok(result):
                    return True
            except TypeError:
                try:
                    result = func(action, params)
                    if hasattr(result, "__await__"):
                        result = await result
                    if self._onebot_forward_action_result_ok(result):
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
                return self._onebot_forward_action_result_ok(result)
            except Exception:
                return False
        return False

    async def _send_segmented_forward_message(
        self,
        *,
        target_type: str,
        target_id: str,
        segments: list[str],
        event: Any | None = None,
        source: str = "",
    ) -> bool:
        if not getattr(self, "segmented_proactive_send_as_forward", False):
            return False
        target_type = str(target_type or "").strip().lower()
        target_id = _single_line(target_id, 80)
        if target_type not in {"private", "group"} or not target_id:
            return False
        raw_segments = [str(item or "").strip() for item in segments if str(item or "").strip()]
        if len(raw_segments) <= 1:
            return False
        if getattr(self, "enable_tts_enhancement", False) and any(re.search(r"</?t{2,}s\b", item, flags=re.IGNORECASE) for item in raw_segments):
            logger.info("[PrivateCompanion] 分段合并消息跳过 TTS 内容: source=%s target=%s:%s", source or "unknown", target_type, target_id)
            return False
        cleaned_segments = self._clean_forward_segment_texts(raw_segments)
        if len(cleaned_segments) <= 1:
            return False
        hit = self._forbidden_recall_hit("\n".join(cleaned_segments))
        if hit:
            logger.warning(
                "[PrivateCompanion] 分段合并消息命中违禁词，已拦截发送: source=%s target=%s:%s word=%s",
                source or "unknown",
                target_type,
                target_id,
                _single_line(hit, 40),
            )
            return True
        client = self._resolve_aiocqhttp_client()
        if client is None:
            return False
        nodes = self._forward_nodes_for_segments(cleaned_segments, event=event)
        if len(nodes) <= 1:
            return False
        target_value: Any = target_id
        try:
            target_value = int(target_id)
        except Exception:
            pass
        if target_type == "group":
            attempts = [
                ("send_group_forward_msg", {"group_id": target_value, "messages": nodes}),
                ("send_group_forward_msg", {"group_id": target_value, "nodes": nodes}),
                ("send_forward_msg", {"group_id": target_value, "messages": nodes}),
                ("send_forward_msg", {"group_id": target_value, "nodes": nodes}),
            ]
        else:
            attempts = [
                ("send_private_forward_msg", {"user_id": target_value, "messages": nodes}),
                ("send_private_forward_msg", {"user_id": target_value, "nodes": nodes}),
                ("send_forward_msg", {"user_id": target_value, "messages": nodes}),
                ("send_forward_msg", {"user_id": target_value, "nodes": nodes}),
            ]
        for action, params in attempts:
            if await self._call_onebot_forward_action(client, action, **params):
                logger.info(
                    "[PrivateCompanion] 分段消息已合并转发发送: source=%s target=%s:%s segments=%s",
                    source or "unknown",
                    target_type,
                    target_id,
                    len(cleaned_segments),
                )
                return True
        logger.info(
            "[PrivateCompanion] 分段合并转发发送不可用，回退普通分段: source=%s target=%s:%s segments=%s",
            source or "unknown",
            target_type,
            target_id,
            len(cleaned_segments),
        )
        return False

    async def _send_segmented_proactive_forward_message(self, umo: str, segments: list[str], *, source: str = "proactive") -> bool:
        session = self._parse_message_session(umo)
        if not session:
            return False
        target_id = _single_line(getattr(session, "session_id", ""), 80)
        if not target_id:
            return False
        target_type = "group" if self._message_type_for_session(session) == MessageType.GROUP_MESSAGE else "private"
        return await self._send_segmented_forward_message(
            target_type=target_type,
            target_id=target_id,
            segments=segments,
            source=source,
        )

    async def _send_segmented_event_forward_message(self, event: AstrMessageEvent, segments: list[str], *, source: str = "decorating_result") -> bool:
        try:
            if bool(getattr(event, "is_private_chat", lambda: False)()):
                user_id = _single_line(event.get_sender_id(), 80)
                if user_id:
                    return await self._send_segmented_forward_message(
                        target_type="private",
                        target_id=user_id,
                        segments=segments,
                        event=event,
                        source=source,
                    )
        except Exception:
            pass
        group_id = self._extract_group_id_from_event(event)
        if group_id:
            return await self._send_segmented_forward_message(
                target_type="group",
                target_id=group_id,
                segments=segments,
                event=event,
                source=source,
            )
        return False

    def _segmented_chat_scope_allows(self, chat_type: str) -> bool:
        scope = str(getattr(self, "segmented_proactive_chat_scope", "all") or "all").strip().lower()
        if scope not in {"all", "private", "group"}:
            scope = "all"
        chat_type = str(chat_type or "").strip().lower()
        return scope == "all" or scope == chat_type

    def _segmented_scope_allows_umo(self, umo: str) -> bool:
        session = self._parse_message_session(umo)
        if not session:
            return self._segmented_chat_scope_allows("private")
        chat_type = "group" if self._message_type_for_session(session) == MessageType.GROUP_MESSAGE else "private"
        return self._segmented_chat_scope_allows(chat_type)

    def _segmented_scope_allows_event(self, event: AstrMessageEvent) -> bool:
        try:
            if bool(getattr(event, "is_private_chat", lambda: False)()):
                return self._segmented_chat_scope_allows("private")
        except Exception:
            pass
        if self._extract_group_id_from_event(event):
            return self._segmented_chat_scope_allows("group")
        return self._segmented_chat_scope_allows("private")

    async def _send_chain_components(self, umo: str, chain: list[Any]) -> None:
        hit = self._forbidden_recall_hit(self._chain_text_for_forbidden_recall(chain))
        if hit:
            logger.warning(
                "[PrivateCompanion] 主动待发送消息命中违禁词，已拦截发送: umo=%s word=%s",
                umo,
                _single_line(hit, 40),
            )
            return
        processed_chain = await self._trigger_proactive_decorating_hooks(umo, chain)
        if not processed_chain:
            return
        hit = self._forbidden_recall_hit(self._chain_text_for_forbidden_recall(processed_chain))
        if hit:
            logger.warning(
                "[PrivateCompanion] 主动装饰后消息命中违禁词，已拦截发送: umo=%s word=%s",
                umo,
                _single_line(hit, 40),
            )
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
        quote_message_id: str = "",
        disable_segmenting: bool = False,
    ) -> None:
        trigger_message_id = _single_line(quote_message_id, 120)
        if self._contains_inline_image_tag(text):
            image_path = ""
            extra_components = []
        if text:
            await self._maybe_send_input_status(umo, text)
        segments = self._split_proactive_text(
            text,
            image_path="",
            extra_components=None,
            disable_segmenting=disable_segmenting or not self._segmented_scope_allows_umo(umo),
        )
        if len(segments) <= 1:
            outbound_text = segments[0] if segments else ""
            if outbound_text:
                recalled_message_id = self._should_cancel_reply_for_recalled_message_ids(trigger_message_id)
                if recalled_message_id:
                    logger.info("[PrivateCompanion] 触发消息已撤回，取消主动文本发送: umo=%s message_id=%s", umo, recalled_message_id)
                    return
                await self._send_chain_components(umo, self._with_optional_reply([Plain(outbound_text)], quote_message_id))
                quote_message_id = ""
        else:
            recalled_message_id = self._should_cancel_reply_for_recalled_message_ids(trigger_message_id)
            if recalled_message_id:
                logger.info("[PrivateCompanion] 触发消息已撤回，取消主动合并分段发送: umo=%s message_id=%s", umo, recalled_message_id)
                return
            if await self._send_segmented_proactive_forward_message(umo, segments, source="proactive_media_text"):
                quote_message_id = ""
            else:
                for index, segment in enumerate(segments):
                    recalled_message_id = self._should_cancel_reply_for_recalled_message_ids(trigger_message_id)
                    if recalled_message_id:
                        logger.info("[PrivateCompanion] 触发消息已撤回，停止主动分段发送: umo=%s message_id=%s index=%s", umo, recalled_message_id, index + 1)
                        return
                    chain = self._with_optional_reply([Plain(segment)], quote_message_id) if index == 0 else [Plain(segment)]
                    await self._send_chain_components(umo, chain)
                    quote_message_id = ""
                    if index < len(segments) - 1:
                        await asyncio.sleep(await self._calc_segmented_proactive_interval(segment))
        has_media = bool((extra_components or []) or (image_path and os.path.exists(image_path)))
        if has_media:
            logger.info(
                "[PrivateCompanion] 主动媒体发送: text_segments=%s image=%s extra_components=%s",
                len(segments),
                bool(image_path and os.path.exists(image_path)),
                len(extra_components or []),
            )
            recalled_message_id = self._should_cancel_reply_for_recalled_message_ids(trigger_message_id)
            if recalled_message_id:
                logger.info("[PrivateCompanion] 触发消息已撤回，取消主动媒体发送: umo=%s message_id=%s", umo, recalled_message_id)
                return
            media_chain = self._build_outbound_chain("", image_path, extra_components=extra_components)
            media_chain = self._with_optional_reply(media_chain, quote_message_id)
            await self._send_chain_components(umo, media_chain)

    async def _send_proactive_message_chain(
        self,
        umo: str,
        text: str,
        image_path: str = "",
        *,
        extra_components: list[Any] | None = None,
        quote_message_id: str = "",
        disable_segmenting: bool = False,
    ) -> None:
        trigger_message_id = _single_line(quote_message_id, 120)
        if image_path or extra_components:
            await self._send_media_proactive_chain(
                umo,
                text,
                image_path,
                extra_components=extra_components,
                quote_message_id=quote_message_id,
                disable_segmenting=disable_segmenting,
            )
            return
        if text:
            await self._maybe_send_input_status(umo, text)
        segments = self._split_proactive_text(
            text,
            image_path="",
            extra_components=None,
            disable_segmenting=disable_segmenting or not self._segmented_scope_allows_umo(umo),
        )
        if len(segments) <= 1:
            outbound_text = segments[0] if segments else text
            recalled_message_id = self._should_cancel_reply_for_recalled_message_ids(trigger_message_id)
            if recalled_message_id:
                logger.info("[PrivateCompanion] 触发消息已撤回，取消主动消息发送: umo=%s message_id=%s", umo, recalled_message_id)
                return
            await self._send_chain_components(
                umo,
                self._with_optional_reply(
                    self._build_outbound_chain(outbound_text, image_path, extra_components=extra_components),
                    quote_message_id,
                ),
            )
            return
        recalled_message_id = self._should_cancel_reply_for_recalled_message_ids(trigger_message_id)
        if recalled_message_id:
            logger.info("[PrivateCompanion] 触发消息已撤回，取消主动合并分段发送: umo=%s message_id=%s", umo, recalled_message_id)
            return
        if await self._send_segmented_proactive_forward_message(umo, segments, source="proactive_text"):
            return
        for index, segment in enumerate(segments):
            recalled_message_id = self._should_cancel_reply_for_recalled_message_ids(trigger_message_id)
            if recalled_message_id:
                logger.info("[PrivateCompanion] 触发消息已撤回，停止主动消息分段发送: umo=%s message_id=%s index=%s", umo, recalled_message_id, index + 1)
                return
            chain = self._with_optional_reply([Plain(segment)], quote_message_id) if index == 0 else [Plain(segment)]
            await self._send_chain_components(umo, chain)
            quote_message_id = ""
            if index < len(segments) - 1:
                await asyncio.sleep(await self._calc_segmented_proactive_interval(segment))

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
        action_text = _single_line(action, 40) or "message"
        motive_text = _single_line(motive, 120)
        lines = [
            "[主动消息]",
            f"触发原因：{_single_line(reason, 40) or 'unknown'}",
            f"行为结果：{action_text}",
        ]
        if motive_text:
            lines.append(f"内部动机：{motive_text}")
        if action_summary:
            lines.append(f"动作摘要：{_single_line(action_summary, 160)}")
        lines.append("说明：这不是用户消息，而是 Private Companion 插件为触发主动消息写入的记录。")
        return "；".join(lines)

    def _build_proactive_archive_assistant_text(
        self,
        *,
        text: str,
        image_path: str = "",
        extra_components: list[Any] | None = None,
        action_summary: str = "",
    ) -> str:
        message_text = self._visible_text_without_tts_reading(text, limit=1000)
        attachment_notes: list[str] = []
        if image_path:
            attachment_notes.append("随消息发送了一张图片")
        if extra_components:
            tts_notes: list[str] = []
            note_builder = getattr(self, "_tts_component_log_note", None)
            for comp in extra_components:
                if isinstance(comp, Record) and callable(note_builder):
                    note = _single_line(note_builder(comp), 220)
                    if note:
                        tts_notes.append(note)
            if tts_notes:
                attachment_notes.extend(tts_notes[:3])
            else:
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
        for attempt in range(4):
            try:
                user_msg_obj = UserMessageSegment(content=str(user_prompt or ""))
                assistant_msg_obj = AssistantMessageSegment(content=str(assistant_response or ""))
                async def _write():
                    conv_id = await self.context.conversation_manager.get_curr_conversation_id(umo)
                    if not conv_id:
                        return False
                    await self.context.conversation_manager.add_message_pair(
                        cid=conv_id,
                        user_message=user_msg_obj,
                        assistant_message=assistant_msg_obj,
                    )
                    return True

                written = await self._conversation_db_operation("archive_proactive_message", _write)
                if not written:
                    logger.debug("[PrivateCompanion] 当前私聊没有活动对话,跳过主动消息存档: %s", umo)
                    return
                if attempt > 0:
                    logger.info("[PrivateCompanion] 主动消息写入 AstrBot 会话历史成功: %s retry=%s", umo, attempt)
                else:
                    logger.info("[PrivateCompanion] 已将主动消息写入 AstrBot 会话历史: %s", umo)
                return
            except Exception as e:
                text = str(e or "").lower()
                if ("database is locked" in text or "sqlite3.operationalerror" in text) and attempt < 3:
                    await asyncio.sleep(0.25 * (attempt + 1))
                    continue
                logger.warning("[PrivateCompanion] 主动消息写入会话历史失败: %s", e)
                return

    def _format_story_plan_for_prompt(self) -> str:
        plan = self.data.get("daily_story_plan", {})
        if not isinstance(plan, dict) or plan.get("date") != _today_key():
            return "（暂无）"
        lines = []
        now_minutes = self._environment_now_minutes()
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
        cleaned = self._strip_internal_identity_anchors(cleaned)
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
        return self._strip_leading_sentence_boundary_artifacts(re.sub(r"\s+", " ", cleaned).strip())

    def _normalize_proactive_sentence_flow(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        cleaned = self._strip_unsupported_proactive_agreement(cleaned)
        cleaned = self._trim_abrupt_closing_topic_shift(cleaned)
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

    def _strip_unsupported_proactive_agreement(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        patterns = (
            r"^(?:哈哈|哈|嘿|嗯嗯|嗯|唔|诶|欸)[，,。.\s]*(?:我也觉得|确实|对吧|是吧|真的)[，,。.\s]*",
            r"^(?:我也觉得|确实|对吧|是吧|真的)[，,。.\s]*",
            r"^(?:哈哈|哈)[，,。.\s]*(?=(?:今天|刚刚|刚才|现在|窗外|路上|云|天气|太阳|雨|风))",
        )
        for pattern in patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE).strip()
        return cleaned or str(text or "").strip()

    def _has_abrupt_closing_topic_shift(self, text: str, *, inbound_text: str = "") -> bool:
        original = str(text or "").strip()
        if not original:
            return False
        trimmed = self._trim_abrupt_closing_topic_shift(original, inbound_text=inbound_text)
        return bool(trimmed and trimmed != original)

    def _trim_abrupt_closing_topic_shift(self, text: str, *, inbound_text: str = "") -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        units = []
        for line in cleaned.splitlines():
            line = line.strip()
            if line:
                units.extend(self._split_proactive_sentence_units(line))
        units = [unit.strip(" ,，、") for unit in units if unit.strip(" ,，、")]
        if len(units) <= 1:
            return cleaned
        inbound = _single_line(inbound_text, 260)
        inbound_is_sleep_context = bool(re.search(r"(晚安|睡了|睡觉|做梦|好梦|困了|休息|先睡|去睡|早点睡)", inbound))
        closing_index = -1
        for index, unit in enumerate(units):
            if re.search(r"(晚安|好梦|做个梦|做梦|睡吧|睡觉|去睡|早点睡|休息吧|明天见|先不吵你)", unit):
                closing_index = index
                break
        if closing_index < 0 or closing_index >= len(units) - 1:
            return cleaned
        tail = "".join(units[closing_index + 1 :])
        if not tail:
            return cleaned
        tail_continues_closing = bool(re.search(r"(梦|睡|晚安|明天|醒来|休息|被窝|枕头|月亮|星星)", tail))
        if tail_continues_closing and inbound_is_sleep_context:
            return cleaned
        abrupt_markers = (
            "今天", "刚刚", "刚才", "现在", "天气", "云", "太阳", "雨", "风", "作业", "阅读",
            "视频", "新闻", "群里", "书柜", "日程", "吃", "喝", "路上", "窗外", "看到", "觉得",
        )
        looks_abrupt = any(marker in tail for marker in abrupt_markers) or len(tail) >= 6
        if not looks_abrupt:
            return cleaned
        kept = units[: closing_index + 1]
        result = "\n".join(self._ensure_chat_sentence_punctuation(unit) for unit in kept if unit)
        return result.strip() or cleaned

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
        if not reasons:
            reasons.append("check_in")
        elif _safe_int(user.get("ignored_streak"), 0, 0) <= 0 and random.random() < 0.12:
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

