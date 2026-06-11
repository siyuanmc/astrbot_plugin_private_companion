# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import uuid
from typing import Any

from astrbot.api.event import AstrMessageEvent
from astrbot.api.event import MessageChain
try:
    from astrbot.api.message_components import At, Plain
except ImportError:
    from astrbot.api.message_components import At, Plain

from .helpers import _now_ts, _safe_float, _safe_int, _single_line


class LlmToolActionsMixin:
    """Implementation bodies for LLM tools registered in main.py."""

    def _qzone_tool_instruction(self) -> str:
        if not (self.enabled and self.enable_qzone_integration):
            return ""
        return """
【QQ 空间动态工具】
当用户明确要求你查看说说、QQ 空间动态、点赞/评论说说,或要求你发一条说说时,可以使用 Private Companion 的 QQ 空间工具。
- 查看说说：使用 `pc_qzone_view_feed`。不知道目标 QQ 时默认当前用户。
- 发布说说：使用 `pc_qzone_publish_feed`。必须把最终要发布的正文放进 `text` 参数,例如 `{"text":"今天想慢一点。"}`；只有用户明确要求发布时才调用；不要把草稿当作已发布。
- 发布内容必须服从当前人格与世界观,但不要泄露私聊隐私、内部状态数值、关系网资料或插件实现。
- 工具失败时简短说明失败原因,不要假装已经发布或点赞。
""".strip()

    async def _pc_qzone_view_feed_impl(self, event: AstrMessageEvent, user_id: str = "", pos: int = 0, like: bool = False, reply: bool = False) -> str:
        if not self.enable_qzone_integration:
            return json.dumps({"status": "disabled", "message": "QQ 空间动态层未启用"}, ensure_ascii=False)
        target = _single_line(user_id, 40)
        if not target:
            try:
                target = str(event.get_sender_id())
            except Exception:
                target = ""
        try:
            posts = await self._qzone_query_feeds(event, target_id=target or None, pos=max(0, int(pos or 0)), num=1, with_detail=True)
            if not posts:
                return json.dumps({"status": "empty", "message": "查询结果为空"}, ensure_ascii=False)
            post = posts[0]
            action_msg = ""
            if reply:
                comment = await self._qzone_comment_post(event, post)
                action_msg = f"已评论：{comment}"
            if like:
                await self._qzone_like_post(event, post)
                action_msg = (action_msg + "；已点赞") if action_msg else "已点赞"
            return json.dumps(
                {
                    "status": "success",
                    "action": action_msg,
                    "author": _single_line(getattr(post, "name", ""), 60),
                    "uin": str(getattr(post, "uin", "") or ""),
                    "text": _single_line(getattr(post, "text", "") or getattr(post, "rt_con", ""), 300),
                    "images": list(getattr(post, "images", []) or [])[:6],
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            return json.dumps({"status": "error", "message": _single_line(exc, 160)}, ensure_ascii=False)

    async def _pc_qzone_publish_feed_impl(self, event: AstrMessageEvent, text: str = "") -> str:
        content = _single_line(text, 300)
        if not content:
            return json.dumps(
                {
                    "status": "need_text",
                    "success": False,
                    "message": "缺少 text 参数。请把要发布的说说正文作为 text 传入,不要空调用。",
                    "required_args": {"text": "要发布到 QQ 空间的说说正文"},
                },
                ensure_ascii=False,
            )
        result = await self._publish_qzone_text(content, event)
        return json.dumps({"status": "success" if result.get("success") else "error", **result}, ensure_ascii=False)

    async def _pc_get_group_id_by_name_impl(self, event: AstrMessageEvent, **kwargs) -> str:
        if not self.enable_atrelay_tools:
            return json.dumps({"status": "disabled", "message": "跨群转述工具未启用"}, ensure_ascii=False)
        group_name = kwargs.get("group_name") or kwargs.get("name") or kwargs.get("keyword") or kwargs.get("group_id") or ""
        keyword = _single_line(group_name, 80)
        bot = getattr(event, "bot", None)
        api = getattr(bot, "api", None)
        call_action = getattr(api, "call_action", None)
        if not callable(call_action):
            return json.dumps({"status": "error", "message": "当前平台不支持获取群列表"}, ensure_ascii=False)
        try:
            groups = await call_action("get_group_list")
            matches = []
            for item in groups if isinstance(groups, list) else []:
                group_id = str(item.get("group_id") or "")
                name = _single_line(item.get("group_name") or item.get("group_remark"), 100)
                if not keyword or keyword in name or keyword in group_id:
                    matches.append({"group_id": group_id, "group_name": name})
            return json.dumps({"status": "success", "count": len(matches), "groups": matches[:20]}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"获取群列表失败: {_single_line(exc, 120)}"}, ensure_ascii=False)

    async def _pc_get_user_id_by_name_impl(self, event: AstrMessageEvent, **kwargs) -> str:
        if not self.enable_atrelay_tools:
            return json.dumps({"status": "disabled", "message": "跨群转述工具未启用"}, ensure_ascii=False)
        group_id = kwargs.get("group_id") or kwargs.get("group") or kwargs.get("group_name") or ""
        nickname = kwargs.get("nickname") or kwargs.get("name") or kwargs.get("keyword") or kwargs.get("user_name") or kwargs.get("user") or ""
        target_group = _single_line(group_id, 40) or self._extract_group_id_from_event(event)
        query = _single_line(nickname, 60)
        if not query:
            return json.dumps({"status": "error", "message": "缺少 nickname/name 参数"}, ensure_ascii=False)
        resolved = await self._resolve_atrelay_target_user(event, target_group, query)
        if resolved.get("ambiguous"):
            return json.dumps({"status": "ambiguous", "message": "匹配到多个群友,需要用户补充 QQ 或更明确称呼", "matches": resolved.get("matches", [])}, ensure_ascii=False)
        if resolved.get("user_id"):
            return json.dumps({"status": "success", **resolved}, ensure_ascii=False)
        return json.dumps({"status": "not_found", "message": "未找到匹配群友"}, ensure_ascii=False)

    async def _pc_get_specified_group_members_impl(self, event: AstrMessageEvent, **kwargs) -> str:
        if not self.enable_atrelay_tools:
            return json.dumps({"status": "disabled", "message": "跨群转述工具未启用"}, ensure_ascii=False)
        group_id = kwargs.get("group_id") or kwargs.get("group") or kwargs.get("group_name") or ""
        keyword = kwargs.get("keyword") or kwargs.get("name") or kwargs.get("nickname") or kwargs.get("user") or ""
        target_group = _single_line(group_id, 40) or self._extract_group_id_from_event(event)
        if not target_group:
            return json.dumps({"status": "error", "message": "未指定群号且当前不在群聊环境中"}, ensure_ascii=False)
        query = _single_line(keyword, 60)
        try:
            members = await self._get_group_member_list_for_tool(event, target_group)
            formatted = [self._format_atrelay_member(item) for item in members]
            if query:
                formatted = [
                    item for item in formatted
                    if query in item.get("user_id", "")
                    or query in item.get("nickname", "")
                    or query in item.get("group_card", "")
                    or query in item.get("relation_name", "")
                ]
            if self.enable_worldbook_member_recognition:
                async with self._data_lock:
                    self._save_data_sync()
            return json.dumps({"status": "success", "group_id": target_group, "count": len(formatted), "members": formatted[:80]}, ensure_ascii=False)
        except Exception as exc:
            return json.dumps({"status": "error", "message": f"查询群成员失败: {_single_line(exc, 120)}"}, ensure_ascii=False)

    async def _pc_relay_message_impl(self, event: AstrMessageEvent, **kwargs) -> str:
        if not self.enable_atrelay_tools:
            return json.dumps({"status": "disabled", "message": "跨会话转述工具未启用"}, ensure_ascii=False)
        destination_raw = _single_line(
            kwargs.get("destination")
            or kwargs.get("target_scope")
            or kwargs.get("scope")
            or kwargs.get("target_type")
            or kwargs.get("type")
            or "auto",
            40,
        ).lower()
        group_hint = kwargs.get("group_hint") or kwargs.get("group_id") or kwargs.get("group") or kwargs.get("target_group") or ""
        recipient_hint = (
            kwargs.get("recipient_hint")
            or kwargs.get("recipient")
            or kwargs.get("to")
            or kwargs.get("at_user")
            or kwargs.get("target_user")
            or kwargs.get("user_id")
            or kwargs.get("nickname")
            or kwargs.get("name")
            or ""
        )
        message = kwargs.get("message") or kwargs.get("text") or kwargs.get("content") or kwargs.get("msg") or ""
        relay_mode = kwargs.get("relay_mode") or kwargs.get("mode") or ""
        sensitive_confirmed = kwargs.get("sensitive_confirmed", kwargs.get("confirmed", False))
        delay_until_seen = self._atrelay_bool_flag(
            kwargs.get("delay_until_recipient_seen", kwargs.get("delay", kwargs.get("wait_until_seen", False)))
        )
        at_recipient = self._atrelay_bool_flag(kwargs.get("at_recipient", kwargs.get("at", False)))
        expire_hours = kwargs.get("expire_hours", kwargs.get("ttl_hours", 24))

        text = _single_line(message, 800)
        recipient = _single_line(recipient_hint, 80)
        if not text:
            return json.dumps({"status": "error", "message": "缺少 message/text 内容"}, ensure_ascii=False)

        if destination_raw in {"group", "groups", "群", "群聊", "send_group", "to_group"}:
            destination = "group"
        elif destination_raw in {"private", "user", "friend", "私聊", "私发", "私信", "to_user", "dm"}:
            destination = "private"
        else:
            if group_hint:
                destination = "group"
            elif recipient:
                destination = "private"
            else:
                destination = "auto"

        if destination == "auto":
            return json.dumps({"status": "need_target", "message": "需要说明发到哪个群或私聊给谁"}, ensure_ascii=False)

        if destination == "group":
            group_result = await self._resolve_atrelay_target_group(event, group_hint)
            if group_result.get("status") != "success":
                return json.dumps(group_result, ensure_ascii=False)
            group_id = _single_line(group_result.get("group_id"), 40)
            if delay_until_seen:
                if not recipient:
                    return json.dumps({"status": "need_recipient", "message": "延迟转述需要目标群友"}, ensure_ascii=False)
                result = await self._pc_schedule_group_relay_impl(
                    event,
                    group_id=group_id,
                    at_user=recipient,
                    message=text,
                    relay_mode=relay_mode,
                    sensitive_confirmed=sensitive_confirmed,
                    expire_hours=expire_hours,
                )
                return json.dumps({"status": "scheduled" if result.startswith("已挂起") else "error", "message": result}, ensure_ascii=False)
            result = await self._pc_send_to_group_impl(
                event,
                group_id=group_id,
                message=text,
                at_user=recipient if (recipient and (at_recipient or recipient)) else "",
                relay_mode=relay_mode,
                sensitive_confirmed=sensitive_confirmed,
            )
            return json.dumps({"status": "success" if result.startswith("消息已发送") else "error", "message": result}, ensure_ascii=False)

        target_user = recipient
        if not target_user:
            return json.dumps({"status": "need_recipient", "message": "需要补充私聊目标 QQ 或称呼"}, ensure_ascii=False)
        if not target_user.isdigit():
            group_result = await self._resolve_atrelay_target_group(event, group_hint)
            group_id = _single_line(group_result.get("group_id"), 40) if group_result.get("status") == "success" else ""
            if not group_id and self._extract_group_id_from_event(event):
                group_id = self._extract_group_id_from_event(event)
            if not group_id:
                return json.dumps(
                    {
                        "status": "need_group_or_qq",
                        "message": "按昵称私聊需要目标所在群号/群名，或直接提供 QQ。",
                    },
                    ensure_ascii=False,
                )
            resolved = await self._resolve_atrelay_target_user(event, group_id, target_user)
            if resolved.get("ambiguous"):
                return json.dumps(
                    {
                        "status": "ambiguous",
                        "message": "匹配到多个用户，请补充 QQ",
                        "matches": resolved.get("matches", [])[:8],
                    },
                    ensure_ascii=False,
                )
            target_user = _single_line(resolved.get("user_id"), 40)
            if not target_user:
                return json.dumps({"status": "not_found", "message": "未找到私聊目标"}, ensure_ascii=False)
        result = await self._pc_send_to_private_user_impl(
            event,
            user_id=target_user,
            message=text,
            relay_mode=relay_mode,
            sensitive_confirmed=sensitive_confirmed,
        )
        return json.dumps({"status": "success" if result.startswith("已向") else "error", "message": result}, ensure_ascii=False)

    async def _pc_send_to_group_impl(self, event: AstrMessageEvent, **kwargs) -> str:
        if not self.enable_atrelay_tools:
            return "发送失败：跨群转述工具未启用"
        group_id = kwargs.get("group_id") or kwargs.get("group") or kwargs.get("target_group") or ""
        message = kwargs.get("message") or kwargs.get("text") or kwargs.get("content") or kwargs.get("msg") or ""
        at_user = kwargs.get("at_user") or kwargs.get("at") or kwargs.get("target_user") or kwargs.get("user_id") or ""
        at_qq_list = kwargs.get("at_qq_list") or kwargs.get("at_users") or kwargs.get("at_list")
        if not at_user and isinstance(at_qq_list, list) and at_qq_list:
            at_user = str(at_qq_list[0])
        relay_mode = kwargs.get("relay_mode") or kwargs.get("mode") or ""
        sensitive_confirmed = kwargs.get("sensitive_confirmed", kwargs.get("confirmed", False))
        target_group = _single_line(group_id, 40)
        text = _single_line(message, 800)
        relay_mode_normalized = self._normalize_atrelay_relay_mode(relay_mode)
        if not target_group.isdigit():
            return "发送失败：群号格式不正确"
        if not text:
            return "发送失败：消息内容为空"
        boundary = self._atrelay_boundary_guard(text)
        if boundary:
            return boundary
        duplicate = self._atrelay_duplicate_guard("group", target_group, text, at_user)
        if duplicate:
            return duplicate
        guard = self._atrelay_confirmation_guard(
            text,
            relay_mode=relay_mode_normalized,
            sensitive_confirmed=self._atrelay_bool_flag(sensitive_confirmed) or self._atrelay_event_confirms_sensitive_send(event),
        )
        if guard:
            return guard
        at_qq = ""
        at_label = ""
        if _single_line(at_user, 60):
            resolved = await self._resolve_atrelay_target_user(event, target_group, at_user)
            if resolved.get("ambiguous"):
                names = "、".join(_single_line(item.get("name") or item.get("relation_name") or item.get("nickname") or item.get("user_id"), 30) for item in resolved.get("matches", [])[:5] if isinstance(item, dict))
                return f"发送失败：@ 对象不唯一，请补充 QQ。候选：{names or '多个成员'}"
            at_qq = _single_line(resolved.get("user_id"), 40)
            at_label = _single_line(resolved.get("name"), 60)
            if not at_qq:
                return "发送失败：未找到要 @ 的群友"
        platform = str(getattr(event, "unified_msg_origin", "") or "").split(":")[0] or self.target_platform or "aiocqhttp"
        target_umo = f"{platform}:GroupMessage:{target_group}"
        chain: list[Any] = []
        if at_qq:
            chain.extend([At(qq=at_qq), Plain(" ")])
        chain.append(Plain(text))
        try:
            await self.context.send_message(target_umo, MessageChain(chain))
            self._note_atrelay_send("group", target_group, text, at_qq or at_user)
            self._save_data_sync()
            return f"消息已发送到群 {target_group}" + (f", 已 @ {at_label or at_qq}" if at_qq else "")
        except Exception as exc:
            return f"发送失败：{_single_line(exc, 160)}"

    async def _pc_send_to_private_user_impl(self, event: AstrMessageEvent, **kwargs) -> str:
        if not self.enable_atrelay_tools:
            return "发送失败：跨群转述工具未启用"
        user_id = kwargs.get("user_id") or kwargs.get("qq") or kwargs.get("target_user") or kwargs.get("target") or ""
        message = kwargs.get("message") or kwargs.get("text") or kwargs.get("content") or kwargs.get("msg") or ""
        relay_mode = kwargs.get("relay_mode") or kwargs.get("mode") or ""
        sensitive_confirmed = kwargs.get("sensitive_confirmed", kwargs.get("confirmed", False))
        target_user = _single_line(user_id, 40)
        text = _single_line(message, 800)
        relay_mode_normalized = self._normalize_atrelay_relay_mode(relay_mode)
        if not target_user.isdigit():
            return "发送失败：QQ 号格式不正确"
        if not text:
            return "发送失败：消息内容为空"
        boundary = self._atrelay_boundary_guard(text)
        if boundary:
            return boundary
        duplicate = self._atrelay_duplicate_guard("private", target_user, text)
        if duplicate:
            return duplicate
        guard = self._atrelay_confirmation_guard(
            text,
            relay_mode=relay_mode_normalized,
            sensitive_confirmed=self._atrelay_bool_flag(sensitive_confirmed) or self._atrelay_event_confirms_sensitive_send(event),
        )
        if guard:
            return guard
        platform = str(getattr(event, "unified_msg_origin", "") or "").split(":")[0] or self.target_platform or "aiocqhttp"
        try:
            await self.context.send_message(f"{platform}:FriendMessage:{target_user}", MessageChain([Plain(text)]))
            self._note_atrelay_send("private", target_user, text)
            self._save_data_sync()
            return f"已向 {target_user} 发送私聊消息"
        except Exception as exc:
            return f"私聊发送失败：{_single_line(exc, 160)}"

    async def _pc_send_to_groups_impl(self, event: AstrMessageEvent, **kwargs) -> str:
        group_ids = kwargs.get("group_ids") or kwargs.get("groups") or kwargs.get("group_id") or kwargs.get("targets") or ""
        message = kwargs.get("message") or kwargs.get("text") or kwargs.get("content") or kwargs.get("msg") or ""
        at_user = kwargs.get("at_user") or kwargs.get("at") or kwargs.get("target_user") or kwargs.get("user_id") or ""
        relay_mode = kwargs.get("relay_mode") or kwargs.get("mode") or ""
        sensitive_confirmed = kwargs.get("sensitive_confirmed", kwargs.get("confirmed", False))
        targets = [item for item in self._parse_atrelay_target_list(group_ids, limit=self.atrelay_multi_target_limit) if item.isdigit()]
        if not targets:
            return "发送失败：没有有效群号"
        results = []
        for group_id in targets:
            result = await self._pc_send_to_group_impl(
                event,
                group_id=group_id,
                message=message,
                at_user=at_user,
                relay_mode=relay_mode,
                sensitive_confirmed=sensitive_confirmed,
            )
            results.append(f"{group_id}: {result}")
        return "多群通知完成：\n" + "\n".join(results[: self.atrelay_multi_target_limit])

    async def _pc_send_to_private_users_impl(self, event: AstrMessageEvent, **kwargs) -> str:
        user_ids = kwargs.get("user_ids") or kwargs.get("users") or kwargs.get("user_id") or kwargs.get("targets") or ""
        message = kwargs.get("message") or kwargs.get("text") or kwargs.get("content") or kwargs.get("msg") or ""
        relay_mode = kwargs.get("relay_mode") or kwargs.get("mode") or ""
        sensitive_confirmed = kwargs.get("sensitive_confirmed", kwargs.get("confirmed", False))
        targets = [item for item in self._parse_atrelay_target_list(user_ids, limit=self.atrelay_multi_target_limit) if item.isdigit()]
        if not targets:
            return "发送失败：没有有效 QQ"
        results = []
        for user_id in targets:
            result = await self._pc_send_to_private_user_impl(
                event,
                user_id=user_id,
                message=message,
                relay_mode=relay_mode,
                sensitive_confirmed=sensitive_confirmed,
            )
            results.append(f"{user_id}: {result}")
        return "多人转述完成：\n" + "\n".join(results[: self.atrelay_multi_target_limit])

    async def _pc_schedule_group_relay_impl(self, event: AstrMessageEvent, **kwargs) -> str:
        if not self.enable_atrelay_tools:
            return "挂起失败：跨群转述工具未启用"
        group_id = kwargs.get("group_id") or kwargs.get("group") or kwargs.get("target_group") or ""
        at_user = kwargs.get("at_user") or kwargs.get("target_user") or kwargs.get("user_id") or kwargs.get("name") or kwargs.get("nickname") or ""
        message = kwargs.get("message") or kwargs.get("text") or kwargs.get("content") or kwargs.get("msg") or ""
        relay_mode = kwargs.get("relay_mode") or kwargs.get("mode") or ""
        sensitive_confirmed = kwargs.get("sensitive_confirmed", kwargs.get("confirmed", False))
        expire_hours = kwargs.get("expire_hours", kwargs.get("ttl_hours", 24))
        target_group = _single_line(group_id, 40) or self._extract_group_id_from_event(event)
        text = _single_line(message, 800)
        if not target_group.isdigit():
            return "挂起失败：群号格式不正确"
        if not text:
            return "挂起失败：消息内容为空"
        boundary = self._atrelay_boundary_guard(text)
        if boundary:
            return boundary.replace("发送失败", "挂起失败", 1)
        relay_mode_normalized = self._normalize_atrelay_relay_mode(relay_mode)
        guard = self._atrelay_confirmation_guard(
            text,
            relay_mode=relay_mode_normalized,
            sensitive_confirmed=self._atrelay_bool_flag(sensitive_confirmed) or self._atrelay_event_confirms_sensitive_send(event),
        )
        if guard:
            return guard.replace("不能直接转述", "不能直接挂起转述")
        resolved = await self._resolve_atrelay_target_user(event, target_group, at_user)
        if resolved.get("ambiguous"):
            names = "、".join(
                _single_line(item.get("name") or item.get("relation_name") or item.get("nickname") or item.get("user_id"), 30)
                for item in resolved.get("matches", [])[:5]
                if isinstance(item, dict)
            )
            return f"挂起失败：目标不唯一，请补充 QQ。候选：{names or '多个成员'}"
        target_user = _single_line(resolved.get("user_id"), 40)
        target_name = _single_line(resolved.get("name"), 60) or target_user
        if not target_user:
            return "挂起失败：未找到目标群友"
        now = _now_ts()
        expire_seconds = max(1, min(168, _safe_int(expire_hours, 24, 1, 168))) * 3600
        async with self._data_lock:
            group = self._get_group(target_group)
            tasks = group.setdefault("pending_atrelay_tasks", [])
            if not isinstance(tasks, list):
                tasks = []
                group["pending_atrelay_tasks"] = tasks
            signature = self._atrelay_send_signature("delayed_group", target_group, text, target_user)
            for task in tasks:
                if isinstance(task, dict) and task.get("signature") == signature and _safe_float(task.get("expires_at"), 0) > now:
                    return f"已存在相同延迟转述：等 {target_name} 在群 {target_group} 出现时发送"
            tasks.append(
                {
                    "id": uuid.uuid4().hex[:12],
                    "created_at": now,
                    "expires_at": now + expire_seconds,
                    "target_user_id": target_user,
                    "target_name": target_name,
                    "message": text,
                    "relay_mode": relay_mode_normalized,
                    "sensitive_confirmed": self._atrelay_bool_flag(sensitive_confirmed) or self._atrelay_event_confirms_sensitive_send(event),
                    "signature": signature,
                }
            )
            del tasks[:-30]
            self._save_data_sync()
        return f"已挂起：等 {target_name} 在群 {target_group} 出现时转述"
