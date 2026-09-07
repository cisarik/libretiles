from __future__ import annotations

import json
import os
import shutil
import subprocess
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

from django.db import transaction
from django.db.utils import OperationalError
from django.utils import timezone as django_timezone

from .admin_controls import (
    LOCK_CONTENTION_MESSAGE,
    CatalogControlError,
    acquire_catalog_write_lock,
)
from .models import (
    MAX_PROBE_LATENCY_MS,
    MAX_PROBE_OUTBOUND_COUNT,
    MAX_PROBES_PER_MODEL,
    PROVIDER_CAPABILITY_STATUSES,
    AIModel,
    CapabilityProbe,
)

LiveWorker = Callable[..., dict[str, Any]]

LIVE_SENTINEL = "PROVIDER_PROBE_LIVE"
PROBE_PROTOCOL_VERSION = 1
PROBE_ADMISSION_SECONDS = 60
PROBE_SUBPROCESS_DEADLINE_SECONDS = 25
PROBE_STDIN_LIMIT = 4096
PROBE_STDOUT_LIMIT = 16_384
PROBE_STDERR_LIMIT = 4096
THROTTLED_MESSAGE = "A catalog probe was recently admitted. Retry after the cooldown."
LIVE_DISABLED_MESSAGE = "Live probing is disabled."
WORKER_UNAVAILABLE_MESSAGE = "The probe worker is unavailable."
SIMULATED_SUMMARY = "Simulated PASS — capability unverified."
FRONTEND_ROOT = Path(__file__).resolve().parents[2] / "frontend"
WORKER_PATH = FRONTEND_ROOT / "scripts" / "probe-worker.mjs"
BASIC_ENV_NAMES = ("PATH", "HOME", "LANG", "LC_ALL", "TZ")
PROVIDER_CREDENTIAL_ENV: dict[str, tuple[str, ...]] = {
    "openrouter": ("OPENROUTER_API_KEY",),
    "nvidia-nim": ("NVIDIA_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "google-gemini": ("GEMINI_API_KEY",),
    "cloudflare-workers-ai": ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN"),
    "mistral": ("MISTRAL_API_KEY",),
    "ibm-watsonx": (
        "IBM_CLOUD_API_KEY",
        "IBM_WATSONX_PROJECT_ID",
        "IBM_WATSONX_REGION",
    ),
    "aion": ("AION_API_KEY",),
    "huggingface": ("HF_TOKEN",),
}
PROBE_SUMMARIES: dict[str, str] = {
    "simulated": SIMULATED_SUMMARY,
    "incomplete": "Live probe did not finish.",
    "live_disabled": "Live probing is disabled.",
    "not_configured": "Provider is not configured.",
    "request_limit": "Probe stopped at the outbound request limit.",
    "timeout": "Probe timed out.",
    "worker_unavailable": "The probe worker is unavailable.",
    "malformed_output": "Probe worker output was discarded.",
    "pair_mismatch": "Probe worker returned a different provider pair.",
    "mode_mismatch": "Probe worker returned a different runtime mode.",
    "capability": "Live capability probe completed.",
    "throttled": "Probe admission is cooling down.",
    "unknown": "Probe finished with an unknown result.",
}

STATUS_SUMMARIES = {
    "pass": "Live capability probe passed.",
    "not_configured": "Provider is not configured.",
    "auth_failed": "Provider authentication failed.",
    "rate_limited": "Provider rate-limited the probe.",
    "model_unavailable": "The probed model is unavailable.",
    "named_tool_unsupported": "Named tool calling is unsupported.",
    "tool_continuation_failed": "Tool continuation failed.",
    "schema_failed": "Probe tool arguments were rejected.",
    "timeout": "Probe timed out.",
    "unknown": "Probe finished with an unknown result.",
}


class ProbeAdmissionError(CatalogControlError):
    def __init__(self, message: str = THROTTLED_MESSAGE, *, status: int = 429) -> None:
        super().__init__(message, status=status)


def run_aimodel_probe(
    *,
    model: AIModel,
    requested_mode: str,
    actor_id: int | None,
    live_sentinel_value: str | None,
    environ: dict[str, str] | None = None,
    spawn: LiveWorker | None = None,
) -> CapabilityProbe:
    mode = "live" if requested_mode == "live" else "fake"
    source = environ if environ is not None else os.environ
    if mode == "live" and live_sentinel_value != "1":
        raise CatalogControlError(LIVE_DISABLED_MESSAGE, status=409)
    spawn_fn = spawn if spawn is not None else _spawn_worker
    try:
        with transaction.atomic():
            control = acquire_catalog_write_lock()
            now = django_timezone.now()
            if control.probe_not_before_at is not None and control.probe_not_before_at > now:
                raise ProbeAdmissionError()
            control.probe_not_before_at = now + timedelta(seconds=PROBE_ADMISSION_SECONDS)
            control.save(update_fields=["probe_not_before_at"])
            if mode == "fake":
                probe = CapabilityProbe.objects.create(
                    ai_model=model,
                    requested_by_id=actor_id,
                    probed_at=now,
                    completed_at=now,
                    provider_snapshot=model.provider[:50],
                    model_id_snapshot=model.model_id[:200],
                    status="pass",
                    latency_ms=0,
                    outbound_count=0,
                    executed_runtime_mode="fake",
                    reason_code="simulated",
                    summary=SIMULATED_SUMMARY,
                )
                _prune_history(model)
                return probe
            probe = CapabilityProbe.objects.create(
                ai_model=model,
                requested_by_id=actor_id,
                probed_at=now,
                completed_at=None,
                provider_snapshot=model.provider[:50],
                model_id_snapshot=model.model_id[:200],
                status="unknown",
                latency_ms=None,
                outbound_count=None,
                executed_runtime_mode="live",
                reason_code="incomplete",
                summary=PROBE_SUMMARIES["incomplete"],
            )
            _prune_history(model)
    except OperationalError as exc:
        raise CatalogControlError(LOCK_CONTENTION_MESSAGE) from exc

    if mode == "fake":
        return probe

    env = _live_worker_env(model.provider, source)
    result = spawn_fn(
        provider=model.provider,
        model_id=model.model_id,
        env=env,
    )
    result = _coerce_live_result(
        result, provider=model.provider, model_id=model.model_id
    )
    _finalize_probe(probe, model=model, result=result)
    return probe


def _live_worker_env(provider: str, source: Mapping[str, str]) -> dict[str, str]:
    env: dict[str, str] = {}
    for name in BASIC_ENV_NAMES:
        value = source.get(name)
        if value:
            env[name] = value
    env[LIVE_SENTINEL] = "1"
    for name in PROVIDER_CREDENTIAL_ENV.get(provider, ()):
        value = source.get(name)
        if value:
            env[name] = value
    return env


def _spawn_worker(*, provider: str, model_id: str, env: dict[str, str]) -> dict[str, Any]:
    node = shutil.which("node")
    if node is None or not WORKER_PATH.is_file():
        return _failure_result(provider, model_id, "worker_unavailable")
    command = {
        "version": PROBE_PROTOCOL_VERSION,
        "mode": "live",
        "provider": provider,
        "model": model_id,
    }
    payload = json.dumps(command, separators=(",", ":"))
    if len(payload.encode("utf-8")) > PROBE_STDIN_LIMIT:
        return _failure_result(provider, model_id, "malformed_output")
    try:
        proc = subprocess.Popen(
            [node, str(WORKER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(FRONTEND_ROOT),
            env=env,
            shell=False,
        )
    except OSError:
        return _failure_result(provider, model_id, "worker_unavailable")
    try:
        stdout, stderr = proc.communicate(
            input=payload,
            timeout=PROBE_SUBPROCESS_DEADLINE_SECONDS,
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        return _failure_result(provider, model_id, "timeout")
    _ = (stderr or "")[:PROBE_STDERR_LIMIT]
    if len((stdout or "").encode("utf-8")) > PROBE_STDOUT_LIMIT:
        return _failure_result(provider, model_id, "malformed_output")
    return _parse_worker_output(stdout or "", provider=provider, model_id=model_id)


def _parse_bounded_int(value: object, maximum: int) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(str(value))
    except (TypeError, ValueError):
        return None
    if parsed < 0 or parsed > maximum:
        return None
    return parsed


def _parse_worker_output(
    stdout: str,
    *,
    provider: str,
    model_id: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return _failure_result(provider, model_id, "malformed_output")
    if not isinstance(payload, dict):
        return _failure_result(provider, model_id, "malformed_output")
    if payload.get("version") != PROBE_PROTOCOL_VERSION:
        return _failure_result(provider, model_id, "malformed_output")
    if payload.get("provider") != provider or payload.get("model") != model_id:
        return _failure_result(provider, model_id, "pair_mismatch")
    if payload.get("executed_runtime_mode") != "live":
        return _failure_result(provider, model_id, "mode_mismatch")
    status = payload.get("status")
    if status not in PROVIDER_CAPABILITY_STATUSES:
        return _failure_result(provider, model_id, "malformed_output")
    reason = payload.get("reason_code")
    if reason not in PROBE_SUMMARIES:
        reason = "unknown"
    return {
        "status": status,
        "reason_code": reason,
        "latency_ms": _parse_bounded_int(payload.get("latency_ms"), MAX_PROBE_LATENCY_MS),
        "outbound_count": _parse_bounded_int(
            payload.get("outbound_count"), MAX_PROBE_OUTBOUND_COUNT
        ),
        "executed_runtime_mode": "live",
        "provider": provider,
        "model": model_id,
    }


def _coerce_live_result(
    result: dict[str, Any],
    *,
    provider: str,
    model_id: str,
) -> dict[str, Any]:
    if not isinstance(result, dict):
        return _failure_result(provider, model_id, "malformed_output")
    if result.get("provider") != provider or result.get("model") != model_id:
        return _failure_result(provider, model_id, "pair_mismatch")
    if result.get("executed_runtime_mode") != "live":
        return _failure_result(provider, model_id, "mode_mismatch")
    status = result.get("status")
    if status not in PROVIDER_CAPABILITY_STATUSES:
        return _failure_result(provider, model_id, "malformed_output")
    reason = result.get("reason_code")
    if reason not in PROBE_SUMMARIES:
        reason = "unknown"
    return {
        "status": status,
        "reason_code": reason,
        "latency_ms": _parse_bounded_int(result.get("latency_ms"), MAX_PROBE_LATENCY_MS),
        "outbound_count": _parse_bounded_int(
            result.get("outbound_count"), MAX_PROBE_OUTBOUND_COUNT
        ),
        "executed_runtime_mode": "live",
        "provider": provider,
        "model": model_id,
    }


def _failure_result(provider: str, model_id: str, reason: str) -> dict[str, Any]:
    status = "timeout" if reason == "timeout" else "unknown"
    if reason == "not_configured":
        status = "not_configured"
    return {
        "status": status,
        "reason_code": reason,
        "latency_ms": None,
        "outbound_count": None,
        "executed_runtime_mode": "live",
        "provider": provider,
        "model": model_id,
    }


def _finalize_probe(
    probe: CapabilityProbe,
    *,
    model: AIModel,
    result: dict[str, Any],
) -> None:
    reason = str(result.get("reason_code") or "unknown")
    status = str(result.get("status") or "unknown")
    if reason == "capability":
        summary = STATUS_SUMMARIES.get(status, PROBE_SUMMARIES["unknown"])
    else:
        summary = PROBE_SUMMARIES.get(reason, PROBE_SUMMARIES["unknown"])
    probe.status = status
    probe.reason_code = reason if reason in PROBE_SUMMARIES else "unknown"
    probe.latency_ms = result.get("latency_ms")
    probe.outbound_count = result.get("outbound_count")
    probe.executed_runtime_mode = "live"
    probe.completed_at = django_timezone.now()
    probe.summary = summary[:200]
    probe.save(
        update_fields=[
            "status",
            "reason_code",
            "latency_ms",
            "outbound_count",
            "executed_runtime_mode",
            "completed_at",
            "summary",
        ]
    )


def _prune_history(model: AIModel) -> None:
    keep_ids = list(
        CapabilityProbe.objects.filter(ai_model=model)
        .order_by("-probed_at", "-id")
        .values_list("id", flat=True)[:MAX_PROBES_PER_MODEL]
    )
    CapabilityProbe.objects.filter(ai_model=model).exclude(id__in=keep_ids).delete()
