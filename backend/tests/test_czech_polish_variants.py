"""Czech and Polish playable variants, listing endpoint, and lexicon checks."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from gamecore.fastdict import load_prefix_index
from gamecore.variant_store import load_two_tile_words, load_variant
from game.services import _word_passes_dictionary

_SUMMARY_KEYS = frozenset({"slug", "display_name", "language_code", "readiness"})
_CZECH_TILELESS = frozenset({"CH", "Q", "W"})
_POLISH_TILELESS: frozenset[str] = frozenset()


def _arithmetic(variant: Any) -> tuple[int, int, int, int]:
    blank_count = variant.distribution.get("?", 0)
    nominal = sum(item.count * item.points for item in variant.letters)
    return variant.total_tiles, len(variant.letters), blank_count, nominal


def test_t1_czech_and_polish_manifests_load() -> None:
    czech = load_variant("czech")
    polish = load_variant("polish")
    assert czech.slug == "czech"
    assert polish.slug == "polish"
    assert czech.two_tile_words_file is None
    assert polish.two_tile_words_file is None
    assert load_two_tile_words(czech) is None
    assert load_two_tile_words(polish) is None


def test_t2_czech_and_polish_tile_arithmetic() -> None:
    assert _arithmetic(load_variant("czech")) == (100, 40, 2, 205)
    assert _arithmetic(load_variant("polish")) == (100, 33, 2, 190)


def test_t3_subset_invariant_both_directions() -> None:
    czech = load_variant("czech")
    polish = load_variant("polish")
    czech_tiles = {item.letter for item in czech.letters if item.letter != "?"}
    polish_tiles = {item.letter for item in polish.letters if item.letter != "?"}
    assert czech_tiles <= set(czech.alphabet_order)
    assert polish_tiles <= set(polish.alphabet_order)
    assert set(czech.alphabet_order) - czech_tiles == _CZECH_TILELESS
    assert set(polish.alphabet_order) - polish_tiles == _POLISH_TILELESS
    assert len(czech_tiles) == 39
    assert len(polish_tiles) == 32
    assert all(token in czech.alphabet_order for token in czech_tiles)
    assert all(token in polish.alphabet_order for token in polish_tiles)
    assert len(czech_tiles) == len(set(czech_tiles))
    assert len(polish_tiles) == len(set(polish_tiles))


def test_t4_playable_letters_follow_alphabet_order() -> None:
    czech = load_variant("czech")
    polish = load_variant("polish")
    assert czech.playable_letters[0] == "A"
    assert czech.playable_letters[1] == "Á"
    assert polish.playable_letters[0] == "A"
    assert polish.playable_letters[1] == "Ą"
    czech_index = {token: i for i, token in enumerate(czech.alphabet_order)}
    polish_index = {token: i for i, token in enumerate(polish.alphabet_order)}
    assert czech.playable_letters == tuple(
        sorted(
            (item.letter for item in czech.letters if item.letter != "?"),
            key=lambda token: czech_index[token],
        )
    )
    assert polish.playable_letters == tuple(
        sorted(
            (item.letter for item in polish.letters if item.letter != "?"),
            key=lambda token: polish_index[token],
        )
    )


def test_t5_no_multi_code_point_tokens() -> None:
    for slug in ("czech", "polish"):
        variant = load_variant(slug)
        tiles = [item.letter for item in variant.letters if item.letter != "?"]
        assert all(len(token) == 1 for token in tiles)


@pytest.fixture(scope="module")
def czech_contains():
    return load_prefix_index(load_variant("czech").dictionary_path).contains


@pytest.fixture(scope="module")
def polish_contains():
    return load_prefix_index(load_variant("polish").dictionary_path).contains


def test_t6_inflected_lexicon_membership(czech_contains, polish_contains) -> None:
    assert _word_passes_dictionary(czech_contains, "domu") is True
    assert _word_passes_dictionary(czech_contains, "knihy") is True
    assert _word_passes_dictionary(czech_contains, "qxqxqxqxq") is False
    assert _word_passes_dictionary(polish_contains, "domach") is True
    assert _word_passes_dictionary(polish_contains, "książki") is True
    assert _word_passes_dictionary(polish_contains, "qxqxqxqxq") is False


def _auth_client() -> APIClient:
    user = User.objects.create_user(username="variant-reader", password="pass1234")
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
def test_t7_variant_list_exact_key_set() -> None:
    resp = _auth_client().get("/api/game/variants/")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    # The catalog order is DERIVED at game/views.py: english pinned first because it is the
    # default slug, then every other variant by casefolded display_name with the slug breaking
    # ties. So a new language inserts itself alphabetically rather than appending, and
    # "Afrikaans" sorts before "Czech". ⚠ This expectation is a hardcoded inventory on purpose
    # — it is what proves a variant did not appear or vanish by accident — so it must be
    # updated deliberately with each new language, and the four original slugs must all still
    # be present and playable below.
    assert [row["slug"] for row in body] == [
        "english",
        "afrikaans",
        "czech",
        "danish",
        "dutch",
        "german",
        "italian",
        "polish",
        "portuguese",
        "slovak",
    ]
    for row in body:
        assert set(row.keys()) == _SUMMARY_KEYS
        assert row["readiness"] == "playable"
        dumped = json.dumps(row)
        assert "dicts" not in dumped
        assert ".txt" not in dumped
        assert "assets" not in dumped
        assert "/" not in "".join(str(value) for value in row.values() if value is not None)
    by_slug = {row["slug"]: row for row in body}
    assert by_slug["english"]["display_name"] == "English"
    assert by_slug["english"]["language_code"] is None
    assert by_slug["czech"] == {
        "slug": "czech",
        "display_name": "Czech",
        "language_code": "cs",
        "readiness": "playable",
    }
    assert by_slug["polish"] == {
        "slug": "polish",
        "display_name": "Polish",
        "language_code": "pl",
        "readiness": "playable",
    }
    assert by_slug["slovak"]["display_name"] == "Slovak"
    assert by_slug["slovak"]["language_code"] == "sk"


@pytest.mark.django_db
def test_t8_variant_list_rejects_unauthenticated() -> None:
    resp = APIClient().get("/api/game/variants/")
    assert resp.status_code == 401


def _write_manifest(directory: Path, slug: str, payload: dict[str, Any]) -> None:
    (directory / f"{slug}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


_MINIMAL_PLAYABLE = {
    "language": "Ghost",
    "slug": "ghost",
    "language_code": "xx",
    "dictionary_file": "ghost_missing.txt",
    "alphabet_order": ["A"],
    "letters": [
        {"letter": "?", "count": 2, "points": 0},
        {"letter": "A", "count": 98, "points": 1},
    ],
}


@pytest.mark.django_db
def test_t9_missing_dictionary_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(tmp_path, "ghost", _MINIMAL_PLAYABLE)
    monkeypatch.setattr("game.views._variant_json_dir", lambda: tmp_path)
    resp = _auth_client().get("/api/game/variants/")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [
        {
            "slug": "ghost",
            "display_name": "Ghost",
            "language_code": "xx",
            "readiness": "unavailable",
        }
    ]
    dumped = json.dumps(body)
    assert "ghost_missing" not in dumped
    assert ".txt" not in dumped
    assert str(tmp_path) not in dumped
    assert "FileNotFound" not in dumped


@pytest.mark.django_db
def test_t10_malformed_manifest_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    _write_manifest(
        tmp_path,
        "bad",
        {
            "language": "Broken",
            "slug": "bad",
            "dictionary_file": "collins2019.txt",
            "alphabet_order": ["A", "A"],
            "letters": [
                {"letter": "?", "count": 2, "points": 0},
                {"letter": "A", "count": 98, "points": 1},
            ],
        },
    )
    _write_manifest(tmp_path, "ghost", _MINIMAL_PLAYABLE)
    monkeypatch.setattr("game.views._variant_json_dir", lambda: tmp_path)
    resp = _auth_client().get("/api/game/variants/")
    assert resp.status_code == 200
    body = resp.json()
    slugs = [row["slug"] for row in body]
    assert "broken" not in slugs
    assert "bad" not in slugs
    assert slugs == ["ghost"]
    assert body[0]["readiness"] == "unavailable"
    dumped = json.dumps(body)
    assert "unavailable" in dumped
    assert "broken" not in dumped
    assert "malformed" not in dumped.lower()


@pytest.mark.django_db
def test_t11_create_accepts_czech_and_rejects_unknown() -> None:
    user = User.objects.create_user(username="variant-writer", password="pass1234")
    client = APIClient()
    client.force_authenticate(user=user)
    czech = client.post(
        "/api/game/create/",
        {"game_mode": "vs_ai", "variant_slug": "czech"},
        format="json",
    )
    assert czech.status_code == 201
    game_id = czech.json()["game_id"]
    state = client.get(f"/api/game/{game_id}/").json()
    assert state["variant_slug"] == "czech"
    assert state["lexicon_id"] == "czech"
    polish = client.post(
        "/api/game/create/",
        {"game_mode": "vs_ai", "variant_slug": "polish"},
        format="json",
    )
    assert polish.status_code == 201
    unknown = client.post(
        "/api/game/create/",
        {"game_mode": "vs_ai", "variant_slug": "klingon"},
        format="json",
    )
    assert unknown.status_code == 400
    assert "unknown_variant" in str(unknown.json())


@pytest.mark.django_db
def test_t12_stem_slug_divergent_manifest_is_omitted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A manifest that can never be loaded is never advertised.

    ``de.json`` declaring ``"slug": "german"`` names a lexicon that really exists, so its
    only defect is the stem/slug divergence the loader rejects with code
    ``slug_stem_mismatch``. ``VariantManifestError`` is a ``ValueError``, not a
    ``FileNotFoundError``, so it lands in the ``except Exception`` branch at
    ``game/views.py:126-128`` and the row is OMITTED rather than reported
    ``unavailable``: an ``unavailable`` row would still leak the existence and the display
    name of a variant no code path can ever load, because ``list_installed_variants``
    advertises the declared slug while ``load_variant`` resolves the filename.
    """
    _write_manifest(
        tmp_path,
        "de",
        {
            "language": "German",
            "slug": "german",
            "language_code": "de",
            "dictionary_file": "collins2019.txt",
            "alphabet_order": ["A"],
            "letters": [
                {"letter": "?", "count": 2, "points": 0},
                {"letter": "A", "count": 98, "points": 1},
            ],
        },
    )
    _write_manifest(
        tmp_path,
        "valid",
        {
            "language": "Valid",
            "slug": "valid",
            "language_code": "xx",
            "dictionary_file": "collins2019.txt",
            "alphabet_order": ["A"],
            "letters": [
                {"letter": "?", "count": 2, "points": 0},
                {"letter": "A", "count": 98, "points": 1},
            ],
        },
    )
    monkeypatch.setattr("game.views._variant_json_dir", lambda: tmp_path)

    resp = _auth_client().get("/api/game/variants/")
    assert resp.status_code == 200
    body = resp.json()
    slugs = [row["slug"] for row in body]
    # Neither the declared slug nor the filename stem may be advertised.
    assert "german" not in slugs
    assert "de" not in slugs
    assert slugs == ["valid"]
    assert body[0] == {
        "slug": "valid",
        "display_name": "Valid",
        "language_code": "xx",
        "readiness": "playable",
    }
    for row in body:
        assert set(row.keys()) == _SUMMARY_KEYS
    # A new failure mode must not become a new leak: game/views.py:100-101 promises
    # "Never include paths, filenames, or errors."
    dumped = json.dumps(body)
    assert "german" not in dumped.lower()
    assert "de.json" not in dumped
    assert str(tmp_path) not in dumped
    assert ".txt" not in dumped
    assert "mismatch" not in dumped.lower()
    assert "slug_stem_mismatch" not in dumped
    assert "VariantManifestError" not in dumped


def _synthetic_asset_root(tmp_path: Path) -> Path:
    """A throwaway assets root with both subdirectories the loader resolves against.

    ``validate_dictionary_file`` and ``VariantDefinition.dictionary_path`` both build on
    ``variant_store.get_assets_path()``, so a synthetic lexicon can only be reached by
    repointing that one function. A shipped asset is never written to.
    """
    root = tmp_path / "assets"
    (root / "dicts").mkdir(parents=True)
    (root / "variants").mkdir(parents=True)
    return root


def _corrupt_manifest(dictionary_file: str) -> dict[str, Any]:
    return {
        "language": "Corrupt",
        "slug": "corrupt",
        "language_code": "xx",
        "dictionary_file": dictionary_file,
        "alphabet_order": ["A"],
        "letters": [
            {"letter": "?", "count": 2, "points": 0},
            {"letter": "A", "count": 98, "points": 1},
        ],
    }


@pytest.mark.django_db
def test_t13_present_but_corrupt_lexicon_reads_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readiness is content-aware: a lexicon that exists but carries no word fails closed.

    Before this slice ``_variant_resources_ready`` asked only ``is_file()``, so this
    manifest reported ``playable`` while every word lookup against it would fail. The
    file below exists, is non-empty and is valid UTF-8; it simply yields no line that
    survives the loader's own filter (``gamecore/fastdict.py:_read_words`` plus the
    two-code-point floor at ``game/services.py:216``).
    """
    root = _synthetic_asset_root(tmp_path)
    (root / "dicts" / "corrupt_lexicon.txt").write_text(
        "# header only, no words at all\n# second header line\n", encoding="utf-8"
    )
    _write_manifest(root / "variants", "corrupt", _corrupt_manifest("corrupt_lexicon.txt"))
    monkeypatch.setattr("gamecore.variant_store.get_assets_path", lambda: root)
    monkeypatch.setattr("game.views._variant_json_dir", lambda: root / "variants")

    resp = _auth_client().get("/api/game/variants/")
    assert resp.status_code == 200
    body = resp.json()
    assert body == [
        {
            "slug": "corrupt",
            "display_name": "Corrupt",
            "language_code": "xx",
            "readiness": "unavailable",
        }
    ]
    for row in body:
        assert set(row.keys()) == _SUMMARY_KEYS
    dumped = json.dumps(body)
    assert "corrupt_lexicon" not in dumped
    assert ".txt" not in dumped
    assert str(tmp_path) not in dumped
    assert "no_surviving_word" not in dumped


@pytest.mark.django_db
def test_t14_omit_branch_reason_discriminates_the_failure_class(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """An operator must be able to tell the two omit causes apart, without a leak.

    The ``game`` logger sets ``propagate: False`` in ``config/settings.py``, so the
    handler is attached to it directly — the same idiom as
    ``tests/test_multiplayer_ws.py:232-241``.
    """
    (tmp_path / "broken.json").write_text("{not json", encoding="utf-8")
    _write_manifest(
        tmp_path,
        "De_Ch",
        {
            "language": "Divergent",
            "slug": "de-ch",
            "dictionary_file": "collins2019.txt",
            "alphabet_order": ["A"],
            "letters": [
                {"letter": "?", "count": 2, "points": 0},
                {"letter": "A", "count": 98, "points": 1},
            ],
        },
    )
    monkeypatch.setattr("game.views._variant_json_dir", lambda: tmp_path)

    game_log = logging.getLogger("game")
    with caplog.at_level(logging.ERROR, logger="game"):
        game_log.addHandler(caplog.handler)
        try:
            resp = _auth_client().get("/api/game/variants/")
        finally:
            game_log.removeHandler(caplog.handler)

    assert resp.status_code == 200
    assert resp.json() == []
    messages = [
        record.getMessage()
        for record in caplog.records
        if record.getMessage().startswith("variant_list_omitted")
    ]
    assert len(messages) == 2, messages
    for message in messages:
        assert "reason=" in message, message
    reasons = {message.split("reason=", 1)[1] for message in messages}
    # The whole point: two different causes must not read identically.
    assert len(reasons) == 2, reasons
    assert reasons == {"JSONDecodeError", "slug_stem_mismatch"}, reasons
    for message in messages:
        assert str(tmp_path) not in message
        assert "/" not in message
        assert ".json" not in message
        assert ".txt" not in message
        assert "De_Ch" not in message
        assert "broken" not in message

