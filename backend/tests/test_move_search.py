"""Bounded legal-move witness search and shared legality evaluator."""

from __future__ import annotations

from collections.abc import Callable

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
    DEFAULT_RANKED_MAX_ELAPSED_MS,
    DEFAULT_RANKED_MAX_NODES,
    DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
    DEFAULT_RANKED_TOP_K,
    MAX_RANKED_TOP_K,
    find_legal_scoring_move,
    find_ranked_scoring_moves,
)
from gamecore.types import Placement

_DICT_PATH = get_assets_path() / "dicts" / "collins2019.txt"


@pytest.fixture(scope="module")
def dictionary() -> tuple[Callable[[str], bool], Callable[[str], bool]]:
    index = load_prefix_index(_DICT_PATH)

    def is_word(word: str) -> bool:
        folded = word.strip().casefold()
        if len(folded) < 2 or not folded.isascii() or not folded.isalpha():
            return False
        return index.contains(folded)

    return is_word, index.has_prefix


def _board(*cells: tuple[int, int, str]) -> Board:
    board = Board(get_premiums_path())
    for row, col, letter in cells:
        board.cells[row][col].letter = letter
    return board


def test_prefix_index_prunes_missing_and_keeps_real_prefixes(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    _is_word, has_prefix = dictionary
    assert has_prefix("AT")
    assert has_prefix("at")
    assert not has_prefix("QZZZ")
    assert has_prefix("")


def test_first_move_horizontal_and_vertical_through_center(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board()
    result = find_legal_scoring_move(board, ["A", "T"], is_word, has_prefix)
    assert result.status == "found"
    assert result.complete is True
    assert result.witness is not None
    cells = {(p.row, p.col) for p in result.witness}
    assert (7, 7) in cells
    legality = evaluate_scoring_move(board, ["A", "T"], result.witness, is_word)
    assert legality.ok
    assert legality.total_score == result.total_score
    assert set(legality.words) == set(result.words)

    vertical = find_legal_scoring_move(board, ["A", "T"], is_word, has_prefix)
    assert vertical.status == "found"
    assert vertical.witness == result.witness


def test_connected_move_uses_fixed_board_letters_and_crosses(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board((7, 7, "A"), (7, 8, "T"))
    result = find_legal_scoring_move(board, ["S"], is_word, has_prefix)
    assert result.status == "found"
    assert result.witness is not None
    legality = evaluate_scoring_move(board, ["S"], result.witness, is_word)
    assert legality.ok
    assert all(is_word(word) for word in result.words)


def test_occupied_cells_cannot_be_overwritten(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board((7, 7, "A"), (7, 8, "T"))
    result = evaluate_scoring_move(
        board,
        ["A", "T"],
        (Placement(7, 7, "Q"), Placement(7, 8, "I")),
        is_word,
    )
    assert not result.ok
    assert result.reason_code == "occupied"


def test_duplicate_letters_and_blank_as_duplicate_trap(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board()
    two_a = find_legal_scoring_move(board, ["A", "A"], is_word, has_prefix)
    assert two_a.status == "found"
    assert two_a.witness is not None
    assert evaluate_scoring_move(board, ["A", "A"], two_a.witness, is_word).ok

    blank_result = find_legal_scoring_move(board, ["?", "T"], is_word, has_prefix)
    assert blank_result.status == "found"
    assert blank_result.witness is not None
    assert any(p.letter == "?" for p in blank_result.witness)
    assert evaluate_scoring_move(board, ["?", "T"], blank_result.witness, is_word).ok

    trap = evaluate_scoring_move(
        board,
        ["A", "?"],
        (
            Placement(7, 7, "A"),
            Placement(7, 8, "A"),
        ),
        is_word,
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
        is_word,
    )
    assert legal_blank_duplicate.ok


def test_blank_as_required_and_forbidden(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, _has_prefix = dictionary
    board = _board()
    missing = evaluate_scoring_move(
        board,
        ["?"],
        (Placement(7, 7, "?"), Placement(7, 8, "A")),
        is_word,
    )
    assert not missing.ok
    extra = evaluate_scoring_move(
        board,
        ["A", "T"],
        (Placement(7, 7, "A", blank_as="T"), Placement(7, 8, "T")),
        is_word,
    )
    assert not extra.ok
    assert extra.reason_code == REASON_INVALID_BLANK


def test_found_none_and_injected_indeterminate(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board()
    found = find_legal_scoring_move(board, ["A", "T"], is_word, has_prefix)
    assert found.status == "found"

    none = find_legal_scoring_move(board, ["Q"], is_word, has_prefix)
    assert none.status == "none"
    assert none.complete is True
    assert none.witness is None

    capped = find_legal_scoring_move(
        board, ["A", "T", "E", "R", "S", "I", "N"], is_word, has_prefix, max_nodes=1
    )
    assert capped.status == "indeterminate"
    assert capped.complete is False
    assert capped.witness is None


def test_phantom_rack_rejected(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, _has_prefix = dictionary
    board = _board()
    result = evaluate_scoring_move(
        board,
        ["A"],
        (Placement(7, 7, "A"), Placement(7, 8, "T")),
        is_word,
    )
    assert not result.ok
    assert result.reason_code == REASON_RACK_MISMATCH


def test_board_boundaries(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board((0, 0, "Q"), (0, 1, "I"))
    result = find_legal_scoring_move(board, ["S"], is_word, has_prefix)
    assert result.status in {"found", "none"}
    assert result.status != "indeterminate"
    if result.status == "found":
        assert result.witness is not None
        for placement in result.witness:
            assert 0 <= placement.row <= 14
            assert 0 <= placement.col <= 14
        assert evaluate_scoring_move(board, ["S"], result.witness, is_word).ok


def _board_snapshot(board: Board) -> tuple[tuple[object, ...], ...]:
    return tuple(
        tuple((cell.letter, cell.is_blank, cell.premium, cell.premium_used) for cell in row)
        for row in board.cells
    )


def test_ranked_search_preserves_first_witness_identity_and_board(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board()
    before = _board_snapshot(board)

    witness = find_legal_scoring_move(board, ["A", "T"], is_word, has_prefix)
    ranked = find_ranked_scoring_moves(
        board,
        ["A", "T"],
        is_word,
        has_prefix,
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
        certified = evaluate_scoring_move(board, ["A", "T"], candidate.placements, is_word)
        assert certified.ok
        assert certified.total_score == candidate.total_score


def test_ranked_search_is_deterministic_and_immediate_score_dominates(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board()
    kwargs = {
        "bag_count": 86,
        "max_nodes": 1_000_000,
        "max_elapsed_ms": 10_000,
    }
    first = find_ranked_scoring_moves(
        board, list("QUIZERS"), is_word, has_prefix, **kwargs
    )
    second = find_ranked_scoring_moves(
        board, list("QUIZERS"), is_word, has_prefix, **kwargs
    )

    assert first.status == second.status
    assert first.complete == second.complete
    assert first.nodes == second.nodes
    assert first.unique_placements == second.unique_placements
    assert first.candidates == second.candidates
    assert first.candidates[0].total_score == 66
    assert first.candidates[0].total_score > find_legal_scoring_move(
        board, list("QUIZERS"), is_word, has_prefix
    ).total_score
    assert [candidate.total_score for candidate in first.candidates] == sorted(
        (candidate.total_score for candidate in first.candidates), reverse=True
    )


def test_ranked_search_canonical_dedupe_keeps_blank_identity(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    result = find_ranked_scoring_moves(
        _board(),
        ["A", "?"],
        is_word,
        has_prefix,
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
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board()

    incomplete_found = find_ranked_scoring_moves(
        board,
        ["A", "T"],
        is_word,
        has_prefix,
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
        is_word,
        has_prefix,
        bag_count=86,
        max_elapsed_ms=10_000,
    )
    assert exhaustive_none.status == "none"
    assert exhaustive_none.complete is True

    capped_empty = find_ranked_scoring_moves(
        board,
        list("QUIZERS"),
        is_word,
        has_prefix,
        bag_count=86,
        max_nodes=1,
        max_elapsed_ms=10_000,
    )
    assert capped_empty.status == "indeterminate"
    assert capped_empty.complete is False
    assert capped_empty.candidates == ()


def test_ranked_search_has_fixed_caps_and_hard_top_k_limit(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    assert DEFAULT_RANKED_TOP_K == 8
    assert MAX_RANKED_TOP_K == 20
    assert DEFAULT_RANKED_MAX_NODES == 500_000
    assert DEFAULT_RANKED_MAX_ELAPSED_MS == 750
    assert DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS == 25_000

    result = find_ranked_scoring_moves(
        _board(),
        list("QUIZERS"),
        is_word,
        has_prefix,
        bag_count=86,
        top_k=999,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
    )

    assert result.status == "found"
    assert len(result.candidates) == MAX_RANKED_TOP_K


def test_ranked_midgame_prefers_stronger_collins_move(
    dictionary: tuple[Callable[[str], bool], Callable[[str], bool]],
) -> None:
    is_word, has_prefix = dictionary
    board = _board((7, 7, "A"), (7, 8, "T"))
    rack = list("QUIZERS")

    witness = find_legal_scoring_move(board, rack, is_word, has_prefix)
    ranked = find_ranked_scoring_moves(
        board,
        rack,
        is_word,
        has_prefix,
        bag_count=50,
        max_nodes=1_000_000,
        max_elapsed_ms=10_000,
    )

    assert witness.status == "found"
    assert ranked.status == "found"
    assert ranked.candidates[0].total_score == 38
    assert ranked.candidates[0].total_score > witness.total_score
