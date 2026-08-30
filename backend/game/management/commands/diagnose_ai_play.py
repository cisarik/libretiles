"""Provider-free AI-turn diagnostic command.

Spawns the pytest turn probe via subprocess. This module must not import
pytest, pytest_django, _pytest, ruff, or mypy.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, TypedDict

from django.core.management.base import BaseCommand, CommandError, CommandParser

from game.diagnostics import (
    DEFAULT_MAX_STEPS,
    DEFAULT_QUEUE_MODE,
    DEFAULT_RUNTIME_MODE,
    DEFAULT_TIMEOUT_SECONDS,
    DEFAULT_TURN_COUNT,
    DiagnosticInputError,
    HANDOFF_ENV,
    LIVE_SENTINEL,
    MAX_STEPS_MAX,
    MAX_STEPS_MIN,
    QUEUE_MODES,
    RUNTIME_MODES,
    TIMEOUT_SECONDS_MAX,
    TIMEOUT_SECONDS_MIN,
    TURN_COUNT_MAX,
    TURN_COUNT_MIN,
    TURN_PROBE_NODE,
    UINT32_MAX,
    bound_text,
    build_turn_report,
    dump_report_json,
    format_turn_metric_line,
    live_opt_in_enabled,
    load_variant_context,
    resolve_engine_scenario,
    samples_from_result_payload,
    turn_exit_code,
    write_report_atomically,
)

_REPO_ROOT = Path(__file__).resolve().parents[4]
_BACKEND_ROOT = Path(__file__).resolve().parents[3]


class TurnCliRequest(TypedDict):
    variant_slug: str
    provider: str
    model_id: str
    runtime_mode: str
    timeout_seconds: int
    max_steps: int
    fixture_id: str | None
    seed: int | None
    turn_count: int
    queue_mode: str
    output: str


class Command(BaseCommand):
    help = (
        "Drive one or more independent AI turns through the real Next.js "
        "move route against an ephemeral Django test database."
    )
    requires_system_checks: list[str] = []

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--variant-slug", required=True)
        parser.add_argument("--provider", required=True)
        parser.add_argument("--model-id", required=True)
        parser.add_argument("--runtime-mode", default=DEFAULT_RUNTIME_MODE)
        parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
        parser.add_argument("--max-steps", type=int, default=DEFAULT_MAX_STEPS)
        parser.add_argument("--fixture-id", default=None)
        parser.add_argument("--seed", type=int, default=None)
        parser.add_argument("--turn-count", type=int, default=DEFAULT_TURN_COUNT)
        parser.add_argument("--queue-mode", default=DEFAULT_QUEUE_MODE)
        parser.add_argument("--output", default="-")

    def handle(self, *args: Any, **options: Any) -> None:
        temp_dir: Path | None = None
        try:
            request = _validated_request(options)
            if request["runtime_mode"] == "live" and not live_opt_in_enabled():
                raise DiagnosticInputError(
                    f"--runtime-mode live requires {LIVE_SENTINEL}=1"
                )
            scenario = resolve_engine_scenario(
                variant_slug=request["variant_slug"],
                fixture_id=request["fixture_id"],
                seed=request["seed"],
            )
            context = load_variant_context(request["variant_slug"])
            temp_dir = Path(tempfile.mkdtemp(prefix="libretiles-ai-play-"))
            result_path = temp_dir / "result.json"
            handoff_path = temp_dir / "handoff.json"
            handoff = {
                **request,
                "fixture_variant_slug": scenario.variant_slug,
                "result_path": str(result_path),
                "repo_root": str(_REPO_ROOT),
                "script": _script_for_fixture(request["fixture_id"]),
            }
            handoff_path.write_text(
                json.dumps(handoff, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env[HANDOFF_ENV] = str(handoff_path)
            env.pop("APPIMAGE", None)
            env.pop("ARGV0", None)
            env.pop("APPDIR", None)
            timeout_seconds = request["timeout_seconds"]
            turn_count = request["turn_count"]
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    TURN_PROBE_NODE,
                    "-q",
                    "--tb=short",
                    "--liveserver=127.0.0.1",
                ],
                cwd=_BACKEND_ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout_seconds * turn_count + 180,
                check=False,
            )
            if completed.returncode != 0 or not result_path.is_file():
                detail = bound_text(completed.stderr or completed.stdout or "turn probe failed")
                raise CommandError(detail, returncode=1)
            result = json.loads(result_path.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise DiagnosticInputError("turn probe result is not an object")
            samples = samples_from_result_payload(result)
            requested: dict[str, str | int] = {
                "variant_slug": request["variant_slug"],
                "provider": request["provider"],
                "model_id": request["model_id"],
                "runtime_mode": request["runtime_mode"],
                "timeout_seconds": request["timeout_seconds"],
                "max_steps": request["max_steps"],
                "turn_count": request["turn_count"],
                "queue_mode": request["queue_mode"],
            }
            if request["fixture_id"] is not None:
                requested["fixture_id"] = request["fixture_id"]
            if request["seed"] is not None:
                requested["seed"] = request["seed"]
            report = build_turn_report(
                requested=requested,
                context=context,
                samples=samples,
            )
            label = request["fixture_id"] or f"seed={request['seed']}"
            for sample in samples:
                self.stderr.write(format_turn_metric_line(scenario.variant_slug, label, sample))
            payload = dump_report_json(report)
            output = request["output"]
            if output == "-":
                self.stdout.write(payload, ending="")
            else:
                write_report_atomically(Path(output), payload)
            code = turn_exit_code(samples, runtime_mode=request["runtime_mode"])
            if code != 0:
                raise CommandError(
                    bound_text(f"turn diagnostic finished with exit {code}"),
                    returncode=code,
                )
        except DiagnosticInputError as exc:
            raise CommandError(bound_text(str(exc)), returncode=2) from None
        finally:
            if temp_dir is not None:
                shutil.rmtree(temp_dir, ignore_errors=True)


def _script_for_fixture(fixture_id: str | None) -> str:
    if fixture_id == "english-turn-dead-qqq":
        return "noop_rescue"
    if fixture_id == "slovak-turn-diacritic-blank":
        return "noop_rescue"
    return "noop_rescue"


def _validated_request(options: dict[str, Any]) -> TurnCliRequest:
    variant_slug = options.get("variant_slug")
    if not isinstance(variant_slug, str) or not variant_slug:
        raise DiagnosticInputError("--variant-slug is required")
    provider = options.get("provider")
    if not isinstance(provider, str) or not provider:
        raise DiagnosticInputError("--provider is required")
    model_id = options.get("model_id")
    if not isinstance(model_id, str) or not model_id:
        raise DiagnosticInputError("--model-id is required")
    runtime_raw = options.get("runtime_mode") or DEFAULT_RUNTIME_MODE
    if not isinstance(runtime_raw, str) or runtime_raw not in RUNTIME_MODES:
        raise DiagnosticInputError("--runtime-mode must be fake or live")
    timeout_raw = options.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS)
    if isinstance(timeout_raw, bool) or not isinstance(timeout_raw, int):
        raise DiagnosticInputError("--timeout-seconds must be an integer")
    if timeout_raw < TIMEOUT_SECONDS_MIN or timeout_raw > TIMEOUT_SECONDS_MAX:
        raise DiagnosticInputError("--timeout-seconds must be in 1..600")
    steps_raw = options.get("max_steps", DEFAULT_MAX_STEPS)
    if isinstance(steps_raw, bool) or not isinstance(steps_raw, int):
        raise DiagnosticInputError("--max-steps must be an integer")
    if steps_raw < MAX_STEPS_MIN or steps_raw > MAX_STEPS_MAX:
        raise DiagnosticInputError("--max-steps must be in 5..100")
    fixture_raw = options.get("fixture_id")
    fixture_id: str | None
    if fixture_raw is None or fixture_raw == "":
        fixture_id = None
    elif isinstance(fixture_raw, str):
        fixture_id = fixture_raw
    else:
        raise DiagnosticInputError("--fixture-id must be a string")
    seed_raw = options.get("seed")
    seed: int | None
    if seed_raw is None:
        seed = None
    elif isinstance(seed_raw, bool) or not isinstance(seed_raw, int):
        raise DiagnosticInputError("--seed must be a UINT32 integer")
    elif seed_raw < 0 or seed_raw > UINT32_MAX:
        raise DiagnosticInputError("--seed must be in 0..4294967295")
    else:
        seed = seed_raw
    if (fixture_id is None) == (seed is None):
        raise DiagnosticInputError("exactly one of --fixture-id or --seed is required")
    turn_raw = options.get("turn_count", DEFAULT_TURN_COUNT)
    if isinstance(turn_raw, bool) or not isinstance(turn_raw, int):
        raise DiagnosticInputError("--turn-count must be an integer")
    if turn_raw < TURN_COUNT_MIN or turn_raw > TURN_COUNT_MAX:
        raise DiagnosticInputError("--turn-count must be in 1..300")
    queue_raw = options.get("queue_mode") or DEFAULT_QUEUE_MODE
    if not isinstance(queue_raw, str) or queue_raw not in QUEUE_MODES:
        raise DiagnosticInputError(
            "--queue-mode must be selected-only or catalog-fallback"
        )
    output_raw = options.get("output") or "-"
    if not isinstance(output_raw, str) or not output_raw:
        raise DiagnosticInputError("--output must be a path or '-'")
    if output_raw != "-":
        path = Path(output_raw)
        if path.exists():
            raise DiagnosticInputError("output path already exists")
        if not path.parent.is_dir():
            raise DiagnosticInputError("output directory does not exist")
    return {
        "variant_slug": variant_slug,
        "provider": provider,
        "model_id": model_id,
        "runtime_mode": runtime_raw,
        "timeout_seconds": timeout_raw,
        "max_steps": steps_raw,
        "fixture_id": fixture_id,
        "seed": seed,
        "turn_count": turn_raw,
        "queue_mode": queue_raw,
        "output": output_raw,
    }
