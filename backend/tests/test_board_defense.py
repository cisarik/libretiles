"""Direct tests for midgame board-control and defensive opportunity cost."""

from __future__ import annotations

from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.board import Board
from gamecore.board_defense import (
    DEFENSE_PENALTY_MAX_CP,
    DEFENSE_PENALTY_MIN_CP,
    BoardDefenseEvaluator,
    posture_weights,
)
from gamecore.fastdict import load_prefix_index
from gamecore.legality import evaluate_scoring_move
from gamecore.move_search import _RankedSearcher, find_ranked_scoring_moves
from gamecore.tile_tracking import LateGameContext
from gamecore.types import Placement
from gamecore.word_authority import WordAuthority

_AUTHORITY = WordAuthority.from_index(load_prefix_index(get_assets_path() / "dicts" / "collins2019.txt"))
_MINI = WordAuthority.from_words(
    [
        "AT", "QI", "QI",
        "EA", "ED", "EF", "EH", "EL", "EM", "EN", "ER", "ES", "ET", "EX",
        "BE", "HE", "ME", "NE", "RE", "TE", "WE", "YE",
    ]
)


def _board(*cells: tuple[int, int, str]) -> Board:
    board = Board(get_premiums_path())
    for row, col, letter in cells:
        board.cells[row][col].token = letter
    return board


def _evaluator(
    board: Board,
    *,
    differential: int = 0,
    authority: WordAuthority = _AUTHORITY,
    variant: object = "english",
) -> BoardDefenseEvaluator:
    return BoardDefenseEvaluator(board, differential, authority, variant)


def test_posture_boundaries_match_the_score_differential_table() -> None:
    assert posture_weights(-60) == posture_weights(-100)
    assert (posture_weights(-60).w, posture_weights(-60).t) == (40, 100)
    assert (posture_weights(-30).w, posture_weights(-30).t) == (65, 50)
    assert (posture_weights(-29).w, posture_weights(29).t) == (100, 0)
    assert (posture_weights(30).w, posture_weights(30).c) == (150, 100)
    assert (posture_weights(60).w, posture_weights(60).c) == (200, 200)
    assert posture_weights(0).t == 0


def test_tw_exposure_is_penalised_against_a_safe_extension() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    evaluator = _evaluator(board)
    exposed = evaluator.defense_penalty_cp([Placement(0, 1, "E")])
    safe = evaluator.defense_penalty_cp([Placement(7, 9, "E")])
    assert exposed > safe
    assert exposed > 0
    assert DEFENSE_PENALTY_MIN_CP <= exposed <= DEFENSE_PENALTY_MAX_CP
    assert DEFENSE_PENALTY_MIN_CP <= safe <= DEFENSE_PENALTY_MAX_CP


def test_vowel_anchor_costs_more_than_a_low_hook_consonant() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    evaluator = _evaluator(board, authority=_MINI)
    vowel = evaluator.defense_penalty_cp([Placement(0, 1, "E")])
    low_hook = evaluator.defense_penalty_cp([Placement(0, 1, "Q")])
    assert vowel > low_hook


def test_consuming_an_exposed_premium_earns_a_denial_bonus() -> None:
    # Occupying (0,1) already opens the corner TW; covering that TW denies it.
    board = _board((7, 7, "A"), (7, 8, "T"), (0, 1, "E"))
    evaluator = _evaluator(board, differential=60)
    deny = evaluator.defense_penalty_cp([Placement(0, 0, "A")])
    reopen = evaluator.defense_penalty_cp([Placement(0, 2, "E")])
    assert deny < reopen


def test_lockdown_penalises_exposure_more_than_comeback() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    expose = [Placement(0, 1, "E")]
    lockdown = _evaluator(board, differential=60).defense_penalty_cp(expose)
    leading = _evaluator(board, differential=30).defense_penalty_cp(expose)
    neutral = _evaluator(board, differential=0).defense_penalty_cp(expose)
    trailing = _evaluator(board, differential=-30).defense_penalty_cp(expose)
    comeback = _evaluator(board, differential=-60).defense_penalty_cp(expose)
    assert lockdown > leading > neutral > trailing > comeback


def test_evaluation_is_deterministic_and_integer() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    first = _evaluator(board).defense_penalty_cp([Placement(0, 1, "S"), Placement(1, 1, "E")])
    second = _evaluator(board).defense_penalty_cp([Placement(0, 1, "S"), Placement(1, 1, "E")])
    assert first == second
    assert isinstance(first, int)


def test_ranked_search_emits_board_control_and_uses_evaluation_cp() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    rack = list("QUIZERS")
    defended = find_ranked_scoring_moves(
        board,
        rack,
        authority=_AUTHORITY,
        bag_count=50,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
        board_defense_enabled=True,
        score_differential=0,
    )
    plain = find_ranked_scoring_moves(
        board,
        rack,
        authority=_AUTHORITY,
        bag_count=50,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
    )
    assert defended.status == "found"
    assert defended.strategy_mode == "board_control"
    assert defended.out_in_two is None
    assert defended.completed_depth == 0
    assert plain.strategy_mode is None
    utilities = [candidate.evaluation_cp for candidate in defended.candidates]
    assert utilities == sorted(utilities, reverse=True)
    for candidate in defended.candidates:
        certified = evaluate_scoring_move(
            board, rack, candidate.placements, authority=_AUTHORITY
        )
        assert certified.ok
        assert candidate.evaluation_cp == (
            candidate.total_score * 100
            + candidate.leave_equity_cp
            - candidate.defense_penalty_cp
        )


def test_defense_stays_off_inside_the_pre_endgame_window() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    result = find_ranked_scoring_moves(
        board,
        list("QUIZERS"),
        authority=_AUTHORITY,
        bag_count=3,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
        board_defense_enabled=True,
        score_differential=80,
        late_game_context=LateGameContext(
            bag_remaining=3,
            unseen_tiles=(("A", 2), ("E", 2), ("O", 2), ("Q", 1), ("X", 1), ("Z", 2)),
            opponent_rack_size=7,
            consecutive_scoreless_turns=0,
            opponent_action_rules="ai_scoring",
        ),
    )
    assert result.strategy_mode == "pre_endgame"
    assert all(candidate.defense_penalty_cp == 0 for candidate in result.candidates)


def test_disabled_default_preserves_midgame_ranking() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    rack = list("QUIZERS")
    kwargs = {
        "authority": _AUTHORITY,
        "bag_count": 50,
        "max_nodes": 1_000_000,
        "max_elapsed_ms": 10_000,
    }
    first = find_ranked_scoring_moves(board, rack, **kwargs)
    second = find_ranked_scoring_moves(
        board, rack, board_defense_enabled=False, score_differential=90, **kwargs
    )
    assert first.strategy_mode is None
    assert second.strategy_mode is None
    assert [c.canonical_key for c in first.candidates] == [
        c.canonical_key for c in second.candidates
    ]


def test_pruning_skips_hopeless_candidates_without_changing_top_k() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    rack = list("QUIZERS")
    result = find_ranked_scoring_moves(
        board,
        rack,
        authority=_AUTHORITY,
        bag_count=50,
        top_k=1,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
        board_defense_enabled=True,
    )
    assert result.status == "found"
    assert result.unique_placements > 1
    searcher = _RankedSearcher(
        board=board,
        rack=rack,
        authority=_AUTHORITY,
        bag_count=50,
        top_k=1,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
        max_unique_placements=25_000,
        tile_points=None,
        variant="english",
        board_defense_enabled=True,
    )
    finished = searcher.run_ranked()
    assert finished.candidates
    assert searcher._defense is not None
    assert searcher._defense.evaluations < finished.unique_placements


def test_midgame_defense_stays_inside_the_live_deadline() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    result = find_ranked_scoring_moves(
        board,
        list("QUIZERS"),
        authority=_AUTHORITY,
        bag_count=50,
        max_elapsed_ms=750,
        board_defense_enabled=True,
    )
    assert result.status == "found"
    assert result.elapsed_ms < 750
