"""Game state serialization for persistence and AI context."""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any, Literal, TypedDict

from .board import BOARD_SIZE, Board
from .tiles import TileBag
from .types import BLANK_TOKEN


class AICell(TypedDict):
    """ONE board square as the AI projection carries it.

    Deliberately the SAME SHAPE the game-state wire already uses
    (``frontend/src/lib/types.ts`` ``BoardCell``) and the same shape Slice A
    persists: ``token`` is the ATOMIC tile token and may be several code
    points (``SZ``, ``DZS``, ``L·L``); ``blank_as`` is what a blank was played
    as, or ``None``. A third encoding of one board is how the concatenated
    ``list[str]`` grid came to lie about column indices.
    """

    token: str
    blank_as: str | None


class AIState(TypedDict, total=False):
    """The AI projection: a 15x15 CELL grid and an ORDERED rack of tokens.

    ⛔ There is no ``blanks`` sidecar. Blank identity lives inside the cell,
    so one fact has exactly one home. The legacy human-readable
    ``compact_state`` string still carries a ``blanks:`` line, but that line is
    DERIVED at render time by :func:`build_compact_state` rather than stored.
    """

    grid: list[list[AICell | None]]
    ai_rack: list[str]
    human_score: int
    ai_score: int
    turn: Literal["HUMAN", "AI"]


def build_ai_state_dict(
    board: Board,
    ai_rack: list[str],
    human_score: int,
    ai_score: int,
    turn: Literal["HUMAN", "AI"],
) -> AIState:
    """Project the board and the AI rack losslessly. Signature unchanged.

    ⛔ NOT the save path: ``build_save_state_dict`` below owns save schema 4
    and its external representation, and keeps its joined-token grid plus
    ``blanks`` sidecar untouched.
    """
    grid: list[list[AICell | None]] = []
    for r in range(BOARD_SIZE):
        row: list[AICell | None] = []
        for c in range(BOARD_SIZE):
            cell = board.cells[r][c]
            token = cell.token
            if token is None:
                row.append(None)
            else:
                row.append(AICell(token=token, blank_as=cell.blank_as))
        grid.append(row)

    return AIState(
        grid=grid,
        ai_rack=list(ai_rack),
        human_score=human_score,
        ai_score=ai_score,
        turn=turn,
    )


def ai_cell_realized_token(cell: AICell | None) -> str | None:
    """Lexical occupant of one AI cell: the blank's assignment, else the token.

    Mirrors ``Cell.realized_token``. A malformed blank (``"?"`` with no
    assignment) realizes as ``"?"`` — occupied, never a word, and never
    mistaken for an empty square.
    """
    if cell is None:
        return None
    token = cell["token"]
    blank_as = cell["blank_as"]
    if token == BLANK_TOKEN and blank_as is not None:
        return blank_as
    return token


def has_multigraph_tile_token(tile_tokens: Iterable[str]) -> bool:
    """THE multigraph predicate. True when any tile token is >1 code point.

    ⚠ ONE definition, in one place. Callers pass the VARIANT'S TILE SET
    (``VariantDefinition.playable_letters``), never the current board
    contents: a Hungarian board that happens to hold only single-code-point
    tiles is still a Hungarian board, and a serialization format that flipped
    with the board would hand the model two different board dialects inside
    one game.

    ``len(token)`` counts code points, which is exactly the tile width here
    because ``variant_store._parse_asset_token`` refuses a non-NFC manifest.
    It is never a tile count.
    """
    return any(len(token) > 1 for token in tile_tokens)


def build_compact_state(ai_state: AIState, *, multigraph: bool) -> str:
    """The human-readable convenience projection of :class:`AIState`.

    ⛔ For a single-code-point tile set the bytes are FROZEN: twelve shipped
    languages send prompts through this string, so the joined rows, the
    derived ``blanks:`` line, the joined ``ai_rack:`` and the ``scores:`` /
    ``turn:`` lines are reproduced exactly as they were before the AI state
    became structured.

    ⇒ For a multigraph tile set the concatenated form is UNREPRESENTABLE — one
    two-code-point token would occupy two columns and every later column index
    would be wrong — so the structured state is serialized as JSON instead,
    preserving cells, blank identity and rack boundaries. ``ai_state`` travels
    beside this string in the payload and is the authoritative copy either way.
    """
    if multigraph:
        return "ai_state_json:\n" + json.dumps(ai_state, ensure_ascii=False) + "\n"

    rows: list[str] = []
    blanks: list[dict[str, int]] = []
    for r, grid_row in enumerate(ai_state["grid"]):
        row_chars: list[str] = []
        for c, cell in enumerate(grid_row):
            realized = ai_cell_realized_token(cell)
            if realized:
                row_chars.append(realized)
                if cell is not None and cell["token"] == BLANK_TOKEN:
                    blanks.append({"row": r, "col": c})
            else:
                row_chars.append(".")
        rows.append("".join(row_chars))

    return (
        "grid:\n"
        + "\n".join(rows)
        + f"\nblanks:{blanks}\n"
        f"ai_rack:{''.join(ai_state['ai_rack'])}\n"
        f"scores: H={ai_state['human_score']} AI={ai_state['ai_score']}\n"
        f"turn:{ai_state['turn']}\n"
    )


class _Pos(TypedDict):
    row: int
    col: int


class SaveGameState(TypedDict, total=False):
    schema_version: str
    grid: list[list[str | None]]
    blanks: list[_Pos]
    premium_used: list[_Pos]
    player_racks: dict[str, list[str]]
    bag: list[str]
    scores: dict[str, int]
    current_turn: int
    variant: str
    last_move_cells: list[_Pos]
    last_move_points: int
    consecutive_scoreless_turns: int
    pass_streaks: dict[str, int]
    game_over: bool
    game_end_reason: str
    seed: int


def _require_schema_4(state: dict[str, Any]) -> None:
    version = state.get("schema_version")
    if version != "4":
        raise ValueError(
            f"Unsupported save schema_version {version!r}; only schema '4' is accepted"
        )


def build_save_state_dict(
    *,
    board: Board,
    player_racks: dict[str, list[str]],
    bag: TileBag,
    scores: dict[str, int],
    current_turn: int,
    last_move_cells: list[tuple[int, int]] | None = None,
    last_move_points: int = 0,
    consecutive_scoreless_turns: int = 0,
    pass_streaks: dict[str, int] | None = None,
    game_over: bool = False,
    game_end_reason: str | None = None,
    seed: int = 0,
    variant_slug: str | None = None,
) -> SaveGameState:
    grid: list[list[str | None]] = []
    blanks: list[_Pos] = []
    premium_used: list[_Pos] = []
    for r in range(15):
        row: list[str | None] = []
        for c in range(15):
            cell = board.cells[r][c]
            if cell.premium_used:
                premium_used.append({"row": r, "col": c})
            realized = cell.realized_token
            if realized is not None:
                # ⛔ SAVE-FILE SCHEMA UNCHANGED: the grid still carries the
                # REALIZED token and blank identity still travels in the sidecar
                # list. Only the in-memory cell was inverted.
                row.append(realized)
                if cell.is_blank:
                    blanks.append({"row": r, "col": c})
            else:
                row.append(None)
        grid.append(row)

    variant = variant_slug or getattr(bag, "variant_slug", "english")

    return SaveGameState(
        schema_version="4",
        grid=grid,
        blanks=blanks,
        premium_used=premium_used,
        player_racks={name: list(rack) for name, rack in player_racks.items()},
        bag=list(bag.tiles),
        scores=scores,
        current_turn=current_turn,
        variant=str(variant),
        last_move_cells=[{"row": r, "col": c} for (r, c) in (last_move_cells or [])],
        last_move_points=last_move_points,
        consecutive_scoreless_turns=consecutive_scoreless_turns,
        pass_streaks=pass_streaks or {},
        game_over=game_over,
        game_end_reason=game_end_reason or "",
        seed=seed,
    )


def read_consecutive_scoreless_turns(state: dict[str, Any]) -> int:
    """Read the current key while accepting the legacy schema-v2 save key."""
    value = state.get("consecutive_scoreless_turns", state.get("consecutive_passes", 0))
    return int(value)


def restore_board_from_save(state: dict[str, Any], premiums_path: str) -> Board:
    _require_schema_4(state)
    board = Board(premiums_path)
    grid = state.get("grid")
    if not isinstance(grid, list) or len(grid) != 15:
        raise ValueError("schema 4 grid must be a 15×15 token matrix")
    for r in range(15):
        row = grid[r]
        if isinstance(row, str) or not isinstance(row, list) or len(row) != 15:
            raise ValueError("schema 4 grid must be a 15×15 token matrix")
        for c in range(15):
            cell_val = row[c]
            if cell_val is None or cell_val == "":
                continue
            if not isinstance(cell_val, str):
                raise ValueError("schema 4 cell must be a token string or empty")
            # The saved grid holds the REALIZED token; the sidecar below decides
            # which of those squares was physically a blank.
            board.cells[r][c].token = cell_val
            board.cells[r][c].blank_as = None
    for pos in state.get("blanks", []):
        rr, cc = pos["row"], pos["col"]
        cell = board.cells[rr][cc]
        if cell.token is not None:
            cell.blank_as = cell.token
            cell.token = BLANK_TOKEN
    for pos in state.get("premium_used", []):
        rr, cc = pos["row"], pos["col"]
        board.cells[rr][cc].premium_used = True
    return board


def restore_bag_from_save(state: dict[str, Any]) -> TileBag:
    _require_schema_4(state)
    bag_tiles = state.get("bag")
    if not isinstance(bag_tiles, list) or not all(isinstance(tok, str) for tok in bag_tiles):
        raise ValueError("schema 4 bag must be a list of tile tokens")
    seed = state.get("seed", 0)
    variant_slug = state.get("variant", "english")
    if bag_tiles:
        return TileBag(seed=seed, tiles=list(bag_tiles), variant=variant_slug)
    bag = TileBag(seed=seed, variant=variant_slug)
    bag.draw(bag.remaining())
    return bag
