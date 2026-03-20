from __future__ import annotations

from .types import Placement


def consume_rack(rack: list[str], placements: list[Placement]) -> list[str]:
    """Return a new rack with tiles used in placements removed.

    Each placement consumes exactly one matching tile from the rack,
    even when multiple placements use the same letter.
    """
    remaining = rack.copy()
    for pl in placements:
        ch = "?" if pl.letter == "?" else pl.letter
        try:
            remaining.remove(ch)
        except ValueError:
            pass
    return remaining


def restore_rack(rack: list[str], placements: list[Placement]) -> list[str]:
    """Return tiles from placements back to rack (non-mutating)."""
    restored = rack.copy()
    for placement in placements:
        letter = "?" if placement.letter == "?" else placement.letter
        restored.append(letter)
    return restored
