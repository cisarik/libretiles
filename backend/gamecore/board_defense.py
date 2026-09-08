"""Midgame board-control and defensive opportunity-cost evaluation.

Pure Python, no Django imports. The estimator scores *incremental opponent
premium opportunity* in integer centipoints. It does not compute an exact
expected reply: that would need an opponent-rack distribution and a second
search. Formed-word legality stays with ``WordAuthority.accepts_tokens``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from .board import BOARD_SIZE, Board
from .leave_equity import LeaveEquityProfile, profile_for_variant
from .tiles import get_tile_distribution, get_tile_points
from .types import Placement, Premium
from .variant_store import VariantDefinition
from .word_authority import WordAuthority

BOARD_CELLS = BOARD_SIZE * BOARD_SIZE
_ALL_BITS = (1 << BOARD_CELLS) - 1

PREMIUM_WEIGHT_CP: dict[Premium, int] = {
    Premium.TW: 1000,
    Premium.DW: 500,
    Premium.TL: 600,
}
DISTANCE_PCT: tuple[int, ...] = (100, 60, 35, 20)
MAX_CHANNEL_DISTANCE = 3
MAX_LANE_SEPARATION = 6
SUPPORT_VOWEL_PCT = 150
SUPPORT_STANDARD_PCT = 100
SUPPORT_LOW_HOOK_PCT = 50
LOW_HOOK_PARTNER_LIMIT = 4
RISK_CAP_CP = 2400
DENIAL_CAP_CP = 400
CLOSURE_CAP_CP = 200
OPENING_CAP_CP = 400
DEFENSE_PENALTY_MIN_CP = -800
DEFENSE_PENALTY_MAX_CP = 3000
LANE_OPEN_RISK_CP = 200
LANE_OPEN_VARIANCE_CP = 200
TW_TL_EXPOSE_CP = 100
ANCHOR_CLOSURE_CP = 50
MAX_LANE_RISK_COUNT = 2
MAX_TW_TL_EXPOSE_COUNT = 2
ORTHOGONAL = ((-1, 0), (1, 0), (0, -1), (0, 1))


def _cell_id(row: int, col: int) -> int:
    return BOARD_SIZE * row + col


def _row_col(cell_id: int) -> tuple[int, int]:
    return divmod(cell_id, BOARD_SIZE)


def _not_edge_masks() -> tuple[int, int]:
    not_col0 = 0
    not_col_last = 0
    last = BOARD_SIZE - 1
    for row in range(BOARD_SIZE):
        for col in range(BOARD_SIZE):
            bit = 1 << _cell_id(row, col)
            if col != 0:
                not_col0 |= bit
            if col != last:
                not_col_last |= bit
    return not_col0, not_col_last


_NOT_COL0, _NOT_COL_LAST = _not_edge_masks()


def _neighbor_mask(occ: int) -> int:
    return (
        (occ >> BOARD_SIZE)
        | ((occ << BOARD_SIZE) & _ALL_BITS)
        | ((occ & _NOT_COL0) >> 1)
        | ((occ & _NOT_COL_LAST) << 1)
    ) & _ALL_BITS


def _neighbor_ids(cell_id: int) -> tuple[int, ...]:
    row, col = _row_col(cell_id)
    found: list[int] = []
    for dr, dc in ORTHOGONAL:
        rr, cc = row + dr, col + dc
        if 0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE:
            found.append(_cell_id(rr, cc))
    return tuple(found)


_NEIGHBOR_IDS: tuple[tuple[int, ...], ...] = tuple(
    _neighbor_ids(cell) for cell in range(BOARD_CELLS)
)
_NEIGHBOR_MASK: tuple[int, ...] = tuple(
    sum(1 << nid for nid in ids) for ids in _NEIGHBOR_IDS
)


def _tile_variant(variant: object) -> VariantDefinition | str | None:
    if variant is None or isinstance(variant, (str, VariantDefinition)):
        return variant
    return None


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _segment_mask(start_id: int, end_id: int) -> int:
    r0, c0 = _row_col(start_id)
    r1, c1 = _row_col(end_id)
    mask = 0
    if r0 == r1:
        lo, hi = (c0, c1) if c0 <= c1 else (c1, c0)
        for col in range(lo, hi + 1):
            mask |= 1 << _cell_id(r0, col)
        return mask
    if c0 == c1:
        lo, hi = (r0, r1) if r0 <= r1 else (r1, r0)
        for row in range(lo, hi + 1):
            mask |= 1 << _cell_id(row, c0)
        return mask
    raise ValueError("channel is not orthogonal")


def _top_two_positive(values: Sequence[int]) -> tuple[int, int]:
    first = 0
    second = 0
    for value in values:
        if value > first:
            second = first
            first = value
        elif value > second:
            second = value
    return first, second


def _top_two_negative_magnitudes(values: Sequence[int]) -> tuple[int, int]:
    first = 0
    second = 0
    for value in values:
        if value >= 0:
            continue
        magnitude = -value
        if magnitude > first:
            second = first
            first = magnitude
        elif magnitude > second:
            second = magnitude
    return first, second


@dataclass(frozen=True)
class PostureWeights:
    w: int
    g: int
    c: int
    t: int


def posture_weights(score_differential: int) -> PostureWeights:
    """Integer posture percentages from the pre-move score difference."""
    if score_differential <= -60:
        return PostureWeights(40, 50, 0, 100)
    if score_differential <= -30:
        return PostureWeights(65, 75, 0, 50)
    if score_differential <= 29:
        return PostureWeights(100, 100, 0, 0)
    if score_differential <= 59:
        return PostureWeights(150, 150, 100, 0)
    return PostureWeights(200, 200, 200, 0)


@dataclass(frozen=True)
class _Channel:
    anchor_id: int
    dist_pct: int
    segment_mask: int
    anchor_neighbor_mask: int


@dataclass(frozen=True)
class _Premium:
    index: int
    cell_id: int
    bit: int
    weight: int
    is_tw_or_tl: bool
    channels: tuple[_Channel, ...]
    dep_cells: tuple[int, ...]


@dataclass(frozen=True)
class _Lane:
    index: int
    left: int
    right: int
    segment_mask: int
    dep_cells: tuple[int, ...]


def _hook_degrees(
    tokens: Sequence[str],
    authority: WordAuthority,
) -> dict[str, int]:
    unique = tuple(sorted(set(tokens)))
    degrees: dict[str, int] = {}
    for token in unique:
        partners = 0
        for partner in unique:
            if authority.accepts_tokens((token, partner)) or authority.accepts_tokens(
                (partner, token)
            ):
                partners += 1
        degrees[token] = partners
    return degrees


def _realized_token(placement: Placement) -> str:
    if placement.letter == "?":
        return placement.blank_as or "?"
    return placement.letter


class BoardDefenseEvaluator:
    """Fast incremental premium-exposure estimator for one ranked search.

    Preprocessing is O(board + alphabet² + premium/lane geometry). Each
    certified candidate is O(k + affected premiums + affected lanes) with no
    board copy and no secondary move generation.
    """

    def __init__(
        self,
        board: Board,
        score_differential: int,
        authority: WordAuthority,
        variant: object = None,
        *,
        tile_points: Mapping[str, int] | None = None,
    ) -> None:
        points = (
            dict(tile_points)
            if tile_points is not None
            else get_tile_points(_tile_variant(variant))
        )
        self.profile: LeaveEquityProfile = profile_for_variant(variant, points)
        self.posture = posture_weights(score_differential)
        self.evaluations = 0
        tokens = {token for token in get_tile_distribution(_tile_variant(variant)) if token != "?"}
        occupancy = 0
        vowel_mask = 0
        standard_mask = 0
        low_hook_mask = 0
        for row, cells in enumerate(board.cells):
            for col, cell in enumerate(cells):
                token = cell.realized_token
                if token is None:
                    continue
                tokens.add(token)
                bit = 1 << _cell_id(row, col)
                occupancy |= bit
        self._hook_degree = _hook_degrees(tuple(tokens), authority)
        for row, cells in enumerate(board.cells):
            for col, cell in enumerate(cells):
                token = cell.realized_token
                if token is None:
                    continue
                bit = 1 << _cell_id(row, col)
                klass = self._support_pct(token)
                if klass == SUPPORT_VOWEL_PCT:
                    vowel_mask |= bit
                elif klass == SUPPORT_LOW_HOOK_PCT:
                    low_hook_mask |= bit
                else:
                    standard_mask |= bit
        self._occ = occupancy
        self._vowel = vowel_mask
        self._standard = standard_mask
        self._low_hook = low_hook_mask
        self._anchor = _neighbor_mask(occupancy) & ~occupancy
        self._anchors_before = self._anchor.bit_count()
        self._premiums = self._build_premiums(board)
        self._lanes = self._build_lanes()
        self._prem_from_cell = self._invert_premiums()
        self._lane_from_cell = self._invert_lanes()
        self._exposure_before = tuple(
            self._premium_exposure(premium, occupancy, vowel_mask, standard_mask, low_hook_mask)
            for premium in self._premiums
        )
        self._lane_active_before = tuple(
            self._lane_is_active(
                lane,
                occupancy,
                self._exposure_before,
                self._anchor,
            )
            for lane in self._lanes
        )

    def _support_pct(self, token: str) -> int:
        if token in self.profile.vowels:
            return SUPPORT_VOWEL_PCT
        if self._hook_degree.get(token, LOW_HOOK_PARTNER_LIMIT) < LOW_HOOK_PARTNER_LIMIT:
            return SUPPORT_LOW_HOOK_PCT
        return SUPPORT_STANDARD_PCT

    def _build_premiums(self, board: Board) -> tuple[_Premium, ...]:
        found: list[_Premium] = []
        for row, cells in enumerate(board.cells):
            for col, cell in enumerate(cells):
                premium = cell.premium
                if premium not in PREMIUM_WEIGHT_CP:
                    continue
                if cell.token is not None or cell.premium_used:
                    continue
                cell_id = _cell_id(row, col)
                channels = self._channels_for(cell_id)
                dep: set[int] = set()
                for channel in channels:
                    dep.update(_segment_cell_ids(channel.segment_mask))
                    dep.update(_NEIGHBOR_IDS[channel.anchor_id])
                found.append(
                    _Premium(
                        index=len(found),
                        cell_id=cell_id,
                        bit=1 << cell_id,
                        weight=PREMIUM_WEIGHT_CP[premium],
                        is_tw_or_tl=premium in {Premium.TW, Premium.TL},
                        channels=channels,
                        dep_cells=tuple(sorted(dep)),
                    )
                )
        return tuple(found)

    def _channels_for(self, premium_id: int) -> tuple[_Channel, ...]:
        channels = [
            _Channel(
                anchor_id=premium_id,
                dist_pct=DISTANCE_PCT[0],
                segment_mask=1 << premium_id,
                anchor_neighbor_mask=_NEIGHBOR_MASK[premium_id],
            )
        ]
        pr, pc = _row_col(premium_id)
        for dr, dc in ORTHOGONAL:
            for distance in range(1, MAX_CHANNEL_DISTANCE + 1):
                rr = pr + dr * distance
                cc = pc + dc * distance
                if not (0 <= rr < BOARD_SIZE and 0 <= cc < BOARD_SIZE):
                    break
                anchor_id = _cell_id(rr, cc)
                channels.append(
                    _Channel(
                        anchor_id=anchor_id,
                        dist_pct=DISTANCE_PCT[distance],
                        segment_mask=_segment_mask(anchor_id, premium_id),
                        anchor_neighbor_mask=_NEIGHBOR_MASK[anchor_id],
                    )
                )
        return tuple(channels)

    def _build_lanes(self) -> tuple[_Lane, ...]:
        lanes: list[_Lane] = []
        premiums = self._premiums
        for i, left in enumerate(premiums):
            r0, c0 = _row_col(left.cell_id)
            for j in range(i + 1, len(premiums)):
                right = premiums[j]
                r1, c1 = _row_col(right.cell_id)
                if r0 == r1:
                    if abs(c0 - c1) > MAX_LANE_SEPARATION:
                        continue
                elif c0 == c1:
                    if abs(r0 - r1) > MAX_LANE_SEPARATION:
                        continue
                else:
                    continue
                segment = _segment_mask(left.cell_id, right.cell_id)
                dep = set(_segment_cell_ids(segment))
                for cell_id in tuple(dep):
                    dep.update(_NEIGHBOR_IDS[cell_id])
                dep.update(left.dep_cells)
                dep.update(right.dep_cells)
                lanes.append(
                    _Lane(
                        index=len(lanes),
                        left=i,
                        right=j,
                        segment_mask=segment,
                        dep_cells=tuple(sorted(dep)),
                    )
                )
        return tuple(lanes)

    def _invert_premiums(self) -> tuple[tuple[int, ...], ...]:
        buckets: list[list[int]] = [[] for _ in range(BOARD_CELLS)]
        for premium in self._premiums:
            for cell_id in premium.dep_cells:
                buckets[cell_id].append(premium.index)
        return tuple(tuple(items) for items in buckets)

    def _invert_lanes(self) -> tuple[tuple[int, ...], ...]:
        buckets: list[list[int]] = [[] for _ in range(BOARD_CELLS)]
        for lane in self._lanes:
            for cell_id in lane.dep_cells:
                buckets[cell_id].append(lane.index)
        return tuple(tuple(items) for items in buckets)

    def _premium_exposure(
        self,
        premium: _Premium,
        occ: int,
        vowel: int,
        standard: int,
        low_hook: int,
    ) -> int:
        if occ & premium.bit:
            return 0
        best = 0
        for channel in premium.channels:
            if occ & channel.segment_mask:
                continue
            neighbours = channel.anchor_neighbor_mask
            if not (neighbours & occ):
                continue
            if neighbours & vowel:
                support = SUPPORT_VOWEL_PCT
            elif neighbours & standard:
                support = SUPPORT_STANDARD_PCT
            elif neighbours & low_hook:
                support = SUPPORT_LOW_HOOK_PCT
            else:
                continue
            risk = premium.weight * channel.dist_pct * support // 10000
            if risk > best:
                best = risk
        return best

    def _lane_is_active(
        self,
        lane: _Lane,
        occ: int,
        exposures: Sequence[int],
        anchor: int,
    ) -> bool:
        if exposures[lane.left] <= 0 or exposures[lane.right] <= 0:
            return False
        if occ & lane.segment_mask:
            return False
        return (anchor & lane.segment_mask) != 0

    def defense_penalty_cp(self, placements: Sequence[Placement]) -> int:
        """Signed positional adjustment. Negative values are a bonus."""
        self.evaluations += 1
        occ = self._occ
        vowel = self._vowel
        standard = self._standard
        low_hook = self._low_hook
        placed_ids: list[int] = []
        for placement in placements:
            cell_id = _cell_id(placement.row, placement.col)
            bit = 1 << cell_id
            occ |= bit
            vowel &= ~bit
            standard &= ~bit
            low_hook &= ~bit
            klass = self._support_pct(_realized_token(placement))
            if klass == SUPPORT_VOWEL_PCT:
                vowel |= bit
            elif klass == SUPPORT_LOW_HOOK_PCT:
                low_hook |= bit
            else:
                standard |= bit
            placed_ids.append(cell_id)
        affected_premiums: set[int] = set()
        affected_lanes: set[int] = set()
        for cell_id in placed_ids:
            affected_premiums.update(self._prem_from_cell[cell_id])
            affected_lanes.update(self._lane_from_cell[cell_id])
        after_exposure = list(self._exposure_before)
        for index in affected_premiums:
            after_exposure[index] = self._premium_exposure(
                self._premiums[index], occ, vowel, standard, low_hook
            )
        deltas = [
            after_exposure[index] - self._exposure_before[index]
            for index in affected_premiums
        ]
        p1, p2 = _top_two_positive(deltas)
        n1, n2 = _top_two_negative_magnitudes(deltas)
        anchor_after = _neighbor_mask(occ) & ~occ
        newly_opened = 0
        for index in affected_lanes:
            now = self._lane_is_active(
                self._lanes[index], occ, after_exposure, anchor_after
            )
            if now and not self._lane_active_before[index]:
                newly_opened += 1
        newly_tw_tl = 0
        for index in affected_premiums:
            premium = self._premiums[index]
            if (
                premium.is_tw_or_tl
                and self._exposure_before[index] == 0
                and after_exposure[index] > 0
            ):
                newly_tw_tl += 1
        opened_lanes = min(MAX_LANE_RISK_COUNT, newly_opened)
        risk = min(
            RISK_CAP_CP,
            p1 + p2 // 2 + LANE_OPEN_RISK_CP * opened_lanes,
        )
        denial = min(DENIAL_CAP_CP, (n1 + n2 // 2) // 4)
        closure = min(
            CLOSURE_CAP_CP,
            ANCHOR_CLOSURE_CP * max(0, self._anchors_before - anchor_after.bit_count()),
        )
        opening = min(
            OPENING_CAP_CP,
            TW_TL_EXPOSE_CP * min(MAX_TW_TL_EXPOSE_COUNT, newly_tw_tl)
            + LANE_OPEN_VARIANCE_CP * min(1, newly_opened),
        )
        posture = self.posture
        return _clamp(
            (posture.w * risk) // 100
            - (posture.g * denial) // 100
            - (posture.c * closure) // 100
            - (posture.t * opening) // 100,
            DEFENSE_PENALTY_MIN_CP,
            DEFENSE_PENALTY_MAX_CP,
        )


def _segment_cell_ids(mask: int) -> tuple[int, ...]:
    if mask == 0:
        return ()
    return tuple(index for index in range(BOARD_CELLS) if mask & (1 << index))
