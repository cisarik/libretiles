"""S7 diagnostic targets: schema, SSRF URL policy, save-time DNS, freeze, audit.

FAKE MODE ONLY: zero provider calls, no real metadata endpoints, no live DNS.
Every network touch is a mock. The URL/IP policy vectors are shared with the
TypeScript side through tests/fixtures/diagnostic_ssrf_cases.json.
"""

from __future__ import annotations

import json
import re
import uuid as uuid_module
from pathlib import Path
from typing import Any
from unittest import mock

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from game import diagnostic_targets as dt
from game import services
from game.models import DiagnosticAllowedHost, DiagnosticTarget, GameSession, PlayerSlot

FIXTURE = json.loads(
    (Path(__file__).resolve().parent / "fixtures" / "diagnostic_ssrf_cases.json").read_text(
        encoding="utf-8"
    )
)
SEED_HOSTS = FIXTURE["allowed_hostnames_seed"]
ALLOWED_HOSTNAME = SEED_HOSTS[0]
PUBLIC_ADDRESS = FIXTURE["ip_policy_accepts"][0]


def _patch_dns(addresses: list[str] | Exception) -> mock.MagicMock:
    if isinstance(addresses, Exception):
        resolver = mock.MagicMock(side_effect=addresses)
    else:
        resolver = mock.MagicMock(return_value=list(addresses))
    return mock.patch.object(dt, "resolve_host_addresses", resolver)


def _make_host(*, hostname: str = ALLOWED_HOSTNAME, **overrides: Any) -> DiagnosticAllowedHost:
    """Idempotent: the migration already seeds the eight shipped hostnames."""
    defaults: dict[str, Any] = {"is_active": True}
    defaults.update(overrides)
    host, _ = DiagnosticAllowedHost.objects.get_or_create(hostname=hostname, defaults=defaults)
    if overrides:
        for field, value in defaults.items():
            setattr(host, field, value)
        host.save()
    return host


def _make_target(*, base_url: str | None = None, host: DiagnosticAllowedHost | None = None, **overrides: Any) -> DiagnosticTarget:
    """Create a target row with DNS validation mocked to a public address."""
    resolved_host = host or _make_host()
    defaults: dict[str, Any] = {
        "name": "Rival target",
        "base_url": base_url or f"https://{resolved_host.hostname}/api/v1",
        "allowed_host": resolved_host,
        "model_id": "vendor/target-model",
        "credential_env_name": "OPENROUTER_API_KEY",
        "is_active": True,
    }
    defaults.update(overrides)
    with _patch_dns([PUBLIC_ADDRESS]):
        return DiagnosticTarget.objects.create(**defaults)


class DiagnosticTargetsF01SchemaTests(TestCase):
    """S7-F01: target/host schema absent on the baseline; cannot save a target."""

    def test_f01_allowed_host_table_exists_and_seeds_eight_hosts(self) -> None:
        for hostname in SEED_HOSTS:
            host = DiagnosticAllowedHost.objects.filter(hostname=hostname).first()
            assert host is not None, f"seed host missing: {hostname}"
            assert host.is_active is True
        assert DiagnosticAllowedHost.objects.count() == len(SEED_HOSTS)

    def test_f01_target_schema_and_slot_fk_exist(self) -> None:
        with _patch_dns([PUBLIC_ADDRESS]):
            target = DiagnosticTarget.objects.create(
                name="Probe target",
                base_url=f"https://{ALLOWED_HOSTNAME}/api/v1",
                allowed_host=DiagnosticAllowedHost.objects.get(hostname=ALLOWED_HOSTNAME),
                model_id="vendor/target-model",
                credential_env_name="OPENROUTER_API_KEY",
            )
        assert target.pk is not None
        slot = PlayerSlot.objects.create(game=GameSession.objects.create(), slot=0)
        slot.diagnostic_target = target
        slot.save(update_fields=["diagnostic_target"])
        slot.refresh_from_db()
        assert slot.diagnostic_target is not None

    def test_f01_slot_rejects_model_and_target_together(self) -> None:
        from catalog.models import AIModel
        from catalog.selection import DEFAULT_FREE_MODEL_ID, FREE_RIVAL_PAIRS

        provider_by_id = {model_id: provider for provider, model_id in FREE_RIVAL_PAIRS}
        provider = provider_by_id[DEFAULT_FREE_MODEL_ID]
        model = AIModel.objects.create(
            provider=provider,
            model_id=DEFAULT_FREE_MODEL_ID,
            display_name="Rival",
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        target = _make_target()
        slot = PlayerSlot.objects.create(game=GameSession.objects.create(), slot=0)
        slot.ai_model = model
        slot.diagnostic_target = target
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                slot.save()


class DiagnosticTargetURLPolicyTests(TestCase):
    """S7-F02 (save side): the one URL policy, exercised from the fixture."""

    def test_f02_shared_fixture_rejects_every_vector(self) -> None:
        for case in FIXTURE["url_policy_rejects"]:
            with self.subTest(reason=case["reason"], input=case["input"]):
                with self.assertRaises(dt.DiagnosticTargetError):
                    dt.parse_target_base_url(case["input"])

    def test_f02_accepts_canonical_https_base(self) -> None:
        parsed = dt.parse_target_base_url(f"https://{ALLOWED_HOSTNAME}/api/v1")
        assert parsed.hostname == ALLOWED_HOSTNAME
        assert parsed.canonical_base == f"https://{ALLOWED_HOSTNAME}/api/v1"

    def test_f02_default_443_port_is_implicit_and_stripped(self) -> None:
        parsed = dt.parse_target_base_url(f"https://{ALLOWED_HOSTNAME}:443/api/v1")
        assert parsed.canonical_base == f"https://{ALLOWED_HOSTNAME}/api/v1"

    def test_f02_model_id_is_metadata_never_a_url(self) -> None:
        target = _make_target()
        target.model_id = "https://openrouter.ai/api/v1#not-a-base"
        with _patch_dns([PUBLIC_ADDRESS]):
            target.save()
        target.refresh_from_db()
        assert target.model_id == "https://openrouter.ai/api/v1#not-a-base"
        parsed = dt.parse_target_base_url(target.base_url)
        assert parsed.hostname == ALLOWED_HOSTNAME
        assert parsed.canonical_base == f"https://{ALLOWED_HOSTNAME}/api/v1"

    def test_f02_host_must_equal_the_allowed_host_row_exactly(self) -> None:
        _make_host()
        other = _make_host(hostname="sub.openrouter.ai")
        with self.assertRaises(dt.DiagnosticTargetError):
            dt.validate_base_url_against_host(
                f"https://{ALLOWED_HOSTNAME}/api/v1", other.hostname
            )
        with self.assertRaises(dt.DiagnosticTargetError):
            dt.validate_base_url_against_host(
                f"https://{ALLOWED_HOSTNAME}.evil.invalid/api/v1", ALLOWED_HOSTNAME
            )


class DiagnosticTargetIPPolicyTests(TestCase):
    """S7-F02/F07: the shared IP policy refuses the whole name on any hit."""

    def test_f02_shared_fixture_rejects_ip_vectors(self) -> None:
        for address in FIXTURE["ip_policy_rejects"]:
            with self.subTest(address=address):
                assert dt.address_allowed(address) is False

    def test_f02_shared_fixture_accepts_public_unicast(self) -> None:
        for address in FIXTURE["ip_policy_accepts"]:
            with self.subTest(address=address):
                assert dt.address_allowed(address) is True

    def test_f02_any_disallowed_address_refuses_the_name(self) -> None:
        with self.assertRaises(dt.DiagnosticTargetError):
            dt.validate_target_dns_addresses(
                ALLOWED_HOSTNAME, resolved=["8.8.8.8", "10.0.0.1"]
            )
        with self.assertRaises(dt.DiagnosticTargetError):
            dt.validate_target_dns_addresses(ALLOWED_HOSTNAME, resolved=["::ffff:10.0.0.1"])

    def test_f02_empty_resolution_refuses(self) -> None:
        with self.assertRaises(dt.DiagnosticTargetError):
            dt.validate_target_dns_addresses(ALLOWED_HOSTNAME, resolved=[])

    def test_f02_dns_timeout_refuses(self) -> None:
        with _patch_dns(dt.DiagnosticTargetError("dns_timeout", "resolution timed out")):
            with self.assertRaises(dt.DiagnosticTargetError):
                dt.validate_target_dns_addresses(ALLOWED_HOSTNAME)

    def test_f02_resolved_ips_are_never_persisted(self) -> None:
        target = _make_target()
        blob = json.dumps(
            {field.name: str(getattr(target, field.name)) for field in DiagnosticTarget._meta.fields}
        )
        assert PUBLIC_ADDRESS not in blob


class DiagnosticTargetSaveValidationTests(TestCase):
    """S7-F02/F11: save() validates connection settings; deactivation needs no DNS."""

    def test_f02_save_refuses_loopback_base_url_and_writes_nothing(self) -> None:
        before = DiagnosticTarget.objects.count()
        with _patch_dns(["127.0.0.1"]):
            with self.assertRaises(dt.DiagnosticTargetError):
                DiagnosticTarget.objects.create(
                    name="Loopback",
                    base_url="https://metadata.invalid/api/v1",
                    allowed_host=_make_host(hostname="metadata.invalid"),
                    model_id="vendor/m",
                    credential_env_name="OPENROUTER_API_KEY",
                )
        assert DiagnosticTarget.objects.count() == before

    def test_f02_save_refuses_when_dns_yields_no_allowed_address(self) -> None:
        before = DiagnosticTarget.objects.count()
        with _patch_dns(dt.DiagnosticTargetError("dns_refused", "no allowed address")):
            with self.assertRaises(dt.DiagnosticTargetError):
                DiagnosticTarget.objects.create(
                    name="Refused",
                    base_url=f"https://{ALLOWED_HOSTNAME}/api/v1",
                    allowed_host=DiagnosticAllowedHost.objects.get(hostname=ALLOWED_HOSTNAME),
                    model_id="vendor/m",
                    credential_env_name="OPENROUTER_API_KEY",
                )
        assert DiagnosticTarget.objects.count() == before

    def test_f11_reactivation_resolves_dns_again(self) -> None:
        target = _make_target()
        target.is_active = False
        target.save(update_fields=["is_active", "updated_at"])
        with _patch_dns(["127.0.0.1"]) as resolver:
            target.is_active = True
            with self.assertRaises(dt.DiagnosticTargetError):
                target.save()
            resolver.assert_called_once()
        target.refresh_from_db()
        assert target.is_active is False

    def test_f11_deactivation_and_rename_need_no_dns(self) -> None:
        target = _make_target()
        target.is_active = False
        with _patch_dns(AssertionError("deactivation must not resolve DNS")) as resolver:
            target.save()
            target.name = "Renamed target"
            target.save()
            resolver.assert_not_called()
        target.refresh_from_db()
        assert target.is_active is False
        assert target.name == "Renamed target"

    def test_f11_name_and_activation_stay_editable_when_frozen(self) -> None:
        target = _make_target()
        admin = services.ensure_diagnostic_service_user()
        created = services.create_diagnostic_game(
            variant_slug="english",
            seed=1,
            seat0_model_id="vendor/target-model",
            seat1_model_id="vendor/target-model",
            prompt_id=None,
            created_by_id=admin.id,
            assist_mode="assisted",
            seat0_target_id=str(target.id),
            seat1_target_id=str(target.id),
        )
        assert created["run_id"]
        target.refresh_from_db()
        target.name = "Frozen but renamed"
        target.save()
        target.is_active = False
        target.save()
        target.refresh_from_db()
        assert target.name == "Frozen but renamed"
        assert target.is_active is False

    def test_f11_frozen_connection_settings_refuse_edits(self) -> None:
        target = _make_target()
        admin = services.ensure_diagnostic_service_user()
        services.create_diagnostic_game(
            variant_slug="english",
            seed=1,
            seat0_model_id="vendor/target-model",
            seat1_model_id="vendor/target-model",
            prompt_id=None,
            created_by_id=admin.id,
            assist_mode="assisted",
            seat0_target_id=str(target.id),
            seat1_target_id=str(target.id),
        )
        for field, value in (
            ("base_url", f"https://{ALLOWED_HOSTNAME}/api/v2"),
            ("model_id", "vendor/other-model"),
            ("credential_env_name", "NVIDIA_API_KEY"),
        ):
            fresh = DiagnosticTarget.objects.get(pk=target.pk)
            setattr(fresh, field, value)
            with self.assertRaises(dt.DiagnosticTargetError):
                fresh.save()
        fresh = DiagnosticTarget.objects.get(pk=target.pk)
        fresh.allowed_host = _make_host(hostname="api.groq.com")
        with self.assertRaises(dt.DiagnosticTargetError):
            fresh.save()

    def test_f11_reference_created_during_dns_freezes_the_save(self) -> None:
        target = _make_target()
        admin = services.ensure_diagnostic_service_user()

        def _launch_during_dns(hostname: str, **kwargs: Any) -> list[str]:
            services.create_diagnostic_game(
                variant_slug="english",
                seed=1,
                seat0_model_id="vendor/target-model",
                seat1_model_id="vendor/target-model",
                prompt_id=None,
                created_by_id=admin.id,
                assist_mode="assisted",
                seat0_target_id=str(target.id),
                seat1_target_id=str(target.id),
            )
            return [PUBLIC_ADDRESS]

        fresh = DiagnosticTarget.objects.get(pk=target.pk)
        fresh.model_id = "vendor/other-model"
        with mock.patch.object(
            dt, "resolve_host_addresses", mock.MagicMock(side_effect=_launch_during_dns)
        ):
            with self.assertRaises(dt.DiagnosticTargetError):
                fresh.save()
        fresh.refresh_from_db()
        assert fresh.model_id == "vendor/target-model"

    def test_f01_allowed_host_hostname_is_immutable(self) -> None:
        host = _make_host()
        host.hostname = "api.groq.com"
        with self.assertRaises(ValidationError):
            host.save()

    def test_f01_allowed_host_activate_deactivate(self) -> None:
        host = _make_host()
        host.is_active = False
        host.save()
        host.refresh_from_db()
        assert host.is_active is False


class DiagnosticTargetCredentialEnvTests(TestCase):
    """S7-F04: closed credential env-name set, parity with the TS module."""

    def test_f04_django_set_matches_typescript_set(self) -> None:
        ts_source = (
            Path(__file__).resolve().parents[2]
            / "frontend"
            / "src"
            / "lib"
            / "provider-logging.ts"
        ).read_text(encoding="utf-8")
        match = re.search(
            r"export const CREDENTIAL_ENV_NAMES = \[(.*?)\] as const", ts_source, re.DOTALL
        )
        assert match is not None, "CREDENTIAL_ENV_NAMES export not found"
        ts_names = re.findall(r'"([A-Z0-9_]+)"', match.group(1))
        assert tuple(ts_names) == dt.CREDENTIAL_ENV_NAMES

    def test_f04_django_secret_key_is_not_a_choice(self) -> None:
        assert "DJANGO_SECRET_KEY" not in dt.CREDENTIAL_ENV_NAMES
        for forbidden in ("DJANGO_SECRET_KEY", "SECRET_KEY", "PASSWORD"):
            with self.subTest(name=forbidden):
                with self.assertRaises(dt.DiagnosticTargetError):
                    dt.validate_credential_env_name(forbidden)

    def test_f04_target_save_rejects_secret_key_env_name(self) -> None:
        host = _make_host()
        with _patch_dns([PUBLIC_ADDRESS]):
            with self.assertRaises(dt.DiagnosticTargetError):
                DiagnosticTarget.objects.create(
                    name="Secret thief",
                    base_url=f"https://{host.hostname}/api/v1",
                    allowed_host=host,
                    model_id="vendor/m",
                    credential_env_name="DJANGO_SECRET_KEY",
                )
        assert (
            DiagnosticTarget.objects.filter(credential_env_name="DJANGO_SECRET_KEY").count()
            == 0
        )

    def test_f04_credential_presence_is_membership_only(self) -> None:
        assert dt.credential_env_present("OPENROUTER_API_KEY", {"OPENROUTER_API_KEY": "x"}) == "yes"
        assert dt.credential_env_present("NVIDIA_API_KEY", {}) == "no"
        assert dt.credential_env_present("OPENROUTER_API_KEY", None) in {"yes", "no", "unknown"}

    def test_f04_parameters_json_accepts_target_uuids_only(self) -> None:
        target_id = str(uuid_module.uuid4())
        services._reject_credential_parameters({"seat0_target_id": target_id})
        for forbidden in (
            "credential_env_name",
            "base_url",
            "env",
            "api_key",
            "DJANGO_SECRET_KEY",
        ):
            with self.subTest(key=forbidden):
                with self.assertRaises(services.DiagnosticSessionError):
                    services._reject_credential_parameters({forbidden: "value"})
