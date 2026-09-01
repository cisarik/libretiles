from datetime import timedelta
from io import StringIO

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from catalog.models import AIModel, AIPrompt
from game.models import ChatMessage, ConsumedWsTicket, GameSession, Move, PlayerSlot

_FIVE = (
    ChatMessage,
    Move,
    PlayerSlot,
    GameSession,
    ConsumedWsTicket,
)


def _five_counts() -> dict[str, int]:
    return {model._meta.db_table: model.objects.count() for model in _FIVE}


def _run_purge(*, dry_run: bool = False, stdout: StringIO | None = None) -> str:
    out = stdout if stdout is not None else StringIO()
    call_command("purge_legacy_game_state", dry_run=dry_run, stdout=out)
    return out.getvalue()


def _seed_populated_session() -> GameSession:
    session = GameSession.objects.create(game_mode="vs_ai")
    slot = PlayerSlot.objects.create(game=session, slot=0, rack=["A", "B"])
    Move.objects.create(game=session, player_slot=slot, seq=1, kind="pass")
    ChatMessage.objects.create(game=session, body="hello")
    return session


def _seed_ticket(*, suffix: str) -> ConsumedWsTicket:
    return ConsumedWsTicket.objects.create(
        ticket_hash=f"{suffix}{'a' * (64 - len(suffix))}",
        expires_at=timezone.now() + timedelta(hours=1),
    )


class PurgeLegacyGameStateCommandTests(TransactionTestCase):
    def test_t1_flag_false_leaves_nonempty_tables_unchanged(self) -> None:
        # Pre-fix: a missing flag read would delete rows even when the setting
        # is false, or would raise too late after a partial delete.
        _seed_populated_session()
        _seed_ticket(suffix="t1")
        before = _five_counts()
        assert any(count > 0 for count in before.values())

        with override_settings(ALLOW_DESTRUCTIVE_GAME_STATE_RESET=False):
            with self.assertRaises(CommandError) as raised:
                _run_purge()

        message = str(raised.exception)
        assert "ALLOW_DESTRUCTIVE_GAME_STATE_RESET" in message
        for table in before:
            assert table in message
        assert _five_counts() == before
        # Post-fix: fail-closed CommandError happens before any of the five change.

    def test_t2_flag_true_empties_all_five(self) -> None:
        # Pre-fix: a no-op or partial delete would leave at least one of five
        # non-zero.
        _seed_populated_session()
        _seed_ticket(suffix="t2")
        assert all(count > 0 for count in _five_counts().values())

        with override_settings(ALLOW_DESTRUCTIVE_GAME_STATE_RESET=True):
            _run_purge()

        assert _five_counts() == {
            "game_chat_message": 0,
            "game_move": 0,
            "game_player_slot": 0,
            "game_session": 0,
            "game_consumed_ws_ticket": 0,
        }
        # Post-fix: every target table is empty after a flagged purge.

    def test_t3_already_empty_is_noop_without_flag(self) -> None:
        # Pre-fix: requiring the flag on an empty database would block a
        # second run and a fresh empty development database.
        assert _five_counts() == {
            "game_chat_message": 0,
            "game_move": 0,
            "game_player_slot": 0,
            "game_session": 0,
            "game_consumed_ws_ticket": 0,
        }

        with override_settings(ALLOW_DESTRUCTIVE_GAME_STATE_RESET=False):
            _run_purge()

        assert _five_counts() == {
            "game_chat_message": 0,
            "game_move": 0,
            "game_player_slot": 0,
            "game_session": 0,
            "game_consumed_ws_ticket": 0,
        }
        # Post-fix: empty tables return without exception and without the flag.

    def test_t4_dry_run_with_flag_true_deletes_nothing(self) -> None:
        # Pre-fix: a destructive default would delete rows from a dry-run, or
        # from a routine migrate that happened to carry the flag.
        _seed_populated_session()
        _seed_ticket(suffix="t4")
        before = _five_counts()
        assert any(count > 0 for count in before.values())

        with override_settings(ALLOW_DESTRUCTIVE_GAME_STATE_RESET=True):
            output = _run_purge(dry_run=True)

        assert _five_counts() == before
        assert "dry-run" in output
        assert "pre-purge counts:" in output
        for table in before:
            assert table in output
        # Post-fix: --dry-run reports counts and deletes nothing, even with the flag.

    def test_t5_protected_rows_survive_flag_true_purge(self) -> None:
        # Pre-fix: a collector or raw DELETE could touch accounts, catalog,
        # token_blacklist, or axes rows.
        user = User.objects.create_user(
            username="purge-protected",
            password="pass1234",
        )
        model = AIModel.objects.create(
            provider="openrouter",
            model_id="purge-protected/model:free",
            display_name="Protected model",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        prompt = AIPrompt.objects.create(
            name="Protected prompt",
            prompt="advisory only",
        )
        RefreshToken.for_user(user)
        AccessAttempt = apps.get_model("axes", "AccessAttempt")
        attempt = AccessAttempt.objects.create(
            user_agent="purge-test",
            ip_address="127.0.0.1",
            username="purge-protected",
            http_accept="*/*",
            path_info="/admin/login/",
            attempt_time=timezone.now(),
            get_data="",
            post_data="",
            failures_since_start=1,
        )
        _seed_populated_session()
        _seed_ticket(suffix="t5")

        user_count = User.objects.count()
        model_count = AIModel.objects.count()
        prompt_count = AIPrompt.objects.count()
        token_count = OutstandingToken.objects.count()
        attempt_count = AccessAttempt.objects.count()
        user_pk = user.pk
        model_pk = model.pk
        prompt_pk = prompt.pk
        attempt_pk = attempt.pk

        with override_settings(ALLOW_DESTRUCTIVE_GAME_STATE_RESET=True):
            _run_purge()

        assert User.objects.count() == user_count
        assert AIModel.objects.count() == model_count
        assert AIPrompt.objects.count() == prompt_count
        assert OutstandingToken.objects.count() == token_count
        assert AccessAttempt.objects.count() == attempt_count
        assert User.objects.filter(pk=user_pk).exists()
        assert AIModel.objects.filter(pk=model_pk).exists()
        assert AIPrompt.objects.filter(pk=prompt_pk).exists()
        assert AccessAttempt.objects.filter(pk=attempt_pk).exists()
        # Post-fix: protected tables keep their rows and counts.

    def test_t6_deletion_order_survives_fk_enforcement(self) -> None:
        # Pre-fix: a parent-first raw DELETE hits SQLite ON DELETE NO ACTION
        # while children still exist.
        _seed_populated_session()
        _seed_ticket(suffix="t6")

        try:
            with override_settings(ALLOW_DESTRUCTIVE_GAME_STATE_RESET=True):
                _run_purge()
        except IntegrityError as exc:
            raise AssertionError("purge raised IntegrityError under FK enforcement") from exc

        assert all(count == 0 for count in _five_counts().values())
        # Post-fix: child-to-parent ORM order empties a populated session graph.

    def test_t7_unrelated_consumed_ticket_is_still_deleted(self) -> None:
        # Pre-fix: deleting GameSession cannot reach game_consumed_ws_ticket
        # because that table has no FK in either direction.
        _seed_populated_session()
        ticket = _seed_ticket(suffix="t7")
        ticket_pk = ticket.pk
        assert ConsumedWsTicket.objects.filter(pk=ticket_pk).exists()

        with override_settings(ALLOW_DESTRUCTIVE_GAME_STATE_RESET=True):
            _run_purge()

        assert not ConsumedWsTicket.objects.filter(pk=ticket_pk).exists()
        assert ConsumedWsTicket.objects.count() == 0
        # Post-fix: step 5 is independent and removes tickets with no session.

    def test_t8_sqlite_sequence_does_not_restart_at_one(self) -> None:
        # Pre-fix: DELETE FROM sqlite_sequence would make the next GameSession
        # primary key restart at 1 and look like a successful reset.
        first = _seed_populated_session()
        first_pk = first.pk
        assert first_pk >= 1

        with override_settings(ALLOW_DESTRUCTIVE_GAME_STATE_RESET=True):
            _run_purge()

        nxt = GameSession.objects.create(game_mode="vs_ai")
        assert nxt.pk != 1
        assert nxt.pk > first_pk
        # Post-fix: AUTOINCREMENT counters survive the purge, as measured.

    def test_t9_second_run_is_a_clean_noop(self) -> None:
        # Pre-fix: a non-idempotent command would raise on a second run, or
        # would require the flag even when every target is already empty.
        _seed_populated_session()
        _seed_ticket(suffix="t9")

        with override_settings(ALLOW_DESTRUCTIVE_GAME_STATE_RESET=True):
            _run_purge()
            assert all(count == 0 for count in _five_counts().values())
            output = _run_purge()

        assert "no-op" in output
        assert all(count == 0 for count in _five_counts().values())
        # Post-fix: a second run is a clean no-op even with the flag still true.
