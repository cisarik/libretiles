"""Django service integration for midgame board-control ranking."""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from game.models import GameSession
from gamecore.move_search import RankedSearchResult


class BoardDefenseServiceTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="defender", password="pass1234")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _ai_turn_game(self) -> str:
        game_id = self.client.post(
            "/api/game/create/", {"game_mode": "vs_ai"}
        ).json()["game_id"]
        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 1
        session.save(update_fields=["current_turn_slot"])
        return game_id

    @patch("game.services.find_ranked_scoring_moves")
    def test_probe_enables_defense_and_derives_the_score_differential(
        self, mock_ranked: Any
    ) -> None:
        mock_ranked.return_value = RankedSearchResult(
            status="none",
            candidates=(),
            nodes=1,
            elapsed_ms=1,
            complete=True,
            unique_placements=0,
            strategy_mode="board_control",
        )
        game_id = self._ai_turn_game()
        session = GameSession.objects.get(public_id=game_id)
        ai_slot = session.slots.get(slot=1)
        human_slot = session.slots.get(slot=0)
        ai_slot.score = 90
        human_slot.score = 30
        ai_slot.save(update_fields=["score"])
        human_slot.save(update_fields=["score"])

        response = self.client.get(f"/api/game/{game_id}/ai-candidates/")

        assert response.status_code == 200
        kwargs = mock_ranked.call_args.kwargs
        assert kwargs["board_defense_enabled"] is True
        assert kwargs["score_differential"] == 60
        data = response.json()
        assert data["strategy_mode"] == "board_control"
        assert "strategy_mode" not in data["search"]

    @patch("game.services.find_ranked_scoring_moves")
    def test_probe_uses_zero_differential_on_a_tied_opening(
        self, mock_ranked: Any
    ) -> None:
        mock_ranked.return_value = RankedSearchResult(
            status="none",
            candidates=(),
            nodes=1,
            elapsed_ms=1,
            complete=True,
            unique_placements=0,
        )
        game_id = self._ai_turn_game()

        response = self.client.get(f"/api/game/{game_id}/ai-candidates/")

        assert response.status_code == 200
        assert mock_ranked.call_args.kwargs["score_differential"] == 0
        assert mock_ranked.call_args.kwargs["board_defense_enabled"] is True

    def test_fresh_midgame_candidates_carry_board_control(self) -> None:
        game_id = self._ai_turn_game()

        response = self.client.get(f"/api/game/{game_id}/ai-candidates/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] in {"found", "none", "indeterminate"}
        if data["status"] == "found":
            assert data["strategy_mode"] == "board_control"
            assert "strategy_mode" not in data["search"]
            assert set(data["search"]) == {
                "complete",
                "nodes",
                "elapsed_ms",
                "unique_placements",
                "candidate_count",
            }
