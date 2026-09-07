"""Exact bounded out-play minimax solver for the empty-bag endgame.

Scenarios use small explicit lexicons (``WordAuthority.from_words``) on a
premium-free board so every spread is hand-checkable from face values. The
default English tile points apply: A/E/I/O/T/S = 1, B = 3, Z/Q = 10, X = 8.
"""

from __future__ import annotations

import pytest

from gamecore.board import Board
from gamecore.endgame import (
    ENDGAME_MAX_ELAPSED_MS,
    ENDGAME_MAX_EXPANSIONS,
    ENDGAME_MAX_UNIQUE_PLACEMENTS,
    ENDGAME_TT_MAX_ENTRIES,
    EndgameSearchResult,
    solve_endgame,
)
from gamecore.legality import evaluate_scoring_move
from gamecore.types import Placement
from gamecore.word_authority import WordAuthority

# Machine-independent evidence: a huge wall clock leaves node/work budgets in
# charge, exactly like the ranked-search parity harnesses.
_NODE_BOUND_MS = 10_000_000


def _board(*cells: tuple[int, int, str]) -> Board:
    board = Board()  # premium-free: scores are pure face sums
    for row, col, letter in cells:
        board.cells[row][col].token = letter
    return board


def _solve(
    board: Board,
    rack: list[str],
    opponent: list[str],
    words: list[str],
    **kwargs: object,
) -> EndgameSearchResult:
    authority = WordAuthority.from_words(words)
    options: dict[str, object] = {"max_elapsed_ms": _NODE_BOUND_MS}
    options.update(kwargs)
    return solve_endgame(
        board, rack, opponent, authority=authority, **options  # type: ignore[arg-type]
    )


def _score(board: Board, rack: list[str], placements: tuple[Placement, ...], words: list[str]) -> int:
    verdict = evaluate_scoring_move(
        board, rack, placements, authority=WordAuthority.from_words(words)
    )
    assert verdict.ok, verdict
    return verdict.total_score


# ---- fixed budget constants ---------------------------------------------------


def test_solver_budget_constants_are_pinned() -> None:
    assert ENDGAME_MAX_ELAPSED_MS == 1250
    assert ENDGAME_MAX_EXPANSIONS == 10_000
    assert ENDGAME_MAX_UNIQUE_PLACEMENTS == 25_000
    assert ENDGAME_TT_MAX_ENTRIES == 4_096


# ---- terminal spread valuation ------------------------------------------------


def test_immediate_out_play_scores_double_opponent_leftover() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    words = ["ATS"]
    result = _solve(board, ["S"], ["Q", "Z"], words)

    assert result.strategy_mode == "exact"
    assert result.status == "found"
    assert result.out_in_two == "proven"
    assert result.completed_depth >= 1
    best = result.candidates[0]
    assert best.rack_out is True
    move_score = _score(board, ["S"], best.placements, words)
    # Out-play spread: my score plus 2 x opponent leftover (Q10 + Z10 = 20).
    assert result.candidate_values[0] == move_score + 2 * 20


def test_two_ply_out_setup_beats_both_greedy_and_immediate_out() -> None:
    # Rack Z,E over board "AT". ZAT scores 12 but strands E in a dead rack;
    # ZEAT is an immediate out worth 13; EAT scores only 3 but keeps the
    # guaranteed ZEAT out for the next turn. The opponent (Q,X = 18 leftover)
    # never has a legal move in this lexicon.
    board = _board((7, 7, "A"), (7, 8, "T"))
    words = ["ZAT", "EAT", "ZEAT"]
    result = _solve(board, ["Z", "E"], ["Q", "X"], words)

    assert result.strategy_mode == "exact"
    assert [sorted(c.words) for c in result.candidates[:3]] == [
        ["EAT"],
        ["ZEAT"],
        ["ZAT"],
    ]
    eat, zeat, zat = result.candidate_values[:3]
    eat_score = _score(board, ["Z", "E"], result.candidates[0].placements, words)
    # EAT line: 3 + (opponent forced pass) + ZEAT-after-EAT 13 + 2 x 18 = 52.
    assert eat == eat_score + 13 + 2 * 18 == 52
    # Immediate ZEAT out: 13 + 2 x 18 = 49.
    assert zeat == 13 + 2 * 18 == 49
    # Greedy ZAT deadlock: 12 - my E leftover (1) + opponent leftover (18) = 29.
    assert zat == 12 - 1 + 18 == 29
    assert eat > zeat > zat
    # The selected setup move is certified out-in-two.
    assert result.out_in_two == "proven"


def test_defensive_block_beats_higher_immediate_score() -> None:
    # Opponent (O) threatens the OAT out at (7,6). Greedy ZA scores 11 but
    # concedes the out (value 2); BAT scores only 5 but occupies (7,6),
    # forces a pass, and keeps my own ZA out (value 18).
    board = _board((7, 7, "A"), (7, 8, "T"))
    words = ["OAT", "BAT", "ZA"]
    result = _solve(board, ["Z", "B"], ["O"], words)

    assert result.strategy_mode == "exact"
    best = result.candidates[0]
    assert sorted(best.words) == ["BAT"]
    values = dict(
        zip(
            [tuple(sorted(c.words)) for c in result.candidates],
            result.candidate_values,
            strict=True,
        )
    )
    assert values[("BAT",)] == 5 + 11 + 2 * 1 == 18
    assert values[("ZA",)] == 11 - 3 - 2 * 3 == 2
    assert result.out_in_two == "proven"


def test_deadlock_valuation_uses_leftover_difference() -> None:
    # Neither side ever has a move: proven forced passes collapse to the
    # six-scoreless terminal, adjusted by the leftover difference.
    board = _board((7, 7, "A"), (7, 8, "T"))
    words = ["ZAT"]
    result = _solve(board, ["Z", "E"], ["Q", "X"], words)

    assert result.strategy_mode == "exact"
    best = result.candidates[0]
    assert sorted(best.words) == ["ZAT"]
    # ZAT 12, then deadlock: -E(1) + QX(18) = +17.
    assert result.candidate_values[0] == 12 - 1 + 18 == 29
    # No out exists for the root; the certificate must refute, not invent.
    assert best.rack_out is False
    assert result.out_in_two == "refuted"


# ---- opponent action rules ----------------------------------------------------


def test_human_opponent_may_pass_voluntarily_ai_may_not() -> None:
    # Root plays BAT; the opponent holds O with OAT blocked. For an AI
    # opponent the pass is forced (no move); for a human it is voluntary.
    # Either way the root out via ZA survives — the certificate must check
    # the pass reply for humans as well.
    board = _board((7, 7, "A"), (7, 8, "T"))
    words = ["OAT", "BAT", "ZA"]
    for rules in ("ai_scoring", "human_open"):
        result = _solve(
            board, ["Z", "B"], ["O"], words, opponent_action_rules=rules
        )
        assert result.strategy_mode == "exact"
        assert sorted(result.candidates[0].words) == ["BAT"]
        assert result.out_in_two == "proven"


# ---- budgets, degradation, determinism ----------------------------------------


def test_expansion_cap_degrades_to_bounded_without_inventing_moves() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    words = ["ZAT", "EAT", "ZEAT"]
    result = _solve(board, ["Z", "E"], ["Q", "X"], words, max_expansions=0)

    assert result.strategy_mode == "bounded"
    assert result.status == "found"
    assert result.completed_depth == 0
    assert result.candidate_values == ()
    # Static best-first order still returns only certified legal moves.
    assert result.candidates
    for candidate in result.candidates:
        verdict = evaluate_scoring_move(
            board, ["Z", "E"], candidate.placements,
            authority=WordAuthority.from_words(words),
        )
        assert verdict.ok


def test_time_deadline_cutoff_never_yields_an_illegal_result() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    words = ["ZAT", "EAT", "ZEAT"]
    result = _solve(board, ["Z", "E"], ["Q", "X"], words, max_elapsed_ms=0)

    # An exhausted clock degrades ("bounded") or abstains ("unavailable");
    # it never fabricates values it did not compute.
    assert result.strategy_mode in {"bounded", "unavailable"}
    if result.strategy_mode == "unavailable":
        assert result.candidates == ()
        assert result.status == "indeterminate"
    assert result.completed_depth == 0


def test_solver_is_deterministic_under_node_budgets() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    words = ["OAT", "BAT", "ZA", "ZAT", "AB"]
    first = _solve(board, ["Z", "B"], ["O"], words)
    second = _solve(board, ["Z", "B"], ["O"], words)

    assert first.candidates == second.candidates
    assert first.candidate_values == second.candidate_values
    assert first.strategy_mode == second.strategy_mode
    assert first.completed_depth == second.completed_depth
    assert first.out_in_two == second.out_in_two
    assert first.nodes == second.nodes
    assert first.expansions == second.expansions


def test_solver_leaves_the_caller_board_untouched() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    before = [
        [(cell.token, cell.blank_as, cell.premium_used) for cell in row]
        for row in board.cells
    ]
    _solve(board, ["Z", "E"], ["Q", "X"], ["ZAT", "EAT", "ZEAT"])
    after = [
        [(cell.token, cell.blank_as, cell.premium_used) for cell in row]
        for row in board.cells
    ]
    assert after == before


# ---- unavailability guards ----------------------------------------------------


@pytest.mark.parametrize(
    "rack,opponent,scoreless",
    [
        ([], ["A"], 0),
        (["A"], [], 0),
        (list("ABCDEFGH"), ["A"], 0),
        (["A"], list("ABCDEFGH"), 0),
        (["A"], ["B"], 6),
    ],
)
def test_invalid_endgame_inputs_are_unavailable(
    rack: list[str], opponent: list[str], scoreless: int
) -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    result = _solve(
        board, rack, opponent, ["ATS"], consecutive_scoreless_turns=scoreless
    )
    assert result.strategy_mode == "unavailable"
    assert result.candidates == ()
    assert result.out_in_two == "unknown"


def test_no_root_move_is_unavailable_never_a_pass_authorization() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    result = _solve(board, ["Q"], ["Z"], ["ATS"])
    assert result.strategy_mode == "unavailable"
    assert result.candidates == ()
    assert result.status == "indeterminate"
