"""Django REST API tests — test the full request/response cycle."""

from io import StringIO
from typing import Any
from unittest.mock import patch

from django.core.management import call_command, load_command_class
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import AIModel, AIPrompt
from catalog.selection import (
    DEFAULT_FREE_MODEL_ID,
    FREE_RIVAL_IDS,
    FREE_RIVAL_PAIRS,
    NVIDIA_NIM_MODEL_ID,
    NVIDIA_NIM_PROVIDER,
    OPENROUTER_PROVIDER,
    is_selectable_model,
)
from game.models import GameSession, Move


class AuthAPITest(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()

    def test_register(self) -> None:
        resp = self.client.post("/api/auth/register/", {
            "username": "testplayer",
            "email": "test@example.com",
            "password": "testpass123",
        })
        assert resp.status_code == 201
        assert User.objects.filter(username="testplayer").exists()
        assert "credit_balance" not in resp.json()
        assert "credit_updated_at" not in resp.json()

    def test_login_and_me(self) -> None:
        User.objects.create_user(username="player1", password="pass1234")
        resp = self.client.post("/api/auth/login/", {
            "username": "player1",
            "password": "pass1234",
        })
        assert resp.status_code == 200
        token = resp.json()["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.get("/api/auth/me/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "player1"
        assert "credit_balance" not in data
        assert "credit_updated_at" not in data

    def test_change_password(self) -> None:
        User.objects.create_user(username="player1", password="pass1234")
        login = self.client.post("/api/auth/login/", {
            "username": "player1",
            "password": "pass1234",
        })
        token = login.json()["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.post("/api/auth/change-password/", {
            "current_password": "pass1234",
            "new_password": "newpass1234",
        })

        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

        old_login = self.client.post("/api/auth/login/", {
            "username": "player1",
            "password": "pass1234",
        })
        assert old_login.status_code == 401

        new_login = self.client.post("/api/auth/login/", {
            "username": "player1",
            "password": "newpass1234",
        })
        assert new_login.status_code == 200

    def test_change_password_rejects_wrong_current_password(self) -> None:
        User.objects.create_user(username="player1", password="pass1234")
        login = self.client.post("/api/auth/login/", {
            "username": "player1",
            "password": "pass1234",
        })
        token = login.json()["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        resp = self.client.post("/api/auth/change-password/", {
            "current_password": "wrongpass",
            "new_password": "newpass1234",
        })

        assert resp.status_code == 400
        assert resp.json()["ok"] is False
        assert resp.json()["error"] == "Current password is incorrect."


_PROVIDER_BY_ID = {model_id: provider for provider, model_id in FREE_RIVAL_PAIRS}


def _make_rival(*, model_id: str = DEFAULT_FREE_MODEL_ID, **overrides: Any) -> AIModel:
    index = list(FREE_RIVAL_IDS).index(model_id) if model_id in FREE_RIVAL_IDS else 0
    provider = _PROVIDER_BY_ID.get(model_id, OPENROUTER_PROVIDER)
    is_nim = provider == NVIDIA_NIM_PROVIDER
    defaults: dict[str, Any] = {
        "provider": provider,
        "model_id": model_id,
        "display_name": f"Rival {index + 1}",
        "openrouter_available": not is_nim,
        "openrouter_managed": not is_nim,
        "is_active": True,
        "model_type": "language",
        "tags": ["tools"],
        "sort_order": (index + 1) * 10,
    }
    defaults.update(overrides)
    return AIModel.objects.create(**defaults)


def _seed_shortlist() -> list[AIModel]:
    return [_make_rival(model_id=model_id) for model_id in FREE_RIVAL_IDS]


class CatalogAPITest(TestCase):
    def test_list_models_returns_shortlist_in_free_rival_order_without_pricing(self) -> None:
        _seed_shortlist()
        AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="GPT-5 Mini",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        AIModel.objects.create(
            provider="openrouter",
            model_id="meta-llama/llama-3.3-70b-instruct:free",
            display_name="Inactive extra free",
            openrouter_available=True,
            is_active=False,
            model_type="language",
            tags=["tools"],
        )

        resp = self.client.get("/api/catalog/models/")
        assert resp.status_code == 200
        data = resp.json()
        assert [(item["provider"], item["model_id"]) for item in data] == list(
            FREE_RIVAL_PAIRS
        )
        assert len(data) <= 5
        money_keys = {
            "cost_per_game",
            "pricing",
            "input_cost_per_million",
            "output_cost_per_million",
            "cache_read_cost_per_million",
            "cache_write_cost_per_million",
            "combined_cost_per_million",
        }
        for item in data:
            assert money_keys.isdisjoint(item)
            assert item["is_flagship"] is (item["model_id"] == DEFAULT_FREE_MODEL_ID)
        assert sum(1 for item in data if item["is_flagship"]) == 1

    def test_list_models_excludes_paid_malformed_non_tool_lm_novita_xai_openai_and_inactive_extra_free(
        self,
    ) -> None:
        _seed_shortlist()
        AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="OpenAI paid",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        AIModel.objects.create(
            provider="openrouter",
            model_id="not-a-valid-id",
            display_name="Malformed",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        AIModel.objects.create(
            provider="openrouter",
            model_id="google/gemma-2-9b-it:free",
            display_name="Free no tools",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["temperature"],
        )
        AIModel.objects.create(
            provider="lmstudio",
            model_id="lmstudio/qwen3-14b-sk",
            display_name="LM Studio",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        AIModel.objects.create(
            provider="novita",
            model_id="novita/qwen3-32b",
            display_name="Novita",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        AIModel.objects.create(
            provider="x-ai",
            model_id="x-ai/grok-4",
            display_name="xAI",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        AIModel.objects.create(
            provider="openrouter",
            model_id="meta-llama/llama-3.3-70b-instruct:free",
            display_name="Inactive extra free",
            openrouter_available=True,
            is_active=False,
            model_type="language",
            tags=["tools"],
        )

        resp = self.client.get("/api/catalog/models/")
        assert [item["model_id"] for item in resp.json()] == list(FREE_RIVAL_IDS)

    def test_legacy_openai_row_survives_and_is_not_selectable(self) -> None:
        _make_rival()
        legacy = AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="GPT-5 Mini",
            openrouter_available=False,
            openrouter_managed=False,
            is_active=False,
            model_type="language",
            tags=["tools"],
        )
        resp = self.client.get("/api/catalog/models/")
        ids = [item["model_id"] for item in resp.json()]
        assert legacy.model_id not in ids
        assert AIModel.objects.filter(model_id="openai/gpt-5-mini").exists()

    def test_list_prompts_returns_active_catalog(self) -> None:
        visible = AIPrompt.objects.create(
            name="Benchmark",
            prompt="Try short hooks first.",
            fitness=1.5,
            sort_order=5,
            is_active=True,
        )
        AIPrompt.objects.create(
            name="Hidden",
            prompt="Do not expose this.",
            fitness=9.9,
            sort_order=1,
            is_active=False,
        )

        resp = self.client.get("/api/catalog/prompts/")
        assert resp.status_code == 200
        data = resp.json()
        names = [item["name"] for item in data]

        assert "Grandmaster" in names
        assert "Benchmark" in names
        assert "Hidden" not in names

        visible_item = next(item for item in data if item["id"] == visible.id)
        assert visible_item["fitness"] == 1.5

    def test_seed_models_is_idempotent_and_has_no_reset_flag(self) -> None:
        leftover = AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="Legacy leftover",
        )
        stdout = StringIO()
        call_command("seed_models", stdout=stdout)
        call_command("seed_models", stdout=stdout)
        ids = list(
            AIModel.objects.filter(model_id__in=FREE_RIVAL_IDS)
            .order_by("sort_order")
            .values_list("model_id", flat=True)
        )
        assert ids == list(FREE_RIVAL_IDS)
        nim = AIModel.objects.get(model_id=NVIDIA_NIM_MODEL_ID)
        assert nim.provider == NVIDIA_NIM_PROVIDER
        assert nim.openrouter_managed is False
        assert nim.openrouter_available is False
        assert AIModel.objects.filter(model_id=leftover.model_id).exists()
        command = load_command_class("catalog", "seed_models")
        parser = command.create_parser("manage.py", "seed_models")
        assert "--reset" not in parser.format_help()

    def test_sync_openrouter_models_command_persists_only_eligible_rows(self) -> None:
        retired = AIModel.objects.create(
            provider="openrouter",
            model_id="old-openrouter/retired:free",
            display_name="Retired",
            openrouter_managed=True,
            openrouter_available=True,
            is_active=True,
        )
        payload = {
            "data": [
                {
                    "id": "openai/gpt-5-mini",
                    "name": "GPT-5 Mini",
                    "description": "Paid",
                    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                    "supported_parameters": ["tools"],
                    "architecture": {"output_modalities": ["text"]},
                    "context_length": 128000,
                },
                {
                    "id": "meta-llama/llama-3.3-70b-instruct:free",
                    "name": "Llama 3.3 70B Instruct",
                    "description": "Eligible extra",
                    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                    "supported_parameters": ["tools", "temperature"],
                    "architecture": {"output_modalities": ["text"]},
                    "context_length": 128000,
                },
                {
                    "id": "google/gemma-2-9b-it:free",
                    "name": "Gemma 2 9B",
                    "description": "Free without tools",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "supported_parameters": ["temperature"],
                    "architecture": {"output_modalities": ["text"]},
                    "context_length": 8192,
                },
                {
                    "id": DEFAULT_FREE_MODEL_ID,
                    "name": "Gemma 4 31B IT",
                    "description": "Shortlist",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "supported_parameters": ["tools"],
                    "architecture": {"output_modalities": ["text"]},
                    "context_length": 131072,
                },
                {
                    "id": "openrouter/free",
                    "name": "OpenRouter Free",
                    "pricing": {"prompt": "0", "completion": "0"},
                    "supported_parameters": ["tools"],
                    "architecture": {"output_modalities": ["text"]},
                },
            ]
        }

        class DummyResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict[str, Any]:
                return payload

        class DummyClient:
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                return None

            def __enter__(self) -> Any:
                return self

            def __exit__(self, *args: Any) -> bool:
                return False

            def get(self, url: str) -> DummyResponse:
                return DummyResponse()

        stdout = StringIO()
        with patch("catalog.openrouter_sync.httpx.Client", DummyClient):
            call_command("sync_openrouter_models", stdout=stdout)

        assert not AIModel.objects.filter(model_id="openai/gpt-5-mini").exists()
        assert not AIModel.objects.filter(model_id="google/gemma-2-9b-it:free").exists()
        extra = AIModel.objects.get(model_id="meta-llama/llama-3.3-70b-instruct:free")
        assert extra.openrouter_managed is True
        assert extra.openrouter_available is True
        assert extra.is_active is False
        assert not hasattr(extra, "pricing")
        assert not hasattr(extra, "cost_per_game")
        default = AIModel.objects.get(model_id=DEFAULT_FREE_MODEL_ID)
        assert default.is_active is True
        assert default.openrouter_managed is True
        assert default.sort_order == 10
        retired.refresh_from_db()
        assert retired.openrouter_available is False
        assert retired.is_active is False
        assert AIModel.objects.filter(pk=retired.pk).exists()

    def test_nim_row_is_selectable_without_openrouter_available(self) -> None:
        nim = _make_rival(model_id=NVIDIA_NIM_MODEL_ID)
        assert nim.provider == NVIDIA_NIM_PROVIDER
        assert nim.openrouter_available is False
        resp = self.client.get("/api/catalog/models/")
        ids = [item["model_id"] for item in resp.json()]
        assert NVIDIA_NIM_MODEL_ID in ids
        assert is_selectable_model(NVIDIA_NIM_MODEL_ID) is True

    def test_openrouter_row_with_nim_id_is_not_selectable(self) -> None:
        AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id=NVIDIA_NIM_MODEL_ID,
            display_name="OpenRouter impersonator",
            openrouter_available=True,
            openrouter_managed=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        resp = self.client.get("/api/catalog/models/")
        ids = [item["model_id"] for item in resp.json()]
        assert NVIDIA_NIM_MODEL_ID not in ids
        assert is_selectable_model(NVIDIA_NIM_MODEL_ID) is False

    def test_eligibility_rejects_inactive_non_language_missing_tools_unavailable_and_non_curated(
        self,
    ) -> None:
        openrouter_rejections: list[dict[str, Any]] = [
            {"is_active": False},
            {"model_type": "image"},
            {"tags": ["temperature"]},
            {"tags": {"tools": True}},
            {"openrouter_available": False},
        ]
        for overrides in openrouter_rejections:
            AIModel.objects.all().delete()
            _make_rival(**overrides)
            assert is_selectable_model(DEFAULT_FREE_MODEL_ID) is False, overrides
            resp = self.client.get("/api/catalog/models/")
            assert DEFAULT_FREE_MODEL_ID not in [
                item["model_id"] for item in resp.json()
            ], overrides

        nim_rejections: list[dict[str, Any]] = [
            {"is_active": False},
            {"model_type": "image"},
            {"tags": ["temperature"]},
        ]
        for overrides in nim_rejections:
            AIModel.objects.all().delete()
            _make_rival(model_id=NVIDIA_NIM_MODEL_ID, **overrides)
            assert is_selectable_model(NVIDIA_NIM_MODEL_ID) is False, overrides
            resp = self.client.get("/api/catalog/models/")
            assert NVIDIA_NIM_MODEL_ID not in [
                item["model_id"] for item in resp.json()
            ], overrides

        AIModel.objects.all().delete()
        _seed_shortlist()
        extra_id = "meta-llama/llama-3.3-70b-instruct:free"
        AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id=extra_id,
            display_name="Non-curated extra",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        assert is_selectable_model(extra_id) is False
        resp = self.client.get("/api/catalog/models/")
        assert [item["model_id"] for item in resp.json()] == list(FREE_RIVAL_IDS)

    def test_seed_models_does_not_steal_conflicting_provider_row(self) -> None:
        collision = AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id=NVIDIA_NIM_MODEL_ID,
            display_name="OpenRouter collision",
            openrouter_managed=True,
            openrouter_available=True,
            is_active=True,
        )
        call_command("seed_models", stdout=StringIO())
        collision.refresh_from_db()
        assert collision.provider == OPENROUTER_PROVIDER
        assert collision.display_name == "OpenRouter collision"
        assert not AIModel.objects.filter(
            provider=NVIDIA_NIM_PROVIDER,
            model_id=NVIDIA_NIM_MODEL_ID,
        ).exists()

    def test_sync_openrouter_models_does_not_mutate_nvidia_nim_row(self) -> None:
        from catalog.openrouter_sync import OpenRouterModelRecord, sync_openrouter_models

        nim = AIModel.objects.create(
            provider=NVIDIA_NIM_PROVIDER,
            model_id=NVIDIA_NIM_MODEL_ID,
            display_name="Nemotron NIM",
            description="seeded nim",
            openrouter_managed=False,
            openrouter_available=False,
            is_active=True,
            model_type="language",
            tags=["tools"],
            sort_order=20,
        )
        sync_openrouter_models(
            models=[
                OpenRouterModelRecord(
                    model_id=NVIDIA_NIM_MODEL_ID,
                    display_name="Stolen",
                    description="must not apply",
                    model_type="multimodal",
                    context_window=1,
                    max_tokens=1,
                    tags=["temperature"],
                    released_at=None,
                )
            ]
        )
        nim.refresh_from_db()
        assert nim.provider == NVIDIA_NIM_PROVIDER
        assert nim.display_name == "Nemotron NIM"
        assert nim.description == "seeded nim"
        assert nim.openrouter_managed is False
        assert nim.openrouter_available is False
        assert nim.is_active is True
        assert nim.model_type == "language"
        assert nim.tags == ["tools"]
        assert nim.sort_order == 20
        assert not AIModel.objects.filter(
            provider=OPENROUTER_PROVIDER,
            model_id=NVIDIA_NIM_MODEL_ID,
        ).exists()


class GameAPITest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="player1", password="pass1234")
        self.user2 = User.objects.create_user(username="player2", password="pass1234")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)
        self.ai_model = _make_rival(display_name="Gemma 4 31B IT")

    def test_create_game(self) -> None:
        resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_id": self.ai_model.id,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "game_id" in data
        assert "starting_draw" in data
        assert "human_rack" in data
        assert data["ai_model_id"] == self.ai_model.model_id
        assert len(data["human_rack"]) == 7

    def test_create_game_with_model_id_string(self) -> None:
        resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        assert resp.status_code == 201
        assert resp.json()["ai_model_id"] == self.ai_model.model_id

    def test_create_game_rejects_dynamic_lmstudio_model_id(self) -> None:
        model_id = "lmstudio/google/gemma-4-12b-qat"

        resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": model_id,
        })

        assert resp.status_code == 400
        assert not AIModel.objects.filter(model_id=model_id).exists()

    def test_ineligible_ids_are_rejected_for_preference_create_and_switch(self) -> None:
        ineligible_ids = [
            "openai/gpt-5-mini",
            "not-a-valid-id",
            "google/gemma-2-9b-it:free",
            "lmstudio/qwen3-14b-sk",
            "novita/qwen3-32b",
            "x-ai/grok-4",
            "meta-llama/llama-3.3-70b-instruct:free",
        ]
        AIModel.objects.create(
            provider="openrouter",
            model_id="meta-llama/llama-3.3-70b-instruct:free",
            display_name="Inactive extra free",
            openrouter_available=True,
            is_active=False,
            model_type="language",
            tags=["tools"],
        )
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": DEFAULT_FREE_MODEL_ID,
        })
        game_id = create_resp.json()["game_id"]

        for model_id in ineligible_ids:
            preference = self.client.patch(
                "/api/auth/me/",
                {"preferred_ai_model_id": model_id},
                format="json",
            )
            assert preference.status_code == 400, model_id
            created = self.client.post("/api/game/create/", {
                "game_mode": "vs_ai",
                "ai_model_model_id": model_id,
            })
            assert created.status_code == 400, model_id
            switched = self.client.patch(
                f"/api/game/{game_id}/ai-model/",
                {"ai_model_model_id": model_id},
                format="json",
            )
            assert switched.status_code == 400, model_id

    def test_charge_ai_turn_endpoint_is_removed(self) -> None:
        resp = self.client.post(
            "/api/billing/charge-ai-turn/",
            {"game_id": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        assert resp.status_code == 404

    def test_admin_has_no_billing_models_or_monetary_controls(self) -> None:
        import importlib

        from django.conf import settings
        from django.contrib import admin

        admin_user = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        admin_client = APIClient()
        admin_client.force_login(admin_user)

        dashboard = admin_client.get("/admin/game/gamesession/dashboard/")
        assert dashboard.status_code == 200
        content = dashboard.content.decode()
        assert "Edit balances" not in content
        assert "AI spend" not in content
        assert "charged credits" not in content.lower()
        assert "USD" not in content
        assert "billing" not in settings.INSTALLED_APPS
        assert all(model._meta.app_label != "billing" for model in admin.site._registry)
        with self.assertRaises(ModuleNotFoundError):
            importlib.import_module("billing.models")

    def test_create_game_with_prompt_returns_prompt_metadata(self) -> None:
        prompt = AIPrompt.objects.create(
            name="Tempo Search",
            prompt="Short plausible words first.",
            fitness=1.25,
            sort_order=5,
        )

        resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
            "ai_prompt_id": prompt.id,
        })

        assert resp.status_code == 201
        data = resp.json()
        assert data["ai_prompt_id"] == prompt.id
        assert data["ai_prompt_name"] == prompt.name

        state = self.client.get(f"/api/game/{data['game_id']}/")
        assert state.status_code == 200
        assert state.json()["ai_prompt_id"] == prompt.id
        assert state.json()["ai_prompt_name"] == prompt.name

    def test_get_game_state(self) -> None:
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        resp = self.client.get(f"/api/game/{game_id}/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert data["ai_model_id"] == self.ai_model.model_id
        assert len(data["slots"]) == 2
        assert data["bag_remaining"] < 100
        assert len(data["my_rack"]) == 7
        assert data["my_slot"] == 0
        assert "total_cost_usd" not in data
        assert "last_move_billing" not in data
        assert all("billing" not in item for item in data["move_history"])

    def test_submit_pass(self) -> None:
        create_resp = self.client.post("/api/game/create/", {"game_mode": "vs_ai"})
        game_id = create_resp.json()["game_id"]
        from game.models import GameSession

        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 0
        session.save(update_fields=["current_turn_slot"])

        resp = self.client.post(f"/api/game/{game_id}/pass/")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @patch("game.realtime.async_to_sync")
    def test_ai_pass_succeeds_when_realtime_publish_fails(self, mock_async_to_sync) -> None:
        create_resp = self.client.post("/api/game/create/", {"game_mode": "vs_ai"})
        game_id = create_resp.json()["game_id"]
        from game.models import GameSession

        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 1
        session.save(update_fields=["current_turn_slot"])

        def fail_group_send(*_args, **_kwargs) -> None:
            raise ConnectionError("Redis unavailable")

        mock_async_to_sync.return_value = fail_group_send

        resp = self.client.post(f"/api/game/{game_id}/ai-pass/")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert resp.json()["state"]["current_turn_slot"] == 0
        assert "billing" not in resp.json()
        assert "last_move_billing" not in resp.json()["state"]
        move = Move.objects.get(game=session, kind="pass")
        assert not move.ai_metadata

    def test_ai_exchange_succeeds_without_billing_metadata(self) -> None:
        create_resp = self.client.post("/api/game/create/", {"game_mode": "vs_ai"})
        game_id = create_resp.json()["game_id"]
        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 1
        session.save(update_fields=["current_turn_slot"])
        ai_slot = session.slots.get(slot=1)
        letter = ai_slot.rack[0]

        resp = self.client.post(
            f"/api/game/{game_id}/ai-exchange/",
            {"letters": [letter]},
            format="json",
        )

        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "billing" not in resp.json()
        assert "last_move_billing" not in resp.json()["state"]
        move = Move.objects.get(game=session, kind="exchange")
        assert not move.ai_metadata

    def test_validate_words(self) -> None:
        create_resp = self.client.post("/api/game/create/", {"game_mode": "vs_ai"})
        game_id = create_resp.json()["game_id"]

        resp = self.client.post(f"/api/game/{game_id}/validate-words/", {
            "words": ["hello", "xyzqw", "cat"],
        }, format="json")
        assert resp.status_code == 200
        results = resp.json()["results"]
        assert len(results) == 3
        assert results[0]["valid"] is True
        assert results[0]["word"] == "hello"
        assert results[1]["valid"] is False
        assert results[2]["valid"] is True

    @override_settings(
        AI_MOVE_MAX_OUTPUT_TOKENS=4321,
        AI_MOVE_TIMEOUT_SECONDS=180,
    )
    def test_ai_context(self) -> None:
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_id": self.ai_model.id,
        })
        game_id = create_resp.json()["game_id"]

        resp = self.client.get(f"/api/game/{game_id}/ai-context/")
        assert resp.status_code == 200
        data = resp.json()
        assert "compact_state" in data
        assert "grid:" in data["compact_state"]
        assert data["variant"] == "english"
        assert data["ai_move_max_output_tokens"] == 4321
        assert data["ai_move_timeout_seconds"] == 180

    def test_submit_move_returns_updated_state_with_refilled_rack(self) -> None:
        from game.models import GameSession

        create_resp = self.client.post("/api/game/create/", {"game_mode": "vs_ai"})
        game_id = create_resp.json()["game_id"]
        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 0
        session.save(update_fields=["current_turn_slot"])

        human = session.slots.get(slot=0)
        human.rack = ["A", "T", "B", "C", "D", "E", "F"]
        human.save(update_fields=["rack"])

        resp = self.client.post(
            f"/api/game/{game_id}/move/",
            {
                "placements": [
                    {"row": 7, "col": 7, "letter": "A"},
                    {"row": 7, "col": 8, "letter": "T"},
                ],
            },
            format="json",
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["state"]["board"][7][7:9] == "AT"
        assert len(data["state"]["my_rack"]) == 7

    @patch("game.views.services.get_game_state_for_user")
    @patch("game.views.services.submit_move_for_ai")
    def test_apply_ai_move_response_has_no_billing(self, mock_submit_move, mock_get_state) -> None:
        mock_submit_move.return_value = {
            "ok": True,
            "points": 42,
            "words": [{"word": "AT", "score": 2}],
        }
        mock_get_state.return_value = {
            "game_id": "stub",
            "status": "active",
        }

        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        resp = self.client.post(
            f"/api/game/{game_id}/ai-move/",
            {
                "placements": [{"row": 7, "col": 7, "letter": "A"}],
                "ai_metadata": {
                    "usage": {
                        "inputTokens": 1000,
                        "outputTokens": 200,
                        "totalTokens": 1200,
                    }
                },
            },
            format="json",
        )

        assert resp.status_code == 200
        assert "billing" not in resp.json()
        assert "last_move_billing" not in resp.json()["state"]

        profile = self.client.get("/api/auth/me/")
        assert profile.status_code == 200
        assert "credit_balance" not in profile.json()
        assert "credit_updated_at" not in profile.json()

    def test_give_up_ends_game_and_marks_it_abandoned(self) -> None:
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        resp = self.client.post(f"/api/game/{game_id}/give-up/")

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["status"] == "abandoned"
        assert data["game_end_reason"] == "give_up"
        assert data["winner_slot"] == 1
        assert data["state"]["game_over"] is True
        assert data["state"]["status"] == "abandoned"

    def test_game_history_can_filter_and_paginate(self) -> None:
        ai_game_ids: list[str] = []
        for _ in range(3):
            resp = self.client.post("/api/game/create/", {
                "game_mode": "vs_ai",
                "ai_model_model_id": self.ai_model.model_id,
            })
            ai_game_ids.append(resp.json()["game_id"])

        waiting = self.client.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        self.client2.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        human_game_id = waiting.json()["state"]["game_id"]

        ai_only = self.client.get("/api/game/history/?game_mode=vs_ai&page=1&page_size=2")
        assert ai_only.status_code == 200
        ai_data = ai_only.json()
        assert ai_data["game_mode"] == "vs_ai"
        assert ai_data["page"] == 1
        assert ai_data["page_size"] == 2
        assert ai_data["total"] == 3
        assert ai_data["total_pages"] == 2
        assert ai_data["has_next"] is True
        assert len(ai_data["items"]) == 2
        assert all(item["game_mode"] == "vs_ai" for item in ai_data["items"])
        assert all("total_cost_usd" not in item for item in ai_data["items"])

        human_only = self.client.get("/api/game/history/?game_mode=vs_human")
        assert human_only.status_code == 200
        human_items = human_only.json()["items"]
        assert len(human_items) == 1
        assert human_items[0]["game_mode"] == "vs_human"
        assert human_items[0]["game_id"] == human_game_id
        assert human_items[0]["opponent_label"] == "player2"

        cost_sorted = self.client.get("/api/game/history/?game_mode=vs_ai&sort=cost_desc")
        assert cost_sorted.status_code == 400

        all_games = self.client.get("/api/game/history/?game_mode=all")
        assert all_games.status_code == 200
        returned_ids = {item["game_id"] for item in all_games.json()["items"]}
        assert human_game_id in returned_ids
        assert set(ai_game_ids).issubset(returned_ids)

    def test_game_history_marks_gave_up_and_opponent_win(self) -> None:
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        give_up = self.client.post(f"/api/game/{game_id}/give-up/")
        assert give_up.status_code == 200

        history = self.client.get("/api/game/history/?game_mode=vs_ai")
        assert history.status_code == 200
        item = next(item for item in history.json()["items"] if item["game_id"] == game_id)
        assert item["outcome"] == "gave_up"
        assert item["opponent_label"] == self.ai_model.display_name
        assert item["game_end_reason"] == "give_up"
        assert "total_cost_usd" not in item

    def test_game_history_marks_in_progress_for_active_game(self) -> None:
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        history = self.client.get("/api/game/history/?game_mode=vs_ai")
        assert history.status_code == 200
        item = next(item for item in history.json()["items"] if item["game_id"] == game_id)
        assert item["outcome"] == "in_progress"
        assert item["status"] == "active"
        assert item["opponent_label"] == self.ai_model.display_name

    def test_can_switch_game_ai_model_during_game(self) -> None:
        alternative_model = _make_rival(
            model_id=FREE_RIVAL_IDS[1],
            display_name="Nemotron 3 Super 120B",
        )
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        resp = self.client.patch(
            f"/api/game/{game_id}/ai-model/",
            {"ai_model_model_id": alternative_model.model_id},
            format="json",
        )

        assert resp.status_code == 200
        assert resp.json()["ai_model_id"] == alternative_model.model_id

        state = self.client.get(f"/api/game/{game_id}/")
        assert state.status_code == 200
        assert state.json()["ai_model_id"] == alternative_model.model_id

    def test_can_switch_game_ai_model_to_dynamic_lmstudio_model(self) -> None:
        local_model_id = "lmstudio/qwen/qwen3-14b-sk"
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        resp = self.client.patch(
            f"/api/game/{game_id}/ai-model/",
            {"ai_model_model_id": local_model_id},
            format="json",
        )

        assert resp.status_code == 400
        assert not AIModel.objects.filter(model_id=local_model_id).exists()

    def test_can_switch_game_ai_prompt_during_game(self) -> None:
        prompt = AIPrompt.objects.create(
            name="Anchor Sprint",
            prompt="Validate short hooks and premiums quickly.",
            fitness=2.25,
            sort_order=5,
        )
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        resp = self.client.patch(
            f"/api/game/{game_id}/ai-prompt/",
            {"ai_prompt_id": prompt.id},
            format="json",
        )

        assert resp.status_code == 200
        assert resp.json()["ai_prompt_id"] == prompt.id
        assert resp.json()["ai_prompt_name"] == prompt.name
        assert resp.json()["ai_prompt_fitness"] == prompt.fitness

        state = self.client.get(f"/api/game/{game_id}/")
        assert state.status_code == 200
        assert state.json()["ai_prompt_id"] == prompt.id
        assert state.json()["ai_prompt_name"] == prompt.name

        context = self.client.get(f"/api/game/{game_id}/ai-context/")
        assert context.status_code == 200
        assert context.json()["ai_prompt_id"] == prompt.id
        assert context.json()["ai_prompt_name"] == prompt.name
        assert context.json()["ai_prompt_text"] == prompt.prompt

    def test_apply_ai_move_returns_human_view_state(self) -> None:
        from game.models import GameSession

        create_resp = self.client.post("/api/game/create/", {"game_mode": "vs_ai"})
        game_id = create_resp.json()["game_id"]
        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 1
        session.save(update_fields=["current_turn_slot"])

        ai_slot = session.slots.get(slot=1)
        ai_slot.rack = ["J", "O", "E", "A", "B", "C", "D"]
        ai_slot.save(update_fields=["rack"])

        resp = self.client.post(
            f"/api/game/{game_id}/ai-move/",
            {
                "placements": [
                    {"row": 7, "col": 7, "letter": "J"},
                    {"row": 7, "col": 8, "letter": "O"},
                    {"row": 7, "col": 9, "letter": "E"},
                ],
                "ai_metadata": {
                    "usage": {"inputTokens": 100, "outputTokens": 20, "totalTokens": 120}
                },
            },
            format="json",
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["state"]["board"][7][7:10] == "JOE"
        assert len(data["state"]["my_rack"]) == 7
        assert data["state"]["current_turn_slot"] == 0
        assert "billing" not in data
        assert "last_move_billing" not in data["state"]
        move = Move.objects.get(game=session, kind="place")
        assert move.ai_metadata["usage"]["totalTokens"] == 120
        assert "billing" not in move.ai_metadata

    def test_human_queue_matches_second_player_into_first_waiting_game(self) -> None:
        first = self.client.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        assert first.status_code == 200
        assert first.json()["waiting"] is True

        second = self.client2.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        assert second.status_code == 200
        assert second.json()["matched"] is True

        first_game_id = first.json()["state"]["game_id"]
        second_game_id = second.json()["state"]["game_id"]
        assert first_game_id == second_game_id
        assert second.json()["state"]["status"] == "active"
        assert len(second.json()["state"]["my_rack"]) == 7

    def test_human_queue_reuses_existing_waiting_session(self) -> None:
        first = self.client.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        second = self.client.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        assert first.status_code == 200
        assert second.status_code == 200
        assert first.json()["state"]["game_id"] == second.json()["state"]["game_id"]
        assert second.json()["waiting"] is True

    def test_waiting_host_can_cancel_queue(self) -> None:
        queue_resp = self.client.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        game_id = queue_resp.json()["state"]["game_id"]

        cancel_resp = self.client.post("/api/game/queue/cancel/", {"game_id": game_id}, format="json")
        assert cancel_resp.status_code == 200
        assert cancel_resp.json()["ok"] is True

        state_resp = self.client.get(f"/api/game/{game_id}/")
        assert state_resp.status_code == 200
        assert state_resp.json()["status"] == "abandoned"

    def test_game_state_is_user_derived_and_hides_opponent_rack(self) -> None:
        first = self.client.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        self.client2.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        game_id = first.json()["state"]["game_id"]

        state1 = self.client.get(f"/api/game/{game_id}/")
        state2 = self.client2.get(f"/api/game/{game_id}/")
        assert state1.status_code == 200
        assert state2.status_code == 200
        assert state1.json()["my_slot"] == 0
        assert state2.json()["my_slot"] == 1
        assert state1.json()["my_rack"] != state2.json()["my_rack"]
        assert state1.json()["slots"][1]["rack_count"] == len(state2.json()["my_rack"])

    def test_server_derives_player_slot_for_multiplayer_actions(self) -> None:
        from game.models import GameSession

        first = self.client.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        self.client2.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        game_id = first.json()["state"]["game_id"]

        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 0
        session.save(update_fields=["current_turn_slot"])

        wrong_player = self.client2.post(f"/api/game/{game_id}/pass/")
        assert wrong_player.status_code == 400
        assert wrong_player.json()["error"] == "Not your turn"

        right_player = self.client.post(f"/api/game/{game_id}/pass/")
        assert right_player.status_code == 200
        assert right_player.json()["ok"] is True

    def test_non_participant_cannot_access_private_game_state(self) -> None:
        outsider = User.objects.create_user(username="outsider", password="pass1234")
        outsider_client = APIClient()
        outsider_client.force_authenticate(user=outsider)
        game_id = self.client.post("/api/game/create/", {"game_mode": "vs_ai"}).json()["game_id"]

        resp = outsider_client.get(f"/api/game/{game_id}/")
        assert resp.status_code == 404

    def test_non_participant_cannot_access_ai_context(self) -> None:
        outsider = User.objects.create_user(username="contextoutsider", password="pass1234")
        outsider_client = APIClient()
        outsider_client.force_authenticate(user=outsider)
        game_id = self.client.post("/api/game/create/", {"game_mode": "vs_ai"}).json()["game_id"]

        resp = outsider_client.get(f"/api/game/{game_id}/ai-context/")
        assert resp.status_code == 404

    def test_ws_ticket_requires_membership(self) -> None:
        outsider = User.objects.create_user(username="ticketoutsider", password="pass1234")
        outsider_client = APIClient()
        outsider_client.force_authenticate(user=outsider)
        game_id = self.client.post("/api/game/create/", {"game_mode": "vs_ai"}).json()["game_id"]

        resp = outsider_client.post(f"/api/game/{game_id}/ws-ticket/")
        assert resp.status_code == 404

    def test_human_queue_waiting_state_has_no_turn_or_rack(self) -> None:
        resp = self.client.post("/api/game/queue/join/", {"variant_slug": "english"}, format="json")
        assert resp.status_code == 200
        state = resp.json()["state"]
        assert state["status"] == "waiting"
        assert state["current_turn_slot"] is None
        assert state["my_rack"] == []
