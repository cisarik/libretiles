"""Slovak SSS variant assets and hunspell-sk lexicon (Slice 0)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gamecore.assets import get_assets_path
from gamecore.variant_store import (
    _load_variant_from_path,
    load_variant,
    validate_dictionary_file,
)

_COLLINS_LINE_COUNT = 279497
_LEXICON_MIN = 80_000
_LEXICON_MAX = 5_000_000


def test_slovak_bag_is_official_sss_100() -> None:
    v = load_variant("slovak")
    assert v.language == "Slovak"
    assert v.slug == "slovak"
    assert v.dictionary_file == "slovak.txt"
    assert v.total_tiles == 100
    assert len(v.playable_letters) == 41
    assert "?" in v.distribution
    assert v.distribution["?"] == 2
    assert v.tile_points["Á"] == 4
    assert v.tile_points["X"] == 10
    assert "Q" not in v.tile_points
    assert v.dictionary_path.is_file()


def test_english_dictionary_file_is_collins() -> None:
    v = load_variant("english")
    assert v.total_tiles == 100
    assert v.tile_points["Q"] == 10
    assert v.distribution["E"] == 12
    assert v.dictionary_file == "collins2019.txt"
    assert v.dictionary_path.name == "collins2019.txt"


def test_slovak_lexicon_meets_floor() -> None:
    path = get_assets_path() / "dicts" / "slovak.txt"
    words: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.startswith("#"):
                continue
            word = line.strip()
            if word:
                words.add(word)
    assert _LEXICON_MIN <= len(words) <= _LEXICON_MAX
    assert "auto" in words
    assert "škola" in words
    assert "not-a-word!" not in words
    assert all(item.isalpha() and len(item) >= 2 for item in words)


def test_collins_line_count_unchanged() -> None:
    path = get_assets_path() / "dicts" / "collins2019.txt"
    # Collins is CRLF and has no trailing newline; wc -l counts ``\n`` bytes.
    assert path.read_bytes().count(b"\n") == _COLLINS_LINE_COUNT


def test_slovak_has_no_ch_tile() -> None:
    v = load_variant("slovak")
    assert "CH" not in v.distribution
    assert "Ch" not in v.distribution
    assert "ch" not in v.distribution
    letters = {item.upper() for item in v.distribution}
    assert "CH" not in letters


def test_dictionary_file_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="basename"):
        validate_dictionary_file("../collins2019.txt")
    with pytest.raises(ValueError, match="basename"):
        validate_dictionary_file("foo/bar.txt")
    with pytest.raises(ValueError, match="basename"):
        validate_dictionary_file("..\\win.txt")
    payload = {
        "language": "Test",
        "slug": "escape",
        "dictionary_file": "../collins2019.txt",
        "letters": [{"letter": "A", "count": 1, "points": 1}],
    }
    path = tmp_path / "escape.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="basename"):
        _load_variant_from_path(path)
