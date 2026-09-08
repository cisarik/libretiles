from __future__ import annotations

from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from game import services
from game.models import DiagnosticPly, DiagnosticRun, GameSession, Move, PlayerSlot
from game.replay import build_snapshot


class AdminReplayAPITests(TestCase):
    def setUp(self) -> None:
        self.client = APIClient()
        self.staff = User.objects.create_user(
            username="replay-admin", password="pass1234", is_staff=True
        )
        self.user = User.objects.create_user(username="replay-player", password="pass1234")
        self.opponent = User.objects.create_user(
            username="replay-opponent", password="pass1234"
        )

    def _authenticate(self, user: User) -> None:
        self.client.force_authenticate(user=user)

    def _session(
        self,
        *,
        user: User | None = None,
        mode: str = "vs_human",
        variant: str = "english",
        status: str = "active",
        diagnostic: bool = False,
    ) -> tuple[GameSession, PlayerSlot, PlayerSlot]:
        owner = user or self.user
        session = GameSession.objects.create(
            game_mode=mode,
            variant_slug=variant,
            status=status,
            is_diagnostic=diagnostic,
            current_turn_slot=0,
            bag_seed=7,
            bag_tiles=list("ERISNODXYZABCDEFGHIJKLMNOP"),
        )
        slot0 = PlayerSlot.objects.create(
            game=session, slot=0, user=owner, rack=["A", "T", "C", "D", "E", "F", "G"]
        )
        slot1 = PlayerSlot.objects.create(
            game=session, slot=1, user=None, rack=["H", "I", "J", "K", "L", "M", "N"]
        )
        session.replay_initial_state = build_snapshot(session)
        session.save(update_fields=["replay_initial_state"])
        return session, slot0, slot1

    def test_admin_games_list_requires_staff(self) -> None:
        self._session()
        assert self.client.get("/api/admin/games/").status_code == 401
        self._authenticate(self.user)
        assert self.client.get("/api/admin/games/").status_code == 403
        self._authenticate(self.staff)
        response = self.client.get("/api/admin/games/")
        assert response.status_code == 200
        assert response.json()["count"] == 1
        assert response["Cache-Control"] == "private, no-store"

    def test_admin_games_list_filtering(self) -> None:
        first, _, _ = self._session()
        second_user = User.objects.create_user(username="needle-user", password="pass1234")
        second, _, _ = self._session(
            user=second_user,
            mode="vs_ai",
            variant="slovak",
            status="finished",
            diagnostic=True,
        )
        self._authenticate(self.staff)

        response = self.client.get(
            "/api/admin/games/",
            {
                "game_mode": "vs_ai",
                "variant_slug": "slovak",
                "status": "finished",
                "is_diagnostic": "true",
            },
        )
        assert response.status_code == 200
        assert [item["game_id"] for item in response.json()["results"]] == [
            str(second.public_id)
        ]
        username_search = self.client.get("/api/admin/games/", {"search": "needle"})
        assert username_search.json()["results"][0]["game_id"] == str(second.public_id)
        uuid_search = self.client.get(
            "/api/admin/games/", {"search": str(first.public_id).replace("-", "")[:10]}
        )
        assert uuid_search.json()["results"][0]["game_id"] == str(first.public_id)

    def test_admin_game_replay_requires_staff(self) -> None:
        session, _, _ = self._session()
        url = f"/api/admin/games/{session.public_id}/replay/"
        assert self.client.get(url).status_code == 401
        self._authenticate(self.user)
        assert self.client.get(url).status_code == 403
        self._authenticate(self.staff)
        assert self.client.get(url).status_code == 200

    def test_admin_game_replay_structure(self) -> None:
        session, slot0, slot1 = self._session()
        placed = services.submit_move_for_user(
            str(session.public_id),
            self.user.id,
            [{"row": 7, "col": 6, "letter": "A"}, {"row": 7, "col": 7, "letter": "T"}],
        )
        assert placed["ok"] is True

        slot1.user = self.opponent
        slot1.rack = ["H", "I", "J", "K", "L", "M", "N"]
        slot1.save(update_fields=["user", "rack"])
        exchanged = services.submit_exchange_for_user(
            str(session.public_id), self.opponent.id, ["H"]
        )
        assert exchanged["ok"] is True
        passed = services.submit_pass_for_user(str(session.public_id), self.user.id)
        assert passed["ok"] is True

        self._authenticate(self.staff)
        response = self.client.get(f"/api/admin/games/{session.public_id}/replay/")
        assert response.status_code == 200
        payload = response.json()
        assert payload["replay_status"] == "complete"
        assert payload["initial_state"]["initial_racks"][0][:2] == ["A", "T"]
        assert [ply["kind"] for ply in payload["plies"]] == ["place", "exchange", "pass"]
        assert payload["plies"][0]["board_delta"] == [
            {"row": 7, "col": 6, "token": "A", "blank_as": None},
            {"row": 7, "col": 7, "token": "T", "blank_as": None},
        ]
        inspection = payload["plies"][0]["words_formed"][0]["inspection"]
        assert inspection["word_total"] == 4
        assert inspection["authority"]["name"] == "WordAuthority"
        assert inspection["authority"]["main_lexicon_id"] == "collins2019"
        assert len(inspection["physical_cells"]) == 2
        assert payload["plies"][1]["exchanged_tiles"] == ["H"]
        assert len(payload["plies"][1]["racks"]) == 2
        assert payload["plies"][2]["cumulative_scores"] == [4, 0]
        assert payload["final_state"]["scores"] == [4, 0]

    def test_admin_game_replay_diagnostic_integration(self) -> None:
        session, slot0, _ = self._session(diagnostic=True)
        before = build_snapshot(session)
        move = Move.objects.create(
            game=session,
            player_slot=slot0,
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
            session=session,
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
            ai_trace={"attempts": 1},
        )
        self._authenticate(self.staff)
        payload = self.client.get(f"/api/admin/games/{session.public_id}/replay/").json()
        assert payload["plies"][0]["diagnostic_ply"]["run_id"] == str(run.id)
        assert payload["plies"][0]["diagnostic_ply"]["wall_clock_ms"] == 12
        assert payload["plies"][0]["diagnostic_ply"]["ai_trace"] == {"attempts": 1}

    def test_replay_capture_includes_final_scores_and_give_up(self) -> None:
        session, slot0, slot1 = self._session()
        session.bag_tiles = []
        session.save(update_fields=["bag_tiles"])
        slot0.rack = ["A", "T"]
        slot0.save(update_fields=["rack"])
        result = services.submit_move_for_user(
            str(session.public_id),
            self.user.id,
            [{"row": 7, "col": 6, "letter": "A"}, {"row": 7, "col": 7, "letter": "T"}],
        )
        assert result["ok"] is True
        assert result["game_over"] is True
        move = Move.objects.get(game=session)
        assert move.replay_before["scores"] == [0, 0]
        slot0.refresh_from_db()
        slot1.refresh_from_db()
        assert move.replay_after["scores"] == [slot0.score, slot1.score]
        assert move.replay_after["scores"] != [move.points, 0]

        other, _, _ = self._session()
        give_up = services.submit_give_up_for_user(
            game_id=str(other.public_id), user_id=self.user.id
        )
        assert give_up["ok"] is True
        give_up_move = Move.objects.get(game=other)
        assert give_up_move.replay_before is not None
        assert give_up_move.replay_after is not None
        assert give_up_move.exchanged_tiles == []

    def test_purge_legacy_games_deletes_only_uncaptured_sessions(self) -> None:
        captured, _, _ = self._session()
        legacy = GameSession.objects.create(variant_slug="english")
        call_command("purge_legacy_games", "--yes")
        assert GameSession.objects.filter(pk=captured.pk).exists()
        assert not GameSession.objects.filter(pk=legacy.pk).exists()

    def test_user_serializer_exposes_is_staff(self) -> None:
        self._authenticate(self.staff)
        staff_response = self.client.get("/api/auth/me/")
        assert staff_response.status_code == 200
        assert staff_response.json()["is_staff"] is True
        patched = self.client.patch("/api/auth/me/", {"is_staff": False}, format="json")
        assert patched.status_code == 200
        self.staff.refresh_from_db()
        assert self.staff.is_staff is True

        self._authenticate(self.user)
        assert self.client.get("/api/auth/me/").json()["is_staff"] is False
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "cannot-escalate",
                "password": "strong-pass-123",
                "email": "",
                "is_staff": True,
            },
            format="json",
        )
        assert response.status_code == 201
        assert User.objects.get(username="cannot-escalate").is_staff is False
