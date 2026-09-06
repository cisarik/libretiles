"""Fake-mode diagnostic match runner (slice 5).

Drives one DiagnosticRun ply-by-ply through ONE long-lived plain-Node worker
(``frontend/scripts/diagnostic-worker.mjs``) that imports the existing
``/api/ai/move`` POST handler. Provider calls stay ZERO: the runner refuses to
start when LIVE_SENTINEL is set, forwards no provider credentials to the Node
child, and this slice only ships script ``generic_unchanged``.

The runner is the ONLY component that mints the access-only service JWT. The
JWT travels solely through the Node child's whitelisted environment
(LIBRETILES_AI_PLAY_JWT); it must never appear on argv, in logs, in reports,
in DiagnosticPly rows, in parameters_json, or in any IPC JSON line.

Isolation rule (same as diagnose_ai_play): this module must not import
pytest, pytest_django, _pytest, ruff, or mypy.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction
from django.utils import timezone

from game.diagnostics import (
    LIVE_SENTINEL,
    PlyMetricRecord,
    redacted_copy,
    live_opt_in_enabled,
    ply_metric_to_dict,
    write_report_atomically,
)
from game.models import DiagnosticPly, DiagnosticRun, GameSession, PlayerSlot
from game.services import abort_diagnostic_run
from game.position_sets import default_position_set_dir

_BACKEND_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_ROOT = _BACKEND_ROOT.parent / "frontend"
_DEFAULT_WORKER_PATH = _FRONTEND_ROOT / "scripts" / "diagnostic-worker.mjs"
_VAR_DIR = _BACKEND_ROOT / "var" / "diagnostics"

_OBSERVATION_LIMIT_BYTES = 1_000_000
_HEARTBEAT_INTERVAL_SECONDS = 30
_HEARTBEAT_PLIES = 5
_WALL_CLOCK_GRACE_SECONDS = 60
_TURN_TIMEOUT_SECONDS = 60
_TURN_MAX_STEPS = 10
_TOKEN_MAX_LIFETIME_SECONDS = 6 * 3600
_MODEL_AUTHORED_SOURCES = frozenset({"provider_candidate", "repair_candidate"})

_FULL_GAME_OVER_REASON = "full_game_over"
_POSITION_SET_EXHAUSTED_REASON = "position_set_exhausted"
_TRUNCATED_REASON = "truncated"


class _RunnerFailure(Exception):
    """Internal condition that must end the run via abort_diagnostic_run."""


class _WallClockExceeded(Exception):
    """SIGALRM backstop past max_wall_clock_seconds + grace."""


def _worker_path() -> Path:
    """Worker script location.

    The default is the committed plain-Node worker. Tests may point the
    LIBRETILES_DIAGNOSTIC_WORKER env var at a stub; the env whitelist and the
    whole IPC protocol are identical for both.
    """
    override = os.environ.get("LIBRETILES_DIAGNOSTIC_WORKER")
    return Path(override) if override else _DEFAULT_WORKER_PATH


def _worker_env_whitelist() -> dict[str, str]:
    """Whitelist, NEVER ``os.environ.copy()``: no Django secrets, no provider
    credentials, no LIVE_SENTINEL, no AppImage harness names."""
    env: dict[str, str] = {}
    for name in ("PATH", "HOME", "LANG", "LC_ALL", "TZ"):
        value = os.environ.get(name)
        if value:
            env[name] = value
    if os.environ.get("LIBRETILES_DIAGNOSTIC_WORKER"):
        # Stub-worker test harness only: forward the STUB_* knobs so pytest
        # can script the fixture worker. The committed default worker never
        # sees this branch because the override is unset outside tests.
        for name, value in os.environ.items():
            if name.startswith("STUB_"):
                env[name] = value
    return env


@dataclass(frozen=True)
class _TurnObservation:
    """Defensive extraction of the worker's TerminalObservation payload."""

    terminal_kind: str | None = None
    action: str | None = None
    completion_source: str | None = None
    probe_status: str | None = None
    repair_attempted: bool | None = None
    terminal_cause: str | None = None
    turn_provider_requests_used: int | None = None
    attempts: tuple[dict[str, Any], ...] = ()
    foreign_origin_count: int | None = None


@dataclass
class _RunnerState:
    jwt: str = ""
    backend_url: str = ""
    script: str = "generic_unchanged"
    queue_mode: str = "selected-only"
    log_path: Path = field(default_factory=Path)
    records: list[PlyMetricRecord] = field(default_factory=list)
    seq: int = 0
    proc: subprocess.Popen[str] | None = None
    _stderr_handle: Any = None


class Command(BaseCommand):
    help = (
        "Drive one fake-mode DiagnosticRun ply-by-ply through a long-lived "
        "plain-Node worker that imports the existing /api/ai/move POST handler."
    )

    requires_system_checks: list[str] = []

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--run-id", type=str, required=True, help="DiagnosticRun UUID")

    def handle(self, *args: Any, **options: Any) -> None:
        raw = str(options["run_id"])
        try:
            run_id = uuid.UUID(raw)
        except ValueError as exc:
            raise CommandError("--run-id must be a UUID") from exc
        if live_opt_in_enabled():
            raise CommandError(
                f"{LIVE_SENTINEL} is set; live diagnostics are a later grant. Refusing to start."
            )
        exit_code = _DiagnosticMatchRunner(run_id, stdout=self.stdout, stderr=self.stderr).run()
        if exit_code != 0:
            raise CommandError(f"diagnostic runner finished with exit code {exit_code}")


class _DiagnosticMatchRunner:
    def __init__(
        self,
        run_id: uuid.UUID,
        *,
        stdout: Any,
        stderr: Any,
    ) -> None:
        self.run_id = run_id
        self.stdout = stdout
        self.stderr = stderr
        self.state = _RunnerState()
        self._plies_since_heartbeat = 0
        self._last_heartbeat_monotonic = time.monotonic()
        self._provider_requests_total = 0
        self._start_monotonic = time.monotonic()

    # ---- logging ---------------------------------------------------------

    def _log(self, message: str) -> None:
        stamp = timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ")
        scrubbed = message.replace(self.state.jwt, "[redacted]") if self.state.jwt else message
        line = f"{stamp} {scrubbed}".replace("\n", " ")
        try:
            with self.state.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError:
            pass

    # ---- entry -----------------------------------------------------------

    def run(self) -> int:
        run = self._claim()
        if run is None:
            return 2
        try:
            if run.instrument == "position-set":
                return self._drive_position_set(run)
            return self._drive_full_game(run)
        except _WallClockExceeded:
            self._log("wall clock exceeded; truncating")
            self._complete(run, _TRUNCATED_REASON)
            return self._finish(0, run)
        except _RunnerFailure as exc:
            self._log(f"runner failure: {exc}")
            abort_diagnostic_run(run_id=run.id, reason="runner_error")
            return self._finish(1, run)
        except Exception as exc:  # pragma: no cover - defensive terminal path
            self._log(f"unexpected runner error: {type(exc).__name__}: {exc}")
            abort_diagnostic_run(run_id=run.id, reason="runner_error")
            return self._finish(1, run)

    def _finish(self, code: int, run: DiagnosticRun) -> int:
        self._shutdown_worker()
        self._write_report(run)
        self._log(f"runner exit code {code}")
        return code

    def _claim(self) -> DiagnosticRun | None:
        run = DiagnosticRun.objects.filter(pk=self.run_id).first()
        self.state.log_path = _VAR_DIR / f"{self.run_id}.log"
        try:
            self.state.log_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass
        if run is None:
            self._log("diagnostic run not found")
            return None
        with transaction.atomic():
            locked = DiagnosticRun.objects.select_for_update().get(pk=self.run_id)
            if locked.status != "queued":
                self._log(f"refusing to claim run in status {locked.status}")
                return None
            if min(
                locked.max_plies,
                locked.max_provider_requests,
                locked.max_wall_clock_seconds,
            ) <= 0:
                self._log("refusing to claim run with a zero cap")
                abort_diagnostic_run(run_id=locked.id, reason="runner_configuration_invalid")
                return None
            locked.status = "running"
            locked.pid = os.getpid()
            locked.heartbeat_at = timezone.now()
            locked.save(
                update_fields=["status", "pid", "heartbeat_at", "updated_at"]
            )
            run = locked
        self._log(f"claimed run {run.id.hex[:8]} pid {run.pid}")
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGALRM, self._on_alarm)
            signal.alarm(run.max_wall_clock_seconds + _WALL_CLOCK_GRACE_SECONDS)
        service_user = _ensure_service_user()
        lifetime = timedelta(
            seconds=min(run.max_wall_clock_seconds + 600, _TOKEN_MAX_LIFETIME_SECONDS)
        )
        self.state.jwt = _mint_token(service_user, lifetime=lifetime)
        parameters = run.parameters_json if isinstance(run.parameters_json, dict) else {}
        backend_url = parameters.get("django_origin")
        if not isinstance(backend_url, str) or not backend_url.startswith(("http://", "https://")):
            self.state.jwt = ""
            self._log("parameters_json is missing django_origin")
            abort_diagnostic_run(run_id=run.id, reason="runner_configuration_invalid")
            return None
        self.state.backend_url = backend_url.rstrip("/")
        self.state.script = (
            str(parameters.get("script", "generic_unchanged")) or "generic_unchanged"
        )
        self.state.queue_mode = (
            str(parameters.get("queue_mode", "selected-only")) or "selected-only"
        )
        run.log_path = str(self.state.log_path)
        run.save(update_fields=["log_path", "updated_at"])
        return run

    def _on_alarm(self, signum: int, frame: Any) -> None:
        raise _WallClockExceeded()

    # ---- shared checks ---------------------------------------------------

    def _check_wall_clock(self, run: DiagnosticRun) -> None:
        elapsed = time.monotonic() - self._start_monotonic
        if elapsed >= run.max_wall_clock_seconds:
            raise _WallClockExceeded()

    def _heartbeat(self, run: DiagnosticRun) -> None:
        now_mono = time.monotonic()
        due_seconds = now_mono - self._last_heartbeat_monotonic >= _HEARTBEAT_INTERVAL_SECONDS
        due_plies = self._plies_since_heartbeat >= _HEARTBEAT_PLIES
        if not (due_seconds or due_plies):
            return
        DiagnosticRun.objects.filter(pk=run.id).update(heartbeat_at=timezone.now())
        self._last_heartbeat_monotonic = now_mono
        self._plies_since_heartbeat = 0

    def _observed_cancel(self, run: DiagnosticRun) -> bool:
        run.refresh_from_db(fields=["status"])
        return run.status == "cancelled"

    # ---- worker process --------------------------------------------------

    def _spawn_worker(self) -> subprocess.Popen[str]:
        node = shutil.which("node")
        if node is None:
            raise _RunnerFailure("node binary not found on PATH")
        worker = _worker_path()
        if not worker.is_file():
            raise _RunnerFailure(f"worker script missing: {worker.name}")
        env = _worker_env_whitelist()
        env["BACKEND_URL"] = self.state.backend_url
        env["LIBRETILES_AI_PLAY_JWT"] = self.state.jwt
        env.setdefault("LIBRETILES_AI_PLAY_SCRIPT", self.state.script)
        stderr_handle = self.state.log_path.open("a", encoding="utf-8")
        self.state._stderr_handle = stderr_handle
        self._log(f"spawning node worker {worker.name} pid-pending")
        return subprocess.Popen(
            [node, str(worker)],
            cwd=str(_FRONTEND_ROOT),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=stderr_handle,
            text=True,
            bufsize=1,
            env=env,
        )

    def _ensure_worker(self) -> subprocess.Popen[str]:
        if self.state.proc is None or self.state.proc.poll() is not None:
            if self.state.proc is not None:
                self._log("node worker no longer alive; spawning a fresh worker")
            self.state.proc = self._spawn_worker()
        return self.state.proc

    def _terminate_worker(self) -> None:
        proc = self.state.proc
        if proc is None:
            return
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        if proc.stdout is not None:
            proc.stdout.close()
        if proc.stdin is not None:
            proc.stdin.close()
        self.state.proc = None
        handle = self.state._stderr_handle
        self.state._stderr_handle = None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                pass

    def _shutdown_worker(self) -> None:
        proc = self.state.proc
        if proc is not None and proc.poll() is None and proc.stdin is not None:
            try:
                proc.stdin.write(json.dumps({"cmd": "shutdown"}) + "\n")
                proc.stdin.flush()
                proc.wait(timeout=10)
            except (OSError, subprocess.TimeoutExpired):
                pass
        self._terminate_worker()

    # ---- one ply over IPC ------------------------------------------------

    def _send_turn(self, **command: Any) -> tuple[_TurnObservation | None, bool]:
        """Send one run_turn command and read ONE capped JSONL observation.

        Returns (observation, worker_alive); observation is None when the
        worker died, spoke garbage, or answered with an error line.
        """
        self.state.seq += 1
        command.update({"cmd": "run_turn", "seq": self.state.seq})
        payload = json.dumps(command, separators=(",", ":"))
        for attempt in range(2):
            proc = self._ensure_worker()
            assert proc.stdin is not None and proc.stdout is not None
            try:
                proc.stdin.write(payload + "\n")
                proc.stdin.flush()
            except (BrokenPipeError, OSError):
                self._terminate_worker()
                continue
            line = proc.stdout.readline()
            if line == "":
                self._log("node worker died mid-ply (stdout EOF)")
                self._terminate_worker()
                return None, False
            if len(line) > _OBSERVATION_LIMIT_BYTES:
                self._log("observation line exceeded length cap; restarting worker")
                self._terminate_worker()
                return None, False
            try:
                answer = json.loads(line)
            except json.JSONDecodeError:
                self._log("malformed worker JSONL; restarting worker")
                self._terminate_worker()
                return None, False
            if not isinstance(answer, dict) or answer.get("seq") != self.state.seq:
                self._log("worker answered out of sequence; restarting worker")
                self._terminate_worker()
                return None, False
            if answer.get("status") != "done":
                message = str(answer.get("message", "worker error"))[:200]
                self._log(f"worker error line: {message}")
                self._terminate_worker()
                return None, False
            observation = answer.get("observation")
            return _extract_observation(observation), True
        return None, False

    # ---- reconciliation --------------------------------------------------

    def _latest_move_after(
        self, session: GameSession, move_count_before: int
    ) -> Any | None:
        moves = list(session.moves.order_by("seq"))
        if len(moves) > move_count_before:
            return moves[-1]
        return None

    # ---- ply record ------------------------------------------------------

    def _build_record(
        self,
        *,
        run: DiagnosticRun,
        acting: PlayerSlot,
        observation: _TurnObservation | None,
        move: Any | None,
        wall_clock_ms: int,
    ) -> PlyMetricRecord:
        meta = move.ai_metadata if move is not None and isinstance(move.ai_metadata, dict) else {}
        source: str | None = observation.completion_source if observation else None
        meta_source = meta.get("completion_source")
        if isinstance(meta_source, str) and meta_source:
            source = meta_source
        attempts = observation.attempts if observation else ()
        if move is not None:
            model_authored: bool | None = source in _MODEL_AUTHORED_SOURCES
        elif observation is not None:
            model_authored = (
                source in _MODEL_AUTHORED_SOURCES if source is not None else None
            )
        else:
            model_authored = None
        valid_raw = meta.get("valid_candidate_count")
        valid_count = valid_raw if isinstance(valid_raw, int) else None
        model_legal_score = (
            move.points
            if move is not None and source in _MODEL_AUTHORED_SOURCES
            else None
        )
        playability = observation.probe_status if observation else None
        if not isinstance(playability, str) or not playability:
            meta_probe = meta.get("probe_status")
            playability = meta_probe if isinstance(meta_probe, str) and meta_probe else None
        cause: str | None = observation.terminal_cause if observation else None
        if not isinstance(cause, str) or not cause:
            meta_cause = meta.get("terminal_cause")
            cause = meta_cause if isinstance(meta_cause, str) and meta_cause else None
        used: int | None = None
        if observation is not None and observation.turn_provider_requests_used is not None:
            used = observation.turn_provider_requests_used
        elif move is not None:
            meta_used = meta.get("provider_requests_used")
            if isinstance(meta_used, int):
                used = meta_used
        give_up: bool | None = None
        action = move.kind if move is not None else (observation.action if observation else None)
        if playability == "found" and action in {"pass", "exchange"}:
            give_up = True
        fallback_index: int | None = None
        if move is not None and attempts:
            fallback_index = len(attempts) - 1
        return PlyMetricRecord(
            seat_index=int(acting.slot),
            model_id=str(acting.ai_model.model_id if acting.ai_model else ""),
            assist_mode=run.assist_mode,  # type: ignore[arg-type]
            score_authority="engine",
            model_authored=model_authored,
            first_validate_valid=None,
            valid_candidate_count=valid_count,
            model_legal_score=model_legal_score,
            ranked_best_score=None,
            ranked_search_complete=None,
            give_up_while_legal=give_up,
            playability_status=playability,
            completion_source=source,
            terminal_cause=cause,
            provider_requests_used=used,
            steps_consumed=None,
            wall_clock_ms=wall_clock_ms,
            malformed_or_non_tool=None,
            fallback_attempt_index=fallback_index,
            earlier_attempt_failures=None,
            executed_runtime_mode="fake",
        )

    def _persist_ply(
        self,
        run: DiagnosticRun,
        record: PlyMetricRecord,
        *,
        ply_index: int,
        position_index: int | None,
    ) -> None:
        DiagnosticPly.objects.create(
            run=run,
            ply_index=ply_index,
            position_index=position_index,
            seat_index=record.seat_index,
            model_id=record.model_id,
            assist_mode=record.assist_mode,
            score_authority=record.score_authority,
            model_authored=record.model_authored,
            first_validate_valid=record.first_validate_valid,
            valid_candidate_count=record.valid_candidate_count,
            model_legal_score=record.model_legal_score,
            ranked_best_score=record.ranked_best_score,
            ranked_search_complete=record.ranked_search_complete,
            give_up_while_legal=record.give_up_while_legal,
            playability_status=record.playability_status,
            completion_source=record.completion_source,
            terminal_cause=record.terminal_cause,
            provider_requests_used=record.provider_requests_used,
            steps_consumed=record.steps_consumed,
            wall_clock_ms=record.wall_clock_ms,
            malformed_or_non_tool=record.malformed_or_non_tool,
            fallback_attempt_index=record.fallback_attempt_index,
            earlier_attempt_failures=(
                list(record.earlier_attempt_failures)
                if record.earlier_attempt_failures is not None
                else None
            ),
            executed_runtime_mode=record.executed_runtime_mode,
        )
        self._log("ply " + json.dumps(redacted_copy(ply_metric_to_dict(record))))

    # ---- terminals -------------------------------------------------------

    def _complete(self, run: DiagnosticRun, end_reason: str) -> None:
        run.refresh_from_db(fields=["status"])
        if run.status in ("cancelled", "failed", "abandoned"):
            return
        run.status = "completed"
        run.diagnostic_end_reason = end_reason
        run.ended_at = timezone.now()
        run.score_authority = "" if end_reason == _TRUNCATED_REASON else "engine"
        run.save(
            update_fields=[
                "status",
                "diagnostic_end_reason",
                "ended_at",
                "score_authority",
                "updated_at",
            ]
        )

    def _write_report(self, run: DiagnosticRun) -> None:
        try:
            run.refresh_from_db()
            if run.report_path:
                return
            context = _load_variant_context(run.variant_slug)
            session = run.session
            slots = {slot.slot: slot for slot in session.slots.all()}
            end_reason = run.diagnostic_end_reason or run.status
            sample = _build_ai_match_sample(
                ply_records=tuple(self.state.records),
                end_reason=end_reason,
                plies=len(self.state.records),
                bag_remaining=len(session.bag_tiles or []),
                rack_remaining={
                    f"slot{number}": tuple(item.rack or [])
                    for number, item in slots.items()
                },
                final_scores={
                    f"slot{number}": item.score for number, item in slots.items()
                },
                score_authority="engine",
                verdict="pass" if run.status == "completed" else "fail",
                reason_code=end_reason,
            )
            requested = {
                "run_id": str(run.id),
                "instrument": run.instrument,
                "variant_slug": run.variant_slug,
                "assist_mode": run.assist_mode,
                "executed_runtime_mode": run.executed_runtime_mode or "fake",
                "driver": "django-runner",
            }
            payload = _dump_ai_match_report(
                requested=requested, context=context, samples=[sample]
            )
            report_path = _VAR_DIR / f"{run.id}-report.json"
            if not report_path.exists():
                write_report_atomically(report_path, payload)
                run.report_path = str(report_path)
                run.save(update_fields=["report_path", "updated_at"])
        except Exception as exc:  # pragma: no cover - report must never kill a run
            self._log(f"report generation skipped: {type(exc).__name__}: {exc}")

    # ---- loops -----------------------------------------------------------

    def _cap_or_truncate(self, run: DiagnosticRun, plies_done: int) -> bool:
        if plies_done >= run.max_plies:
            return True
        if self._provider_requests_total >= run.max_provider_requests:
            self._log("provider request ceiling reached")
            return True
        return False

    def _drive_full_game(self, run: DiagnosticRun) -> int:
        session = run.session
        session.refresh_from_db()
        ply_index = 0
        while True:
            if self._observed_cancel(run):
                self._log("cancel observed; exiting cleanly")
                return self._finish(0, run)
            self._check_wall_clock(run)
            if session.game_over:
                self._complete(run, _FULL_GAME_OVER_REASON)
                return self._finish(0, run)
            if self._cap_or_truncate(run, ply_index):
                self._complete(run, _TRUNCATED_REASON)
                return self._finish(0, run)
            acting = _resolve_acting_slot(session)
            if acting is None or acting.ai_model is None:
                raise _RunnerFailure("no acting AI slot with a model")
            move_count_before = session.moves.count()
            started = time.monotonic()
            observation, alive = self._send_turn(
                game_id=str(session.public_id),
                provider=str(acting.ai_model.provider),
                model_id=str(acting.ai_model.model_id),
                timeout_seconds=_TURN_TIMEOUT_SECONDS,
                max_steps=_TURN_MAX_STEPS,
                script=self.state.script,
                queue_mode=self.state.queue_mode,
                ai_slot=int(session.current_turn_slot or 0),
            )
            wall_ms = int((time.monotonic() - started) * 1000)
            session.refresh_from_db()
            move = self._latest_move_after(session, move_count_before)
            record = self._build_record(
                run=run,
                acting=acting,
                observation=observation if alive else None,
                move=move,
                wall_clock_ms=wall_ms,
            )
            if not alive and observation is None:
                record = _record_with_cause(record, "worker_died")
            self.state.records.append(record)
            self._persist_ply(run, record, ply_index=ply_index, position_index=None)
            ply_index += 1
            self._plies_since_heartbeat += 1
            used = record.provider_requests_used or 0
            self._provider_requests_total += used
            self._heartbeat(run)
            if run.assist_mode == "authorship" and record.completion_source not in _MODEL_AUTHORED_SOURCES:
                self._log(
                    "authorship mode: completion_source "
                    f"{record.completion_source!r} is not model-authored; aborting"
                )
                abort_diagnostic_run(run_id=run.id, reason="model_authorship_failure")
                return self._finish(1, run)

    def _load_position_set(self, digest: str) -> dict[str, Any]:
        directory = default_position_set_dir()
        if digest:
            for path in sorted(directory.glob("*.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if isinstance(data, dict) and data.get("set_digest") == digest:
                    return data
        raise _RunnerFailure(f"no committed position set matches digest {digest[:12]}")

    def _drive_position_set(self, run: DiagnosticRun) -> int:
        session = run.session
        session.refresh_from_db()
        asset = self._load_position_set(run.position_set_digest)
        positions = asset.get("positions")
        if not isinstance(positions, list) or not positions:
            raise _RunnerFailure("position set asset carries no positions")
        ply_index = 0
        for index, snapshot in enumerate(positions):
            if self._observed_cancel(run):
                self._log("cancel observed; exiting cleanly")
                return self._finish(0, run)
            self._check_wall_clock(run)
            if self._cap_or_truncate(run, ply_index):
                self._complete(run, _TRUNCATED_REASON)
                return self._finish(0, run)
            if not isinstance(snapshot, dict):
                continue
            _apply_position_snapshot(session, snapshot)
            session.refresh_from_db()
            if session.game_over:
                continue
            acting = _resolve_acting_slot(session)
            if acting is None or acting.ai_model is None:
                raise _RunnerFailure(f"position {index} has no acting AI slot with a model")
            move_count_before = session.moves.count()
            started = time.monotonic()
            observation, alive = self._send_turn(
                game_id=str(session.public_id),
                provider=str(acting.ai_model.provider),
                model_id=str(acting.ai_model.model_id),
                timeout_seconds=_TURN_TIMEOUT_SECONDS,
                max_steps=_TURN_MAX_STEPS,
                script=self.state.script,
                queue_mode=self.state.queue_mode,
                ai_slot=int(session.current_turn_slot or 0),
            )
            wall_ms = int((time.monotonic() - started) * 1000)
            session.refresh_from_db()
            move = self._latest_move_after(session, move_count_before)
            record = self._build_record(
                run=run,
                acting=acting,
                observation=observation if alive else None,
                move=move,
                wall_clock_ms=wall_ms,
            )
            if not alive and observation is None:
                record = _record_with_cause(record, "worker_died")
            self.state.records.append(record)
            self._persist_ply(run, record, ply_index=ply_index, position_index=index)
            ply_index += 1
            self._plies_since_heartbeat += 1
            used = record.provider_requests_used or 0
            self._provider_requests_total += used
            self._heartbeat(run)
            if run.assist_mode == "authorship" and record.completion_source not in _MODEL_AUTHORED_SOURCES:
                self._log(
                    "authorship mode: completion_source "
                    f"{record.completion_source!r} is not model-authored; aborting"
                )
                abort_diagnostic_run(run_id=run.id, reason="model_authorship_failure")
                return self._finish(1, run)
        self._complete(run, _POSITION_SET_EXHAUSTED_REASON)
        return self._finish(0, run)


# Thin indirections so tests can monkeypatch without importing heavy modules
# at command import time beyond what the loop already needs.

def _resolve_acting_slot(session: GameSession) -> PlayerSlot | None:
    from game.services import _resolve_acting_ai_slot

    return _resolve_acting_ai_slot(session)


def _ensure_service_user() -> Any:
    from game.services import ensure_diagnostic_service_user

    return ensure_diagnostic_service_user()


def _mint_token(service_user: Any, *, lifetime: timedelta) -> str:
    from game.services import mint_diagnostic_access_token

    return mint_diagnostic_access_token(service_user, lifetime=lifetime)


def _apply_position_snapshot(session: GameSession, snapshot: dict[str, Any]) -> None:
    from game.services import apply_position_snapshot

    apply_position_snapshot(session, snapshot)


def _load_variant_context(variant_slug: str) -> Any:
    from game.diagnostics import load_variant_context

    return load_variant_context(variant_slug)


def _build_ai_match_sample(**kwargs: Any) -> Any:
    from game.diagnostics import AiMatchSample

    return AiMatchSample(**kwargs)


def _dump_ai_match_report(**kwargs: Any) -> str:
    from game.diagnostics import build_ai_match_report, dump_report_json

    return dump_report_json(build_ai_match_report(**kwargs))


def _record_with_cause(record: PlyMetricRecord, cause: str) -> PlyMetricRecord:
    from dataclasses import replace

    return replace(record, terminal_cause=cause)


def _extract_observation(payload: Any) -> _TurnObservation | None:
    if not isinstance(payload, dict):
        return None

    def _string(key: str) -> str | None:
        value = payload.get(key)
        return value if isinstance(value, str) and value else None

    used = payload.get("turn_provider_requests_used")
    foreign = payload.get("foreign_origins")
    attempts_raw = payload.get("attempts")
    attempts = tuple(item for item in attempts_raw if isinstance(item, dict)) if isinstance(
        attempts_raw, list
    ) else ()
    repair = payload.get("repair_attempted")
    return _TurnObservation(
        terminal_kind=_string("terminal_kind"),
        action=_string("action"),
        completion_source=_string("completion_source"),
        probe_status=_string("probe_status"),
        repair_attempted=repair if isinstance(repair, bool) else None,
        terminal_cause=_string("terminal_cause"),
        turn_provider_requests_used=used if isinstance(used, int) else None,
        attempts=attempts,
        foreign_origin_count=len(foreign) if isinstance(foreign, list) else None,
    )
