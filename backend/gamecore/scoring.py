from __future__ import annotations

from .board import Board
from .tiles import get_tile_points
from .types import Placement, Premium, ScoreBreakdown


def score_words(
    board: Board,
    placements: list[Placement],
    words_coords: list[tuple[str, list[tuple[int, int]]]],
    variant: object = None,
) -> tuple[int, list[ScoreBreakdown]]:
    """Calculate total score and per-word breakdowns.

    Premium squares (DL/TL/DW/TW) apply only to newly placed tiles
    and only if not already consumed.
    """
    placed = {(p.row, p.col): p for p in placements}
    total_score = 0
    breakdowns: list[ScoreBreakdown] = []
    new_cells = set(placed.keys())
    tile_points = get_tile_points(variant)

    for word, coords in words_coords:
        word_multiplier = 1
        word_points = 0
        letter_bonus = 0
        for r, c in coords:
            cell = board.cells[r][c]
            letter = cell.letter or ""
            base = 0 if cell.is_blank else tile_points.get(letter, 0)
            if (r, c) in new_cells and cell.premium and not cell.premium_used:
                if cell.premium == Premium.DL:
                    letter_bonus += base
                elif cell.premium == Premium.TL:
                    letter_bonus += base * 2
                elif cell.premium == Premium.DW:
                    word_multiplier *= 2
                elif cell.premium == Premium.TW:
                    word_multiplier *= 3
            word_points += base
        total = (word_points + letter_bonus) * word_multiplier
        total_score += total
        breakdowns.append(
            ScoreBreakdown(
                word=word,
                base_points=word_points,
                letter_bonus_points=letter_bonus,
                word_multiplier=word_multiplier,
                total=total,
            )
        )
    return total_score, breakdowns


def apply_premium_consumption(board: Board, placements: list[Placement]) -> None:
    for p in placements:
        cell = board.cells[p.row][p.col]
        if cell.premium:
            cell.premium_used = True
