from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class Direction(Enum):
    ACROSS = auto()
    DOWN = auto()


@dataclass(frozen=True)
class Placement:
    """A single tile placed at (row, col) during a turn."""

    row: int
    col: int
    letter: str  # 'A'..'Z' or '?' for blank
    blank_as: str | None = None


@dataclass
class Move:
    placements: list[Placement]


@dataclass
class WordFound:
    word: str
    letters: list[tuple[int, int]]


@dataclass
class ScoreBreakdown:
    word: str
    base_points: int
    letter_bonus_points: int
    word_multiplier: int
    total: int


class Premium(Enum):
    DL = auto()
    TL = auto()
    DW = auto()
    TW = auto()


TilePoints = dict[str, int]
