"""Fast in-memory dictionary lookup for word validation (Tier 1)."""

from __future__ import annotations

import unicodedata as ud
from bisect import bisect_left
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


def _nfc_casefold(s: str) -> str:
    return ud.normalize("NFC", s).casefold()


def _read_words(
    path: Path,
    *,
    normalize: Callable[[str], str] | None,
    comment_prefix: str,
    entry_predicate: Callable[[str], bool] | None,
) -> frozenset[str]:
    words: set[str] = set()
    predicate = str.isalpha if entry_predicate is None else entry_predicate
    with path.open("r", encoding="utf-8", errors="strict") as f:
        for line in f:
            if comment_prefix and line.startswith(comment_prefix):
                continue
            w = line.strip()
            if not w:
                continue
            normalized = normalize(w) if normalize else w
            # Default predicate is str.isalpha — byte-identical English/Slovak
            # indexes. Inject a predicate to admit tokens such as Catalan L·L.
            if not predicate(normalized):
                continue
            words.add(normalized)
    return frozenset(words)


@dataclass(frozen=True)
class PrefixIndex:
    """Cached sorted-prefix dictionary: membership plus bisect prefix probes."""

    words: tuple[str, ...]
    membership: frozenset[str]
    normalize: Callable[[str], str] | None

    def contains(self, word: str) -> bool:
        key = self.normalize(word) if self.normalize is not None else word
        return key in self.membership

    def has_prefix(self, prefix: str) -> bool:
        if not prefix:
            return bool(self.words)
        key = self.normalize(prefix) if self.normalize is not None else prefix
        index = bisect_left(self.words, key)
        return index < len(self.words) and self.words[index].startswith(key)


_INDEX_CACHE: dict[tuple[str, str, str], PrefixIndex] = {}


def _predicate_cache_key(entry_predicate: Callable[[str], bool] | None) -> str:
    if entry_predicate is None:
        return "default_isalpha"
    name = getattr(entry_predicate, "__name__", "custom")
    return f"{name}:{id(entry_predicate)}"


def load_prefix_index(
    path: str | Path,
    *,
    normalize: Callable[[str], str] | None = _nfc_casefold,
    comment_prefix: str = "#",
    entry_predicate: Callable[[str], bool] | None = None,
) -> PrefixIndex:
    """Load (or reuse) a sorted-prefix index for `path`."""
    resolved = str(Path(path).resolve())
    norm_key = "none" if normalize is None else getattr(normalize, "__name__", "custom")
    cache_key = (resolved, norm_key, _predicate_cache_key(entry_predicate))
    cached = _INDEX_CACHE.get(cache_key)
    if cached is not None:
        return cached
    frozen = _read_words(
        Path(path),
        normalize=normalize,
        comment_prefix=comment_prefix,
        entry_predicate=entry_predicate,
    )
    index = PrefixIndex(words=tuple(sorted(frozen)), membership=frozen, normalize=normalize)
    _INDEX_CACHE[cache_key] = index
    return index


def load_dictionary(
    path: str | Path,
    *,
    normalize: Callable[[str], str] | None = _nfc_casefold,
    comment_prefix: str = "#",
    entry_predicate: Callable[[str], bool] | None = None,
) -> Callable[[str], bool]:
    """Load a word list (one word per line) into a frozenset and return a fast lookup function."""
    return load_prefix_index(
        path,
        normalize=normalize,
        comment_prefix=comment_prefix,
        entry_predicate=entry_predicate,
    ).contains
