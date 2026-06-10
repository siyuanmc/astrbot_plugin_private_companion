# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import os
import re
import shutil
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent
try:
    from astrbot.api.message_components import Image, Plain
except ImportError:
    from astrbot.api.message_components import Image, Plain
from astrbot.api.provider import ProviderRequest
from astrbot.core import file_token_service
from astrbot.core.astr_main_agent import MainAgentBuildConfig, build_main_agent
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from .helpers import _now_ts, _safe_float, _safe_int, _single_line, _strip_internal_message_blocks

class PrivateImageMixin:
    """Methods split from main.PrivateCompanionPlugin."""

    def _is_private_image_only_message(self, event: AstrMessageEvent, text: str) -> bool:
        cleaned = _single_line(text, 120)
        if cleaned and cleaned not in {"[图片]", "【图片】", "图片"}:
            return False
        components = self._event_components(event)
        if not components:
            return False
        has_image = False
        for comp in components:
            class_name = comp.__class__.__name__.lower()
            if class_name == "image":
                has_image = True
                continue
            if class_name in {"at", "reply"}:
                continue
            comp_text = _single_line(
                getattr(comp, "text", "")
                or getattr(comp, "message", "")
                or getattr(comp, "content", ""),
                120,
            )
            if comp_text and comp_text not in {"[图片]", "【图片】", "图片"}:
                return False
        return has_image

    def _image_component_source(self, comp: Any) -> str:
        data = getattr(comp, "data", None)
        if not isinstance(data, dict):
            data = comp.get("data") if isinstance(comp, dict) and isinstance(comp.get("data"), dict) else {}
        candidates: list[Any] = []
        for source in (data, comp if isinstance(comp, dict) else None):
            if not isinstance(source, dict):
                continue
            nested = source.get("data")
            if isinstance(nested, dict):
                candidates.append(nested)
            candidates.append(source)
        attrs = (
            "url",
            "origin_url",
            "source_url",
            "src",
            "path",
            "image_path",
            "file_path",
            "local_path",
            "file",
        )
        for attr in attrs:
            for candidate in candidates:
                value = candidate.get(attr)
                text = str(value or "").strip()
                if text:
                    return text
            value = getattr(comp, attr, None)
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def _raw_private_image_sources(self, event: AstrMessageEvent) -> list[str]:
        message_obj = getattr(event, "message_obj", None)
        raw_values = [
            getattr(message_obj, "raw_message", None) if message_obj is not None else None,
            getattr(message_obj, "message", None) if message_obj is not None else None,
            getattr(event, "message_str", None),
        ]
        sources: list[str] = []

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in sources:
                sources.append(text)

        def visit(value: Any) -> None:
            if isinstance(value, list):
                for item in value:
                    visit(item)
                return
            if isinstance(value, dict):
                item_type = str(value.get("type") or value.get("post_type") or "").lower()
                data = value.get("data") if isinstance(value.get("data"), dict) else value
                if item_type == "image":
                    add(self._extract_image_url_from_segment_data(data))
                    for key in ("url", "origin_url", "source_url", "path", "image_path", "file_path", "local_path", "file"):
                        add(data.get(key))
                for key in ("message", "messages", "content", "data"):
                    nested = value.get(key)
                    if nested is not value:
                        visit(nested)
                return
            raw_text = str(value or "")
            for match in re.finditer(r"\[CQ:image,([^\]]+)\]", raw_text):
                fields: dict[str, str] = {}
                for part in match.group(1).split(","):
                    if "=" not in part:
                        continue
                    key, val = part.split("=", 1)
                    fields[key.strip()] = html.unescape(val.strip())
                add(self._extract_image_url_from_segment_data(fields))
                for key in ("url", "path", "file"):
                    add(fields.get(key))

        for raw in raw_values:
            visit(raw)
        return [source for source in sources if source]

    async def _persist_private_inbound_images(self, event: AstrMessageEvent, user_id: str) -> list[str]:
        result: list[str] = []
        target_dir = Path(self.data_dir) / "private_inbound_images" / re.sub(r"[^0-9A-Za-z_.-]+", "_", str(user_id or "unknown"))
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return result
        now_ms = int(_now_ts() * 1000)

        async def resolve_source(comp: Any) -> str:
            source = self._image_component_source(comp)
            if source:
                return source
            converter = getattr(comp, "convert_to_file_path", None)
            if callable(converter):
                try:
                    maybe = converter()
                    return str(await maybe if hasattr(maybe, "__await__") else maybe or "").strip()
                except Exception as exc:
                    logger.debug("[PrivateCompanion] 私聊图片组件转换失败: %s", exc)
            return ""

        for index, comp in enumerate(self._event_components(event), 1):
            class_name = comp.__class__.__name__.lower()
            if isinstance(comp, dict):
                class_name = str(comp.get("type") or "").lower()
            if class_name != "image":
                continue
            source = await resolve_source(comp)
            if not source:
                data = getattr(comp, "data", None)
                data_keys = ",".join(sorted(str(key) for key in data.keys())) if isinstance(data, dict) else ""
                logger.info(
                    "[PrivateCompanion] 私聊图片组件未能解析出文件路径: class=%s data_keys=%s",
                    comp.__class__.__name__,
                    data_keys or "-",
                )
                continue
            source_path = Path(source)
            if source_path.exists() and source_path.is_file():
                suffix = source_path.suffix.lower() if source_path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"} else ".jpg"
                target = target_dir / f"{now_ms}_{index}{suffix}"
                try:
                    shutil.copy2(source_path, target)
                    result.append(str(target))
                    continue
                except Exception as exc:
                    logger.debug("[PrivateCompanion] 私聊图片暂存失败: %s", exc)
            if re.match(r"^https?://", source, flags=re.I):
                persisted = await self._persist_private_remote_image_source(source, target_dir, f"{now_ms}_{index}")
                if persisted:
                    result.append(persisted)
                    continue
            if re.match(r"^(?:data|file|base64)://", source, flags=re.I):
                result.append(source)
        if not result:
            for source in self._raw_private_image_sources(event):
                if not source or source in result:
                    continue
                persisted = await self._persist_private_remote_image_source(source, target_dir, f"{now_ms}_raw_{len(result) + 1}")
                if persisted:
                    result.append(persisted)
                    continue
                if self._private_image_source_to_model_url(source):
                    result.append(source)
        return result

    async def _persist_private_remote_image_source(self, source: str, target_dir: Path, stem: str) -> str:
        text = str(source or "").strip()
        if not re.match(r"^https?://", text, flags=re.I):
            return ""

        def download() -> str:
            try:
                request = urllib.request.Request(
                    text,
                    headers={
                        "User-Agent": "Mozilla/5.0 AstrBot PrivateCompanion/3.2.1",
                        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    },
                )
                with urllib.request.urlopen(request, timeout=15) as response:
                    content_type = str(response.headers.get("Content-Type") or "").lower()
                    length = _safe_int(response.headers.get("Content-Length"), 0, 0)
                    max_bytes = 12 * 1024 * 1024
                    if length and length > max_bytes:
                        logger.info("[PrivateCompanion] 私聊远程图片过大,跳过下载: size=%s url=%s", length, _single_line(text, 120))
                        return ""
                    chunks: list[bytes] = []
                    total = 0
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        total += len(chunk)
                        if total > max_bytes:
                            logger.info("[PrivateCompanion] 私聊远程图片下载超过限制,已中止: url=%s", _single_line(text, 120))
                            return ""
                        chunks.append(chunk)
                data = b"".join(chunks)
                if not data:
                    return ""
                prefix = data[:16]
                suffix = ".jpg"
                if prefix.startswith(b"\x89PNG\r\n\x1a\n") or "png" in content_type:
                    suffix = ".png"
                elif (prefix.startswith(b"RIFF") and b"WEBP" in data[:32]) or "webp" in content_type:
                    suffix = ".webp"
                elif prefix.startswith(b"GIF8") or "gif" in content_type:
                    suffix = ".gif"
                elif prefix.startswith(b"\xff\xd8\xff") or "jpeg" in content_type or "jpg" in content_type:
                    suffix = ".jpg"
                elif "image/" not in content_type:
                    logger.info("[PrivateCompanion] 私聊远程图片响应不是图片,跳过: content_type=%s url=%s", content_type or "-", _single_line(text, 120))
                    return ""
                target = target_dir / f"{re.sub(r'[^0-9A-Za-z_.-]+', '_', stem)}{suffix}"
                target.write_bytes(data)
                return str(target)
            except Exception as exc:
                logger.info("[PrivateCompanion] 私聊远程图片下载失败: %s url=%s", _single_line(exc, 120), _single_line(text, 120))
                return ""

        return await asyncio.to_thread(download)

    async def _prepare_private_image_sources_for_model(self, image_sources: list[str], *, namespace: str = "vision") -> list[str]:
        target_dir = Path(self.data_dir) / "private_inbound_images" / re.sub(r"[^0-9A-Za-z_.-]+", "_", str(namespace or "vision"))
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            return []
        prepared: list[str] = []
        now_ms = int(_now_ts() * 1000)
        for index, source in enumerate([str(item).strip() for item in (image_sources or []) if str(item or "").strip()][:12], 1):
            if re.match(r"^https?://", source, flags=re.I):
                persisted = await self._persist_private_remote_image_source(source, target_dir, f"{now_ms}_{index}")
                if persisted and persisted not in prepared:
                    prepared.append(persisted)
                continue
            if self._private_image_source_to_model_url(source) and source not in prepared:
                prepared.append(source)
        return prepared

    def _private_image_sources_for_astrbot_request(self, image_sources: list[str]) -> list[str]:
        refs: list[str] = []
        for source in [str(item).strip() for item in (image_sources or []) if str(item or "").strip()][:4]:
            text = source
            if text.startswith("file://"):
                text = text[len("file://"):]
            if text.startswith("data:") or text.startswith("base64://"):
                continue
            if re.match(r"^https?://", text, flags=re.I):
                continue
            path = Path(text)
            if not path.exists() or not path.is_file():
                continue
            ref = str(path.resolve())
            if ref not in refs:
                refs.append(ref)
        return refs

    def _private_image_source_to_model_url(self, source: str) -> str:
        text = str(source or "").strip()
        if not text:
            return ""
        if re.match(r"^https?://", text, flags=re.I) or text.startswith("data:"):
            return text
        if text.startswith("base64://"):
            return f"data:image/jpeg;base64,{text[len('base64://'):]}"
        if text.startswith("file://"):
            text = text[len("file://"):]
        path = Path(text)
        if not path.exists() or not path.is_file():
            return ""
        suffix = path.suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/webp" if suffix == ".webp" else "image/gif" if suffix == ".gif" else "image/jpeg"
        try:
            return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"
        except Exception as exc:
            logger.debug("[PrivateCompanion] 私聊图片转 data url 失败: %s", exc)
            return ""

    def _private_image_source_cache_key(self, source: str) -> str:
        text = str(source or "").strip()
        if not text:
            return ""
        try:
            if text.startswith("data:") and "," in text:
                meta, payload = text.split(",", 1)
                raw = base64.b64decode(payload, validate=False) if ";base64" in meta.lower() else payload.encode("utf-8", errors="ignore")
                return "sha256:" + hashlib.sha256(raw).hexdigest()
            if text.startswith("base64://"):
                raw = base64.b64decode(text[len("base64://"):], validate=False)
                return "sha256:" + hashlib.sha256(raw).hexdigest()
            if text.startswith("file://"):
                text = text[len("file://"):]
            path = Path(text)
            if path.exists() and path.is_file():
                return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception as exc:
            logger.debug("[PrivateCompanion] 私聊图片缓存键生成失败: %s", exc)
        if re.match(r"^https?://", text, flags=re.I):
            try:
                parsed = urlparse(text)
                volatile_keys = {
                    "term", "is_origin", "spec", "rkey", "token", "sign", "expires", "expire", "ts",
                    "timestamp", "t", "time", "cache", "cache_key", "ck", "rand", "random", "nonce",
                    "download", "disposition", "file_size", "size", "width", "height",
                }
                query_parts = []
                for key, value in parse_qsl(parsed.query, keep_blank_values=True):
                    lowered = key.lower()
                    if lowered in volatile_keys or lowered.startswith("utm_"):
                        continue
                    query_parts.append((key, value))
                normalized = urlunparse((
                    parsed.scheme.lower() or "https",
                    parsed.netloc.lower(),
                    parsed.path,
                    "",
                    urlencode(sorted(query_parts)),
                    "",
                ))
                return "url:" + hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()
            except Exception:
                return "url:" + hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()
        return ""

    def _private_image_cache_image_keys(self, sources: list[str]) -> list[str]:
        keys: list[str] = []
        for source in sources or []:
            key = self._private_image_source_cache_key(source)
            if key and key not in keys:
                keys.append(key)
        return keys[:4]

    def _private_image_vision_cache_store(self) -> dict[str, Any]:
        cache = self.data.setdefault("private_image_vision_cache", {})
        if not isinstance(cache, dict):
            cache = {}
            self.data["private_image_vision_cache"] = cache
        return cache

    def _private_image_vision_cache_key(self, image_keys: list[str], provider_id: str, prompt: str = "", *, scope: str = "private_image") -> str:
        clean_keys = [str(item).strip() for item in image_keys if str(item or "").strip()]
        if not clean_keys:
            return ""
        raw = "v2|" + _single_line(scope, 40) + "|" + str(provider_id or "") + "|" + "|".join(clean_keys)
        return hashlib.sha1(raw.encode("utf-8", errors="ignore")).hexdigest()

    def _get_private_image_vision_cache(self, cache_key: str, *, provider_id: str = "", image_keys: list[str] | None = None, scope: str = "private_image") -> str:
        if not bool(getattr(self, "enable_private_image_vision_cache", True)):
            return ""
        cache = self._private_image_vision_cache_store()
        clean_image_keys = [str(item).strip() for item in (image_keys or []) if str(item or "").strip()]

        def use_item(key: str, item: dict[str, Any], *, fallback: bool = False) -> str:
            text = _single_line(item.get("text"), 900 if scope == "forward_image" else 600)
            if not text:
                cache.pop(key, None)
                return ""
            item["hits"] = _safe_int(item.get("hits"), 0, 0) + 1
            item["last_hit_ts"] = _now_ts()
            if fallback and cache_key and key != cache_key:
                item.setdefault("migrated_from", key)
                cache[cache_key] = item
                cache.pop(key, None)
            self._record_cache_metric(f"image_vision:{scope}", hit=True, detail="fallback" if fallback else "direct")
            return text

        item = cache.get(cache_key)
        if isinstance(item, dict):
            text = use_item(cache_key, item)
            if text:
                return text

        if clean_image_keys:
            expected_provider = _single_line(provider_id, 160)
            expected_scope = _single_line(scope, 40)
            for key, item in list(cache.items()):
                if key == cache_key or not isinstance(item, dict):
                    continue
                cached_keys = [str(value).strip() for value in item.get("image_keys", []) if str(value or "").strip()]
                if cached_keys != clean_image_keys:
                    continue
                cached_provider = _single_line(item.get("provider_id"), 160)
                if expected_provider and cached_provider and cached_provider != expected_provider:
                    continue
                cached_scope = _single_line(item.get("scope"), 40)
                if cached_scope and expected_scope and cached_scope != expected_scope:
                    continue
                text = use_item(key, item, fallback=True)
                if text:
                    return text

        self._record_cache_metric(f"image_vision:{scope}", hit=False, detail="miss")
        return ""

    def _set_private_image_vision_cache(self, cache_key: str, text: str, *, provider_id: str, image_keys: list[str], prompt: str = "", scope: str = "private_image") -> None:
        if not bool(getattr(self, "enable_private_image_vision_cache", True)):
            return
        cleaned = _single_line(text, 900 if scope == "forward_image" else 600)
        if not cache_key or not cleaned:
            return
        cache = self._private_image_vision_cache_store()
        cache[cache_key] = {
            "text": cleaned,
            "provider_id": _single_line(provider_id, 160),
            "image_keys": [str(item) for item in image_keys[:4]],
            "scope": _single_line(scope, 40),
            "prompt_sig": hashlib.sha1(str(prompt or "").encode("utf-8", errors="ignore")).hexdigest()[:16] if prompt else "",
            "created_ts": _now_ts(),
            "last_hit_ts": 0,
            "hits": 0,
        }
        max_items = int(getattr(self, "private_image_vision_cache_max_items", 300) or 0)
        if max_items > 0 and len(cache) > max_items:
            stale = sorted(
                cache.items(),
                key=lambda item: _safe_float((item[1] if isinstance(item[1], dict) else {}).get("last_hit_ts"), 0)
                or _safe_float((item[1] if isinstance(item[1], dict) else {}).get("created_ts"), 0),
            )
            for key, _ in stale[: max(1, len(cache) - max_items)]:
                cache.pop(key, None)
        try:
            self._save_data_sync()
        except Exception as exc:
            logger.debug("[PrivateCompanion] 私聊图片视觉缓存保存失败: %s", exc)

    def _invalidate_private_image_vision_cache_by_image_keys(self, image_keys: list[str], *, reason: str = "") -> int:
        targets = {str(item) for item in image_keys or [] if str(item or "").strip()}
        if not targets:
            return 0
        cache = self._private_image_vision_cache_store()
        removed = 0
        for key, item in list(cache.items()):
            if not isinstance(item, dict):
                continue
            cached_keys = {str(value) for value in item.get("image_keys", []) if str(value or "").strip()}
            if cached_keys & targets:
                cache.pop(key, None)
                removed += 1
        if removed:
            logger.info("[PrivateCompanion] 私聊图片视觉缓存已因负反馈失效: removed=%s reason=%s", removed, _single_line(reason, 120))
            try:
                self._save_data_sync()
            except Exception as exc:
                logger.debug("[PrivateCompanion] 私聊图片视觉缓存失效保存失败: %s", exc)
        return removed

    def _is_private_image_vision_negative_feedback(self, text: str) -> bool:
        cleaned = _single_line(text, 160)
        if not cleaned:
            return False
        negative_patterns = (
            r"(识别|看|理解|读|认).{0,8}(错|不对|不准|偏了|歪了)",
            r"(不是|不对|错了).{0,12}(这个意思|这样|这意思|你说的|图里|图片|表情包)",
            r"(你|bot|机器人).{0,8}(看错|认错|理解错|识别错)",
            r"(不是.{0,8}你|不是.{0,8}bot|不是.{0,8}本人|不是.{0,8}这个)",
        )
        return any(re.search(pattern, cleaned, flags=re.I) for pattern in negative_patterns)

    def _apply_private_image_vision_negative_feedback(self, user: dict[str, Any], text: str) -> bool:
        if not self._is_private_image_vision_negative_feedback(text):
            return False
        target = user.get("last_private_image_vision_feedback_target")
        if not isinstance(target, dict):
            return False
        ts = _safe_float(target.get("ts"), 0)
        if ts <= 0 or _now_ts() - ts > 180:
            return False
        image_keys = [str(item) for item in target.get("image_keys", []) if str(item or "").strip()]
        removed = self._invalidate_private_image_vision_cache_by_image_keys(image_keys, reason=text)
        target["negative_feedback_ts"] = _now_ts()
        target["negative_feedback_text"] = _single_line(text, 160)
        target["invalidated_cache_items"] = removed
        logger.info(
            "[PrivateCompanion] 私聊图片视觉负反馈记录: user_image_keys=%s removed=%s text=%s",
            len(image_keys),
            removed,
            _single_line(text, 120),
        )
        return bool(removed or image_keys)

    def _astrbot_provider_settings_for_umo(self, umo: str = "") -> dict[str, Any]:
        try:
            cfg = self.context.get_config(umo=umo) if umo else self.context.get_config()
        except Exception:
            try:
                cfg = self.context.get_config()
            except Exception:
                cfg = {}
        provider_settings = cfg.get("provider_settings", {}) if isinstance(cfg, dict) else {}
        return dict(provider_settings) if isinstance(provider_settings, dict) else {}

    def _private_image_caption_provider_id(self, umo: str = "") -> tuple[str, str, str]:
        provider_settings = self._astrbot_provider_settings_for_umo(umo)
        astrbot_provider_id = _single_line(provider_settings.get("default_image_caption_provider_id"), 160)
        prompt = str(provider_settings.get("image_caption_prompt") or "").strip()
        if astrbot_provider_id:
            return astrbot_provider_id, "astrbot_image_caption", prompt
        fallback_provider_id = self._task_provider(self.jm_cosmos_vision_provider_id, self.narration_provider_id)
        return fallback_provider_id, "plugin_vision", prompt

    def _private_image_provider_by_id(self, provider_id: str) -> Any:
        provider_id = _single_line(provider_id, 160)
        if not provider_id:
            return None
        getter = getattr(self.context, "get_provider_by_id", None)
        if not callable(getter):
            return None
        try:
            return getter(provider_id)
        except Exception:
            return None

    def _private_image_visual_provider_candidates(self, umo: str = "") -> list[tuple[str, str, str]]:
        provider_settings = self._astrbot_provider_settings_for_umo(umo)
        prompt = str(provider_settings.get("image_caption_prompt") or "").strip()
        return [
            (_single_line(provider_settings.get("default_image_caption_provider_id"), 160), "astrbot_image_caption", prompt),
            (self._task_provider(self.jm_cosmos_vision_provider_id, self.narration_provider_id), "plugin_vision", prompt),
            (self._task_provider(self.llm_provider_id), "plugin_main", prompt),
        ]

    def _select_private_image_visual_provider(self, umo: str = "") -> tuple[str, str, str, Any]:
        seen: set[str] = set()
        for provider_id, provider_source, prompt in self._private_image_visual_provider_candidates(umo):
            provider_id = _single_line(provider_id, 160)
            if not provider_id or provider_id in seen:
                continue
            seen.add(provider_id)
            if self._private_image_provider_in_failure_cooldown(provider_id, provider_source):
                continue
            provider = self._private_image_provider_by_id(provider_id)
            if provider is not None and self._provider_supports_image(provider):
                return provider_id, provider_source, prompt, provider
        return "", "", "", None

    def _private_image_provider_failure_cache(self) -> dict[str, Any]:
        cache = getattr(self, "_private_image_provider_failures", None)
        if not isinstance(cache, dict):
            cache = {}
            try:
                setattr(self, "_private_image_provider_failures", cache)
            except Exception:
                return {}
        return cache

    def _private_image_provider_failure_key(self, provider_id: str, provider_source: str = "") -> str:
        return f"{_single_line(provider_source, 80)}:{_single_line(provider_id, 160)}"

    def _private_image_provider_in_failure_cooldown(self, provider_id: str, provider_source: str = "") -> bool:
        key = self._private_image_provider_failure_key(provider_id, provider_source)
        item = self._private_image_provider_failure_cache().get(key)
        if not isinstance(item, dict):
            return False
        until = _safe_float(item.get("until"), 0)
        if until <= _now_ts():
            self._private_image_provider_failure_cache().pop(key, None)
            return False
        return True

    def _mark_private_image_provider_failure(self, provider_id: str, provider_source: str, exc: Exception | str, *, task: str) -> None:
        key = self._private_image_provider_failure_key(provider_id, provider_source)
        cooldown = 300.0
        self._private_image_provider_failure_cache()[key] = {
            "until": _now_ts() + cooldown,
            "provider_id": _single_line(provider_id, 160),
            "source": _single_line(provider_source, 80),
            "task": _single_line(task, 80),
            "error": _single_line(exc, 180),
        }
        logger.info(
            "[PrivateCompanion] 图片视觉 provider 临时降权: provider=%s source=%s task=%s cooldown=%ss error=%s",
            provider_id,
            provider_source,
            task,
            int(cooldown),
            _single_line(exc, 160),
        )

    def _clear_private_image_provider_failure(self, provider_id: str, provider_source: str = "") -> None:
        self._private_image_provider_failure_cache().pop(
            self._private_image_provider_failure_key(provider_id, provider_source),
            None,
        )

    def _private_image_model_image_items(self, image_sources: list[str]) -> list[tuple[str, str]]:
        image_items: list[tuple[str, str]] = []
        seen_image_keys: set[str] = set()
        for source in [str(item).strip() for item in (image_sources or []) if str(item or "").strip()][:4]:
            url = self._private_image_source_to_model_url(source)
            if not url:
                continue
            image_key = self._private_image_source_cache_key(source) or ("model_url:" + hashlib.sha1(url.encode("utf-8", errors="ignore")).hexdigest())
            if image_key in seen_image_keys:
                continue
            seen_image_keys.add(image_key)
            image_items.append((image_key, url))
        return image_items

    @staticmethod
    def _provider_supports_image(provider: Any) -> bool:
        config = getattr(provider, "provider_config", None) or getattr(provider, "config", None) or {}
        modalities = config.get("modalities") if isinstance(config, dict) else None
        return isinstance(modalities, list) and "image" in modalities

    def _event_main_provider_supports_image(self, event: AstrMessageEvent) -> bool:
        provider = None
        try:
            selected = _single_line(event.get_extra("selected_provider"), 160)
        except Exception:
            selected = ""
        try:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            image_caption_provider_id = _single_line(
                self._astrbot_provider_settings_for_umo(umo).get("default_image_caption_provider_id"),
                160,
            )
        except Exception:
            image_caption_provider_id = ""
        if selected and image_caption_provider_id and selected == image_caption_provider_id:
            logger.info(
                "[PrivateCompanion] 私聊图片 selected_provider 是图片转述模型,不按主视觉模型直挂: provider=%s",
                selected,
            )
            selected = ""
        getter = getattr(self.context, "get_provider_by_id", None)
        if selected and callable(getter):
            try:
                provider = getter(str(selected))
            except Exception:
                provider = None
        if provider is None:
            get_using = getattr(self.context, "get_using_provider", None)
            if callable(get_using):
                try:
                    provider = get_using(umo=getattr(event, "unified_msg_origin", ""))
                except TypeError:
                    try:
                        provider = get_using(getattr(event, "unified_msg_origin", ""))
                    except Exception:
                        provider = None
                except Exception:
                    provider = None
        return self._provider_supports_image(provider)

    def _private_image_role_self_recognition_hint(self) -> str:
        raw = str(getattr(self, "private_image_self_recognition_hint", "") or "")
        if not raw.strip():
            return ""
        user_labels = (
            "对用户的称呼", "用户性别", "用户生日", "用户年龄", "用户职业",
            "是角色的XX", "与角色的相处方式", "与用户关系", "相处边界",
        )
        kept: list[str] = []
        for line in raw.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if any(stripped.startswith(f"{label}：") or stripped.startswith(f"{label}:") for label in user_labels):
                continue
            kept.append(stripped)
        return _single_line("\n".join(kept), 900)

    def _private_image_self_recognition_prompt(self) -> str:
        if not bool(getattr(self, "enable_private_image_self_recognition", True)):
            return ""
        bot_name = _single_line(getattr(self, "bot_name", ""), 40)
        schedule_persona = str(getattr(self, "schedule_persona_prompt", "") or "")
        custom_hint = self._private_image_role_self_recognition_hint()
        visual_profile_parts: list[str] = []
        for label in ("姓名", "年龄", "生日", "性别", "识别点", "外貌", "发型发色", "瞳色", "服饰风格", "种族", "职业/身份"):
            value = self._roleplay_labeled_value(schedule_persona, label)
            if value:
                visual_profile_parts.append(f"{label}：{value}")
        visual_profile = "\n".join(visual_profile_parts)
        parts = [
            f"当前角色名称/可能出现在图中的名字：{bot_name}" if bot_name else "",
            f"结构化外观线索：\n{visual_profile}" if visual_profile else "",
            f"额外角色自我识别线索：{custom_hint}" if custom_hint else "",
        ]
        context = "\n".join(part for part in parts if part)
        if not context:
            return ""
        return (
            "【角色识别线索】\n"
            "以下只用于给图片归属打标签,不要展开推理,不要复述规则。当前角色不是发图用户。\n"
            "这里的“当前角色自己/当前角色的表情包”包括头像、Q版、二创、表情包、同人图和风格化卡通形象；"
            "不要求图片写出角色名字,也不要求完全等同官方立绘。\n"
            "如果画面主体同时命中多个当前角色显著视觉锚点,例如发色/发型、瞳色、发饰、服饰、物种、星月等专属元素,"
            "且没有明显冲突,请优先判断为当前角色自己；如果明显是表情包或贴纸语境,判断为当前角色的表情包。\n"
            "只有视觉锚点过少、与角色线索冲突,或主体明显是无关人物/物品时,才写无法判断或用户发来的无关图片。\n"
            f"{context}\n"
            "只在最后一行输出归属标签：图像归属判断：当前角色自己/当前角色的表情包/当前角色的聊天截图/发图用户本人/用户发来的无关图片/无法判断。"
        )

    def _roleplay_labeled_value(self, text: str, label: str, *, limit: int = 180) -> str:
        source = str(text or "")
        if not source or not label:
            return ""
        label_pattern = re.escape(str(label))
        known_labels = (
            "姓名", "种族", "年龄", "生日", "性别", "识别点", "外貌", "发型发色", "瞳色", "服饰风格",
            "职业/身份", "身份", "性格描述", "核心欲望/目标", "爱好", "禁忌",
            "关键设定", "其他补充信息", "所处世界", "所在世界", "时代背景",
            "基本法则/基调", "特殊规则", "主要活动场景", "世界观关系网",
            "对用户的称呼", "用户性别", "用户生日", "用户职业", "是角色的XX", "与角色的相处方式",
        )
        stop_pattern = "|".join(re.escape(item) for item in known_labels if item != label)
        match = re.search(
            rf"(?m)^\s*{label_pattern}\s*[：:]\s*(.*?)(?=^\s*(?:{stop_pattern})\s*[：:]|\Z)",
            source,
            flags=re.S,
        )
        if not match:
            return ""
        return _single_line(match.group(1), limit)

    def _private_image_identity_disambiguation_instruction(self) -> str:
        return (
            "若视觉摘要包含“图像归属判断”,请按该标签区分身份："
            "当前角色/Bot/assistant 指当前回复者扮演的角色这一方,user/用户指发图者这一方。"
            "但回复主目标始终是理解用户发这张图想表达什么；"
            "归属判断只是补充线索,只有用户明确问归属、图片文字/梗依赖 Bot 身份,或自然接话需要时,才轻轻带到自我关联。"
            "普通表情包优先按表情包文字、情绪和动作回应,不要把每张相似图都变成辨认当前角色自己。"
        )

    def _private_image_intent_line(self, text: str) -> str:
        segment = self._private_image_labeled_segment(text, "图像表达意图")
        if segment:
            return segment
        for raw_line in str(text or "").replace("；", "\n").replace("。", "\n").splitlines():
            line = _single_line(raw_line, 220)
            if "图像表达意图" in line or "表达意图" in line:
                return line
        return ""

    def _private_image_ownership_line(self, text: str) -> str:
        segment = self._private_image_labeled_segment(text, "图像归属判断")
        if segment:
            return segment
        for raw_line in str(text or "").replace("；", "\n").replace("。", "\n").splitlines():
            line = _single_line(raw_line, 180)
            if "图像归属判断" in line or "归属判断" in line:
                return line
        return ""

    @staticmethod
    def _private_image_labeled_segment(text: str, label: str) -> str:
        source = _single_line(text, 900)
        if not source or not label:
            return ""
        next_labels = ("图片类型", "可见内容", "图像表达意图", "图像归属判断")
        starts = [source.find(f"{label}："), source.find(f"{label}:")]
        starts = [idx for idx in starts if idx >= 0]
        if not starts:
            return ""
        start = min(starts)
        colon_idx = source.find("：", start)
        ascii_colon_idx = source.find(":", start)
        colon_candidates = [idx for idx in (colon_idx, ascii_colon_idx) if idx >= 0]
        if not colon_candidates:
            return ""
        value_start = min(colon_candidates) + 1
        value_end = len(source)
        for next_label in next_labels:
            if next_label == label:
                continue
            for marker in (f" {next_label}：", f" {next_label}:", f"{next_label}：", f"{next_label}:"):
                idx = source.find(marker, value_start)
                if idx >= 0:
                    value_end = min(value_end, idx)
        value = _single_line(source[value_start:value_end], 160)
        return f"{label}：{value}" if value else ""

    def _private_image_ownership_kind(self, ownership_line: str) -> str:
        compact = re.sub(r"\s+", "", str(ownership_line or "")).lower()
        if "当前角色的表情包" in compact or "bot的表情包" in compact:
            return "bot_sticker"
        if "当前角色的聊天截图" in compact or "bot的聊天截图" in compact:
            return "bot_chat"
        if "当前角色自己" in compact or "当前回复角色自己" in compact or "bot自己" in compact:
            return "bot_self"
        if "发图用户本人" in compact or "用户本人" in compact:
            return "user_self"
        if "用户发来的无关图片" in compact:
            return "unrelated"
        if "无法判断" in compact:
            return "unknown"
        return ""

    def _private_image_reply_objective(self, ownership_line: str) -> str:
        kind = self._private_image_ownership_kind(ownership_line)
        if kind in {"bot_self", "bot_sticker", "bot_chat"}:
            return (
                "回复目标：优先回应图片作为用户消息的表达意图,例如表情包文字、情绪、动作或梗。"
                "这张图是用户发来的聊天内容,不是让回复者复述图片台词或扮演图片角色；"
                "请直接回应用户这次调侃、吐槽、撒娇或分享的行为。"
                "不要使用括号动作、神态旁白或舞台描写,只写真正会发给用户看的短聊天句。"
                "归属判断指向当前回复者这一方时,只把它作为语气辅助；"
            "除非用户在问归属或语境明显需要,不要主动把重点放在辨认当前角色自己。"
            )
        if kind == "user_self":
            return (
                "回复目标：优先回应图片作为用户消息的表达意图。"
                "这张图是用户发来的聊天内容,不是让回复者复述图片台词或扮演图片角色；"
                "不要使用括号动作、神态旁白或舞台描写。"
                "归属判断指向用户本人时,注意不要说成是当前回复者自己。"
            )
        return (
            "回复目标：优先回应图片作为用户消息的表达意图；"
            "不要复述图片台词、不要扮演图片角色、不要使用括号动作或神态旁白。"
            "如果归属无法判断,不要强行认定属于任何一方。"
        )

    async def _transcribe_private_inbound_images(self, image_sources: list[str], *, umo: str = "") -> str:
        sources = await self._prepare_private_image_sources_for_model(
            [str(item).strip() for item in (image_sources or []) if str(item or "").strip()][:4],
            namespace="private_vision",
        )
        if not sources:
            return ""
        image_items = self._private_image_model_image_items(sources)
        image_keys = [key for key, _ in image_items]
        image_urls = [url for _, url in image_items]
        if not image_urls:
            return ""
        default_prompt = (
            "请把用户刚发的图片压缩成给聊天模型看的短摘要。只输出下面 4 行,不要写标题、分析过程、帧列表或长篇描述。\n"
            "图片类型：<照片/截图/表情包/聊天记录/其他>\n"
            "可见内容：<主体、文字或最关键细节,30字内>\n"
            "图像表达意图：<用户可能表达的情绪、态度或梗,30字内>\n"
            "图像归属判断：<当前角色自己/当前角色的表情包/当前角色的聊天截图/发图用户本人/用户发来的无关图片/无法判断>\n"
            "无法确定就写无法判断；不要为了归属判断反复比较。"
        )
        attempts = 0
        seen: set[str] = set()
        for provider_id, provider_source, _configured_prompt in self._private_image_visual_provider_candidates(umo):
            provider_id = _single_line(provider_id, 160)
            if not provider_id or provider_id in seen:
                continue
            seen.add(provider_id)
            if self._private_image_provider_in_failure_cooldown(provider_id, provider_source):
                continue
            provider = self._private_image_provider_by_id(provider_id)
            if provider is None or not self._provider_supports_image(provider):
                continue
            attempts += 1
            prompt = default_prompt
            self_recognition_prompt = self._private_image_self_recognition_prompt()
            if self_recognition_prompt and self_recognition_prompt not in prompt:
                prompt = f"{prompt}\n\n{self_recognition_prompt}"
            cache_key = self._private_image_vision_cache_key(image_keys, provider_id, prompt, scope="private_image")
            cached_text = self._get_private_image_vision_cache(cache_key, provider_id=provider_id, image_keys=image_keys, scope="private_image")
            if cached_text:
                intent_line = self._private_image_intent_line(cached_text)
                ownership_line = self._private_image_ownership_line(cached_text)
                logger.info(
                    "[PrivateCompanion] 私聊图片视觉转述命中缓存: provider=%s images=%s intent=%s ownership=%s preview=%s",
                    provider_id,
                    len(image_urls),
                    intent_line or "无",
                    ownership_line or "无",
                    _single_line(cached_text, 220),
                )
                return cached_text
            if not self._can_run_llm_task(provider_id, task="private_image_vision"):
                self._record_llm_budget_skip(provider_id=provider_id, task="private_image_vision", prompt=prompt)
                continue
            try:
                start = time.time()
                result = await provider.text_chat(prompt=prompt, image_urls=image_urls, max_tokens=220)
                text = str(getattr(result, "completion_text", result) or "").strip()
                cleaned_text = _single_line(_strip_internal_message_blocks(text), 600)
                intent_line = self._private_image_intent_line(cleaned_text)
                ownership_line = self._private_image_ownership_line(cleaned_text)
                self._record_llm_usage(
                    provider_id=provider_id,
                    task="private_image_vision",
                    prompt=prompt,
                    completion=text,
                    resp=result,
                    elapsed_ms=int((time.time() - start) * 1000),
                    success=True,
                    budget_exempt=True,
                )
                self._clear_private_image_provider_failure(provider_id, provider_source)
                logger.info(
                    "[PrivateCompanion] 私聊图片视觉转述完成: provider=%s source=%s images=%s chars=%s intent=%s ownership=%s preview=%s",
                    provider_id,
                    provider_source,
                    len(image_urls),
                    len(text),
                    intent_line or "无",
                    ownership_line or "无",
                    _single_line(cleaned_text, 220),
                )
                self._set_private_image_vision_cache(cache_key, cleaned_text, provider_id=provider_id, image_keys=image_keys, prompt=prompt, scope="private_image")
                return cleaned_text
            except Exception as exc:
                self._record_llm_usage(
                    provider_id=provider_id,
                    task="private_image_vision",
                    prompt=prompt,
                    completion="",
                    elapsed_ms=int((time.time() - start) * 1000) if "start" in locals() else 0,
                    success=False,
                    error=_single_line(exc, 180),
                    budget_exempt=True,
                )
                self._mark_private_image_provider_failure(provider_id, provider_source, exc, task="private_image_vision")
                continue
        logger.info("[PrivateCompanion] 私聊图片视觉转述失败: 所有候选 provider 均不可用或失败 attempts=%s", attempts)
        return ""

    async def _consume_semantic_message_buffer_for_event(self, event: AstrMessageEvent, *, private_chat: bool) -> str:
        try:
            sender_id = str(event.get_sender_id())
        except Exception:
            sender_id = ""
        if not sender_id:
            return ""
        force_consume = False
        if private_chat:
            if not self.enable_semantic_message_debounce:
                return ""
            wait = max(0.0, float(getattr(self, "semantic_message_debounce_seconds", 0.0) or 0.0))
            if wait <= 0:
                return ""
            scope = f"private:{sender_id}"
            key = self._semantic_buffer_key(scope, sender_id)
        else:
            group_id = self._extract_group_id_from_event(event)
            if not group_id:
                return ""
            scope = f"group:{group_id}"
            high_intensity = getattr(event, "private_companion_group_high_intensity", None)
            buffers = getattr(self, "_semantic_message_buffers", None)
            high_key = self._group_high_intensity_buffer_key(group_id)
            if isinstance(high_intensity, dict) and high_intensity.get("active") and isinstance(buffers, dict) and isinstance(buffers.get(high_key), dict):
                key = high_key
                force_consume = True
            else:
                if not self.enable_semantic_message_debounce:
                    return ""
                wait = max(0.0, float(getattr(self, "semantic_message_debounce_seconds", 0.0) or 0.0))
                if wait <= 0:
                    return ""
                key = self._semantic_buffer_key(scope, sender_id)
        buffers = getattr(self, "_semantic_message_buffers", None)
        if not isinstance(buffers, dict):
            return ""
        buffer = buffers.get(key)
        if not isinstance(buffer, dict):
            return ""
        wait = max(0.0, _safe_float(buffer.get("wait_seconds"), getattr(self, "semantic_message_debounce_seconds", 0.0), 0.0))
        if wait <= 0:
            return ""
        deadline_guard = _now_ts() + max(wait + 2.0, min(30.0, wait * 3.0 + 2.0))
        while True:
            buffer = buffers.get(key)
            if not isinstance(buffer, dict):
                return ""
            updated_ts = _safe_float(buffer.get("updated_ts"), buffer.get("first_ts"), _now_ts())
            remaining = max(0.0, updated_ts + wait - _now_ts())
            if remaining <= 0:
                break
            if _now_ts() + remaining > deadline_guard:
                remaining = max(0.0, deadline_guard - _now_ts())
                if remaining <= 0:
                    break
            await asyncio.sleep(min(remaining, 1.0))
        buffer = buffers.pop(key, None)
        if not isinstance(buffer, dict):
            return ""
        messages = buffer.get("messages") if isinstance(buffer.get("messages"), list) else []
        lines = []
        for item in messages[:8]:
            if not isinstance(item, dict):
                continue
            text = _single_line(item.get("text"), 260)
            if text:
                name = _single_line(item.get("sender_name"), 40)
                if force_consume and name:
                    lines.append(f"{name}: {text}")
                else:
                    lines.append(text)
        if len(lines) <= 1:
            return ""
        return "\n".join(f"{idx + 1}. {line}" for idx, line in enumerate(lines))

    def _take_buffered_private_images_for_event(self, event: AstrMessageEvent) -> list[str]:
        context = self._take_buffered_private_image_context_for_event(event)
        return [str(item) for item in context.get("images", [])[:4] if str(item or "").strip()] if isinstance(context, dict) else []

    def _completed_private_image_vision_task_text(self, vision_task: Any) -> str:
        if not isinstance(vision_task, asyncio.Task) or not vision_task.done() or vision_task.cancelled():
            return ""
        try:
            return _single_line(vision_task.result(), 600)
        except Exception as exc:
            logger.info("[PrivateCompanion] 私聊单图后台视觉任务结果读取失败: %s", _single_line(exc, 120))
            return ""

    def _normalize_private_image_reply_text(self, text: str) -> str:
        cleaned = str(text or "").strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        if "\n" not in cleaned and re.search(r"[\u4e00-\u9fff][ \t]+[\u4e00-\u9fff]", cleaned):
            # Some providers use spaces as short-message pauses. Preserve that intent for manual sends.
            cleaned = re.sub(r"(?<=[\u4e00-\u9fff…！？?！~～])\s+(?=[\u4e00-\u9fff])", "\n", cleaned)
        return cleaned.strip()

    async def _send_private_image_reply_text(self, event: AstrMessageEvent, reply: str) -> None:
        text = self._normalize_private_image_reply_text(reply)
        if not text:
            return
        should_segment = (
            bool(getattr(self, "enable_segmented_proactive_reply", False))
            and str(getattr(self, "segmented_proactive_scope", "") or "") == "all_llm"
        )
        segments = self._split_proactive_text(text) if should_segment else [part.strip() for part in text.splitlines() if part.strip()]
        segments = [segment for segment in segments if segment]
        if not segments:
            segments = [text]
        if len(segments) <= 1:
            await event.send(event.plain_result(segments[0]))
            return
        logger.info("[PrivateCompanion] 私聊单图回复按手动链路分段发送: segments=%s", len(segments))
        for index, segment in enumerate(segments):
            await event.send(event.plain_result(segment))
            if index < len(segments) - 1:
                await asyncio.sleep(await self._calc_segmented_proactive_interval(segment))

    def _take_buffered_private_image_context_for_event(self, event: AstrMessageEvent) -> dict[str, Any]:
        try:
            sender_id = str(event.get_sender_id())
        except Exception:
            sender_id = ""
        if not sender_id:
            return {}
        key = self._semantic_buffer_key(f"private:{sender_id}", sender_id)
        buffers = getattr(self, "_semantic_message_buffers", None)
        if not isinstance(buffers, dict):
            return {}
        buffer = buffers.get(key)
        if not isinstance(buffer, dict):
            return {}
        if _now_ts() - _safe_float(buffer.get("updated_ts"), buffer.get("first_ts"), 0) > max(30.0, float(getattr(self, "semantic_message_debounce_seconds", 8.0) or 8.0) + 30.0):
            return {}
        images = buffer.pop("images", [])
        return {
            "images": [str(item) for item in images[:4] if str(item or "").strip()],
            "image_mode": _single_line(buffer.pop("image_mode", ""), 20),
            "vision_task": buffer.pop("vision_task", None),
            "vision_text": _single_line(buffer.pop("vision_text", ""), 600),
        }

    async def _send_delayed_private_image_only_event(
        self,
        event: AstrMessageEvent,
        user_id: str,
        buffer: dict[str, Any],
    ) -> None:
        images = buffer.get("images") if isinstance(buffer.get("images"), list) else []
        vision_task = buffer.get("vision_task")
        vision_text = _single_line(buffer.get("vision_text"), 600)
        if not vision_text and isinstance(vision_task, asyncio.Task):
            timeout = max(0.0, float(getattr(self, "private_image_vision_wait_seconds", 30.0) or 0.0))
            try:
                if timeout > 0:
                    logger.info("[PrivateCompanion] 私聊单图等待视觉转述完成: user=%s timeout=%.1fs", user_id, timeout)
                    vision_text = _single_line(await asyncio.wait_for(asyncio.shield(vision_task), timeout=timeout), 600)
            except asyncio.TimeoutError:
                logger.info("[PrivateCompanion] 私聊单图延迟处理时视觉转述仍未完成: user=%s timeout=%.1fs", user_id, timeout)
            except Exception as exc:
                logger.info("[PrivateCompanion] 私聊单图延迟视觉转述失败: user=%s error=%s", user_id, _single_line(exc, 120))
        ownership_line = self._private_image_ownership_line(vision_text)
        intent_line = self._private_image_intent_line(vision_text)
        prompt = _single_line(getattr(event, "message_str", ""), 120) or "[图片]"
        reply_objective = self._private_image_reply_objective(ownership_line)
        logger.info(
            "[PrivateCompanion] 私聊单图准备进入主链: user=%s images=%s has_vision=%s intent=%s ownership=%s objective=%s vision_preview=%s",
            user_id,
            len(images),
            bool(vision_text),
            intent_line or "无",
            ownership_line or "无",
            _single_line(reply_objective, 120),
            _single_line(vision_text, 220),
        )
        raw_image_sources = [str(item) for item in images[:4] if str(item or "").strip()]
        image_items = self._private_image_model_image_items(raw_image_sources)
        model_image_urls = [url for _, url in image_items]
        request_image_refs = self._private_image_sources_for_astrbot_request(raw_image_sources)
        try:
            umo = str(getattr(event, "unified_msg_origin", "") or "")
            framework_event = event
            if umo:
                try:
                    from astrbot.core.platform.message_session import MessageSession
                    from .proactive_message import SyntheticPrivateWakeEvent

                    session = MessageSession.from_str(umo)
                    sender_name = ""
                    try:
                        sender_name = _single_line(event.get_sender_name(), 60)
                    except Exception:
                        sender_name = ""
                    framework_event = SyntheticPrivateWakeEvent(
                        context=self.context,
                        session=session,
                        message="[图片]",
                        sender_name=sender_name or "PrivateCompanion",
                    )
                    try:
                        selected_provider = event.get_extra("selected_provider")
                        if selected_provider:
                            framework_event.set_extra("selected_provider", selected_provider)
                    except Exception:
                        pass
                    logger.info("[PrivateCompanion] 私聊单图主链使用合成私聊事件执行: user=%s session=%s", user_id, umo)
                except Exception as exc:
                    framework_event = event
                    logger.info("[PrivateCompanion] 私聊单图合成私聊事件创建失败,回退原事件: user=%s error=%s", user_id, _single_line(exc, 160))
            setattr(framework_event, "private_companion_deferred_private_image_only_ready", True)
            setattr(framework_event, "private_companion_deferred_private_image_only", False)
            setattr(framework_event, "private_companion_delayed_image_vision_text", vision_text)
            setattr(framework_event, "private_companion_delayed_image_sources", list(request_image_refs))
            buffered_image_mode = _single_line(buffer.get("image_mode"), 20)
            main_provider_supports_image = self._event_main_provider_supports_image(framework_event)
            direct_image_mode = bool(request_image_refs and buffered_image_mode == "direct" and main_provider_supports_image)
            direct_provider_id = ""
            direct_provider_source = "current_main_provider"
            if direct_image_mode:
                try:
                    direct_provider_id = _single_line(framework_event.get_extra("selected_provider"), 160)
                except Exception:
                    direct_provider_id = ""
                if not direct_provider_id:
                    direct_provider_id = "current_main_provider"
                setattr(framework_event, "private_companion_delayed_image_mode", "direct")
            elif request_image_refs:
                setattr(framework_event, "private_companion_delayed_image_mode", "caption")
            elif not vision_text and images:
                vision_text = _single_line(await self._transcribe_private_inbound_images(images, umo=umo), 600)
                setattr(framework_event, "private_companion_delayed_image_vision_text", vision_text)
                ownership_line = self._private_image_ownership_line(vision_text)
                intent_line = self._private_image_intent_line(vision_text)
                reply_objective = self._private_image_reply_objective(ownership_line)
            conv = None
            if umo:
                conv_id = await self.context.conversation_manager.get_curr_conversation_id(umo)
                if conv_id:
                    conv = await self.context.conversation_manager.get_conversation(umo, conv_id)
            cfg = self.context.get_config(umo=umo) if umo else self.context.get_config()
            provider_settings = cfg.get("provider_settings", {}) if isinstance(cfg, dict) else {}
            build_cfg = MainAgentBuildConfig(
                tool_call_timeout=int(provider_settings.get("tool_call_timeout", 120) or 120),
                llm_safety_mode=False,
                streaming_response=False,
            )
            req = ProviderRequest(
                prompt=prompt,
                conversation=conv,
                session_id=getattr(framework_event, "session_id", None) or umo,
            )
            previous_selected_provider = ""
            selected_provider_changed = False
            if direct_image_mode:
                req.image_urls = list(request_image_refs)
            await self.inject_humanized_state(framework_event, req)
            if direct_image_mode:
                existing = getattr(req, "image_urls", None)
                if not isinstance(existing, list):
                    existing = []
                for image_ref in request_image_refs:
                    if image_ref not in existing:
                        existing.append(image_ref)
                req.image_urls = existing
                logger.info(
                    "[PrivateCompanion] 私聊单图主链已挂载图片: user=%s provider=%s source=%s images=%s has_vision=%s",
                    user_id,
                    direct_provider_id,
                    direct_provider_source,
                    len(existing),
                    bool(vision_text),
                )
            start = time.time()
            captured_tool_sends = []
            try:
                async def _runner_factory():
                    return await build_main_agent(
                        event=framework_event,
                        plugin_context=self.context,
                        config=build_cfg,
                        req=req,
                    )

                capture_runner = getattr(self, "_capture_framework_send_message_calls", None)
                if callable(capture_runner) and umo:
                    result, captured_tool_sends = await capture_runner(
                        target_session=umo,
                        runner_factory=_runner_factory,
                    )
                    if captured_tool_sends:
                        logger.info(
                            "[PrivateCompanion] 私聊单图主链拦截到框架工具直发: user=%s count=%s",
                            user_id,
                            len(captured_tool_sends),
                        )
                else:
                    result = await _runner_factory()
                    runner_for_step = getattr(result, "agent_runner", None) if result else None
                    if runner_for_step is not None and hasattr(runner_for_step, "step_until_done"):
                        async for _ in runner_for_step.step_until_done(20):
                            pass
            finally:
                if selected_provider_changed:
                    try:
                        framework_event.set_extra("selected_provider", previous_selected_provider)
                    except Exception:
                        pass
            runner = getattr(result, "agent_runner", None) if result else None
            llm_resp = runner.get_final_llm_resp() if runner else None
            reply = str(getattr(llm_resp, "completion_text", "") or "").strip()
            reply_source = "main_chain"
            if not reply and captured_tool_sends:
                captured_text_parts: list[str] = []
                sanitizer = getattr(self, "_sanitize_captured_plain_text", None)
                for call in reversed(captured_tool_sends):
                    messages = getattr(call, "messages", [])
                    if not isinstance(messages, list):
                        continue
                    for item in messages:
                        if not isinstance(item, dict):
                            continue
                        if str(item.get("type") or "").strip().lower() != "plain":
                            continue
                        raw_text = item.get("text")
                        text_value = sanitizer(raw_text) if callable(sanitizer) else _single_line(raw_text, 260)
                        if text_value:
                            captured_text_parts.append(text_value)
                    if captured_text_parts:
                        break
                reply = _single_line("\n".join(captured_text_parts), 500)
                if reply:
                    reply_source = "main_chain_tool_capture"
                    logger.info(
                        "[PrivateCompanion] 私聊单图主链工具直发文本已转为普通回复: user=%s chars=%s reply_preview=%s",
                        user_id,
                        len(reply),
                        _single_line(reply, 180),
                    )
            if reply:
                logger.info(
                    "[PrivateCompanion] 私聊单图主链回复生成: user=%s chars=%s intent=%s ownership=%s reply_preview=%s",
                    user_id,
                    len(reply),
                    intent_line or "无",
                    ownership_line or "无",
                    _single_line(reply, 180),
                )
            if not reply:
                if not vision_text and images:
                    vision_text = self._completed_private_image_vision_task_text(vision_task)
                    if vision_text:
                        logger.info(
                            "[PrivateCompanion] 私聊单图兜底前取到后台视觉摘要: user=%s preview=%s",
                            user_id,
                            _single_line(vision_text, 220),
                        )
                    else:
                        vision_text = _single_line(await self._transcribe_private_inbound_images(images, umo=umo), 600)
                    setattr(event, "private_companion_delayed_image_vision_text", vision_text)
                    ownership_line = self._private_image_ownership_line(vision_text)
                    intent_line = self._private_image_intent_line(vision_text)
                    reply_objective = self._private_image_reply_objective(ownership_line)
                fallback_prompt = (
                    "用户刚刚只发了一张图片,没有补充文字。请用当前私聊人格自然回复一句,像 QQ 私聊短句；不要提模型、插件、视觉转述或路径,不要使用括号动作、神态旁白或舞台描写。\n"
                    f"{self._private_image_identity_disambiguation_instruction()}\n"
                    f"{reply_objective}\n"
                    f"图片内容摘要：{vision_text}"
                    if vision_text
                    else "用户刚刚只发了一张图片,没有补充文字。当前没有可靠图片内容。请自然回复一句,不要编造画面,可以让用户补一句想让你看哪里。"
                )
                fallback_reply = await self._llm_call(
                    fallback_prompt,
                    max_tokens=160,
                    task="private_image_only_fallback",
                )
                reply = _single_line(_strip_internal_message_blocks(fallback_reply or ""), 500)
                reply_source = "fallback_llm"
                logger.info(
                    "[PrivateCompanion] 私聊单图兜底回复生成: user=%s chars=%s intent=%s ownership=%s objective=%s reply_preview=%s",
                    user_id,
                    len(reply),
                    intent_line or "无",
                    ownership_line or "无",
                    _single_line(reply_objective, 120),
                    _single_line(reply, 180),
                )
                if not reply:
                    reply_source = "fallback_static"
                    reply = (
                        f"我看到了，{_single_line(vision_text, 120)}"
                        if vision_text
                        else "我看到你发了图片，但这边暂时没看清内容。你补一句想让我看哪里就好。"
                    )
                logger.warning("[PrivateCompanion] 私聊单图原生链路回复为空,已使用兜底回复: user=%s images=%s", user_id, len(images))
            self._record_llm_usage(
                provider_id="framework",
                task="private_image_only_framework",
                prompt=prompt,
                completion=reply,
                elapsed_ms=int((time.time() - start) * 1000),
                success=True,
                resp=llm_resp,
                budget_exempt=True,
            )
            await self._send_private_image_reply_text(event, reply)
            image_keys = self._private_image_cache_image_keys([str(item) for item in images[:4] if str(item or "").strip()])
            if image_keys:
                try:
                    async with self._data_lock:
                        user = self._get_user(user_id)
                        user["last_private_image_vision_feedback_target"] = {
                            "ts": _now_ts(),
                            "image_keys": image_keys,
                            "vision_text": _single_line(vision_text, 600),
                            "reply": _single_line(reply, 300),
                            "ownership": ownership_line,
                            "intent": intent_line,
                        }
                        self._save_data_sync()
                except Exception as exc:
                    logger.debug("[PrivateCompanion] 私聊图片视觉反馈目标记录失败: %s", exc)
            if reply_source == "main_chain":
                logger.info("[PrivateCompanion] 私聊单图无补充说明,已由原生 LLM 链路回复: user=%s images=%s", user_id, len(images))
            else:
                logger.info(
                    "[PrivateCompanion] 私聊单图无补充说明,原生链路为空,已由兜底回复发送: user=%s images=%s source=%s",
                    user_id,
                    len(images),
                    reply_source,
                )
        except Exception as exc:
            logger.warning("[PrivateCompanion] 私聊单图延迟回复失败: user=%s error=%s", user_id, _single_line(exc, 180), exc_info=True)

    async def _finalize_private_image_buffer_after_wait(self, key: str, user_id: str, first_ts: float) -> None:
        wait = max(0.0, float(getattr(self, "semantic_message_debounce_seconds", 0.0) or 0.0))
        remaining = max(0.0, first_ts + wait - _now_ts())
        if remaining > 0:
            await asyncio.sleep(remaining)
        buffers = getattr(self, "_semantic_message_buffers", None)
        buffer = buffers.get(key) if isinstance(buffers, dict) else None
        if not isinstance(buffer, dict):
            return
        messages = buffer.get("messages") if isinstance(buffer.get("messages"), list) else []
        placeholder = "用户刚刚先单独发送了一张图片,可能马上会补充说明。"
        has_followup = any(
            isinstance(item, dict)
            and (cleaned := _single_line(item.get("text"), 260))
            and cleaned != placeholder
            for item in messages
        )
        if has_followup:
            logger.info("[PrivateCompanion] 私聊单图已由补充消息接管: user=%s", user_id)
            return
        buffers.pop(key, None)
        original_event = buffer.get("original_event")
        if isinstance(original_event, AstrMessageEvent):
            await self._send_delayed_private_image_only_event(original_event, user_id, buffer)
            return
        vision_task = buffer.get("vision_task")
        if isinstance(vision_task, asyncio.Task) and not vision_task.done():
            vision_task.cancel()
        logger.info("[PrivateCompanion] 私聊单图等待补充后无文字指示,但原事件不可用: user=%s", user_id)

