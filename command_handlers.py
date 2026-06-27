# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import base64
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from astrbot.api.event import AstrMessageEvent

from .helpers import _now_ts, _safe_float, _safe_int, _set_into_config, _single_line


_PHOTO_REFERENCE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


class CommandHandlersMixin:
    """Implementation bodies for command handlers registered in main.py."""

    def _photo_reference_image_dir(self) -> Path:
        target_dir = Path(self.data_dir) / "photo_reference_images"
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir

    def _photo_reference_stem(self, stem: str = "reference") -> str:
        clean = re.sub(r"[^0-9A-Za-z_.-]+", "_", str(stem or "reference")).strip("._")
        if not clean:
            clean = "reference"
        return f"{clean}_{int(_now_ts() * 1000)}_{uuid.uuid4().hex[:8]}"

    def _photo_reference_copy_local_file(self, source_path: Path, *, stem: str = "reference") -> str:
        try:
            resolved = source_path.resolve()
        except Exception:
            resolved = source_path
        if not resolved.exists() or not resolved.is_file():
            return ""
        suffix = resolved.suffix.lower()
        if suffix not in _PHOTO_REFERENCE_SUFFIXES:
            return ""
        target = self._photo_reference_image_dir() / f"{self._photo_reference_stem(stem)}{suffix}"
        shutil.copy2(resolved, target)
        return str(target.resolve())

    def _photo_reference_write_data_image(self, source: str, *, stem: str = "reference") -> str:
        text = str(source or "").strip()
        try:
            if text.startswith("base64://"):
                raw = base64.b64decode(text[len("base64://"):], validate=False)
                suffix = ".jpg"
            elif text.startswith("data:") and "," in text:
                meta, payload = text.split(",", 1)
                if ";base64" not in meta.lower():
                    return ""
                raw = base64.b64decode(payload, validate=False)
                lowered = meta.lower()
                suffix = ".png" if "png" in lowered else ".webp" if "webp" in lowered else ".jpg"
            else:
                return ""
            if not raw:
                return ""
            target = self._photo_reference_image_dir() / f"{self._photo_reference_stem(stem)}{suffix}"
            target.write_bytes(raw)
            return str(target.resolve())
        except Exception:
            return ""

    async def _photo_reference_source_to_stable_path(self, source: str, *, stem: str = "reference") -> str:
        text = str(source or "").strip()
        if not text:
            return ""
        data_path = self._photo_reference_write_data_image(text, stem=stem)
        if data_path:
            return data_path
        if re.match(r"^https?://", text, flags=re.I):
            downloader = getattr(self, "_persist_private_remote_image_source", None)
            if callable(downloader):
                try:
                    downloaded = await downloader(text, self._photo_reference_image_dir(), self._photo_reference_stem(f"{stem}_remote"))
                except Exception:
                    downloaded = ""
                if downloaded:
                    return self._photo_reference_copy_local_file(Path(downloaded), stem=stem) or downloaded
            return ""
        local_text = text[len("file://"):] if text.startswith("file://") else text
        try:
            return self._photo_reference_copy_local_file(Path(local_text), stem=stem)
        except (OSError, ValueError):
            return ""

    async def _photo_reference_sources_from_current_event(self, event: AstrMessageEvent, user_id: str) -> list[str]:
        sources: list[str] = []

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in sources:
                sources.append(text)

        persister = getattr(self, "_persist_private_inbound_images", None)
        if callable(persister):
            try:
                for source in await persister(event, user_id):
                    add(source)
            except Exception:
                pass
        raw_extractor = getattr(self, "_raw_private_image_sources", None)
        if callable(raw_extractor):
            try:
                for source in raw_extractor(event):
                    add(source)
            except Exception:
                pass
        return sources

    def _photo_reference_sources_from_reply_cache(self, event: AstrMessageEvent) -> list[str]:
        sources: list[str] = []

        def add(value: Any) -> None:
            text = str(value or "").strip()
            if text and text not in sources:
                sources.append(text)

        cleanup = getattr(self, "_cleanup_recall_message_cache", None)
        if callable(cleanup):
            try:
                cleanup()
            except Exception:
                pass
        cache = getattr(self, "_recall_message_cache", None)
        if not isinstance(cache, dict):
            return sources
        id_getter = getattr(self, "_event_reply_message_ids", None)
        message_ids = id_getter(event) if callable(id_getter) else []
        scope_getter = getattr(self, "_event_scope_key", None)
        current_scope = _single_line(scope_getter(event), 160) if callable(scope_getter) else ""
        item_getter = getattr(self, "_recall_image_items_from_snapshot", None)
        for message_id in message_ids:
            snapshot = cache.get(message_id)
            if not isinstance(snapshot, dict):
                continue
            snapshot_scope = _single_line(snapshot.get("scope"), 160)
            if current_scope and snapshot_scope and snapshot_scope != current_scope:
                continue
            if callable(item_getter):
                try:
                    items = item_getter(snapshot)
                except Exception:
                    items = []
            else:
                raw_items = snapshot.get("image_items") if isinstance(snapshot.get("image_items"), list) else []
                items = [item for item in raw_items if isinstance(item, dict)]
            for item in items:
                if not isinstance(item, dict):
                    continue
                tier = _single_line(item.get("tier"), 40)
                source = str(item.get("source") or "").strip()
                if not source or tier in {"placeholder", "platform_file"}:
                    continue
                add(source)
            for source in snapshot.get("images") if isinstance(snapshot.get("images"), list) else []:
                add(source)
        return sources

    async def _photo_reference_image_from_command_context(
        self,
        event: AstrMessageEvent,
        user_id: str,
    ) -> tuple[str, str, bool]:
        saw_image = False
        for source in await self._photo_reference_sources_from_current_event(event, user_id):
            saw_image = True
            path = await self._photo_reference_source_to_stable_path(source, stem="message")
            if path:
                return path, "随消息发送的图片", True
        for source in self._photo_reference_sources_from_reply_cache(event):
            saw_image = True
            path = await self._photo_reference_source_to_stable_path(source, stem="reply")
            if path:
                return path, "引用消息里的图片", True
        return "", "", saw_image

    def _resolve_photo_reference_command_path(self, value: str) -> tuple[str, str]:
        raw = _single_line(value, 260).strip().strip('"').strip("'")
        if not raw:
            return "", "请这样设置：陪伴 参考图 <本地图片路径>"
        expanded = os.path.expandvars(os.path.expanduser(raw))
        candidates = [Path(expanded)]
        if not candidates[0].is_absolute():
            candidates.append(Path(self.data_dir) / expanded)
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except Exception:
                resolved = candidate
            if not resolved.exists() or not resolved.is_file():
                continue
            if resolved.suffix.lower() not in _PHOTO_REFERENCE_SUFFIXES:
                return "", "参考图只支持 png、jpg、jpeg、webp。"
            return str(resolved), ""
        return "", "没有找到这张本地图片。请确认路径存在，并且 Bot 所在机器能访问。"

    def _set_photo_reference_config_path(self, path: str) -> bool:
        clean = _single_line(path, 260)
        self.photo_persona_reference_image_path = clean
        try:
            saved = _set_into_config(self.config, "photo_persona_reference_image_path", clean)
            if saved:
                self._save_config_if_possible()
            return bool(saved)
        except Exception:
            return False

    async def _photo_reference_command_text(self, event: AstrMessageEvent, user_id: str, value: str = "") -> str:
        action = _single_line(value, 260)
        if action in {"清空", "删除", "移除", "clear", "none", "空"}:
            saved = self._set_photo_reference_config_path("")
            return "已清空主动自拍人设参考图。" + ("" if saved else "\n但配置保存可能失败，请稍后在配置页确认。")
        force_image = action in {"图片", "这张", "这张图", "引用", "引用图", "引用图片", "设置", "更换", "更新", "添加", "上传", "用这张", "使用这张"}
        if action in {"查看", "状态", "当前", "current", "show"}:
            force_image = False
        if not action or force_image:
            image_path, image_label, saw_image = await self._photo_reference_image_from_command_context(event, user_id)
            if image_path:
                saved = self._set_photo_reference_config_path(image_path)
                return (
                    f"已把{image_label}设为主动自拍人设参考图：\n"
                    f"{image_path}\n"
                    "只会在 selfie/人像类主动生图里使用；ComfyUI 需要支持 images=1 的自拍工作流。"
                    + ("" if saved else "\n但配置保存可能失败，请稍后在配置页确认。")
                )
            if force_image:
                if saw_image:
                    return "找到了图片，但没能保存成参考图。参考图只支持 png、jpg、jpeg、webp；也可能是平台只给了图片 file id，拿不到原图。"
                return "没有在这条消息或引用消息里找到图片。可以发送图片并附上“陪伴 参考图”，或回复一条近期图片消息发送“陪伴 参考图”。"
        if not action or action in {"查看", "状态", "当前", "current", "show"}:
            configured = _single_line(getattr(self, "photo_persona_reference_image_path", ""), 260)
            resolved = self._photo_persona_reference_image_path() if callable(getattr(self, "_photo_persona_reference_image_path", None)) else ""
            if not configured:
                return "当前没有设置主动自拍人设参考图。\n设置方式：陪伴 参考图 <本地图片路径>；也可以发送图片并附上“陪伴 参考图”。"
            return (
                "当前主动自拍人设参考图：\n"
                f"{configured}\n"
                f"状态：{'可用' if resolved else '路径不可用或格式不支持'}"
            )
        path, error = self._resolve_photo_reference_command_path(action)
        if error:
            return error
        stable_path = await self._photo_reference_source_to_stable_path(path, stem="manual") or path
        saved = self._set_photo_reference_config_path(stable_path)
        return (
            "已设置主动自拍人设参考图：\n"
            f"{stable_path}\n"
            "只会在 selfie/人像类主动生图里使用；ComfyUI 需要支持 images=1 的自拍工作流。"
            + ("" if saved else "\n但配置保存可能失败，请稍后在配置页确认。")
        )

    def _natural_language_photo_intent(self, text: str, *, has_reference: bool = False) -> dict[str, Any]:
        raw = re.sub(r"\[CQ:image,[^\]]+\]", "", str(text or ""))
        raw = _single_line(raw, 800)
        if not raw:
            return {}
        compact = re.sub(r"\s+", "", raw)
        edit_markers = (
            "改成", "改为", "改一下", "改图", "修图", "重绘", "p成", "P成",
            "换成", "变成", "加上", "加个", "去掉", "去除", "把这张", "这张图",
        )
        draw_patterns = (
            r"(?:帮我|给我|替我)?(?:画|画一张|画个|生成|生成一张|生一张|做一张|做个|出一张)(?:图|图片|插画|照片|头像|壁纸|表情包)?",
            r"(?:来|整)(?:一张|个)?(?:图|图片|插画|照片|头像|壁纸|表情包)",
        )
        draw_hit = any(re.search(pattern, raw, flags=re.I) for pattern in draw_patterns)
        edit_hit = bool(has_reference and any(marker in compact for marker in edit_markers))
        if not draw_hit and not edit_hit:
            return {}
        prompt = raw
        cleanup_patterns = [
            r"^(?:麻烦|可以|能不能|能|帮我|给我|替我|请你|请)?",
            r"^(?:画|画一张|画个|生成|生成一张|生一张|做一张|做个|出一张|来一张|整一张)(?:图|图片|插画|照片|头像|壁纸|表情包)?",
            r"^(?:把)?(?:这张图|这个图|这张|引用图|图片)?(?:帮我)?(?:改成|改为|改一下|改图|修图|重绘|p成|P成|换成|变成)",
        ]
        for pattern in cleanup_patterns:
            prompt = re.sub(pattern, "", prompt, count=1, flags=re.I).strip()
        prompt = prompt.strip(" ，,。.!！?？:：；;")
        if not prompt or prompt in {"图", "图片", "一张图", "这张", "这张图"}:
            return {"kind": "edit" if edit_hit else "text2img", "prompt": "", "needs_prompt": True}
        return {
            "kind": "edit" if edit_hit else "text2img",
            "prompt": _single_line(prompt, 700),
            "raw": raw,
        }

    def _natural_language_photo_quota_left(self, user: dict[str, Any]) -> int:
        limit = max(0, _safe_int(getattr(self, "natural_language_photo_generation_max_daily", 0), 0))
        if limit <= 0:
            return 0
        today = self._environment_now().strftime("%Y-%m-%d") if callable(getattr(self, "_environment_now", None)) else ""
        if not today:
            today = str(getattr(self, "_today_key", lambda: "")() or "")
        used = _safe_int(user.get("natural_photo_generated_today"), 0)
        if str(user.get("natural_photo_generated_day") or "") != today:
            used = 0
        return max(0, limit - used)

    def _note_natural_language_photo_generation_attempt(self, user: dict[str, Any], image_path: str = "") -> None:
        today = self._environment_now().strftime("%Y-%m-%d") if callable(getattr(self, "_environment_now", None)) else ""
        if not today:
            today = str(getattr(self, "_today_key", lambda: "")() or "")
        if user.get("natural_photo_generated_day") != today:
            user["natural_photo_generated_day"] = today
            user["natural_photo_generated_today"] = 0
        user["natural_photo_generated_today"] = _safe_int(user.get("natural_photo_generated_today"), 0) + 1
        user["last_natural_photo_path"] = _single_line(image_path, 260)
        user["last_natural_photo_at"] = _now_ts()

    def _build_natural_language_photo_prompt(self, *, prompt: str, kind: str, has_reference: bool) -> str:
        style_name, style_instruction = self._get_photo_style_instruction() if callable(getattr(self, "_get_photo_style_instruction", None)) else ("默认", "")
        if kind == "edit" and has_reference:
            base = (
                "基于用户提供或引用的参考图进行改图。"
                f"用户要求：{prompt}。"
                "尽量保留用户未要求修改的主体、构图和重要细节，只改变明确要求的部分。"
            )
        else:
            base = f"根据用户自然语言请求生成图片。用户要求：{prompt}。"
        return _single_line(
            " ".join(
                [
                    base,
                    "画面干净清晰，构图自然，不要加入无关文字、水印、Logo 或多余说明。",
                    f"风格：{style_name}；{style_instruction}",
                ]
            ),
            1000,
        )

    async def _maybe_handle_natural_language_photo_request(
        self,
        event: AstrMessageEvent,
        user_id: str,
        text: str,
    ) -> bool:
        if not getattr(self, "enable_natural_language_photo_generation", False):
            return False
        if not getattr(self, "enable_photo_text_action", False):
            return False
        text = _single_line(text, 800)
        if not text or text.startswith(("陪伴", "/陪伴", "私聊陪伴", "主动陪伴")):
            return False
        has_reference = bool(self._private_event_has_image(event) if callable(getattr(self, "_private_event_has_image", None)) else False)
        has_reference = has_reference or bool(self._photo_reference_sources_from_reply_cache(event))
        intent = self._natural_language_photo_intent(text, has_reference=has_reference)
        if not intent:
            return False
        if intent.get("needs_prompt"):
            await self._reply(event, "要画成什么样？给我一句具体点的描述就行。")
            event.stop_event()
            return True
        async with self._data_lock:
            user = self._get_user(user_id)
            if not self._is_target_private_user(user_id, user) or not bool(user.get("enabled", True)):
                return False
            if self._private_user_role(user, user_id) == "friend":
                await self._reply(event, "这个自然语言生图入口只给主人私聊开放。")
                event.stop_event()
                return True
            if self._natural_language_photo_quota_left(user) <= 0:
                await self._reply(event, "今天自然语言生图/改图额度用完了。")
                event.stop_event()
                return True
        if not self._photo_text_available():
            await self._reply(event, "现在没有可用的生图后端，先画不了。")
            event.stop_event()
            return True
        reference_path = ""
        reference_label = ""
        if intent.get("kind") == "edit":
            reference_path, reference_label, saw_image = await self._photo_reference_image_from_command_context(event, user_id)
            if not reference_path:
                await self._reply(
                    event,
                    "我没拿到要改的图。可以把图片和要求一起发，或者引用一张近期图片再说“改成……”。"
                    if not saw_image
                    else "看到了图片，但没能保存成可用参考图，暂时改不了。",
                )
                event.stop_event()
                return True
        prompt_text = self._build_natural_language_photo_prompt(
            prompt=str(intent.get("prompt") or ""),
            kind=str(intent.get("kind") or "text2img"),
            has_reference=bool(reference_path),
        )
        workflow_kind = "selfie" if reference_path else "text2img"
        backend_name, image_path, note = await self._generate_photo_image(
            workflow_kind=workflow_kind,
            prompt_text=prompt_text,
            session_key=f"natural_photo_{user_id}",
            reference_image_path=reference_path,
        )
        counted = bool(image_path)
        if not image_path and callable(getattr(self, "_photo_generation_failure_counts_as_attempt", None)):
            counted = bool(self._photo_generation_failure_counts_as_attempt(note))
        if counted:
            async with self._data_lock:
                user = self._get_user(user_id)
                self._note_natural_language_photo_generation_attempt(user, image_path=image_path)
                self._save_data_sync()
        if not image_path:
            await self._reply(
                event,
                f"这次没生成出来：{_single_line(note, 160) or '后端没有返回图片'}"
                + ("\n这次已经计入自然语言生图额度，避免后端异常时反复请求。" if counted else ""),
            )
            event.stop_event()
            return True
        caption = "好了。" if not reference_path else f"好了，按{reference_label or '这张图'}改了一版。"
        chain = self._build_outbound_chain(caption, image_path)
        try:
            await event.send(self._build_result_from_chain(chain))
        except Exception:
            await event.send(event.chain_result(chain))
        event.stop_event()
        return True

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
