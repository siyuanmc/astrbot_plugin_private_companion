# -*- coding: utf-8 -*-
"""
IntegrationStatusMixin — 外部插件状态、世界观适配与运行环境描述
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




class IntegrationStatusMixin:
    """外部插件状态、世界观适配与运行环境描述"""

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

    def _patch_livingmemory_processor_compat(self) -> None:
        """Work around LivingMemory versions whose MemoryProcessor lacks config."""
        if not self.enable_livingmemory_integration:
            return
        try:
            module = importlib.import_module(
                "data.plugins.astrbot_plugin_livingmemory.core.processors.memory_processor"
            )
        except Exception:
            try:
                module = importlib.import_module(
                    "astrbot_plugin_livingmemory.core.processors.memory_processor"
                )
            except Exception:
                return
        processor_cls = getattr(module, "MemoryProcessor", None)
        if processor_cls is None or hasattr(processor_cls, "config"):
            return
        try:
            setattr(processor_cls, "config", {"atom_enabled": True})
            logger.info("[PrivateCompanion] 已为 LivingMemory MemoryProcessor 添加 config 兼容兜底")
        except Exception as exc:
            logger.debug("[PrivateCompanion] LivingMemory 兼容补丁应用失败: %s", _single_line(exc, 120))

    def _integrated_plugin_installed(self, *names: str) -> bool:
        roots = [
            Path(__file__).resolve().parent.parent,
            Path(self.data_dir).parent.parent / "plugins",
        ]
        for root in roots:
            for name in names:
                try:
                    path = root / name
                    if (path / "main.py").exists() or (path / "metadata.yaml").exists():
                        return True
                except Exception:
                    continue
        return False

    def _report_integrated_feature_conflicts(self) -> None:
        rules = [
            (
                "enable_environment_perception",
                ("astrbot_plugin_llmperception", "astrbot_plugin_LLMPerception"),
                "检测到已安装 astrbot_plugin_LLMPerception,本插件内置环境感知仍按用户配置保持%s；如同时开启可能重复注入。",
            ),
            (
                "enable_group_scene_awareness",
                ("astrbot_plugin_context_aware",),
                "检测到已安装 astrbot_plugin_context_aware,本插件群聊场景感知仍按用户配置保持%s；如同时开启可能重复注入。",
            ),
            (
                "enable_atrelay_tools",
                ("astrbot_plugin_atrelay",),
                "检测到已安装 astrbot_plugin_atrelay,本插件跨群转述与 @ 群友工具仍按用户配置保持%s；如同时开启可能出现重复工具。",
            ),
        ]
        for key, plugin_names, message in rules:
            if self._integrated_plugin_installed(*plugin_names):
                state = "开启" if bool(getattr(self, key, False)) else "关闭"
                logger.info("[PrivateCompanion] %s", message % state)

    def _worldview_mode_effective(self) -> str:
        mode = str(getattr(self, "worldview_adaptation_mode", "auto") or "auto")
        if mode != "auto":
            return mode
        source = " ".join(
            part
            for part in (
                self.schedule_persona_prompt,
                self.schedule_worldview_prompt,
                self.worldview_adaptation_prompt,
                self.bot_name,
            )
            if part
        )
        if any(token in source for token in ("异世界", "冒险者", "魔法", "公会", "地下城", "勇者", "魔王", "骑士", "法师", "精灵", "龙")):
            return "fantasy"
        if any(token in source for token in ("赛博", "星舰", "宇宙", "殖民", "仿生", "义体", "AI 城市", "空间站")):
            return "sci_fi"
        return "modern"

    def _worldview_terms(self) -> dict[str, str]:
        mode = self._worldview_mode_effective()
        if mode == "fantasy":
            return {
                "mode": "fantasy",
                "life_log": "旅记/营地手札",
                "bookshelf": "行囊书匣",
                "secret_drawer": "暗格",
                "screen": "水晶映像",
                "video": "吟游诗人的影像记录",
                "group_chat": "酒馆/公会里的闲谈",
                "private_chat": "私信",
                "schedule": "旅途安排",
                "bored_watch": "翻看见闻记录",
                "private_reading": "翻暗格里的藏书",
            }
        if mode == "sci_fi":
            return {
                "mode": "sci_fi",
                "life_log": "航行日志",
                "bookshelf": "私人资料柜",
                "secret_drawer": "加密夹层",
                "screen": "终端画面",
                "video": "影像流记录",
                "group_chat": "频道通信",
                "private_chat": "私密通信",
                "schedule": "今日流程",
                "bored_watch": "浏览影像流",
                "private_reading": "翻加密藏本",
            }
        return {
            "mode": "modern",
            "life_log": "日记",
            "bookshelf": "书柜",
            "secret_drawer": "夹层",
            "screen": "屏幕",
            "video": "B 站视频",
            "group_chat": "群聊",
            "private_chat": "私聊",
            "schedule": "日程",
            "bored_watch": "刷视频",
            "private_reading": "翻书柜夹层",
        }

    def _format_worldview_adaptation_prompt(self) -> str:
        mode = self._worldview_mode_effective()
        if mode == "off":
            return ""
        terms = self._worldview_terms()
        custom = _single_line(getattr(self, "worldview_adaptation_prompt", ""), 1200)
        base = [
            "【世界观适配】",
            f"当前适配模式：{mode}。",
            "插件功能名称只代表现实实现；最终表达必须服从当前人格、身份和世界观。",
            f"可把日程理解为：{terms['schedule']}；书柜理解为：{terms['bookshelf']}；隐藏夹层理解为：{terms['secret_drawer']}；群聊理解为：{terms['group_chat']}；私聊理解为：{terms['private_chat']}。",
            f"外部或整合动作可转译为世界内等价行为：看视频≈{terms['bored_watch']}；识屏≈观察{terms['screen']}；夹层阅读≈{terms['private_reading']}；空间动态≈公开生活札记/状态栏。",
            "如果人格/世界观与现代词冲突，优先使用世界内说法；但不要编造会改变功能结果的事实，也不要向用户解释后台实现。",
            "未在人格、世界观、关系网、近期对话或用户输入中明确出现的人际关系不得凭空添加；家人、父母、兄弟姐妹、亲戚、室友、同学、老师、同事、朋友、邻居、前辈、后辈等关系只能在材料有依据时使用。",
        ]
        if custom:
            base.append(f"自定义适配：{custom}")
        knowledge_formatter = getattr(self, "_format_roleplay_knowledge_context", None)
        if callable(knowledge_formatter):
            knowledge_context = knowledge_formatter(purpose="worldview", max_chars=1800, max_chunks=10)
            if knowledge_context:
                base.append(knowledge_context)
        return "\n".join(base)

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

    def _llmperception_plugin_dir(self) -> Path:
        candidates = [
            Path(__file__).resolve().parent.parent / "astrbot_plugin_llmperception",
            Path(__file__).resolve().parent.parent / "astrbot_plugin_LLMPerception",
            Path(self.data_dir).parent.parent / "plugins" / "astrbot_plugin_llmperception",
            Path(self.data_dir).parent.parent / "plugins" / "astrbot_plugin_LLMPerception",
        ]
        for path in candidates:
            if (path / "main.py").exists():
                return path
        return candidates[0]

    def _llmperception_available(self) -> bool:
        try:
            return (self._llmperception_plugin_dir() / "main.py").exists()
        except Exception:
            return False

    def _context_aware_available(self) -> bool:
        return self._integrated_plugin_installed("astrbot_plugin_context_aware")

    def _atrelay_plugin_available(self) -> bool:
        return self._integrated_plugin_installed("astrbot_plugin_atrelay")

    def _platform_display_name(self, value: str) -> str:
        raw = _single_line(value, 40).lower()
        return _PLATFORM_DISPLAY_NAMES.get(raw, _single_line(value, 40) or self.target_platform or "未知平台")

    def _message_type_label(self, event: AstrMessageEvent) -> str:
        try:
            if bool(getattr(event, "is_private_chat", lambda: False)()):
                return "私聊"
        except Exception:
            pass
        try:
            if bool(getattr(event, "is_group_chat", lambda: False)()):
                return "群聊"
        except Exception:
            pass
        getter = getattr(event, "get_message_type", None)
        message_type = None
        if callable(getter):
            try:
                message_type = getter()
            except Exception:
                message_type = None
        friend_type = getattr(MessageType, "FRIEND_MESSAGE", None)
        group_type = getattr(MessageType, "GROUP_MESSAGE", None)
        if message_type == friend_type or str(message_type).lower().endswith("friend_message"):
            return "私聊"
        if message_type == group_type or str(message_type).lower().endswith("group_message"):
            return "群聊"
        umo = str(getattr(event, "unified_msg_origin", "") or "")
        if ":GroupMessage:" in umo:
            return "群聊"
        if ":FriendMessage:" in umo:
            return "私聊"
        return "当前会话"

    async def _format_platform_perception(self, event: AstrMessageEvent) -> str:
        if not self.enable_platform_perception:
            return ""
        platform = ""
        getter = getattr(event, "get_platform_name", None)
        if callable(getter):
            try:
                platform = _single_line(getter(), 40)
            except Exception:
                platform = ""
        if not platform:
            platform = str(getattr(event, "unified_msg_origin", "") or "").split(":")[0]
        if not platform:
            platform = self.target_platform or "aiocqhttp"
        parts = [self._platform_display_name(platform), self._message_type_label(event)]
        group_id = self._extract_group_id_from_event(event)
        group_name = ""
        if group_id:
            message_obj = getattr(event, "message_obj", None)
            group_obj = getattr(message_obj, "group", None) if message_obj is not None else None
            for attr in ("group_name", "name", "display_name"):
                value = getattr(group_obj, attr, None) if group_obj is not None else None
                if value:
                    group_name = _single_line(value, 50)
                    break
            get_group = getattr(event, "get_group", None)
            if not group_name and callable(get_group):
                try:
                    value = get_group(group_id=group_id)
                    if hasattr(value, "__await__"):
                        value = await value
                    group_name = _single_line(getattr(value, "group_name", "") or getattr(value, "name", ""), 50)
                except Exception:
                    group_name = ""
            parts.append(f"群号{group_id}" + (f"({group_name})" if group_name else ""))
        component_types: set[str] = set()
        for comp in self._event_components(event):
            class_name = comp.__class__.__name__.lower()
            if class_name == "image":
                component_types.add("含图片")
            elif class_name in {"record", "voice", "audio"}:
                component_types.add("含语音")
            elif class_name == "video":
                component_types.add("含视频")
        parts.extend(sorted(component_types))
        return "、".join(part for part in parts if part)

    @staticmethod
    def _provider_config_value(provider: Any, *keys: str) -> str:
        config = getattr(provider, "provider_config", None) or getattr(provider, "config", None) or {}
        for key in keys:
            value = ""
            if isinstance(config, dict):
                value = str(config.get(key, "") or "")
            else:
                value = str(getattr(config, key, "") or "")
            if value.strip():
                return value.strip()
        return ""

    def _provider_identity_label(self, provider_id: str = "", provider: Any | None = None) -> str:
        safe_id = _single_line(provider_id, 120)
        if provider is None and safe_id:
            getter = getattr(self.context, "get_provider_by_id", None)
            if callable(getter):
                try:
                    provider = getter(safe_id)
                except Exception:
                    provider = None
        if provider is None:
            return safe_id or "AstrBot 默认会话模型"
        name = (
            self._provider_config_value(provider, "name", "display_name", "provider")
            or _single_line(getattr(provider, "name", ""), 80)
        )
        model = self._provider_config_value(provider, "model", "model_name", "api_model", "model_id")
        provider_id = safe_id or self._provider_config_value(provider, "id", "provider_id") or _single_line(getattr(provider, "provider_id", ""), 120)
        pieces = []
        if name:
            pieces.append(name)
        if model and model not in pieces:
            pieces.append(model)
        if provider_id and provider_id not in pieces:
            pieces.append(provider_id)
        return " / ".join(_single_line(piece, 120) for piece in pieces if piece) or "AstrBot 默认会话模型"

    def _current_event_chat_provider_id(self, event: AstrMessageEvent) -> tuple[str, Any | None]:
        provider = None
        provider_id = ""
        try:
            provider_id = _single_line(event.get_extra("selected_provider"), 160)
        except Exception:
            provider_id = ""
        getter = getattr(self.context, "get_provider_by_id", None)
        if provider_id and callable(getter):
            try:
                provider = getter(provider_id)
            except Exception:
                provider = None
        if provider is None:
            get_using = getattr(self.context, "get_using_provider", None)
            if callable(get_using):
                umo = str(getattr(event, "unified_msg_origin", "") or "")
                try:
                    provider = get_using(umo=umo)
                except TypeError:
                    provider = None
                except Exception:
                    provider = None
                for args in ((umo,), ()):
                    if provider is not None:
                        break
                    try:
                        provider = get_using(*args)
                        break
                    except TypeError:
                        continue
                    except Exception:
                        provider = None
                        break
        if provider is not None and not provider_id:
            provider_id = self._provider_config_value(provider, "id", "provider_id") or _single_line(getattr(provider, "provider_id", ""), 160)
        return provider_id, provider

    def _format_model_perception(self, event: AstrMessageEvent) -> str:
        if not self.enable_model_perception:
            return ""
        lines: list[str] = []
        chat_provider_id, chat_provider = self._current_event_chat_provider_id(event)
        lines.append(f"当前对话 LLM：{self._provider_identity_label(chat_provider_id, chat_provider)}")
        plugin_main = self._task_provider(self.llm_provider_id)
        if plugin_main:
            lines.append(f"插件任务主模型覆盖：{self._provider_identity_label(plugin_main)}")
        else:
            lines.append("插件任务主模型覆盖：未单独配置,跟随当前会话或 AstrBot 默认模型")
        task_models = [
            ("日程", self._task_provider(self.daily_plan_provider_id, self.mai_style_provider_id, self.llm_provider_id)),
            ("日记/梦境", self._task_provider(self.dream_diary_provider_id, self.mai_style_provider_id, self.llm_provider_id)),
            ("创作", self._task_provider(self.creative_provider_id, self.mai_style_provider_id, self.llm_provider_id)),
            ("新闻/搜索整理", self._task_provider(self.news_provider_id, self.web_exploration_provider_id, self.llm_provider_id)),
        ]
        task_lines = [f"{name}={self._provider_identity_label(provider_id)}" for name, provider_id in task_models if provider_id]
        if task_lines:
            lines.append("插件分项模型：" + "；".join(task_lines[:6]))
        vision_id, vision_source, _ = self._private_image_caption_provider_id(str(getattr(event, "unified_msg_origin", "") or ""))
        if vision_id:
            source_label = {
                "astrbot_image_caption": "首选识图模型",
                "plugin_vision": "备选识图模型",
                "plugin_vision_fallback": "备选识图模型兜底",
            }.get(vision_source, vision_source or "视觉转述模型")
            lines.append(f"视觉转述模型：{source_label}={self._provider_identity_label(vision_id)}")
        else:
            lines.append("视觉转述模型：未配置；遇到需要看图的插件任务会跳过或退回非视觉处理")
        return "\n".join(lines)

    async def _format_environment_perception(self, event: AstrMessageEvent) -> str:
        checker = getattr(self, "_feature_enabled_or_temp_unlocked", None)
        if callable(checker):
            if not checker("enable_environment_perception"):
                return ""
        elif not self.enable_environment_perception:
            return ""
        current = self._environment_now()
        lines = [
            "【环境感知】",
            "这是当前消息的环境边界,只影响语境判断、节奏和措辞；不要主动声明“我读取到环境/平台/系统时间”。",
            f"发送时间：{current.strftime('%Y-%m-%d %H:%M')}",
        ]
        holiday = self._format_holiday_perception(current)
        if holiday:
            lines.append(f"日期语境：{holiday}")
        lunar = self._format_lunar_perception(current)
        if lunar:
            lines.append(f"农历：{lunar}")
        solar_term = self._format_solar_term_perception(current)
        if solar_term:
            lines.append(f"节气：{solar_term}")
        almanac = self._format_almanac_perception(current)
        if almanac:
            lines.append(f"轻量黄历：{almanac}")
        platform = await self._format_platform_perception(event)
        if platform:
            lines.append(f"平台环境：{platform}")
        model = self._format_model_perception(event)
        if model:
            lines.append(f"模型环境：\n{model}")
        return "\n".join(lines)

    def _environment_timezone(self) -> zoneinfo.ZoneInfo | None:
        timezone_name = _single_line(self.environment_perception_timezone, 64) or "Asia/Shanghai"
        try:
            return zoneinfo.ZoneInfo(timezone_name)
        except Exception:
            return None

    def _environment_now(self) -> datetime:
        tz = self._environment_timezone()
        return datetime.now(tz) if tz is not None else datetime.now()

    def _environment_fromtimestamp(self, timestamp: float) -> datetime:
        tz = self._environment_timezone()
        return datetime.fromtimestamp(timestamp, tz) if tz is not None else datetime.fromtimestamp(timestamp)

    def _environment_today_key(self) -> str:
        return self._environment_now().strftime("%Y-%m-%d")

    def _environment_now_minutes(self) -> int:
        current = self._environment_now()
        return current.hour * 60 + current.minute

    def _format_holiday_perception(self, current: datetime) -> str:
        if not self.enable_holiday_perception:
            return ""
        label, _ = self._current_time_period_label(current)
        weekday = "一二三四五六日"[current.weekday()]
        parts = [f"周{weekday}"]
        if self.holiday_country != "CN" or calendar_cn is None:
            parts.append("周末" if current.weekday() >= 5 else "工作日")
        else:
            try:
                if calendar_cn.is_holiday(current.date()):
                    name = _single_line(calendar_cn.get_holiday_detail(current.date())[1], 30)
                    parts.append(name or "节假日")
                elif calendar_cn.is_workday(current.date()):
                    parts.append("工作日")
                else:
                    parts.append("休息日")
            except Exception:
                parts.append("周末" if current.weekday() >= 5 else "工作日")
        parts.append(label)
        return "、".join(part for part in parts if part)

    def _format_lunar_perception(self, current: datetime) -> str:
        if not self.enable_lunar_perception or Converter is None or Solar is None:
            return ""
        try:
            lunar = Converter.Solar2Lunar(Solar(current.year, current.month, current.day))
            month_index = max(1, min(12, int(getattr(lunar, "month", 1)))) - 1
            day_index = max(1, min(30, int(getattr(lunar, "day", 1)))) - 1
            leap = "闰" if bool(getattr(lunar, "isleap", False)) else ""
            return f"{leap}{_LUNAR_MONTH_NAMES[month_index]}{_LUNAR_DAY_NAMES[day_index]}"
        except Exception:
            return ""

    def _format_solar_term_perception(self, current: datetime) -> str:
        if not self.enable_solar_term_perception:
            return ""
        today = (current.month, current.day)
        if today in _SOLAR_TERM_DATES:
            return _SOLAR_TERM_DATES[today]
        current_date = current.date()
        for offset in range(1, 4):
            next_day = current_date + timedelta(days=offset)
            name = _SOLAR_TERM_DATES.get((next_day.month, next_day.day))
            if name:
                return f"{offset}天后{name}"
        return ""

    def _format_almanac_perception(self, current: datetime) -> str:
        if not self.enable_almanac_perception:
            return ""
        seed = current.year * 10000 + current.month * 100 + current.day
        yi = _ALMANAC_YI[seed % len(_ALMANAC_YI)]
        ji = _ALMANAC_JI[(seed // 7) % len(_ALMANAC_JI)]
        return f"宜{yi}，忌{ji}"

