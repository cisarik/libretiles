from __future__ import annotations

from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from game import simulations
from game.models import GameSession, Move, PlaygroundSimulation
from gamecore.move_search import RankedMoveCandidate, RankedSearchResult
from gamecore.types import Placement


class SimulationServiceTests(TestCase):
    def setUp(self) -> None:
        self.staff = User.objects.create_user(
            username="simulation-owner", password="pass1234", is_staff=True
        )

    def create(self, *, slot0: dict[str, object] | None = None) -> PlaygroundSimulation:
        return simulations.create_playground_simulation(
            created_by_id=self.staff.id,
            slot0=slot0 or {"kind": "cpu"},
            slot1={"kind": "cpu"},
            variant_slug="english",
            seed=0,
            ai_timeout=30,
            ai_max_steps=10,
        )

    def test_fixed_seed_creates_reproducible_two_ai_session(self) -> None:
        first = self.create()
        first_state = simulations.serialize_simulation_state(
            simulations.get_playground_simulation(str(first.game.public_id))
        )
        simulations.stop_playground_simulation(
            game_id=str(first.game.public_id), user_id=self.staff.id
        )
        second = self.create()
        second_state = simulations.serialize_simulation_state(
            simulations.get_playground_simulation(str(second.game.public_id))
        )
        assert first_state["racks"] == second_state["racks"]
        assert first_state["current_turn_slot"] == second_state["current_turn_slot"]
        assert second.game.slots.filter(is_ai=True).count() == 2
        assert second.game.replay_initial_state is not None

    def test_only_one_unfinished_simulation_per_creator(self) -> None:
        first = self.create()
        with self.assertRaises(simulations.SimulationConflictError) as raised:
            self.create()
        assert raised.exception.game_id == str(first.game.public_id)

    def test_cpu_step_commits_ranked_candidate_with_zero_provider_requests(self) -> None:
        simulation = self.create()
        placements = (Placement(row=7, col=7, letter="A"), Placement(row=7, col=8, letter="T"))
        candidate = RankedMoveCandidate(
            placements=placements,
            words=("AT",),
            total_score=4,
            tiles_used=2,
            leave_equity_cp=0,
            rack_out=False,
            canonical_key=((7, 7, "A", ""), (7, 8, "T", "")),
        )
        ranked = RankedSearchResult(
            status="found",
            candidates=(candidate,),
            nodes=1,
            elapsed_ms=1,
            complete=True,
            unique_placements=1,
        )
        acting = simulation.game.slots.get(slot=simulation.game.current_turn_slot)
        acting.rack = ["A", "T", "C", "D", "E", "F", "G"]
        acting.save(update_fields=["rack"])
        with patch("game.services._probe_ai_ranked_candidates", return_value=ranked):
            result = simulations.step_playground_simulation(
                game_id=str(simulation.game.public_id),
                user_id=self.staff.id,
                expected_move_count=0,
            )
        assert result["kind"] == "cpu"
        move = Move.objects.get(game=simulation.game)
        assert move.ai_metadata["provider_requests_used"] == 0
        assert move.ai_metadata["completion_source"] == "backend_ranked_candidate"

    def test_stop_is_idempotent_and_preserves_position(self) -> None:
        simulation = self.create()
        game_id = str(simulation.game.public_id)
        first = simulations.stop_playground_simulation(game_id=game_id, user_id=self.staff.id)
        second = simulations.stop_playground_simulation(game_id=game_id, user_id=self.staff.id)
        assert first.game.game_end_reason == "simulation_stopped"
        assert second.ended_at == first.ended_at
        assert GameSession.objects.get(public_id=game_id).status == "abandoned"
