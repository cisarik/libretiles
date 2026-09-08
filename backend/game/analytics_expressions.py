from __future__ import annotations

from collections.abc import Iterable
from typing import Any


def nonnegative_number(value: object) -> float | None:
    """Accept measured JSON numbers without treating booleans as counters."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        return None
    return float(value)


def average(values: Iterable[float]) -> float | None:
    items = list(values)
    return sum(items) / len(items) if items else None


def rounded(value: Any) -> float | None:
    return round(float(value), 2) if value is not None else None
