from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

import httpx
from django.utils import timezone as django_timezone

from .models import AIModel
from .selection import (
    NVIDIA_NIM_MODEL_ID,
    NVIDIA_NIM_PROVIDER,
    OPENROUTER_SHORTLIST_IDS,
    SHORTLIST_SORT_ORDER,
    TOOLS_TAG,
)

OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
AUTO_SORT_ORDER_START = 1000
EXCLUDED_MODEL_IDS = frozenset({"openrouter/free"})
_ZERO = Decimal("0")


@dataclass(frozen=True)
class OpenRouterModelRecord:
    model_id: str
    display_name: str
    description: str
    model_type: str
    context_window: int | None
    max_tokens: int | None
    tags: list[str]
    pricing: dict[str, Any]
    released_at: datetime | None


def fetch_openrouter_models(
    *,
    url: str = OPENROUTER_MODELS_URL,
    timeout: float = 20.0,
) -> list[OpenRouterModelRecord]:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
    payload = response.json()
    raw_models = payload.get("data", []) if isinstance(payload, dict) else []
    models: list[OpenRouterModelRecord] = []
    for item in raw_models:
        record = normalize_openrouter_model(item)
        if record is not None:
            models.append(record)
    models.sort(key=lambda model: (model.display_name.lower(), model.model_id))
    return models


def sync_openrouter_models(*, models: list[OpenRouterModelRecord]) -> dict[str, int]:
    now = django_timezone.now()
    seen_model_ids = {model.model_id for model in models}

    created = 0
    updated = 0
    unchanged = 0
    disabled = 0

    for index, remote in enumerate(models):
        if remote.model_id == NVIDIA_NIM_MODEL_ID:
            continue
        is_shortlist = remote.model_id in OPENROUTER_SHORTLIST_IDS
        sort_order = (
            SHORTLIST_SORT_ORDER[remote.model_id]
            if is_shortlist
            else AUTO_SORT_ORDER_START + index
        )
        obj = AIModel.objects.filter(model_id=remote.model_id).first()
        if obj is not None and obj.provider == NVIDIA_NIM_PROVIDER:
            continue
        if obj is None:
            AIModel.objects.create(
                provider="openrouter",
                model_id=remote.model_id,
                display_name=remote.display_name,
                description=remote.description,
                quality_tier="standard",
                cost_per_game=0,
                openrouter_managed=True,
                openrouter_available=True,
                model_type=remote.model_type,
                context_window=remote.context_window,
                max_tokens=remote.max_tokens,
                tags=remote.tags,
                pricing=remote.pricing,
                released_at=remote.released_at,
                last_synced_at=now,
                is_active=is_shortlist,
                sort_order=sort_order,
            )
            created += 1
            continue

        changed_fields: list[str] = []
        changed_fields.extend(_set_if_changed(obj, "provider", "openrouter"))
        changed_fields.extend(_set_if_changed(obj, "openrouter_available", True))
        changed_fields.extend(_set_if_changed(obj, "openrouter_managed", True))
        changed_fields.extend(_set_if_changed(obj, "model_type", remote.model_type))
        changed_fields.extend(_set_if_changed(obj, "context_window", remote.context_window))
        changed_fields.extend(_set_if_changed(obj, "max_tokens", remote.max_tokens))
        changed_fields.extend(_set_if_changed(obj, "tags", remote.tags))
        changed_fields.extend(_set_if_changed(obj, "pricing", remote.pricing))
        changed_fields.extend(_set_if_changed(obj, "released_at", remote.released_at))
        changed_fields.extend(_set_if_changed(obj, "last_synced_at", now))
        changed_fields.extend(_set_if_changed(obj, "is_active", is_shortlist))
        if is_shortlist:
            changed_fields.extend(_set_if_changed(obj, "cost_per_game", 0))
            changed_fields.extend(_set_if_changed(obj, "sort_order", sort_order))
        changed_fields.extend(_set_if_changed(obj, "display_name", remote.display_name))
        changed_fields.extend(_set_if_changed(obj, "description", remote.description))

        if changed_fields:
            obj.save(update_fields=changed_fields)
            updated += 1
        else:
            unchanged += 1

    missing = (
        AIModel.objects.filter(openrouter_managed=True)
        .exclude(model_id__in=seen_model_ids)
        .exclude(provider=NVIDIA_NIM_PROVIDER)
    )
    for obj in missing:
        changed_fields = _set_if_changed(obj, "openrouter_available", False)
        changed_fields.extend(_set_if_changed(obj, "is_active", False))
        changed_fields.extend(_set_if_changed(obj, "last_synced_at", now))
        if changed_fields:
            obj.save(update_fields=changed_fields)
            disabled += 1

    return {
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "disabled": disabled,
        "total_seen": len(models),
    }


def normalize_openrouter_model(item: Any) -> OpenRouterModelRecord | None:
    if not isinstance(item, dict):
        return None

    model_id = _as_non_empty_string(item.get("id"))
    if model_id is None or "/" not in model_id:
        return None
    if model_id == NVIDIA_NIM_MODEL_ID:
        return None
    if model_id in EXCLUDED_MODEL_IDS or not model_id.endswith(":free"):
        return None

    pricing = _normalize_pricing(item.get("pricing"))
    if not _is_numeric_zero(pricing.get("input")) or not _is_numeric_zero(pricing.get("output")):
        return None

    tags = _normalize_tags(item.get("supported_parameters"))
    if TOOLS_TAG not in tags:
        return None

    if not _has_text_output(item.get("architecture")):
        return None

    display_name = _as_non_empty_string(item.get("name")) or model_id
    description = _as_non_empty_string(item.get("description")) or ""
    top_provider = item.get("top_provider")
    max_tokens = None
    if isinstance(top_provider, dict):
        max_tokens = _as_optional_int(top_provider.get("max_completion_tokens"))

    return OpenRouterModelRecord(
        model_id=model_id,
        display_name=display_name,
        description=description,
        model_type="language",
        context_window=_as_optional_int(item.get("context_length")),
        max_tokens=max_tokens,
        tags=tags,
        pricing=pricing,
        released_at=_parse_unix_timestamp(item.get("created")),
    )


def _has_text_output(architecture: Any) -> bool:
    if not isinstance(architecture, dict):
        return False
    output_modalities = architecture.get("output_modalities")
    if output_modalities is None:
        output_modalities = architecture.get("output_modalities")
    if isinstance(output_modalities, list):
        return any(str(item).lower() == "text" for item in output_modalities)
    if isinstance(output_modalities, str) and "text" in output_modalities.lower():
        return True
    modality = architecture.get("modality")
    return isinstance(modality, str) and "text" in modality.lower()


def _normalize_tags(raw_tags: Any) -> list[str]:
    if not isinstance(raw_tags, list):
        return []
    result: list[str] = []
    for tag in raw_tags:
        if isinstance(tag, str) and tag not in result:
            result.append(tag)
    return result


def _normalize_pricing(raw_pricing: Any) -> dict[str, Any]:
    if not isinstance(raw_pricing, dict):
        return {}
    result: dict[str, Any] = {}
    prompt = raw_pricing.get("prompt", raw_pricing.get("input"))
    completion = raw_pricing.get("completion", raw_pricing.get("output"))
    if prompt is not None:
        result["input"] = prompt
    if completion is not None:
        result["output"] = completion
    cache_read = raw_pricing.get("input_cache_read", raw_pricing.get("cache_read"))
    cache_write = raw_pricing.get("input_cache_write", raw_pricing.get("cache_write"))
    if cache_read is not None:
        result["input_cache_read"] = cache_read
    if cache_write is not None:
        result["input_cache_write"] = cache_write
    return result


def _is_numeric_zero(value: Any) -> bool:
    parsed = _parse_decimal(value)
    return parsed is not None and parsed == _ZERO


def _parse_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _as_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _as_optional_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _parse_unix_timestamp(value: Any) -> datetime | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    return None


def _set_if_changed(obj: AIModel, field_name: str, value: Any) -> list[str]:
    if getattr(obj, field_name) == value:
        return []
    setattr(obj, field_name, value)
    return [field_name]
