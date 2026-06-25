# -*- coding: utf-8 -*-

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

LEGACY_KEY_ALIASES: dict[str, tuple[str, ...]] = {
    "target_group_ids": ("group_whitelist_ids",),
    "timezone": ("environment_perception_timezone",),
    "enable_maintenance_token_saver": ("enable_daily_token_soft_limit",),
    "maintenance_token_soft_limit": ("daily_token_soft_limit",),
    "DIARY_PROVIDER_ID": ("DREAM_DIARY_PROVIDER_ID",),
    "DREAM_PROVIDER_ID": ("DREAM_DIARY_PROVIDER_ID",),
    "COMFYUI_PHOTO_WORKFLOW_NAME": ("COMFYUI_TEXT2IMG_WORKFLOW_NAME", "COMFYUI_SELFIE_WORKFLOW_NAME"),
    "allow_photo_text_action": ("enable_photo_text_action",),
    "allow_screen_peek_action": ("enable_screen_glance_action",),
    "allow_poke_action": ("enable_poke_action",),
    "allow_voice_action": ("enable_voice_action",),
    "creative_base_chars_per_hour": ("creative_chars_per_session",),
    "enable_hot_trend_sources": ("enable_news_daily_hot_read",),
    "hot_trend_sources": ("news_hot_sources",),
    "hot_trend_max_items": ("news_hot_max_items",),
    "enable_jm_cosmos_integration": ("enable_private_reading_integration",),
    "enable_jm_cosmos_boredom_read": ("enable_private_reading_boredom_read",),
    "jm_cosmos_min_interval_hours": ("private_reading_min_interval_hours",),
    "jm_cosmos_max_photo_count": ("private_reading_max_photo_count",),
    "jm_cosmos_share_probability": ("private_reading_share_probability",),
    "jm_cosmos_default_keywords": ("private_reading_default_keywords",),
    "jm_cosmos_blocked_tags": ("private_reading_blocked_tags",),
    "JM_COSMOS_VISION_PROVIDER_ID": ("PRIVATE_READING_VISION_PROVIDER_ID",),
}


def migrate_flat_config_into_schema_groups(
    config: Any,
    *,
    schema_path: Path,
    logger: Any | None = None,
) -> int:
    """Copy legacy flat config values into the new AstrBot schema groups."""
    try:
        return _migrate_flat_config_into_schema_groups(config, schema_path=schema_path, logger=logger)
    except Exception as exc:
        if logger is not None:
            logger.warning("[PrivateCompanion] 配置分组迁移失败，已跳过且不影响插件加载: %s", _single_line(exc, 160))
        return 0


def _migrate_flat_config_into_schema_groups(config: Any, *, schema_path: Path, logger: Any | None = None) -> int:
    root = _config_root_mapping(config)
    if not isinstance(root, dict):
        return 0
    schema_map = _schema_group_items(schema_path, logger=logger)
    if not schema_map:
        return 0

    changed: list[str] = []
    for key, item in schema_map.items():
        if key not in root:
            continue
        old_value = root.get(key)
        if old_value == item.get("default"):
            continue
        if _copy_into_schema_group(root, schema_map, key, old_value):
            changed.append(key)

    legacy_group = root.get("legacy_compat_config")
    legacy_sources = [root]
    if isinstance(legacy_group, dict):
        legacy_sources.append(legacy_group)
    for old_key, new_keys in LEGACY_KEY_ALIASES.items():
        for source in legacy_sources:
            if old_key not in source:
                continue
            old_value = source.get(old_key)
            if _is_empty(old_value):
                continue
            for new_key in new_keys:
                if _copy_into_schema_group(root, schema_map, new_key, old_value):
                    changed.append(f"{old_key}->{new_key}")

    if not changed:
        return 0
    if logger is not None:
        logger.info("[PrivateCompanion] 已将旧版扁平配置迁移到新版分组配置: %s 项", len(changed))
    _save_config_after_schema_migration(config, logger=logger)
    return len(changed)


def _config_root_mapping(config: Any) -> dict[str, Any] | None:
    if isinstance(config, dict):
        return config
    for attr in ("data", "config"):
        target = getattr(config, attr, None)
        if isinstance(target, dict):
            return target
    return None


def _copy_into_schema_group(root: dict[str, Any], schema_map: dict[str, dict[str, Any]], key: str, value: Any) -> bool:
    item = schema_map.get(key)
    if not item:
        return False
    default = item.get("default")
    value = _coerce_schema_value(value, item)
    if value == default:
        return False
    group_key = str(item.get("group") or "")
    group = root.get(group_key)
    if not isinstance(group, dict):
        group = {}
        root[group_key] = group
    group_value = group.get(key)
    should_copy = key not in group or group_value == default
    if not should_copy and _is_empty(group_value) and not _is_empty(value):
        should_copy = True
    if not should_copy:
        return False
    group[key] = value
    return True


def _schema_group_items(schema_path: Path, *, logger: Any | None = None) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    try:
        raw = json.loads(schema_path.read_text(encoding="utf-8"))
    except Exception as exc:
        if logger is not None:
            logger.debug("[PrivateCompanion] 读取配置 schema 用于分组迁移失败: %s", exc)
        return mapping
    if not isinstance(raw, dict):
        return mapping
    for group_key, group in raw.items():
        if not isinstance(group, dict) or group.get("type") != "object":
            continue
        items = group.get("items")
        if not isinstance(items, dict):
            continue
        for key, item in items.items():
            if isinstance(item, dict):
                copied = dict(item)
                copied["group"] = str(group_key)
                mapping[str(key)] = copied
    return mapping


def _coerce_schema_value(value: Any, item: dict[str, Any]) -> Any:
    item_type = str(item.get("type") or "")
    if item_type == "bool":
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"true", "1", "yes", "y", "on", "enable", "enabled", "启用", "开启", "开", "是"}:
                return True
            if text in {"false", "0", "no", "n", "off", "disable", "disabled", "停用", "关闭", "关", "否", ""}:
                return False
        return bool(value)
    if item_type == "int":
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return item.get("default")
    if item_type == "float":
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return item.get("default")
        slider = item.get("slider")
        if (
            isinstance(slider, dict)
            and float(slider.get("max", 0) or 0) <= 1.0
            and parsed > 1.0
            and ("probability" in str(item.get("description") or "").lower() or "概率" in str(item.get("description") or ""))
        ):
            parsed /= 100.0
        return parsed
    if item_type == "list":
        if isinstance(value, list):
            return value
        text = str(value or "").strip()
        if not text:
            return []
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("，", ",").replace("\n", ",")
        return [part.strip() for part in text.split(",") if part.strip()]
    if item_type in {"string", "text"}:
        return str(value or "")
    return value


def _save_config_after_schema_migration(config: Any, *, logger: Any | None = None) -> None:
    for method_name in ("save_config", "save", "save_conf"):
        save = getattr(config, method_name, None)
        if not callable(save):
            continue
        try:
            result = save()
            if asyncio.iscoroutine(result) or hasattr(result, "__await__"):
                try:
                    asyncio.get_running_loop().create_task(result)
                except RuntimeError:
                    close = getattr(result, "close", None)
                    if callable(close):
                        close()
                    if logger is not None:
                        logger.debug("[PrivateCompanion] 配置分组迁移已写入运行态，当前无事件循环可异步保存")
            return
        except TypeError:
            continue
        except Exception as exc:
            if logger is not None:
                logger.warning("[PrivateCompanion] 保存配置分组迁移结果失败: %s", _single_line(exc, 160))
            return


def _is_empty(value: Any) -> bool:
    return value in (None, "", [], {})


def _single_line(text: Any, limit: int = 80) -> str:
    return " ".join(str(text or "").split())[:limit]
