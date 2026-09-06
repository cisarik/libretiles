"""Diagnostic session foundation: two AI seats, acting-slot branch, abort, invisibility."""

from __future__ import annotations

import importlib
import io
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path
from typing import Any

from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured
from django.db import IntegrityError
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

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

    def test_f_l_collision_fails_closed(self) -> None:
        """Reserved username with a usable password must not be adopted.

        Pre-fix finding proof (APMC-S4-IA-F01): ensure_diagnostic_service_user()
        returned quietly with the claimant's password intact.
        """
        User.objects.filter(username=services.DIAGNOSTIC_SERVICE_USERNAME).delete()
        claimant = User.objects.create_user(
            username=services.DIAGNOSTIC_SERVICE_USERNAME,
            password="claimant-pass-123",
        )
        with self.assertRaises(ImproperlyConfigured) as raised:
            services.ensure_diagnostic_service_user()
        claimant.refresh_from_db()
        assert claimant.has_usable_password() is True
        assert claimant.check_password("claimant-pass-123") is True
        assert claimant.is_staff is False
        message = str(raised.exception)
        assert services.DIAGNOSTIC_SERVICE_USERNAME in message
        assert "usable password" in message

    def test_f_m_idempotent_managed_account(self) -> None:
        first = services.ensure_diagnostic_service_user()
        second = services.ensure_diagnostic_service_user()
        assert first.id == second.id
        assert first.has_usable_password() is False
        assert second.has_usable_password() is False
        assert first.is_staff is False
        assert first.is_superuser is False
        assert first.is_active is True
        assert first.groups.count() == 0
        assert first.user_permissions.count() == 0

    def test_f_n_service_bearer_cannot_create_product_game(self) -> None:
        """Pre-fix finding proof (APMC-S4-IA-F02): create returned 201/ok."""
        service = User.objects.get(username=services.DIAGNOSTIC_SERVICE_USERNAME)
        client = APIClient()
        client.force_authenticate(user=service)
        before = GameSession.objects.filter(is_diagnostic=False).count()
        resp = client.post(
            "/api/game/create/",
            {"game_mode": "vs_ai", "ai_model_id": self.seat0.id},
        )
        assert 400 <= resp.status_code < 500
        assert resp.status_code == 400
        assert GameSession.objects.filter(is_diagnostic=False).count() == before
        body = resp.json()
        assert body.get("ok") is False
        assert services.DIAGNOSTIC_SERVICE_USERNAME in str(body)

    def test_f_o_service_bearer_cannot_join_human_matchmaking(self) -> None:
        """Pre-fix finding proof (APMC-S4-IA-F02): queue join succeeded (joined)."""
        service = User.objects.get(username=services.DIAGNOSTIC_SERVICE_USERNAME)
        client = APIClient()
        client.force_authenticate(user=service)
        before = GameSession.objects.filter(game_mode="vs_human").count()
        resp = client.post(
            "/api/game/queue/join/",
            {"variant_slug": "english"},
            format="json",
        )
        assert 400 <= resp.status_code < 500
        assert resp.status_code == 400
        assert GameSession.objects.filter(game_mode="vs_human").count() == before
        body = resp.json()
        assert body.get("ok") is False
        assert body.get("waiting") is not True
        assert body.get("matched") is not True

    def test_f_p_reverse_keeps_claimant_deletes_managed(self) -> None:
        """Pre-fix finding proof (APMC-S4-IA-F03): reverse deleted the claimant."""
        migration = importlib.import_module(
            "game.migrations.0010_diagnostic_service_account"
        )
        unensure = migration.unensure_diagnostic_service_user

        User.objects.filter(username=services.DIAGNOSTIC_SERVICE_USERNAME).delete()
        claimant = User.objects.create_user(
            username=services.DIAGNOSTIC_SERVICE_USERNAME,
            password="claimant-pass-123",
        )
        claimant_id = claimant.id
        unensure(django_apps, None)
        assert User.objects.filter(pk=claimant_id).exists()
        claimant.refresh_from_db()
        assert claimant.has_usable_password() is True
        assert claimant.check_password("claimant-pass-123") is True

        User.objects.filter(username=services.DIAGNOSTIC_SERVICE_USERNAME).delete()
        managed = services.ensure_diagnostic_service_user()
        assert managed.has_usable_password() is False
        managed_id = managed.id
        unensure(django_apps, None)
        assert not User.objects.filter(pk=managed_id).exists()

    def test_f_q_flagged_account_rename_is_rejected(self) -> None:
        """Pre-fix finding proof (APMC-S4-IA-F02 P09): PATCH rename returned 200.

        Captured verbatim before this correction:
        PRE-FIX rename status: 200
        PRE-FIX rename username field: renamed-service
        """
        service = User.objects.get(username=services.DIAGNOSTIC_SERVICE_USERNAME)
        assert service.is_service_account is True
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(service).access_token}"
        )
        resp = client.patch(
            "/api/auth/me/",
            {"username": "renamed-service"},
            format="json",
        )
        assert 400 <= resp.status_code < 500
        service.refresh_from_db()
        assert service.username == services.DIAGNOSTIC_SERVICE_USERNAME
        assert service.is_service_account is True

    def test_f_r_service_jwt_rename_create_queue_chain_fails_at_rename(self) -> None:
        """The exact P03→P09 chain must now fail at the rename step.

        Captured verbatim before this correction:
        PRE-FIX rename status: 200
        PRE-FIX create status: 201
        PRE-FIX queue status: 200
        PRE-FIX queue ok/waiting/matched: True True False
        """
        service = User.objects.get(username=services.DIAGNOSTIC_SERVICE_USERNAME)
        client = APIClient()
        client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(service).access_token}"
        )
        before_product = GameSession.objects.filter(is_diagnostic=False).count()
        before_human = GameSession.objects.filter(game_mode="vs_human").count()

        rename = client.patch(
            "/api/auth/me/",
            {"username": "renamed-service"},
            format="json",
        )
        assert 400 <= rename.status_code < 500
        service.refresh_from_db()
        assert service.username == services.DIAGNOSTIC_SERVICE_USERNAME

        created = client.post(
            "/api/game/create/",
            {"game_mode": "vs_ai", "ai_model_id": self.seat0.id},
        )
        assert created.status_code == 400
        body = created.json()
        assert body.get("ok") is False
        assert GameSession.objects.filter(is_diagnostic=False).count() == before_product

        queue = client.post(
            "/api/game/queue/join/",
            {"variant_slug": "english"},
            format="json",
        )
        assert queue.status_code == 400
        qbody = queue.json()
        assert qbody.get("ok") is False
        assert qbody.get("waiting") is not True
        assert qbody.get("matched") is not True
        assert GameSession.objects.filter(game_mode="vs_human").count() == before_human

    def test_f_s_ensure_restores_cleared_service_account_flag(self) -> None:
        managed = services.ensure_diagnostic_service_user()
        assert managed.is_service_account is True
        managed.is_service_account = False
        managed.save(update_fields=["is_service_account"])
        again = services.ensure_diagnostic_service_user()
        assert again.id == managed.id
        again.refresh_from_db()
        assert again.is_service_account is True

    def test_f_t_ordinary_user_rename_and_participation_unaffected(self) -> None:
        client = APIClient()
        login = client.post(
            "/api/auth/login/",
            {"username": "player1", "password": "pass1234"},
        )
        assert login.status_code == 200
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")
        resp = client.patch(
            "/api/auth/me/",
            {"username": "player1-renamed"},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "player1-renamed"
        created = client.post(
            "/api/game/create/",
            {"game_mode": "vs_ai", "ai_model_id": self.seat0.id},
        )
        assert created.status_code == 201
        queue = client.post(
            "/api/game/queue/join/",
            {"variant_slug": "english"},
            format="json",
        )
        assert queue.status_code == 200
        qbody = queue.json()
        assert qbody.get("ok") is not False

    def test_f_u_fresh_db_applies_flag_before_diagnostic_seed(self) -> None:
        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        accounts_0005 = ("accounts", "0005_service_account_flag")
        game_0010 = ("game", "0010_diagnostic_service_account")
        loader = MigrationLoader(connection)
        assert accounts_0005 in loader.disk_migrations[game_0010].dependencies
        plan = loader.graph.forwards_plan(game_0010)
        assert plan.index(accounts_0005) < plan.index(game_0010)
        seeded = User.objects.get(username=services.DIAGNOSTIC_SERVICE_USERNAME)
        assert seeded.is_service_account is True

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


_BACKEND = Path(__file__).resolve().parents[1]
_PRE_FLAG_COMMIT = "f6c9db913450d56ade4399ec5d2e6a3cd807e347"
_STRANDED_COMMIT = "6049f2895321da33c7594aedd922aef63544e18d"


def _export_migration_tree(tmp_path: Path, commit: str) -> Path:
    """Export tracked Python only: no secrets, dev DB, network, or Git writes."""
    paths = subprocess.check_output(
        ["git", "ls-tree", "-r", "--name-only", commit, "--", "backend"],
        cwd=_BACKEND.parent,
        text=True,
    ).splitlines()
    archive = subprocess.check_output(
        ["git", "archive", commit, "--", *[p for p in paths if p.endswith(".py")]],
        cwd=_BACKEND.parent,
    )
    destination = tmp_path / commit
    destination.mkdir()
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        tree.extractall(destination, filter="data")
    return destination / "backend"


def _migration_process(backend: Path, database: Path, code: str) -> subprocess.CompletedProcess[str]:
    """Run real migrate against an isolated SQLite DB before Django opens it."""
    env = os.environ.copy()
    for name in ("APPIMAGE", "ARGV0", "APPDIR"):
        env.pop(name, None)
    env.update(
        PYTHON_DOTENV_DISABLED="1",
        DJANGO_SECRET_KEY=secrets.token_urlsafe(64),
        DJANGO_SETTINGS_MODULE="config.settings",
        DJANGO_DEBUG="true",
        DB_ENGINE="sqlite3",
    )
    bootstrap = (
        "import sys\n"
        "from django.conf import settings\n"
        "settings.DATABASES['default']['NAME'] = sys.argv[1]\n"
        "import django\n"
        "django.setup()\n"
        "from django.core.management import call_command\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", bootstrap + code, str(database)],
        cwd=backend,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    print(result.stdout, end="")
    print(result.stderr, end="")
    return result


def _assert_managed_flag(database: Path) -> None:
    with sqlite3.connect(database) as db:
        rows = db.execute(
            "SELECT is_service_account, password FROM accounts_user WHERE username = ?",
            (services.DIAGNOSTIC_SERVICE_USERNAME,),
        ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == 1
    assert rows[0][1].startswith("!")
    print("Reserved managed account: is_service_account=True, unusable_password=True")


def test_f_v_existing_applied_0009_one_normal_migrate_rescues(tmp_path: Path) -> None:
    """Reproduce F07 from real historical trees, then upgrade the same database."""
    database = tmp_path / "existing.sqlite3"
    original = _export_migration_tree(tmp_path, _PRE_FLAG_COMMIT)
    before = _migration_process(original, database, "call_command('migrate', no_color=True)\n")
    assert before.returncode == 0, before.stderr
    with sqlite3.connect(database) as db:
        assert db.execute(
            "SELECT 1 FROM django_migrations WHERE app='game' AND name=?",
            ("0009_diagnostic_session_foundation",),
        ).fetchone()
        assert not db.execute(
            "SELECT 1 FROM django_migrations WHERE app='accounts' AND name=?",
            ("0005_service_account_flag",),
        ).fetchone()
        assert "is_service_account" not in {
            row[1] for row in db.execute("PRAGMA table_info(accounts_user)")
        }
        original_id, password = db.execute(
            "SELECT id, password FROM accounts_user WHERE username=?",
            (services.DIAGNOSTIC_SERVICE_USERNAME,),
        ).fetchone()
        assert password.startswith("!")

    stranded = _export_migration_tree(tmp_path, _STRANDED_COMMIT)
    broken = _migration_process(stranded, database, "call_command('migrate', no_color=True)\n")
    assert broken.returncode != 0
    assert (
        "django.db.migrations.exceptions.InconsistentMigrationHistory: "
        "Migration game.0009_diagnostic_session_foundation is applied before its dependency "
        "accounts.0005_service_account_flag on database 'default'."
    ) in broken.stderr

    interrupted_database = tmp_path / "between_0005_and_0010.sqlite3"
    shutil.copyfile(database, interrupted_database)
    rescued = _migration_process(_BACKEND, database, "call_command('migrate', no_color=True)\n")
    assert rescued.returncode == 0, rescued.stderr
    flag_line = "Applying accounts.0005_service_account_flag... OK"
    seed_line = "Applying game.0010_diagnostic_service_account... OK"
    assert flag_line in rescued.stdout
    assert seed_line in rescued.stdout
    assert rescued.stdout.index(flag_line) < rescued.stdout.index(seed_line)
    _assert_managed_flag(database)
    with sqlite3.connect(database) as db:
        assert db.execute(
            "SELECT id FROM accounts_user WHERE username=?",
            (services.DIAGNOSTIC_SERVICE_USERNAME,),
        ).fetchone() == (original_id,)

    # A completed 0005 followed by interruption before 0010 is also resumable.
    column_only = _migration_process(
        _BACKEND, interrupted_database,
        "call_command('migrate', 'accounts', '0005', no_color=True)\n",
    )
    assert column_only.returncode == 0, column_only.stderr
    with sqlite3.connect(interrupted_database) as db:
        assert db.execute(
            "SELECT is_service_account FROM accounts_user WHERE id=?", (original_id,),
        ).fetchone() == (0,)
    resumed = _migration_process(
        _BACKEND, interrupted_database, "call_command('migrate', no_color=True)\n",
    )
    assert resumed.returncode == 0, resumed.stderr
    assert flag_line not in resumed.stdout
    assert seed_line in resumed.stdout
    _assert_managed_flag(interrupted_database)


def test_f_w_fresh_schema_seed_and_schema_only_reverse(tmp_path: Path) -> None:
    zero_database = tmp_path / "from_zero.sqlite3"
    zero = _migration_process(
        _BACKEND, zero_database, "call_command('migrate', no_color=True)\n",
    )
    assert zero.returncode == 0, zero.stderr
    for migration in (
        "accounts.0005_service_account_flag",
        "game.0009_diagnostic_session_foundation",
        "game.0010_diagnostic_service_account",
    ):
        assert f"Applying {migration}... OK" in zero.stdout
    _assert_managed_flag(zero_database)

    database = tmp_path / "fresh.sqlite3"
    schema = _migration_process(
        _BACKEND, database,
        "call_command('migrate', 'game', '0009', no_color=True)\n",
    )
    assert schema.returncode == 0, schema.stderr
    assert "Applying game.0009_diagnostic_session_foundation... OK" in schema.stdout
    with sqlite3.connect(database) as db:
        assert not db.execute(
            "SELECT 1 FROM accounts_user WHERE username=?",
            (services.DIAGNOSTIC_SERVICE_USERNAME,),
        ).fetchone()
    print("After 0009 alone: reserved account absent")

    full = _migration_process(_BACKEND, database, "call_command('migrate', no_color=True)\n")
    assert full.returncode == 0, full.stderr
    assert "Applying accounts.0005_service_account_flag... OK" in full.stdout
    assert "Applying game.0010_diagnostic_service_account... OK" in full.stdout
    _assert_managed_flag(database)

    # Reverse 0010 first (it owns the seed), then insert a managed sentinel.
    # Reversing 0009 itself must preserve that user.
    reverse = _migration_process(
        _BACKEND, database,
        "call_command('migrate', 'game', '0009', no_color=True)\n"
        "from game.services import ensure_diagnostic_service_user\n"
        "from accounts.models import User\n"
        "assert not User.objects.filter(username='libretiles-diagnostic').exists()\n"
        "user = ensure_diagnostic_service_user()\n"
        "call_command('migrate', 'game', '0008', no_color=True)\n"
        "assert User.objects.filter(pk=user.pk, is_service_account=True).exists()\n"
        "print('Reversing 0009 preserves the managed sentinel user')\n",
    )
    assert reverse.returncode == 0, reverse.stderr
    _assert_managed_flag(database)
