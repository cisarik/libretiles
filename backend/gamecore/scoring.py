from __future__ import annotations

from typing import cast

from .board import Board
from .tiles import get_tile_points
from .types import Placement, Premium, ScoreBreakdown, ScoreCellBreakdown
from .variant_store import VariantDefinition


def score_words(
    board: Board,
    placements: list[Placement],
    words_coords: list[tuple[str, list[tuple[int, int]]]],
    variant: object = None,
    *,
    include_inspection: bool = False,
) -> tuple[int, list[ScoreBreakdown]]:
    """Calculate total score and per-word breakdowns.

    Premium squares (DL/TL/DW/TW) apply only to newly placed tiles
    and only if not already consumed.
    """
    placed = {(p.row, p.col): p for p in placements}
    total_score = 0
    breakdowns: list[ScoreBreakdown] = []
    new_cells = set(placed.keys())
    # Points are keyed by the COMPLETE PHYSICAL TILE TOKEN on the square, never
    # by slicing a concatenated string. A physical blank scores zero whatever it
    # realizes, so the lookup uses `cell.token`, not `cell.realized_token`.
    tile_points = get_tile_points(cast(VariantDefinition | str | None, variant))

    for word, coords in words_coords:
        word_multiplier = 1
        word_points = 0
        letter_bonus = 0
        physical_cells: list[ScoreCellBreakdown] | None = [] if include_inspection else None
        for r, c in coords:
            cell = board.cells[r][c]
            base = 0 if cell.is_blank else tile_points.get(cell.token or "", 0)
            is_new = (r, c) in new_cells
            premium_applied = bool(is_new and cell.premium and not cell.premium_used)
            letter_multiplier = 1
            if premium_applied:
                if cell.premium == Premium.DL:
                    letter_multiplier = 2
                    letter_bonus += base
                elif cell.premium == Premium.TL:
                    letter_multiplier = 3
                    letter_bonus += base * 2
                elif cell.premium == Premium.DW:
                    word_multiplier *= 2
                elif cell.premium == Premium.TW:
                    word_multiplier *= 3
            word_points += base
            if physical_cells is not None:
                physical_cells.append(
                    ScoreCellBreakdown(
                        row=r,
                        col=c,
                        token=cell.token or "",
                        blank_as=cell.blank_as,
                        base_points=base,
                        is_new=is_new,
                        premium=cell.premium.name if cell.premium else None,
                        premium_applied=premium_applied,
                        letter_multiplier=letter_multiplier,
                    )
                )
        total = (word_points + letter_bonus) * word_multiplier
        total_score += total
        breakdowns.append(
            ScoreBreakdown(
                word=word,
                base_points=word_points,
                letter_bonus_points=letter_bonus,
                word_multiplier=word_multiplier,
                total=total,
                physical_cells=physical_cells,
            )
        )
    return total_score, breakdowns


def apply_premium_consumption(board: Board, placements: list[Placement]) -> None:
    for p in placements:
        cell = board.cells[p.row][p.col]
        if cell.premium:
            cell.premium_used = True
