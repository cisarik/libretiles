from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable, Mapping, Sequence

from django.conf import settings
from django.contrib.admin.models import CHANGE, LogEntry
from django.core import signing
from django.db import transaction
from django.db.models import F
from django.db.utils import OperationalError
from django.utils import timezone as django_timezone

from .models import AIModel, CatalogAdminControl
from .selection import TOOLS_TAG, get_selectable_models, select_models_from_rows

INT32_MIN = -2_147_483_648
INT32_MAX = 2_147_483_647
MAX_REVIEW_BATCH = 100
REVIEW_TOKEN_SALT = "catalog.admin.controls.review"
REVIEW_TOKEN_MAX_AGE_SECONDS = 600
LOCK_CONTENTION_MESSAGE = "The catalog is busy. Retry the review."
MISSING_CONTROL_MESSAGE = "Catalog coordination state is missing."
STALE_REVIEW_MESSAGE = "The catalog changed after review. Review the current values again."
EMPTY_FLAG_OFF_MESSAGE = (
    "This change would leave no selectable models with the dynamic catalog disabled."
)
EMPTY_FLAG_ON_MESSAGE = (
    "This change would leave no selectable models with the dynamic catalog enabled."
)
LAST_TOOLS_MESSAGE = "Keep at least one active language model with tool support."


class CatalogControlError(Exception):
    def __init__(self, message: str, *, status: int = 409) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass(frozen=True)
class CatalogChange:
    model_id: int
    is_active: bool
    sort_order: int


def acquire_catalog_write_lock() -> CatalogAdminControl:
    try:
        control = (
            CatalogAdminControl.objects.select_for_update().get(
                pk=CatalogAdminControl.SINGLETON_PK
            )
        )
    except CatalogAdminControl.DoesNotExist as exc:
        raise CatalogControlError(MISSING_CONTROL_MESSAGE) from exc
    CatalogAdminControl.objects.filter(pk=control.pk).update(revision=F("revision"))
    control.refresh_from_db()
    return control


def acquire_or_create_catalog_write_lock() -> CatalogAdminControl:
    CatalogAdminControl.objects.get_or_create(
        pk=CatalogAdminControl.SINGLETON_PK,
        defaults={"revision": 0, "ordering_reviewed": False},
    )
    return acquire_catalog_write_lock()


def ordering_reviewed() -> bool:
    control = CatalogAdminControl.objects.filter(pk=CatalogAdminControl.SINGLETON_PK).first()
    return bool(control is not None and control.ordering_reviewed)


def catalog_fingerprint(*, revision: int) -> str:
    rows = list(
        AIModel.objects.order_by("id").values(
            "id",
            "is_active",
            "sort_order",
            "provider",
            "model_id",
            "model_type",
            "tags",
            "openrouter_available",
            "openrouter_managed",
        )
    )
    payload = json.dumps(
        {"revision": revision, "rows": rows},
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_review_changes(payload: Mapping[str, Any]) -> list[CatalogChange]:
    raw_ids = payload.get("id")
    if raw_ids is None:
        raw_ids = payload.get("ids")
    if isinstance(raw_ids, str) or isinstance(raw_ids, bytes):
        raise CatalogControlError("Review contained malformed identifiers.", status=400)
    if raw_ids is None:
        ids = _collect_formset_ids(payload)
    else:
        if not isinstance(raw_ids, (list, tuple)):
            raw_ids = [raw_ids]
        ids = [_parse_model_pk(value) for value in raw_ids]
    if not ids:
        raise CatalogControlError("Review contained no catalog rows.", status=400)
    if len(ids) > MAX_REVIEW_BATCH:
        raise CatalogControlError("Review exceeded the 100-row batch limit.", status=400)
    if len(ids) != len(set(ids)):
        raise CatalogControlError("Review contained duplicate catalog rows.", status=400)

    changes: list[CatalogChange] = []
    for pk in ids:
        changes.append(
            CatalogChange(
                model_id=pk,
                is_active=_parse_bool(payload, pk, "is_active"),
                sort_order=_parse_sort_order(payload, pk),
            )
        )
    return changes


def preview_review(
    changes: Sequence[CatalogChange],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    rows = list(AIModel.objects.all())
    by_id = {model.pk: model for model in rows}
    unknown = [change.model_id for change in changes if change.model_id not in by_id]
    if unknown:
        raise CatalogControlError("Review contained unknown catalog rows.", status=400)
    captured = now or django_timezone.now()
    current_off = select_models_from_rows(
        rows,
        dynamic_enabled=False,
        ordering_reviewed=ordering_reviewed(),
        now=captured,
    )
    current_on = select_models_from_rows(
        rows,
        dynamic_enabled=True,
        ordering_reviewed=ordering_reviewed(),
        now=captured,
    )
    proposed_rows = list(AIModel.objects.all())
    proposed = _apply_changes_in_memory(proposed_rows, changes)
    flag_off = select_models_from_rows(
        proposed,
        dynamic_enabled=False,
        ordering_reviewed=True,
        now=captured,
    )
    flag_on = select_models_from_rows(
        proposed,
        dynamic_enabled=True,
        ordering_reviewed=True,
        now=captured,
    )
    return {
        "changes": changes,
        "current_flag_off": current_off,
        "current_flag_on": current_on,
        "proposed_flag_off": flag_off,
        "proposed_flag_on": flag_on,
        "current_flagship_off": current_off[0] if current_off else None,
        "current_flagship_on": current_on[0] if current_on else None,
        "proposed_flagship_off": flag_off[0] if flag_off else None,
        "proposed_flagship_on": flag_on[0] if flag_on else None,
    }


def sign_review_token(
    *,
    actor_id: int,
    revision: int,
    dynamic_enabled: bool,
    changes: Sequence[CatalogChange],
) -> str:
    payload = {
        "actor_id": actor_id,
        "revision": revision,
        "dynamic_enabled": dynamic_enabled,
        "fingerprint": catalog_fingerprint(revision=revision),
        "changes": [
            {
                "id": change.model_id,
                "is_active": change.is_active,
                "sort_order": change.sort_order,
            }
            for change in changes
        ],
    }
    return signing.dumps(payload, salt=REVIEW_TOKEN_SALT)


def load_review_token(token: str) -> dict[str, Any]:
    try:
        payload = signing.loads(
            token,
            salt=REVIEW_TOKEN_SALT,
            max_age=REVIEW_TOKEN_MAX_AGE_SECONDS,
        )
    except signing.SignatureExpired as exc:
        raise CatalogControlError(STALE_REVIEW_MESSAGE) from exc
    except signing.BadSignature as exc:
        raise CatalogControlError(STALE_REVIEW_MESSAGE) from exc
    if not isinstance(payload, dict):
        raise CatalogControlError(STALE_REVIEW_MESSAGE)
    return payload


def apply_reviewed_token(
    *,
    token: str,
    actor_id: int,
    has_row_change_permission: bool,
) -> list[AIModel]:
    payload = load_review_token(token)
    if payload.get("actor_id") != actor_id:
        raise CatalogControlError(STALE_REVIEW_MESSAGE)
    raw_changes = payload.get("changes")
    if not isinstance(raw_changes, list):
        raise CatalogControlError(STALE_REVIEW_MESSAGE)
    changes = [
        CatalogChange(
            model_id=int(item["id"]),
            is_active=bool(item["is_active"]),
            sort_order=int(item["sort_order"]),
        )
        for item in raw_changes
        if isinstance(item, dict)
    ]
    if len(changes) != len(raw_changes):
        raise CatalogControlError(STALE_REVIEW_MESSAGE)
    return apply_reviewed_changes(
        changes,
        actor_id=actor_id,
        expected_revision=int(payload["revision"]),
        expected_fingerprint=str(payload["fingerprint"]),
        has_row_change_permission=has_row_change_permission,
    )


def apply_reviewed_changes(
    changes: Sequence[CatalogChange],
    *,
    actor_id: int,
    expected_revision: int,
    expected_fingerprint: str,
    has_row_change_permission: bool,
) -> list[AIModel]:
    if not has_row_change_permission:
        raise CatalogControlError("Missing catalog change permission.", status=403)
    try:
        with transaction.atomic():
            control = acquire_catalog_write_lock()
            if control.revision != expected_revision:
                raise CatalogControlError(STALE_REVIEW_MESSAGE)
            fingerprint = catalog_fingerprint(revision=control.revision)
            if fingerprint != expected_fingerprint:
                raise CatalogControlError(STALE_REVIEW_MESSAGE)
            locked_rows = list(AIModel.objects.select_for_update().order_by("pk"))
            by_id = {model.pk: model for model in locked_rows}
            unknown = [change.model_id for change in changes if change.model_id not in by_id]
            if unknown:
                raise CatalogControlError("Review contained unknown catalog rows.", status=400)
            mutated: list[AIModel] = []
            for change in changes:
                model = by_id[change.model_id]
                if model.is_active == change.is_active and model.sort_order == change.sort_order:
                    continue
                model.is_active = change.is_active
                model.sort_order = change.sort_order
                model.save(update_fields=["is_active", "sort_order", "updated_at"])
                mutated.append(model)
            refreshed = list(AIModel.objects.order_by("pk"))
            validate_catalog_invariants(refreshed, now=django_timezone.now())
            control.ordering_reviewed = True
            control.revision = control.revision + 1
            control.save(update_fields=["ordering_reviewed", "revision"])
            if not get_selectable_models():
                if bool(getattr(settings, "DYNAMIC_FREE_MODEL_CATALOG_ENABLED", False)):
                    raise CatalogControlError(EMPTY_FLAG_ON_MESSAGE)
                raise CatalogControlError(EMPTY_FLAG_OFF_MESSAGE)
            _write_audit_entries(actor_id=actor_id, models=mutated)
            return mutated
    except OperationalError as exc:
        raise CatalogControlError(LOCK_CONTENTION_MESSAGE) from exc


def validate_catalog_invariants(
    rows: Sequence[AIModel],
    *,
    now: datetime,
) -> None:
    tools_active = [
        model
        for model in rows
        if model.is_active
        and model.model_type == "language"
        and _has_tools_tag(model)
    ]
    if not tools_active:
        raise CatalogControlError(LAST_TOOLS_MESSAGE)
    flag_off = select_models_from_rows(
        rows,
        dynamic_enabled=False,
        ordering_reviewed=True,
        now=now,
    )
    if not flag_off:
        raise CatalogControlError(EMPTY_FLAG_OFF_MESSAGE)
    flag_on = select_models_from_rows(
        rows,
        dynamic_enabled=True,
        ordering_reviewed=True,
        now=now,
    )
    if not flag_on:
        raise CatalogControlError(EMPTY_FLAG_ON_MESSAGE)


def bump_catalog_revision_locked() -> CatalogAdminControl:
    control = acquire_or_create_catalog_write_lock()
    control.revision = control.revision + 1
    control.save(update_fields=["revision"])
    return control


def _apply_changes_in_memory(
    rows: Sequence[AIModel],
    changes: Sequence[CatalogChange],
) -> list[AIModel]:
    by_id = {model.pk: model for model in rows}
    for change in changes:
        model = by_id[change.model_id]
        model.is_active = change.is_active
        model.sort_order = change.sort_order
    return list(by_id.values())


def _write_audit_entries(*, actor_id: int, models: Iterable[AIModel]) -> None:
    rows = list(models)
    if not rows:
        return
    LogEntry.objects.log_actions(
        user_id=actor_id,
        queryset=rows,
        action_flag=CHANGE,
        change_message="Reviewed catalog activation and fallback order.",
    )


def _has_tools_tag(model: AIModel) -> bool:
    tags = model.tags if isinstance(model.tags, list) else []
    return TOOLS_TAG in tags


def _collect_formset_ids(payload: Mapping[str, Any]) -> list[int]:
    ids: list[int] = []
    total = payload.get("form-TOTAL_FORMS")
    if total is None:
        return ids
    try:
        count = int(total)
    except (TypeError, ValueError) as exc:
        raise CatalogControlError("Review contained a malformed formset.", status=400) from exc
    if count > MAX_REVIEW_BATCH:
        raise CatalogControlError("Review exceeded the 100-row batch limit.", status=400)
    for index in range(count):
        ids.append(_parse_model_pk(payload.get(f"form-{index}-id")))
    return ids


def _parse_model_pk(value: Any) -> int:
    try:
        pk = int(value)
    except (TypeError, ValueError) as exc:
        raise CatalogControlError("Review contained malformed identifiers.", status=400) from exc
    if pk <= 0:
        raise CatalogControlError("Review contained malformed identifiers.", status=400)
    return pk


def _parse_bool(payload: Mapping[str, Any], pk: int, field: str) -> bool:
    raw = payload.get(f"{field}_{pk}", payload.get(f"row-{pk}-{field}"))
    if raw is None:
        raw = payload.get(f"form-{_form_index(payload, pk)}-{field}")
    if isinstance(raw, bool):
        return raw
    if raw is None or raw == "":
        return False
    if not isinstance(raw, str):
        raise CatalogControlError("Review contained a malformed boolean.", status=400)
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "on", "yes"}:
        return True
    if normalized in {"0", "false", "off", "no"}:
        return False
    raise CatalogControlError("Review contained a malformed boolean.", status=400)


def _parse_sort_order(payload: Mapping[str, Any], pk: int) -> int:
    raw = payload.get(f"sort_order_{pk}", payload.get(f"row-{pk}-sort_order"))
    if raw is None:
        raw = payload.get(f"form-{_form_index(payload, pk)}-sort_order")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise CatalogControlError("Review contained a malformed sort order.", status=400) from exc
    if value < INT32_MIN or value > INT32_MAX:
        raise CatalogControlError("Review contained a sort order outside integer bounds.", status=400)
    return value


def _form_index(payload: Mapping[str, Any], pk: int) -> int:
    total = payload.get("form-TOTAL_FORMS")
    if total is None:
        return 0
    try:
        count = int(total)
    except (TypeError, ValueError):
        return 0
    for index in range(count):
        raw = payload.get(f"form-{index}-id")
        if raw is None:
            continue
        try:
            if int(str(raw)) == pk:
                return index
        except (TypeError, ValueError):
            continue
    return 0
