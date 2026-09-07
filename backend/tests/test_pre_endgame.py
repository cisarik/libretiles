"""Pre-endgame leave valuation (1 <= bag_remaining <= 7).

Deterministic integer heuristics: transition burden toward expected leftover,
unrepairable vowel/consonant imbalance, and the separate board-aware premium
exposure penalty.
"""

from __future__ import annotations

from gamecore.leave_equity import (
    PRE_ENDGAME_IMBALANCE_CAP_CP,
    PRE_ENDGAME_IMBALANCE_STEP_CP,
    PREMIUM_EXPOSURE_CAP_CP,
    PREMIUM_EXPOSURE_MIN_POINTS,
    leave_equity_cp,
    pre_endgame_equity_cp,
    premium_exposure_penalty_cp,
    profile_for_variant,
)
from gamecore.tiles import get_tile_points

_POINTS = get_tile_points("english")
_PROFILE = profile_for_variant("english", _POINTS)


def _pre(leave: dict[str, int], unseen: dict[str, int], bag: int, opp: int = 7) -> int:
    return pre_endgame_equity_cp(
        leave,
        unseen_tiles=unseen,
        bag_remaining=bag,
        opponent_rack_size=opp,
        profile=_PROFILE,
        tile_points=_POINTS,
    )


def test_calibration_constants_are_pinned() -> None:
    assert PRE_ENDGAME_IMBALANCE_STEP_CP == 200
    assert PRE_ENDGAME_IMBALANCE_CAP_CP == 1200
    assert PREMIUM_EXPOSURE_CAP_CP == 1500
    assert PREMIUM_EXPOSURE_MIN_POINTS == 8


def test_outside_the_window_the_ordinary_equity_is_returned() -> None:
    leave = {"A": 1, "E": 1}
    unseen = {"T": 3, "O": 2, "Q": 1}
    for bag in (0, 8, 30):
        assert _pre(leave, unseen, bag) == leave_equity_cp(
            leave, profile=_PROFILE, bag_count=bag, tile_points=_POINTS
        )
    # An empty unseen pool cannot support the deduction either.
    assert _pre(leave, {}, 3) == leave_equity_cp(
        leave, profile=_PROFILE, bag_count=3, tile_points=_POINTS
    )


def test_deterministic_integer_arithmetic() -> None:
    leave = {"Q": 1, "E": 1, "S": 1}
    unseen = {"Z": 1, "A": 3, "O": 2, "N": 2}
    first = _pre(leave, unseen, 5)
    second = _pre(leave, unseen, 5)
    assert isinstance(first, int)
    assert first == second


def test_transition_burden_punishes_heavy_leaves_more_as_bag_drains() -> None:
    heavy = {"Q": 1, "Z": 1}
    light = {"E": 1, "S": 1}
    unseen = {"A": 4, "O": 4, "T": 4}
    for bag in range(1, 8):
        assert _pre(heavy, unseen, bag) < _pre(light, unseen, bag)


def test_transition_burden_reflects_the_unseen_pool_quality() -> None:
    leave = {"E": 1, "S": 1}
    heavy_pool = {"Q": 1, "Z": 1, "X": 1, "J": 1, "K": 1, "W": 2, "V": 2}
    light_pool = {"E": 3, "A": 3, "I": 3}
    # Draws from a heavy pool leave a heavier expected final rack.
    assert _pre(leave, heavy_pool, 4) < _pre(leave, light_pool, 4)


def test_unrepairable_vowel_scarcity_is_penalized() -> None:
    consonant_leave = {"B": 1, "C": 1, "D": 1}
    vowel_pool = {"A": 4, "E": 4, "I": 4}
    dry_pool = {"B": 4, "C": 4, "D": 4}
    # Identical tile faces would be ideal, but points differ slightly; the
    # decisive signal is the imbalance penalty on the vowel-free pool.
    repairable = _pre(consonant_leave, vowel_pool, 4)
    unrepairable = _pre(consonant_leave, dry_pool, 4)
    assert unrepairable < repairable


def test_blanks_halve_the_imbalance_penalty() -> None:
    from gamecore.leave_equity import _imbalance_penalty_cp

    unseen = {"B": 6, "C": 6}
    base = _imbalance_penalty_cp(
        {"B": 1, "C": 1, "D": 1},
        unseen_tiles=unseen,
        pool_size=12,
        draws=4,
        profile=_PROFILE,
    )
    halved = _imbalance_penalty_cp(
        {"B": 1, "C": 1, "D": 1, "?": 1},
        unseen_tiles=unseen,
        pool_size=12,
        draws=4,
        profile=_PROFILE,
    )
    assert base > 0
    assert halved == base // 2


def test_balanced_leave_has_no_imbalance_penalty() -> None:
    from gamecore.leave_equity import _imbalance_penalty_cp

    assert (
        _imbalance_penalty_cp(
            {"B": 1, "A": 1},
            unseen_tiles={"B": 4, "C": 4},
            pool_size=8,
            draws=4,
            profile=_PROFILE,
        )
        == 0
    )


# ---- premium exposure ---------------------------------------------------------


def _exposure(before: int, after: int, unseen: dict[str, int], opp: int = 7) -> int:
    return premium_exposure_penalty_cp(
        before_multiplier=before,
        after_multiplier=after,
        unseen_tiles=unseen,
        opponent_rack_size=opp,
        tile_points=_POINTS,
    )


def test_premium_exposure_requires_a_strict_multiplier_increase() -> None:
    dangerous = {"Q": 1, "A": 6}
    assert _exposure(3, 3, dangerous) == 0
    assert _exposure(3, 2, dangerous) == 0
    assert _exposure(1, 3, dangerous) > 0


def test_premium_exposure_ignores_low_value_unseen_pools() -> None:
    cheap = {"A": 4, "E": 4, "T": 4}  # nothing >= 8 face points
    assert _exposure(1, 3, cheap) == 0
    # X carries exactly 8 points and crosses the threshold.
    assert _exposure(1, 3, {"X": 1, "A": 6}) > 0


def test_premium_exposure_scales_with_certainty_and_is_capped() -> None:
    # With an empty bag and a one-tile pool, the opponent holds the Q with
    # certainty: 100 x 10 points x (3 - 1) = 2000 cp, capped at 1500.
    assert _exposure(1, 3, {"Q": 1}, opp=1) == PREMIUM_EXPOSURE_CAP_CP
    # A diluted pool (1 of 8 tiles in a 1-tile rack) carries an eighth of the
    # weight: 2000 // 8 = 250 cp.
    assert _exposure(1, 3, {"Q": 1, "A": 7}, opp=1) == 250
    certain = _exposure(1, 2, {"Q": 1}, opp=1)
    diluted = _exposure(1, 2, {"Q": 1, "A": 7}, opp=1)
    assert certain > diluted > 0


def test_premium_exposure_edge_inputs_are_zero() -> None:
    assert _exposure(1, 3, {}, opp=7) == 0
    assert _exposure(1, 3, {"Q": 1}, opp=0) == 0
    # Opponent rack larger than the pool is inconsistent public data.
    assert _exposure(1, 3, {"Q": 1}, opp=2) == 0
