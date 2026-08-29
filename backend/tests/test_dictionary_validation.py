"""Tier-1 dictionary validation (Collins 2019) — regression tests for word acceptance."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from django.conf import settings

from gamecore.board import Board
from gamecore.fastdict import load_dictionary, load_prefix_index
from gamecore.types import Placement

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_PRIMARY_DICT = settings.PRIMARY_DICTIONARY_PATH


@pytest.fixture(scope="module")
def contains() -> Callable[[str], bool]:
    assert _PRIMARY_DICT.is_file(), f"Missing dictionary at {_PRIMARY_DICT}"
    return load_dictionary(_PRIMARY_DICT)


def test_qlet_not_in_dictionary(contains: Callable[[str], bool]) -> None:
    """QLET is not a valid English Scrabble word — must never be accepted."""
    assert contains("qlet") is False
    assert contains("QLET") is False


def test_common_valid_two_letter_words(contains: Callable[[str], bool]) -> None:
    assert contains("qi") is True
    assert contains("za") is True
    assert contains("fe") is True


def test_collins_allows_tournament_short_words(contains: Callable[[str], bool]) -> None:
    assert contains("ae") is True
    assert contains("ern") is True
    assert contains("zag") is True


def test_let_valid(contains: Callable[[str], bool]) -> None:
    assert contains("let") is True


def test_board_extracts_main_word_qlet() -> None:
    """Sanity: word extraction must include the full main-line word for scoring."""
    premiums = _BACKEND_ROOT / "assets" / "premiums.json"
    b = Board(str(premiums))
    for c, ch in enumerate(["Q", "L", "E", "T"], start=4):
        b.cells[7][c].letter = ch
    placements = [Placement(7, c, ch) for c, ch in zip([4, 5, 6, 7], ["Q", "L", "E", "T"])]
    words = b.build_words_for_move(placements)
    assert len(words) == 1
    assert words[0].word == "QLET"


def test_primary_dictionary_has_no_qlet_line() -> None:
    text = _PRIMARY_DICT.read_text(encoding="utf-8")
    lines = {ln.strip().casefold() for ln in text.splitlines() if ln.strip() and not ln.startswith("#")}
    assert "qlet" not in lines


def test_prefix_index_matches_collins_membership(contains: Callable[[str], bool]) -> None:
    index = load_prefix_index(_PRIMARY_DICT)
    assert index.contains("hello") is contains("hello")
    assert index.has_prefix("HEL")
    assert index.has_prefix("qi")
    assert not index.has_prefix("qzzz")


def test_word_passes_dictionary_english_lock(contains: Callable[[str], bool]) -> None:
    from game.services import _word_passes_dictionary

    assert _word_passes_dictionary(contains, "qi") is True
    assert _word_passes_dictionary(contains, "za") is True
    assert _word_passes_dictionary(contains, "fe") is True
    assert _word_passes_dictionary(contains, "qlet") is False


def test_word_passes_dictionary_rejects_short_and_non_alpha(
    contains: Callable[[str], bool],
) -> None:
    from game.services import _word_passes_dictionary

    assert _word_passes_dictionary(contains, "a") is False
    assert _word_passes_dictionary(contains, "hi!") is False
    assert _word_passes_dictionary(contains, "12") is False
    assert _word_passes_dictionary(contains, "") is False


def test_word_passes_dictionary_has_no_isascii() -> None:
    import inspect

    from game.services import _word_passes_dictionary

    assert "isascii" not in inspect.getsource(_word_passes_dictionary)
