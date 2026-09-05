from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

# One atomic tile token is one physical bag entry, rack entry, placement, or
# board cell. It may contain more than one Unicode code point (Hungarian SZ).
# Canonicalization is trim → NFC → uppercase → NFC. `len(str)` is a resource
# bound only — physical tile count is always the length of a token container.
TileToken = str

BLANK_TOKEN: TileToken = "?"


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
    """A complete formed word as TILES, not as a string that happens to spell it.

    ``tokens`` is the storage identity and is REQUIRED. Physical length is
    ``len(tokens)`` and equals ``len(letters)``; the lexical text is exactly
    their concatenation. Both are enforced here so no caller can hand the word
    authority a record whose tile evidence and lexical text disagree — that is
    the shape a reverse-segmented string would have.
    """

    word: str
    letters: list[tuple[int, int]]
    tokens: list[TileToken]

    def __post_init__(self) -> None:
        if len(self.tokens) != len(self.letters):
            raise ValueError(
                "WordFound needs one token per coordinate: "
                f"{len(self.tokens)} tokens for {len(self.letters)} coordinates"
            )
        joined = "".join(self.tokens)
        if joined != self.word:
            raise ValueError(
                "WordFound tokens must concatenate to word: "
                f"{joined!r} != {self.word!r}"
            )


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
