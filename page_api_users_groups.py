# -*- coding: utf-8 -*-
from __future__ import annotations

from copy import deepcopy
from typing import Any

from astrbot.api import logger
from quart import request

from .helpers import _safe_int


class PrivateCompanionPageApiUsersGroupsMixin:
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
                worldbook_member = self._worldbook_member_for_private_user_locked(self.plugin.data, user_id, user if isinstance(user, dict) else {})
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
                    "worldbook_member": worldbook_member,
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
                    if enabled:
                        self.plugin._ensure_private_user_umo(user_id, user)
                    if not enabled:
                        self.plugin._clear_pending_proactive_plan(user)
                if "nickname" in payload:
                    user["nickname"] = self._single_line(payload.get("nickname"), 24)
                if "style" in payload:
                    user["style"] = self._single_line(payload.get("style"), 24)
                if "relationship_role" in payload:
                    role = self.plugin._normalize_private_user_role(payload.get("relationship_role"))
                    if role:
                        user["relationship_role"] = role
                if "proactive_daily_limit" in payload:
                    user["proactive_daily_limit"] = max(-1, _safe_int(payload.get("proactive_daily_limit"), -1))
                if any(key in payload for key in ("nickname", "style", "relationship_role", "proactive_daily_limit")):
                    for key in (
                        "proactive_idle_minutes",
                        "proactive_min_interval_minutes",
                        "photo_daily_limit",
                        "screen_peek_daily_limit",
                        "poke_daily_limit",
                    ):
                        user[key] = -1
                    user["proactive_boundary_note"] = ""
                if self.plugin._private_user_role(user, user_id) == "friend":
                    user["photo_daily_limit"] = -1
                    user["photo_sent_today"] = 0
                    user["photo_sent_day"] = ""
                    user["photo_generated_today"] = 0
                    user["photo_generated_day"] = ""
                    user["last_generated_photo_path"] = ""
                    user["last_generated_photo_at"] = 0
                    user["screen_peek_daily_limit"] = -1
                    user["screen_peek_today"] = 0
                    user["screen_peek_day"] = ""
                    user["screen_peek_last_at"] = 0
                if "proactive_boundary_note" in payload:
                    user["proactive_boundary_note"] = self._single_line(payload.get("proactive_boundary_note"), 180)
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
                if payload.get("clear_emotion_state"):
                    user["intent_profile"] = {}
                    user["relationship_state"] = {}
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
            visible_groups = [
                (group_id, group)
                for group_id, group in groups.items()
                if isinstance(group, dict) and not self._looks_like_member_shadow_group(str(group_id), group)
            ]
            shadow_count = len(groups) - len(visible_groups)
            items = [self._group_summary(group_id, group) for group_id, group in visible_groups]
            items.sort(key=lambda item: item.get("last_seen_ts") or 0, reverse=True)
            return self._ok({"items": items[:limit], "total": len(items), "shadow_total": shadow_count})
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 获取群列表失败: {exc}", exc_info=True)
            return self._error(str(exc))

    def _looks_like_member_shadow_group(self, group_id: str, group: dict[str, Any]) -> bool:
        """Hide historical records created when a sender id was mistaken for a group id."""
        gid = str(group_id or group.get("group_id") or "").strip()
        if not gid or not gid.isdigit():
            return False
        configured = set(self.plugin._configured_group_ids()) | set(self.plugin._configured_group_blacklist_ids())
        if gid in configured:
            return False
        recent = group.get("recent_messages") if isinstance(group.get("recent_messages"), list) else []
        sender_ids = [
            str(item.get("sender_id") or "").strip()
            for item in recent
            if isinstance(item, dict) and str(item.get("sender_id") or "").strip()
        ]
        if not sender_ids:
            return False
        members = group.get("members") if isinstance(group.get("members"), dict) else {}
        same_sender_hits = sum(1 for sender_id in sender_ids if sender_id == gid)
        unique_senders = {sender_id for sender_id in sender_ids if sender_id}
        if gid in members and same_sender_hits >= max(1, int(len(sender_ids) * 0.8)) and len(unique_senders) <= 2:
            return True
        if not self._single_line(group.get("name") or group.get("group_name"), 80) and same_sender_hits == len(sender_ids) and len(members) <= 2:
            return True
        return False
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
                    "last_bot_interjection": self._sanitize_last_bot_interjection(group.get("last_bot_interjection")),
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
