"""Bounded legal-move witness search and shared legality evaluator."""

from __future__ import annotations

import pytest

from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.board import Board
from gamecore.fastdict import load_prefix_index
from gamecore.legality import (
    REASON_INVALID_BLANK,
    REASON_RACK_MISMATCH,
    evaluate_scoring_move,
)
from gamecore.move_search import (
    DEFAULT_MAX_ELAPSED_MS,
    DEFAULT_RANKED_MAX_ELAPSED_MS,
    DEFAULT_RANKED_MAX_NODES,
    DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
    DEFAULT_RANKED_TOP_K,
    MAX_RANKED_TOP_K,
    enumerate_certified_moves,
    find_legal_scoring_move,
    find_ranked_scoring_moves,
)
from gamecore.tile_tracking import LateGameContext
from gamecore.types import Placement
from gamecore.word_authority import WordAuthority

_DICT_PATH = get_assets_path() / "dicts" / "collins2019.txt"


@pytest.fixture(scope="module")
def authority() -> WordAuthority:
    """Migrated fixture: the two injected callables became the one authority.

    English tiles are all ASCII letters, so dropping the fixture's own
    `isascii` clause cannot change a verdict reachable from an English rack.
    """
    return WordAuthority.from_index(load_prefix_index(_DICT_PATH))


def _board(*cells: tuple[int, int, str]) -> Board:
    board = Board(get_premiums_path())
    for row, col, letter in cells:
        board.cells[row][col].token = letter
    return board


def test_prefix_index_prunes_missing_and_keeps_real_prefixes(
    authority: WordAuthority,
) -> None:
    assert authority.has_prefix("AT")
    assert authority.has_prefix("at")
    assert not authority.has_prefix("QZZZ")
    assert authority.has_prefix("")


def test_first_move_horizontal_and_vertical_through_center(
    authority: WordAuthority,
) -> None:
    board = _board()
    result = find_legal_scoring_move(board, ["A", "T"], authority=authority)
    assert result.status == "found"
    assert result.complete is True
    assert result.witness is not None
    cells = {(p.row, p.col) for p in result.witness}
    assert (7, 7) in cells
    legality = evaluate_scoring_move(
        board, ["A", "T"], result.witness, authority=authority
    )
    assert legality.ok
    assert legality.total_score == result.total_score
    assert set(legality.words) == set(result.words)

    vertical = find_legal_scoring_move(board, ["A", "T"], authority=authority)
    assert vertical.status == "found"
    assert vertical.witness == result.witness


def test_connected_move_uses_fixed_board_letters_and_crosses(
    authority: WordAuthority,
) -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    result = find_legal_scoring_move(board, ["S"], authority=authority)
    assert result.status == "found"
    assert result.witness is not None
    legality = evaluate_scoring_move(board, ["S"], result.witness, authority=authority)
    assert legality.ok
    assert all(authority.accepts_word_query(word) for word in result.words)


def test_occupied_cells_cannot_be_overwritten(
    authority: WordAuthority,
) -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    result = evaluate_scoring_move(
        board,
        ["A", "T"],
        (Placement(7, 7, "Q"), Placement(7, 8, "I")),
        authority=authority,
    )
    assert not result.ok
    assert result.reason_code == "occupied"


def test_duplicate_letters_and_blank_as_duplicate_trap(
    authority: WordAuthority,
) -> None:
    board = _board()
    two_a = find_legal_scoring_move(board, ["A", "A"], authority=authority)
    assert two_a.status == "found"
    assert two_a.witness is not None
    assert evaluate_scoring_move(
        board, ["A", "A"], two_a.witness, authority=authority
    ).ok

    blank_result = find_legal_scoring_move(board, ["?", "T"], authority=authority)
    assert blank_result.status == "found"
    assert blank_result.witness is not None
    assert any(p.letter == "?" for p in blank_result.witness)
    assert evaluate_scoring_move(
        board, ["?", "T"], blank_result.witness, authority=authority
    ).ok

    trap = evaluate_scoring_move(
        board,
        ["A", "?"],
        (
            Placement(7, 7, "A"),
            Placement(7, 8, "A"),
        ),
        authority=authority,
    )
    assert not trap.ok
    assert trap.reason_code == REASON_RACK_MISMATCH

    legal_blank_duplicate = evaluate_scoring_move(
        board,
        ["A", "?"],
        (
            Placement(7, 7, "A"),
            Placement(7, 8, "?", blank_as="A"),
        ),
        authority=authority,
    )
    assert legal_blank_duplicate.ok


def test_blank_as_required_and_forbidden(
    authority: WordAuthority,
) -> None:
    board = _board()
    missing = evaluate_scoring_move(
        board,
        ["?"],
        (Placement(7, 7, "?"), Placement(7, 8, "A")),
        authority=authority,
    )
    assert not missing.ok
    extra = evaluate_scoring_move(
        board,
        ["A", "T"],
        (Placement(7, 7, "A", blank_as="T"), Placement(7, 8, "T")),
        authority=authority,
    )
    assert not extra.ok
    assert extra.reason_code == REASON_INVALID_BLANK


def test_found_none_and_injected_indeterminate(
    authority: WordAuthority,
) -> None:
    board = _board()
    found = find_legal_scoring_move(board, ["A", "T"], authority=authority)
    assert found.status == "found"

    none = find_legal_scoring_move(board, ["Q"], authority=authority)
    assert none.status == "none"
    assert none.complete is True
    assert none.witness is None

    capped = find_legal_scoring_move(
        board, ["A", "T", "E", "R", "S", "I", "N"], authority=authority, max_nodes=1
    )
    assert capped.status == "indeterminate"
    assert capped.complete is False
    assert capped.witness is None


def test_phantom_rack_rejected(
    authority: WordAuthority,
) -> None:
    board = _board()
    result = evaluate_scoring_move(
        board,
        ["A"],
        (Placement(7, 7, "A"), Placement(7, 8, "T")),
        authority=authority,
    )
    assert not result.ok
    assert result.reason_code == REASON_RACK_MISMATCH


def test_board_boundaries(
    authority: WordAuthority,
) -> None:
    board = _board((0, 0, "Q"), (0, 1, "I"))
    result = find_legal_scoring_move(board, ["S"], authority=authority)
    assert result.status in {"found", "none"}
    assert result.status != "indeterminate"
    if result.status == "found":
        assert result.witness is not None
        for placement in result.witness:
            assert 0 <= placement.row <= 14
            assert 0 <= placement.col <= 14
        assert evaluate_scoring_move(
            board, ["S"], result.witness, authority=authority
        ).ok


def _board_snapshot(board: Board) -> tuple[tuple[object, ...], ...]:
    return tuple(
        tuple((cell.letter, cell.is_blank, cell.premium, cell.premium_used) for cell in row)
        for row in board.cells
    )


def test_ranked_search_preserves_first_witness_identity_and_board(
    authority: WordAuthority,
) -> None:
    board = _board()
    before = _board_snapshot(board)

    witness = find_legal_scoring_move(board, ["A", "T"], authority=authority)
    ranked = find_ranked_scoring_moves(
        board,
        ["A", "T"],
        authority=authority,
        bag_count=86,
        max_elapsed_ms=10_000,
    )

    assert witness.witness == (
        Placement(7, 6, "A"),
        Placement(7, 7, "T"),
    )
    assert ranked.status == "found"
    assert ranked.complete is True
    assert _board_snapshot(board) == before
    for candidate in ranked.candidates:
        certified = evaluate_scoring_move(
            board, ["A", "T"], candidate.placements, authority=authority
        )
        assert certified.ok
        assert certified.total_score == candidate.total_score


def test_ranked_search_is_deterministic_and_immediate_score_dominates(
    authority: WordAuthority,
) -> None:
    board = _board()
    kwargs = {
        "bag_count": 86,
        "max_nodes": 1_000_000,
        "max_elapsed_ms": 10_000,
    }
    first = find_ranked_scoring_moves(
        board, list("QUIZERS"), authority=authority, **kwargs
    )
    second = find_ranked_scoring_moves(
        board, list("QUIZERS"), authority=authority, **kwargs
    )

    assert first.status == second.status
    assert first.complete == second.complete
    assert first.nodes == second.nodes
    assert first.unique_placements == second.unique_placements
    assert first.candidates == second.candidates
    assert first.candidates[0].total_score == 66
    assert first.candidates[0].total_score > find_legal_scoring_move(
        board, list("QUIZERS"), authority=authority
    ).total_score
    utilities = [
        candidate.total_score * 100 + candidate.leave_equity_cp
        for candidate in first.candidates
    ]
    assert utilities == sorted(utilities, reverse=True)


def test_ranked_search_canonical_dedupe_keeps_blank_identity(
    authority: WordAuthority,
) -> None:
    result = find_ranked_scoring_moves(
        _board(),
        ["A", "?"],
        authority=authority,
        bag_count=86,
        top_k=MAX_RANKED_TOP_K,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
    )

    keys = [candidate.canonical_key for candidate in result.candidates]
    assert len(keys) == len(set(keys))
    aa_keys = [
        key
        for candidate, key in zip(result.candidates, keys, strict=True)
        if candidate.words == ("AA",)
    ]
    assert len(aa_keys) >= 2
    assert any(any(item[2] == "?" and item[3] == "A" for item in key) for key in aa_keys)


def test_ranked_status_contract_for_found_none_and_caps(
    authority: WordAuthority,
) -> None:
    board = _board()

    incomplete_found = find_ranked_scoring_moves(
        board,
        ["A", "T"],
        authority=authority,
        bag_count=86,
        max_nodes=4,
        max_elapsed_ms=10_000,
    )
    assert incomplete_found.status == "found"
    assert incomplete_found.complete is False
    assert incomplete_found.candidates

    exhaustive_none = find_ranked_scoring_moves(
        board,
        ["Q"],
        authority=authority,
        bag_count=86,
        max_elapsed_ms=10_000,
    )
    assert exhaustive_none.status == "none"
    assert exhaustive_none.complete is True

    capped_empty = find_ranked_scoring_moves(
        board,
        list("QUIZERS"),
        authority=authority,
        bag_count=86,
        max_nodes=1,
        max_elapsed_ms=10_000,
    )
    assert capped_empty.status == "indeterminate"
    assert capped_empty.complete is False
    assert capped_empty.candidates == ()


def test_ranked_search_has_fixed_caps_and_hard_top_k_limit(
    authority: WordAuthority,
) -> None:
    assert DEFAULT_MAX_ELAPSED_MS == 2000
    assert DEFAULT_RANKED_TOP_K == 8
    assert MAX_RANKED_TOP_K == 20
    assert DEFAULT_RANKED_MAX_NODES == 500_000
    assert DEFAULT_RANKED_MAX_ELAPSED_MS == 750
    assert DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS == 25_000

    result = find_ranked_scoring_moves(
        _board(),
        list("QUIZERS"),
        authority=authority,
        bag_count=86,
        top_k=999,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
    )

    assert result.status == "found"
    assert len(result.candidates) == MAX_RANKED_TOP_K


def _late_context(
    bag_remaining: int,
    unseen: tuple[tuple[str, int], ...],
    *,
    opponent_rack_size: int,
) -> LateGameContext:
    return LateGameContext(
        bag_remaining=bag_remaining,
        unseen_tiles=unseen,
        opponent_rack_size=opponent_rack_size,
        consecutive_scoreless_turns=0,
        opponent_action_rules="ai_scoring",
    )


def test_ranked_empty_bag_delegates_to_the_endgame_solver() -> None:
    # Defensive-block scenario: BAT (5 points) blocks the opponent's OAT out
    # and keeps my own ZA out; greedy ZA (11 points) concedes it. A strategic
    # ordering therefore CANNOT be the raw-score ordering.
    board = _board((7, 7, "A"), (7, 8, "T"))
    mini = WordAuthority.from_words(["OAT", "BAT", "ZA"])
    result = find_ranked_scoring_moves(
        board,
        ["Z", "B"],
        authority=mini,
        bag_count=0,
        max_elapsed_ms=10_000_000,
        late_game_context=_late_context(0, (("O", 1),), opponent_rack_size=1),
    )

    assert result.status == "found"
    assert result.strategy_mode == "exact"
    assert result.out_in_two == "proven"
    assert result.completed_depth >= 1
    assert result.candidates[0].words == ("BAT",)
    scores = [candidate.total_score for candidate in result.candidates]
    assert scores != sorted(scores, reverse=True)


def test_ranked_empty_bag_respects_top_k_clamp() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    mini = WordAuthority.from_words(["OAT", "BAT", "ZA"])
    result = find_ranked_scoring_moves(
        board,
        ["Z", "B"],
        authority=mini,
        bag_count=0,
        top_k=1,
        max_elapsed_ms=10_000_000,
        late_game_context=_late_context(0, (("O", 1),), opponent_rack_size=1),
    )
    assert result.strategy_mode == "exact"
    assert len(result.candidates) == 1
    assert result.candidates[0].words == ("BAT",)


def test_ranked_ignores_a_context_that_contradicts_bag_count() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    mini = WordAuthority.from_words(["OAT", "BAT", "ZA"])
    result = find_ranked_scoring_moves(
        board,
        ["Z", "B"],
        authority=mini,
        bag_count=50,
        max_elapsed_ms=10_000,
        late_game_context=_late_context(0, (("O", 1),), opponent_rack_size=1),
    )
    assert result.strategy_mode is None
    assert result.out_in_two is None
    # Ordinary midgame ordering: raw score dominates again.
    assert result.candidates[0].words == ("ZA",)


def test_ranked_pre_endgame_window_marks_and_revalues_candidates(
    authority: WordAuthority,
) -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    rack = list("QUIZERS")
    kwargs = {
        "bag_count": 3,
        "max_nodes": 1_000_000,
        "max_elapsed_ms": 10_000,
    }
    unseen = (("A", 2), ("E", 2), ("O", 2), ("Q", 1), ("X", 1), ("Z", 2))
    strategic = find_ranked_scoring_moves(
        board,
        rack,
        authority=authority,
        late_game_context=_late_context(3, unseen, opponent_rack_size=7),
        **kwargs,
    )
    plain = find_ranked_scoring_moves(board, rack, authority=authority, **kwargs)

    assert strategic.status == "found"
    assert strategic.strategy_mode == "pre_endgame"
    assert plain.strategy_mode is None
    # Same certified moves, re-valued: utility stays internally consistent.
    utilities = [
        candidate.total_score * 100 + candidate.leave_equity_cp
        for candidate in strategic.candidates
    ]
    assert utilities == sorted(utilities, reverse=True)
    for candidate in strategic.candidates:
        certified = evaluate_scoring_move(
            board, rack, candidate.placements, authority=authority
        )
        assert certified.ok
        assert certified.total_score == candidate.total_score


def test_enumerate_certified_moves_returns_every_certified_move() -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    mini = WordAuthority.from_words(["ATS", "SAT"])
    result = enumerate_certified_moves(
        board, ["S"], authority=mini, max_elapsed_ms=10_000_000
    )

    assert result.status == "found"
    assert result.complete is True
    words = sorted(candidate.words[0] for candidate in result.candidates)
    assert words == ["ATS", "SAT"]
    scores = [candidate.total_score for candidate in result.candidates]
    assert scores == sorted(scores, reverse=True)
    for candidate in result.candidates:
        certified = evaluate_scoring_move(
            board, ["S"], candidate.placements, authority=mini
        )
        assert certified.ok
        assert candidate.rack_out is True
        assert candidate.leave_equity_cp == 0


def test_enumerate_certified_moves_gates_non_scoring_on_the_flag() -> None:
    # Two blanks over an empty board: "AA" is legal but scores zero, which is
    # exactly the evaluator's non_scoring verdict. Only simulated HUMAN action
    # nodes may retain it.
    board = _board()
    mini = WordAuthority.from_words(["AA"])
    with_zero = enumerate_certified_moves(
        board, ["?", "?"], authority=mini,
        include_non_scoring=True, max_elapsed_ms=10_000_000,
    )
    without_zero = enumerate_certified_moves(
        board, ["?", "?"], authority=mini,
        include_non_scoring=False, max_elapsed_ms=10_000_000,
    )

    assert with_zero.status == "found"
    assert all(candidate.total_score == 0 for candidate in with_zero.candidates)
    assert any(
        all(p.letter == "?" for p in candidate.placements)
        for candidate in with_zero.candidates
    )
    assert without_zero.status == "none"
    assert without_zero.candidates == ()


def test_ranked_midgame_prefers_stronger_collins_move(
    authority: WordAuthority,
) -> None:
    board = _board((7, 7, "A"), (7, 8, "T"))
    rack = list("QUIZERS")

    witness = find_legal_scoring_move(board, rack, authority=authority)
    ranked = find_ranked_scoring_moves(
        board,
        rack,
        authority=authority,
        bag_count=50,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
    )

    assert witness.status == "found"
    assert ranked.status == "found"
    # Utility ranking keeps QUIZ 35 (leave E,R,S) over RISQUE 38 (leave Z):
    # the higher raw score survives in the pool but loses the top slot.
    assert ranked.candidates[0].total_score == 35
    assert ranked.candidates[0].words == ("QUIZ", "QAT")
    assert max(candidate.total_score for candidate in ranked.candidates) == 38
    assert ranked.candidates[0].total_score > witness.total_score
    utilities = [
        candidate.total_score * 100 + candidate.leave_equity_cp
        for candidate in ranked.candidates
    ]
    assert utilities == sorted(utilities, reverse=True)
