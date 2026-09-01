"""Game state serialization for persistence and AI context."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from .board import Board
from .tiles import TileBag


class BlankPos(TypedDict):
    row: int
    col: int


class AIState(TypedDict, total=False):
    grid: list[str]
    blanks: list[BlankPos]
    ai_rack: str
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
    grid: list[str] = []
    blanks: list[BlankPos] = []
    for r in range(15):
        row_chars: list[str] = []
        for c in range(15):
            cell = board.cells[r][c]
            if cell.letter:
                row_chars.append(cell.letter)
                if cell.is_blank:
                    blanks.append({"row": r, "col": c})
            else:
                row_chars.append(".")
        grid.append("".join(row_chars))

    return AIState(
        grid=grid,
        blanks=blanks,
        ai_rack="".join(ai_rack),
        human_score=human_score,
        ai_score=ai_score,
        turn=turn,
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
            if getattr(cell, "premium_used", False):
                premium_used.append({"row": r, "col": c})
            if cell.letter:
                row.append(cell.letter)
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
            board.cells[r][c].letter = cell_val
            board.cells[r][c].is_blank = False
    for pos in state.get("blanks", []):
        rr, cc = pos["row"], pos["col"]
        if board.cells[rr][cc].letter:
            board.cells[rr][cc].is_blank = True
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
