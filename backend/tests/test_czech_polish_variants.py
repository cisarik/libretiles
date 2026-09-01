"""Czech and Polish playable variants, listing endpoint, and lexicon checks."""

from __future__ import annotations

import json
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
    assert [row["slug"] for row in body] == ["english", "czech", "polish", "slovak"]
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
