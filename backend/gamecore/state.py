"""Game state serialization for persistence and AI context."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from .board import Board
from .tiles import TileBag, get_tile_distribution


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
    grid: list[str]
    blanks: list[_Pos]
    premium_used: list[_Pos]
    player_racks: dict[str, str]
    bag: str
    scores: dict[str, int]
    current_turn: int
    variant: str
    last_move_cells: list[_Pos]
    last_move_points: int
    consecutive_passes: int
    pass_streaks: dict[str, int]
    game_over: bool
    game_end_reason: str
    seed: int


def build_save_state_dict(
    *,
    board: Board,
    player_racks: dict[str, list[str]],
    bag: TileBag,
    scores: dict[str, int],
    current_turn: int,
    last_move_cells: list[tuple[int, int]] | None = None,
    last_move_points: int = 0,
    consecutive_passes: int = 0,
    pass_streaks: dict[str, int] | None = None,
    game_over: bool = False,
    game_end_reason: str | None = None,
    seed: int = 0,
    variant_slug: str | None = None,
) -> SaveGameState:
    grid: list[str] = []
    blanks: list[_Pos] = []
    premium_used: list[_Pos] = []
    for r in range(15):
        row_chars: list[str] = []
        for c in range(15):
            cell = board.cells[r][c]
            if getattr(cell, "premium_used", False):
                premium_used.append({"row": r, "col": c})
            if cell.letter:
                row_chars.append(cell.letter)
                if cell.is_blank:
                    blanks.append({"row": r, "col": c})
            else:
                row_chars.append(".")
        grid.append("".join(row_chars))

    variant = variant_slug or getattr(bag, "variant_slug", "english")

    return SaveGameState(
        schema_version="2",
        grid=grid,
        blanks=blanks,
        premium_used=premium_used,
        player_racks={name: "".join(rack) for name, rack in player_racks.items()},
        bag="".join(bag.tiles),
        scores=scores,
        current_turn=current_turn,
        variant=str(variant),
        last_move_cells=[{"row": r, "col": c} for (r, c) in (last_move_cells or [])],
        last_move_points=last_move_points,
        consecutive_passes=consecutive_passes,
        pass_streaks=pass_streaks or {},
        game_over=game_over,
        game_end_reason=game_end_reason or "",
        seed=seed,
    )


def restore_board_from_save(state: dict[str, Any], premiums_path: str) -> Board:
    board = Board(premiums_path)
    for r in range(15):
        row = state["grid"][r]
        for c in range(15):
            ch = row[c]
            if ch != ".":
                board.cells[r][c].letter = ch
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
    bag_serialized = state.get("bag", "")
    seed = state.get("seed", 0)
    variant_slug = state.get("variant", "english")

    def _parse_bag(serialized: str) -> list[str]:
        if not serialized:
            return []
        distribution = get_tile_distribution(variant_slug)
        symbols = sorted(distribution.keys(), key=len, reverse=True)
        if "?" not in distribution:
            symbols.append("?")
        result: list[str] = []
        idx = 0
        length = len(serialized)
        while idx < length:
            matched = None
            for symbol in symbols:
                if serialized.startswith(symbol, idx):
                    matched = symbol
                    idx += len(symbol)
                    break
            if matched is None:
                matched = serialized[idx]
                idx += 1
            result.append(matched)
        return result

    letters = _parse_bag(bag_serialized)
    return TileBag(seed=seed, tiles=letters, variant=variant_slug)
