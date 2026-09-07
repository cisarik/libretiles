"""Rack leave equity engine: profiles, balance, synergy, endgame, clamps."""

from __future__ import annotations

from gamecore.leave_equity import (
    BALANCE_CP,
    BLANK_EQUITY_CP,
    EQUITY_MAX_CP,
    EQUITY_MIN_CP,
    LeaveEquityProfile,
    leave_equity_cp,
    profile_for_variant,
)
from gamecore.tiles import get_tile_points
from gamecore.variant_store import VariantDefinition, VariantLetter

_EN_POINTS = get_tile_points("english")
_SK_POINTS = get_tile_points("slovak")
_EN = profile_for_variant("english", _EN_POINTS)
_SK = profile_for_variant("slovak", _SK_POINTS)


def _en(leave: dict[str, int], *, bag_count: int = 50) -> int:
    return leave_equity_cp(
        leave, profile=_EN, bag_count=bag_count, tile_points=_EN_POINTS
    )


# --- profile resolution -----------------------------------------------------------


def test_english_profile_is_curated() -> None:
    assert _EN.variant_slug == "english"
    assert _EN.vowels == frozenset("AEIOU")
    assert _EN.tile_equity_cp["?"] == BLANK_EQUITY_CP == 2500
    assert _EN.tile_equity_cp["S"] == 800
    assert _EN.tile_equity_cp["Q"] == -700
    assert _EN.duplicate_penalties_cp["S"] == -300
    assert _EN.synergy_pairs_cp[frozenset({"Q", "U"})] == 600


def test_slovak_profile_is_curated_with_slovak_vowels() -> None:
    assert _SK.variant_slug == "slovak"
    assert {"Á", "Ä", "Ô", "Ý", "Y"} <= _SK.vowels
    assert {"Ĺ", "Ŕ"}.isdisjoint(_SK.vowels)
    assert _SK.tile_equity_cp["X"] == -650
    assert _SK.tile_equity_cp["A"] == 150
    assert "S" not in _SK.duplicate_penalties_cp
    assert _SK.synergy_pairs_cp[frozenset({"O", "V"})] == 50


def test_fallback_profile_derives_nfkd_vowels_and_formula_equity() -> None:
    points = get_tile_points("czech")
    profile = profile_for_variant("czech", points)
    assert profile.variant_slug == "czech"
    assert {"Á", "É", "Í", "Ů"} <= profile.vowels
    assert "Č" not in profile.vowels
    assert profile.synergy_pairs_cp == {}
    assert profile.tile_equity_cp["?"] == BLANK_EQUITY_CP
    # 1-point vowel: clamp(200 - 80*(points-1), -400, 200) == 200.
    assert points["A"] == 1
    assert profile.tile_equity_cp["A"] == 200
    for token, value in profile.tile_equity_cp.items():
        if token == "?":
            continue
        assert -700 <= value <= 300


def test_declared_vowels_take_priority_over_derivation() -> None:
    variant = VariantDefinition(
        slug="vowel-probe",
        language="Probe",
        letters=(
            VariantLetter(letter="?", count=1, points=0),
            VariantLetter(letter="Á", count=1, points=4),
            VariantLetter(letter="B", count=1, points=4),
        ),
        dictionary_file="collins2019.txt",
        alphabet_order=("Á", "B"),
        vowels=("Á",),
    )
    profile = profile_for_variant(variant, {"Á": 4, "B": 4})
    assert profile.vowels == frozenset({"Á"})
    # Declared vowel Á uses the vowel formula: clamp(200 - 80*3, -400, 200).
    assert profile.tile_equity_cp["Á"] == -40
    # B stays a consonant: clamp(150 - 80*3 + 25*min(0, 5), -700, 300).
    assert profile.tile_equity_cp["B"] == -90


# --- blank retention --------------------------------------------------------------


def test_blank_retention_beats_any_single_tile_despite_zero_face_points() -> None:
    assert _EN_POINTS["?"] == 0
    assert _en({"?": 1}) == 2500
    best_non_blank = max(
        _en({token: 1}) for token in _EN.tile_equity_cp if token != "?"
    )
    assert _en({"?": 1}) > best_non_blank


# --- synergy ----------------------------------------------------------------------


def test_q_with_u_synergy_recovers_most_of_the_dead_q() -> None:
    assert _en({"Q": 1}) == -700
    assert _en({"U": 1}) == -450
    assert _en({"Q": 1, "U": 1}) == -550
    synergy_effect = _en({"Q": 1, "U": 1}) - (_en({"Q": 1}) + _en({"U": 1}))
    assert synergy_effect == 600


# --- balance curve ----------------------------------------------------------------


def _balance_probe() -> LeaveEquityProfile:
    """Zero tile equity and zero duplicate penalties isolate the balance term."""
    return LeaveEquityProfile(
        variant_slug="probe",
        tile_equity_cp={},
        vowels=frozenset("AE"),
        balance_cp=BALANCE_CP,
        duplicate_penalties_cp={},
        synergy_pairs_cp={},
    )


def test_balance_extremes_and_blank_halving() -> None:
    profile = _balance_probe()

    def probe(leave: dict[str, int]) -> int:
        return leave_equity_cp(leave, profile=profile, bag_count=50, tile_points={})

    six_consonants = {"B": 1, "C": 1, "D": 1, "F": 1, "G": 1, "H": 1}
    assert probe(six_consonants) == -1500
    assert probe({"A": 3, "E": 3}) == -1800
    assert probe({"A": 2, "E": 1, "B": 1, "C": 1, "D": 1}) == -50
    # The probe profile zeroes tile equity and duplicate penalties, so blanks
    # contribute only their balance-halving effect here.
    assert probe({**six_consonants, "?": 1}) == -1500 // 2
    assert probe({**six_consonants, "?": 2}) == -1500 // 4
    assert probe({}) == 0


# --- duplicates -------------------------------------------------------------------


def test_duplicate_penalties_escalate_and_s_class_is_special() -> None:
    # {E:2}: 700 base, -75 duplicate, -150 all-vowel balance.
    assert _en({"E": 2}) == 475
    # {E:3}: 1050 base, -75*2 + -75*1 (third copy counts double), -450 balance.
    assert _en({"E": 3}) == 375
    # {S:2}: 1600 base, -300 S-class duplicate, -100 all-consonant balance.
    assert _en({"S": 2}) == 1200
    # {U:3}: -1350 base, -225 duplicates, -450 all-vowel balance.
    assert _en({"U": 3}) == -2025


# --- endgame mode -----------------------------------------------------------------


def test_empty_bag_switches_to_pure_leftover_burden() -> None:
    assert _en({"Q": 1}, bag_count=0) == -1000
    assert _en({"?": 1}, bag_count=0) == 0
    assert _en({"A": 1, "B": 1}, bag_count=0) == -400
    assert _en({}, bag_count=0) == 0
    # The endgame branch is unclamped leftover burden.
    assert _en({"Q": 6}, bag_count=0) == -6000
    assert _en({"Q": 1}, bag_count=1) == -700


# --- determinism and clamps -------------------------------------------------------


def test_equity_is_deterministic_integer() -> None:
    leave = {"Q": 1, "U": 1, "E": 2, "S": 1}
    first = _en(leave)
    second = _en(leave)
    assert first == second
    assert isinstance(first, int)


def test_midgame_totals_clamp_to_envelope() -> None:
    assert _en({"Q": 6}) == EQUITY_MIN_CP == -3000
    assert _en({"?": 2, "S": 3, "E": 1}) == EQUITY_MAX_CP == 6000
