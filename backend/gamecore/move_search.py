"""Deterministic bounded searches for legal scoring moves.

The original witness search deliberately keeps its first-match semantics because
it is the pass/exchange safety authority.  The ranked search is a separate,
stricter quality path: it re-certifies and ranks a bounded set of legal moves,
but its result never authorizes a non-scoring action.

Both take the ONE ``WordAuthority``. Cross checks and completed prefixes are
decided over PHYSICAL TOKEN SEQUENCES; only the extension probe stays lexical,
because a prefix has no complete-word verdict to give.
"""

from __future__ import annotations

import string
import time
from collections import Counter
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from .board import BOARD_SIZE, Board
from .leave_equity import (
    LeaveEquityProfile,
    leave_equity_cp,
    pre_endgame_equity_cp,
    premium_exposure_penalty_cp,
    profile_for_variant,
)
from .legality import REASON_NON_SCORING, evaluate_scoring_move
from .tile_tracking import LateGameContext
from .tiles import get_tile_points
from .types import Direction, Placement, Premium
from .word_authority import WordAuthority

DEFAULT_MAX_NODES = 2_000_000
DEFAULT_MAX_ELAPSED_MS = 2000
DEFAULT_RANKED_TOP_K = 8
MAX_RANKED_TOP_K = 20
DEFAULT_RANKED_MAX_NODES = 500_000
DEFAULT_RANKED_MAX_ELAPSED_MS = 750
DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS = 25_000
CENTER = (7, 7)
SearchStatus = Literal["found", "none", "indeterminate"]
StrategyMode = Literal["exact", "bounded", "pre_endgame"]
OutInTwoStatus = Literal["proven", "refuted", "unknown"]
CanonicalPlacementKey = tuple[tuple[int, int, str, str], ...]
_BLANK_LETTERS = string.ascii_uppercase
_DELTA = {
    Direction.ACROSS: (0, 1),
    Direction.DOWN: (1, 0),
}
# Word multipliers a placement can newly expose to the opponent. Letter
# premiums are deliberately excluded from the pre-endgame exposure heuristic.
_WORD_PREMIUM_MULTIPLIER: dict[Premium, int] = {Premium.DW: 2, Premium.TW: 3}


@dataclass(frozen=True)
class SearchResult:
    status: SearchStatus
    witness: tuple[Placement, ...] | None
    words: tuple[str, ...]
    total_score: int
    nodes: int
    elapsed_ms: int
    complete: bool


@dataclass(frozen=True)
class RankedMoveCandidate:
    placements: tuple[Placement, ...]
    words: tuple[str, ...]
    total_score: int
    tiles_used: int
    leave_equity_cp: int
    rack_out: bool
    canonical_key: CanonicalPlacementKey


@dataclass(frozen=True)
class RankedSearchResult:
    status: SearchStatus
    candidates: tuple[RankedMoveCandidate, ...]
    nodes: int
    elapsed_ms: int
    complete: bool
    unique_placements: int
    # Late-game strategy metadata. None on the ordinary midgame path.
    strategy_mode: StrategyMode | None = None
    out_in_two: OutInTwoStatus | None = None
    completed_depth: int = 0


def find_legal_scoring_move(
    board: Board,
    rack: Sequence[str],
    *,
    authority: WordAuthority,
    max_nodes: int = DEFAULT_MAX_NODES,
    max_elapsed_ms: int = DEFAULT_MAX_ELAPSED_MS,
    blank_letters: Sequence[str] = _BLANK_LETTERS,
    variant: object = None,
) -> SearchResult:
    """Search for the first legal scoring move on `board` with `rack`."""
    searcher = _Searcher(
        board=board,
        rack=rack,
        authority=authority,
        max_nodes=max_nodes,
        max_elapsed_ms=max_elapsed_ms,
        blank_letters=blank_letters,
        variant=variant,
    )
    return searcher.run()


def find_ranked_scoring_moves(
    board: Board,
    rack: Sequence[str],
    *,
    authority: WordAuthority,
    bag_count: int,
    top_k: int = DEFAULT_RANKED_TOP_K,
    max_nodes: int = DEFAULT_RANKED_MAX_NODES,
    max_elapsed_ms: int = DEFAULT_RANKED_MAX_ELAPSED_MS,
    max_unique_placements: int = DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
    tile_points: Mapping[str, int] | None = None,
    blank_letters: Sequence[str] = _BLANK_LETTERS,
    variant: object = None,
    late_game_context: LateGameContext | None = None,
) -> RankedSearchResult:
    """Return the strongest re-certified moves found within fixed bounds.

    A capped traversal with at least one candidate is still ``found`` and safe
    to play.  With no candidate, only an exhaustive traversal returns ``none``;
    any cap returns ``indeterminate``.

    A ``late_game_context`` whose ``bag_remaining`` matches ``bag_count``
    upgrades the valuation: with an empty bag the exact endgame solver ranks
    candidates by proven spread (``strategy_mode`` "exact"/"bounded"), and with
    1..7 bag tiles the pre-endgame equity replaces the midgame leave equity
    (``strategy_mode`` "pre_endgame"). An unusable context degrades silently to
    the ordinary ranked search; it never blocks a result.
    """
    clamped_top_k = max(1, min(int(top_k), MAX_RANKED_TOP_K))
    context = late_game_context
    if context is not None and context.bag_remaining != max(0, bag_count):
        context = None

    if context is not None and context.bag_remaining == 0:
        # Local import: endgame builds on this module's enumeration seam.
        from .endgame import ENDGAME_MAX_ELAPSED_MS, solve_endgame

        opponent_rack = context.exact_opponent_rack()
        if opponent_rack is not None:
            # An explicit caller time budget is authoritative (node-bound tests
            # keep their very large elapsed limit for machine-independent
            # evidence); the ranked default upgrades to the 1,250 ms late-game
            # quality budget.
            solver_elapsed_ms = (
                max_elapsed_ms
                if max_elapsed_ms != DEFAULT_RANKED_MAX_ELAPSED_MS
                else ENDGAME_MAX_ELAPSED_MS
            )
            endgame = solve_endgame(
                board,
                rack,
                opponent_rack,
                authority=authority,
                consecutive_scoreless_turns=context.consecutive_scoreless_turns,
                opponent_action_rules=context.opponent_action_rules,
                tile_points=tile_points,
                blank_letters=blank_letters,
                variant=variant,
                max_elapsed_ms=solver_elapsed_ms,
            )
            if endgame.strategy_mode != "unavailable" and endgame.candidates:
                return RankedSearchResult(
                    status="found",
                    candidates=endgame.candidates[:clamped_top_k],
                    nodes=endgame.nodes,
                    elapsed_ms=endgame.elapsed_ms,
                    complete=endgame.complete,
                    unique_placements=endgame.unique_placements,
                    strategy_mode=endgame.strategy_mode,
                    out_in_two=endgame.out_in_two,
                    completed_depth=endgame.completed_depth,
                )
        context = None

    searcher = _RankedSearcher(
        board=board,
        rack=rack,
        authority=authority,
        bag_count=max(0, bag_count),
        top_k=clamped_top_k,
        max_nodes=max_nodes,
        max_elapsed_ms=max_elapsed_ms,
        max_unique_placements=max_unique_placements,
        tile_points=tile_points,
        blank_letters=blank_letters,
        variant=variant,
        late_game_context=context,
    )
    return searcher.run_ranked()


class _Searcher:
    def __init__(
        self,
        *,
        board: Board,
        rack: Sequence[str],
        authority: WordAuthority,
        max_nodes: int,
        max_elapsed_ms: int,
        blank_letters: Sequence[str] = _BLANK_LETTERS,
        variant: object = None,
    ) -> None:
        self.board = board
        self.grid = tuple(tuple(cell.realized_token for cell in row) for row in board.cells)
        self.authority = authority
        self.max_nodes = max_nodes
        self.max_elapsed_ms = max_elapsed_ms
        self.blank_letters = blank_letters
        self.letter_set = frozenset(blank_letters)
        self.variant = variant
        self.rack_size = len(rack)
        self.initial_rack = Counter(rack)
        self.nodes = 0
        self.capped = False
        self.found: SearchResult | None = None
        self.started = time.perf_counter()

    def run(self) -> SearchResult:
        if self.rack_size == 0 or self.max_nodes <= 0:
            return self._finish()
        if self._board_empty():
            self._search_first_move()
        else:
            self._search_connected()
        return self._finish()

    def _elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.started) * 1000)

    def _finish(self) -> SearchResult:
        elapsed = self._elapsed_ms()
        if self.found is not None:
            return SearchResult(
                status="found",
                witness=self.found.witness,
                words=self.found.words,
                total_score=self.found.total_score,
                nodes=self.nodes,
                elapsed_ms=elapsed,
                complete=not self.capped,
            )
        if self.capped or self.max_nodes <= 0:
            return SearchResult(
                status="indeterminate",
                witness=None,
                words=(),
                total_score=0,
                nodes=self.nodes,
                elapsed_ms=elapsed,
                complete=False,
            )
        return SearchResult(
            status="none",
            witness=None,
            words=(),
            total_score=0,
            nodes=self.nodes,
            elapsed_ms=elapsed,
            complete=True,
        )

    def _board_empty(self) -> bool:
        return not any(letter for row in self.grid for letter in row)

    def _inside(self, row: int, col: int) -> bool:
        return 0 <= row < BOARD_SIZE and 0 <= col < BOARD_SIZE

    def _stop(self) -> bool:
        if self.found is not None or self.capped:
            return True
        if self.nodes >= self.max_nodes:
            self.capped = True
            return True
        if self._elapsed_ms() >= self.max_elapsed_ms:
            self.capped = True
            return True
        return False

    def _touch(self) -> bool:
        if self._stop():
            return True
        self.nodes += 1
        if self.nodes > self.max_nodes:
            self.capped = True
            return True
        return False

    def _search_first_move(self) -> None:
        max_len = min(7, self.rack_size)
        if max_len < 2:
            return
        min_start = max(0, 7 - max_len + 1)
        for start_col in range(min_start, 8):
            self._extend(
                row=7,
                col=start_col,
                dr=0,
                dc=1,
                prefix=[],
                rack=self.initial_rack.copy(),
                placed=[],
                first_move=True,
            )
            if self._stop():
                return
        for start_row in range(min_start, 8):
            self._extend(
                row=start_row,
                col=7,
                dr=1,
                dc=0,
                prefix=[],
                rack=self.initial_rack.copy(),
                placed=[],
                first_move=True,
            )
            if self._stop():
                return

    def _is_anchor(self, row: int, col: int) -> bool:
        if self.grid[row][col]:
            return False
        for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            rr, cc = row + dr, col + dc
            if self._inside(rr, cc) and self.grid[rr][cc]:
                return True
        return False

    def _is_left_boundary(self, row: int, col: int, dr: int, dc: int) -> bool:
        pr, pc = row - dr, col - dc
        return not (self._inside(pr, pc) and self.grid[pr][pc])

    def _span_can_connect(self, row: int, col: int, dr: int, dc: int) -> bool:
        tiles_left = min(7, self.rack_size)
        rr, cc = row, col
        while self._inside(rr, cc) and tiles_left >= 0:
            if self.grid[rr][cc]:
                return True
            if self._is_anchor(rr, cc):
                return True
            tiles_left -= 1
            rr += dr
            cc += dc
        return False

    def _search_connected(self) -> None:
        for row in range(BOARD_SIZE):
            for col in range(BOARD_SIZE):
                for direction in (Direction.ACROSS, Direction.DOWN):
                    dr, dc = _DELTA[direction]
                    if not self._is_left_boundary(row, col, dr, dc):
                        continue
                    if not self._span_can_connect(row, col, dr, dc):
                        continue
                    self._extend(
                        row=row,
                        col=col,
                        dr=dr,
                        dc=dc,
                        prefix=[],
                        rack=self.initial_rack.copy(),
                        placed=[],
                        first_move=False,
                    )
                    if self._stop():
                        return

    def _plays(self, rack: Counter[str]) -> Iterator[tuple[str, str | None, str, Counter[str]]]:
        letters = sorted(tile for tile, count in rack.items() if count > 0 and tile != "?")
        for tile in letters:
            nxt = rack.copy()
            nxt[tile] -= 1
            if nxt[tile] <= 0:
                del nxt[tile]
            yield tile, None, tile, nxt
        if rack.get("?", 0) > 0:
            nxt = rack.copy()
            nxt["?"] -= 1
            if nxt["?"] <= 0:
                del nxt["?"]
            for letter in self.blank_letters:
                yield "?", letter, letter, nxt

    def _cross_ok(self, row: int, col: int, letter: str, dr: int, dc: int) -> bool:
        pdr, pdc = dc, dr
        rr, cc = row, col
        while self._inside(rr - pdr, cc - pdc):
            prev = self.grid[rr - pdr][cc - pdc]
            if not prev:
                break
            rr -= pdr
            cc -= pdc
        word_chars: list[str] = []
        cr, cc2 = rr, cc
        while self._inside(cr, cc2):
            if cr == row and cc2 == col:
                ch: str | None = letter
            else:
                ch = self.grid[cr][cc2]
            if not ch:
                break
            word_chars.append(ch)
            cr += pdr
            cc2 += pdc
        if len(word_chars) < 2:
            return True
        # Whole-token authority: `word_chars` is a TILE sequence, one entry per
        # square, so a digraph tile counts once.
        return self.authority.accepts_tokens(word_chars)

    def _try_complete(self, prefix: list[str], placed: list[Placement], first_move: bool) -> None:
        if not placed or len(prefix) < 2:
            return
        if first_move and not any((p.row, p.col) == CENTER for p in placed):
            return
        if not self.authority.accepts_tokens(prefix):
            return
        result = evaluate_scoring_move(
            self.board,
            list(self.initial_rack.elements()),
            placed,
            authority=self.authority,
            letters=self.letter_set,
            variant=self.variant,
        )
        if result.ok:
            self.found = SearchResult(
                status="found",
                witness=tuple(placed),
                words=result.words,
                total_score=result.total_score,
                nodes=self.nodes,
                elapsed_ms=0,
                complete=True,
            )

    def _extend(
        self,
        *,
        row: int,
        col: int,
        dr: int,
        dc: int,
        prefix: list[str],
        rack: Counter[str],
        placed: list[Placement],
        first_move: bool,
    ) -> None:
        if self._touch():
            return
        if not self._inside(row, col):
            self._try_complete(prefix, placed, first_move)
            return

        existing = self.grid[row][col]
        if existing:
            prefix.append(existing)
            if not self.authority.has_prefix("".join(prefix)):
                prefix.pop()
                return
            self._extend(
                row=row + dr,
                col=col + dc,
                dr=dr,
                dc=dc,
                prefix=prefix,
                rack=rack,
                placed=placed,
                first_move=first_move,
            )
            prefix.pop()
            return

        self._try_complete(prefix, placed, first_move)
        if self._stop() or not rack:
            return
        if first_move:
            next_center_dist = (7 - col) if dr == 0 else (7 - row)
            if next_center_dist > 0 and sum(rack.values()) < next_center_dist:
                return

        for tile, blank_as, letter, nxt_rack in self._plays(rack):
            if self._stop():
                return
            if not self._cross_ok(row, col, letter, dr, dc):
                continue
            prefix.append(letter)
            if not self.authority.has_prefix("".join(prefix)):
                prefix.pop()
                continue
            placed.append(Placement(row=row, col=col, letter=tile, blank_as=blank_as))
            self._extend(
                row=row + dr,
                col=col + dc,
                dr=dr,
                dc=dc,
                prefix=prefix,
                rack=nxt_rack,
                placed=placed,
                first_move=first_move,
            )
            placed.pop()
            prefix.pop()
            if self._stop():
                return


class _RankedSearcher(_Searcher):
    """Full traversal variant kept separate from first-witness semantics."""

    def __init__(
        self,
        *,
        board: Board,
        rack: Sequence[str],
        authority: WordAuthority,
        bag_count: int,
        top_k: int,
        max_nodes: int,
        max_elapsed_ms: int,
        max_unique_placements: int,
        tile_points: Mapping[str, int] | None,
        blank_letters: Sequence[str] = _BLANK_LETTERS,
        variant: object = None,
        late_game_context: LateGameContext | None = None,
    ) -> None:
        super().__init__(
            board=board,
            rack=rack,
            authority=authority,
            max_nodes=max_nodes,
            max_elapsed_ms=max_elapsed_ms,
            blank_letters=blank_letters,
            variant=variant,
        )
        self.rack_tiles = tuple(rack)
        self.bag_count = bag_count
        self.top_k = top_k
        self.max_unique_placements = max_unique_placements
        self.tile_points = dict(tile_points) if tile_points is not None else get_tile_points()
        self.profile: LeaveEquityProfile = profile_for_variant(variant, self.tile_points)
        self._leave_cache: dict[tuple[tuple[str, int], ...], int] = {}
        self.seen: set[CanonicalPlacementKey] = set()
        self.ranked: list[RankedMoveCandidate] = []
        # Pre-endgame valuation activates only for 1..7 bag tiles; the empty
        # bag is the endgame solver's territory, handled before construction.
        if late_game_context is not None and 1 <= late_game_context.bag_remaining <= 7:
            self.late_game_context: LateGameContext | None = late_game_context
            self._unseen_tiles: dict[str, int] = dict(late_game_context.unseen_tiles)
            self._open_word_premiums = self._collect_open_word_premiums()
            self._exposure_before = self._max_open_multiplier(
                extra_occupied=frozenset(), covered=frozenset()
            )
        else:
            self.late_game_context = None
            self._unseen_tiles = {}
            self._open_word_premiums = []
            self._exposure_before = 1

    def run_ranked(self) -> RankedSearchResult:
        if self.max_unique_placements <= 0:
            self.capped = True
            return self._ranked_finish()
        if self.rack_size == 0 or self.max_nodes <= 0:
            if self.max_nodes <= 0:
                self.capped = True
            return self._ranked_finish()
        if self._board_empty():
            self._search_first_move()
        else:
            self._search_connected()
        return self._ranked_finish()

    def _stop(self) -> bool:
        if self.capped:
            return True
        if self.nodes >= self.max_nodes:
            self.capped = True
            return True
        if self._elapsed_ms() >= self.max_elapsed_ms:
            self.capped = True
            return True
        return False

    @staticmethod
    def _canonical_key(placements: Sequence[Placement]) -> CanonicalPlacementKey:
        return tuple(
            sorted(
                (
                    placement.row,
                    placement.col,
                    placement.letter,
                    placement.blank_as or "",
                )
                for placement in placements
            )
        )

    def _calculate_leave_equity(self, placed: Sequence[Placement]) -> int:
        remaining = Counter(self.rack_tiles)
        for placement in placed:
            tile = "?" if placement.letter == "?" else placement.letter
            remaining[tile] -= 1
            if remaining[tile] <= 0:
                del remaining[tile]
        key = tuple(sorted(remaining.items()))
        cached = self._leave_cache.get(key)
        if cached is None:
            if self.late_game_context is not None:
                cached = pre_endgame_equity_cp(
                    remaining,
                    unseen_tiles=self._unseen_tiles,
                    bag_remaining=self.late_game_context.bag_remaining,
                    opponent_rack_size=self.late_game_context.opponent_rack_size,
                    profile=self.profile,
                    tile_points=self.tile_points,
                )
            else:
                cached = leave_equity_cp(
                    remaining,
                    profile=self.profile,
                    bag_count=self.bag_count,
                    tile_points=self.tile_points,
                )
            self._leave_cache[key] = cached
        return cached

    def _collect_open_word_premiums(self) -> list[tuple[int, int, int]]:
        """Empty, unconsumed DW/TW squares — the pre-endgame exposure pool."""
        squares: list[tuple[int, int, int]] = []
        for row_index, row in enumerate(self.board.cells):
            for col_index, cell in enumerate(row):
                if cell.token is not None or cell.premium_used:
                    continue
                multiplier = (
                    _WORD_PREMIUM_MULTIPLIER.get(cell.premium)
                    if cell.premium is not None
                    else None
                )
                if multiplier is not None:
                    squares.append((row_index, col_index, multiplier))
        return squares

    def _max_open_multiplier(
        self,
        *,
        extra_occupied: frozenset[tuple[int, int]],
        covered: frozenset[tuple[int, int]],
    ) -> int:
        """Largest open word multiplier on an empty anchor, floor 1.

        An anchor is an empty square adjacent to an occupied square; the
        placements under evaluation extend occupancy (``extra_occupied``) and
        may cover premium squares (``covered``).
        """
        best = 1
        for row, col, multiplier in self._open_word_premiums:
            if multiplier <= best or (row, col) in covered:
                continue
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                rr, cc = row + dr, col + dc
                if not self._inside(rr, cc):
                    continue
                if self.grid[rr][cc] or (rr, cc) in extra_occupied:
                    best = multiplier
                    break
        return best

    def _premium_exposure_cp(self, placed: Sequence[Placement]) -> int:
        context = self.late_game_context
        if context is None or not self._open_word_premiums:
            return 0
        cells = frozenset((placement.row, placement.col) for placement in placed)
        after = self._max_open_multiplier(extra_occupied=cells, covered=cells)
        return premium_exposure_penalty_cp(
            before_multiplier=self._exposure_before,
            after_multiplier=after,
            unseen_tiles=self._unseen_tiles,
            opponent_rack_size=context.opponent_rack_size,
            tile_points=self.tile_points,
        )

    @staticmethod
    def _rank_key(candidate: RankedMoveCandidate) -> tuple[object, ...]:
        return (
            -(candidate.total_score * 100 + candidate.leave_equity_cp),
            -(1 if candidate.rack_out else 0),
            -candidate.tiles_used,
            candidate.canonical_key,
        )

    def _try_complete(self, prefix: list[str], placed: list[Placement], first_move: bool) -> None:
        if self._stop() or not placed or len(prefix) < 2:
            return
        if first_move and not any((p.row, p.col) == CENTER for p in placed):
            return
        if not self.authority.accepts_tokens(prefix):
            return

        canonical_key = self._canonical_key(placed)
        if canonical_key in self.seen:
            return
        if len(self.seen) >= self.max_unique_placements:
            self.capped = True
            return

        certified = evaluate_scoring_move(
            self.board,
            self.rack_tiles,
            placed,
            authority=self.authority,
            letters=self.letter_set,
            variant=self.variant,
        )
        if not certified.ok:
            return
        self.seen.add(canonical_key)

        tiles_used = len(placed)
        equity_cp = self._calculate_leave_equity(placed) - self._premium_exposure_cp(placed)
        candidate = RankedMoveCandidate(
            placements=tuple(sorted(placed, key=lambda item: (item.row, item.col))),
            words=certified.words,
            total_score=certified.total_score,
            tiles_used=tiles_used,
            leave_equity_cp=equity_cp,
            rack_out=self.bag_count == 0 and tiles_used == len(self.rack_tiles),
            canonical_key=canonical_key,
        )
        self.ranked.append(candidate)
        self.ranked.sort(key=self._rank_key)
        if len(self.ranked) > self.top_k:
            self.ranked.pop()

    def _ranked_finish(self) -> RankedSearchResult:
        elapsed_ms = self._elapsed_ms()
        candidates = tuple(sorted(self.ranked, key=self._rank_key))
        if candidates:
            status: SearchStatus = "found"
        elif self.capped:
            status = "indeterminate"
        else:
            status = "none"
        return RankedSearchResult(
            status=status,
            candidates=candidates,
            nodes=self.nodes,
            elapsed_ms=elapsed_ms,
            complete=not self.capped,
            unique_placements=len(self.seen),
            strategy_mode="pre_endgame" if self.late_game_context is not None else None,
        )


class _ExhaustiveSearcher(_RankedSearcher):
    """Enumeration seam for the endgame solver: keep EVERY certified move.

    No top-k pruning and no leave equity — the caller values moves itself.
    ``include_non_scoring`` additionally retains legal zero-score placements
    (the evaluator's ``non_scoring`` verdict), which only simulated HUMAN
    action nodes may play.
    """

    def __init__(
        self,
        *,
        include_non_scoring: bool,
        board: Board,
        rack: Sequence[str],
        authority: WordAuthority,
        max_nodes: int,
        max_elapsed_ms: int,
        max_unique_placements: int,
        tile_points: Mapping[str, int] | None,
        blank_letters: Sequence[str] = _BLANK_LETTERS,
        variant: object = None,
    ) -> None:
        super().__init__(
            board=board,
            rack=rack,
            authority=authority,
            bag_count=0,
            top_k=1,
            max_nodes=max_nodes,
            max_elapsed_ms=max_elapsed_ms,
            max_unique_placements=max_unique_placements,
            tile_points=tile_points,
            blank_letters=blank_letters,
            variant=variant,
        )
        self.include_non_scoring = include_non_scoring

    def _try_complete(self, prefix: list[str], placed: list[Placement], first_move: bool) -> None:
        if self._stop() or not placed or len(prefix) < 2:
            return
        if first_move and not any((p.row, p.col) == CENTER for p in placed):
            return
        if not self.authority.accepts_tokens(prefix):
            return

        canonical_key = self._canonical_key(placed)
        if canonical_key in self.seen:
            return
        if len(self.seen) >= self.max_unique_placements:
            self.capped = True
            return

        certified = evaluate_scoring_move(
            self.board,
            self.rack_tiles,
            placed,
            authority=self.authority,
            letters=self.letter_set,
            variant=self.variant,
        )
        if not certified.ok and not (
            self.include_non_scoring
            and certified.reason_code == REASON_NON_SCORING
            and certified.total_score == 0
        ):
            return
        self.seen.add(canonical_key)

        tiles_used = len(placed)
        self.ranked.append(
            RankedMoveCandidate(
                placements=tuple(sorted(placed, key=lambda item: (item.row, item.col))),
                words=certified.words,
                total_score=certified.total_score,
                tiles_used=tiles_used,
                leave_equity_cp=0,
                rack_out=tiles_used == len(self.rack_tiles),
                canonical_key=canonical_key,
            )
        )

    def _ranked_finish(self) -> RankedSearchResult:
        elapsed_ms = self._elapsed_ms()
        candidates = tuple(
            sorted(
                self.ranked,
                key=lambda item: (-item.total_score, -item.tiles_used, item.canonical_key),
            )
        )
        if candidates:
            status: SearchStatus = "found"
        elif self.capped:
            status = "indeterminate"
        else:
            status = "none"
        return RankedSearchResult(
            status=status,
            candidates=candidates,
            nodes=self.nodes,
            elapsed_ms=elapsed_ms,
            complete=not self.capped,
            unique_placements=len(self.seen),
        )


def enumerate_certified_moves(
    board: Board,
    rack: Sequence[str],
    *,
    authority: WordAuthority,
    include_non_scoring: bool = False,
    max_nodes: int = DEFAULT_RANKED_MAX_NODES,
    max_elapsed_ms: int = DEFAULT_RANKED_MAX_ELAPSED_MS,
    max_unique_placements: int = DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
    tile_points: Mapping[str, int] | None = None,
    blank_letters: Sequence[str] = _BLANK_LETTERS,
    variant: object = None,
) -> RankedSearchResult:
    """Enumerate ALL certified moves for one position, without ranking.

    The endgame solver's move-generation authority: every retained candidate is
    re-certified through ``evaluate_scoring_move`` and ``complete`` reports
    whether the traversal was exhaustive. Candidates come back ordered by
    descending score (a good alpha-beta ordering), then canonical key.
    """
    searcher = _ExhaustiveSearcher(
        include_non_scoring=include_non_scoring,
        board=board,
        rack=rack,
        authority=authority,
        max_nodes=max_nodes,
        max_elapsed_ms=max_elapsed_ms,
        max_unique_placements=max_unique_placements,
        tile_points=tile_points,
        blank_letters=blank_letters,
        variant=variant,
    )
    return searcher.run_ranked()
