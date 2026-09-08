from __future__ import annotations

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User


class AdminSimulationAPITests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="simulation-admin", password="pass1234", is_staff=True
        )
        self.other_staff = User.objects.create_user(
            username="simulation-admin-two", password="pass1234", is_staff=True
        )
        self.user = User.objects.create_user(username="simulation-user", password="pass1234")

    def payload(self) -> dict[str, object]:
        return {
            "slot0": {"kind": "cpu"},
            "slot1": {"kind": "cpu"},
            "variant_slug": "english",
            "seed": 0,
            "ai_timeout": 30,
            "ai_max_steps": 10,
        }

    def test_create_requires_staff_and_returns_complete_initial_state(self) -> None:
        assert self.client.post("/api/admin/simulate/", self.payload(), format="json").status_code == 401
        self.client.force_authenticate(self.user)
        assert self.client.post("/api/admin/simulate/", self.payload(), format="json").status_code == 403
        self.client.force_authenticate(self.staff)
        response = self.client.post("/api/admin/simulate/", self.payload(), format="json")
        assert response.status_code == 201
        data = response.json()
        assert data["simulation_schema_version"] == 1
        assert len(data["board"]) == 15
        assert [len(rack) for rack in data["racks"]] == [7, 7]
        assert data["config"]["seed"] == 0
        assert response["Cache-Control"] == "private, no-store"

    def test_strict_payload_and_conflict_return_no_partial_second_game(self) -> None:
        self.client.force_authenticate(self.staff)
        bad = {**self.payload(), "runtime_url": "https://example.test"}
        assert self.client.post("/api/admin/simulate/", bad, format="json").status_code == 400
        first = self.client.post("/api/admin/simulate/", self.payload(), format="json")
        second = self.client.post("/api/admin/simulate/", self.payload(), format="json")
        assert first.status_code == 201
        assert second.status_code == 409
        assert second.json()["game_id"] == first.json()["game_id"]

    def test_any_staff_can_read_but_only_creator_can_mutate(self) -> None:
        self.client.force_authenticate(self.staff)
        created = self.client.post("/api/admin/simulate/", self.payload(), format="json").json()
        game_id = created["game_id"]
        self.client.force_authenticate(self.other_staff)
        assert self.client.get(f"/api/admin/simulate/{game_id}/").status_code == 200
        assert self.client.post(
            f"/api/admin/simulate/{game_id}/step/",
            {"expected_move_count": 0},
            format="json",
        ).status_code == 404
        assert self.client.post(
            f"/api/admin/simulate/{game_id}/stop/", {}, format="json"
        ).status_code == 404

    def test_stop_returns_replay_transition_state(self) -> None:
        self.client.force_authenticate(self.staff)
        created = self.client.post("/api/admin/simulate/", self.payload(), format="json").json()
        response = self.client.post(
            f"/api/admin/simulate/{created['game_id']}/stop/", {}, format="json"
        )
        assert response.status_code == 200
        assert response.json()["game_end_reason"] == "simulation_stopped"
        assert response.json()["replay_url"].endswith(created["game_id"])
