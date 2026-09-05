"""The AI projection is LOSSLESS and its legacy string is BYTE-FROZEN (MEC-C1-B).

⭐ Two obligations that pull in opposite directions live here, and both are
pinned:

1. ``AIState`` must carry ONE ATOMIC TILE PER COLUMN. Measured at the baseline
   ``cbb2865``, a board holding ``SZ`` at (7,7) and ``DZS`` at (7,8) produced
   grid row 7 = ``'.......SZDZS......'`` — EIGHTEEN characters where there are
   fifteen squares — and ``ai_rack='SZDZS?'``, a string that cannot be
   segmented back into the three tiles that produced it.
2. ``compact_state`` must not move ONE BYTE for a single-code-point tile set.
   Twelve shipped languages send AI prompts through that string, so the digests
   below were captured from the baseline producer BEFORE the shape changed and
   are the regression oracle for it.

⛔ The save path is not exercised here: ``build_save_state_dict`` keeps schema
4, its joined-token grid and its stored ``blanks`` sidecar, and
``tests/test_atomic_tile_tokens.py`` owns that. This file covers only the AI
projection.
"""

from __future__ import annotations

import hashlib
import json

from gamecore.assets import get_premiums_path
from gamecore.board import BOARD_SIZE, Board
from gamecore.state import (
    ai_cell_realized_token,
    build_ai_state_dict,
    build_compact_state,
    has_multigraph_tile_token,
)
from gamecore.tiles import get_tile_points
from gamecore.variant_store import list_installed_variants, load_variant

# Captured from the BASELINE producer at cbb2865, before AIState was structured.
# ⛔ Do not recompute these from the implementation; they are the oracle.
_BASELINE_COMPACT_SHA256 = {
    "empty": "0bebc568739a3642445aa2283b899c2e7ed7777d4b446197cbb08c4eb1a7ca83",
    "mid": "5b6186cc7c7c59ace8d747472785df7a2d9e34b6d63e9e81146f630fcc84d049",
    "blank": "85540d502ae31d34f04a09354d54021d228f610be58f88d30013e538063b79ed",
}

# A Hungarian-shaped tile set: ``S`` and ``Z`` exist ALONGSIDE ``SZ``, which is
# what makes a joined string unsegmentable in the first place.
MULTIGRAPH_TILES: tuple[str, ...] = ("A", "Á", "CS", "DZS", "L·L", "S", "SZ", "Z")
ENGLISH_TILES: tuple[str, ...] = tuple(
    token for token in get_tile_points("english") if token != "?"
)


def _english_board() -> Board:
    return Board(get_premiums_path())


def _mid_board() -> Board:
    board = _english_board()
    for col, letter in zip(range(7, 11), "RATE"):
        board.cells[7][col].token = letter
    for row, letter in zip(range(8, 11), "OAD"):
        board.cells[row][7].token = letter
    return board


def _blank_board() -> Board:
    """RATE + a blank realizing ``S`` on the double-letter square at (7,11)."""
    board = _mid_board()
    board.cells[7][11].token = "?"
    board.cells[7][11].blank_as = "S"
    board.cells[7][11].premium_used = True
    return board


def _multigraph_board() -> Board:
    """``SZ``/``DZS`` on row 7 and a blank realizing the digraph ``CS`` on row 8."""
    board = _english_board()
    board.cells[7][7].token = "SZ"
    board.cells[7][8].token = "DZS"
    board.cells[8][7].token = "?"
    board.cells[8][7].blank_as = "CS"
    return board


def _realized_row(ai_state: dict, row: int) -> list[str | None]:
    return [ai_cell_realized_token(cell) for cell in ai_state["grid"][row]]


def _english_compact(board: Board, rack: list[str], human: int, ai: int) -> str:
    ai_state = build_ai_state_dict(
        board=board, ai_rack=rack, human_score=human, ai_score=ai, turn="AI"
    )
    return build_compact_state(
        ai_state, multigraph=has_multigraph_tile_token(ENGLISH_TILES)
    )


# --- 1. the structured shape ---------------------------------------------------


def test_ai_state_is_a_cell_grid_with_an_ordered_rack_and_no_sidecar() -> None:
    board = _english_board()
    board.cells[7][7].token = "A"
    board.cells[7][8].token = "T"
    ai = build_ai_state_dict(board, ["Q", "I"], 1, 2, "HUMAN")

    assert list(ai.keys()) == ["grid", "ai_rack", "human_score", "ai_score", "turn"]
    assert "blanks" not in ai
    assert len(ai["grid"]) == BOARD_SIZE
    assert all(len(row) == BOARD_SIZE for row in ai["grid"])
    assert ai["grid"][7][7] == {"token": "A", "blank_as": None}
    assert ai["grid"][7][8] == {"token": "T", "blank_as": None}
    assert ai["grid"][7][9] is None
    # The rack is an ORDERED ARRAY of complete tokens, never a joined string.
    assert ai["ai_rack"] == ["Q", "I"]
    assert ai["human_score"] == 1
    assert ai["ai_score"] == 2
    assert ai["turn"] == "HUMAN"


def test_multigraph_row_has_fifteen_columns_and_the_rack_keeps_boundaries() -> None:
    ai = build_ai_state_dict(_multigraph_board(), ["SZ", "DZS", "?"], 0, 0, "AI")

    # ⭐ FIFTEEN cells, not eighteen characters.
    assert len(ai["grid"][7]) == BOARD_SIZE
    assert ai["grid"][7][7] == {"token": "SZ", "blank_as": None}
    assert ai["grid"][7][8] == {"token": "DZS", "blank_as": None}
    assert ai["grid"][7][9] is None
    # The old defect, kept here as a WITNESS: joining the same row's realized
    # tokens is what produced eighteen characters and wrong column indices.
    assert len("".join(token or "." for token in _realized_row(ai, 7))) == 18
    # Three tiles stay three tiles. 'SZDZS' is `SZ`+`DZS`, or `S`+`Z`+`D`+`Z`+`S`,
    # or `SZ`+`D`+`ZS`; the array cannot be misread as any of them.
    assert ai["ai_rack"] == ["SZ", "DZS", "?"]
    assert "".join(ai["ai_rack"]) == "SZDZS?"
    assert len(ai["ai_rack"]) == 3


def test_blank_realizing_a_multigraph_no_longer_widens_its_row() -> None:
    """⭐ The blank path widened rows too, not only real multigraph tiles."""
    ai = build_ai_state_dict(_multigraph_board(), ["A"], 0, 0, "AI")

    # Blank identity lives INSIDE the cell — one fact, one home.
    assert ai["grid"][8][7] == {"token": "?", "blank_as": "CS"}
    assert ai_cell_realized_token(ai["grid"][8][7]) == "CS"
    assert len(ai["grid"][8]) == BOARD_SIZE
    # The legacy string stored the REALIZED token, so this row measured SIXTEEN
    # characters at the baseline even though only a blank had been played.
    assert len("".join(token or "." for token in _realized_row(ai, 8))) == 16


def test_malformed_blank_cell_survives_the_projection_and_is_not_empty() -> None:
    board = _english_board()
    board.cells[6][6].token = "?"
    board.cells[6][6].blank_as = None
    ai = build_ai_state_dict(board, [], 0, 0, "AI")

    assert ai["grid"][6][6] == {"token": "?", "blank_as": None}
    assert ai["grid"][6][6] is not None
    assert ai_cell_realized_token(ai["grid"][6][6]) == "?"
    # It reaches the legacy string as an occupied square plus a blank record,
    # never as an empty one.
    compact = build_compact_state(ai, multigraph=False)
    assert "blanks:[{'row': 6, 'col': 6}]" in compact
    assert compact.splitlines()[7] == "......?........"


# --- 2. the byte-frozen legacy string -----------------------------------------


def test_compact_state_bytes_are_unchanged_for_single_code_point_boards() -> None:
    cases = {
        "empty": _english_compact(
            _english_board(), ["A", "E", "I", "R", "S", "T", "?"], 0, 0
        ),
        "mid": _english_compact(
            _mid_board(), ["A", "E", "I", "N", "O", "S", "T"], 100, 120
        ),
        "blank": _english_compact(
            _blank_board(), ["?", "B", "E", "L", "O", "W", "Z"], 137, 152
        ),
    }
    for name, compact in cases.items():
        digest = hashlib.sha256(compact.encode("utf-8")).hexdigest()
        assert digest == _BASELINE_COMPACT_SHA256[name], (name, compact)

    # The `blanks:` line is DERIVED from the cells at render time, in the exact
    # repr the baseline emitted; dropping it would lose the only channel that
    # tells a model a square holds a blank rather than a real tile.
    assert "blanks:[]" in cases["empty"]
    assert "blanks:[{'row': 7, 'col': 11}]" in cases["blank"]
    assert "ai_rack:?BELOWZ" in cases["blank"]
    assert cases["blank"].startswith("grid:\n")
    assert cases["blank"].endswith("scores: H=137 AI=152\nturn:AI\n")
    assert ".......RATES...\n" in cases["blank"]


# --- 3. the multigraph serialization ------------------------------------------


def test_multigraph_compact_state_is_lossless_json() -> None:
    ai = build_ai_state_dict(_multigraph_board(), ["SZ", "DZS", "?"], 3, 4, "AI")
    compact = build_compact_state(ai, multigraph=True)

    assert compact.startswith("ai_state_json:\n")
    # ⛔ The unrepresentable concatenation must not appear anywhere.
    assert "SZDZS" not in compact
    decoded = json.loads(compact.split("\n", 1)[1])
    assert decoded["ai_rack"] == ["SZ", "DZS", "?"]
    assert len(decoded["grid"]) == BOARD_SIZE
    assert all(len(row) == BOARD_SIZE for row in decoded["grid"])
    assert decoded["grid"][7][7] == {"token": "SZ", "blank_as": None}
    assert decoded["grid"][7][8] == {"token": "DZS", "blank_as": None}
    assert decoded["grid"][8][7] == {"token": "?", "blank_as": "CS"}
    assert decoded["grid"][7][9] is None
    assert decoded["human_score"] == 3
    assert decoded["ai_score"] == 4
    assert decoded["turn"] == "AI"
    assert "blanks" not in decoded


# --- 4. the ONE predicate ------------------------------------------------------


def test_multigraph_predicate_reads_the_tile_set_not_the_board() -> None:
    assert has_multigraph_tile_token(MULTIGRAPH_TILES) is True
    assert has_multigraph_tile_token(ENGLISH_TILES) is False
    # An accented single letter is ONE code point in NFC and is not a multigraph.
    assert has_multigraph_tile_token(("A", "Á", "Ž", "Ł")) is False
    assert has_multigraph_tile_token(()) is False
    assert has_multigraph_tile_token(("CH",)) is True

    # ⭐ An EMPTY board in a multigraph variant is still a multigraph board, so
    # the serialization format cannot flip mid-game.
    empty = build_ai_state_dict(_english_board(), ["A"], 0, 0, "AI")
    assert build_compact_state(
        empty, multigraph=has_multigraph_tile_token(MULTIGRAPH_TILES)
    ).startswith("ai_state_json:\n")
    # And a board holding only single-code-point tiles in that same variant.
    single = _english_board()
    single.cells[7][7].token = "A"
    only_singles = build_ai_state_dict(single, ["S", "Z"], 0, 0, "AI")
    assert build_compact_state(
        only_singles, multigraph=has_multigraph_tile_token(MULTIGRAPH_TILES)
    ).startswith("ai_state_json:\n")


def test_every_shipped_variant_still_takes_the_byte_frozen_path() -> None:
    """No shipped language changes serialization form because of this slice."""
    variants = list_installed_variants()
    assert len(variants) == 12
    for variant in variants:
        assert has_multigraph_tile_token(variant.playable_letters) is False, variant.slug
    # Slovak `CH` is an alphabet letter that is NOT a tile, so it must not drag
    # Slovak onto the JSON path.
    slovak = load_variant("slovak")
    assert "CH" in slovak.alphabet_order
    assert "CH" not in slovak.playable_letters
    assert has_multigraph_tile_token(slovak.playable_letters) is False
