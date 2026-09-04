"""Generic variant invariants: one harness parameterized over EVERY installed variant.

Scope boundary. This module owns the invariants that must hold for *any* language.
Per-variant data — 100 tiles, 205 nominal points, 42 alphabet tokens, the tileless
sets ``{CH, Q, W}`` — is owned by ``tests/test_slovak_variant.py`` and
``tests/test_czech_polish_variants.py`` and is deliberately not restated here.

Two rules this module must never break:

* ``len(token)`` is a RESOURCE BOUND, never a tile count (``gamecore/types.py:6-11``).
  Nothing here asserts ``len(token) == 1``; Czech ``CH`` and Slovak ``DZ``/``DŽ`` are
  legitimate multi-code-point alphabet tokens.
* the tile/alphabet subset invariant runs in ONE direction only. Every non-blank tile
  token must appear in ``alphabet_order``; an alphabet letter with no tile is normal
  and shipped (Slovak ``DZ DŽ CH Q W``, Czech ``CH Q W``).

The parameterization is driven by the live installed set rather than a literal list,
so a fifth manifest is covered the moment it lands. ``G1`` and ``G9`` guard the
parameterization itself: ``list_installed_variants`` logs and SKIPS a manifest it
cannot load (``gamecore/variant_store.py:538-545``), so without a count comparison a
broken manifest would be invisible to this harness as well as to the product.
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

from gamecore.assets import get_assets_path
from gamecore.fastdict import load_prefix_index
from gamecore.variant_store import (
    MAX_TILE_TOKEN_CODEPOINTS,
    VariantDefinition,
    VariantManifestError,
    _BLANK_ALIASES,
    _load_variant_from_path,
    canonicalize_tile_token,
    list_installed_variants,
    load_two_tile_words,
    load_variant,
    slugify,
    validate_dictionary_file,
)

_INSTALLED = list_installed_variants()
_SLUGS = [variant.slug for variant in _INSTALLED]
# Containment, never equality: a fifth manifest must not break this harness.
_REQUIRED_SLUGS = frozenset({"english", "slovak", "czech", "polish"})
_LANGUAGE_CODE_RE = re.compile(r"[a-z-]{2,8}")

# A RANGE CHECK IS NOT A CORRECTNESS CHECK. A candidate lexicon can sit comfortably
# inside every mechanical bound and still be the wrong word list; only membership of
# real inflected forms catches that. Each present-word claim below is already proven
# by an existing test in this repository:
#   english  tests/test_dictionary_validation.py:32-34
#   slovak   tests/test_slovak_engine.py:43-46  (absent from Collins, present in Slovak)
#   czech    tests/test_czech_polish_variants.py:102-103
#   polish   tests/test_czech_polish_variants.py:105-106
_NEGATIVE_PROBE = "qxqxqxqxq"
_LEXICON_PROBES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "english": (("qi", "za", "fe"), (_NEGATIVE_PROBE,)),
    "slovak": (("škola",), (_NEGATIVE_PROBE,)),
    "czech": (("domu", "knihy"), (_NEGATIVE_PROBE,)),
    "polish": (("domach", "książki"), (_NEGATIVE_PROBE,)),
    # ⛔ `more` is the FOLDED form of `môre`. The Afrikaans edition bears plain Latin tiles and
    # ignores diacritics, so build_afrikaans_lexicon.py folds them and `môre` is unreachable
    # while MORE must be playable. Keeping a folded witness here means a build that silently
    # stopped folding fails this probe rather than shipping 4 614 unplayable words.
    "afrikaans": (("die", "van", "more"), (_NEGATIVE_PROBE,)),
    # ⛔ `citta` and `perche` are FOLDED forms of `città` and `perché`. The Italian edition
    # bears plain Latin tiles and ignores diacritic marks, so the fold is what makes them
    # playable; a build that stopped folding fails here instead of shipping 34 114 dead words.
    "italian": (("casa", "citta", "perche"), (_NEGATIVE_PROBE,)),
    # ⛔ `ijs` and `dijk` are LIGATURE witnesses: upstream nl_NL spells them with U+0133, and
    # the modern Dutch edition has no IJ tile, so build_dutch_lexicon.py writes them as `ij`.
    # Both are absent from the raw expansion and present after the rewrite — measured. `reeel`
    # is the separate diacritic-fold witness, from `reëel`.
    "dutch": (("kaas", "ijs", "dijk", "reeel"), (_NEGATIVE_PROBE,)),
    # ⛔ `strasse` is `Straße` after Unicode full case folding, which expands eszett on its own —
    # the German edition has no eszett tile. `käse` is the PRESERVATION witness: German Ä Ö Ü
    # are tiles worth 6, 8 and 6 points, so the fold that Afrikaans, Italian and Dutch apply
    # totally must stay PARTIAL here. If someone makes it total, this probe fails instead of
    # 155 641 playable words disappearing.
    "german": (("haus", "strasse", "käse"), (_NEGATIVE_PROBE,)),
}

_BLANK_ENTRY: dict[str, Any] = {"letter": "?", "count": 2, "points": 0}
_A_ENTRY: dict[str, Any] = {"letter": "A", "count": 98, "points": 1}


def _variants_dir() -> Path:
    """Derive the manifest directory the way the loader does, never hardcoded."""
    return get_assets_path() / "variants"


# The manifest PATHS, for the invariants that are about files rather than about loaded
# variants. An empty list here cannot pass unnoticed: G1 requires the loaded set to
# contain the four shipped slugs and G9 ties the loaded count to this file count, so
# either would fail loudly before a vacuous parameterization could hide.
_MANIFEST_PATHS = sorted(_variants_dir().glob("*.json"))
_MANIFEST_STEMS = [path.stem for path in _MANIFEST_PATHS]

# Keys that duplicate a DERIVED property of VariantDefinition and must therefore never
# be declared in a manifest. Each name below was confirmed to be a ``property`` on
# VariantDefinition, with no declared counterpart:
#   total_tiles       variant_store.py:104-106  sum of letter counts
#   distribution      variant_store.py:96-98    {token: count}
#   tile_points       variant_store.py:100-102  {token: points}
#   playable_letters  variant_store.py:124-135  tile set ordered by alphabet index
#   display_label     variant_store.py:108-112  composed from language and variant_name
# dictionary_file and two_tile_words_file are deliberately absent from this tuple: they
# are legitimate declared INPUTS whose derived twins are dictionary_path and
# two_tile_words_path.
# ⛔ lexicon_provenance is a DECLARED key, not a derived property, and must never be added
# here: all four shipped manifests declare it.
_FORBIDDEN_DERIVED_KEYS = (
    "total_tiles",
    "distribution",
    "tile_points",
    "playable_letters",
    "display_label",
)

# The other side of the same classification: a derived property whose manifest twin is a
# legitimate INPUT under a different name. G27b keeps the two sets exhaustive, so a future
# derived property forces a deliberate decision instead of quietly landing in neither.
_DERIVED_KEYS_WITH_DECLARED_TWINS = {
    "dictionary_path": "dictionary_file",
    "two_tile_words_path": "two_tile_words_file",
}


def _declared_tokens(variant: VariantDefinition) -> list[str]:
    return [item.letter for item in variant.letters] + list(variant.alphabet_order)


def _tile_tokens(variant: VariantDefinition) -> set[str]:
    return {item.letter for item in variant.letters if item.letter != "?"}


def _write_manifest(directory: Path, slug: str, payload: dict[str, Any]) -> Path:
    path = directory / f"{slug}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _synthetic(slug: str, **overrides: Any) -> dict[str, Any]:
    """A minimal loadable manifest, overridable one key at a time.

    ``dictionary_file`` always names a real lexicon. ``validate_dictionary_file`` runs
    at ``variant_store.py:432``, BEFORE ``alphabet_order`` is parsed at ``:442``, so a
    synthetic manifest pointing at an absent lexicon would raise ``FileNotFoundError``
    first and the intended ``VariantManifestError`` would never fire.
    """
    payload: dict[str, Any] = {
        "language": "Synthetic",
        "slug": slug,
        "dictionary_file": "collins2019.txt",
        "alphabet_order": ["A"],
        "letters": [_BLANK_ENTRY, _A_ENTRY],
    }
    payload.update(overrides)
    return payload


def _load_synthetic(
    tmp_path: Path, slug: str, *, drop: tuple[str, ...] = (), **overrides: Any
) -> VariantDefinition:
    payload = _synthetic(slug, **overrides)
    for key in drop:
        payload.pop(key, None)
    return _load_variant_from_path(_write_manifest(tmp_path, slug, payload))


# --- Guards on the parameterization itself ---------------------------------------------


def test_g1_installed_list_is_non_empty_and_contains_the_shipped_slugs() -> None:
    assert _INSTALLED, (
        "list_installed_variants() returned nothing; every parameterized test in this "
        "module would pass vacuously"
    )
    assert len(_SLUGS) == len(set(_SLUGS)), f"duplicate slugs in the installed set: {_SLUGS}"
    missing = sorted(_REQUIRED_SLUGS - set(_SLUGS))
    assert not missing, f"installed set is missing shipped variants: {missing}"


def test_g9_installed_count_matches_manifest_file_count() -> None:
    files = sorted(_variants_dir().glob("*.json"))
    loaded = list_installed_variants()
    assert len(loaded) == len(files), (
        "list_installed_variants() logs and SKIPS a manifest it cannot load; "
        f"{len(files)} manifest files produced {len(loaded)} variants "
        f"(loaded={[item.slug for item in loaded]}, files={[item.name for item in files]})"
    )


def test_g9c_installed_count_detects_a_manifest_the_loader_skips(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove G9 can fail: the count comparison must notice a silently skipped manifest.

    This monkeypatches ``variant_store._variants_dir`` (the LOADER list). The existing
    ``test_czech_polish_variants.py:201`` monkeypatches ``game.views._variant_json_dir``
    (the VIEW). They are two different functions and both are legitimate.
    """
    _write_manifest(tmp_path, "alpha", _synthetic("alpha"))
    _write_manifest(tmp_path, "beta", _synthetic("beta"))
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    monkeypatch.setattr("gamecore.variant_store._variants_dir", lambda: tmp_path)

    files = sorted(tmp_path.glob("*.json"))
    loaded = list_installed_variants()
    assert len(files) == 3
    assert [item.slug for item in loaded] == ["alpha", "beta"]
    assert "broken" not in {item.slug for item in loaded}
    assert len(loaded) != len(files), "the G9 count comparison failed to detect the skip"


# --- Structural invariants, over every installed variant --------------------------------


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g2_declared_tokens_are_canonical(variant: VariantDefinition) -> None:
    for token in _declared_tokens(variant):
        assert canonicalize_tile_token(token) == token, f"{variant.slug}: {token!r}"
        assert unicodedata.normalize("NFC", token) == token, f"{variant.slug}: {token!r}"
        assert not any(character.isspace() for character in token), f"{variant.slug}: {token!r}"
        assert not any(
            unicodedata.category(character).startswith("C") for character in token
        ), f"{variant.slug}: {token!r} contains a control character"
        # A resource bound, never a tile count: Czech CH and Slovak DZ are two code points.
        assert 1 <= len(token) <= MAX_TILE_TOKEN_CODEPOINTS, f"{variant.slug}: {token!r}"


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g3_tile_tokens_are_pairwise_distinct(variant: VariantDefinition) -> None:
    tiles = [item.letter for item in variant.letters if item.letter != "?"]
    assert len(tiles) == len(set(tiles)), f"{variant.slug}: duplicate tile token in {tiles}"
    canonical = {canonicalize_tile_token(token) for token in tiles}
    assert len(tiles) == len(canonical), f"{variant.slug}: tokens collide after canonicalization"


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g4_exactly_one_blank_record(variant: VariantDefinition) -> None:
    blanks = [item for item in variant.letters if item.letter == "?"]
    assert len(blanks) == 1, f"{variant.slug}: expected exactly one '?' entry, got {len(blanks)}"
    assert blanks[0].count >= 1
    assert blanks[0].points == 0
    assert "?" not in variant.alphabet_order
    for token in sorted(_tile_tokens(variant)):
        assert token not in _BLANK_ALIASES, f"{variant.slug}: {token!r} is a reserved blank alias"


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g5_derived_arithmetic_is_consistent(variant: VariantDefinition) -> None:
    # No specific total is asserted here: 100 is per-variant data owned elsewhere.
    assert variant.total_tiles == sum(item.count for item in variant.letters)
    assert variant.total_tiles > 0
    assert all(item.count >= 1 for item in variant.letters), f"{variant.slug}: count < 1"
    assert all(item.points >= 0 for item in variant.letters), f"{variant.slug}: points < 0"
    assert set(variant.distribution) == {item.letter for item in variant.letters}


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g6_alphabet_order_is_well_formed(variant: VariantDefinition) -> None:
    order = variant.alphabet_order
    assert order, f"{variant.slug}: alphabet_order is empty"
    assert len(order) == len(set(order)), f"{variant.slug}: duplicate alphabet_order token"
    for token in order:
        assert unicodedata.normalize("NFC", token) == token, f"{variant.slug}: {token!r}"
    assert "?" not in order


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g7_every_tile_token_appears_once_in_alphabet_order(variant: VariantDefinition) -> None:
    # One direction only. The reverse is NOT an invariant: Slovak ships DZ DŽ CH Q W and
    # Czech ships CH Q W as alphabet letters with no tile.
    tiles = _tile_tokens(variant)
    order = variant.alphabet_order
    missing = sorted(tiles - set(order))
    assert not missing, f"{variant.slug}: tile tokens absent from alphabet_order: {missing}"
    for token in sorted(tiles):
        assert order.count(token) == 1, f"{variant.slug}: {token!r} is not unique in alphabet_order"


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g8_playable_letters_is_the_tile_set_in_alphabet_order(variant: VariantDefinition) -> None:
    playable = variant.playable_letters
    tiles = _tile_tokens(variant)
    assert "?" not in playable
    assert set(playable) == tiles
    assert len(playable) == len(set(playable))
    index = {token: position for position, token in enumerate(variant.alphabet_order)}
    assert playable == tuple(sorted(tiles, key=lambda token: index[token]))


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g10_declared_asset_references_resolve(variant: VariantDefinition) -> None:
    assert variant.dictionary_path.is_file(), f"{variant.slug}: {variant.dictionary_file}"
    assert validate_dictionary_file(variant.dictionary_file) == variant.dictionary_file
    two_tile = load_two_tile_words(variant)
    if variant.two_tile_words_file is None:
        assert variant.two_tile_words_path is None
        assert two_tile is None
    else:
        assert validate_dictionary_file(variant.two_tile_words_file) == variant.two_tile_words_file
        assert variant.two_tile_words_path is not None
        assert variant.two_tile_words_path.is_file()
        assert isinstance(two_tile, frozenset)
        assert two_tile, f"{variant.slug}: two-tile set is empty"


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g11_extension_points_are_identity_today(variant: VariantDefinition) -> None:
    # Pins the CURRENT identity behaviour of variant_store.py:137-143 so that a future
    # non-identity lexical or display mapping is a deliberate, visible change.
    for token in sorted(_tile_tokens(variant)):
        assert variant.lexical_contribution(token) == token
        assert variant.tile_display(token) == token


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g12_starting_draw_order_is_blank_first_then_alphabet(variant: VariantDefinition) -> None:
    tiles = _tile_tokens(variant)
    blank_key = variant.starting_draw_order_key("?")
    for token in sorted(tiles):
        assert blank_key < variant.starting_draw_order_key(token), f"{variant.slug}: {token!r}"
    ordered = [token for token in variant.alphabet_order if token in tiles]
    keys = [variant.starting_draw_order_key(token) for token in ordered]
    assert all(
        earlier < later for earlier, later in zip(keys, keys[1:])
    ), f"{variant.slug}: draw keys are not strictly increasing along alphabet_order"


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g13_metadata_shape_tolerates_the_declared_asymmetry(variant: VariantDefinition) -> None:
    assert variant.slug
    assert variant.slug == slugify(variant.slug), f"{variant.slug!r} is not canonical slug form"
    assert variant.language.strip()
    assert variant.display_label.strip()
    assert isinstance(variant.source, str)
    assert variant.source
    if variant.fetched_at is not None:
        assert isinstance(variant.fetched_at, str)
        # A real calendar date at minimum. datetime.fromisoformat ALONE is too weak: on
        # this interpreter it accepts ISO basic format ("20260901") and ISO week dates
        # ("2026-W36-4"), neither of which is a reviewable YYYY-MM-DD. A timezone is
        # deliberately NOT required — the four shipped values are naive timestamps.
        assert len(variant.fetched_at) >= 10, (
            f"{variant.slug}: fetched_at {variant.fetched_at!r} is too short to carry a "
            "YYYY-MM-DD calendar date"
        )
        parsed = datetime.fromisoformat(variant.fetched_at)
        stamp = f"{parsed.year:04d}-{parsed.month:02d}-{parsed.day:02d}"
        assert variant.fetched_at[:10] == stamp, (
            f"{variant.slug}: fetched_at {variant.fetched_at!r} does not begin with the "
            f"calendar date it parses to ({stamp})"
        )
    # english.json declares NEITHER language_code NOR source_url; None must pass.
    if variant.language_code is not None:
        assert variant.language_code == variant.language_code.strip()
        assert _LANGUAGE_CODE_RE.fullmatch(variant.language_code) is not None, (
            f"{variant.slug}: language_code {variant.language_code!r} is not 2..8 "
            "ASCII-lowercase letters and hyphens"
        )
    if variant.source_url is not None:
        assert variant.source_url.startswith("https://"), f"{variant.slug}: {variant.source_url!r}"


@pytest.mark.parametrize("variant", _INSTALLED, ids=_SLUGS)
def test_g14_inflected_form_membership_probe(variant: VariantDefinition) -> None:
    assert variant.slug in _LEXICON_PROBES, (
        f"variant {variant.slug!r} is installed but has no lexicon probe. A range check "
        "is not a correctness check: add a tuple of real inflected forms and a tuple of "
        f"nonsense strings for {variant.slug!r} to _LEXICON_PROBES in this module."
    )
    present, absent = _LEXICON_PROBES[variant.slug]
    assert present, f"{variant.slug}: probe table has no positive words"
    assert _NEGATIVE_PROBE in absent, f"{variant.slug}: probe table has no negative word"
    # DEFAULT keyword arguments only, so this hits fastdict._INDEX_CACHE instead of
    # loading a second copy of a 50 MB lexicon.
    contains = load_prefix_index(variant.dictionary_path).contains
    for word in present:
        assert contains(word) is True, f"{variant.slug}: expected {word!r} in the lexicon"
    for word in absent:
        assert contains(word) is False, f"{variant.slug}: {word!r} must not be in the lexicon"


# --- Manifest-file invariants: stem/slug agreement and no declared derived key ----------


@pytest.mark.parametrize("manifest_path", _MANIFEST_PATHS, ids=_MANIFEST_STEMS)
def test_g26a_manifest_stem_equals_declared_slug(manifest_path: Path) -> None:
    """The ``{stem: slug}`` pair of every installed manifest must be equal.

    ``load_variant(slug)`` resolves a FILENAME — ``_variant_path`` at
    ``variant_store.py:207-208`` builds ``f"{slugify(slug)}.json"`` — while
    ``list_installed_variants`` advertises the DECLARED ``slug`` key
    (``variant_store.py:386``). When the two diverge the loader now rejects the
    manifest with code ``slug_stem_mismatch``, so ``G9``'s count comparison sees the
    gap; ``G26b`` pins that rejection. This test keeps the repository's own manifests
    honest so that rejection is never reached in practice.
    """
    stem = manifest_path.stem
    pair = {stem: _load_variant_from_path(manifest_path).slug}
    assert pair[stem] == stem, (
        f"manifest {manifest_path.name} declares slug {pair[stem]!r} but its filename "
        f"stem is {stem!r}; list_installed_variants() would advertise {pair[stem]!r} as "
        f"selectable while load_variant({pair[stem]!r}) raises FileNotFoundError"
    )


def test_g26b_a_stem_slug_divergence_is_rejected_at_ingest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest whose declared slug disagrees with its own filename cannot be loaded.

    Before this rule, a manifest named ``de.json`` declaring ``"slug": "german"`` was
    advertised as selectable under ``german`` and could never be loaded under it. That was
    reachable from the product because every incoming ``variant_slug`` is validated
    against ``list_installed_variants()`` at ``game/serializers.py:180``,
    ``game/serializers.py:215`` and ``game/services.py:173``, while every later load goes
    through ``load_variant``, which resolves a FILENAME.

    The divergence is now closed at ingest instead. ``load_variant``,
    ``list_installed_variants``, ``_variant_path``, ``slugify`` and the three call sites
    above are all deliberately unchanged.
    """
    _write_manifest(tmp_path, "de", _synthetic("german"))
    monkeypatch.setattr("gamecore.variant_store._variants_dir", lambda: tmp_path)
    files = sorted(tmp_path.glob("*.json"))
    assert [path.stem for path in files] == ["de"]

    with pytest.raises(VariantManifestError) as caught:
        _load_variant_from_path(files[0])
    assert caught.value.code == "slug_stem_mismatch"

    # G9 is no longer blind to this class: list_installed_variants() logs and SKIPS the
    # manifest, so one manifest file now produces ZERO variants and the count comparison
    # sees the gap.
    listed = list_installed_variants()
    assert listed == []
    assert len(listed) != len(files)

    # The lookup path was deliberately left alone, and stays observable as such.
    with pytest.raises(FileNotFoundError):
        load_variant("german")
    # Not even the filename route can load it: the rejection is fail-closed both ways.
    with pytest.raises(VariantManifestError) as caught_by_stem:
        load_variant("de")
    assert caught_by_stem.value.code == "slug_stem_mismatch"


def test_g28_a_non_canonical_manifest_filename_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A filename that is not already in canonical slug form can never be resolved.

    Measured before this condition existed: ``De_Ch.json`` declaring ``"slug": "de-ch"``
    was ACCEPTED, ``list_installed_variants()`` advertised it as ``'de-ch'``, and it was
    unloadable under BOTH names — ``load_variant('de-ch')`` and ``load_variant('De_Ch')``
    each raised ``FileNotFoundError: Variant ... not found`` — because ``_variant_path``
    looks for ``f"{slugify(slug)}.json"`` and no such file exists on disk.

    Comparing the declared slug against ``slugify(path.stem)`` cannot see this: both
    values were ``'de-ch'``. The RAW filename is a third value, and it is the one that
    decides whether the file can be found, which is why the loader needs its own
    ``path.stem != slugify(path.stem)`` condition.
    """
    path = _write_manifest(tmp_path, "De_Ch", _synthetic("de-ch"))
    monkeypatch.setattr("gamecore.variant_store._variants_dir", lambda: tmp_path)
    assert path.stem == "De_Ch"
    assert slugify(path.stem) == "de-ch"

    with pytest.raises(VariantManifestError) as caught:
        _load_variant_from_path(path)
    assert caught.value.code == "slug_stem_mismatch"

    assert list_installed_variants() == []
    for candidate in ("de-ch", "De_Ch"):
        with pytest.raises(FileNotFoundError):
            load_variant(candidate)


@pytest.mark.parametrize("manifest_path", _MANIFEST_PATHS, ids=_MANIFEST_STEMS)
def test_g27_no_manifest_declares_a_derived_property(manifest_path: Path) -> None:
    """Read as RAW JSON, because the loader silently ignores unknown keys.

    ``total_tiles`` is DERIVED at ``variant_store.py:104-106`` as the sum of letter counts,
    so a declared value could disagree with the real tile set: it would read as
    authoritative to a human reviewer while being completely ignored by the code. The
    same reasoning applies to every other manifest key that duplicates a derived
    property of ``VariantDefinition``.
    """
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    declared = sorted(key for key in _FORBIDDEN_DERIVED_KEYS if key in data)
    assert not declared, (
        f"manifest {manifest_path.name} declares derived key(s) {declared}; each is a "
        "computed property of VariantDefinition, so a declared value is silently ignored "
        "by the loader while looking authoritative to a reader"
    )


def test_g27b_every_derived_property_is_classified() -> None:
    """Neither set may quietly grow a third category.

    ``_FORBIDDEN_DERIVED_KEYS`` and ``_DERIVED_KEYS_WITH_DECLARED_TWINS`` must together
    cover EVERY ``property`` on ``VariantDefinition``. Without this, a future derived
    property would land in neither set and G27 would be blind to it — which is exactly how
    ``display_label`` stayed unguarded until this exchange.
    """
    derived = {
        name
        for name, member in vars(VariantDefinition).items()
        if isinstance(member, property)
    }
    classified = set(_FORBIDDEN_DERIVED_KEYS) | set(_DERIVED_KEYS_WITH_DECLARED_TWINS)
    assert derived == classified, (
        f"unclassified derived properties: {sorted(derived - classified)}; "
        f"names classified but no longer properties: {sorted(classified - derived)}"
    )
    # lexicon_provenance is a declared manifest key, not a derived property.
    assert "lexicon_provenance" not in derived
    assert "lexicon_provenance" not in _FORBIDDEN_DERIVED_KEYS


def test_g27c_the_forbidden_set_catches_a_declared_display_label(tmp_path: Path) -> None:
    """Prove G27 can fail, on the key this exchange added.

    ``display_label`` is composed at ``variant_store.py:108-112`` from ``language`` and
    ``variant_name`` and has no declared twin, so a manifest declaring it reads as
    authoritative to a reviewer while the loader ignores it completely. Against the
    pre-change forbidden set this assertion failed — ``declared`` was ``[]`` — which is the
    whole reason the key is now listed.
    """
    payload = _synthetic("g27c", display_label="Synthetic – NOT the real label")
    path = _write_manifest(tmp_path, "g27c", payload)

    data = json.loads(path.read_text(encoding="utf-8"))
    declared = sorted(key for key in _FORBIDDEN_DERIVED_KEYS if key in data)
    assert declared == ["display_label"], (
        "the forbidden-derived-key set is blind to a declared display_label; a manifest "
        "could carry a label that the loader silently ignores"
    )

    # And the reason it must be forbidden: the declared value really is discarded.
    variant = _load_variant_from_path(path)
    assert variant.display_label == "Synthetic"
    assert variant.display_label != payload["display_label"]


# --- Negative tests: a malformed manifest must fail with its exact code -----------------


def test_g15_duplicate_alphabet_order_token_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VariantManifestError) as caught:
        _load_synthetic(tmp_path, "g15", alphabet_order=["A", "A"])
    assert caught.value.code == "duplicate_alphabet"


def test_g16_blank_in_alphabet_order_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VariantManifestError) as caught:
        _load_synthetic(tmp_path, "g16", alphabet_order=["A", "?"])
    assert caught.value.code == "blank_in_alphabet"


def test_g17_absent_alphabet_order_key_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VariantManifestError) as caught:
        _load_synthetic(tmp_path, "g17", drop=("alphabet_order",))
    assert caught.value.code == "missing_alphabet_order"


def test_g18_tile_token_outside_alphabet_order_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VariantManifestError) as caught:
        _load_synthetic(
            tmp_path,
            "g18",
            alphabet_order=["A"],
            letters=[_BLANK_ENTRY, _A_ENTRY, {"letter": "B", "count": 1, "points": 1}],
        )
    assert caught.value.code == "tile_not_in_alphabet"


def test_g19_decomposed_tile_token_is_rejected(tmp_path: Path) -> None:
    decomposed = "A\u0301"
    assert unicodedata.normalize("NFC", decomposed) != decomposed
    with pytest.raises(VariantManifestError) as caught:
        _load_synthetic(
            tmp_path,
            "g19",
            letters=[_BLANK_ENTRY, _A_ENTRY, {"letter": decomposed, "count": 1, "points": 1}],
        )
    assert caught.value.code == "non_nfc"


def test_g20_overlong_tile_token_is_rejected(tmp_path: Path) -> None:
    overlong = "A" * (MAX_TILE_TOKEN_CODEPOINTS + 1)
    with pytest.raises(VariantManifestError) as caught:
        _load_synthetic(
            tmp_path,
            "g20",
            letters=[_BLANK_ENTRY, _A_ENTRY, {"letter": overlong, "count": 1, "points": 1}],
        )
    assert caught.value.code == "too_long"


def test_g21_reserved_blank_alias_tile_token_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VariantManifestError) as caught:
        _load_synthetic(
            tmp_path,
            "g21",
            letters=[_BLANK_ENTRY, _A_ENTRY, {"letter": "JOKER", "count": 1, "points": 1}],
        )
    assert caught.value.code == "blank_alias"


def test_g22_duplicate_tile_token_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VariantManifestError) as caught:
        _load_synthetic(
            tmp_path,
            "g22",
            letters=[_BLANK_ENTRY, _A_ENTRY, {"letter": "A", "count": 1, "points": 1}],
        )
    assert caught.value.code == "duplicate_token"


def test_g23_whitespace_in_a_tile_token_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(VariantManifestError) as caught:
        _load_synthetic(
            tmp_path,
            "g23",
            letters=[_BLANK_ENTRY, _A_ENTRY, {"letter": "A B", "count": 1, "points": 1}],
        )
    assert caught.value.code == "whitespace"


def test_g24_dictionary_file_guard_keeps_two_exception_classes_apart() -> None:
    # Shape and path-escape rejections are ValueError ...
    for bad in ("../collins2019.txt", "dicts/collins2019.txt", "no_ext"):
        with pytest.raises(ValueError):
            validate_dictionary_file(bad)
    # ... but a merely absent lexicon is FileNotFoundError, which is NOT a ValueError.
    # game/views.py:117-125 catches it separately and reports readiness "unavailable".
    with pytest.raises(FileNotFoundError) as caught:
        validate_dictionary_file("definitely_absent_lexicon.txt")
    assert not isinstance(caught.value, ValueError)
    assert not isinstance(caught.value, VariantManifestError)


def test_g25_manifest_without_tiles_raises_plain_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError) as caught:
        _load_synthetic(tmp_path, "g25", letters=[])
    assert type(caught.value) is ValueError
    assert not isinstance(caught.value, VariantManifestError)
    assert "contains no tiles" in str(caught.value)
