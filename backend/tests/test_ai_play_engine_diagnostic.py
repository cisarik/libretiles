"""Parameterized provider-free engine diagnostic (Slice E)."""

from __future__ import annotations

import ast
import inspect
import json
from collections.abc import Mapping, Sequence
from dataclasses import fields
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from game import diagnostics as diagnostics_mod
from game.diagnostics import (
    ARTIFACT_ID,
    COMPLETION_SOURCE_VOCABULARY,
    REPORT_KIND_AI_MATCH,
    REPORT_KIND_ENGINE,
    REPORT_KIND_MODEL_POSITION,
    REPORT_KIND_POLICY_COMPARISON,
    REPORT_KIND_TURN,
    SECRET_KEY_FRAGMENTS,
    AiMatchSample,
    EngineSample,
    ModelPositionSample,
    PlyMetricRecord,
    PolicyComparisonSample,
    PolicySearchCost,
    TurnAttemptRecord,
    TurnPersistenceEvidence,
    TurnSample,
    ai_match_sample_to_dict,
    build_ai_match_report,
    build_diagnostic_report,
    build_model_position_report,
    build_policy_comparison_report,
    build_turn_report,
    classify_complete_formed_words,
    dump_report_json,
    load_named_scenario,
    load_variant_context,
    model_position_sample_to_dict,
    observe_source_revision,
    ply_metric_to_dict,
    redacted_copy,
    reserved_completion_sources,
    scenario_asset_path,
)
from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.board import Board
from gamecore.legality import REASON_INVALID_WORD, evaluate_scoring_move
from gamecore.types import Placement, WordFound
from gamecore.variant_store import load_two_tile_words, load_variant

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
_SCHEMA_REPORT_KINDS = {
    "engine",
    "turn",
    "policy-comparison",
    "ai-match",
    "model-position",
}
_PLY_METRIC_FIELD_NAMES = tuple(item.name for item in fields(PlyMetricRecord))
_SET_DIGEST = "a" * 64


def _hook_board() -> Board:
    scenario = load_named_scenario("slovak-hooks-umenasi")
    board = Board(get_premiums_path())
    for row, col, letter in scenario.board_letters:
        board.cells[row][col].token = letter
    return board


def _single_codepoint_records(words: Sequence[str]) -> tuple[WordFound, ...]:
    """WordFound records for a variant whose every tile is one code point.

    ⛔ NOT a segmenter for production use. These fixtures state their tile
    evidence explicitly; nothing here reverse-segments an aggregate string that
    a real board produced.
    """
    return tuple(
        WordFound(word, [(7, index) for index in range(len(word))], list(word))
        for word in words
    )


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
    schema = _load_report_schema()
    _assert_schema_v1_structure(schema)
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
        _single_codepoint_records([_OSAMENIU, "LATINOU"]),
        authority=context.authority,
    )
    assert longer == ()
    mixed = classify_complete_formed_words(
        _single_codepoint_records([_OSAMENIU, "am", "LATINOU", "ou"]),
        authority=context.authority,
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
        authority=context.authority,
        letters=context.letters,
        variant="slovak",
    )
    assert move.ok is True
    assert move.total_score == _OSAMENIU_SCORE
    formed = {word.casefold() for word in move.words}
    assert _OSAMENIU.casefold() in formed
    rejected = classify_complete_formed_words(
        move.words_found,
        authority=context.authority,
    )
    assert rejected == ()


def test_slovak_b2_accepts_named_legal_complete_words() -> None:
    context = load_variant_context("slovak")
    assert context.allowlist is not None
    for word in _LEGAL_SLOVAK_TWO_LETTER:
        assert context.is_word(word) is True
        rejected = classify_complete_formed_words(
            _single_codepoint_records([word]),
            authority=context.authority,
        )
        assert rejected == ()


def test_slovak_b2_rejects_complete_ou_and_am() -> None:
    context = load_variant_context("slovak")
    assert context.is_word("um") is True
    assert context.is_word("ou") is False
    assert context.is_word("mi") is True
    assert context.is_word("am") is False

    ou_board = Board(get_premiums_path())
    ou_board.cells[6][7].token = "O"
    ou_move = evaluate_scoring_move(
        ou_board,
        ["U", "M"],
        (Placement(7, 7, "U"), Placement(7, 8, "M")),
        authority=context.authority,
        letters=context.letters,
        variant="slovak",
    )
    assert ou_move.reason_code == REASON_INVALID_WORD
    assert ou_move.total_score == 0
    assert "ou" in {word.casefold() for word in ou_move.words}

    am_board = Board(get_premiums_path())
    am_board.cells[6][7].token = "A"
    am_move = evaluate_scoring_move(
        am_board,
        ["M", "I"],
        (Placement(7, 7, "M"), Placement(7, 8, "I")),
        authority=context.authority,
        letters=context.letters,
        variant="slovak",
    )
    assert am_move.reason_code == REASON_INVALID_WORD
    assert am_move.total_score == 0
    assert "am" in {word.casefold() for word in am_move.words}

    assert context.is_word(_OSAMENIU) is True
    assert context.is_word("LATINOU") is True
    longer = classify_complete_formed_words(
        _single_codepoint_records([_OSAMENIU, "LATINOU"]),
        authority=context.authority,
    )
    assert longer == ()


def test_english_two_letter_policy_delegates_to_collins() -> None:
    english = load_variant("english")
    assert load_two_tile_words(english) is None
    context = load_variant_context("english")
    assert context.allowlist is None
    module_text = Path(diagnostics_mod.__file__).read_text(encoding="utf-8")
    assert "isascii" not in module_text
    assert context.is_word("qi") is True
    assert context.is_word("tranquil") is True
    rejected_long = classify_complete_formed_words(
        _single_codepoint_records(["TRANQUIL"]),
        authority=context.authority,
    )
    assert rejected_long == ()
    rejected_qx = classify_complete_formed_words(
        _single_codepoint_records(["QX"]),
        authority=context.authority,
    )
    assert {word.casefold() for word in rejected_qx} == {"qx"}
    assert context.authority.accepts_word_query("qi") is True
    assert context.authority.accepts_tokens(("Q", "I")) is True


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


def _load_report_schema() -> dict[str, Any]:
    schema_path = get_assets_path() / "diagnostics" / "ai_play_report_v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert isinstance(schema, dict)
    return schema


def _iter_local_refs(node: object) -> list[str]:
    found: list[str] = []
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str):
            found.append(ref)
        for value in node.values():
            found.extend(_iter_local_refs(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_iter_local_refs(item))
    return found


def _resolve_local_ref(schema: Mapping[str, Any], ref: str) -> dict[str, Any]:
    assert ref.startswith("#/"), ref
    current: object = schema
    for part in ref[2:].split("/"):
        assert isinstance(current, dict), ref
        assert part in current, f"{ref} missing {part}"
        current = current[part]
    assert isinstance(current, dict), ref
    return current


def _merged_properties(
    schema: Mapping[str, Any], defn: Mapping[str, Any]
) -> dict[str, Any]:
    props: dict[str, Any] = dict(defn.get("properties") or {})
    for item in defn.get("allOf") or []:
        if not isinstance(item, dict):
            continue
        if "$ref" in item:
            resolved = _resolve_local_ref(schema, str(item["$ref"]))
            props.update(resolved.get("properties") or {})
        elif "properties" in item and isinstance(item["properties"], dict):
            props.update(item["properties"])
    return props


def _assert_keys_redaction_safe(keys: Sequence[str]) -> None:
    for key in keys:
        lowered = key.lower()
        colliding = [fragment for fragment in SECRET_KEY_FRAGMENTS if fragment in lowered]
        assert colliding == [], f"{key} collides with {colliding}"


def _assert_nested_keys_survive(original: object, redacted: object) -> None:
    if isinstance(original, dict):
        assert isinstance(redacted, dict)
        missing = original.keys() - redacted.keys()
        assert not missing, missing
        for key, value in original.items():
            _assert_nested_keys_survive(value, redacted[key])
    elif isinstance(original, list):
        assert isinstance(redacted, list)
        assert len(redacted) == len(original)
        for left, right in zip(original, redacted, strict=True):
            _assert_nested_keys_survive(left, right)


def _assert_schema_v1_structure(schema: Mapping[str, Any]) -> None:
    assert schema["properties"]["artifact"]["const"] == ARTIFACT_ID
    assert set(schema["required"]) == _SCHEMA_REQUIRED
    enum = schema["properties"]["report_kind"]["enum"]
    assert set(enum) == _SCHEMA_REPORT_KINDS
    defs = schema["$defs"]
    assert isinstance(defs, dict)
    one_of = schema["properties"]["samples"]["items"]["oneOf"]
    refs = [item["$ref"] for item in one_of]
    expected_defs = (
        "engineSample",
        "turnSample",
        "policyComparisonSample",
        "modelPositionSample",
        "aiMatchSample",
    )
    for name in expected_defs:
        ref = f"#/$defs/{name}"
        assert ref in refs
        assert name in defs
        _resolve_local_ref(schema, ref)
    for ref in _iter_local_refs(schema):
        _resolve_local_ref(schema, ref)
    variant = schema["properties"]["variant"]
    assert variant["additionalProperties"] is False
    assert set(variant["properties"]) == {
        "slug",
        "lexicon_id",
        "two_letter_lexicon_size",
    }
    two_letter = defs["engineSample"]["properties"]["two_letter_policy"]
    assert two_letter["additionalProperties"] is False
    assert set(two_letter["properties"]) == {"complete_formed_words", "rejected"}
    ply_props = set(defs["plyMetricRecord"]["properties"])
    assert ply_props == set(_PLY_METRIC_FIELD_NAMES)
    completion_enum = set(defs["plyMetricRecord"]["properties"]["completion_source"]["enum"])
    assert completion_enum == {None, *COMPLETION_SOURCE_VOCABULARY}
    assert len(COMPLETION_SOURCE_VOCABULARY) == 6
    position = defs["modelPositionSample"]["properties"]["position"]
    assert position["additionalProperties"] is False
    assert set(position["properties"]) == {"set_digest", "position_index"}
    merged = set(_merged_properties(schema, defs["modelPositionSample"]))
    assert ply_props <= merged
    assert {"position", "score", "verdict", "reason_code"} <= merged
    match_props = set(defs["aiMatchSample"]["properties"])
    assert {
        "ply_records",
        "end_reason",
        "plies",
        "bag_remaining",
        "rack_remaining",
        "final_scores",
        "score_authority",
        "verdict",
        "reason_code",
    } <= match_props
    ply_items = defs["aiMatchSample"]["properties"]["ply_records"]["items"]
    assert ply_items["$ref"] == "#/$defs/plyMetricRecord"


def _assert_report_matches_kind(
    payload: Mapping[str, Any],
    *,
    kind: str,
    def_name: str,
) -> None:
    schema = _load_report_schema()
    missing = _SCHEMA_REQUIRED - payload.keys()
    assert not missing
    assert payload["artifact"] == ARTIFACT_ID
    assert payload["report_kind"] == kind
    assert kind in schema["properties"]["report_kind"]["enum"]
    required = set(schema["$defs"][def_name]["required"])
    samples = payload["samples"]
    assert isinstance(samples, list)
    assert samples
    for sample in samples:
        assert isinstance(sample, dict)
        assert required <= sample.keys()
    summary = payload["summary"]
    assert isinstance(summary, dict)
    assert summary["sample_count"] == len(samples)


def _fully_populated_ply(**overrides: Any) -> PlyMetricRecord:
    payload: dict[str, Any] = {
        "seat_index": 0,
        "model_id": "nvidia/nemotron-3-super-120b-a12b",
        "assist_mode": "assisted",
        "score_authority": "engine",
        "model_authored": True,
        "first_validate_valid": True,
        "valid_candidate_count": 3,
        "model_legal_score": 82,
        "ranked_best_score": 90,
        "ranked_search_complete": True,
        "give_up_while_legal": False,
        "playability_status": "found",
        "completion_source": "provider_candidate",
        "terminal_cause": "done",
        "provider_requests_used": 1,
        "steps_consumed": 4,
        "wall_clock_ms": 1200,
        "malformed_or_non_tool": False,
        "fallback_attempt_index": 1,
        "earlier_attempt_failures": ("timeout",),
        "executed_runtime_mode": "fake",
    }
    payload.update(overrides)
    return PlyMetricRecord(**payload)


def _synthetic_engine_sample() -> EngineSample:
    return EngineSample(
        search_status="found",
        complete=True,
        nodes=1,
        elapsed_ms=1,
        rack="AEINRST",
        formed_words=("RETAINS",),
        score=72,
        placements=[],
        rejected_two_letter_words=(),
        verdict="pass",
        reason_code="ok",
        top_candidate=None,
    )


def _synthetic_turn_sample() -> TurnSample:
    return TurnSample(
        playability_status="found",
        witness=None,
        action="place",
        placements=[],
        formed_words=("RATE",),
        score=8,
        completion_source="backend_ranked_candidate",
        probe_status="found",
        repair_attempted=False,
        terminal_cause=None,
        attempts=(
            TurnAttemptRecord(
                provider="nvidia-nim",
                model_id="nvidia/nemotron-3-super-120b-a12b",
                timeout_seconds=60,
                step_grant=30,
                provider_requests_used=1,
            ),
        ),
        turn_provider_requests_used=1,
        queue_length=1,
        unresolved_in_flight=0,
        persistence=TurnPersistenceEvidence(
            move_id=1,
            move_count_delta=1,
            state_version_delta=1,
            action_matches_sse=True,
            words_match_sse=True,
            score_matches_sse=True,
        ),
        rejected_two_letter_words=(),
        terminal_kind="done",
        lost_terminal=False,
        external_provider_invocations=0,
        backend_origins=(),
        foreign_origins=(),
        executed_runtime_mode="fake",
        verdict="pass",
        reason_code="ok",
    )


def _synthetic_policy_sample() -> PolicyComparisonSample:
    return PolicyComparisonSample(
        variant_slug="english",
        policy_id="witness-first",
        seed=1,
        plies=2,
        end_reason="bag_empty_and_player_out",
        bag_remaining=0,
        rack_remaining={"0": (), "1": ()},
        stranded_total=0,
        rare_unplayed=0,
        rare_total=0,
        exchanges=0,
        passes=0,
        placement_scores={"0": 10, "1": 8},
        final_scores={"0": 10, "1": 8},
        leftover_points={"0": 0, "1": 0},
        search_cost=PolicySearchCost(nodes_sum=1, elapsed_ms_sum=1, decision_count=1),
        formed_words=(),
        rejected_two_letter_words=(),
        verdict="pass",
        reason_code="ok",
    )


def _synthetic_model_position_sample() -> ModelPositionSample:
    return ModelPositionSample(
        set_digest=_SET_DIGEST,
        position_index=3,
        ply=_fully_populated_ply(),
        score=82,
        verdict="pass",
        reason_code="ok",
    )


def _synthetic_ai_match_sample() -> AiMatchSample:
    return AiMatchSample(
        ply_records=(
            _fully_populated_ply(seat_index=0),
            _fully_populated_ply(
                seat_index=1,
                assist_mode="authorship",
                score_authority="model",
                completion_source="repair_candidate",
            ),
        ),
        end_reason="bag_empty_and_player_out",
        plies=2,
        bag_remaining=0,
        rack_remaining={"0": ("A",), "1": ()},
        final_scores={"0": 82, "1": 40},
        score_authority="engine",
        verdict="pass",
        reason_code="ok",
    )


def test_schema_enum_includes_ai_match_and_model_position() -> None:
    schema = _load_report_schema()
    enum = schema["properties"]["report_kind"]["enum"]
    assert "model-position" in enum
    assert "ai-match" in enum
    assert REPORT_KIND_MODEL_POSITION in enum
    assert REPORT_KIND_AI_MATCH in enum


def test_report_kind_constants_include_ai_match_and_model_position() -> None:
    assert REPORT_KIND_AI_MATCH == "ai-match"
    assert REPORT_KIND_MODEL_POSITION == "model-position"
    assert REPORT_KIND_ENGINE == "engine"
    assert REPORT_KIND_TURN == "turn"
    assert REPORT_KIND_POLICY_COMPARISON == "policy-comparison"


def test_schema_structurally_covers_existing_and_new_kinds() -> None:
    schema = _load_report_schema()
    _assert_schema_v1_structure(schema)
    context = load_variant_context("english")
    requested: dict[str, str | int] = {"variant_slug": "english"}
    stamp = datetime(2026, 9, 6, tzinfo=timezone.utc)
    engine_report = build_diagnostic_report(
        requested=requested,
        context=context,
        samples=[_synthetic_engine_sample()],
        generated_at=stamp,
        source_revision="test-revision",
    )
    turn_report = build_turn_report(
        requested=requested,
        context=context,
        samples=[_synthetic_turn_sample()],
        generated_at=stamp,
        source_revision="test-revision",
    )
    policy_report = build_policy_comparison_report(
        requested=requested,
        context=context,
        samples=[_synthetic_policy_sample()],
        generated_at=stamp,
        source_revision="test-revision",
    )
    _assert_report_matches_kind(
        engine_report, kind=REPORT_KIND_ENGINE, def_name="engineSample"
    )
    _assert_report_matches_kind(
        turn_report, kind=REPORT_KIND_TURN, def_name="turnSample"
    )
    _assert_report_matches_kind(
        policy_report, kind=REPORT_KIND_POLICY_COMPARISON, def_name="policyComparisonSample"
    )


def test_new_sample_types_round_trip_and_survive_redaction() -> None:
    ply = _fully_populated_ply()
    ply_payload = ply_metric_to_dict(ply)
    assert set(ply_payload) == set(_PLY_METRIC_FIELD_NAMES)
    _assert_keys_redaction_safe(list(ply_payload))
    ply_with_secret = dict(ply_payload)
    ply_with_secret["token"] = "drop-me"
    ply_redacted = redacted_copy(ply_with_secret)
    assert isinstance(ply_redacted, dict)
    assert "token" not in ply_redacted
    _assert_nested_keys_survive(ply_payload, ply_redacted)

    position = _synthetic_model_position_sample()
    position_payload = model_position_sample_to_dict(position)
    restored_ply = {key: position_payload[key] for key in _PLY_METRIC_FIELD_NAMES}
    assert restored_ply["seat_index"] == ply.seat_index
    assert restored_ply["earlier_attempt_failures"] == list(ply.earlier_attempt_failures or ())
    _assert_keys_redaction_safe(
        [
            *position_payload,
            *position_payload["position"],
        ]
    )
    position_redacted = redacted_copy(position_payload)
    _assert_nested_keys_survive(position_payload, position_redacted)

    match = _synthetic_ai_match_sample()
    match_payload = ai_match_sample_to_dict(match)
    assert match_payload["ply_records"][0]["seat_index"] == 0
    assert match_payload["ply_records"][1]["seat_index"] == 1
    _assert_keys_redaction_safe(
        [
            *match_payload,
            *match_payload["ply_records"][0],
            *match_payload["ply_records"][1],
            *match_payload["rack_remaining"],
            *match_payload["final_scores"],
        ]
    )
    match_redacted = redacted_copy(match_payload)
    _assert_nested_keys_survive(match_payload, match_redacted)


def test_new_report_kinds_build_redact_and_dump() -> None:
    context = load_variant_context("english")
    stamp = datetime(2026, 9, 6, tzinfo=timezone.utc)
    position_report = build_model_position_report(
        requested={"variant_slug": "english", "probe_count": 1},
        context=context,
        samples=[_synthetic_model_position_sample()],
        generated_at=stamp,
        source_revision="test-revision",
    )
    match_report = build_ai_match_report(
        requested={"variant_slug": "english", "turn_count": 2},
        context=context,
        samples=[_synthetic_ai_match_sample()],
        generated_at=stamp,
        source_revision="test-revision",
    )
    _assert_report_matches_kind(
        position_report, kind=REPORT_KIND_MODEL_POSITION, def_name="modelPositionSample"
    )
    _assert_report_matches_kind(
        match_report, kind=REPORT_KIND_AI_MATCH, def_name="aiMatchSample"
    )
    position_dumped = json.loads(dump_report_json(position_report))
    match_dumped = json.loads(dump_report_json(match_report))
    assert position_dumped["report_kind"] == REPORT_KIND_MODEL_POSITION
    assert match_dumped["report_kind"] == REPORT_KIND_AI_MATCH
    assert position_dumped["samples"][0]["position"]["set_digest"] == _SET_DIGEST
    assert match_dumped["samples"][0]["ply_records"][1]["assist_mode"] == "authorship"
    dumped = json.dumps(position_dumped) + json.dumps(match_dumped)
    assert "Bearer" not in dumped
    assert "drop-me" not in dumped


def test_diagnostics_module_ast_forbids_dev_imports() -> None:
    source = Path(diagnostics_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(diagnostics_mod.__file__))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".", 1)[0])
    assert names & {"pytest", "pytest_django", "_pytest", "ruff", "mypy"} == set()
