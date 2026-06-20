# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import json
import time
import re
import shutil
import base64
import hashlib
import mimetypes
import secrets
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import quote

from astrbot.api import logger
from quart import request, send_file

from .helpers import _safe_int, _strip_internal_message_blocks, _today_key
from .page_api_users_groups import PrivateCompanionPageApiUsersGroupsMixin

PLUGIN_NAME = "astrbot_plugin_private_companion"
PAGE_API_PREFIX = f"/{PLUGIN_NAME}/page"


class PrivateCompanionPageApi(PrivateCompanionPageApiUsersGroupsMixin):
    """AstrBot 官方插件拓展页面 API。"""

    PERCENT_PROBABILITY_KEYS = {
        "group_repeat_follow_probability",
        "group_repeat_interrupt_probability",
        "group_repeat_interrupt_probability_step",
        "group_wakeup_interest_probability",
        "group_wakeup_topic_interest_max_boost",
        "group_wakeup_debounce_pending_penalty",
        "tts_trigger_probability",
        "auto_voice_probability",
        "main_user_mention_voice_probability",
        "rest_reply_probability",
    }
    INHERIT_PERCENT_PROBABILITY_KEYS = {
        "tts_private_trigger_probability",
        "tts_group_trigger_probability",
        "main_user_voice_probability",
    }

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin
        self._schema_bool_key_cache: set[str] | None = None

    def register_routes(self) -> None:
        register = self.plugin.context.register_web_api
        routes = [
            ("/overview", self.get_overview, ["GET"], "Private Companion Page overview"),
            ("/users", self.list_users, ["GET"], "Private Companion Page users"),
            ("/user", self.get_user, ["GET"], "Private Companion Page user detail"),
            ("/user/update", self.update_user, ["POST"], "Private Companion Page update user"),
            ("/groups", self.list_groups, ["GET"], "Private Companion Page groups"),
            ("/group", self.get_group, ["GET"], "Private Companion Page group detail"),
            ("/group/update", self.update_group, ["POST"], "Private Companion Page update group"),
            ("/settings/update", self.update_settings, ["POST"], "Private Companion Page update settings"),
            ("/diagnostics", self.get_diagnostics, ["GET"], "Private Companion Page diagnostics"),
            ("/troubleshooting", self.get_troubleshooting, ["GET"], "Private Companion Page troubleshooting"),
            ("/troubleshooting/test", self.run_troubleshooting_test, ["POST"], "Private Companion Page troubleshooting test"),
            ("/token/stats", self.get_token_stats, ["GET"], "Private Companion Page token stats"),
            ("/token/reset", self.reset_token_stats, ["POST"], "Private Companion Page reset token stats"),
            ("/image_cache/list", self.list_image_cache, ["GET"], "Private Companion Page image cache list"),
            ("/image_cache/preview", self.get_image_cache_preview, ["GET"], "Private Companion Page image cache preview"),
            ("/image_cache/update", self.update_image_cache_item, ["POST"], "Private Companion Page update image cache item"),
            ("/image_cache/delete", self.delete_image_cache_item, ["POST"], "Private Companion Page delete image cache item"),
            ("/bookshelf/unlock", self.unlock_bookshelf, ["POST"], "Private Companion Page unlock bookshelf"),
            ("/bookshelf/image", self.get_bookshelf_image, ["GET"], "Private Companion Page bookshelf image"),
            ("/bookshelf/image_data", self.get_bookshelf_image_data, ["GET"], "Private Companion Page bookshelf image data"),
            ("/bookshelf/delete", self.delete_bookshelf_item, ["POST"], "Private Companion Page delete bookshelf item"),
            ("/bookshelf/rate", self.rate_bookshelf_item, ["POST"], "Private Companion Page rate bookshelf item"),
            ("/bookshelf/tags", self.update_bookshelf_item_tags, ["POST"], "Private Companion Page update bookshelf item tags"),
            ("/bookshelf/comments/update", self.update_bookshelf_item_comments, ["POST"], "Private Companion Page update bookshelf item comments"),
            ("/worldbook/import", self.import_worldbook, ["POST"], "Private Companion Page import worldbook"),
            ("/worldbook/member/livingmemory", self.get_worldbook_member_livingmemory, ["GET"], "Private Companion Page worldbook member LivingMemory"),
            ("/worldbook/member/update", self.update_worldbook_member, ["POST"], "Private Companion Page update worldbook member"),
            ("/worldbook/observations/clear", self.clear_worldbook_pending_observations, ["POST"], "Private Companion Page clear worldbook pending observations"),
            ("/worldbook/group/update", self.update_worldbook_group, ["POST"], "Private Companion Page update worldbook group"),
            ("/skill/update", self.update_skill_growth, ["POST"], "Private Companion Page update skill growth"),
            ("/external_ability/update", self.update_external_ability, ["POST"], "Private Companion Page update external proactive ability"),
            ("/preset/apply", self.apply_preset, ["POST"], "Private Companion Page apply preset"),
            ("/providers/available", self.list_available_providers, ["GET"], "Private Companion Page available providers"),
            ("/provider/test", self.test_provider, ["POST"], "Private Companion Page test provider"),
        ]
        for path, handler, methods, desc in routes:
            register(f"{PAGE_API_PREFIX}{path}", handler, methods, desc)

    async def get_overview(self) -> dict[str, Any]:
        try:
            async with self.plugin._data_lock:
                self._auto_import_worldbook_if_needed_locked()
                refresher = getattr(self.plugin, "_refresh_sleep_runtime_state", None)
                if callable(refresher):
                    refresher()
                data = deepcopy(self.plugin.data)
            users = data.get("users") if isinstance(data.get("users"), dict) else {}
            groups = data.get("groups") if isinstance(data.get("groups"), dict) else {}
            enabled_users = sum(1 for item in users.values() if isinstance(item, dict) and item.get("enabled", True))
            visible_groups = {
                str(group_id): group
                for group_id, group in groups.items()
                if isinstance(group, dict) and not self._looks_like_member_shadow_group(str(group_id), group)
            }
            enabled_groups = sum(1 for item in visible_groups.values() if isinstance(item, dict) and item.get("enabled", True))
            return self._ok(
                {
                    "plugin": {
                        "enabled": bool(getattr(self.plugin, "enabled", False)),
                        "bot_name": getattr(self.plugin, "bot_name", ""),
                        "data_file": getattr(self.plugin, "data_file", ""),
                        "data_version": data.get("version"),
                    },
                    "private": {
                        "user_count": len(users),
                        "enabled_user_count": enabled_users,
                        "require_opt_in": bool(getattr(self.plugin, "require_private_opt_in", True)),
                        "max_daily_messages": getattr(self.plugin, "max_daily_messages", 0),
                        "idle_minutes": getattr(self.plugin, "idle_minutes", 0),
                        "min_interval_minutes": getattr(self.plugin, "min_interval_minutes", 0),
                    },
                    "group": {
                        "enabled": bool(getattr(self.plugin, "enable_group_companion", False)),
                        "group_count": len(visible_groups),
                        "enabled_group_count": enabled_groups,
                        "shadow_group_count": max(0, len(groups) - len(visible_groups)),
                        "access_mode": getattr(self.plugin, "group_access_mode", "whitelist"),
                        "whitelist": self.plugin._configured_group_ids(),
                        "blacklist": self.plugin._configured_group_blacklist_ids(),
                        "interjection_enabled": bool(getattr(self.plugin, "enable_group_interjection", False)),
                        "repeat_follow_enabled": bool(getattr(self.plugin, "enable_group_repeat_follow", False)),
                    },
                    "features": self._feature_flags(),
                    "providers": self._provider_settings(),
                    "settings": self._runtime_settings(),
                    "cache": self._cache_summary(data),
                    "livingmemory": self._livingmemory_summary(),
                    "screen_companion": self._screen_companion_summary(data),
                    "knowledge": self.plugin._roleplay_knowledge_summary(),
                    "worldbook": self._worldbook_summary(data),
                    "proactive_candidates": self._proactive_candidate_summary(data),
                    "proactive_tasks": self._proactive_task_summary(data),
                    "message_debounce": self._message_debounce_summary(data),
                    "bilibili": self._bilibili_summary(data),
                    "news": self._news_summary(data),
                    "web_exploration": self._web_exploration_summary(data),
                    "qzone": self._qzone_summary(data),
                    "private_reading": self._jm_cosmos_summary(data),
                    "creative": self._creative_summary(data),
                    "bookshelf": await self._bookshelf_summary(data, unlocked=False),
                    "skill_growth": self._skill_growth_summary(data),
                    "external_abilities": self._external_ability_summary(data),
                    "life_observation": self._life_observation_summary(data),
                    "daily_state": self._daily_state_summary(data.get("daily_state")),
                    "daily_timeline": self._daily_timeline_summary(data),
                }
            )
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取总览失败: {exc}", exc_info=True)
            return self._error(str(exc))

    def _cache_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        image_cache = data.get("private_image_vision_cache") if isinstance(data.get("private_image_vision_cache"), dict) else {}
        metrics = data.get("cache_metrics") if isinstance(data.get("cache_metrics"), dict) else {}

        def metric_row(name: str) -> dict[str, Any]:
            item = metrics.get(name) if isinstance(metrics.get(name), dict) else {}
            hits = 0
            misses = 0
            try:
                hits = max(0, int(item.get("hits") or 0))
            except (TypeError, ValueError):
                hits = 0
            try:
                misses = max(0, int(item.get("misses") or 0))
            except (TypeError, ValueError):
                misses = 0
            total = hits + misses
            return {
                "hits": hits,
                "misses": misses,
                "total": total,
                "hit_rate": round(hits / total, 4) if total else 0,
                "last_hit_at": self.plugin._format_timestamp_elapsed(item.get("last_hit_ts", 0)),
                "last_miss_at": self.plugin._format_timestamp_elapsed(item.get("last_miss_ts", 0)),
            }

        atrelay_cache = getattr(self.plugin, "_atrelay_member_cache", {})
        atrelay_count = len(atrelay_cache) if isinstance(atrelay_cache, dict) else 0
        weather = data.get("daily_weather") if isinstance(data.get("daily_weather"), dict) else {}
        weather_age = self.plugin._format_timestamp_elapsed(weather.get("fetched_ts", 0)) if weather else ""
        return {
            "private_image_vision": {
                "enabled": bool(getattr(self.plugin, "enable_private_image_vision_cache", False)),
                "items": len(image_cache),
                "max_items": int(getattr(self.plugin, "private_image_vision_cache_max_items", 0) or 0),
                "private": metric_row("image_vision:private_image"),
                "forward": metric_row("image_vision:forward_image"),
            },
            "atrelay_member_cache": {
                "items": atrelay_count,
                "ttl_minutes": int(getattr(self.plugin, "atrelay_member_cache_minutes", 0) or 0),
            },
            "weather": {
                "cached": bool(weather),
                "age": weather_age,
            },
        }

    async def list_image_cache(self) -> dict[str, Any]:
        try:
            scope_filter = self._single_line(request.args.get("scope"), 40)
            keyword = self._single_line(request.args.get("q"), 120).lower()
            limit = self._query_int("limit", 80, 1, 300)
            offset = self._query_int("offset", 0, 0, 100000)
            async with self.plugin._data_lock:
                data = deepcopy(self.plugin.data)
            cache = data.get("private_image_vision_cache") if isinstance(data.get("private_image_vision_cache"), dict) else {}
            rows: list[dict[str, Any]] = []
            scopes: set[str] = set()
            for key, raw in cache.items():
                if not isinstance(raw, dict):
                    continue
                item = self._image_cache_item_summary(str(key), raw)
                scope = item.get("scope") or "private_image"
                scopes.add(str(scope))
                if scope_filter and scope_filter != "all" and scope != scope_filter:
                    continue
                if keyword:
                    haystack = " ".join(
                        str(item.get(name) or "")
                        for name in (
                            "key",
                            "text",
                            "provider_id",
                            "scope",
                            "image_keys_text",
                            "image_aliases_text",
                            "image_type",
                            "ownership",
                            "intent",
                        )
                    ).lower()
                    if keyword not in haystack:
                        continue
                rows.append(item)
            rows.sort(
                key=lambda item: (
                    self._float(item.get("last_hit_ts"))
                    or self._float(item.get("created_ts")),
                    self._float(item.get("created_ts")),
                ),
                reverse=True,
            )
            total = len(rows)
            return self._ok(
                {
                    "items": rows[offset : offset + limit],
                    "total": total,
                    "offset": offset,
                    "limit": limit,
                    "scopes": sorted(scopes),
                    "enabled": bool(getattr(self.plugin, "enable_private_image_vision_cache", False)),
                    "max_items": int(getattr(self.plugin, "private_image_vision_cache_max_items", 0) or 0),
                }
            )
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取图片缓存失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def update_image_cache_item(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        key = self._single_line(payload.get("key"), 120)
        if not key:
            return self._error("缺少缓存 key")
        text = str(payload.get("text") or "").strip()
        if not text:
            return self._error("视觉摘要不能为空")
        try:
            async with self.plugin._data_lock:
                cache = self.plugin.data.get("private_image_vision_cache")
                if not isinstance(cache, dict) or not isinstance(cache.get(key), dict):
                    return self._error("缓存条目不存在")
                item = cache[key]
                scope = self._single_line(item.get("scope"), 40) or "private_image"
                item["text"] = self._single_line(text, 900 if scope == "forward_image" else 600)
                if "provider_id" in payload:
                    item["provider_id"] = self._single_line(payload.get("provider_id"), 160)
                if "scope" in payload:
                    next_scope = self._single_line(payload.get("scope"), 40)
                    if next_scope:
                        item["scope"] = next_scope
                item["edited_ts"] = time.time()
                self.plugin._save_data_sync()
                updated = deepcopy(item)
            return self._ok(self._image_cache_item_summary(key, updated))
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新图片缓存失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def get_image_cache_preview(self) -> Any:
        key = self._single_line(request.args.get("key"), 120)
        if not key:
            return self._error("缺少缓存 key")
        try:
            async with self.plugin._data_lock:
                cache = deepcopy(self.plugin.data.get("private_image_vision_cache") or {})
            item = cache.get(key) if isinstance(cache, dict) else None
            if not isinstance(item, dict):
                return self._error("缓存条目不存在")
            preview_path = self._single_line(item.get("preview_path"), 260)
            if not preview_path:
                return self._error("该缓存没有预览图")
            path = Path(preview_path).resolve()
            base = (Path(getattr(self.plugin, "data_dir", "")) / "private_image_cache_previews").resolve()
            if not path.is_file() or not path.is_relative_to(base):
                return self._error("预览图不存在")
            response = await send_file(path)
            response.headers["Cache-Control"] = "private, max-age=3600"
            return response
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取图片缓存预览失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def delete_image_cache_item(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        key = self._single_line(payload.get("key"), 120)
        if not key:
            return self._error("缺少缓存 key")
        try:
            preview_path = ""
            async with self.plugin._data_lock:
                cache = self.plugin.data.get("private_image_vision_cache")
                if not isinstance(cache, dict) or key not in cache:
                    return self._error("缓存条目不存在")
                removed = cache.pop(key, None)
                if isinstance(removed, dict):
                    preview_path = self._single_line(removed.get("preview_path"), 260)
                self.plugin._save_data_sync()
                remaining = len(cache)
            self._remove_image_cache_preview_file(preview_path)
            return self._ok({"key": key, "remaining": remaining})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 删除图片缓存失败: {exc}", exc_info=True)
            return self._error(str(exc))

    def _remove_image_cache_preview_file(self, preview_path: str) -> None:
        if not preview_path:
            return
        try:
            path = Path(preview_path).resolve()
            base = (Path(getattr(self.plugin, "data_dir", "")) / "private_image_cache_previews").resolve()
            if path.is_file() and path.is_relative_to(base):
                path.unlink(missing_ok=True)
        except Exception:
            pass

    def _image_cache_item_summary(self, key: str, raw: dict[str, Any]) -> dict[str, Any]:
        text = str(raw.get("text") or "").strip()
        image_keys = [str(value).strip() for value in raw.get("image_keys", []) if str(value or "").strip()]
        image_aliases = [str(value).strip() for value in raw.get("image_aliases", []) if str(value or "").strip()]
        scope = self._single_line(raw.get("scope"), 40) or "private_image"
        created_ts = self._float(raw.get("created_ts"))
        last_hit_ts = self._float(raw.get("last_hit_ts"))
        edited_ts = self._float(raw.get("edited_ts"))
        preview_path = self._single_line(raw.get("preview_path"), 260)
        preview_exists = False
        if preview_path:
            try:
                preview_exists = Path(preview_path).is_file()
            except Exception:
                preview_exists = False
        return {
            "key": self._single_line(key, 120),
            "text": self._single_line(text, 900 if scope == "forward_image" else 600),
            "provider_id": self._single_line(raw.get("provider_id"), 160),
            "scope": scope,
            "prompt_sig": self._single_line(raw.get("prompt_sig"), 32),
            "image_keys": image_keys[:8],
            "image_aliases": image_aliases[:12],
            "image_keys_text": " ".join(image_keys[:8]),
            "image_aliases_text": " ".join(image_aliases[:12]),
            "image_count": _safe_int(raw.get("image_count"), len(image_keys), 0),
            "preview_url": f"{PAGE_API_PREFIX}/image_cache/preview?key={quote(key, safe='')}" if preview_exists else "",
            "preview_size": _safe_int(raw.get("preview_size"), 0, 0),
            "preview_width": _safe_int(raw.get("preview_width"), 0, 0),
            "preview_height": _safe_int(raw.get("preview_height"), 0, 0),
            "hits": _safe_int(raw.get("hits"), 0, 0),
            "created_ts": created_ts,
            "last_hit_ts": last_hit_ts,
            "edited_ts": edited_ts,
            "created": self.plugin._format_timestamp_elapsed(created_ts),
            "last_hit": self.plugin._format_timestamp_elapsed(last_hit_ts),
            "edited": self.plugin._format_timestamp_elapsed(edited_ts),
            "image_type": self._extract_labeled_text(text, "图片类型", 40),
            "visible": self._extract_labeled_text(text, "可见内容", 180),
            "intent": self._extract_labeled_text(text, "图像表达意图", 180),
            "ownership": self._extract_labeled_text(text, "图像归属判断", 80),
        }

    @staticmethod
    def _extract_labeled_text(text: str, label: str, limit: int) -> str:
        source = str(text or "")
        pattern = rf"{re.escape(label)}\s*[：:]\s*(.+?)(?=(?:\s+[^\s：:]{{2,20}}\s*[：:])|$)"
        match = re.search(pattern, source)
        if not match:
            return ""
        return PrivateCompanionPageApi._single_line(match.group(1), limit)

    def _auto_import_worldbook_if_needed_locked(self) -> None:
        if not bool(getattr(self.plugin, "worldbook_auto_import", False)):
            return
        if not bool(getattr(self.plugin, "enable_worldbook_member_recognition", False)):
            return
        data = getattr(self.plugin, "data", {})
        if not isinstance(data, dict):
            return
        has_imported = bool(data.get("worldbook_entries")) or bool(data.get("worldbook_member_profiles")) or bool(data.get("worldbook_group_profiles"))
        if has_imported:
            return
        importer = getattr(self.plugin, "_import_worldbook_entries_from_sources", None)
        if not callable(importer):
            return
        if importer():
            self.plugin._save_data_sync()


    async def update_settings(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        try:
            changed: dict[str, Any] = {}
            if "group_access_mode" in payload:
                mode = str(payload.get("group_access_mode") or "").strip().lower()
                if mode not in {"whitelist", "blacklist"}:
                    return self._error("group_access_mode 只能是 whitelist 或 blacklist")
                changed["group_access_mode"] = mode
            if "group_whitelist_ids" in payload:
                changed["group_whitelist_ids"] = self._normalize_id_list(payload.get("group_whitelist_ids"))
            if "group_blacklist_ids" in payload:
                changed["group_blacklist_ids"] = self._normalize_id_list(payload.get("group_blacklist_ids"))
            for key, value in (payload.get("features") or {}).items():
                if key in self._allowed_feature_keys():
                    changed[key] = self._normalize_bool_value(value)
                elif key in self._schema_bool_keys() and key in self._allowed_setting_keys():
                    changed[key] = self._normalize_bool_value(value)
            for key, value in (payload.get("providers") or {}).items():
                if key in self._allowed_provider_keys():
                    changed[key] = self._single_line(value, 160)
            for key, value in (payload.get("settings") or {}).items():
                if key in self._allowed_setting_keys():
                    changed[key] = self._normalize_setting_value(key, value)
            for key, value in changed.items():
                self._apply_config_value(key, value, changed)
            config_saved = True
            if changed:
                config_saved = await self._save_config_if_possible()
            overview = await self.get_overview()
            if overview.get("success"):
                overview["data"]["changed"] = changed
                overview["data"]["config_saved"] = config_saved
                data = overview.get("data") if isinstance(overview.get("data"), dict) else {}
                features = data.get("features") if isinstance(data.get("features"), dict) else {}
                settings = data.get("settings") if isinstance(data.get("settings"), dict) else {}
                for key, value in changed.items():
                    if key in self._allowed_feature_keys():
                        features[key] = self._normalize_bool_value(value)
                    if key in self._allowed_setting_keys():
                        settings[key] = value
            return overview
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新设置失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def get_diagnostics(self) -> dict[str, Any]:
        try:
            async with self.plugin._data_lock:
                data = deepcopy(self.plugin.data)
            users = data.get("users") if isinstance(data.get("users"), dict) else {}
            groups = data.get("groups") if isinstance(data.get("groups"), dict) else {}
            items = self._build_diagnostics(users, groups)
            return self._ok({"items": items})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取诊断失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def get_troubleshooting(self) -> dict[str, Any]:
        try:
            async with self.plugin._data_lock:
                data = deepcopy(self.plugin.data)
            users = data.get("users") if isinstance(data.get("users"), dict) else {}
            groups = data.get("groups") if isinstance(data.get("groups"), dict) else {}
            diagnostics = self._build_diagnostics(users, groups)
            proactive_tasks = self._proactive_task_summary(data)
            proactive_candidates = self._proactive_candidate_summary(data)
            token_stats = self._token_stats_payload(data.get("token_usage", {}))
            cache = self._cache_summary(data)
            tts = self._tts_runtime_summary(users)
            sqlite_status = await self._sqlite_wal_status_summary()
            recent_events = self._troubleshooting_recent_events(
                diagnostics=diagnostics,
                proactive_tasks=proactive_tasks,
                proactive_candidates=proactive_candidates,
                token_stats=token_stats,
            )
            checks = self._troubleshooting_checks(
                data=data,
                users=users,
                diagnostics=diagnostics,
                proactive_tasks=proactive_tasks,
                proactive_candidates=proactive_candidates,
                token_stats=token_stats,
                cache=cache,
                tts=tts,
                sqlite_status=sqlite_status,
            )
            counts = {
                "error": sum(1 for item in recent_events if item.get("level") == "error") + sum(1 for item in checks if item.get("level") == "error"),
                "warn": sum(1 for item in recent_events if item.get("level") == "warn") + sum(1 for item in checks if item.get("level") == "warn"),
                "info": sum(1 for item in recent_events if item.get("level") == "info") + sum(1 for item in checks if item.get("level") == "info"),
                "ok": sum(1 for item in checks if item.get("level") == "ok"),
            }
            headline_level = "error" if counts["error"] else ("warn" if counts["warn"] else "ok")
            headline = "发现需要处理的异常" if headline_level == "error" else ("有可关注项" if headline_level == "warn" else "运行状态正常")
            return self._ok(
                {
                    "summary": {
                        "level": headline_level,
                        "headline": headline,
                        "counts": counts,
                        "generated_at": self.plugin._format_timestamp_elapsed(time.time()),
                    },
                    "recent_events": recent_events[:80],
                    "checks": checks,
                    "diagnostics": diagnostics,
                    "sqlite": sqlite_status,
                    "chain_tests": self._troubleshooting_test_results(data),
                    "prompt_injections": self._prompt_injection_summary(data),
                    "proactive_runtime": proactive_tasks.get("runtime", {}),
                    "token_budget": token_stats.get("budget", {}),
                    "cache": cache,
                }
            )
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取排障信息失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def run_troubleshooting_test(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        test_type = self._single_line(payload.get("type"), 40)
        start = time.time()
        try:
            if test_type == "image_generation":
                result = await self._run_image_generation_chain_test(payload)
            elif test_type == "tts_generation":
                result = await self._run_tts_generation_chain_test(payload)
            elif test_type == "proactive_message":
                result = await self._run_proactive_message_chain_test(payload)
            elif test_type == "skill_similarity":
                result = await self._run_skill_similarity_check(payload)
            else:
                return self._error("未知排障测试类型")
        except Exception as exc:
            logger.warning("[PrivateCompanionPage] 排障链路测试失败: %s", self._single_line(exc, 160), exc_info=True)
            result = {
                "type": test_type,
                "ok": False,
                "title": self._troubleshooting_test_title(test_type),
                "error": str(exc),
            }
        result["type"] = test_type
        result["elapsed_ms"] = self._int(result.get("elapsed_ms")) or int((time.time() - start) * 1000)
        result["ran_at"] = time.time()
        result["ran_at_text"] = self.plugin._format_timestamp_elapsed(result["ran_at"])
        await self._remember_troubleshooting_test_result(test_type, result)
        return self._ok(result)

    async def _run_image_generation_chain_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        generator = getattr(self.plugin, "_generate_photo_image", None)
        if not callable(generator):
            return {
                "ok": False,
                "title": "图片生成链路测试",
                "error": "插件缺少图片生成入口 _generate_photo_image",
            }
        prompt_text = self._single_line(payload.get("prompt"), 600) or (
            "排障测试图，一枚小小的绿色对勾贴纸放在白色桌面上，旁边有柔和台灯光，"
            "画面干净清晰，真实摄影风格，不包含人物、不包含文字水印"
        )
        workflow_kind = self._single_line(payload.get("workflow_kind"), 20) or "text2img"
        started = time.time()
        timeout = max(45, self._int(getattr(self.plugin, "comfyui_photo_wait_seconds", 90)) + 30)
        backend_name, image_path, note = await asyncio.wait_for(
            generator(
                workflow_kind=workflow_kind,
                prompt_text=prompt_text,
                session_key="private_companion_troubleshooting",
            ),
            timeout=timeout,
        )
        elapsed_ms = int((time.time() - started) * 1000)
        exists = False
        file_size = 0
        if image_path:
            try:
                image_file = Path(str(image_path))
                exists = image_file.exists()
                file_size = image_file.stat().st_size if exists else 0
            except Exception:
                exists = False
        return {
            "ok": bool(image_path and exists),
            "title": "图片生成链路测试",
            "backend": self._single_line(backend_name, 80),
            "path": self._single_line(image_path, 260),
            "file_size": file_size,
            "detail": self._single_line(note, 220) or ("已生成图片" if image_path else "未返回图片路径"),
            "prompt": self._single_line(prompt_text, 220),
            "elapsed_ms": elapsed_ms,
            "error": "" if image_path and exists else (self._single_line(note, 220) or "图片生成未返回有效文件"),
        }

    async def _run_tts_generation_chain_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        context = getattr(self.plugin, "context", None)
        if context is None:
            return {
                "ok": False,
                "title": "TTS 生成链路测试",
                "error": "AstrBot context 不可用",
            }
        async with self.plugin._data_lock:
            users = deepcopy(self.plugin.data.get("users") if isinstance(self.plugin.data.get("users"), dict) else {})
        umo = self._single_line(payload.get("umo"), 180) or self._preferred_tts_test_umo(users)
        config: dict[str, Any] = {}
        getter = getattr(context, "get_config", None)
        if callable(getter):
            try:
                config = getter(umo) if umo else getter()
                if not isinstance(config, dict):
                    config = {}
            except Exception:
                config = {}
        provider_getter = getattr(context, "get_using_tts_provider", None)
        tts_provider = None
        if callable(provider_getter):
            try:
                tts_provider = provider_getter(umo) if umo else provider_getter()
            except Exception:
                tts_provider = None
        if tts_provider is None:
            return {
                "ok": False,
                "title": "TTS 生成链路测试",
                "umo": umo,
                "error": "当前会话没有可用 TTS provider",
            }
        provider_settings = dict((config or {}).get("provider_tts_settings", {}) or {})
        spoken = self._single_line(payload.get("text"), 240) or "这是一条排障测试语音，用来确认 TTS 生成链路可以跑通。"
        record_builder = getattr(self.plugin, "_tts_record_component", None)
        started = time.time()
        if callable(record_builder):
            component = await record_builder(
                spoken,
                tts_provider,
                provider_settings,
                config,
                source_text=spoken,
            )
            refs_getter = getattr(self.plugin, "_tts_record_refs", None)
            refs = refs_getter(component) if callable(refs_getter) and component is not None else []
        else:
            audio_path = await tts_provider.get_audio(spoken)
            component = None
            refs = [str(audio_path)] if audio_path else []
        elapsed_ms = int((time.time() - started) * 1000)
        audio_ref = self._single_line(refs[0] if refs else "", 260)
        exists = False
        file_size = 0
        if audio_ref and not re.match(r"^https?://", audio_ref, flags=re.IGNORECASE):
            try:
                audio_file = Path(audio_ref)
                exists = audio_file.exists()
                file_size = audio_file.stat().st_size if exists else 0
            except Exception:
                exists = False
        else:
            exists = bool(audio_ref)
        provider_id = self._provider_id(tts_provider)
        provider_label = self._provider_name(tts_provider, provider_id) if provider_id else getattr(tts_provider, "__class__", type(tts_provider)).__name__
        return {
            "ok": bool(audio_ref and exists),
            "title": "TTS 生成链路测试",
            "umo": umo,
            "provider": self._single_line(provider_label, 100),
            "path": audio_ref,
            "file_size": file_size,
            "detail": "已生成语音组件" if component is not None else "已调用 TTS provider 生成音频",
            "text": spoken,
            "elapsed_ms": elapsed_ms,
            "error": "" if audio_ref and exists else "TTS provider 未返回有效音频文件",
        }

    async def _run_proactive_message_chain_test(self, payload: dict[str, Any]) -> dict[str, Any]:
        steps: list[dict[str, str]] = []

        def add_step(name: str, status: str, detail: str = "") -> None:
            steps.append(
                {
                    "name": self._single_line(name, 40),
                    "status": self._single_line(status, 16) or "info",
                    "detail": self._single_line(detail, 180),
                }
            )

        context = getattr(self.plugin, "context", None)
        if context is None:
            add_step("上下文", "error", "AstrBot context 不可用")
            return {
                "ok": False,
                "title": "主动消息链路测试",
                "steps": steps,
                "error": "AstrBot context 不可用",
            }

        target_user_id = self._single_line(payload.get("user_id"), 80)
        async with self.plugin._data_lock:
            users = deepcopy(self.plugin.data.get("users") if isinstance(self.plugin.data.get("users"), dict) else {})
        target_user_id, target_user = self._preferred_proactive_test_user(users, target_user_id)
        if not target_user_id or not target_user:
            add_step("目标会话", "error", "没有找到已启用且带私聊会话的私聊对象")
            return {
                "ok": False,
                "title": "主动消息链路测试",
                "steps": steps,
                "error": "没有找到可用于测试的私聊对象",
            }
        umo = self._single_line(target_user.get("umo"), 180)
        if not umo:
            add_step("目标会话", "error", "目标用户缺少 umo")
            return {
                "ok": False,
                "title": "主动消息链路测试",
                "user_id": target_user_id,
                "steps": steps,
                "error": "目标用户缺少私聊会话",
            }
        add_step("目标会话", "ok", f"用户 {target_user.get('nickname') or target_user_id} / {umo}")

        now = time.time()
        scheduled_ts = now + 60
        test_id = secrets.token_hex(6)
        plan_keys = (
            "next_proactive_at",
            "planned_proactive_reason",
            "planned_proactive_action",
            "planned_proactive_source",
            "planned_proactive_motive",
            "planned_proactive_topic",
            "planned_event_chain",
            "planned_opener_mode",
            "planned_followup_kind",
            "planned_proactive_quota_exempt",
            "planned_candidate_id",
            "planned_proactive_trigger_message_id",
            "planned_proactive_trigger_umo",
            "planned_proactive_trigger_created_at",
            "llm_timer_event",
            "sent_today",
            "proactive_sent_count",
            "ignored_streak",
            "awaiting_reply_since",
            "last_sent",
            "last_companion_message",
            "last_proactive_reason",
            "last_proactive_action",
            "last_proactive_behavior_summary",
            "last_proactive_motive",
            "recent_proactive_topics",
            "proactive_daypart_counts",
            "pending_followup_event",
            "suspended_proactive",
            "poke_daily_limit",
            "photo_daily_limit",
            "screen_peek_daily_limit",
        )

        async with self.plugin._data_lock:
            current = self.plugin._get_user(target_user_id)
            if not isinstance(current, dict) or not current.get("enabled", True):
                add_step("临时任务", "error", "目标私聊对象未启用")
                return {
                    "ok": False,
                    "title": "主动消息链路测试",
                    "user_id": target_user_id,
                    "umo": umo,
                    "steps": steps,
                    "error": "目标私聊对象未启用",
                }
            if current.get("proactive_sending"):
                add_step("临时任务", "error", "该用户已有主动发送正在进行")
                return {
                    "ok": False,
                    "title": "主动消息链路测试",
                    "user_id": target_user_id,
                    "umo": umo,
                    "steps": steps,
                    "error": "该用户已有主动发送正在进行",
                }
            if (
                str(current.get("planned_proactive_source") or "") == "troubleshooting"
                and isinstance(current.get("troubleshooting_proactive_restore"), dict)
            ):
                existing_steps = current.get("troubleshooting_proactive_steps") if isinstance(current.get("troubleshooting_proactive_steps"), list) else []
                return {
                    "ok": True,
                    "pending": True,
                    "title": "主动消息链路测试",
                    "user_id": target_user_id,
                    "umo": umo,
                    "steps": existing_steps,
                    "detail": "已有一个排障临时主动任务在等待执行，请约 1 分钟后刷新查看结果",
                    "action": "message",
                    "reason": self._single_line(current.get("planned_proactive_reason"), 40) or "check_in",
                    "error": "",
                }
            restore = {key: deepcopy(current.get(key)) for key in plan_keys}
            current["troubleshooting_proactive_restore"] = restore
            current["troubleshooting_proactive_test_id"] = test_id
            current["troubleshooting_proactive_started_at"] = now
            current["troubleshooting_proactive_steps"] = [
                {"name": "目标会话", "status": "ok", "detail": f"用户 {current.get('nickname') or target_user_id} / {umo}"},
                {"name": "临时任务", "status": "ok", "detail": "已预约 60 秒后由主动循环执行"},
            ]
            current["user_id"] = str(current.get("user_id") or target_user_id)
            current["umo"] = umo
            current["next_proactive_at"] = scheduled_ts
            current["planned_proactive_reason"] = "check_in"
            current["planned_proactive_action"] = "message"
            current["planned_proactive_source"] = "troubleshooting"
            current["planned_proactive_motive"] = "对方希望你主动来找一下,轻轻开口确认主动消息链路能正常工作。"
            current["planned_proactive_topic"] = "主动来找对方一下"
            current["planned_event_chain"] = []
            current["planned_opener_mode"] = ""
            current["planned_followup_kind"] = ""
            current["planned_proactive_quota_exempt"] = True
            current["planned_candidate_id"] = f"troubleshooting_{test_id}"
            current["llm_timer_event"] = {}
            current["poke_daily_limit"] = 0
            current["photo_daily_limit"] = 0
            current["screen_peek_daily_limit"] = 0
            result = {
                "ok": True,
                "pending": True,
                "title": "主动消息链路测试",
                "user_id": target_user_id,
                "umo": umo,
                "steps": list(current["troubleshooting_proactive_steps"]),
                "detail": "已预约 1 分钟后的排障临时主动任务；到点后由主动循环走完整生成、复核、发送和归档流程",
                "action": "message",
                "reason": "check_in",
                "error": "",
            }
            raw = self.plugin.data.setdefault("troubleshooting_test_results", {})
            if not isinstance(raw, dict):
                raw = {}
                self.plugin.data["troubleshooting_test_results"] = raw
            raw["proactive_message"] = self._sanitize_troubleshooting_test_result(result)
            self.plugin._save_data_sync()
        add_step("临时任务", "ok", "已预约 60 秒后由主动循环执行")
        return result

    def _preferred_tts_test_umo(self, users: dict[str, Any]) -> str:
        fallback = ""
        for user_id, item in users.items():
            if not isinstance(item, dict) or not item.get("enabled", True) or not item.get("umo"):
                continue
            umo = self._single_line(item.get("umo"), 180)
            if not fallback:
                fallback = umo
            if self.plugin._private_user_role(item, str(item.get("user_id") or user_id)) == "owner":
                return umo
        return fallback

    def _preferred_proactive_test_user(
        self,
        users: dict[str, Any],
        preferred_user_id: str = "",
    ) -> tuple[str, dict[str, Any] | None]:
        if preferred_user_id:
            item = users.get(preferred_user_id)
            if isinstance(item, dict) and item.get("enabled", True) and item.get("umo"):
                item = deepcopy(item)
                item["user_id"] = str(item.get("user_id") or preferred_user_id)
                return preferred_user_id, item
        fallback: tuple[str, dict[str, Any] | None] = ("", None)
        for user_id, item in users.items():
            if not isinstance(item, dict) or not item.get("enabled", True) or not item.get("umo"):
                continue
            candidate = deepcopy(item)
            candidate["user_id"] = str(candidate.get("user_id") or user_id)
            if not fallback[0]:
                fallback = (str(user_id), candidate)
            if self.plugin._private_user_role(candidate, str(candidate.get("user_id") or user_id)) == "owner":
                return str(user_id), candidate
        return fallback

    async def _run_skill_similarity_check(self, payload: dict[str, Any]) -> dict[str, Any]:
        started = time.time()
        use_model = self._normalize_bool_value(payload.get("use_model", True))
        async with self.plugin._data_lock:
            data = deepcopy(self.plugin.data)
        local_items = self._skill_similarity_local_candidates(data)
        steps: list[dict[str, str]] = [
            {
                "name": "本地规则",
                "status": "ok" if local_items else "info",
                "detail": f"发现 {len(local_items)} 组疑似相似/冲突项" if local_items else "未发现明显重复、别名冲突或高重叠项",
            }
        ]
        model_items: list[str] = []
        provider_id = ""
        if use_model and local_items:
            caller = getattr(self.plugin, "_llm_call", None)
            if callable(caller):
                provider_selector = getattr(self.plugin, "_task_provider", None)
                if callable(provider_selector):
                    provider_id = provider_selector(
                        getattr(self.plugin, "troubleshooting_provider_id", ""),
                        getattr(self.plugin, "response_review_provider_id", ""),
                        getattr(self.plugin, "mai_style_provider_id", ""),
                        getattr(self.plugin, "llm_provider_id", ""),
                    )
                else:
                    provider_id = str(
                        getattr(self.plugin, "troubleshooting_provider_id", "")
                        or getattr(self.plugin, "response_review_provider_id", "")
                        or getattr(self.plugin, "mai_style_provider_id", "")
                        or getattr(self.plugin, "llm_provider_id", "")
                        or ""
                    )
                prompt = self._skill_similarity_review_prompt(data, local_items)
                try:
                    raw = await caller(
                        prompt,
                        max_tokens=500,
                        provider_id=provider_id,
                        task="troubleshooting_skill_similarity",
                    )
                    model_items = self._parse_skill_similarity_model_result(raw)
                    steps.append(
                        {
                            "name": "模型复核",
                            "status": "ok" if model_items else "info",
                            "detail": f"模型给出 {len(model_items)} 条建议" if model_items else "模型未给出额外合并建议",
                        }
                    )
                except Exception as exc:
                    steps.append({"name": "模型复核", "status": "warn", "detail": f"调用失败: {self._single_line(exc, 120)}"})
            else:
                steps.append({"name": "模型复核", "status": "warn", "detail": "插件缺少 _llm_call，无法调用模型"})
        elif not use_model:
            steps.append({"name": "模型复核", "status": "info", "detail": "本次按请求仅执行本地规则检查"})
        elif not local_items:
            steps.append({"name": "模型复核", "status": "info", "detail": "没有本地候选，未调用模型"})

        local_preview = [
            f"{item.get('a')} ↔ {item.get('b')}：{item.get('reason')}"
            for item in local_items[:8]
        ]
        all_suggestions = [*local_preview, *model_items]
        detail = (
            f"本地发现 {len(local_items)} 组候选，模型给出 {len(model_items)} 条建议"
            if all_suggestions
            else "技能项目前看起来没有明显相似/冲突问题"
        )
        return {
            "ok": True,
            "title": "技能相似项检查",
            "provider": self._single_line(provider_id, 100),
            "detail": self._single_line(detail, 220),
            "text_preview": self._single_line(" | ".join(all_suggestions[:5]), 220),
            "suggestions": [self._single_line(item, 220) for item in all_suggestions[:10]],
            "local_count": len(local_items),
            "model_count": len(model_items),
            "suggestion_count": len(all_suggestions),
            "extra_count": max(0, len(all_suggestions) - 5),
            "steps": steps,
            "elapsed_ms": int((time.time() - started) * 1000),
            "error": "",
        }

    def _skill_similarity_local_candidates(self, data: dict[str, Any]) -> list[dict[str, str]]:
        state = data.get("skill_growth") if isinstance(data.get("skill_growth"), dict) else {}
        skills = state.get("skills") if isinstance(state.get("skills"), dict) else {}
        generic_terms = {
            "学习",
            "上课",
            "下课",
            "作业",
            "复习",
            "预习",
            "考试",
            "测验",
            "练习",
            "刷题",
            "做题",
            "题目",
            "课堂",
            "课程",
            "笔记",
            "讲题",
            "错题",
            "背诵",
            "背书",
            "阅读",
            "听课",
            "训练",
        }
        items: list[dict[str, Any]] = []
        for raw in skills.values():
            if not isinstance(raw, dict):
                continue
            name = self._single_line(raw.get("name"), 32)
            if not name:
                continue
            keywords = raw.get("keywords") if isinstance(raw.get("keywords"), list) else []
            aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
            keyword_terms: set[str] = set()
            for raw_term in keywords:
                term = self._single_line(raw_term, 24)
                if term and term not in generic_terms:
                    keyword_terms.add(term)
            identity_terms: set[str] = set()
            for raw_term in [name, *aliases]:
                term = self._single_line(raw_term, 24)
                if term:
                    identity_terms.add(term)
            items.append(
                {
                    "name": name,
                    "category": self._single_line(raw.get("category"), 24),
                    "hidden": bool(raw.get("hidden")),
                    "frozen": bool(raw.get("frozen")),
                    "keyword_terms": keyword_terms,
                    "identity_terms": identity_terms,
                }
            )
        candidates: list[dict[str, str]] = []
        seen: set[tuple[str, str, str]] = set()
        for idx, left in enumerate(items):
            for right in items[idx + 1:]:
                reason = ""
                if left["name"] == right["name"]:
                    reason = "名称完全重复"
                elif left["name"] in right["identity_terms"] or right["name"] in left["identity_terms"]:
                    reason = "名称与对方合并别名冲突"
                elif len(left["name"]) >= 2 and len(right["name"]) >= 2 and (left["name"] in right["name"] or right["name"] in left["name"]):
                    reason = "名称相互包含"
                else:
                    overlap = left["keyword_terms"] & right["keyword_terms"]
                    if left["category"] and left["category"] == right["category"] and len(overlap) >= 3:
                        reason = f"同分类专有关键词重叠: {'、'.join(sorted(overlap)[:4])}"
                if not reason:
                    continue
                key = tuple(sorted([left["name"], right["name"]]) + [reason])
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({"a": left["name"], "b": right["name"], "reason": reason})
        return candidates[:12]

    def _skill_similarity_review_prompt(self, data: dict[str, Any], candidates: list[dict[str, str]]) -> str:
        summary = self._skill_growth_summary(data)
        skills = summary.get("items") if isinstance(summary.get("items"), list) else []
        skill_lines = []
        for item in skills[:80]:
            aliases = "、".join(item.get("aliases") or [])
            keywords = "、".join((item.get("keywords") or [])[:8])
            flags = " ".join(flag for flag in ("隐藏" if item.get("hidden") else "", "冻结" if item.get("frozen") else "") if flag)
            skill_lines.append(
                f"- {item.get('name')}｜{item.get('category')}｜{item.get('level_title')}｜别名:{aliases or '-'}｜关键词:{keywords or '-'}｜{flags or '正常'}"
            )
        candidate_lines = [f"- {item.get('a')} / {item.get('b')}：{item.get('reason')}" for item in candidates[:12]]
        return (
            "你是插件排障助手。请检查技能成长列表中是否存在疑似重复技能、别名冲突、过泛关键词或应该隐藏/冻结的项。\n"
            "只根据给出的列表判断，不要发散。不要修改数据，只给建议。\n"
            "不要把“上课、作业、复习、考试、练习、笔记、题目”等通用学习流程词当作技能相似证据。\n"
            "只有名称/别名明显指向同一能力，或多个专有关键词高度重叠时，才建议合并。\n"
            "请输出 1-6 条短建议，每条不超过 45 字；如果没有问题，只输出“未发现需要合并的技能”。\n\n"
            "本地候选：\n" + "\n".join(candidate_lines) + "\n\n"
            "技能列表：\n" + "\n".join(skill_lines)
        )

    def _parse_skill_similarity_model_result(self, raw: Any) -> list[str]:
        text = str(raw or "").strip()
        if not text:
            return []
        lines = []
        for line in re.split(r"[\r\n]+", text):
            item = re.sub(r"^\s*[-*•\d.、)）]+\s*", "", line).strip()
            item = self._single_line(item, 90)
            if item and item not in lines:
                lines.append(item)
        return lines[:6]

    async def _remember_troubleshooting_test_result(self, test_type: str, result: dict[str, Any]) -> None:
        if not test_type:
            return
        try:
            async with self.plugin._data_lock:
                raw = self.plugin.data.setdefault("troubleshooting_test_results", {})
                if not isinstance(raw, dict):
                    raw = {}
                    self.plugin.data["troubleshooting_test_results"] = raw
                raw[test_type] = self._sanitize_troubleshooting_test_result(result)
                self.plugin._save_data_sync()
        except Exception as exc:
            logger.warning("[PrivateCompanionPage] 保存排障测试结果失败: %s", self._single_line(exc, 120))

    def _troubleshooting_test_results(self, data: dict[str, Any]) -> dict[str, Any]:
        raw = data.get("troubleshooting_test_results")
        if not isinstance(raw, dict):
            return {}
        return {
            key: self._sanitize_troubleshooting_test_result(value)
            for key, value in raw.items()
            if isinstance(value, dict)
        }

    def _prompt_injection_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        raw = data.get("recent_prompt_injections")
        if not isinstance(raw, dict):
            raw = {}

        def normalize_item(item: Any) -> dict[str, Any] | None:
            if not isinstance(item, dict):
                return None
            ts = self._float(item.get("ts"))
            metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            raw_modules = item.get("modules") if isinstance(item.get("modules"), list) else []
            if not raw_modules:
                normalizer = getattr(self.plugin, "_normalize_prompt_injection_modules", None)
                if callable(normalizer):
                    try:
                        raw_modules = normalizer(str(item.get("content") or ""), None)
                    except Exception:
                        raw_modules = []
            modules: list[dict[str, Any]] = []
            for index, module in enumerate(raw_modules[:28]):
                if not isinstance(module, dict):
                    continue
                content = str(module.get("content") or "")[:6500]
                if not content.strip():
                    continue
                modules.append(
                    {
                        "key": self._single_line(module.get("key"), 100) or f"module.{index + 1}",
                        "source": self._single_line(module.get("source"), 80),
                        "priority": self._int(module.get("priority")),
                        "title": self._single_line(module.get("title"), 80) or "提示词片段",
                        "description": self._single_line(module.get("description"), 260),
                        "chars": self._int(module.get("chars")),
                        "truncated": bool(module.get("truncated")),
                        "preview": self._single_line(module.get("preview"), 220),
                        "content": content,
                    }
                )
            return {
                "ts": ts,
                "time": self.plugin._format_timestamp_elapsed(ts),
                "kind": self._single_line(item.get("kind"), 20),
                "session": self._single_line(item.get("session"), 160),
                "title": self._single_line(item.get("title"), 80),
                "mode": self._single_line(item.get("mode"), 40),
                "chars": self._int(item.get("chars")),
                "truncated": bool(item.get("truncated")),
                "preview": self._single_line(item.get("preview"), 260),
                "content": str(item.get("content") or "")[:13000],
                "modules": modules,
                "metadata": {
                    self._single_line(key, 40): self._single_line(value, 240)
                    for key, value in metadata.items()
                    if self._single_line(key, 40) and self._single_line(value, 240)
                },
            }

        result: dict[str, Any] = {}
        for kind in ("tts", "proactive", "passive", "request"):
            items = raw.get(kind) if isinstance(raw.get(kind), list) else []
            limit = 8 if kind == "tts" else 5
            normalized = [entry for entry in (normalize_item(item) for item in items[:limit]) if entry]
            result[kind] = normalized
        result["total"] = (
            len(result.get("tts", []))
            + len(result.get("proactive", []))
            + len(result.get("passive", []))
            + len(result.get("request", []))
        )
        return result

    def _sanitize_troubleshooting_test_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": self._single_line(result.get("type"), 40),
            "ok": bool(result.get("ok")),
            "pending": bool(result.get("pending")),
            "title": self._single_line(result.get("title"), 60),
            "backend": self._single_line(result.get("backend"), 80),
            "provider": self._single_line(result.get("provider"), 100),
            "umo": self._single_line(result.get("umo"), 180),
            "path": self._single_line(result.get("path"), 260),
            "file_size": self._int(result.get("file_size")),
            "detail": self._single_line(result.get("detail"), 220),
            "error": self._single_line(result.get("error"), 220),
            "text_preview": self._single_line(result.get("text_preview"), 220),
            "action": self._single_line(result.get("action"), 60),
            "reason": self._single_line(result.get("reason"), 40),
            "extra_count": self._int(result.get("extra_count")),
            "steps": [
                {
                    "name": self._single_line(step.get("name"), 40),
                    "status": self._single_line(step.get("status"), 16),
                    "detail": self._single_line(step.get("detail"), 180),
                }
                for step in (result.get("steps") if isinstance(result.get("steps"), list) else [])[:12]
                if isinstance(step, dict)
            ],
            "elapsed_ms": self._int(result.get("elapsed_ms")),
            "ran_at": self._float(result.get("ran_at")),
            "ran_at_text": self._single_line(result.get("ran_at_text"), 40),
        }

    @staticmethod
    def _troubleshooting_test_title(test_type: str) -> str:
        return {
            "image_generation": "图片生成链路测试",
            "tts_generation": "TTS 生成链路测试",
            "proactive_message": "主动消息链路测试",
            "skill_similarity": "技能相似项检查",
        }.get(test_type, "排障链路测试")

    def _troubleshooting_recent_events(
        self,
        *,
        diagnostics: list[dict[str, Any]],
        proactive_tasks: dict[str, Any],
        proactive_candidates: dict[str, Any],
        token_stats: dict[str, Any],
    ) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []

        def add(level: str, source: str, title: str, detail: str = "", *, ts: float = 0, action: str = "", jump: str = "") -> None:
            events.append(
                {
                    "level": level,
                    "source": source,
                    "title": self._single_line(title, 90),
                    "detail": self._single_line(detail, 220),
                    "action": self._single_line(action, 160),
                    "jump": self._single_line(jump, 40),
                    "ts": self._float(ts),
                    "time": self.plugin._format_timestamp_elapsed(ts) if ts else "",
                }
            )

        for item in diagnostics:
            level = self._single_line(item.get("level"), 12)
            if level not in {"error", "warn"}:
                continue
            add(level, "配置诊断", item.get("title", ""), item.get("text", ""), action=item.get("action", ""), jump="troubleshooting")

        for item in proactive_tasks.get("audit_items", [])[:40]:
            status = self._single_line(item.get("status"), 24)
            if status not in {"failed", "dropped", "deferred"}:
                continue
            note = self._single_line(item.get("note"), 180)
            if status in {"dropped", "deferred"} and not self._proactive_audit_note_needs_troubleshooting(note):
                continue
            level = "error" if status == "failed" else "warn"
            title = item.get("topic") or item.get("reason") or item.get("note") or "主动执行异常"
            detail = "；".join(
                part
                for part in [
                    f"用户 {item.get('user_label') or item.get('user_id') or '-'}",
                    f"动作 {item.get('action') or 'message'}",
                    note,
                    item.get("text_preview") or "",
                ]
                if part
            )
            add(level, "主动审计", title, detail, ts=self._float(item.get("updated_ts") or item.get("created_ts")), jump="proactive")

        for item in proactive_candidates.get("items", [])[:40]:
            if self._single_line(item.get("status"), 24) != "blocked":
                continue
            note = self._single_line(item.get("note"), 180)
            if self._proactive_candidate_block_is_normal(note):
                continue
            title = item.get("topic") or item.get("reason") or "主动候选被拦截"
            detail = "；".join(
                part
                for part in [
                    f"用户 {item.get('user_label') or item.get('user_id') or '-'}",
                    f"动作 {item.get('action') or 'message'}",
                    note,
                ]
                if part
            )
            add("warn", "主动候选", title, detail, ts=self._float(item.get("last_seen_ts") or item.get("created_ts")), jump="proactive")

        for item in self._active_token_failures(token_stats.get("recent", []), limit=50):
            title = f"{self._single_line(item.get('task'), 40) or 'LLM 调用'} 失败"
            detail = "；".join(
                part
                for part in [
                    f"Provider {item.get('provider') or '-'}",
                    item.get("error") or "无错误详情",
                ]
                if part
            )
            add("error", "模型调用", title, detail, ts=self._float(item.get("ts")), jump="tokens")

        events.sort(key=lambda item: self._float(item.get("ts")), reverse=True)
        return events

    def _active_token_failures(
        self,
        recent: Any,
        *,
        max_age_seconds: float = 30 * 60,
        limit: int = 80,
    ) -> list[dict[str, Any]]:
        if not isinstance(recent, list):
            return []
        now = time.time()
        recovered: set[tuple[str, str]] = set()
        failures: list[dict[str, Any]] = []
        for item in recent[:limit]:
            if not isinstance(item, dict):
                continue
            task = self._single_line(item.get("task"), 40) or "LLM 调用"
            provider = self._single_line(item.get("provider"), 80) or "-"
            key = (task, provider)
            if bool(item.get("success", True)):
                recovered.add(key)
                continue
            ts = self._float(item.get("ts"))
            if ts > 0 and now - ts > max_age_seconds:
                continue
            if key in recovered:
                continue
            failures.append(item)
        return failures

    def _proactive_candidate_block_is_normal(self, note: str) -> bool:
        text = self._single_line(note, 180)
        if not text:
            return True
        exact_normal = {
            "已有更早主动候选",
            "近期主题过于相似",
            "已有用户预约/定时主动",
            "用户明确休息中",
            "当前时段主动已足够,已避开扎堆",
            "朋友主动已按日内节奏延后",
            "已有更早主动候选",
        }
        if text in exact_normal:
            return True
        normal_tokens = (
            "已有更早",
            "近期主题",
            "过于相似",
            "用户明确休息",
            "休息中",
            "免打扰",
            "已避开扎堆",
            "按日内节奏延后",
            "额度",
            "冷却",
            "间隔",
            "频率",
            "调度过滤",
        )
        return any(token in text for token in normal_tokens)

    def _proactive_audit_note_needs_troubleshooting(self, note: str) -> bool:
        text = self._single_line(note, 180)
        if not text:
            return False
        normal_tokens = (
            "主动行为失败或不适合发送",
            "不适合发送",
            "用户明确休息",
            "休息中",
            "免打扰",
            "已有更早",
            "调度过滤",
            "已避开扎堆",
            "按日内节奏延后",
            "冷却",
            "间隔",
            "频率",
            "额度",
            "低分",
            "未达到阈值",
        )
        if any(token in text for token in normal_tokens):
            return False
        error_tokens = (
            "异常",
            "报错",
            "Traceback",
            "Error",
            "Exception",
            "provider",
            "模型",
            "超时",
            "不可用",
            "发送失败",
            "生成失败",
            "调用失败",
            "保存失败",
            "处理失败",
            "database is locked",
        )
        return any(token in text for token in error_tokens)

    def _troubleshooting_checks(
        self,
        *,
        data: dict[str, Any],
        users: dict[str, Any],
        diagnostics: list[dict[str, Any]],
        proactive_tasks: dict[str, Any],
        proactive_candidates: dict[str, Any],
        token_stats: dict[str, Any],
        cache: dict[str, Any],
        tts: dict[str, Any],
        sqlite_status: dict[str, Any],
    ) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []

        def add(level: str, title: str, text: str, action: str = "", jump: str = "") -> None:
            checks.append(
                {
                    "level": level,
                    "title": self._single_line(title, 90),
                    "text": self._single_line(text, 240),
                    "action": self._single_line(action, 180),
                    "jump": self._single_line(jump, 40),
                }
            )

        enabled_users = [item for item in users.values() if isinstance(item, dict) and item.get("enabled", True)]
        runtime = proactive_tasks.get("runtime", {})
        daily_limit = self._int(getattr(self.plugin, "max_daily_messages", 0))
        budget = token_stats.get("budget", {})
        if not enabled_users:
            add("warn", "主动消息没有私聊对象", "当前没有启用的私聊对象，主动消息不会有目标。", "到私聊页新增或启用对象", "private")
        elif daily_limit <= 0:
            add("warn", "私聊主动总额度为 0", "每日主动上限为 0 时，主动消息不会发送。", "到模块配置调高每日主动上限", "modules")
        elif not runtime.get("healthy"):
            add("warn", "主动循环心跳不新鲜", runtime.get("last_tick_error") or "最近没有检测到主动循环心跳。", "查看主动页的循环状态", "proactive")
        else:
            add("ok", "主动循环可运行", f"启用对象 {len(enabled_users)} 个，最近心跳 {runtime.get('last_tick_started') or '-'}。", "", "proactive")

        if budget.get("exceeded"):
            add("error", "今日 Token 硬限额已耗尽", f"今日已用 {budget.get('used')}，硬限额 {budget.get('limit')}。", "调高每日 Token 限额或等待明日重置", "tokens")
        elif budget.get("soft_active"):
            add("warn", "Token 软限额正在暂缓后台任务", f"今日已用 {budget.get('used')}，软限额 {budget.get('soft_limit')}；主动生图、新闻、创作等低优先级任务会延后。", "到 Token 页或模块配置检查限额", "tokens")
        else:
            add("ok", "Token 预算未阻塞", f"今日已用 {budget.get('used', 0)}；软限额剩余 {budget.get('soft_remaining') if budget.get('soft_remaining') is not None else '不限'}。", "", "tokens")

        photo_enabled = bool(getattr(self.plugin, "enable_photo_text_action", False))
        photo_available = bool(getattr(self.plugin, "_photo_text_available", lambda *args, **kwargs: False)())
        photo_blocked = [
            item for item in proactive_candidates.get("items", [])
            if "photo_text" in str(item.get("action") or "") and str(item.get("status") or "") == "blocked"
        ]
        if not photo_enabled:
            add("warn", "主动带图功能未开启", "enable_photo_text_action 关闭时不会生成主动图片。", "到功能开关打开主动拍照/生图", "config")
        elif not photo_available:
            add("warn", "主动带图后端或额度不可用", "生图后端不可用、每日生图额度用完，或当前对象不允许 photo_text。", "检查生图后端、每日生图上限和用户关系角色", "modules")
        elif photo_blocked:
            add("warn", "近期带图候选被拦截", self._single_line(photo_blocked[0].get("note"), 160) or "最近 photo_text 候选没有进入发送。", "到主动页筛选 photo_text", "proactive")
        else:
            add("ok", "主动带图链路可尝试", "开关和可用性检查通过；是否出现取决于主动动机、天气/日程和候选权重。", "", "proactive")

        if bool(tts.get("enhancement_enabled")):
            if bool(tts.get("provider_available")):
                add("ok", "TTS provider 可用", f"模式 {tts.get('mode')}，语种 {tts.get('language')}，provider {tts.get('provider_label') or '-'}。", "", "modules")
            else:
                add("warn", "TTS 强化开启但合成 provider 不可用", "插件能处理 TTS 标签，但真实语音合成需要 AstrBot 当前会话启用 TTS provider。", "到 AstrBot 会话 TTS 配置启用 provider", "modules")
        else:
            add("info", "TTS 强化未开启", "模型不应被要求生成 TTS 标签；如仍出现标签，发送前会清理。", "", "modules")

        sqlite_bad = [item for item in sqlite_status.get("items", []) if item.get("level") in {"warn", "error"}]
        if sqlite_bad:
            add("warn", "SQLite 并发状态需要关注", sqlite_bad[0].get("text") or "有数据库未处于 WAL 或检查失败。", "重启插件后查看是否仍有 database is locked", "troubleshooting")
        else:
            add("ok", "SQLite WAL 检查通过", f"已检查 {len(sqlite_status.get('items', []))} 个数据库文件。", "", "troubleshooting")

        token_errors = self._active_token_failures(token_stats.get("recent", []))
        if token_errors:
            first = token_errors[0]
            add("error", "最近存在模型调用失败", first.get("error") or f"{first.get('task') or '任务'} 调用失败。", "到 Token 页查看失败任务和 provider", "tokens")
        else:
            add("ok", "近期模型调用无待处理失败", "近 30 分钟内没有未恢复的模型调用失败；历史失败可在 Token 页查看。", "", "tokens")

        image_cache = cache.get("private_image_vision", {})
        if image_cache.get("enabled"):
            add("ok", "图片视觉缓存已开启", f"当前缓存 {image_cache.get('items', 0)}/{image_cache.get('max_items') or '不限'} 条。", "", "image-cache")
        else:
            add("info", "图片视觉缓存未开启", "重复表情包会重复调用视觉模型，但不影响首次识图。", "到模块配置开启重复图片缓存", "modules")

        diag_warns = [item for item in diagnostics if item.get("level") in {"warn", "error"}]
        if diag_warns:
            add("warn", "配置诊断仍有待处理项", f"{len(diag_warns)} 项需要关注：{diag_warns[0].get('title') or '-'}。", diag_warns[0].get("action") or "查看下方最近异常", "troubleshooting")
        else:
            add("ok", "配置诊断无警告", "现有诊断项没有 warn/error。", "", "dashboard")
        return checks

    async def _sqlite_wal_status_summary(self) -> dict[str, Any]:
        items: list[dict[str, Any]] = []
        paths_getter = getattr(self.plugin, "_sqlite_wal_candidate_paths", None)
        paths = paths_getter() if callable(paths_getter) else []

        def inspect(path: Path) -> dict[str, Any]:
            try:
                conn = sqlite3.connect(str(path), timeout=2.0)
                try:
                    mode_row = conn.execute("PRAGMA journal_mode").fetchone()
                    timeout_row = conn.execute("PRAGMA busy_timeout").fetchone()
                    mode = str(mode_row[0] if mode_row else "").lower()
                    timeout_ms = self._int(timeout_row[0] if timeout_row else 0)
                finally:
                    conn.close()
                level = "ok" if mode == "wal" and timeout_ms >= 1000 else "warn"
                text = f"journal_mode={mode or '-'}，busy_timeout={timeout_ms}ms"
                return {"path": str(path), "name": path.name, "level": level, "text": text, "journal_mode": mode, "busy_timeout_ms": timeout_ms}
            except Exception as exc:
                return {"path": str(path), "name": path.name, "level": "error", "text": self._single_line(exc, 180)}

        for path in paths[:12]:
            items.append(await self._to_thread_sqlite_inspect(inspect, path))
        return {
            "items": items,
            "ok": sum(1 for item in items if item.get("level") == "ok"),
            "warn": sum(1 for item in items if item.get("level") == "warn"),
            "error": sum(1 for item in items if item.get("level") == "error"),
        }

    async def _to_thread_sqlite_inspect(self, func: Any, path: Path) -> dict[str, Any]:
        try:
            import asyncio

            return await asyncio.to_thread(func, path)
        except Exception:
            return func(path)

    async def get_token_stats(self) -> dict[str, Any]:
        try:
            async with self.plugin._data_lock:
                usage = deepcopy(self.plugin.data.get("token_usage", {}))
            return self._ok(self._token_stats_payload(usage))
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取 Token 统计失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def reset_token_stats(self) -> dict[str, Any]:
        try:
            async with self.plugin._data_lock:
                self.plugin.data["token_usage"] = {}
                self.plugin._save_data_sync()
            return self._ok(self._token_stats_payload({}))
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 重置 Token 统计失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def unlock_bookshelf(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        password = str(payload.get("password", "")).strip()
        try:
            expected = await self.plugin._ensure_bookshelf_password_async()
            async with self.plugin._data_lock:
                if not self._bookshelf_password_matches(password, expected):
                    return self._error("密码不对。需要在聊天里自然向 Bot 询问。")
                access_token = self._issue_bookshelf_access_token()
                data = deepcopy(self.plugin.data)
            return self._ok({"bookshelf": await self._bookshelf_summary(data, unlocked=True, access_token=access_token)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 解锁书柜夹层失败: {exc}", exc_info=True)
            return self._error(str(exc))

    @staticmethod
    def _normalize_bookshelf_password(value: Any) -> str:
        text = _strip_internal_message_blocks(value)
        text = re.sub(r"\s+", "", text)
        text = text.strip("「」『』“”\"'` 。，,.;；:：!！?？、~～（）()[]【】")
        return text.lower()

    def _bookshelf_password_matches(self, provided: Any, expected: Any) -> bool:
        normalized_expected = self._normalize_bookshelf_password(expected)
        normalized_provided = self._normalize_bookshelf_password(provided)
        if not normalized_expected or not normalized_provided:
            return False
        if normalized_provided == normalized_expected:
            return True
        return len(normalized_expected) >= 2 and normalized_expected in normalized_provided

    def _bookshelf_access_tokens(self) -> dict[str, float]:
        store = getattr(self.plugin, "_bookshelf_access_tokens", None)
        if not isinstance(store, dict):
            store = {}
            setattr(self.plugin, "_bookshelf_access_tokens", store)
        now = time.time()
        for token, expires_at in list(store.items()):
            if self._float(expires_at) <= now:
                store.pop(token, None)
        return store

    def _issue_bookshelf_access_token(self) -> str:
        token = secrets.token_urlsafe(24)
        self._bookshelf_access_tokens()[token] = time.time() + 2 * 3600
        return token

    def _bookshelf_access_token_valid(self, token: Any) -> bool:
        token_text = self._single_line(token, 120)
        if not token_text:
            return False
        expires_at = self._bookshelf_access_tokens().get(token_text)
        return bool(expires_at and self._float(expires_at) > time.time())

    def _bookshelf_request_token(self, payload: dict[str, Any] | None = None) -> str:
        if isinstance(payload, dict):
            token = self._single_line(payload.get("access_token") or payload.get("token"), 120)
            if token:
                return token
        return self._single_line(request.args.get("access_token") or request.args.get("token"), 120)

    def _bookshelf_access_error(self) -> dict[str, str]:
        return {"error": "夹层访问已过期，请重新输入密码打开抽屉"}

    async def get_bookshelf_image(self):
        if not self._bookshelf_access_token_valid(self._bookshelf_request_token()):
            return self._error(self._bookshelf_access_error()["error"])
        resolved = await self._resolve_bookshelf_image_path_from_request()
        if isinstance(resolved, dict):
            return self._error(str(resolved.get("error") or "图片不存在"))
        path = resolved
        try:
            response = await send_file(path)
            response.headers["Cache-Control"] = "no-store, max-age=0"
            return response
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 读取书柜图片失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def get_bookshelf_image_data(self) -> dict[str, Any]:
        if not self._bookshelf_access_token_valid(self._bookshelf_request_token()):
            return self._error(self._bookshelf_access_error()["error"])
        resolved = await self._resolve_bookshelf_image_path_from_request()
        if isinstance(resolved, dict):
            return self._error(str(resolved.get("error") or "图片不存在"))
        path = resolved
        try:
            mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
            data = await self._read_file_base64(path)
            return self._ok(
                {
                    "mime": mime,
                    "data_url": f"data:{mime};base64,{data}",
                    "size": path.stat().st_size,
                    "mtime": int(path.stat().st_mtime),
                }
            )
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 读取书柜图片数据失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def _read_file_base64(self, path: Path) -> str:
        import asyncio

        raw = await asyncio.to_thread(path.read_bytes)
        return base64.b64encode(raw).decode("ascii")

    async def _resolve_bookshelf_image_path_from_request(self) -> Path | dict[str, str]:
        album_id = self._single_line(request.args.get("album_id"), 40)
        page_index = self._int(request.args.get("page"))
        cover_requested = str(request.args.get("cover") or "").lower() in {"1", "true", "yes"}
        if not album_id or (page_index < 1 and not cover_requested):
            return {"error": "缺少图片参数"}
        try:
            async with self.plugin._data_lock:
                data = deepcopy(self.plugin.data)
            shelf_items = data.get("bookshelf_items") if isinstance(data.get("bookshelf_items"), list) else []
            target = None
            for item in shelf_items:
                if not isinstance(item, dict) or item.get("type") != "jm_album":
                    continue
                if self._single_line(item.get("album_id") or item.get("id"), 40) == album_id:
                    target = item
                    break
            if target is None:
                jm_state = data.get("jm_cosmos_integration") if isinstance(data.get("jm_cosmos_integration"), dict) else {}
                last_album = jm_state.get("last_album") if isinstance(jm_state.get("last_album"), dict) else {}
                if self._single_line(last_album.get("id") or last_album.get("album_id"), 40) == album_id:
                    target = last_album
            pages = target.get("pages") if isinstance(target, dict) and isinstance(target.get("pages"), list) else []
            data_root = Path(str(getattr(self.plugin, "data_dir", ""))).resolve()
            path: Path | None = None
            if cover_requested and isinstance(target, dict):
                cover_path = self._single_line(target.get("cover_path"), 300)
                if cover_path:
                    path = Path(cover_path).resolve()
            if path is None:
                page = next((item for item in pages if isinstance(item, dict) and self._int(item.get("index")) == page_index), None)
                if cover_requested and not isinstance(page, dict):
                    page = next((item for item in pages if isinstance(item, dict) and self._int(item.get("index")) > 0), None)
                if not isinstance(page, dict):
                    return {"error": "图片不存在"}
                path = Path(str(page.get("path") or "")).resolve()
            try:
                path.relative_to(data_root)
            except ValueError:
                return {"error": "图片路径不在书柜目录内"}
            if not path.exists() or not path.is_file():
                return {"error": "图片文件不存在"}
            return path
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 读取书柜图片失败: {exc}", exc_info=True)
            return {"error": str(exc)}

    async def delete_bookshelf_item(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        access_token = self._bookshelf_request_token(payload)
        if not self._bookshelf_access_token_valid(access_token):
            return self._error(self._bookshelf_access_error()["error"])
        kind = self._single_line(payload.get("kind"), 32)
        item_id = self._single_line(payload.get("id"), 80)
        album_payload_id = self._single_line(payload.get("album_id"), 80)
        title_payload = self._single_line(payload.get("title"), 120)
        date_key = self._single_line(payload.get("date"), 32)
        try:
            async with self.plugin._data_lock:
                changed = False
                if kind == "creative":
                    projects = self.plugin.data.setdefault("creative_projects", [])
                    if not isinstance(projects, list):
                        projects = []
                    before = len(projects)
                    self.plugin.data["creative_projects"] = [
                        item
                        for item in projects
                        if not (isinstance(item, dict) and self._single_line(item.get("id"), 80) == item_id)
                    ]
                    changed = len(self.plugin.data["creative_projects"]) != before
                elif kind == "diary":
                    diaries = self.plugin.data.setdefault("bot_diaries", [])
                    if not isinstance(diaries, list):
                        diaries = []
                    before = len(diaries)
                    self.plugin.data["bot_diaries"] = [
                        item
                        for item in diaries
                        if not (isinstance(item, dict) and self._single_line(item.get("date"), 32) == date_key)
                    ]
                    changed = len(self.plugin.data["bot_diaries"]) != before
                elif kind == "jm_album":
                    album_id = album_payload_id or item_id.removeprefix("jm-")
                    album_id = album_id.removeprefix("jm-").removeprefix("jm_album:")
                    match_keys = {
                        value
                        for value in {
                            album_id,
                            item_id,
                            item_id.removeprefix("jm-"),
                            f"jm-{album_id}" if album_id else "",
                            f"jm_album:{album_id}" if album_id else "",
                        }
                        if value
                    }
                    items = self.plugin.data.setdefault("bookshelf_items", [])
                    if not isinstance(items, list):
                        items = []
                    removed_pages: list[dict[str, Any]] = []
                    removed_album_ids: set[str] = set()
                    kept = []
                    for item in items:
                        if not isinstance(item, dict) or item.get("type") != "jm_album":
                            kept.append(item)
                            continue
                        item_values = {
                            self._single_line(item.get("album_id"), 80),
                            self._single_line(item.get("id"), 80),
                            self._single_line(item.get("key"), 100),
                        }
                        title_matched = bool(title_payload and self._single_line(item.get("title"), 120) == title_payload)
                        if match_keys.intersection(value for value in item_values if value) or title_matched:
                            removed_album_id = self._single_line(item.get("album_id") or item.get("id"), 80)
                            if removed_album_id:
                                removed_album_ids.add(removed_album_id)
                            if isinstance(item.get("pages"), list):
                                removed_pages.extend(page for page in item.get("pages", []) if isinstance(page, dict))
                            changed = True
                            continue
                        kept.append(item)
                    self.plugin.data["bookshelf_items"] = kept
                    state = self.plugin.data.get("jm_cosmos_integration")
                    if isinstance(state, dict):
                        last_album = state.get("last_album")
                        last_values = {
                            self._single_line(last_album.get("id"), 80),
                            self._single_line(last_album.get("album_id"), 80),
                            self._single_line(last_album.get("key"), 100),
                        } if isinstance(last_album, dict) else set()
                        last_title_matched = bool(
                            isinstance(last_album, dict)
                            and title_payload
                            and self._single_line(last_album.get("title"), 120) == title_payload
                        )
                        if isinstance(last_album, dict) and (match_keys.intersection(value for value in last_values if value) or last_title_matched):
                            removed_album_id = self._single_line(last_album.get("id") or last_album.get("album_id"), 80)
                            if removed_album_id:
                                removed_album_ids.add(removed_album_id)
                            state["last_album"] = {}
                            changed = True
                    if not changed and album_id:
                        data_root = Path(str(getattr(self.plugin, "data_dir", ""))).resolve()
                        if (data_root / "bookshelf_pages" / album_id).exists():
                            removed_album_ids.add(album_id)
                            changed = True
                    if removed_album_ids or title_payload:
                        state = self.plugin.data.setdefault("jm_cosmos_integration", {})
                        if not isinstance(state, dict):
                            state = {}
                            self.plugin.data["jm_cosmos_integration"] = state
                        deleted_ids = state.setdefault("deleted_album_ids", [])
                        if not isinstance(deleted_ids, list):
                            deleted_ids = []
                            state["deleted_album_ids"] = deleted_ids
                        for removed_id in sorted(removed_album_ids):
                            if removed_id and removed_id not in deleted_ids:
                                deleted_ids.append(removed_id)
                        del deleted_ids[:-300]
                        deleted_titles = state.setdefault("deleted_titles", [])
                        if not isinstance(deleted_titles, list):
                            deleted_titles = []
                            state["deleted_titles"] = deleted_titles
                        removed_titles = [
                            self._single_line(item.get("title"), 120)
                            for item in items
                            if isinstance(item, dict)
                            and item.get("type") == "jm_album"
                            and self._single_line(item.get("album_id") or item.get("id"), 80) in removed_album_ids
                        ]
                        if title_payload:
                            removed_titles.append(title_payload)
                        for removed_title in removed_titles:
                            if removed_title and removed_title not in deleted_titles:
                                deleted_titles.append(removed_title)
                        del deleted_titles[:-300]
                    self._cleanup_bookshelf_page_files(removed_pages)
                    self._cleanup_bookshelf_album_dirs(removed_album_ids)
                    logger.info(
                        "[PrivateCompanionPage] 书柜夹层移除: changed=%s id=%s album_id=%s title=%s removed=%s",
                        changed,
                        item_id,
                        album_id,
                        title_payload,
                        sorted(removed_album_ids),
                    )
                else:
                    return self._error("不支持的书柜项目类型")
                if changed:
                    self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"changed": changed, "bookshelf": await self._bookshelf_summary(data, unlocked=True, access_token=access_token)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 删除书柜项目失败: {exc}", exc_info=True)
            return self._error(str(exc))

    def _cleanup_bookshelf_page_files(self, pages: list[dict[str, Any]]) -> None:
        data_root = Path(str(getattr(self.plugin, "data_dir", ""))).resolve()
        touched_dirs: set[Path] = set()
        for page in pages:
            path = Path(str(page.get("path") or "")).resolve()
            try:
                path.relative_to(data_root)
            except ValueError:
                continue
            if not path.exists() or not path.is_file():
                continue
            touched_dirs.add(path.parent)
            try:
                path.unlink()
            except Exception:
                pass
        for folder in touched_dirs:
            try:
                folder.relative_to(data_root / "bookshelf_pages")
            except ValueError:
                continue
            try:
                if folder.exists() and not any(folder.iterdir()):
                    shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                pass

    def _cleanup_bookshelf_album_dirs(self, album_ids: set[str]) -> None:
        if not album_ids:
            return
        data_root = Path(str(getattr(self.plugin, "data_dir", ""))).resolve()
        page_root = data_root / "bookshelf_pages"
        for album_id in album_ids:
            safe_id = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(album_id or ""))
            if not safe_id:
                continue
            folder = (page_root / safe_id).resolve()
            try:
                folder.relative_to(page_root.resolve())
            except ValueError:
                continue
            try:
                shutil.rmtree(folder, ignore_errors=True)
            except Exception:
                pass

    async def rate_bookshelf_item(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        access_token = self._bookshelf_request_token(payload)
        if not self._bookshelf_access_token_valid(access_token):
            return self._error(self._bookshelf_access_error()["error"])
        album_id = self._single_line(payload.get("album_id") or payload.get("id"), 32)
        rating = self._int(payload.get("rating"))
        reason = self._single_line(payload.get("reason"), 160)
        if not album_id:
            return self._error("缺少 album_id")
        if rating < 1 or rating > 10:
            return self._error("评分必须是 1 到 10")
        try:
            async with self.plugin._data_lock:
                items = self.plugin.data.setdefault("bookshelf_items", [])
                if not isinstance(items, list):
                    items = []
                    self.plugin.data["bookshelf_items"] = items
                target: dict[str, Any] | None = None
                for item in items:
                    if not isinstance(item, dict) or item.get("type") != "jm_album":
                        continue
                    if str(item.get("album_id") or item.get("id") or "") == album_id:
                        item["user_rating"] = rating
                        item["user_rating_reason"] = reason
                        item["user_rated_ts"] = time.time()
                        target = item
                        break
                state = self.plugin.data.setdefault("jm_cosmos_integration", {})
                if isinstance(state, dict):
                    last_album = state.get("last_album")
                    if isinstance(last_album, dict) and str(last_album.get("id") or last_album.get("album_id") or "") == album_id:
                        last_album["user_rating"] = rating
                        last_album["user_rating_reason"] = reason
                        last_album["user_rated_ts"] = time.time()
                        if target is None:
                            target = last_album
                if target is None:
                    return self._error("没有找到这条私密阅读记录")
                updater = getattr(self.plugin, "_update_private_reading_preference_profile", None)
                if callable(updater):
                    updater(target)
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"bookshelf": await self._bookshelf_summary(data, unlocked=True, access_token=access_token)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 保存私密阅读评分失败: {exc}", exc_info=True)
            return self._error(str(exc))

    def _normalize_bookshelf_tag_list(self, value: Any, *, limit: int = 8) -> list[str]:
        raw_items: list[Any]
        if isinstance(value, str):
            raw_items = re.split(r"[,，、\s\n\r]+", value)
        elif isinstance(value, list):
            raw_items = value
        else:
            raw_items = []
        tags: list[str] = []
        seen: set[str] = set()
        for raw in raw_items:
            tag = self._single_line(raw, 24)
            if not tag:
                continue
            normalized = tag.casefold()
            if normalized in seen:
                continue
            seen.add(normalized)
            tags.append(tag)
            if len(tags) >= limit:
                break
        return tags

    def _normalize_bookshelf_page_comment(self, value: Any, *, limit: int = 100) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        page_no = self._int(value.get("page"))
        comment_text = self._single_line(value.get("comment"), limit)
        if page_no <= 0 or not comment_text:
            return None
        return {
            "page": page_no,
            "comment": comment_text,
            "raw_page": self._int(value.get("raw_page")),
            "sample_order": self._int(
                value.get("sample_order")
                or value.get("sample_index")
                or value.get("reference_index")
                or value.get("image_index")
            ),
        }

    def _merge_bookshelf_page_comments(self, *sources: Any, limit: int = 24) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[tuple[int, str]] = set()
        for source in sources:
            if not isinstance(source, list):
                continue
            for item in source:
                normalized = self._normalize_bookshelf_page_comment(item)
                if not normalized:
                    continue
                key = (normalized["page"], normalized["comment"])
                if key in seen:
                    continue
                seen.add(key)
                merged.append(normalized)
                if len(merged) >= limit:
                    return merged
        return merged

    async def update_bookshelf_item_tags(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        access_token = self._bookshelf_request_token(payload)
        if not self._bookshelf_access_token_valid(access_token):
            return self._error(self._bookshelf_access_error()["error"])
        album_id = self._single_line(payload.get("album_id") or payload.get("id"), 32)
        liked_tags = self._normalize_bookshelf_tag_list(payload.get("liked_tags"))
        disliked_tags_raw = self._normalize_bookshelf_tag_list(payload.get("disliked_tags"))
        liked_seen = {tag.casefold() for tag in liked_tags}
        disliked_tags = [tag for tag in disliked_tags_raw if tag.casefold() not in liked_seen]
        if not album_id:
            return self._error("缺少 album_id")
        try:
            async with self.plugin._data_lock:
                items = self.plugin.data.setdefault("bookshelf_items", [])
                if not isinstance(items, list):
                    items = []
                    self.plugin.data["bookshelf_items"] = items
                target: dict[str, Any] | None = None
                for item in items:
                    if not isinstance(item, dict) or item.get("type") != "jm_album":
                        continue
                    if str(item.get("album_id") or item.get("id") or "") == album_id:
                        item["user_liked_tags"] = liked_tags
                        item["user_disliked_tags"] = disliked_tags
                        item["user_tags_updated_ts"] = time.time()
                        target = item
                        break
                state = self.plugin.data.setdefault("jm_cosmos_integration", {})
                if isinstance(state, dict):
                    last_album = state.get("last_album")
                    if isinstance(last_album, dict) and str(last_album.get("id") or last_album.get("album_id") or "") == album_id:
                        last_album["user_liked_tags"] = liked_tags
                        last_album["user_disliked_tags"] = disliked_tags
                        last_album["user_tags_updated_ts"] = time.time()
                        if target is None:
                            target = last_album
                if target is None:
                    return self._error("没有找到这条私密阅读记录")
                updater = getattr(self.plugin, "_update_private_reading_preference_profile", None)
                if callable(updater):
                    updater(target)
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"bookshelf": await self._bookshelf_summary(data, unlocked=True, access_token=access_token)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 保存私密阅读标签失败: {exc}", exc_info=True)
            return self._error(str(exc))

    def _resolve_bookshelf_data_file(self, value: Any) -> Path | None:
        path_text = self._single_line(value, 500)
        if not path_text:
            return None
        data_root = Path(str(getattr(self.plugin, "data_dir", ""))).resolve()
        try:
            raw_path = Path(path_text)
            path = raw_path.resolve() if raw_path.is_absolute() else (data_root / raw_path).resolve()
            path.relative_to(data_root)
            if path.exists() and path.is_file():
                return path
        except Exception:
            return None
        return None

    def _jm_album_comment_sample(self, item: dict[str, Any]) -> tuple[Path | None, list[Path], list[int]]:
        cover_path = self._resolve_bookshelf_data_file(item.get("cover_path"))
        pages = item.get("pages") if isinstance(item.get("pages"), list) else []
        page_by_index: dict[int, Path] = {}
        for page in pages:
            if not isinstance(page, dict):
                continue
            page_index = self._int(page.get("index"))
            page_path = self._resolve_bookshelf_data_file(page.get("path"))
            if page_index > 0 and page_path:
                page_by_index[page_index] = page_path
        sampled_pages = [
            self._int(page)
            for page in (item.get("sampled_pages") if isinstance(item.get("sampled_pages"), list) else [])
            if self._int(page) > 0 and self._int(page) in page_by_index
        ][:5]
        if not sampled_pages:
            sampled_pages = sorted(page_by_index)[:5]
        return cover_path, [page_by_index[page] for page in sampled_pages if page in page_by_index], sampled_pages

    async def update_bookshelf_item_comments(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        access_token = self._bookshelf_request_token(payload)
        if not self._bookshelf_access_token_valid(access_token):
            return self._error(self._bookshelf_access_error()["error"])
        album_id = self._single_line(payload.get("album_id") or payload.get("id"), 32)
        if not album_id:
            return self._error("缺少 album_id")
        try:
            async with self.plugin._data_lock:
                items = self.plugin.data.get("bookshelf_items") if isinstance(self.plugin.data.get("bookshelf_items"), list) else []
                target = next(
                    (
                        item
                        for item in items
                        if isinstance(item, dict)
                        and item.get("type") == "jm_album"
                        and str(item.get("album_id") or item.get("id") or "") == album_id
                    ),
                    None,
                )
                if target is None:
                    state = self.plugin.data.get("jm_cosmos_integration") if isinstance(self.plugin.data.get("jm_cosmos_integration"), dict) else {}
                    last_album = state.get("last_album") if isinstance(state.get("last_album"), dict) else None
                    if last_album and str(last_album.get("id") or last_album.get("album_id") or "") == album_id:
                        target = last_album
                if target is None:
                    return self._error("没有找到这条私密阅读记录")
                target_snapshot = deepcopy(target)
            cover_path, page_paths, sampled_pages = self._jm_album_comment_sample(target_snapshot)
            if not page_paths:
                return self._error("没有找到可用于重读的本地图片")
            vision = getattr(self.plugin, "_call_jm_cosmos_vision", None)
            if not callable(vision):
                return self._error("当前插件版本不支持让 Bot 重读")
            vision_result = await vision(cover_path, target_snapshot, page_paths=page_paths, sampled_pages=sampled_pages)
            if not isinstance(vision_result, dict) or not (vision_result.get("impression") or vision_result.get("page_comments")):
                return self._error("这次没有生成新的读后感或批注")
            updates: dict[str, Any] = {
                "comments_updated_ts": time.time(),
                "sampled_pages": sampled_pages,
            }
            impression = self._single_line(vision_result.get("impression"), 600)
            if impression:
                updates["impression"] = impression
                updates["reading_impression"] = impression
            rating = self._int(vision_result.get("rating"))
            if 1 <= rating <= 10:
                updates["rating"] = rating
            rating_reason = self._single_line(vision_result.get("rating_reason"), 160)
            if rating_reason:
                updates["rating_reason"] = rating_reason
            preference_tags = self._normalize_bookshelf_tag_list(vision_result.get("preference_tags"))
            if preference_tags:
                updates["preference_tags"] = preference_tags
            page_comments = vision_result.get("page_comments") if isinstance(vision_result.get("page_comments"), list) else []
            normalized_comments: list[dict[str, Any]] = []
            for comment in page_comments[:8]:
                normalized = self._normalize_bookshelf_page_comment(comment, limit=80)
                if normalized:
                    normalized_comments.append(normalized)
            if normalized_comments:
                existing_comments = target_snapshot.get("page_comments") if isinstance(target_snapshot.get("page_comments"), list) else []
                previous_comments = (
                    target_snapshot.get("page_comments_previous")
                    if isinstance(target_snapshot.get("page_comments_previous"), list)
                    else []
                )
                updates["page_comments"] = self._merge_bookshelf_page_comments(
                    existing_comments,
                    normalized_comments,
                    previous_comments,
                    limit=24,
                )
                updates["page_comments_previous"] = existing_comments[:12]
            async with self.plugin._data_lock:
                items = self.plugin.data.get("bookshelf_items") if isinstance(self.plugin.data.get("bookshelf_items"), list) else []
                written = False
                for item in items:
                    if not isinstance(item, dict) or item.get("type") != "jm_album":
                        continue
                    if str(item.get("album_id") or item.get("id") or "") == album_id:
                        item.update(updates)
                        target = item
                        written = True
                        break
                state = self.plugin.data.setdefault("jm_cosmos_integration", {})
                if isinstance(state, dict):
                    last_album = state.get("last_album")
                    if isinstance(last_album, dict) and str(last_album.get("id") or last_album.get("album_id") or "") == album_id:
                        last_album.update(updates)
                        if not written:
                            target = last_album
                            written = True
                if not written:
                    return self._error("没有找到可写回的私密阅读记录")
                updater = getattr(self.plugin, "_update_private_reading_preference_profile", None)
                if callable(updater):
                    updater(target)
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"message": "Bot 已重新读过并更新读后感", "bookshelf": await self._bookshelf_summary(data, unlocked=True, access_token=access_token)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新私密阅读批注失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def import_worldbook(self) -> dict[str, Any]:
        try:
            async with self.plugin._data_lock:
                changed = bool(self.plugin._import_worldbook_entries_from_sources())
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"changed": changed, "worldbook": self._worldbook_summary(data)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 导入世界书失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def update_worldbook_member(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        raw_user_id = self._single_line(payload.get("user_id"), 80)
        user_id = self._normalize_worldbook_member_id(raw_user_id)
        if not user_id:
            return self._error("缺少 user_id")
        try:
            async with self.plugin._data_lock:
                profiles = self.plugin.data.setdefault("worldbook_member_profiles", {})
                if not isinstance(profiles, dict):
                    profiles = {}
                    self.plugin.data["worldbook_member_profiles"] = profiles
                if payload.get("delete"):
                    deleted = self.plugin.data.setdefault("worldbook_deleted_member_ids", [])
                    if not isinstance(deleted, list):
                        deleted = []
                        self.plugin.data["worldbook_deleted_member_ids"] = deleted
                    if user_id not in deleted:
                        deleted.append(user_id)
                    changed = profiles.pop(user_id, None) is not None
                    self.plugin._save_data_sync()
                    data = deepcopy(self.plugin.data)
                    return self._ok({"changed": changed, "message": "已删除关系节点", "worldbook": self._worldbook_summary(data)})
                if not self._worldbook_member_id_valid(user_id):
                    return self._error("关系节点必须使用有效 QQ 号或 B 站外部身份键")
                linked_qq_user_id = self._single_line(
                    payload.get("linked_qq_user_id") or payload.get("bound_qq_user_id") or payload.get("qq_user_id"),
                    40,
                )
                if linked_qq_user_id and (not linked_qq_user_id.isdigit() or len(linked_qq_user_id) < 5):
                    return self._error("绑定目标必须是有效 QQ 号")
                deleted = self.plugin.data.setdefault("worldbook_deleted_member_ids", [])
                if isinstance(deleted, list) and user_id in deleted:
                    self.plugin.data["worldbook_deleted_member_ids"] = [item for item in deleted if str(item) != user_id]
                profile = profiles.get(user_id)
                if not isinstance(profile, dict):
                    profile = {
                        "user_id": user_id,
                        "name": user_id,
                        "gender": "",
                        "aliases": [],
                        "content": "",
                        "identity_note": "",
                        "boundary_note": "",
                        "important_memories": [],
                        "enabled": True,
                        "priority": 120,
                        "source_entries": ["手动维护"],
                        "observed_names": [],
                    }
                    profiles[user_id] = profile
                profile["user_id"] = user_id
                profile["identity_type"] = "qq" if user_id.isdigit() else "external"
                if "enabled" in payload:
                    profile["enabled"] = bool(payload.get("enabled"))
                if "name" in payload:
                    profile["name"] = self._single_line(payload.get("name"), 80) or user_id
                if "gender" in payload:
                    profile["gender"] = self._single_line(payload.get("gender"), 40)
                if "aliases" in payload and isinstance(payload.get("aliases"), list):
                    profile["aliases"] = [self._single_line(item, 40) for item in payload.get("aliases", []) if self._single_line(item, 40)]
                if "content" in payload:
                    profile["content"] = str(payload.get("content") or "").strip()[:2000]
                if "note" in payload:
                    profile["note"] = str(payload.get("note") or "").strip()[:2000]
                if "identity_note" in payload:
                    profile["identity_note"] = str(payload.get("identity_note") or "").strip()[:2000]
                if "boundary_note" in payload:
                    profile["boundary_note"] = str(payload.get("boundary_note") or "").strip()[:1200]
                if "important_memories" in payload:
                    profile["important_memories"] = self._normalize_important_memories(payload.get("important_memories"))
                if "accept_pending_observation_id" in payload or "reject_pending_observation_id" in payload:
                    pending = profile.get("pending_observations") if isinstance(profile.get("pending_observations"), list) else []
                    target_id = self._single_line(
                        payload.get("accept_pending_observation_id") or payload.get("reject_pending_observation_id"),
                        40,
                    )
                    kept = []
                    accepted = None
                    for item in pending:
                        if not isinstance(item, dict):
                            continue
                        if self._single_line(item.get("id"), 40) == target_id:
                            accepted = item
                            continue
                        kept.append(item)
                    profile["pending_observations"] = kept[:8]
                    if accepted and payload.get("accept_pending_observation_id"):
                        memories = self._normalize_important_memories(profile.get("important_memories"))
                        memories.insert(
                            0,
                            {
                                "title": self._single_line(accepted.get("title"), 60) or "群聊观察",
                                "content": str(accepted.get("content") or accepted.get("evidence") or "").strip()[:500],
                                "weight": self._clamp_int(accepted.get("weight"), 35, 0, 100),
                                "privacy": "internal",
                                "source": "group_observation",
                                "enabled": True,
                                "updated_at": time.time(),
                            },
                        )
                        profile["important_memories"] = self._normalize_important_memories(memories)
                if "priority" in payload:
                    profile["priority"] = self._clamp_int(payload.get("priority"), 120, -1000, 10000)
                profile["manual_edit_ts"] = time.time()
                bind_result: dict[str, Any] | None = None
                if linked_qq_user_id and linked_qq_user_id != user_id:
                    bind_result = self._bind_worldbook_external_member_locked(profiles, user_id, linked_qq_user_id, profile)
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            if payload.keys() <= {"user_id", "enabled"}:
                message = "已更新关系节点状态"
            elif "important_memories" in payload and len(payload) <= 2:
                message = "已更新重要记忆"
            elif bind_result:
                message = "已绑定到 QQ 关系节点"
            else:
                message = "已保存关系节点"
            response = {"message": message, "worldbook": self._worldbook_summary(data)}
            if bind_result:
                response["bind"] = bind_result
            return self._ok(response)
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新关系节点失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def get_worldbook_member_livingmemory(self) -> dict[str, Any]:
        user_id = self._normalize_worldbook_member_id(self._single_line(request.args.get("user_id"), 80))
        if not user_id:
            return self._error("缺少 user_id")
        limit = self._query_int("limit", 20, 1, 60)
        try:
            async with self.plugin._data_lock:
                profiles = self.plugin.data.get("worldbook_member_profiles") if isinstance(self.plugin.data.get("worldbook_member_profiles"), dict) else {}
                profile = profiles.get(user_id)
                if not isinstance(profile, dict):
                    return self._error("没有找到对应关系节点")
                profile_copy = deepcopy(profile)
            token_bundle = self._worldbook_member_livingmemory_tokens(user_id, profile_copy)
            tokens = token_bundle.get("tokens", [])
            db_path = self._livingmemory_db_path()
            if not db_path:
                return self._ok(
                    {
                        "available": False,
                        "user_id": user_id,
                        "tokens": tokens,
                        "items": [],
                        "total": 0,
                        "message": "未找到 LivingMemory 数据库",
                    }
                )
            items = await asyncio.to_thread(self._query_livingmemory_for_tokens, db_path, token_bundle, limit)
            return self._ok(
                {
                    "available": True,
                    "db_path": str(db_path),
                    "user_id": user_id,
                    "tokens": tokens,
                    "primary_tokens": token_bundle.get("primary_tokens", []),
                    "support_tokens": token_bundle.get("support_tokens", []),
                    "items": items,
                    "total": len(items),
                    "filter_note": "默认仅召回命中 QQ/绑定身份/关系节点名称的记忆；别名和群名片只用于加分。",
                    "message": f"已找到 {len(items)} 条 LivingMemory 相关记忆",
                }
            )
        except sqlite3.OperationalError as exc:
            logger.warning(f"[PrivateCompanionPage] 查询 LivingMemory 失败: {exc}")
            return self._error(f"LivingMemory 数据库暂时不可读：{exc}")
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 查询关系节点 LivingMemory 失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def clear_worldbook_pending_observations(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        user_id = self._single_line(payload.get("user_id"), 40)
        try:
            async with self.plugin._data_lock:
                profiles = self.plugin.data.setdefault("worldbook_member_profiles", {})
                if not isinstance(profiles, dict):
                    profiles = {}
                    self.plugin.data["worldbook_member_profiles"] = profiles
                cleared = 0
                touched = 0
                for profile_id, profile in profiles.items():
                    if user_id and str(profile_id) != user_id:
                        continue
                    if not isinstance(profile, dict):
                        continue
                    pending = profile.get("pending_observations")
                    if not isinstance(pending, list) or not pending:
                        continue
                    cleared += len([item for item in pending if isinstance(item, dict)])
                    profile["pending_observations"] = []
                    profile["pending_observations_cleared_at"] = time.time()
                    touched += 1
                if user_id and not touched:
                    return self._error("没有找到可清理的待确认观察")
                if touched:
                    self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            message = f"已清理 {cleared} 条待确认观察" if cleared else "没有待确认观察需要清理"
            return self._ok({"message": message, "cleared": cleared, "worldbook": self._worldbook_summary(data)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 清理待确认观察失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def update_worldbook_group(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        group_id = self._single_line(payload.get("group_id"), 40)
        if not group_id:
            return self._error("缺少 group_id")
        try:
            async with self.plugin._data_lock:
                groups = self.plugin.data.setdefault("worldbook_group_profiles", {})
                if not isinstance(groups, dict):
                    groups = {}
                    self.plugin.data["worldbook_group_profiles"] = groups
                if payload.get("delete"):
                    deleted = self.plugin.data.setdefault("worldbook_deleted_group_ids", [])
                    if not isinstance(deleted, list):
                        deleted = []
                        self.plugin.data["worldbook_deleted_group_ids"] = deleted
                    if group_id not in deleted:
                        deleted.append(group_id)
                    changed = groups.pop(group_id, None) is not None
                    self.plugin._save_data_sync()
                    data = deepcopy(self.plugin.data)
                    return self._ok({"changed": changed, "message": "已删除群资料", "worldbook": self._worldbook_summary(data)})
                deleted = self.plugin.data.setdefault("worldbook_deleted_group_ids", [])
                if isinstance(deleted, list) and group_id in deleted:
                    self.plugin.data["worldbook_deleted_group_ids"] = [item for item in deleted if str(item) != group_id]
                group = groups.get(group_id)
                if not isinstance(group, dict):
                    group = {
                        "group_id": group_id,
                        "name": group_id,
                        "content": "",
                        "enabled": True,
                        "priority": 110,
                        "aliases": [],
                        "source_entries": ["手动维护"],
                    }
                    groups[group_id] = group
                group["group_id"] = group_id
                if "enabled" in payload:
                    group["enabled"] = bool(payload.get("enabled"))
                if "name" in payload:
                    group["name"] = self._single_line(payload.get("name"), 80) or group_id
                if "content" in payload:
                    group["content"] = str(payload.get("content") or "").strip()[:2000]
                if "priority" in payload:
                    group["priority"] = self._clamp_int(payload.get("priority"), 110, -1000, 10000)
                group["manual_edit_ts"] = time.time()
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"message": "已保存群资料", "worldbook": self._worldbook_summary(data)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新群资料失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def apply_preset(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        name = str(payload.get("name", "")).strip()
        presets = self._presets()
        if name not in presets:
            return self._error("未知预设")
        preset = presets[name]
        try:
            for key, value in preset.get("settings", {}).items():
                self._apply_config_value(key, self._normalize_setting_value(key, value))
            for key, value in preset.get("features", {}).items():
                if key in self._allowed_feature_keys():
                    self._apply_config_value(key, self._normalize_bool_value(value))
            config_saved = await self._save_config_if_possible()
            overview = await self.get_overview()
            if overview.get("success"):
                overview["data"]["preset"] = name
                overview["data"]["preset_label"] = preset.get("label", name)
                overview["data"]["config_saved"] = config_saved
            return overview
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 应用预设失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def update_skill_growth(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        skill_id = self._single_line(payload.get("id"), 40)
        name = self._single_line(payload.get("name"), 32)
        if not skill_id and not name:
            return self._error("缺少技能名称")
        def _parse_bool(value: Any, default: bool = False) -> bool:
            if value is None:
                return default
            if isinstance(value, bool):
                return value
            if isinstance(value, (int, float)):
                return bool(value)
            return str(value).strip().lower() in {"1", "true", "yes", "on", "启用", "开启"}

        def _parse_terms(value: Any, *, limit: int = 16) -> list[str]:
            if isinstance(value, list):
                raw_items = value
            else:
                raw_items = re.split(r"[,，、\n]+", str(value or ""))
            items: list[str] = []
            for raw in raw_items:
                item = self._single_line(raw, 24)
                if item and item not in items:
                    items.append(item)
            return items[:limit]

        try:
            async with self.plugin._data_lock:
                state = self.plugin.data.setdefault("skill_growth", {})
                if not isinstance(state, dict):
                    state = {}
                    self.plugin.data["skill_growth"] = state
                skills = state.setdefault("skills", {})
                if not isinstance(skills, dict):
                    skills = {}
                    state["skills"] = skills

                if payload.get("delete"):
                    changed = bool(skill_id and skills.pop(skill_id, None) is not None)
                    state["updated_ts"] = time.time()
                    self.plugin._save_data_sync()
                    return self._ok({"changed": changed, "message": "已删除技能", "skill_growth": self._skill_growth_summary(self.plugin.data)})

                if not name:
                    return self._error("缺少技能名称")
                if not skill_id:
                    for existing_id, existing_skill in skills.items():
                        if not isinstance(existing_skill, dict):
                            continue
                        existing_name = self._single_line(existing_skill.get("name"), 32)
                        existing_aliases = existing_skill.get("aliases") if isinstance(existing_skill.get("aliases"), list) else []
                        alias_set = {self._single_line(item, 24) for item in existing_aliases}
                        if name == existing_name:
                            skill_id = self._single_line(existing_id, 40)
                            break
                        if name in alias_set:
                            return self._error(f"“{name}”已经是“{existing_name or '未命名技能'}”的合并别名，请直接编辑该技能")
                if not skill_id:
                    skill_id = hashlib.sha1(name.encode("utf-8")).hexdigest()[:12]
                existing = skills.get(skill_id) if isinstance(skills.get(skill_id), dict) else {}
                level = max(1, min(6, self._int(payload.get("level")) or self._int(existing.get("level")) or 1))
                exp = self._float(payload.get("exp"))
                if exp <= 0 and isinstance(existing, dict):
                    exp = self._float(existing.get("exp"))
                if exp <= 0:
                    exp = {1: 0, 2: 100, 3: 260, 4: 520, 5: 900, 6: 1400}.get(level, 0)
                if hasattr(self.plugin, "_skill_level_from_exp"):
                    level = self.plugin._skill_level_from_exp(exp)
                keywords = _parse_terms(payload.get("keywords")) or [name]
                aliases = _parse_terms(payload.get("aliases"), limit=12)
                hidden = _parse_bool(payload.get("hidden"), bool(existing.get("hidden")) if isinstance(existing, dict) else False)
                frozen = _parse_bool(payload.get("frozen"), bool(existing.get("frozen")) if isinstance(existing, dict) else False)
                skill = dict(existing) if isinstance(existing, dict) else {}
                skill.update(
                    {
                        "id": skill_id,
                        "name": name,
                        "category": self._single_line(payload.get("category"), 20) or self._single_line(skill.get("category"), 20) or "能力",
                        "keywords": keywords,
                        "aliases": [item for item in aliases if item != name],
                        "hidden": hidden,
                        "frozen": frozen,
                        "exp": round(max(0.0, exp), 2),
                        "level": level,
                        "level_title": self.plugin._skill_level_title(level) if hasattr(self.plugin, "_skill_level_title") else self._single_line(skill.get("level_title"), 24),
                        "created_ts": self._float(skill.get("created_ts")) or time.time(),
                        "last_trained_ts": self._float(skill.get("last_trained_ts")),
                        "training_count": self._int(skill.get("training_count")),
                        "recent_logs": skill.get("recent_logs") if isinstance(skill.get("recent_logs"), list) else [],
                    }
                )
                skills[skill_id] = skill
                state["updated_ts"] = time.time()
                self.plugin._save_data_sync()
                return self._ok({"message": "已保存技能", "skill_growth": self._skill_growth_summary(self.plugin.data)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新技能失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def update_external_ability(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        normalizer = getattr(self.plugin, "_normalize_external_ability_name", None)
        name = self._single_line(payload.get("name"), 80)
        name = normalizer(name) if callable(normalizer) else name
        if not name:
            return self._error("缺少外部能力名称")
        try:
            async with self.plugin._data_lock:
                store_getter = getattr(self.plugin, "_external_ability_store", None)
                store = store_getter() if callable(store_getter) else self.plugin.data.setdefault("external_proactive_abilities", {})
                if not isinstance(store, dict):
                    store = {}
                    self.plugin.data["external_proactive_abilities"] = store
                item = store.get(name) if isinstance(store.get(name), dict) else {"name": name}
                if "enabled" in payload:
                    item["enabled"] = bool(payload.get("enabled"))
                if "share_probability" in payload:
                    item["share_probability"] = max(0.0, min(1.0, self._float(payload.get("share_probability"))))
                if "min_interval_hours" in payload:
                    item["min_interval_hours"] = max(0.0, self._float(payload.get("min_interval_hours")))
                if "config" in payload:
                    config = payload.get("config")
                    if isinstance(config, str):
                        import json
                        config = json.loads(config or "{}")
                    if not isinstance(config, dict):
                        return self._error("自定义配置必须是 JSON 对象")
                    item["config"] = config
                item["updated_ts"] = time.time()
                store[name] = item
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"message": "已保存外部主动能力", "external_abilities": self._external_ability_summary(data)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新外部主动能力失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def list_available_providers(self) -> dict[str, Any]:
        try:
            items = self._available_provider_items()
            return self._ok({"items": items, "total": len(items)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取 Provider 列表失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def test_provider(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        key = str(payload.get("key", "")).strip()
        provider_id = self._single_line(payload.get("provider_id"), 160)
        if key and key not in self._allowed_provider_keys():
            return self._error("不允许测试该 Provider 配置项")
        start = time.time()
        try:
            text = await self.plugin._llm_call(
                "请只回复两个字：正常",
                max_tokens=16,
                provider_id=provider_id,
                task="provider_test",
            )
            elapsed_ms = int((time.time() - start) * 1000)
            ok = bool(text)
            return self._ok(
                {
                    "ok": ok,
                    "key": key,
                    "provider_id": provider_id,
                    "elapsed_ms": elapsed_ms,
                    "sample": self._single_line(text, 80),
                }
            )
        except Exception as exc:
            return self._ok(
                {
                    "ok": False,
                    "key": key,
                    "provider_id": provider_id,
                    "elapsed_ms": int((time.time() - start) * 1000),
                    "error": str(exc),
                }
            )

    def _user_summary(self, user_id: str, user: dict[str, Any]) -> dict[str, Any]:
        last_seen = user.get("last_seen", 0)
        last_sent = user.get("last_sent", 0)
        user_id_text = str(user_id)
        is_qq_user = user_id_text.isdigit()
        umo = str(user.get("umo", "") or "")
        source = self._single_line(umo.split(":", 1)[0], 40) if ":" in umo else ""
        nickname = self._single_line(user.get("nickname"), 40)
        generic_names = {"用户", "主人", "默认用户"}
        if is_qq_user:
            display_name = nickname if nickname and nickname not in generic_names else user_id_text
        else:
            display_name = f"临时会话 · {user_id_text[:8]}"
        relationship_stage = ""
        rel_state = user.get("relationship_state") if isinstance(user.get("relationship_state"), dict) else {}
        if isinstance(rel_state, dict):
            relationship_stage = self._single_line(rel_state.get("stage"), 12)
        profile_getter = getattr(self.plugin, "_relationship_profile", None)
        if not relationship_stage and callable(profile_getter):
            try:
                profile = profile_getter(user)
                if isinstance(profile, dict):
                    relationship_stage = self._single_line(profile.get("level"), 12)
            except Exception:
                relationship_stage = ""
        if relationship_stage not in {"亲近", "熟悉", "陌生"}:
            persona_profile = user.get("persona_relationship") if isinstance(user.get("persona_relationship"), dict) else {}
            relationship_stage = self._single_line(persona_profile.get("level"), 12) if isinstance(persona_profile, dict) else ""
        if relationship_stage not in {"亲近", "熟悉", "陌生"}:
            score = self._int(user.get("relationship_score"))
            inbound_count = self._int(user.get("inbound_count"))
            proactive_count = self._int(user.get("proactive_sent_count"))
            reply_count = self._int(user.get("reply_count"))
            reply_rate = reply_count / proactive_count if proactive_count > 0 else 0.0
            if score >= 16 and reply_rate >= 0.35:
                relationship_stage = "亲近"
            elif score >= 3 or inbound_count >= 1 or reply_rate >= 0.2:
                relationship_stage = "熟悉"
            else:
                relationship_stage = "陌生"
        role = self.plugin._private_user_role(user, user_id_text) if hasattr(self.plugin, "_private_user_role") else ""
        role_labeler = getattr(self.plugin, "_private_user_role_label", None)
        role_label = role_labeler(role) if callable(role_labeler) else ("主人" if role == "owner" else "朋友")
        return {
            "user_id": user_id_text,
            "display_name": display_name,
            "is_qq_user": is_qq_user,
            "source": source,
            "enabled": bool(user.get("enabled", True)),
            "relationship_role": role,
            "relationship_role_label": role_label,
            "nickname": user.get("nickname", ""),
            "style": user.get("style", ""),
            "umo": user.get("umo", ""),
            "last_seen_ts": last_seen,
            "last_seen": self.plugin._format_timestamp_elapsed(last_seen),
            "last_sent_ts": last_sent,
            "last_sent": self.plugin._format_timestamp_elapsed(last_sent),
            "sent_today": user.get("sent_today", 0),
            "last_proactive_skip_ts": self._float(user.get("last_proactive_skip_at")),
            "last_proactive_skip": self.plugin._format_timestamp_elapsed(user.get("last_proactive_skip_at", 0)),
            "last_proactive_skip_reason": self._single_line(user.get("last_proactive_skip_reason"), 120),
            "last_proactive_skip_prefix": self._single_line(user.get("last_proactive_skip_prefix"), 20),
            "effective_daily_limit": (
                self.plugin._effective_user_daily_limit(user)
                if hasattr(self.plugin, "_effective_user_daily_limit")
                else getattr(self.plugin, "max_daily_messages", 0)
            ),
            "effective_idle_minutes": (
                self.plugin._effective_user_idle_minutes(user)
                if hasattr(self.plugin, "_effective_user_idle_minutes")
                else getattr(self.plugin, "idle_minutes", 0)
            ),
            "effective_min_interval_minutes": (
                self.plugin._effective_user_min_interval_minutes(user)
                if hasattr(self.plugin, "_effective_user_min_interval_minutes")
                else getattr(self.plugin, "min_interval_minutes", 0)
            ),
            "effective_screen_peek_daily_limit": (
                self.plugin._effective_user_screen_peek_daily_limit(user)
                if hasattr(self.plugin, "_effective_user_screen_peek_daily_limit")
                else getattr(self.plugin, "screen_peek_max_daily", 0)
            ),
            "effective_photo_daily_limit": (
                self.plugin._effective_user_photo_daily_limit(user)
                if hasattr(self.plugin, "_effective_user_photo_daily_limit")
                else getattr(self.plugin, "photo_action_max_daily", 0)
            ),
            "proactive_daily_limit": user.get("proactive_daily_limit", -1),
            "proactive_idle_minutes": user.get("proactive_idle_minutes", -1),
            "proactive_min_interval_minutes": user.get("proactive_min_interval_minutes", -1),
            "photo_daily_limit": user.get("photo_daily_limit", -1),
            "screen_peek_daily_limit": user.get("screen_peek_daily_limit", -1),
            "poke_daily_limit": user.get("poke_daily_limit", -1),
            "proactive_boundary_note": user.get("proactive_boundary_note", ""),
            "inbound_count": user.get("inbound_count", 0),
            "reply_count": user.get("reply_count", 0),
            "proactive_sent_count": user.get("proactive_sent_count", 0),
            "relationship_score": user.get("relationship_score", 0),
            "relationship_stage": relationship_stage,
            "planned_reason": user.get("planned_proactive_reason", ""),
            "planned_action": user.get("planned_proactive_action", ""),
            "next_proactive_ts": user.get("next_proactive_at", 0),
            "next_proactive": self.plugin._format_next_proactive(user),
            "memory_items": self._memory_item_count(user.get("companion_memory")),
            "dialogue_episode_count": len(user.get("dialogue_episodes") or []),
            "open_loop_count": len(user.get("open_loops") or []),
            "habit_count": len(self._behavior_habit_summary(user).get("items", [])),
            "alias_user_ids": [
                self._single_line(item, 80)
                for item in (user.get("alias_user_ids") if isinstance(user.get("alias_user_ids"), list) else [])
                if self._single_line(item, 80)
            ],
        }

    def _worldbook_member_for_private_user_locked(
        self,
        data: dict[str, Any],
        user_id: str,
        user: dict[str, Any],
    ) -> dict[str, Any] | None:
        profiles = data.get("worldbook_member_profiles") if isinstance(data.get("worldbook_member_profiles"), dict) else {}
        if not profiles:
            return None
        candidate_ids = [str(user_id)]
        if isinstance(user, dict):
            candidate_ids.extend(
                self._single_line(item, 80)
                for item in (user.get("alias_user_ids") if isinstance(user.get("alias_user_ids"), list) else [])
                if self._single_line(item, 80)
            )
        for candidate_id in candidate_ids:
            profile = profiles.get(candidate_id)
            if isinstance(profile, dict):
                return self._worldbook_member_profile_summary(candidate_id, profile)
        for profile_id, profile in profiles.items():
            if not isinstance(profile, dict):
                continue
            linked_id = self._single_line(profile.get("linked_qq_user_id") or profile.get("merged_into_user_id"), 80)
            external_ids = profile.get("external_ids") if isinstance(profile.get("external_ids"), list) else []
            external_id_set = {self._single_line(item, 80) for item in external_ids if self._single_line(item, 80)}
            if linked_id in candidate_ids or any(candidate_id in external_id_set for candidate_id in candidate_ids):
                return self._worldbook_member_profile_summary(str(profile_id), profile)
        return None

    def _worldbook_member_profile_summary(self, user_id: str, item: dict[str, Any]) -> dict[str, Any]:
        aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
        observed = item.get("observed_names") if isinstance(item.get("observed_names"), list) else []
        external_ids = item.get("external_ids") if isinstance(item.get("external_ids"), list) else []
        memories = self._normalize_important_memories(item.get("important_memories"))
        pending = item.get("pending_observations") if isinstance(item.get("pending_observations"), list) else []
        return {
            "user_id": self._single_line(user_id, 40),
            "identity_type": self._single_line(item.get("identity_type") or ("qq" if str(user_id).isdigit() else "external"), 20),
            "name": self._single_line(item.get("name"), 60),
            "gender": self._single_line(item.get("gender"), 40),
            "enabled": bool(item.get("enabled", True)),
            "priority": item.get("priority", 120),
            "aliases": [self._single_line(alias, 40) for alias in aliases if self._single_line(alias, 40)],
            "observed_names": [self._single_line(name, 40) for name in observed if self._single_line(name, 40)],
            "external_ids": [self._single_line(ext, 80) for ext in external_ids if self._single_line(ext, 80)],
            "linked_qq_user_id": self._single_line(item.get("linked_qq_user_id") or item.get("merged_into_user_id"), 40),
            "linked_bili_profile_id": self._single_line(item.get("linked_bili_profile_id"), 80),
            "content": self._single_line(item.get("content"), 260),
            "identity_note": self._single_line(item.get("identity_note") or item.get("note") or item.get("content"), 500),
            "boundary_note": self._single_line(item.get("boundary_note"), 500),
            "important_memories": memories[:6],
            "pending_observation_count": len(pending),
            "source_entries": item.get("source_entries") if isinstance(item.get("source_entries"), list) else [],
            "note": self._single_line(item.get("note"), 500),
        }

    def _behavior_habit_summary(self, user: dict[str, Any]) -> dict[str, Any]:
        formatter = getattr(self.plugin, "_qualified_user_behavior_habits", None)
        if callable(formatter):
            try:
                items = formatter(user)
            except Exception:
                items = []
        else:
            raw = user.get("behavior_habits") if isinstance(user.get("behavior_habits"), dict) else {}
            patterns = raw.get("patterns") if isinstance(raw.get("patterns"), list) else []
            items = [item for item in patterns if isinstance(item, dict)]
        normalized = []
        for item in items[:12]:
            if not isinstance(item, dict):
                continue
            normalized.append(
                {
                    "bucket": self._single_line(item.get("bucket"), 12),
                    "category": self._single_line(item.get("category"), 20),
                    "topic": self._single_line(item.get("topic"), 80),
                    "count": self._int(item.get("count")),
                    "avg_time": self.plugin._format_user_habit_time(item.get("avg_minute")) if hasattr(self.plugin, "_format_user_habit_time") else "",
                    "last_seen": self.plugin._format_timestamp_elapsed(item.get("last_seen_ts", 0)),
                    "last_seen_text": self._single_line(item.get("last_seen_text"), 100),
                }
            )
        raw_habits = user.get("behavior_habits") if isinstance(user.get("behavior_habits"), dict) else {}
        return {
            "enabled": bool(getattr(self.plugin, "enable_user_habit_learning", False)),
            "updated_at": self._single_line(raw_habits.get("updated_at"), 30) if isinstance(raw_habits, dict) else "",
            "items": normalized,
        }

    @classmethod
    def _display_message_text(cls, value: Any, limit: int = 500) -> str:
        source = str(value or "").strip()
        source = source.strip("\"'“”‘’` ")
        if re.fullmatch(r"[.。…~～\s\"'“”‘’`-]{0,12}", source):
            return ""
        if re.search(r"<t{2,}s\b[^>]*>.*?</t{2,}s>", source, flags=re.IGNORECASE | re.DOTALL):
            outside = re.sub(r"<t{2,}s\b[^>]*>.*?</t{2,}s>", "", source, flags=re.IGNORECASE | re.DOTALL)
            outside = re.sub(r"</?t{2,}s\b[^>]*>", "", outside, flags=re.IGNORECASE).strip()
            if re.search(r"[\u4e00-\u9fff]", outside):
                source = outside
            else:
                source = re.sub(r"</?t{2,}s\b[^>]*>", "", source, flags=re.IGNORECASE)
        if re.search(r"[\u3040-\u30ff]", source) and re.search(r"[\u4e00-\u9fff]", source):
            units = re.findall(r".*?[。！？!?…~～]+|.+$", source, flags=re.DOTALL)
            kept = [unit.strip() for unit in units if unit.strip() and not re.search(r"[\u3040-\u30ff]", unit)]
            if kept and any(re.search(r"[\u4e00-\u9fff]", item) for item in kept):
                source = "".join(kept)
        return cls._single_line(_strip_internal_message_blocks(source), limit)

    def _group_wakeup_runtime(self, group: dict[str, Any]) -> dict[str, Any]:
        fatigue = group.get("group_wakeup_fatigue") if isinstance(group.get("group_wakeup_fatigue"), dict) else {}
        high_intensity = {}
        if hasattr(self.plugin, "_group_high_intensity_state"):
            try:
                high_intensity = self.plugin._group_high_intensity_state(group, mutate=False)
            except Exception:
                high_intensity = {}
        value = self._float(fatigue.get("value"))
        limit = self._int(fatigue.get("limit")) or int(getattr(self.plugin, "group_wakeup_fatigue_limit", 5) or 5)
        ratio = max(0.0, min(1.0, value / max(1, limit)))
        if ratio >= 1.0:
            label = "疲劳高"
            level = "high"
        elif ratio >= 0.55:
            label = "有点累"
            level = "medium"
        elif value >= 0.4:
            label = "轻微"
            level = "low"
        else:
            label = "无"
            level = "none"
        return {
            "value": round(value, 2),
            "limit": limit,
            "ratio": round(ratio, 3),
            "label": label,
            "level": level,
            "updated": self.plugin._format_timestamp_elapsed(fatigue.get("updated_ts", 0)),
            "high_intensity": {
                "active": bool(high_intensity.get("active")) if isinstance(high_intensity, dict) else False,
                "reason": self._single_line(high_intensity.get("reason"), 40) if isinstance(high_intensity, dict) else "",
                "recent_wakeups": self._int(high_intensity.get("recent_wakeups")) if isinstance(high_intensity, dict) else 0,
                "threshold": self._int(high_intensity.get("threshold")) if isinstance(high_intensity, dict) else 0,
                "remaining_seconds": self._float(high_intensity.get("remaining_seconds")) if isinstance(high_intensity, dict) else 0.0,
                "merge_seconds": self._float(getattr(self.plugin, "group_high_intensity_merge_seconds", 8)),
                "max_merge_messages": self._int(getattr(self.plugin, "group_high_intensity_max_merge_messages", 8)),
            },
        }

    def _group_wakeup_logs(self, group: dict[str, Any], limit: int = 30) -> list[dict[str, Any]]:
        logs = group.get("group_wakeup_logs") if isinstance(group.get("group_wakeup_logs"), list) else []
        items: list[dict[str, Any]] = []
        for raw in reversed(logs[-limit:]):
            if not isinstance(raw, dict):
                continue
            items.append(
                {
                    "ts": self._float(raw.get("ts")),
                    "time": self.plugin._format_timestamp_elapsed(raw.get("ts", 0)),
                    "result": self._single_line(raw.get("result"), 32),
                    "type": self._single_line(raw.get("type"), 40),
                    "word": self._single_line(raw.get("word"), 60),
                    "strength": self._single_line(raw.get("strength"), 24),
                    "strength_label": self._single_line(raw.get("strength_label"), 24),
                    "probability": round(self._float(raw.get("probability")), 3),
                    "reason": self._single_line(raw.get("reason"), 80),
                    "topic_weight": raw.get("topic_weight") if isinstance(raw.get("topic_weight"), dict) else {},
                    "note": self._single_line(raw.get("note"), 180),
                    "sender_id": self._single_line(raw.get("sender_id"), 40),
                    "sender_name": self._single_line(raw.get("sender_name"), 40),
                    "text": self._display_message_text(raw.get("text"), 160),
                    "fatigue_value": round(self._float(raw.get("fatigue_value")), 2),
                    "fatigue_label": self._single_line(raw.get("fatigue_label"), 20),
                }
            )
        return items

    def _group_summary(self, group_id: str, group: dict[str, Any]) -> dict[str, Any]:
        atmosphere = group.get("atmosphere") if isinstance(group.get("atmosphere"), dict) else {}
        slang_terms = group.get("slang_terms") if isinstance(group.get("slang_terms"), list) else []
        cleaner = getattr(self.plugin, "_cleanup_group_slang_terms", None)
        if callable(cleaner):
            try:
                group_for_filter = deepcopy(group)
                if cleaner(group_for_filter):
                    slang_terms = group_for_filter.get("slang_terms") if isinstance(group_for_filter.get("slang_terms"), list) else []
            except Exception:
                pass
        members = group.get("members") if isinstance(group.get("members"), dict) else {}
        identity_count = sum(1 for item in members.values() if isinstance(item, dict) and item.get("identity_known"))
        wakeup_logs = group.get("group_wakeup_logs") if isinstance(group.get("group_wakeup_logs"), list) else []
        last_wakeup = group.get("last_group_wakeup") if isinstance(group.get("last_group_wakeup"), dict) else {}
        last_interjection = self._sanitize_last_bot_interjection(group.get("last_bot_interjection"))
        return {
            "group_id": str(group_id),
            "enabled": bool(group.get("enabled", True)),
            "allowed_by_mode": self.plugin._group_allowed_by_access_mode(str(group_id)),
            "message_count": group.get("message_count", 0),
            "last_seen_ts": group.get("last_seen", 0),
            "last_seen": self.plugin._format_timestamp_elapsed(group.get("last_seen", 0)),
            "member_count": len(members),
            "recognized_member_count": identity_count,
            "recent_message_count": len(group.get("recent_messages") or []),
            "slang_count": len(slang_terms),
            "slang_terms": slang_terms[:16],
            "topic_count": len(group.get("topic_threads") or []),
            "episode_count": len(group.get("group_episodes") or []),
            "relationship_edge_count": len(group.get("relationship_edges") or {}),
            "interject_today": group.get("interject_today", 0),
            "last_interject": self.plugin._format_timestamp_elapsed(group.get("last_interject_at", 0)),
            "last_bot_interjection": last_interjection,
            "wakeup_log_count": len(wakeup_logs),
            "wakeup_fatigue": self._group_wakeup_runtime(group),
            "last_group_wakeup": {
                "time": self.plugin._format_timestamp_elapsed(last_wakeup.get("ts", 0)),
                "type": self._single_line(last_wakeup.get("type"), 40),
                "word": self._single_line(last_wakeup.get("word"), 60),
                "strength_label": self._single_line(last_wakeup.get("strength_label"), 24),
                "sender_name": self._single_line(last_wakeup.get("sender_name"), 40),
                "text": self._display_message_text(last_wakeup.get("text"), 120),
            } if last_wakeup else {},
            "atmosphere": {
                "mood": atmosphere.get("mood", ""),
                "heat": atmosphere.get("heat", ""),
                "last_summary": atmosphere.get("summary", ""),
            },
        }

    def _sanitize_last_bot_interjection(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict) or not value:
            return {}
        item = dict(value)
        item["text"] = self._display_message_text(item.get("text"), 120)
        if not item["text"] and not item.get("has_image"):
            return {}
        return item

    def _group_topic_thread_items(self, group: dict[str, Any], limit: int = 16) -> list[dict[str, Any]]:
        threads = group.get("topic_threads") if isinstance(group.get("topic_threads"), list) else []
        members = group.get("members") if isinstance(group.get("members"), dict) else {}
        now = time.time()
        items: list[dict[str, Any]] = []
        for index, raw in enumerate(threads[:limit]):
            if not isinstance(raw, dict):
                continue
            started_ts = self._float(raw.get("started_ts"))
            last_ts = self._float(raw.get("last_ts"))
            duration_seconds = max(0.0, (last_ts or started_ts) - started_ts) if started_ts else 0.0
            participants = raw.get("participants") if isinstance(raw.get("participants"), list) else []
            participant_items = []
            for user_id in participants[:8]:
                uid = self._single_line(user_id, 40)
                member = members.get(uid) if isinstance(members.get(uid), dict) else {}
                name = self._single_line(
                    member.get("display_name")
                    or member.get("nickname")
                    or member.get("name")
                    or member.get("card")
                    or uid,
                    24,
                )
                if uid:
                    participant_items.append({"id": uid, "name": name or uid})
            examples = []
            for example in (raw.get("recent_examples") if isinstance(raw.get("recent_examples"), list) else [])[-4:]:
                if not isinstance(example, dict):
                    continue
                examples.append(
                    {
                        "name": self._single_line(example.get("name"), 24),
                        "text": self._single_line(example.get("text"), 120),
                        "time": self.plugin._format_timestamp_elapsed(example.get("ts", 0)),
                    }
                )
            message_count = self._int(raw.get("message_count"))
            freshness = max(0.0, now - last_ts) if last_ts else 0.0
            heat = min(100, max(8, message_count * 10 + len(participant_items) * 8 - int(freshness / 600) * 5))
            status = "活跃" if freshness <= 15 * 60 else "刚冷却" if freshness <= 90 * 60 else "历史"
            title = self._single_line(raw.get("title") or raw.get("topic") or raw.get("summary"), 80)
            items.append(
                {
                    "rank": index + 1,
                    "title": title or "未命名话题",
                    "summary": self._single_line(raw.get("summary"), 180),
                    "message_count": message_count,
                    "participant_count": len(participants),
                    "participants": participant_items,
                    "recent_examples": examples,
                    "started": self.plugin._format_timestamp_elapsed(started_ts),
                    "last_seen": self.plugin._format_timestamp_elapsed(last_ts),
                    "duration": self._format_duration(duration_seconds),
                    "heat": heat,
                    "status": status,
                    "bot_joined": bool(raw.get("bot_joined")),
                }
            )
        return items

    @staticmethod
    def _format_duration(seconds: float) -> str:
        seconds = max(0, int(seconds or 0))
        if seconds < 60:
            return "不到 1 分钟"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes} 分钟"
        hours = minutes // 60
        rest = minutes % 60
        return f"{hours} 小时 {rest} 分钟" if rest else f"{hours} 小时"

    def _skill_growth_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        state = data.get("skill_growth") if isinstance(data.get("skill_growth"), dict) else {}
        skills = state.get("skills") if isinstance(state.get("skills"), dict) else {}
        items: list[dict[str, Any]] = []
        for raw in skills.values():
            if not isinstance(raw, dict):
                continue
            level = self._int(raw.get("level")) or 1
            exp = self._float(raw.get("exp"))
            next_exp = self.plugin._skill_next_exp(level) if hasattr(self.plugin, "_skill_next_exp") else None
            prev_exp = {1: 0, 2: 100, 3: 260, 4: 520, 5: 900, 6: 1400}.get(level, 0)
            if next_exp:
                progress = max(0, min(100, int(((exp - prev_exp) / max(1, next_exp - prev_exp)) * 100)))
            else:
                progress = 100
            logs = raw.get("recent_logs") if isinstance(raw.get("recent_logs"), list) else []
            keywords = raw.get("keywords") if isinstance(raw.get("keywords"), list) else []
            aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
            items.append(
                {
                    "id": self._single_line(raw.get("id"), 32),
                    "name": self._single_line(raw.get("name"), 32),
                    "category": self._single_line(raw.get("category"), 24),
                    "keywords": [self._single_line(item, 24) for item in keywords if self._single_line(item, 24)][:16],
                    "aliases": [self._single_line(item, 24) for item in aliases if self._single_line(item, 24)][:12],
                    "hidden": bool(raw.get("hidden")),
                    "frozen": bool(raw.get("frozen")),
                    "level": level,
                    "level_title": self.plugin._skill_level_title(level) if hasattr(self.plugin, "_skill_level_title") else self._single_line(raw.get("level_title"), 24),
                    "description": self.plugin._skill_level_description(level) if hasattr(self.plugin, "_skill_level_description") else "",
                    "exp": round(exp, 2),
                    "next_exp": next_exp,
                    "progress": progress,
                    "training_count": self._int(raw.get("training_count")),
                    "last_trained": self.plugin._format_timestamp_elapsed(raw.get("last_trained_ts", 0)),
                    "recent_logs": [
                        {
                            "activity": self._single_line(log.get("activity"), 80),
                            "exp": self._float(log.get("exp")),
                            "time": self.plugin._format_timestamp_elapsed(log.get("ts", 0)),
                            "level_up": bool(log.get("level_up")),
                        }
                        for log in logs[-4:]
                        if isinstance(log, dict)
                    ],
                }
            )
        items.sort(key=lambda item: (bool(item.get("hidden")), -item["level"], -item["exp"], -item["training_count"], item.get("category") or "", item.get("name") or ""))
        return {
            "enabled": bool(getattr(self.plugin, "enable_skill_growth_simulation", False)),
            "rate": float(getattr(self.plugin, "skill_growth_rate", 1.0) or 1.0),
            "passive_injection": bool(getattr(self.plugin, "enable_skill_growth_passive_injection", False)),
            "schedule_influence": bool(getattr(self.plugin, "enable_skill_growth_schedule_influence", False)),
            "schedule_influence_strength": float(getattr(self.plugin, "skill_growth_schedule_influence_strength", 0.35) or 0.0),
            "updated": self.plugin._format_timestamp_elapsed(state.get("updated_ts", 0)),
            "skill_count": len(items),
            "hidden_count": sum(1 for item in items if item.get("hidden")),
            "frozen_count": sum(1 for item in items if item.get("frozen")),
            "items": items[:120],
        }

    def _external_ability_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        runtime_getter = getattr(self.plugin, "external_proactive_abilities", None)
        if callable(runtime_getter):
            raw_items = runtime_getter()
        else:
            store = data.get("external_proactive_abilities") if isinstance(data.get("external_proactive_abilities"), dict) else {}
            raw_items = list(store.values()) if isinstance(store, dict) else []
        items: list[dict[str, Any]] = []
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            config = raw.get("config") if isinstance(raw.get("config"), dict) else {}
            schema = raw.get("config_schema") if isinstance(raw.get("config_schema"), dict) else {}
            items.append(
                {
                    "name": self._single_line(raw.get("name"), 64),
                    "module": self._single_line(raw.get("module"), 24) or "外部主动能力",
                    "label": self._single_line(raw.get("label"), 32) or self._single_line(raw.get("name"), 64),
                    "description": self._single_line(raw.get("description"), 180),
                    "when": self._single_line(raw.get("when"), 140),
                    "use_for": self._single_line(raw.get("use_for"), 140),
                    "avoid": self._single_line(raw.get("avoid"), 140),
                    "enabled": bool(raw.get("enabled")),
                    "available": bool(raw.get("available")),
                    "registered": bool(raw.get("registered")),
                    "share_probability": max(0.0, min(1.0, self._float(raw.get("share_probability")))),
                    "min_interval_hours": max(0.0, self._float(raw.get("min_interval_hours"))),
                    "config": config,
                    "config_schema": schema,
                    "last_executed": self.plugin._format_timestamp_elapsed(raw.get("last_executed_ts", 0)),
                    "last_status": self._single_line(raw.get("last_status"), 160),
                    "last_summary": self._single_line(raw.get("last_summary"), 160),
                    "success_count": self._int(raw.get("success_count")),
                    "failure_count": self._int(raw.get("failure_count")),
                    "updated": self.plugin._format_timestamp_elapsed(raw.get("updated_ts", 0)),
                }
            )
        items.sort(key=lambda item: (not item["enabled"], not item["available"], item["module"], item["label"]))
        return {
            "total": len(items),
            "enabled_count": sum(1 for item in items if item["enabled"]),
            "available_count": sum(1 for item in items if item["available"]),
            "items": items,
        }

    def _feature_flags(self) -> dict[str, bool]:
        keys = [
            "enable_proactive_only_mode",
            "enable_mai_style_integration",
            "enable_companion_memory",
            "enable_expression_learning",
            "enable_companion_reply_planner",
            "enable_intent_emotion_analysis",
            "enable_response_self_review",
            "enable_llm_timer_scheduling",
            "enable_passive_topic_suppression",
            "enable_relationship_state_machine",
            "enable_emotion_simulation",
            "enable_dialogue_episode_memory",
            "enable_open_loop_tracking",
            "enable_user_habit_learning",
            "enable_humanized_states",
            "enable_segmented_proactive_reply",
            "enable_proactive_quote_trigger_message",
            "enable_photo_text_action",
            "inject_passive_states",
            "enable_cycle_state",
            "enable_skill_growth_simulation",
            "enable_skill_growth_passive_injection",
            "enable_message_debounce",
            "enable_smart_message_debounce",
            "enable_recall_enhancement",
            "enable_recall_cancel_reply",
            "enable_recall_message_cache",
            "enable_recall_transcribe_command",
            "enable_forbidden_word_recall",
            "enable_semantic_message_debounce",
            "enable_environment_perception",
            "enable_holiday_perception",
            "enable_platform_perception",
            "enable_model_perception",
            "enable_worldview_perception",
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "enable_group_companion",
            "enable_group_slang_learning",
            "enable_group_member_profiles",
            "enable_group_context_injection",
            "enable_group_persona_denoise",
            "enable_forward_message_adaptation",
            "enable_group_scene_awareness",
            "enable_group_reality_promise_guard",
            "enable_group_wakeup_enhancement",
            "enable_group_high_intensity_mode",
            "enable_private_image_self_recognition",
            "enable_private_image_gif_enhancement",
            "enable_group_conversation_followup",
            "enable_group_interjection",
            "enable_group_repeat_follow",
            "group_repeat_count_distinct_users_only",
            "enable_group_topic_threads",
            "enable_group_episode_memory",
            "enable_group_interjection_feedback",
            "enable_group_slang_meanings",
            "enable_group_slang_web_search",
            "enable_group_relationship_graph",
            "enable_group_privacy_guard",
            "enable_worldbook_member_recognition",
            "enable_atrelay_tools",
            "enable_livingmemory_integration",
            "enable_bilibili_integration",
            "enable_bilibili_boredom_watch",
            "enable_news_integration",
            "enable_news_daily_hot_read",
            "enable_news_boredom_read",
            "enable_ai_daily_watch",
            "enable_external_event_self_link",
            "enable_web_exploration",
            "enable_web_exploration_boredom_search",
            "enable_qzone_integration",
            "enable_qzone_life_publish",
            "enable_qzone_emotional_vent_publish",
            "enable_private_reading_integration",
            "enable_private_reading_boredom_read",
            "enable_private_reading_ask_recommendation",
            "enable_private_reading_preference_influence",
            "enable_unanswered_screen_peek_followup",
            "enable_yesterday_screen_diary_context",
            "enable_tts_enhancement",
            "enable_creative_writing",
            "creative_hidden_mode",
        ]
        values = {key: bool(getattr(self.plugin, key, False)) for key in keys}
        try:
            livingmemory_available = bool(getattr(self.plugin, "_livingmemory_available", lambda: False)())
        except Exception:
            livingmemory_available = False
        try:
            bilibili_available = bool(getattr(self.plugin, "_bilibili_available", lambda: False)())
        except Exception:
            bilibili_available = False
        try:
            qzone_available = bool(getattr(self.plugin, "_qzone_available", lambda: False)())
        except Exception:
            qzone_available = False
        try:
            screen_companion_available = bool(self._screen_companion_available())
        except Exception:
            screen_companion_available = False
        try:
            private_reading_available = bool(getattr(self.plugin, "_jm_cosmos_available", lambda: False)())
        except Exception:
            private_reading_available = False
        values["enable_livingmemory_integration"] = bool(livingmemory_available and getattr(self.plugin, "enable_livingmemory_integration", False))
        values["enable_bilibili_integration"] = bool(bilibili_available and getattr(self.plugin, "enable_bilibili_integration", False))
        values["enable_bilibili_boredom_watch"] = bool(bilibili_available and getattr(self.plugin, "enable_bilibili_boredom_watch", False))
        values["enable_qzone_integration"] = bool(qzone_available and getattr(self.plugin, "enable_qzone_integration", False))
        values["enable_qzone_life_publish"] = bool(qzone_available and getattr(self.plugin, "enable_qzone_life_publish", False))
        values["enable_qzone_emotional_vent_publish"] = bool(
            qzone_available
            and getattr(self.plugin, "enable_emotion_simulation", False)
            and getattr(self.plugin, "enable_qzone_emotional_vent_publish", False)
        )
        values["enable_yesterday_screen_diary_context"] = bool(screen_companion_available and getattr(self.plugin, "enable_yesterday_screen_diary_context", False))
        values["enable_private_reading_integration"] = bool(private_reading_available and getattr(self.plugin, "enable_jm_cosmos_integration", False))
        values["enable_private_reading_boredom_read"] = bool(private_reading_available and getattr(self.plugin, "enable_jm_cosmos_boredom_read", False))
        values["enable_private_reading_ask_recommendation"] = bool(private_reading_available and getattr(self.plugin, "enable_private_reading_ask_recommendation", False))
        values["enable_private_reading_preference_influence"] = bool(private_reading_available and getattr(self.plugin, "enable_private_reading_preference_influence", True))
        return values

    def _provider_settings(self) -> dict[str, str]:
        keys = [
            "LLM_PROVIDER_ID",
            "MAI_STYLE_PROVIDER_ID",
            "DAILY_PLAN_PROVIDER_ID",
            "DETAIL_ENHANCEMENT_PROVIDER_ID",
            "DREAM_DIARY_PROVIDER_ID",
            "CREATIVE_PROVIDER_ID",
            "VOICE_PROMPT_PROVIDER_ID",
            "PHOTO_PROMPT_PROVIDER_ID",
            "NARRATION_PROVIDER_ID",
            "HISTORY_SUMMARY_PROVIDER_ID",
            "RESPONSE_REVIEW_PROVIDER_ID",
            "TROUBLESHOOTING_PROVIDER_ID",
            "RELATIONSHIP_ANALYSIS_PROVIDER_ID",
            "COMPANION_MEMORY_PROVIDER_ID",
            "DIALOGUE_EPISODE_PROVIDER_ID",
            "GROUP_INTERJECT_PROVIDER_ID",
            "GROUP_EPISODE_PROVIDER_ID",
            "GROUP_SLANG_PROVIDER_ID",
            "GROUP_FOLLOWUP_JUDGE_PROVIDER_ID",
            "FORWARD_MESSAGE_PROVIDER_ID",
            "PLUGIN_VISION_PROVIDER_ID",
            "PRIVATE_READING_VISION_PROVIDER_ID",
            "NEWS_PROVIDER_ID",
            "WEB_EXPLORATION_PROVIDER_ID",
        ]
        values = {key: self._config_get(key) for key in keys}
        if not values.get("PLUGIN_VISION_PROVIDER_ID"):
            values["PLUGIN_VISION_PROVIDER_ID"] = str(getattr(self.plugin, "plugin_vision_provider_id", "") or "")
        if not values.get("PRIVATE_READING_VISION_PROVIDER_ID"):
            values["PRIVATE_READING_VISION_PROVIDER_ID"] = str(getattr(self.plugin, "jm_cosmos_vision_provider_id", "") or "")
        if not values.get("DREAM_DIARY_PROVIDER_ID"):
            values["DREAM_DIARY_PROVIDER_ID"] = str(getattr(self.plugin, "dream_diary_provider_id", "") or "")
        return values

    def _available_provider_items(self) -> list[dict[str, Any]]:
        providers: list[Any] = []
        context = getattr(self.plugin, "context", None)
        get_all = getattr(context, "get_all_providers", None)
        if callable(get_all):
            try:
                providers = list(get_all() or [])
            except Exception:
                providers = []
        if not providers:
            manager = getattr(context, "provider_manager", None)
            inst_map = getattr(manager, "inst_map", None)
            if isinstance(inst_map, dict):
                providers = list(inst_map.values())

        using_id = ""
        get_using = getattr(context, "get_using_provider", None)
        if callable(get_using):
            try:
                using_id = self._provider_id(get_using())
            except Exception:
                using_id = ""

        items: list[dict[str, str]] = []
        seen: set[str] = set()
        for provider in providers:
            provider_id = self._provider_id(provider)
            if not provider_id or provider_id in seen:
                continue
            seen.add(provider_id)
            items.append(
                {
                    "id": provider_id,
                    "name": self._provider_name(provider, provider_id),
                    "type": self._provider_type(provider),
                    "model": self._provider_model(provider),
                    "is_default": provider_id == using_id,
                }
            )
        items.sort(key=lambda item: (not item["is_default"], item["name"].lower(), item["id"].lower()))
        return items

    @staticmethod
    def _provider_config(provider: Any) -> Any:
        return getattr(provider, "provider_config", None) or getattr(provider, "config", None) or {}

    @classmethod
    def _provider_config_value(cls, provider: Any, *keys: str) -> str:
        config = cls._provider_config(provider)
        for key in keys:
            value = ""
            if isinstance(config, dict):
                value = str(config.get(key, "") or "")
            else:
                value = str(getattr(config, key, "") or "")
            if value:
                return value.strip()
        return ""

    @classmethod
    def _provider_id(cls, provider: Any) -> str:
        if provider is None:
            return ""
        return (
            cls._provider_config_value(provider, "id", "provider_id")
            or str(getattr(provider, "provider_id", "") or "").strip()
            or str(getattr(provider, "id", "") or "").strip()
        )

    @classmethod
    def _provider_name(cls, provider: Any, provider_id: str) -> str:
        return (
            cls._provider_config_value(provider, "name", "display_name", "provider")
            or str(getattr(provider, "name", "") or "").strip()
            or provider_id
        )

    @classmethod
    def _provider_model(cls, provider: Any) -> str:
        return cls._provider_config_value(provider, "model", "model_name", "api_model", "model_id")

    @classmethod
    def _provider_type(cls, provider: Any) -> str:
        return (
            cls._provider_config_value(provider, "type", "provider_type")
            or provider.__class__.__name__
        )

    def _runtime_settings(self) -> dict[str, Any]:
        keys = [
            "bot_name",
            "plugin_specific_persona_id",
            "target_user_ids",
            "private_user_aliases",
            "target_platform",
            "environment_perception_timezone",
            "holiday_country",
            "enable_environment_perception",
            "enable_holiday_perception",
            "enable_platform_perception",
            "enable_model_perception",
            "enable_worldview_perception",
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "default_nickname",
            "default_style",
            "enable_llm_timer_scheduling",
            "schedule_persona_prompt",
            "schedule_worldview_prompt",
            "roleplay_user_profile_prompt",
            "roleplay_knowledge_source_ids",
            "worldview_adaptation_mode",
            "worldview_adaptation_prompt",
            "quiet_hours",
            "passive_topic_memory_hours",
            "tts_generation_mode",
            "tts_voice_language",
            "tts_conversion_provider_id",
            "tts_extra_prompt",
            "tts_frequency_control_mode",
            "tts_constraint_mode",
            "tts_session_min_interval_seconds",
            "tts_private_min_interval_seconds",
            "tts_group_min_interval_seconds",
            "tts_trigger_probability",
            "tts_private_trigger_probability",
            "tts_group_trigger_probability",
            "enable_tts_local_playback",
            "enable_tts_local_playback_live_only",
            "enable_tts_live_subtitle_sync",
            "tts_live_subtitle_url",
            "tts_local_playback_min_interval_seconds",
            "auto_voice_enabled",
            "auto_voice_full_conversion_enabled",
            "auto_voice_probability",
            "auto_voice_max_chars",
            "auto_voice_cooldown_seconds",
            "main_user_voice_probability",
            "main_user_mention_voice_keywords",
            "main_user_mention_voice_probability",
            "main_user_mention_voice_prompt",
            "daily_token_limit",
            "enable_daily_token_soft_limit",
            "daily_token_soft_limit",
            "humanized_state_intensity",
            "enable_rest_reply_simulation",
            "rest_reply_mode",
            "rest_reply_probability",
            "rest_reply_llm_threshold",
            "REST_WAKEUP_PROVIDER_ID",
            "check_interval_seconds",
            "idle_minutes",
            "min_interval_minutes",
            "max_daily_messages",
            "inbound_message_debounce_seconds",
            "enable_message_debounce",
            "enable_smart_message_debounce",
            "SMART_MESSAGE_DEBOUNCE_PROVIDER_ID",
            "smart_message_debounce_model_timeout_seconds",
            "smart_message_debounce_wait_seconds",
            "smart_message_debounce_learning_window_seconds",
            "smart_message_debounce_examples_limit",
            "enable_recall_enhancement",
            "enable_recall_cancel_reply",
            "enable_recall_message_cache",
            "enable_recall_transcribe_command",
            "recall_message_cache_ttl_seconds",
            "recall_message_cache_max_items",
            "enable_forbidden_word_recall",
            "recall_forbidden_words",
            "recall_forbidden_scope",
            "recall_forbidden_word_case_sensitive",
            "text_message_debounce_seconds",
            "image_message_debounce_seconds",
            "forward_message_debounce_seconds",
            "text_message_debounce_max_wait_seconds",
            "message_debounce_max_merge_messages",
            "enable_semantic_message_debounce",
            "semantic_message_debounce_seconds",
            "enable_proactive_quote_trigger_message",
            "enable_photo_text_action",
            "photo_action_max_daily",
            "photo_generation_backend",
            "COMFYUI_TEXT2IMG_WORKFLOW_NAME",
            "COMFYUI_SELFIE_WORKFLOW_NAME",
            "comfyui_photo_wait_seconds",
            "enable_local_photo_load_guard",
            "local_photo_cpu_busy_percent",
            "local_photo_memory_busy_percent",
            "local_photo_defer_minutes",
            "EXTERNAL_IMAGE_API_BASE_URL",
            "EXTERNAL_IMAGE_API_MODEL",
            "external_image_api_size",
            "external_image_api_timeout_seconds",
            "photo_generation_style",
            "photo_generation_style_custom_prompt",
            "private_image_vision_wait_seconds",
            "enable_private_image_gif_enhancement",
            "private_image_gif_max_frames",
            "enable_private_image_self_recognition",
            "private_image_self_recognition_hint",
            "enable_private_image_vision_cache",
            "private_image_vision_cache_max_items",
            "screen_diary_context_max_chars",
            "enable_segmented_proactive_reply",
            "segmented_proactive_scope",
            "segmented_proactive_chat_scope",
            "segmented_proactive_threshold",
            "segmented_proactive_min_segment_chars",
            "segmented_proactive_max_segments",
            "segmented_proactive_send_as_forward",
            "segmented_proactive_split_mode",
            "segmented_proactive_regex",
            "segmented_proactive_split_words",
            "enable_segmented_proactive_content_cleanup",
            "segmented_proactive_content_cleanup_scope",
            "segmented_proactive_content_cleanup_rule",
            "segmented_proactive_content_cleanup_words",
            "segmented_proactive_interval_method",
            "segmented_proactive_interval_min",
            "segmented_proactive_interval_max",
            "segmented_proactive_log_base",
            "group_conversation_followup_seconds",
            "group_conversation_followup_max_turns",
            "enable_group_conversation_followup",
            "enable_group_repeat_follow",
            "group_repeat_trigger_threshold",
            "group_repeat_count_distinct_users_only",
            "group_interject_min_interval_minutes",
            "group_interject_max_daily",
            "group_repeat_follow_probability",
            "group_repeat_interrupt_probability",
            "group_repeat_interrupt_probability_step",
            "group_repeat_interrupt_text",
            "group_repeat_interrupt_image_path",
            "group_scene_recent_limit",
            "enable_group_reality_promise_guard",
            "group_wakeup_direct_words",
            "group_wakeup_context_words",
            "group_wakeup_interest_keywords",
            "group_wakeup_interest_probability",
            "group_wakeup_cooldown_seconds",
            "group_wakeup_generated_keyword_limit",
            "group_wakeup_topic_interest_max_boost",
            "group_wakeup_debounce_pending_penalty",
            "group_wakeup_fatigue_limit",
            "group_wakeup_fatigue_decay_minutes",
            "group_wakeup_log_limit",
            "enable_group_high_intensity_mode",
            "group_high_intensity_wakeup_window_seconds",
            "group_high_intensity_wakeup_threshold",
            "group_high_intensity_cooldown_seconds",
            "group_high_intensity_merge_seconds",
            "group_high_intensity_max_merge_messages",
            "enable_forward_message_adaptation",
            "forward_message_mode",
            "forward_message_max_messages",
            "forward_message_max_chars",
            "forward_message_parse_nested",
            "forward_message_image_vision",
            "forward_message_image_limit",
            "enable_recall_cancel_reply",
            "enable_recall_message_cache",
            "enable_recall_transcribe_command",
            "recall_message_cache_ttl_seconds",
            "recall_message_cache_max_items",
            "enable_forbidden_word_recall",
            "recall_forbidden_words",
            "recall_forbidden_scope",
            "recall_forbidden_word_case_sensitive",
            "screen_diary_context_max_chars",
            "max_group_recent_messages",
            "max_group_slang_terms",
            "group_slang_web_search_terms",
            "group_slang_web_search_results",
            "memory_refresh_interval_minutes",
            "episode_memory_refresh_messages",
            "episode_memory_refresh_minutes",
            "max_companion_memory_items",
            "max_learned_expression_items",
            "max_dialogue_episodes",
            "user_habit_min_count",
            "user_habit_max_items",
            "emotional_gate_hurt_threshold",
            "emotional_gate_refuse_threshold",
            "emotional_gate_recovery_per_hour",
            "emotional_gate_max_hurt_minutes",
            "enable_skill_growth_simulation",
            "skill_growth_rate",
            "skill_growth_custom_skills",
            "enable_skill_growth_passive_injection",
            "enable_skill_growth_schedule_influence",
            "skill_growth_schedule_influence_strength",
            "enable_bilibili_integration",
            "enable_bilibili_boredom_watch",
            "bilibili_boredom_min_interval_hours",
            "bilibili_share_probability",
            "bilibili_share_min_score",
            "enable_news_integration",
            "enable_news_boredom_read",
            "enable_news_daily_hot_read",
            "enable_ai_daily_watch",
            "enable_external_event_self_link",
            "news_min_interval_hours",
            "news_share_probability",
            "external_event_self_link_probability",
            "external_event_self_link_cooldown_hours",
            "news_max_items_per_source",
            "news_sources",
            "news_hot_sources",
            "news_hot_max_items",
            "enable_web_exploration",
            "enable_web_exploration_boredom_search",
            "web_exploration_min_interval_hours",
            "web_exploration_share_probability",
            "web_exploration_max_results",
            "web_exploration_interests",
            "enable_qzone_integration",
            "QZONE_COOKIE",
            "enable_qzone_life_publish",
            "qzone_life_publish_min_interval_hours",
            "qzone_life_publish_probability",
            "enable_qzone_emotional_vent_publish",
            "qzone_emotional_vent_threshold",
            "qzone_emotional_vent_cooldown_hours",
            "qzone_emotional_vent_probability",
            "enable_private_reading_integration",
            "enable_private_reading_boredom_read",
            "enable_private_reading_ask_recommendation",
            "enable_private_reading_preference_influence",
            "enable_unanswered_screen_peek_followup",
            "unanswered_screen_peek_after_minutes",
            "unanswered_screen_peek_cooldown_minutes",
            "private_reading_min_interval_hours",
            "private_reading_max_photo_count",
            "private_reading_share_probability",
            "private_reading_ask_probability",
            "private_reading_preference_min_ratings",
            "private_reading_preference_max_terms",
            "private_reading_default_keywords",
            "private_reading_blocked_tags",
            "enable_unanswered_screen_peek_followup",
            "unanswered_screen_peek_after_minutes",
            "unanswered_screen_peek_cooldown_minutes",
            "enable_creative_writing",
            "creative_inspiration_probability",
            "creative_share_probability",
            "creative_chars_per_session",
            "creative_max_active_projects",
            "creative_hidden_mode",
            "enable_worldbook_member_recognition",
            "worldbook_auto_import",
            "worldbook_member_match_aliases",
            "worldbook_self_registration",
            "worldbook_auto_pending_observations",
            "worldbook_member_inject_limit",
            "worldbook_config_paths",
            "enable_atrelay_tools",
            "atrelay_require_worldbook_first",
            "atrelay_member_cache_minutes",
            "atrelay_sensitive_confirm",
            "atrelay_default_relay_style",
            "atrelay_multi_target_limit",
        ]
        values = {key: getattr(self.plugin, key, self._config_get(key)) for key in keys}
        values["private_user_aliases"] = self._config_get("private_user_aliases")
        values.update(
            {
                "enable_private_reading_integration": bool(getattr(self.plugin, "enable_jm_cosmos_integration", False)),
                "enable_private_reading_boredom_read": bool(getattr(self.plugin, "enable_jm_cosmos_boredom_read", False)),
                "enable_private_reading_ask_recommendation": bool(getattr(self.plugin, "enable_private_reading_ask_recommendation", False)),
                "enable_private_reading_preference_influence": bool(getattr(self.plugin, "enable_private_reading_preference_influence", True)),
                "private_reading_min_interval_hours": getattr(self.plugin, "jm_cosmos_min_interval_hours", 18),
                "private_reading_max_photo_count": getattr(self.plugin, "jm_cosmos_max_photo_count", 60),
                "private_reading_share_probability": getattr(self.plugin, "jm_cosmos_share_probability", 0.18),
                "private_reading_ask_probability": getattr(self.plugin, "private_reading_ask_probability", 0.16),
                "private_reading_preference_min_ratings": getattr(self.plugin, "private_reading_preference_min_ratings", 5),
                "private_reading_preference_max_terms": getattr(self.plugin, "private_reading_preference_max_terms", 8),
                "private_reading_default_keywords": getattr(self.plugin, "jm_cosmos_default_keywords", ""),
                "private_reading_blocked_tags": getattr(self.plugin, "private_reading_blocked_tags", "連載中,長篇,青年漫"),
                "group_repeat_trigger_threshold": int(getattr(self.plugin, "group_repeat_trigger_threshold", 4) or 4),
                "group_repeat_count_distinct_users_only": bool(getattr(self.plugin, "group_repeat_count_distinct_users_only", False)),
                "group_repeat_follow_probability": int(round(float(getattr(self.plugin, "group_repeat_follow_probability", 0.18) or 0) * 100)),
                "group_repeat_interrupt_probability": int(round(float(getattr(self.plugin, "group_repeat_interrupt_probability", 0.10) or 0) * 100)),
                "group_repeat_interrupt_probability_step": int(round(float(getattr(self.plugin, "group_repeat_interrupt_probability_step", 0.12) or 0) * 100)),
            }
        )
        def _percent_attr(name: str, default: float = 0.0, *, inherit: bool = False) -> int:
            try:
                raw = float(getattr(self.plugin, name, default) or 0.0)
            except (TypeError, ValueError):
                raw = default
            if inherit and raw < 0:
                return -1
            if raw <= 1:
                raw *= 100
            return max(-1 if inherit else 0, min(100, int(round(raw))))

        values.update(
            {
                "tts_trigger_probability": _percent_attr("tts_trigger_probability", 0.2),
                "tts_private_trigger_probability": _percent_attr("tts_private_trigger_probability", -0.01, inherit=True),
                "tts_group_trigger_probability": _percent_attr("tts_group_trigger_probability", -0.01, inherit=True),
                "auto_voice_probability": _percent_attr("auto_voice_probability", 0.2),
                "main_user_voice_probability": _percent_attr("main_user_voice_probability", -0.01, inherit=True),
                "main_user_mention_voice_probability": _percent_attr("main_user_mention_voice_probability", 0.0),
                "rest_reply_probability": _percent_attr("rest_reply_probability", 0.18),
            }
        )
        return values

    def _build_diagnostics(self, users: dict[str, Any], groups: dict[str, Any]) -> list[dict[str, str]]:
        items: list[dict[str, str]] = []

        def add(level: str, title: str, text: str, action: str = "") -> None:
            items.append({"level": level, "title": title, "text": text, "action": action})

        features = self._feature_flags()
        providers = self._provider_settings()
        group_mode = str(getattr(self.plugin, "group_access_mode", "whitelist") or "whitelist")
        whitelist = self.plugin._configured_group_ids()
        blacklist = self.plugin._configured_group_blacklist_ids()
        enabled_users = sum(1 for item in users.values() if isinstance(item, dict) and item.get("enabled", True))
        enabled_groups = sum(1 for item in groups.values() if isinstance(item, dict) and item.get("enabled", True))

        if getattr(self.plugin, "enabled", False):
            add("ok", "插件已启用", "后台主动检查与事件处理会正常运行")
        else:
            add("error", "插件未启用", "当前不会进行私聊主动陪伴或群聊观察", "在配置中打开 enabled")

        if providers.get("LLM_PROVIDER_ID") or getattr(self.plugin, "llm_provider_id", ""):
            add("ok", "主模型可见", providers.get("LLM_PROVIDER_ID") or "运行态已配置")
        else:
            add("info", "主模型留空", "会回退到 AstrBot 默认模型；建议为陪伴插件单独配置主模型")

        tts_summary = self._tts_runtime_summary(users)
        if tts_summary.get("enhancement_enabled"):
            if tts_summary.get("provider_available"):
                add(
                    "ok",
                    "TTS 语音链路可用",
                    f"模式 {tts_summary.get('mode')}，语种 {tts_summary.get('language')}，真实 TTS provider：{tts_summary.get('provider_label')}",
                )
            elif tts_summary.get("settings_enabled"):
                add(
                    "warn",
                    "TTS 配置已开但 provider 不可用",
                    f"会话 {tts_summary.get('umo') or '-'} 已启用 TTS 设置，但当前取不到可用 TTS provider",
                    "在 AstrBot 会话 TTS 配置里选择并启用真实语音合成 provider",
                )
            else:
                add(
                    "warn",
                    "TTS 强化已开但会话 TTS 未启用",
                    "本插件只能处理 <tts> 标签和文本转换；真正合成音频需要 AstrBot 当前会话启用 TTS provider",
                    "到 AstrBot 配置中为目标会话启用 TTS provider",
                )
        else:
            add(
                "info",
                "TTS 强化未开启",
                "VOICE_PROMPT_PROVIDER_ID / TTS文本转换模型都是文本模型；语音合成模型请在 AstrBot TTS provider 中配置",
            )

        if enabled_users:
            add("ok", "私聊对象已就绪", f"已启用 {enabled_users} 个私聊对象")
        else:
            add("warn", "暂无启用的私聊对象", "私聊主动陪伴没有明确目标", "在私聊页新增对象或配置 target_user_ids")

        max_daily = int(getattr(self.plugin, "max_daily_messages", 0) or 0)
        if max_daily > 0:
            add("ok", "私聊主动额度可用", f"每日上限 {max_daily} 条")
        else:
            add("warn", "私聊主动已关闭", "每日主动上限为 0", "在模块配置里调高每日主动上限")

        if getattr(self.plugin, "enable_daily_token_soft_limit", True):
            soft_limit = int(getattr(self.plugin, "daily_token_soft_limit", 0) or 0)
            today_tokens = int(getattr(self.plugin, "_today_llm_token_total", lambda: 0)() or 0)
            if soft_limit > 0 and today_tokens >= soft_limit:
                add(
                    "warn",
                    "每日 Token 软限额已接管",
                    f"今日已用约 {today_tokens} Token，低优先级后台 LLM 任务会暂缓",
                )
            elif soft_limit > 0:
                add("ok", "每日 Token 软限额已启用", f"软限额 {soft_limit}，当前约 {today_tokens}")
            else:
                add("info", "每日 Token 软限额未设置", "只使用每日硬限额")
        else:
            add("info", "每日 Token 软限额已关闭", "功能全开时后台任务会按各自开关正常运行")

        if features.get("enable_companion_memory") and features.get("enable_expression_learning"):
            add("ok", "私聊学习链路完整", "长期画像与表达学习均已打开")
        else:
            add("warn", "私聊学习链路不完整", "画像记忆或表达学习未开启", "在配置页打开对应功能开关")

        if features.get("enable_livingmemory_integration"):
            living_level = "ok" if self.plugin._livingmemory_available() else "warn"
            living_text = "LivingMemory 插件可被调用" if living_level == "ok" else "已启用协同，但当前未检测到可用工具"
            add(living_level, "LivingMemory 协同", living_text)

        if features.get("enable_bilibili_integration"):
            bili_available = bool(getattr(self.plugin, "_bilibili_available", lambda: False)())
            add(
                "ok" if bili_available else "info",
                "B 站 Bot 联动",
                "已检测到 B 站插件或观看日志" if bili_available else "联动开关已开，但暂未检测到 B 站插件实例或日志",
            )

        if features.get("enable_private_reading_integration"):
            jm_available = bool(getattr(self.plugin, "_jm_cosmos_available", lambda: False)())
            add(
                "ok" if jm_available else "info",
                "夹层阅读素材",
                "已检测到可用素材能力" if jm_available else "开关已开，但暂未检测到可用素材能力",
            )

        if features.get("enable_photo_text_action") and getattr(self.plugin, "enable_local_photo_load_guard", False):
            load_state = getattr(self.plugin, "_local_photo_generation_load_state", lambda: {})()
            if isinstance(load_state, dict):
                if load_state.get("available"):
                    add(
                        "warn" if load_state.get("busy") else "ok",
                        "本地生图负载保护",
                        str(load_state.get("reason") or "负载正常"),
                    )
                else:
                    add("info", "本地生图负载保护未采样", str(load_state.get("reason") or "无法读取系统负载"))

        llm_perception_available = bool(getattr(self.plugin, "_llmperception_available", lambda: False)())
        if llm_perception_available:
            if features.get("enable_environment_perception"):
                add(
                    "warn",
                    "检测到 LLMPerception 插件",
                    "本插件已内置时间、节假日、农历节气和平台环境感知；两者同时启用会重复注入并增加 Token 消耗",
                    "建议手动二选一；本插件不会再自动改写 enable_environment_perception",
                )
            else:
                add("ok", "环境感知由外部插件接管", "检测到 LLMPerception，且本插件内置环境感知当前为关闭")

        if features.get("enable_creative_writing"):
            projects = self._creative_summary({"creative_projects": getattr(self.plugin, "data", {}).get("creative_projects", [])})
            active = projects.get("active_projects", 0)
            add(
                "ok" if active else "info",
                "私下创作行为",
                f"当前进行中创作 {active} 个" if active else "已开启；会在生活/梦境触发后慢慢开坑",
            )

        if getattr(self.plugin, "enable_group_companion", False):
            if group_mode == "whitelist" and not whitelist:
                add("warn", "群聊白名单为空", "白名单模式下所有群都会被拦截", "在配置页加入群号或切换为黑名单模式")
            elif group_mode == "blacklist":
                add("ok", "群聊黑名单模式", f"已屏蔽 {len(blacklist)} 个群，其余群可观察")
            else:
                add("ok", "群聊白名单模式", f"允许 {len(whitelist)} 个群")

            if enabled_groups:
                add("ok", "已有群聊观测数据", f"已启用 {enabled_groups} 个群")
            else:
                add("info", "暂无群聊观测数据", "收到群消息后会逐步建立群画像")
        else:
            add("info", "群聊陪伴未开启", "当前不会记录群聊上下文")

        if features.get("enable_group_interjection"):
            limit = int(getattr(self.plugin, "group_interject_max_daily", 0) or 0)
            if limit > 0:
                add("ok", "群聊插话可用", f"每群每日上限 {limit} 次")
            else:
                add("warn", "群聊插话开关已开但额度为 0", "功能不会真正触发", "在模块配置里调高每群每日插话上限")
        elif getattr(self.plugin, "enable_group_companion", False):
            add("info", "群聊以观察为主", "当前只积累群上下文，不主动插话")

        context_aware_installed = bool(getattr(self.plugin, "_context_aware_available", lambda: False)())
        if context_aware_installed:
            if features.get("enable_group_scene_awareness"):
                add(
                    "warn",
                    "检测到上下文场景感知增强插件",
                    "不会造成代码级冲突，但若两个插件同时注入群聊场景，会增加重复上下文和 Token 消耗",
                    "建议手动二选一；本插件不会再自动改写 enable_group_scene_awareness",
                )
            else:
                add("ok", "群聊场景感知由外部插件接管", "检测到 context_aware，且本插件对应内置功能当前为关闭")

        atrelay_installed = bool(getattr(self.plugin, "_atrelay_plugin_available", lambda: False)())
        if atrelay_installed:
            if features.get("enable_atrelay_tools"):
                add(
                    "warn",
                    "检测到艾特群友插件",
                    "本插件已内置跨群转述与 @ 群友工具；两者同时启用可能让模型看到重复工具",
                    "建议手动二选一；本插件不会再自动改写 enable_atrelay_tools",
                )
            else:
                add("ok", "跨群转述由外部插件接管", "检测到 atrelay，且本插件对应内置工具当前为关闭")

        if not features.get("enable_group_privacy_guard"):
            add("warn", "群聊隐私保护未开启", "私聊记忆注入群聊时缺少额外防护", "建议打开 enable_group_privacy_guard")

        refresh_minutes = int(getattr(self.plugin, "memory_refresh_interval_minutes", 0) or 0)
        if refresh_minutes and refresh_minutes < 60:
            add("warn", "长期记忆整理过于频繁", f"当前 {refresh_minutes} 分钟，可能增加模型调用量", "建议设置为 120 分钟以上")

        return items

    def _tts_runtime_summary(self, users: dict[str, Any]) -> dict[str, Any]:
        enabled_user = None
        for item in users.values():
            if isinstance(item, dict) and item.get("enabled", True) and item.get("umo"):
                enabled_user = item
                if self.plugin._private_user_role(item, str(item.get("user_id") or "")) == "owner":
                    break
        umo = self._single_line((enabled_user or {}).get("umo"), 180) if isinstance(enabled_user, dict) else ""
        config: dict[str, Any] = {}
        provider_settings: dict[str, Any] = {}
        provider = None
        context = getattr(self.plugin, "context", None)
        if context is not None:
            getter = getattr(context, "get_config", None)
            if callable(getter):
                try:
                    config = getter(umo) if umo else getter()
                    if not isinstance(config, dict):
                        config = {}
                except Exception:
                    config = {}
            provider_settings = dict((config or {}).get("provider_tts_settings", {}) or {})
            provider_getter = getattr(context, "get_using_tts_provider", None)
            if callable(provider_getter):
                try:
                    provider = provider_getter(umo) if umo else provider_getter()
                except Exception:
                    provider = None
        provider_label = ""
        if provider is not None:
            provider_id = self._provider_id(provider)
            provider_label = self._provider_name(provider, provider_id) if provider_id else getattr(provider, "__class__", type(provider)).__name__
        return {
            "enhancement_enabled": bool(getattr(self.plugin, "enable_tts_enhancement", False)),
            "mode": self._single_line(getattr(self.plugin, "tts_generation_mode", ""), 24) or "fast_tag",
            "language": self.plugin._tts_language_label() if hasattr(self.plugin, "_tts_language_label") else "",
            "umo": umo,
            "settings_enabled": bool(provider_settings.get("enable", False)),
            "provider_available": provider is not None,
            "provider_label": self._single_line(provider_label, 80) or "未知 provider",
        }

    def _message_debounce_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        raw = data.get("smart_message_debounce")
        if not isinstance(raw, dict):
            raw = {}
        logs_raw = raw.get("recent_logs") if isinstance(raw.get("recent_logs"), list) else []
        examples_raw = raw.get("examples") if isinstance(raw.get("examples"), list) else []
        logs: list[dict[str, Any]] = []
        for item in logs_raw[-30:][::-1]:
            if not isinstance(item, dict):
                continue
            logs.append(
                {
                    "ts": self._float(item.get("ts")),
                    "time": self.plugin._format_timestamp_elapsed(self._float(item.get("ts"))) if self._float(item.get("ts")) else "",
                    "scope": self._single_line(item.get("scope"), 80),
                    "sender_id": self._single_line(item.get("sender_id"), 40),
                    "chat": self._single_line(item.get("chat"), 20),
                    "text": self._single_line(item.get("text"), 180),
                    "decision": self._single_line(item.get("decision"), 40),
                    "confidence": self._float(item.get("confidence")),
                    "reason": self._single_line(item.get("reason"), 120),
                    "wait_seconds": self._float(item.get("wait_seconds")),
                    "outcome": self._single_line(item.get("outcome"), 40),
                    "note": self._single_line(item.get("note"), 160),
                    "source": self._single_line(item.get("source"), 40),
                    "raw": self._single_line(item.get("raw"), 180),
                    "message_count": self._int(item.get("message_count")),
                }
            )
        examples: list[dict[str, Any]] = []
        for item in examples_raw[-10:][::-1]:
            if not isinstance(item, dict):
                continue
            messages = item.get("messages") if isinstance(item.get("messages"), list) else []
            examples.append(
                {
                    "time": self.plugin._format_timestamp_elapsed(self._float(item.get("ts"))) if self._float(item.get("ts")) else "",
                    "kind": self._single_line(item.get("kind"), 40),
                    "scope": self._single_line(item.get("scope"), 80),
                    "sender_id": self._single_line(item.get("sender_id"), 40),
                    "messages": [self._single_line(message, 120) for message in messages[:4]],
                    "previous_decision": self._single_line(item.get("previous_decision"), 40),
                    "note": self._single_line(item.get("note"), 120),
                }
            )
        return {
            "enabled": bool(getattr(self.plugin, "enable_message_debounce", False)),
            "smart_enabled": bool(getattr(self.plugin, "enable_smart_message_debounce", False)),
            "text_wait": self._float(getattr(self.plugin, "text_message_debounce_seconds", 0.0)),
            "max_wait": self._float(getattr(self.plugin, "text_message_debounce_max_wait_seconds", 0.0)),
            "max_merge": self._int(getattr(self.plugin, "message_debounce_max_merge_messages", 0)),
            "smart_wait": self._float(getattr(self.plugin, "smart_message_debounce_wait_seconds", 0.0)),
            "learning_window": self._float(getattr(self.plugin, "smart_message_debounce_learning_window_seconds", 0.0)),
            "provider_id": self._single_line(getattr(self.plugin, "smart_message_debounce_provider_id", ""), 160),
            "recent_logs": logs,
            "examples": examples,
        }

    @staticmethod
    def _presets() -> dict[str, dict[str, Any]]:
        return {
            "safe": {
                "label": "保守低打扰",
                "settings": {
                    "max_daily_messages": 3,
                    "idle_minutes": 180,
                    "min_interval_minutes": 360,
                    "group_interject_max_daily": 0,
                    "group_interject_min_interval_minutes": 360,
                    "memory_refresh_interval_minutes": 720,
                    "episode_memory_refresh_messages": 12,
                    "episode_memory_refresh_minutes": 180,
                },
                "features": {
                    "enable_group_companion": True,
                    "enable_group_interjection": False,
                    "enable_companion_memory": True,
                    "enable_expression_learning": True,
                    "enable_response_self_review": True,
                    "enable_livingmemory_integration": True,
                },
            },
            "standard": {
                "label": "标准陪伴",
                "settings": {
                    "max_daily_messages": 6,
                    "idle_minutes": 60,
                    "min_interval_minutes": 120,
                    "group_interject_max_daily": 1,
                    "group_interject_min_interval_minutes": 240,
                    "memory_refresh_interval_minutes": 360,
                    "episode_memory_refresh_messages": 8,
                    "episode_memory_refresh_minutes": 90,
                },
                "features": {
                    "enable_group_companion": True,
                    "enable_group_interjection": False,
                    "enable_group_context_injection": True,
                    "enable_companion_memory": True,
                    "enable_expression_learning": True,
                    "enable_dialogue_episode_memory": True,
                    "enable_open_loop_tracking": True,
                    "enable_response_self_review": True,
                },
            },
            "active": {
                "label": "高互动学习",
                "settings": {
                    "max_daily_messages": 10,
                    "idle_minutes": 30,
                    "min_interval_minutes": 60,
                    "group_interject_max_daily": 2,
                    "group_interject_min_interval_minutes": 180,
                    "memory_refresh_interval_minutes": 240,
                    "episode_memory_refresh_messages": 5,
                    "episode_memory_refresh_minutes": 60,
                },
                "features": {
                    "enable_group_companion": True,
                    "enable_companion_memory": True,
                    "enable_expression_learning": True,
                    "enable_companion_reply_planner": True,
                    "enable_intent_emotion_analysis": True,
                    "enable_response_self_review": True,
                    "enable_dialogue_episode_memory": True,
                    "enable_open_loop_tracking": True,
                    "enable_group_interjection": True,
                    "enable_group_interjection_feedback": True,
                },
            },
            "group_observer": {
                "label": "群聊观察优先",
                "settings": {
                    "max_daily_messages": 4,
                    "idle_minutes": 90,
                    "min_interval_minutes": 180,
                    "group_interject_max_daily": 0,
                    "group_interject_min_interval_minutes": 240,
                    "max_group_recent_messages": 120,
                    "max_group_slang_terms": 80,
                },
                "features": {
                    "enable_group_companion": True,
                    "enable_group_context_injection": True,
                    "enable_group_slang_learning": True,
                    "enable_group_member_profiles": True,
                    "enable_group_topic_threads": True,
                    "enable_group_episode_memory": True,
                    "enable_group_slang_meanings": True,
                    "enable_group_relationship_graph": True,
                    "enable_group_privacy_guard": True,
                    "enable_group_interjection": False,
                },
            },
        }

    def _apply_config_value(self, key: str, value: Any, overrides: dict[str, Any] | None = None) -> None:
        self._set_config_value(key, value)
        attr_map = {
            "LLM_PROVIDER_ID": "llm_provider_id",
            "MAI_STYLE_PROVIDER_ID": "mai_style_provider_id",
            "DAILY_PLAN_PROVIDER_ID": "daily_plan_provider_id",
            "DETAIL_ENHANCEMENT_PROVIDER_ID": "detail_enhancement_provider_id",
            "DREAM_DIARY_PROVIDER_ID": "dream_diary_provider_id",
            "CREATIVE_PROVIDER_ID": "creative_provider_id",
            "VOICE_PROMPT_PROVIDER_ID": "voice_prompt_provider_id",
            "PHOTO_PROMPT_PROVIDER_ID": "photo_prompt_provider_id",
            "NARRATION_PROVIDER_ID": "narration_provider_id",
            "HISTORY_SUMMARY_PROVIDER_ID": "history_summary_provider_id",
            "RESPONSE_REVIEW_PROVIDER_ID": "response_review_provider_id",
            "TROUBLESHOOTING_PROVIDER_ID": "troubleshooting_provider_id",
            "RELATIONSHIP_ANALYSIS_PROVIDER_ID": "relationship_analysis_provider_id",
            "COMPANION_MEMORY_PROVIDER_ID": "companion_memory_provider_id",
            "DIALOGUE_EPISODE_PROVIDER_ID": "dialogue_episode_provider_id",
            "GROUP_INTERJECT_PROVIDER_ID": "group_interject_provider_id",
            "GROUP_EPISODE_PROVIDER_ID": "group_episode_provider_id",
            "GROUP_SLANG_PROVIDER_ID": "group_slang_provider_id",
            "GROUP_FOLLOWUP_JUDGE_PROVIDER_ID": "group_followup_judge_provider_id",
            "FORWARD_MESSAGE_PROVIDER_ID": "forward_message_provider_id",
            "PLUGIN_VISION_PROVIDER_ID": "plugin_vision_provider_id",
            "PRIVATE_READING_VISION_PROVIDER_ID": "jm_cosmos_vision_provider_id",
            "NEWS_PROVIDER_ID": "news_provider_id",
            "WEB_EXPLORATION_PROVIDER_ID": "web_exploration_provider_id",
            "SMART_MESSAGE_DEBOUNCE_PROVIDER_ID": "smart_message_debounce_provider_id",
        }
        if key in attr_map:
            setattr(self.plugin, attr_map[key], str(value or "").strip())
            if key == "DREAM_DIARY_PROVIDER_ID":
                shared = str(value or "").strip()
                self.plugin.dream_provider_id = shared
                self.plugin.diary_provider_id = shared
            return
        if key == "group_access_mode":
            self.plugin.group_access_mode = str(value or "whitelist").lower()
            return
        if key == "group_whitelist_ids":
            self.plugin.group_whitelist_ids = list(value or [])
            return
        if key == "group_blacklist_ids":
            self.plugin.group_blacklist_ids = list(value or [])
            return
        if key == "QZONE_COOKIE":
            self.plugin.qzone_cookie = str(value or "").strip()
            return
        if key == "roleplay_knowledge_source_ids":
            normalizer = getattr(self.plugin, "_normalize_roleplay_knowledge_source_ids", None)
            self.plugin.roleplay_knowledge_source_ids = normalizer(value) if callable(normalizer) else list(value or [])
            return
        private_reading_attr_map = {
            "enable_private_reading_integration": "enable_jm_cosmos_integration",
            "enable_private_reading_boredom_read": "enable_jm_cosmos_boredom_read",
            "enable_private_reading_ask_recommendation": "enable_private_reading_ask_recommendation",
            "enable_private_reading_preference_influence": "enable_private_reading_preference_influence",
            "private_reading_min_interval_hours": "jm_cosmos_min_interval_hours",
            "private_reading_max_photo_count": "jm_cosmos_max_photo_count",
            "private_reading_share_probability": "jm_cosmos_share_probability",
            "private_reading_ask_probability": "private_reading_ask_probability",
            "private_reading_preference_min_ratings": "private_reading_preference_min_ratings",
            "private_reading_preference_max_terms": "private_reading_preference_max_terms",
            "private_reading_default_keywords": "jm_cosmos_default_keywords",
            "private_reading_blocked_tags": "private_reading_blocked_tags",
        }
        if key in private_reading_attr_map:
            setattr(self.plugin, private_reading_attr_map[key], value)
            return
        if key == "plugin_specific_persona_id":
            self.plugin.plugin_specific_persona_id = str(value or "").strip()
            self.plugin._default_persona_prompt_cache = ""
            self.plugin._default_persona_prompt_cache_persona_id = ""
            return
        if key == "private_user_aliases":
            self.plugin.private_user_aliases = self.plugin._parse_private_user_aliases(value)
            if self.plugin._merge_private_user_alias_records():
                self.plugin._save_data_sync()
            return
        if key in {"group_repeat_follow_probability", "group_repeat_interrupt_probability", "group_repeat_interrupt_probability_step"}:
            raw = float(value or 0)
            setattr(self.plugin, key, max(0.0, min(1.0, raw / 100.0 if raw > 1 else raw)))
            return
        if key == "rest_reply_probability":
            raw = float(value or 0)
            setattr(self.plugin, key, max(0.0, min(1.0, raw / 100.0 if raw > 1 else raw)))
            return
        tts_runtime_keys = {
            "tts_generation_mode",
            "tts_voice_language",
            "tts_conversion_provider_id",
            "tts_extra_prompt",
            "tts_frequency_control_mode",
            "tts_constraint_mode",
            "tts_session_min_interval_seconds",
            "tts_private_min_interval_seconds",
            "tts_group_min_interval_seconds",
            "tts_trigger_probability",
            "tts_private_trigger_probability",
            "tts_group_trigger_probability",
            "enable_tts_local_playback",
            "enable_tts_local_playback_live_only",
            "enable_tts_live_subtitle_sync",
            "tts_live_subtitle_url",
            "tts_local_playback_min_interval_seconds",
            "auto_voice_enabled",
            "auto_voice_full_conversion_enabled",
            "auto_voice_probability",
            "auto_voice_max_chars",
            "auto_voice_cooldown_seconds",
            "main_user_voice_probability",
            "main_user_mention_voice_keywords",
            "main_user_mention_voice_probability",
            "main_user_mention_voice_prompt",
        }
        if key == "enable_tts_enhancement" or key in tts_runtime_keys:
            loader = getattr(self.plugin, "_load_tts_enhancement_config", None)
            if callable(loader):
                loader(self._config_overlay(overrides or {key: value}))
            else:
                setattr(self.plugin, key, value)
            return
        if key in self._allowed_feature_keys():
            setattr(self.plugin, key, self._normalize_bool_value(value))
            return
        if key in self._allowed_setting_keys():
            setattr(self.plugin, key, value)

    @staticmethod
    def _normalize_bool_value(value: Any) -> bool:
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"true", "1", "yes", "y", "on", "enable", "enabled", "启用", "开启", "开", "是"}:
                return True
            if text in {"false", "0", "no", "n", "off", "disable", "disabled", "停用", "关闭", "关", "否", ""}:
                return False
        return bool(value)

    def _set_config_value(self, key: str, value: Any) -> None:
        config = getattr(self.plugin, "config", None)
        if config is None:
            return
        try:
            config[key] = value
            return
        except Exception:
            pass
        setter = getattr(config, "set", None)
        if callable(setter):
            try:
                setter(key, value)
                return
            except Exception:
                pass
        data = getattr(config, "data", None)
        if isinstance(data, dict):
            data[key] = value
            return
        raw = getattr(config, "config", None)
        if isinstance(raw, dict):
            raw[key] = value
            return
        try:
            setattr(config, key, value)
        except Exception:
            logger.debug("[PrivateCompanionPage] 配置字段写入失败: %s", key)

    def _config_overlay(self, overrides: dict[str, Any]) -> Any:
        base = getattr(self.plugin, "config", {}) or {}

        class _Overlay:
            def get(self, item: str, default: Any = None) -> Any:
                if item in overrides:
                    return overrides[item]
                getter = getattr(base, "get", None)
                if callable(getter):
                    try:
                        return getter(item, default)
                    except Exception:
                        return default
                if isinstance(base, dict):
                    return base.get(item, default)
                return getattr(base, item, default)

        return _Overlay()

    def _config_get(self, key: str) -> str:
        config = getattr(self.plugin, "config", None)
        if isinstance(config, dict):
            return str(config.get(key, "") or "")
        return ""

    async def _save_config_if_possible(self) -> bool:
        config = getattr(self.plugin, "config", None)
        for method_name in ("save_config", "save", "save_conf"):
            save = getattr(config, method_name, None)
            if callable(save):
                try:
                    result = save()
                    if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
                        await result
                    return True
                except TypeError:
                    continue
                except Exception as exc:
                    logger.warning("[PrivateCompanionPage] 配置保存失败(%s): %s", method_name, self._single_line(exc, 160))
                    return False
        logger.warning("[PrivateCompanionPage] 当前配置对象没有可用保存方法,本次改动可能只在运行态生效")
        return False

    def _can_save_config(self) -> bool:
        config = getattr(self.plugin, "config", None)
        return any(callable(getattr(config, method_name, None)) for method_name in ("save_config", "save", "save_conf"))

    @staticmethod
    def _allowed_feature_keys() -> set[str]:
        return {
            "enable_proactive_only_mode",
            "enable_mai_style_integration",
            "enable_companion_memory",
            "enable_expression_learning",
            "enable_companion_reply_planner",
            "enable_intent_emotion_analysis",
            "enable_response_self_review",
            "enable_llm_timer_scheduling",
            "enable_passive_topic_suppression",
            "enable_relationship_state_machine",
            "enable_emotion_simulation",
            "enable_dialogue_episode_memory",
            "enable_open_loop_tracking",
            "enable_user_habit_learning",
            "enable_humanized_states",
            "enable_segmented_proactive_reply",
            "enable_proactive_quote_trigger_message",
            "enable_photo_text_action",
            "inject_passive_states",
            "enable_cycle_state",
            "enable_skill_growth_simulation",
            "enable_skill_growth_passive_injection",
            "enable_message_debounce",
            "enable_smart_message_debounce",
            "enable_recall_enhancement",
            "enable_recall_cancel_reply",
            "enable_recall_message_cache",
            "enable_recall_transcribe_command",
            "enable_forbidden_word_recall",
            "enable_semantic_message_debounce",
            "enable_environment_perception",
            "enable_holiday_perception",
            "enable_platform_perception",
            "enable_model_perception",
            "enable_worldview_perception",
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "enable_group_companion",
            "enable_group_slang_learning",
            "enable_group_member_profiles",
            "enable_group_context_injection",
            "enable_group_persona_denoise",
            "enable_forward_message_adaptation",
            "enable_group_reality_promise_guard",
            "enable_group_wakeup_enhancement",
            "enable_group_high_intensity_mode",
            "enable_private_image_self_recognition",
            "enable_private_image_gif_enhancement",
            "enable_group_conversation_followup",
            "enable_group_interjection",
            "enable_group_repeat_follow",
            "group_repeat_count_distinct_users_only",
            "enable_group_topic_threads",
            "enable_group_episode_memory",
            "enable_group_interjection_feedback",
            "enable_group_slang_meanings",
            "enable_group_slang_web_search",
            "enable_group_relationship_graph",
            "enable_group_privacy_guard",
            "enable_worldbook_member_recognition",
            "enable_group_scene_awareness",
            "enable_group_reality_promise_guard",
            "enable_atrelay_tools",
            "enable_livingmemory_integration",
            "enable_bilibili_integration",
            "enable_bilibili_boredom_watch",
            "enable_news_integration",
            "enable_news_boredom_read",
            "enable_news_daily_hot_read",
            "enable_ai_daily_watch",
            "enable_external_event_self_link",
            "enable_web_exploration",
            "enable_web_exploration_boredom_search",
            "enable_qzone_integration",
            "enable_qzone_life_publish",
            "enable_qzone_emotional_vent_publish",
            "enable_private_reading_integration",
            "enable_private_reading_boredom_read",
            "enable_private_reading_ask_recommendation",
            "enable_private_reading_preference_influence",
            "enable_unanswered_screen_peek_followup",
            "enable_yesterday_screen_diary_context",
            "enable_tts_enhancement",
            "enable_creative_writing",
            "creative_hidden_mode",
        }

    @staticmethod
    def _allowed_provider_keys() -> set[str]:
        return {
            "LLM_PROVIDER_ID",
            "MAI_STYLE_PROVIDER_ID",
            "DAILY_PLAN_PROVIDER_ID",
            "DETAIL_ENHANCEMENT_PROVIDER_ID",
            "DREAM_DIARY_PROVIDER_ID",
            "CREATIVE_PROVIDER_ID",
            "VOICE_PROMPT_PROVIDER_ID",
            "PHOTO_PROMPT_PROVIDER_ID",
            "NARRATION_PROVIDER_ID",
            "HISTORY_SUMMARY_PROVIDER_ID",
            "RESPONSE_REVIEW_PROVIDER_ID",
            "TROUBLESHOOTING_PROVIDER_ID",
            "RELATIONSHIP_ANALYSIS_PROVIDER_ID",
            "COMPANION_MEMORY_PROVIDER_ID",
            "DIALOGUE_EPISODE_PROVIDER_ID",
            "GROUP_INTERJECT_PROVIDER_ID",
            "GROUP_EPISODE_PROVIDER_ID",
            "GROUP_SLANG_PROVIDER_ID",
            "GROUP_FOLLOWUP_JUDGE_PROVIDER_ID",
            "FORWARD_MESSAGE_PROVIDER_ID",
            "PLUGIN_VISION_PROVIDER_ID",
            "PRIVATE_READING_VISION_PROVIDER_ID",
            "NEWS_PROVIDER_ID",
            "WEB_EXPLORATION_PROVIDER_ID",
        }

    @staticmethod
    def _allowed_setting_keys() -> set[str]:
        return {
            "bot_name",
            "enable_proactive_only_mode",
            "plugin_specific_persona_id",
            "target_user_ids",
            "private_user_aliases",
            "target_platform",
            "environment_perception_timezone",
            "holiday_country",
            "enable_environment_perception",
            "enable_holiday_perception",
            "enable_platform_perception",
            "enable_model_perception",
            "enable_worldview_perception",
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "default_nickname",
            "default_style",
            "schedule_persona_prompt",
            "schedule_worldview_prompt",
            "roleplay_user_profile_prompt",
            "roleplay_knowledge_source_ids",
            "worldview_adaptation_mode",
            "worldview_adaptation_prompt",
            "quiet_hours",
            "passive_topic_memory_hours",
            "tts_generation_mode",
            "tts_voice_language",
            "tts_conversion_provider_id",
            "tts_extra_prompt",
            "tts_frequency_control_mode",
            "tts_constraint_mode",
            "tts_session_min_interval_seconds",
            "tts_private_min_interval_seconds",
            "tts_group_min_interval_seconds",
            "tts_trigger_probability",
            "tts_private_trigger_probability",
            "tts_group_trigger_probability",
            "enable_tts_local_playback",
            "enable_tts_local_playback_live_only",
            "enable_tts_live_subtitle_sync",
            "tts_live_subtitle_url",
            "tts_local_playback_min_interval_seconds",
            "auto_voice_enabled",
            "auto_voice_full_conversion_enabled",
            "auto_voice_probability",
            "auto_voice_max_chars",
            "auto_voice_cooldown_seconds",
            "main_user_voice_probability",
            "main_user_mention_voice_keywords",
            "main_user_mention_voice_probability",
            "main_user_mention_voice_prompt",
            "daily_token_limit",
            "enable_daily_token_soft_limit",
            "daily_token_soft_limit",
            "humanized_state_intensity",
            "enable_rest_reply_simulation",
            "rest_reply_mode",
            "rest_reply_probability",
            "rest_reply_llm_threshold",
            "REST_WAKEUP_PROVIDER_ID",
            "check_interval_seconds",
            "idle_minutes",
            "min_interval_minutes",
            "max_daily_messages",
            "inbound_message_debounce_seconds",
            "enable_message_debounce",
            "enable_smart_message_debounce",
            "SMART_MESSAGE_DEBOUNCE_PROVIDER_ID",
            "smart_message_debounce_model_timeout_seconds",
            "smart_message_debounce_wait_seconds",
            "smart_message_debounce_learning_window_seconds",
            "smart_message_debounce_examples_limit",
            "text_message_debounce_seconds",
            "image_message_debounce_seconds",
            "forward_message_debounce_seconds",
            "text_message_debounce_max_wait_seconds",
            "message_debounce_max_merge_messages",
            "enable_semantic_message_debounce",
            "semantic_message_debounce_seconds",
            "enable_proactive_quote_trigger_message",
            "photo_action_max_daily",
            "photo_generation_backend",
            "COMFYUI_TEXT2IMG_WORKFLOW_NAME",
            "COMFYUI_SELFIE_WORKFLOW_NAME",
            "comfyui_photo_wait_seconds",
            "enable_local_photo_load_guard",
            "local_photo_cpu_busy_percent",
            "local_photo_memory_busy_percent",
            "local_photo_defer_minutes",
            "EXTERNAL_IMAGE_API_BASE_URL",
            "EXTERNAL_IMAGE_API_MODEL",
            "external_image_api_size",
            "external_image_api_timeout_seconds",
            "photo_generation_style",
            "photo_generation_style_custom_prompt",
            "private_image_vision_wait_seconds",
            "enable_private_image_gif_enhancement",
            "private_image_gif_max_frames",
            "enable_private_image_self_recognition",
            "private_image_self_recognition_hint",
            "enable_private_image_vision_cache",
            "private_image_vision_cache_max_items",
            "enable_segmented_proactive_reply",
            "segmented_proactive_scope",
            "segmented_proactive_chat_scope",
            "segmented_proactive_threshold",
            "segmented_proactive_min_segment_chars",
            "segmented_proactive_max_segments",
            "segmented_proactive_send_as_forward",
            "segmented_proactive_split_mode",
            "segmented_proactive_regex",
            "segmented_proactive_split_words",
            "enable_segmented_proactive_content_cleanup",
            "segmented_proactive_content_cleanup_scope",
            "segmented_proactive_content_cleanup_rule",
            "segmented_proactive_content_cleanup_words",
            "segmented_proactive_interval_method",
            "segmented_proactive_interval_min",
            "segmented_proactive_interval_max",
            "segmented_proactive_log_base",
            "group_conversation_followup_seconds",
            "group_conversation_followup_max_turns",
            "enable_group_conversation_followup",
            "enable_group_repeat_follow",
            "group_repeat_trigger_threshold",
            "group_repeat_count_distinct_users_only",
            "group_interject_min_interval_minutes",
            "group_interject_max_daily",
            "group_repeat_follow_probability",
            "group_repeat_interrupt_probability",
            "group_repeat_interrupt_probability_step",
            "group_repeat_interrupt_text",
            "group_repeat_interrupt_image_path",
            "group_scene_recent_limit",
            "enable_group_persona_denoise",
            "group_wakeup_direct_words",
            "group_wakeup_context_words",
            "group_wakeup_interest_keywords",
            "group_wakeup_interest_probability",
            "group_wakeup_cooldown_seconds",
            "group_wakeup_generated_keyword_limit",
            "group_wakeup_topic_interest_max_boost",
            "group_wakeup_debounce_pending_penalty",
            "group_wakeup_fatigue_limit",
            "group_wakeup_fatigue_decay_minutes",
            "group_wakeup_log_limit",
            "enable_group_high_intensity_mode",
            "group_high_intensity_wakeup_window_seconds",
            "group_high_intensity_wakeup_threshold",
            "group_high_intensity_cooldown_seconds",
            "group_high_intensity_merge_seconds",
            "group_high_intensity_max_merge_messages",
            "enable_forward_message_adaptation",
            "forward_message_mode",
            "forward_message_max_messages",
            "forward_message_max_chars",
            "forward_message_parse_nested",
            "forward_message_image_vision",
            "forward_message_image_limit",
            "enable_recall_cancel_reply",
            "enable_recall_message_cache",
            "enable_recall_transcribe_command",
            "recall_message_cache_ttl_seconds",
            "recall_message_cache_max_items",
            "enable_forbidden_word_recall",
            "recall_forbidden_words",
            "recall_forbidden_scope",
            "recall_forbidden_word_case_sensitive",
            "screen_diary_context_max_chars",
            "max_group_recent_messages",
            "max_group_slang_terms",
            "group_slang_web_search_terms",
            "group_slang_web_search_results",
            "memory_refresh_interval_minutes",
            "episode_memory_refresh_messages",
            "episode_memory_refresh_minutes",
            "max_companion_memory_items",
            "max_learned_expression_items",
            "max_dialogue_episodes",
            "user_habit_min_count",
            "user_habit_max_items",
            "emotional_gate_hurt_threshold",
            "emotional_gate_refuse_threshold",
            "emotional_gate_recovery_per_hour",
            "emotional_gate_max_hurt_minutes",
            "enable_skill_growth_simulation",
            "skill_growth_rate",
            "skill_growth_custom_skills",
            "enable_skill_growth_passive_injection",
            "enable_skill_growth_schedule_influence",
            "skill_growth_schedule_influence_strength",
            "enable_bilibili_integration",
            "enable_bilibili_boredom_watch",
            "bilibili_boredom_min_interval_hours",
            "bilibili_share_probability",
            "bilibili_share_min_score",
            "enable_news_integration",
            "enable_news_boredom_read",
            "enable_news_daily_hot_read",
            "enable_external_event_self_link",
            "news_min_interval_hours",
            "news_share_probability",
            "external_event_self_link_probability",
            "external_event_self_link_cooldown_hours",
            "news_max_items_per_source",
            "news_sources",
            "news_hot_sources",
            "news_hot_max_items",
            "enable_web_exploration",
            "enable_web_exploration_boredom_search",
            "web_exploration_min_interval_hours",
            "web_exploration_share_probability",
            "external_event_self_link_probability",
            "external_event_self_link_cooldown_hours",
            "web_exploration_max_results",
            "web_exploration_interests",
            "enable_qzone_integration",
            "QZONE_COOKIE",
            "enable_qzone_life_publish",
            "qzone_life_publish_min_interval_hours",
            "qzone_life_publish_probability",
            "enable_qzone_emotional_vent_publish",
            "qzone_emotional_vent_threshold",
            "qzone_emotional_vent_cooldown_hours",
            "qzone_emotional_vent_probability",
            "enable_private_reading_integration",
            "enable_private_reading_boredom_read",
            "enable_private_reading_ask_recommendation",
            "private_reading_min_interval_hours",
            "private_reading_max_photo_count",
            "private_reading_share_probability",
            "private_reading_ask_probability",
            "private_reading_preference_min_ratings",
            "private_reading_preference_max_terms",
            "private_reading_default_keywords",
            "private_reading_blocked_tags",
            "enable_unanswered_screen_peek_followup",
            "unanswered_screen_peek_after_minutes",
            "unanswered_screen_peek_cooldown_minutes",
            "enable_creative_writing",
            "creative_inspiration_probability",
            "creative_share_probability",
            "creative_chars_per_session",
            "creative_max_active_projects",
            "creative_hidden_mode",
            "enable_worldbook_member_recognition",
            "worldbook_auto_import",
            "worldbook_member_match_aliases",
            "worldbook_self_registration",
            "worldbook_auto_pending_observations",
            "worldbook_member_inject_limit",
            "worldbook_config_paths",
            "enable_atrelay_tools",
            "atrelay_require_worldbook_first",
            "atrelay_member_cache_minutes",
            "atrelay_sensitive_confirm",
            "atrelay_default_relay_style",
            "atrelay_multi_target_limit",
        }

    def _normalize_setting_value(self, key: str, value: Any) -> Any:
        if key in self._schema_bool_keys():
            return self._normalize_bool_value(value)
        if key == "target_user_ids":
            return self._normalize_id_list(value)
        if key == "plugin_specific_persona_id":
            return str(value or "").strip()[:160]
        if key == "private_user_aliases":
            return str(value or "").strip()[:4000]
        if key == "worldbook_config_paths":
            return str(value or "").strip()[:1000]
        if key in {"news_sources", "ai_daily_sources"}:
            return self._normalize_multiline_source_config(value, limit=4000)
        if key in {"news_hot_sources", "web_exploration_interests", "private_reading_default_keywords", "private_reading_blocked_tags"}:
            return str(value or "").strip()[:1200]
        if key == "QZONE_COOKIE":
            return str(value or "").replace("\r", ";").replace("\n", ";").strip()[:8000]
        if key in {"group_wakeup_direct_words", "group_wakeup_context_words", "group_wakeup_interest_keywords", "recall_forbidden_words"}:
            return str(value or "").strip()[:1200]
        if key == "recall_forbidden_scope":
            scope = str(value or "bot_and_group").strip().lower()
            return scope if scope in {"bot_only", "group_only", "bot_and_group"} else "bot_and_group"
        if key == "private_image_self_recognition_hint":
            return str(value or "").strip()[:1200]
        if key == "worldview_adaptation_mode":
            mode = str(value or "auto").strip()
            return mode if mode in {"auto", "modern", "fantasy", "sci_fi", "custom", "off"} else "auto"
        if key == "rest_reply_mode":
            mode = str(value or "probability").strip().lower()
            aliases = {
                "概率": "probability",
                "仅概率": "probability",
                "仅概率醒来": "probability",
                "模型": "llm",
                "模型判断": "llm",
                "模型判断是否醒来": "llm",
                "model": "llm",
                "llm_judge": "llm",
            }
            mode = aliases.get(mode, mode)
            return mode if mode in {"probability", "llm"} else "probability"
        if key == "REST_WAKEUP_PROVIDER_ID":
            return str(value or "").strip()[:160]
        if key == "tts_generation_mode":
            mode = str(value or "fast_tag").strip().lower()
            aliases = {
                "hybrid": "fast_tag",
                "direct": "fast_tag",
                "tag": "fast_tag",
                "fast": "fast_tag",
                "快速": "fast_tag",
                "标签": "fast_tag",
                "标签直出": "fast_tag",
                "convert": "postprocess",
                "post": "postprocess",
                "llm": "postprocess",
                "后处理": "postprocess",
                "判断翻译": "postprocess",
            }
            mode = aliases.get(mode, mode)
            return mode if mode in {"fast_tag", "postprocess"} else "fast_tag"
        if key == "tts_frequency_control_mode":
            mode = str(value or "global").strip().lower()
            aliases = {
                "全局": "global",
                "全局频控": "global",
                "新版": "global",
                "旧版": "legacy",
                "旧版行为": "legacy",
                "legacy_mode": "legacy",
            }
            mode = aliases.get(mode, mode)
            return mode if mode in {"global", "legacy"} else "global"
        if key == "tts_constraint_mode":
            mode = str(value or "weak").strip().lower()
            aliases = {
                "弱": "weak",
                "弱约束": "weak",
                "软": "weak",
                "软约束": "weak",
                "强": "strong",
                "强约束": "strong",
                "硬": "strong",
                "硬约束": "strong",
            }
            mode = aliases.get(mode, mode)
            return mode if mode in {"weak", "strong"} else "weak"
        if key == "tts_voice_language":
            lang = str(value or "ja").strip().lower()
            return lang if lang in {"ja", "zh", "en"} else "ja"
        if key in {"tts_extra_prompt", "main_user_mention_voice_prompt"}:
            return str(value or "").strip()[:1200]
        if key == "tts_conversion_provider_id":
            return str(value or "").strip()[:160]
        if key == "tts_session_min_interval_seconds":
            try:
                return max(0.0, min(3600.0, float(value)))
            except (TypeError, ValueError):
                return 90.0
        if key in {"tts_private_min_interval_seconds", "tts_group_min_interval_seconds"}:
            try:
                return max(-1.0, min(3600.0, float(value)))
            except (TypeError, ValueError):
                return -1.0
        if key == "main_user_mention_voice_keywords":
            return str(value or "").strip()[:1200]
        if key == "forward_message_mode":
            mode = str(value or "inject").strip().lower()
            if mode in {"注入", "injection"}:
                return "inject"
            if mode in {"转述", "summary", "summarize", "narrate", "relay"}:
                return "transcribe"
            return mode if mode in {"inject", "transcribe"} else "inject"
        if key == "photo_generation_backend":
            mode = str(value or "auto").strip().lower()
            return mode if mode in {"auto", "comfyui", "sdgen", "external"} else "auto"
        if key == "segmented_proactive_split_mode":
            mode = str(value or "regex").strip().lower()
            return mode if mode in {"regex", "words"} else "regex"
        if key == "segmented_proactive_scope":
            mode = str(value or "proactive_only").strip().lower()
            aliases = {
                "plugin": "proactive_only",
                "plugins": "proactive_only",
                "proactive": "proactive_only",
                "插件": "proactive_only",
                "插件主动": "proactive_only",
                "all": "all_llm",
                "llm": "all_llm",
                "全部": "all_llm",
                "全部分段": "all_llm",
            }
            mode = aliases.get(mode, mode)
            return mode if mode in {"proactive_only", "all_llm"} else "proactive_only"
        if key == "segmented_proactive_chat_scope":
            mode = str(value or "all").strip().lower()
            aliases = {
                "全部": "all",
                "all_chat": "all",
                "both": "all",
                "私聊": "private",
                "仅私聊": "private",
                "private_only": "private",
                "群聊": "group",
                "仅群聊": "group",
                "group_only": "group",
            }
            mode = aliases.get(mode, mode)
            return mode if mode in {"all", "private", "group"} else "all"
        if key == "segmented_proactive_interval_method":
            mode = str(value or "log").strip().lower()
            return mode if mode in {"log", "random"} else "log"
        if key == "segmented_proactive_content_cleanup_scope":
            mode = str(value or "all").strip().lower()
            return mode if mode in {"all", "trailing"} else "all"
        if key in {"segmented_proactive_split_words", "segmented_proactive_content_cleanup_words"}:
            def _decode_segmented_word(raw: Any) -> str:
                text = str(raw or "")
                stripped = text.strip()
                lowered = stripped.lower()
                if lowered in {"<space>", "{space}", "[space]", "\\s", "\\u0020", "空格"}:
                    return " "
                if lowered in {"<newline>", "{newline}", "[newline]", "\\n", "换行"}:
                    return "\n"
                if lowered in {"<tab>", "{tab}", "[tab]", "\\t", "tab"}:
                    return "\t"
                if lowered in {"<comma>", "{comma}", "[comma]", "comma", "英文逗号"}:
                    return ","
                if lowered in {"<zh_comma>", "{zh_comma}", "[zh_comma]", "zh_comma", "中文逗号", "逗号"}:
                    return "，"
                if text and text.isspace():
                    return text[:1]
                return stripped

            if isinstance(value, list):
                words = [_decode_segmented_word(item) for item in value]
            else:
                raw_words = str(value or "")
                parts = re.split(r"\r?\n", raw_words) if ("\n" in raw_words or "\r" in raw_words) else re.split(r"[,、]+", raw_words)
                words = [_decode_segmented_word(part) for part in parts]
            words = [word for word in words if word != ""]
            return words[:80]
        if key in {"segmented_proactive_regex", "segmented_proactive_content_cleanup_rule"}:
            return str(value or "").strip()[:800]
        if key == "atrelay_default_relay_style":
            mode = str(value or "persona").strip()
            return mode if mode in {"persona", "soft", "original"} else "persona"
        if key == "worldview_adaptation_prompt":
            return str(value or "").strip()[:1200]
        if key == "roleplay_knowledge_source_ids":
            normalizer = getattr(self.plugin, "_normalize_roleplay_knowledge_source_ids", None)
            if callable(normalizer):
                return normalizer(value)
            return []
        if key in {"schedule_persona_prompt", "schedule_worldview_prompt", "roleplay_user_profile_prompt"}:
            return str(value or "").strip()[:2000]
        if key == "humanized_state_intensity":
            try:
                return max(0, min(100, int(value)))
            except (TypeError, ValueError):
                return 50
        if key in {"local_photo_cpu_busy_percent", "local_photo_memory_busy_percent"}:
            try:
                return max(1, min(100, int(value)))
            except (TypeError, ValueError):
                return 85 if key == "local_photo_cpu_busy_percent" else 88
        if key == "local_photo_defer_minutes":
            try:
                return max(1, min(240, int(value)))
            except (TypeError, ValueError):
                return 30
        if key == "comfyui_photo_wait_seconds":
            try:
                return max(5, min(600, int(value)))
            except (TypeError, ValueError):
                return 90
        if key == "external_image_api_timeout_seconds":
            try:
                return max(20, min(600, int(value)))
            except (TypeError, ValueError):
                return 180
        if key == "photo_action_max_daily":
            try:
                return max(0, min(5, int(value)))
            except (TypeError, ValueError):
                return 1
        if key in self.PERCENT_PROBABILITY_KEYS:
            try:
                raw = float(value)
                return max(0, min(100, int(round(raw * 100 if 0 <= raw <= 1 else raw))))
            except (TypeError, ValueError):
                return 18 if key == "rest_reply_probability" else 20
        if key in self.INHERIT_PERCENT_PROBABILITY_KEYS:
            try:
                raw = float(value)
                if raw < 0:
                    return -1
                return max(0, min(100, int(round(raw * 100 if 0 <= raw <= 1 else raw))))
            except (TypeError, ValueError):
                return -1
        if key == "rest_reply_llm_threshold":
            try:
                return max(0, min(100, int(value)))
            except (TypeError, ValueError):
                return 65
        if key in {
            "check_interval_seconds",
            "daily_token_limit",
            "daily_token_soft_limit",
            "rest_reply_llm_threshold",
            "idle_minutes",
            "min_interval_minutes",
            "max_daily_messages",
            "segmented_proactive_threshold",
            "segmented_proactive_min_segment_chars",
            "segmented_proactive_max_segments",
            "group_conversation_followup_seconds",
            "group_conversation_followup_max_turns",
            "group_interject_min_interval_minutes",
            "group_interject_max_daily",
            "group_scene_recent_limit",
            "group_wakeup_cooldown_seconds",
            "group_wakeup_generated_keyword_limit",
            "group_wakeup_topic_interest_max_boost",
            "group_wakeup_debounce_pending_penalty",
            "group_wakeup_fatigue_limit",
            "group_wakeup_fatigue_decay_minutes",
            "group_wakeup_log_limit",
            "group_high_intensity_wakeup_window_seconds",
            "group_high_intensity_wakeup_threshold",
            "group_high_intensity_cooldown_seconds",
            "group_high_intensity_merge_seconds",
            "group_high_intensity_max_merge_messages",
            "photo_action_max_daily",
            "comfyui_photo_wait_seconds",
            "local_photo_cpu_busy_percent",
            "local_photo_memory_busy_percent",
            "local_photo_defer_minutes",
            "external_image_api_timeout_seconds",
            "forward_message_max_messages",
            "forward_message_max_chars",
            "forward_message_image_limit",
            "max_group_recent_messages",
            "max_group_slang_terms",
            "memory_refresh_interval_minutes",
            "episode_memory_refresh_messages",
            "episode_memory_refresh_minutes",
            "max_companion_memory_items",
            "max_learned_expression_items",
            "max_dialogue_episodes",
            "user_habit_min_count",
            "user_habit_max_items",
            "emotional_gate_hurt_threshold",
            "emotional_gate_refuse_threshold",
            "emotional_gate_recovery_per_hour",
            "emotional_gate_max_hurt_minutes",
            "bilibili_boredom_min_interval_hours",
            "bilibili_share_min_score",
            "news_min_interval_hours",
            "news_max_items_per_source",
            "news_hot_max_items",
            "ai_daily_check_interval_minutes",
            "external_event_self_link_cooldown_hours",
            "web_exploration_min_interval_hours",
            "web_exploration_max_results",
            "qzone_life_publish_min_interval_hours",
            "qzone_emotional_vent_threshold",
            "qzone_emotional_vent_cooldown_hours",
            "private_reading_min_interval_hours",
            "private_reading_max_photo_count",
            "private_reading_preference_min_ratings",
            "private_reading_preference_max_terms",
            "unanswered_screen_peek_after_minutes",
            "unanswered_screen_peek_cooldown_minutes",
            "creative_chars_per_session",
            "creative_max_active_projects",
            "worldbook_member_inject_limit",
            "atrelay_member_cache_minutes",
            "atrelay_multi_target_limit",
            "private_image_vision_cache_max_items",
            "group_slang_web_search_terms",
            "group_slang_web_search_results",
            "auto_voice_max_chars",
            "auto_voice_cooldown_seconds",
        }:
            try:
                if key == "group_high_intensity_max_merge_messages":
                    return max(0, min(50, int(value)))
                parsed = max(0, int(value))
                return parsed
            except (TypeError, ValueError):
                if key == "group_high_intensity_max_merge_messages":
                    return 8
                return 0
        if key == "group_wakeup_interest_probability":
            try:
                raw = float(value)
                return max(0, min(100, int(round(raw * 100 if 0 <= raw <= 1 else raw))))
            except (TypeError, ValueError):
                return 0
        if key == "inbound_message_debounce_seconds":
            try:
                return max(0.0, min(30.0, float(value)))
            except (TypeError, ValueError):
                return 3.0
        if key == "semantic_message_debounce_seconds":
            try:
                return max(0.0, min(15.0, float(value)))
            except (TypeError, ValueError):
                return 8.0
        if key in {"text_message_debounce_seconds", "image_message_debounce_seconds", "forward_message_debounce_seconds"}:
            try:
                return max(0.0, min(15.0, float(value)))
            except (TypeError, ValueError):
                return 0.0 if key != "image_message_debounce_seconds" else 8.0
        if key == "text_message_debounce_max_wait_seconds":
            try:
                return max(0.0, min(30.0, float(value)))
            except (TypeError, ValueError):
                return 12.0
        if key == "message_debounce_max_merge_messages":
            try:
                return max(0, min(30, int(value)))
            except (TypeError, ValueError):
                return 8
        if key in {"smart_message_debounce_model_timeout_seconds", "smart_message_debounce_wait_seconds", "smart_message_debounce_learning_window_seconds"}:
            try:
                upper = 5.0 if key == "smart_message_debounce_model_timeout_seconds" else 30.0
                lower = 0.2 if key == "smart_message_debounce_model_timeout_seconds" else 0.0
                return max(lower, min(upper, float(value)))
            except (TypeError, ValueError):
                if key == "smart_message_debounce_model_timeout_seconds":
                    return 0.8
                return 3.0 if key == "smart_message_debounce_wait_seconds" else 8.0
        if key == "smart_message_debounce_examples_limit":
            try:
                return max(0, min(30, int(value)))
            except (TypeError, ValueError):
                return 8
        if key == "SMART_MESSAGE_DEBOUNCE_PROVIDER_ID":
            return self._single_line(value, 160)
        if key == "private_image_vision_wait_seconds":
            try:
                return max(0.0, min(90.0, float(value)))
            except (TypeError, ValueError):
                return 30.0
        if key == "private_image_gif_max_frames":
            try:
                return max(1, min(8, int(value)))
            except (TypeError, ValueError):
                return 4
        if key == "group_repeat_trigger_threshold":
            try:
                return max(3, min(20, int(value)))
            except (TypeError, ValueError):
                return 4
        if key in {
            "group_repeat_follow_probability",
            "group_repeat_interrupt_probability",
            "group_repeat_interrupt_probability_step",
        }:
            try:
                raw = float(value)
                return max(0, min(100, int(round(raw * 100 if 0 <= raw <= 1 else raw))))
            except (TypeError, ValueError):
                return 0
        if key in {
            "bilibili_share_probability",
            "news_share_probability",
            "external_event_self_link_probability",
            "web_exploration_share_probability",
            "qzone_life_publish_probability",
            "qzone_emotional_vent_probability",
            "private_reading_share_probability",
            "private_reading_ask_probability",
            "creative_inspiration_probability",
            "creative_share_probability",
            "skill_growth_schedule_influence_strength",
        }:
            try:
                return max(0.0, min(1.0, float(value)))
            except (TypeError, ValueError):
                return 0.0
        if key == "skill_growth_rate":
            try:
                return max(0.1, min(3.0, float(value)))
            except (TypeError, ValueError):
                return 1.0
        if key in {
            "segmented_proactive_interval_min",
            "segmented_proactive_interval_max",
            "segmented_proactive_log_base",
        }:
            try:
                raw = float(value)
                if key == "segmented_proactive_log_base":
                    return max(1.1, min(10.0, raw))
                return max(0.1, min(30.0, raw))
            except (TypeError, ValueError):
                return 1.8 if key == "segmented_proactive_log_base" else 1.5
        if key in {
            "enable_daily_token_soft_limit",
            "enable_bilibili_integration",
            "enable_bilibili_boredom_watch",
            "enable_news_integration",
            "enable_news_boredom_read",
            "enable_news_daily_hot_read",
            "enable_ai_daily_watch",
            "ai_daily_prefer_text_version",
            "enable_external_event_self_link",
            "enable_web_exploration",
            "enable_web_exploration_boredom_search",
            "enable_qzone_integration",
            "enable_qzone_life_publish",
            "enable_qzone_emotional_vent_publish",
            "enable_private_reading_integration",
            "enable_private_reading_boredom_read",
            "enable_private_reading_ask_recommendation",
            "enable_private_reading_preference_influence",
            "enable_unanswered_screen_peek_followup",
            "enable_creative_writing",
            "creative_hidden_mode",
            "enable_environment_perception",
            "enable_holiday_perception",
            "enable_platform_perception",
            "enable_model_perception",
            "enable_worldview_perception",
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "auto_voice_enabled",
            "auto_voice_full_conversion_enabled",
            "enable_humanized_states",
            "inject_passive_states",
            "enable_cycle_state",
            "enable_worldbook_member_recognition",
            "enable_group_scene_awareness",
            "enable_group_reality_promise_guard",
            "enable_group_wakeup_enhancement",
            "enable_group_high_intensity_mode",
            "enable_group_persona_denoise",
            "enable_group_repeat_follow",
            "group_repeat_count_distinct_users_only",
            "enable_forward_message_adaptation",
            "enable_skill_growth_simulation",
            "enable_skill_growth_passive_injection",
            "enable_skill_growth_schedule_influence",
            "forward_message_parse_nested",
            "forward_message_image_vision",
            "enable_message_debounce",
            "enable_smart_message_debounce",
            "enable_recall_enhancement",
            "enable_recall_cancel_reply",
            "enable_recall_message_cache",
            "enable_recall_transcribe_command",
            "recall_message_cache_ttl_seconds",
            "recall_message_cache_max_items",
            "enable_forbidden_word_recall",
            "recall_forbidden_words",
            "recall_forbidden_scope",
            "recall_forbidden_word_case_sensitive",
            "enable_semantic_message_debounce",
            "enable_proactive_quote_trigger_message",
            "enable_local_photo_load_guard",
            "enable_private_image_self_recognition",
            "enable_private_image_gif_enhancement",
            "enable_private_image_vision_cache",
            "enable_segmented_proactive_reply",
            "segmented_proactive_send_as_forward",
            "enable_segmented_proactive_content_cleanup",
            "enable_humanized_states",
            "inject_passive_states",
            "enable_cycle_state",
            "enable_group_conversation_followup",
            "worldbook_auto_import",
            "worldbook_member_match_aliases",
            "worldbook_self_registration",
            "enable_atrelay_tools",
            "atrelay_require_worldbook_first",
            "atrelay_sensitive_confirm",
        }:
            return self._normalize_bool_value(value)
        return self._single_line(value, 240)

    @staticmethod
    def _normalize_multiline_source_config(value: Any, *, limit: int = 4000) -> str:
        text = str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()
        if text and "\n" not in text:
            markers = list(re.finditer(r"(?:^|\s+)(#?\s*[^|\n]+?)\|(?=(?:https?://|bilibili:|bvid:))", text, flags=re.I))
            if len(markers) > 1:
                recovered: list[str] = []
                for index, match in enumerate(markers):
                    start = match.end()
                    end = markers[index + 1].start() if index + 1 < len(markers) else len(text)
                    name = str(match.group(1) or "").strip()
                    target = text[start:end].strip()
                    if name and target:
                        recovered.append(f"{name}|{target}")
                if recovered:
                    text = "\n".join(recovered)
        lines: list[str] = []
        for raw_line in text.split("\n"):
            line = raw_line.strip()
            if line:
                lines.append(line)
        return "\n".join(lines)[:limit].strip()

    def _schema_bool_keys(self) -> set[str]:
        cached = self._schema_bool_key_cache
        if cached is not None:
            return cached
        keys: set[str] = set()
        try:
            raw = json.loads(Path(__file__).with_name("_conf_schema.json").read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                keys = {
                    str(key)
                    for key, item in raw.items()
                    if isinstance(item, dict) and item.get("type") == "bool"
                }
        except Exception as exc:
            logger.debug("[PrivateCompanionPage] 读取配置 schema 布尔字段失败: %s", exc)
        self._schema_bool_key_cache = keys
        return keys

    @classmethod
    def _normalize_worldbook_member_id(cls, value: Any) -> str:
        text = cls._single_line(value, 80)
        if not text:
            return ""
        lowered = text.lower()
        if lowered.startswith("bili:") or lowered.startswith("bilibili:"):
            digits = re.sub(r"\D+", "", lowered.split(":", 1)[1])
            return f"bili:{digits}" if digits else ""
        if lowered.startswith("bili_live_"):
            return re.sub(r"[^A-Za-z0-9_:-]+", "_", text)[:80]
        if text.isdigit():
            return text
        return re.sub(r"[^A-Za-z0-9_:-]+", "_", text)[:80]

    @staticmethod
    def _worldbook_member_id_valid(user_id: str) -> bool:
        if user_id.isdigit():
            return len(user_id) >= 5
        lowered = user_id.lower()
        if lowered.startswith("bili:"):
            return bool(re.fullmatch(r"bili:\d{2,}", lowered))
        if lowered.startswith("bili_live_"):
            return bool(re.fullmatch(r"bili_live_[A-Za-z0-9_-]{6,64}", user_id))
        return False

    def _bind_worldbook_external_member_locked(
        self,
        profiles: dict[str, Any],
        source_id: str,
        target_id: str,
        source_profile: dict[str, Any],
    ) -> dict[str, Any]:
        target = profiles.get(target_id)
        if not isinstance(target, dict):
            target = {
                "user_id": target_id,
                "name": self._single_line(source_profile.get("name"), 80) or target_id,
                "gender": self._single_line(source_profile.get("gender"), 40),
                "aliases": [],
                "content": "",
                "identity_note": f"QQ {target_id}，由外部身份绑定创建。",
                "boundary_note": "",
                "important_memories": [],
                "enabled": True,
                "priority": 120,
                "source_entries": [],
                "observed_names": [],
            }
            profiles[target_id] = target
        target["user_id"] = target_id
        target["identity_type"] = "qq"
        source_gender = self._single_line(source_profile.get("gender"), 40)
        if source_gender and not self._single_line(target.get("gender"), 40):
            target["gender"] = source_gender
        live_names = self._worldbook_string_list(source_profile.get("observed_names"), limit=12, item_limit=40)
        live_name = self._single_line(source_profile.get("name"), 40)
        if live_name and live_name != target_id:
            live_names.insert(0, live_name)
        aliases = self._worldbook_string_list(target.get("aliases"), limit=30, item_limit=40)
        for alias in live_names:
            if alias and alias != target_id and alias not in aliases:
                aliases.append(alias)
        target["aliases"] = aliases[:30]

        external_ids = self._worldbook_string_list(target.get("external_ids"), limit=20, item_limit=80)
        if source_id not in external_ids:
            external_ids.insert(0, source_id)
        target["external_ids"] = external_ids[:20]
        target["linked_bili_profile_id"] = source_id
        target["manual_edit_ts"] = time.time()

        for field, limit in (("content", 2000), ("identity_note", 2000), ("boundary_note", 1200)):
            source_text = str(source_profile.get(field) or "").strip()
            target_text = str(target.get(field) or "").strip()
            if source_text and source_text not in target_text:
                glue = "\n" if target_text else ""
                target[field] = (target_text + glue + source_text)[:limit]

        source_memories = self._normalize_important_memories(source_profile.get("important_memories"))
        target_memories = self._normalize_important_memories(target.get("important_memories"))
        seen = {self._single_line(item.get("content"), 160) for item in target_memories if isinstance(item, dict)}
        for memory in source_memories:
            content = self._single_line(memory.get("content"), 160)
            if content and content not in seen:
                target_memories.append(memory)
                seen.add(content)
        target["important_memories"] = target_memories[:30]

        source_entries = self._worldbook_string_list(target.get("source_entries"), limit=30, item_limit=80)
        for entry in self._worldbook_string_list(source_profile.get("source_entries"), limit=12, item_limit=80):
            if entry not in source_entries:
                source_entries.append(entry)
        if "live_stream_companion" not in source_entries:
            source_entries.append("live_stream_companion")
        target["source_entries"] = source_entries[:30]

        source_profile["enabled"] = False
        source_profile["linked_qq_user_id"] = target_id
        source_profile["merged_into_user_id"] = target_id
        source_profile["manual_edit_ts"] = time.time()
        self._merge_live_viewer_activity_for_worldbook_bind(source_id, target_id, live_names)
        return {"source_user_id": source_id, "target_user_id": target_id}

    def _worldbook_string_list(self, value: Any, *, limit: int = 20, item_limit: int = 60) -> list[str]:
        raw_items: list[Any]
        if isinstance(value, list):
            raw_items = value
        elif isinstance(value, str):
            raw_items = re.split(r"[\n,，;；]+", value)
        else:
            raw_items = []
        result: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            text = self._single_line(item, item_limit)
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
            if len(result) >= limit:
                break
        return result

    def _merge_live_viewer_activity_for_worldbook_bind(self, source_id: str, target_id: str, live_names: list[str]) -> None:
        store = self.plugin.data.get("live_stream_companion")
        if not isinstance(store, dict):
            return
        activity = store.get("viewer_activity")
        if not isinstance(activity, dict):
            return
        target_key = f"user:{target_id}"
        source_keys = [f"user:{source_id}"]
        source_keys.extend(f"live:{name}" for name in live_names if name)
        target = activity.setdefault(target_key, {"viewer_key": target_key, "user_id": target_id, "recent_events": [], "recent_danmaku": [], "event_counts": {}})
        if not isinstance(target, dict):
            target = {"viewer_key": target_key, "user_id": target_id, "recent_events": [], "recent_danmaku": [], "event_counts": {}}
            activity[target_key] = target
        target["viewer_key"] = target_key
        target["user_id"] = target_id
        aliases = target.setdefault("live_usernames", [])
        if not isinstance(aliases, list):
            aliases = []
            target["live_usernames"] = aliases
        for name in live_names:
            if name and name not in aliases:
                aliases.insert(0, name)
        del aliases[8:]
        for key in source_keys:
            item = activity.get(key)
            if not isinstance(item, dict) or item is target:
                continue
            self._merge_activity_item(target, item)
            activity.pop(key, None)

    @staticmethod
    def _merge_activity_item(target: dict[str, Any], source: dict[str, Any]) -> None:
        def as_float(value: Any, default: float = 0.0) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        def as_int(value: Any, default: int = 0) -> int:
            try:
                return int(value)
            except (TypeError, ValueError):
                return default

        target["total_events"] = as_int(target.get("total_events")) + as_int(source.get("total_events"))
        if source.get("display_name") and not target.get("display_name"):
            target["display_name"] = source.get("display_name")
        if source.get("live_username") and not target.get("live_username"):
            target["live_username"] = source.get("live_username")
        target["first_seen"] = min(as_float(target.get("first_seen"), time.time()), as_float(source.get("first_seen"), time.time()))
        target["last_seen"] = max(as_float(target.get("last_seen")), as_float(source.get("last_seen")))
        counts = target.setdefault("event_counts", {})
        if isinstance(counts, dict) and isinstance(source.get("event_counts"), dict):
            for key, value in source["event_counts"].items():
                counts[key] = as_int(counts.get(key)) + as_int(value)
        for field, limit in (("recent_events", 12), ("recent_danmaku", 8)):
            rows = []
            for row in [*(target.get(field) if isinstance(target.get(field), list) else []), *(source.get(field) if isinstance(source.get(field), list) else [])]:
                if isinstance(row, dict):
                    rows.append(row)
            rows.sort(key=lambda row: as_float(row.get("ts")), reverse=True)
            target[field] = rows[:limit]

    def _worldbook_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        profiles = data.get("worldbook_member_profiles") if isinstance(data.get("worldbook_member_profiles"), dict) else {}
        groups = data.get("worldbook_group_profiles") if isinstance(data.get("worldbook_group_profiles"), dict) else {}
        entries = data.get("worldbook_entries") if isinstance(data.get("worldbook_entries"), list) else []
        state = data.get("worldbook_import_state") if isinstance(data.get("worldbook_import_state"), dict) else {}
        profile_items = []
        for user_id, item in profiles.items():
            if not isinstance(item, dict):
                continue
            aliases = item.get("aliases") if isinstance(item.get("aliases"), list) else []
            observed = item.get("observed_names") if isinstance(item.get("observed_names"), list) else []
            external_ids = item.get("external_ids") if isinstance(item.get("external_ids"), list) else []
            memories = self._normalize_important_memories(item.get("important_memories"))
            pending = item.get("pending_observations") if isinstance(item.get("pending_observations"), list) else []
            pending_items = []
            for raw in pending[:8]:
                if not isinstance(raw, dict):
                    continue
                pending_items.append(
                    {
                        "id": self._single_line(raw.get("id"), 40),
                        "title": self._single_line(raw.get("title"), 60) or "群聊观察",
                        "content": self._single_line(raw.get("content"), 260),
                        "evidence": self._single_line(raw.get("evidence"), 160),
                        "group_id": self._single_line(raw.get("group_id"), 40),
                        "weight": self._clamp_int(raw.get("weight"), 35, 0, 100),
                        "count": self._clamp_int(raw.get("count"), 1, 1, 999),
                        "created_at": self.plugin._format_timestamp_elapsed(raw.get("created_at", 0)),
                    }
                )
            profile_items.append(
                {
                    "user_id": self._single_line(user_id, 40),
                    "identity_type": self._single_line(item.get("identity_type") or ("qq" if str(user_id).isdigit() else "external"), 20),
                    "name": self._single_line(item.get("name"), 60),
                    "gender": self._single_line(item.get("gender"), 40),
                    "enabled": bool(item.get("enabled", True)),
                    "priority": item.get("priority", 120),
                    "aliases": [self._single_line(alias, 40) for alias in aliases if self._single_line(alias, 40)],
                    "observed_names": [self._single_line(name, 40) for name in observed if self._single_line(name, 40)],
                    "external_ids": [self._single_line(ext, 80) for ext in external_ids if self._single_line(ext, 80)],
                    "linked_qq_user_id": self._single_line(item.get("linked_qq_user_id") or item.get("merged_into_user_id"), 40),
                    "linked_bili_profile_id": self._single_line(item.get("linked_bili_profile_id"), 80),
                    "auto_registration_pending": bool(item.get("auto_registration_pending", False)),
                    "content": self._single_line(item.get("content"), 260),
                    "identity_note": self._single_line(item.get("identity_note") or item.get("note") or item.get("content"), 500),
                    "boundary_note": self._single_line(item.get("boundary_note"), 500),
                    "important_memories": memories,
                    "pending_observations": pending_items,
                    "pending_observation_count": len(pending_items),
                    "source_entries": item.get("source_entries") if isinstance(item.get("source_entries"), list) else [],
                    "note": self._single_line(item.get("note"), 500),
                }
            )
        profile_items.sort(key=lambda item: (not item.get("enabled", True), item.get("name") or item.get("user_id")))
        group_items = [
            {
                "group_id": self._single_line(group_id, 40),
                "name": self._single_line(item.get("name"), 60),
                "enabled": bool(item.get("enabled", True)),
                "priority": item.get("priority", 110),
                "content": self._single_line(item.get("content"), 220),
            }
            for group_id, item in groups.items()
            if isinstance(item, dict)
        ]
        return {
            "enabled": bool(getattr(self.plugin, "enable_worldbook_member_recognition", False)),
            "auto_import": bool(getattr(self.plugin, "worldbook_auto_import", False)),
            "match_aliases": bool(getattr(self.plugin, "worldbook_member_match_aliases", False)),
            "self_registration": bool(getattr(self.plugin, "worldbook_self_registration", False)),
            "auto_pending_observations": bool(getattr(self.plugin, "worldbook_auto_pending_observations", False)),
            "inject_limit": getattr(self.plugin, "worldbook_member_inject_limit", 0),
            "entry_count": len(entries),
            "member_count": len(profile_items),
            "enabled_member_count": sum(1 for item in profile_items if item.get("enabled", True)),
            "pending_observation_total": sum(self._clamp_int(item.get("pending_observation_count"), 0, 0, 999) for item in profile_items),
            "group_count": len(group_items),
            "last_import": self.plugin._format_timestamp_elapsed(state.get("last_import_at", 0)),
            "source_files": state.get("source_files") if isinstance(state.get("source_files"), list) else [],
            "members": profile_items[:120],
            "groups": group_items[:80],
        }

    def _normalize_important_memories(self, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        memories: list[dict[str, Any]] = []
        for raw in value[:12]:
            if not isinstance(raw, dict):
                continue
            content = str(raw.get("content") or "").strip()[:500]
            if not content:
                continue
            privacy = self._single_line(raw.get("privacy"), 20).lower()
            if privacy not in {"public", "private", "internal"}:
                privacy = "internal"
            memories.append(
                {
                    "title": self._single_line(raw.get("title"), 60),
                    "content": content,
                    "weight": self._clamp_int(raw.get("weight"), 50, 0, 100),
                    "privacy": privacy,
                    "source": self._single_line(raw.get("source"), 40),
                    "enabled": bool(raw.get("enabled", True)),
                    "updated_at": float(raw.get("updated_at") or time.time()),
                }
            )
        memories.sort(key=lambda item: (item.get("enabled", True), item.get("weight", 50), item.get("updated_at", 0)), reverse=True)
        return memories[:8]

    def _livingmemory_summary(self) -> dict[str, Any]:
        try:
            available = bool(self.plugin._livingmemory_available())
        except Exception:
            available = False
        try:
            plugin_dir = str(self.plugin._livingmemory_plugin_dir())
        except Exception:
            plugin_dir = ""
        try:
            status = self.plugin._format_livingmemory_status()
        except Exception:
            status = "LivingMemory：状态探测失败，已跳过协同。"
        return {
            "enabled": bool(available and getattr(self.plugin, "enable_livingmemory_integration", False)),
            "available": available,
            "tool_name": getattr(self.plugin, "livingmemory_tool_name", ""),
            "plugin_dir": plugin_dir,
            "status": status,
        }

    def _screen_companion_available(self) -> bool:
        getter = getattr(self.plugin, "_get_screen_companion_plugin", None)
        if callable(getter):
            try:
                return getter() is not None
            except Exception:
                return False
        return False

    def _screen_companion_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        available = self._screen_companion_available()
        context = data.get("screen_diary_context") if isinstance(data.get("screen_diary_context"), dict) else {}
        return {
            "enabled": bool(available and getattr(self.plugin, "enable_yesterday_screen_diary_context", False)),
            "available": available,
            "source": context.get("source", ""),
            "source_date": context.get("source_date", ""),
            "context_available": bool(context.get("available")),
            "summary_chars": len(str(context.get("summary") or "")),
        }

    def _bilibili_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        state = data.get("bilibili_integration") if isinstance(data.get("bilibili_integration"), dict) else {}
        try:
            available = bool(getattr(self.plugin, "_bilibili_available", lambda: False)())
        except Exception:
            available = False
        latest = None
        try:
            latest = self.plugin._latest_bilibili_video_candidate()
        except Exception:
            latest = None
        try:
            watch_log = str(getattr(self.plugin, "_bilibili_watch_log_file", lambda: "")())
        except Exception:
            watch_log = ""
        try:
            memory_api_available = bool(getattr(self.plugin, "_bilibili_memory_api_available", lambda: False)())
        except Exception:
            memory_api_available = False
        return {
            "enabled": bool(available and getattr(self.plugin, "enable_bilibili_integration", False)),
            "boredom_watch_enabled": bool(available and getattr(self.plugin, "enable_bilibili_boredom_watch", False)),
            "available": available,
            "memory_api_available": memory_api_available,
            "watch_log": watch_log,
            "last_boredom_watch_at": self.plugin._format_timestamp_elapsed(state.get("last_boredom_watch_at", 0)),
            "last_status": state.get("last_boredom_watch_status", ""),
            "latest_video": latest if isinstance(latest, dict) else {},
        }

    def _news_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        state = data.get("news_integration") if isinstance(data.get("news_integration"), dict) else {}
        digest = state.get("last_digest") if isinstance(state.get("last_digest"), dict) else {}
        latest_items = state.get("latest_items") if isinstance(state.get("latest_items"), list) else []
        ai_daily = state.get("ai_daily") if isinstance(state.get("ai_daily"), dict) else {}
        ai_digest = ai_daily.get("last_digest") if isinstance(ai_daily.get("last_digest"), dict) else {}
        ai_digest_items = ai_digest.get("items") if isinstance(ai_digest.get("items"), list) else []
        ai_digest_first_item = ai_digest_items[0] if ai_digest_items and isinstance(ai_digest_items[0], dict) else {}
        try:
            ai_text_chars = max(0, int(ai_daily.get("last_text_chars") or 0))
        except (TypeError, ValueError):
            ai_text_chars = 0
        if not ai_text_chars and ai_digest_first_item:
            ai_text_chars = len(str(ai_digest_first_item.get("article_text") or ""))
        try:
            ai_subtitle_chars = max(0, int(ai_daily.get("last_video_subtitle_chars") or 0))
        except (TypeError, ValueError):
            ai_subtitle_chars = 0
        if not ai_subtitle_chars and ai_digest_first_item:
            ai_subtitle_chars = len(str(ai_digest_first_item.get("video_subtitle_text") or ""))
        try:
            ai_video_context_chars = max(0, int(ai_daily.get("last_video_context_chars") or 0))
        except (TypeError, ValueError):
            ai_video_context_chars = 0
        if not ai_video_context_chars and ai_digest_first_item:
            ai_video_context_chars = len(str(ai_digest_first_item.get("video_context_text") or ""))
        try:
            ai_video_duration = max(0, int(ai_daily.get("last_video_duration") or ai_digest_first_item.get("video_duration") or 0))
        except (TypeError, ValueError):
            ai_video_duration = 0
        ai_video_tags_raw = ai_daily.get("last_video_tags") if isinstance(ai_daily.get("last_video_tags"), list) else ai_digest_first_item.get("video_tags")
        ai_video_tags = [
            self._single_line(tag, 40)
            for tag in ai_video_tags_raw
            if self._single_line(tag, 40)
        ] if isinstance(ai_video_tags_raw, list) else []
        ai_video_comments_raw = ai_daily.get("last_video_hot_comments") if isinstance(ai_daily.get("last_video_hot_comments"), list) else ai_digest_first_item.get("video_hot_comments")
        ai_video_comments = [
            self._single_line(comment, 120)
            for comment in ai_video_comments_raw
            if self._single_line(comment, 120)
        ] if isinstance(ai_video_comments_raw, list) else []
        try:
            source_count = len(getattr(self.plugin, "_news_source_items", lambda: [])())
        except Exception:
            source_count = 0
        return {
            "enabled": bool(getattr(self.plugin, "enable_news_integration", False)),
            "boredom_read_enabled": bool(getattr(self.plugin, "enable_news_boredom_read", False)),
            "daily_hot_enabled": bool(getattr(self.plugin, "enable_news_daily_hot_read", False)),
            "ai_daily_enabled": bool(getattr(self.plugin, "enable_ai_daily_watch", False)),
            "source_count": source_count,
            "last_read_at": self.plugin._format_timestamp_elapsed(state.get("last_read_at", 0)),
            "last_status": self._single_line(state.get("last_status"), 80),
            "ai_daily": {
                "status": self._single_line(ai_daily.get("status"), 80),
                "date": self._single_line(ai_daily.get("date"), 20),
                "last_checked_at": self.plugin._format_timestamp_elapsed(ai_daily.get("last_checked_at", 0)),
                "last_success_date": self._single_line(ai_daily.get("last_success_date"), 20),
                "last_source_name": self._single_line(ai_daily.get("last_source_name"), 40),
                "last_source_author": self._single_line(ai_daily.get("last_source_author"), 60),
                "last_source_mid": self._single_line(ai_daily.get("last_source_mid"), 40),
                "last_source_schedule": self._single_line(ai_daily.get("last_source_schedule"), 10),
                "last_video_title": self._single_line(ai_daily.get("last_video_title"), 120),
                "last_video_link": self._single_line(ai_daily.get("last_video_link"), 400),
                "last_video_owner_name": self._single_line(ai_daily.get("last_video_owner_name") or ai_digest_first_item.get("video_owner_name"), 80),
                "last_video_tname": self._single_line(ai_daily.get("last_video_tname") or ai_digest_first_item.get("video_tname"), 60),
                "last_video_duration": ai_video_duration,
                "last_video_context_chars": ai_video_context_chars,
                "last_video_tags": ai_video_tags[:10],
                "last_video_hot_comments": ai_video_comments[:5],
                "last_text_link": self._single_line(ai_daily.get("last_text_link"), 400),
                "last_text_readable": bool(ai_daily.get("last_text_readable")) if "last_text_readable" in ai_daily else bool(ai_digest_first_item.get("article_readable") and ai_digest_first_item.get("article_text")),
                "last_text_chars": ai_text_chars,
                "last_video_subtitle_readable": bool(ai_daily.get("last_video_subtitle_readable")) if "last_video_subtitle_readable" in ai_daily else bool(ai_digest_first_item.get("video_subtitle_readable") and ai_digest_first_item.get("video_subtitle_text")),
                "last_video_subtitle_chars": ai_subtitle_chars,
                "last_video_subtitle_status": self._single_line(ai_daily.get("last_video_subtitle_status") or ai_digest_first_item.get("video_subtitle_status"), 40),
                "last_read_basis": self._single_line(ai_daily.get("last_read_basis"), 40),
                "sources": [
                    {
                        "key": self._single_line(item.get("key"), 80),
                        "name": self._single_line(item.get("name"), 40),
                        "author_name": self._single_line(item.get("author_name"), 60),
                        "mid": self._single_line(item.get("mid"), 40),
                        "schedule": self._single_line(item.get("schedule"), 10),
                    }
                    for item in (ai_daily.get("sources") if isinstance(ai_daily.get("sources"), list) else [])
                    if isinstance(item, dict)
                ],
                "source_states": {
                    self._single_line(key, 80): {
                        "name": self._single_line(value.get("name"), 40),
                        "author_name": self._single_line(value.get("author_name"), 60),
                        "mid": self._single_line(value.get("mid"), 40),
                        "schedule": self._single_line(value.get("schedule"), 10),
                        "status": self._single_line(value.get("status"), 80),
                        "last_checked_at": self.plugin._format_timestamp_elapsed(value.get("last_checked_at", 0)),
                        "last_success_date": self._single_line(value.get("last_success_date"), 20),
                        "last_video_title": self._single_line(value.get("last_video_title"), 120),
                    }
                    for key, value in (ai_daily.get("source_states") if isinstance(ai_daily.get("source_states"), dict) else {}).items()
                    if isinstance(value, dict)
                },
                "topic": self._single_line(ai_digest.get("topic"), 60),
                "headline": self._single_line(ai_digest.get("headline"), 120),
            },
            "last_digest": {
                "topic": self._single_line(digest.get("topic"), 60),
                "headline": self._single_line(digest.get("headline"), 120),
                "source": self._single_line(digest.get("selected_source"), 40),
                "impression": self._single_line(digest.get("impression"), 180),
                "link": self._single_line(digest.get("selected_link"), 400),
            },
            "latest_items": [
                {
                    "source": self._single_line(item.get("source"), 40),
                    "title": self._single_line(item.get("title"), 120),
                    "summary": self._single_line(item.get("summary"), 160),
                    "link": self._single_line(item.get("link"), 400),
                }
                for item in latest_items[:8]
                if isinstance(item, dict)
            ],
        }

    def _web_exploration_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        state = data.get("web_exploration") if isinstance(data.get("web_exploration"), dict) else {}
        digest = state.get("last_digest") if isinstance(state.get("last_digest"), dict) else {}
        notes = state.get("notes") if isinstance(state.get("notes"), list) else []
        history = self._browsing_history_entries(data)
        try:
            available = bool(getattr(self.plugin, "_astrbot_any_web_search_available", lambda: False)())
        except Exception:
            available = False
        return {
            "enabled": bool(getattr(self.plugin, "enable_web_exploration", False)),
            "boredom_search_enabled": bool(getattr(self.plugin, "enable_web_exploration_boredom_search", False)),
            "available": available,
            "last_explore_at": self.plugin._format_timestamp_elapsed(state.get("last_explore_at", 0)),
            "last_status": self._single_line(state.get("last_status"), 80),
            "last_query": {
                "query": self._single_line((state.get("last_query") or {}).get("query") if isinstance(state.get("last_query"), dict) else "", 80),
                "reason": self._single_line((state.get("last_query") or {}).get("reason") if isinstance(state.get("last_query"), dict) else "", 120),
                "topic": self._single_line((state.get("last_query") or {}).get("topic") if isinstance(state.get("last_query"), dict) else "", 20),
            },
            "last_digest": {
                "topic": self._single_line(digest.get("topic"), 80),
                "note": self._single_line(digest.get("note"), 220),
                "source_title": self._single_line(digest.get("source_title"), 120),
                "source_url": self._single_line(digest.get("source_url"), 400),
            },
            "note_count": len(notes),
            "history_count": len(history),
            "history": history,
            "recent_notes": [
                {
                    "topic": self._single_line(item.get("topic"), 80),
                    "note": self._single_line(item.get("note"), 180),
                    "query": self._single_line(item.get("query"), 80),
                    "created_at": self.plugin._format_timestamp_elapsed(item.get("created_ts", 0)),
                }
                for item in notes[-8:]
                if isinstance(item, dict)
            ],
        }

    def _browsing_history_entries(self, data: dict[str, Any]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        news_state = data.get("news_integration") if isinstance(data.get("news_integration"), dict) else {}
        news_digest = news_state.get("last_digest") if isinstance(news_state.get("last_digest"), dict) else {}
        news_digests = news_state.get("digests") if isinstance(news_state.get("digests"), list) else []
        news_items = [item for item in news_digests if isinstance(item, dict)]
        if news_digest and not any(
            self._single_line(item.get("selected_key"), 32) == self._single_line(news_digest.get("selected_key"), 32)
            and self._float(item.get("created_ts")) == self._float(news_digest.get("created_ts"))
            for item in news_items
        ):
            news_items.append(news_digest)
        for news_digest in news_items:
            headline = self._single_line(news_digest.get("headline") or news_digest.get("topic"), 120)
            impression = self._single_line(news_digest.get("impression"), 1000)
            selected_source = self._single_line(news_digest.get("selected_source"), 40)
            selected_link = self._single_line(news_digest.get("selected_link"), 400)
            created_ts = self._float(news_digest.get("created_ts"))
            entries.append(
                {
                    "_ts": created_ts,
                    "source": "news",
                    "source_label": "新闻阅读",
                    "date": self.plugin._format_timestamp_elapsed(created_ts) or "今日新闻",
                    "generated_at": self.plugin._format_timestamp_elapsed(created_ts),
                    "title": headline or "新闻阅读",
                    "query": "",
                    "intro": impression or "这次新闻阅读没有留下明显印象。",
                    "content": "\n\n".join(
                        part
                        for part in (
                            f"新闻见闻：{headline}" if headline else "",
                            impression,
                            f"来源：{selected_source}" if selected_source else "",
                            f"链接：{selected_link}" if selected_link else "",
                        )
                        if part
                    ) or "这次新闻阅读没有留下正文。",
                    "source_title": selected_source,
                    "source_url": selected_link,
                    "tags": ["新闻阅读"],
                }
            )
        web_state = data.get("web_exploration") if isinstance(data.get("web_exploration"), dict) else {}
        web_notes = web_state.get("notes") if isinstance(web_state.get("notes"), list) else []
        web_items = [note for note in web_notes if isinstance(note, dict)]
        last_digest = web_state.get("last_digest") if isinstance(web_state.get("last_digest"), dict) else {}
        if last_digest:
            last_key = "|".join(
                self._single_line(last_digest.get(key), 120)
                for key in ("query", "topic", "created_ts")
            )
            if not any(
                "|".join(
                    self._single_line(item.get(key), 120)
                    for key in ("query", "topic", "created_ts")
                ) == last_key
                for item in web_items
            ):
                web_items.append(last_digest)
        for item in web_items:
            topic = self._single_line(item.get("topic"), 100)
            query = self._single_line(item.get("query"), 100)
            note = self._single_line(
                item.get("note")
                or item.get("summary")
                or item.get("impression")
                or item.get("content"),
                1000,
            )
            source_title = self._single_line(item.get("source_title"), 120)
            source_url = self._single_line(item.get("source_url"), 400)
            created_ts = self._float(item.get("created_ts"))
            result_lines = []
            raw_results = item.get("results") if isinstance(item.get("results"), list) else []
            for result in raw_results[:4]:
                if not isinstance(result, dict):
                    continue
                title = self._single_line(result.get("title"), 100)
                snippet = self._single_line(result.get("snippet"), 180)
                if title and snippet:
                    result_lines.append(f"{title}：{snippet}")
                elif title:
                    result_lines.append(title)
                elif snippet:
                    result_lines.append(snippet)
            result_excerpt = self._single_line("；".join(result_lines), 1000)
            if not note:
                note = result_excerpt
            entries.append(
                {
                    "_ts": created_ts,
                    "source": self._single_line(item.get("source"), 40) or "web_exploration",
                    "source_label": self._single_line(item.get("source_label"), 40) or "主动搜索",
                    "date": self.plugin._format_timestamp_elapsed(created_ts) or "某次搜索",
                    "generated_at": self.plugin._format_timestamp_elapsed(created_ts),
                    "title": topic or query or "主动搜索",
                    "query": query,
                    "intro": note or "这次搜索没有留下明显印象。",
                    "content": "\n\n".join(
                        part
                        for part in (
                            f"搜索词：{query}" if query else "",
                            f"搜索动机：{self._single_line(item.get('reason'), 160)}" if self._single_line(item.get("reason"), 160) else "",
                            f"笔记：{note}" if note else "",
                            f"结果摘录：{result_excerpt}" if result_excerpt and result_excerpt != note else "",
                            f"主要来源：{source_title}" if source_title else "",
                            f"链接：{source_url}" if source_url else "",
                        )
                        if part
                    ) or "这次主动搜索没有留下正文。",
                    "source_title": source_title,
                    "source_url": source_url,
                    "tags": ["主动搜索"],
                }
            )
        entries.sort(key=lambda item: self._float(item.get("_ts")))
        for item in entries:
            item.pop("_ts", None)
        return entries

    def _qzone_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        state = data.get("qzone_integration") if isinstance(data.get("qzone_integration"), dict) else {}
        try:
            available = bool(getattr(self.plugin, "_qzone_available", lambda: False)())
        except Exception:
            available = False
        return {
            "enabled": bool(available and getattr(self.plugin, "enable_qzone_integration", False)),
            "life_publish_enabled": bool(available and getattr(self.plugin, "enable_qzone_life_publish", False)),
            "emotional_vent_enabled": bool(
                available
                and getattr(self.plugin, "enable_emotion_simulation", False)
                and getattr(self.plugin, "enable_qzone_emotional_vent_publish", False)
            ),
            "available": available,
            "last_life_publish_at": self.plugin._format_timestamp_elapsed(state.get("last_life_publish_at", 0)),
            "last_status": state.get("last_life_publish_status", ""),
            "last_text": state.get("last_life_publish_text", ""),
            "last_emotional_vent_at": self.plugin._format_timestamp_elapsed(state.get("last_emotional_vent_at", 0)),
            "last_emotional_vent_status": state.get("last_emotional_vent_status", ""),
            "last_emotional_vent_text": state.get("last_emotional_vent_text", ""),
        }

    def _jm_cosmos_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        state = data.get("jm_cosmos_integration") if isinstance(data.get("jm_cosmos_integration"), dict) else {}
        try:
            available = bool(getattr(self.plugin, "_jm_cosmos_available", lambda: False)())
        except Exception:
            available = False
        album = state.get("last_album") if isinstance(state.get("last_album"), dict) else {}
        return {
            "enabled": bool(available and getattr(self.plugin, "enable_jm_cosmos_integration", False)),
            "boredom_read_enabled": bool(available and getattr(self.plugin, "enable_jm_cosmos_boredom_read", False)),
            "ask_recommendation_enabled": bool(available and getattr(self.plugin, "enable_private_reading_ask_recommendation", False)),
            "available": available,
            "last_read_at": self.plugin._format_timestamp_elapsed(state.get("last_read_at", 0)),
            "last_status": state.get("last_status", ""),
            "last_keyword": state.get("last_keyword", ""),
            "last_album": {
                "id": self._single_line(album.get("id"), 32),
                "title": self._single_line(album.get("title"), 100),
                "impression": self._single_line(album.get("impression"), 160),
                "rating": self._int(album.get("rating")),
                "user_rating": self._int(album.get("user_rating")),
            },
        }

    def _bookshelf_image_url(
        self,
        album_id: str,
        *,
        data_root: Path,
        page_index: int = 0,
        cover: bool = False,
        path_value: Any = "",
        access_token: str = "",
    ) -> str:
        if not album_id or (page_index < 1 and not cover):
            return ""
        url = f"{PAGE_API_PREFIX}/bookshelf/image?album_id={quote(str(album_id), safe='')}"
        if cover:
            url += "&cover=1"
        elif page_index > 0:
            url += f"&page={page_index}"
        if access_token:
            url += f"&access_token={quote(str(access_token), safe='')}"
        raw_path = self._single_line(path_value, 500)
        if raw_path:
            try:
                path = Path(raw_path).resolve()
                path.relative_to(data_root)
                if path.exists() and path.is_file():
                    stat = path.stat()
                    url += f"&v={int(stat.st_mtime)}-{stat.st_size}"
            except Exception:
                pass
        return url

    def _bookshelf_cover_url(
        self,
        album_id: str,
        item: dict[str, Any],
        page_items: list[dict[str, Any]],
        data_root: Path,
        *,
        access_token: str = "",
    ) -> str:
        cover_path = self._single_line(item.get("cover_path"), 500)
        if cover_path:
            return self._bookshelf_image_url(
                album_id,
                data_root=data_root,
                cover=True,
                path_value=cover_path,
                access_token=access_token,
            )
        first_page = page_items[0] if page_items else {}
        if isinstance(first_page, dict):
            return self._single_line(first_page.get("src"), 500)
        return ""

    async def _bookshelf_summary(self, data: dict[str, Any], *, unlocked: bool, access_token: str = "") -> dict[str, Any]:
        projects = data.get("creative_projects") if isinstance(data.get("creative_projects"), list) else []
        diaries = data.get("bot_diaries") if isinstance(data.get("bot_diaries"), list) else []
        shelf_items = data.get("bookshelf_items") if isinstance(data.get("bookshelf_items"), list) else []
        jm_items = [item for item in shelf_items if isinstance(item, dict) and item.get("type") == "jm_album"]
        jm_state = data.get("jm_cosmos_integration") if isinstance(data.get("jm_cosmos_integration"), dict) else {}
        last_album = jm_state.get("last_album") if isinstance(jm_state.get("last_album"), dict) else {}
        if last_album and not any(str(item.get("album_id") or item.get("id") or "") == str(last_album.get("id") or "") for item in jm_items):
            jm_items.append(
                {
                    "type": "jm_album",
                    "title": last_album.get("title"),
                    "album_id": last_album.get("id"),
                    "description": last_album.get("description") or last_album.get("intro") or last_album.get("summary"),
                    "keyword": last_album.get("keyword"),
                    "author": last_album.get("author"),
                    "tags": last_album.get("tags"),
                    "photo_count": last_album.get("photo_count"),
                    "impression": last_album.get("impression"),
                    "reading_impression": last_album.get("reading_impression") or last_album.get("impression"),
                    "vision": last_album.get("vision"),
                    "rating": last_album.get("rating"),
                    "rating_reason": last_album.get("rating_reason"),
                    "user_rating": last_album.get("user_rating"),
                    "user_rating_reason": last_album.get("user_rating_reason"),
                    "user_rated_ts": last_album.get("user_rated_ts"),
                    "preference_tags": last_album.get("preference_tags") if isinstance(last_album.get("preference_tags"), list) else [],
                    "user_liked_tags": last_album.get("user_liked_tags") if isinstance(last_album.get("user_liked_tags"), list) else [],
                    "user_disliked_tags": last_album.get("user_disliked_tags") if isinstance(last_album.get("user_disliked_tags"), list) else [],
                    "user_tags_updated_ts": last_album.get("user_tags_updated_ts"),
                    "page_comments": last_album.get("page_comments") if isinstance(last_album.get("page_comments"), list) else [],
                    "image_count": last_album.get("image_count"),
                    "pages": last_album.get("pages") if isinstance(last_album.get("pages"), list) else [],
                    "sampled_pages": last_album.get("sampled_pages") if isinstance(last_album.get("sampled_pages"), list) else [],
                    "created_ts": last_album.get("created_ts"),
                }
            )
        data_root = Path(str(getattr(self.plugin, "data_dir", ""))).resolve()
        pages_root = data_root / "bookshelf_pages"
        covers_root = data_root / "jm_cosmos_covers"
        known_jm_ids = {
            self._single_line(item.get("album_id") or item.get("id"), 80)
            for item in jm_items
            if isinstance(item, dict) and self._single_line(item.get("album_id") or item.get("id"), 80)
        }
        preference_history = []
        profile = jm_state.get("preference_profile") if isinstance(jm_state.get("preference_profile"), dict) else {}
        if isinstance(profile.get("history"), list):
            preference_history = [item for item in profile.get("history", []) if isinstance(item, dict)]
        history_by_album: dict[str, dict[str, Any]] = {}
        for item in preference_history:
            album_id = self._single_line(item.get("album_id") or item.get("id"), 80)
            if album_id:
                history_by_album[album_id] = {**history_by_album.get(album_id, {}), **item}
        try:
            orphan_dirs = [
                path
                for path in pages_root.iterdir()
                if path.is_dir() and self._single_line(path.name, 80) and self._single_line(path.name, 80) not in known_jm_ids
            ] if pages_root.exists() else []
        except Exception:
            orphan_dirs = []
        for path in orphan_dirs:
            album_id = self._single_line(path.name, 80)
            page_files = sorted(
                file
                for file in path.iterdir()
                if file.is_file() and file.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif"}
            )
            if not album_id or not page_files:
                continue
            meta = history_by_album.get(album_id, {})
            created_ts = self._float(meta.get("created_ts")) or max((file.stat().st_mtime for file in page_files), default=0.0)
            cover_path = covers_root / f"{album_id}.jpg"
            jm_items.append(
                {
                    "type": "jm_album",
                    "album_id": album_id,
                    "title": meta.get("title") or f"私密阅读 {album_id}",
                    "description": meta.get("reason") or "",
                    "tags": meta.get("terms") if isinstance(meta.get("terms"), list) else [],
                    "rating": meta.get("bot_rating") or meta.get("rating"),
                    "user_rating": meta.get("user_rating"),
                    "rating_reason": meta.get("reason") or "",
                    "user_rating_reason": meta.get("reason") or "",
                    "cover_path": str(cover_path) if cover_path.exists() else "",
                    "pages": [
                        {
                            "index": index + 1,
                            "path": str(file),
                            "name": file.name,
                        }
                        for index, file in enumerate(page_files)
                    ],
                    "image_count": len(page_files),
                    "created_ts": created_ts,
                    "source": "bookshelf_orphan_recovered",
                    "locked": True,
                }
            )
        public_books = []
        browsing_entries = self._browsing_history_entries(data)
        for item in [project for project in projects if isinstance(project, dict)][-12:]:
            chunks = item.get("draft_chunks") if isinstance(item.get("draft_chunks"), list) else []
            full_text = "\n\n".join(
                self._single_line(chunk.get("text"), 2000)
                for chunk in chunks
                if isinstance(chunk, dict) and self._single_line(chunk.get("text"), 2000)
            )
            chunk_entries = [
                {
                    "index": index + 1,
                    "text": self._single_line(chunk.get("text"), 2000),
                    "created": self.plugin._format_timestamp_elapsed(chunk.get("created_ts", 0) or chunk.get("created_at", 0)),
                }
                for index, chunk in enumerate(chunks)
                if isinstance(chunk, dict) and self._single_line(chunk.get("text"), 2000)
            ]
            status = self._single_line(item.get("status"), 24)
            progress = f"{self._int(item.get('current_chars'))}/{self._int(item.get('target_chars')) or '-'} 字"
            public_books.append(
                {
                    "id": self._single_line(item.get("id"), 32) or f"creative-{len(public_books)}",
                    "kind": "creative",
                    "category": self._single_line(item.get("work_type"), 30) or "创作",
                    "work_type": self._single_line(item.get("work_type"), 30) or "短篇小说",
                    "title": self._single_line(item.get("title"), 60) or "未定标题",
                    "intro": self._single_line(item.get("premise"), 240) or "这本书还没整理出简介。",
                    "status": status,
                    "tone": self._single_line(item.get("tone"), 40),
                    "point_of_view": self._single_line(item.get("point_of_view"), 40) or "第三人称有限视角",
                    "progress": progress,
                    "content": full_text or self._single_line(chunks[-1].get("text") if chunks else "", 2000) or "这本书还没有正文。",
                    "chunks": chunk_entries,
                    "created": self.plugin._format_timestamp_elapsed(item.get("created_at", 0)),
                }
            )
        if browsing_entries:
            latest = browsing_entries[-1]
            public_books.append(
                {
                    "id": "browsing-history-main",
                    "kind": "browsing",
                    "category": "浏览记录",
                    "title": "浏览记录",
                    "intro": f"这里收着 {len(browsing_entries)} 条新闻阅读和主动搜索记录。打开后可以选择记录。",
                    "content": self._single_line(latest.get("content"), 2000) or self._single_line(latest.get("intro"), 1200),
                    "entries": browsing_entries,
                    "created": self._single_line(latest.get("generated_at") or latest.get("date"), 32),
                    "progress": f"{len(browsing_entries)} 条记录",
                    "tags": ["新闻阅读", "主动搜索"],
                }
            )
        locked_count = (1 if diaries else 0) + len(jm_items)
        secret_books: list[dict[str, Any]] = []
        if unlocked:
            diary_entries = []
            for item in [entry for entry in diaries if isinstance(entry, dict)][-60:]:
                body = self._single_line(item.get("body"), 1600)
                summary = self._single_line(item.get("summary"), 1000)
                share_seed = self._single_line(item.get("share_seed"), 1000)
                content = body or "\n\n".join(part for part in (summary, share_seed) if part)
                diary_entries.append(
                    {
                        "date": self._single_line(item.get("date"), 24) or "某天",
                        "generated_at": self._single_line(item.get("generated_at"), 32),
                        "title": f"{self._single_line(item.get('date'), 24) or '某天'}",
                        "intro": summary or "这一天没有留下摘要。",
                        "content": content or "这一天的日记暂时没有写出正文。",
                        "tags": [self._single_line(tag, 24) for tag in item.get("tags", [])[:8] if self._single_line(tag, 24)]
                        if isinstance(item.get("tags"), list)
                        else [],
                    }
                )
            if diary_entries:
                secret_books.append(
                    {
                        "id": "diary-main",
                        "kind": "diary",
                        "category": "日记",
                        "title": "日记本",
                        "intro": f"这里收着 {len(diary_entries)} 天的日记。打开后可以选择日期。",
                        "content": diary_entries[-1].get("content") or "这本日记暂时没有可读内容。",
                        "entries": diary_entries,
                        "created": diary_entries[-1].get("generated_at", ""),
                    }
            )
            recent_jm_items = sorted(
                jm_items,
                key=lambda item: self._float(item.get("created_ts") or item.get("created_at") or item.get("ts")),
                reverse=True,
            )[:18]
            for item in recent_jm_items:
                album_id = self._single_line(item.get("album_id") or item.get("id"), 32)
                pages = item.get("pages") if isinstance(item.get("pages"), list) else []
                reading_impression = self._single_line(item.get("reading_impression") or item.get("impression"), 1000)
                vision_impression = self._single_line(item.get("vision"), 1000)
                bot_rating = self._int(item.get("rating"))
                user_rating = self._int(item.get("user_rating"))
                rating_reason = self._single_line(item.get("rating_reason"), 180)
                user_rating_reason = self._single_line(item.get("user_rating_reason"), 180)
                album_description = self._single_line(
                    item.get("description")
                    or item.get("intro")
                    or item.get("summary")
                    or item.get("desc"),
                    600,
                )
                if not album_description:
                    detail_parts = []
                    author_text = self._single_line(item.get("author"), 40)
                    photo_count = self._int(item.get("photo_count")) or self._int(item.get("image_count"))
                    tag_text = "、".join(
                        self._single_line(tag, 24)
                        for tag in (item.get("tags") if isinstance(item.get("tags"), list) else [])[:6]
                        if self._single_line(tag, 24)
                    )
                    if author_text:
                        detail_parts.append(f"作者：{author_text}")
                    if photo_count:
                        detail_parts.append(f"页数：{photo_count}")
                    if tag_text:
                        detail_parts.append(f"标签：{tag_text}")
                    album_description = "；".join(detail_parts) or "这条阅读记录暂时没有整理出明确简介。"
                page_comment_map: dict[int, list[str]] = {}
                raw_comments = self._merge_bookshelf_page_comments(
                    item.get("page_comments") if isinstance(item.get("page_comments"), list) else [],
                    item.get("page_comments_previous") if isinstance(item.get("page_comments_previous"), list) else [],
                    limit=32,
                )
                for comment_item in raw_comments:
                    if not isinstance(comment_item, dict):
                        continue
                    page_no = self._int(comment_item.get("page"))
                    comment_text = self._single_line(comment_item.get("comment"), 100)
                    if page_no > 0 and comment_text:
                        page_comments = page_comment_map.setdefault(page_no, [])
                        if comment_text not in page_comments:
                            page_comments.append(comment_text)
                page_items = []
                for page in pages:
                    if not isinstance(page, dict):
                        continue
                    index = self._int(page.get("index"))
                    if index <= 0:
                        continue
                    page_src = self._bookshelf_image_url(
                        album_id,
                        data_root=data_root,
                        page_index=index,
                        path_value=page.get("path"),
                        access_token=access_token,
                    )
                    page_items.append(
                        {
                            "index": index,
                            "src": page_src,
                            "comment": "\n".join(page_comment_map.get(index, [])),
                        }
                    )
                cover_src = ""
                if album_id:
                    cover_src = self._bookshelf_cover_url(album_id, item, page_items, data_root, access_token=access_token)
                secret_books.append(
                    {
                        "id": f"jm-{album_id or len(secret_books)}",
                        "kind": "jm_album",
                        "category": "私密阅读",
                        "album_id": album_id,
                        "title": self._single_line(item.get("title"), 100) or "未命名阅读记录",
                        "intro": self._single_line(album_description, 600),
                        "reading_impression": reading_impression or vision_impression,
                        "rating": bot_rating,
                        "rating_reason": rating_reason,
                        "user_rating": user_rating,
                        "user_rating_reason": user_rating_reason,
                        "user_rated": bool(user_rating),
                        "author": self._single_line(item.get("author"), 40),
                        "progress": f"{len(page_items) or self._int(item.get('image_count')) or self._int(item.get('photo_count'))} 页",
                        "created": self.plugin._format_timestamp_elapsed(item.get("created_ts", 0)),
                        "content": "\n\n".join(
                            part
                            for part in (
                                f"读后感：{reading_impression}" if reading_impression else "",
                                f"Bot 评分：{bot_rating}/10" if bot_rating else "",
                                f"用户评分：{user_rating}/10" if user_rating else "",
                                f"评分理由：{user_rating_reason or rating_reason}" if (user_rating_reason or rating_reason) else "",
                                f"画面记录：{vision_impression}" if vision_impression and vision_impression != reading_impression else "",
                                f"关键词：{self._single_line(item.get('keyword'), 80)}" if self._single_line(item.get("keyword"), 80) else "",
                            )
                            if part
                        ) or "这本只留下了一点很含糊的阅读印象。",
                        "tags": [self._single_line(tag, 24) for tag in item.get("tags", [])[:8] if self._single_line(tag, 24)]
                        if isinstance(item.get("tags"), list)
                        else [],
                        "preference_tags": [
                            self._single_line(tag, 24)
                            for tag in (item.get("preference_tags") if isinstance(item.get("preference_tags"), list) else [])[:8]
                            if self._single_line(tag, 24)
                        ],
                        "user_liked_tags": [
                            self._single_line(tag, 24)
                            for tag in (item.get("user_liked_tags") if isinstance(item.get("user_liked_tags"), list) else [])[:8]
                            if self._single_line(tag, 24)
                        ],
                        "user_disliked_tags": [
                            self._single_line(tag, 24)
                            for tag in (item.get("user_disliked_tags") if isinstance(item.get("user_disliked_tags"), list) else [])[:8]
                            if self._single_line(tag, 24)
                        ],
                        "user_tags_updated": bool(item.get("user_tags_updated_ts")),
                        "cover_src": cover_src,
                        "pages": page_items,
                        "page_comment_count": sum(len(comments) for comments in page_comment_map.values()),
                        "page_comments": [
                            {"page": page, "comment": comment}
                            for page, comments in sorted(page_comment_map.items())
                            for comment in comments
                        ],
                    }
                )
        return {
            "unlocked": unlocked,
            "access_token": access_token if unlocked and self._bookshelf_access_token_valid(access_token) else "",
            "access_expires_in": int(max(0, self._bookshelf_access_tokens().get(access_token, 0) - time.time()))
            if unlocked and access_token
            else 0,
            "public_count": len(public_books),
            "secret_count": locked_count,
            "diary_count": 1 if diaries else 0,
            "jm_album_count": len(jm_items),
            "public_books": public_books,
            "secret_books": secret_books,
        }

    def _proactive_candidate_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        raw = data.get("proactive_candidate_pool") if isinstance(data.get("proactive_candidate_pool"), list) else []
        users = data.get("users") if isinstance(data.get("users"), dict) else {}
        now = time.time()
        buckets: list[dict[str, Any]] = []
        counts: dict[str, int] = {}
        source_counts: dict[str, int] = {}
        user_counts: dict[str, dict[str, Any]] = {}
        total_attempts = 0

        def candidate_user_meta(user_id: str, user: Any) -> dict[str, str]:
            if not isinstance(user, dict):
                return {"label": user_id or "未知用户", "role": "unknown", "role_label": "未知"}
            role = self.plugin._private_user_role(user, user_id) if hasattr(self.plugin, "_private_user_role") else ""
            role_labeler = getattr(self.plugin, "_private_user_role_label", None)
            role_label = role_labeler(role) if callable(role_labeler) else ("主人" if role == "owner" else "朋友")
            nickname = self._single_line(user.get("nickname"), 40)
            generic_names = {"用户", "主人", "默认用户"}
            if str(user_id).isdigit():
                label = nickname if nickname and nickname not in generic_names else user_id
            else:
                label = f"临时会话 · {str(user_id)[:8]}"
            return {"label": label or user_id or "未知用户", "role": role or "friend", "role_label": role_label}

        for item in raw[-240:]:
            if not isinstance(item, dict):
                continue
            repeat_count = max(1, self._int(item.get("repeat_count")))
            status = self._single_line(item.get("status"), 24) or "unknown"
            note = self._single_line(item.get("note"), 160)
            if status == "blocked" and note == "朋友关系不接收敏感主动":
                continue
            user_id = self._single_line(item.get("user_id"), 32)
            user = users.get(user_id) if isinstance(users, dict) else None
            reason_raw = self._single_line(item.get("reason"), 40)
            action_raw = self._single_line(item.get("action"), 40)
            if (
                isinstance(user, dict)
                and hasattr(self.plugin, "_friend_can_receive_proactive_reason")
                and not self.plugin._friend_can_receive_proactive_reason(user, reason_raw, action_raw)
            ):
                continue
            if status != "sent" and not bool(
                isinstance(user, dict)
                and getattr(self.plugin, "_user_enabled_for_proactive", lambda uid, profile: bool(profile and profile.get("enabled", True)))(
                    user_id,
                    user,
                )
            ):
                continue
            total_attempts += repeat_count
            user_meta = candidate_user_meta(user_id, user)
            user_bucket = user_counts.setdefault(
                user_id or "unknown",
                {
                    "user_id": user_id,
                    "label": user_meta["label"],
                    "role": user_meta["role"],
                    "role_label": user_meta["role_label"],
                    "total": 0,
                    "counts": {},
                },
            )
            user_bucket["total"] = self._int(user_bucket.get("total")) + repeat_count
            bucket_counts = user_bucket.get("counts")
            if not isinstance(bucket_counts, dict):
                bucket_counts = {}
                user_bucket["counts"] = bucket_counts
            bucket_counts[status] = self._int(bucket_counts.get(status)) + repeat_count
            source = self._single_line(item.get("source"), 40) or "unknown"
            display_source = "bookshelf_reading" if source == "jm_cosmos" else source
            counts[status] = counts.get(status, 0) + repeat_count
            source_counts[display_source] = source_counts.get(display_source, 0) + repeat_count
            scheduled = self._float(item.get("scheduled_ts"))
            created = self._float(item.get("created_ts"))
            last_seen = self._float(item.get("last_seen_ts")) or created
            reason = reason_raw
            action = action_raw
            if reason == "jm_cosmos_share":
                reason = "bookshelf_reading_share"
            if reason == "jm_cosmos_recommendation_request":
                reason = "bookshelf_recommendation_request"
            if action == "jm_cosmos_read":
                action = "bookshelf_reading"
            signature = self._single_line(item.get("signature"), 120)
            topic = self._single_line(item.get("topic"), 100)
            motive = self._single_line(item.get("motive"), 180)
            sanitizer = getattr(self.plugin, "_sanitize_friend_proactive_plan_fields", None)
            if isinstance(user, dict) and callable(sanitizer):
                sanitized = sanitizer(
                    user,
                    reason=reason,
                    action=action,
                    topic=topic,
                    motive=motive,
                )
                reason = self._single_line(sanitized.get("reason"), 40) or reason
                action = self._single_line(sanitized.get("action"), 40) or action
                topic = self._single_line(sanitized.get("topic"), 100)
                motive = self._single_line(sanitized.get("motive"), 180)
            merged = None
            for existing in reversed(buckets):
                if existing.get("status") != status:
                    continue
                if existing.get("user_id") != user_id:
                    continue
                old_signature = str(existing.get("_signature") or "")
                if signature and old_signature:
                    similar = bool(getattr(self.plugin, "_topic_signature_similar", lambda a, b: a == b)(signature, old_signature))
                else:
                    similar = (topic or motive) == (existing.get("topic") or existing.get("motive"))
                if not similar:
                    continue
                if max(last_seen, scheduled, created) - self._float(existing.get("_first_ts")) > 36 * 3600:
                    continue
                merged = existing
                break
            if merged is None:
                buckets.append(
                    {
                        "id": self._single_line(item.get("id"), 20),
                        "user_id": user_id,
                        "user_label": user_meta["label"],
                        "user_role": user_meta["role"],
                        "user_role_label": user_meta["role_label"],
                        "source": display_source,
                        "reason": reason,
                        "action": action,
                        "topic": topic,
                        "motive": motive,
                        "score": self._int(item.get("score")),
                        "status": status,
                        "note": note,
                        "repeat_count": repeat_count,
                        "created_ts": created,
                        "last_seen_ts": last_seen,
                        "scheduled_ts": scheduled,
                        "is_due": bool(scheduled and scheduled <= now),
                        "_signature": signature,
                        "_first_ts": max(created, scheduled, last_seen),
                    }
                )
                continue
            merged["repeat_count"] = self._int(merged.get("repeat_count")) + repeat_count
            merged["last_seen_ts"] = max(self._float(merged.get("last_seen_ts")), last_seen, created)
            merged["scheduled_ts"] = max(self._float(merged.get("scheduled_ts")), scheduled)
            merged["score"] = max(self._int(merged.get("score")), self._int(item.get("score")))
            if topic:
                merged["topic"] = topic
            if motive:
                merged["motive"] = motive
            if note and note != merged.get("note"):
                merged["note"] = "多来源合并"
            merged["is_due"] = bool(merged.get("scheduled_ts") and self._float(merged.get("scheduled_ts")) <= now)
        items: list[dict[str, Any]] = []
        for item in buckets:
            created = self._float(item.get("created_ts"))
            last_seen = self._float(item.get("last_seen_ts")) or created
            scheduled = self._float(item.get("scheduled_ts"))
            item.pop("_signature", None)
            item.pop("_first_ts", None)
            item["created"] = self.plugin._format_timestamp_elapsed(created)
            item["last_seen"] = self.plugin._format_timestamp_elapsed(last_seen)
            item["scheduled"] = self.plugin._format_timestamp_elapsed(scheduled)
            items.append(item)
        items.sort(key=lambda item: item.get("last_seen_ts") or item.get("scheduled_ts") or 0, reverse=True)
        return {
            "total": total_attempts,
            "visible_total": len(items),
            "counts": counts,
            "source_counts": source_counts,
            "users": sorted(
                user_counts.values(),
                key=lambda item: (self._int(item.get("total")), self._single_line(item.get("label"), 40)),
                reverse=True,
            ),
            "items": items[:60],
        }

    def _proactive_task_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        users = data.get("users") if isinstance(data.get("users"), dict) else {}
        now = time.time()
        items: list[dict[str, Any]] = []
        source_counts: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        audit_items: list[dict[str, Any]] = []
        audit_status_counts: dict[str, int] = {}
        user_states: list[dict[str, Any]] = []

        for user_id, user in users.items():
            if not isinstance(user, dict):
                continue
            if bool(user.get("enabled", True)):
                user_summary_for_state = self._user_summary(str(user_id), user)
                effective_limit = (
                    self.plugin._effective_user_daily_limit(user)
                    if hasattr(self.plugin, "_effective_user_daily_limit")
                    else getattr(self.plugin, "max_daily_messages", 0)
                )
                next_for_state = self._float(user.get("next_proactive_at"))
                user_states.append(
                    {
                        "user_id": str(user_id),
                        "user_label": user_summary_for_state.get("display_name") or str(user_id),
                        "user_role": user_summary_for_state.get("relationship_role") or "",
                        "user_role_label": user_summary_for_state.get("relationship_role_label") or "",
                        "sent_today": self._int(user.get("sent_today")),
                        "effective_daily_limit": effective_limit,
                        "next_proactive_ts": next_for_state,
                        "next_proactive": self.plugin._format_timestamp_elapsed(next_for_state),
                        "proactive_sending": bool(user.get("proactive_sending")),
                        "last_skip_ts": self._float(user.get("last_proactive_skip_at")),
                        "last_skip": self.plugin._format_timestamp_elapsed(user.get("last_proactive_skip_at", 0)),
                        "last_skip_reason": self._single_line(user.get("last_proactive_skip_reason"), 160),
                        "last_skip_prefix": self._single_line(user.get("last_proactive_skip_prefix"), 20),
                        "last_sent_ts": self._float(user.get("last_sent")),
                        "last_sent": self.plugin._format_timestamp_elapsed(user.get("last_sent", 0)),
                    }
                )
            scheduled_ts = self._float(user.get("next_proactive_at"))
            timer_event = user.get("llm_timer_event") if isinstance(user.get("llm_timer_event"), dict) else {}
            if scheduled_ts <= 0 and timer_event:
                scheduled_ts = self._float(timer_event.get("scheduled_ts"))
            if scheduled_ts <= 0:
                continue
            source = self._single_line(user.get("planned_proactive_source"), 40)
            if not source and timer_event:
                source = "timer"
            source = source or "proactive"
            status = "due" if scheduled_ts <= now else "scheduled"
            if scheduled_ts < now - 15 * 60:
                status = "overdue"
            user_summary = self._user_summary(str(user_id), user)
            source_counts[source] = source_counts.get(source, 0) + 1
            status_counts[status] = status_counts.get(status, 0) + 1
            action = (
                self._single_line(user.get("planned_proactive_action"), 40)
                or self._single_line(timer_event.get("action"), 40)
                or "message"
            )
            reason = (
                self._single_line(user.get("planned_proactive_reason"), 40)
                or self._single_line(timer_event.get("reason"), 40)
            )
            topic = (
                self._single_line(user.get("planned_proactive_topic"), 80)
                or self._single_line(timer_event.get("topic"), 80)
            )
            motive = (
                self._single_line(user.get("planned_proactive_motive"), 180)
                or self._single_line(timer_event.get("motive"), 180)
            )
            sanitizer = getattr(self.plugin, "_sanitize_friend_proactive_plan_fields", None)
            if callable(sanitizer):
                sanitized = sanitizer(
                    user,
                    reason=reason,
                    action=action,
                    topic=topic,
                    motive=motive,
                )
                reason = self._single_line(sanitized.get("reason"), 40) or reason
                action = self._single_line(sanitized.get("action"), 40) or action
                topic = self._single_line(sanitized.get("topic"), 80)
                motive = self._single_line(sanitized.get("motive"), 180)
            items.append(
                {
                    "user_id": str(user_id),
                    "user_label": user_summary.get("display_name") or str(user_id),
                    "user_role": user_summary.get("relationship_role") or "",
                    "user_role_label": user_summary.get("relationship_role_label") or "",
                    "source": source,
                    "status": status,
                    "action": action,
                    "reason": reason,
                    "topic": topic,
                    "motive": motive,
                    "scheduled_ts": scheduled_ts,
                    "scheduled": self.plugin._format_timestamp_elapsed(scheduled_ts),
                    "last_skip": self.plugin._format_timestamp_elapsed(user.get("last_proactive_skip_at", 0)),
                    "last_skip_ts": self._float(user.get("last_proactive_skip_at")),
                    "last_skip_reason": self._single_line(user.get("last_proactive_skip_reason"), 120),
                    "last_skip_prefix": self._single_line(user.get("last_proactive_skip_prefix"), 20),
                    "created_ts": self._float(timer_event.get("created_at")),
                    "created": self.plugin._format_timestamp_elapsed(timer_event.get("created_at", 0)),
                    "origin": self._single_line(timer_event.get("origin"), 40),
                    "raw_time": self._single_line(timer_event.get("raw_time"), 40),
                    "trigger_message_id": self._single_line(timer_event.get("trigger_message_id"), 120),
                    "trigger_umo": self._single_line(timer_event.get("trigger_umo"), 160),
                    "has_timer_event": bool(timer_event),
                    "silence_until_due": bool(timer_event.get("silence_until_due")) if timer_event else False,
                }
            )

        items.sort(key=lambda item: self._float(item.get("scheduled_ts")))
        raw_audit = data.get("proactive_audit_log") if isinstance(data.get("proactive_audit_log"), list) else []
        seen_audit_signatures: dict[str, dict[str, Any]] = {}
        for raw in raw_audit:
            if not isinstance(raw, dict):
                continue
            user_id = str(raw.get("user_id") or "")
            user = users.get(user_id) if isinstance(users.get(user_id), dict) else {}
            user_summary = self._user_summary(user_id, user) if user_id else {}
            status = self._single_line(raw.get("status"), 32) or "unknown"
            audit_reason = self._single_line(raw.get("reason"), 40)
            audit_action = self._single_line(raw.get("action"), 60)
            audit_topic = self._single_line(raw.get("topic"), 100)
            audit_motive = self._single_line(raw.get("motive"), 180)
            sanitizer = getattr(self.plugin, "_sanitize_friend_proactive_plan_fields", None)
            if isinstance(user, dict) and callable(sanitizer):
                sanitized = sanitizer(
                    user,
                    reason=audit_reason,
                    action=audit_action,
                    topic=audit_topic,
                    motive=audit_motive,
                )
                audit_reason = self._single_line(sanitized.get("reason"), 40) or audit_reason
                audit_action = self._single_line(sanitized.get("action"), 60) or audit_action
                audit_topic = self._single_line(sanitized.get("topic"), 100)
                audit_motive = self._single_line(sanitized.get("motive"), 180)
            note = self._single_line(raw.get("note"), 180)
            updated_ts = self._float(raw.get("updated_ts"))
            bucket = int(updated_ts // 300) if updated_ts > 0 else 0
            signature = "|".join(
                self._single_line(value, 120)
                for value in (
                    user_id,
                    status,
                    self._single_line(raw.get("source"), 40),
                    audit_reason,
                    audit_action,
                    audit_topic,
                    audit_motive,
                    note,
                    bucket,
                )
            )
            existing = seen_audit_signatures.get(signature)
            if existing is not None:
                existing["updated_ts"] = max(self._float(existing.get("updated_ts")), updated_ts)
                existing["updated"] = self.plugin._format_timestamp_elapsed(existing["updated_ts"])
                existing["duplicate_count"] = max(1, self._int(existing.get("duplicate_count"))) + max(1, self._int(raw.get("duplicate_count")))
                continue
            audit_status_counts[status] = audit_status_counts.get(status, 0) + 1
            item = {
                "id": self._single_line(raw.get("id"), 40),
                "user_id": user_id,
                "user_label": user_summary.get("display_name") or user_id,
                "user_role": user_summary.get("relationship_role") or "",
                "user_role_label": user_summary.get("relationship_role_label") or "",
                "status": status,
                "source": self._single_line(raw.get("source"), 40),
                "reason": audit_reason,
                "action": audit_action,
                "topic": audit_topic,
                "motive": audit_motive,
                "note": note,
                "text_preview": self._display_message_text(raw.get("text_preview"), 180),
                "scheduled_ts": self._float(raw.get("scheduled_ts")),
                "scheduled": self.plugin._format_timestamp_elapsed(raw.get("scheduled_ts", 0)),
                "created_ts": self._float(raw.get("created_ts")),
                "created": self.plugin._format_timestamp_elapsed(raw.get("created_ts", 0)),
                "updated_ts": updated_ts,
                "updated": self.plugin._format_timestamp_elapsed(raw.get("updated_ts", 0)),
                "candidate_id": self._single_line(raw.get("candidate_id"), 40),
                "has_image": bool(self._single_line(raw.get("image_path"), 260)),
                "extra_count": self._int(raw.get("extra_count")),
                "duplicate_count": max(1, self._int(raw.get("duplicate_count"))),
            }
            seen_audit_signatures[signature] = item
            audit_items.append(item)
        audit_items.sort(key=lambda item: self._float(item.get("updated_ts") or item.get("created_ts")), reverse=True)
        runtime = data.get("proactive_runtime") if isinstance(data.get("proactive_runtime"), dict) else {}
        last_tick_started = self._float(runtime.get("last_tick_started_at")) if runtime else 0
        last_tick_finished = self._float(runtime.get("last_tick_finished_at")) if runtime else 0
        tick_age = now - max(last_tick_started, last_tick_finished) if max(last_tick_started, last_tick_finished) > 0 else -1
        expected_interval = max(30, self._int(getattr(self.plugin, "check_interval_seconds", 60)))
        return {
            "total": len(items),
            "source_counts": source_counts,
            "status_counts": status_counts,
            "items": items[:30],
            "audit_total": len(audit_items),
            "audit_status_counts": audit_status_counts,
            "audit_items": audit_items[:40],
            "user_states": sorted(
                user_states,
                key=lambda item: (
                    0 if item.get("user_role") == "owner" else 1,
                    self._float(item.get("next_proactive_ts")) if self._float(item.get("next_proactive_ts")) > 0 else 9999999999,
                    self._single_line(item.get("user_label"), 40),
                ),
            )[:40],
            "runtime": {
                "last_tick_started_ts": last_tick_started,
                "last_tick_started": self.plugin._format_timestamp_elapsed(last_tick_started),
                "last_tick_finished_ts": last_tick_finished,
                "last_tick_finished": self.plugin._format_timestamp_elapsed(last_tick_finished),
                "tick_age_seconds": round(tick_age, 1) if tick_age >= 0 else -1,
                "expected_interval_seconds": expected_interval,
                "healthy": bool(tick_age >= 0 and tick_age <= max(180, expected_interval * 4)),
                "last_tick_error": self._single_line(runtime.get("last_tick_error"), 180) if runtime else "",
            },
        }

    def _creative_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        projects = data.get("creative_projects") if isinstance(data.get("creative_projects"), list) else []
        items = [item for item in projects if isinstance(item, dict)]
        active = [item for item in items if item.get("status") == "drafting"]
        latest = items[-1] if items else {}
        return {
            "enabled": bool(getattr(self.plugin, "enable_creative_writing", False)),
            "hidden_mode": bool(getattr(self.plugin, "creative_hidden_mode", False)),
            "project_count": len(items),
            "active_projects": len(active),
            "latest_title": self._single_line(latest.get("title"), 60) if isinstance(latest, dict) else "",
            "latest_status": self._single_line(latest.get("status"), 24) if isinstance(latest, dict) else "",
            "latest_progress": {
                "current_chars": self._int(latest.get("current_chars")) if isinstance(latest, dict) else 0,
                "target_chars": self._int(latest.get("target_chars")) if isinstance(latest, dict) else 0,
            },
            "items": [
                {
                    "id": self._single_line(item.get("id"), 20),
                    "title": self._single_line(item.get("title"), 60),
                    "work_type": self._single_line(item.get("work_type"), 30) or "短篇小说",
                    "premise": self._single_line(item.get("premise"), 160),
                    "tone": self._single_line(item.get("tone"), 40),
                    "point_of_view": self._single_line(item.get("point_of_view"), 40) or "第三人称有限视角",
                    "source": self._single_line(item.get("source_text"), 160),
                    "status": self._single_line(item.get("status"), 24),
                    "current_chars": self._int(item.get("current_chars")),
                    "target_chars": self._int(item.get("target_chars")),
                    "chunk_count": len(item.get("draft_chunks") or []) if isinstance(item.get("draft_chunks"), list) else 0,
                    "latest_snippet": self._single_line(
                        (item.get("draft_chunks") or [])[-1].get("text") if isinstance(item.get("draft_chunks"), list) and item.get("draft_chunks") else "",
                        260,
                    ),
                    "milestones": item.get("disclosed_milestones") if isinstance(item.get("disclosed_milestones"), list) else [],
                    "created_at": self.plugin._format_timestamp_elapsed(item.get("created_at", 0)),
                    "last_advanced": self.plugin._format_timestamp_elapsed(item.get("last_advanced_at", 0)),
                    "next_advance": self.plugin._format_timestamp_elapsed(item.get("next_advance_at", 0)),
                }
                for item in items[-6:]
            ],
        }

    def _daily_state_summary(self, state: Any) -> dict[str, Any]:
        if not isinstance(state, dict):
            return {}
        keys = ["date", "sleep", "dream", "health", "hunger", "body_cycle", "location", "weather", "mood_bias", "energy", "note"]
        summary = {key: state.get(key, "") for key in keys}
        runtime = state.get("sleep_runtime") if isinstance(state.get("sleep_runtime"), dict) else {}
        if runtime:
            summary["sleep_phase"] = self._single_line(runtime.get("label") or runtime.get("phase"), 40)
            summary["sleep_runtime"] = {
                "phase": self._single_line(runtime.get("phase"), 40),
                "label": self._single_line(runtime.get("label") or runtime.get("phase"), 40),
                "last_event": self._single_line(runtime.get("last_event"), 120),
                "source": self._single_line(runtime.get("source"), 40),
                "woken_count": self._int(runtime.get("woken_count")),
                "updated_at": self.plugin._format_timestamp_elapsed(runtime.get("updated_at", 0)),
            }
        return summary

    def _life_observation_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        dream = data.get("daily_dream") if isinstance(data.get("daily_dream"), dict) else {}
        diaries = data.get("bot_diaries") if isinstance(data.get("bot_diaries"), list) else []
        fragments = data.get("dream_fragments") if isinstance(data.get("dream_fragments"), list) else []
        plan = data.get("daily_plan") if isinstance(data.get("daily_plan"), dict) else {}
        try:
            live_plan = self.plugin.data.get("daily_plan") if isinstance(self.plugin.data.get("daily_plan"), dict) else {}
            if live_plan and self.plugin._sanitize_daily_plan_inplace(live_plan):
                self.plugin._refresh_daily_state_location_from_plan(plan=live_plan)
                self.plugin._save_data_sync()
                plan = deepcopy(live_plan)
                data["daily_plan"] = plan
        except Exception:
            pass
        story = data.get("daily_story_plan") if isinstance(data.get("daily_story_plan"), dict) else {}
        current_item = {}
        try:
            picked = self.plugin._get_current_plan_item(plan)
            current_item = picked if isinstance(picked, dict) else {}
        except Exception:
            current_item = {}

        return {
            "dream": {
                "date": self._single_line(dream.get("date"), 24),
                "label": self._single_line(dream.get("label"), 120),
                "dream_type": self._single_line(dream.get("dream_type"), 40),
                "content": self._single_line(dream.get("content"), 1000),
                "afterglow": self._single_line(dream.get("afterglow"), 220),
                "mood": self._single_line(dream.get("mood"), 30),
                "energy_delta": self._int(dream.get("energy_delta")),
                "duration_hours": self._int(dream.get("duration_hours")),
                "generated_at": self._single_line(dream.get("generated_at"), 24),
                "factors": [self._single_line(item, 40) for item in dream.get("factors", [])[:8] if self._single_line(item, 40)]
                if isinstance(dream.get("factors"), list)
                else [],
            },
            "diaries": [
                {
                    "date": self._single_line(item.get("date"), 24),
                    "summary": self._single_line(item.get("summary"), 180),
                    "body": self._single_line(item.get("body"), 500),
                    "share_seed": self._single_line(item.get("share_seed"), 140),
                    "tags": [self._single_line(tag, 20) for tag in item.get("tags", [])[:6] if self._single_line(tag, 20)]
                    if isinstance(item.get("tags"), list)
                    else [],
                    "generated_at": self._single_line(item.get("generated_at"), 24),
                }
                for item in diaries[-4:]
                if isinstance(item, dict)
            ],
            "dream_fragments": self._limited_dream_fragments(fragments),
            "current_plan": {
                "time": self._single_line(current_item.get("time"), 12),
                "activity": self._single_line(current_item.get("activity"), 600),
                "mood": self._single_line(current_item.get("mood"), 40),
                "message_seed": self._single_line(current_item.get("message_seed"), 500),
            },
            "story": {
                "date": self._single_line(story.get("date"), 24),
                "today_events": self._limited_story_items(story.get("today_events"), 4),
                "proactive_events": self._limited_story_items(story.get("proactive_events"), 4),
            },
        }

    def _daily_timeline_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        plan = data.get("daily_plan") if isinstance(data.get("daily_plan"), dict) else {}
        enhanced = data.get("detail_enhanced_segments") if isinstance(data.get("detail_enhanced_segments"), dict) else {}
        story = data.get("daily_story_plan") if isinstance(data.get("daily_story_plan"), dict) else {}
        adjustments = data.get("schedule_adjustments") if isinstance(data.get("schedule_adjustments"), list) else []
        presence = data.get("qq_presence_state") if isinstance(data.get("qq_presence_state"), dict) else {}

        segments: list[dict[str, Any]] = []
        for key, snapshot in enhanced.items():
            if not isinstance(snapshot, dict):
                continue
            segment = self._segment_from_key(str(key), plan, snapshot)
            segments.append(
                {
                    "key": str(key),
                    "window": segment.get("window", str(key)),
                    "start": segment.get("start", 99999),
                    "status": snapshot.get("status", ""),
                    "summary": snapshot.get("summary", ""),
                    "state_variables": self._limited_state_variables(snapshot.get("state_variables")),
                    "presence_status": snapshot.get("presence_status") if isinstance(snapshot.get("presence_status"), dict) else {},
                    "interaction_updates": self._limited_interaction_updates(snapshot.get("interaction_updates")),
                    "today_events": self._limited_story_items(snapshot.get("today_events"), 5),
                    "proactive_events": self._limited_story_items(snapshot.get("proactive_events"), 4),
                }
            )
        segments.sort(key=lambda item: item.get("start", 99999))

        return {
            "plan_date": plan.get("date", ""),
            "story_date": story.get("date", ""),
            "detail_day": data.get("detail_enhanced_day", ""),
            "segment_count": len(segments),
            "segments": segments,
            "story_today_events": self._limited_story_items(story.get("today_events"), 12),
            "story_proactive_events": self._limited_story_items(story.get("proactive_events"), 12),
            "adjustments": self._limited_adjustments(adjustments),
            "qq_presence_state": presence,
        }

    def _segment_from_key(self, key: str, plan: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
        keyed = re.fullmatch(r"(\d{4}-\d{2}-\d{2}):(\d+):(\d{1,2}:\d{2})", key)
        if keyed:
            index = int(keyed.group(2))
            start = self.plugin._parse_hhmm_to_minutes(keyed.group(3))
            items = plan.get("items") if isinstance(plan, dict) else []
            end = None
            if isinstance(items, list):
                for next_item in items[index + 1:]:
                    if isinstance(next_item, dict):
                        end = self.plugin._parse_hhmm_to_minutes(next_item.get("time"))
                        if end is not None:
                            break
            if start is not None:
                if end is None:
                    item = items[index] if isinstance(items, list) and index < len(items) and isinstance(items[index], dict) else None
                    end = self.plugin._segment_end_minutes(start, item)
                return {"window": f"{self.plugin._minutes_to_hhmm(start)}-{self.plugin._minutes_to_hhmm(end)}", "start": start}

        inferred = self._segment_from_story_windows(snapshot)
        if inferred:
            return inferred

        match = re.search(r"(?:^|[:|_])(\d{1,4})[-_](\d{1,4})(?:$|[:|_])", key)
        if not match:
            return {"window": key, "start": 99999}
        start = int(match.group(1))
        end = int(match.group(2))
        if not (0 <= start < 24 * 60 and 0 < end <= 28 * 60):
            return {"window": key, "start": 99999}
        return {"window": f"{self.plugin._minutes_to_hhmm(start)}-{self.plugin._minutes_to_hhmm(end)}", "start": start}

    def _token_stats_payload(self, usage: Any) -> dict[str, Any]:
        if not isinstance(usage, dict):
            usage = {}
        external_usage = usage.get("external") if isinstance(usage.get("external"), dict) else {}
        totals = self._token_bucket(usage.get("totals"))
        by_provider = self._token_ranked_map(usage.get("by_provider"))
        by_task = self._token_ranked_map(usage.get("by_task"))
        by_day = self._token_series_map(usage.get("by_day"), limit=30)
        by_day_provider_raw = usage.get("by_day_provider") if isinstance(usage.get("by_day_provider"), dict) else {}
        by_day_task_raw = usage.get("by_day_task") if isinstance(usage.get("by_day_task"), dict) else {}
        by_day_detail = []
        for item in by_day:
            day_key = item.get("key", "")
            providers = self._token_ranked_map(by_day_provider_raw.get(day_key))[:5]
            tasks = self._token_ranked_map(by_day_task_raw.get(day_key))[:6]
            by_day_detail.append({**item, "providers": providers, "tasks": tasks})
        by_hour = self._token_series_map(usage.get("by_hour"), limit=48)
        today_key = _today_key()
        today_bucket = usage.get("by_day", {}).get(today_key, {}) if isinstance(usage.get("by_day"), dict) else {}
        today_total_tokens = self._int(today_bucket.get("total_tokens")) if isinstance(today_bucket, dict) else 0
        exempt_by_day = usage.get("budget_exempt_by_day") if isinstance(usage.get("budget_exempt_by_day"), dict) else {}
        today_exempt_bucket = exempt_by_day.get(today_key, {}) if isinstance(exempt_by_day, dict) else {}
        today_exempt_tokens = self._int(today_exempt_bucket.get("total_tokens")) if isinstance(today_exempt_bucket, dict) else 0
        if today_exempt_tokens <= 0:
            today_tasks = by_day_task_raw.get(today_key, {}) if isinstance(by_day_task_raw, dict) else {}
            if isinstance(today_tasks, dict):
                is_exempt_task = getattr(self.plugin, "_is_llm_budget_exempt_task", None)
                today_exempt_tokens = sum(
                    self._int(bucket.get("total_tokens"))
                    for task, bucket in today_tasks.items()
                    if (
                        (
                            callable(is_exempt_task)
                            and is_exempt_task(task)
                        )
                        or (
                            not callable(is_exempt_task)
                            and str(task) in {"proactive_framework", "voice_framework"}
                        )
                    )
                    and isinstance(bucket, dict)
                )
        today_tokens = max(0, today_total_tokens - today_exempt_tokens)
        daily_limit = self._int(getattr(self.plugin, "daily_token_limit", 0))
        soft_limit = self._int(getattr(self.plugin, "daily_token_soft_limit", 0))
        soft_enabled = bool(getattr(self.plugin, "enable_daily_token_soft_limit", True))
        budget_skips = usage.get("budget_skips", {})
        today_skips = budget_skips.get(today_key, {}) if isinstance(budget_skips, dict) else {}
        budget = {
            "day": today_key,
            "limit": daily_limit,
            "soft_limit": soft_limit,
            "soft_enabled": soft_enabled,
            "soft_active": bool(soft_enabled and soft_limit > 0 and today_tokens >= soft_limit),
            "used": today_tokens,
            "total_used": today_total_tokens,
            "exempt_used": today_exempt_tokens,
            "remaining": max(0, daily_limit - today_tokens) if daily_limit > 0 else None,
            "soft_remaining": max(0, soft_limit - today_tokens) if soft_enabled and soft_limit > 0 else None,
            "ratio": round(today_tokens / daily_limit, 4) if daily_limit > 0 else 0,
            "soft_ratio": round(today_tokens / soft_limit, 4) if soft_enabled and soft_limit > 0 else 0,
            "exceeded": bool(daily_limit > 0 and today_tokens >= daily_limit),
            "deferred_calls": (
                self._int(today_skips.get("daily_token_soft_limit_deferred"))
                + self._int(today_skips.get("maintenance_token_saver_deferred"))
            )
            if isinstance(today_skips, dict)
            else 0,
            "skipped_calls": self._int(today_skips.get("count")) if isinstance(today_skips, dict) else 0,
        }
        recent_raw = usage.get("recent")
        recent = []
        if isinstance(recent_raw, list):
            for item in recent_raw[-80:][::-1]:
                if not isinstance(item, dict):
                    continue
                recent.append(
                    {
                        "time": self._single_line(item.get("time"), 24),
                        "ts": self._float(item.get("ts")),
                        "provider": self._single_line(item.get("provider"), 80),
                        "task": self._single_line(item.get("task"), 40),
                        "success": bool(item.get("success", True)),
                        "prompt_tokens": self._int(item.get("prompt_tokens")),
                        "completion_tokens": self._int(item.get("completion_tokens")),
                        "total_tokens": self._int(item.get("total_tokens")),
                        "estimated": bool(item.get("estimated", False)),
                        "elapsed_ms": self._int(item.get("elapsed_ms")),
                        "prompt_chars": self._int(item.get("prompt_chars")),
                        "completion_chars": self._int(item.get("completion_chars")),
                        "error": self._single_line(item.get("error"), 160),
                        "budget_exempt": bool(item.get("budget_exempt", False)),
                    }
                )
        return {
            "updated_at": self._single_line(usage.get("updated_at"), 24),
            "totals": totals,
            "by_provider": by_provider,
            "by_task": by_task,
            "by_day": by_day,
            "by_day_detail": by_day_detail,
            "by_hour": by_hour,
            "budget": budget,
            "recent": recent,
            "external": self._token_external_payload(external_usage),
        }

    def _token_external_payload(self, usage: Any) -> dict[str, Any]:
        if not isinstance(usage, dict):
            usage = {}
        by_day = self._token_series_map(usage.get("by_day"), limit=30)
        by_day_provider_raw = usage.get("by_day_provider") if isinstance(usage.get("by_day_provider"), dict) else {}
        by_day_task_raw = usage.get("by_day_task") if isinstance(usage.get("by_day_task"), dict) else {}
        by_day_detail = []
        for item in by_day:
            day_key = item.get("key", "")
            by_day_detail.append(
                {
                    **item,
                    "providers": self._token_ranked_map(by_day_provider_raw.get(day_key))[:5],
                    "tasks": self._token_ranked_map(by_day_task_raw.get(day_key))[:6],
                }
            )
        recent = []
        recent_raw = usage.get("recent")
        if isinstance(recent_raw, list):
            for item in recent_raw[-80:][::-1]:
                if not isinstance(item, dict):
                    continue
                recent.append(
                    {
                        "time": self._single_line(item.get("time"), 24),
                        "ts": self._float(item.get("ts")),
                        "provider": self._single_line(item.get("provider"), 80),
                        "task": self._single_line(item.get("task"), 40),
                        "success": bool(item.get("success", True)),
                        "prompt_tokens": self._int(item.get("prompt_tokens")),
                        "completion_tokens": self._int(item.get("completion_tokens")),
                        "total_tokens": self._int(item.get("total_tokens")),
                        "estimated": bool(item.get("estimated", False)),
                        "elapsed_ms": self._int(item.get("elapsed_ms")),
                        "prompt_chars": self._int(item.get("prompt_chars")),
                        "completion_chars": self._int(item.get("completion_chars")),
                        "error": self._single_line(item.get("error"), 160),
                        "external": True,
                    }
                )
        return {
            "updated_at": self._single_line(usage.get("updated_at"), 24),
            "totals": self._token_bucket(usage.get("totals")),
            "by_provider": self._token_ranked_map(usage.get("by_provider")),
            "by_task": self._token_ranked_map(usage.get("by_task")),
            "by_day": by_day,
            "by_day_detail": by_day_detail,
            "by_hour": self._token_series_map(usage.get("by_hour"), limit=48),
            "recent": recent,
        }

    @classmethod
    def _token_bucket(cls, value: Any) -> dict[str, Any]:
        bucket = value if isinstance(value, dict) else {}
        calls = cls._int(bucket.get("calls"))
        elapsed = cls._int(bucket.get("elapsed_ms"))
        total_tokens = cls._int(bucket.get("total_tokens"))
        estimated_tokens = cls._int(bucket.get("estimated_tokens"))
        return {
            "calls": calls,
            "success": cls._int(bucket.get("success")),
            "errors": cls._int(bucket.get("errors")),
            "prompt_tokens": cls._int(bucket.get("prompt_tokens")),
            "completion_tokens": cls._int(bucket.get("completion_tokens")),
            "total_tokens": total_tokens,
            "estimated_tokens": estimated_tokens,
            "estimated_ratio": round(estimated_tokens / total_tokens, 4) if total_tokens > 0 else 0,
            "avg_tokens": round(total_tokens / calls, 1) if calls > 0 else 0,
            "avg_latency_ms": round(elapsed / calls, 1) if calls > 0 else 0,
            "last_ts": cls._float(bucket.get("last_ts")),
        }

    @classmethod
    def _token_ranked_map(cls, value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, dict):
            return []
        rows = []
        for key, bucket in value.items():
            item = cls._token_bucket(bucket)
            item["key"] = cls._single_line(key, 120)
            rows.append(item)
        rows.sort(key=lambda item: item.get("total_tokens", 0), reverse=True)
        return rows

    @classmethod
    def _token_series_map(cls, value: Any, *, limit: int) -> list[dict[str, Any]]:
        if not isinstance(value, dict):
            return []
        rows = []
        for key, bucket in value.items():
            item = cls._token_bucket(bucket)
            item["key"] = cls._single_line(key, 32)
            rows.append(item)
        rows.sort(key=lambda item: item.get("key", ""))
        return rows[-limit:]

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def _segment_from_story_windows(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        minutes: list[int] = []
        for key in ("today_events", "proactive_events"):
            items = snapshot.get(key)
            if not isinstance(items, list):
                continue
            for item in items:
                if not isinstance(item, dict):
                    continue
                start, end = self.plugin._parse_window_minutes(str(item.get("window") or ""))
                if start is not None:
                    minutes.append(start)
                if end is not None:
                    minutes.append(end)
        if not minutes:
            return None
        start = min(minutes)
        end = max(minutes)
        return {"window": f"{self.plugin._minutes_to_hhmm(start)}-{self.plugin._minutes_to_hhmm(end)}", "start": start}

    @staticmethod
    def _limited_state_variables(value: Any) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        items: list[dict[str, str]] = []
        for item in value[:8]:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "name": PrivateCompanionPageApi._single_line(item.get("name") or item.get("key"), 40),
                    "value": PrivateCompanionPageApi._single_line(item.get("value"), 80),
                    "note": PrivateCompanionPageApi._single_line(item.get("note"), 100),
                }
            )
        return items

    @staticmethod
    def _limited_interaction_updates(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        items: list[dict[str, Any]] = []
        for item in value[-8:]:
            if not isinstance(item, dict):
                continue
            updates = item.get("state_updates")
            items.append(
                {
                    "at": PrivateCompanionPageApi._single_line(item.get("at"), 12),
                    "source": PrivateCompanionPageApi._single_line(item.get("source"), 24),
                    "reaction": PrivateCompanionPageApi._single_line(item.get("reaction"), 140),
                    "state_updates": [
                        PrivateCompanionPageApi._single_line(update, 80)
                        for update in updates[:6]
                        if PrivateCompanionPageApi._single_line(update, 80)
                    ]
                    if isinstance(updates, list)
                    else [],
                }
            )
        return items

    @staticmethod
    def _limited_story_items(value: Any, limit: int) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        items: list[dict[str, str]] = []
        for item in value[:limit]:
            if not isinstance(item, dict):
                continue
            items.append(
                {
                    "window": PrivateCompanionPageApi._single_line(item.get("window") or item.get("time"), 24),
                    "text": PrivateCompanionPageApi._single_line(
                        item.get("event")
                        or item.get("topic")
                        or item.get("summary")
                        or item.get("text")
                        or item.get("content"),
                        160,
                    ),
                    "mood": PrivateCompanionPageApi._single_line(item.get("mood"), 24),
                    "action": PrivateCompanionPageApi._single_line(item.get("action"), 24),
                    "reason": PrivateCompanionPageApi._single_line(item.get("reason"), 32),
                }
            )
        return items

    @staticmethod
    def _limited_adjustments(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        items: list[dict[str, Any]] = []
        for item in value[-10:]:
            if not isinstance(item, dict):
                continue
            updates = item.get("state_updates")
            items.append(
                {
                    "date": PrivateCompanionPageApi._single_line(item.get("date"), 12),
                    "source": PrivateCompanionPageApi._single_line(item.get("source"), 24),
                    "note": PrivateCompanionPageApi._single_line(item.get("note"), 140),
                    "reaction": PrivateCompanionPageApi._single_line(item.get("immediate_reaction"), 140),
                    "state_updates": [
                        PrivateCompanionPageApi._single_line(update, 80)
                        for update in updates[:6]
                        if PrivateCompanionPageApi._single_line(update, 80)
                    ]
                    if isinstance(updates, list)
                    else [],
                }
            )
        return items

    @staticmethod
    def _limited_dream_fragments(value: Any) -> list[dict[str, Any]]:
        if not isinstance(value, list):
            return []
        items: list[dict[str, Any]] = []
        for raw in value[-18:]:
            if isinstance(raw, dict):
                text = PrivateCompanionPageApi._single_line(
                    raw.get("text") or raw.get("keyword") or raw.get("label"),
                    42,
                )
                if not text:
                    continue
                items.append(
                    {
                        "text": text,
                        "weight": PrivateCompanionPageApi._float(raw.get("effective_weight") or raw.get("weight")),
                        "source": PrivateCompanionPageApi._single_line(raw.get("source"), 24),
                        "created_at": PrivateCompanionPageApi._single_line(raw.get("created_at") or raw.get("created_ts"), 24),
                    }
                )
            else:
                text = PrivateCompanionPageApi._single_line(raw, 42)
                if text:
                    items.append({"text": text, "weight": 1.0, "source": "", "created_at": ""})
        items.sort(key=lambda item: float(item.get("weight") or 0), reverse=True)
        return items[:14]

    @staticmethod
    def _limited_list(value: Any, limit: int) -> list[Any]:
        return list(value[:limit]) if isinstance(value, list) else []

    @staticmethod
    def _memory_item_count(memory: Any) -> int:
        if not isinstance(memory, dict):
            return 0
        count = 0
        for value in memory.values():
            if isinstance(value, list):
                count += len(value)
            elif value:
                count += 1
        return count

    def _livingmemory_db_path(self) -> Path | None:
        candidates: list[Path] = []
        data_dir = Path(str(getattr(self.plugin, "data_dir", "") or "")).resolve()
        if data_dir:
            candidates.append(data_dir.parent / "astrbot_plugin_livingmemory" / "livingmemory.db")
            candidates.append(data_dir.parent / "astrbot_plugin_livingmemory" / "livingmemory_graph_documents.db")
        candidates.append(Path.home() / ".astrbot" / "data" / "plugin_data" / "astrbot_plugin_livingmemory" / "livingmemory.db")
        for path in candidates:
            try:
                if path.exists() and path.is_file():
                    return path
            except OSError:
                continue
        return None

    def _worldbook_member_livingmemory_tokens(self, user_id: str, profile: dict[str, Any]) -> dict[str, list[str]]:
        primary_raw: list[Any] = [
            user_id,
            profile.get("linked_qq_user_id"),
            profile.get("merged_into_user_id"),
            profile.get("linked_bili_profile_id"),
            profile.get("name"),
        ]
        external_ids = profile.get("external_ids")
        if isinstance(external_ids, list):
            primary_raw.extend(external_ids)
        support_raw: list[Any] = []
        for key in ("aliases", "observed_names"):
            value = profile.get(key)
            if isinstance(value, list):
                support_raw.extend(value)

        def normalize(raw_items: list[Any], seen: set[str]) -> list[str]:
            tokens: list[str] = []
            for raw in raw_items:
                text = self._single_line(raw, 80)
                if not text or text in seen:
                    continue
                if text.isdigit():
                    if len(text) < 5:
                        continue
                elif len(text) < 2:
                    continue
                seen.add(text)
                tokens.append(text)
            return tokens

        def stable_support(raw_items: list[Any]) -> list[Any]:
            stable: list[Any] = []
            for raw in raw_items:
                text = self._single_line(raw, 40)
                if not text or len(text) > 16:
                    continue
                if any(mark in text for mark in ("，", ",", "。", "！", "？", " ", "：", ":", "|", "\n")):
                    continue
                stable.append(text)
            return stable

        seen_tokens: set[str] = set()
        primary_tokens = normalize(primary_raw, seen_tokens)
        support_tokens = normalize(stable_support(support_raw), seen_tokens)
        tokens = [*primary_tokens, *support_tokens]
        return {
            "tokens": tokens[:18],
            "primary_tokens": primary_tokens[:8],
            "support_tokens": support_tokens[:12],
        }

    @staticmethod
    def _sqlite_like_pattern(token: str) -> str:
        escaped = str(token).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return f"%{escaped}%"

    @staticmethod
    def _json_dict(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not isinstance(value, str) or not value.strip():
            return {}
        try:
            parsed = json.loads(value)
        except Exception:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _json_list(value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if not isinstance(value, str) or not value.strip():
            return []
        try:
            parsed = json.loads(value)
        except Exception:
            return []
        return parsed if isinstance(parsed, list) else []

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _livingmemory_match_info(self, content: str, metadata_text: str, token_bundle: dict[str, list[str]]) -> dict[str, Any]:
        haystack = f"{content}\n{metadata_text}".lower()
        score = 0.0
        primary_tokens = token_bundle.get("primary_tokens", [])
        support_tokens = token_bundle.get("support_tokens", [])
        matched_primary: list[str] = []
        matched_support: list[str] = []
        for token in primary_tokens:
            text = token.lower()
            if not text or text not in haystack:
                continue
            count = max(1, haystack.count(text))
            if token.isdigit():
                score += 9.0 + min(count, 4)
            else:
                score += min(8.0, 3.5 + len(token) * 0.65) + min(count - 1, 3) * 0.7
            matched_primary.append(token)
        for token in support_tokens:
            text = token.lower()
            if not text or text not in haystack:
                continue
            count = max(1, haystack.count(text))
            score += min(3.0, 0.8 + len(token) * 0.25) + min(count - 1, 2) * 0.25
            matched_support.append(token)
        accepted = bool(matched_primary) or (not primary_tokens and len(matched_support) >= 2)
        return {
            "accepted": accepted,
            "score": round(score, 3),
            "matched_tokens": [*matched_primary, *matched_support][:8],
            "primary_hits": len(matched_primary),
            "support_hits": len(matched_support),
        }

    def _livingmemory_item_from_document(self, row: sqlite3.Row, token_bundle: dict[str, list[str]]) -> dict[str, Any] | None:
        metadata = self._json_dict(row["metadata"])
        content = str(row["text"] or "").strip()
        match = self._livingmemory_match_info(content, str(row["metadata"] or ""), token_bundle)
        if not match.get("accepted"):
            return None
        create_time = self._coerce_float(metadata.get("create_time"))
        last_access = self._coerce_float(metadata.get("last_access_time"))
        topics = metadata.get("topics") if isinstance(metadata.get("topics"), list) else []
        key_facts = metadata.get("key_facts") if isinstance(metadata.get("key_facts"), list) else []
        return {
            "source": "documents",
            "source_label": "长期记忆文档",
            "id": row["doc_id"] or row["id"],
            "score": match.get("score"),
            "matched_tokens": match.get("matched_tokens", []),
            "primary_hits": match.get("primary_hits", 0),
            "support_hits": match.get("support_hits", 0),
            "session_id": self._single_line(metadata.get("session_id"), 80),
            "persona_id": self._single_line(metadata.get("persona_id"), 80),
            "importance": metadata.get("importance"),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "create_time": create_time,
            "last_access_time": last_access,
            "topics": [self._single_line(item, 40) for item in topics[:8] if self._single_line(item, 40)],
            "key_facts": [self._single_line(item, 120) for item in key_facts[:8] if self._single_line(item, 120)],
            "preview": self._single_line(metadata.get("canonical_summary") or content, 260),
            "content": content[:1800],
        }

    def _livingmemory_item_from_atom(self, row: sqlite3.Row, token_bundle: dict[str, list[str]]) -> dict[str, Any] | None:
        content = str(row["content"] or "").strip()
        entities = self._json_list(row["entities"])
        metadata = self._json_dict(row["metadata"])
        metadata_text = " ".join([str(row["entities"] or ""), str(row["metadata"] or "")])
        match = self._livingmemory_match_info(content, metadata_text, token_bundle)
        if not match.get("accepted"):
            return None
        return {
            "source": "atoms",
            "source_label": "原子记忆",
            "id": row["id"],
            "parent_memory_id": row["parent_memory_id"],
            "score": match.get("score"),
            "matched_tokens": match.get("matched_tokens", []),
            "primary_hits": match.get("primary_hits", 0),
            "support_hits": match.get("support_hits", 0),
            "session_id": self._single_line(row["session_id"], 80),
            "persona_id": self._single_line(row["persona_id"], 80),
            "importance": row["importance"],
            "confidence": row["confidence"],
            "created_at": str(row["created_at"] or ""),
            "create_time": self._coerce_float(row["created_at"]),
            "last_access_time": self._coerce_float(row["last_accessed_at"]),
            "topics": [self._single_line(item, 40) for item in entities[:8] if self._single_line(item, 40)],
            "key_facts": [self._single_line(item, 120) for item in metadata.get("key_facts", [])[:6]] if isinstance(metadata.get("key_facts"), list) else [],
            "preview": self._single_line(content, 260),
            "content": content[:1200],
        }

    def _livingmemory_item_from_graph_entry(self, row: sqlite3.Row, token_bundle: dict[str, list[str]]) -> dict[str, Any] | None:
        metadata = self._json_dict(row["metadata"])
        content = str(row["content"] or "").strip()
        match = self._livingmemory_match_info(content, str(row["metadata"] or ""), token_bundle)
        if not match.get("accepted"):
            return None
        return {
            "source": "graph",
            "source_label": "关系图谱",
            "id": row["entry_key"] or row["id"],
            "parent_memory_id": row["source_memory_id"],
            "score": match.get("score"),
            "matched_tokens": match.get("matched_tokens", []),
            "primary_hits": match.get("primary_hits", 0),
            "support_hits": match.get("support_hits", 0),
            "session_id": self._single_line(row["session_id"] or metadata.get("session_id"), 80),
            "persona_id": self._single_line(row["persona_id"] or metadata.get("persona_id"), 80),
            "importance": metadata.get("importance"),
            "created_at": str(row["created_at"] or ""),
            "updated_at": str(row["updated_at"] or ""),
            "create_time": self._coerce_float(metadata.get("create_time")),
            "last_access_time": self._coerce_float(metadata.get("last_access_time")),
            "topics": [],
            "key_facts": [],
            "preview": self._single_line(content, 260),
            "content": content[:1600],
        }

    def _query_livingmemory_for_tokens(self, db_path: Path, token_bundle: dict[str, list[str]], limit: int) -> list[dict[str, Any]]:
        tokens = token_bundle.get("primary_tokens") or token_bundle.get("tokens", [])
        if not tokens:
            return []
        db_uri = f"file:{db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(db_uri, uri=True, timeout=2.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA query_only=ON")
            conn.execute("PRAGMA busy_timeout=1500")
            like_tokens = [self._sqlite_like_pattern(token) for token in tokens]
            table_limit = max(80, limit * 8)
            items: list[dict[str, Any]] = []

            def where_for(columns: list[str]) -> tuple[str, list[str]]:
                parts: list[str] = []
                params: list[str] = []
                for pattern in like_tokens:
                    sub = []
                    for column in columns:
                        sub.append(f"{column} LIKE ? ESCAPE '\\'")
                        params.append(pattern)
                    parts.append("(" + " OR ".join(sub) + ")")
                return " OR ".join(parts), params

            if self._sqlite_table_exists(conn, "documents"):
                where, params = where_for(["text", "metadata"])
                for row in conn.execute(
                    f"SELECT id, doc_id, text, metadata, created_at, updated_at FROM documents WHERE {where} ORDER BY id DESC LIMIT ?",
                    [*params, table_limit],
                ).fetchall():
                    item = self._livingmemory_item_from_document(row, token_bundle)
                    if item:
                        items.append(item)

            if self._sqlite_table_exists(conn, "memory_atoms"):
                where, params = where_for(["content", "entities", "metadata"])
                for row in conn.execute(
                    f"""SELECT id, parent_memory_id, atom_type, content, entities, importance, confidence,
                              created_at, last_accessed_at, session_id, persona_id, metadata
                         FROM memory_atoms
                        WHERE (status IS NULL OR status != 'expired') AND ({where})
                        ORDER BY id DESC LIMIT ?""",
                    [*params, table_limit],
                ).fetchall():
                    item = self._livingmemory_item_from_atom(row, token_bundle)
                    if item:
                        items.append(item)

            if self._sqlite_table_exists(conn, "graph_entries"):
                where, params = where_for(["content", "metadata", "session_id"])
                for row in conn.execute(
                    f"""SELECT id, entry_key, source_memory_id, session_id, persona_id, entry_type,
                              relation_type, content, metadata, created_at, updated_at
                         FROM graph_entries
                        WHERE {where}
                        ORDER BY id DESC LIMIT ?""",
                    [*params, table_limit],
                ).fetchall():
                    item = self._livingmemory_item_from_graph_entry(row, token_bundle)
                    if item:
                        items.append(item)

            seen: set[tuple[str, str]] = set()
            unique: list[dict[str, Any]] = []
            for item in sorted(items, key=lambda entry: (entry.get("score") or 0, entry.get("last_access_time") or entry.get("create_time") or 0), reverse=True):
                key = (str(item.get("source") or ""), str(item.get("id") or ""))
                if key in seen:
                    continue
                seen.add(key)
                unique.append(item)
                if len(unique) >= limit:
                    break
            return unique
        finally:
            conn.close()

    @staticmethod
    def _sqlite_table_exists(conn: sqlite3.Connection, table: str) -> bool:
        row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)).fetchone()
        return row is not None

    @staticmethod
    def _query_int(name: str, default: int, minimum: int, maximum: int) -> int:
        raw = request.args.get(name, default)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _clamp_int(raw: Any, default: int, minimum: int, maximum: int) -> int:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            value = default
        return max(minimum, min(maximum, value))

    @staticmethod
    def _normalize_id_list(value: Any) -> list[str]:
        if isinstance(value, str):
            raw_items = value.replace("，", ",").replace("\n", ",").split(",")
        elif isinstance(value, list):
            raw_items = value
        else:
            raw_items = []
        result: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            text = PrivateCompanionPageApi._single_line(item, 64)
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _single_line(value: Any, limit: int) -> str:
        text = " ".join(str(value or "").strip().split())
        return text[:limit]

    @staticmethod
    def _ok(data: Any = None) -> dict[str, Any]:
        return {"success": True, "data": data, "ts": int(time.time())}

    @staticmethod
    def _error(message: str) -> dict[str, Any]:
        return {"success": False, "error": str(message), "ts": int(time.time())}
