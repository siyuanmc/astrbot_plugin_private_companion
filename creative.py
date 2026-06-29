# -*- coding: utf-8 -*-
"""
CreativeMixin — 从 main.py 重新拆分出的创作系统
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

class CreativeMixin:
    """创作系统"""

    def _creative_projects(self) -> list[dict[str, Any]]:
        projects = self.data.setdefault("creative_projects", [])
        if not isinstance(projects, list):
            projects = []
            self.data["creative_projects"] = projects
        valid_projects = [item for item in projects if isinstance(item, dict)]
        for project in valid_projects:
            project.setdefault("work_type", "短篇小说")
            point_of_view = _single_line(project.get("point_of_view"), 40)
            if not point_of_view:
                project["point_of_view"] = "第三人称有限视角"
                project.setdefault("point_of_view_policy_version", 2)
                continue
            if (
                "第一人称" in point_of_view
                and not project.get("point_of_view_policy_version")
                and "书信" not in point_of_view
                and "日记" not in point_of_view
                and "手记" not in point_of_view
            ):
                project["point_of_view"] = "第三人称有限视角"
                project["point_of_view_note"] = "legacy_first_person_rebalanced"
                project["point_of_view_policy_version"] = 2
        return valid_projects

    def _creative_chars_per_session(self) -> int:
        style = str(self.default_style or "")
        persona = f"{self.schedule_persona_prompt} {self.default_style} {self.bot_name}"
        budget = self.creative_chars_per_session
        if any(token in persona for token in ("慢热", "寡言", "内敛", "病弱", "疲惫", "懒", "迟钝")):
            budget = int(budget * 0.72)
        elif any(token in persona for token in ("活泼", "话多", "元气", "急性子")) or style == "活泼":
            budget = int(budget * 1.18)
        elif style == "校园风":
            budget = int(budget * 0.88)
        state = self.data.get("daily_state", {})
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        if energy < 40:
            budget = int(budget * 0.72)
        elif energy > 82:
            budget = int(budget * 1.12)
        return max(60, min(1200, budget))

    def _bot_currently_idle_for_creative_writing(self) -> bool:
        now_dt = datetime.now()
        if now_dt.hour < 7:
            return False
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        if self._is_sleepy_plan_item(current_item):
            return False
        activity = _single_line((current_item or {}).get("activity"), 100)
        mood = _single_line((current_item or {}).get("mood"), 40)
        seed = _single_line((current_item or {}).get("message_seed"), 100)
        state = self.data.get("daily_state", {})
        state_mood = _single_line(state.get("mood_bias") if isinstance(state, dict) else "", 30)
        energy = _safe_int(state.get("energy") if isinstance(state, dict) else 70, 70, 0, 100)
        text = f"{activity} {mood} {seed} {state_mood}"
        busy_tokens = (
            "上课", "学习", "复习", "考试", "作业", "工作", "开会", "通勤",
            "忙", "赶", "处理", "训练", "任务", "外出", "出门", "睡",
        )
        if any(token in text for token in busy_tokens):
            return False
        idle_tokens = (
            "创作", "写字", "写作", "灵感", "读书", "阅读", "休息", "摸鱼",
            "发呆", "无聊", "闲", "空", "散步", "听歌", "整理", "安静",
            "下午也要加油", "缓一缓", "歇", "偷懒",
        )
        if any(token in text for token in idle_tokens):
            return random.random() < 0.55
        return 38 <= energy <= 82 and random.random() < 0.18

    def _creative_has_pending_proactive_plan(self) -> bool:
        now = _now_ts()
        users = self.data.get("users", {})
        if not isinstance(users, dict):
            return False
        for user in users.values():
            if not isinstance(user, dict):
                continue
            next_at = _safe_float(user.get("next_proactive_at"), 0)
            source = str(user.get("planned_proactive_source") or "")
            if next_at > now and (next_at - now <= 45 * 60 or source in {"timer", "simulation"}):
                return True
        return False

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
                "创作要求：作品类型、题材、叙事声音、比喻密度、说话习惯、关注点和节奏都要像这个人格会写出来的东西。",
                "身份边界：如果人格没有学生、职场、异世界、职业、年龄、身体特征等设定,不要凭空添加；如果人格明确不是人类,不要写成人类日常生理经验。",
                "文风边界：不要套用通用网文腔、营销文案腔或过度华丽散文腔；不要为了梦境感牺牲可读性。",
            )
            if part
        )

    def _creative_point_of_view(self, project: dict[str, Any] | None = None) -> str:
        if isinstance(project, dict):
            point_of_view = _single_line(project.get("point_of_view"), 40)
        else:
            point_of_view = ""
        return point_of_view or "第三人称有限视角"

    def _creative_work_type(self, project: dict[str, Any] | None = None) -> str:
        work_type = _single_line(project.get("work_type") if isinstance(project, dict) else "", 30)
        return work_type or "短篇小说"

    def _creative_work_output_rule(self, work_type: str, point_of_view: str) -> str:
        work_type = _single_line(work_type, 30) or "短篇小说"
        if any(token in work_type for token in ("诗", "短诗", "歌词", "歌")):
            return "只输出本次写下的诗句/歌词片段,可以换行,不要解释意象,不要写成小说叙事。"
        if any(token in work_type for token in ("随笔", "散文", "札记", "观察", "影评", "读后感")):
            return "只输出本次写下的随笔/札记正文,可以有作者自己的观察,但不要写成对用户的聊天回复或系统汇报。"
        if any(token in work_type for token in ("剧本", "短剧", "分镜", "脚本", "对白")):
            return "只输出本次写下的剧本/分镜/对白片段,允许出现角色名和简短舞台提示,不要写成完整成片方案。"
        if any(token in work_type for token in ("设定", "世界观", "角色", "怪谈", "图鉴")):
            return "只输出本次补上的设定正文,可以像设定集、图鉴或角色档案,但要保留作品感,不要写成插件配置。"
        return f"只输出本次写下的正文片段。叙事视角规则：{self._creative_point_of_view_rule(point_of_view)}"

    def _creative_point_of_view_rule(self, point_of_view: str) -> str:
        pov = _single_line(point_of_view, 40) or "第三人称有限视角"
        if "第一人称" in pov:
            return (
                "本项目允许第一人称叙述,但叙述者应是小说角色,不是 Bot 本人在写日记；"
                "除非设定明确,不要把作者身份直接塞进正文。"
            )
        if "书信" in pov or "日记" in pov or "手记" in pov:
            return (
                f"按“{pov}”写作,可以出现文本载体中的自称,但要保持它属于故事内部角色；"
                "不要写成 Bot 对用户的日常汇报。"
            )
        return (
            f"严格按“{pov}”写作。正文不要用“我”作为叙述者,角色台词里的“我”可以保留；"
            "不要写成日记、自述或作者独白。"
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
你是一个拟人化 Bot 的私人创作状态生成器。她因为一个生活小事、日记碎片或梦境灵感,突然想开一个自己的创作项目。

【人格与身份】
{persona_context}

要求：
1. 只设计“正在做的创作计划”,不要写正文。
2. 作品类型可以是短篇小说、诗/歌词、随笔/散文、短剧/对白、分镜脚本、角色设定、世界观片段、怪谈、图鉴条目或其他符合人格的文本作品；不要固定为小说。
3. 风格必须贴合上面的人格、身份和默认说话气质；标题、设定和 tone 都要像她自己会想到的。
4. 灵感来源：{source_label}｜{source_text}
5. 目标 300-5200 字。诗/歌词/短设定可以较短,小说/剧本/世界观可以较长；不能一次写完。
6. 题材可以日常、轻奇幻、悬疑、校园、都市、梦境感、观察、角色小传、世界碎片等,但不要色情、血腥或攻击性。
7. 不要为了题材方便凭空改变 Bot 身份,也不要写出和人格不相称的成熟度、职业经验或生活经验。
8. 作者人格只决定选题、审美、句子节奏和观察方式,不等于正文必须用第一人称。
9. 如果 work_type 不是叙事类,point_of_view 可写“无固定叙事视角”。
10. 输出 JSON。

格式：
{{
  "work_type": "作品类型,如短篇小说/短诗/随笔/短剧/分镜脚本/角色设定/世界观片段",
  "title": "临时标题,不要超过18字",
  "premise": "一句话核心设定",
  "tone": "行文气质,2到5个词",
  "point_of_view": "第三人称有限视角/第三人称全知视角/多视角/第一人称角色视角/书信体/无固定叙事视角之一",
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
        work_type = _single_line(payload.get("work_type"), 30) or "短篇小说"
        target_chars = _safe_int(payload.get("target_chars"), random.randint(900, 2800), 300, 5200)
        now = _now_ts()
        return {
            "id": uuid.uuid4().hex[:12],
            "title": title,
            "work_type": work_type,
            "premise": _single_line(payload.get("premise"), 140) or f"从{source_label}里长出来的一个短篇念头",
            "tone": _single_line(payload.get("tone"), 40) or self.default_style,
            "point_of_view": _single_line(payload.get("point_of_view"), 30) or "第三人称有限视角",
            "point_of_view_policy_version": 2,
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
        remaining = _safe_int(project.get("target_chars"), 2400, 300, 5200) - _safe_int(project.get("current_chars"), 0, 0)
        finish_hint = "可以自然收束到一个小段落结尾,但不要完结全篇。" if remaining <= budget + 120 else "不要完结全篇,只推进一个很小的片段。"
        persona_context = self._creative_persona_style_context()
        work_type = self._creative_work_type(project)
        point_of_view = self._creative_point_of_view(project)
        output_rule = self._creative_work_output_rule(work_type, point_of_view)
        prompt = f"""
你正在模拟拟人化 Bot 在闲暇时慢慢创作一个文本作品。请只写本次随手能写下的一小段。

【作者人格与身份】
{persona_context}

作品类型：{work_type}
标题：{_single_line(project.get("title"), 40)}
核心设定：{_single_line(project.get("premise"), 180)}
行文气质：{_single_line(project.get("tone"), 60)}
叙事视角：{point_of_view}
灵感来源：{_single_line(project.get("source_text"), 180)}
上一段：{recent or "还没有正文。"}
下一步念头：{_single_line(project.get("next_hint"), 140)}

本次字数上限：{budget} 个中文字符左右。
要求：
1. {output_rule}
2. 不要标题、说明、JSON、系统旁白或“下面是”。
3. 这是一次可选的闲暇创作行为,只写一个片段,不要一口气完成整个作品。
4. 文风要像这个人格与身份自然写出的作品：用词、观察角度、人物成熟度、知识范围都不能越过人设。
5. 作者人格影响文风,但作者不等于必须直接出现在作品里；不要把所有作品都写成 Bot 的日记或对用户的自白。
6. 细节要具体,但不要堆辞藻；可以有一点梦境感或生活感。
7. {finish_hint}
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
                "她把那个念头又往后推了一小步,像把一枚很轻的纸片压进书页里,等下次再翻开。",
            ])
        return cleaned

    async def _maybe_start_creative_project(self, *, idle_checked: bool = False) -> bool:
        if not self.enable_creative_writing:
            return False
        if not idle_checked and not self._bot_currently_idle_for_creative_writing():
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
        logger.info("[PrivateCompanion] 新增创作项目: %s / %s", project.get("work_type"), project.get("title"))
        return True

    async def _maybe_advance_creative_projects(self) -> None:
        if not self.enable_creative_writing:
            return
        if self._creative_has_pending_proactive_plan():
            return
        if not self._bot_currently_idle_for_creative_writing():
            return
        await self._maybe_start_creative_project(idle_checked=True)
        projects = self._creative_projects()
        now = _now_ts()
        changed = False
        for project in projects:
            if project.get("status") != "drafting":
                continue
            if now < _safe_float(project.get("next_advance_at"), 0):
                continue
            budget = int(self._creative_chars_per_session() * random.uniform(0.72, 1.18))
            budget = max(60, min(1200, budget))
            remaining = _safe_int(project.get("target_chars"), 2400, 300, 5200) - _safe_int(project.get("current_chars"), 0, 0)
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
            project["next_advance_at"] = now + random.randint(95, 320) * 60
            if project["current_chars"] >= _safe_int(project.get("target_chars"), 2400, 300, 5200):
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
            target_chars = _safe_int(project.get("target_chars"), 2400, 300, 5200)
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
                "work_type": self._creative_work_type(project),
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
            if not isinstance(user, dict) or not self._is_target_private_user(str(user_id), user) or not user.get("enabled", True) or not user.get("umo"):
                continue
            if not self._friend_can_receive_proactive_reason(user, "creative_share", "message"):
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
            title = _single_line(candidate.get("title"), 40) or "刚开的创作项目"
            work_type = _single_line(candidate.get("work_type"), 30) or "作品"
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
                    "motive": f"刚慢慢写到{work_type}《{title}》的一小段,有点想给 {user_id} 看一句,但不要像交作业",
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

