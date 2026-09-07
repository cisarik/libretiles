from __future__ import annotations

import json
from typing import Any
from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from catalog.models import AIModel, CapabilityProbe, CatalogAdminControl
from catalog.provider_probes import (
    LIVE_SENTINEL,
    PROVIDER_CREDENTIAL_ENV,
    run_aimodel_probe,
)
from catalog.selection import DIRECT_FREE_RIVAL_PAIRS


def _model() -> AIModel:
    model, _ = AIModel.objects.get_or_create(
        model_id=DIRECT_FREE_RIVAL_PAIRS[0][1],
        defaults={
            "provider": DIRECT_FREE_RIVAL_PAIRS[0][0],
            "display_name": "Groq",
            "is_active": True,
            "model_type": "language",
            "tags": ["tools"],
            "sort_order": 1,
        },
    )
    return model


class ProviderProbeWorkerTests(TestCase):
    def setUp(self) -> None:
        CatalogAdminControl.objects.get_or_create(
            pk=1, defaults={"revision": 0, "ordering_reviewed": False}
        )
        self.user = User.objects.create_user(username="probe-user", password="x", is_staff=True)
        self.model = _model()

    def test_f03_mocked_live_not_configured_and_spoofed_pair(self) -> None:
        def spawn(*, provider: str, model_id: str, env: dict[str, str]) -> dict[str, Any]:
            assert provider == self.model.provider
            assert model_id == self.model.model_id
            assert LIVE_SENTINEL in env
            return {
                "status": "not_configured",
                "reason_code": "not_configured",
                "latency_ms": 1,
                "outbound_count": 0,
                "executed_runtime_mode": "live",
                "provider": provider,
                "model": model_id,
            }

        probe = run_aimodel_probe(
            model=self.model,
            requested_mode="live",
            actor_id=self.user.pk,
            live_sentinel_value="1",
            environ={"PATH": "/usr/bin", "GROQ_API_KEY": "placeholder"},
            spawn=spawn,
        )
        assert probe.status == "not_configured"
        assert probe.outbound_count == 0
        assert probe.executed_runtime_mode == "live"

        def spoof(*, provider: str, model_id: str, env: dict[str, str]) -> dict[str, Any]:
            return {
                "status": "pass",
                "reason_code": "capability",
                "latency_ms": 9,
                "outbound_count": 1,
                "executed_runtime_mode": "live",
                "provider": "openrouter",
                "model": "attacker/model:free",
            }

        CatalogAdminControl.objects.filter(pk=1).update(probe_not_before_at=None)
        mismatched = run_aimodel_probe(
            model=self.model,
            requested_mode="live",
            actor_id=self.user.pk,
            live_sentinel_value="1",
            environ={"PATH": "/usr/bin"},
            spawn=spoof,
        )
        assert mismatched.status == "unknown"
        assert mismatched.reason_code == "pair_mismatch"
        assert mismatched.outbound_count is None

    def test_f05_worker_faults_are_bounded_without_raw_output(self) -> None:
        from catalog.provider_probes import _parse_worker_output, _spawn_worker

        parsed = _parse_worker_output(
            "not-json <script>alert(1)</script> sk-secret",
            provider=self.model.provider,
            model_id=self.model.model_id,
        )
        assert parsed["reason_code"] == "malformed_output"
        assert "sk-secret" not in json.dumps(parsed)
        oversized = "x" * 20_000
        parsed = _parse_worker_output(
            json.dumps(
                {
                    "version": 1,
                    "executed_runtime_mode": "live",
                    "provider": self.model.provider,
                    "model": self.model.model_id,
                    "status": "pass",
                    "reason_code": "capability",
                    "latency_ms": 1,
                    "outbound_count": 1,
                }
            )
            + oversized,
            provider=self.model.provider,
            model_id=self.model.model_id,
        )
        assert parsed["reason_code"] == "malformed_output"

        def crash(*, provider: str, model_id: str, env: dict[str, str]) -> dict[str, Any]:
            return {
                "status": "unknown",
                "reason_code": "worker_unavailable",
                "latency_ms": None,
                "outbound_count": None,
                "executed_runtime_mode": "live",
                "provider": provider,
                "model": model_id,
            }

        probe = run_aimodel_probe(
            model=self.model,
            requested_mode="live",
            actor_id=self.user.pk,
            live_sentinel_value="1",
            environ={"PATH": "/usr/bin"},
            spawn=crash,
        )
        assert probe.status == "unknown"
        assert probe.reason_code == "worker_unavailable"
        assert probe.outbound_count is None
        assert probe.summary != ""
        assert "Traceback" not in probe.summary

        with patch("catalog.provider_probes.shutil.which", return_value=None):
            missing = _spawn_worker(
                provider=self.model.provider,
                model_id=self.model.model_id,
                env={"PATH": "/usr/bin"},
            )
        assert missing["reason_code"] == "worker_unavailable"

    def test_f06_live_env_is_restricted_and_does_not_start_a_second_probe(self) -> None:
        captured: dict[str, str] = {}

        def spawn(*, provider: str, model_id: str, env: dict[str, str]) -> dict[str, Any]:
            captured.update(env)
            return {
                "status": "unknown",
                "reason_code": "request_limit",
                "latency_ms": 12,
                "outbound_count": 4,
                "executed_runtime_mode": "live",
                "provider": provider,
                "model": model_id,
            }

        probe = run_aimodel_probe(
            model=self.model,
            requested_mode="live",
            actor_id=self.user.pk,
            live_sentinel_value="1",
            environ={
                "PATH": "/usr/bin",
                "HOME": "/tmp",
                "GROQ_API_KEY": "secret-value",
                "DJANGO_SECRET_KEY": "django-secret",
                "NODE_OPTIONS": "--require evil",
                "LIBRETILES_AI_PLAY_LIVE": "1",
                "NVIDIA_API_KEY": "other-secret",
            },
            spawn=spawn,
        )
        assert probe.reason_code == "request_limit"
        assert probe.outbound_count == 4
        assert captured.get("GROQ_API_KEY") == "secret-value"
        assert "DJANGO_SECRET_KEY" not in captured
        assert "NODE_OPTIONS" not in captured
        assert "LIBRETILES_AI_PLAY_LIVE" not in captured
        assert "NVIDIA_API_KEY" not in captured
        assert LIVE_SENTINEL in captured
        assert CapabilityProbe.objects.count() == 1
        for name in PROVIDER_CREDENTIAL_ENV["nvidia-nim"]:
            assert name not in captured
