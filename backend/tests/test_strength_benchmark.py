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
from pathlib import Path
from time import perf_counter

import pytest

from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.board import Board
from gamecore.fastdict import load_prefix_index
from gamecore.game import Game, GameEndReason, PlayerState
from gamecore.legality import evaluate_scoring_move
from gamecore.move_search import find_legal_scoring_move, find_ranked_scoring_moves
from gamecore.tiles import TileBag, get_tile_distribution
from gamecore.word_authority import WordAuthority
from gamecore.types import Placement

_DICTIONARY_PATH = Path(get_assets_path()) / "dicts" / "collins2019.txt"
_INDEX = load_prefix_index(_DICTIONARY_PATH)
_EXPECTED_TILES = Counter(get_tile_distribution("english"))
_ALLOWED_END_REASONS = {
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES,
}
_SAFETY_SEARCH_MAX_ELAPSED_MS = 10_000
_MAX_PLIES = 200
_OPT_IN_ENV = "LIBRETILES_RUN_STRENGTH_ACCEPTANCE"


# Migrated fixture, identical expectations: one authority over the same index.
_AUTHORITY = WordAuthority.from_index(_INDEX)


def _tile_counter(game: Game) -> Counter[str]:
    tiles = Counter(game.bag.tiles)
    for player in game.players:
        tiles.update(player.rack)
    for row in game.board.cells:
        for cell in row:
            if cell.letter:
                tiles.update(["?" if cell.is_blank else cell.letter])
    return tiles


def _fingerprint(game: Game) -> tuple[object, ...]:
    board = tuple(
        (cell.letter, cell.is_blank, cell.premium, cell.premium_used)
        for row in game.board.cells
        for cell in row
    )
    return (
        board,
        tuple(game.bag.tiles),
        tuple(tuple(player.rack) for player in game.players),
        tuple((player.score, player.pass_streak) for player in game.players),
        game.current_index,
        game.consecutive_scoreless_turns,
    )


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


def _first_witness(game: Game, rack: list[str], context: str) -> tuple[Placement, ...] | None:
    result = find_legal_scoring_move(
        game.board,
        rack,
        authority=_AUTHORITY,
        max_elapsed_ms=_SAFETY_SEARCH_MAX_ELAPSED_MS,
    )
    assert result.status != "indeterminate", (
        f"{context}: safety search capped nodes={result.nodes} "
        f"elapsed_ms={result.elapsed_ms}"
    )
    if result.status == "none":
        assert result.complete is True, context
        return None
    assert result.witness is not None, context
    return result.witness


def _strategy_move(
    game: Game,
    rack: list[str],
    *,
    use_ranked: bool,
    context: str,
) -> tuple[Placement, ...] | None:
    if use_ranked:
        ranked = find_ranked_scoring_moves(
            game.board,
            rack,
            authority=_AUTHORITY,
            bag_count=game.bag.remaining(),
        )
        if ranked.candidates:
            assert ranked.status == "found", context
            return ranked.candidates[0].placements

    # Ranked search is a quality path only. Its none/indeterminate status never
    # authorizes exchange or pass; the unchanged first-witness safety search does.
    return _first_witness(game, rack, context)


def _simulate(seed: int, strategy_slot: int) -> StrengthGameResult:
    bag = TileBag(seed=seed, variant="english")
    players = [
        PlayerState(name="P0", rack=bag.draw(7)),
        PlayerState(name="P1", rack=bag.draw(7)),
    ]
    game = Game(
        board=Board(get_premiums_path()),
        bag=bag,
        players=players,
        starting_index=seed % 2,
    )
    fingerprints = {_fingerprint(game)}

    assert strategy_slot in {0, 1}
    assert _tile_counter(game) == _EXPECTED_TILES

    for ply in range(1, _MAX_PLIES + 1):
        assert not game.ended, f"seed={seed} slot={strategy_slot} ply={ply}: post-terminal loop"
        acting_slot = game.current_index
        rack = game.current_player().rack.copy()
        context = f"seed={seed} strategy_slot={strategy_slot} ply={ply} acting={acting_slot}"

        assert _tile_counter(game) == _EXPECTED_TILES, f"{context}: pre-turn conservation"
        move = _strategy_move(
            game,
            rack,
            use_ranked=acting_slot == strategy_slot,
            context=context,
        )

        if move is not None:
            certified = evaluate_scoring_move(
                game.board, rack, move, authority=_AUTHORITY
            )
            assert certified.ok, f"{context}: selected move failed Collins certification"
            assert certified.total_score > 0, context
            assert game.play_move(move) == certified.total_score, context
        elif game.bag.remaining() >= 7:
            game.exchange_turn(rack)
        else:
            game.pass_turn()

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
