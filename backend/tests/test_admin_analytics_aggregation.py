from __future__ import annotations

from django.test import TestCase

from catalog.models import AIModel, AIPrompt
from game.analytics import build_admin_analytics
from game.models import GameSession, Move, PlayerSlot, PlaygroundSimulation


class AdminAnalyticsAggregationTests(TestCase):
    def test_playground_outcomes_runtime_authorship_and_recommendations(self) -> None:
        model = AIModel.objects.create(provider="openrouter", model_id="google/gemma-4-31b-it:free", display_name="Gemma", tags=["tools"], sort_order=10)
        prompt = AIPrompt.objects.get(name="Initial")
        game = GameSession.objects.create(status="finished", game_over=True, winner_slot=0, variant_slug="english")
        first = PlayerSlot.objects.create(game=game, slot=0, is_ai=True, score=42, ai_model=model, ai_prompt=prompt)
        PlayerSlot.objects.create(game=game, slot=1, is_ai=True, score=31)
        PlaygroundSimulation.objects.create(created_by_id=self._user_id(), game=game, ended_at=game.created_at, config_json={"slots": [{"kind": "llm", "provider": model.provider, "model_id": model.model_id, "display_name": model.display_name, "prompt_id": prompt.id, "prompt_name": prompt.name}, {"kind": "cpu", "provider": "engine", "model_id": "engine/cpu", "display_name": "CPU Master", "prompt_id": None, "prompt_name": None}]})
        Move.objects.create(game=game, player_slot=first, seq=1, kind="place", points=12, ai_metadata={"runtime_provider": model.provider, "runtime_model_id": model.model_id, "completion_source": "provider_candidate", "inspection_trace": {"version": 1, "attempts": [{"attempt_index": 0, "provider": model.provider, "model_id": model.model_id, "latency_ms": 250, "provider_requests_used": 2}]}})

        result = build_admin_analytics(days=30, source="all", variant_slug="all")
        row = next(item for item in result["models"] if item["model_id"] == model.model_id)
        assert result["summary"]["total_games"] == 1
        assert result["summary"]["total_plies"] == 1
        assert row["wins"] == 1
        assert row["avg_spread"] == 11.0
        assert row["provider_candidate_pct"] == 100.0
        assert row["avg_attempt_latency_ms"] == 250.0
        assert row["avg_provider_requests_per_turn"] == 2.0
        assert result["recommendations"]["offline_cpu"]["model_id"] == "engine/cpu"
        assert next(item for item in result["presets"] if item["name"] == "Initial")["wins"] == 1

    def _user_id(self) -> int:
        from accounts.models import User
        return User.objects.create_user(username="aggregation-admin", password="pass1234", is_staff=True).id
