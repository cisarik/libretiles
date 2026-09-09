"""Slice-1 infosec hardening: privilege boundaries, simulation identifiers,
replay/simulation output projection, and lease ownership.

Every test uses synthetic users and the in-memory database. No live provider,
no DNS, no sleep-based expiry (lease timestamps are mutated in the DB).
Never print a token or password value.
"""

from __future__ import annotations

import json
import uuid
from datetime import timedelta
from io import StringIO

from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import User
from game import simulations
from game.models import (
    DiagnosticPly,
    DiagnosticRun,
    GameSession,
    Move,
    PlayerSlot,
    PlaygroundSimulation,
)
from game.replay import build_snapshot

_PASSWORD = "testpass123"
LLM_PAIR = {
    "provider": "nvidia-nim",
    "model_id": "nvidia/nemotron-3-super-120b-a12b",
}


def _bearer(token: str) -> dict[str, str]:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


def _expired_access_token(user: User) -> str:
    token = AccessToken.for_user(user)
    token.set_exp(lifetime=timedelta(seconds=-10))
    return str(token)


class _ThrottleResettingTestCase(TestCase):
    """ScopedRateThrottle counters live in the shared LocMem cache; reset per
    test so create/step-heavy suites cannot trip 10/hour caps."""

    def setUp(self) -> None:
        cache.clear()


class AdminPrivilegeBoundaryTests(_ThrottleResettingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="boundary-user", password=_PASSWORD
        )

    def test_nonstaff_patch_cannot_change_privileged_fields(self) -> None:
        original_password = _PASSWORD
        original = User.objects.get(pk=self.user.pk)
        original_date_joined = original.date_joined
        original_id = original.id
        fields = {
            "is_staff": True,
            "is_superuser": True,
            "is_service_account": True,
            "is_active": False,
            "groups": [1],
            "user_permissions": [1],
            "password": "escalated-pass-1",
            "password_changed_at": "2026-01-01T00:00:00Z",
            "id": original_id + 500,
            "date_joined": "2025-01-01T00:00:00Z",
        }
        for field, value in fields.items():
            self.client.force_authenticate(self.user)
            response = self.client.patch(
                "/api/auth/me/", {field: value}, format="json"
            )
            assert response.status_code == 200, field
            self.user.refresh_from_db()
            assert self.user.is_staff is False
            assert self.user.is_superuser is False
            assert self.user.is_service_account is False
            assert self.user.is_active is True
            assert self.user.groups.count() == 0
            assert self.user.user_permissions.count() == 0
            assert self.user.id == original_id
            assert self.user.date_joined == original_date_joined
            assert self.user.password_changed_at is None
            assert self.user.check_password(original_password)
        self.client.force_authenticate(self.user)
        assert self.client.get("/api/admin/games/").status_code == 403

    def test_patch_ignores_privilege_fields_while_updating_email(self) -> None:
        self.client.force_authenticate(self.user)
        response = self.client.patch(
            "/api/auth/me/",
            {"email": "new-boundary@example.test", "is_staff": True},
            format="json",
        )
        assert response.status_code == 200
        self.user.refresh_from_db()
        assert self.user.email == "new-boundary@example.test"
        assert self.user.is_staff is False

    def test_register_ignores_unexposed_user_fields(self) -> None:
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "register-hardened",
                "password": "strong-pass-123",
                "email": "register-hardened@example.test",
                "is_superuser": True,
                "is_service_account": True,
                "is_active": False,
                "groups": [1],
                "user_permissions": [1],
            },
            format="json",
        )
        assert response.status_code == 201
        created = User.objects.get(username="register-hardened")
        assert created.is_superuser is False
        assert created.is_service_account is False
        assert created.is_active is True
        assert created.groups.count() == 0
        assert created.user_permissions.count() == 0


class AdminTokenBoundaryTests(_ThrottleResettingTestCase):
    def setUp(self) -> None:
        super().setUp()
        call_command("seed_models", stdout=StringIO())
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="token-admin", password=_PASSWORD, is_staff=True
        )
        self.user = User.objects.create_user(
            username="token-user", password=_PASSWORD
        )

    def _simulation_game_id(self) -> str:
        self.client.force_authenticate(self.staff)
        response = self.client.post(
            "/api/admin/simulate/",
            {
                "slot0": {"kind": "cpu"},
                "slot1": {"kind": "cpu"},
                "variant_slug": "english",
                "seed": 0,
                "ai_timeout": 30,
                "ai_max_steps": 10,
            },
            format="json",
        )
        assert response.status_code == 201
        self.client.force_authenticate(user=None)
        return response.json()["game_id"]

    def _endpoints(self, game_id: str) -> list[tuple[str, str]]:
        return [
            ("GET", "/api/admin/games/"),
            ("GET", f"/api/admin/games/{game_id}/replay/"),
            ("GET", "/api/admin/analytics/"),
            ("POST", "/api/admin/simulate/"),
            ("GET", f"/api/admin/simulate/{game_id}/"),
            ("POST", f"/api/admin/simulate/{game_id}/step/"),
            ("POST", f"/api/admin/simulate/{game_id}/action/"),
            ("POST", f"/api/admin/simulate/{game_id}/stop/"),
        ]

    def test_admin_routes_reject_invalid_access_token(self) -> None:
        game_id = self._simulation_game_id()
        before = (
            GameSession.objects.count(),
            PlaygroundSimulation.objects.count(),
            Move.objects.count(),
        )
        for method, path in self._endpoints(game_id):
            body = {"expected_move_count": 0} if path.endswith("/step/") else {}
            response = getattr(self.client, method.lower())(
                path, body, format="json", **_bearer("not-a-real-jwt")
            )
            assert response.status_code == 401, (method, path)
        assert (
            GameSession.objects.count(),
            PlaygroundSimulation.objects.count(),
            Move.objects.count(),
        ) == before

    def test_admin_routes_reject_expired_access_token(self) -> None:
        game_id = self._simulation_game_id()
        expired = _expired_access_token(self.staff)
        before = (
            GameSession.objects.count(),
            PlaygroundSimulation.objects.count(),
            Move.objects.count(),
        )
        for method, path in self._endpoints(game_id):
            body = {"expected_move_count": 0} if path.endswith("/step/") else {}
            response = getattr(self.client, method.lower())(
                path, body, format="json", **_bearer(expired)
            )
            assert response.status_code == 401, (method, path)
        assert (
            GameSession.objects.count(),
            PlaygroundSimulation.objects.count(),
            Move.objects.count(),
        ) == before

    def test_demoted_staff_token_loses_admin_access(self) -> None:
        game_id = self._simulation_game_id()
        self.staff.is_staff = False
        self.staff.save(update_fields=["is_staff"])
        token = str(AccessToken.for_user(self.staff))
        assert self.client.get("/api/admin/games/", **_bearer(token)).status_code == 403
        response = self.client.post(
            f"/api/admin/simulate/{game_id}/action/",
            {
                "operation": "release",
                "lease_id": str(uuid.uuid4()),
                "expected_move_count": 0,
            },
            format="json",
            **_bearer(token),
        )
        assert response.status_code == 403

    def test_inactive_staff_token_is_rejected(self) -> None:
        self.staff.is_active = False
        self.staff.save(update_fields=["is_active"])
        token = str(AccessToken.for_user(self.staff))
        assert self.client.get("/api/admin/games/", **_bearer(token)).status_code == 401

    def test_simulation_remaining_endpoints_require_staff(self) -> None:
        game_id = self._simulation_game_id()
        for path in (
            f"/api/admin/simulate/{game_id}/",
            f"/api/admin/simulate/{game_id}/step/",
            f"/api/admin/simulate/{game_id}/action/",
            f"/api/admin/simulate/{game_id}/stop/",
        ):
            assert self.client.get(path).status_code == 401
            assert self.client.post(path, {}, format="json").status_code == 401
        self.client.force_authenticate(self.user)
        assert self.client.get(f"/api/admin/simulate/{game_id}/").status_code == 403
        assert (
            self.client.post(
                f"/api/admin/simulate/{game_id}/step/",
                {"expected_move_count": 0},
                format="json",
            ).status_code
            == 403
        )
        assert (
            self.client.post(
                f"/api/admin/simulate/{game_id}/action/",
                {
                    "operation": "release",
                    "lease_id": str(uuid.uuid4()),
                    "expected_move_count": 0,
                },
                format="json",
            ).status_code
            == 403
        )
        assert (
            self.client.post(
                f"/api/admin/simulate/{game_id}/stop/", {}, format="json"
            ).status_code
            == 403
        )

    def test_session_simulation_mutations_require_csrf(self) -> None:
        csrf_client = APIClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff)
        for path, body in (
            ("/api/admin/simulate/", {}),
            ("/api/admin/simulate/anything/step/", {"expected_move_count": 0}),
            ("/api/admin/simulate/anything/action/", {}),
            ("/api/admin/simulate/anything/stop/", {}),
        ):
            response = csrf_client.post(path, body, format="json")
            assert response.status_code == 403, path


class SimulationLeaseOwnershipTests(_ThrottleResettingTestCase):
    def setUp(self) -> None:
        super().setUp()
        call_command("seed_models", stdout=StringIO())
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="lease-admin", password=_PASSWORD, is_staff=True
        )
        self.other_staff = User.objects.create_user(
            username="lease-admin-two", password=_PASSWORD, is_staff=True
        )

    def _llm_payload(self) -> dict[str, object]:
        return {
            "slot0": {"kind": "llm", **LLM_PAIR},
            "slot1": {"kind": "llm", **LLM_PAIR},
            "variant_slug": "english",
            "seed": 0,
            "ai_timeout": 30,
            "ai_max_steps": 10,
        }

    def _create_and_claim(self) -> tuple[str, str]:
        self.client.force_authenticate(self.staff)
        created = self.client.post(
            "/api/admin/simulate/", self._llm_payload(), format="json"
        ).json()
        game_id = created["game_id"]
        claimed = self.client.post(
            f"/api/admin/simulate/{game_id}/step/",
            {"expected_move_count": 0},
            format="json",
        )
        assert claimed.status_code == 200
        assert claimed.json()["kind"] == "llm"
        return game_id, claimed.json()["lease_id"]

    def test_staff_cannot_use_another_creators_lease(self) -> None:
        game_id, lease_id = self._create_and_claim()
        simulation = PlaygroundSimulation.objects.get(game__public_id=game_id)
        racks_before = [
            list(slot.rack) for slot in simulation.game.slots.order_by("slot")
        ]
        scores_before = [
            slot.score for slot in simulation.game.slots.order_by("slot")
        ]
        self.client.force_authenticate(self.other_staff)
        response = self.client.post(
            f"/api/admin/simulate/{game_id}/action/",
            {
                "operation": "release",
                "lease_id": lease_id,
                "expected_move_count": 0,
            },
            format="json",
        )
        assert response.status_code == 404
        simulation.refresh_from_db()
        assert str(simulation.lease_id) == lease_id
        assert simulation.game.moves.count() == 0
        racks_after = [
            list(slot.rack) for slot in simulation.game.slots.order_by("slot")
        ]
        scores_after = [
            slot.score for slot in simulation.game.slots.order_by("slot")
        ]
        assert racks_after == racks_before
        assert scores_after == scores_before
        # Staff B can still read the state.
        assert (
            self.client.get(f"/api/admin/simulate/{game_id}/").status_code == 200
        )

    def test_simulation_state_never_exposes_lease_material(self) -> None:
        game_id, lease_id = self._create_and_claim()
        self.client.force_authenticate(self.staff)
        response = self.client.get(f"/api/admin/simulate/{game_id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["in_flight"] is True
        assert "lease_id" not in data
        assert "leased_move_count" not in data
        assert "lease_expires_at" not in data
        serialized = json.dumps(data)
        assert lease_id not in serialized
        for slot in data["config"]["slots"]:
            assert "lease_id" not in slot
            assert "leased_move_count" not in slot

    def test_second_client_cannot_claim_an_inflight_turn(self) -> None:
        self.client.force_authenticate(self.staff)
        created = self.client.post(
            "/api/admin/simulate/", self._llm_payload(), format="json"
        ).json()
        game_id = created["game_id"]
        second = APIClient()
        second.force_authenticate(self.staff)
        assert (
            self.client.post(
                f"/api/admin/simulate/{game_id}/step/",
                {"expected_move_count": 0},
                format="json",
            ).status_code
            == 200
        )
        conflict = second.post(
            f"/api/admin/simulate/{game_id}/step/",
            {"expected_move_count": 0},
            format="json",
        )
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "state_conflict"
        simulation = PlaygroundSimulation.objects.get(game__public_id=game_id)
        assert simulation.game.moves.count() == 0

    def test_wrong_lease_is_rejected(self) -> None:
        game_id, lease_id = self._create_and_claim()
        assert lease_id != str(uuid.uuid4())
        response = self.client.post(
            f"/api/admin/simulate/{game_id}/action/",
            {
                "operation": "release",
                "lease_id": str(uuid.uuid4()),
                "expected_move_count": 0,
            },
            format="json",
        )
        assert response.status_code == 409
        assert response.json()["code"] == "state_conflict"
        simulation = PlaygroundSimulation.objects.get(game__public_id=game_id)
        assert str(simulation.lease_id) == lease_id

    def test_expired_lease_is_rejected(self) -> None:
        game_id, lease_id = self._create_and_claim()
        simulation = PlaygroundSimulation.objects.get(game__public_id=game_id)
        simulation.lease_expires_at = timezone.now() - timedelta(seconds=1)
        simulation.save(update_fields=["lease_expires_at"])
        response = self.client.post(
            f"/api/admin/simulate/{game_id}/action/",
            {
                "operation": "release",
                "lease_id": lease_id,
                "expected_move_count": 0,
            },
            format="json",
        )
        assert response.status_code == 409
        assert response.json()["code"] == "state_conflict"

    def test_stale_move_count_is_rejected(self) -> None:
        game_id, lease_id = self._create_and_claim()
        response = self.client.post(
            f"/api/admin/simulate/{game_id}/action/",
            {
                "operation": "release",
                "lease_id": lease_id,
                "expected_move_count": 7,
            },
            format="json",
        )
        assert response.status_code == 409
        assert response.json()["code"] == "state_conflict"

    def test_released_lease_cannot_be_reused(self) -> None:
        game_id, lease_id = self._create_and_claim()
        first = self.client.post(
            f"/api/admin/simulate/{game_id}/action/",
            {
                "operation": "release",
                "lease_id": lease_id,
                "expected_move_count": 0,
            },
            format="json",
        )
        assert first.status_code == 200
        second = self.client.post(
            f"/api/admin/simulate/{game_id}/action/",
            {
                "operation": "release",
                "lease_id": lease_id,
                "expected_move_count": 0,
            },
            format="json",
        )
        assert second.status_code == 409
        assert second.json()["code"] == "state_conflict"

    def test_expired_lease_can_be_reclaimed_by_creator(self) -> None:
        game_id, lease_id = self._create_and_claim()
        simulation = PlaygroundSimulation.objects.get(game__public_id=game_id)
        simulation.lease_expires_at = timezone.now() - timedelta(seconds=1)
        simulation.save(update_fields=["lease_expires_at"])
        response = self.client.post(
            f"/api/admin/simulate/{game_id}/step/",
            {"expected_move_count": 0},
            format="json",
        )
        assert response.status_code == 200
        reclaimed = response.json()
        assert reclaimed["kind"] == "llm"
        assert reclaimed["lease_id"] != lease_id
        assert simulation.game.moves.count() == 0


class SimulationIdentifierHardeningTests(_ThrottleResettingTestCase):
    def setUp(self) -> None:
        super().setUp()
        call_command("seed_models", stdout=StringIO())
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="identifier-admin", password=_PASSWORD, is_staff=True
        )
        self.client.force_authenticate(self.staff)
        self.simulation = simulations.create_playground_simulation(
            created_by_id=self.staff.id,
            slot0={"kind": "cpu"},
            slot1={"kind": "cpu"},
            variant_slug="english",
            seed=0,
            ai_timeout=30,
            ai_max_steps=10,
        )
        self.game_id = str(self.simulation.game.public_id)
        self.plain_game = GameSession.objects.create(
            game_mode="vs_ai",
            variant_slug="english",
            status="active",
            is_diagnostic=False,
        )

    def test_simulation_identifiers_return_controlled_404(self) -> None:
        malformed = "not-a-uuid"
        absent = str(uuid.uuid4())
        for bad_id in (malformed, absent, str(self.plain_game.public_id)):
            assert (
                self.client.get(f"/api/admin/simulate/{bad_id}/").status_code == 404
            )
            response = self.client.post(
                f"/api/admin/simulate/{bad_id}/step/",
                {"expected_move_count": 0},
                format="json",
            )
            assert response.status_code == 404
            body = response.content.decode()
            assert "Traceback" not in body
            response = self.client.post(
                f"/api/admin/simulate/{bad_id}/action/",
                {
                    "operation": "release",
                    "lease_id": str(uuid.uuid4()),
                    "expected_move_count": 0,
                },
                format="json",
            )
            assert response.status_code == 404
            assert "Traceback" not in response.content.decode()
            assert (
                self.client.post(
                    f"/api/admin/simulate/{bad_id}/stop/", {}, format="json"
                ).status_code
                == 404
            )
        simulation = PlaygroundSimulation.objects.get(pk=self.simulation.pk)
        assert simulation.ended_at is None
        assert simulation.game.status == "active"
        assert simulation.game.moves.count() == 0

    def test_create_rejects_nested_runtime_and_target_injection(self) -> None:
        before = (
            GameSession.objects.count(),
            PlaygroundSimulation.objects.count(),
        )
        injections = [
            {"runtime_url": "http://127.0.0.1:9/not-real"},
            {"base_url": "http://127.0.0.1:9/not-real"},
            {"diagnostic_target_id": str(uuid.uuid4())},
            {"api_key": "sk-synthetic"},
            {"slot0": {"kind": "llm", **LLM_PAIR, "target_url": "http://127.0.0.1:9"}},
            {"slot1": {"kind": "cpu", "runtime": {"mode": "fake"}}},
        ]
        for extra in injections:
            payload: dict[str, object] = {
                "slot0": {"kind": "cpu"},
                "slot1": {"kind": "cpu"},
                "variant_slug": "english",
                "seed": 0,
                "ai_timeout": 30,
                "ai_max_steps": 10,
            }
            payload.update(extra)
            response = self.client.post(
                "/api/admin/simulate/", payload, format="json"
            )
            assert response.status_code == 400, extra
        assert (
            GameSession.objects.count(),
            PlaygroundSimulation.objects.count(),
        ) == before

    def test_create_rejects_owner_and_credential_overrides(self) -> None:
        before = (GameSession.objects.count(), PlaygroundSimulation.objects.count())
        for key in ("created_by", "owner_id", "user_id", "api_key", "access_token"):
            payload: dict[str, object] = {
                "slot0": {"kind": "cpu"},
                "slot1": {"kind": "cpu"},
                "variant_slug": "english",
                "seed": 0,
                "ai_timeout": 30,
                "ai_max_steps": 10,
            }
            payload[key] = 1 if key != "api_key" else "sk-synthetic"
            response = self.client.post(
                "/api/admin/simulate/", payload, format="json"
            )
            assert response.status_code == 400, key
        assert (
            GameSession.objects.count(),
            PlaygroundSimulation.objects.count(),
        ) == before

    def test_slot_kind_and_catalog_pair_fail_closed(self) -> None:
        before = (GameSession.objects.count(), PlaygroundSimulation.objects.count())
        bad_payloads = [
            {
                "slot0": {"kind": "llm", "provider": "openrouter", "model_id": "missing/model"},
                "slot1": {"kind": "cpu"},
                "variant_slug": "english",
            },
            {
                "slot0": {"kind": "cpu", "provider": "openrouter", "model_id": "missing/model"},
                "slot1": {"kind": "cpu"},
                "variant_slug": "english",
            },
            {
                "slot0": {"kind": "quantum"},
                "slot1": {"kind": "cpu"},
                "variant_slug": "english",
            },
        ]
        for payload in bad_payloads:
            response = self.client.post(
                "/api/admin/simulate/", payload, format="json"
            )
            assert response.status_code == 400, payload
        assert (
            GameSession.objects.count(),
            PlaygroundSimulation.objects.count(),
        ) == before

    def test_simulation_actions_reject_identity_overrides(self) -> None:
        self.client.force_authenticate(self.staff)
        assert (
            self.client.post(
                f"/api/admin/simulate/{self.game_id}/step/",
                {
                    "expected_move_count": 0,
                    "user_id": self.staff.id,
                    "slot": 0,
                    "runtime": {"mode": "fake"},
                },
                format="json",
            ).status_code
            == 400
        )
        assert (
            self.client.post(
                f"/api/admin/simulate/{self.game_id}/action/",
                {
                    "operation": "release",
                    "lease_id": str(uuid.uuid4()),
                    "expected_move_count": 0,
                    "user_id": self.staff.id,
                    "slot": 0,
                    "runtime": {"mode": "fake"},
                },
                format="json",
            ).status_code
            == 400
        )
        assert self.simulation.game.moves.count() == 0


class SimulationOutputProjectionTests(_ThrottleResettingTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="projection-admin", password=_PASSWORD, is_staff=True
        )
        self.client.force_authenticate(self.staff)
        self.simulation = simulations.create_playground_simulation(
            created_by_id=self.staff.id,
            slot0={"kind": "cpu"},
            slot1={"kind": "cpu"},
            variant_slug="english",
            seed=0,
            ai_timeout=30,
            ai_max_steps=10,
        )
        self.game_id = str(self.simulation.game.public_id)

    def test_simulation_config_output_is_projected(self) -> None:
        self.simulation.config_json = {
            "version": 1,
            "variant_slug": "english",
            "seed": 0,
            "ai_timeout": 30,
            "ai_max_steps": 10,
            "judge_mode": "dictionary",
            "judge_model_id": None,
            "internal_config_secret": "config-leak",
            "lease_id": str(uuid.uuid4()),
            "slots": [
                {
                    "kind": "cpu",
                    "provider": "engine",
                    "model_id": "engine/cpu",
                    "display_name": "CPU Master",
                    "prompt_id": None,
                    "prompt_name": None,
                    "policy": "ranked_witness_safe",
                    "internal_slot_secret": "slot-leak",
                    "lease_id": "slot-lease-leak",
                },
                {
                    "kind": "cpu",
                    "provider": "engine",
                    "model_id": "engine/cpu",
                    "display_name": "CPU Master",
                    "prompt_id": None,
                    "prompt_name": None,
                    "policy": "ranked_witness_safe",
                },
            ],
        }
        self.simulation.save(update_fields=["config_json"])
        response = self.client.get(f"/api/admin/simulate/{self.game_id}/")
        assert response.status_code == 200
        config = response.json()["config"]
        assert set(config) == {
            "version",
            "variant_slug",
            "seed",
            "ai_timeout",
            "ai_max_steps",
            "judge_mode",
            "judge_model_id",
            "slots",
        }
        assert config["version"] == 1
        assert config["seed"] == 0
        assert config["judge_mode"] == "dictionary"
        serialized = json.dumps(response.json())
        assert "config-leak" not in serialized
        assert "slot-leak" not in serialized
        assert "slot-lease-leak" not in serialized
        for slot in config["slots"]:
            assert set(slot) == {
                "kind",
                "provider",
                "model_id",
                "display_name",
                "prompt_id",
                "prompt_name",
                "policy",
            }
            assert slot["policy"] == "ranked_witness_safe"

    def test_admin_list_and_analytics_exclude_internal_payloads(self) -> None:
        self.simulation.config_json["slots"][0]["internal_sentinel"] = "list-leak"
        self.simulation.save(update_fields=["config_json"])
        acting = self.simulation.game.slots.get(
            slot=self.simulation.game.current_turn_slot
        )
        Move.objects.create(
            game=self.simulation.game,
            player_slot=acting,
            seq=1,
            kind="pass",
            ai_metadata={
                "completion_source": "genuine_no_move_pass",
                "provider_requests_used": 0,
                "internal_sentinel": "move-leak",
            },
        )
        listing = self.client.get("/api/admin/games/").json()
        assert "list-leak" not in json.dumps(listing)
        assert "move-leak" not in json.dumps(listing)
        analytics = self.client.get("/api/admin/analytics/").json()
        assert "list-leak" not in json.dumps(analytics)
        assert "move-leak" not in json.dumps(analytics)


class ReplayProjectionTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="replay-project-admin", password=_PASSWORD, is_staff=True
        )
        self.user = User.objects.create_user(
            username="replay-project-user", password=_PASSWORD
        )
        self.session = GameSession.objects.create(
            game_mode="vs_human",
            variant_slug="english",
            status="active",
            is_diagnostic=True,
            current_turn_slot=0,
            bag_seed=7,
            bag_tiles=list("ERISNODXYZABCDEFGHIJKLMNOP"),
        )
        self.slot0 = PlayerSlot.objects.create(
            game=self.session, slot=0, user=self.user, rack=["A", "T"]
        )
        PlayerSlot.objects.create(
            game=self.session, slot=1, user=None, rack=["H", "I"]
        )
        self.session.replay_initial_state = build_snapshot(self.session)
        self.session.save(update_fields=["replay_initial_state"])

    def _diagnostic_ply(self, *, ai_trace: object, failures: object) -> None:
        before = build_snapshot(self.session)
        move = Move.objects.create(
            game=self.session,
            player_slot=self.slot0,
            seq=1,
            kind="pass",
            replay_before=before,
            replay_after=before,
            exchanged_tiles=[],
        )
        run = DiagnosticRun.objects.create(
            assist_mode="assisted",
            instrument="full-game",
            variant_slug="english",
            seat0_model_id="model-a",
            seat1_model_id="model-b",
            session=self.session,
        )
        DiagnosticPly.objects.create(
            run=run,
            move=move,
            ply_index=0,
            seat_index=0,
            model_id="model-a",
            assist_mode="assisted",
            score_authority="engine",
            wall_clock_ms=12,
            replay_before=before,
            replay_after=before,
            ai_trace=ai_trace,
            earlier_attempt_failures=failures,
        )

    def _replay_payload(self) -> dict[str, object]:
        self.client.force_authenticate(self.staff)
        response = self.client.get(
            f"/api/admin/games/{self.session.public_id}/replay/"
        )
        assert response.status_code == 200
        return response.json()["plies"][0]["diagnostic_ply"]

    def test_replay_projects_diagnostic_trace(self) -> None:
        self._diagnostic_ply(
            ai_trace={
                "attempts": 1,
                "internal_secret": "sk-leak-value",
                "nested": {"attempts": 9},
                "path": "/etc/passwd",
                "commands": ["rm", "-rf", "/"],
            },
            failures=None,
        )
        payload = self._replay_payload()
        assert payload["ai_trace"] == {"attempts": 1}
        serialized = json.dumps(payload)
        assert "sk-leak-value" not in serialized
        assert "/etc/passwd" not in serialized
        assert "commands" not in serialized
        assert "rm -rf" not in serialized

    def test_replay_bounds_failure_codes(self) -> None:
        self._diagnostic_ply(
            ai_trace={"attempts": True, "bogus": 1},
            failures=[
                "timeout",
                "secret_failure",
                "rate_limited",
                "provider_unavailable",
                "provider_auth_failed",
                {"nested": "object-leak"},
            ],
        )
        payload = self._replay_payload()
        assert payload["ai_trace"] == {}
        assert payload["earlier_attempt_failures"] == [
            "timeout",
            "redacted",
            "rate_limited",
        ]
        assert "secret_failure" not in json.dumps(payload)
        assert "object-leak" not in json.dumps(payload)

    def test_replay_projects_non_dict_traces_to_null(self) -> None:
        self._diagnostic_ply(
            ai_trace=["attempts", 1],
            failures="not-a-list",
        )
        payload = self._replay_payload()
        assert payload["ai_trace"] is None
        assert payload["earlier_attempt_failures"] is None


class RegularGameStateTests(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="regular-user", password=_PASSWORD
        )
        self.staff = User.objects.create_user(
            username="regular-staff", password=_PASSWORD, is_staff=True
        )

    def _session(self) -> tuple[GameSession, PlayerSlot]:
        session = GameSession.objects.create(
            game_mode="vs_ai",
            variant_slug="english",
            status="active",
            is_diagnostic=False,
            current_turn_slot=0,
            bag_seed=7,
            bag_tiles=list("ERISNODXYZABCDEFGHIJKLMNOP"),
        )
        slot0 = PlayerSlot.objects.create(
            game=session, slot=0, user=self.user, rack=["A", "T", "C", "D", "E", "F", "G"]
        )
        PlayerSlot.objects.create(
            game=session, slot=1, user=None, rack=["H", "I", "J", "K", "L", "M", "N"]
        )
        return session, slot0

    def test_regular_state_excludes_replay_and_opponent_racks(self) -> None:
        session, _ = self._session()
        self.client.force_authenticate(self.user)
        response = self.client.get(f"/api/game/{session.public_id}/")
        assert response.status_code == 200
        data = response.json()
        assert data["my_rack"] == ["A", "T", "C", "D", "E", "F", "G"]
        assert "opponent_rack" not in data
        for slot in data["slots"]:
            assert "rack" not in slot
        serialized = json.dumps(data)
        assert "replay_initial_state" not in serialized
        assert "replay_before" not in serialized
        assert "replay_after" not in serialized
        assert "bag_seed" not in serialized
        assert "bag_tiles" not in serialized

    def test_staff_status_does_not_bypass_regular_game_membership(self) -> None:
        session, _ = self._session()
        self.client.force_authenticate(self.staff)
        assert self.client.get(f"/api/game/{session.public_id}/").status_code == 404