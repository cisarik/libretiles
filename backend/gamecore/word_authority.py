"""Central word authority for the pure game engine.

Owns normalized dictionary membership, two-tile authority, prefix probes, and
optional forbidden physical sequences. This is the ONLY formed-word authority:
``evaluate_scoring_move`` and both searchers require one, and the human
persisted-move verdict loop in ``game/services.py`` routes through
``accepts_formed_word``. There is no bare ``is_word`` predicate path and no
``_word_passes_dictionary``.

Three surfaces, deliberately separate
-------------------------------------
``accepts_tokens``       physical token sequence -> legality. THE authority.
``accepts_formed_word``  the same decision over a complete ``WordFound``.
``accepts_word_query``   ADVISORY string query with NO placement evidence.
                         ``/validate-words/`` only. ⛔ Never a scoring path and
                         never search certification: a string query must not be
                         able to authorize a move.

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
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from functools import lru_cache

from .fastdict import PrefixIndex, load_prefix_index
from .types import TileToken, WordFound
from .variant_store import VariantDefinition, load_two_tile_words

Route = str  # "two_tile" | "main" | "forbidden"

MIN_PHYSICAL_TILES = 2


def _nfc_casefold(s: str) -> str:
    return unicodedata.normalize("NFC", s).casefold()


def _prefixes_of(words: frozenset[str]) -> frozenset[str]:
    prefixes: set[str] = {""}
    for word in words:
        for end in range(1, len(word) + 1):
            prefixes.add(word[:end])
    return frozenset(prefixes)


@lru_cache(maxsize=64)
def _extended_entry_predicate(extra: frozenset[str]) -> Callable[[str], bool]:
    """A cached predicate admitting letters plus exactly ``extra`` nonletters.

    ⭐ CACHED ON PURPOSE. ``fastdict._predicate_cache_key`` keys the index cache
    on ``id(predicate)``, so a fresh closure per call would re-read the lexicon
    on every request and grow that cache without bound. One predicate object per
    distinct nonletter set keeps the index cache stable.
    """

    def admits_declared_nonletters(normalized: str) -> bool:
        if not any(character.isalpha() for character in normalized):
            return False
        return all(
            character.isalpha() or character in extra for character in normalized
        )

    return admits_declared_nonletters


def variant_entry_predicate(
    variant: VariantDefinition,
) -> Callable[[str], bool] | None:
    """The index entry predicate a variant's declared tokens require.

    ``None`` means "keep ``str.isalpha``", which is what every one of the twelve
    shipped tile sets gets: their tokens are alphabetic, so their indexes stay
    byte-identical. A variant that declares a nonalphabetic character INSIDE a
    token (Catalan ``L·L``) gets a predicate that requires a letter and permits
    only letters plus that variant's own declared nonletters. ⛔ No shipped index
    is broadened, and nothing is inferred from the lexicon file.
    """
    extra = frozenset(
        character
        for token in variant.playable_letters
        for character in _nfc_casefold(token)
        if not character.isalpha()
    )
    if not extra:
        return None
    return _extended_entry_predicate(extra)


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
            entry_predicate=(
                entry_predicate
                if entry_predicate is not None
                else variant_entry_predicate(variant)
            ),
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

    @classmethod
    def from_words(
        cls,
        words: Sequence[str],
        *,
        two_tile_words: frozenset[str] | None = None,
        forbidden_token_sequences: tuple[tuple[TileToken, ...], ...] = (),
    ) -> WordAuthority:
        """An in-memory authority over an explicit word list.

        The small-fixture constructor: it keeps callers that need a handful of
        words off the ``is_word`` callable they used to inject, without loading a
        shipped lexicon.
        """
        membership = frozenset(_nfc_casefold(word) for word in words)
        index = PrefixIndex(
            words=tuple(sorted(membership)),
            membership=membership,
            normalize=_nfc_casefold,
        )
        return cls.from_index(
            index,
            two_tile_words=two_tile_words,
            forbidden_token_sequences=forbidden_token_sequences,
        )

    def route(self, word: WordFound) -> Route:
        """Which lexicon a complete formed word is routed to. Assert this, not just the verdict."""
        return self.route_tokens(word.tokens)

    def route_tokens(self, tokens: Sequence[TileToken]) -> Route:
        """Routing over a physical token sequence. Physical count, never code points."""
        if tuple(tokens) in self._forbidden:
            return "forbidden"
        if len(tokens) == MIN_PHYSICAL_TILES and self.two_tile_words is not None:
            return "two_tile"
        return "main"

    def accepts_tokens(self, tokens: Sequence[TileToken]) -> bool:
        """THE authority: is this physical token sequence a legal complete word?

        Routing is by PHYSICAL TILE COUNT. Hungarian ``SZ``+``A`` and
        Slovak-style ``Á``+``CS`` are two tiles and three code points, and they
        route to the two-tile lexicon. A single ``CS`` tile is ONE tile and is
        never a word, however many code points it spells.
        """
        sequence = tuple(tokens)
        if sequence in self._forbidden:
            return False
        if len(sequence) < MIN_PHYSICAL_TILES:
            return False
        lexical = "".join(sequence)
        if len(sequence) == MIN_PHYSICAL_TILES and self.two_tile_words is not None:
            return self.normalize(lexical) in self.two_tile_words
        return bool(self.contains_main(lexical))

    def accepts_formed_word(self, word: WordFound) -> bool:
        """True iff this complete formed word is legal under the invariant above."""
        return self.accepts_tokens(word.tokens)

    def accepts_word_query(self, word: str) -> bool:
        """ADVISORY string query. NO placement evidence, so NO authority.

        ⛔ ``/validate-words/`` only — Tier-3 assistance. No scoring path and no
        search certification may call this: a bare string carries no tile
        boundaries, so accepting one here must never authorize a move. Physical
        legality is ``accepts_tokens``.

        Behaviour is the pre-collapse ``game.services._word_passes_dictionary``
        verbatim: trim, NFC-casefold, reject shorter than two code points,
        reject nonalphabetic, route a two-code-point query to the two-tile
        lexicon when the variant declares one, otherwise the main lexicon.
        """
        normalized = self.normalize(word.strip())
        if len(normalized) < MIN_PHYSICAL_TILES:
            return False
        if not normalized.isalpha():
            return False
        if self.two_tile_words is not None and len(normalized) == MIN_PHYSICAL_TILES:
            return normalized in self.two_tile_words
        return bool(self.contains_main(normalized))

    def is_lexical_word(self, word: str) -> bool:
        """Searcher prune over a concatenated lexical string (no physical length).

        Two-tile membership here is advisory for prefix-driven search. The
        legality gate is ``accepts_tokens`` / ``accepts_formed_word``.
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
