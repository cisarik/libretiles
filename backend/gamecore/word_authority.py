"""Central word authority for the pure game engine.

Owns normalized dictionary membership, two-tile authority, prefix probes, and
optional forbidden physical sequences. Callers that still pass a bare
``is_word`` predicate into ``evaluate_scoring_move`` are the pre-F2 path;
F2 re-points those callers here and deletes ``_word_passes_dictionary``.

Formed-word invariant
---------------------
A move is illegal iff a COMPLETE formed dictionary-word produced by the
placement has a PHYSICAL LENGTH of exactly two tiles and is outside the
variant's two-tile lexicon. It is NEVER illegal because a LONGER formed word
CONTAINS a two-letter string.

``OSAMENIU`` is legal even though it contains ``AM``. Physical length is
``len(word.tokens)`` and equals ``len(word.letters)`` — the coordinate list
already counts tiles. Do not key two-tile routing on lexical code-point
length: Hungarian ``SZ``+``A`` and Slovak-style ``Á``+``CS`` are two tiles
and three code points.

Prefix probes cover the union of main-dictionary prefixes and all prefixes of
two-tile authority words, so ``ÁCS`` is reachable with no reverse
segmentation. Forbidden sequences, when declared, are exact matches of a
complete formed word's token sequence; none are inferred.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, field

from .fastdict import PrefixIndex, load_prefix_index
from .types import TileToken, WordFound
from .variant_store import VariantDefinition, load_two_tile_words

Route = str  # "two_tile" | "main" | "forbidden"


def _nfc_casefold(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


def _lexical_of(word: WordFound) -> str:
    if word.tokens:
        return "".join(word.tokens)
    return word.word


def _prefixes_of(words: frozenset[str]) -> frozenset[str]:
    prefixes: set[str] = {""}
    for word in words:
        for end in range(1, len(word) + 1):
            prefixes.add(word[:end])
    return frozenset(prefixes)


@dataclass(frozen=True)
class WordAuthority:
    """Pure word legality over complete formed words (physical tile count)."""

    contains_main: Callable[[str], bool]
    has_main_prefix: Callable[[str], bool]
    two_tile_words: frozenset[str] | None
    forbidden_token_sequences: tuple[tuple[TileToken, ...], ...] = ()
    normalize: Callable[[str], str] = _nfc_casefold
    _two_tile_prefixes: frozenset[str] = field(init=False, repr=False)
    _forbidden: frozenset[tuple[TileToken, ...]] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        two_tile = self.two_tile_words or frozenset()
        object.__setattr__(self, "_two_tile_prefixes", _prefixes_of(two_tile))
        object.__setattr__(self, "_forbidden", frozenset(self.forbidden_token_sequences))

    @classmethod
    def for_variant(
        cls,
        variant: VariantDefinition,
        *,
        entry_predicate: Callable[[str], bool] | None = None,
    ) -> WordAuthority:
        index = load_prefix_index(
            variant.dictionary_path,
            entry_predicate=entry_predicate,
        )
        return cls(
            contains_main=index.contains,
            has_main_prefix=index.has_prefix,
            two_tile_words=load_two_tile_words(variant),
            forbidden_token_sequences=variant.forbidden_token_sequences,
        )

    @classmethod
    def from_index(
        cls,
        index: PrefixIndex,
        *,
        two_tile_words: frozenset[str] | None = None,
        forbidden_token_sequences: tuple[tuple[TileToken, ...], ...] = (),
    ) -> WordAuthority:
        return cls(
            contains_main=index.contains,
            has_main_prefix=index.has_prefix,
            two_tile_words=two_tile_words,
            forbidden_token_sequences=forbidden_token_sequences,
            normalize=index.normalize or _nfc_casefold,
        )

    def route(self, word: WordFound) -> Route:
        """Which lexicon a complete formed word is routed to. Assert this, not just the verdict."""
        if tuple(word.tokens) in self._forbidden:
            return "forbidden"
        physical = len(word.letters)
        if physical == 2 and self.two_tile_words is not None:
            return "two_tile"
        return "main"

    def accepts_formed_word(self, word: WordFound) -> bool:
        """True iff this complete formed word is legal under the invariant above."""
        if tuple(word.tokens) in self._forbidden:
            return False
        physical = len(word.letters)
        if physical < 2:
            return False
        lexical = self.normalize(_lexical_of(word))
        if physical == 2 and self.two_tile_words is not None:
            return lexical in self.two_tile_words
        return self.contains_main(_lexical_of(word))

    def is_lexical_word(self, word: str) -> bool:
        """Searcher prune over a concatenated lexical string (no physical length).

        Two-tile membership here is advisory for prefix-driven search. The
        legality gate is ``accepts_formed_word`` over a ``WordFound``.
        """
        folded = self.normalize(word)
        if self.two_tile_words is not None and folded in self.two_tile_words:
            return True
        return self.contains_main(word)

    def has_prefix(self, prefix: str) -> bool:
        """Union of main-dictionary prefixes and two-tile-word prefixes."""
        if self.has_main_prefix(prefix):
            return True
        if self.two_tile_words is None:
            return False
        folded = self.normalize(prefix)
        return folded in self._two_tile_prefixes
