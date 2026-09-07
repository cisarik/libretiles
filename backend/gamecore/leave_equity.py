"""Rack Leave Equity valuation in integer centipoints (1 point = 100 cp).

Pure Python, no Django imports. The ranked move search combines a candidate's
immediate score with the equity of the tiles it keeps (the "leave"), so the
engine stops dumping its best rack tiles for one or two extra points.

All arithmetic is integer-only to preserve byte-for-byte determinism of the
ranked search. Values are calibration data, not architecture: the strength
benchmark matrix is the acceptance authority for any re-tuning.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from math import comb

from .tiles import _resolve_variant
from .variant_store import VariantDefinition

CENTIPOINTS_PER_POINT = 100
BLANK_EQUITY_CP = 2500
EQUITY_MIN_CP = -3000
EQUITY_MAX_CP = 6000
SYNERGY_MIN_CP = -800
SYNERGY_MAX_CP = 800

# Pre-endgame calibration (1 <= bag_remaining <= 7). Frozen by tests; any
# retuning must re-run the fixed benchmark comparison.
PRE_ENDGAME_RACK_CAPACITY = 7
PRE_ENDGAME_IMBALANCE_STEP_CP = 200
PRE_ENDGAME_IMBALANCE_CAP_CP = 1200
PREMIUM_EXPOSURE_CAP_CP = 1500
PREMIUM_EXPOSURE_MIN_POINTS = 8

# Vowel/consonant balance penalty, indexed [non_blank_leave_size][vowel_count].
# The optimum sits at ~40-50% vowels; all-vowel and all-consonant leaves are
# heavily punished. Each blank in the leave halves the penalty (wildcards
# repair either imbalance direction).
BALANCE_CP: tuple[tuple[int, ...], ...] = (
    (0,),
    (0, 0),
    (-100, 0, -150),
    (-300, 0, -100, -450),
    (-600, -100, 0, -300, -800),
    (-1000, -300, 0, -150, -700, -1200),
    (-1500, -500, -100, -50, -400, -900, -1800),
)

_STANDARD_DUPLICATE_PENALTIES_CP: dict[str, int] = {
    "vowel": -75,
    "consonant": -125,
    "blank": -1000,
}

_ENGLISH_TILE_EQUITY_CP: dict[str, int] = {
    "?": BLANK_EQUITY_CP,
    "S": 800, "E": 350, "R": 150, "X": 150,
    "A": 100, "H": 100, "N": 50, "M": 50, "C": 0, "T": 0,
    "D": -50, "K": -50, "L": -50, "P": -50, "I": -100,
    "O": -150, "G": -200, "Y": -200, "J": -250, "F": -250,
    "B": -300, "Z": -300, "W": -350, "U": -450, "V": -550, "Q": -700,
}

_ENGLISH_VOWELS = frozenset("AEIOU")

_ENGLISH_SYNERGY_CP: dict[frozenset[str], int] = {
    frozenset({"Q", "U"}): 600,
    frozenset({"E", "R"}): 75,
    frozenset({"?", "S"}): 100,
    frozenset({"S", "T"}): 50,
    frozenset({"E", "S"}): 50,
    frozenset({"I", "N"}): 50,
    frozenset({"A", "N"}): 40,
    frozenset({"E", "D"}): 40,
}

_ENGLISH_DUPLICATE_PENALTIES_CP: dict[str, int] = {
    **_STANDARD_DUPLICATE_PENALTIES_CP,
    "S": -300,
}

_SLOVAK_TILE_EQUITY_CP: dict[str, int] = {
    "?": BLANK_EQUITY_CP,
    "A": 150, "E": 150, "S": 150, "T": 150,
    "O": 100, "I": 100, "N": 100, "R": 100,
    "V": 50, "M": 50, "D": 50, "L": 50, "K": 0, "P": 0, "U": -50,
    "J": -100, "Á": -100, "C": -150, "H": -150, "Z": -150, "Í": -150,
    "B": -200, "Š": -200, "Y": -250, "Č": -250, "Ž": -250, "Ý": -300,
    "Ľ": -350, "Ť": -350, "Ú": -350, "É": -400, "Ň": -400, "Ô": -400,
    "Ď": -450, "F": -450, "G": -450, "Ó": -550,
    "Ä": -600, "Ĺ": -600, "Ŕ": -600, "X": -650,
}

# Slovak Y/Ý are vowels; syllabic Ĺ/Ŕ stay consonants.
_SLOVAK_VOWELS = frozenset("AÁÄEÉIÍOÓÔUÚYÝ")

_SLOVAK_SYNERGY_CP: dict[frozenset[str], int] = {
    frozenset({"O", "V"}): 50,
    frozenset({"S", "T"}): 50,
    frozenset({"N", "I"}): 40,
    frozenset({"E", "N"}): 40,
    frozenset({"A", "K"}): 40,
    frozenset({"P", "R"}): 40,
}


@dataclass(frozen=True)
class LeaveEquityProfile:
    variant_slug: str
    tile_equity_cp: Mapping[str, int]
    vowels: frozenset[str]
    balance_cp: Sequence[Sequence[int]]
    duplicate_penalties_cp: Mapping[str, int]
    synergy_pairs_cp: Mapping[frozenset[str], int]


@dataclass(frozen=True)
class _CuratedTables:
    tile_equity_cp: Mapping[str, int]
    vowels: frozenset[str]
    duplicate_penalties_cp: Mapping[str, int]
    synergy_pairs_cp: Mapping[frozenset[str], int]


# Curated calibration is DATA keyed by slug, not a language branch: gamecore
# behaviour stays uniform and only the valuation table differs per tile set.
_CURATED_TABLES: dict[str, _CuratedTables] = {
    "english": _CuratedTables(
        tile_equity_cp=_ENGLISH_TILE_EQUITY_CP,
        vowels=_ENGLISH_VOWELS,
        duplicate_penalties_cp=_ENGLISH_DUPLICATE_PENALTIES_CP,
        synergy_pairs_cp=_ENGLISH_SYNERGY_CP,
    ),
    "slovak": _CuratedTables(
        tile_equity_cp=_SLOVAK_TILE_EQUITY_CP,
        vowels=_SLOVAK_VOWELS,
        duplicate_penalties_cp=_STANDARD_DUPLICATE_PENALTIES_CP,
        synergy_pairs_cp=_SLOVAK_SYNERGY_CP,
    ),
}


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _nfkd_base_is_aeiou(token: str) -> bool:
    decomposed = unicodedata.normalize("NFKD", token)
    base = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return len(base) == 1 and base.upper() in {"A", "E", "I", "O", "U"}


def _resolve(variant: object) -> VariantDefinition:
    if isinstance(variant, VariantDefinition):
        return variant
    if isinstance(variant, str):
        return _resolve_variant(variant)
    return _resolve_variant(None)


def _declared_vowels(variant: object) -> frozenset[str] | None:
    """Non-empty ``vowels`` on the ORIGINAL argument, or None.

    Production callers pass slug strings, which have no ``vowels`` attribute,
    so curated profiles keep their curated vowel sets. A caller that hands over
    a variant OBJECT gets exactly that object's declared vowels honored.
    """
    raw = getattr(variant, "vowels", None)
    if not raw:
        return None
    return frozenset(str(token) for token in raw)


def _fallback_tile_equity_cp(
    resolved: VariantDefinition,
    tile_points: Mapping[str, int],
    vowels: frozenset[str],
) -> dict[str, int]:
    manifest_points = resolved.tile_points
    equity: dict[str, int] = {}
    for token, count in resolved.distribution.items():
        if token == "?":
            equity[token] = BLANK_EQUITY_CP
            continue
        points = int(tile_points.get(token, manifest_points.get(token, 0)))
        if token in vowels:
            equity[token] = _clamp(200 - 80 * (points - 1), -400, 200)
        else:
            equity[token] = _clamp(
                150 - 80 * (points - 1) + 25 * min(count - 1, 5), -700, 300
            )
    equity.setdefault("?", BLANK_EQUITY_CP)
    return equity


def profile_for_variant(
    variant: object,
    tile_points: Mapping[str, int],
) -> LeaveEquityProfile:
    """Build the leave-equity profile for one search.

    Declared vowels on the passed variant OBJECT take priority over every
    curated or derived vowel set. Tile equity, synergy, and duplicate classes
    follow the resolved slug: curated english/slovak tables, or a universal
    derivation from the manifest for every other variant.
    """
    declared = _declared_vowels(variant)
    resolved = _resolve(variant)
    slug = resolved.slug
    curated = _CURATED_TABLES.get(slug)
    if curated is not None:
        return LeaveEquityProfile(
            variant_slug=slug,
            tile_equity_cp=curated.tile_equity_cp,
            vowels=declared if declared is not None else curated.vowels,
            balance_cp=BALANCE_CP,
            duplicate_penalties_cp=curated.duplicate_penalties_cp,
            synergy_pairs_cp=curated.synergy_pairs_cp,
        )
    if declared is not None:
        vowels = declared
    else:
        vowels = frozenset(
            token
            for token in resolved.distribution
            if token != "?" and _nfkd_base_is_aeiou(token)
        )
    return LeaveEquityProfile(
        variant_slug=slug,
        tile_equity_cp=_fallback_tile_equity_cp(resolved, tile_points, vowels),
        vowels=vowels,
        balance_cp=BALANCE_CP,
        duplicate_penalties_cp=_STANDARD_DUPLICATE_PENALTIES_CP,
        synergy_pairs_cp={},
    )


def _duplicate_class(token: str, profile: LeaveEquityProfile) -> int:
    penalties = profile.duplicate_penalties_cp
    if token == "?":
        return penalties.get("blank", 0)
    exact = penalties.get(token)
    if exact is not None:
        return exact
    if token in profile.vowels:
        return penalties.get("vowel", 0)
    return penalties.get("consonant", 0)


def leave_equity_cp(
    leave: Mapping[str, int],
    *,
    profile: LeaveEquityProfile,
    bag_count: int,
    tile_points: Mapping[str, int],
) -> int:
    """Equity of a kept rack multiset, in integer centipoints.

    With an empty bag there are no redraws: balance, duplicates, and synergy
    are meaningless, and the leave is pure leftover burden aligned with final
    scoring (leftover face points are subtracted at game end).
    """
    if bag_count == 0:
        return -CENTIPOINTS_PER_POINT * sum(
            tile_points.get(token, 0) * count for token, count in leave.items()
        )

    total = 0
    for token, count in leave.items():
        total += profile.tile_equity_cp.get(token, 0) * count

    blanks = leave.get("?", 0)
    non_blank = sum(count for token, count in leave.items() if token != "?")
    vowel_count = sum(
        count for token, count in leave.items() if token != "?" and token in profile.vowels
    )
    row = profile.balance_cp[min(non_blank, len(profile.balance_cp) - 1)]
    penalty = row[min(vowel_count, len(row) - 1)]
    total += penalty // (2 ** blanks)

    for token, count in leave.items():
        if count >= 2:
            per_copy = _duplicate_class(token, profile)
            total += per_copy * (count - 1) + per_copy * max(count - 2, 0)

    synergy = 0
    for pair, bonus in profile.synergy_pairs_cp.items():
        first, second = tuple(pair)
        synergy += bonus * min(leave.get(first, 0), leave.get(second, 0))
    total += _clamp(synergy, SYNERGY_MIN_CP, SYNERGY_MAX_CP)

    return _clamp(total, EQUITY_MIN_CP, EQUITY_MAX_CP)


def _face_points(
    tiles: Mapping[str, int],
    tile_points: Mapping[str, int],
) -> int:
    return sum(tile_points.get(token, 0) * count for token, count in tiles.items())


def pre_endgame_equity_cp(
    leave: Mapping[str, int],
    *,
    unseen_tiles: Mapping[str, int],
    bag_remaining: int,
    opponent_rack_size: int,
    profile: LeaveEquityProfile,
    tile_points: Mapping[str, int],
) -> int:
    """Pre-endgame leave valuation for ``1 <= bag_remaining <= 7``, in cp.

    Heuristic by design: a nearly empty bag does NOT make draws known, so this
    blends the ordinary leave equity toward expected leftover burden and adds
    an unrepairable vowel/consonant imbalance penalty. Deterministic integer
    arithmetic only; each component is floored exactly once. Premium exposure
    is a separate board-aware penalty (``premium_exposure_penalty_cp``).
    """
    equity = leave_equity_cp(
        leave, profile=profile, bag_count=bag_remaining, tile_points=tile_points
    )
    if bag_remaining < 1 or bag_remaining > PRE_ENDGAME_RACK_CAPACITY:
        return equity

    pool_size = sum(unseen_tiles.values())
    if pool_size <= 0:
        return equity

    leave_size = sum(leave.values())
    draws = min(bag_remaining, max(PRE_ENDGAME_RACK_CAPACITY - leave_size, 0))
    bag_after = bag_remaining - draws

    # Transition burden: T = -100 * (F(L) + d * F(unseen) / N), floored once.
    face_leave = _face_points(leave, tile_points)
    face_unseen = _face_points(unseen_tiles, tile_points)
    burden_cp = -(
        CENTIPOINTS_PER_POINT * (face_leave * pool_size + draws * face_unseen)
    ) // pool_size
    transition_cp = (
        bag_after * equity + (PRE_ENDGAME_RACK_CAPACITY - bag_after) * burden_cp
    ) // PRE_ENDGAME_RACK_CAPACITY

    return transition_cp - _imbalance_penalty_cp(
        leave,
        unseen_tiles=unseen_tiles,
        pool_size=pool_size,
        draws=draws,
        profile=profile,
    )


def _imbalance_penalty_cp(
    leave: Mapping[str, int],
    *,
    unseen_tiles: Mapping[str, int],
    pool_size: int,
    draws: int,
    profile: LeaveEquityProfile,
) -> int:
    """Unrepairable vowel/consonant imbalance under a uniform unseen pool."""
    blanks = leave.get("?", 0)
    vowels = sum(
        count for token, count in leave.items() if token != "?" and token in profile.vowels
    )
    consonants = sum(
        count
        for token, count in leave.items()
        if token != "?" and token not in profile.vowels
    )
    excess = max(abs(vowels - consonants) - 1, 0)
    if excess == 0:
        return 0

    # Helpful draws repair the scarce side; blanks repair either direction.
    wants_vowels = consonants > vowels
    helpful = unseen_tiles.get("?", 0) + sum(
        count
        for token, count in unseen_tiles.items()
        if token != "?" and (token in profile.vowels) == wants_vowels
    )

    total_ways = comb(pool_size, draws)
    if total_ways <= 0:
        return 0
    missing_ways = comb(max(pool_size - helpful, 0), draws)
    penalty = (
        PRE_ENDGAME_IMBALANCE_STEP_CP * excess * missing_ways
    ) // total_ways
    penalty = min(penalty, PRE_ENDGAME_IMBALANCE_CAP_CP)
    return penalty // (1 << blanks)


def premium_exposure_penalty_cp(
    *,
    before_multiplier: int,
    after_multiplier: int,
    unseen_tiles: Mapping[str, int],
    opponent_rack_size: int,
    tile_points: Mapping[str, int],
) -> int:
    """Penalty for newly opening a word-multiplier anchor, in cp.

    Board scanning stays in the move search; this receives the largest unused
    word multiplier reachable from an empty anchor before and after the
    placement. Exposure counts only when the multiplier strictly increased,
    and only unseen tiles worth at least eight face points matter. Each such
    tile is weighted by the probability that at least one copy sits in an
    opponent rack of the known size (uniform unseen-pool assumption); the
    LARGEST weighted risk is used, capped at 1,500 cp.
    """
    increase = after_multiplier - before_multiplier
    if increase <= 0 or opponent_rack_size <= 0:
        return 0
    pool_size = sum(unseen_tiles.values())
    if pool_size <= 0 or opponent_rack_size > pool_size:
        return 0
    total_ways = comb(pool_size, opponent_rack_size)
    if total_ways <= 0:
        return 0

    worst = 0
    for token, count in unseen_tiles.items():
        points = tile_points.get(token, 0)
        if points < PREMIUM_EXPOSURE_MIN_POINTS or count <= 0:
            continue
        absent_ways = comb(max(pool_size - count, 0), opponent_rack_size)
        risk = (
            CENTIPOINTS_PER_POINT
            * points
            * increase
            * (total_ways - absent_ways)
        ) // total_ways
        worst = max(worst, risk)
    return min(worst, PREMIUM_EXPOSURE_CAP_CP)
