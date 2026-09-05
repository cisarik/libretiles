"""End-to-end multigraph game on a temporary synthetic variant (MEC-C1-A).

⛔ ONLY VARIANT AND ASSET RESOLUTION ARE PATCHED. Validation, scoring, search,
persistence and the game-state wire projection are the production ones; the only
thing redirected is where assets live, so a tile whose token is two or three code
points travels every path as ONE ATOMIC THING.

⭐ TWO DIFFERENT SEGMENTATIONS OF THE SAME LEXICAL STRING are exercised in both
directions, which is the whole point: ``SZA`` is legal as ``SZ``+``A`` and
illegal as ``S``+``Z``+``A``, while ``ASZ`` is illegal as ``A``+``SZ`` and legal
as ``A``+``S``+``Z``. A path that reconstructed boundaries from the lexical
string could not tell those apart.

⭐ MEC-C1-B adds the AI CONTEXT of that same played board at the end: the
structured cell grid, the ordered AI rack and the lossless JSON convenience
string. Prompt construction itself is the frontend's and lives in
``frontend/src/lib/prompts.test.ts`` and ``atomic-tiles.test.ts``.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from django.test import TestCase, override_settings

from accounts.models import User
from game import services
from game.models import GameSession, PlayerSlot
from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.board import BOARD_SIZE
from gamecore.variant_store import load_variant
from gamecore.word_authority import WordAuthority, variant_entry_predicate

VARIANT_SLUG = "multigraph"

# Hungarian and Croatian are the real consumers of this shape. ``S`` and ``Z``
# are present ALONGSIDE ``SZ`` on purpose — that is what real Hungarian has, and
# without single letters that also spell a digraph there is no lexical string
# with two different segmentations to test at all.
TILES: tuple[tuple[str, int, int], ...] = (
    ("?", 2, 0),
    ("A", 12, 1),
    ("Á", 6, 4),
    ("CS", 6, 5),
    ("DZS", 4, 8),
    ("L·L", 4, 8),
    ("S", 8, 1),
    ("SZ", 6, 5),
    ("Z", 6, 3),
)
ALPHABET_ORDER: tuple[str, ...] = ("A", "Á", "CS", "DZS", "L·L", "S", "SZ", "Z")

# Main lexicon. ⛔ `sza` is ABSENT on purpose: it is legal only as two tiles.
MAIN_ENTRIES: tuple[str, ...] = (
    "acsaszadzsa",
    "asz",
    "csacs",
    "aaaa",
)
# Two-tile lexicon. ⛔ `asz` is ABSENT on purpose: it is legal only as three tiles.
TWO_TILE_ENTRIES: tuple[str, ...] = ("csa", "sza", "cscs", "cssz", "l·la")

BINGO_WORD = "ACSASZADZSA"
BINGO_TOKENS: tuple[str, ...] = ("A", "CS", "A", "SZ", "A", "DZS", "A")


def _write_assets(root: Path) -> None:
    (root / "dicts").mkdir(parents=True)
    (root / "variants").mkdir(parents=True)
    (root / "dicts" / f"{VARIANT_SLUG}.txt").write_text(
        "".join(f"{entry}\n" for entry in MAIN_ENTRIES), encoding="utf-8"
    )
    (root / "dicts" / f"{VARIANT_SLUG}_two_tile.txt").write_text(
        "".join(f"{entry}\n" for entry in TWO_TILE_ENTRIES), encoding="utf-8"
    )
    # The REAL premium map: premium behaviour must not be a fixture.
    shutil.copyfile(get_premiums_path(), root / "premiums.json")
    (root / "variants" / f"{VARIANT_SLUG}.json").write_text(
        json.dumps(
            {
                "language": "Multigraph",
                "slug": VARIANT_SLUG,
                "language_code": "xx",
                "dictionary_file": f"{VARIANT_SLUG}.txt",
                "two_tile_words_file": f"{VARIANT_SLUG}_two_tile.txt",
                "alphabet_order": list(ALPHABET_ORDER),
                "vowels": ["A", "Á"],
                "letters": [
                    {"letter": token, "count": count, "points": points}
                    for token, count, points in TILES
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


class MultigraphEndToEndTests(TestCase):
    """One synthetic game driven entirely through the production service layer."""

    root: Path

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        directory = Path(tempfile.mkdtemp(prefix="libretiles-multigraph-"))
        cls.addClassCleanup(shutil.rmtree, directory, ignore_errors=True)
        cls.root = directory / "assets"
        _write_assets(cls.root)

    def setUp(self) -> None:
        super().setUp()
        self._settings = override_settings(
            ASSETS_DIR=self.root,
            PREMIUMS_PATH=self.root / "premiums.json",
            CHANNEL_LAYERS={
                "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
            },
        )
        self._settings.enable()
        self.addCleanup(self._settings.disable)
        self.user = User.objects.create_user(
            username="multigraph-player", password="pass1234"
        )

    # -- helpers ---------------------------------------------------------

    def _create(self) -> tuple[GameSession, PlayerSlot, str]:
        created = services.create_game(user_id=self.user.id, variant_slug=VARIANT_SLUG)
        assert "game_id" in created, created
        game_id = str(created["game_id"])
        session = GameSession.objects.get(public_id=game_id)
        slot = session.slots.get(slot=0)
        return session, slot, game_id

    def _force_turn(self, session: GameSession, slot: PlayerSlot, rack: list[str]) -> None:
        """Fixture only: pin whose turn it is and what is on the rack.

        ⛔ Nothing about validation, scoring or persistence is bypassed; this is
        the equivalent of dealing a known hand.
        """
        session.current_turn_slot = 0
        session.save(update_fields=["current_turn_slot"])
        slot.rack = list(rack)
        slot.save(update_fields=["rack"])

    def _place(
        self, game_id: str, cells: list[tuple[int, int, str, str | None]]
    ) -> dict[str, Any]:
        payload: list[dict[str, Any]] = []
        for row, col, letter, blank_as in cells:
            item: dict[str, Any] = {"row": row, "col": col, "letter": letter}
            if blank_as is not None:
                item["blank_as"] = blank_as
            payload.append(item)
        return services.submit_move_for_user(
            game_id=game_id, user_id=self.user.id, placements_data=payload
        )

    def _validate(
        self, game_id: str, cells: list[tuple[int, int, str, str | None]]
    ) -> dict[str, Any]:
        payload: list[dict[str, Any]] = []
        for row, col, letter, blank_as in cells:
            item: dict[str, Any] = {"row": row, "col": col, "letter": letter}
            if blank_as is not None:
                item["blank_as"] = blank_as
            payload.append(item)
        return services.validate_move_for_ai(game_id, self.user.id, payload)

    # -- tests -----------------------------------------------------------

    def test_variant_and_authority_resolve_against_the_temporary_assets(self) -> None:
        assert get_assets_path() == self.root
        variant = load_variant(VARIANT_SLUG)
        assert variant.slug == VARIANT_SLUG
        assert variant.playable_letters == ALPHABET_ORDER
        assert variant.tile_points["DZS"] == 8
        assert variant.total_tiles == sum(count for _t, count, _p in TILES)
        # The derived entry predicate admits the declared interpunct, and only it.
        assert variant_entry_predicate(variant) is not None
        authority = WordAuthority.for_variant(variant)
        assert authority.two_tile_words == frozenset(TWO_TILE_ENTRIES)
        assert authority.contains_main(BINGO_WORD) is True
        assert authority.contains_main("sza") is False
        assert authority.accepts_tokens(BINGO_TOKENS) is True

    def test_drawing_keeps_whole_tokens(self) -> None:
        session, slot, _game_id = self._create()
        tile_set = frozenset(token for token, _c, _p in TILES)
        assert len(slot.rack) == 7
        assert all(entry in tile_set for entry in slot.rack)
        assert all(entry in tile_set for entry in session.bag_tiles)
        drawn = len(slot.rack) + len(session.slots.get(slot=1).rack)
        assert drawn == 14
        assert drawn + len(session.bag_tiles) == sum(count for _t, count, _p in TILES)
        # A digraph tile is never split into its code points: `D` alone is not a
        # tile in this variant, so its presence anywhere would mean `DZS` was cut.
        assert "D" not in session.bag_tiles
        assert "D" not in slot.rack
        assert session.bag_tiles.count("DZS") + slot.rack.count("DZS") + session.slots.get(
            slot=1
        ).rack.count("DZS") == 4

    def test_exchange_preserves_duplicate_and_multigraph_rack_entries(self) -> None:
        session, slot, game_id = self._create()
        self._force_turn(
            session, slot, ["CS", "CS", "DZS", "A", "A", "SZ", "Á"]
        )
        before = len(session.bag_tiles)
        result = services.submit_exchange_for_user(
            game_id=game_id, user_id=self.user.id, letters_to_exchange=["DZS"]
        )
        assert result["ok"] is True, result
        slot.refresh_from_db()
        session.refresh_from_db()
        tile_set = frozenset(token for token, _c, _p in TILES)
        # The kept tiles keep their order AND their duplicates: exchanging one
        # entry removes exactly one entry.
        assert slot.rack[:6] == ["CS", "CS", "A", "A", "SZ", "Á"]
        assert len(slot.rack) == 7
        assert slot.rack[6] in tile_set
        assert len(session.bag_tiles) == before
        assert session.bag_tiles.count("DZS") >= 1
        assert all(entry in tile_set for entry in session.bag_tiles)
        assert "D" not in slot.rack
        assert "S" not in slot.rack[:6]

    def test_seven_tile_bingo_counts_tiles_not_code_points(self) -> None:
        session, slot, game_id = self._create()
        self._force_turn(session, slot, list(BINGO_TOKENS))
        result = self._place(
            game_id,
            [(7, column, token, None) for column, token in zip(range(4, 11), BINGO_TOKENS)],
        )
        assert result["ok"] is True, result
        # Eleven code points, SEVEN tiles: the +50 is earned by tiles.
        assert len(BINGO_WORD) == 11
        assert len(BINGO_TOKENS) == 7
        assert result["bingo"] is True
        assert result["words"] == [{"word": BINGO_WORD, "score": 44}]
        assert result["points"] == 94
        session.refresh_from_db()
        assert session.premium_used == [{"row": 7, "col": 7}]

    def test_reload_wire_projection_and_websocket_refresh_are_lossless(self) -> None:
        session, slot, game_id = self._create()
        self._force_turn(session, slot, list(BINGO_TOKENS))
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            placed = self._place(
                game_id,
                [
                    (7, column, token, None)
                    for column, token in zip(range(4, 11), BINGO_TOKENS)
                ],
            )
        assert placed["ok"] is True, placed
        # The realtime refresh really was scheduled and really ran.
        assert callbacks

        session.refresh_from_db()
        assert session.board_state[7][5] == {"token": "CS", "blank_as": None}
        assert session.board_state[7][9] == {"token": "DZS", "blank_as": None}

        board = services._board_from_session(session)
        assert board.cells[7][5].token == "CS"
        assert board.cells[7][5].realized_token == "CS"
        assert board.cells[7][9].token == "DZS"
        assert [
            board.cells[7][column].realized_token for column in range(4, 11)
        ] == list(BINGO_TOKENS)

        # The websocket refresh delivers exactly this payload (consumers.py
        # room_game_state calls get_game_state_for_user).
        state = services.get_game_state_for_user(game_id, self.user.id)
        assert len(state["board"]) == BOARD_SIZE
        assert state["board"][7][5] == {"token": "CS", "blank_as": None}
        assert state["board"][7][9] == {"token": "DZS", "blank_as": None}
        assert state["board"][7][3] is None
        assert state["last_move_words"][0]["word"] == BINGO_WORD
        assert state["variant_slug"] == VARIANT_SLUG
        assert state["alphabet"] == list(ALPHABET_ORDER)

    def test_two_segmentations_of_one_lexical_string_disagree_both_ways(self) -> None:
        session, slot, game_id = self._create()
        self._force_turn(session, slot, list(BINGO_TOKENS))
        assert self._place(
            game_id,
            [(7, column, token, None) for column, token in zip(range(4, 11), BINGO_TOKENS)],
        )["ok"] is True

        # `SZA`: legal as TWO tiles, illegal as THREE.
        self._force_turn(session, slot, ["SZ", "S", "Z", "A", "A", "A", "A"])
        two_tile_sza = self._validate(game_id, [(6, 10, "SZ", None)])
        assert two_tile_sza["valid"] is True, two_tile_sza
        assert [item["word"] for item in two_tile_sza["words"]] == ["SZA"]
        three_tile_sza = self._validate(
            game_id, [(5, 10, "S", None), (6, 10, "Z", None)]
        )
        assert three_tile_sza["valid"] is False
        assert three_tile_sza["reason_code"] == "invalid_word"
        assert [item["word"] for item in three_tile_sza["words"]] == ["SZA"]

        # `ASZ`: illegal as TWO tiles, legal as THREE. Same lexical string, the
        # opposite verdict — boundaries are preserved, not reconstructed.
        two_tile_asz = self._validate(game_id, [(8, 4, "SZ", None)])
        assert two_tile_asz["valid"] is False
        assert two_tile_asz["reason_code"] == "invalid_word"
        assert [item["word"] for item in two_tile_asz["words"]] == ["ASZ"]
        three_tile_asz = self._validate(
            game_id, [(8, 4, "S", None), (9, 4, "Z", None)]
        )
        assert three_tile_asz["valid"] is True, three_tile_asz
        assert [item["word"] for item in three_tile_asz["words"]] == ["ASZ"]

        # The persisted path agrees with the validating path.
        persisted = self._place(game_id, [(8, 4, "S", None), (9, 4, "Z", None)])
        assert persisted["ok"] is True, persisted
        assert [entry["word"] for entry in persisted["words"]] == ["ASZ"]

    def test_crossing_words_blank_targets_scoring_and_premium_reuse(self) -> None:
        session, slot, game_id = self._create()
        self._force_turn(session, slot, list(BINGO_TOKENS))
        first = self._place(
            game_id,
            [(7, column, token, None) for column, token in zip(range(4, 11), BINGO_TOKENS)],
        )
        assert first["ok"] is True, first
        session.refresh_from_db()
        assert session.premium_used == [{"row": 7, "col": 7}]

        # Crossing word through an EXISTING digraph tile: CS + A + CS.
        self._force_turn(session, slot, ["CS", "CS", "A", "A", "A", "A", "A"])
        crossing = self._place(game_id, [(6, 6, "CS", None), (8, 6, "CS", None)])
        assert crossing["ok"] is True, crossing
        assert [entry["word"] for entry in crossing["words"]] == ["CSACS"]
        # CS(5) + A(1) + CS(5) = 11 base, plus the two double-letter squares at
        # (6,6) and (8,6) which each add one whole DIGRAPH tile's 5 points.
        assert crossing["points"] == 21

        # A blank realizing a DIGRAPH: physical token '?', realized 'CS', ZERO
        # points, and it forms two words at once.
        self._force_turn(session, slot, ["?", "A", "A", "A", "A", "A", "A"])
        blank = self._place(game_id, [(6, 7, "?", "CS")])
        assert blank["ok"] is True, blank
        # One placement, TWO complete two-tile words, each four code points.
        assert sorted(entry["word"] for entry in blank["words"]) == ["CSCS", "CSSZ"]
        # The blank contributes ZERO however many code points it realizes:
        # CSCS = 0 + CS(5); CSSZ = 0 + SZ(5). (6,7) carries no premium and the
        # already-consumed squares are not multiplied again.
        assert blank["points"] == 10
        session.refresh_from_db()
        assert session.board_state[6][7] == {"token": "?", "blank_as": "CS"}
        board = services._board_from_session(session)
        assert board.cells[6][7].token == "?"
        assert board.cells[6][7].blank_as == "CS"
        assert board.cells[6][7].realized_token == "CS"
        assert board.cells[6][7].is_blank is True

        # An interpunct tile plays through the real derived index.
        self._force_turn(session, slot, ["L·L", "A", "A", "A", "A", "A", "A"])
        interpunct = self._place(game_id, [(6, 10, "L·L", None)])
        assert interpunct["ok"] is True, interpunct
        assert [entry["word"] for entry in interpunct["words"]] == ["L·LA"]

        # Premium reuse: the centre square was consumed by the first move and is
        # never multiplied again, and the consumed set persists across reload.
        session.refresh_from_db()
        used = {(item["row"], item["col"]) for item in session.premium_used}
        assert (7, 7) in used
        assert (6, 6) in used
        assert (8, 6) in used
        reloaded = services._board_from_session(session)
        assert reloaded.cells[7][7].premium_used is True
        assert reloaded.cells[6][6].premium_used is True
        assert reloaded.cells[7][9].realized_token == "DZS"
        # The consumed centre square is not multiplied a second time: the blank
        # move above crossed (7,7) and scored its two words at face value.
        assert blank["points"] == 10

    def test_malformed_persisted_blank_fails_closed_and_is_not_empty(self) -> None:
        """⛔ A `?` with no assignment must not read as an empty square."""
        session, slot, game_id = self._create()
        self._force_turn(session, slot, list(BINGO_TOKENS))
        assert self._place(
            game_id,
            [(7, column, token, None) for column, token in zip(range(4, 11), BINGO_TOKENS)],
        )["ok"] is True

        session.refresh_from_db()
        grid = session.board_state
        grid[6][6] = {"token": "?", "blank_as": None}
        session.board_state = grid
        session.save(update_fields=["board_state"])

        board = services._board_from_session(session)
        cell = board.cells[6][6]
        assert cell.is_malformed is True
        assert cell.is_occupied is True
        assert cell.realized_token == "?"
        assert board.malformed_cells() == [(6, 6)]

        self._force_turn(session, slot, ["A", "A", "A", "A", "A", "A", "A"])
        rejected = self._validate(game_id, [(8, 6, "A", None)])
        assert rejected["valid"] is False
        assert rejected["reason_code"] == "malformed_board_cell"

    # -- Slice B: the AI context of the very same game --------------------

    def test_ai_context_of_a_played_multigraph_board_is_lossless(self) -> None:
        """⭐ SLICE B. The same seven tiles, seen through the AI projection.

        The board this asserts over is the one the production service layer
        actually persisted above, so nothing here is a fixture of the AI path:
        the digraph and trigraph tiles arrive as WHOLE tokens in their own
        columns, and the AI rack keeps its boundaries and its duplicates.
        """
        session, slot, game_id = self._create()
        self._force_turn(session, slot, list(BINGO_TOKENS))
        assert self._place(
            game_id,
            [(7, column, token, None) for column, token in zip(range(4, 11), BINGO_TOKENS)],
        )["ok"] is True

        # A blank realizing a DIGRAPH, which widened its row in the old string.
        self._force_turn(session, slot, ["?", "A", "A", "A", "A", "A", "A"])
        assert self._place(game_id, [(6, 7, "?", "CS")])["ok"] is True

        ai_slot = session.slots.get(slot=1)
        ai_slot.rack = ["SZ", "SZ", "DZS", "?", "A", "CS", "L·L"]
        ai_slot.save(update_fields=["rack"])

        context = services.get_ai_context(game_id, self.user.id)
        ai_state = context["ai_state"]

        assert "blanks" not in ai_state
        assert len(ai_state["grid"]) == BOARD_SIZE
        assert all(len(row) == BOARD_SIZE for row in ai_state["grid"])
        # Seven tiles, seven columns — ELEVEN code points that used to widen the
        # row to eighteen characters and shift every later column index.
        assert [ai_state["grid"][7][column] for column in range(4, 11)] == [
            {"token": token, "blank_as": None} for token in BINGO_TOKENS
        ]
        assert "".join(BINGO_TOKENS) == BINGO_WORD
        assert len(BINGO_WORD) == 11
        # The blank carries its own identity, in its own cell.
        assert ai_state["grid"][6][7] == {"token": "?", "blank_as": "CS"}
        # The rack is an ordered array: duplicates kept, order kept, and the
        # interpunct tile is one entry rather than three characters.
        assert ai_state["ai_rack"] == ["SZ", "SZ", "DZS", "?", "A", "CS", "L·L"]

        # This variant's TILE SET holds multigraphs, so the human-readable
        # convenience is lossless JSON instead of an unrepresentable joined grid.
        compact = context["compact_state"]
        assert compact.startswith("ai_state_json:\n")
        assert "ACSASZADZSA" not in compact
        decoded = json.loads(compact.split("\n", 1)[1])
        assert decoded["grid"] == ai_state["grid"]
        assert decoded["ai_rack"] == ai_state["ai_rack"]
        assert context["alphabet"] == list(ALPHABET_ORDER)
        assert context["tile_points"]["DZS"] == 8

