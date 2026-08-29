"""Slice 1: per-variant lexicon, alphabet, NFC ingest, and scoring."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any

import pytest

from game.services import (
    _board_from_session,
    _placements_from_data,
    _word_passes_dictionary,
)
from gamecore.assets import get_premiums_path
from gamecore.board import Board
from gamecore.fastdict import load_prefix_index
from gamecore.legality import REASON_INVALID_BLANK, evaluate_scoring_move
from gamecore.move_search import find_legal_scoring_move
from gamecore.scoring import score_words
from gamecore.types import Placement
from gamecore.variant_store import load_variant


@pytest.fixture(scope="module")
def collins_contains() -> Callable[[str], bool]:
    return load_prefix_index(load_variant("english").dictionary_path).contains


@pytest.fixture(scope="module")
def slovak_index() -> Any:
    return load_prefix_index(load_variant("slovak").dictionary_path)


def test_slovak_diacritic_membership_only_on_slovak_path(
    collins_contains: Callable[[str], bool],
    slovak_index: Any,
) -> None:
    assert _word_passes_dictionary(slovak_index.contains, "škola") is True
    assert _word_passes_dictionary(collins_contains, "škola") is False
    assert _word_passes_dictionary(collins_contains, "qi") is True


def test_combining_character_nfc_equivalent_is_accepted(slovak_index: Any) -> None:
    composed = "škola"
    decomposed = unicodedata.normalize("NFD", composed)
    assert decomposed != composed
    assert _word_passes_dictionary(slovak_index.contains, composed) is True
    assert _word_passes_dictionary(slovak_index.contains, decomposed) is True


def test_slovak_blank_acute_a_is_not_invalid_blank() -> None:
    letters = frozenset(load_variant("slovak").playable_letters)
    board = Board(get_premiums_path())
    placements = [
        Placement(7, 7, "?", "Á"),
        Placement(7, 8, "T"),
    ]
    slovak = evaluate_scoring_move(
        board,
        ["?", "T"],
        placements,
        lambda _word: True,
        letters=letters,
        variant="slovak",
    )
    assert slovak.reason_code != REASON_INVALID_BLANK

    english = evaluate_scoring_move(
        board,
        ["?", "T"],
        placements,
        lambda _word: True,
    )
    assert english.reason_code == REASON_INVALID_BLANK


def test_acute_a_scores_with_slovak_variant() -> None:
    board = Board(get_premiums_path())
    placements = [Placement(7, 7, "Á"), Placement(7, 8, "A")]
    board.place_letters(placements)
    words_coords = [("ÁA", [(7, 7), (7, 8)])]
    slovak_total, _ = score_words(board, placements, words_coords, variant="slovak")
    english_total, _ = score_words(board, placements, words_coords, variant="english")
    assert slovak_total > 0
    assert slovak_total > english_total


def test_placements_nfc_composes_letter() -> None:
    decomposed = unicodedata.normalize("NFD", "Á")
    assert decomposed != "Á"
    placements = _placements_from_data(
        [{"row": 7, "col": 7, "letter": decomposed}]
    )
    assert placements[0].letter == "Á"


def test_board_from_session_nfc_keeps_fifteen_cells() -> None:
    decomposed = unicodedata.normalize("NFD", "Š")
    assert len(decomposed) > 1
    row = decomposed + ("." * 14)
    session = SimpleNamespace(
        board_state=[row] + ["." * 15] * 14,
        blanks=[],
        premium_used=[],
    )
    board = _board_from_session(session)  # type: ignore[arg-type]
    assert board.cells[0][0].letter == "Š"
    assert not board.cells[0][1].letter


def test_empty_board_slovak_rack_finds_legal_word(slovak_index: Any) -> None:
    variant = load_variant("slovak")

    def is_word(word: str) -> bool:
        return _word_passes_dictionary(slovak_index.contains, word)

    result = find_legal_scoring_move(
        Board(get_premiums_path()),
        ["A", "U", "T", "O", "L", "I", "N"],
        is_word,
        slovak_index.has_prefix,
        blank_letters=variant.playable_letters,
        variant="slovak",
    )
    assert result.status == "found"
    assert result.witness is not None
    assert result.total_score > 0
