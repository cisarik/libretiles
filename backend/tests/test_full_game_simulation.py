"""Deterministic complete games through the real engine and Collins search."""

from __future__ import annotations

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
from gamecore.move_search import DEFAULT_MAX_NODES, find_legal_scoring_move
from gamecore.tiles import TileBag, get_tile_distribution, get_tile_points

_DICTIONARY_PATH = Path(get_assets_path()) / "dicts" / "collins2019.txt"
_INDEX = load_prefix_index(_DICTIONARY_PATH)
_EXPECTED_TILES = Counter(get_tile_distribution("english"))
_TILE_POINTS = get_tile_points("english")
_ALLOWED_END_REASONS = {
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES,
}
_ACCEPTANCE_SEARCH_MAX_ELAPSED_MS = 10_000


def _is_word(word: str) -> bool:
    folded = word.strip().casefold()
    return (
        len(folded) >= 2
        and folded.isascii()
        and folded.isalpha()
        and _INDEX.contains(folded)
    )


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
        tuple(player.score for player in game.players),
        game.current_index,
        game.consecutive_scoreless_turns,
    )


def _rack_points(rack: list[str]) -> int:
    return sum(_TILE_POINTS[tile] for tile in rack)


@dataclass(frozen=True)
class SimulationResult:
    seed: int
    plies: int
    end_reason: GameEndReason


def _simulate(seed: int, *, max_plies: int = 200) -> SimulationResult:
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
    placement_scores = [0, 0]
    fingerprints = {_fingerprint(game)}
    terminal_transitions = 0

    assert _tile_counter(game) == _EXPECTED_TILES, f"seed={seed} initial conservation"

    for ply in range(1, max_plies + 1):
        assert not game.ended, f"seed={seed} ply={ply} entered loop after terminal"
        acting_index = game.current_index
        acting = game.current_player()
        score_before = tuple(player.score for player in players)
        rack_before = acting.rack.copy()
        bag_before = game.bag.remaining()
        scoreless_before = game.consecutive_scoreless_turns
        pass_streak_before = acting.pass_streak
        assert _tile_counter(game) == _EXPECTED_TILES, (
            f"seed={seed} ply={ply} pre-action conservation"
        )

        search = find_legal_scoring_move(
            game.board,
            rack_before,
            is_word=_is_word,
            has_prefix=_INDEX.has_prefix,
            max_nodes=DEFAULT_MAX_NODES,
            max_elapsed_ms=_ACCEPTANCE_SEARCH_MAX_ELAPSED_MS,
        )
        context = (
            f"seed={seed} ply={ply} status={search.status} nodes={search.nodes} "
            f"elapsed_ms={search.elapsed_ms}"
        )

        if search.status == "indeterminate":
            pytest.fail(f"{context}: bounded search must not authorize a non-scoring action")

        if search.status == "found":
            assert search.witness is not None, context
            legality = evaluate_scoring_move(
                game.board,
                rack_before,
                search.witness,
                _is_word,
            )
            assert legality.ok, f"{context}: witness failed re-certification: {legality}"
            assert legality.total_score == search.total_score, context
            awarded = game.play_move(search.witness)
            assert awarded == legality.total_score, context
            placement_scores[acting_index] += awarded
            assert game.consecutive_scoreless_turns == 0, context
            assert acting.pass_streak == 0, context
            if not game.ended:
                assert acting.score - score_before[acting_index] == awarded, context
        elif bag_before >= 7:
            assert search.complete is True, context
            game.exchange_turn(rack_before)
            assert game.consecutive_scoreless_turns == scoreless_before + 1, context
            assert acting.pass_streak == 0, context
            if not game.ended:
                assert tuple(player.score for player in players) == score_before, context
        else:
            assert search.status == "none" and search.complete is True, context
            game.pass_turn()
            assert game.consecutive_scoreless_turns == scoreless_before + 1, context
            assert acting.pass_streak == pass_streak_before + 1, context
            if not game.ended:
                assert tuple(player.score for player in players) == score_before, context

        assert _tile_counter(game) == _EXPECTED_TILES, (
            f"{context}: post-action conservation differs: {_tile_counter(game)}"
        )
        if game.ended:
            terminal_transitions += 1
            assert game.current_index == acting_index, context
        else:
            assert game.current_index == (acting_index + 1) % len(players), context

        fingerprint = _fingerprint(game)
        assert fingerprint not in fingerprints, f"{context}: repeated full position"
        fingerprints.add(fingerprint)

        if game.ended:
            assert terminal_transitions == 1, context
            assert game.end_reason in _ALLOWED_END_REASONS, context

            expected_scores = placement_scores.copy()
            leftovers = [_rack_points(player.rack) for player in players]
            for index, leftover in enumerate(leftovers):
                expected_scores[index] -= leftover
            if game.end_reason is GameEndReason.BAG_EMPTY_AND_PLAYER_OUT:
                finishers = [index for index, player in enumerate(players) if not player.rack]
                assert len(finishers) == 1, context
                finisher = finishers[0]
                expected_scores[finisher] += sum(
                    leftover for index, leftover in enumerate(leftovers) if index != finisher
                )
            else:
                assert all(player.rack for player in players), context

            assert [player.score for player in players] == expected_scores, context
            top_score = max(expected_scores)
            leaders = [index for index, score in enumerate(expected_scores) if score == top_score]
            expected_winner = players[leaders[0]].name if len(leaders) == 1 else None
            assert game.winner_name == expected_winner, context
            return SimulationResult(seed=seed, plies=ply, end_reason=game.end_reason)

    pytest.fail(f"seed={seed}: game did not terminate within {max_plies} plies")


def _run_seeds(seeds: range, *, label: str) -> list[SimulationResult]:
    started = perf_counter()
    results = [_simulate(seed) for seed in seeds]
    elapsed = perf_counter() - started
    distribution = Counter(result.end_reason.name for result in results)
    max_plies = max(result.plies for result in results)
    print(
        f"{label}: games={len(results)} elapsed={elapsed:.3f}s max_plies={max_plies} "
        f"end_reasons={dict(sorted(distribution.items()))} indeterminate=0"
    )
    return results


def test_ci_twenty_seed_complete_games() -> None:
    results = _run_seeds(range(20), label="ci-20")
    assert len(results) == 20


@pytest.mark.slow
def test_acceptance_one_hundred_seed_complete_games() -> None:
    results = _run_seeds(range(100), label="acceptance-100")
    assert len(results) == 100
