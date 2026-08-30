"""Parameterized provider-free engine diagnostic (Slice E)."""

from __future__ import annotations

import inspect
import json
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from game import diagnostics as diagnostics_mod
from game.diagnostics import (
    ARTIFACT_ID,
    classify_complete_formed_words,
    load_named_scenario,
    load_variant_context,
    observe_source_revision,
    reserved_completion_sources,
    scenario_asset_path,
)
from game.services import _word_passes_dictionary
from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.board import Board
from gamecore.legality import REASON_INVALID_WORD, evaluate_scoring_move
from gamecore.types import Placement
from gamecore.variant_store import load_two_letter_allowlist, load_variant

_OSAMENIU = "OSAMENIU"
_OSAMENIU_SCORE = 74
_OSAMENIU_PLACEMENTS = (
    Placement(7, 7, "S"),
    Placement(8, 7, "A"),
    Placement(9, 7, "M"),
    Placement(10, 7, "E"),
    Placement(11, 7, "N"),
    Placement(12, 7, "I"),
    Placement(13, 7, "U"),
)
_LEGAL_SLOVAK_TWO_LETTER = (
    "ja",
    "ty",
    "my",
    "ex",
    "on",
    "si",
    "to",
    "um",
    "mi",
    "aj",
    "ak",
)
_SCHEMA_REQUIRED = {
    "artifact",
    "report_kind",
    "generated_at",
    "source_revision",
    "requested",
    "variant",
    "samples",
    "summary",
}


def _hook_board() -> Board:
    scenario = load_named_scenario("slovak-hooks-umenasi")
    board = Board(get_premiums_path())
    for row, col, letter in scenario.board_letters:
        board.cells[row][col].letter = letter
    return board


def _assert_engine_report_v1(payload: object) -> dict[str, Any]:
    assert isinstance(payload, dict)
    missing = _SCHEMA_REQUIRED - payload.keys()
    assert not missing
    assert payload["artifact"] == ARTIFACT_ID
    assert payload["report_kind"] == "engine"
    assert isinstance(payload["generated_at"], str)
    assert payload["generated_at"].endswith("Z")
    assert payload["source_revision"] == observe_source_revision()
    requested = payload["requested"]
    assert isinstance(requested, dict)
    assert "variant_slug" in requested
    assert "probe_count" in requested
    variant = payload["variant"]
    assert isinstance(variant, dict)
    assert {"slug", "lexicon_id", "two_letter_lexicon_size"} <= variant.keys()
    samples = payload["samples"]
    assert isinstance(samples, list)
    assert samples
    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["sample_count"] == len(samples)
    assert summary["pass_count"] + summary["fail_count"] == len(samples)
    for sample in samples:
        assert isinstance(sample, dict)
        assert sample["verdict"] in {"pass", "fail"}
        assert isinstance(sample["reason_code"], str)
        assert "search_status" in sample
        assert "complete" in sample
        assert "nodes" in sample
        assert "elapsed_ms" in sample
        policy = sample["two_letter_policy"]
        assert isinstance(policy, dict)
        assert "complete_formed_words" in policy
        assert "rejected" in policy
        assert sample.get("completion_source") in (None, *reserved_completion_sources())
        if "completion_source" in sample:
            assert sample["completion_source"] is None
    return payload


def test_engine_cli_writes_v1_json_for_named_fixture() -> None:
    stdout = StringIO()
    stderr = StringIO()
    call_command(
        "diagnose_ai_engine",
        variant_slug="english",
        fixture_id="english-empty-autolin",
        probe_count=1,
        stdout=stdout,
        stderr=stderr,
    )
    payload = _assert_engine_report_v1(json.loads(stdout.getvalue()))
    assert payload["requested"] == {
        "variant_slug": "english",
        "probe_count": 1,
        "fixture_id": "english-empty-autolin",
    }
    assert payload["variant"]["slug"] == "english"
    assert payload["variant"]["two_letter_lexicon_size"] is None
    sample = payload["samples"][0]
    assert sample["verdict"] == "pass"
    assert "status=" in stderr.getvalue()
    assert "elapsed_ms=" in stderr.getvalue()
    schema_path = get_assets_path() / "diagnostics" / "ai_play_report_v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["artifact"]["const"] == ARTIFACT_ID
    assert set(schema["required"]) == _SCHEMA_REQUIRED


def test_seeded_engine_probe_is_repeatable() -> None:
    def run_once() -> dict[str, Any]:
        stdout = StringIO()
        call_command(
            "diagnose_ai_engine",
            variant_slug="slovak",
            seed=20260830,
            probe_count=2,
            stdout=stdout,
            stderr=StringIO(),
        )
        payload = _assert_engine_report_v1(json.loads(stdout.getvalue()))
        return payload

    first = run_once()
    second = run_once()
    assert first["requested"]["seed"] == 20260830
    assert "fixture_id" not in first["requested"]
    racks = [sample["rack"] for sample in first["samples"]]
    assert racks[0] == racks[1]
    assert racks[0] == second["samples"][0]["rack"]
    assert racks[0]


def test_formed_word_policy_checks_complete_words_not_substrings() -> None:
    context = load_variant_context("slovak")
    source = inspect.getsource(classify_complete_formed_words)
    assert ".find(" not in source
    assert "re.search" not in source
    assert "re.findall" not in source
    assert "isascii" not in source
    module_text = Path(diagnostics_mod.__file__).read_text(encoding="utf-8")
    assert "isascii" not in module_text
    longer = classify_complete_formed_words(
        [_OSAMENIU, "LATINOU"],
        contains=context.index.contains,
        two_letter_allowlist=context.allowlist,
    )
    assert longer == ()
    mixed = classify_complete_formed_words(
        [_OSAMENIU, "am", "LATINOU", "ou"],
        contains=context.index.contains,
        two_letter_allowlist=context.allowlist,
    )
    rejected = {word.casefold() for word in mixed}
    assert rejected == {"am", "ou"}
    assert _OSAMENIU.casefold() not in rejected
    assert "latinou" not in rejected


def test_slovak_hook_fixture_keeps_osameniu_legal() -> None:
    context = load_variant_context("slovak")
    assert context.is_word(_OSAMENIU) is True
    scenario = load_named_scenario("slovak-hooks-umenasi")
    move = evaluate_scoring_move(
        _hook_board(),
        scenario.rack,
        _OSAMENIU_PLACEMENTS,
        context.is_word,
        letters=context.letters,
        variant="slovak",
    )
    assert move.ok is True
    assert move.total_score == _OSAMENIU_SCORE
    formed = {word.casefold() for word in move.words}
    assert _OSAMENIU.casefold() in formed
    rejected = classify_complete_formed_words(
        move.words,
        contains=context.index.contains,
        two_letter_allowlist=context.allowlist,
    )
    assert rejected == ()


def test_slovak_b2_accepts_named_legal_complete_words() -> None:
    context = load_variant_context("slovak")
    assert context.allowlist is not None
    for word in _LEGAL_SLOVAK_TWO_LETTER:
        assert context.is_word(word) is True
        rejected = classify_complete_formed_words(
            [word],
            contains=context.index.contains,
            two_letter_allowlist=context.allowlist,
        )
        assert rejected == ()


def test_slovak_b2_rejects_complete_ou_and_am() -> None:
    context = load_variant_context("slovak")
    assert context.is_word("um") is True
    assert context.is_word("ou") is False
    assert context.is_word("mi") is True
    assert context.is_word("am") is False

    ou_board = Board(get_premiums_path())
    ou_board.cells[6][7].letter = "O"
    ou_move = evaluate_scoring_move(
        ou_board,
        ["U", "M"],
        (Placement(7, 7, "U"), Placement(7, 8, "M")),
        context.is_word,
        letters=context.letters,
        variant="slovak",
    )
    assert ou_move.reason_code == REASON_INVALID_WORD
    assert ou_move.total_score == 0
    assert "ou" in {word.casefold() for word in ou_move.words}

    am_board = Board(get_premiums_path())
    am_board.cells[6][7].letter = "A"
    am_move = evaluate_scoring_move(
        am_board,
        ["M", "I"],
        (Placement(7, 7, "M"), Placement(7, 8, "I")),
        context.is_word,
        letters=context.letters,
        variant="slovak",
    )
    assert am_move.reason_code == REASON_INVALID_WORD
    assert am_move.total_score == 0
    assert "am" in {word.casefold() for word in am_move.words}

    assert context.is_word(_OSAMENIU) is True
    assert context.is_word("LATINOU") is True
    longer = classify_complete_formed_words(
        [_OSAMENIU, "LATINOU"],
        contains=context.index.contains,
        two_letter_allowlist=context.allowlist,
    )
    assert longer == ()


def test_english_two_letter_policy_delegates_to_collins() -> None:
    english = load_variant("english")
    assert load_two_letter_allowlist(english) is None
    context = load_variant_context("english")
    assert context.allowlist is None
    module_text = Path(diagnostics_mod.__file__).read_text(encoding="utf-8")
    assert "isascii" not in module_text
    assert context.is_word("qi") is True
    assert context.is_word("tranquil") is True
    rejected_long = classify_complete_formed_words(
        ["TRANQUIL"],
        contains=context.index.contains,
        two_letter_allowlist=None,
    )
    assert rejected_long == ()
    rejected_qx = classify_complete_formed_words(
        ["QX"],
        contains=context.index.contains,
        two_letter_allowlist=None,
    )
    assert {word.casefold() for word in rejected_qx} == {"qx"}
    assert _word_passes_dictionary(context.index.contains, "qi") is True


def test_engine_cli_rejects_unknown_variant_or_fixture_before_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def _forbidden_index(*args: object, **kwargs: object) -> object:
        calls.append("index")
        raise AssertionError("dictionary must not load for invalid input")

    def _forbidden_search(*args: object, **kwargs: object) -> object:
        calls.append("search")
        raise AssertionError("search must not run for invalid input")

    monkeypatch.setattr(diagnostics_mod, "load_prefix_index", _forbidden_index)
    monkeypatch.setattr(diagnostics_mod, "find_ranked_scoring_moves", _forbidden_search)

    stdout = StringIO()
    stderr = StringIO()
    with pytest.raises(CommandError) as unknown_variant:
        call_command(
            "diagnose_ai_engine",
            variant_slug="klingon",
            fixture_id="nope",
            stdout=stdout,
            stderr=stderr,
        )
    assert unknown_variant.value.returncode == 2
    assert stdout.getvalue() == ""
    assert calls == []

    with pytest.raises(CommandError) as unknown_fixture:
        call_command(
            "diagnose_ai_engine",
            variant_slug="slovak",
            fixture_id="no-such-fixture",
            stdout=stdout,
            stderr=stderr,
        )
    assert unknown_fixture.value.returncode == 2
    assert stdout.getvalue() == ""
    assert calls == []

    assert scenario_asset_path().is_file()
