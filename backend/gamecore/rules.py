from __future__ import annotations

from .board import BOARD_SIZE, Board
from .types import Direction, Placement, WordFound

CENTER = (7, 7)


def first_move_must_cover_center(placements: list[Placement]) -> bool:
    return any((p.row, p.col) == CENTER for p in placements)


def placements_in_line(placements: list[Placement]) -> Direction | None:
    rows = {p.row for p in placements}
    cols = {p.col for p in placements}
    if len(rows) == 1:
        return Direction.ACROSS
    if len(cols) == 1:
        return Direction.DOWN
    return None


def connected_to_existing(board: Board, placements: list[Placement]) -> bool:
    has_any = any(board.cells[r][c].letter for r in range(BOARD_SIZE) for c in range(BOARD_SIZE))
    if not has_any:
        return True
    for p in placements:
        r, c = p.row, p.col
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            rr, cc = r + dr, c + dc
            if 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE and board.cells[rr][cc].letter:
                return True
    return False


def no_gaps_in_line(
    board: Board,
    placements: list[Placement],
    direction: Direction,
) -> bool:
    rows = [p.row for p in placements]
    cols = [p.col for p in placements]
    new_positions = {(p.row, p.col) for p in placements}
    if direction == Direction.ACROSS:
        r = rows[0]
        cmin, cmax = min(cols), max(cols)
        for c in range(cmin, cmax + 1):
            if not board.cells[r][c].letter and (r, c) not in new_positions:
                return False
    else:
        c = cols[0]
        rmin, rmax = min(rows), max(rows)
        for r in range(rmin, rmax + 1):
            if not board.cells[r][c].letter and (r, c) not in new_positions:
                return False
    return True


def extract_all_words(board: Board, placements: list[Placement]) -> list[WordFound]:
    return board.build_words_for_move(placements)
