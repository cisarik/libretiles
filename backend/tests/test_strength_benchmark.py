"""Deterministic ranked-search strength checks against the first-witness baseline.

This is an engine-to-engine regression benchmark, not evidence about human play.
The ordinary suite keeps four balanced games; the larger 100-game matrix is
explicitly opt-in because it exercises the real Collins search for several
minutes.
"""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from time import perf_counter

import pytest

from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.fastdict import load_prefix_index
from gamecore.game import GameEndReason
from gamecore.legality import evaluate_scoring_move
from gamecore.move_search import (
    DEFAULT_MAX_NODES, DEFAULT_RANKED_MAX_ELAPSED_MS, DEFAULT_RANKED_MAX_NODES,
    DEFAULT_RANKED_TOP_K, DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
)
from gamecore.tiles import get_tile_distribution
from gamecore.word_authority import WordAuthority
from gamecore.selfplay import (
    SelfPlayConfig, SelfPlayContext, simulate_engine_game, POLICY_WITNESS,
    POLICY_RANKED_WITNESS_SAFE, _tile_counter, _fingerprint as fingerprint,
)

_DICTIONARY_PATH = Path(get_assets_path()) / "dicts" / "collins2019.txt"
_INDEX = load_prefix_index(_DICTIONARY_PATH)
_EXPECTED_TILES = Counter(get_tile_distribution("english"))
_ALLOWED_END_REASONS = {
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES,
}
_SAFETY_SEARCH_MAX_ELAPSED_MS = 10_000

# Exact tuple pins use node bounds; production's wall-clock cap is load-sensitive.
_PARITY_RANKED_MAX_NODES = 20_000
_PARITY_MAX_ELAPSED_MS = 10_000_000
_MAX_PLIES = 200
_OPT_IN_ENV = "LIBRETILES_RUN_STRENGTH_ACCEPTANCE"


# Migrated fixture, identical expectations: one authority over the same index.
_AUTHORITY = WordAuthority.from_index(_INDEX)


_fingerprint = partial(fingerprint, include_pass_streak=True)


@dataclass(frozen=True)
class StrengthGameResult:
    seed: int
    strategy_slot: int
    plies: int
    ranked_score: int
    witness_score: int
    end_reason: GameEndReason

    @property
    def spread(self) -> int:
        return self.ranked_score - self.witness_score


def _simulate(
    seed: int, strategy_slot: int, *, node_bound: bool = False, late_game: bool = False,
) -> StrengthGameResult:
    assert strategy_slot in {0, 1}
    policies = [POLICY_WITNESS, POLICY_WITNESS]
    policies[strategy_slot] = POLICY_RANKED_WITNESS_SAFE
    sample = simulate_engine_game(
        SelfPlayConfig(
            variant_slug="english", seed=seed, policy_id=POLICY_RANKED_WITNESS_SAFE,
            max_plies=_MAX_PLIES, witness_max_elapsed_ms=(
                _PARITY_MAX_ELAPSED_MS if node_bound else _SAFETY_SEARCH_MAX_ELAPSED_MS
            ),
            witness_max_nodes=DEFAULT_MAX_NODES,
            ranked_max_elapsed_ms=(
                _PARITY_MAX_ELAPSED_MS if node_bound else DEFAULT_RANKED_MAX_ELAPSED_MS
            ),
            ranked_max_nodes=(
                _PARITY_RANKED_MAX_NODES if node_bound else DEFAULT_RANKED_MAX_NODES
            ),
            ranked_top_k=DEFAULT_RANKED_TOP_K,
            ranked_max_unique_placements=DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
            include_pass_streak=True, strict_unknown_tile=None,
            player_policy_ids=(policies[0], policies[1]), record_trace=True,
            # Pinned tuples below freeze the LEGACY policy; the strategic
            # late-game stack has its own enabled matrices.
            late_game_enabled=late_game,
        ),
        context=SelfPlayContext(
            authority=_AUTHORITY, letters=frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
            blank_letters=tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
            premiums_path=get_premiums_path(),
        ),
    )
    if node_bound:
        assert all(event.decision.elapsed_ms < _PARITY_MAX_ELAPSED_MS for event in sample.trace)
        # Strategic endgame decisions carry solver node accounting, not the
        # ranked traversal cap; the parity pin applies to the ranked path.
        capped = [
            event for event in sample.trace
            if not event.decision.complete and event.decision.strategy_mode is None
        ]
        assert all(event.decision.nodes == _PARITY_RANKED_MAX_NODES for event in capped)
        assert capped, "ranked parity must exercise the node bound"
    game = sample.initial_state
    assert game is not None
    players = game.players
    fingerprints = {_fingerprint(game)}

    assert strategy_slot in {0, 1}
    assert _tile_counter(game) == _EXPECTED_TILES

    for event in sample.trace:
        ply = event.ply
        game = event.before
        assert not game.ended, f"seed={seed} slot={strategy_slot} ply={ply}: post-terminal loop"
        acting_slot = game.current_index
        rack = game.current_player().rack.copy()
        context = f"seed={seed} strategy_slot={strategy_slot} ply={ply} acting={acting_slot}"

        assert _tile_counter(game) == _EXPECTED_TILES, f"{context}: pre-turn conservation"
        decision = event.decision
        move = decision.placements
        # Preserve the safety-search assertions formerly in _first_witness.
        assert decision.status != "indeterminate", (
            f"{context}: safety search capped nodes={decision.nodes} "
            f"elapsed_ms={decision.elapsed_ms}"
        )
        if decision.status == "none":
            assert decision.complete is True, context
        else:
            assert move is not None, context
        if acting_slot == strategy_slot and move is not None:
            assert decision.status == "found", context

        if move is not None:
            certified = evaluate_scoring_move(
                game.board, rack, move, authority=_AUTHORITY
            )
            assert certified.ok, f"{context}: selected move failed Collins certification"
            assert certified.total_score > 0, context
            assert event.awarded == certified.total_score, context

        game = event.after
        players = game.players

        assert _tile_counter(game) == _EXPECTED_TILES, f"{context}: post-turn conservation"
        if game.ended:
            assert game.current_index == acting_slot, f"{context}: terminal turn advanced"
        else:
            assert game.current_index == 1 - acting_slot, f"{context}: wrong acting slot"

        fingerprint = _fingerprint(game)
        assert fingerprint not in fingerprints, f"{context}: repeated full position"
        fingerprints.add(fingerprint)

        if game.ended:
            assert game.end_reason in _ALLOWED_END_REASONS, context
            assert sample.plies == ply
            assert sample.end_reason == game.end_reason.name
            assert sample.final_scores == game.scores()
            print(
                "selfplay-node-bound" if node_bound else "selfplay-production",
                (seed, strategy_slot, players[strategy_slot].score - players[1 - strategy_slot].score,
                 game.end_reason.name), flush=True,
            )
            return StrengthGameResult(
                seed=seed,
                strategy_slot=strategy_slot,
                plies=ply,
                ranked_score=players[strategy_slot].score,
                witness_score=players[1 - strategy_slot].score,
                end_reason=game.end_reason,
            )

    pytest.fail(
        f"seed={seed} strategy_slot={strategy_slot}: game exceeded {_MAX_PLIES} plies"
    )


def _run_matrix(seeds: range | tuple[int, ...], *, label: str) -> list[StrengthGameResult]:
    started = perf_counter()
    results = [
        _simulate(seed, strategy_slot)
        for seed in seeds
        for strategy_slot in (0, 1)
    ]
    elapsed = perf_counter() - started
    wins = sum(result.spread > 0 for result in results)
    draws = sum(result.spread == 0 for result in results)
    losses = sum(result.spread < 0 for result in results)
    total_spread = sum(result.spread for result in results)
    print(
        f"{label}: games={len(results)} W/D/L={wins}/{draws}/{losses} "
        f"total_spread={total_spread:+d} avg_spread={total_spread / len(results):+.2f} "
        f"elapsed={elapsed:.3f}s max_plies={max(result.plies for result in results)}"
    )
    return results


def test_ranked_strategy_beats_first_witness_on_default_balanced_seeds() -> None:
    results = _run_matrix((300, 301), label="strength-default")

    assert len(results) == 4
    assert all(result.spread > 0 for result in results)


def test_node_bound_strength_regression_tuples() -> None:
    """New candidate baselines under node bounds, separate from extraction-equivalence evidence."""
    results = [
        _simulate(seed, strategy_slot, node_bound=True)
        for seed in (300, 301) for strategy_slot in (0, 1)
    ]
    assert [
        (result.seed, result.strategy_slot, result.spread, result.end_reason.name)
        for result in results
    ] == [
        (300, 0, 583, "BAG_EMPTY_AND_PLAYER_OUT"),
        (300, 1, 419, "BAG_EMPTY_AND_PLAYER_OUT"),
        (301, 0, 282, "BAG_EMPTY_AND_PLAYER_OUT"),
        (301, 1, 515, "BAG_EMPTY_AND_PLAYER_OUT"),
    ]


def test_late_game_strategy_engages_and_terminates_on_default_seeds() -> None:
    """Node-bound late-game runs: deterministic evidence, allowed terminals."""
    results = [
        _simulate(seed, strategy_slot, node_bound=True, late_game=True)
        for seed in (300, 301) for strategy_slot in (0, 1)
    ]
    for result in results:
        assert result.end_reason in _ALLOWED_END_REASONS
        assert 0 < result.plies <= _MAX_PLIES
    total = sum(result.spread for result in results)
    print(
        "strength-late-game "
        + " ".join(
            f"(seed={r.seed},slot={r.strategy_slot},spread={r.spread:+d},{r.end_reason.name})"
            for r in results
        )
        + f" total={total:+d}",
        flush=True,
    )
    repeat = _simulate(300, 0, node_bound=True, late_game=True)
    assert repeat == results[0]


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get(_OPT_IN_ENV) != "1",
    reason=f"set {_OPT_IN_ENV}=1 for the 100-game strength acceptance",
)
def test_ranked_strategy_one_hundred_game_acceptance() -> None:
    results = _run_matrix(range(300, 350), label="strength-acceptance-100")

    wins = sum(result.spread > 0 for result in results)
    losses = sum(result.spread < 0 for result in results)
    assert len(results) == 100
    assert sum(result.spread for result in results) > 0
    assert wins > losses


@pytest.mark.parametrize("status,complete", [("none", True), ("indeterminate", False)])
def test_ranked_safety_fallback_preserves_policy_and_bounds(
    monkeypatch: pytest.MonkeyPatch, status: str, complete: bool,
) -> None:
    from dataclasses import replace
    from gamecore import selfplay
    from gamecore.board import Board
    from gamecore.game import Game, PlayerState
    from gamecore.move_search import RankedSearchResult, SearchResult
    from gamecore.tiles import TileBag

    calls = []
    ranked = RankedSearchResult(status, (), 12, 3, complete, 0)
    witness = SearchResult("none", None, (), 0, 23, 4, True)

    def ranked_search(*args, **kwargs):
        calls.append(("ranked", kwargs))
        return ranked

    def witness_search(*args, **kwargs):
        calls.append(("witness", kwargs))
        return witness

    monkeypatch.setattr(selfplay, "find_ranked_scoring_moves", ranked_search)
    monkeypatch.setattr(selfplay, "find_legal_scoring_move", witness_search)
    config = SelfPlayConfig(
        variant_slug="english", seed=0, policy_id=POLICY_RANKED_WITNESS_SAFE,
        max_plies=_MAX_PLIES, witness_max_elapsed_ms=_SAFETY_SEARCH_MAX_ELAPSED_MS,
        witness_max_nodes=DEFAULT_MAX_NODES,
        ranked_max_elapsed_ms=DEFAULT_RANKED_MAX_ELAPSED_MS,
        ranked_max_nodes=DEFAULT_RANKED_MAX_NODES,
        ranked_top_k=DEFAULT_RANKED_TOP_K,
        ranked_max_unique_placements=DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
        include_pass_streak=True, strict_unknown_tile=None,
    )
    context = SelfPlayContext(
        authority=_AUTHORITY, letters=frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        blank_letters=tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ"), premiums_path=get_premiums_path(),
    )
    game = Game(board=Board(), bag=TileBag(seed=0),
                players=[PlayerState(name="P0", rack=["Q"])])
    decision = selfplay._choose(config.policy_id, game, ["Q"], context, config)
    assert [kind for kind, _ in calls] == ["ranked", "witness"]
    assert decision.status == "none" and decision.complete is True
    assert decision.nodes == 35 and decision.elapsed_ms == 7
    assert calls[0][1]["max_nodes"] == DEFAULT_RANKED_MAX_NODES
    assert calls[0][1]["max_elapsed_ms"] == DEFAULT_RANKED_MAX_ELAPSED_MS
    assert calls[0][1]["max_unique_placements"] == DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS
    assert calls[1][1]["max_nodes"] == DEFAULT_MAX_NODES
    assert calls[1][1]["max_elapsed_ms"] == _SAFETY_SEARCH_MAX_ELAPSED_MS
    calls.clear()
    pure = replace(config, policy_id=selfplay.POLICY_RANKED_BEST)
    decision = selfplay._choose(pure.policy_id, game, ["Q"], context, pure)
    assert [kind for kind, _ in calls] == ["ranked"]
    assert decision.status == status and decision.complete is complete
