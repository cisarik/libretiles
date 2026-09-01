from __future__ import annotations

from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import JSONField
from django.test import TestCase, TransactionTestCase

from accounts.models import User
from game.models import GameSession, PlayerSlot
from game.services import (
    _WIRE_ADAPTER_REMOVAL,
    _bag_from_session,
    _board_from_session,
    _build_state,
    _legacy_wire_board_and_blanks,
    _perform_starting_draw,
    _persist_bag,
    _persist_board,
)
from gamecore.board import BOARD_SIZE, Board
from gamecore.scoring import score_words
from gamecore.tiles import TileBag
from gamecore.types import Placement
from gamecore.variant_store import VariantDefinition, VariantLetter, load_variant
from tests._migration_restore import restore_apps_to_leaf

_GAME_0007 = [("game", "0007_consumedwsticket")]
_GAME_0008 = [("game", "0008_atomic_token_state_schema")]


def _synthetic_digraph_variant() -> VariantDefinition:
    return VariantDefinition(
        slug="synthetic-digraph",
        language="test",
        letters=(
            VariantLetter(letter="A", count=1, points=1),
            VariantLetter(letter="CS", count=1, points=8),
            VariantLetter(letter="SZ", count=1, points=5),
            VariantLetter(letter="?", count=1, points=0),
        ),
        dictionary_file="collins2019.txt",
        alphabet_order=("A", "CS", "SZ"),
    )


def _session_with_slot(*, username: str) -> tuple[GameSession, PlayerSlot, User]:
    user = User.objects.create_user(username=username, password="pass1234")
    session = GameSession.objects.create(
        game_mode="vs_ai",
        status="active",
        variant_slug="english",
    )
    slot = PlayerSlot.objects.create(
        game=session, slot=0, user=user, is_ai=False, rack=[]
    )
    return session, slot, user


class AtomicTokenSchemaMigrationTests(TransactionTestCase):
    def test_p1_guard_refuses_when_session_row_exists(self) -> None:
        # Pre-fix: applying the schema change on a non-empty game_session table
        # would drop/retype columns with live rows still present.
        executor = MigrationExecutor(connection)
        executor.migrate(_GAME_0007)
        old_apps = executor.loader.project_state(_GAME_0007).apps
        OldSession = old_apps.get_model("game", "GameSession")
        session = OldSession.objects.create()
        pk = session.pk
        try:
            executor = MigrationExecutor(connection)
            with self.assertRaises(RuntimeError) as raised:
                executor.migrate(_GAME_0008)
            message = str(raised.exception)
            assert "manage.py purge_legacy_game_state" in message
            assert OldSession.objects.filter(pk=pk).exists()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM game_session WHERE id = %s", [pk])
            restore_apps_to_leaf("game")

    def test_p2_guard_passes_on_empty_tables_and_reverses(self) -> None:
        # Pre-fix: reverse after a schema rewrite could silently recast JSON
        # tokens back into joined strings.
        executor = MigrationExecutor(connection)
        executor.migrate(_GAME_0007)
        try:
            with connection.cursor() as cursor:
                for table in (
                    "game_chat_message",
                    "game_move",
                    "game_player_slot",
                    "game_session",
                    "game_consumed_ws_ticket",
                ):
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    assert cursor.fetchone()[0] == 0

            executor = MigrationExecutor(connection)
            executor.migrate(_GAME_0008)
            new_apps = executor.loader.project_state(_GAME_0008).apps
            NewSession = new_apps.get_model("game", "GameSession")
            field_names = {field.name for field in NewSession._meta.local_fields}
            assert "blanks" not in field_names
            assert isinstance(NewSession._meta.get_field("bag_tiles"), JSONField)

            executor = MigrationExecutor(connection)
            executor.migrate(_GAME_0007)
            old_apps = executor.loader.project_state(_GAME_0007).apps
            OldSession = old_apps.get_model("game", "GameSession")
            restored_names = {field.name for field in OldSession._meta.local_fields}
            assert "blanks" in restored_names
        finally:
            restore_apps_to_leaf("game")


class AtomicTokenPersistenceTests(TestCase):
    def test_p3_multicodepoint_token_round_trips_as_one_cell_and_one_bag_entry(self) -> None:
        # Pre-fix: "".join(["SZ", "A"]) -> "SZA"; list("SZA") -> ["S", "Z", "A"].
        session, _slot, _user = _session_with_slot(username="p3-roundtrip")
        synthetic = _synthetic_digraph_variant()
        board = Board(str(settings.PREMIUMS_PATH))
        board.cells[3][4].letter = "SZ"
        board.cells[3][4].is_blank = False
        _persist_board(session, board)
        _persist_bag(session, TileBag(seed=1, tiles=["SZ", "A"], variant=synthetic))
        session.save()

        session.refresh_from_db()
        assert session.board_state[3][4] == {"token": "SZ", "blank_as": None}
        assert session.bag_tiles == ["SZ", "A"]

        loaded = _board_from_session(session)
        assert loaded.cells[3][4].letter == "SZ"
        assert loaded.cells[3][4].token == "SZ"
        assert not loaded.cells[3][4].is_blank
        occupied = [
            (r, c)
            for r in range(BOARD_SIZE)
            for c in range(BOARD_SIZE)
            if loaded.cells[r][c].letter
        ]
        assert occupied == [(3, 4)]

        loaded_bag = _bag_from_session(session)
        assert loaded_bag.tiles == ["SZ", "A"]
        assert loaded_bag.remaining() == 2

    def test_p4_blank_realized_as_multicodepoint_keeps_blank_identity_and_scores_zero(
        self,
    ) -> None:
        # Pre-fix: blanks lived in a sidecar coordinate list; a joined-string
        # board could not store blank_as "CS" as one cell.
        session, _slot, _user = _session_with_slot(username="p4-blank-cs")
        synthetic = _synthetic_digraph_variant()
        board = Board()
        board.cells[2][2].letter = "CS"
        board.cells[2][2].is_blank = True
        board.cells[2][3].letter = "A"
        board.cells[2][3].is_blank = False
        _persist_board(session, board)
        session.save()

        session.refresh_from_db()
        assert session.board_state[2][2] == {"token": "?", "blank_as": "CS"}
        loaded = _board_from_session(session)
        assert loaded.cells[2][2].is_blank
        assert loaded.cells[2][2].token == "?"
        assert loaded.cells[2][2].blank_as == "CS"
        assert loaded.cells[2][2].letter == "CS"

        placements = [
            Placement(2, 2, "?", "CS"),
            Placement(2, 3, "A"),
        ]
        _total, breakdowns = score_words(
            loaded,
            placements,
            [("CSA", [(2, 2), (2, 3)])],
            variant=synthetic,
        )
        # Blank CS contributes 0; A contributes 1. Premiums on reload may
        # multiply the total; base_points is the tile-point identity.
        assert breakdowns[0].base_points == 1

    def test_p5_bag_remaining_counts_tiles_not_codepoints(self) -> None:
        # Pre-fix: bag_tiles="SZA" (joined SZ+A) made len(session.bag_tiles)==3.
        session, slot, user = _session_with_slot(username="p5-bag-count")
        session.bag_tiles = ["SZ", "A"]
        session.save(update_fields=["bag_tiles"])
        state = _build_state(session, current_user_id=user.id, my_slot=slot)
        assert state["bag_remaining"] == 2

    def test_p6_slovak_starting_draw_accent_beats_z_blank_lowest_english_and_ties(self) -> None:
        # Pre-fix: _perform_starting_draw used slot0_value <= slot1_value;
        # ('Á' <= 'Z') is False (codepoints 193 vs 90), so Á lost to Z.
        slovak = load_variant("slovak")
        english = load_variant("english")

        draw_accent = _perform_starting_draw(
            TileBag(seed=0, tiles=["Á", "Z"] + ["A"] * 10, variant=slovak),
            slovak,
        )
        assert draw_accent["slot0_tile"] == "Á"
        assert draw_accent["slot1_tile"] == "Z"
        assert draw_accent["slot0_first"] is True

        draw_blank = _perform_starting_draw(
            TileBag(seed=0, tiles=["?", "A"] + ["B"] * 10, variant=slovak),
            slovak,
        )
        assert draw_blank["slot0_tile"] == "?"
        assert draw_blank["slot0_first"] is True

        draw_en_a = _perform_starting_draw(
            TileBag(seed=0, tiles=["A", "Z"] + ["E"] * 10, variant=english),
            english,
        )
        assert draw_en_a["slot0_first"] is True

        draw_en_z = _perform_starting_draw(
            TileBag(seed=0, tiles=["Z", "A"] + ["E"] * 10, variant=english),
            english,
        )
        assert draw_en_z["slot0_first"] is False

        draw_tie = _perform_starting_draw(
            TileBag(seed=0, tiles=["A", "A"] + ["E"] * 10, variant=english),
            english,
        )
        assert draw_tie["slot0_first"] is True

    def test_p7_adapter_is_lossless_for_english_blank_board(self) -> None:
        # Pre-fix: _build_state emitted session.board_state / session.blanks raw.
        session, slot, user = _session_with_slot(username="p7-adapter")
        board = Board(str(settings.PREMIUMS_PATH))
        board.place_letters(
            [
                Placement(7, 7, "?", "A"),
                Placement(7, 8, "T"),
            ]
        )
        _persist_board(session, board)
        session.save()

        state = _build_state(session, current_user_id=user.id, my_slot=slot)
        assert len(state["board"]) == 15
        assert all(isinstance(row, str) and len(row) == 15 for row in state["board"])
        assert state["board"][7][7] == "A"
        assert state["board"][7][8] == "T"
        assert state["blanks"] == [{"row": 7, "col": 7}]
        expected_row = "." * 7 + "A" + "T" + "." * 6
        assert state["board"][7] == expected_row

    def test_p8_adapter_raises_on_multicodepoint_token(self) -> None:
        # Pre-fix: joined-string persist truncated or split SZ into S+Z.
        session, slot, user = _session_with_slot(username="p8-raise")
        grid = [[None] * 15 for _ in range(15)]
        grid[0][0] = {"token": "SZ", "blank_as": None}
        session.board_state = grid
        session.save(update_fields=["board_state"])
        with self.assertRaises(ValueError) as raised:
            _build_state(session, current_user_id=user.id, my_slot=slot)
        assert str(raised.exception) == _WIRE_ADAPTER_REMOVAL
        with self.assertRaises(ValueError) as raised_direct:
            _legacy_wire_board_and_blanks(session.board_state)
        assert "state_schema_version 4" in str(raised_direct.exception)

    def test_p9_rack_survives_as_ordered_token_array_with_duplicate_and_blank(self) -> None:
        session, slot, user = _session_with_slot(username="p9-rack")
        slot.rack = ["A", "A", "?", "B"]
        slot.save(update_fields=["rack"])
        state = _build_state(session, current_user_id=user.id, my_slot=slot)
        assert state["my_rack"] == ["A", "A", "?", "B"]
        slot.refresh_from_db()
        assert slot.rack == ["A", "A", "?", "B"]
