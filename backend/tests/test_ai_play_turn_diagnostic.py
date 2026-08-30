"""Command-level tests for diagnose_ai_play."""

from __future__ import annotations

import json
import subprocess
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from game.diagnostics import (
    ARTIFACT_ID,
    COMPLETION_SOURCE_VOCABULARY,
    LIVE_SENTINEL,
    REASON_FOUND_NONSCORING_ACTION,
    REASON_GENERIC_UNCHANGED,
    REASON_PERSIST_LOST_TERMINAL,
    REASON_RUNTIME_MODE_NOT_HONORED,
    classify_turn_sample,
    observe_source_revision,
)

_NIM = "nvidia/nemotron-3-super-120b-a12b"
_GEMMA = "google/gemma-4-31b-it:free"


def _sample_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "playability": {"status": "found", "witness": {"words": ["SČÍTALO"]}},
        "action": "place",
        "placements": [
            {"row": 7, "col": 7, "letter": "S"},
            {"row": 7, "col": 8, "letter": "Č"},
            {"row": 7, "col": 9, "letter": "?", "blank_as": "Í"},
        ],
        "formed_words": ["SČÍTALO"],
        "score": 82,
        "completion_source": "backend_ranked_candidate",
        "probe_status": "found",
        "repair_attempted": False,
        "terminal_cause": "backend_ranked_candidate",
        "attempts": [
            {
                "provider": "nvidia-nim",
                "model_id": _NIM,
                "timeout_seconds": 60,
                "step_grant": 30,
                "provider_requests_used": 0,
            }
        ],
        "turn_provider_requests_used": 0,
        "queue_length": 1,
        "unresolved_in_flight": 0,
        "persistence": {
            "move_id": 1,
            "move_count_delta": 1,
            "state_version_delta": 1,
            "action_matches_sse": True,
            "words_match_sse": True,
            "score_matches_sse": True,
        },
        "two_letter_policy": {"complete_formed_words": ["SČÍTALO"], "rejected": []},
        "terminal_kind": "done",
        "lost_terminal": False,
        "external_provider_invocations": 0,
        "backend_origins": ["http://127.0.0.1:9"],
        "foreign_origins": [],
        "verdict": "pass",
        "reason_code": "ok",
        "token": "should-be-redacted",
        "Authorization": "Bearer secret-token",
    }
    payload.update(overrides)
    return payload


def _fake_pytest(monkeypatch: pytest.MonkeyPatch, sample: dict[str, Any]) -> dict[str, Any]:
    captured: dict[str, Any] = {}
    real_run = subprocess.run

    def fake_run(args: list[object], **kwargs: Any) -> MagicMock:
        argv = [str(item) for item in args]
        if "pytest" not in argv:
            return real_run(args, **kwargs)  # type: ignore[return-value]
        captured["args"] = argv
        captured["env"] = kwargs.get("env") or {}
        handoff_path = Path(captured["env"]["LIBRETILES_AI_PLAY_HANDOFF"])
        captured["handoff"] = json.loads(handoff_path.read_text(encoding="utf-8"))
        result_path = Path(str(captured["handoff"]["result_path"]))
        result_path.write_text(
            json.dumps({"samples": [sample]}, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        completed = MagicMock()
        completed.returncode = 0
        completed.stdout = ""
        completed.stderr = ""
        return completed

    monkeypatch.setattr("game.management.commands.diagnose_ai_play.subprocess.run", fake_run)
    return captured


def test_diagnose_ai_play_preserves_all_axes_and_native_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _fake_pytest(monkeypatch, _sample_payload())
    stdout = StringIO()
    call_command(
        "diagnose_ai_play",
        variant_slug="slovak",
        provider="nvidia-nim",
        model_id=_NIM,
        runtime_mode="fake",
        timeout_seconds=60,
        max_steps=30,
        fixture_id="slovak-turn-diacritic-blank",
        turn_count=1,
        queue_mode="selected-only",
        stdout=stdout,
        stderr=StringIO(),
    )
    handoff = captured["handoff"]
    assert handoff["provider"] == "nvidia-nim"
    assert handoff["model_id"] == _NIM
    assert handoff["runtime_mode"] == "fake"
    assert handoff["timeout_seconds"] == 60
    assert handoff["max_steps"] == 30
    assert handoff["fixture_id"] == "slovak-turn-diacritic-blank"
    assert handoff["turn_count"] == 1
    assert handoff["queue_mode"] == "selected-only"
    report = json.loads(stdout.getvalue())
    assert report["requested"]["model_id"] == _NIM
    assert ":" not in _NIM

    captured_free = _fake_pytest(monkeypatch, _sample_payload())
    call_command(
        "diagnose_ai_play",
        variant_slug="english",
        provider="openrouter",
        model_id=_GEMMA,
        fixture_id="english-empty-autolin",
        stdout=StringIO(),
        stderr=StringIO(),
    )
    assert captured_free["handoff"]["model_id"] == _GEMMA
    assert captured_free["handoff"]["model_id"].endswith(":free")


def test_invalid_arguments_exit_two_before_any_server_or_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("pytest/worker must not start for invalid input")

    monkeypatch.setattr("game.management.commands.diagnose_ai_play.subprocess.run", forbidden)
    stdout = StringIO()
    with pytest.raises(CommandError) as missing:
        call_command(
            "diagnose_ai_play",
            variant_slug="slovak",
            provider="nvidia-nim",
            model_id=_NIM,
            stdout=stdout,
            stderr=StringIO(),
        )
    assert missing.value.returncode == 2
    assert stdout.getvalue() == ""

    with pytest.raises(CommandError) as unknown:
        call_command(
            "diagnose_ai_play",
            variant_slug="klingon",
            provider="nvidia-nim",
            model_id=_NIM,
            fixture_id="nope",
            stdout=stdout,
            stderr=StringIO(),
        )
    assert unknown.value.returncode == 2


def test_existing_output_path_is_not_overwritten(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "game.management.commands.diagnose_ai_play.subprocess.run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not run")),
    )
    target = tmp_path / "turn.json"
    target.write_text("keep-me\n", encoding="utf-8")
    with pytest.raises(CommandError) as exc:
        call_command(
            "diagnose_ai_play",
            variant_slug="slovak",
            provider="nvidia-nim",
            model_id=_NIM,
            fixture_id="slovak-hooks-umenasi",
            output=str(target),
            stderr=StringIO(),
        )
    assert exc.value.returncode == 2
    assert target.read_text(encoding="utf-8") == "keep-me\n"


def test_report_matches_v1_turn_branch_and_redacts_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_pytest(monkeypatch, _sample_payload())
    stdout = StringIO()
    call_command(
        "diagnose_ai_play",
        variant_slug="slovak",
        provider="nvidia-nim",
        model_id=_NIM,
        fixture_id="slovak-turn-diacritic-blank",
        stdout=stdout,
        stderr=StringIO(),
    )
    report = json.loads(stdout.getvalue())
    assert report["artifact"] == ARTIFACT_ID
    assert report["report_kind"] == "turn"
    assert report["source_revision"] == observe_source_revision()
    sample = report["samples"][0]
    assert sample["completion_source"] in COMPLETION_SOURCE_VOCABULARY
    dumped = json.dumps(report)
    assert "Bearer" not in dumped
    assert "secret-token" not in dumped
    assert "should-be-redacted" not in dumped
    assert "token" not in sample
    assert report["summary"]["external_provider_invocations"] == 0
    assert report["executed_runtime_mode"] == "fake"
    assert sample["executed_runtime_mode"] == "fake"


def test_live_mode_requires_sentinel_and_exits_two_without_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LIBRETILES_AI_PLAY_LIVE", raising=False)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("live mode must not spawn pytest without sentinel")

    monkeypatch.setattr("game.management.commands.diagnose_ai_play.subprocess.run", forbidden)
    with pytest.raises(CommandError) as exc:
        call_command(
            "diagnose_ai_play",
            variant_slug="slovak",
            provider="nvidia-nim",
            model_id=_NIM,
            runtime_mode="live",
            fixture_id="slovak-hooks-umenasi",
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert exc.value.returncode == 2
    assert LIVE_SENTINEL in str(exc.value)


def test_live_mode_refuses_when_named_credential_is_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIBRETILES_AI_PLAY_LIVE", "1")
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("live mode must not spawn without the named credential")

    monkeypatch.setattr("game.management.commands.diagnose_ai_play.subprocess.run", forbidden)
    stdout = StringIO()
    with pytest.raises(CommandError) as exc:
        call_command(
            "diagnose_ai_play",
            variant_slug="slovak",
            provider="nvidia-nim",
            model_id=_NIM,
            runtime_mode="live",
            fixture_id="slovak-hooks-umenasi",
            stdout=stdout,
            stderr=StringIO(),
        )
    assert exc.value.returncode == 2
    message = str(exc.value)
    assert "NVIDIA_API_KEY" in message
    assert "redacted" in message.casefold()
    assert stdout.getvalue() == ""
    monkeypatch.setenv("NVIDIA_API_KEY", "your-nvidia-api-key")
    with pytest.raises(CommandError) as placeholder:
        call_command(
            "diagnose_ai_play",
            variant_slug="slovak",
            provider="nvidia-nim",
            model_id=_NIM,
            runtime_mode="live",
            fixture_id="slovak-hooks-umenasi",
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert placeholder.value.returncode == 2
    assert "NVIDIA_API_KEY" in str(placeholder.value)
    assert "your-nvidia-api-key" not in str(placeholder.value)


def test_live_mode_refuses_unsupported_provider_before_any_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIBRETILES_AI_PLAY_LIVE", "1")
    monkeypatch.setenv("NVIDIA_API_KEY", "nim-diagnostic-fixture-key")

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("unsupported live provider must not spawn")

    monkeypatch.setattr("game.management.commands.diagnose_ai_play.subprocess.run", forbidden)
    with pytest.raises(CommandError) as exc:
        call_command(
            "diagnose_ai_play",
            variant_slug="slovak",
            provider="groq",
            model_id="openai/gpt-oss-120b",
            runtime_mode="live",
            fixture_id="slovak-hooks-umenasi",
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert exc.value.returncode == 2
    assert "shipped provider" in str(exc.value)


def test_handoff_carries_runtime_mode_to_the_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _fake_pytest(monkeypatch, _sample_payload())
    call_command(
        "diagnose_ai_play",
        variant_slug="slovak",
        provider="nvidia-nim",
        model_id=_NIM,
        runtime_mode="fake",
        fixture_id="slovak-turn-diacritic-blank",
        stdout=StringIO(),
        stderr=StringIO(),
    )
    assert captured["handoff"]["runtime_mode"] == "fake"
    monkeypatch.setenv("LIBRETILES_AI_PLAY_LIVE", "1")
    monkeypatch.setenv("NVIDIA_API_KEY", "nim-diagnostic-fixture-key")
    live_captured = _fake_pytest(monkeypatch, _sample_payload(executed_runtime_mode="live"))
    call_command(
        "diagnose_ai_play",
        variant_slug="slovak",
        provider="nvidia-nim",
        model_id=_NIM,
        runtime_mode="live",
        fixture_id="slovak-turn-diacritic-blank",
        stdout=StringIO(),
        stderr=StringIO(),
    )
    assert live_captured["handoff"]["runtime_mode"] == "live"


def test_report_records_executed_runtime_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _fake_pytest(monkeypatch, _sample_payload(executed_runtime_mode="fake"))
    stdout = StringIO()
    call_command(
        "diagnose_ai_play",
        variant_slug="slovak",
        provider="nvidia-nim",
        model_id=_NIM,
        runtime_mode="fake",
        fixture_id="slovak-turn-diacritic-blank",
        stdout=stdout,
        stderr=StringIO(),
    )
    report = json.loads(stdout.getvalue())
    assert report["requested"]["runtime_mode"] == "fake"
    assert report["executed_runtime_mode"] == "fake"
    assert report["samples"][0]["executed_runtime_mode"] == "fake"


def test_requested_live_but_executed_fake_is_a_verdict_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LIBRETILES_AI_PLAY_LIVE", "1")
    monkeypatch.setenv("NVIDIA_API_KEY", "nim-diagnostic-fixture-key")
    _fake_pytest(monkeypatch, _sample_payload(executed_runtime_mode="fake"))
    stdout = StringIO()
    with pytest.raises(CommandError) as exc:
        call_command(
            "diagnose_ai_play",
            variant_slug="slovak",
            provider="nvidia-nim",
            model_id=_NIM,
            runtime_mode="live",
            fixture_id="slovak-turn-diacritic-blank",
            stdout=stdout,
            stderr=StringIO(),
        )
    assert exc.value.returncode == 1
    report = json.loads(stdout.getvalue())
    assert report["requested"]["runtime_mode"] == "live"
    assert report["executed_runtime_mode"] == "fake"
    sample = report["samples"][0]
    assert sample["verdict"] == "fail"
    assert sample["reason_code"] == REASON_RUNTIME_MODE_NOT_HONORED
    dumped = json.dumps(report)
    assert "nim-diagnostic-fixture-key" not in dumped


def test_command_forwards_only_named_credential_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NVIDIA_API_KEY", "nim-diagnostic-fixture-key")
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-diagnostic-fixture-key")
    monkeypatch.setenv("UNRELATED_API_KEY", "decoy-must-not-be-special-cased")
    fake_captured = _fake_pytest(monkeypatch, _sample_payload())
    stdout = StringIO()
    call_command(
        "diagnose_ai_play",
        variant_slug="slovak",
        provider="nvidia-nim",
        model_id=_NIM,
        runtime_mode="fake",
        fixture_id="slovak-turn-diacritic-blank",
        stdout=stdout,
        stderr=StringIO(),
    )
    fake_env = fake_captured["env"]
    assert "NVIDIA_API_KEY" not in fake_env
    assert "OPENROUTER_API_KEY" not in fake_env
    fake_report = json.loads(stdout.getvalue())
    fake_dump = json.dumps(fake_report)
    assert "nim-diagnostic-fixture-key" not in fake_dump
    assert "or-diagnostic-fixture-key" not in fake_dump
    assert "runtime_mode" in fake_captured["handoff"]
    assert "NVIDIA_API_KEY" not in fake_captured["handoff"]
    monkeypatch.setenv("LIBRETILES_AI_PLAY_LIVE", "1")
    live_captured = _fake_pytest(
        monkeypatch, _sample_payload(executed_runtime_mode="live")
    )
    live_stdout = StringIO()
    call_command(
        "diagnose_ai_play",
        variant_slug="slovak",
        provider="nvidia-nim",
        model_id=_NIM,
        runtime_mode="live",
        fixture_id="slovak-turn-diacritic-blank",
        stdout=live_stdout,
        stderr=StringIO(),
    )
    live_env = live_captured["env"]
    assert "NVIDIA_API_KEY" in live_env
    assert "OPENROUTER_API_KEY" in live_env
    live_dump = json.dumps(json.loads(live_stdout.getvalue()))
    assert "nim-diagnostic-fixture-key" not in live_dump
    assert "or-diagnostic-fixture-key" not in live_dump
    handoff_dump = json.dumps(live_captured["handoff"])
    assert "nim-diagnostic-fixture-key" not in handoff_dump
    assert "or-diagnostic-fixture-key" not in handoff_dump


def test_classify_found_pass_is_fail() -> None:
    verdict, reason = classify_turn_sample(
        playability_status="found",
        action="pass",
        formed_words=(),
        sse_words=(),
        persisted_words=(),
        sse_placements=(),
        persisted_placements=(),
        rejected_two_letter_words=(),
        terminal_kind="done",
        completion_source="genuine_no_move_pass",
        terminal_cause="genuine_no_move_pass",
        coded_provider_error=False,
        move_count_delta=1,
        move_id=9,
        lost_terminal=False,
    )
    assert verdict == "fail"
    assert reason == REASON_FOUND_NONSCORING_ACTION


def test_classify_generic_unchanged_is_fail() -> None:
    verdict, reason = classify_turn_sample(
        playability_status="found",
        action=None,
        formed_words=(),
        sse_words=(),
        persisted_words=(),
        sse_placements=(),
        persisted_placements=(),
        rejected_two_letter_words=(),
        terminal_kind="generic_error",
        completion_source=None,
        terminal_cause=None,
        coded_provider_error=False,
        move_count_delta=0,
        move_id=None,
        lost_terminal=False,
    )
    assert verdict == "fail"
    assert reason == REASON_GENERIC_UNCHANGED


def test_classify_persist_then_lost_terminal() -> None:
    verdict, reason = classify_turn_sample(
        playability_status="found",
        action="place",
        formed_words=("RATE",),
        sse_words=(),
        persisted_words=("RATE",),
        sse_placements=(),
        persisted_placements=[{"row": 7, "col": 7, "letter": "R"}],
        rejected_two_letter_words=(),
        terminal_kind="no_terminal",
        completion_source="backend_ranked_candidate",
        terminal_cause="lost_sse_done",
        coded_provider_error=False,
        move_count_delta=1,
        move_id=3,
        lost_terminal=True,
    )
    assert verdict == "pass_with_telemetry"
    assert reason == REASON_PERSIST_LOST_TERMINAL
