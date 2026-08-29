"""Shared rack-aware legality evaluator.

Used by AI validation, AI submission, and witness certification so those
paths cannot drift apart. Pure Python; the caller supplies the dictionary
predicate (Collins 2019 via the existing loader).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from .board import BOARD_SIZE, Board
from .rules import (
    connected_to_existing,
    extract_all_words,
    first_move_must_cover_center,
    no_gaps_in_line,
    placements_in_line,
)
from .scoring import score_words
from .types import Placement, ScoreBreakdown

LETTERS = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
MAX_PLACEMENTS = 7

REASON_OK = "ok"
REASON_EMPTY = "empty_placements"
REASON_TOO_MANY = "too_many_placements"
REASON_OUT_OF_BOUNDS = "out_of_bounds"
REASON_DUPLICATE_CELL = "duplicate_cell"
REASON_INVALID_LETTER = "invalid_letter"
REASON_INVALID_BLANK = "invalid_blank"
REASON_NOT_IN_LINE = "not_in_line"
REASON_OCCUPIED = "occupied"
REASON_RACK_MISMATCH = "rack_mismatch"
REASON_FIRST_MOVE_CENTER = "first_move_center"
REASON_NOT_CONNECTED = "not_connected"
REASON_GAPS = "gaps"
REASON_NO_WORDS = "no_words"
REASON_INVALID_WORD = "invalid_word"
REASON_NON_SCORING = "non_scoring"


@dataclass(frozen=True)
class WordVerdict:
    word: str
    valid: bool


@dataclass(frozen=True)
class LegalityResult:
    ok: bool
    reason_code: str
    reason: str
    total_score: int = 0
    words: tuple[str, ...] = ()
    word_results: tuple[WordVerdict, ...] = ()
    breakdowns: tuple[ScoreBreakdown, ...] = ()


def _fail(code: str, reason: str) -> LegalityResult:
    return LegalityResult(ok=False, reason_code=code, reason=reason)


def _is_board_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def board_has_letters(board: Board) -> bool:
    return any(cell.letter for row in board.cells for cell in row)


def rack_covers_placements(rack: Sequence[str], placements: Sequence[Placement]) -> bool:
    """True iff every placement consumes one matching tile from the current rack."""
    remaining = list(rack)
    for placement in placements:
        tile = "?" if placement.letter == "?" else placement.letter
        try:
            remaining.remove(tile)
        except ValueError:
            return False
    return True


def placements_to_dicts(placements: Sequence[Placement]) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for placement in placements:
        item: dict[str, object] = {
            "row": placement.row,
            "col": placement.col,
            "letter": placement.letter,
        }
        if placement.letter == "?":
            item["blank_as"] = placement.blank_as
        payload.append(item)
    return payload


def evaluate_scoring_move(
    board: Board,
    rack: Sequence[str],
    placements: Sequence[Placement],
    is_word: Callable[[str], bool],
    *,
    letters: frozenset[str] | None = None,
    variant: object = None,
) -> LegalityResult:
    """Return whether `placements` are a legal scoring move for `rack` on `board`."""
    alphabet = LETTERS if letters is None else letters
    if not placements:
        return _fail(REASON_EMPTY, "Move must contain at least one tile")
    if len(placements) > MAX_PLACEMENTS:
        return _fail(REASON_TOO_MANY, "Move may place at most seven tiles")

    seen: set[tuple[int, int]] = set()
    for placement in placements:
        if not _is_board_int(placement.row) or not _is_board_int(placement.col):
            return _fail(REASON_OUT_OF_BOUNDS, "Row and column must be integers")
        if not (0 <= placement.row < BOARD_SIZE and 0 <= placement.col < BOARD_SIZE):
            return _fail(
                REASON_OUT_OF_BOUNDS,
                f"Cell ({placement.row},{placement.col}) is out of bounds",
            )
        cell = (placement.row, placement.col)
        if cell in seen:
            return _fail(REASON_DUPLICATE_CELL, f"Duplicate cell {cell}")
        seen.add(cell)

        letter = placement.letter
        if not isinstance(letter, str) or (letter not in alphabet and letter != "?"):
            return _fail(REASON_INVALID_LETTER, "Letter must be A-Z or '?'")
        if letter == "?":
            blank_as = placement.blank_as
            if not isinstance(blank_as, str) or blank_as not in alphabet:
                return _fail(REASON_INVALID_BLANK, "blank_as must be A-Z for a blank")
        elif placement.blank_as is not None:
            return _fail(REASON_INVALID_BLANK, "blank_as is forbidden for a non-blank tile")

    direction = placements_in_line(list(placements))
    if direction is None:
        return _fail(REASON_NOT_IN_LINE, "Tiles must be in a single row or column")

    for placement in placements:
        if board.cells[placement.row][placement.col].letter:
            return _fail(
                REASON_OCCUPIED,
                f"Cell ({placement.row},{placement.col}) is occupied",
            )

    if not rack_covers_placements(rack, placements):
        return _fail(REASON_RACK_MISMATCH, "Placements are not coverable by the current rack")

    is_first = not board_has_letters(board)
    if is_first:
        if not first_move_must_cover_center(list(placements)):
            return _fail(REASON_FIRST_MOVE_CENTER, "First move must cover center square")
    elif not connected_to_existing(board, list(placements)):
        return _fail(REASON_NOT_CONNECTED, "Move must connect to existing tiles")

    if not no_gaps_in_line(board, list(placements), direction):
        return _fail(REASON_GAPS, "Move has gaps")

    placed = list(placements)
    board.place_letters(placed)
    try:
        words_found = extract_all_words(board, placed)
        if not words_found:
            return _fail(REASON_NO_WORDS, "No words formed")

        words_coords = [(word.word, word.letters) for word in words_found]
        word_results = tuple(WordVerdict(word=word, valid=is_word(word)) for word, _ in words_coords)
        invalid = [verdict.word for verdict in word_results if not verdict.valid]
        if invalid:
            return LegalityResult(
                ok=False,
                reason_code=REASON_INVALID_WORD,
                reason=f"Invalid word(s): {', '.join(invalid)}",
                words=tuple(verdict.word for verdict in word_results),
                word_results=word_results,
            )

        total, breakdowns = score_words(board, placed, words_coords, variant=variant)
        if len(placed) == 7:
            total += 50
        if total <= 0:
            return LegalityResult(
                ok=False,
                reason_code=REASON_NON_SCORING,
                reason="Move must score more than zero",
                total_score=total,
                words=tuple(verdict.word for verdict in word_results),
                word_results=word_results,
                breakdowns=tuple(breakdowns),
            )
        return LegalityResult(
            ok=True,
            reason_code=REASON_OK,
            reason="ok",
            total_score=total,
            words=tuple(verdict.word for verdict in word_results),
            word_results=word_results,
            breakdowns=tuple(breakdowns),
        )
    finally:
        board.clear_letters(placed)
