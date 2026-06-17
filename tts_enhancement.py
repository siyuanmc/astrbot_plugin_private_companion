# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import struct
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from astrbot.api import logger
try:
    from astrbot.api.message_components import Plain, Record
except ImportError:
    from astrbot.api.message_components import Plain
    from astrbot.core.message.components import Record
from astrbot.core import file_token_service
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .helpers import _single_line


TTS_BLOCK_PATTERN = re.compile(r"<t{2,}s\b[^>]*>.*?</t{2,}s>", re.IGNORECASE | re.DOTALL)
TTS_TAG_PATTERN = re.compile(r"</?t{2,}s\b[^>]*>", re.IGNORECASE)
TTS_BLOCK_TOKEN_PATTERN = re.compile(r"\[\[TTSBLOCK:([0-9a-f]{16})\]\]")
EMOTION_TAG_PATTERN = re.compile(r"\[([^\[\]\n]{1,24})\]")
DEFAULT_AUTO_VOICE_PROMPT_MARKERS = (
    "随机日语语音模式",
    "日语语音",
    "原中文文本",
    "自动日语语音",
)
DEFAULT_TTS_SANITIZE_REMOVE_PATTERNS = (
    r"[（(][^（()]*[）)]",
    r"[＞>][＿_][＜<]",
    r"[＾^][＿_][＾^]",
    r"[oO][＿_][oO]",
    r"[xX][＿_][xX]",
    r"[－-][＿_][－-]",
    r"[★☆♪♫♬♩♡♥❤️💖💕💗💓💝💟💜💛💚💙🧡🤍🖤🤎💔❣️💋]",
    r"[→←↑↓↖↗↘↙↔↕↺↻]",
)
DEFAULT_TTS_SANITIZE_FILTER_WORDS = (
    "ω", "Ω", "σ", "Σ", "ε", "д", "Д",
    "´", "`", "＝", "∀", "∇",
    "orz", "OTZ", "QAQ", "QWQ", "TAT", "TUT", "www",
)
DEFAULT_TTS_SANITIZE_REPLACEMENTS = {
    "233": "哈哈哈",
    "666": "厉害",
    "999": "很棒",
    "555": "呜呜呜",
}
TTS_EMOTION_PLACEHOLDER_PREFIX = "__PRIVATE_COMPANION_TTS_EMOTION_"


class TtsEnhancementMixin:
    """Integrated TTS enhancement for private_companion.

    This is intentionally not a verbatim copy of tts_modify. It keeps the useful
    behavior surface but maps identity and prompts to private_companion concepts.
    """

    def _load_tts_enhancement_config(self, config: Any) -> None:
        self.enable_tts_enhancement = self._cfg_bool(config, "enable_tts_enhancement", False)
        self.tts_generation_mode = self._cfg_str(config, "tts_generation_mode", "hybrid", "hybrid").lower()
        if self.tts_generation_mode not in {"hybrid", "direct", "convert"}:
            self.tts_generation_mode = "hybrid"
        self.tts_voice_language = self._cfg_str(config, "tts_voice_language", "ja", "ja").lower()
        if self.tts_voice_language not in {"ja", "zh", "en"}:
            self.tts_voice_language = "ja"
        self.tts_conversion_provider_id = self._cfg_str(config, "tts_conversion_provider_id", "")
        self.tts_extra_prompt = self._cfg_str(config, "tts_extra_prompt", "")
        self.auto_voice_enabled = self._cfg_bool(config, "auto_voice_enabled", self._cfg_bool(config, "auto_japanese_voice_enabled", False))
        self.auto_voice_full_conversion_enabled = self._cfg_bool(
            config,
            "auto_voice_full_conversion_enabled",
            self._cfg_bool(config, "auto_japanese_voice_full_conversion_enabled", False),
        )
        self.auto_voice_probability = self._cfg_int(
            config,
            "auto_voice_probability",
            self._cfg_int(config, "auto_japanese_voice_probability", 20, 0, 100),
            0,
            100,
        ) / 100.0
        self.auto_voice_max_chars = self._cfg_int(
            config,
            "auto_voice_max_chars",
            self._cfg_int(config, "auto_japanese_voice_max_chars", 50, 0),
            0,
        )
        self.auto_voice_cooldown_seconds = self._cfg_int(
            config,
            "auto_voice_cooldown_seconds",
            self._cfg_int(config, "auto_japanese_voice_cooldown_seconds", 120, 0),
            0,
        )
        self.main_user_voice_probability = self._cfg_int(
            config,
            "main_user_voice_probability",
            self._cfg_int(config, "auto_japanese_voice_admin_probability", -1, -1, 100),
            -1,
            100,
        ) / 100.0
        self.main_user_mention_voice_keywords = self._parse_text_list_config(
            config.get("main_user_mention_voice_keywords", config.get("admin_mention_keyword_voice_keywords", "")),
            limit=80,
        )
        self.main_user_mention_voice_probability = self._cfg_int(
            config,
            "main_user_mention_voice_probability",
            self._cfg_int(config, "admin_mention_keyword_voice_probability", 0, 0, 100),
            0,
            100,
        ) / 100.0
        self.main_user_mention_voice_prompt = self._cfg_str(
            config,
            "main_user_mention_voice_prompt",
            self._cfg_str(config, "admin_mention_keyword_voice_prompt", ""),
        )
        self.enable_tts_local_playback = self._cfg_bool(config, "enable_tts_local_playback", False)
        self.enable_tts_live_subtitle_sync = self._cfg_bool(config, "enable_tts_live_subtitle_sync", False)
        self.tts_live_subtitle_url = self._cfg_str(config, "tts_live_subtitle_url", "http://127.0.0.1:18081/show", "http://127.0.0.1:18081/show")
        self.tts_local_playback_volume = self._cfg_int(config, "tts_local_playback_volume", 35, 0, 100)
        self.tts_local_playback_min_interval_seconds = self._cfg_float(config, "tts_local_playback_min_interval_seconds", 0.0, 0.0)
        self._tts_local_playback_last_at = 0.0
        self._tts_auto_voice_last_at: dict[str, float] = {}

    def _tts_provider_kind(self, tts_provider: Any = None, provider_settings: dict[str, Any] | None = None) -> str:
        pieces: list[str] = []
        if tts_provider is not None:
            pieces.extend([
                tts_provider.__class__.__name__,
                str(getattr(tts_provider, "name", "") or ""),
                str(getattr(tts_provider, "provider_type", "") or ""),
            ])
        if provider_settings:
            for key in ("type", "provider", "provider_id", "api_base", "model", "name"):
                pieces.append(str(provider_settings.get(key, "") or ""))
        text = " ".join(pieces).lower()
        if "fish" in text:
            return "fishaudio"
        if "gsv" in text or "gptsovits" in text or "so-vits" in text:
            return "gsv"
        if "openai" in text:
            return "openai"
        if "edge" in text:
            return "edge"
        if "azure" in text:
            return "azure"
        if "gemini" in text:
            return "gemini"
        if "minimax" in text:
            return "minimax"
        if "aliyun" in text or "alibaba" in text or "阿里" in text:
            return "aliyun"
        if "volc" in text or "huoshan" in text or "火山" in text:
            return "volcengine"
        return "generic"

    def _tts_provider_allows_emotion_tags(self, kind: str) -> bool:
        return kind in {"fishaudio", "gsv"}

    def _tts_language_label(self) -> str:
        return {"ja": "日语", "zh": "中文", "en": "英语"}.get(getattr(self, "tts_voice_language", "ja"), "日语")

    def _normalize_tts_voice_language_value(self, value: Any) -> str:
        text = str(value or "").strip().lower()
        compact = re.sub(r"[\s_\\/-]+", "", text)
        aliases = {
            "ja": "ja",
            "jp": "ja",
            "japanese": "ja",
            "日语": "ja",
            "日文": "ja",
            "日本语": "ja",
            "日本語": "ja",
            "zh": "zh",
            "cn": "zh",
            "chinese": "zh",
            "中文": "zh",
            "汉语": "zh",
            "汉文": "zh",
            "普通话": "zh",
            "国语": "zh",
            "en": "en",
            "eng": "en",
            "english": "en",
            "英语": "en",
            "英文": "en",
        }
        return aliases.get(compact, "")

    def _apply_tts_runtime_overrides(self) -> None:
        settings = self.data.get("runtime_settings") if isinstance(getattr(self, "data", None), dict) else None
        if not isinstance(settings, dict):
            return
        lang = self._normalize_tts_voice_language_value(settings.get("tts_voice_language"))
        if lang:
            self.tts_voice_language = lang

    def _format_tts_voice_language_status(self) -> str:
        settings = self.data.get("runtime_settings") if isinstance(getattr(self, "data", None), dict) else None
        override = ""
        if isinstance(settings, dict):
            override = self._normalize_tts_voice_language_value(settings.get("tts_voice_language"))
        source = "指令覆盖" if override else "配置页"
        return f"当前 TTS 语音语种：{self._tts_language_label()}（来源：{source}）。可用：日语 / 中文 / 英语；发送“陪伴 TTS语种 默认”可恢复配置页设置。"

    def _set_tts_voice_language_from_command(self, value: str) -> str:
        text = str(value or "").strip()
        if not text or text in {"查看", "状态", "当前"}:
            return self._format_tts_voice_language_status()
        settings = self.data.setdefault("runtime_settings", {})
        if not isinstance(settings, dict):
            settings = {}
            self.data["runtime_settings"] = settings
        if text.lower() in {"default", "config", "reset", "clear"} or text in {"默认", "配置", "配置页", "重置", "清除", "跟随配置"}:
            settings.pop("tts_voice_language", None)
            configured = self._normalize_tts_voice_language_value(getattr(self, "config", {}).get("tts_voice_language", "ja") if getattr(self, "config", None) is not None else "ja")
            self.tts_voice_language = configured or "ja"
            self._save_data_sync()
            return f"已恢复 TTS 语音语种为配置页设置：{self._tts_language_label()}。"
        lang = self._normalize_tts_voice_language_value(text)
        if not lang:
            return "没认出这个 TTS 语种。可用：日语 / 中文 / 英语；例如：陪伴 TTS语种 日语。"
        self.tts_voice_language = lang
        settings["tts_voice_language"] = lang
        self._save_data_sync()
        return f"已切换 TTS 语音语种：{self._tts_language_label()}。之后 <tts> 和自动语音转换会按这个语种处理。"

    def _normalize_tts_tags(self, text: str) -> str:
        source = str(text or "")
        source = re.sub(r"<(/?)t{2,}s\b[^>]*>", lambda m: f"</tts>" if m.group(1) else "<tts>", source, flags=re.IGNORECASE)
        source = re.sub(r"</tts>\s*</tts>+", "</tts>", source, flags=re.IGNORECASE)
        pieces: list[str] = []
        open_count = 0
        pos = 0
        for match in re.finditer(r"</?tts>", source, flags=re.IGNORECASE):
            pieces.append(source[pos:match.start()])
            tag = match.group(0).lower()
            if tag == "<tts>":
                open_count += 1
                pieces.append("<tts>")
            elif open_count > 0:
                open_count -= 1
                pieces.append("</tts>")
            pos = match.end()
        pieces.append(source[pos:])
        if open_count > 0:
            pieces.append("</tts>" * open_count)
        return "".join(pieces)

    def _strip_any_tts_markup(self, text: str) -> str:
        cleaned = re.sub(r"</?t{2,}s\b[^>]*>", "", str(text or ""), flags=re.IGNORECASE)
        return cleaned.strip()

    def _tts_record_refs(self, component: Any) -> list[str]:
        refs: list[str] = []
        for attr in ("file", "url", "path"):
            value = str(getattr(component, attr, "") or "").strip()
            if value and value not in refs:
                refs.append(value)
        try:
            data = getattr(component, "data", None)
            if isinstance(data, dict):
                for key in ("file", "url", "path"):
                    value = str(data.get(key) or "").strip()
                    if value and value not in refs:
                        refs.append(value)
        except Exception:
            pass
        return refs

    def _remember_tts_record_text(self, component: Any, spoken: str, source: str) -> None:
        refs = self._tts_record_refs(component)
        if not refs:
            return
        index = getattr(self, "_tts_record_text_index", None)
        if not isinstance(index, dict):
            index = {}
            try:
                setattr(self, "_tts_record_text_index", index)
            except Exception:
                return
        now = time.time()
        for ref in refs:
            index[ref] = {"spoken": spoken, "source": source, "ts": now}
        if len(index) > 300:
            kept = sorted(index.items(), key=lambda item: float((item[1] or {}).get("ts") or 0))[-180:]
            index.clear()
            index.update(kept)

    def _lookup_tts_record_text(self, component: Any) -> tuple[str, str]:
        index = getattr(self, "_tts_record_text_index", None)
        if not isinstance(index, dict):
            return "", ""
        for ref in self._tts_record_refs(component):
            item = index.get(ref)
            if isinstance(item, dict):
                return (
                    _single_line(item.get("spoken"), 180),
                    _single_line(item.get("source"), 180),
                )
        return "", ""

    def _annotate_tts_record_component(self, component: Any, spoken_text: str, *, source_text: str = "") -> Any:
        spoken = _single_line(self._strip_any_tts_markup(spoken_text), 500)
        source = _single_line(self._strip_any_tts_markup(source_text), 500)
        try:
            setattr(component, "_private_companion_tts_spoken_text", spoken)
            setattr(component, "_private_companion_tts_source_text", source)
        except Exception:
            pass
        self._remember_tts_record_text(component, spoken, source)
        return component

    def _tts_component_log_note(self, component: Any) -> str:
        spoken = _single_line(getattr(component, "_private_companion_tts_spoken_text", ""), 180)
        source = _single_line(getattr(component, "_private_companion_tts_source_text", ""), 180)
        if not spoken:
            spoken, source = self._lookup_tts_record_text(component)
        if spoken and source and spoken != source:
            return f"语音：{spoken}｜对应文本：{source}"
        if spoken:
            return f"语音：{spoken}"
        return "语音消息"

    def _tts_chain_log_text(self, chain: list[Any]) -> str:
        parts: list[str] = []
        for comp in chain:
            if isinstance(comp, Plain):
                text = _single_line(getattr(comp, "text", ""), 180)
                if text:
                    parts.append(f"文本：{text}")
            elif isinstance(comp, Record):
                parts.append(self._tts_component_log_note(comp))
        return "；".join(parts)

    def _strip_or_keep_emotion_tags(self, text: str, *, provider_kind: str) -> str:
        if self._tts_provider_allows_emotion_tags(provider_kind):
            return str(text or "")
        return EMOTION_TAG_PATTERN.sub("", str(text or "")).strip()

    def _normalize_tts_spoken_text(self, text: str, *, provider_kind: str) -> str:
        cleaned = self._normalize_tts_tags(text)
        cleaned = self._strip_or_keep_emotion_tags(cleaned, provider_kind=provider_kind)
        cleaned = re.sub(r"</?tts>", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</?t{2,}s\b[^>]*>", "", cleaned, flags=re.IGNORECASE)
        return _single_line(cleaned, 2000)

    def _sanitize_tts_spoken_text(self, text: str, *, provider_kind: str) -> str:
        """Clean text immediately before get_audio, scoped to TTS强化 only."""
        if not text:
            return ""
        source = str(text)
        protected: dict[str, str] = {}
        if self._tts_provider_allows_emotion_tags(provider_kind):
            def _protect_emotion(match: re.Match[str]) -> str:
                token = f"{TTS_EMOTION_PLACEHOLDER_PREFIX}{len(protected)}__"
                protected[token] = match.group(0)
                return token

            source = EMOTION_TAG_PATTERN.sub(_protect_emotion, source)

        if len(source) > 10000:
            return ""

        for pattern in DEFAULT_TTS_SANITIZE_REMOVE_PATTERNS:
            try:
                source = re.sub(pattern, "", source)
            except re.error:
                continue
        for word in DEFAULT_TTS_SANITIZE_FILTER_WORDS:
            source = source.replace(word, "")
        for original, replacement in DEFAULT_TTS_SANITIZE_REPLACEMENTS.items():
            source = source.replace(original, replacement)

        source = re.sub(r"(.)\1{2,}", lambda m: m.group(1) * 2, source)
        source = re.sub(r'[""\u201c\u201d]\s*[""\u201c\u201d]', "", source)
        source = re.sub(r"[''\u2018\u2019]\s*[''\u2018\u2019]", "", source)
        source = re.sub(r"[「」『』【】\[\]]\s*[「」『』【】\[\]]", "", source)
        source = re.sub(r"[,，、;；]\s*(?=[,，、;；\s])", "", source)
        source = re.sub(r"[,，、;；]\s*$", "", source)
        source = re.sub(r"^\s*[,，、;；]\s*", "", source)
        source = re.sub(r"\s+", " ", source).strip()

        for token, original in protected.items():
            source = source.replace(token, original)
        return source.strip()

    def _tts_text_matches_language(self, text: str) -> bool:
        spoken = self._normalize_tts_spoken_text(text, provider_kind="fishaudio")
        lang = getattr(self, "tts_voice_language", "ja")
        if lang == "ja":
            return bool(re.search(r"[\u3040-\u30ff\u31f0-\u31ff]", spoken))
        if lang == "en":
            letters = len(re.findall(r"[A-Za-z]", spoken))
            cjk = len(re.findall(r"[\u4e00-\u9fff]", spoken))
            return letters >= max(4, cjk)
        return bool(spoken)

    def _tts_text_needs_language_conversion(self, text: str, *, provider_kind: str) -> bool:
        spoken = self._normalize_tts_spoken_text(text, provider_kind=provider_kind)
        if not spoken:
            return False
        lang = getattr(self, "tts_voice_language", "ja")
        if lang == "zh":
            return False
        cjk_count = len(re.findall(r"[\u4e00-\u9fff]", spoken))
        if lang == "en":
            return cjk_count > 0
        if lang != "ja":
            return False
        kana_count = len(re.findall(r"[\u3040-\u30ff\u31f0-\u31ff]", spoken))
        chinese_markers = (
            "的", "了", "吗", "呢", "吧", "呀", "哦", "啊", "嘛",
            "就是", "有点", "很", "超", "画风", "氛围", "标签", "喜欢",
            "不好意思", "说出口", "温柔",
        )
        if any(marker in spoken for marker in chinese_markers):
            return True
        if not kana_count and cjk_count >= 4:
            return True
        return bool(cjk_count >= 6 and kana_count < max(2, int(cjk_count * 0.35)))

    def _build_tts_rule_prompt(self, provider_kind: str = "generic") -> str:
        lang = self._tts_language_label()
        mode = getattr(self, "tts_generation_mode", "hybrid")
        bilingual_rule = (
            f"当语音正文目标语种不是中文时，<tts>...</tts> 外必须保留或补上一句自然中文含义，优先放在语音块后面，方便用户看到语音对应中文；不要只输出一个外语语音块。"
            if getattr(self, "tts_voice_language", "ja") != "zh"
            else ""
        )
        tag_rule = (
            "可以使用 <tts>...</tts> 标出真正需要朗读的内容；标签外文本会作为普通聊天文字保留。适合采用“中文显示文本 + 外语语音块”的表达：标签外中文自然聊天，标签内按目标语种朗读。"
            if mode in {"hybrid", "direct"}
            else "本轮主模型可以正常回复，不需要主动写 <tts>；后处理会生成语音格式。"
        )
        emotion_rule = (
            "当前 TTS provider 适合保留 [happy]、[sad] 这类方括号情绪标签。"
            if self._tts_provider_allows_emotion_tags(provider_kind)
            else ""
        )
        extra = _single_line(getattr(self, "tts_extra_prompt", ""), 800)
        if not extra:
            extra = self._legacy_nondefault_tts_prompt()
        return "\n".join(
            item
            for item in [
                "【TTS强化】",
                f"当前语音正文目标语种：{lang}。",
                tag_rule,
                bilingual_rule,
                emotion_rule,
                "如果写错成 <ttts>、<tttts> 等多 t 标签，系统会规范化，但你应优先输出标准 <tts>...</tts>。",
                f"补充规则：{extra}" if extra else "",
            ]
            if item
        )

    def _legacy_nondefault_tts_prompt(self) -> str:
        try:
            config = getattr(self, "config", {}) or {}
            value = str(config.get("tts_prompt", "") or "").strip()
        except Exception:
            value = ""
        if not value:
            return ""
        lowered = value.lower()
        if "<tts>" in lowered and "日语" in value and len(value) > 80:
            return ""
        return _single_line(value, 800)

    async def apply_tts_enhancement_request(self, event: Any, req: Any) -> None:
        if not getattr(self, "enabled", False) or not getattr(self, "enable_tts_enhancement", False):
            return
        if not hasattr(req, "system_prompt"):
            return
        try:
            config = self.context.get_config(str(getattr(event, "unified_msg_origin", "") or "")) or {}
        except Exception:
            config = getattr(self, "config", {}) or {}
        provider_settings = dict(config.get("provider_tts_settings", {}) or {})
        provider_kind = self._tts_provider_kind(provider_settings=provider_settings)
        marker = "<!-- private_companion_tts_enhancement_v1 -->"
        prompt = str(getattr(req, "system_prompt", "") or "")
        if marker not in prompt and getattr(self, "tts_generation_mode", "hybrid") in {"hybrid", "direct"}:
            req.system_prompt = f"{prompt}\n\n{marker}\n{self._build_tts_rule_prompt(provider_kind)}".strip()
        if self._should_force_tts_for_main_user_event(event):
            req.system_prompt = (
                f"{req.system_prompt}\n\n【本轮 TTS 强化触发】\n"
                "这轮消息来自主用户或明确 @ 到主用户。请在自然回复里包含一段适合 TTS 朗读的 <tts>...</tts> 内容。"
            ).strip()

    async def protect_tts_enhancement_response_blocks(self, event: Any, resp: Any) -> None:
        if not getattr(self, "enable_tts_enhancement", False):
            text = str(getattr(resp, "completion_text", "") or "")
            if re.search(r"</?t{2,}s\b", text, flags=re.IGNORECASE):
                resp.completion_text = self._strip_any_tts_markup(text)
                logger.info(
                    "[PrivateCompanion] TTS强化未开启,已从模型回复中移除 TTS 标签: session=%s preview=%s",
                    _single_line(getattr(event, "unified_msg_origin", ""), 120) or "unknown",
                    _single_line(resp.completion_text, 160),
                )
            return
        text = self._normalize_tts_tags(str(getattr(resp, "completion_text", "") or ""))
        if text:
            resp.completion_text = text

    async def apply_tts_enhancement_before_send(self, event: Any) -> None:
        if not getattr(self, "enabled", False) or not getattr(self, "enable_tts_enhancement", False):
            return
        result = event.get_result()
        chain = list(getattr(result, "chain", []) or []) if result is not None else []
        if not chain or any(isinstance(comp, Record) for comp in chain):
            return
        plain_parts = [str(getattr(comp, "text", "") or "") for comp in chain if isinstance(comp, Plain)]
        if not plain_parts:
            return
        text = "".join(plain_parts).strip()
        if not text:
            return
        normalized = self._normalize_tts_tags(text)
        if "<tts>" in normalized.lower() and "</tts>" in normalized.lower():
            new_chain = await self._process_tts_tags(normalized, event)
        else:
            new_chain = await self._maybe_convert_plain_reply_to_tts(normalized, event)
        if not new_chain:
            return
        if len(plain_parts) != len(chain):
            non_plain_tail = [comp for comp in chain if not isinstance(comp, Plain)]
            if non_plain_tail:
                new_chain = list(new_chain) + non_plain_tail
        ordered_chunks = self._split_tts_chain_for_ordered_send(new_chain)
        if len(ordered_chunks) > 1:
            remainder_started_at = time.time()
            event.set_result(self._build_result_from_chain(ordered_chunks[0]))
            asyncio.create_task(
                self._send_tts_chain_chunks_after_first(
                    event,
                    ordered_chunks[1:],
                    started_at=remainder_started_at,
                )
            )
            return
        event.set_result(self._build_result_from_chain(new_chain))

    def _split_tts_chain_for_ordered_send(self, chain: list[Any]) -> list[list[Any]]:
        chunks: list[list[Any]] = []
        current_visible: list[Any] = []
        has_record = False
        has_visible = False
        for comp in chain:
            if isinstance(comp, Record):
                has_record = True
                if current_visible:
                    chunks.append(current_visible)
                    current_visible = []
                chunks.append([comp])
            else:
                has_visible = True
                current_visible.append(comp)
        if current_visible:
            chunks.append(current_visible)
        return chunks if has_record and has_visible else [chain]

    def _tts_segment_plain_chunk_for_ordered_send(self, event: Any, chunk: list[Any]) -> list[list[Any]]:
        if not (
            bool(getattr(self, "enable_segmented_proactive_reply", False))
            and str(getattr(self, "segmented_proactive_scope", "") or "") == "all_llm"
        ):
            return [chunk]
        scope_checker = getattr(self, "_segmented_scope_allows_event", None)
        if callable(scope_checker):
            try:
                if not scope_checker(event):
                    return [chunk]
            except Exception:
                return [chunk]
        if not chunk or any(not isinstance(comp, Plain) for comp in chunk):
            return [chunk]
        text = "".join(str(getattr(comp, "text", "") or "") for comp in chunk).strip()
        if not text:
            return []
        splitter = getattr(self, "_split_proactive_text", None)
        if not callable(splitter):
            return [chunk]
        try:
            segments = [item for item in splitter(text) if str(item or "").strip()]
        except Exception as exc:
            logger.debug("[PrivateCompanion] TTS 后置文本分段失败,保持原样: %s", _single_line(exc, 120))
            return [chunk]
        if len(segments) <= 1:
            cleaned = segments[0] if segments else text
            return [[Plain(cleaned)]] if cleaned and cleaned != text else [chunk]
        logger.info(
            "[PrivateCompanion] TTS 后置文本按分段规则拆分: session=%s segments=%s first=%s",
            _single_line(getattr(event, "unified_msg_origin", ""), 120) or "unknown",
            len(segments),
            _single_line(segments[0], 100),
        )
        return [[Plain(segment)] for segment in segments]

    async def _send_tts_chain_chunks_after_first(
        self,
        event: Any,
        chunks: list[list[Any]],
        *,
        started_at: float | None = None,
    ) -> None:
        if not chunks:
            return
        expanded_chunks: list[list[Any]] = []
        for chunk in chunks:
            expanded_chunks.extend(self._tts_segment_plain_chunk_for_ordered_send(event, chunk))
        scope_getter = getattr(self, "_event_scope_key", None)
        scope = ""
        if callable(scope_getter):
            try:
                scope = _single_line(scope_getter(event), 160)
            except Exception:
                scope = ""
        if not scope:
            scope = _single_line(getattr(event, "unified_msg_origin", ""), 160) or "unknown"
        lock_getter = getattr(self, "_segmented_remainder_lock", None)
        lock = lock_getter(scope) if callable(lock_getter) else asyncio.Lock()
        started_at = float(started_at or time.time())
        previous_text = ""
        async with lock:
            for chunk in expanded_chunks:
                if not chunk:
                    continue
                delay = 0.45
                if previous_text and len(expanded_chunks) > 1:
                    calc_interval = getattr(self, "_calc_segmented_proactive_interval", None)
                    if callable(calc_interval):
                        try:
                            delay = max(0.45, float(await calc_interval(previous_text)))
                        except Exception:
                            delay = 0.45
                await asyncio.sleep(delay)
                activity_checker = getattr(self, "_scope_has_new_inbound_activity", None)
                if callable(activity_checker):
                    try:
                        if activity_checker(scope, started_at, ignore_self=True):
                            logger.info(
                                "[PrivateCompanion] 会话已有新消息，停止发送 TTS 后续分块: session=%s sent_preview=%s",
                                scope,
                                _single_line(previous_text, 120) or "0",
                            )
                            return
                    except Exception:
                        pass
                try:
                    await event.send(event.chain_result(chunk))
                    logger.info(
                        "[PrivateCompanion] TTS 分块后台补发完成: session=%s %s",
                        _single_line(getattr(event, "unified_msg_origin", ""), 120) or "unknown",
                        self._tts_chain_log_text(chunk),
                    )
                except Exception as exc:
                    try:
                        await event.send(self._build_result_from_chain(chunk))
                        logger.info(
                            "[PrivateCompanion] TTS 分块后台补发完成: session=%s %s",
                            _single_line(getattr(event, "unified_msg_origin", ""), 120) or "unknown",
                            self._tts_chain_log_text(chunk),
                        )
                    except Exception:
                        logger.warning("[PrivateCompanion] TTS 分块后台补发失败: %s", _single_line(exc, 120))
                        return
                previous_text = " ".join(
                    str(getattr(comp, "text", "") or "").strip()
                    for comp in chunk
                    if isinstance(comp, Plain)
                ).strip() or previous_text

    async def _maybe_convert_plain_reply_to_tts(self, text: str, event: Any) -> list[Any]:
        mode = getattr(self, "tts_generation_mode", "hybrid")
        if mode == "direct":
            return []
        should_convert = mode == "convert"
        reason = "convert_mode" if should_convert else ""
        if not should_convert:
            ok, reason = self._auto_voice_trigger_reason(text, event)
            should_convert = ok
        if not should_convert:
            return []
        converted = await self._convert_text_to_tts_markup(text, event, full=(mode == "convert" or self.auto_voice_full_conversion_enabled))
        if not converted:
            return []
        chain = await self._process_tts_tags(converted, event, fallback_plain=text)
        if chain:
            session = str(getattr(event, "unified_msg_origin", "") or "")
            self._tts_auto_voice_last_at[session] = time.time()
            logger.info(
                "[PrivateCompanion] TTS强化已转换纯文本回复: reason=%s session=%s %s",
                reason,
                _single_line(session, 80),
                self._tts_chain_log_text(chain),
            )
        return chain

    def _auto_voice_trigger_reason(self, text: str, event: Any) -> tuple[bool, str]:
        if not getattr(self, "auto_voice_enabled", False):
            return False, ""
        session = str(getattr(event, "unified_msg_origin", "") or "")
        is_main = self._event_targets_main_user(event)
        if is_main and self.main_user_voice_probability >= 0:
            probability = self.main_user_voice_probability
            bypass_limits = True
            reason = "main_user"
        else:
            probability = getattr(self, "auto_voice_probability", 0.0)
            bypass_limits = False
            reason = "auto"
        if self._event_mentions_main_user_with_keyword(event):
            probability = max(probability, getattr(self, "main_user_mention_voice_probability", 0.0))
            bypass_limits = True
            reason = "main_user_keyword"
        if probability <= 0 or random.random() > probability:
            return False, ""
        cleaned = _single_line(self._normalize_tts_spoken_text(text, provider_kind="generic"), 10000)
        max_chars = int(getattr(self, "auto_voice_max_chars", 0) or 0)
        if max_chars > 0 and not bypass_limits and len(cleaned) > max_chars:
            return False, ""
        cooldown = int(getattr(self, "auto_voice_cooldown_seconds", 0) or 0)
        if cooldown > 0 and not bypass_limits and session:
            last = float(getattr(self, "_tts_auto_voice_last_at", {}).get(session, 0) or 0)
            if time.time() - last < cooldown:
                return False, ""
        return True, reason

    def _configured_main_user_ids(self) -> set[str]:
        ids: set[str] = set()
        for value in getattr(self, "target_user_ids", []) or []:
            text = re.sub(r"\D+", "", str(value or ""))
            if text:
                ids.add(text)
        aliases = getattr(self, "private_user_aliases", {}) or {}
        if isinstance(aliases, dict):
            for key, value in aliases.items():
                for raw in (key, value):
                    text = re.sub(r"\D+", "", str(raw or ""))
                    if text:
                        ids.add(text)
        return ids

    def _event_targets_main_user(self, event: Any) -> bool:
        main_ids = self._configured_main_user_ids()
        if not main_ids:
            return False
        try:
            sender = re.sub(r"\D+", "", str(event.get_sender_id()))
        except Exception:
            sender = ""
        if sender and sender in main_ids:
            return True
        for target in self._event_at_qq_ids(event):
            if target in main_ids:
                return True
        return False

    def _event_mentions_main_user_with_keyword(self, event: Any) -> bool:
        if not self._event_targets_main_user(event):
            return False
        keywords = [item for item in getattr(self, "main_user_mention_voice_keywords", []) or [] if item]
        if not keywords:
            return False
        text = str(getattr(event, "message_str", "") or "")
        return any(keyword in text for keyword in keywords)

    def _should_force_tts_for_main_user_event(self, event: Any) -> bool:
        if not getattr(self, "auto_voice_enabled", False):
            return False
        if self._event_mentions_main_user_with_keyword(event) and self.main_user_mention_voice_probability > 0:
            return random.random() <= self.main_user_mention_voice_probability
        if self._event_targets_main_user(event) and self.main_user_voice_probability >= 0:
            return random.random() <= self.main_user_voice_probability
        return False

    def _event_at_qq_ids(self, event: Any) -> set[str]:
        ids: set[str] = set()
        message_obj = getattr(event, "message_obj", None)
        chain = getattr(message_obj, "message", None)
        for comp in chain or []:
            qq = getattr(comp, "qq", None) or getattr(comp, "target", None)
            text = re.sub(r"\D+", "", str(qq or ""))
            if text:
                ids.add(text)
        raw = str(getattr(event, "message_str", "") or "")
        for match in re.finditer(r"\[At:(\d+)\]|@(\d{5,})", raw):
            ids.add(match.group(1) or match.group(2))
        return ids

    async def _convert_text_to_tts_markup(self, text: str, event: Any, *, full: bool = False) -> str:
        source = _single_line(text, 1200)
        if not source:
            return ""
        provider = await self._get_tts_conversion_provider(event)
        provider_kind = self._tts_provider_kind(provider_settings={})
        lang = self._tts_language_label()
        extra = _single_line(getattr(self, "main_user_mention_voice_prompt", ""), 500) if self._event_mentions_main_user_with_keyword(event) else ""
        if getattr(self, "tts_voice_language", "ja") == "zh":
            output_rule = "必须包含一个 <tts>...</tts> 语音块"
            display_rule = "语音和显示文本同为中文时，不需要额外翻译。"
        else:
            output_rule = "必须包含一个 <tts>...</tts> 语音块，且语音块后必须补一句自然中文含义"
            display_rule = "不要只输出 <tts>...</tts>；最终格式建议为：<tts>目标语种朗读文本</tts>\\n中文含义。"
        prompt = f"""
请把下面这条回复转换成适合 TTS 朗读的最终输出。

目标语种：{lang}
输出格式：{output_rule}
显示文本规则：{display_rule}
Provider 规则：{"可保留少量方括号情绪标签" if self._tts_provider_allows_emotion_tags(provider_kind) else "按普通朗读文本处理"}
补充要求：{extra or "无"}

原回复：
{source}

只输出最终消息，不要解释。
""".strip()
        try:
            if provider is not None:
                resp = await self._tts_provider_text_chat(provider, prompt, max_tokens=700)
                converted = str(getattr(resp, "completion_text", resp) or "").strip()
            else:
                converted = f"<tts>{source}</tts>"
        except Exception as exc:
            logger.warning("[PrivateCompanion] TTS强化转换模型失败: %s", _single_line(exc, 120))
            converted = f"<tts>{source}</tts>"
        converted = self._normalize_tts_tags(converted)
        if "<tts>" not in converted.lower():
            converted = f"<tts>{converted}</tts>"
        return converted

    async def _get_tts_conversion_provider(self, event: Any) -> Any:
        provider_id = str(getattr(self, "tts_conversion_provider_id", "") or "").strip()
        if provider_id:
            getter = getattr(self.context, "get_provider_by_id", None)
            if callable(getter):
                try:
                    return getter(provider_id)
                except Exception:
                    pass
        get_using = getattr(self.context, "get_using_provider", None)
        if callable(get_using) and event is not None:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            try:
                return get_using(umo=umo)
            except TypeError:
                try:
                    return get_using(umo)
                except Exception:
                    return None
            except Exception:
                return None
        return None

    async def _tts_provider_text_chat(self, provider: Any, prompt: str, *, max_tokens: int = 700, task: str = "tts_conversion") -> Any:
        start = time.time()
        provider_id = ""
        provider_id_getter = getattr(self, "_provider_id_from_instance", None)
        if callable(provider_id_getter):
            try:
                provider_id = provider_id_getter(provider)
            except Exception:
                provider_id = ""
        record_usage = getattr(self, "_record_llm_usage", None)
        try:
            try:
                resp = await provider.text_chat(prompt=prompt, max_tokens=max_tokens)
            except TypeError:
                resp = await provider.text_chat(prompt=prompt)
            if callable(record_usage):
                completion = str(getattr(resp, "completion_text", resp) or "")
                record_usage(
                    provider_id=provider_id,
                    task=task,
                    prompt=prompt,
                    completion=completion,
                    elapsed_ms=int((time.time() - start) * 1000),
                    success=True,
                    resp=resp,
                )
            return resp
        except Exception as exc:
            if callable(record_usage):
                record_usage(
                    provider_id=provider_id,
                    task=task,
                    prompt=prompt,
                    completion="",
                    elapsed_ms=int((time.time() - start) * 1000),
                    success=False,
                    error=str(exc),
                )
            raise

    def _open_tts_audio_file_local(self, audio_path: str) -> None:
        path = str(audio_path or "").strip()
        if not path:
            return
        volume = max(0, min(100, _safe_int(getattr(self, "tts_local_playback_volume", 35), 35)))
        if sys.platform.startswith("win"):
            self._play_tts_audio_file_windows_silent(path, volume=volume)
            return
        if sys.platform == "darwin":
            subprocess.run(["afplay", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
            return
        subprocess.run(["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-volume", str(volume), path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)

    def _play_tts_audio_file_windows_silent(self, path: str, *, volume: int = 35) -> None:
        if Path(path).suffix.lower() == ".wav":
            path = self._prepare_windows_wav_for_playback(path)
        if self._run_windows_media_player_script(path, use_wpf=True, volume=volume):
            return
        if self._run_windows_media_player_script(path, use_wpf=False, volume=volume):
            return
        raise RuntimeError("Windows 后台播放器均未能播放该音频")

    def _prepare_windows_wav_for_playback(self, path: str) -> str:
        source = Path(path)
        try:
            data = source.read_bytes()
            if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
                return path
            riff_size = struct.unpack_from("<I", data, 4)[0]
            pos = 12
            fmt_chunk: bytes | None = None
            data_start = 0
            data_size = 0
            while pos + 8 <= len(data):
                chunk_id = data[pos:pos + 4]
                chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
                chunk_start = pos + 8
                remaining = max(0, len(data) - chunk_start)
                actual_size = min(chunk_size, remaining)
                if chunk_id == b"fmt ":
                    fmt_chunk = data[chunk_start:chunk_start + actual_size]
                elif chunk_id == b"data":
                    data_start = chunk_start
                    data_size = actual_size
                    break
                if chunk_size > remaining:
                    break
                pos = chunk_start + chunk_size + (chunk_size % 2)
            if not fmt_chunk or not data_start or data_size <= 0:
                return path
            if riff_size == len(data) - 8:
                declared_data_size = struct.unpack_from("<I", data, data_start - 4)[0]
                if declared_data_size == data_size:
                    return path
            fixed = source.with_name(f"{source.stem}.playback.wav")
            payload = data[data_start:data_start + data_size]
            riff_payload_size = 4 + (8 + len(fmt_chunk)) + (8 + len(payload))
            with fixed.open("wb") as f:
                f.write(b"RIFF")
                f.write(struct.pack("<I", riff_payload_size))
                f.write(b"WAVE")
                f.write(b"fmt ")
                f.write(struct.pack("<I", len(fmt_chunk)))
                f.write(fmt_chunk)
                f.write(b"data")
                f.write(struct.pack("<I", len(payload)))
                f.write(payload)
            return str(fixed)
        except Exception as exc:
            logger.debug("[PrivateCompanion] 修正 WAV 播放头失败，使用原文件: %s", _single_line(exc, 120))
            return path

    def _run_windows_media_player_script(self, path: str, *, use_wpf: bool, volume: int = 35) -> bool:
        volume = max(0, min(100, int(volume)))
        if use_wpf:
            script = (
                "$p = [System.IO.Path]::GetFullPath($args[0]); "
                "$vol = [Math]::Max(0, [Math]::Min(100, [int]$args[1])); "
                "Add-Type -AssemblyName PresentationCore; "
                "$player = New-Object System.Windows.Media.MediaPlayer; "
                "$player.Volume = $vol / 100.0; "
                "$player.Open([Uri]::new($p)); "
                "$deadline = (Get-Date).AddSeconds(10); "
                "while (-not $player.NaturalDuration.HasTimeSpan -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 50 }; "
                "$duration = if ($player.NaturalDuration.HasTimeSpan) { $player.NaturalDuration.TimeSpan.TotalMilliseconds } else { 5000 }; "
                "$player.Play(); "
                "Start-Sleep -Milliseconds ([Math]::Min([Math]::Max([int]$duration + 300, 800), 90000)); "
                "$player.Close()"
            )
            args = ["powershell", "-NoProfile", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script, path, str(volume)]
        else:
            script = (
                "$p = [System.IO.Path]::GetFullPath($args[0]); "
                "$vol = [Math]::Max(0, [Math]::Min(100, [int]$args[1])); "
                "$player = New-Object -ComObject WMPlayer.OCX; "
                "$player.settings.volume = $vol; "
                "$player.URL = $p; "
                "$player.controls.play(); "
                "$deadline = (Get-Date).AddSeconds(90); "
                "while ($player.playState -notin 1,8 -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 100 }; "
                "$player.close()"
            )
            args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script, path, str(volume)]
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=95,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode == 0:
            return True
        logger.debug(
            "[PrivateCompanion] Windows 静默播放方式失败: mode=%s code=%s err=%s",
            "wpf" if use_wpf else "wmp",
            result.returncode,
            _single_line(result.stderr or result.stdout, 160),
        )
        return False

    async def _post_tts_live_subtitle(self, text: str) -> None:
        if not bool(getattr(self, "enable_tts_live_subtitle_sync", False)):
            return
        cleaned = _single_line(text, 500)
        if not cleaned:
            return
        url = str(getattr(self, "tts_live_subtitle_url", "") or "").strip() or "http://127.0.0.1:18081/show"

        def _post() -> None:
            payload = json.dumps({"text": cleaned}, ensure_ascii=False).encode("utf-8")
            request = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(request, timeout=2.0) as response:
                response.read(256)

        try:
            await asyncio.to_thread(_post)
            logger.info("[PrivateCompanion] 已同步 TTS 文本到直播打字机字幕: %s", _single_line(cleaned, 80))
        except Exception as exc:
            logger.debug("[PrivateCompanion] TTS 直播字幕同步失败: %s", _single_line(exc, 120))

    async def _after_tts_audio_generated(
        self,
        audio_path: str,
        spoken_text: str,
        *,
        source: str = "",
        subtitle_text: str = "",
    ) -> None:
        is_live_reply = source == "bili_live_auto_reply"
        visible_text = subtitle_text or spoken_text
        subtitle_task = (
            asyncio.create_task(self._post_tts_live_subtitle(visible_text))
            if is_live_reply
            else None
        )
        if is_live_reply and bool(getattr(self, "enable_tts_local_playback", False)):
            interval = max(0.0, float(getattr(self, "tts_local_playback_min_interval_seconds", 0.0) or 0.0))
            now = time.time()
            if interval <= 0 or now - float(getattr(self, "_tts_local_playback_last_at", 0.0) or 0.0) >= interval:
                self._tts_local_playback_last_at = now
                try:
                    await asyncio.to_thread(self._open_tts_audio_file_local, audio_path)
                    logger.info("[PrivateCompanion] 已触发 TTS 本机播放: %s", _single_line(audio_path, 160))
                except Exception as exc:
                    logger.warning("[PrivateCompanion] TTS 本机播放失败: %s", _single_line(exc, 120))
        if subtitle_task is not None:
            await subtitle_task

    async def _process_tts_tags(self, text: str, event_or_provider: Any, provider_settings: dict[str, Any] | None = None, config: dict[str, Any] | None = None, fallback_plain: str = "") -> list[Any]:
        if hasattr(event_or_provider, "get_result"):
            event = event_or_provider
            try:
                config = self.context.get_config(str(getattr(event, "unified_msg_origin", "") or "")) or {}
            except Exception:
                config = getattr(self, "config", {}) or {}
            provider_settings = dict((config or {}).get("provider_tts_settings", {}) or {})
            try:
                tts_provider = self.context.get_using_tts_provider(str(getattr(event, "unified_msg_origin", "") or ""))
            except Exception:
                tts_provider = None
        else:
            event = None
            tts_provider = event_or_provider
            config = config or getattr(self, "config", {}) or {}
            provider_settings = provider_settings or dict((config or {}).get("provider_tts_settings", {}) or {})
        if not tts_provider:
            fallback_text = fallback_plain or re.sub(TTS_TAG_PATTERN, "", str(text or "")).strip()
            if fallback_text:
                logger.warning(
                    "[PrivateCompanion] TTS强化检测到标签但当前会话没有可用 TTS provider,已按普通文本发送: %s",
                    _single_line(fallback_text, 160),
                )
                return [Plain(fallback_text)]
            return []
        provider_kind = self._tts_provider_kind(tts_provider, provider_settings)
        normalized = self._normalize_tts_tags(text)
        output: list[Any] = []
        record_failed = False
        pos = 0
        for match in re.finditer(r"<tts>(.*?)</tts>", normalized, flags=re.IGNORECASE | re.DOTALL):
            before = normalized[pos:match.start()]
            if before.strip():
                output.append(Plain(before.strip()))
            spoken = self._normalize_tts_spoken_text(match.group(1), provider_kind=provider_kind)
            if not spoken:
                pos = match.end()
                continue
            source_spoken = spoken
            if self._tts_text_needs_language_conversion(spoken, provider_kind=provider_kind):
                before_convert = spoken
                spoken = await self._convert_text_to_spoken_language(spoken, event, provider_kind=provider_kind)
                if spoken != before_convert:
                    logger.info(
                        "[PrivateCompanion] TTS语音块已按目标语种修正: '%s' -> '%s'",
                        _single_line(before_convert, 80),
                        _single_line(spoken, 80),
                    )
            record = await self._tts_record_component(
                spoken,
                tts_provider,
                provider_settings,
                config or {},
                source_text=fallback_plain or source_spoken,
            )
            if record is not None:
                output.append(record)
            else:
                record_failed = True
                if fallback_plain:
                    logger.warning(
                        "[PrivateCompanion] TTS语音组件生成失败,已隐藏朗读文本并保留可见中文: %s",
                        _single_line(spoken, 120),
                    )
                else:
                    output.append(Plain(spoken))
            pos = match.end()
        after = re.sub(r"</?t{2,}s\b[^>]*>", "", normalized[pos:], flags=re.IGNORECASE).strip()
        if after:
            output.append(Plain(after))
        has_record = any(isinstance(comp, Record) for comp in output)
        if record_failed and fallback_plain and not has_record:
            fallback_text = _single_line(fallback_plain, 800)
            visible_text = "\n".join(
                str(getattr(comp, "text", "") or "").strip()
                for comp in output
                if isinstance(comp, Plain)
            ).strip()
            if fallback_text and fallback_text not in visible_text:
                output.append(Plain(fallback_text))
        plain_after_last_record = False
        for comp in reversed(output):
            if isinstance(comp, Record):
                break
            if isinstance(comp, Plain) and str(getattr(comp, "text", "") or "").strip():
                plain_after_last_record = True
        if (
            fallback_plain
            and getattr(self, "tts_voice_language", "ja") != "zh"
            and has_record
            and not plain_after_last_record
        ):
            output.append(Plain(_single_line(fallback_plain, 800)))
        return output

    async def _convert_text_to_spoken_language(self, text: str, event: Any, *, provider_kind: str) -> str:
        provider = await self._get_tts_conversion_provider(event) if event is not None else None
        lang = self._tts_language_label()
        prompt = f"""
把下面内容改写成自然{lang}口语，只输出朗读文本，不要解释。
要求：
- 作品名、人名、专有名词可以按原文保留或自然音译。
- 中文评价、语气词和说明句必须改成{lang}，不要夹中文。
- 保留原本害羞、轻声、亲近的语气。

原文：
{text}
""".strip()
        try:
            if provider is not None:
                resp = await self._tts_provider_text_chat(provider, prompt, max_tokens=360)
                converted = str(getattr(resp, "completion_text", resp) or "").strip()
                return self._normalize_tts_spoken_text(converted, provider_kind=provider_kind) or text
        except Exception:
            pass
        return text

    async def _tts_record_component(
        self,
        spoken: str,
        tts_provider: Any,
        provider_settings: dict[str, Any],
        config: dict[str, Any],
        *,
        source_text: str = "",
    ) -> Any | None:
        provider_kind = self._tts_provider_kind(tts_provider, provider_settings)
        sanitized = self._sanitize_tts_spoken_text(spoken, provider_kind=provider_kind)
        if not sanitized:
            return None
        if sanitized != spoken:
            logger.info(
                "[PrivateCompanion] TTS强化朗读文本已清洗: '%s' -> '%s'",
                _single_line(spoken, 80),
                _single_line(sanitized, 80),
            )
        try:
            audio_path = await tts_provider.get_audio(sanitized)
        except Exception as exc:
            logger.warning("[PrivateCompanion] TTS强化生成语音失败: %s", _single_line(exc, 120))
            return None
        if not audio_path:
            return None
        try:
            audio_file = Path(audio_path).resolve()
            expected_dir = Path(get_astrbot_data_path()).resolve()
            if not audio_file.is_relative_to(expected_dir):
                logger.warning("[PrivateCompanion] TTS强化拒绝不安全语音路径: %s", _single_line(audio_path, 160))
                return None
        except Exception as exc:
            logger.warning("[PrivateCompanion] TTS强化检查语音路径失败: %s", _single_line(exc, 120))
            return None
        final_ref = str(audio_path)
        asyncio.create_task(
            self._after_tts_audio_generated(
                str(audio_path),
                sanitized,
                source="private_companion",
            )
        )
        if provider_settings.get("use_file_service", False):
            callback_api_base = str((config or {}).get("callback_api_base", "") or "").strip()
            if callback_api_base:
                try:
                    token = await file_token_service.register_file(str(audio_path))
                    final_ref = f"{callback_api_base}/api/file/{token}"
                except Exception as exc:
                    logger.warning("[PrivateCompanion] TTS强化注册语音文件失败: %s", _single_line(exc, 120))
        try:
            component = Record(file=final_ref, url=final_ref)
        except TypeError:
            try:
                component = Record(file=final_ref)
            except TypeError:
                component = Record.fromFileSystem(str(audio_path))
        self._annotate_tts_record_component(component, sanitized, source_text=source_text or spoken)
        logger.info("[PrivateCompanion] TTS语音组件已生成: %s", self._tts_component_log_note(component))
        return component
