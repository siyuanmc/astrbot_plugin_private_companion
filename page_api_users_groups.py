# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from copy import deepcopy
from datetime import datetime
from typing import Any

from astrbot.api import logger
from quart import request

from .helpers import _safe_int


class PrivateCompanionPageApiUsersGroupsMixin:
    async def list_users(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            limit = self._query_int("limit", 80, 1, 300)
            async with self.plugin._data_lock:
                users = self.plugin.data.get("users", {})
                if not isinstance(users, dict):
                    users = {}
                user_items = [(user_id, dict(user)) for user_id, user in users.items() if isinstance(user, dict)]
            items = [self._user_summary(user_id, user) for user_id, user in user_items]
            items.sort(key=lambda item: item.get("last_seen_ts") or 0, reverse=True)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if elapsed_ms > 1200:
                logger.warning("[PrivateCompanionPage] 用户列表接口耗时较高: elapsed=%sms users=%s", elapsed_ms, len(items))
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
                    "expression_profile": self._expression_profile_summary(user),
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
            action_message = ""
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
                    user["proactive_daily_limit"] = _safe_int(payload.get("proactive_daily_limit"), -1, -1, 30)
                for key in (
                    "proactive_idle_minutes",
                    "proactive_min_interval_minutes",
                    "photo_daily_limit",
                    "screen_peek_daily_limit",
                    "poke_daily_limit",
                ):
                    if key in payload:
                        user[key] = _safe_int(payload.get(key), -1, -1)
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
                if payload.get("clear_open_loops"):
                    action_message = self.plugin._remove_open_loop_entry(user, "全部")
                remove_open_loop_text = self._single_line(payload.get("remove_open_loop_text"), 120)
                if remove_open_loop_text:
                    action_message = self.plugin._remove_open_loop_entry(user, remove_open_loop_text)
                expression_action = self._single_line(payload.get("expression_action"), 40)
                if expression_action:
                    action_message = self._apply_expression_profile_action(user, payload)
                self.plugin._save_data_sync()
                snapshot = deepcopy(user)
            result = self._user_summary(user_id, snapshot)
            result.update(
                {
                    "expression_profile": self._expression_profile_summary(snapshot),
                }
            )
            if action_message:
                result["message"] = action_message
            return self._ok(result)
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新用户失败: {exc}", exc_info=True)
            return self._error(str(exc))
    async def list_groups(self) -> dict[str, Any]:
        start = time.perf_counter()
        try:
            limit = self._query_int("limit", 80, 1, 300)
            async with self.plugin._data_lock:
                groups = self.plugin.data.get("groups", {})
                if not isinstance(groups, dict):
                    groups = {}
                visible_groups = [
                    (group_id, dict(group))
                    for group_id, group in groups.items()
                    if isinstance(group, dict) and not self._looks_like_member_shadow_group(str(group_id), group)
                ]
                shadow_count = len(groups) - len(visible_groups)
            items = [self._group_summary(group_id, group) for group_id, group in visible_groups]
            items.sort(key=lambda item: item.get("last_seen_ts") or 0, reverse=True)
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            if elapsed_ms > 1200:
                logger.warning("[PrivateCompanionPage] 群列表接口耗时较高: elapsed=%sms groups=%s", elapsed_ms, len(items))
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
                    "slang_items": self._group_slang_items(group),
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

    async def delete_group(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        group_id = str(payload.get("group_id", "")).strip()
        if not group_id:
            return self._error("缺少 group_id")
        try:
            async with self.plugin._data_lock:
                groups = self.plugin.data.get("groups")
                if not isinstance(groups, dict):
                    groups = {}
                    self.plugin.data["groups"] = groups
                removed_group = groups.pop(group_id, None) is not None

                whitelist = [
                    str(item).strip()
                    for item in (getattr(self.plugin, "group_whitelist_ids", []) or [])
                    if str(item).strip() and str(item).strip() != group_id
                ]
                blacklist = [
                    str(item).strip()
                    for item in (getattr(self.plugin, "group_blacklist_ids", []) or [])
                    if str(item).strip() and str(item).strip() != group_id
                ]
                removed_whitelist = len(whitelist) != len(getattr(self.plugin, "group_whitelist_ids", []) or [])
                removed_blacklist = len(blacklist) != len(getattr(self.plugin, "group_blacklist_ids", []) or [])
                self._apply_config_value("group_whitelist_ids", whitelist, {"group_whitelist_ids": whitelist, "group_blacklist_ids": blacklist})
                self._apply_config_value("group_blacklist_ids", blacklist, {"group_whitelist_ids": whitelist, "group_blacklist_ids": blacklist})
                self.plugin._save_data_sync()

            config_saved = await self._save_config_if_possible()
            message_parts = []
            if removed_group:
                message_parts.append("已删除群聊观测")
            if removed_whitelist or removed_blacklist:
                message_parts.append("已移出群聊名单")
            message = "，".join(message_parts) if message_parts else "没有找到可删除的群聊记录"
            return self._ok(
                {
                    "group_id": group_id,
                    "removed_group": removed_group,
                    "removed_whitelist": removed_whitelist,
                    "removed_blacklist": removed_blacklist,
                    "config_saved": config_saved,
                    "message": message,
                }
            )
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 删除群失败: {exc}", exc_info=True)
            return self._error(str(exc))

    async def update_group_slang(self) -> dict[str, Any]:
        payload = await request.get_json(silent=True) or {}
        group_id = str(payload.get("group_id", "")).strip()
        term = self._single_line(payload.get("term"), 40)
        if not group_id:
            return self._error("缺少 group_id")
        if not term:
            return self._error("缺少黑话词")
        try:
            async with self.plugin._data_lock:
                group = self.plugin._get_group(group_id)
                terms = group.setdefault("slang_terms", [])
                if not isinstance(terms, list):
                    terms = []
                    group["slang_terms"] = terms
                meanings = group.setdefault("slang_meanings", {})
                if not isinstance(meanings, dict):
                    meanings = {}
                    group["slang_meanings"] = meanings

                if payload.get("delete"):
                    group["slang_terms"] = [
                        item
                        for item in terms
                        if self._single_line(item.get("term") if isinstance(item, dict) else item, 40) != term
                    ]
                    meanings.pop(term, None)
                else:
                    existing_term = None
                    for item in terms:
                        if isinstance(item, dict) and self._single_line(item.get("term"), 40) == term:
                            existing_term = item
                            break
                    if existing_term is None:
                        existing_term = {"term": term, "count": 0, "last_seen": 0}
                        terms.append(existing_term)
                    previous = meanings.get(term) if isinstance(meanings.get(term), dict) else {}
                    confidence_raw = payload.get("confidence") if "confidence" in payload else previous.get("confidence", 0.85)
                    web_match_raw = payload.get("web_match") if "web_match" in payload else previous.get("web_match", 0.0)
                    confidence = max(0.0, min(1.0, self._float(confidence_raw)))
                    web_match = max(0.0, min(1.0, self._float(web_match_raw)))
                    meanings[term] = {
                        "meaning": self._single_line(payload.get("meaning"), 120),
                        "usage": self._single_line(payload.get("usage"), 120),
                        "type": self._single_line(payload.get("type"), 24),
                        "not_owner": self._single_line(payload.get("not_owner"), 90),
                        "evidence": self._single_line(payload.get("evidence"), 160),
                        "web_evidence": self._single_line(payload.get("web_evidence"), 220),
                        "confidence": f"{confidence:.2f}",
                        "web_match": f"{web_match:.2f}" if web_match > 0 else "",
                        "source": "manual",
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
                    }
                    terms.sort(key=lambda item: (_safe_int(item.get("count"), 0) if isinstance(item, dict) else 0), reverse=True)
                self.plugin._save_data_sync()
                snapshot = deepcopy(group)
            detail = self._group_summary(group_id, snapshot)
            detail["slang_items"] = self._group_slang_items(snapshot)
            return self._ok(detail)
        except Exception as exc:
            logger.error(f"[PrivateCompanionPage] 更新群黑话失败: {exc}", exc_info=True)
            return self._error(str(exc))
