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
    _session_authority,
)
from gamecore.assets import get_premiums_path
from gamecore.board import Board
from gamecore.fastdict import load_prefix_index
from gamecore.legality import REASON_INVALID_BLANK, evaluate_scoring_move
from gamecore.move_search import find_legal_scoring_move
from gamecore.scoring import score_words
from gamecore.types import Placement
from gamecore.variant_store import load_two_tile_words, load_variant
from gamecore.word_authority import WordAuthority


@pytest.fixture(scope="module")
def collins_contains() -> Callable[[str], bool]:
    return load_prefix_index(load_variant("english").dictionary_path).contains


@pytest.fixture(scope="module")
def slovak_index() -> Any:
    return load_prefix_index(load_variant("slovak").dictionary_path)


@pytest.fixture(scope="module")
def slovak_authority() -> WordAuthority:
    return WordAuthority.for_variant(load_variant("slovak"))


@pytest.fixture(scope="module")
def english_authority() -> WordAuthority:
    return WordAuthority.for_variant(load_variant("english"))


def test_slovak_diacritic_membership_only_on_slovak_path(
    slovak_authority: WordAuthority,
    english_authority: WordAuthority,
) -> None:
    # Migrated fixture, identical expectations: the injected callable became the
    # one authority for the same variant.
    assert slovak_authority.accepts_word_query("škola") is True
    assert english_authority.accepts_word_query("škola") is False
    assert english_authority.accepts_word_query("qi") is True
    assert english_authority.accepts_word_query("za") is True
    assert english_authority.accepts_word_query("fe") is True


def test_slovak_two_letter_b2_is_the_lexicon(slovak_authority: WordAuthority) -> None:
    allowlist = load_two_tile_words(load_variant("slovak"))
    assert allowlist is not None
    assert slovak_authority.two_tile_words == allowlist
    assert slovak_authority.accepts_word_query("as") is True
    assert slovak_authority.accepts_word_query("ja") is True
    assert slovak_authority.accepts_word_query("škola") is True
    assert slovak_authority.accepts_word_query("ou") is False
    assert slovak_authority.accepts_word_query("am") is False
    # Residual is hunspell junk of length ≥3, not missing B2.
    assert slovak_authority.accepts_word_query("aj") is True
    assert slovak_authority.accepts_word_query("ak") is True
    assert slovak_authority.accepts_word_query("či") is True
    # The same verdicts as PHYSICAL tile sequences, which is the authority.
    assert slovak_authority.accepts_tokens(("A", "S")) is True
    assert slovak_authority.accepts_tokens(("O", "U")) is False
    assert slovak_authority.accepts_tokens(("Š", "K", "O", "L", "A")) is True


def test_session_authority_rejects_slovak_ou_on_session_stub() -> None:
    session = SimpleNamespace(variant_slug="slovak")
    authority = _session_authority(session)  # type: ignore[arg-type]
    assert authority.accepts_word_query("ou") is False
    assert authority.accepts_word_query("am") is False
    assert authority.accepts_word_query("as") is True
    assert authority.accepts_word_query("aj") is True
    assert authority.accepts_word_query("či") is True
    assert authority.accepts_word_query("škola") is True
    assert authority.accepts_tokens(("O", "U")) is False
    assert authority.accepts_tokens(("A", "S")) is True
    english = _session_authority(SimpleNamespace(variant_slug="english"))  # type: ignore[arg-type]
    assert english.accepts_word_query("qi") is True
    assert english.accepts_word_query("za") is True
    assert english.accepts_word_query("fe") is True


def test_combining_character_nfc_equivalent_is_accepted(
    slovak_authority: WordAuthority,
) -> None:
    composed = "škola"
    decomposed = unicodedata.normalize("NFD", composed)
    assert decomposed != composed
    assert slovak_authority.accepts_word_query(composed) is True
    assert slovak_authority.accepts_word_query(decomposed) is True
    assert slovak_authority.accepts_tokens(tuple(decomposed.upper())) is True


def test_slovak_blank_acute_a_is_not_invalid_blank() -> None:
    letters = frozenset(load_variant("slovak").playable_letters)
    board = Board(get_premiums_path())
    placements = [
        Placement(7, 7, "?", "Á"),
        Placement(7, 8, "T"),
    ]
    accept_all = WordAuthority.from_words(("ÁT", "TÁ"))
    slovak = evaluate_scoring_move(
        board,
        ["?", "T"],
        placements,
        authority=accept_all,
        letters=letters,
        variant="slovak",
    )
    assert slovak.reason_code != REASON_INVALID_BLANK

    english = evaluate_scoring_move(
        board,
        ["?", "T"],
        placements,
        authority=accept_all,
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


def test_board_from_session_structured_cell_is_one_cell() -> None:
    decomposed = unicodedata.normalize("NFD", "Š")
    assert len(decomposed) > 1
    session = SimpleNamespace(
        board_state=[[{"token": decomposed, "blank_as": None}] + [None] * 14]
        + [[None] * 15] * 14,
        premium_used=[],
    )
    board = _board_from_session(session)  # type: ignore[arg-type]
    assert board.cells[0][0].letter == "Š"
    assert not board.cells[0][1].letter


def test_empty_board_slovak_rack_finds_legal_word(
    slovak_authority: WordAuthority,
) -> None:
    variant = load_variant("slovak")
    result = find_legal_scoring_move(
        Board(get_premiums_path()),
        ["A", "U", "T", "O", "L", "I", "N"],
        authority=slovak_authority,
        blank_letters=variant.playable_letters,
        variant="slovak",
    )
    assert result.status == "found"
    assert result.witness is not None
    assert result.total_score > 0


def test_placement_serializer_accepts_slovak_acute_a() -> None:
    from game.serializers import PlacementSerializer

    acute = PlacementSerializer(data={"row": 7, "col": 7, "letter": "Á"})
    assert acute.is_valid(), acute.errors
    assert acute.validated_data["letter"] == "Á"

    blank = PlacementSerializer(
        data={"row": 7, "col": 7, "letter": "?", "blank_as": "Á"}
    )
    assert blank.is_valid(), blank.errors
    assert blank.validated_data["blank_as"] == "Á"

    decomposed = unicodedata.normalize("NFD", "Á")
    nfc_letter = PlacementSerializer(data={"row": 7, "col": 7, "letter": decomposed})
    assert nfc_letter.is_valid(), nfc_letter.errors
    assert nfc_letter.validated_data["letter"] == "Á"

    # Was `assert not PlacementSerializer(letter="CH").is_valid()`, and it was
    # passing for the WRONG REASON. "CH" is structurally identical to "SZ" on
    # every dimension a serializer can see — NFC-stable, uppercase-stable, two
    # code points — so no shape predicate that accepts SZ can reject CH.
    # PlacementSerializer has NO VARIANT IN SCOPE and cannot know whether CH is
    # a tile in the game being played. SAME INVARIANT, split where it belongs:
    # shape is the serializer's job, playability is the engine's. Both halves
    # are asserted here, and the engine half is also pinned in
    # tests/test_atomic_tile_tokens.py:237 (`"CH" not in playable_letters`).
    digraph = PlacementSerializer(data={"row": 7, "col": 7, "letter": "CH"})
    assert digraph.is_valid(), digraph.errors
    assert digraph.validated_data["letter"] == "CH"
    assert "CH" not in load_variant("slovak").playable_letters

    assert not PlacementSerializer(data={"row": 7, "col": 7, "letter": ""}).is_valid()
    # `1` is still rejected, now for a better reason than a length limit: a tile
    # token must contain at least one Unicode letter, and a digit has none.
    assert not PlacementSerializer(data={"row": 7, "col": 7, "letter": "1"}).is_valid()

