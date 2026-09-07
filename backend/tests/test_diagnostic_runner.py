"""Fake-mode diagnostic runner: ply persistence, cancel, caps, JWT discipline.

Python-loop tests drive the committed runner against the STUB Node worker
(backend/tests/fixtures/diagnostic_stub_worker.mjs) so pytest never imports
Next.js. The real worker's K2 import path is proven separately under plain
node (see the slice report), not here.
"""

from __future__ import annotations

import json
import threading
import uuid as uuid_module
from dataclasses import fields
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from typing import Any

from django.core.management import call_command
from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.urls import reverse

from accounts.models import User
from catalog.models import AIModel
from catalog.selection import DEFAULT_FREE_MODEL_ID, FREE_RIVAL_IDS, FREE_RIVAL_PAIRS
from game import services
from game.admin import spawn_diagnostic_runner
from game.diagnostics import (
    COMPLETION_SOURCE_VOCABULARY,
    LIVE_SENTINEL,
    ModelPositionSample,
    PlyMetricRecord,
    build_model_position_report,
    load_variant_context,
)
from game.management.commands import run_diagnostic_match as runner_module
from game.models import DiagnosticPly, DiagnosticRun, Move
from game.position_sets import default_position_set_dir
from game.services import (
    cancel_diagnostic_run,
    configure_diagnostic_run,
    create_diagnostic_game,
    mint_diagnostic_access_token,
)
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework.test import APIClient

_STUB_WORKER = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "diagnostic_stub_worker.mjs"
)
_POSITION_SET_DIGEST = "f5ae61b467b4f21e6fe9ee94024e9c3c06e09e0dbae7e6cc8954ff911dc86ef4"
_CLOSED_ORIGIN = "http://127.0.0.1:9"

_PROVIDER_BY_ID = {model_id: provider for provider, model_id in FREE_RIVAL_PAIRS}


def _make_rival(*, model_id: str = DEFAULT_FREE_MODEL_ID, **overrides: Any) -> AIModel:
    """Idempotent rival row: TransactionTestCase teardowns in this suite do
    not flush between tests, so seeding must tolerate pre-existing rows."""
    index = list(FREE_RIVAL_IDS).index(model_id) if model_id in FREE_RIVAL_IDS else 0
    provider = _PROVIDER_BY_ID.get(model_id, "openrouter")
    defaults: dict[str, Any] = {
        "provider": provider,
        "display_name": f"Rival {index + 1}",
        "openrouter_available": provider != "nvidia-nim",
        "openrouter_managed": provider != "nvidia-nim",
        "is_active": True,
        "model_type": "language",
        "tags": ["tools"],
        "sort_order": (index + 1) * 10,
    }
    defaults.update(overrides)
    rival, _ = AIModel.objects.get_or_create(model_id=model_id, defaults=defaults)
    return rival


def _create_run(
    *,
    assist_mode: str = "assisted",
    instrument: str = "full-game",
    max_plies: int = 60,
    max_provider_requests: int = 200,
    max_wall_clock_seconds: int = 3600,
    extra_parameters: dict[str, Any] | None = None,
    seat0: AIModel | None = None,
    seat1: AIModel | None = None,
    created_by: User | None = None,
) -> DiagnosticRun:
    seat0 = seat0 or _make_rival()
    seat1 = seat1 or _make_rival(model_id=FREE_RIVAL_IDS[1])
    admin = created_by or User.objects.create_user(username=f"runner-{uuid_module.uuid4().hex[:8]}")
    created = create_diagnostic_game(
        variant_slug="english",
        seed=1234,
        seat0_model_id=seat0.model_id,
        seat1_model_id=seat1.model_id,
        prompt_id=None,
        created_by_id=admin.id,
        assist_mode=assist_mode,
    )
    run = DiagnosticRun.objects.get(pk=created["run_id"])
    parameters: dict[str, Any] = {"django_origin": _CLOSED_ORIGIN}
    if extra_parameters:
        parameters.update(extra_parameters)
    return configure_diagnostic_run(
        run,
        instrument=instrument,
        position_set_digest=_POSITION_SET_DIGEST if instrument == "position-set" else "",
        max_plies=max_plies,
        max_provider_requests=max_provider_requests,
        max_wall_clock_seconds=max_wall_clock_seconds,
        extra_parameters=parameters,
    )


def _run_runner(run_id: uuid_module.UUID, timeout: float = 180.0) -> list[BaseException]:
    result: list[BaseException] = []
    thread = threading.Thread(
        target=_call_runner_with_env, args=(run_id, {}, result)
    )
    thread.start()
    thread.join(timeout=timeout)
    assert not thread.is_alive(), "runner thread did not finish in time"
    return result


def _ply_blob(run: DiagnosticRun) -> str:
    rows = []
    for ply in DiagnosticPly.objects.filter(run=run).order_by("ply_index"):
        rows.append(
            {field.name: str(getattr(ply, field.name)) for field in DiagnosticPly._meta.fields}
        )
    return json.dumps(rows)


def _load_committed_position_set(digest: str) -> dict[str, Any]:
    directory = default_position_set_dir()
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("set_digest") == digest:
            return data
    raise AssertionError(f"committed position set not found for {digest[:12]}")


class DiagnosticRunnerHelperTests(TestCase):
    def test_configure_rejects_zero_and_over_max_caps(self) -> None:
        run = _create_run(max_plies=10)
        for kwargs in (
            {"max_plies": 0},
            {"max_plies": 201},
            {"max_provider_requests": 0},
            {"max_provider_requests": 1001},
            {"max_wall_clock_seconds": 0},
            {"max_wall_clock_seconds": 21601},
        ):
            with self.assertRaises(services.DiagnosticSessionError):
                configure_diagnostic_run(run, instrument="full-game", **kwargs)

    def test_configure_rejects_position_digest_mismatch(self) -> None:
        run = _create_run()
        with self.assertRaises(services.DiagnosticSessionError):
            configure_diagnostic_run(run, instrument="position-set", position_set_digest="nope")
        with self.assertRaises(services.DiagnosticSessionError):
            configure_diagnostic_run(run, instrument="full-game", position_set_digest="a" * 64)

    def test_configure_writes_caps_fake_mode_and_provisional_subcaps(self) -> None:
        run = _create_run(max_plies=7, max_provider_requests=9, max_wall_clock_seconds=11)
        run.refresh_from_db()
        assert run.max_plies == 7
        assert run.max_provider_requests == 9
        assert run.max_wall_clock_seconds == 11
        assert run.executed_runtime_mode == "fake"
        assert run.parameters_json["subcaps_provisional"] is True
        assert run.parameters_json["django_origin"] == _CLOSED_ORIGIN

    def test_configure_rejects_credential_parameters(self) -> None:
        run = _create_run()
        with self.assertRaises(services.DiagnosticSessionError):
            configure_diagnostic_run(
                run, instrument="full-game", extra_parameters={"api_key": "k"}
            )
        with self.assertRaises(services.DiagnosticSessionError):
            configure_diagnostic_run(
                run,
                instrument="full-game",
                extra_parameters={
                    "note": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlLXZhbHVl"
                },
            )

    def test_cancel_is_cancelled_not_failed_and_creates_no_moves(self) -> None:
        run = _create_run()
        session = run.session
        result = cancel_diagnostic_run(run_id=run.id)
        run.refresh_from_db()
        session.refresh_from_db()
        assert result["ok"] is True
        assert run.status == "cancelled"
        assert run.diagnostic_end_reason == "cancelled"
        assert run.ended_at is not None
        assert session.status == "abandoned"
        assert session.game_end_reason == ""
        assert Move.objects.filter(game=session).count() == 0

    def test_cancel_refuses_terminal_statuses(self) -> None:
        run = _create_run()
        run.status = "completed"
        run.save(update_fields=["status"])
        with self.assertRaises(services.DiagnosticSessionError):
            cancel_diagnostic_run(run_id=run.id)

    def test_stale_heartbeat_flip_abandons_only_stale_rows(self) -> None:
        stale = _create_run()
        stale.status = "running"
        stale.heartbeat_at = services.timezone.now() - services.timedelta(seconds=400)
        stale.max_wall_clock_seconds = 60  # threshold max(300, 120) = 300 < 400
        stale.save()

        abandoned = services.abandon_stale_diagnostic_runs()

        stale.refresh_from_db()
        assert str(stale.id) in abandoned
        assert stale.status == "abandoned"
        assert stale.diagnostic_end_reason == "stale_heartbeat"

        # With the stale row gone the inflight slot is free again; a fresh
        # heartbeat must survive a second sweep untouched.
        fresh = _create_run()
        fresh.status = "running"
        fresh.heartbeat_at = services.timezone.now()
        fresh.save()
        abandoned_again = services.abandon_stale_diagnostic_runs()
        fresh.refresh_from_db()
        assert str(fresh.id) not in abandoned_again
        assert fresh.status == "running"

    def test_mint_is_access_only_and_writes_no_outstanding_token(self) -> None:
        run = _create_run()
        service_user = services.ensure_diagnostic_service_user()
        before = OutstandingToken.objects.count()
        token = mint_diagnostic_access_token(
            service_user, lifetime=services.timedelta(seconds=1200)
        )
        after = OutstandingToken.objects.count()
        assert after == before
        assert token.count(".") == 2
        assert run is not None


class DiagnosticRunnerLoopTests(TransactionTestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_superuser(
            username="runner-admin",
            email="runner-admin@example.com",
            password="runner-admin-pass",
        )

    def _completed_run(self, **kwargs: Any) -> DiagnosticRun:
        return _create_run(**kwargs)

    def test_f03_ply_ceiling_truncates_and_persists_plys(self) -> None:
        run = self._completed_run(max_plies=2)
        errors = _run_runner(run.id)
        assert errors == []
        run.refresh_from_db()
        assert run.status == "completed"
        assert run.diagnostic_end_reason == "truncated"
        assert run.score_authority == ""
        plies = list(DiagnosticPly.objects.filter(run=run).order_by("ply_index"))
        assert len(plies) == 2
        first = plies[0]
        assert first.position_index is None
        assert first.seat_index in (0, 1)
        assert first.model_id in {FREE_RIVAL_IDS[0], FREE_RIVAL_IDS[1]}
        assert first.assist_mode == "assisted"
        assert first.score_authority == "engine"
        assert first.completion_source is None
        assert first.model_authored is None
        assert first.terminal_cause == "AI move failed"
        assert first.provider_requests_used == 0
        assert first.wall_clock_ms is not None
        assert first.executed_runtime_mode == "fake"
        assert first.earlier_attempt_failures is None
        assert first.first_validate_valid is None

    def test_provider_request_ceiling_is_independent(self) -> None:
        run = self._completed_run(
            max_plies=60, max_provider_requests=3, max_wall_clock_seconds=3600
        )
        result: list[BaseException] = []
        thread = threading.Thread(
            target=_call_runner_with_env,
            args=(run.id, {"STUB_REQUESTS_PER_TURN": "2"}, result),
        )
        thread.start()
        thread.join(timeout=180)
        assert not thread.is_alive()
        assert result == []
        run.refresh_from_db()
        assert run.status == "completed"
        assert run.diagnostic_end_reason == "truncated"
        plies = list(DiagnosticPly.objects.filter(run=run).order_by("ply_index"))
        assert len(plies) == 2
        assert all((ply.provider_requests_used or 0) == 2 for ply in plies)

    def test_worker_death_mid_ply_persists_ply_and_respawns(self) -> None:
        run = self._completed_run(max_plies=3)
        result: list[BaseException] = []
        thread = threading.Thread(
            target=_call_runner_with_env,
            args=(run.id, {"STUB_DIE_BEFORE_TURN": "2"}, result),
        )
        thread.start()
        thread.join(timeout=180)
        assert not thread.is_alive()
        assert result == []
        run.refresh_from_db()
        assert run.status == "completed"
        assert run.diagnostic_end_reason == "truncated"
        plies = list(DiagnosticPly.objects.filter(run=run).order_by("ply_index"))
        assert len(plies) == 3
        assert plies[1].terminal_cause == "worker_died"
        assert plies[0].terminal_cause == "AI move failed"
        assert plies[2].terminal_cause == "AI move failed"

    def test_f02_cancel_from_admin_is_cancelled_and_runner_exits_cleanly(self) -> None:
        run = self._completed_run(max_plies=20, max_wall_clock_seconds=600)
        result: list[BaseException] = []
        thread = threading.Thread(
            target=_call_runner_with_env,
            args=(run.id, {"STUB_DELAY_MS": "250"}, result),
        )
        thread.start()
        deadline = 30.0
        waited = 0.0
        while DiagnosticPly.objects.filter(run=run).count() < 1 and waited < deadline:
            threading.Event().wait(0.05)
            waited += 0.05
        assert DiagnosticPly.objects.filter(run=run).count() >= 1
        cancelled = cancel_diagnostic_run(run_id=run.id)
        assert cancelled["ok"] is True
        thread.join(timeout=60)
        assert not thread.is_alive()
        assert result == []
        run.refresh_from_db()
        run.session.refresh_from_db()
        assert run.status == "cancelled"
        assert run.diagnostic_end_reason == "cancelled"
        assert run.session.status == "abandoned"
        assert Move.objects.filter(game=run.session).count() == 0

    def test_f05_live_sentinel_refuses_to_start(self) -> None:
        import os

        run = self._completed_run()
        previous = os.environ.get(LIVE_SENTINEL)
        os.environ[LIVE_SENTINEL] = "1"
        try:
            with self.assertRaises(Exception) as raised:
                call_command(
                    "run_diagnostic_match", "--run-id", str(run.id), stdout=StringIO()
                )
        finally:
            if previous is None:
                os.environ.pop(LIVE_SENTINEL, None)
            else:
                os.environ[LIVE_SENTINEL] = previous
        assert "Refusing to start" in str(raised.exception)
        run.refresh_from_db()
        assert run.status == "queued"

    def test_f06_authorship_abort_writes_ply_first(self) -> None:
        run = self._completed_run(assist_mode="authorship", max_plies=5)
        result: list[BaseException] = []
        thread = threading.Thread(
            target=_call_runner_with_env,
            args=(run.id, {"STUB_COMPLETION_SOURCE": "backend_ranked_candidate"}, result),
        )
        thread.start()
        thread.join(timeout=120)
        assert not thread.is_alive()
        assert len(result) == 1
        run.refresh_from_db()
        assert run.status == "failed"
        assert run.diagnostic_end_reason == "model_authorship_failure"
        ply = DiagnosticPly.objects.filter(run=run).first()
        assert ply is not None
        assert ply.completion_source == "backend_ranked_candidate"

    def test_assisted_mode_continues_on_backend_committed_source(self) -> None:
        run = self._completed_run(assist_mode="assisted", max_plies=2)
        result: list[BaseException] = []
        thread = threading.Thread(
            target=_call_runner_with_env,
            args=(run.id, {"STUB_COMPLETION_SOURCE": "backend_ranked_candidate"}, result),
        )
        thread.start()
        thread.join(timeout=120)
        assert not thread.is_alive()
        assert result == []
        run.refresh_from_db()
        assert run.status == "completed"
        assert run.diagnostic_end_reason == "truncated"
        plies = list(DiagnosticPly.objects.filter(run=run).order_by("ply_index"))
        assert [ply.completion_source for ply in plies] == [
            "backend_ranked_candidate",
            "backend_ranked_candidate",
        ]
        assert all(ply.model_authored is False for ply in plies)

    def test_f04_jwt_is_never_echoed_anywhere(self) -> None:
        env_dump = _var_dir() / f"env-{uuid_module.uuid4().hex}.json"
        ipc_dump = _var_dir() / f"ipc-{uuid_module.uuid4().hex}.jsonl"
        run = self._completed_run(max_plies=1)
        result: list[BaseException] = []
        thread = threading.Thread(
            target=_call_runner_with_env,
            args=(
                run.id,
                {"STUB_ENV_DUMP": str(env_dump), "STUB_IPC_DUMP": str(ipc_dump)},
                result,
            ),
        )
        thread.start()
        thread.join(timeout=120)
        assert not thread.is_alive()
        assert result == []
        run.refresh_from_db()

        assert env_dump.is_file()
        stub_env = json.loads(env_dump.read_text(encoding="utf-8"))
        jwt = stub_env["LIBRETILES_AI_PLAY_JWT"]
        assert jwt.count(".") == 2

        before = OutstandingToken.objects.count()
        service_user = services.ensure_diagnostic_service_user()
        mint_diagnostic_access_token(
            service_user, lifetime=services.timedelta(seconds=600)
        )
        assert OutstandingToken.objects.count() == before

        log_bytes = Path(run.log_path).read_text(encoding="utf-8")
        assert jwt not in log_bytes
        assert jwt not in _ply_blob(run)
        assert jwt not in json.dumps(run.parameters_json)
        if run.report_path:
            assert jwt not in Path(run.report_path).read_text(encoding="utf-8")
        assert ipc_dump.is_file()
        assert jwt not in ipc_dump.read_text(encoding="utf-8")

    def test_f09_node_env_is_whitelisted(self) -> None:
        env_dump = _var_dir() / f"env-{uuid_module.uuid4().hex}.json"
        run = self._completed_run(max_plies=1)
        result: list[BaseException] = []
        thread = threading.Thread(
            target=_call_runner_with_env,
            args=(
                run.id,
                {"STUB_ENV_DUMP": str(env_dump)},
                result,
                {
                    "DJANGO_SECRET_KEY": "decoy-must-not-cross",
                    "DATABASE_URL": "postgres://decoy",
                    "SECRET_KEY": "decoy-two",
                    "NVIDIA_API_KEY": "decoy-nim",
                    "OPENROUTER_API_KEY": "decoy-or",
                    "APPIMAGE": "decoy-appimage",
                    "ARGV0": "decoy-argv0",
                    "APPDIR": "decoy-appdir",
                },
            ),
        )
        thread.start()
        thread.join(timeout=120)
        assert not thread.is_alive()
        assert result == []

        stub_env = json.loads(env_dump.read_text(encoding="utf-8"))
        for forbidden in (
            "DJANGO_SECRET_KEY",
            "DATABASE_URL",
            "SECRET_KEY",
            "NVIDIA_API_KEY",
            "OPENROUTER_API_KEY",
            "LIBRETILES_AI_PLAY_LIVE",
            "APPIMAGE",
            "ARGV0",
            "APPDIR",
        ):
            assert forbidden not in stub_env, forbidden
        assert stub_env["BACKEND_URL"] == _CLOSED_ORIGIN
        assert "LIBRETILES_AI_PLAY_JWT" in stub_env
        assert "PATH" in stub_env

    def test_position_set_run_persists_position_index_and_exhausts(self) -> None:
        rival = _make_rival()
        run = self._completed_run(
            instrument="position-set",
            max_plies=200,
            max_wall_clock_seconds=3600,
            seat0=rival,
            seat1=rival,
        )
        errors = _run_runner(run.id, timeout=300)
        assert errors == []
        run.refresh_from_db()
        assert run.status == "completed"
        assert run.diagnostic_end_reason == "position_set_exhausted"
        assert run.score_authority == "engine"
        plies = list(DiagnosticPly.objects.filter(run=run).order_by("ply_index"))
        assert [ply.position_index for ply in plies] == list(range(24))
        assert run.report_path
        report = json.loads(Path(run.report_path).read_text(encoding="utf-8"))
        assert report["report_kind"] == "model-position"
        assert report["executed_runtime_mode"] == "fake"
        assert report["requested"]["position_set_digest"] == _POSITION_SET_DIGEST
        assert report["requested"]["model_id"] == rival.model_id
        assert report["requested"]["script"] == "generic_unchanged"
        assert report["requested"]["queue_mode"] == "selected-only"
        assert "parameters_json" not in json.dumps(report)
        samples = report["samples"]
        assert [sample["position"]["position_index"] for sample in samples] == list(range(24))
        assert all(
            sample["position"]["set_digest"] == _POSITION_SET_DIGEST for sample in samples
        )
        summary = report["summary"]
        assert summary["sample_count"] == 24
        assert summary["pass_count"] == 0
        assert summary["fail_count"] == 24
        assert summary["position_count"] == 24
        assert summary["unattempted_count"] == 0
        assert summary["end_reason"] == "position_set_exhausted"
        assert summary["truncated"] is False
        assert summary["move_quality_sample_count"] == 0
        assert summary["did_not_measure"] == 24
        assert "move_quality_ratio" not in summary
        assert summary["completion_source_counts"] == {
            source: 0 for source in COMPLETION_SOURCE_VOCABULARY
        }
        assert summary["completion_source_did_not_measure_count"] == 24
        assert summary["total_provider_requests"] == 0
        asset = _load_committed_position_set(_POSITION_SET_DIGEST)
        for index, sample in enumerate(samples):
            assert sample["score"] is None
            assert sample["verdict"] == "fail"
            assert sample["reason_code"] == "generic_unchanged_turn"
            assert sample["model_legal_score"] is None
            baseline = asset["positions"][index]["engine_baseline"]
            assert sample["ranked_best_score"] == baseline["ranked_best_score"]
            assert sample["ranked_search_complete"] == baseline["ranked_search_complete"]
            assert sample["seat_index"] == asset["positions"][index]["to_move_seat_index"]
            assert sample["executed_runtime_mode"] == "fake"

    def test_position_set_truncated_reports_actual_plies_and_unattempted(self) -> None:
        rival = _make_rival()
        run = self._completed_run(
            instrument="position-set", max_plies=2, seat0=rival, seat1=rival
        )
        errors = _run_runner(run.id, timeout=300)
        assert errors == []
        run.refresh_from_db()
        assert run.status == "completed"
        assert run.diagnostic_end_reason == "truncated"
        assert DiagnosticPly.objects.filter(run=run).count() == 2
        assert run.report_path
        report = json.loads(Path(run.report_path).read_text(encoding="utf-8"))
        assert report["report_kind"] == "model-position"
        samples = report["samples"]
        assert [sample["position"]["position_index"] for sample in samples] == [0, 1]
        summary = report["summary"]
        assert summary["sample_count"] == 2
        assert summary["position_count"] == 24
        assert summary["unattempted_count"] == 22
        assert summary["end_reason"] == "truncated"
        assert summary["truncated"] is True
        assert summary["move_quality_sample_count"] == 0
        assert summary["did_not_measure"] == 2
        assert "move_quality_ratio" not in summary

    def test_position_set_authorship_abort_serializes_only_actual_plies(self) -> None:
        rival = _make_rival()
        run = self._completed_run(
            instrument="position-set",
            assist_mode="authorship",
            max_plies=5,
            seat0=rival,
            seat1=rival,
        )
        result: list[BaseException] = []
        thread = threading.Thread(
            target=_call_runner_with_env,
            args=(run.id, {"STUB_COMPLETION_SOURCE": "backend_ranked_candidate"}, result),
        )
        thread.start()
        thread.join(timeout=120)
        assert not thread.is_alive()
        assert len(result) == 1
        run.refresh_from_db()
        assert run.status == "failed"
        assert run.diagnostic_end_reason == "model_authorship_failure"
        assert DiagnosticPly.objects.filter(run=run).count() == 1
        assert run.report_path
        report = json.loads(Path(run.report_path).read_text(encoding="utf-8"))
        assert report["report_kind"] == "model-position"
        assert len(report["samples"]) == 1
        summary = report["summary"]
        assert summary["sample_count"] == 1
        assert summary["unattempted_count"] == 23
        assert summary["end_reason"] == "model_authorship_failure"
        assert summary["truncated"] is False

    def test_mixed_pair_position_set_drives_but_refuses_publication(self) -> None:
        run = self._completed_run(
            instrument="position-set", max_plies=200, max_wall_clock_seconds=3600
        )
        errors = _run_runner(run.id, timeout=300)
        assert errors == []
        run.refresh_from_db()
        assert run.status == "completed"
        assert run.diagnostic_end_reason == "position_set_exhausted"
        assert DiagnosticPly.objects.filter(run=run).count() == 24
        assert run.report_path == ""
        assert not (_var_dir() / f"{run.id}-report.json").exists()

    def test_report_and_log_live_under_backend_var(self) -> None:
        run = self._completed_run(max_plies=1)
        errors = _run_runner(run.id)
        assert errors == []
        run.refresh_from_db()
        assert str(Path(run.log_path)).startswith(str(_var_dir()))
        assert Path(run.log_path).is_file()
        assert Path(run.report_path).is_file()
        report = json.loads(Path(run.report_path).read_text(encoding="utf-8"))
        assert report["report_kind"] == "ai-match"


def _var_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "var" / "diagnostics"


def _call_runner_with_env(
    run_id: uuid_module.UUID,
    stub_env: dict[str, str],
    result: list[BaseException],
    decoys: dict[str, str] | None = None,
) -> None:
    """Run the runner in this thread with stub knobs and optional decoys."""
    import os

    for name, value in stub_env.items():
        os.environ[name] = value
    if decoys:
        for name, value in decoys.items():
            os.environ[name] = value
    os.environ["LIBRETILES_DIAGNOSTIC_WORKER"] = str(_STUB_WORKER)
    try:
        call_command("run_diagnostic_match", "--run-id", str(run_id), stdout=StringIO())
    except BaseException as exc:
        result.append(exc)
    finally:
        for name in list(stub_env) + list(decoys or {}):
            os.environ.pop(name, None)
        os.environ.pop("LIBRETILES_DIAGNOSTIC_WORKER", None)
        connection.close()


class DiagnosticAdminLauncherTests(TransactionTestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_superuser(
            username="launcher-admin",
            email="launcher-admin@example.com",
            password="launcher-admin-pass",
        )
        self.seat0 = _make_rival()
        self.seat1 = _make_rival(model_id=FREE_RIVAL_IDS[1])
        self.client = APIClient()
        self.client.force_login(self.admin)
        self.launch_url = reverse("admin:game_diagnosticrun_launch")
        self.spawns: list[Any] = []
        self._original_spawn = spawn_diagnostic_runner
        import game.admin as admin_module

        def _capture_spawn(run_id: Any) -> None:
            self.spawns.append(run_id)

        admin_module.spawn_diagnostic_runner = _capture_spawn

    def tearDown(self) -> None:
        import game.admin as admin_module

        admin_module.spawn_diagnostic_runner = self._original_spawn

    def _post_launch(self, **overrides: str) -> Any:
        payload: dict[str, str] = {
            "instrument": "full-game",
            "assist_mode": "assisted",
            "variant_slug": "english",
            "seat0_model_id": self.seat0.model_id,
            "seat1_model_id": self.seat1.model_id,
            "seed": "4242",
            "max_plies": "60",
            "max_provider_requests": "200",
            "max_wall_clock_seconds": "3600",
            "position_set_digest": "",
        }
        payload.update(overrides)
        return self.client.post(self.launch_url, payload)

    def test_launcher_creates_configured_run_and_spawns_runner(self) -> None:
        response = self._post_launch()
        assert response.status_code == 302
        run = DiagnosticRun.objects.order_by("-created_at").first()
        assert run is not None
        assert run.created_by_id == self.admin.id
        assert run.status == "queued"
        assert run.executed_runtime_mode == "fake"
        assert run.instrument == "full-game"
        assert run.max_plies == 60
        assert run.max_provider_requests == 200
        assert run.max_wall_clock_seconds == 3600
        assert run.parameters_json["script"] == "generic_unchanged"
        assert run.parameters_json["queue_mode"] == "selected-only"
        assert run.parameters_json["subcaps_provisional"] is True
        assert run.parameters_json["django_origin"].startswith("http")
        assert len(self.spawns) == 1
        assert str(self.spawns[0]) == str(run.id)

    def test_f07_second_inflight_launch_is_form_message_not_500(self) -> None:
        first = self._post_launch()
        assert first.status_code == 302
        second = self._post_launch()
        assert second.status_code == 302
        assert len(self.spawns) == 1
        followed = self.client.get(self.launch_url, follow=True)
        assert followed.status_code == 200
        assert "already in flight" in followed.content.decode()

    def test_launcher_refuses_position_set_without_digest(self) -> None:
        response = self._post_launch(
            instrument="position-set", position_set_digest="short"
        )
        assert response.status_code == 200
        assert DiagnosticRun.objects.count() == 0
        assert self.spawns == []

    def test_cancel_action_cancels_running_run(self) -> None:
        run = _create_run(created_by=self.admin)
        run.status = "running"
        run.save(update_fields=["status"])
        changelist = reverse("admin:game_diagnosticrun_changelist")
        response = self.client.post(
            changelist,
            {
                "action": "cancel_selected_runs",
                "_selected_action": [str(run.id)],
            },
        )
        assert response.status_code == 302
        run.refresh_from_db()
        assert run.status == "cancelled"
        assert run.diagnostic_end_reason == "cancelled"
        assert run.session.status == "abandoned"

    def test_changelist_shows_heartbeat_and_inflight_badge(self) -> None:
        run = _create_run(created_by=self.admin)
        run.status = "running"
        run.heartbeat_at = services.timezone.now()
        run.save(update_fields=["status", "heartbeat_at"])
        changelist = reverse("admin:game_diagnosticrun_changelist")
        response = self.client.get(changelist)
        assert response.status_code == 200
        content = response.content.decode()
        assert run.id.hex[:8] in content
        assert "0s" in content


def _position_ply_defaults(run: DiagnosticRun) -> dict[str, Any]:
    return {
        "run": run,
        "seat_index": 0,
        "model_id": run.seat0_model_id,
        "assist_mode": "assisted",
        "score_authority": "engine",
        "model_authored": None,
        "first_validate_valid": None,
        "valid_candidate_count": None,
        "model_legal_score": None,
        "ranked_best_score": None,
        "ranked_search_complete": None,
        "give_up_while_legal": None,
        "playability_status": None,
        "completion_source": None,
        "terminal_cause": "AI move failed",
        "provider_requests_used": 0,
        "steps_consumed": None,
        "wall_clock_ms": 1200,
        "malformed_or_non_tool": None,
        "fallback_attempt_index": None,
        "earlier_attempt_failures": None,
        "executed_runtime_mode": "fake",
    }


class DiagnosticPositionReportTests(TransactionTestCase):
    """In-process model-position reporting: mapping, refusals, no re-drive."""

    def _same_pair_run(self, **kwargs: Any) -> DiagnosticRun:
        rival = _make_rival()
        run = _create_run(instrument="position-set", seat0=rival, seat1=rival, **kwargs)
        # Reporting does not care about status; terminalize so a test can hold
        # several runs without tripping unique_inflight_diagnostic_run.
        run.status = "completed"
        run.save(update_fields=["status", "updated_at"])
        return run

    def _add_ply(
        self,
        run: DiagnosticRun,
        *,
        ply_index: int,
        position_index: int | None,
        **overrides: Any,
    ) -> DiagnosticPly:
        fields_payload = _position_ply_defaults(run)
        fields_payload["ply_index"] = ply_index
        fields_payload["position_index"] = position_index
        fields_payload.update(overrides)
        return DiagnosticPly.objects.create(**fields_payload)

    def _asset_seats(self) -> tuple[int, int]:
        asset = _load_committed_position_set(_POSITION_SET_DIGEST)
        return (
            asset["positions"][0]["to_move_seat_index"],
            asset["positions"][3]["to_move_seat_index"],
        )

    def test_persisted_plies_join_snapshots_and_supply_all_ply_metrics(self) -> None:
        run = self._same_pair_run()
        asset = _load_committed_position_set(_POSITION_SET_DIGEST)
        seat0_move, seat3_move = self._asset_seats()
        self._add_ply(
            run,
            ply_index=0,
            position_index=0,
            seat_index=seat0_move,
            earlier_attempt_failures=["timeout", "rate_limited"],
            valid_candidate_count=3,
            give_up_while_legal=False,
            playability_status="indeterminate",
            wall_clock_ms=1500,
        )
        self._add_ply(
            run,
            ply_index=1,
            position_index=3,
            seat_index=seat3_move,
            provider_requests_used=None,
        )
        fresh_runner = runner_module._DiagnosticMatchRunner(
            run.id, stdout=StringIO(), stderr=StringIO()
        )
        assert fresh_runner.state.records == []
        payload = runner_module._position_set_report_payload(run)
        samples = payload["samples"]
        assert [sample["position"]["position_index"] for sample in samples] == [0, 3]
        ply_field_names = {item.name for item in fields(PlyMetricRecord)}
        for sample in samples:
            assert set(sample) - {
                "position",
                "score",
                "verdict",
                "reason_code",
                "move_quality_ratio",
            } == ply_field_names
        first, third = samples
        assert first["earlier_attempt_failures"] == ["timeout", "rate_limited"]
        assert first["valid_candidate_count"] == 3
        assert first["give_up_while_legal"] is False
        assert first["playability_status"] == "indeterminate"
        assert first["wall_clock_ms"] == 1500
        baseline0 = asset["positions"][0]["engine_baseline"]
        assert first["ranked_best_score"] == baseline0["ranked_best_score"]
        assert first["ranked_search_complete"] == baseline0["ranked_search_complete"]
        baseline3 = asset["positions"][3]["engine_baseline"]
        assert third["ranked_best_score"] == baseline3["ranked_best_score"]
        assert third["ranked_search_complete"] is False
        assert third["provider_requests_used"] is None
        assert third["earlier_attempt_failures"] is None
        assert first["score"] is None
        assert first["verdict"] == "fail"
        assert first["reason_code"] == "generic_unchanged_turn"
        assert first["position"]["set_digest"] == _POSITION_SET_DIGEST
        assert payload["summary"]["sample_count"] == 2
        assert payload["summary"]["unattempted_count"] == 22

    def test_missing_digest_asset_refuses_report_and_writes_no_file(self) -> None:
        run = self._same_pair_run()
        configure_diagnostic_run(
            run,
            instrument="position-set",
            position_set_digest="e" * 64,
            max_plies=10,
            max_provider_requests=100,
            max_wall_clock_seconds=600,
            extra_parameters={"django_origin": _CLOSED_ORIGIN},
        )
        self._add_ply(run, ply_index=0, position_index=0)
        runner = runner_module._DiagnosticMatchRunner(
            run.id, stdout=StringIO(), stderr=StringIO()
        )
        runner._write_report(run)
        run.refresh_from_db()
        assert run.report_path == ""
        assert not (_var_dir() / f"{run.id}-report.json").exists()
        assert DiagnosticPly.objects.filter(run=run).count() == 1

    def test_digest_and_variant_mismatch_refuse_publication(self) -> None:
        run = self._same_pair_run()
        seat0_move, _ = self._asset_seats()
        self._add_ply(run, ply_index=0, position_index=0, seat_index=seat0_move)
        asset = _load_committed_position_set(_POSITION_SET_DIGEST)
        wrong_digest = dict(asset)
        wrong_digest["set_digest"] = "b" * 64
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload_from_asset(run, wrong_digest)
        assert "digest" in str(raised.exception)
        wrong_variant = dict(asset)
        wrong_variant["variant_slug"] = "slovak"
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload_from_asset(run, wrong_variant)
        assert "variant" in str(raised.exception)

    def test_invalid_and_duplicate_position_index_refuse_publication(self) -> None:
        run = self._same_pair_run()
        self._add_ply(run, ply_index=0, position_index=None)
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload(run)
        assert "position_index" in str(raised.exception)
        duplicate = self._same_pair_run()
        seat0_move, _ = self._asset_seats()
        self._add_ply(duplicate, ply_index=0, position_index=0, seat_index=seat0_move)
        self._add_ply(duplicate, ply_index=1, position_index=0, seat_index=seat0_move)
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload(duplicate)
        assert "same position_index" in str(raised.exception)
        unknown = self._same_pair_run()
        self._add_ply(unknown, ply_index=0, position_index=99)
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload(unknown)
        assert "unknown" in str(raised.exception)

    def test_seat_and_model_identity_refusals(self) -> None:
        run = self._same_pair_run()
        seat0_move, _ = self._asset_seats()
        wrong_seat = (seat0_move + 1) % 2
        self._add_ply(run, ply_index=0, position_index=0, seat_index=wrong_seat)
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload(run)
        assert "seat" in str(raised.exception)
        mixed_model = self._same_pair_run()
        self._add_ply(
            mixed_model,
            ply_index=0,
            position_index=0,
            model_id=FREE_RIVAL_IDS[1],
        )
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload(mixed_model)
        assert "model" in str(raised.exception)

    def test_malformed_baseline_and_failures_refuse_publication(self) -> None:
        run = self._same_pair_run()
        seat0_move, _ = self._asset_seats()
        self._add_ply(run, ply_index=0, position_index=0, seat_index=seat0_move)
        asset = _load_committed_position_set(_POSITION_SET_DIGEST)
        tampered = json.loads(json.dumps(asset))
        tampered["positions"][3]["engine_baseline"]["ranked_best_score"] = True
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload_from_asset(run, tampered)
        assert "ranked_best_score" in str(raised.exception)
        tampered_type = json.loads(json.dumps(asset))
        tampered_type["positions"][0]["engine_baseline"]["ranked_search_complete"] = "yes"
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload_from_asset(run, tampered_type)
        assert "ranked_search_complete" in str(raised.exception)
        malformed_failures = self._same_pair_run()
        self._add_ply(
            malformed_failures,
            ply_index=0,
            position_index=0,
            seat_index=seat0_move,
            earlier_attempt_failures={"boom": 1},
        )
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload(malformed_failures)
        assert "earlier_attempt_failures" in str(raised.exception)
        outside_vocabulary = self._same_pair_run()
        self._add_ply(
            outside_vocabulary,
            ply_index=0,
            position_index=0,
            seat_index=seat0_move,
            completion_source="made_up_source",
        )
        with self.assertRaises(runner_module._ReportRefusal) as raised:
            runner_module._position_set_report_payload(outside_vocabulary)
        assert "completion_source" in str(raised.exception)

    def test_reporting_never_drives_remounts_or_overwrites(self) -> None:
        run = self._same_pair_run()
        seat0_move, seat3_move = self._asset_seats()
        self._add_ply(run, ply_index=0, position_index=0, seat_index=seat0_move)
        runner = runner_module._DiagnosticMatchRunner(
            run.id, stdout=StringIO(), stderr=StringIO()
        )

        def _fail_apply(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("reporting remounted a position snapshot")

        def _fail_resolve(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("reporting resolved an acting slot")

        def _fail_turn(**kwargs: Any) -> Any:
            raise AssertionError("reporting sent a worker turn")

        original_apply = runner_module._apply_position_snapshot
        original_resolve = runner_module._resolve_acting_slot
        runner_module._apply_position_snapshot = _fail_apply
        runner_module._resolve_acting_slot = _fail_resolve
        runner._send_turn = _fail_turn
        try:
            runner._write_report(run)
        finally:
            runner_module._apply_position_snapshot = original_apply
            runner_module._resolve_acting_slot = original_resolve
        run.refresh_from_db()
        assert run.report_path
        first_bytes = Path(run.report_path).read_text(encoding="utf-8")
        assert len(json.loads(first_bytes)["samples"]) == 1
        self._add_ply(run, ply_index=1, position_index=3, seat_index=seat3_move)
        runner._write_report(run)
        run.refresh_from_db()
        assert Path(run.report_path).read_text(encoding="utf-8") == first_bytes


class DiagnosticPositionAggregationTests(TestCase):
    """Pure D3 aggregation arithmetic over synthetic position samples."""

    _DIGEST = "c" * 64

    def _sample(self, position_index: int = 0, **ply_overrides: Any) -> ModelPositionSample:
        ply_fields: dict[str, Any] = {
            "seat_index": 0,
            "model_id": "nvidia/nemotron-3-super-120b-a12b",
            "assist_mode": "assisted",
            "score_authority": "engine",
            "model_authored": True,
            "first_validate_valid": True,
            "valid_candidate_count": 2,
            "model_legal_score": 82,
            "ranked_best_score": 90,
            "ranked_search_complete": True,
            "give_up_while_legal": False,
            "playability_status": "found",
            "completion_source": "provider_candidate",
            "terminal_cause": "done",
            "provider_requests_used": 1,
            "steps_consumed": 4,
            "wall_clock_ms": 900,
            "malformed_or_non_tool": False,
            "fallback_attempt_index": None,
            "earlier_attempt_failures": None,
            "executed_runtime_mode": "fake",
        }
        ply_fields.update(ply_overrides)
        return ModelPositionSample(
            set_digest=self._DIGEST,
            position_index=position_index,
            ply=PlyMetricRecord(**ply_fields),
            score=None,
            verdict="fail",
            reason_code="generic_unchanged_turn",
        )

    def _augmented(
        self,
        samples: list[ModelPositionSample],
        *,
        position_count: int,
        attempted_count: int,
        end_reason: str = "position_set_exhausted",
    ) -> dict[str, Any]:
        base = build_model_position_report(
            requested={"variant_slug": "english"},
            context=load_variant_context("english"),
            samples=samples,
            generated_at=datetime(2026, 9, 6, tzinfo=timezone.utc),
            source_revision="test-revision",
        )
        return runner_module._augment_model_position_report(
            base,
            samples=samples,
            position_count=position_count,
            attempted_indices=frozenset(range(attempted_count)),
            end_reason=end_reason,
        )

    def test_ratio_eligibility_values_and_missingness(self) -> None:
        samples = [
            self._sample(0),  # 82/90 eligible
            self._sample(1, model_legal_score=0, ranked_best_score=50),  # measured zero
            self._sample(2, model_legal_score=91, ranked_best_score=76),  # above one
            self._sample(3, ranked_search_complete=False),  # incomplete still eligible
            self._sample(4, model_legal_score=None),  # absent numerator
            self._sample(5, ranked_best_score=None),  # absent denominator
            self._sample(6, ranked_best_score=0),  # zero denominator
            self._sample(7, model_legal_score=True),  # bool masquerade excluded
            self._sample(8, completion_source="backend_ranked_candidate"),  # rescue
            self._sample(9, completion_source="backend_witness_rescue"),
            self._sample(10, model_authored=False),
            self._sample(11, model_authored=None),
        ]
        payload = self._augmented(samples, position_count=12, attempted_count=12)
        sample_payloads = payload["samples"]
        assert sample_payloads[0]["move_quality_ratio"] == 82 / 90
        assert sample_payloads[1]["move_quality_ratio"] == 0.0
        assert sample_payloads[2]["move_quality_ratio"] == 91 / 76 > 1
        assert sample_payloads[3]["move_quality_ratio"] == 82 / 90
        for index in (4, 5, 6, 7, 8, 9, 10, 11):
            assert "move_quality_ratio" not in sample_payloads[index]
        summary = payload["summary"]
        assert summary["move_quality_sample_count"] == 4
        assert summary["did_not_measure"] == 8
        assert summary["move_quality_ratio"] == (82 / 90 + 0.0 + 91 / 76 + 82 / 90) / 4

    def test_d3_summary_keys_histograms_and_totals(self) -> None:
        samples = [
            self._sample(0, completion_source="provider_candidate", provider_requests_used=2),
            self._sample(1, completion_source="provider_candidate", provider_requests_used=1),
            self._sample(
                2,
                completion_source="genuine_no_move_pass",
                model_authored=False,
                model_legal_score=None,
                provider_requests_used=0,
            ),
            self._sample(3, completion_source=None, provider_requests_used=None),
        ]
        payload = self._augmented(samples, position_count=6, attempted_count=4)
        summary = payload["summary"]
        assert summary["position_count"] == 6
        assert summary["unattempted_count"] == 2
        assert summary["end_reason"] == "position_set_exhausted"
        assert summary["truncated"] is False
        assert summary["completion_source_counts"] == {
            "provider_candidate": 2,
            "backend_ranked_candidate": 0,
            "repair_candidate": 0,
            "backend_witness_rescue": 0,
            "genuine_no_move_exchange": 0,
            "genuine_no_move_pass": 1,
        }
        assert summary["completion_source_did_not_measure_count"] == 1
        assert "total_provider_requests" not in summary
        assert payload["executed_runtime_mode"] == "fake"
        measured = self._augmented(samples[:3], position_count=6, attempted_count=4)
        assert measured["summary"]["total_provider_requests"] == 3
        truncated = self._augmented(
            samples[:1], position_count=24, attempted_count=1, end_reason="truncated"
        )
        assert truncated["summary"]["truncated"] is True
        assert truncated["summary"]["end_reason"] == "truncated"
        empty = self._augmented([], position_count=24, attempted_count=0)
        assert empty["summary"]["sample_count"] == 0
        assert empty["summary"]["did_not_measure"] == 0
        assert "move_quality_ratio" not in empty["summary"]
        assert "total_provider_requests" not in empty["summary"]


# ---------------------------------------------------------------------------
# S7 diagnostic target identity: runner + report (F10)
# ---------------------------------------------------------------------------

from unittest import mock  # noqa: E402

from game import diagnostic_targets as dt_module  # noqa: E402
from game.models import DiagnosticAllowedHost, DiagnosticTarget  # noqa: E402

_RUNNER_PUBLIC_ADDRESS = "8.8.8.8"


def _runner_target_dns(addresses: list[str]) -> Any:
    return mock.patch.object(
        dt_module, "resolve_host_addresses", mock.MagicMock(return_value=addresses)
    )


def _runner_target(*, name: str = "Runner target") -> DiagnosticTarget:
    host = DiagnosticAllowedHost.objects.get_or_create(hostname="rival.example.com")[0]
    with _runner_target_dns([_RUNNER_PUBLIC_ADDRESS]):
        return DiagnosticTarget.objects.create(
            name=name,
            base_url=f"https://{host.hostname}/api/v1",
            allowed_host=host,
            model_id="vendor/target-model",
            credential_env_name="OPENROUTER_API_KEY",
        )


class DiagnosticRunnerTargetIdentityTests(TransactionTestCase):
    def setUp(self) -> None:
        self.admin = User.objects.create_user(
            username=f"runner-target-{uuid_module.uuid4().hex[:8]}"
        )
        self.target = _runner_target()

    def _create_target_run(
        self,
        *,
        seat0_target: bool = True,
        seat1_target: bool = True,
        instrument: str = "full-game",
        max_plies: int = 2,
        max_provider_requests: int = 20,
        max_wall_clock_seconds: int = 60,
    ) -> DiagnosticRun:
        seat0 = _make_rival()
        seat1 = _make_rival(model_id=FREE_RIVAL_IDS[1])
        created = create_diagnostic_game(
            variant_slug="english",
            seed=1234,
            seat0_model_id=self.target.model_id if seat0_target else seat0.model_id,
            seat1_model_id=self.target.model_id if seat1_target else seat1.model_id,
            prompt_id=None,
            created_by_id=self.admin.id,
            assist_mode="assisted",
            seat0_target_id=str(self.target.id) if seat0_target else None,
            seat1_target_id=str(self.target.id) if seat1_target else None,
        )
        run = DiagnosticRun.objects.get(pk=created["run_id"])
        parameters: dict[str, Any] = {"django_origin": _CLOSED_ORIGIN}
        return configure_diagnostic_run(
            run,
            instrument=instrument,
            position_set_digest=_POSITION_SET_DIGEST if instrument == "position-set" else "",
            max_plies=max_plies,
            max_provider_requests=max_provider_requests,
            max_wall_clock_seconds=max_wall_clock_seconds,
            extra_parameters=parameters,
        )

    def test_f10_position_pair_identity_is_catalog_or_target(self) -> None:
        run = self._create_target_run(instrument="position-set")
        provider, model_id = runner_module._position_pair_identity(run)
        self.assertEqual(provider, f"diagnostic-target/{self.target.id}")
        self.assertEqual(model_id, "vendor/target-model")

    def test_f10_position_pair_identity_refuses_mixed_identities(self) -> None:
        run = self._create_target_run(instrument="position-set", seat1_target=False)
        with self.assertRaises(runner_module._ReportRefusal):
            runner_module._position_pair_identity(run)

    def test_f10_build_record_carries_target_model_id(self) -> None:
        run = self._create_target_run()
        session = run.session
        acting = services._resolve_acting_ai_slot(session)
        assert acting is not None and acting.diagnostic_target is not None
        runner = runner_module._DiagnosticMatchRunner(
            run.id, stdout=StringIO(), stderr=StringIO()
        )
        record = runner._build_record(
            run=run,
            acting=acting,
            observation=None,
            move=None,
            wall_clock_ms=12,
        )
        self.assertEqual(record.model_id, "vendor/target-model")

    def test_f10_runner_jsonl_carries_only_the_target_id(self) -> None:
        ipc_dump = _var_dir() / f"ipc-target-{uuid_module.uuid4().hex}.jsonl"
        run = self._create_target_run(max_plies=1)
        result: list[BaseException] = []
        thread = threading.Thread(
            target=_call_runner_with_env,
            args=(run.id, {"STUB_IPC_DUMP": str(ipc_dump)}, result),
        )
        thread.start()
        thread.join(timeout=180)
        assert not thread.is_alive()
        self.assertEqual(result, [])
        lines = [
            json.loads(line)
            for line in ipc_dump.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        turn_commands = [item for item in lines if item.get("cmd") == "run_turn"]
        self.assertTrue(turn_commands)
        for command in turn_commands:
            self.assertEqual(command.get("diagnostic_target_id"), str(self.target.id))
            blob = json.dumps(command)
            self.assertNotIn("https://", blob)
            self.assertNotIn("base_url", blob)
            self.assertNotIn("credential_env_name", blob)

    def test_f10_runner_persists_target_model_id_for_ply(self) -> None:
        run = self._create_target_run(max_plies=1)
        result: list[BaseException] = []
        thread = threading.Thread(target=_call_runner_with_env, args=(run.id, {}, result))
        thread.start()
        thread.join(timeout=180)
        assert not thread.is_alive()
        self.assertEqual(result, [])
        ply = DiagnosticPly.objects.filter(run=run).first()
        assert ply is not None
        self.assertEqual(ply.model_id, "vendor/target-model")
        self.assertEqual(ply.seat_index, run.session.current_turn_slot)
