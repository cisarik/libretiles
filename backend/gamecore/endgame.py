"""Exact bounded out-play minimax solver for the empty-bag endgame.

With ``bag_remaining == 0`` the unseen pool IS the opponent's rack, so perfect
information holds and spread can be searched instead of estimated. The solver
runs iterative-deepening minimax with alpha-beta pruning over a PRIVATE board
copy with reversible make/unmake operations. Move generation is the ranked
search enumeration seam (every candidate re-certified through
``evaluate_scoring_move``); terminal valuation delegates to
``determine_end_reason`` and ``apply_final_scoring`` — the solver introduces no
second scoring implementation.

Budgets are strict: wall-clock deadline, minimax state expansions, retained
placements, and a capped transposition table. Exceeding any budget degrades the
result to ``bounded`` (last completed depth) — never to an illegal or invented
move. ``unavailable`` means no usable strategic analysis; the caller falls back
to the ordinary ranked search. A solver result never authorizes pass/exchange.
"""

from __future__ import annotations

import string
import time
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from .board import Board, Cell
from .game import PlayerState, apply_final_scoring, determine_end_reason
from .move_search import (
    CanonicalPlacementKey,
    RankedMoveCandidate,
    SearchStatus,
    enumerate_certified_moves,
)
from .types import Placement
from .variant_store import VariantDefinition
from .word_authority import WordAuthority

ENDGAME_MAX_ELAPSED_MS = 1250
ENDGAME_FINISH_RESERVE_MS = 50
ENDGAME_MAX_EXPANSIONS = 10_000
ENDGAME_MAX_WORK_UNITS = 500_000
ENDGAME_MAX_UNIQUE_PLACEMENTS = 25_000
ENDGAME_TT_MAX_ENTRIES = 4_096
ENDGAME_ENUM_CACHE_MAX_ENTRIES = 4_096
# Root enumeration may consume at most 60% of the time/work budget; the
# remainder funds the deepening iterations.
ENDGAME_ROOT_BUDGET_PERCENT = 60
ENDGAME_MAX_DEPTH_CEILING = 90
DEADLOCK_SCORELESS_LIMIT = 6
_INFINITY = 10**9

_TT_EXACT = 0
_TT_LOWER = 1
_TT_UPPER = 2

_ROOT = 0
_OPPONENT = 1

EndgameStrategyMode = Literal["exact", "bounded", "unavailable"]
OutInTwo = Literal["proven", "refuted", "unknown"]


class _BudgetExceeded(Exception):
    """Internal control flow: the current deepening iteration is abandoned."""


@dataclass(frozen=True)
class EndgameSearchResult:
    """Strategic endgame analysis for the acting (root) player.

    ``candidates`` are legal certified placements ordered best-first by proven
    (or last-completed-depth) additional spread; ``candidate_values`` is the
    parallel spread tuple, empty when no depth iteration completed.
    ``out_in_two`` certifies the SELECTED (first) candidate only.
    """

    strategy_mode: EndgameStrategyMode
    status: SearchStatus
    candidates: tuple[RankedMoveCandidate, ...]
    candidate_values: tuple[int, ...]
    out_in_two: OutInTwo
    completed_depth: int
    nodes: int
    elapsed_ms: int
    complete: bool
    unique_placements: int
    expansions: int


def _unavailable(*, elapsed_ms: int, nodes: int = 0, expansions: int = 0) -> EndgameSearchResult:
    return EndgameSearchResult(
        strategy_mode="unavailable",
        status="indeterminate",
        candidates=(),
        candidate_values=(),
        out_in_two="unknown",
        completed_depth=0,
        nodes=nodes,
        elapsed_ms=elapsed_ms,
        complete=False,
        unique_placements=0,
        expansions=expansions,
    )


def _copy_board(board: Board) -> Board:
    clone = Board()
    for row_index, row in enumerate(board.cells):
        for col_index, cell in enumerate(row):
            target = clone.cells[row_index][col_index]
            target.token = cell.token
            target.blank_as = cell.blank_as
            target.premium = cell.premium
            target.premium_used = cell.premium_used
    return clone


def solve_endgame(
    board: Board,
    rack: Sequence[str],
    opponent_rack: Sequence[str],
    *,
    authority: WordAuthority,
    consecutive_scoreless_turns: int = 0,
    opponent_action_rules: str = "ai_scoring",
    tile_points: Mapping[str, int] | None = None,
    blank_letters: Sequence[str] | None = None,
    variant: object = None,
    max_elapsed_ms: int = ENDGAME_MAX_ELAPSED_MS,
    max_expansions: int = ENDGAME_MAX_EXPANSIONS,
    max_unique_placements: int = ENDGAME_MAX_UNIQUE_PLACEMENTS,
) -> EndgameSearchResult:
    """Solve the empty-bag endgame for the acting player within fixed budgets."""
    if not rack or len(rack) > 7 or len(opponent_rack) > 7 or not opponent_rack:
        return _unavailable(elapsed_ms=0)
    if consecutive_scoreless_turns >= DEADLOCK_SCORELESS_LIMIT:
        return _unavailable(elapsed_ms=0)
    solver = _EndgameSolver(
        board=board,
        rack=rack,
        opponent_rack=opponent_rack,
        authority=authority,
        consecutive_scoreless_turns=consecutive_scoreless_turns,
        human_opponent=opponent_action_rules == "human_open",
        tile_points=tile_points,
        blank_letters=blank_letters,
        variant=variant,
        max_elapsed_ms=max_elapsed_ms,
        max_expansions=max_expansions,
        max_unique_placements=max_unique_placements,
    )
    return solver.solve()


class _EndgameSolver:
    def __init__(
        self,
        *,
        board: Board,
        rack: Sequence[str],
        opponent_rack: Sequence[str],
        authority: WordAuthority,
        consecutive_scoreless_turns: int,
        human_opponent: bool,
        tile_points: Mapping[str, int] | None,
        blank_letters: Sequence[str] | None,
        variant: object,
        max_elapsed_ms: int,
        max_expansions: int,
        max_unique_placements: int,
    ) -> None:
        self.board = _copy_board(board)
        self.authority = authority
        self.racks: tuple[Counter[str], Counter[str]] = (
            Counter(rack),
            Counter(opponent_rack),
        )
        self.root_scoreless = consecutive_scoreless_turns
        self.human_opponent = human_opponent
        self.tile_points = tile_points
        self.blank_letters: Sequence[str] = (
            blank_letters if blank_letters is not None else string.ascii_uppercase
        )
        self.variant = variant
        self.scoring_variant: VariantDefinition | str | None = (
            variant if isinstance(variant, (VariantDefinition, str)) else None
        )
        self.max_expansions = max_expansions
        self.max_unique_placements = max_unique_placements
        self.started = time.perf_counter()
        search_ms = max(max_elapsed_ms - ENDGAME_FINISH_RESERVE_MS, 1)
        self.deadline = self.started + search_ms / 1000.0
        self.root_deadline = self.started + (
            search_ms * ENDGAME_ROOT_BUDGET_PERCENT / 100.0
        ) / 1000.0
        # Depth ceiling: placements consume tiles and pass streaks terminate,
        # so 6 x (remaining rack tiles + 1) bounds the finite game tree.
        self.depth_ceiling = min(
            6 * (len(rack) + len(opponent_rack) + 1), ENDGAME_MAX_DEPTH_CEILING
        )

        self.expansions = 0
        self.enum_nodes = 0
        self.placements_used = 0
        self.heuristic_events = 0
        self.enumeration_capped = False
        # Placements applied since the root, for reversible state keys.
        self._trail: list[tuple[list[Placement], list[Cell]]] = []
        self._tt: dict[tuple[object, ...], tuple[int, int, int, bool]] = {}
        self._enum_cache: dict[
            tuple[object, ...], tuple[tuple[RankedMoveCandidate, ...], bool]
        ] = {}

    # ---- state plumbing ----------------------------------------------------

    def _elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def _check_budget(self) -> None:
        if time.perf_counter() >= self.deadline:
            raise _BudgetExceeded
        if self.expansions > self.max_expansions:
            raise _BudgetExceeded
        # Shared work-unit ceiling charges BOTH generator traversal nodes and
        # minimax expansions; child searches never receive renewed budgets.
        if self.enum_nodes + self.expansions > ENDGAME_MAX_WORK_UNITS:
            raise _BudgetExceeded

    def _board_key(self) -> tuple[tuple[int, int, str, str], ...]:
        return tuple(
            sorted(
                (item.row, item.col, item.letter, item.blank_as or "")
                for placements, _cells in self._trail
                for item in placements
            )
        )

    def _rack_sequence(self, side: int) -> tuple[str, ...]:
        return tuple(sorted(self.racks[side].elements()))

    def _make(self, move: RankedMoveCandidate, side: int) -> None:
        placements = list(move.placements)
        self.board.place_letters(placements)
        consumed: list[Cell] = []
        for item in placements:
            cell = self.board.cells[item.row][item.col]
            if cell.premium is not None and not cell.premium_used:
                cell.premium_used = True
                consumed.append(cell)
        rack = self.racks[side]
        for item in placements:
            tile = "?" if item.letter == "?" else item.letter
            rack[tile] -= 1
            if rack[tile] <= 0:
                del rack[tile]
        self._trail.append((placements, consumed))

    def _unmake(self, side: int) -> None:
        placements, consumed = self._trail.pop()
        for cell in consumed:
            cell.premium_used = False
        self.board.clear_letters(placements)
        rack = self.racks[side]
        for item in placements:
            tile = "?" if item.letter == "?" else item.letter
            rack[tile] += 1

    def _end_reached(self, scoreless: int) -> bool:
        """Terminal authority: ``determine_end_reason`` on the search state."""
        return (
            determine_end_reason(
                bag_remaining=0,
                racks={
                    "root": list(self._rack_sequence(_ROOT)),
                    "opponent": list(self._rack_sequence(_OPPONENT)),
                },
                consecutive_scoreless_turns=scoreless,
                no_moves_available=False,
            )
            is not None
        )

    def _final_adjustment(self) -> int:
        """Terminal spread adjustment from the root player's perspective.

        ``apply_final_scoring`` is the ONE terminal authority: a finisher gains
        the opponent's leftover while the opponent loses it (net 2x swing); a
        deadlock subtracts each side's own leftover. Applied to zero-score
        shadow players, the score difference is exactly the adjustment.
        """
        players = [
            PlayerState(name="root", rack=list(self._rack_sequence(_ROOT))),
            PlayerState(name="opponent", rack=list(self._rack_sequence(_OPPONENT))),
        ]
        apply_final_scoring(players, variant=self.scoring_variant)
        return players[0].score - players[1].score

    # ---- move generation ---------------------------------------------------

    def _enumerate(
        self, side: int, *, root: bool = False
    ) -> tuple[tuple[RankedMoveCandidate, ...], bool]:
        key: tuple[object, ...] = (self._board_key(), side, self._rack_sequence(side))
        cached = self._enum_cache.get(key)
        if cached is not None:
            return cached
        self._check_budget()
        remaining_placements = self.max_unique_placements - self.placements_used
        if remaining_placements <= 0:
            raise _BudgetExceeded
        deadline = self.root_deadline if root else self.deadline
        remaining_ms = int((deadline - time.perf_counter()) * 1000)
        if remaining_ms <= 0:
            raise _BudgetExceeded
        remaining_work = ENDGAME_MAX_WORK_UNITS - self.enum_nodes - self.expansions
        if root:
            remaining_work = remaining_work * ENDGAME_ROOT_BUDGET_PERCENT // 100
        if remaining_work <= 0:
            raise _BudgetExceeded
        result = enumerate_certified_moves(
            self.board,
            self._rack_sequence(side),
            authority=self.authority,
            include_non_scoring=side == _OPPONENT and self.human_opponent,
            max_nodes=remaining_work,
            max_elapsed_ms=remaining_ms,
            max_unique_placements=remaining_placements,
            tile_points=self.tile_points,
            blank_letters=self.blank_letters,
            variant=self.variant,
        )
        self.enum_nodes += result.nodes
        self.placements_used += result.unique_placements
        value = (result.candidates, result.complete)
        if len(self._enum_cache) < ENDGAME_ENUM_CACHE_MAX_ENTRIES:
            self._enum_cache[key] = value
        return value

    # ---- minimax -----------------------------------------------------------

    def _search(
        self,
        side: int,
        scoreless: int,
        depth: int,
        alpha: int,
        beta: int,
        parent_forced_pass: bool,
    ) -> int:
        """Best additional spread from this position onward (root perspective)."""
        self.expansions += 1
        self._check_budget()

        if depth <= 0:
            self.heuristic_events += 1
            return self._final_adjustment()

        original_alpha, original_beta = alpha, beta
        # Board trail + both racks + side + scoreless. Action rules are
        # constant for the search, so they do not belong in the key.
        tt_key: tuple[object, ...] = (
            self._board_key(),
            self._rack_sequence(_ROOT),
            self._rack_sequence(_OPPONENT),
            side,
            scoreless,
        )
        entry = self._tt.get(tt_key)
        if entry is not None:
            entry_depth, entry_value, entry_flag, entry_heuristic = entry
            if entry_depth >= depth:
                usable = (
                    entry_flag == _TT_EXACT
                    or (entry_flag == _TT_LOWER and entry_value >= beta)
                    or (entry_flag == _TT_UPPER and entry_value <= alpha)
                )
                if usable:
                    if entry_heuristic:
                        self.heuristic_events += 1
                    return entry_value

        events_before = self.heuristic_events
        moves, complete = self._enumerate(side)
        if not complete:
            self.enumeration_capped = True
            self.heuristic_events += 1

        # Deadlock collapse: two consecutive PROVEN forced passes on an
        # unchanged board are equivalent to the six-scoreless terminal.
        forced_pass = not moves and complete
        if forced_pass and parent_forced_pass:
            return self._final_adjustment()

        maximizing = side == _ROOT
        best = -_INFINITY if maximizing else _INFINITY

        # A human opponent may pass voluntarily; an AI (and the root engine)
        # passes only when no legal placement exists — proven when the
        # enumeration was exhaustive, assumed (heuristic) after a cap.
        pass_allowed = not moves or (side == _OPPONENT and self.human_opponent)
        cutoff = False

        if pass_allowed:
            next_scoreless = scoreless + 1
            if self._end_reached(next_scoreless):
                value = self._final_adjustment()
            else:
                value = self._search(
                    1 - side, next_scoreless, depth - 1, alpha, beta, forced_pass
                )
            if maximizing:
                best = max(best, value)
                alpha = max(alpha, best)
                cutoff = best >= beta
            else:
                best = min(best, value)
                beta = min(beta, best)
                cutoff = best <= alpha

        if not cutoff:
            for move in moves:
                contrib = move.total_score if maximizing else -move.total_score
                self._make(move, side)
                try:
                    if self._end_reached(0):
                        value = contrib + self._final_adjustment()
                    else:
                        value = contrib + self._search(
                            1 - side,
                            0,
                            depth - 1,
                            alpha - contrib,
                            beta - contrib,
                            False,
                        )
                finally:
                    self._unmake(side)
                if maximizing:
                    if value > best:
                        best = value
                    alpha = max(alpha, best)
                    if best >= beta:
                        break
                else:
                    if value < best:
                        best = value
                    beta = min(beta, best)
                    if best <= alpha:
                        break

        heuristic = self.heuristic_events > events_before
        if best <= original_alpha:
            flag = _TT_UPPER
        elif best >= original_beta:
            flag = _TT_LOWER
        else:
            flag = _TT_EXACT
        if tt_key in self._tt or len(self._tt) < ENDGAME_TT_MAX_ENTRIES:
            previous = self._tt.get(tt_key)
            if previous is None or previous[0] <= depth:
                self._tt[tt_key] = (depth, best, flag, heuristic)
        return best

    # ---- out-in-two certificate ---------------------------------------------

    def _has_root_out(self) -> bool | None:
        """True/False when proven for the CURRENT board; None when capped."""
        moves, complete = self._enumerate(_ROOT)
        if any(move.rack_out for move in moves):
            return True
        return False if complete else None

    def _certify_out_in_two(self, move: RankedMoveCandidate) -> OutInTwo:
        """Certificate for the selected root move.

        "Proven" requires either an immediate out, or exhaustive coverage of
        every legal opponent reply with a legal root out-play available after
        each. A principal variation alone is insufficient; any cap yields
        "unknown".
        """
        if move.rack_out:
            return "proven"
        try:
            self._make(move, _ROOT)
            try:
                replies, complete = self._enumerate(_OPPONENT)
                if not complete:
                    return "unknown"
                unknown = False
                for reply in replies:
                    if reply.rack_out:
                        # Opponent goes out first; the guarantee fails.
                        return "refuted"
                    self._make(reply, _OPPONENT)
                    try:
                        has_out = self._has_root_out()
                    finally:
                        self._unmake(_OPPONENT)
                    if has_out is False:
                        return "refuted"
                    if has_out is None:
                        unknown = True
                # Pass replies: forced for a move-less AI opponent, always
                # voluntary for a human. The board is unchanged by a pass.
                if self.human_opponent or not replies:
                    has_out = self._has_root_out()
                    if has_out is False:
                        return "refuted"
                    if has_out is None:
                        unknown = True
                return "unknown" if unknown else "proven"
            finally:
                self._unmake(_ROOT)
        except _BudgetExceeded:
            return "unknown"

    # ---- driver --------------------------------------------------------------

    @staticmethod
    def _static_order_key(move: RankedMoveCandidate) -> tuple[object, ...]:
        return (
            -move.total_score,
            -(1 if move.rack_out else 0),
            -move.tiles_used,
            move.canonical_key,
        )

    @staticmethod
    def _value_order(
        moves: Sequence[RankedMoveCandidate],
        values: Mapping[CanonicalPlacementKey, int],
    ) -> list[RankedMoveCandidate]:
        """Best-first by proven spread; ties resolved by immediate rack-out,
        tiles consumed, then canonical placement key."""

        def key(move: RankedMoveCandidate) -> tuple[object, ...]:
            return (
                -values[move.canonical_key],
                -(1 if move.rack_out else 0),
                -move.tiles_used,
                move.canonical_key,
            )

        return sorted(moves, key=key)

    def solve(self) -> EndgameSearchResult:
        try:
            root_moves, root_complete = self._enumerate(_ROOT, root=True)
        except _BudgetExceeded:
            return _unavailable(
                elapsed_ms=self._elapsed_ms(),
                nodes=self.enum_nodes,
                expansions=self.expansions,
            )
        if not root_moves:
            return _unavailable(
                elapsed_ms=self._elapsed_ms(),
                nodes=self.enum_nodes,
                expansions=self.expansions,
            )
        if not root_complete:
            self.enumeration_capped = True

        ordered = sorted(root_moves, key=self._static_order_key)
        best_values: dict[CanonicalPlacementKey, int] | None = None
        completed_depth = 0
        exact = False

        for depth in range(1, self.depth_ceiling + 1, 2):
            self.heuristic_events = 0
            iteration_values: dict[CanonicalPlacementKey, int] = {}
            try:
                for move in ordered:
                    contrib = move.total_score
                    self._make(move, _ROOT)
                    try:
                        if self._end_reached(0):
                            value = contrib + self._final_adjustment()
                        else:
                            # Full root window: every candidate needs its TRUE
                            # value for strategic ordering, not just the best.
                            value = contrib + self._search(
                                _OPPONENT,
                                0,
                                depth - 1,
                                -_INFINITY,
                                _INFINITY,
                                False,
                            )
                    finally:
                        self._unmake(_ROOT)
                    iteration_values[move.canonical_key] = value
            except _BudgetExceeded:
                break
            best_values = iteration_values
            completed_depth = depth
            ordered = self._value_order(root_moves, iteration_values)
            if self.heuristic_events == 0 and not self.enumeration_capped:
                exact = True
                break

        candidates = tuple(ordered)
        values: tuple[int, ...] = ()
        if best_values is not None:
            values = tuple(best_values[move.canonical_key] for move in candidates)

        out_in_two: OutInTwo = "unknown"
        if candidates:
            out_in_two = self._certify_out_in_two(candidates[0])

        return EndgameSearchResult(
            strategy_mode="exact" if exact else "bounded",
            status="found",
            candidates=candidates,
            candidate_values=values,
            out_in_two=out_in_two,
            completed_depth=completed_depth,
            nodes=self.enum_nodes + self.expansions,
            elapsed_ms=self._elapsed_ms(),
            complete=root_complete,
            unique_placements=self.placements_used,
            expansions=self.expansions,
        )
