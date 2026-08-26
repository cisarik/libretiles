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
from gamecore.move_search import find_legal_scoring_move
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
