from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto

# One atomic tile token is one physical bag entry, rack entry, placement, or
# board cell. It may contain more than one Unicode code point (Hungarian SZ).
# Canonicalization is trim → NFC → uppercase → NFC. `len(str)` is a resource
# bound only — physical tile count is always the length of a token container.
TileToken = str


class Direction(Enum):
    ACROSS = auto()
    DOWN = auto()


@dataclass(frozen=True)
class Placement:
    """A single tile placed at (row, col) during a turn."""

    row: int
    col: int
    letter: TileToken  # atomic token, or '?' for a physical blank
    blank_as: TileToken | None = None


@dataclass
class Move:
    placements: list[Placement]


@dataclass
class WordFound:
    word: str
    letters: list[tuple[int, int]]
    # Realized tokens at `letters` coordinates. Third field with a default so
    # positional WordFound(word, coords) constructions keep working. F2 will
    # make tokens the storage identity; this slice only adds the field.
    tokens: list[TileToken] = field(default_factory=list)


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
