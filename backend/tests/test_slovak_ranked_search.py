"""Provider-free Slovak ranked-search CLI fixtures (Slice S)."""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import pytest

from game.services import _word_passes_dictionary
from gamecore.assets import get_premiums_path
from gamecore.board import Board
from gamecore.fastdict import load_prefix_index
from gamecore.legality import REASON_INVALID_WORD, evaluate_scoring_move, placements_to_dicts
from gamecore.move_search import RankedSearchResult, find_ranked_scoring_moves
from gamecore.tiles import get_tile_points
from gamecore.types import Placement
from gamecore.variant_store import VariantDefinition, load_two_tile_words, load_variant

_REJECTED_CROSSES = frozenset({"ou", "am"})


@dataclass(frozen=True)
class _SlovakSearch:
    variant: VariantDefinition
    allowlist: frozenset[str]
    is_word: Callable[[str], bool]
    has_prefix: Callable[[str], bool]
    letters: frozenset[str]


@pytest.fixture(scope="module")
def slovak_search() -> _SlovakSearch:
    variant = load_variant("slovak")
    index = load_prefix_index(variant.dictionary_path)
    allowlist = load_two_tile_words(variant)
    assert allowlist is not None

    def is_word(word: str) -> bool:
        return _word_passes_dictionary(
            index.contains,
            word,
            two_letter_allowlist=allowlist,
        )

    def has_prefix(prefix: str) -> bool:
        if index.has_prefix(prefix):
            return True
        folded = unicodedata.normalize("NFC", prefix).casefold()
        return len(folded) == 2 and folded in allowlist

    return _SlovakSearch(
        variant=variant,
        allowlist=allowlist,
        is_word=is_word,
        has_prefix=has_prefix,
        letters=frozenset(variant.playable_letters),
    )


def _nfc_tiles(raw: str) -> list[str]:
    return [unicodedata.normalize("NFC", tile).upper() for tile in raw]


def _is_nfc_unicode_letter_tile(letter: object, blank_as: object = None) -> bool:
    """Python equivalent of JS /^[\\p{L}?]$/u plus blank_as /^\\p{L}$/u."""
    if not isinstance(letter, str):
        return False
    normalized = unicodedata.normalize("NFC", letter.strip()).upper()
    if normalized == "?":
        if not isinstance(blank_as, str):
            return False
        blank = unicodedata.normalize("NFC", blank_as.strip()).upper()
        return len(blank) == 1 and blank.isalpha()
    return len(normalized) == 1 and normalized.isalpha()


def _placement_dicts_are_unicode(payload: Sequence[dict[str, object]]) -> bool:
    return all(
        _is_nfc_unicode_letter_tile(item.get("letter"), item.get("blank_as"))
        for item in payload
    )


def _has_diacritic_placement(payload: Sequence[dict[str, object]]) -> bool:
    for item in payload:
        letter = item.get("letter")
        value = item.get("blank_as") if letter == "?" else letter
        if not isinstance(value, str):
            continue
        nfc = unicodedata.normalize("NFC", value.strip()).upper()
        if len(nfc) == 1 and nfc.isalpha() and nfc not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            return True
    return False


def _auto_row7_board() -> Board:
    board = Board(get_premiums_path())
    for col, letter in enumerate("AUTO", start=5):
        board.cells[7][col].letter = letter
    return board


def _hook_board(*cells: tuple[int, int, str]) -> Board:
    board = Board(get_premiums_path())
    for row, col, letter in cells:
        board.cells[row][col].letter = letter
    return board


def _ranked(
    board: Board,
    rack: Sequence[str],
    search: _SlovakSearch,
) -> RankedSearchResult:
    return find_ranked_scoring_moves(
        board,
        rack,
        search.is_word,
        search.has_prefix,
        bag_count=100,
        tile_points=get_tile_points("slovak"),
        blank_letters=search.variant.playable_letters,
        variant="slovak",
    )


def _log_ranked(label: str, result: RankedSearchResult) -> None:
    top = result.candidates[0] if result.candidates else None
    top_words = ",".join(top.words) if top else "-"
    top_score = top.total_score if top else 0
    print(
        f"slovak ranked {label} status={result.status} complete={result.complete} "
        f"nodes={result.nodes} elapsed_ms={result.elapsed_ms} "
        f"top={top_words} score={top_score}",
        flush=True,
    )


def _assert_found_with_score(result: RankedSearchResult) -> None:
    assert result.status == "found"
    assert result.candidates
    assert result.candidates[0].total_score > 0


def _candidate_words_casefold(result: RankedSearchResult) -> set[str]:
    folded: set[str] = set()
    for candidate in result.candidates:
        folded.update(word.casefold() for word in candidate.words)
    return folded


def test_empty_board_ranked_slovak_returns_found_with_and_without_blank(
    slovak_search: _SlovakSearch,
) -> None:
    empty = Board(get_premiums_path())
    plain = _ranked(empty, _nfc_tiles("AUTOLIN"), slovak_search)
    _log_ranked("empty AUTOLIN", plain)
    _assert_found_with_score(plain)

    blanked = _ranked(empty, _nfc_tiles("?AUTOLI"), slovak_search)
    _log_ranked("empty ?AUTOLI", blanked)
    _assert_found_with_score(blanked)


def test_midgame_ranked_slovak_returns_found_with_unicode_candidate(
    slovak_search: _SlovakSearch,
) -> None:
    assert not _is_nfc_unicode_letter_tile("1")
    assert not _is_nfc_unicode_letter_tile("😀")
    assert not _is_nfc_unicode_letter_tile("?")
    assert _is_nfc_unicode_letter_tile("?", "Á")

    result = _ranked(_auto_row7_board(), _nfc_tiles("ĽŤÁSENI"), slovak_search)
    _log_ranked("midgame AUTO+ĽŤÁSENI", result)
    _assert_found_with_score(result)

    unicode_payloads = [
        placements_to_dicts(candidate.placements) for candidate in result.candidates
    ]
    assert any(_has_diacritic_placement(payload) for payload in unicode_payloads)
    for payload in unicode_payloads:
        assert payload
        assert _placement_dicts_are_unicode(payload)


def test_slovak_ranked_search_rejects_ou_and_am_crosses_without_scoring(
    slovak_search: _SlovakSearch,
) -> None:
    assert slovak_search.is_word("um") is True
    assert slovak_search.is_word("ou") is False
    assert slovak_search.is_word("mi") is True
    assert slovak_search.is_word("am") is False

    ou_board = _hook_board((6, 7, "O"))
    ou_move = evaluate_scoring_move(
        ou_board,
        ["U", "M"],
        (Placement(7, 7, "U"), Placement(7, 8, "M")),
        slovak_search.is_word,
        letters=slovak_search.letters,
        variant="slovak",
    )
    assert ou_move.reason_code == REASON_INVALID_WORD
    assert ou_move.total_score == 0
    assert "ou" in {word.casefold() for word in ou_move.words}

    am_board = _hook_board((6, 7, "A"))
    am_move = evaluate_scoring_move(
        am_board,
        ["M", "I"],
        (Placement(7, 7, "M"), Placement(7, 8, "I")),
        slovak_search.is_word,
        letters=slovak_search.letters,
        variant="slovak",
    )
    assert am_move.reason_code == REASON_INVALID_WORD
    assert am_move.total_score == 0
    assert "am" in {word.casefold() for word in am_move.words}

    hook_board = _hook_board((6, 7, "O"), (6, 8, "A"))
    ranked = _ranked(hook_board, _nfc_tiles("UMENASI"), slovak_search)
    _log_ranked("hooks O/A + UMENASI", ranked)
    assert _REJECTED_CROSSES.isdisjoint(_candidate_words_casefold(ranked))
    if ranked.status == "found":
        assert ranked.candidates
        for candidate in ranked.candidates:
            assert candidate.total_score > 0
