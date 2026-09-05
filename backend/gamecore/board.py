from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .types import BLANK_TOKEN, Direction, Placement, Premium, WordFound

BOARD_SIZE = 15


@dataclass
class Cell:
    """One board square, stored as the tile that physically sits on it.

    Canonical storage is ``token`` plus ``blank_as``. The invariant is the whole
    specification and getting it backwards would score blanks as real tiles:

    ========================  ==============  ==============  ================
    occupancy                 token           blank_as        realized_token
    ========================  ==============  ==============  ================
    empty                     ``None``        ``None``        ``None``
    ordinary tile ``T``       ``T``           ``None``        ``T``
    blank assigned ``T``      ``"?"``         ``T``           ``T``
    ========================  ==============  ==============  ================

    An assigned blank scores ZERO regardless of what it realizes.

    ``letter`` and ``is_blank`` survive as COMPATIBILITY ACCESSORS backed solely
    by the two canonical fields, so persistence and projection paths outside
    ``gamecore`` keep compiling and every existing assignment idiom keeps its
    meaning. ``letter`` is the REALIZED token, which is what it always was.
    """

    token: str | None = None
    blank_as: str | None = None
    premium: Premium | None = None
    premium_used: bool = False

    @property
    def is_occupied(self) -> bool:
        return self.token is not None

    @property
    def is_malformed(self) -> bool:
        """A physical blank with no assignment, or an assignment with no blank.

        ⛔ Fails closed before evaluation. It must NOT read as an empty cell:
        silently vanishing would turn a corrupt payload into a legal-looking
        board.
        """
        if self.token == BLANK_TOKEN:
            return self.blank_as is None
        return self.blank_as is not None

    @property
    def realized_token(self) -> str | None:
        """Lexical occupant: the blank's assignment if blank, else the tile token.

        A malformed blank realizes as ``"?"`` — occupied, never a word, and
        never mistaken for an empty square.
        """
        if self.token is None:
            return None
        if self.token == BLANK_TOKEN and self.blank_as is not None:
            return self.blank_as
        return self.token

    @property
    def letter(self) -> str | None:
        """Compatibility accessor for ``realized_token``."""
        return self.realized_token

    @letter.setter
    def letter(self, value: str | None) -> None:
        if value is None:
            self.token = None
            self.blank_as = None
        elif self.token == BLANK_TOKEN:
            # Retarget an existing blank rather than turning it into a real tile.
            self.blank_as = value
        else:
            self.token = value
            self.blank_as = None

    @property
    def is_blank(self) -> bool:
        """Compatibility accessor: this square holds a physical blank."""
        return self.token == BLANK_TOKEN

    @is_blank.setter
    def is_blank(self, value: bool) -> None:
        if value:
            if self.token == BLANK_TOKEN:
                return
            # Preserve what the square realizes; the tile underneath becomes '?'.
            self.blank_as = self.token
            self.token = BLANK_TOKEN
        else:
            if self.token != BLANK_TOKEN:
                self.blank_as = None
                return
            self.token = self.blank_as
            self.blank_as = None


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
        return self.cells[row][col].realized_token

    def malformed_cells(self) -> list[tuple[int, int]]:
        """Occupied squares whose token/blank_as pair cannot be evaluated."""
        return [
            (r, c)
            for r in range(BOARD_SIZE)
            for c in range(BOARD_SIZE)
            if self.cells[r][c].is_malformed
        ]

    def place_letters(self, placements: list[Placement]) -> None:
        for p in placements:
            cell = self.cells[p.row][p.col]
            if p.letter == BLANK_TOKEN:
                cell.token = BLANK_TOKEN
                cell.blank_as = p.blank_as
            else:
                cell.token = p.letter
                cell.blank_as = None

    def clear_letters(self, placements: list[Placement]) -> None:
        for p in placements:
            cell = self.cells[p.row][p.col]
            cell.token = None
            cell.blank_as = None

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
            tokens = [self.get_letter(r, c) or "" for r, c in main_coords]
            w = "".join(tokens)
            words[(main_coords[0][0], main_coords[0][1], direction)] = WordFound(
                w, main_coords, tokens
            )

        cross_dir = Direction.DOWN if direction == Direction.ACROSS else Direction.ACROSS
        for p in placements:
            coords = self.extend_word(p.row, p.col, cross_dir)
            if len(coords) >= 2:
                tokens = [self.get_letter(r, c) or "" for r, c in coords]
                w = "".join(tokens)
                words[(coords[0][0], coords[0][1], cross_dir)] = WordFound(w, coords, tokens)

        return list(words.values())
