"""Lexicon health: the cheap per-request tier, the expensive audit tier, and the command.

Every corrupt lexicon in this module is SYNTHETIC and lives under ``tmp_path``. No shipped
asset is ever written to. ``N8`` reads the four shipped lexicons read-only and is the most
important case here: it is the evidence that the new validation did not make a shipped
language ``unavailable``.

Four measured properties of the shipped assets are pinned as tests rather than left as
prose, because each one would break a real language if a rule tripped on it:
``N9`` (``collins2019.txt`` opens with a prose line that is not a ``#`` comment, and uses
CRLF), ``N10`` (English is UPPERCASE while the expanded lexicons are lowercase), ``N11``
(``czech.txt`` deliberately carries non-Czech code points such as the Greek mu in
``μa μg μm μv``) and ``N12`` (the cheap tier is cached, so a rebuilt file at the same path
must invalidate).
"""

from __future__ import annotations

import io
import json
from itertools import islice, product
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from gamecore.fastdict import load_prefix_index
from gamecore.lexicon_health import (
    DEFAULT_MIN_SURVIVING_WORDS,
    MAX_PREFIX_BYTES,
    audit_lexicon,
    check_lexicon,
    surviving_word,
)
from gamecore.variant_store import list_installed_variants

_INSTALLED = list_installed_variants()

# Collins' real first two lines: prose, then an empty line. Neither starts with '#'.
_COLLINS_HEADER = "Collins Scrabble Words (2019). 279,496 words. Words only."
_VALID_TEXT = "alpha\nbeta\ngamma\ndelta\n"


def _shipped_targets() -> list[tuple[str, Path]]:
    targets: list[tuple[str, Path]] = []
    for variant in _INSTALLED:
        targets.append((f"{variant.slug}-dictionary", variant.dictionary_path))
        if variant.two_tile_words_path is not None:
            targets.append((f"{variant.slug}-two-tile", variant.two_tile_words_path))
    return targets


_TARGETS = _shipped_targets()
_TARGET_PATHS = [path for _, path in _TARGETS]
_TARGET_IDS = [name for name, _ in _TARGETS]


def _write_bytes(tmp_path: Path, name: str, payload: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(payload)
    return path


def _write_text(tmp_path: Path, name: str, payload: str) -> Path:
    return _write_bytes(tmp_path, name, payload.encode("utf-8"))


# --- The cheap tier: N1-N12 -------------------------------------------------------------


def test_n1_missing_file_is_not_ok(tmp_path: Path) -> None:
    health = check_lexicon(tmp_path / "absent.txt")
    assert health.ok is False
    assert health.reason == "missing"


def test_n2_zero_byte_file_is_not_ok(tmp_path: Path) -> None:
    health = check_lexicon(_write_bytes(tmp_path, "empty.txt", b""))
    assert health.ok is False
    assert health.reason == "empty"


def test_n3_bom_prefixed_file_is_not_ok(tmp_path: Path) -> None:
    """The words are fine; the BOM is the defect, and it is the first byte the loader sees.

    ``fastdict`` opens with plain ``utf-8``, not ``utf-8-sig``, so a BOM would be glued to
    the first word and that word would never match.
    """
    payload = b"\xef\xbb\xbf" + _VALID_TEXT.encode("utf-8")
    health = check_lexicon(_write_bytes(tmp_path, "bom.txt", payload))
    assert health.ok is False
    assert health.reason == "bom"


def test_n4_invalid_utf8_inside_the_prefix_is_not_ok(tmp_path: Path) -> None:
    payload = b"alpha\nbe\xffta\ngamma\n"
    health = check_lexicon(_write_bytes(tmp_path, "badbytes.txt", payload))
    assert health.ok is False
    assert health.reason == "invalid_utf8"


def test_n5_comment_only_file_is_not_ok(tmp_path: Path) -> None:
    text = "# a header\n# https://example.invalid/source\n# third header line\n"
    health = check_lexicon(_write_text(tmp_path, "comments.txt", text))
    assert health.ok is False
    assert health.reason == "no_surviving_word"


def test_n6_file_whose_lines_all_fail_the_filter_is_not_ok(tmp_path: Path) -> None:
    text = "a\nb\n1\n42\n!!\n?\n-\n\n"
    health = check_lexicon(_write_text(tmp_path, "junk.txt", text))
    assert health.ok is False
    assert health.reason == "no_surviving_word"


def test_n7_valid_lexicon_is_ok(tmp_path: Path) -> None:
    path = _write_text(tmp_path, "valid.txt", _VALID_TEXT)
    health = check_lexicon(path)
    assert health.ok is True
    assert health.reason == "ok"
    assert health.surviving_words_in_prefix == 4
    assert health.bytes_read == path.stat().st_size


@pytest.mark.parametrize("path", _TARGET_PATHS, ids=_TARGET_IDS)
def test_n8_every_shipped_lexicon_is_ok_and_is_read_bounded(path: Path) -> None:
    """⛔ The most important case in this file: no shipped language may become unavailable.

    It also pins the bound that makes the cheap tier safe on a request path: the largest
    shipped lexicon is over 54 MB and the check must never read more than
    ``MAX_PREFIX_BYTES`` of it.
    """
    size = path.stat().st_size
    health = check_lexicon(path)
    assert health.ok is True, f"{path.name}: {health.reason}"
    assert health.reason == "ok"
    assert health.surviving_words_in_prefix >= 1
    assert health.bytes_read <= MAX_PREFIX_BYTES
    assert health.bytes_read == min(size, MAX_PREFIX_BYTES)


def test_n9_prose_first_line_then_words_is_ok(tmp_path: Path) -> None:
    """Trap T1 as a test. ``collins2019.txt`` is exactly this shape, CRLF included.

    The first line is prose and does NOT start with '#', so a rule phrased as "every
    non-comment line must be a word" would reject the English lexicon. The only correct
    phrasing is "at least one line SURVIVING the loader's filter".
    """
    text = f"{_COLLINS_HEADER}\r\n\r\nAA\r\nAAH\r\nAAHED\r\n"
    health = check_lexicon(_write_text(tmp_path, "collins_shaped.txt", text))
    assert health.ok is True
    assert health.reason == "ok"
    assert health.surviving_words_in_prefix == 3


def test_n10_uppercase_lexicon_is_ok(tmp_path: Path) -> None:
    """Trap T2 as a test: casing is not uniform across the shipped set."""
    health = check_lexicon(_write_text(tmp_path, "upper.txt", "ALPHA\nBETA\nGAMMA\n"))
    assert health.ok is True
    assert health.surviving_words_in_prefix == 3


def test_n11_non_alphabet_code_points_are_ok(tmp_path: Path) -> None:
    """Trap T4 as a test: ``czech.txt`` ships the Greek mu in ``μa μg μm μv``.

    Lexicon characters are never validated against the variant alphabet — that invariant
    is about TILES — so these lines must survive exactly like any other word.
    """
    health = check_lexicon(_write_text(tmp_path, "mu.txt", "μa\nμg\nμm\nμv\ndomu\n"))
    assert health.ok is True
    assert health.surviving_words_in_prefix == 5


def test_n12_cache_invalidates_when_the_file_changes_at_the_same_path(tmp_path: Path) -> None:
    """The cache key is (resolved path, st_size, st_mtime_ns), never the path alone.

    The rewrite below deliberately changes the SIZE as well as the content: mtime_ns has
    filesystem-dependent granularity, so on a fast filesystem two writes inside the same
    tick could share an mtime. Keying on size as well means this test cannot pass by
    accident of clock resolution.
    """
    path = _write_text(tmp_path, "mutating.txt", _VALID_TEXT)
    first = check_lexicon(path)
    assert first.ok is True

    path.write_text("# every word replaced by a single long comment line\n", encoding="utf-8")
    assert path.stat().st_size != len(_VALID_TEXT.encode("utf-8"))
    second = check_lexicon(path)
    assert second.ok is False
    assert second.reason == "no_surviving_word"

    path.write_text(_VALID_TEXT + "epsilon\n", encoding="utf-8")
    third = check_lexicon(path)
    assert third.ok is True
    assert third.surviving_words_in_prefix == 5


# --- The filter itself is the loader's filter, not a second one -------------------------


def test_the_surviving_filter_matches_the_loader_plus_the_two_codepoint_floor(
    tmp_path: Path,
) -> None:
    """One filter, two call sites.

    ``gamecore/fastdict.py:_read_words`` decides what enters the index; ``str.isalpha``
    plus the two-code-point floor at ``game/services.py:216`` decides what the product
    will ever accept as a word. The cheap tier must be the conjunction, and the ONLY
    difference from the raw loader must be that single-code-point line.
    """
    lines = ["# comment", "", "AB", "a", "ab", "1234", "hi!", "gamma", "μg", "  spaced  "]
    path = _write_text(tmp_path, "filter.txt", "\n".join(lines) + "\n")
    index = load_prefix_index(path)
    mine = {
        token for line in lines if (token := surviving_word(line)) is not None
    }
    assert mine == {"ab", "gamma", "μg", "spaced"}
    assert mine <= index.membership
    assert index.membership - mine == {"a"}


# --- The expensive tier -----------------------------------------------------------------


def test_audit_accepts_a_valid_lexicon(tmp_path: Path) -> None:
    audit = audit_lexicon(_write_text(tmp_path, "ok.txt", _VALID_TEXT), min_words=4)
    assert audit.ok is True
    assert audit.reason == "ok"
    assert audit.surviving_words == 4
    assert audit.duplicate_words == 0
    assert audit.non_nfc_lines == 0


def test_audit_rejects_a_duplicate_surviving_token(tmp_path: Path) -> None:
    """The duplicate policy, stated and asserted: a surviving token appears exactly once.

    The index collapses duplicates into a ``frozenset`` (``gamecore/fastdict.py:37``), so a
    duplicate is invisible waste that only a whole-file audit can see. Measured at this
    baseline: all THIRTEEN shipped assets — twelve dictionaries plus the Slovak two-tile list —
    carry ZERO duplicates, so the policy costs the shipped assets nothing.
    """
    audit = audit_lexicon(
        _write_text(tmp_path, "dup.txt", "alpha\nbeta\nALPHA\ngamma\n"), min_words=1
    )
    assert audit.ok is False
    assert audit.reason == "duplicate_word"
    assert audit.duplicate_words == 1


def test_audit_rejects_a_non_nfc_surviving_line(tmp_path: Path) -> None:
    decomposed = "a\u0301lfa"
    audit = audit_lexicon(
        _write_text(tmp_path, "nfd.txt", f"alpha\n{decomposed}\n"), min_words=1
    )
    assert audit.ok is False
    assert audit.reason == "non_nfc_line"
    assert audit.non_nfc_lines == 1


def test_audit_rejects_a_lexicon_below_the_word_floor(tmp_path: Path) -> None:
    audit = audit_lexicon(_write_text(tmp_path, "thin.txt", "alpha\nbeta\n"))
    assert audit.ok is False
    assert audit.reason == "too_few_words"
    assert audit.surviving_words == 2
    assert DEFAULT_MIN_SURVIVING_WORDS > 2


def test_audit_inherits_the_cheap_verdict(tmp_path: Path) -> None:
    audit = audit_lexicon(tmp_path / "absent.txt")
    assert audit.ok is False
    assert audit.reason == "missing"


def test_audit_runs_the_membership_probe(tmp_path: Path) -> None:
    path = _write_text(tmp_path, "probe.txt", "domu\nknihy\nalpha\n")
    present = audit_lexicon(
        path, min_words=1, expect_present=frozenset({"domu", "KNIHY"})
    )
    assert present.ok is True
    assert present.missing_probes == ()

    absent = audit_lexicon(path, min_words=1, expect_present=frozenset({"qxqxqxqxq"}))
    assert absent.ok is False
    assert absent.reason == "probe_absent"
    assert absent.missing_probes == ("qxqxqxqxq",)

    forbidden = audit_lexicon(path, min_words=1, expect_absent=frozenset({"alpha"}))
    assert forbidden.ok is False
    assert forbidden.reason == "probe_present"
    assert forbidden.unexpected_probes == ("alpha",)


# --- The management command -------------------------------------------------------------


def test_validate_lexicons_passes_on_the_shipped_variants() -> None:
    """Read-only audit over every installed variant; exit 0 means every asset passed.

    The stdout assertion is where the duplicate policy becomes visible to an operator.
    """
    out = io.StringIO()
    call_command("validate_lexicons", stdout=out)
    printed = out.getvalue()
    lines = [line for line in printed.splitlines() if line.strip()]
    assert lines, printed
    for variant in _INSTALLED:
        assert variant.slug in printed
    for line in lines:
        if line.startswith("validate_lexicons:"):
            continue
        assert " ok " in line, line
        assert "duplicates=0" in line, line
        assert "non_nfc=0" in line, line
    assert "FAILED" not in printed


def _synthetic_asset_root(tmp_path: Path, *, lexicon: str) -> Path:
    root = tmp_path / "assets"
    (root / "dicts").mkdir(parents=True)
    (root / "variants").mkdir(parents=True)
    (root / "dicts" / "synthetic_lexicon.txt").write_text(lexicon, encoding="utf-8")
    payload: dict[str, Any] = {
        "language": "Synthetic",
        "slug": "synthetic",
        "dictionary_file": "synthetic_lexicon.txt",
        "alphabet_order": ["A"],
        "letters": [
            {"letter": "?", "count": 2, "points": 0},
            {"letter": "A", "count": 98, "points": 1},
        ],
    }
    (root / "variants" / "synthetic.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )
    return root


def test_validate_lexicons_fails_on_a_corrupt_lexicon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non-zero exit is the whole point of the command; CommandError is Django's route.

    The synthetic assets root repoints ``variant_store.get_assets_path`` only, which is
    what ``_variants_dir``, ``validate_dictionary_file`` and ``dictionary_path`` all build
    on, so no shipped asset is touched.
    """
    root = _synthetic_asset_root(tmp_path, lexicon="# header only, no words\n")
    monkeypatch.setattr("gamecore.variant_store.get_assets_path", lambda: root)
    out = io.StringIO()
    with pytest.raises(CommandError) as caught:
        call_command("validate_lexicons", stdout=out)
    assert "no_surviving_word" in str(caught.value)
    assert "FAILED" in out.getvalue()


def test_validate_lexicons_passes_on_a_healthy_synthetic_variant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Alphabetic only: a token containing a digit does not survive ``str.isalpha``.
    words = "\n".join(
        "".join(triple)
        for triple in islice(product("abcde", repeat=3), DEFAULT_MIN_SURVIVING_WORDS)
    )
    root = _synthetic_asset_root(tmp_path, lexicon=f"# header\n{words}\n")
    monkeypatch.setattr("gamecore.variant_store.get_assets_path", lambda: root)
    out = io.StringIO()
    call_command("validate_lexicons", stdout=out)
    printed = out.getvalue()
    assert "synthetic" in printed
    assert "FAILED" not in printed
