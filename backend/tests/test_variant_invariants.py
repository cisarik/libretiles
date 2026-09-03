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
cannot load (``gamecore/variant_store.py:433-440``), so without a count comparison a
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
}

_BLANK_ENTRY: dict[str, Any] = {"letter": "?", "count": 2, "points": 0}
_A_ENTRY: dict[str, Any] = {"letter": "A", "count": 98, "points": 1}


def _variants_dir() -> Path:
    """Derive the manifest directory the way the loader does, never hardcoded."""
    return get_assets_path() / "variants"


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
    at ``variant_store.py:333``, BEFORE ``alphabet_order`` is parsed at ``:343``, so a
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
    # Pins the CURRENT identity behaviour of variant_store.py:108-114 so that a future
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
        datetime.fromisoformat(variant.fetched_at)
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
