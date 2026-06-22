# -*- coding: utf-8 -*-
from __future__ import annotations

from astrbot.api.event import AstrMessageEvent

from .helpers import _safe_float, _safe_int, _single_line


class CommandHandlersMixin:
    """Implementation bodies for command handlers registered in main.py."""

    async def _group_companion_command_impl(self, event: AstrMessageEvent):
        group_id = self._extract_group_id_from_event(event)
        if not group_id:
            yield event.plain_result("这条命令需要在群聊里使用。")
            return
        if not self.enable_group_companion or not self._group_allowed_by_access_mode(group_id):
            if self.group_access_mode == "blacklist" and group_id in self._configured_group_blacklist_ids():
                yield event.plain_result("这个群在群聊陪伴黑名单中，暂时不启用。")
            elif self.group_access_mode == "whitelist":
                yield event.plain_result("这个群还没有加入群聊陪伴白名单，暂时不启用。")
            else:
                yield event.plain_result("这个群暂时不启用群聊陪伴。")
            return
        message = str(event.message_str or "").strip()
        action = ""
        response_chain = None
        parts = message.split(maxsplit=2)
        if len(parts) >= 2:
            action = parts[1].strip()
        if action in {"开启", "启用", "打开", "关闭", "停用", "关掉", "撤回消息", "防撤回", "转述撤回", "撤回转述"} and not self._can_manage_group_companion(event):
            yield event.plain_result(self._management_denied_text())
            return
        async with self._data_lock:
            group = self._get_group(group_id)
            if action in {"开启", "启用", "打开"}:
                group["enabled"] = True
                self._save_data_sync()
                response = "群聊陪伴观察已开启。"
            elif action in {"关闭", "停用", "关掉"}:
                group["enabled"] = False
                self._save_data_sync()
                response = "群聊陪伴观察已关闭。"
            elif action in {"黑话", "梗", "词"}:
                slang = group.get("slang_terms") if isinstance(group.get("slang_terms"), list) else []
                meanings = group.get("slang_meanings") if isinstance(group.get("slang_meanings"), dict) else {}
                if slang:
                    lines = ["当前群内常见词/梗："]
                    for item in slang[:20]:
                        if not isinstance(item, dict):
                            continue
                        term = _single_line(item.get("term"), 20)
                        if not term:
                            continue
                        meaning = ""
                        if isinstance(meanings.get(term), dict):
                            meaning_item = meanings[term]
                            confidence = min(1.0, _safe_float(meaning_item.get("confidence"), 1.0, 0.0))
                            raw_meaning = _single_line(meaning_item.get("meaning"), 60)
                            raw_usage = _single_line(meaning_item.get("usage"), 60)
                            if confidence >= 0.55 and not self._is_uncertain_group_slang_meaning(raw_meaning, raw_usage):
                                meaning = raw_meaning
                        lines.append(f"- {term}｜出现 {item.get('count', 0)} 次" + (f"｜{meaning}" if meaning else ""))
                    response = "\n".join(lines)
                else:
                    response = "还没有学到稳定的群内常见词。"
            elif action in {"群友", "成员", "画像"}:
                members = group.get("members") if isinstance(group.get("members"), dict) else {}
                ranked = sorted(
                    [item for item in members.values() if isinstance(item, dict)],
                    key=lambda item: _safe_int(item.get("count"), 0, 0),
                    reverse=True,
                )[:12]
                if ranked:
                    response = "当前群内成员观察：\n" + "\n".join(
                        f"- {_single_line(item.get('name'), 18) or '群友'}"
                        + (
                            "｜" + " / ".join(
                                _single_line(x, 18)
                                for x in (item.get('recent_phrases') or [])[:3]
                                if _single_line(x, 18)
                            )
                            if item.get("recent_phrases")
                            else ""
                        )
                        for item in ranked
                    )
                else:
                    response = "还没有群友样本。"
            elif action in {"话题", "线程"}:
                response = "当前群聊话题线程：\n" + (self._format_group_topic_threads_for_prompt(group) or "暂无。")
            elif action in {"片段", "群聊片段", "记忆"}:
                response = "近期群聊片段记忆：\n" + (self._format_group_episodes_for_prompt(group) or "暂无。")
            elif action in {"插话判定", "插话反馈", "反馈"}:
                response = "群聊插话反馈：" + self._format_group_interjection_feedback(group)
            elif action in {"关系网", "关系网络", "互动关系"}:
                response = "群友互动图：\n" + (self._format_group_relationship_graph_for_prompt(group) or "暂无。")
            elif action in {"撤回消息", "防撤回", "转述撤回", "撤回转述"}:
                if not self.enable_recall_enhancement or not self.enable_recall_transcribe_command:
                    response = "撤回消息转述没有开启。"
                else:
                    response = self._format_recalled_messages_for_event(event, limit=5)
                    extra_components = self._recalled_message_media_components_for_event(event, limit=5)
                    if extra_components:
                        response_chain = self._build_outbound_chain(response, extra_components=extra_components)
            elif action in {"状态", "气氛", ""}:
                response = self._format_group_status(group)
            else:
                response = (
                    "群聊陪伴命令：\n"
                    "陪伴群 状态\n"
                    "陪伴群 黑话\n"
                    "陪伴群 群友\n"
                    "陪伴群 话题\n"
                    "陪伴群 片段\n"
                    "陪伴群 插话反馈\n"
                    "陪伴群 关系网\n"
                    "陪伴群 撤回消息\n"
                    "陪伴群 开启\n"
                    "陪伴群 关闭"
                )
        if response_chain:
            yield event.chain_result(response_chain)
        else:
            yield event.plain_result(response)
        event.stop_event()
