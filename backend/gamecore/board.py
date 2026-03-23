from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .types import Direction, Placement, Premium, WordFound

BOARD_SIZE = 15


@dataclass
class Cell:
    letter: str | None = None
    is_blank: bool = False
    premium: Premium | None = None
    premium_used: bool = False


class Board:
    """15x15 Libre Tiles board with premium squares."""

    def __init__(self, premiums_path: str | None = None) -> None:
        self.cells: list[list[Cell]] = [
            [Cell() for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)
        ]
        if premiums_path:
            self._load_premiums(premiums_path)

    def _load_premiums(self, path: str) -> None:
        p = Path(path)
        with p.open("r", encoding="utf-8") as f:
            data = json.load(f)
        _TAG_MAP = {"DL": Premium.DL, "TL": Premium.TL, "DW": Premium.DW, "TW": Premium.TW}
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                tag = data[r][c]
                if tag in _TAG_MAP:
                    self.cells[r][c].premium = _TAG_MAP[tag]

    def inside(self, row: int, col: int) -> bool:
        return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE

    def get_letter(self, row: int, col: int) -> str | None:
        return self.cells[row][col].letter

    def place_letters(self, placements: list[Placement]) -> None:
        for p in placements:
            cell = self.cells[p.row][p.col]
            cell.letter = p.blank_as or p.letter
            cell.is_blank = p.letter == "?"

    def clear_letters(self, placements: list[Placement]) -> None:
        for p in placements:
            cell = self.cells[p.row][p.col]
            cell.letter = None
            cell.is_blank = False

    def letters_in_line(self, placements: list[Placement]) -> Direction | None:
        rows = {p.row for p in placements}
        cols = {p.col for p in placements}
        if len(rows) == 1:
            return Direction.ACROSS
        if len(cols) == 1:
            return Direction.DOWN
        return None

    def extend_word(self, row: int, col: int, direction: Direction) -> list[tuple[int, int]]:
        dr, dc = (0, 1) if direction == Direction.ACROSS else (1, 0)
        r, c = row, col
        while self.inside(r - dr, c - dc) and self.get_letter(r - dr, c - dc):
            r -= dr
            c -= dc
        coords: list[tuple[int, int]] = []
        while self.inside(r, c) and self.get_letter(r, c):
            coords.append((r, c))
            r += dr
            c += dc
        return coords

    def build_words_for_move(self, placements: list[Placement]) -> list[WordFound]:
        words: dict[tuple[int, int, Direction], WordFound] = {}
        direction = self.letters_in_line(placements)
        if direction is None:
            return []

        r0, c0 = placements[0].row, placements[0].col
        main_coords = self.extend_word(r0, c0, direction)
        if len(main_coords) >= 2:
            w = "".join(self.get_letter(r, c) or "" for r, c in main_coords)
            words[(main_coords[0][0], main_coords[0][1], direction)] = WordFound(w, main_coords)

        cross_dir = Direction.DOWN if direction == Direction.ACROSS else Direction.ACROSS
        for p in placements:
            coords = self.extend_word(p.row, p.col, cross_dir)
            if len(coords) >= 2:
                w = "".join(self.get_letter(r, c) or "" for r, c in coords)
                words[(coords[0][0], coords[0][1], cross_dir)] = WordFound(w, coords)

        return list(words.values())
