"""Deterministic complete games through the real engine and Collins search."""

from __future__ import annotations

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
from gamecore.tiles import get_tile_distribution, get_tile_points
from gamecore.word_authority import WordAuthority
from gamecore.selfplay import (
    SelfPlayConfig, SelfPlayContext, simulate_engine_game,
    POLICY_WITNESS, _tile_counter, _fingerprint as fingerprint,
    _rack_points as rack_points,
)
from tests.opt_in import requires_simulation

_DICTIONARY_PATH = Path(get_assets_path()) / "dicts" / "collins2019.txt"
_INDEX = load_prefix_index(_DICTIONARY_PATH)
_EXPECTED_TILES = Counter(get_tile_distribution("english"))
_TILE_POINTS = get_tile_points("english")
_ALLOWED_END_REASONS = {
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES,
}
_ACCEPTANCE_SEARCH_MAX_ELAPSED_MS = 10_000

# Exact tuple pins use node bounds; production's wall-clock cap is load-sensitive.
_PARITY_RANKED_MAX_NODES = 20_000
_PARITY_MAX_ELAPSED_MS = 10_000_000


# Migrated fixture, identical expectations: the injected Collins callable became
# the one authority over the same index. English tiles are all ASCII letters, so
# the dropped `isascii` clause cannot change a verdict reachable from this rack.
_AUTHORITY = WordAuthority.from_index(_INDEX)


_fingerprint = partial(fingerprint, include_pass_streak=False)
_rack_points = partial(rack_points, points=_TILE_POINTS, strict_unknown_tile=True)


@dataclass(frozen=True)
class SimulationResult:
    seed: int
    plies: int
    end_reason: GameEndReason


def _simulate(
    seed: int, *, max_plies: int = 200, node_bound: bool = False,
) -> SimulationResult:
    sample = simulate_engine_game(
        SelfPlayConfig(
            variant_slug="english", seed=seed, policy_id=POLICY_WITNESS, max_plies=max_plies,
            witness_max_elapsed_ms=(
                _PARITY_MAX_ELAPSED_MS if node_bound else _ACCEPTANCE_SEARCH_MAX_ELAPSED_MS
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
            include_pass_streak=False, strict_unknown_tile=True,
            record_trace=True,
        ),
        context=SelfPlayContext(
            authority=_AUTHORITY, letters=frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
            blank_letters=tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
            premiums_path=get_premiums_path(),
        ),
    )
    if node_bound:
        assert all(event.decision.elapsed_ms < _PARITY_MAX_ELAPSED_MS for event in sample.trace)
        capped = [event for event in sample.trace if not event.decision.complete]
        assert all(event.decision.nodes == _PARITY_RANKED_MAX_NODES for event in capped)
    game = sample.initial_state
    assert game is not None
    players = game.players
    placement_scores = [0, 0]
    fingerprints = {_fingerprint(game)}
    terminal_transitions = 0

    assert _tile_counter(game) == _EXPECTED_TILES, f"seed={seed} initial conservation"

    for event in sample.trace:
        ply = event.ply
        game = event.before
        players = game.players
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

        search = event.decision
        context = (
            f"seed={seed} ply={ply} status={search.status} nodes={search.nodes} "
            f"elapsed_ms={search.elapsed_ms}"
        )

        if search.status == "indeterminate":
            pytest.fail(f"{context}: bounded search must not authorize a non-scoring action")

        game = event.after
        players = game.players
        acting = players[acting_index]

        if search.status == "found":
            assert search.placements is not None, context
            legality = evaluate_scoring_move(
                event.before.board,
                rack_before,
                search.placements,
                authority=_AUTHORITY,
            )
            assert legality.ok, f"{context}: witness failed re-certification: {legality}"
            assert legality.total_score == search.total_score, context
            awarded = event.awarded
            assert awarded == legality.total_score, context
            placement_scores[acting_index] += awarded
            assert game.consecutive_scoreless_turns == 0, context
            assert acting.pass_streak == 0, context
            if not game.ended:
                assert acting.score - score_before[acting_index] == awarded, context
        elif bag_before >= 7:
            assert search.complete is True, context
            assert game.consecutive_scoreless_turns == scoreless_before + 1, context
            assert acting.pass_streak == 0, context
            if not game.ended:
                assert tuple(player.score for player in players) == score_before, context
        else:
            assert search.status == "none" and search.complete is True, context
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
            assert sample.plies == ply
            assert sample.end_reason == game.end_reason.name
            assert sample.final_scores == game.scores()
            print(
                "selfplay-node-bound" if node_bound else "selfplay-production",
                ("english", POLICY_WITNESS, seed, ply,
                 game.end_reason.name, tuple(game.scores().values())), flush=True,
            )
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


@pytest.mark.slow
@requires_simulation
def test_ci_twenty_seed_complete_games() -> None:
    results = _run_seeds(range(20), label="ci-20")
    assert len(results) == 20


@pytest.mark.slow
@requires_simulation
def test_acceptance_one_hundred_seed_complete_games() -> None:
    results = _run_seeds(range(100), label="acceptance-100")
    assert len(results) == 100


@pytest.mark.slow
@requires_simulation
def test_node_bound_english_regression_tuple(monkeypatch: pytest.MonkeyPatch) -> None:
    """New candidate baseline under node bounds, separate from extraction-equivalence evidence."""
    samples = []
    run = simulate_engine_game

    def capture(config, *, context):
        sample = run(config, context=context)
        samples.append(sample)
        return sample

    monkeypatch.setitem(globals(), "simulate_engine_game", capture)
    result = _simulate(0, node_bound=True)
    assert (result.plies, result.end_reason.name, tuple(samples[0].final_scores.values())) == (
        69, "SIX_CONSECUTIVE_ZERO_SCORES", (375, 138),
    )


def test_shared_helpers_preserve_physical_blanks_and_unknown_tile_options() -> None:
    from gamecore.board import Board
    from gamecore.game import Game, PlayerState
    from gamecore.tiles import TileBag

    game = Game(
        board=Board(),
        bag=TileBag(seed=0, tiles=["A"]),
        players=[PlayerState(name="P0", rack=["?"]), PlayerState(name="P1", rack=["Z"])],
    )
    game.board.cells[0][0].token = "?"
    game.board.cells[0][0].blank_as = "Z"
    assert _tile_counter(game) == Counter({"?": 2, "A": 1, "Z": 1})
    assert _rack_points(["?"]) == 0
    with pytest.raises(KeyError, match="Á"):
        _rack_points(["Á"])
    assert rack_points(["Á"], _TILE_POINTS, strict_unknown_tile=False) == 0
    # Production final scoring also tolerates unknown tokens. Conservation
    # independently rejects such tokens in a complete English game.
    assert PlayerState(name="corrupt", rack=["Á"]).rack_points("english") == 0
    assert "Á" not in _EXPECTED_TILES


def test_fingerprint_option_preserves_pass_streak_distinction() -> None:
    from gamecore.board import Board
    from gamecore.game import Game, PlayerState
    from gamecore.tiles import TileBag

    game = Game(
        board=Board(), bag=TileBag(seed=0, tiles=["A"]),
        players=[PlayerState(name="P0"), PlayerState(name="P1")],
    )
    coarse = fingerprint(game, include_pass_streak=False)
    detailed = fingerprint(game, include_pass_streak=True)
    game.players[0].pass_streak = 1
    assert fingerprint(game, include_pass_streak=False) == coarse
    assert fingerprint(game, include_pass_streak=True) != detailed
    # Even the score-only variant includes the global scoreless counter.
    game.consecutive_scoreless_turns = 1
    assert fingerprint(game, include_pass_streak=False) != coarse


def test_selfplay_has_no_application_or_dev_imports() -> None:
    import ast
    from gamecore import selfplay

    source = Path(selfplay.__file__).read_text(encoding="utf-8")
    forbidden = {"game", "tests", "django", "pytest", "pytest_django", "_pytest", "ruff", "mypy"}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            assert not {alias.name.split(".")[0] for alias in node.names} & forbidden
        elif isinstance(node, ast.ImportFrom):
            # Relative .game is the pure engine, not the top-level Django app.
            if node.level == 0:
                assert (node.module or "").split(".")[0] not in forbidden


def _empty_word_selfplay_config(**changes):
    from dataclasses import replace

    return replace(SelfPlayConfig(
        variant_slug="english", seed=0, policy_id=POLICY_WITNESS, max_plies=200,
        witness_max_elapsed_ms=_ACCEPTANCE_SEARCH_MAX_ELAPSED_MS,
        witness_max_nodes=DEFAULT_MAX_NODES,
        ranked_max_elapsed_ms=DEFAULT_RANKED_MAX_ELAPSED_MS,
        ranked_max_nodes=DEFAULT_RANKED_MAX_NODES,
        ranked_top_k=DEFAULT_RANKED_TOP_K,
        ranked_max_unique_placements=DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
        include_pass_streak=False, strict_unknown_tile=True,
    ), **changes)


def _empty_word_selfplay_context():
    return SelfPlayContext(
        authority=WordAuthority.from_words([]),
        letters=frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        blank_letters=tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
        premiums_path=get_premiums_path(),
    )


def test_selfplay_bounded_failures_are_explicit() -> None:
    from gamecore.selfplay import SelfPlayInvariantError

    with pytest.raises(SelfPlayInvariantError, match="did not terminate"):
        simulate_engine_game(_empty_word_selfplay_config(max_plies=1),
                             context=_empty_word_selfplay_context())
    with pytest.raises(SelfPlayInvariantError, match="bounded search"):
        simulate_engine_game(_empty_word_selfplay_config(witness_max_nodes=0),
                             context=_empty_word_selfplay_context())


def test_selfplay_conservation_check_detects_lost_tile(monkeypatch: pytest.MonkeyPatch) -> None:
    from gamecore.game import Game

    exchange = Game.exchange_turn

    def lose_tile(game, rack):
        exchange(game, rack)
        game.bag.tiles.pop()

    monkeypatch.setattr(Game, "exchange_turn", lose_tile)
    with pytest.raises(AssertionError, match="conservation"):
        simulate_engine_game(_empty_word_selfplay_config(),
                             context=_empty_word_selfplay_context())


def test_selfplay_cycle_check_is_live(monkeypatch: pytest.MonkeyPatch) -> None:
    from gamecore import selfplay

    monkeypatch.setattr(selfplay, "_fingerprint", lambda *args, **kwargs: ())
    with pytest.raises(AssertionError, match="repeated full position"):
        simulate_engine_game(_empty_word_selfplay_config(),
                             context=_empty_word_selfplay_context())


def test_selfplay_calls_have_isolated_state() -> None:
    from concurrent.futures import ThreadPoolExecutor

    context = _empty_word_selfplay_context()
    config = _empty_word_selfplay_config(record_trace=True)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(simulate_engine_game, config, context=context) for _ in range(2)]
        first, second = [future.result() for future in futures]
    assert first.plies == second.plies == 6
    assert first.final_scores == second.final_scores
    assert first.rack_remaining == second.rack_remaining
    assert first.initial_state is not None and second.initial_state is not None
    first.initial_state.players[0].rack.clear()
    assert len(second.initial_state.players[0].rack) == 7
    assert len(first.trace[-1].after.players[0].rack) == 7
