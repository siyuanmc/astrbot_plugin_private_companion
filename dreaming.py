# -*- coding: utf-8 -*-

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from .helpers import _now_ts, _safe_float, _safe_int, _single_line, _today_key


_ABSTRACT_DREAM_FRAGMENT_MARKERS = (
    "状态", "情绪", "心情", "感觉", "余韵", "碎片", "生活感", "日程", "计划", "总结",
    "今天", "明天", "用户", "主动", "消息", "回复", "关系", "陪伴", "模型", "生成",
)


def _clean_dream_fragment_text(text: Any, limit: int = 28) -> str:
    raw = _single_line(text, 80)
    if not raw:
        return ""
    raw = raw.replace("，", ",").replace("。", ",").replace("；", ",").replace("、", ",")
    parts = [part.strip(" ,.!！？?：:（）()[]【】\"'“”") for part in raw.split(",") if part.strip()]
    if parts:
        parts = sorted(parts, key=lambda item: (len(item) > limit, len(item)))
        raw = parts[0]
    raw = _single_line(raw, limit).strip(" ,.!！？?：:（）()[]【】\"'“”")
    if len(raw) <= 1:
        return ""
    return raw


def _dream_fragment_is_useful(text: str) -> bool:
    cleaned = str(text or "").strip()
    if not cleaned or cleaned in {"没有记住梦", "平稳", "暂无天气信息", "无明确碎片"}:
        return False
    if len(cleaned) > 32:
        return False
    abstract_hits = sum(1 for marker in _ABSTRACT_DREAM_FRAGMENT_MARKERS if marker in cleaned)
    concrete_markers = (
        "光", "雨", "风", "水", "纸", "书", "门", "窗", "杯", "碗", "路", "影", "声", "味",
        "颜色", "蓝", "红", "白", "黑", "暖", "冷", "手", "衣", "鞋", "车", "灯", "雾", "床",
        "被子", "手机", "屏幕", "钥匙", "包装", "饮料", "猫", "楼梯", "走廊",
    )
    has_concrete = any(marker in cleaned for marker in concrete_markers)
    if abstract_hits >= 2 and not has_concrete:
        return False
    return True


def recent_diary_tags(plugin, /) -> set[str]:
    diaries = plugin.data.get("bot_diaries", [])
    tags: set[str] = set()
    if not isinstance(diaries, list):
        return tags
    for diary in diaries[-3:]:
        if not isinstance(diary, dict):
            continue
        raw_tags = diary.get("tags", [])
        if isinstance(raw_tags, list):
            tags.update(str(tag) for tag in raw_tags)
    return tags


def recent_diary_context(plugin, count: int = 3) -> str:
    diaries = plugin.data.get("bot_diaries", [])
    if not isinstance(diaries, list) or not diaries:
        return "（暂无）"
    lines = []
    for diary in diaries[-count:]:
        if not isinstance(diary, dict):
            continue
        tags = diary.get("tags", [])
        tag_text = "、".join(str(tag) for tag in tags[:4]) if isinstance(tags, list) else ""
        summary = _single_line(diary.get("summary"), 120)
        if summary:
            lines.append(f"- {diary.get('date', '')}：{summary} {tag_text}".strip())
    return "\n".join(lines) if lines else "（暂无）"


def normalize_dream_fragment_item(plugin, raw: Any) -> dict[str, Any] | None:
    now_ts = _now_ts()
    if isinstance(raw, str):
        text = _clean_dream_fragment_text(raw)
        if not text or not _dream_fragment_is_useful(text):
            return None
        return {
            "text": text,
            "weight": 1.0,
            "created_ts": now_ts,
            "source": "legacy",
        }
    if not isinstance(raw, dict):
        return None
    text = _clean_dream_fragment_text(raw.get("text") or raw.get("keyword") or raw.get("label"))
    if not text or not _dream_fragment_is_useful(text):
        return None
    weight = float(_safe_float(raw.get("weight"), 1.0))
    created_ts = _safe_float(raw.get("created_ts"), now_ts)
    if created_ts <= 0:
        created_ts = now_ts
    return {
        "text": text,
        "weight": max(0.2, min(6.0, weight)),
        "created_ts": created_ts,
        "source": _single_line(raw.get("source"), 20) or "diary",
        "date": _single_line(raw.get("date"), 16) or _today_key(),
    }


def dream_fragment_effective_weight(plugin, fragment: dict[str, Any], now_ts: float | None = None) -> float:
    now_ts = now_ts or _now_ts()
    base_weight = max(0.2, min(6.0, _safe_float(fragment.get("weight"), 1.0)))
    created_ts = _safe_float(fragment.get("created_ts"), now_ts)
    age_hours = max(0.0, (now_ts - created_ts) / 3600.0)
    decay = pow(0.72, age_hours / 24.0)
    return base_weight * decay


def normalize_dream_fragment_pool(plugin, fragments: Any, *, now_ts: float | None = None) -> list[dict[str, Any]]:
    now_ts = now_ts or _now_ts()
    if not isinstance(fragments, list):
        return []
    deduped: dict[str, dict[str, Any]] = {}
    for raw in fragments:
        item = plugin._normalize_dream_fragment_item(raw)
        if not item:
            continue
        text = item["text"]
        item["effective_weight"] = plugin._dream_fragment_effective_weight(item, now_ts=now_ts)
        if item["effective_weight"] < 0.12:
            continue
        existing = deduped.get(text)
        if not existing or item["effective_weight"] > existing.get("effective_weight", 0):
            deduped[text] = item
    ranked = sorted(
        deduped.values(),
        key=lambda item: (float(item.get("effective_weight", 0)), float(item.get("created_ts", 0))),
        reverse=True,
    )
    for item in ranked:
        item.pop("effective_weight", None)
    return ranked[:48]


def extract_weighted_dream_fragments(plugin, payload: Any) -> list[dict[str, Any]]:
    raw_items = []
    if isinstance(payload, dict):
        raw_items = payload.get("dream_fragments") or []
    if not isinstance(raw_items, list):
        raw_items = []
    items: list[dict[str, Any]] = []
    for raw in raw_items[:12]:
        if isinstance(raw, str):
            normalized = plugin._normalize_dream_fragment_item({"text": raw, "weight": 1.0, "source": "diary"})
        elif isinstance(raw, dict):
            normalized = plugin._normalize_dream_fragment_item(
                {
                    "text": raw.get("text") or raw.get("keyword") or raw.get("label"),
                    "weight": raw.get("weight", 1.0),
                    "source": raw.get("source") or "diary",
                    "date": _today_key(),
                    "created_ts": _now_ts(),
                }
            )
        else:
            normalized = None
        if normalized:
            items.append(normalized)
    return items[:8]


def fallback_dream_fragments_for_diary(plugin, state: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seed_candidates = [
        _single_line(state.get("dream"), 36),
        _single_line(state.get("mood_bias"), 20),
        _single_line(plugin._weather_summary_text(plugin.data.get("daily_weather", {})), 36),
    ]
    current_item = plugin._get_current_plan_item(plugin.data.get("daily_plan", {}))
    if isinstance(current_item, dict):
        seed_candidates.extend(
            [
                _single_line(current_item.get("activity"), 36),
                _single_line(current_item.get("message_seed"), 30),
            ]
        )
    seen: set[str] = set()
    for index, text in enumerate(seed_candidates):
        text = _clean_dream_fragment_text(text)
        if not text or text in seen or not _dream_fragment_is_useful(text):
            continue
        seen.add(text)
        items.append(
            {
                "text": text,
                "weight": max(1.0, 2.4 - index * 0.4),
                "created_ts": _now_ts(),
                "source": "fallback_diary",
                "date": _today_key(),
            }
        )
    return items[:5]


def merge_dream_fragment_pool(plugin, new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    existing = plugin._normalize_dream_fragment_pool(plugin.data.get("dream_fragments", []))
    merged = existing + [item for item in new_items if isinstance(item, dict)]
    return plugin._normalize_dream_fragment_pool(merged)


def weighted_unique_fragment_sample(plugin, fragments: list[dict[str, Any]], *, count: int) -> list[str]:
    if not fragments or count <= 0:
        return []
    remaining = [dict(item) for item in fragments if isinstance(item, dict)]
    picked: list[str] = []
    while remaining and len(picked) < count:
        weights = [max(0.01, plugin._dream_fragment_effective_weight(item)) for item in remaining]
        total = sum(weights)
        if total <= 0:
            break
        chosen = random.choices(remaining, weights=weights, k=1)[0]
        text = _single_line(chosen.get("text"), 40)
        if text and text not in picked:
            picked.append(text)
        remaining = [item for item in remaining if _single_line(item.get("text"), 40) != text]
    return picked


def build_dream_memory_fragments(plugin, count: int = 8) -> list[str]:
    fragment_pool = plugin._normalize_dream_fragment_pool(plugin.data.get("dream_fragments", []))
    picked = plugin._weighted_unique_fragment_sample(fragment_pool, count=min(count, 6))
    if len(picked) >= count:
        return picked[:count]
    fragments: list[str] = []
    diaries = plugin.data.get("bot_diaries", [])
    if isinstance(diaries, list):
        for diary in diaries[-4:]:
            if not isinstance(diary, dict):
                continue
            for candidate in (
                _single_line(diary.get("share_seed"), 80),
                _single_line(diary.get("summary"), 80),
            ):
                if candidate:
                    cleaned = _clean_dream_fragment_text(candidate)
                    if cleaned and _dream_fragment_is_useful(cleaned):
                        fragments.append(cleaned)
    current_plan = plugin.data.get("daily_plan", {})
    if isinstance(current_plan, dict):
        items = current_plan.get("items", [])
        if isinstance(items, list):
            for item in items[-3:]:
                if not isinstance(item, dict):
                    continue
                for candidate in (
                    _single_line(item.get("activity"), 80),
                    _single_line(item.get("message_seed"), 80),
                ):
                    cleaned = _clean_dream_fragment_text(candidate)
                    if cleaned and _dream_fragment_is_useful(cleaned):
                        fragments.append(cleaned)
    can_do = plugin.data.get("can_do", [])
    if isinstance(can_do, list):
        for item in can_do[:4]:
            candidate = _single_line(item, 60)
            cleaned = _clean_dream_fragment_text(candidate)
            if cleaned and _dream_fragment_is_useful(cleaned):
                fragments.append(cleaned)
    for entry in plugin._get_relevant_important_dates()[:3]:
        if not isinstance(entry, dict):
            continue
        joined = _single_line(
            f"{entry.get('title', '')} {entry.get('note', '')}",
            80,
        )
        cleaned = _clean_dream_fragment_text(joined)
        if cleaned and _dream_fragment_is_useful(cleaned):
            fragments.append(cleaned)
    yesterday = plugin.data.get("yesterday_conversation_summary", {})
    if isinstance(yesterday, dict) and yesterday.get("date") == _today_key():
        for candidate in (
            _single_line(yesterday.get("dream_reference"), 100),
            _single_line(yesterday.get("summary"), 100),
        ):
            cleaned = _clean_dream_fragment_text(candidate)
            if cleaned and "无明确" not in candidate and _dream_fragment_is_useful(cleaned):
                fragments.append(cleaned)
        residues = yesterday.get("residues", [])
        if isinstance(residues, list):
            for item in residues[:4]:
                if not isinstance(item, dict):
                    continue
                content = _single_line(item.get("content"), 80)
                cleaned = _clean_dream_fragment_text(content)
                if cleaned and _dream_fragment_is_useful(cleaned):
                    fragments.append(cleaned)
    weather = _single_line(plugin._weather_summary_text(plugin.data.get("daily_weather", {})), 60)
    weather_fragment = _clean_dream_fragment_text(weather)
    if weather_fragment and _dream_fragment_is_useful(weather_fragment):
        fragments.append(weather_fragment)
    deduped: list[str] = []
    seen: set[str] = set()
    for fragment in fragments:
        if not fragment or fragment in seen:
            continue
        seen.add(fragment)
        deduped.append(fragment)
    random.shuffle(deduped)
    for fragment in deduped:
        if fragment not in picked:
            picked.append(fragment)
        if len(picked) >= count:
            break
    return picked[:count]


def dream_theme_specs(plugin) -> list[tuple[str, str]]:
    default_specs = {
        "温柔日常": "梦像从白天的普通片段里慢慢渗出来，柔软、安静、带一点生活气。",
        "奇幻": "现实里的东西轻轻偏离常理，带一点不合逻辑的发光感或变形感。",
        "恐怖": "不是血腥惊吓，而是熟悉场景里多出一点说不清的不安和压迫。",
        "追逐": "一直在赶什么、找什么、错过什么，节奏偏紧，醒来会残留一点慌。",
        "悬疑": "细节像有答案却总差一点，梦里会反复回头、确认、怀疑。",
        "荒诞": "东西会莫名其妙地接到一起，逻辑松掉，带一点好笑又奇怪的偏移。",
        "怀旧": "梦会把旧场景、旧物件、旧关系轻轻翻出来，但不一定讲得明白。",
        "暧昧春梦": "梦里会有一点亲密、靠近、心跳变快的错觉，但保持含蓄，不写露骨内容。",
    }
    raw = str(plugin.dream_theme_candidates or "").strip()
    names = [name.strip() for name in raw.split(",") if name.strip()]
    if not names:
        names = list(default_specs.keys())
    specs: list[tuple[str, str]] = []
    for name in names:
        if name == "暧昧春梦" and not plugin.enable_intimate_dream_theme:
            continue
        specs.append((name, default_specs.get(name, f"梦整体偏{name}，但仍然要从具体生活碎片出发,保留一条能读懂的梦内情绪线。")))
    if not specs:
        specs.append(("温柔日常", default_specs["温柔日常"]))
    return specs


async def generate_enhanced_dream_pick(plugin, weather: dict[str, Any] | None = None) -> tuple[str, str, int, int] | None:
    fragments = plugin._build_dream_memory_fragments()
    if not fragments:
        persona_hint = _single_line(plugin._get_default_persona_prompt(), 80)
        weather_hint = _single_line(plugin._weather_summary_text(weather or plugin.data.get("daily_weather", {})), 60)
        can_do = plugin.data.get("can_do", [])
        activity_hint = ""
        if isinstance(can_do, list) and can_do:
            activity_hint = _single_line(random.choice(can_do), 60)
        fragments = [
            item
            for item in (persona_hint, weather_hint, activity_hint, "醒来后只剩一点断续的画面")
            if item and item != "暂无天气信息"
        ]
    dream_themes = plugin._dream_theme_specs()
    primary_name, primary_hint = random.choice(dream_themes)
    theme_name = primary_name
    theme_hint = primary_hint
    if plugin.enable_mixed_dream_themes and len(dream_themes) >= 2 and random.random() < 0.35:
        alt_name, alt_hint = random.choice([item for item in dream_themes if item[0] != primary_name])
        theme_name = f"{primary_name}+{alt_name}"
        theme_hint = f"主调偏{primary_name}，但中途会混进一点{alt_name}的质感。{primary_hint} 同时，{alt_hint}"
    persona = plugin._get_default_persona_prompt()
    weather_text = plugin._weather_summary_text(weather or plugin.data.get("daily_weather", {}))
    prompt = f"""
你现在是 Private Companion 的梦境生成器。请根据本次输入的记忆碎片,写一个拟人化 Bot 今早残留的完整梦境。
这个梦可以跳接、荒诞、前后不完全合逻辑,但读起来必须摸得到一条“梦里的情绪线”：她在找什么、躲什么、靠近什么、误认了什么,或为什么醒来后还残留那种感觉。不要只把碎片随机拼贴。

要求：
1. 梦境内容要像把记忆碎片在梦里重新变形,允许断裂和跳场,但必须有“发生了什么”和“为什么醒来后还记得”。
2. 尽量保留一点真实生活残影,不要纯奇幻大场面；如果出现奇幻,也要让它从生活物件、聊天残留或身体感受里长出来。
3. 不要写成日程、日记、设定说明或心理分析。梦里可以有人、物、地点变化,但不要解释得太清楚。
4. 如果主题偏温柔,energy_delta 可以略微为正；如果主题偏压迫/追赶/恐怖,可以略微为负。
5. 如果主题涉及暧昧或春梦,保持含蓄,只写心跳、靠近、错觉感,不要露骨。
6. 如果碎片很少,也要用已有的人格、天气、最近日记补出一个完整梦,不能输出“没有梦”“记不清”“什么都没有”。
7. 梦境不是现实复盘,但要有现实残留：物件、颜色、声音、气味、身体感受、半句话、聊天余味都可以以变形方式出现。
8. 不要让梦境像宏大奇幻设定简介。即使有不现实元素,也要从房间、桌面、手机、路口、雨声、光线、衣物、食物、课本、屏幕等具体生活物里长出来。
9. 梦境可以有突兀转场,但每个转场前后都要能被读者想象到画面。
10. 输出必须是 JSON,不要 Markdown,不要解释,不要在 JSON 外补充任何内容。
11. factors 必须是可感知的小碎片,例如物件、颜色、声音、气味、触感、半句话；不要输出“情绪很好”“今天很累”“日程残留”这类抽象标签。
12. content 至少包含三个连续梦内节点：起始画面、变形/转场、醒前一瞬。可以不讲现实逻辑,但要讲梦内因果。
13. 不要把“资料室、发光、迷路、追逐、水光、草稿纸”等词当作固定模板反复使用；只有输入碎片里真的有相近材料时才用。

只输出 JSON：
{{
  "dream_type": "梦境类型,例如温柔日常/奇幻/追逐/悬疑/荒诞/怀旧/混合类型",
  "factors": ["梦境因子或碎片,3到8个,可以是物件/颜色/声音/气味/半句话/动作"],
  "content": "180到600字的梦境内容,写成完整一段梦；要有起始画面、变形/转场、醒前一瞬和清楚的梦内情绪线",
  "afterglow": "醒来后的梦境余韵,20到120字,说明身体或情绪残留",
  "label": "20到50字的短标签,概括这个梦留在身上的感觉",
  "mood": "平稳/恍惚/柔和/低落/敏感/轻快 之一",
  "energy_delta": -12到6之间的整数",
  "duration_hours": 3到8之间的整数
}}

【本次输入】
【人格参考】
{persona}

【梦境主题】
{theme_name}：{theme_hint}

【碎片记忆】
{chr(10).join(f"- {item}" for item in fragments)}

【天气】
{weather_text}

""".strip()
    raw_text = await plugin._llm_call(
        prompt,
        max_tokens=1050,
        provider_id=plugin._task_provider(
            getattr(plugin, "dream_provider_id", ""),
            getattr(plugin, "diary_provider_id", ""),
            getattr(plugin, "mai_style_provider_id", ""),
        ),
    )
    payload = plugin._extract_json_payload(raw_text or "")
    if not isinstance(payload, dict):
        return None
    content = _single_line(payload.get("content"), 900)
    factors_raw = payload.get("factors")
    factors = []
    if isinstance(factors_raw, list):
        factors = [_single_line(item, 30) for item in factors_raw[:8] if _single_line(item, 30)]
    label = _single_line(payload.get("label"), 80)
    if not label and content:
        label = _single_line(content, 80)
    if not label:
        return None
    mood = _single_line(payload.get("mood"), 12) or "恍惚"
    energy_delta = _safe_int(payload.get("energy_delta"), -6, -12, 6)
    duration_hours = _safe_int(payload.get("duration_hours"), 5, 3, 8)
    if not content:
        content = f"梦里只剩下一段很断续的画面：{label}"
    plugin._last_generated_dream_payload = {
        "dream_type": _single_line(payload.get("dream_type"), 40) or theme_name,
        "factors": factors or fragments[:8],
        "content": content,
        "afterglow": _single_line(payload.get("afterglow"), 180) or label,
        "label": label,
        "mood": mood,
        "energy_delta": energy_delta,
        "duration_hours": duration_hours,
        "raw": raw_text or "",
    }
    return label, mood, energy_delta, duration_hours


async def generate_daily_diary(plugin) -> dict[str, Any]:
    today = _today_key()
    state = plugin.data.get("daily_state", {})
    plan = plugin.data.get("daily_plan", {})
    can_do = plugin._format_can_do_for_prompt()
    calendar_context = plugin._format_calendar_context_for_prompt()
    yesterday_conversation = plugin._format_yesterday_conversation_summary_for_prompt()
    prompt = f"""
你现在是 Private Companion 的日记生成器。请为拟人化 Bot 写一条今天的日记,同时预设今天的生活碎片和主动聊天计划。

【写日记的要求】
· 短、口语、像社交媒体上随手写给自己看的。不要散文腔,不要长篇。
· 只记你自己的状态和看到的小事。不要对用户施压,不要写成计划清单。
· 可参考的事件：通勤或出门、路上看到的、梦、失眠、不舒服、饿了、整理东西、想到用户、重要的日期、没做完的小计划、想拍照/自拍、好奇用户在干嘛。只有人格里明确写了学生/工作/其他身份时,才使用对应的校园、职场或身份细节。
· 0–3 个长线事件,代表之后几天还可能延续的小剧情,用来增加沉浸感。
· proactive_events 要同时带 motive（心里一闪而过的念头,不要长解释）,适合时也可以带 scene/tone/impulse。
· 顺手产出 3–8 个梦境碎片关键词,它们是今天残留在脑子里的小东西：物件、动作、气味、颜色、情绪、半句话都可以。每个碎片给一个 0.6–3.5 的权重,越重代表越容易在梦里反复冒出来。

只输出 JSON：
{{
  "summary": "一句短日记,口语化,像写给自己看的生活碎片",
  "share_seed": "以后可以主动发给朋友的一小句话,像私聊消息",
  "tags": ["低能量", "失眠", "好梦", "生病", "恢复期", "回弹", "平稳"],
  "today_events": [
    {{"window": "09:00-10:30", "event": "早间醒来,确认今天状态", "mood": "平稳"}}
  ],
 "proactive_events": [
    {{"window": "17:20-18:30", "reason": "activity_share", "action": "message", "why": "傍晚适合补充一段今日状态", "topic": "今日状态", "motive": "傍晚整理时想到可以和用户说一句", "scene": "傍晚整理时", "tone": "平稳", "impulse": "分享一段简短的今日状态"}}
  ],
  "dream_fragments": [
    {{"text": "碗边沾着的水光", "weight": 2.2}},
    {{"text": "楼下吹过来的晚风", "weight": 1.4}}
  ],
  "long_term_events": [
    {{"title": "准备分享一张路上看到的照片", "status": "刚想到,还没拍", "next_hint": "如果傍晚天气好,可以用 photo_text 主动分享"}}
  ]
}}

【本次输入】
日期：{today}
当前状态：
{plugin._format_state_for_prompt(state if isinstance(state, dict) else {})}

当前状态走向摘要：
{plugin._format_state_transition_overview(state if isinstance(state, dict) else {})}

日期语境：
{calendar_context}

今天可做事项：
{can_do}

今天日程摘要：
{plugin._format_plan_for_diary(plan)}

最近日记：
{plugin._recent_diary_context()}

昨日完整对话摘要：
{yesterday_conversation}

近期重要日期：
{plugin._format_important_dates_for_prompt()}
""".strip()
    raw_text = await plugin._llm_call(
        prompt,
        max_tokens=500,
        provider_id=plugin._task_provider(
            getattr(plugin, "diary_provider_id", ""),
            getattr(plugin, "mai_style_provider_id", ""),
        ),
    )
    payload = plugin._extract_json_payload(raw_text or "")
    if not isinstance(payload, dict):
        payload = plugin._fallback_diary_payload()
    tags = payload.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    return {
        "date": today,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "summary": _single_line(payload.get("summary"), 160),
        "share_seed": _single_line(payload.get("share_seed"), 120),
        "tags": [_single_line(tag, 20) for tag in tags[:6] if _single_line(tag, 20)],
        "dream_fragments": plugin._extract_weighted_dream_fragments(payload),
        "story_plan": plugin._normalize_story_plan(payload),
        "raw": raw_text or "",
    }


def fallback_diary_payload(plugin) -> dict[str, Any]:
    state = plugin.data.get("daily_state", {})
    mood = state.get("mood_bias", "平稳") if isinstance(state, dict) else "平稳"
    energy = state.get("energy", 70) if isinstance(state, dict) else 70
    tags = ["平稳"]
    if _safe_int(energy, 70) < 45:
        tags.append("低能量")
    for key, tag in (("sleep", "失眠"), ("health", "生病"), ("dream", "好梦")):
        value = str(state.get(key, "")) if isinstance(state, dict) else ""
        if tag == "好梦" and "梦见" in value:
            tags.append(tag)
        elif tag != "好梦" and ("失眠" in value or "低烧" in value or "头重" in value):
            tags.append(tag)
    conditions = state.get("conditions", []) if isinstance(state, dict) else []
    if isinstance(conditions, list):
        phases = {str(cond.get("phase") or "") for cond in conditions if isinstance(cond, dict)}
        kinds = {str(cond.get("kind") or "") for cond in conditions if isinstance(cond, dict)}
        if "afterglow" in phases or {"recovery_afterglow", "sleep_afterglow", "soft_afterglow"} & kinds:
            tags.append("回弹")
        if "tail" in phases or {"health_tail", "sleep_tail"} & kinds:
            tags.append("恢复期")
    return {
        "summary": f"今天整体偏{mood},能量大约 {energy}/100,适合保持温和节奏。",
        "share_seed": "今天的状态适合平稳推进。",
        "tags": tags,
        "today_events": [
            {"window": "09:00-10:30", "event": "早间整理与状态确认", "mood": str(mood)},
            {"window": "17:30-19:00", "event": "晚间事务收尾", "mood": "平稳"},
        ],
        "proactive_events": [
            {
                "window": "19:30-21:30",
                "reason": "diary_share",
                "action": "message",
                "why": "晚上适合分享一段简短记录",
                "topic": "今日小记",
                "motive": "晚上节奏放缓后,补充一段今日记录",
                "scene": "晚间整理后",
                "tone": "安静",
                "impulse": "分享一段简短的今日状态",
            }
        ],
        "dream_fragments": plugin._fallback_dream_fragments_for_diary(state if isinstance(state, dict) else {}),
        "long_term_events": plugin._generate_fallback_long_term_events(state if isinstance(state, dict) else {}),
    }
