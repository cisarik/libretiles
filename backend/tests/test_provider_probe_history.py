from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone as django_timezone

from accounts.models import User
from catalog.models import AIModel, CapabilityProbe, CatalogAdminControl
from catalog.provider_probes import LIVE_SENTINEL, SIMULATED_SUMMARY, run_aimodel_probe
from catalog.selection import DIRECT_FREE_RIVAL_PAIRS, FREE_RIVAL_PAIRS


def _make_model(**overrides: Any) -> AIModel:
    defaults: dict[str, Any] = {
        "provider": DIRECT_FREE_RIVAL_PAIRS[0][0],
        "model_id": DIRECT_FREE_RIVAL_PAIRS[0][1],
        "display_name": "Groq",
        "is_active": True,
        "model_type": "language",
        "tags": ["tools"],
        "sort_order": 1,
    }
    defaults.update(overrides)
    model, _ = AIModel.objects.get_or_create(
        model_id=defaults["model_id"], defaults=defaults
    )
    for key, value in defaults.items():
        setattr(model, key, value)
    model.save()
    return model


def _staff(*, perms: list[str]) -> User:
    user = User.objects.create_user(
        username=f"staff-{User.objects.count()}",
        password="x",
        is_staff=True,
    )
    permission_set = Permission.objects.filter(
        content_type__app_label="catalog",
        codename__in=perms,
    )
    user.user_permissions.add(*permission_set)
    return user


class ProviderProbeHistoryTests(TestCase):
    def setUp(self) -> None:
        self.model = _make_model()
        CatalogAdminControl.objects.get_or_create(
            pk=1, defaults={"revision": 0, "ordering_reviewed": False}
        )
        self.user = _staff(perms=["change_aimodel", "view_aimodel", "probe_aimodel"])
        self.client = Client()
        self.client.force_login(self.user)
        self.probe_url = reverse("admin:catalog_aimodel_probe", args=[self.model.pk])

    def test_f01_authorized_fake_post_persists_one_simulated_record(self) -> None:
        with (
            patch("catalog.provider_probes._spawn_worker") as spawn,
            patch("catalog.provider_probes._live_worker_env") as env_fn,
        ):
            response = self.client.post(self.probe_url, {"mode": "fake"})
        assert response.status_code in {200, 302}
        spawn.assert_not_called()
        env_fn.assert_not_called()
        probes = list(CapabilityProbe.objects.filter(ai_model=self.model))
        assert len(probes) == 1
        probe = probes[0]
        assert probe.requested_by_id == self.user.pk
        assert probe.provider_snapshot == self.model.provider
        assert probe.model_id_snapshot == self.model.model_id
        assert probe.executed_runtime_mode == "fake"
        assert probe.status == "pass"
        assert probe.outbound_count == 0
        assert probe.latency_ms == 0
        assert probe.reason_code == "simulated"
        assert probe.summary == SIMULATED_SUMMARY
        assert probe.completed_at is not None

    def test_f02_default_stays_fake_when_live_sentinel_is_set(self) -> None:
        with patch.dict("os.environ", {LIVE_SENTINEL: "1", "GROQ_API_KEY": "secret"}):
            with patch("catalog.provider_probes._spawn_worker") as spawn:
                response = self.client.post(self.probe_url, {})
        spawn.assert_not_called()
        assert response.status_code == 302
        probe = CapabilityProbe.objects.get()
        assert probe.executed_runtime_mode == "fake"
        assert probe.reason_code == "simulated"

    def test_f02_explicit_live_without_gate_creates_no_record(self) -> None:
        with patch.dict("os.environ", {LIVE_SENTINEL: "0"}):
            with patch("catalog.provider_probes._spawn_worker") as spawn:
                response = self.client.post(self.probe_url, {"mode": "live"})
        spawn.assert_not_called()
        assert response.status_code == 409
        assert CapabilityProbe.objects.count() == 0

    def test_f07_competing_requests_share_one_admission_slot(self) -> None:
        first = run_aimodel_probe(
            model=self.model,
            requested_mode="fake",
            actor_id=self.user.pk,
            live_sentinel_value=None,
        )
        assert first.pk
        with self.assertRaises(Exception):
            run_aimodel_probe(
                model=self.model,
                requested_mode="fake",
                actor_id=self.user.pk,
                live_sentinel_value=None,
            )
        assert CapabilityProbe.objects.count() == 1
        control = CatalogAdminControl.objects.get(pk=1)
        control.probe_not_before_at = django_timezone.now() - timedelta(seconds=1)
        control.save(update_fields=["probe_not_before_at"])
        second = run_aimodel_probe(
            model=self.model,
            requested_mode="fake",
            actor_id=self.user.pk,
            live_sentinel_value=None,
        )
        assert CapabilityProbe.objects.count() == 2
        assert second.pk != first.pk

    def test_f14_hostile_text_is_escaped_in_changeform_and_history(self) -> None:
        hostile = '<script>alert("xss")</script>'
        self.model.display_name = hostile
        self.model.provider = "groq"
        self.model.save(update_fields=["display_name"])
        CapabilityProbe.objects.create(
            ai_model=self.model,
            requested_by=self.user,
            probed_at=django_timezone.now(),
            completed_at=django_timezone.now(),
            provider_snapshot=hostile[:50],
            model_id_snapshot=self.model.model_id,
            status="unknown",
            latency_ms=0,
            outbound_count=0,
            executed_runtime_mode="fake",
            reason_code="unknown",
            summary=hostile,
        )
        change = self.client.get(
            reverse("admin:catalog_aimodel_change", args=[self.model.pk])
        )
        body = change.content.decode()
        assert hostile not in body
        assert "alert(" not in body or "&lt;script&gt;" in body
        assert "&lt;script&gt;" in body
        history = self.client.get(reverse("admin:catalog_capabilityprobe_changelist"))
        # view-only history requires view_capabilityprobe; superuser-style staff may 403
        viewer = _staff(perms=["view_capabilityprobe", "view_aimodel"])
        view_client = Client()
        view_client.force_login(viewer)
        history = view_client.get(reverse("admin:catalog_capabilityprobe_changelist"))
        assert history.status_code == 200
        history_body = history.content.decode()
        assert "&lt;script&gt;" in history_body
        assert "<script>alert" not in history_body
        templates = Path(__file__).resolve().parents[1] / "catalog" / "templates"
        for path in templates.rglob("*.html"):
            text = path.read_text(encoding="utf-8")
            assert "|safe" not in text
            assert "autoescape off" not in text
        admin_source = (
            Path(__file__).resolve().parents[1] / "catalog" / "admin.py"
        ).read_text(encoding="utf-8")
        assert "mark_safe" not in admin_source

    def test_f18_retention_keeps_newest_100_and_history_is_read_only(self) -> None:
        now = django_timezone.now()
        for index in range(101):
            CapabilityProbe.objects.create(
                ai_model=self.model,
                requested_by=self.user,
                probed_at=now + timedelta(seconds=index),
                completed_at=now + timedelta(seconds=index),
                provider_snapshot=self.model.provider,
                model_id_snapshot=self.model.model_id,
                status="pass",
                latency_ms=0,
                outbound_count=0,
                executed_runtime_mode="fake",
                reason_code="simulated",
                summary=SIMULATED_SUMMARY,
            )
        run_aimodel_probe(
            model=self.model,
            requested_mode="fake",
            actor_id=self.user.pk,
            live_sentinel_value=None,
        )
        assert CapabilityProbe.objects.filter(ai_model=self.model).count() == 100
        newest = list(
            CapabilityProbe.objects.filter(ai_model=self.model).order_by(
                "-probed_at", "-id"
            )[:10]
        )
        assert len(newest) == 10
        add = self.client.get(reverse("admin:catalog_capabilityprobe_add"))
        assert add.status_code == 403
        sample = CapabilityProbe.objects.order_by("-id").first()
        assert sample is not None
        delete = self.client.post(
            reverse("admin:catalog_capabilityprobe_delete", args=[sample.pk])
        )
        assert delete.status_code == 403
        assert CapabilityProbe.objects.filter(pk=sample.pk).exists()

    def test_f19_probe_path_has_no_diagnostic_target_fk(self) -> None:
        field_names = {field.name for field in CapabilityProbe._meta.fields}
        assert "diagnostic_target" not in field_names
        with patch("catalog.provider_probes._spawn_worker") as spawn:
            self.client.post(
                self.probe_url,
                {"mode": "fake", "diagnostic_target_id": "abc", "base_url": "https://evil"},
            )
        spawn.assert_not_called()
        probe = CapabilityProbe.objects.get()
        assert probe.ai_model_id == self.model.pk


class SeededCatalogOrderBaseline(TestCase):
    def test_unreviewed_order_matches_bootstrap_pairs(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        from catalog.selection import get_selectable_models

        call_command("seed_models", stdout=StringIO())
        assert [
            (row.provider, row.model_id) for row in get_selectable_models()
        ] == list(FREE_RIVAL_PAIRS)
