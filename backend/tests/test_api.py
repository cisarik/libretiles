"""Django REST API tests — test the full request/response cycle."""

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
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


class CatalogAPITest(TestCase):
    def test_list_models(self) -> None:
        AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="GPT-5 Mini",
            cost_per_game=1,
            is_active=True,
        )
        AIModel.objects.create(
            provider="google",
            model_id="google/gemini-pro",
            display_name="Gemini Pro",
            cost_per_game=2,
            is_active=False,
        )
        resp = self.client.get("/api/catalog/models/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["model_id"] == "openai/gpt-5-mini"


class GameAPITest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="player1", password="pass1234")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.ai_model = AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="GPT-5 Mini",
            cost_per_game=1,
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
        assert len(data["human_rack"]) == 7

    def test_get_game_state(self) -> None:
        create_resp = self.client.post("/api/game/create/", {"game_mode": "vs_ai"})
        game_id = create_resp.json()["game_id"]

        resp = self.client.get(f"/api/game/{game_id}/?slot=0")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "active"
        assert len(data["slots"]) == 2
        assert data["bag_remaining"] < 100
        assert len(data["my_rack"]) == 7

    def test_submit_pass(self) -> None:
        create_resp = self.client.post("/api/game/create/", {"game_mode": "vs_ai"})
        game_id = create_resp.json()["game_id"]
        turn_slot = create_resp.json()["current_turn_slot"]

        resp = self.client.post(f"/api/game/{game_id}/pass/", {"slot": turn_slot})
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
                "slot": 0,
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
        assert data["state"]["current_turn_slot"] == 1

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
