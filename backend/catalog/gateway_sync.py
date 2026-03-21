from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from django.utils import timezone as django_timezone

from .models import AIModel

GATEWAY_MODELS_URL = "https://ai-gateway.vercel.sh/v1/models"
AUTO_SORT_ORDER_START = 1000


@dataclass(frozen=True)
class GatewayModelRecord:
    model_id: str
    provider: str
    display_name: str
    description: str
    model_type: str
    context_window: int | None
    max_tokens: int | None
    tags: list[str]
    pricing: dict[str, Any]
    released_at: datetime | None


def fetch_gateway_models(
    *,
    url: str = GATEWAY_MODELS_URL,
    timeout: float = 20.0,
) -> list[GatewayModelRecord]:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
    payload = response.json()

    raw_models = payload.get("data", []) if isinstance(payload, dict) else []
    models: list[GatewayModelRecord] = []
    for item in raw_models:
        record = _normalize_gateway_model(item)
        if record is not None and record.model_type == "language":
            models.append(record)

    models.sort(key=lambda model: (model.provider, model.display_name.lower(), model.model_id))
    return models


def sync_gateway_models(
    *,
    models: list[GatewayModelRecord],
    activate_new: bool = False,
) -> dict[str, int]:
    now = django_timezone.now()
    seen_model_ids = {model.model_id for model in models}

    created = 0
    updated = 0
    unchanged = 0
    disabled = 0

    for index, remote in enumerate(models):
        obj = AIModel.objects.filter(model_id=remote.model_id).first()
        if obj is None:
            AIModel.objects.create(
                provider=remote.provider,
                model_id=remote.model_id,
                display_name=remote.display_name,
                description=remote.description,
                quality_tier="standard",
                cost_per_game=0,
                gateway_managed=True,
                gateway_available=True,
                model_type=remote.model_type,
                context_window=remote.context_window,
                max_tokens=remote.max_tokens,
                tags=remote.tags,
                pricing=remote.pricing,
                released_at=remote.released_at,
                last_synced_at=now,
                is_active=activate_new,
                sort_order=AUTO_SORT_ORDER_START + index,
            )
            created += 1
            continue

        changed_fields: list[str] = []
        changed_fields.extend(_set_if_changed(obj, "provider", remote.provider))
        changed_fields.extend(_set_if_changed(obj, "gateway_available", True))
        changed_fields.extend(_set_if_changed(obj, "model_type", remote.model_type))
        changed_fields.extend(_set_if_changed(obj, "context_window", remote.context_window))
        changed_fields.extend(_set_if_changed(obj, "max_tokens", remote.max_tokens))
        changed_fields.extend(_set_if_changed(obj, "tags", remote.tags))
        changed_fields.extend(_set_if_changed(obj, "pricing", remote.pricing))
        changed_fields.extend(_set_if_changed(obj, "released_at", remote.released_at))
        changed_fields.extend(_set_if_changed(obj, "last_synced_at", now))

        if obj.gateway_managed:
            changed_fields.extend(_set_if_changed(obj, "display_name", remote.display_name))
            changed_fields.extend(_set_if_changed(obj, "description", remote.description))

        if changed_fields:
            obj.save(update_fields=changed_fields)
            updated += 1
        else:
            unchanged += 1

    missing = AIModel.objects.exclude(model_id__in=seen_model_ids)
    for obj in missing:
        changed_fields = _set_if_changed(obj, "gateway_available", False)
        changed_fields.extend(_set_if_changed(obj, "last_synced_at", now))
        if obj.gateway_managed:
            changed_fields.extend(_set_if_changed(obj, "is_active", False))
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


def _normalize_gateway_model(item: Any) -> GatewayModelRecord | None:
    if not isinstance(item, dict):
        return None

    model_id = _as_non_empty_string(item.get("id"))
    if model_id is None or "/" not in model_id:
        return None

    display_name = _as_non_empty_string(item.get("name")) or model_id
    provider = model_id.split("/", 1)[0]
    description = _as_non_empty_string(item.get("description")) or ""
    model_type = _as_non_empty_string(item.get("type")) or "language"
    context_window = _as_optional_int(item.get("context_window"))
    max_tokens = _as_optional_int(item.get("max_tokens"))
    tags = _normalize_tags(item.get("tags"))
    pricing = _normalize_pricing(item.get("pricing"))
    released_at = _parse_unix_timestamp(item.get("released"))

    return GatewayModelRecord(
        model_id=model_id,
        provider=provider,
        display_name=display_name,
        description=description,
        model_type=model_type,
        context_window=context_window,
        max_tokens=max_tokens,
        tags=tags,
        pricing=pricing,
        released_at=released_at,
    )


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
    return {str(key): value for key, value in raw_pricing.items()}


def _as_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


def _as_optional_int(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    return None


def _parse_unix_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, int):
        return None
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _set_if_changed(obj: AIModel, field_name: str, value: Any) -> list[str]:
    if getattr(obj, field_name) == value:
        return []
    setattr(obj, field_name, value)
    return [field_name]
