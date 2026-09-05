"""FROZEN BASELINE ORACLE plus the formed-word verdict differential (MEC-C1-A).

⛔ THIS FILE IS THE PROOF OBLIGATION FOR COLLAPSING TWO WORD-AUTHORITY PATHS INTO
ONE. ``game.services._word_passes_dictionary`` is deleted by the same commit that
adds this file. Once it is gone there is nothing left to compare the surviving
path against — so the oracle below is a VERBATIM FROZEN COPY of it, taken from
the baseline commit, and it must never be edited to follow the implementation.

Provenance of the oracle
------------------------
commit  b50f84a06d05c95f32a7b9f930a4b42648d2990a
path    backend/game/services.py
lines   209-222 (``def _word_passes_dictionary`` through ``return bool(contains(w))``)
sha256  260bfe15306f4785eb015c3357e5b596cfe72eecd9f54807fdf0a88da2a36461
        over the UTF-8 bytes of the exact source segment, as produced by
        ``ast.get_source_segment`` — which carries NO trailing newline.

An independent acceptor re-derives it without trusting this file. ``head -c -1``
drops the trailing newline ``sed`` leaves behind, which is the only difference
between the segment and the raw line range::

    git show b50f84a06d05c95f32a7b9f930a4b42648d2990a:backend/game/services.py \
      | sed -n '209,222p' | head -c -1 | sha256sum
    # 260bfe15306f4785eb015c3357e5b596cfe72eecd9f54807fdf0a88da2a36461

The same comparison runs inside the suite, so drift fails a gate rather than
passing quietly::

    .venv/bin/python -m pytest tests/test_word_authority_parity.py -q -k \
      "pinned_digest or byte_identical or baseline_helper_executed"

⚠ THE ORACLE IS NOT A GOLD STANDARD. It is wrong in exactly the cases C1 exists
to fix, so equivalence is REQUIRED over shipped legal tile configurations and is
DELIBERATELY VIOLATED in the six named synthetic cases below. Every observed
difference must be one of those named corrections, or a failure.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import unicodedata
from collections.abc import Callable
from pathlib import Path

import pytest
from django.test import TestCase

from accounts.models import User
from game import services
from game.models import GameSession, PlayerSlot
from gamecore import move_search
from gamecore.assets import get_premiums_path
from gamecore.board import Board
from gamecore.fastdict import _INDEX_CACHE, load_prefix_index
from gamecore.legality import (
    REASON_INVALID_WORD,
    REASON_OK,
    evaluate_scoring_move,
)
from gamecore.scoring import apply_premium_consumption, score_words
from gamecore.types import Placement, WordFound
from gamecore import variant_store
from gamecore.variant_store import (
    VariantDefinition,
    VariantLetter,
    list_installed_variants,
    load_two_tile_words,
    load_variant,
)
from gamecore.word_authority import WordAuthority, variant_entry_predicate

BASELINE_COMMIT = "b50f84a06d05c95f32a7b9f930a4b42648d2990a"
BASELINE_ORACLE_PATH = "backend/game/services.py"
BASELINE_ORACLE_FIRST_LINE = 209
BASELINE_ORACLE_LAST_LINE = 222
ORACLE_SOURCE_SHA256 = "260bfe15306f4785eb015c3357e5b596cfe72eecd9f54807fdf0a88da2a36461"

# Measured by the planner and re-measured here. A twelfth variant appearing or a
# tile set changing size must break these, not slip through.
EXPECTED_ORDERED_TILE_PAIRS = 10_457
EXPECTED_ORDERED_TILE_TRIPLES = 328_685
EXPECTED_SHIPPED_VARIANTS = 12
SLOVAK_TWO_TILE_ENTRIES = 103
SLOVAK_TWO_TILE_PREFIXES = 135
BOARD_LINE_TILES = 15

# Indexes many other tests reuse. Evicting these would only make the rest of the
# suite reload multi-million-entry lexicons for nothing.
_KEEP_LOADED = frozenset({"english", "slovak"})


# ---------------------------------------------------------------------------
# ⛔ FROZEN BASELINE ORACLE — TEST ONLY. VERBATIM COPY. DO NOT EDIT.
# Copied byte for byte from backend/game/services.py:209-222 at
# b50f84a06d05c95f32a7b9f930a4b42648d2990a. It is deliberately still named
# ``_word_passes_dictionary`` so the comparison against the baseline git object
# is a byte comparison rather than a paraphrase. It has no production caller and
# must never gain one.
# ---------------------------------------------------------------------------
def _word_passes_dictionary(
    contains: Callable[[str], bool],
    word: str,
    *,
    two_letter_allowlist: frozenset[str] | None = None,
) -> bool:
    w = unicodedata.normalize("NFC", word.strip()).casefold()
    if len(w) < 2:
        return False
    if not w.isalpha():
        return False
    if two_letter_allowlist is not None and len(w) == 2:
        return w in two_letter_allowlist
    return bool(contains(w))


# ---------------------------------------------------------------------------
# END FROZEN BASELINE ORACLE
# ---------------------------------------------------------------------------

FROZEN_BASELINE_ORACLE = _word_passes_dictionary
_REPO_ROOT = Path(__file__).resolve().parents[2]


def _nfc_casefold(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


def _source_segment(module_text: str, function_name: str) -> str:
    tree = ast.parse(module_text)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            segment = ast.get_source_segment(module_text, node)
            assert segment is not None, function_name
            return segment
    raise AssertionError(f"{function_name} not found")


def _frozen_oracle_source() -> str:
    return _source_segment(
        Path(__file__).read_text(encoding="utf-8"), "_word_passes_dictionary"
    )


def _baseline_services_source() -> str | None:
    """The baseline ``services.py`` blob, or ``None`` when git cannot supply it."""
    try:
        completed = subprocess.run(
            ["git", "show", f"{BASELINE_COMMIT}:{BASELINE_ORACLE_PATH}"],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except OSError:
        return None
    if completed.returncode != 0 or not completed.stdout:
        return None
    return completed.stdout


def _tile_token_by_folded_character(
    variant: VariantDefinition,
) -> dict[str, str]:
    """Folded code point -> canonical tile token, for single-code-point tile sets.

    ⛔ NOT a segmenter. It exists only so a dictionary ENTRY can be turned into
    the token sequence a board line would really hold, and it refuses to guess:
    a variant with a multi-code-point tile has no unique mapping and is skipped
    by the caller.
    """
    mapping: dict[str, str] = {}
    for token in variant.playable_letters:
        folded = _nfc_casefold(token)
        assert len(folded) == 1, (variant.slug, token)
        assert folded not in mapping, (variant.slug, token, mapping[folded])
        mapping[folded] = token
    return mapping


def _evict_variant_index(variant: VariantDefinition) -> None:
    if variant.slug in _KEEP_LOADED:
        return
    resolved = str(Path(variant.dictionary_path).resolve())
    for key in [key for key in _INDEX_CACHE if key[0] == resolved]:
        del _INDEX_CACHE[key]


# ---------------------------------------------------------------------------
# 1. The oracle is a copy, not a reconstruction
# ---------------------------------------------------------------------------


def test_frozen_oracle_source_matches_its_pinned_digest() -> None:
    """Catches the implementer editing the oracle. No git required."""
    segment = _frozen_oracle_source()
    assert hashlib.sha256(segment.encode("utf-8")).hexdigest() == ORACLE_SOURCE_SHA256
    assert segment.splitlines()[0] == "def _word_passes_dictionary("
    assert segment.splitlines()[-1] == "    return bool(contains(w))"
    assert (
        BASELINE_ORACLE_LAST_LINE - BASELINE_ORACLE_FIRST_LINE + 1
        == len(segment.splitlines())
    )


def test_frozen_oracle_is_byte_identical_to_the_baseline_git_object() -> None:
    """The comparison an independent acceptor makes, made inside the suite."""
    baseline = _baseline_services_source()
    if baseline is None:
        pytest.skip("git could not supply the baseline services.py blob")
    baseline_segment = _source_segment(baseline, "_word_passes_dictionary")
    assert baseline_segment == _frozen_oracle_source()
    assert (
        hashlib.sha256(baseline_segment.encode("utf-8")).hexdigest()
        == ORACLE_SOURCE_SHA256
    )


def test_frozen_oracle_has_no_production_caller() -> None:
    """The oracle is test-only, and the deleted helper stays deleted."""
    for module_path in ("game/services.py", "game/diagnostics.py"):
        text = (_REPO_ROOT / "backend" / module_path).read_text(encoding="utf-8")
        assert "_word_passes_dictionary" not in text, module_path
    assert not hasattr(services, "_word_passes_dictionary")
    # ``isascii`` never enters a word verdict. Pre-existing lock, restated over
    # the module that now owns the decision.
    authority_text = (
        _REPO_ROOT / "backend" / "gamecore" / "word_authority.py"
    ).read_text(encoding="utf-8")
    assert "is" + "ascii" not in authority_text
    assert "is" + "ascii" not in _frozen_oracle_source()


def _baseline_helper_from_git() -> Callable[..., bool] | None:
    """The BASELINE PRODUCTION helper itself, compiled from the pinned blob.

    ⭐ This is what makes the oracle a copy rather than a reconstruction, and it
    keeps working after the production helper is deleted: the comparison target
    is the immutable git object named by ``BASELINE_COMMIT``, not the working
    tree.
    """
    baseline = _baseline_services_source()
    if baseline is None:
        return None
    segment = _source_segment(baseline, "_word_passes_dictionary")
    namespace: dict[str, object] = {
        "unicodedata": unicodedata,
        "Callable": Callable,
        "frozenset": frozenset,
    }
    exec(compile(segment, f"<{BASELINE_COMMIT}:{BASELINE_ORACLE_PATH}>", "exec"), namespace)
    helper = namespace["_word_passes_dictionary"]
    assert callable(helper)
    return helper  # type: ignore[return-value]


def test_frozen_oracle_agrees_with_the_baseline_helper_executed_from_git() -> None:
    """Step 2 of the proof obligation, made permanent and re-derivable."""
    helper = _baseline_helper_from_git()
    if helper is None:
        pytest.skip("git could not supply the baseline services.py blob")
    variant = load_variant("slovak")
    index = load_prefix_index(variant.dictionary_path)
    allowlist = load_two_tile_words(variant)
    checked = 0
    for slug, word, _expected in _LANGUAGE_LOCKS:
        del slug
        for candidate in (word, word.upper(), f" {word} "):
            checked += 1
            assert helper(
                index.contains, candidate, two_letter_allowlist=allowlist
            ) == FROZEN_BASELINE_ORACLE(
                index.contains, candidate, two_letter_allowlist=allowlist
            )
            assert helper(index.contains, candidate) == FROZEN_BASELINE_ORACLE(
                index.contains, candidate
            )
    for query in _QUERY_SURFACE:
        checked += 1
        assert helper(
            index.contains, query, two_letter_allowlist=allowlist
        ) == FROZEN_BASELINE_ORACLE(
            index.contains, query, two_letter_allowlist=allowlist
        )
        assert helper(index.contains, query) == FROZEN_BASELINE_ORACLE(
            index.contains, query
        )
    for first in variant.playable_letters:
        for second in variant.playable_letters:
            checked += 1
            joined = first + second
            assert helper(
                index.contains, joined, two_letter_allowlist=allowlist
            ) == FROZEN_BASELINE_ORACLE(
                index.contains, joined, two_letter_allowlist=allowlist
            )
    print(f"parity oracle-vs-baseline-git checks={checked} disagreements=0", flush=True)
    assert checked > 1_700


# ---------------------------------------------------------------------------
# 2. Shipped-configuration verdict equivalence
# ---------------------------------------------------------------------------


def _shipped_variants() -> list[VariantDefinition]:
    variants = sorted(list_installed_variants(), key=lambda item: item.slug)
    assert len(variants) == EXPECTED_SHIPPED_VARIANTS
    return variants


def test_shipped_formed_word_verdicts_agree_over_the_whole_corpus() -> None:
    """⛔ ANY shipped formed-word verdict difference blocks the slice.

    One pass per variant covering, for that variant's real tile set and real
    lexicon: every ordered two-tile sequence, every ordered three-tile sequence,
    every lexicon entry realizable by that tile set inside one board line, and
    the two-tile allowlist with its prefixes.
    """
    total_pairs = 0
    total_triples = 0
    total_entries_visited = 0
    total_entries_compared = 0
    differences: list[tuple[str, tuple[str, ...], bool, bool]] = []

    for variant in _shipped_variants():
        index = load_prefix_index(variant.dictionary_path)
        allowlist = load_two_tile_words(variant)
        authority = WordAuthority.for_variant(variant)
        # No shipped index is broadened: the authority reuses the identical
        # ``str.isalpha`` index the baseline helper read.
        assert variant_entry_predicate(variant) is None, variant.slug
        assert authority.contains_main == index.contains, variant.slug
        assert authority.two_tile_words == allowlist, variant.slug

        tiles = variant.playable_letters

        pairs = 0
        for first in tiles:
            for second in tiles:
                tokens = (first, second)
                pairs += 1
                old = FROZEN_BASELINE_ORACLE(
                    index.contains, "".join(tokens), two_letter_allowlist=allowlist
                )
                new = authority.accepts_tokens(tokens)
                if old != new:
                    differences.append((variant.slug, tokens, old, new))
        total_pairs += pairs

        triples = 0
        for first in tiles:
            for second in tiles:
                prefix = first + second
                for third in tiles:
                    tokens = (first, second, third)
                    triples += 1
                    old = FROZEN_BASELINE_ORACLE(
                        index.contains, prefix + third, two_letter_allowlist=allowlist
                    )
                    new = authority.accepts_tokens(tokens)
                    if old != new:
                        differences.append((variant.slug, tokens, old, new))
        total_triples += triples

        token_by_character = _tile_token_by_folded_character(variant)
        realizable = 0
        visited = 0
        for entry in index.membership:
            visited += 1
            if len(entry) > BOARD_LINE_TILES:
                continue
            tokens_list = [token_by_character.get(character) for character in entry]
            if any(token is None for token in tokens_list):
                continue
            tokens = tuple(token for token in tokens_list if token is not None)
            realizable += 1
            old = FROZEN_BASELINE_ORACLE(
                index.contains, "".join(tokens), two_letter_allowlist=allowlist
            )
            new = authority.accepts_tokens(tokens)
            if old != new:
                differences.append((variant.slug, tokens, old, new))
        total_entries_visited += visited
        total_entries_compared += realizable

        allowlist_size = 0 if allowlist is None else len(allowlist)
        if allowlist is not None:
            for word in allowlist:
                tokens = tuple(token_by_character[character] for character in word)
                old = FROZEN_BASELINE_ORACLE(
                    index.contains, "".join(tokens), two_letter_allowlist=allowlist
                )
                new = authority.accepts_tokens(tokens)
                assert old is True and new is True, (variant.slug, word)
                # An allowlist-only multigraph word stays REACHABLE by prefix.
                assert authority.has_prefix(word[0]), (variant.slug, word)
                assert authority.has_prefix(word), (variant.slug, word)

        print(
            f"parity {variant.slug:11s} tiles={len(tiles):3d} pairs={pairs:6d} "
            f"triples={triples:8d} entries={visited:8d} realizable={realizable:8d} "
            f"two_tile={allowlist_size:4d} differences={len(differences):3d}",
            flush=True,
        )
        _evict_variant_index(variant)

    print(
        f"parity TOTAL pairs={total_pairs} triples={total_triples} "
        f"entries_visited={total_entries_visited} "
        f"entries_compared={total_entries_compared} "
        f"shipped_differences={len(differences)}",
        flush=True,
    )
    assert total_pairs == EXPECTED_ORDERED_TILE_PAIRS
    assert total_triples == EXPECTED_ORDERED_TILE_TRIPLES
    assert total_entries_visited > 21_000_000
    assert total_entries_compared > 10_000_000
    # ⛔ ZERO. A shipped verdict difference is a stop, not a reconciliation.
    assert differences == []


def test_slovak_two_tile_allowlist_and_prefix_counts_are_unchanged() -> None:
    variant = load_variant("slovak")
    allowlist = load_two_tile_words(variant)
    assert allowlist is not None
    assert len(allowlist) == SLOVAK_TWO_TILE_ENTRIES
    authority = WordAuthority.for_variant(variant)
    prefixes = {""}
    for word in allowlist:
        for end in range(1, len(word) + 1):
            prefixes.add(word[:end])
    assert len(prefixes) == SLOVAK_TWO_TILE_PREFIXES
    for prefix in prefixes:
        assert authority.has_prefix(prefix), prefix


_LANGUAGE_LOCKS: tuple[tuple[str, str, bool], ...] = (
    ("english", "qi", True),
    ("english", "za", True),
    ("english", "fe", True),
    ("english", "qlet", False),
    ("english", "tranquil", True),
    ("english", "qx", False),
    ("slovak", "as", True),
    ("slovak", "ja", True),
    ("slovak", "aj", True),
    ("slovak", "ak", True),
    ("slovak", "či", True),
    ("slovak", "um", True),
    ("slovak", "mi", True),
    ("slovak", "ou", False),
    ("slovak", "am", False),
    ("slovak", "škola", True),
    ("slovak", "osameniu", True),
    ("slovak", "latinou", True),
    ("czech", "domu", True),
    ("czech", "knihy", True),
    ("czech", "qxqxqxqxq", False),
    ("polish", "domach", True),
    ("polish", "książki", True),
    ("polish", "qxqxqxqxq", False),
)

_QUERY_SURFACE: tuple[str, ...] = (
    "",
    " ",
    "a",
    "A",
    " qi ",
    "QI",
    "Qi",
    "qi\n",
    "hi!",
    "12",
    "q i",
    "l·la",
    "L·LA",
    "-",
    "?",
    "??",
    "škola",
    unicodedata.normalize("NFD", "škola"),
    "ŠKOLA",
    unicodedata.normalize("NFD", "ŠKOLA"),
    "ács",
    "ÁCS",
    "cs",
    "sz",
    "qzzzzz",
)


@pytest.mark.parametrize(("slug", "word", "expected"), _LANGUAGE_LOCKS)
def test_language_locks_hold_on_both_paths(slug: str, word: str, expected: bool) -> None:
    variant = load_variant(slug)
    index = load_prefix_index(variant.dictionary_path)
    allowlist = load_two_tile_words(variant)
    authority = WordAuthority.for_variant(variant)
    old = FROZEN_BASELINE_ORACLE(
        index.contains, word, two_letter_allowlist=allowlist
    )
    new = authority.accepts_word_query(word)
    assert old is expected, (slug, word)
    assert new is expected, (slug, word)


def test_public_query_surface_agrees_on_every_shipped_variant() -> None:
    """⛔ Any public-query difference also blocks the slice."""
    differences: list[tuple[str, str, bool, bool]] = []
    for variant in _shipped_variants():
        index = load_prefix_index(variant.dictionary_path)
        allowlist = load_two_tile_words(variant)
        authority = WordAuthority.for_variant(variant)
        for query in _QUERY_SURFACE:
            old = FROZEN_BASELINE_ORACLE(
                index.contains, query, two_letter_allowlist=allowlist
            )
            new = authority.accepts_word_query(query)
            if old != new:
                differences.append((variant.slug, query, old, new))
        _evict_variant_index(variant)
    print(
        f"parity query surface queries={len(_QUERY_SURFACE)} "
        f"variants={EXPECTED_SHIPPED_VARIANTS} differences={len(differences)}",
        flush=True,
    )
    assert differences == []


def test_nfd_token_sequences_agree_with_their_nfc_form() -> None:
    """Normalization, never accent folding: ``A`` must not become ``Á``."""
    variant = load_variant("slovak")
    index = load_prefix_index(variant.dictionary_path)
    allowlist = load_two_tile_words(variant)
    authority = WordAuthority.for_variant(variant)
    composed = ("Š", "K", "O", "L", "A")
    decomposed = tuple(unicodedata.normalize("NFD", token) for token in composed)
    assert decomposed != composed
    assert authority.accepts_tokens(composed) is True
    assert authority.accepts_tokens(decomposed) is True
    assert FROZEN_BASELINE_ORACLE(
        index.contains, "".join(decomposed), two_letter_allowlist=allowlist
    ) is True
    # ``Á`` is a different tile from ``A`` on both paths.
    assert authority.accepts_word_query("aj") is True
    assert authority.accepts_word_query("áj") is False
    assert (
        FROZEN_BASELINE_ORACLE(
            index.contains, "áj", two_letter_allowlist=allowlist
        )
        is False
    )


# ---------------------------------------------------------------------------
# 3. The six named synthetic disagreements — the new verdict is the correct one
# ---------------------------------------------------------------------------


def _digraph_variant(
    tmp_path: Path,
    *,
    slug: str,
    tokens: tuple[str, ...],
    entries: tuple[str, ...],
    two_tile: tuple[str, ...] | None,
    forbidden: tuple[tuple[str, ...], ...] = (),
) -> tuple[VariantDefinition, WordAuthority]:
    """A synthetic tile set with a REAL temporary lexicon on disk.

    ⛔ Only asset resolution is redirected. The index, the entry predicate, the
    two-tile lexicon and the authority are the production ones.
    """
    root = tmp_path / slug
    (root / "dicts").mkdir(parents=True)
    (root / "variants").mkdir(parents=True)
    (root / "dicts" / f"{slug}.txt").write_text(
        "".join(f"{entry}\n" for entry in entries), encoding="utf-8"
    )
    two_tile_file: str | None = None
    if two_tile is not None:
        two_tile_file = f"{slug}_two_tile.txt"
        (root / "dicts" / two_tile_file).write_text(
            "".join(f"{entry}\n" for entry in two_tile), encoding="utf-8"
        )
    variant = VariantDefinition(
        slug=slug,
        language="Synthetic",
        letters=tuple(
            VariantLetter(letter=token, count=2, points=index + 1)
            for index, token in enumerate(tokens)
        )
        + (VariantLetter(letter="?", count=1, points=0),),
        dictionary_file=f"{slug}.txt",
        two_tile_words_file=two_tile_file,
        alphabet_order=tokens,
        forbidden_token_sequences=forbidden,
    )

    # ``dictionary_path`` derives from ``get_assets_path()``; point that at the
    # throwaway root for the duration of this construction only.
    original = variant_store.get_assets_path
    variant_store.get_assets_path = lambda: root  # type: ignore[assignment]
    try:
        authority = WordAuthority.for_variant(variant)
        # Force the lexicon read while resolution is redirected.
        assert authority.contains_main(entries[0]) is True
    finally:
        variant_store.get_assets_path = original  # type: ignore[assignment]
    return variant, authority


def test_case_1_two_tiles_in_two_tile_authority_only_old_false_new_true(
    tmp_path: Path,
) -> None:
    """Á + CS present only in the two-tile authority: old false -> new TRUE."""
    variant, authority = _digraph_variant(
        tmp_path,
        slug="case1",
        tokens=("Á", "CS"),
        entries=("aaaa",),
        two_tile=("ács",),
    )
    tokens = ("Á", "CS")
    allowlist = authority.two_tile_words
    assert allowlist == frozenset({"ács"})
    old = FROZEN_BASELINE_ORACLE(
        authority.contains_main, "ÁCS", two_letter_allowlist=allowlist
    )
    assert old is False
    assert authority.route_tokens(tokens) == "two_tile"
    assert authority.accepts_tokens(tokens) is True
    assert variant.slug == "case1"


def test_case_2_two_tiles_in_main_dictionary_only_old_true_new_false(
    tmp_path: Path,
) -> None:
    """Á + CS present only in the main dictionary: old true -> new FALSE."""
    _variant, authority = _digraph_variant(
        tmp_path,
        slug="case2",
        tokens=("Á", "CS"),
        entries=("ács",),
        two_tile=("aa",),
    )
    allowlist = authority.two_tile_words
    old = FROZEN_BASELINE_ORACLE(
        authority.contains_main, "ÁCS", two_letter_allowlist=allowlist
    )
    assert old is True
    assert authority.route_tokens(("Á", "CS")) == "two_tile"
    assert authority.accepts_tokens(("Á", "CS")) is False


def test_case_3_three_tiles_in_main_dictionary_both_true(tmp_path: Path) -> None:
    """Á + C + S present in the main dictionary: both paths true."""
    _variant, authority = _digraph_variant(
        tmp_path,
        slug="case3",
        tokens=("Á", "C", "S"),
        entries=("ács",),
        two_tile=("aa",),
    )
    tokens = ("Á", "C", "S")
    old = FROZEN_BASELINE_ORACLE(
        authority.contains_main, "ÁCS", two_letter_allowlist=authority.two_tile_words
    )
    assert old is True
    assert authority.route_tokens(tokens) == "main"
    assert authority.accepts_tokens(tokens) is True


def test_case_4_one_physical_tile_with_a_two_letter_entry_old_true_new_false(
    tmp_path: Path,
) -> None:
    """One physical CS tile, lexical entry ``cs``: old true -> new FALSE.

    Fewer than two physical tiles despite a longer lexical string. One tile is
    never a complete word, however many code points it spells.
    """
    _variant, authority = _digraph_variant(
        tmp_path,
        slug="case4",
        tokens=("A", "CS"),
        entries=("aaaa",),
        two_tile=("cs",),
    )
    old = FROZEN_BASELINE_ORACLE(
        authority.contains_main, "CS", two_letter_allowlist=authority.two_tile_words
    )
    assert old is True
    assert authority.accepts_tokens(("CS",)) is False
    # And the same two code points as TWO tiles are decided on their own merits.
    assert authority.accepts_tokens(("A", "CS")) is False


def test_case_5_interpunct_token_admitted_by_a_custom_index_old_false_new_true(
    tmp_path: Path,
) -> None:
    """L·L + A admitted by a derived index predicate: old false -> new TRUE."""
    variant, authority = _digraph_variant(
        tmp_path,
        slug="case5",
        tokens=("A", "L·L"),
        entries=("l·la",),
        two_tile=None,
    )
    assert variant_entry_predicate(variant) is not None
    tokens = ("L·L", "A")
    old = FROZEN_BASELINE_ORACLE(authority.contains_main, "L·LA")
    assert old is False
    assert authority.two_tile_words is None
    assert authority.route_tokens(tokens) == "main"
    assert authority.accepts_tokens(tokens) is True
    # The derived predicate permits only THIS variant's declared nonletters.
    assert authority.contains_main("l·la") is True


def test_case_6_exact_forbidden_sequence_old_true_new_false(tmp_path: Path) -> None:
    """The exact declared sequence S + Z: old true -> new FALSE.

    THAT sequence only. A different segmentation of the same code points and a
    longer containing word are untouched.
    """
    _variant, authority = _digraph_variant(
        tmp_path,
        slug="case6",
        tokens=("A", "S", "SZ", "Z"),
        entries=("sz", "sza"),
        two_tile=None,
        forbidden=(("S", "Z"),),
    )
    old = FROZEN_BASELINE_ORACLE(authority.contains_main, "SZ")
    assert old is True
    assert authority.route_tokens(("S", "Z")) == "forbidden"
    assert authority.accepts_tokens(("S", "Z")) is False
    # Another segmentation of the same lexical string: not forbidden.
    assert authority.route_tokens(("SZ", "A")) == "main"
    assert authority.accepts_tokens(("SZ", "A")) is True
    # A longer word that CONTAINS the forbidden sequence: not forbidden.
    assert authority.route_tokens(("S", "Z", "A")) == "main"
    assert authority.accepts_tokens(("S", "Z", "A")) is True


# ---------------------------------------------------------------------------
# 4. The remaining disagreement categories
# ---------------------------------------------------------------------------


def test_none_two_tile_lexicon_differs_from_an_empty_one() -> None:
    """``None`` means "no two-tile lexicon". ``frozenset()`` means "none legal"."""
    absent = WordAuthority.from_words(("at", "ate"), two_tile_words=None)
    empty = WordAuthority.from_words(("at", "ate"), two_tile_words=frozenset())
    assert absent.route_tokens(("A", "T")) == "main"
    assert absent.accepts_tokens(("A", "T")) is True
    assert empty.route_tokens(("A", "T")) == "two_tile"
    assert empty.accepts_tokens(("A", "T")) is False
    # Three tiles are unaffected by either choice.
    assert absent.accepts_tokens(("A", "T", "E")) is True
    assert empty.accepts_tokens(("A", "T", "E")) is True


def test_word_found_requires_matching_tokens_coordinates_and_lexical_text() -> None:
    ok = WordFound("AT", [(7, 7), (7, 8)], ["A", "T"])
    assert ok.tokens == ["A", "T"]
    with pytest.raises(ValueError, match="coordinate"):
        WordFound("AT", [(7, 7)], ["A", "T"])
    with pytest.raises(ValueError, match="concatenat"):
        WordFound("AT", [(7, 7), (7, 8)], ["A", "X"])
    with pytest.raises(ValueError, match="concatenat"):
        WordFound("ÁCS", [(7, 7), (7, 8)], ["Á", "C"])


def test_search_membership_and_prefix_shortcuts_reach_a_two_tile_only_word() -> None:
    authority = WordAuthority.from_words((), two_tile_words=frozenset({"ács"}))
    # Advisory lexical membership stays available for search pruning...
    assert authority.is_lexical_word("ÁCS") is True
    # ...and is NOT the legality gate: the physical decision is separate.
    assert authority.accepts_tokens(("Á", "CS")) is True
    assert authority.accepts_tokens(("Á", "C", "S")) is False
    assert authority.has_prefix("Á") is True
    assert authority.has_prefix("ÁCS") is True
    assert authority.has_main_prefix("ÁCS") is False


def test_lexical_membership_never_substitutes_for_final_legality() -> None:
    """``AM`` is a Slovak lexicon entry that formed-word authority rejects.

    ⛔ BOUNDARY 2. ``is_lexical_word`` is the PERMISSIVE advisory prune and says
    yes here; the authority says no. Substituting the former for final legality
    would make ``AM`` playable, which is the defect the two-tile lexicon exists
    to prevent.
    """
    authority = WordAuthority.for_variant(load_variant("slovak"))
    assert authority.contains_main("am") is True
    assert authority.is_lexical_word("am") is True
    assert authority.accepts_tokens(("A", "M")) is False
    assert authority.accepts_word_query("am") is False
    # Structural half of the boundary: no production module reaches for the
    # advisory prune at all.
    for directory in ("gamecore", "game"):
        for path in sorted((_REPO_ROOT / "backend" / directory).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if path.name == "word_authority.py":
                continue
            assert "is_lexical_word" not in text, path
    board = Board(get_premiums_path())
    board.cells[6][7].token = "A"
    result = evaluate_scoring_move(
        board,
        ["M", "I"],
        (Placement(7, 7, "M"), Placement(7, 8, "I")),
        letters=frozenset(load_variant("slovak").playable_letters),
        variant="slovak",
        authority=authority,
    )
    assert result.reason_code == REASON_INVALID_WORD
    assert result.total_score == 0
    assert "am" in {word.casefold() for word in result.words}


def test_no_language_slug_branch_in_gamecore_or_game() -> None:
    """Closure condition 6 stays satisfied: authority is data, not a slug switch."""
    slugs = tuple(variant.slug for variant in _shipped_variants())
    for directory in ("gamecore", "game"):
        for path in sorted((_REPO_ROOT / "backend" / directory).rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            for slug in slugs:
                if slug == "english":
                    # ``_DEFAULT_VARIANT_SLUG`` and the settings default are not
                    # a branch on language behaviour.
                    continue
                assert f'== "{slug}"' not in text, (path, slug)
                assert f'"{slug}" ==' not in text, (path, slug)


# ---------------------------------------------------------------------------
# 5. Deterministic move fixtures, pinned at the baseline, controlled clock
# ---------------------------------------------------------------------------


class _FrozenClock:
    """Elapsed time cannot hide a behaviour change if it never advances."""

    @staticmethod
    def perf_counter() -> float:
        return 1000.0


@pytest.fixture()
def frozen_search_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(move_search, "time", _FrozenClock)


def _english_authority() -> WordAuthority:
    return WordAuthority.for_variant(load_variant("english"))


def _empty_board() -> Board:
    return Board(get_premiums_path())


def test_witness_search_matches_the_pinned_baseline(
    frozen_search_clock: None,
) -> None:
    authority = _english_authority()
    board = _empty_board()
    result = move_search.find_legal_scoring_move(board, ["A", "T"], authority=authority)
    assert result.status == "found"
    assert result.complete is True
    assert result.witness == (Placement(7, 6, "A"), Placement(7, 7, "T"))
    assert result.words == ("AT",)
    assert result.total_score == 4
    assert result.nodes == 3
    assert result.elapsed_ms == 0

    legality = evaluate_scoring_move(
        board, ["A", "T"], result.witness, authority=authority
    )
    assert legality.ok is True
    assert legality.reason_code == REASON_OK
    assert legality.total_score == 4
    assert legality.words == ("AT",)
    assert [
        (
            item.word,
            item.base_points,
            item.letter_bonus_points,
            item.word_multiplier,
            item.total,
        )
        for item in legality.breakdowns
    ] == [("AT", 2, 0, 2, 4)]


def test_ranked_search_matches_the_pinned_baseline(frozen_search_clock: None) -> None:
    authority = _english_authority()
    result = move_search.find_ranked_scoring_moves(
        _empty_board(), list("QUIZERS"), authority=authority, bag_count=86
    )
    assert result.status == "found"
    assert result.complete is True
    assert result.nodes == 2408
    assert result.unique_placements == 350
    assert result.elapsed_ms == 0
    assert len(result.candidates) == 8
    top = result.candidates[0]
    assert top.placements == (
        Placement(7, 7, "S"),
        Placement(7, 8, "Q"),
        Placement(7, 9, "U"),
        Placement(7, 10, "I"),
        Placement(7, 11, "Z"),
    )
    assert top.words == ("SQUIZ",)
    assert top.total_score == 66
    assert top.tiles_used == 5
    assert top.leave_value == 200
    assert top.rack_out is False
    assert [candidate.total_score for candidate in result.candidates] == sorted(
        (candidate.total_score for candidate in result.candidates), reverse=True
    )


def test_blank_premium_and_bingo_scoring_match_the_pinned_baseline() -> None:
    authority = _english_authority()
    english = load_variant("english")
    board = _empty_board()
    placements = [Placement(7, 7, "?", "A"), Placement(7, 8, "T")]

    legality = evaluate_scoring_move(board, ["?", "T"], placements, authority=authority)
    assert legality.ok is True
    assert legality.total_score == 2
    assert legality.words == ("AT",)
    assert [
        (item.word, item.base_points, item.letter_bonus_points, item.word_multiplier)
        for item in legality.breakdowns
    ] == [("AT", 1, 0, 2)]

    board.place_letters(placements)
    assert board.cells[7][7].token == "?"
    assert board.cells[7][7].blank_as == "A"
    assert board.cells[7][7].realized_token == "A"
    assert board.cells[7][8].token == "T"
    assert board.cells[7][8].blank_as is None
    words = board.build_words_for_move(placements)
    assert words[0].tokens == ["A", "T"]
    before, _ = score_words(
        board, placements, [(word.word, word.letters) for word in words], variant=english
    )
    apply_premium_consumption(board, placements)
    after, _ = score_words(
        board, placements, [(word.word, word.letters) for word in words], variant=english
    )
    assert (before, after) == (2, 1)

    bingo_board = _empty_board()
    bingo_authority = WordAuthority.from_words(("QUIZERS",))
    bingo = evaluate_scoring_move(
        bingo_board,
        list("QUIZERS"),
        [Placement(7, column, letter) for column, letter in zip(range(4, 11), "QUIZERS")],
        authority=bingo_authority,
    )
    assert bingo.ok is True
    assert bingo.total_score == 100
    assert bingo.words == ("QUIZERS",)


def test_slovak_rejection_fixture_matches_the_pinned_baseline() -> None:
    variant = load_variant("slovak")
    authority = WordAuthority.for_variant(variant)
    board = _empty_board()
    board.cells[6][7].letter = "O"
    result = evaluate_scoring_move(
        board,
        ["U", "M"],
        (Placement(7, 7, "U"), Placement(7, 8, "M")),
        letters=frozenset(variant.playable_letters),
        variant="slovak",
        authority=authority,
    )
    assert result.ok is False
    assert result.reason_code == REASON_INVALID_WORD
    assert result.reason == "Invalid word(s): OU"
    assert result.total_score == 0
    assert result.words == ("UM", "OU")
    assert [(item.word, item.valid) for item in result.word_results] == [
        ("UM", True),
        ("OU", False),
    ]


class PersistedPayloadParityTests(TestCase):
    """The human persist path: verdict loop, rack, bag and persisted payload."""

    def _english_game(self) -> tuple[GameSession, PlayerSlot, User]:
        user = User.objects.create_user(username="parity-human", password="pass1234")
        session = GameSession.objects.create(
            game_mode="vs_human",
            status="active",
            variant_slug="english",
            current_turn_slot=0,
            bag_tiles=["E", "R", "S", "I", "N", "O", "D", "X", "Y"],
        )
        slot = PlayerSlot.objects.create(
            game=session, slot=0, user=user, is_ai=False, rack=["A", "T"]
        )
        PlayerSlot.objects.create(
            game=session, slot=1, user=None, is_ai=False, rack=["B", "C"]
        )
        return session, slot, user

    def test_human_persisted_move_payload_matches_the_pinned_baseline(self) -> None:
        session, slot, user = self._english_game()
        result = services.submit_move_for_user(
            game_id=str(session.public_id),
            user_id=user.id,
            placements_data=[
                {"row": 7, "col": 6, "letter": "A"},
                {"row": 7, "col": 7, "letter": "T"},
            ],
        )
        assert result["ok"] is True
        assert result["points"] == 4
        assert result["bingo"] is False
        assert result["game_over"] is False
        assert result["words"] == [{"word": "AT", "score": 4}]
        assert result["new_rack"] == ["E", "R", "S", "I", "N", "O", "D"]
        assert result["bag_remaining"] == 2
        session.refresh_from_db()
        assert session.board_state[7][6] == {"token": "A", "blank_as": None}
        assert session.board_state[7][7] == {"token": "T", "blank_as": None}
        assert session.board_state[7][8] is None
        assert session.premium_used == [{"row": 7, "col": 7}]
        assert session.bag_tiles == ["X", "Y"]
        slot.refresh_from_db()
        assert slot.rack == ["E", "R", "S", "I", "N", "O", "D"]
        assert slot.score == 4
        move = session.moves.get()
        assert move.kind == "place"
        assert move.points == 4
        assert move.words_formed == [
            {
                "word": "AT",
                "score": 4,
                "multiplier": 2,
                "coords": [{"row": 7, "col": 6}, {"row": 7, "col": 7}],
            }
        ]

    def test_human_persisted_move_rejects_an_invalid_word_through_the_authority(
        self,
    ) -> None:
        session, slot, user = self._english_game()
        slot.rack = ["Q", "X"]
        slot.save(update_fields=["rack"])
        result = services.submit_move_for_user(
            game_id=str(session.public_id),
            user_id=user.id,
            placements_data=[
                {"row": 7, "col": 6, "letter": "Q"},
                {"row": 7, "col": 7, "letter": "X"},
            ],
        )
        assert result["ok"] is False
        assert result["invalid_words"] == ["QX"]
        assert result["error"] == "Invalid word(s): QX"
        session.refresh_from_db()
        assert session.moves.count() == 0
        assert session.board_state[7][6] is None

    def test_validate_words_stays_an_advisory_string_query(self) -> None:
        session, _slot, user = self._english_game()
        rows = services.validate_words(
            game_id=str(session.public_id),
            user_id=user.id,
            words=["qi", "qlet", "a", "hi!", " za "],
        )
        assert rows == [
            {"word": "qi", "valid": True, "source": "collins2019"},
            {"word": "qlet", "valid": False, "source": "collins2019"},
            {"word": "a", "valid": False, "source": "collins2019"},
            {"word": "hi!", "valid": False, "source": "collins2019"},
            {"word": " za ", "valid": True, "source": "collins2019"},
        ]
