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
from game.diagnostics import LIVE_SENTINEL
from game.models import DiagnosticPly, DiagnosticRun, Move
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
        run = self._completed_run(
            instrument="position-set", max_plies=200, max_wall_clock_seconds=3600
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
        assert report["report_kind"] == "ai-match"
        sample = report["samples"][0]
        assert sample["plies"] == 24
        assert len(sample["ply_records"]) == 24

    def test_report_and_log_live_under_backend_var(self) -> None:
        run = self._completed_run(max_plies=1)
        errors = _run_runner(run.id)
        assert errors == []
        run.refresh_from_db()
        assert str(Path(run.log_path)).startswith(str(_var_dir()))
        assert Path(run.log_path).is_file()
        assert Path(run.report_path).is_file()


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
