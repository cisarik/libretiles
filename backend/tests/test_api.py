"""Django REST API tests — test the full request/response cycle."""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from accounts.models import User
from catalog.gateway_sync import GatewayModelRecord
from catalog.models import AIModel


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
        assert resp.json()["username"] == "player1"
        assert resp.json()["credit_balance"] == "100.00"


class CatalogAPITest(TestCase):
    def test_list_models_returns_top_twenty_sorted_with_pinned_gpt_5_4(self) -> None:
        for index in range(20):
            input_price = Decimal("0.000020") - (Decimal(index) * Decimal("0.000001"))
            output_price = Decimal("0.000040") - (Decimal(index) * Decimal("0.000001"))
            AIModel.objects.create(
                provider="openai",
                model_id=f"openai/gpt-5-expensive-{index}",
                display_name=f"GPT-5 Expensive {index}",
                gateway_available=True,
                model_type="language",
                tags=["tool-use"],
                pricing={
                    "input": str(input_price),
                    "output": str(output_price),
                },
            )

        AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5.4",
            display_name="GPT-5.4",
            gateway_available=True,
            model_type="language",
            tags=["tool-use"],
            pricing={"input": "0.0000025", "output": "0.000015"},
        )

        resp = self.client.get("/api/catalog/models/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 20
        assert any(item["model_id"] == "openai/gpt-5.4" for item in data)
        assert not any(item["model_id"] == "openai/gpt-5-expensive-19" for item in data)
        combined_costs = [Decimal(item["combined_cost_per_million"]) for item in data]
        assert combined_costs == sorted(combined_costs, reverse=True)
        assert data[0]["combined_cost_per_million"]

    def test_list_models_falls_back_to_active_models_before_first_sync(self) -> None:
        AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="GPT-5 Mini",
            gateway_available=False,
            is_active=True,
        )
        resp = self.client.get("/api/catalog/models/")
        assert resp.status_code == 200
        assert len(resp.json()) == 1
        assert resp.json()[0]["model_id"] == "openai/gpt-5-mini"

    def test_list_models_prefers_tool_capable_gateway_models(self) -> None:
        AIModel.objects.create(
            provider="anthropic",
            model_id="anthropic/claude-3-opus",
            display_name="Claude 3 Opus",
            gateway_available=True,
            model_type="language",
            tags=[],
            pricing={"input": "0.00003", "output": "0.00006"},
        )
        AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5.4",
            display_name="GPT-5.4",
            gateway_available=True,
            model_type="language",
            tags=["tool-use"],
            pricing={"input": "0.0000025", "output": "0.000015"},
        )

        resp = self.client.get("/api/catalog/models/")
        assert resp.status_code == 200
        data = resp.json()
        assert [item["model_id"] for item in data] == ["openai/gpt-5.4"]

    def test_list_models_excludes_inactive_gateway_models_except_pinned_gpt_5_4(self) -> None:
        AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5.2",
            display_name="GPT-5.2",
            gateway_available=True,
            is_active=True,
            model_type="language",
            tags=["tool-use"],
            pricing={"input": "0.00000175", "output": "0.000014"},
        )
        AIModel.objects.create(
            provider="anthropic",
            model_id="anthropic/claude-opus-4.1",
            display_name="Claude Opus 4.1",
            gateway_available=True,
            is_active=False,
            model_type="language",
            tags=["tool-use"],
            pricing={"input": "0.000015", "output": "0.000075"},
        )
        AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5.4",
            display_name="GPT-5.4",
            gateway_available=True,
            is_active=False,
            model_type="language",
            tags=["tool-use"],
            pricing={"input": "0.0000025", "output": "0.000015"},
        )

        resp = self.client.get("/api/catalog/models/")
        assert resp.status_code == 200
        data = resp.json()
        assert [item["model_id"] for item in data] == [
            "openai/gpt-5.4",
            "openai/gpt-5.2",
        ]

    def test_sync_gateway_models_command(self) -> None:
        manual = AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="Custom GPT-5 Mini",
            description="Manual label",
            is_active=True,
            gateway_managed=False,
        )
        AIModel.objects.create(
            provider="openai",
            model_id="openai/retired-model",
            display_name="Retired",
            gateway_managed=True,
            gateway_available=True,
            is_active=True,
        )

        models = [
            GatewayModelRecord(
                model_id="openai/gpt-5-mini",
                provider="openai",
                display_name="GPT-5 Mini",
                description="Latest synced description",
                model_type="language",
                context_window=200000,
                max_tokens=10000,
                tags=["reasoning", "tool-use"],
                pricing={"input": "0.000001", "output": "0.000002"},
                released_at=None,
            ),
            GatewayModelRecord(
                model_id="anthropic/claude-sonnet-4.6",
                provider="anthropic",
                display_name="Claude Sonnet 4.6",
                description="Balanced model",
                model_type="language",
                context_window=200000,
                max_tokens=8000,
                tags=["tool-use"],
                pricing={"input": "0.000003", "output": "0.000015"},
                released_at=None,
            ),
        ]

        stdout = StringIO()
        with patch("catalog.management.commands.sync_gateway_models.fetch_gateway_models") as fetch:
            fetch.return_value = models
            call_command("sync_gateway_models", stdout=stdout)

        manual.refresh_from_db()
        assert manual.display_name == "Custom GPT-5 Mini"
        assert manual.description == "Manual label"
        assert manual.gateway_available is True
        assert manual.context_window == 200000
        assert manual.pricing == {"input": "0.000001", "output": "0.000002"}

        created = AIModel.objects.get(model_id="anthropic/claude-sonnet-4.6")
        assert created.gateway_managed is True
        assert created.is_active is False
        assert created.gateway_available is True

        retired = AIModel.objects.get(model_id="openai/retired-model")
        assert retired.gateway_available is False
        assert retired.is_active is False


class GameAPITest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="player1", password="pass1234")
        self.user2 = User.objects.create_user(username="player2", password="pass1234")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client2 = APIClient()
        self.client2.force_authenticate(user=self.user2)
        self.ai_model = AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="GPT-5 Mini",
            cost_per_game=1,
            tags=["tool-use"],
            pricing={"input": "0.000001", "output": "0.000002"},
        )

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
    def test_apply_ai_move_returns_billing(self, mock_submit_move, mock_get_state) -> None:
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
        assert resp.json()["billing"]["charge_source"] == "token_usage"
        assert resp.json()["billing"]["charged_credits"] == "0.14"
        assert resp.json()["state"]["last_move_billing"]["charged_usd"] == resp.json()["billing"]["charged_usd"]

        profile = self.client.get("/api/auth/me/")
        assert profile.status_code == 200
        assert profile.json()["credit_balance"] == "99.86"

    def test_charge_ai_turn_endpoint_deducts_credits(self) -> None:
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        resp = self.client.post(
            "/api/billing/charge-ai-turn/",
            {
                "game_id": game_id,
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
        assert resp.json()["charge_source"] == "token_usage"
        assert resp.json()["charged_credits"] == "0.14"

        profile = self.client.get("/api/auth/me/")
        assert profile.status_code == 200
        assert profile.json()["credit_balance"] == "99.86"

    def test_charge_ai_turn_accepts_nested_ai_sdk_usage_shape(self) -> None:
        create_resp = self.client.post("/api/game/create/", {
            "game_mode": "vs_ai",
            "ai_model_model_id": self.ai_model.model_id,
        })
        game_id = create_resp.json()["game_id"]

        resp = self.client.post(
            "/api/billing/charge-ai-turn/",
            {
                "game_id": game_id,
                "ai_metadata": {
                    "usage": {
                        "inputTokens": {
                            "total": 1200,
                            "noCache": 1000,
                            "cacheRead": 200,
                            "cacheWrite": 0,
                        },
                        "outputTokens": {
                            "total": 300,
                            "text": 240,
                            "reasoning": 60,
                        },
                        "totalTokens": 1500,
                    }
                },
            },
            format="json",
        )

        assert resp.status_code == 200
        assert resp.json()["charge_source"] == "token_usage"
        assert resp.json()["charged_credits"] == "0.16"
        assert resp.json()["input_tokens"] == 1200
        assert resp.json()["output_tokens"] == 300
        assert resp.json()["total_tokens"] == 1500

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

    def test_can_switch_game_ai_model_during_game(self) -> None:
        alternative_model = AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5.4",
            display_name="GPT-5.4",
            tags=["tool-use"],
            pricing={"input": "0.0000025", "output": "0.000015"},
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
            },
            format="json",
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["state"]["board"][7][7:10] == "JOE"
        assert len(data["state"]["my_rack"]) == 7
        assert data["state"]["current_turn_slot"] == 0

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
