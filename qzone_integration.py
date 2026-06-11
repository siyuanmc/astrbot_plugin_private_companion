# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import random
import re
import time
from http.cookies import SimpleCookie
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlparse

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent

from .helpers import _now_ts, _safe_float, _safe_int, _single_line

class QzoneMixin:
    """QQ Zone integration helpers."""

    def _qzone_plugin_dir(self) -> Path:
        candidates = [
            Path(__file__).resolve().parent.parent / "astrbot_plugin_qzone",
            Path(self.data_dir).parent.parent / "plugins" / "astrbot_plugin_qzone",
        ]
        for path in candidates:
            if (path / "main.py").exists():
                return path
        return candidates[0]

    def _find_qzone_instance(self) -> Any | None:
        return None

    def _qzone_available(self) -> bool:
        return bool(self.enable_qzone_integration)

    def _qzone_note_event_bot(self, event: AstrMessageEvent | None) -> None:
        """Cache the latest OneBot connection for background Qzone jobs."""
        bot = getattr(event, "bot", None) if event is not None else None
        if bot is not None:
            self._qzone_last_bot = bot

    @staticmethod
    def _qzone_gtk(p_skey: str) -> str:
        hash_val = 5381
        for ch in str(p_skey or ""):
            hash_val += (hash_val << 5) + ord(ch)
        return str(hash_val & 0x7FFFFFFF)

    @staticmethod
    def _qzone_normalize_cookie_fields(cookies: dict[str, Any]) -> dict[str, str]:
        aliases = {
            "pskey": "p_skey",
            "p-skey": "p_skey",
            "p_uin": "p_uin",
            "ptui_loginuin": "ptui_loginuin",
            "csrf-token": "csrf_token",
        }
        normalized: dict[str, str] = {}
        for key, value in (cookies or {}).items():
            if value in (None, ""):
                continue
            original = str(key).strip()
            if not original:
                continue
            text = str(value).strip().strip('"')
            if not text:
                continue
            canonical = aliases.get(original.lower(), original)
            normalized.setdefault(original, text)
            normalized.setdefault(canonical, text)
        if "uin" in normalized and "p_uin" not in normalized:
            normalized["p_uin"] = normalized["uin"]
        if "p_uin" in normalized and "uin" not in normalized:
            normalized["uin"] = normalized["p_uin"]
        return normalized

    @classmethod
    def _qzone_parse_cookie_text(cls, cookie_text: str) -> dict[str, str]:
        raw = str(cookie_text or "").strip()
        if not raw:
            return {}
        if raw.lower().startswith("cookie:"):
            raw = raw.split(":", 1)[1].strip()
        raw = raw.replace("\r", ";").replace("\n", ";")
        if raw.startswith(("{", "[")):
            try:
                payload = json.loads(raw)
            except Exception:
                payload = None
            if isinstance(payload, dict):
                return cls._qzone_normalize_cookie_fields(payload)
        try:
            return cls._qzone_normalize_cookie_fields({key: morsel.value for key, morsel in SimpleCookie(raw).items()})
        except Exception:
            parsed: dict[str, str] = {}
            for part in raw.split(";"):
                if "=" not in part:
                    continue
                key, value = part.split("=", 1)
                key = key.strip()
                if key:
                    parsed[key] = value.strip().strip('"')
            return cls._qzone_normalize_cookie_fields(parsed)

    @staticmethod
    def _qzone_cookie_header(cookies: dict[str, Any]) -> str:
        return "; ".join(f"{key}={value}" for key, value in (cookies or {}).items() if key and value not in (None, ""))

    def _qzone_extract_cookie_text(self, payload: Any, *, _depth: int = 0, _seen: set[int] | None = None) -> str:
        if _seen is None:
            _seen = set()
        if payload is None or _depth > 8:
            return ""
        if isinstance(payload, bytes):
            try:
                payload = payload.decode("utf-8")
            except Exception:
                return ""
        if isinstance(payload, str):
            text = payload.strip()
            return text if "=" in text and re.search(r"\b(?:uin|p_uin|skey|p_skey|pskey|g_tk|gtk|bkn)\s*=", text, re.I) else ""
        if isinstance(payload, (list, tuple)):
            parts = [self._qzone_extract_cookie_text(item, _depth=_depth + 1, _seen=_seen) for item in payload]
            cookies: dict[str, str] = {}
            for part in parts:
                cookies.update(self._qzone_parse_cookie_text(part))
            return self._qzone_cookie_header(cookies)
        if not isinstance(payload, dict):
            return ""
        obj_id = id(payload)
        if obj_id in _seen:
            return ""
        _seen.add(obj_id)
        name = payload.get("name") or payload.get("key")
        value = payload.get("value")
        if name and value not in (None, ""):
            return f"{name}={value}"
        cookie_keys = {
            "cookies",
            "cookie",
            "cookie_text",
            "cookie_str",
            "cookies_str",
            "data",
            "result",
            "retdata",
            "ret_data",
            "payload",
            "response",
        }
        allow = {
            "uin",
            "p_uin",
            "ptui_loginuin",
            "luin",
            "skey",
            "p_skey",
            "pskey",
            "skey2",
            "pt4_token",
            "pt_key",
            "pt_login_sig",
            "clientkey",
            "superkey",
            "qzonetoken",
            "qm_keyst",
            "qm_sid",
            "o_cookie",
            "uin_cookie",
            "rv2",
            "ptcz",
            "lskey",
            "ldw",
            "g_tk",
            "gtk",
            "bkn",
            "csrf_token",
            "qqmusic_key",
        }
        cookies = {
            str(key): value
            for key, value in payload.items()
            if str(key).lower().replace("-", "_") in allow and value not in (None, "")
        }
        parts = [self._qzone_cookie_header(self._qzone_normalize_cookie_fields(cookies))] if cookies else []
        for key in cookie_keys:
            if key in payload:
                text = self._qzone_extract_cookie_text(payload.get(key), _depth=_depth + 1, _seen=_seen)
                if text:
                    parts.append(text)
        for value in payload.values():
            if isinstance(value, (dict, list, tuple, str, bytes)):
                text = self._qzone_extract_cookie_text(value, _depth=_depth + 1, _seen=_seen)
                if text:
                    parts.append(text)
        merged: dict[str, str] = {}
        for part in parts:
            merged.update(self._qzone_parse_cookie_text(part))
        return self._qzone_cookie_header(merged)

    @staticmethod
    def _qzone_normalize_uin(cookies: dict[str, Any]) -> int:
        for key in ("uin", "p_uin", "ptui_loginuin", "luin"):
            raw = str(cookies.get(key) or "").strip().lstrip("oO")
            if raw.isdigit():
                return int(raw)
        return 0

    def _qzone_context_from_cookies(self, cookies_str: str) -> dict[str, Any]:
        parsed = self._qzone_parse_cookie_text(cookies_str)
        uin = self._qzone_normalize_uin(parsed)
        if not uin:
            raise RuntimeError("Cookie 中缺少合法 uin")
        p_skey = parsed.get("p_skey") or parsed.get("pskey") or ""
        skey = parsed.get("skey") or ""
        gtk = str(parsed.get("g_tk") or parsed.get("gtk") or parsed.get("bkn") or parsed.get("csrf_token") or "")
        if not gtk.isdigit():
            secret = p_skey or skey or parsed.get("skey2") or ""
            gtk = self._qzone_gtk(secret) if secret else ""
        if not gtk:
            raise RuntimeError("Cookie 中缺少 p_skey/skey，无法计算 g_tk")
        cookies = {**parsed, "uin": f"o{uin}"}
        if skey:
            cookies["skey"] = skey
        if p_skey:
            cookies["p_skey"] = p_skey
        return {
            "uin": int(uin),
            "skey": skey,
            "p_skey": p_skey,
            "gtk": gtk,
            "cookies": cookies,
            "cookie_header": self._qzone_cookie_header(cookies),
        }

    async def _qzone_get_cookies(self, event: AstrMessageEvent | None = None) -> str:
        bot = getattr(event, "bot", None) if event is not None else getattr(self, "_qzone_last_bot", None)
        if bot is not None:
            self._qzone_last_bot = bot
        if bot is None:
            raise RuntimeError("没有可用的 OneBot 连接，无法获取 QQ 空间 Cookie")
        merged: dict[str, str] = {}
        domains = [
            "user.qzone.qq.com",
            "qzone.qq.com",
            "h5.qzone.qq.com",
            "mobile.qzone.qq.com",
            "taotao.qzone.qq.com",
        ]
        actions = ("get_cookies", "get_credentials")
        api = getattr(bot, "api", None)
        call_action = getattr(api, "call_action", None)
        for action in actions:
            direct = getattr(bot, action, None)
            for domain in domains:
                for kwargs in ({"domain": domain}, {}):
                    result = None
                    if callable(direct):
                        try:
                            maybe = direct(**kwargs)
                            result = await maybe if hasattr(maybe, "__await__") else maybe
                        except Exception:
                            result = None
                    if result is None and callable(call_action):
                        try:
                            maybe = call_action(action, **kwargs)
                            result = await maybe if hasattr(maybe, "__await__") else maybe
                        except Exception:
                            result = None
                    cookie_text = self._qzone_extract_cookie_text(result)
                    if cookie_text:
                        merged.update(self._qzone_parse_cookie_text(cookie_text))
                if self._qzone_normalize_uin(merged) and (merged.get("p_skey") or merged.get("pskey") or merged.get("skey")):
                    break
            if self._qzone_normalize_uin(merged) and (merged.get("p_skey") or merged.get("pskey") or merged.get("skey")):
                break
        if not self._qzone_normalize_uin(merged):
            login_uin = 0
            direct_login = getattr(bot, "get_login_info", None)
            try:
                result = None
                if callable(direct_login):
                    maybe = direct_login()
                    result = await maybe if hasattr(maybe, "__await__") else maybe
                if result is None and callable(call_action):
                    maybe = call_action("get_login_info")
                    result = await maybe if hasattr(maybe, "__await__") else maybe
                if isinstance(result, dict):
                    login_uin = _safe_int(result.get("user_id") or result.get("uin") or result.get("qq"), 0, 0)
            except Exception:
                login_uin = 0
            if login_uin:
                merged["uin"] = f"o{login_uin}"
                merged["p_uin"] = f"o{login_uin}"
        if merged:
            cookie_text = self._qzone_cookie_header(merged)
            try:
                ctx = self._qzone_context_from_cookies(cookie_text)
                if ctx.get("uin") and ctx.get("gtk"):
                    return cookie_text
            except Exception:
                pass
            if self._qzone_normalize_uin(merged):
                return cookie_text
        raise RuntimeError("获取 QQ 空间 Cookie 失败")

    @staticmethod
    def _qzone_parse_response(text: str) -> dict[str, Any]:
        raw = str(text or "")
        if not raw.strip():
            return {"code": -1, "message": "接口返回空响应"}
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end < start:
            return {"code": -1, "message": "接口响应缺少 JSON"}
        payload = raw[start : end + 1].replace("undefined", "null")
        try:
            parsed = json.loads(payload)
        except Exception as exc:
            return {"code": -1, "message": f"JSON 解析失败：{_single_line(exc, 80)}"}
        if isinstance(parsed, dict) and isinstance(parsed.get("data"), dict):
            nested = dict(parsed.get("data") or {})
            nested.setdefault("_raw_code", parsed.get("code", parsed.get("ret")))
            nested.setdefault("_raw_message", parsed.get("message") or parsed.get("msg"))
            return nested
        return parsed if isinstance(parsed, dict) else {"code": -1, "message": "接口响应不是对象"}

    async def _qzone_request(
        self,
        event: AstrMessageEvent | None,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 20.0,
    ) -> dict[str, Any]:
        import aiohttp

        ctx = self._qzone_context_from_cookies(await self._qzone_get_cookies(event))
        parsed_url = urlparse(url)
        origin = f"{parsed_url.scheme}://{parsed_url.netloc}" if parsed_url.scheme and parsed_url.netloc else "https://user.qzone.qq.com"
        request_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36",
            "Cookie": ctx["cookie_header"],
            "Referer": f"https://user.qzone.qq.com/{ctx['uin']}",
            "Origin": origin,
            "Host": parsed_url.netloc or "user.qzone.qq.com",
            "Connection": "keep-alive",
        }
        if headers:
            request_headers.update(headers)
        timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        async with aiohttp.ClientSession(timeout=timeout, headers=request_headers) as session:
            async with session.request(method, url, params=params, data=data) as response:
                text = await response.text()
                parsed = self._qzone_parse_response(text)
                parsed.setdefault("_http_status", response.status)
                if parsed.get("message") == "接口返回空响应":
                    parsed["message"] = f"接口返回空响应（HTTP {response.status}）"
                if response.status == 403 and parsed.get("code") in {-1, None}:
                    parsed["message"] = "无权限访问 QQ 空间或 Cookie 已失效"
                return parsed

    def _qzone_parse_feeds(self, msglist: list[Any]) -> list[Any]:
        posts: list[Any] = []
        for msg in msglist:
            if not isinstance(msg, dict):
                continue
            images: list[str] = []
            for image in msg.get("pic", []) if isinstance(msg.get("pic"), list) else []:
                if not isinstance(image, dict):
                    continue
                for key in ("url2", "url3", "url1", "smallurl"):
                    raw = image.get(key)
                    if raw:
                        images.append(str(raw))
                        break
            for video in msg.get("video", []) if isinstance(msg.get("video"), list) else []:
                if isinstance(video, dict) and (video.get("url1") or video.get("pic_url")):
                    images.append(str(video.get("url1") or video.get("pic_url")))
            posts.append(
                SimpleNamespace(
                    tid=str(msg.get("tid") or ""),
                    uin=int(msg.get("uin") or 0),
                    name=str(msg.get("name") or ""),
                    text=str(msg.get("content") or "").strip(),
                    rt_con=str((msg.get("rt_con") or {}).get("content") or "") if isinstance(msg.get("rt_con"), dict) else "",
                    images=images,
                    comments=[],
                    create_time=msg.get("created_time") or 0,
                    status="approved",
                )
            )
        return posts

    async def _qzone_query_feeds(
        self,
        event: AstrMessageEvent | None = None,
        *,
        target_id: str | None = None,
        pos: int = 0,
        num: int = 1,
        with_detail: bool = False,
    ) -> list[Any]:
        ctx = self._qzone_context_from_cookies(await self._qzone_get_cookies(event))
        target = _single_line(target_id, 40)
        if not target:
            target = str(ctx["uin"])
        payload = await self._qzone_request(
            event,
            "GET",
            "https://user.qzone.qq.com/proxy/domain/taotao.qq.com/cgi-bin/emotion_cgi_msglist_v6",
            params={
                "g_tk": ctx["gtk"],
                "uin": target,
                "ftype": 0,
                "sort": 0,
                "pos": max(0, int(pos or 0)),
                "num": max(1, int(num or 1)),
                "replynum": 100,
                "callback": "_preloadCallback",
                "code_version": 1,
                "format": "json",
                "need_comment": 1 if with_detail else 0,
                "need_private_comment": 1 if with_detail else 0,
            },
        )
        code = payload.get("code", 0)
        if code not in {0, "0"}:
            raise RuntimeError(_single_line(payload.get("message") or payload.get("msg") or f"查询失败 code={code}", 160))
        msglist = payload.get("msglist") or []
        if not isinstance(msglist, list):
            msglist = []
        return self._qzone_parse_feeds(msglist)

    async def _qzone_publish_post(
        self,
        event: AstrMessageEvent | None = None,
        *,
        text: str = "",
        images: list[str] | None = None,
    ) -> Any:
        ctx = self._qzone_context_from_cookies(await self._qzone_get_cookies(event))
        content = _single_line(text, 300)
        if not content and not images:
            raise RuntimeError("说说内容为空")
        referrer = f"https://user.qzone.qq.com/{ctx['uin']}"
        data = {
            "syn_tweet_verson": "1",
            "paramstr": "1",
            "who": "1",
            "con": content,
            "feedversion": "1",
            "ver": "1",
            "ugc_right": 1,
            "to_sign": 0,
            "hostuin": ctx["uin"],
            "code_version": "1",
            "richval": "",
            "issyncweibo": 0,
            "format": "json",
            "qzreferrer": referrer,
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Referer": referrer,
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
        }
        endpoints = [
            "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6",
            "https://h5.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6",
            "http://taotao.qzone.qq.com/cgi-bin/emotion_cgi_publish_v6",
        ]
        payload: dict[str, Any] = {}
        failures: list[str] = []
        for endpoint in endpoints:
            payload = await self._qzone_request(
                event,
                "POST",
                endpoint,
                params={"g_tk": ctx["gtk"]},
                data=data,
                headers=headers,
            )
            code = payload.get("code", 0)
            if code in {0, "0"}:
                break
            failures.append(f"{urlparse(endpoint).netloc}: {_single_line(payload.get('message') or payload.get('msg') or f'code={code}', 120)}")
        code = payload.get("code", 0)
        if code not in {0, "0"}:
            detail = "；".join(failures) or _single_line(payload.get("message") or payload.get("msg") or f"发布失败 code={code}", 160)
            raise RuntimeError(_single_line(detail, 220))
        return SimpleNamespace(
            tid=str(payload.get("tid") or ""),
            uin=int(ctx["uin"]),
            name=str(ctx["uin"]),
            text=content,
            images=images or [],
            create_time=payload.get("now") or int(time.time()),
            status="approved",
        )

    async def _qzone_like_post(self, event: AstrMessageEvent | None, post: Any) -> None:
        ctx = self._qzone_context_from_cookies(await self._qzone_get_cookies(event))
        tid = str(getattr(post, "tid", "") or "")
        uin = str(getattr(post, "uin", "") or "")
        if not tid or not uin:
            raise RuntimeError("说说 tid 或 uin 为空，无法点赞")
        payload = await self._qzone_request(
            event,
            "POST",
            "https://user.qzone.qq.com/proxy/domain/w.qzone.qq.com/cgi-bin/likes/internal_dolike_app",
            params={"g_tk": ctx["gtk"]},
            data={
                "qzreferrer": f"https://user.qzone.qq.com/{ctx['uin']}",
                "opuin": ctx["uin"],
                "unikey": f"https://user.qzone.qq.com/{uin}/mood/{tid}",
                "curkey": f"https://user.qzone.qq.com/{uin}/mood/{tid}",
                "appid": 311,
                "from": 1,
                "typeid": 0,
                "abstime": int(time.time()),
                "fid": tid,
                "active": 0,
                "format": "json",
                "fupdate": 1,
            },
        )
        code = payload.get("code", 0)
        if code not in {0, "0"}:
            raise RuntimeError(_single_line(payload.get("message") or payload.get("msg") or f"点赞失败 code={code}", 160))

    async def _qzone_generate_comment(self, post: Any) -> str:
        prompt = f"""
请以当前 Bot 人格，为下面这条 QQ 空间说说写一句自然评论。
只输出评论正文，不要解释。

要求：
- 8 到 40 字。
- 像真实熟人评论，不要像客服或总结。
- 不要泄露私聊内容、插件内部信息、关系网资料或状态数值。
- 如果内容信息不足，可以写轻量回应。

【作者】
{_single_line(getattr(post, "name", ""), 40) or _single_line(getattr(post, "uin", ""), 40) or "对方"}

【说说内容】
{_single_line(getattr(post, "text", "") or getattr(post, "rt_con", ""), 240) or "无文本"}
""".strip()
        text = await self._llm_call(
            prompt,
            max_tokens=80,
            provider_id=self._task_provider(self.mai_style_provider_id, self.llm_provider_id),
            task="qzone_comment",
        )
        return _single_line(text, 80)

    async def _qzone_comment_post(self, event: AstrMessageEvent | None, post: Any, content: str = "") -> str:
        ctx = self._qzone_context_from_cookies(await self._qzone_get_cookies(event))
        tid = str(getattr(post, "tid", "") or "")
        uin = str(getattr(post, "uin", "") or "")
        if not tid or not uin:
            raise RuntimeError("说说 tid 或 uin 为空，无法评论")
        comment = _single_line(content, 120) or await self._qzone_generate_comment(post)
        if not comment:
            raise RuntimeError("评论内容为空")
        payload = await self._qzone_request(
            event,
            "POST",
            "https://user.qzone.qq.com/proxy/domain/taotao.qzone.qq.com/cgi-bin/emotion_cgi_re_feeds",
            params={"g_tk": ctx["gtk"]},
            data={
                "topicId": f"{uin}_{tid}__1",
                "uin": ctx["uin"],
                "hostUin": uin,
                "feedsType": 100,
                "inCharset": "utf-8",
                "outCharset": "utf-8",
                "plat": "qzone",
                "source": "ic",
                "platformid": 52,
                "format": "fs",
                "ref": "feeds",
                "content": comment,
            },
        )
        code = payload.get("code", 0)
        if code not in {0, "0"}:
            raise RuntimeError(_single_line(payload.get("message") or payload.get("msg") or f"评论失败 code={code}", 160))
        return comment


    async def _publish_qzone_text(self, text: str, event: AstrMessageEvent | None = None) -> dict[str, Any]:
        if not self.enable_qzone_integration:
            return {"success": False, "message": "QQ 空间动态层未启用"}
        content = _single_line(text, 300)
        if not content:
            return {"success": False, "message": "说说内容为空"}
        try:
            post = await self._qzone_publish_post(event, text=content, images=[])
            return {
                "success": True,
                "text": _single_line(getattr(post, "text", content), 300) or content,
                "tid": str(getattr(post, "tid", "") or ""),
                "uin": str(getattr(post, "uin", "") or ""),
            }
        except Exception as exc:
            return {"success": False, "message": _single_line(exc, 160)}

    async def _test_qzone_publish_tool_chain(self, event: AstrMessageEvent | None = None) -> str:
        lines = ["QQ 空间发布链路模拟："]
        lines.append(f"- 整合开关：{'开启' if self.enable_qzone_integration else '关闭'}")
        lines.append("- 真实发布：否，本指令只模拟工具链路")

        try:
            empty_result_raw = await self._pc_qzone_publish_feed_impl(event, "")
            empty_result = json.loads(empty_result_raw)
        except Exception as exc:
            empty_result = {"status": "exception", "message": _single_line(exc, 160)}
        lines.append(
            "- 空参数工具调用："
            + (
                "通过，返回 need_text"
                if empty_result.get("status") == "need_text"
                else f"异常，返回 {empty_result.get('status') or empty_result.get('message') or empty_result}"
            )
        )

        daily_state = self.data.get("daily_state", {})
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        diary_context = self._recent_diary_context(count=2)
        prompt = f"""
请以当前 Bot 人格写一条 QQ 空间说说。
只输出说说正文,不要解释,不要加标题。

要求：
- 30 到 120 字。
- 像自然生活动态,不是公告、不是任务汇报。
- 可以带一点当前状态、日程、天气或日记余味,但不要暴露插件、模型、内部状态数值。
- 不要 @ 用户,不要泄露私聊内容,不要写得像营销文。

【当前状态】
{self._format_state_for_prompt(daily_state if isinstance(daily_state, dict) else {})}

【当前/附近日程】
{self._format_plan_item_for_prompt(current_item) or "无明确日程"}

【近日私密日记余味】
{diary_context or "暂无"}

{self._format_worldview_adaptation_prompt()}
""".strip()
        try:
            draft = await self._llm_call(
                prompt,
                max_tokens=180,
                provider_id=self._task_provider(self.mai_style_provider_id, self.llm_provider_id),
                task="qzone_publish_test",
            )
            draft = _single_line(draft, 180)
        except Exception as exc:
            draft = ""
            lines.append(f"- 草稿生成：失败，{_single_line(exc, 160)}")
        if draft:
            lines.append("- 草稿生成：成功")
            lines.append(f"- 将传入工具参数：{{\"text\":\"{draft}\"}}")
            lines.append(f"- 草稿正文：{draft}")
        else:
            lines.append("- 草稿生成：失败或为空")
        lines.append("结果：模拟完成。若要真实发布,请使用 `陪伴 发说说 <正文>` 或让模型调用带 text 的 `pc_qzone_publish_feed`。")
        return "\n".join(lines)

    async def _test_qzone_integration(self, event: AstrMessageEvent, target_id: str = "") -> str:
        lines = ["QQ 空间测试："]

        lines.append(f"- 整合开关：{'开启' if self.enable_qzone_integration else '关闭'}")
        lines.append("- 内置服务：可用")
        lines.append("- 外部插件依赖：无")

        if not self.enable_qzone_integration:
            lines.append("结果：整合开关关闭。")
            return "\n".join(lines)

        target = _single_line(target_id, 40)
        try:
            ctx = self._qzone_context_from_cookies(await self._qzone_get_cookies(event))
            target = target or str(ctx.get("uin") or "")
            lines.append(f"- Cookie：已获取，登录 QQ {ctx.get('uin')}")
            lines.append("- 读取动态：可用")
            lines.append("- 发布说说：可用")
            lines.append("- 点赞/评论：可用")
            posts = await self._qzone_query_feeds(event, target_id=target or None, pos=0, num=1, with_detail=True)
            if not posts:
                lines.append(f"- 查询目标：{target or '默认'}")
                lines.append("- 查询结果：空")
                lines.append("结果：读取链路可调用，但没有拿到动态。")
                return "\n".join(lines)
            post = posts[0]
            text = _single_line(getattr(post, "text", "") or getattr(post, "rt_con", ""), 120)
            images = list(getattr(post, "images", []) or [])
            lines.append(f"- 查询目标：{target or '默认'}")
            lines.append("- 查询结果：成功")
            lines.append(f"- 作者：{_single_line(getattr(post, 'name', ''), 40) or '未知'}")
            lines.append(f"- QQ：{str(getattr(post, 'uin', '') or '') or '未知'}")
            lines.append(f"- 内容：{text or '无文本'}")
            lines.append(f"- 图片数：{len(images)}")
            lines.append("结果：QQ 空间读取链路正常。")
            return "\n".join(lines)
        except Exception as exc:
            lines.append(f"- 查询目标：{target or '默认'}")
            error_text = _single_line(exc, 160)
            if "空响应" in error_text:
                error_text = "接口返回空响应，通常表示目标空间不可见、无权限访问，或当前 Cookie 对该目标无访问权"
            lines.append(f"- 查询结果：失败：{error_text}")
            lines.append("结果：内置服务已加载，但 QQ 空间访问失败。")
            return "\n".join(lines)

    async def _maybe_publish_qzone_life_post(self) -> None:
        if not (self.enable_qzone_integration and self.enable_qzone_life_publish):
            return
        now = _now_ts()
        state = self.data.setdefault("qzone_integration", {})
        if not isinstance(state, dict):
            self.data["qzone_integration"] = {}
            state = self.data["qzone_integration"]
        last_status = str(state.get("last_life_publish_status") or "").strip()
        if (
            last_status == "published"
            and now - _safe_float(state.get("last_life_publish_at"), 0) < max(4, self.qzone_life_publish_min_interval_hours) * 3600
        ):
            return
        if now - _safe_float(state.get("last_life_publish_failed_at"), 0) < 15 * 60:
            return
        if random.random() > self.qzone_life_publish_probability:
            state["last_life_publish_status"] = "skipped:probability_miss"
            state["last_life_publish_checked_at"] = now
            self._save_data_sync()
            return
        if getattr(self, "_qzone_last_bot", None) is None:
            state["last_life_publish_failed_at"] = now
            state["last_life_publish_status"] = "failed:no_onebot_connection"
            state["last_life_publish_checked_at"] = now
            self._save_data_sync()
            return
        daily_state = self.data.get("daily_state", {})
        current_item = self._get_current_plan_item(self.data.get("daily_plan", {}))
        diary_context = self._recent_diary_context(count=2)
        prompt = f"""
请以当前 Bot 人格写一条 QQ 空间说说。
只输出说说正文,不要解释,不要加标题。

要求：
- 30 到 120 字。
- 像自然生活动态,不是公告、不是任务汇报。
- 可以带一点当前状态、日程、天气或日记余味,但不要暴露插件、模型、内部状态数值。
- 不要 @ 用户,不要泄露私聊内容,不要写得像营销文。

【当前状态】
{self._format_state_for_prompt(daily_state if isinstance(daily_state, dict) else {})}

【当前/附近日程】
{self._format_plan_item_for_prompt(current_item) or "无明确日程"}

【近日私密日记余味】
{diary_context or "暂无"}

{self._format_worldview_adaptation_prompt()}
""".strip()
        text = await self._llm_call(
            prompt,
            max_tokens=180,
            provider_id=self._task_provider(self.mai_style_provider_id, self.llm_provider_id),
            task="qzone_publish",
        )
        text = _single_line(text, 180)
        result = await self._publish_qzone_text(text)
        if result.get("success"):
            state["last_life_publish_at"] = now
            state.pop("last_life_publish_failed_at", None)
            state["last_life_publish_status"] = "published"
        else:
            state["last_life_publish_failed_at"] = now
            state["last_life_publish_status"] = f"failed:{_single_line(result.get('message'), 80)}"
        state["last_life_publish_checked_at"] = now
        state["last_life_publish_text"] = _single_line(result.get("text") or text, 180)
        self._save_data_sync()

