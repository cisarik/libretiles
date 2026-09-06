"""Diagnostic session foundation: two AI seats, acting-slot branch, abort, invisibility."""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import AIModel
from catalog.selection import (
    DEFAULT_FREE_MODEL_ID,
    FREE_RIVAL_IDS,
    FREE_RIVAL_PAIRS,
    NVIDIA_NIM_PROVIDER,
    OPENROUTER_PROVIDER,
)
from game import services
from game.models import DiagnosticRun, GameSession, Move

_PROVIDER_BY_ID = {model_id: provider for provider, model_id in FREE_RIVAL_PAIRS}
_COMMITTED_POSITION_SET = (
    Path(__file__).resolve().parents[1]
    / "assets"
    / "diagnostics"
    / "position_sets"
    / "english-f5ae61b4.json"
)


def _make_rival(*, model_id: str = DEFAULT_FREE_MODEL_ID, **overrides: Any) -> AIModel:
    index = list(FREE_RIVAL_IDS).index(model_id) if model_id in FREE_RIVAL_IDS else 0
    provider = _PROVIDER_BY_ID.get(model_id, OPENROUTER_PROVIDER)
    is_nim = provider == NVIDIA_NIM_PROVIDER
    defaults: dict[str, Any] = {
        "provider": provider,
        "model_id": model_id,
        "display_name": f"Rival {index + 1}",
        "openrouter_available": not is_nim,
        "openrouter_managed": not is_nim,
        "is_active": True,
        "model_type": "language",
        "tags": ["tools"],
        "sort_order": (index + 1) * 10,
    }
    defaults.update(overrides)
    return AIModel.objects.create(**defaults)


def _seed_two_rivals() -> tuple[AIModel, AIModel]:
    first = _make_rival(model_id=FREE_RIVAL_IDS[0])
    second = _make_rival(model_id=FREE_RIVAL_IDS[1])
    return first, second


class DiagnosticSessionTests(TestCase):
    def setUp(self) -> None:
        self.player = User.objects.create_user(username="player1", password="pass1234")
        self.admin = User.objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="adminpass123",
        )
        self.seat0, self.seat1 = _seed_two_rivals()

    def _create_diagnostic(self, **overrides: Any) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "variant_slug": "english",
            "seed": 4242,
            "seat0_model_id": self.seat0.model_id,
            "seat1_model_id": self.seat1.model_id,
            "prompt_id": None,
            "created_by_id": self.admin.id,
            "assist_mode": "authorship",
        }
        kwargs.update(overrides)
        return services.create_diagnostic_game(**kwargs)

    def test_f_a_product_get_ai_context_uses_slot_1_on_human_turn(self) -> None:
        created = services.create_game(user_id=self.player.id, ai_model_id=self.seat0.id)
        game_id = created["game_id"]
        session = GameSession.objects.get(public_id=game_id)
        session.current_turn_slot = 0
        session.save(update_fields=["current_turn_slot"])
        slot0 = session.slots.get(slot=0)
        slot1 = session.slots.get(slot=1)
        slot0.score = 11
        slot1.score = 22
        slot0.save(update_fields=["score"])
        slot1.save(update_fields=["score"])

        context = services.get_ai_context(game_id, self.player.id)
        assert slot0.is_ai is False
        assert slot1.is_ai is True
        assert context["ai_state"]["ai_rack"] == list(slot1.rack)
        assert context["ai_state"]["ai_rack"] != list(slot0.rack)
        assert context["ai_state"]["human_score"] == 11
        assert context["ai_state"]["ai_score"] == 22
        assert context["ai_model_id"] == self.seat0.model_id

    def test_f_a_diagnostic_acting_slot_0_uses_seat_0_rack_and_model(self) -> None:
        created = self._create_diagnostic()
        session = GameSession.objects.get(public_id=created["game_id"])
        slot0 = session.slots.get(slot=0)
        slot1 = session.slots.get(slot=1)
        slot0.rack = ["Z", "Z", "Z", "Z", "Z", "Z", "Z"]
        slot1.rack = ["A", "A", "A", "A", "A", "A", "A"]
        slot0.score = 3
        slot1.score = 9
        slot0.save(update_fields=["rack", "score"])
        slot1.save(update_fields=["score"])
        session.current_turn_slot = 0
        session.save(update_fields=["current_turn_slot"])

        context = services.get_ai_context(created["game_id"], created["service_user_id"])
        assert context["ai_state"]["ai_rack"] == list(slot0.rack)
        assert context["ai_state"]["human_score"] == 9
        assert context["ai_state"]["ai_score"] == 3
        assert context["ai_model_id"] == self.seat0.model_id

    def test_f_b_two_ai_seats_turn_1_persists_acting_slot_1(self) -> None:
        created = self._create_diagnostic()
        session = GameSession.objects.get(public_id=created["game_id"])
        slot1 = session.slots.get(slot=1)
        slot1.rack = ["A", "T", "E", "R", "S", "O", "N"]
        slot1.save(update_fields=["rack"])
        session.current_turn_slot = 1
        session.board_state = services._empty_board_state()
        session.premium_used = []
        session.save(update_fields=["current_turn_slot", "board_state", "premium_used"])

        loaded = services._load_vs_ai_session(
            game_id=created["game_id"],
            user_id=created["service_user_id"],
        )
        assert loaded[2].slot == 1

        result = services.submit_move_for_ai(
            created["game_id"],
            created["service_user_id"],
            [
                {"row": 7, "col": 7, "letter": "A"},
                {"row": 7, "col": 8, "letter": "T"},
            ],
        )
        assert result["ok"] is True
        move = Move.objects.get(game=session)
        assert move.player_slot.slot == 1

    def test_f_c_list_games_for_user_excludes_diagnostic_rows(self) -> None:
        product = services.create_game(user_id=self.player.id, ai_model_id=self.seat0.id)
        diagnostic = self._create_diagnostic()
        listed = services.list_games_for_user(user_id=self.player.id)
        ids = {item["game_id"] for item in listed["items"]}
        assert product["game_id"] in ids
        assert diagnostic["game_id"] not in ids

        service_listed = services.list_games_for_user(user_id=diagnostic["service_user_id"])
        service_ids = {item["game_id"] for item in service_listed["items"]}
        assert diagnostic["game_id"] not in service_ids

    def test_f_d_reserved_user_cannot_login_and_has_unusable_password(self) -> None:
        user = User.objects.get(username="libretiles-diagnostic")
        assert user.has_usable_password() is False
        assert user.is_staff is False
        assert user.is_superuser is False
        assert user.is_active is True
        assert user.groups.count() == 0
        assert user.user_permissions.count() == 0

        client = APIClient()
        resp = client.post(
            "/api/auth/login/",
            {"username": "libretiles-diagnostic", "password": "anything123"},
        )
        assert resp.status_code == 401

    def test_f_e_ordinary_user_jwt_cannot_see_diagnostic_game(self) -> None:
        created = self._create_diagnostic()
        client = APIClient()
        login = client.post(
            "/api/auth/login/",
            {"username": "player1", "password": "pass1234"},
        )
        assert login.status_code == 200
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
        resp = client.get(f"/api/game/{created['game_id']}/")
        assert resp.status_code == 404

    def test_f_f_abort_records_reason_without_creating_moves(self) -> None:
        created = self._create_diagnostic()
        session = GameSession.objects.get(public_id=created["game_id"])
        before = Move.objects.filter(game=session).count()
        result = services.abort_diagnostic_run(
            run_id=uuid.UUID(created["run_id"]),
            reason="model_authorship_failure",
        )
        session.refresh_from_db()
        run = DiagnosticRun.objects.get(pk=created["run_id"])
        assert result["ok"] is True
        assert run.status == "failed"
        assert run.diagnostic_end_reason == "model_authorship_failure"
        assert run.ended_at is not None
        assert session.status == "abandoned"
        assert session.game_end_reason == ""
        assert Move.objects.filter(game=session).count() == before
        assert not Move.objects.filter(game=session, kind="pass").exists()
        assert not Move.objects.filter(game=session, kind="exchange").exists()

    def test_f_g_create_game_still_human_slot_0_and_assigns_bag_seed(self) -> None:
        created = services.create_game(user_id=self.player.id, ai_model_id=self.seat0.id)
        session = GameSession.objects.get(public_id=created["game_id"])
        slot0 = session.slots.get(slot=0)
        slot1 = session.slots.get(slot=1)
        assert slot0.is_ai is False
        assert slot1.is_ai is True
        assert session.is_diagnostic is False
        assert session.bag_seed != 0
        assert session.bag_rng_state is None

    def test_f_h_apply_position_snapshot_sets_turn_and_rejects_product(self) -> None:
        created = self._create_diagnostic()
        session = GameSession.objects.get(public_id=created["game_id"])
        asset = json.loads(_COMMITTED_POSITION_SET.read_text(encoding="utf-8"))
        snapshot = asset["positions"][0]
        assert isinstance(snapshot, dict)

        services.apply_position_snapshot(session, snapshot)
        session.refresh_from_db()
        assert session.current_turn_slot == snapshot["to_move_seat_index"]
        assert session.bag_rng_state == snapshot["bag_rng_state"]
        acting = session.slots.get(slot=snapshot["to_move_seat_index"])
        opponent = session.slots.get(slot=1 - int(snapshot["to_move_seat_index"]))
        assert list(acting.rack) == list(snapshot["rack"])
        assert list(opponent.rack) == list(snapshot["opponent_rack"])

        product = services.create_game(user_id=self.player.id, ai_model_id=self.seat0.id)
        product_session = GameSession.objects.get(public_id=product["game_id"])
        with self.assertRaises(services.DiagnosticSessionError):
            services.apply_position_snapshot(product_session, snapshot)

    def test_f_i_diagnostic_null_turn_fails_closed(self) -> None:
        created = self._create_diagnostic()
        session = GameSession.objects.get(public_id=created["game_id"])
        session.current_turn_slot = None
        session.save(update_fields=["current_turn_slot"])
        with self.assertRaises(services.GameNotFoundError):
            services.get_ai_context(created["game_id"], created["service_user_id"])
        with self.assertRaises(services.GameNotFoundError):
            services.validate_move_for_ai(
                created["game_id"],
                created["service_user_id"],
                [{"row": 7, "col": 7, "letter": "A"}],
                rack_owner="ai",
            )

    def test_f_j_register_reserved_username_is_rejected(self) -> None:
        client = APIClient()
        resp = client.post(
            "/api/auth/register/",
            {
                "username": "libretiles-diagnostic",
                "email": "dup@example.com",
                "password": "testpass123",
            },
        )
        assert resp.status_code == 400

    def test_f_k_second_inflight_diagnostic_run_raises_integrity_error(self) -> None:
        self._create_diagnostic()
        with self.assertRaises(IntegrityError):
            self._create_diagnostic(seed=4243)

        running = DiagnosticRun.objects.get(status="queued")
        running.status = "running"
        running.save(update_fields=["status"])
        with self.assertRaises(IntegrityError):
            DiagnosticRun.objects.create(
                status="queued",
                assist_mode="assisted",
                variant_slug="english",
                seat0_model_id=self.seat0.model_id,
                seat1_model_id=self.seat1.model_id,
                session=GameSession.objects.create(
                    game_mode="vs_ai",
                    is_diagnostic=True,
                ),
                created_by=self.admin,
            )

    def test_unknown_model_writes_no_row(self) -> None:
        before_sessions = GameSession.objects.count()
        before_runs = DiagnosticRun.objects.count()
        with self.assertRaises(services.DiagnosticSessionError):
            self._create_diagnostic(seat0_model_id="not-a-real-model")
        assert GameSession.objects.count() == before_sessions
        assert DiagnosticRun.objects.count() == before_runs

    def test_create_return_has_no_credential_material(self) -> None:
        created = self._create_diagnostic()
        assert set(created) == {
            "game_id",
            "run_id",
            "current_turn_slot",
            "service_user_id",
        }
        blob = json.dumps(created)
        assert "jwt" not in blob.lower()
        assert "token" not in blob.lower()
        assert "password" not in blob.lower()

    def test_build_ws_ticket_refuses_diagnostic(self) -> None:
        created = self._create_diagnostic()
        with self.assertRaises(services.GameNotFoundError):
            services.build_ws_ticket(
                game_id=created["game_id"],
                user_id=created["service_user_id"],
            )

    def test_admin_dashboard_excludes_diagnostic_from_named_cards(self) -> None:
        services.create_game(user_id=self.player.id, ai_model_id=self.seat0.id)
        self._create_diagnostic()
        client = APIClient()
        client.force_login(self.admin)
        resp = client.get(reverse("admin:game_gamesession_dashboard"))
        assert resp.status_code == 200
        cards = {row["label"]: row["value"] for row in resp.context["summary_cards"]}
        assert cards["Games"] == 1
        assert cards["Active games"] == 1

    def test_admin_changelist_still_lists_diagnostic_games(self) -> None:
        created = self._create_diagnostic()
        session = GameSession.objects.get(public_id=created["game_id"])
        client = APIClient()
        client.force_login(self.admin)
        resp = client.get(reverse("admin:game_gamesession_changelist"))
        assert resp.status_code == 200
        assert session.public_id.hex[:8] in resp.content.decode()

    def test_ensure_diagnostic_service_user_is_idempotent(self) -> None:
        first = services.ensure_diagnostic_service_user()
        second = services.ensure_diagnostic_service_user()
        assert first.id == second.id
        assert User.objects.filter(username="libretiles-diagnostic").count() == 1
        assert first.has_usable_password() is False
