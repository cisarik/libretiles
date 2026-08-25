from datetime import datetime, timezone
from io import StringIO
from typing import Any
from unittest.mock import patch

from django.core.management import call_command, load_command_class
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone as django_timezone
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import AIModel
from catalog.openrouter_sync import (
    CatalogSyncAborted,
    OpenRouterModelRecord,
    normalize_openrouter_model,
    sync_openrouter_models,
)
from catalog.selection import (
    DEFAULT_FREE_MODEL_ID,
    FREE_RIVAL_IDS,
    FREE_RIVAL_PAIRS,
    NVIDIA_NIM_MODEL_ID,
    NVIDIA_NIM_PROVIDER,
    OPENROUTER_PROVIDER,
    get_selectable_models,
    is_selectable_model,
)
from game.models import GameSession


def _unix(dt: datetime) -> int:
    return int(dt.replace(tzinfo=timezone.utc).timestamp()) if dt.tzinfo is None else int(dt.timestamp())


def _eligible_payload_item(
    model_id: str,
    *,
    created: int | None = None,
    pricing: dict[str, Any] | None = None,
    supported_parameters: list[str] | None = None,
    architecture: dict[str, Any] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "id": model_id,
        "name": model_id,
        "description": "fixture",
        "pricing": pricing if pricing is not None else {"prompt": "0", "completion": "0"},
        "supported_parameters": (
            supported_parameters if supported_parameters is not None else ["tools"]
        ),
        "architecture": architecture if architecture is not None else {"output_modalities": ["text"]},
        "context_length": 8192,
    }
    if created is not None:
        item["created"] = created
    item.update(overrides)
    return item


def _httpx_client_returning(payload: dict[str, Any]) -> type:
    class DummyResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return payload

    class DummyClient:
        calls = 0

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            return None

        def __enter__(self) -> Any:
            return self

        def __exit__(self, *args: Any) -> bool:
            return False

        def get(self, url: str) -> DummyResponse:
            DummyClient.calls += 1
            return DummyResponse()

    return DummyClient


def _make_openrouter(
    model_id: str,
    *,
    released_at: datetime | None = None,
    is_active: bool = True,
    openrouter_available: bool = True,
    openrouter_managed: bool = True,
    **overrides: Any,
) -> AIModel:
    defaults: dict[str, Any] = {
        "provider": OPENROUTER_PROVIDER,
        "model_id": model_id,
        "display_name": model_id,
        "openrouter_available": openrouter_available,
        "openrouter_managed": openrouter_managed,
        "is_active": is_active,
        "model_type": "language",
        "tags": ["tools"],
        "released_at": released_at,
    }
    defaults.update(overrides)
    return AIModel.objects.create(**defaults)


def _make_nim(*, is_active: bool = True, **overrides: Any) -> AIModel:
    defaults: dict[str, Any] = {
        "provider": NVIDIA_NIM_PROVIDER,
        "model_id": NVIDIA_NIM_MODEL_ID,
        "display_name": "Nemotron NIM",
        "openrouter_available": False,
        "openrouter_managed": False,
        "is_active": is_active,
        "model_type": "language",
        "tags": ["tools"],
        "released_at": None,
        "sort_order": 20,
    }
    defaults.update(overrides)
    return AIModel.objects.create(**defaults)


class NormalizeOpenRouterModelTests(SimpleTestCase):
    def test_rejects_paid_malformed_non_tool_non_text_and_excluded_ids(self) -> None:
        created = _unix(datetime(2026, 1, 1, tzinfo=timezone.utc))
        cases: list[tuple[str, dict[str, Any]]] = [
            ("paid", _eligible_payload_item("vendor/paid:free", pricing={"prompt": "1", "completion": "0"})),
            (
                "malformed-pricing",
                _eligible_payload_item("vendor/ok:free", pricing={"prompt": "0"}),
            ),
            ("no-tools", _eligible_payload_item("vendor/ok:free", supported_parameters=["temperature"])),
            (
                "non-text",
                _eligible_payload_item(
                    "vendor/ok:free",
                    architecture={"output_modalities": ["image"]},
                ),
            ),
            ("excluded", _eligible_payload_item("openrouter/free")),
            ("not-free-suffix", _eligible_payload_item("vendor/paid-model")),
            ("no-slash", {"id": "nocolonfree", "pricing": {"prompt": "0", "completion": "0"}}),
            ("nim-id", _eligible_payload_item(NVIDIA_NIM_MODEL_ID)),
        ]
        for label, item in cases:
            assert normalize_openrouter_model(item) is None, label
        ok = normalize_openrouter_model(_eligible_payload_item("vendor/ok:free", created=created))
        assert ok is not None
        assert ok.model_id == "vendor/ok:free"
        assert ok.released_at is not None

    def test_future_timestamp_is_treated_as_missing(self) -> None:
        future = _unix(datetime(2099, 6, 1, tzinfo=timezone.utc))
        record = normalize_openrouter_model(_eligible_payload_item("vendor/ok:free", created=future))
        assert record is not None
        assert record.released_at is None


class DynamicCatalogSelectionTests(TestCase):
    def test_flag_off_matches_bootstrap_pairs(self) -> None:
        for model_id in FREE_RIVAL_IDS:
            if model_id == NVIDIA_NIM_MODEL_ID:
                _make_nim()
            else:
                _make_openrouter(model_id)
        extra = _make_openrouter(
            "meta-llama/llama-3.3-70b-instruct:free",
            released_at=django_timezone.now(),
        )
        selected = get_selectable_models()
        assert [(model.provider, model.model_id) for model in selected] == list(FREE_RIVAL_PAIRS)
        assert extra.model_id not in {model.model_id for model in selected}

        resp = self.client.get("/api/catalog/models/")
        payload = resp.json()
        assert [item["model_id"] for item in payload] == list(FREE_RIVAL_IDS)
        assert payload[0]["is_flagship"] is True
        assert payload[0]["recommended"] is True
        assert sum(1 for item in payload if item["is_flagship"]) == 1
        assert sum(1 for item in payload if item["recommended"]) == 1
        assert "released_at" in payload[0]
        money_keys = {
            "cost_per_game",
            "pricing",
            "input_cost_per_million",
            "output_cost_per_million",
        }
        for item in payload:
            assert money_keys.isdisjoint(item)

    @override_settings(DYNAMIC_FREE_MODEL_CATALOG_ENABLED=True)
    def test_flag_on_orders_newest_openrouter_then_nim_last(self) -> None:
        t1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        t2 = datetime(2026, 2, 1, tzinfo=timezone.utc)
        t3 = datetime(2026, 3, 1, tzinfo=timezone.utc)
        t4 = datetime(2026, 4, 1, tzinfo=timezone.utc)
        t5 = datetime(2026, 5, 1, tzinfo=timezone.utc)
        _make_openrouter("vendor/old-a:free", released_at=t1)
        _make_openrouter("vendor/old-b:free", released_at=t2)
        third = _make_openrouter("vendor/mid:free", released_at=t3)
        second = _make_openrouter("vendor/newer:free", released_at=t4)
        newest = _make_openrouter("vendor/newest:free", released_at=t5)
        killed = _make_openrouter("vendor/killed-newest:free", released_at=datetime(2026, 6, 1, tzinfo=timezone.utc), is_active=False)
        missing = _make_openrouter("vendor/missing-ts:free", released_at=None)
        future = _make_openrouter(
            "vendor/future:free",
            released_at=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )
        tied_b = _make_openrouter("vendor/tied-b:free", released_at=t3)
        _make_nim()

        selected = get_selectable_models()
        ids = [model.model_id for model in selected]
        assert ids[:4] == [
            newest.model_id,
            second.model_id,
            "vendor/mid:free",
            "vendor/tied-b:free",
        ]
        assert "vendor/old-a:free" not in ids
        assert "vendor/old-b:free" not in ids
        assert ids[-1] == NVIDIA_NIM_MODEL_ID
        assert killed.model_id not in ids
        assert missing.model_id not in ids
        assert future.model_id not in ids
        assert third.model_id in ids
        assert tied_b.model_id in ids
        # Tied t3 rows: mid before tied-b by model_id because neither is bootstrap.
        assert ids.index("vendor/mid:free") < ids.index("vendor/tied-b:free")

        resp = self.client.get("/api/catalog/models/")
        payload = resp.json()
        assert [item["model_id"] for item in payload] == ids
        assert payload[0]["is_flagship"] is True
        assert payload[0]["recommended"] is True
        assert payload[0]["model_id"] == newest.model_id
        assert sum(1 for item in payload if item["is_flagship"]) == 1
        assert payload[-1]["model_id"] == NVIDIA_NIM_MODEL_ID
        assert payload[0]["released_at"] is not None
        assert payload[-1]["released_at"] is None

    @override_settings(DYNAMIC_FREE_MODEL_CATALOG_ENABLED=True)
    def test_kill_switch_fills_next_openrouter_row(self) -> None:
        for index, day in enumerate((1, 2, 3, 4, 5)):
            _make_openrouter(
                f"vendor/slot-{day}:free",
                released_at=datetime(2026, 1, day, tzinfo=timezone.utc),
                is_active=index != 4,
            )
        newest_killed = AIModel.objects.get(model_id="vendor/slot-5:free")
        newest_killed.is_active = False
        newest_killed.save(update_fields=["is_active"])
        ids = [model.model_id for model in get_selectable_models()]
        assert ids == [
            "vendor/slot-4:free",
            "vendor/slot-3:free",
            "vendor/slot-2:free",
            "vendor/slot-1:free",
        ]
        assert "vendor/slot-5:free" not in ids

    @override_settings(DYNAMIC_FREE_MODEL_CATALOG_ENABLED=True)
    def test_unavailable_and_unmanaged_rows_are_excluded_while_inactive_nim_is_omitted(
        self,
    ) -> None:
        _make_openrouter(
            "vendor/available:free",
            released_at=datetime(2026, 4, 1, tzinfo=timezone.utc),
        )
        _make_openrouter(
            "vendor/unavailable:free",
            released_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            openrouter_available=False,
        )
        _make_openrouter(
            "vendor/unmanaged:free",
            released_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            openrouter_managed=False,
        )
        _make_nim(is_active=False)
        ids = [model.model_id for model in get_selectable_models()]
        assert ids == ["vendor/available:free"]
        assert NVIDIA_NIM_MODEL_ID not in ids

    @override_settings(DYNAMIC_FREE_MODEL_CATALOG_ENABLED=True)
    def test_bootstrap_sort_breaks_ties_before_model_id(self) -> None:
        same = datetime(2026, 3, 1, tzinfo=timezone.utc)
        _make_openrouter(DEFAULT_FREE_MODEL_ID, released_at=same)
        _make_openrouter("google/gemma-4-26b-a4b-it:free", released_at=same)
        ids = [model.model_id for model in get_selectable_models()]
        assert ids[0] == DEFAULT_FREE_MODEL_ID
        assert ids[1] == "google/gemma-4-26b-a4b-it:free"

    def test_seed_models_preserves_admin_is_active(self) -> None:
        call_command("seed_models", stdout=StringIO())
        gemma = AIModel.objects.get(model_id=DEFAULT_FREE_MODEL_ID)
        nim = AIModel.objects.get(model_id=NVIDIA_NIM_MODEL_ID)
        gemma.is_active = False
        nim.is_active = False
        gemma.save(update_fields=["is_active"])
        nim.save(update_fields=["is_active"])
        call_command("seed_models", stdout=StringIO())
        gemma.refresh_from_db()
        nim.refresh_from_db()
        assert gemma.is_active is False
        assert nim.is_active is False
        assert is_selectable_model(DEFAULT_FREE_MODEL_ID) is False
        assert is_selectable_model(NVIDIA_NIM_MODEL_ID) is False


class DynamicCatalogSyncGuardTests(TestCase):
    def _available_fixture(self, count: int) -> list[AIModel]:
        rows = []
        for index in range(count):
            rows.append(
                _make_openrouter(
                    f"vendor/existing-{index}:free",
                    openrouter_available=True,
                    openrouter_managed=True,
                    is_active=index != 0,
                )
            )
        return rows

    def test_sync_does_not_reactivate_or_deactivate_existing_rows(self) -> None:
        killed = _make_openrouter(DEFAULT_FREE_MODEL_ID, is_active=False)
        extra_id = "vendor/new-eligible:free"
        sync_openrouter_models(
            models=[
                OpenRouterModelRecord(
                    model_id=DEFAULT_FREE_MODEL_ID,
                    display_name="Gemma",
                    description="shortlist",
                    model_type="language",
                    context_window=131072,
                    max_tokens=None,
                    tags=["tools"],
                    released_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
                OpenRouterModelRecord(
                    model_id=extra_id,
                    display_name="New",
                    description="new",
                    model_type="language",
                    context_window=8192,
                    max_tokens=None,
                    tags=["tools"],
                    released_at=datetime(2026, 2, 1, tzinfo=timezone.utc),
                ),
            ]
        )
        killed.refresh_from_db()
        extra = AIModel.objects.get(model_id=extra_id)
        assert killed.is_active is False
        assert extra.is_active is True

    def test_large_drop_aborts_with_zero_writes(self) -> None:
        existing = self._available_fixture(10)
        snapshot = [
            (row.pk, row.is_active, row.openrouter_available, row.last_synced_at)
            for row in existing
        ]
        incoming = [
            OpenRouterModelRecord(
                model_id=f"vendor/new-{index}:free",
                display_name=f"New {index}",
                description="",
                model_type="language",
                context_window=8192,
                max_tokens=None,
                tags=["tools"],
                released_at=None,
            )
            for index in range(4)
        ]
        with self.assertRaises(CatalogSyncAborted) as raised:
            sync_openrouter_models(models=incoming)
        assert raised.exception.reason == "large-drop"
        assert raised.exception.previous_count == 10
        assert raised.exception.new_count == 4
        assert not AIModel.objects.filter(model_id__startswith="vendor/new-").exists()
        for pk, is_active, available, last_synced_at in snapshot:
            row = AIModel.objects.get(pk=pk)
            assert row.is_active is is_active
            assert row.openrouter_available is available
            assert row.last_synced_at == last_synced_at

    def test_allow_large_drop_writes_after_guard_would_abort(self) -> None:
        self._available_fixture(10)
        incoming = [
            OpenRouterModelRecord(
                model_id="vendor/kept:free",
                display_name="Kept",
                description="",
                model_type="language",
                context_window=8192,
                max_tokens=None,
                tags=["tools"],
                released_at=None,
            )
        ]
        stats = sync_openrouter_models(models=incoming, allow_large_drop=True)
        assert stats["created"] == 1
        kept = AIModel.objects.get(model_id="vendor/kept:free")
        assert kept.is_active is True
        dropped = AIModel.objects.get(model_id="vendor/existing-1:free")
        assert dropped.openrouter_available is False
        assert dropped.is_active is True

    def test_empty_cohort_aborts_even_with_allow_large_drop(self) -> None:
        existing = self._available_fixture(3)
        last_synced = existing[0].last_synced_at
        for allow in (False, True):
            with self.assertRaises(CatalogSyncAborted) as raised:
                sync_openrouter_models(models=[], allow_large_drop=allow)
            assert raised.exception.reason == "empty-cohort"
        for row in existing:
            row.refresh_from_db()
            assert row.openrouter_available is True
            assert row.last_synced_at == last_synced

    def test_exact_fifty_percent_drop_is_allowed(self) -> None:
        self._available_fixture(10)
        incoming = [
            OpenRouterModelRecord(
                model_id=f"vendor/half-{index}:free",
                display_name=f"Half {index}",
                description="",
                model_type="language",
                context_window=8192,
                max_tokens=None,
                tags=["tools"],
                released_at=None,
            )
            for index in range(5)
        ]
        stats = sync_openrouter_models(models=incoming)
        assert stats["created"] == 5

    def test_command_large_drop_and_allow_flag(self) -> None:
        self._available_fixture(10)
        payload = {"data": [_eligible_payload_item("vendor/only:free")]}
        dummy = _httpx_client_returning(payload)
        stdout = StringIO()
        with patch("catalog.openrouter_sync.httpx.Client", dummy):
            with self.assertRaises(CommandError):
                call_command("sync_openrouter_models", stdout=stdout)
        assert dummy.calls == 1
        assert not AIModel.objects.filter(model_id="vendor/only:free").exists()

        dummy.calls = 0
        with patch("catalog.openrouter_sync.httpx.Client", dummy):
            call_command("sync_openrouter_models", allow_large_drop=True, stdout=stdout)
        assert dummy.calls == 1
        assert AIModel.objects.filter(model_id="vendor/only:free").exists()

        command = load_command_class("catalog", "sync_openrouter_models")
        parser = command.create_parser("manage.py", "sync_openrouter_models")
        help_text = parser.format_help()
        assert "--allow-large-drop" in help_text

    def test_command_performs_one_catalog_get(self) -> None:
        payload = {
            "data": [
                _eligible_payload_item(DEFAULT_FREE_MODEL_ID, created=_unix(datetime(2026, 1, 1))),
            ]
        }
        dummy = _httpx_client_returning(payload)
        with patch("catalog.openrouter_sync.httpx.Client", dummy):
            call_command("sync_openrouter_models", stdout=StringIO())
        assert dummy.calls == 1


class DynamicCatalogDefaultModelTests(TestCase):
    @override_settings(DYNAMIC_FREE_MODEL_CATALOG_ENABLED=True)
    def test_create_game_without_preference_uses_newest_row(self) -> None:
        newest = _make_openrouter(
            "vendor/newest:free",
            released_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )
        _make_openrouter(
            DEFAULT_FREE_MODEL_ID,
            released_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        _make_nim()
        user = User.objects.create_user(username="player1", password="pass1234")
        client = APIClient()
        client.force_authenticate(user=user)
        resp = client.post("/api/game/create/", {"game_mode": "vs_ai"})
        assert resp.status_code == 201
        assert resp.json()["ai_model_id"] == newest.model_id
        session = GameSession.objects.get(public_id=resp.json()["game_id"])
        assert session.ai_model_id == newest.id
