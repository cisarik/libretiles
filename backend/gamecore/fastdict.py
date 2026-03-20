"""Fast in-memory dictionary lookup for word validation (Tier 1)."""

from __future__ import annotations

import unicodedata as ud
from pathlib import Path
from typing import Callable


def _nfc_casefold(s: str) -> str:
    return ud.normalize("NFC", s).casefold()


def load_dictionary(
    path: str | Path,
    *,
    normalize: Callable[[str], str] | None = _nfc_casefold,
    comment_prefix: str = "#",
) -> Callable[[str], bool]:
    """Load a word list (one word per line) into a frozenset and return a fast lookup function."""
    path = Path(path)
    words: set[str] = set()

    with path.open("r", encoding="utf-8", errors="strict") as f:
        for line in f:
            if comment_prefix and line.startswith(comment_prefix):
                continue
            w = line.strip()
            if not w:
                continue
            normalized = normalize(w) if normalize else w
            # Ignore headers or metadata lines; only alphabetic entries are playable words.
            if not normalized.isalpha():
                continue
            words.add(normalized)

    frozen_words = frozenset(words)

    if normalize:

        def contains(word: str) -> bool:
            return normalize(word) in frozen_words

    else:

        def contains(word: str) -> bool:
            return word in frozen_words

    return contains
