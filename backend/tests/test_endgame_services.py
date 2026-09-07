"""Django service integration for late-game strategic candidates.

`_probe_ai_ranked_candidates` must hand the ranked search a validated
``LateGameContext`` built from PUBLIC session state (opponent rack SIZE only,
never its contents inside the context), and the candidates payload must carry
the strategy marker exactly when a strategic search ran.

The late-game context validates the WHOLE physical inventory, so mounted
positions come from a deterministic node-bound self-play game rather than a
toy board: only a complete, conserving position can enter the window.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from game.diagnostics import load_variant_context
from game.models import GameSession
from gamecore.assets import get_premiums_path
from gamecore.move_search import (
    DEFAULT_MAX_NODES,
    DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
    DEFAULT_RANKED_TOP_K,
)
from gamecore.selfplay import (
    POLICY_RANKED_BEST,
    SelfPlayConfig,
    SelfPlayContext,
    simulate_engine_game,
)

_PARITY_RANKED_MAX_NODES = 20_000
_PARITY_MAX_ELAPSED_MS = 10_000_000


class _MountedPosition:
    def __init__(
        self,
        board: list[list[dict[str, Any] | None]],
        ai_rack: list[str],
        human_rack: list[str],
        bag_tiles: list[str],
    ) -> None:
        self.board = board
        self.ai_rack = ai_rack
        self.human_rack = human_rack
        self.bag_tiles = bag_tiles


def _grid_from_board(board: Any) -> list[list[dict[str, Any] | None]]:
    grid: list[list[dict[str, Any] | None]] = []
    for row in board.cells:
        cells: list[dict[str, Any] | None] = []
        for cell in row:
            if cell.token is None:
                cells.append(None)
            else:
                cells.append({"token": cell.token, "blank_as": cell.blank_as})
        grid.append(cells)
    return grid


@lru_cache(maxsize=1)
def _late_game_positions() -> dict[str, _MountedPosition]:
    """First empty-bag ply and first 1..7-bag ply of a deterministic game.

    Legacy search (late_game_enabled=False) generates the positions; the
    Django probe under test then re-enters them through the strategic path.
    """
    context = load_variant_context("english")
    sample = simulate_engine_game(
        SelfPlayConfig(
            variant_slug="english",
            seed=0,
            policy_id=POLICY_RANKED_BEST,
            max_plies=200,
            witness_max_elapsed_ms=_PARITY_MAX_ELAPSED_MS,
            witness_max_nodes=DEFAULT_MAX_NODES,
            ranked_max_elapsed_ms=_PARITY_MAX_ELAPSED_MS,
            ranked_max_nodes=_PARITY_RANKED_MAX_NODES,
            ranked_top_k=DEFAULT_RANKED_TOP_K,
            ranked_max_unique_placements=DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
            include_pass_streak=False,
            strict_unknown_tile=False,
            record_trace=True,
            late_game_enabled=False,
        ),
        context=SelfPlayContext(
            authority=context.authority,
            letters=context.letters,
            blank_letters=tuple(context.variant.playable_letters),
            premiums_path=get_premiums_path(),
        ),
    )
    positions: dict[str, _MountedPosition] = {}
    for event in sample.trace:
        game = event.before
        bag = game.bag.remaining()
        if event.decision.placements is None:
            continue
        acting = game.current_player()
        opponent = game.players[1 - game.current_index]
        mounted = _MountedPosition(
            board=_grid_from_board(game.board),
            ai_rack=list(acting.rack),
            human_rack=list(opponent.rack),
            bag_tiles=list(game.bag.tiles),
        )
        if bag == 0 and "empty" not in positions:
            positions["empty"] = mounted
        if 1 <= bag <= 7 and "pre" not in positions:
            positions["pre"] = mounted
        if {"empty", "pre"} <= positions.keys():
            break
    assert {"empty", "pre"} <= positions.keys(), "seed 0 must reach the late game"
    return positions


class EndgameServiceTest(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="endgamer", password="pass1234")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def _mounted_session(self, position: _MountedPosition) -> str:
        game_id = self.client.post(
            "/api/game/create/", {"game_mode": "vs_ai"}
        ).json()["game_id"]
        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 1
        session.bag_tiles = position.bag_tiles
        session.board_state = position.board
        session.save(update_fields=["current_turn_slot", "bag_tiles", "board_state"])
        ai_slot = session.slots.get(slot=1)
        ai_slot.rack = position.ai_rack
        ai_slot.save(update_fields=["rack"])
        human_slot = session.slots.get(slot=0)
        human_slot.rack = position.human_rack
        human_slot.save(update_fields=["rack"])
        return game_id

    @patch("game.services.find_ranked_scoring_moves")
    def test_probe_builds_public_late_game_context_for_empty_bag(
        self, mock_ranked: Any
    ) -> None:
        from gamecore.move_search import RankedSearchResult
        from gamecore.tile_tracking import LateGameContext

        mock_ranked.return_value = RankedSearchResult(
            status="none",
            candidates=(),
            nodes=1,
            elapsed_ms=1,
            complete=True,
            unique_placements=0,
        )
        position = _late_game_positions()["empty"]
        game_id = self._mounted_session(position)

        response = self.client.get(f"/api/game/{game_id}/ai-candidates/")

        assert response.status_code == 200
        context = mock_ranked.call_args.kwargs["late_game_context"]
        assert isinstance(context, LateGameContext)
        assert context.bag_remaining == 0
        assert context.opponent_rack_size == len(position.human_rack)
        # The opponent seat is human: voluntary passes are modeled.
        assert context.opponent_action_rules == "human_open"
        # Empty bag: the public deduction IS the opponent rack.
        assert context.exact_opponent_rack() == tuple(sorted(position.human_rack))

    @patch("game.services.find_ranked_scoring_moves")
    def test_probe_passes_none_context_outside_the_late_game_window(
        self, mock_ranked: Any
    ) -> None:
        from gamecore.move_search import RankedSearchResult

        mock_ranked.return_value = RankedSearchResult(
            status="none",
            candidates=(),
            nodes=1,
            elapsed_ms=1,
            complete=True,
            unique_placements=0,
        )
        # A fresh vs_ai game keeps its full drawn bag (> 7 tiles).
        game_id = self.client.post(
            "/api/game/create/", {"game_mode": "vs_ai"}
        ).json()["game_id"]
        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 1
        session.save(update_fields=["current_turn_slot"])

        response = self.client.get(f"/api/game/{game_id}/ai-candidates/")

        assert response.status_code == 200
        assert mock_ranked.call_args.kwargs["late_game_context"] is None
        # No strategic search ran: the payload shape stays legacy.
        assert "strategy_mode" not in response.json()
        assert "strategy_mode" not in response.json()["search"]

    def test_empty_bag_candidates_carry_the_strategy_marker(self) -> None:
        game_id = self._mounted_session(_late_game_positions()["empty"])

        response = self.client.get(f"/api/game/{game_id}/ai-candidates/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "found"
        assert data["candidates"]
        assert data["strategy_mode"] in {"exact", "bounded"}
        assert data["search"]["strategy_mode"] == data["strategy_mode"]
        assert data["search"]["out_in_two"] in {"proven", "refuted", "unknown"}
        assert data["search"]["completed_depth"] >= 0
        # Private state stays private even on the strategic path.
        body = response.content.decode()
        assert "bag_tiles" not in body
        assert "opponent" not in body

    def test_pre_endgame_bag_marks_candidates_pre_endgame(self) -> None:
        game_id = self._mounted_session(_late_game_positions()["pre"])

        response = self.client.get(f"/api/game/{game_id}/ai-candidates/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "found"
        assert data["strategy_mode"] == "pre_endgame"
        assert data["search"]["strategy_mode"] == "pre_endgame"

    def test_inconsistent_public_state_degrades_to_ordinary_search(self) -> None:
        # Corrupting the acting rack breaks physical conservation; the context
        # builder fails closed and the ordinary ranked search still answers.
        position = _late_game_positions()["empty"]
        game_id = self._mounted_session(position)
        session = GameSession.objects.get(public_id=game_id)
        ai_slot = session.slots.get(slot=1)
        ai_slot.rack = ["Z", "Z", "Z"]
        ai_slot.save(update_fields=["rack"])

        response = self.client.get(f"/api/game/{game_id}/ai-candidates/")

        assert response.status_code == 200
        data = response.json()
        assert "strategy_mode" not in data
        assert "strategy_mode" not in data["search"]
