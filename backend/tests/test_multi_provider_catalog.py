from datetime import datetime, timezone
from io import StringIO
from typing import Any

from django.core.management import call_command
from django.test import TestCase, override_settings

from catalog.management.commands.seed_models import SEEDED_MODELS
from catalog.models import AIModel
from catalog.openrouter_sync import (
    OpenRouterModelRecord,
    normalize_openrouter_model,
    sync_openrouter_models,
)
from catalog.selection import (
    DIRECT_FREE_RIVAL_PAIRS,
    DIRECT_FREE_RIVALS,
    FREE_RIVAL_PAIRS,
    NVIDIA_NIM_MODEL_ID,
    NVIDIA_NIM_PROVIDER,
    OPENROUTER_PROVIDER,
    PREPARED_FREE_RIVAL_PAIRS,
    WATCHLIST_FREE_RIVAL_PAIRS,
    get_selectable_models,
)


def _selected_pairs() -> list[tuple[str, str]]:
    return [(row.provider, row.model_id) for row in get_selectable_models()]


def _set_active(pair: tuple[str, str], *, active: bool = True) -> AIModel:
    provider, model_id = pair
    row = AIModel.objects.get(provider=provider, model_id=model_id)
    row.is_active = active
    row.save(update_fields=["is_active"])
    return row


def _dynamic_openrouter(model_id: str, released_at: datetime) -> AIModel:
    return AIModel.objects.create(
        provider=OPENROUTER_PROVIDER,
        model_id=model_id,
        display_name=model_id,
        openrouter_managed=True,
        openrouter_available=True,
        model_type="language",
        tags=["tools"],
        released_at=released_at,
        is_active=True,
    )


class MultiProviderSelectionTests(TestCase):
    def setUp(self) -> None:
        call_command("seed_models", stdout=StringIO())

    def test_flag_off_places_active_direct_rows_before_compatibility_tail(self) -> None:
        first = _set_active(DIRECT_FREE_RIVAL_PAIRS[0])
        third = _set_active(DIRECT_FREE_RIVAL_PAIRS[2])

        assert _selected_pairs() == [
            (first.provider, first.model_id),
            (third.provider, third.model_id),
            *FREE_RIVAL_PAIRS,
        ]

        payload = self.client.get("/api/catalog/models/").json()
        assert [(item["provider"], item["model_id"]) for item in payload] == [
            (first.provider, first.model_id),
            (third.provider, third.model_id),
            *FREE_RIVAL_PAIRS,
        ]
        assert payload[0]["is_flagship"] is True
        assert payload[0]["recommended"] is True
        assert sum(1 for item in payload if item["is_flagship"]) == 1
        assert sum(1 for item in payload if item["recommended"]) == 1

    @override_settings(DYNAMIC_FREE_MODEL_CATALOG_ENABLED=True)
    def test_flag_on_keeps_direct_order_and_changes_only_openrouter_tail(self) -> None:
        direct = _set_active(DIRECT_FREE_RIVAL_PAIRS[1])
        dynamic = [
            _dynamic_openrouter(
                f"vendor/direct-tail-{index}:free",
                datetime(2026, index, 1, tzinfo=timezone.utc),
            )
            for index in range(1, 6)
        ]

        selected = _selected_pairs()
        assert selected[0] == (direct.provider, direct.model_id)
        assert selected[1:5] == [
            (OPENROUTER_PROVIDER, row.model_id) for row in reversed(dynamic[1:])
        ]
        assert selected[5] == (NVIDIA_NIM_PROVIDER, NVIDIA_NIM_MODEL_ID)
        assert len(selected) == 6

    def test_direct_rows_require_active_language_tools_and_watchlist_is_not_selectable(
        self,
    ) -> None:
        for pair in DIRECT_FREE_RIVAL_PAIRS:
            _set_active(pair)
        no_tools = AIModel.objects.get(model_id=DIRECT_FREE_RIVAL_PAIRS[1][1])
        no_tools.tags = ["temperature"]
        no_tools.save(update_fields=["tags"])
        wrong_type = AIModel.objects.get(model_id=DIRECT_FREE_RIVAL_PAIRS[3][1])
        wrong_type.model_type = "image"
        wrong_type.save(update_fields=["model_type"])
        for pair in WATCHLIST_FREE_RIVAL_PAIRS:
            _set_active(pair)

        selected = _selected_pairs()
        assert selected[:3] == [
            DIRECT_FREE_RIVAL_PAIRS[0],
            DIRECT_FREE_RIVAL_PAIRS[2],
            DIRECT_FREE_RIVAL_PAIRS[4],
        ]
        assert DIRECT_FREE_RIVAL_PAIRS[1] not in selected
        assert DIRECT_FREE_RIVAL_PAIRS[3] not in selected
        assert set(WATCHLIST_FREE_RIVAL_PAIRS).isdisjoint(selected)


class MultiProviderSeedTests(TestCase):
    def test_seed_creates_prepared_rows_inactive_and_preserves_every_kill_switch(
        self,
    ) -> None:
        seeded_ids = [item["model_id"] for item in SEEDED_MODELS]
        AIModel.objects.filter(model_id__in=seeded_ids).delete()

        call_command("seed_models", stdout=StringIO())

        for metadata in DIRECT_FREE_RIVALS:
            row = AIModel.objects.get(
                provider=metadata["provider"], model_id=metadata["model_id"]
            )
            assert row.is_active is False
            assert row.openrouter_managed is False
            assert row.openrouter_available is False
            assert row.model_type == "language"
            assert row.tags == ["tools"]
            assert row.display_name == metadata["display_name"]
            assert row.sort_order == metadata["sort_order"]

        direct = _set_active(DIRECT_FREE_RIVAL_PAIRS[0])
        watchlist = _set_active(WATCHLIST_FREE_RIVAL_PAIRS[0])
        compatibility = _set_active(FREE_RIVAL_PAIRS[0], active=False)
        direct.description = "stale direct metadata"
        direct.save(update_fields=["description"])

        call_command("seed_models", stdout=StringIO())

        direct.refresh_from_db()
        watchlist.refresh_from_db()
        compatibility.refresh_from_db()
        assert direct.is_active is True
        assert watchlist.is_active is True
        assert compatibility.is_active is False
        assert direct.description == DIRECT_FREE_RIVALS[0]["description"]

    def test_seed_fails_closed_on_global_model_id_provider_collision(self) -> None:
        provider, model_id = DIRECT_FREE_RIVAL_PAIRS[0]
        AIModel.objects.filter(model_id=model_id).delete()
        collision = AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id=model_id,
            display_name="Owner collision",
            description="must survive",
            is_active=True,
        )

        call_command("seed_models", stdout=StringIO())

        collision.refresh_from_db()
        assert collision.provider == OPENROUTER_PROVIDER
        assert collision.display_name == "Owner collision"
        assert collision.description == "must survive"
        assert collision.is_active is True
        assert not AIModel.objects.filter(provider=provider, model_id=model_id).exists()

    def test_openrouter_sync_pipeline_does_not_own_prepared_rows(self) -> None:
        call_command("seed_models", stdout=StringIO())
        rows = list(
            AIModel.objects.filter(
                model_id__in=[model_id for _, model_id in PREPARED_FREE_RIVAL_PAIRS]
            ).order_by("model_id")
        )
        before = {
            row.model_id: (
                row.provider,
                row.display_name,
                row.description,
                row.openrouter_managed,
                row.openrouter_available,
                row.is_active,
                row.sort_order,
            )
            for row in rows
        }
        for provider, model_id in PREPARED_FREE_RIVAL_PAIRS:
            payload: dict[str, Any] = {
                "id": model_id,
                "name": f"OpenRouter attempt for {provider}",
                "pricing": {"prompt": "0", "completion": "0"},
                "supported_parameters": ["tools"],
                "architecture": {"output_modalities": ["text"]},
            }
            assert normalize_openrouter_model(payload) is None

        sync_openrouter_models(
            models=[
                OpenRouterModelRecord(
                    model_id="vendor/sync-control:free",
                    display_name="Sync control",
                    description="eligible OpenRouter control",
                    model_type="language",
                    context_window=8192,
                    max_tokens=None,
                    tags=["tools"],
                    released_at=None,
                )
            ],
            allow_large_drop=True,
        )

        after_rows = AIModel.objects.filter(model_id__in=before).order_by("model_id")
        after = {
            row.model_id: (
                row.provider,
                row.display_name,
                row.description,
                row.openrouter_managed,
                row.openrouter_available,
                row.is_active,
                row.sort_order,
            )
            for row in after_rows
        }
        assert after == before
