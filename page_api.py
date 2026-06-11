# -*- coding: utf-8 -*-
from __future__ import annotations

import time
import re
import shutil
import base64
import hashlib
import mimetypes
import secrets
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import quote

from astrbot.api import logger
from quart import request, send_file

from .helpers import _strip_internal_message_blocks, _today_key

PLUGIN_NAME = "astrbot_plugin_private_companion"
PAGE_API_PREFIX = f"/{PLUGIN_NAME}/page"


class PrivateCompanionPageApi:
    """AstrBot 官方插件拓展页面 API。"""

    def __init__(self, plugin: Any) -> None:
        self.plugin = plugin

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
            ("/token/stats", self.get_token_stats, ["GET"], "Private Companion Page token stats"),
            ("/token/reset", self.reset_token_stats, ["POST"], "Private Companion Page reset token stats"),
            ("/bookshelf/unlock", self.unlock_bookshelf, ["POST"], "Private Companion Page unlock bookshelf"),
            ("/bookshelf/image", self.get_bookshelf_image, ["GET"], "Private Companion Page bookshelf image"),
            ("/bookshelf/image_data", self.get_bookshelf_image_data, ["GET"], "Private Companion Page bookshelf image data"),
            ("/bookshelf/delete", self.delete_bookshelf_item, ["POST"], "Private Companion Page delete bookshelf item"),
            ("/bookshelf/rate", self.rate_bookshelf_item, ["POST"], "Private Companion Page rate bookshelf item"),
            ("/bookshelf/tags", self.update_bookshelf_item_tags, ["POST"], "Private Companion Page update bookshelf item tags"),
            ("/bookshelf/comments/update", self.update_bookshelf_item_comments, ["POST"], "Private Companion Page update bookshelf item comments"),
            ("/worldbook/import", self.import_worldbook, ["POST"], "Private Companion Page import worldbook"),
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
            enabled_groups = sum(1 for item in groups.values() if isinstance(item, dict) and item.get("enabled", True))
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
                        "group_count": len(groups),
                        "enabled_group_count": enabled_groups,
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
                    "worldbook": self._worldbook_summary(data),
                    "proactive_candidates": self._proactive_candidate_summary(data),
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

    async def list_users(self) -> dict[str, Any]:
        try:
            limit = self._query_int("limit", 80, 1, 300)
            async with self.plugin._data_lock:
                users = deepcopy(self.plugin.data.get("users", {}))
            if not isinstance(users, dict):
                users = {}
            items = [self._user_summary(user_id, user) for user_id, user in users.items() if isinstance(user, dict)]
            items.sort(key=lambda item: item.get("last_seen_ts") or 0, reverse=True)
            return self._ok({"items": items[:limit], "total": len(items)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取用户列表失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def get_user(self) -> dict[str, Any]:
        user_id = str(request.args.get("user_id", "")).strip()
        if not user_id:
            return self._error("缺少 user_id")
        try:
            async with self.plugin._data_lock:
                user = deepcopy((self.plugin.data.get("users") or {}).get(user_id))
            if not isinstance(user, dict):
                return self._error("用户不存在")
            detail = self._user_summary(user_id, user)
            detail.update(
                {
                    "memory": user.get("companion_memory") if isinstance(user.get("companion_memory"), dict) else {},
                    "expression_profile": user.get("expression_profile") if isinstance(user.get("expression_profile"), dict) else {},
                    "intent_profile": user.get("intent_profile") if isinstance(user.get("intent_profile"), dict) else {},
                    "relationship_state": user.get("relationship_state") if isinstance(user.get("relationship_state"), dict) else {},
                    "behavior_habits": self._behavior_habit_summary(user),
                    "dialogue_episodes": self._limited_list(user.get("dialogue_episodes"), 12),
                    "open_loops": self._limited_list(user.get("open_loops"), 12),
                    "recent_reply_topics": self._limited_list(user.get("recent_reply_topics"), 16),
                    "last_user_message": self._display_message_text(user.get("last_user_message"), 500),
                    "last_companion_message": self._display_message_text(user.get("last_companion_message"), 500),
                    "formatted": {
                        "relationship": self.plugin._format_relationship_summary(user),
                        "action_affinity": self.plugin._format_action_affinity_summary(user),
                        "next_proactive": self.plugin._format_next_proactive(user),
                    },
                }
            )
            return self._ok(detail)
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取用户详情失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def update_user(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        user_id = str(payload.get("user_id", "")).strip()
        if not user_id:
            return self._error("缺少 user_id")
        try:
            async with self.plugin._data_lock:
                user = self.plugin._get_user(user_id)
                if "enabled" in payload:
                    enabled = bool(payload.get("enabled"))
                    user["enabled"] = enabled
                    user["manual_enabled"] = enabled
                    user["manual_disabled"] = not enabled
                    if not enabled:
                        self.plugin._clear_pending_proactive_plan(user)
                if "nickname" in payload:
                    user["nickname"] = self._single_line(payload.get("nickname"), 24)
                if "style" in payload:
                    user["style"] = self._single_line(payload.get("style"), 24)
                if payload.get("reset_daily"):
                    user["sent_today"] = 0
                    user["sent_day"] = ""
                    user["ignored_streak"] = 0
                    user["photo_sent_today"] = 0
                    user["photo_sent_day"] = ""
                    user["photo_generated_today"] = 0
                    user["photo_generated_day"] = ""
                    user["screen_peek_today"] = 0
                if payload.get("clear_schedule"):
                    self.plugin._clear_pending_proactive_plan(user)
                if payload.get("clear_learning"):
                    for key, empty in (
                        ("companion_memory", {}),
                        ("expression_profile", {}),
                        ("reply_planner", {}),
                        ("intent_profile", {}),
                        ("relationship_state", {}),
                        ("recent_reply_topics", []),
                        ("dialogue_episodes", []),
                        ("open_loops", []),
                        ("action_preferences", {}),
                    ):
                        user[key] = empty
                    user["episode_message_count"] = 0
                    user["last_episode_refresh_at"] = 0
                    user["last_memory_refresh_at"] = 0
                self.plugin._save_data_sync()
                snapshot = deepcopy(user)
            return self._ok(self._user_summary(user_id, snapshot))
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新用户失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def list_groups(self) -> dict[str, Any]:
        try:
            limit = self._query_int("limit", 80, 1, 300)
            async with self.plugin._data_lock:
                groups = deepcopy(self.plugin.data.get("groups", {}))
            if not isinstance(groups, dict):
                groups = {}
            items = [self._group_summary(group_id, group) for group_id, group in groups.items() if isinstance(group, dict)]
            items.sort(key=lambda item: item.get("last_seen_ts") or 0, reverse=True)
            return self._ok({"items": items[:limit], "total": len(items)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取群列表失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def get_group(self) -> dict[str, Any]:
        group_id = str(request.args.get("group_id", "")).strip()
        if not group_id:
            return self._error("缺少 group_id")
        try:
            async with self.plugin._data_lock:
                group = deepcopy((self.plugin.data.get("groups") or {}).get(group_id))
            if not isinstance(group, dict):
                return self._error("群不存在")
            detail = self._group_summary(group_id, group)
            detail.update(
                {
                    "members": group.get("members") if isinstance(group.get("members"), dict) else {},
                    "recent_messages": self._limited_list(group.get("recent_messages"), 30),
                    "topic_threads": self._group_topic_thread_items(group),
                    "group_episodes": self._limited_list(group.get("group_episodes"), 12),
                    "relationship_edges": group.get("relationship_edges") if isinstance(group.get("relationship_edges"), dict) else {},
                    "interjection_feedback": group.get("interjection_feedback") if isinstance(group.get("interjection_feedback"), dict) else {},
                    "last_bot_interjection": group.get("last_bot_interjection") if isinstance(group.get("last_bot_interjection"), dict) else {},
                    "group_wakeup_logs": self._group_wakeup_logs(group),
                    "formatted": {
                        "status": self.plugin._format_group_status(group),
                        "feedback": self.plugin._format_group_interjection_feedback(group),
                        "relationship_graph": self.plugin._format_group_relationship_graph_for_prompt(group),
                    },
                }
            )
            return self._ok(detail)
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取群详情失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def update_group(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        group_id = str(payload.get("group_id", "")).strip()
        if not group_id:
            return self._error("缺少 group_id")
        try:
            async with self.plugin._data_lock:
                group = self.plugin._get_group(group_id)
                if "enabled" in payload:
                    group["enabled"] = bool(payload.get("enabled"))
                if payload.get("reset_interjection"):
                    group["last_interject_at"] = 0
                    group["interject_day"] = ""
                    group["interject_today"] = 0
                    group["last_bot_interjection"] = {}
                    group["interjection_feedback"] = {}
                if payload.get("clear_observation"):
                    enabled = bool(group.get("enabled", True))
                    group.clear()
                    group.update(
                        {
                            "enabled": enabled,
                            "group_id": group_id,
                            "message_count": 0,
                            "last_seen": 0,
                            "last_interject_at": 0,
                            "interject_day": "",
                            "interject_today": 0,
                            "recent_messages": [],
                            "members": {},
                            "slang_terms": [],
                            "slang_meanings": {},
                            "topic_signatures": [],
                            "topic_threads": [],
                            "group_episodes": [],
                            "relationship_edges": {},
                            "interjection_feedback": {},
                            "last_bot_interjection": {},
                            "last_speaker": {},
                            "atmosphere": {},
                            "last_summary_at": 0,
                            "last_episode_refresh_at": 0,
                            "last_slang_summary_at": 0,
                        }
                    )
                self.plugin._save_data_sync()
                snapshot = deepcopy(group)
            return self._ok(self._group_summary(group_id, snapshot))
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新群失败: {exc}", exc_info=True)
            return self._error(str(exc))

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
                    changed[key] = bool(value)
            for key, value in (payload.get("providers") or {}).items():
                if key in self._allowed_provider_keys():
                    changed[key] = self._single_line(value, 160)
            for key, value in (payload.get("settings") or {}).items():
                if key in self._allowed_setting_keys():
                    changed[key] = self._normalize_setting_value(key, value)
            for key, value in changed.items():
                self._apply_config_value(key, value)
            if changed:
                self._save_config_if_possible()
            overview = await self.get_overview()
            if overview.get("success"):
                overview["data"]["changed"] = changed
                overview["data"]["config_saved"] = self._can_save_config()
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
                    return self._error("没有找到这本夹层藏书")
                updater = getattr(self.plugin, "_update_private_reading_preference_profile", None)
                if callable(updater):
                    updater(target)
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"bookshelf": await self._bookshelf_summary(data, unlocked=True, access_token=access_token)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 保存夹层藏书评分失败: {exc}", exc_info=True)
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
                    return self._error("没有找到这本夹层藏书")
                updater = getattr(self.plugin, "_update_private_reading_preference_profile", None)
                if callable(updater):
                    updater(target)
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"bookshelf": await self._bookshelf_summary(data, unlocked=True, access_token=access_token)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 保存夹层藏书标签失败: {exc}", exc_info=True)
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
                    return self._error("没有找到这本夹层藏书")
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
                    return self._error("没有找到可写回的夹层藏书")
                updater = getattr(self.plugin, "_update_private_reading_preference_profile", None)
                if callable(updater):
                    updater(target)
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            return self._ok({"message": "Bot 已重新读过并更新读后感", "bookshelf": await self._bookshelf_summary(data, unlocked=True, access_token=access_token)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新夹层藏书批注失败: {exc}", exc_info=True)
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
        user_id = self._single_line(payload.get("user_id"), 40)
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
                if not user_id.isdigit() or len(user_id) < 5:
                    return self._error("关系节点必须使用有效 QQ 号作为身份键")
                deleted = self.plugin.data.setdefault("worldbook_deleted_member_ids", [])
                if isinstance(deleted, list) and user_id in deleted:
                    self.plugin.data["worldbook_deleted_member_ids"] = [item for item in deleted if str(item) != user_id]
                profile = profiles.get(user_id)
                if not isinstance(profile, dict):
                    profile = {
                        "user_id": user_id,
                        "name": user_id,
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
                if "enabled" in payload:
                    profile["enabled"] = bool(payload.get("enabled"))
                if "name" in payload:
                    profile["name"] = self._single_line(payload.get("name"), 80) or user_id
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
                self.plugin._save_data_sync()
                data = deepcopy(self.plugin.data)
            if payload.keys() <= {"user_id", "enabled"}:
                message = "已更新关系节点状态"
            elif "important_memories" in payload and len(payload) <= 2:
                message = "已更新重要记忆"
            else:
                message = "已保存关系节点"
            return self._ok({"message": message, "worldbook": self._worldbook_summary(data)})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新关系节点失败: {exc}", exc_info=True)
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
                    self._apply_config_value(key, bool(value))
            self._save_config_if_possible()
            overview = await self.get_overview()
            if overview.get("success"):
                overview["data"]["preset"] = name
                overview["data"]["preset_label"] = preset.get("label", name)
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
                raw_keywords = payload.get("keywords")
                if isinstance(raw_keywords, list):
                    keywords = [self._single_line(item, 24) for item in raw_keywords]
                else:
                    keywords = [self._single_line(item, 24) for item in re.split(r"[,，、\n]+", str(raw_keywords or ""))]
                keywords = [item for item in keywords if item][:16] or [name]
                skill = dict(existing) if isinstance(existing, dict) else {}
                skill.update(
                    {
                        "id": skill_id,
                        "name": name,
                        "category": self._single_line(payload.get("category"), 20) or self._single_line(skill.get("category"), 20) or "能力",
                        "keywords": keywords,
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
        return {
            "user_id": user_id_text,
            "display_name": display_name,
            "is_qq_user": is_qq_user,
            "source": source,
            "enabled": bool(user.get("enabled", True)),
            "nickname": user.get("nickname", ""),
            "style": user.get("style", ""),
            "umo": user.get("umo", ""),
            "last_seen_ts": last_seen,
            "last_seen": self.plugin._format_timestamp_elapsed(last_seen),
            "last_sent_ts": last_sent,
            "last_sent": self.plugin._format_timestamp_elapsed(last_sent),
            "sent_today": user.get("sent_today", 0),
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
        return cls._single_line(_strip_internal_message_blocks(value), limit)

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
            items.append(
                {
                    "id": self._single_line(raw.get("id"), 32),
                    "name": self._single_line(raw.get("name"), 32),
                    "category": self._single_line(raw.get("category"), 24),
                    "keywords": [self._single_line(item, 24) for item in keywords if self._single_line(item, 24)][:16],
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
        items.sort(key=lambda item: (item["level"], item["exp"], item["training_count"]), reverse=True)
        return {
            "enabled": bool(getattr(self.plugin, "enable_skill_growth_simulation", False)),
            "rate": float(getattr(self.plugin, "skill_growth_rate", 1.0) or 1.0),
            "schedule_influence": bool(getattr(self.plugin, "enable_skill_growth_schedule_influence", False)),
            "schedule_influence_strength": float(getattr(self.plugin, "skill_growth_schedule_influence_strength", 0.35) or 0.0),
            "updated": self.plugin._format_timestamp_elapsed(state.get("updated_ts", 0)),
            "skill_count": len(items),
            "items": items[:24],
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
            "enable_mai_style_integration",
            "enable_companion_memory",
            "enable_expression_learning",
            "enable_companion_reply_planner",
            "enable_intent_emotion_analysis",
            "enable_response_self_review",
            "enable_passive_topic_suppression",
            "enable_relationship_state_machine",
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
            "enable_message_debounce",
            "enable_environment_perception",
            "enable_holiday_perception",
            "enable_platform_perception",
            "enable_model_perception",
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "enable_group_companion",
            "enable_group_slang_learning",
            "enable_group_member_profiles",
            "enable_group_context_injection",
            "enable_forward_message_adaptation",
            "enable_group_scene_awareness",
            "enable_group_reality_promise_guard",
            "enable_group_wakeup_enhancement",
            "enable_group_high_intensity_mode",
            "enable_private_image_self_recognition",
            "enable_group_conversation_followup",
            "enable_group_interjection",
            "enable_group_repeat_follow",
            "enable_group_topic_threads",
            "enable_group_episode_memory",
            "enable_group_interjection_feedback",
            "enable_group_slang_meanings",
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
            "enable_private_reading_integration",
            "enable_private_reading_boredom_read",
            "enable_private_reading_ask_recommendation",
            "enable_private_reading_preference_influence",
            "enable_unanswered_screen_peek_followup",
            "enable_yesterday_screen_diary_context",
            "enable_creative_writing",
            "creative_hidden_mode",
        ]
        values = {key: bool(getattr(self.plugin, key, False)) for key in keys}
        try:
            private_reading_available = bool(getattr(self.plugin, "_jm_cosmos_available", lambda: False)())
        except Exception:
            private_reading_available = False
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
            "RELATIONSHIP_ANALYSIS_PROVIDER_ID",
            "COMPANION_MEMORY_PROVIDER_ID",
            "DIALOGUE_EPISODE_PROVIDER_ID",
            "GROUP_INTERJECT_PROVIDER_ID",
            "GROUP_EPISODE_PROVIDER_ID",
            "GROUP_SLANG_PROVIDER_ID",
            "GROUP_FOLLOWUP_JUDGE_PROVIDER_ID",
            "FORWARD_MESSAGE_PROVIDER_ID",
            "PLUGIN_VISION_PROVIDER_ID",
            "NEWS_PROVIDER_ID",
            "WEB_EXPLORATION_PROVIDER_ID",
        ]
        values = {key: self._config_get(key) for key in keys}
        if not values.get("PLUGIN_VISION_PROVIDER_ID"):
            values["PLUGIN_VISION_PROVIDER_ID"] = (
                str(getattr(self.plugin, "jm_cosmos_vision_provider_id", "") or "")
            )
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
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "default_nickname",
            "default_style",
            "schedule_persona_prompt",
            "schedule_worldview_prompt",
            "roleplay_user_profile_prompt",
            "worldview_adaptation_mode",
            "worldview_adaptation_prompt",
            "quiet_hours",
            "daily_token_limit",
            "enable_daily_token_soft_limit",
            "daily_token_soft_limit",
            "humanized_state_intensity",
            "check_interval_seconds",
            "idle_minutes",
            "min_interval_minutes",
            "max_daily_messages",
            "inbound_message_debounce_seconds",
            "enable_message_debounce",
            "text_message_debounce_seconds",
            "image_message_debounce_seconds",
            "forward_message_debounce_seconds",
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
            "enable_private_image_self_recognition",
            "private_image_self_recognition_hint",
            "enable_private_image_vision_cache",
            "private_image_vision_cache_max_items",
            "screen_diary_context_max_chars",
            "enable_segmented_proactive_reply",
            "segmented_proactive_scope",
            "segmented_proactive_threshold",
            "segmented_proactive_min_segment_chars",
            "segmented_proactive_max_segments",
            "segmented_proactive_split_mode",
            "segmented_proactive_regex",
            "segmented_proactive_split_words",
            "enable_segmented_proactive_content_cleanup",
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
            "enable_forward_message_adaptation",
            "forward_message_mode",
            "forward_message_max_messages",
            "forward_message_max_chars",
            "forward_message_parse_nested",
            "forward_message_image_vision",
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
            "enable_skill_growth_simulation",
            "skill_growth_rate",
            "skill_growth_custom_skills",
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
            "ai_daily_sources",
            "ai_daily_source_uid",
            "ai_daily_check_window",
            "ai_daily_check_interval_minutes",
            "ai_daily_prefer_text_version",
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
            "enable_qzone_life_publish",
            "qzone_life_publish_min_interval_hours",
            "qzone_life_publish_probability",
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
                "group_repeat_follow_probability": int(round(float(getattr(self.plugin, "group_repeat_follow_probability", 0.18) or 0) * 100)),
                "group_repeat_interrupt_probability": int(round(float(getattr(self.plugin, "group_repeat_interrupt_probability", 0.10) or 0) * 100)),
                "group_repeat_interrupt_probability_step": int(round(float(getattr(self.plugin, "group_repeat_interrupt_probability_step", 0.12) or 0) * 100)),
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
                    "重启插件会自动关闭 enable_environment_perception，或手动二选一",
                )
            else:
                add("ok", "环境感知由外部插件接管", "检测到 LLMPerception，本插件内置环境感知已关闭")

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
                    "重启插件会自动关闭 enable_group_scene_awareness，或手动二选一",
                )
            else:
                add("ok", "群聊场景感知由外部插件接管", "检测到 context_aware，本插件对应内置功能已关闭")

        atrelay_installed = bool(getattr(self.plugin, "_atrelay_plugin_available", lambda: False)())
        if atrelay_installed:
            if features.get("enable_atrelay_tools"):
                add(
                    "warn",
                    "检测到艾特群友插件",
                    "本插件已内置跨群转述与 @ 群友工具；两者同时启用可能让模型看到重复工具",
                    "重启插件会自动关闭 enable_atrelay_tools，或手动二选一",
                )
            else:
                add("ok", "跨群转述由外部插件接管", "检测到 atrelay，本插件对应内置工具已关闭")

        if not features.get("enable_group_privacy_guard"):
            add("warn", "群聊隐私保护未开启", "私聊记忆注入群聊时缺少额外防护", "建议打开 enable_group_privacy_guard")

        refresh_minutes = int(getattr(self.plugin, "memory_refresh_interval_minutes", 0) or 0)
        if refresh_minutes and refresh_minutes < 60:
            add("warn", "长期记忆整理过于频繁", f"当前 {refresh_minutes} 分钟，可能增加模型调用量", "建议设置为 120 分钟以上")

        return items

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

    def _apply_config_value(self, key: str, value: Any) -> None:
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
            "RELATIONSHIP_ANALYSIS_PROVIDER_ID": "relationship_analysis_provider_id",
            "COMPANION_MEMORY_PROVIDER_ID": "companion_memory_provider_id",
            "DIALOGUE_EPISODE_PROVIDER_ID": "dialogue_episode_provider_id",
            "GROUP_INTERJECT_PROVIDER_ID": "group_interject_provider_id",
            "GROUP_EPISODE_PROVIDER_ID": "group_episode_provider_id",
            "GROUP_SLANG_PROVIDER_ID": "group_slang_provider_id",
            "GROUP_FOLLOWUP_JUDGE_PROVIDER_ID": "group_followup_judge_provider_id",
            "FORWARD_MESSAGE_PROVIDER_ID": "forward_message_provider_id",
            "PLUGIN_VISION_PROVIDER_ID": "jm_cosmos_vision_provider_id",
            "PRIVATE_READING_VISION_PROVIDER_ID": "jm_cosmos_vision_provider_id",
            "NEWS_PROVIDER_ID": "news_provider_id",
            "WEB_EXPLORATION_PROVIDER_ID": "web_exploration_provider_id",
        }
        if key in attr_map:
            setattr(self.plugin, attr_map[key], str(value or "").strip())
            if key == "PLUGIN_VISION_PROVIDER_ID":
                self._set_config_value("PRIVATE_READING_VISION_PROVIDER_ID", str(value or "").strip())
            elif key == "PRIVATE_READING_VISION_PROVIDER_ID" and not self._config_get("PLUGIN_VISION_PROVIDER_ID"):
                self._set_config_value("PLUGIN_VISION_PROVIDER_ID", str(value or "").strip())
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
        if key in self._allowed_feature_keys():
            setattr(self.plugin, key, bool(value))
            return
        if key in self._allowed_setting_keys():
            setattr(self.plugin, key, value)

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

    def _config_get(self, key: str) -> str:
        config = getattr(self.plugin, "config", None)
        if isinstance(config, dict):
            return str(config.get(key, "") or "")
        return ""

    def _save_config_if_possible(self) -> None:
        config = getattr(self.plugin, "config", None)
        for method_name in ("save_config", "save", "save_conf"):
            save = getattr(config, method_name, None)
            if callable(save):
                try:
                    save()
                    return
                except TypeError:
                    continue

    def _can_save_config(self) -> bool:
        config = getattr(self.plugin, "config", None)
        return any(callable(getattr(config, method_name, None)) for method_name in ("save_config", "save", "save_conf"))

    @staticmethod
    def _allowed_feature_keys() -> set[str]:
        return {
            "enable_mai_style_integration",
            "enable_companion_memory",
            "enable_expression_learning",
            "enable_companion_reply_planner",
            "enable_intent_emotion_analysis",
            "enable_response_self_review",
            "enable_passive_topic_suppression",
            "enable_relationship_state_machine",
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
            "enable_message_debounce",
            "enable_environment_perception",
            "enable_holiday_perception",
            "enable_platform_perception",
            "enable_model_perception",
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "enable_group_companion",
            "enable_group_slang_learning",
            "enable_group_member_profiles",
            "enable_group_context_injection",
            "enable_forward_message_adaptation",
            "enable_group_reality_promise_guard",
            "enable_group_wakeup_enhancement",
            "enable_group_high_intensity_mode",
            "enable_private_image_self_recognition",
            "enable_group_conversation_followup",
            "enable_group_interjection",
            "enable_group_repeat_follow",
            "enable_group_topic_threads",
            "enable_group_episode_memory",
            "enable_group_interjection_feedback",
            "enable_group_slang_meanings",
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
            "ai_daily_sources",
            "ai_daily_source_uid",
            "ai_daily_check_window",
            "ai_daily_check_interval_minutes",
            "ai_daily_prefer_text_version",
            "enable_external_event_self_link",
            "enable_web_exploration",
            "enable_web_exploration_boredom_search",
            "enable_qzone_integration",
            "enable_qzone_life_publish",
            "enable_private_reading_integration",
            "enable_private_reading_boredom_read",
            "enable_private_reading_ask_recommendation",
            "enable_private_reading_preference_influence",
            "enable_unanswered_screen_peek_followup",
            "enable_yesterday_screen_diary_context",
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
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "default_nickname",
            "default_style",
            "schedule_persona_prompt",
            "schedule_worldview_prompt",
            "roleplay_user_profile_prompt",
            "worldview_adaptation_mode",
            "worldview_adaptation_prompt",
            "quiet_hours",
            "daily_token_limit",
            "enable_daily_token_soft_limit",
            "daily_token_soft_limit",
            "humanized_state_intensity",
            "check_interval_seconds",
            "idle_minutes",
            "min_interval_minutes",
            "max_daily_messages",
            "inbound_message_debounce_seconds",
            "enable_message_debounce",
            "text_message_debounce_seconds",
            "image_message_debounce_seconds",
            "forward_message_debounce_seconds",
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
            "enable_private_image_self_recognition",
            "private_image_self_recognition_hint",
            "enable_private_image_vision_cache",
            "private_image_vision_cache_max_items",
            "enable_segmented_proactive_reply",
            "segmented_proactive_scope",
            "segmented_proactive_threshold",
            "segmented_proactive_min_segment_chars",
            "segmented_proactive_max_segments",
            "segmented_proactive_split_mode",
            "segmented_proactive_regex",
            "segmented_proactive_split_words",
            "enable_segmented_proactive_content_cleanup",
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
            "group_interject_min_interval_minutes",
            "group_interject_max_daily",
            "group_repeat_follow_probability",
            "group_repeat_interrupt_probability",
            "group_repeat_interrupt_probability_step",
            "group_repeat_interrupt_text",
            "group_repeat_interrupt_image_path",
            "group_scene_recent_limit",
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
            "enable_forward_message_adaptation",
            "forward_message_mode",
            "forward_message_max_messages",
            "forward_message_max_chars",
            "forward_message_parse_nested",
            "forward_message_image_vision",
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
            "enable_skill_growth_simulation",
            "skill_growth_rate",
            "skill_growth_custom_skills",
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
            "enable_qzone_life_publish",
            "qzone_life_publish_min_interval_hours",
            "qzone_life_publish_probability",
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
        if key in {"group_wakeup_direct_words", "group_wakeup_context_words", "group_wakeup_interest_keywords"}:
            return str(value or "").strip()[:1200]
        if key == "private_image_self_recognition_hint":
            return str(value or "").strip()[:1200]
        if key == "worldview_adaptation_mode":
            mode = str(value or "auto").strip()
            return mode if mode in {"auto", "modern", "fantasy", "sci_fi", "custom", "off"} else "auto"
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
        if key == "segmented_proactive_interval_method":
            mode = str(value or "log").strip().lower()
            return mode if mode in {"log", "random"} else "log"
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
        if key in {
            "check_interval_seconds",
            "daily_token_limit",
            "daily_token_soft_limit",
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
        }:
            try:
                parsed = max(0, int(value))
                return parsed
            except (TypeError, ValueError):
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
        if key == "private_image_vision_wait_seconds":
            try:
                return max(0.0, min(90.0, float(value)))
            except (TypeError, ValueError):
                return 30.0
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
            "enable_lunar_perception",
            "enable_solar_term_perception",
            "enable_almanac_perception",
            "enable_humanized_states",
            "inject_passive_states",
            "enable_cycle_state",
            "enable_worldbook_member_recognition",
            "enable_group_scene_awareness",
            "enable_group_reality_promise_guard",
            "enable_group_wakeup_enhancement",
            "enable_group_high_intensity_mode",
            "enable_group_repeat_follow",
            "enable_forward_message_adaptation",
            "enable_skill_growth_simulation",
            "enable_skill_growth_schedule_influence",
            "forward_message_parse_nested",
            "forward_message_image_vision",
            "enable_message_debounce",
            "enable_semantic_message_debounce",
            "enable_proactive_quote_trigger_message",
            "enable_local_photo_load_guard",
            "enable_private_image_self_recognition",
            "enable_private_image_vision_cache",
            "enable_segmented_proactive_reply",
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
            return bool(value)
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
                    "name": self._single_line(item.get("name"), 60),
                    "enabled": bool(item.get("enabled", True)),
                    "priority": item.get("priority", 120),
                    "aliases": [self._single_line(alias, 40) for alias in aliases if self._single_line(alias, 40)],
                    "observed_names": [self._single_line(name, 40) for name in observed if self._single_line(name, 40)],
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
            "enabled": bool(getattr(self.plugin, "enable_livingmemory_integration", False)),
            "available": available,
            "tool_name": getattr(self.plugin, "livingmemory_tool_name", ""),
            "plugin_dir": plugin_dir,
            "status": status,
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
            "enabled": bool(getattr(self.plugin, "enable_bilibili_integration", False)),
            "boredom_watch_enabled": bool(getattr(self.plugin, "enable_bilibili_boredom_watch", False)),
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
            "enabled": bool(getattr(self.plugin, "enable_qzone_integration", False)),
            "life_publish_enabled": bool(getattr(self.plugin, "enable_qzone_life_publish", False)),
            "available": available,
            "last_life_publish_at": self.plugin._format_timestamp_elapsed(state.get("last_life_publish_at", 0)),
            "last_status": state.get("last_life_publish_status", ""),
            "last_text": state.get("last_life_publish_text", ""),
        }

    def _jm_cosmos_summary(self, data: dict[str, Any]) -> dict[str, Any]:
        state = data.get("jm_cosmos_integration") if isinstance(data.get("jm_cosmos_integration"), dict) else {}
        try:
            available = bool(getattr(self.plugin, "_jm_cosmos_available", lambda: False)())
        except Exception:
            available = False
        album = state.get("last_album") if isinstance(state.get("last_album"), dict) else {}
        return {
            "enabled": bool(getattr(self.plugin, "enable_jm_cosmos_integration", False)),
            "boredom_read_enabled": bool(getattr(self.plugin, "enable_jm_cosmos_boredom_read", False)),
            "ask_recommendation_enabled": bool(getattr(self.plugin, "enable_private_reading_ask_recommendation", False)),
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
                    "title": meta.get("title") or f"夹层藏书 {album_id}",
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
                    album_description = "；".join(detail_parts) or "这本藏书暂时没有整理出明确简介。"
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
                        "category": "夹层藏书",
                        "album_id": album_id,
                        "title": self._single_line(item.get("title"), 100) or "未命名藏书",
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
        total_attempts = 0
        for item in raw[-240:]:
            if not isinstance(item, dict):
                continue
            repeat_count = max(1, self._int(item.get("repeat_count")))
            status = self._single_line(item.get("status"), 24) or "unknown"
            user_id = self._single_line(item.get("user_id"), 32)
            user = users.get(user_id) if isinstance(users, dict) else None
            if status != "sent" and not bool(
                isinstance(user, dict)
                and getattr(self.plugin, "_user_enabled_for_proactive", lambda uid, profile: bool(profile and profile.get("enabled", True)))(
                    user_id,
                    user,
                )
            ):
                continue
            total_attempts += repeat_count
            source = self._single_line(item.get("source"), 40) or "unknown"
            display_source = "bookshelf_reading" if source == "jm_cosmos" else source
            counts[status] = counts.get(status, 0) + repeat_count
            source_counts[display_source] = source_counts.get(display_source, 0) + repeat_count
            scheduled = self._float(item.get("scheduled_ts"))
            created = self._float(item.get("created_ts"))
            last_seen = self._float(item.get("last_seen_ts")) or created
            reason = self._single_line(item.get("reason"), 40)
            action = self._single_line(item.get("action"), 40)
            if reason == "jm_cosmos_share":
                reason = "bookshelf_reading_share"
            if reason == "jm_cosmos_recommendation_request":
                reason = "bookshelf_recommendation_request"
            if action == "jm_cosmos_read":
                action = "bookshelf_reading"
            signature = self._single_line(item.get("signature"), 120)
            topic = self._single_line(item.get("topic"), 100)
            motive = self._single_line(item.get("motive"), 180)
            note = self._single_line(item.get("note"), 160)
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
            "items": items[:60],
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
                today_exempt_tokens = sum(
                    self._int(bucket.get("total_tokens"))
                    for task, bucket in today_tasks.items()
                    if str(task) in {"proactive_framework", "voice_framework"} and isinstance(bucket, dict)
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
