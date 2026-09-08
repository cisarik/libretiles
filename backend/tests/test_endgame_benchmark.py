"""Paired A/B late-game benchmark: identical seeds with and without late_game.

Engine-to-engine evidence for the strategic late-game stack (pre-endgame
equity + exact endgame solver): the ranked seat plays a first-witness
opponent on the SAME seed twice — once with ``late_game_enabled=False``
(legacy baseline) and once with ``True`` — under node-bound budgets, so both
arms are machine-independent and the only variable is the late-game policy.

The ordinary suite keeps a four-seed default pairing per variant; the wide
100-game acceptance (English seeds 300-349, Slovak seeds 0-49) is opt-in via
``LIBRETILES_RUN_ENDGAME_ACCEPTANCE=1`` because it runs the real searches for
many minutes.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from functools import lru_cache
from statistics import median
from time import perf_counter

import pytest

from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.fastdict import load_prefix_index
from gamecore.game import GameEndReason
from gamecore.move_search import (
    DEFAULT_MAX_NODES,
    DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
    DEFAULT_RANKED_TOP_K,
)
from gamecore.selfplay import (
    POLICY_RANKED_WITNESS_SAFE,
    POLICY_WITNESS,
    SelfPlayConfig,
    SelfPlayContext,
    simulate_engine_game,
)
from gamecore.variant_store import load_variant
from gamecore.word_authority import WordAuthority

_OPT_IN_ENV = "LIBRETILES_RUN_ENDGAME_ACCEPTANCE"
_PARITY_RANKED_MAX_NODES = 20_000
_PARITY_MAX_ELAPSED_MS = 10_000_000
_MAX_PLIES = 200
_ALLOWED_END_REASONS = {
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES.name,
}

_DEFAULT_SEEDS = {"english": (300, 301), "slovak": (0, 1)}
_WIDE_SEEDS = {"english": tuple(range(300, 350)), "slovak": tuple(range(0, 50))}


@lru_cache(maxsize=2)
def _context(variant_slug: str) -> SelfPlayContext:
    if variant_slug == "english":
        authority = WordAuthority.from_index(
            load_prefix_index(get_assets_path() / "dicts" / "collins2019.txt")
        )
        letters = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
        blanks = tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    else:
        variant = load_variant(variant_slug)
        authority = WordAuthority.for_variant(variant)
        letters = frozenset(variant.playable_letters)
        blanks = tuple(variant.playable_letters)
    return SelfPlayContext(
        authority=authority,
        letters=letters,
        blank_letters=blanks,
        premiums_path=get_premiums_path(),
    )


@dataclass(frozen=True)
class PairedGame:
    variant_slug: str
    seed: int
    strategy_slot: int
    late_game: bool
    plies: int
    spread: int
    end_reason: str
    strategic_decisions: int
    strategic_elapsed_ms: tuple[int, ...]
    ranked_out: bool


def _play(variant_slug: str, seed: int, strategy_slot: int, late_game: bool) -> PairedGame:
    policies = [POLICY_WITNESS, POLICY_WITNESS]
    policies[strategy_slot] = POLICY_RANKED_WITNESS_SAFE
    sample = simulate_engine_game(
        SelfPlayConfig(
            variant_slug=variant_slug,
            seed=seed,
            policy_id=POLICY_RANKED_WITNESS_SAFE,
            max_plies=_MAX_PLIES,
            witness_max_elapsed_ms=_PARITY_MAX_ELAPSED_MS,
            witness_max_nodes=DEFAULT_MAX_NODES,
            ranked_max_elapsed_ms=_PARITY_MAX_ELAPSED_MS,
            ranked_max_nodes=_PARITY_RANKED_MAX_NODES,
            ranked_top_k=DEFAULT_RANKED_TOP_K,
            ranked_max_unique_placements=DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
            include_pass_streak=True,
            strict_unknown_tile=None,
            player_policy_ids=(policies[0], policies[1]),
            record_trace=True,
            late_game_enabled=late_game,
        ),
        context=_context(variant_slug),
    )
    strategic = [
        event.decision.elapsed_ms
        for event in sample.trace
        if event.decision.strategy_mode is not None
    ]
    if not late_game:
        assert strategic == [], "legacy arm must never take the strategic path"
    final = sample.trace[-1].after
    scores = [final.players[0].score, final.players[1].score]
    ranked_out = (
        sample.end_reason == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name
        and not final.players[strategy_slot].rack
    )
    return PairedGame(
        variant_slug=variant_slug,
        seed=seed,
        strategy_slot=strategy_slot,
        late_game=late_game,
        plies=sample.plies,
        spread=scores[strategy_slot] - scores[1 - strategy_slot],
        end_reason=sample.end_reason,
        strategic_decisions=len(strategic),
        strategic_elapsed_ms=tuple(strategic),
        ranked_out=ranked_out,
    )


def _run_pairs(seeds_by_variant: dict[str, tuple[int, ...]], *, label: str) -> list[tuple[PairedGame, PairedGame]]:
    started = perf_counter()
    pairs: list[tuple[PairedGame, PairedGame]] = []
    for variant_slug, seeds in seeds_by_variant.items():
        for seed in seeds:
            slot = seed % 2
            off = _play(variant_slug, seed, slot, late_game=False)
            on = _play(variant_slug, seed, slot, late_game=True)
            pairs.append((off, on))
            print(
                f"{label} {variant_slug} seed={seed} slot={slot} "
                f"spread_off={off.spread:+d} spread_on={on.spread:+d} "
                f"delta={on.spread - off.spread:+d} "
                f"end_off={off.end_reason} end_on={on.end_reason} "
                f"strategic_plies={on.strategic_decisions} "
                f"ranked_out_off={off.ranked_out} ranked_out_on={on.ranked_out}",
                flush=True,
            )
    _print_summary(label, pairs, elapsed=perf_counter() - started)
    return pairs


def _print_summary(
    label: str, pairs: list[tuple[PairedGame, PairedGame]], *, elapsed: float
) -> None:
    for variant_slug in sorted({off.variant_slug for off, _on in pairs}):
        rows = [(off, on) for off, on in pairs if off.variant_slug == variant_slug]
        off_total = sum(off.spread for off, _on in rows)
        on_total = sum(on.spread for _off, on in rows)
        off_outs = sum(off.ranked_out for off, _on in rows)
        on_outs = sum(on.ranked_out for _off, on in rows)
        off_bag_empty = sum(
            off.end_reason == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name
            for off, _on in rows
        )
        on_bag_empty = sum(
            on.end_reason == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name
            for _off, on in rows
        )
        latencies = [
            ms for _off, on in rows for ms in on.strategic_elapsed_ms
        ]
        latency_line = (
            f"strategic_ms=med/max={median(latencies):g}/{max(latencies)}"
            if latencies
            else "strategic_ms=none"
        )
        print(
            f"{label}-summary {variant_slug} games={len(rows)}x2 "
            f"total_spread_off={off_total:+d} total_spread_on={on_total:+d} "
            f"delta={on_total - off_total:+d} "
            f"ranked_out_off/on={off_outs}/{on_outs} "
            f"bag_empty_off/on={off_bag_empty}/{on_bag_empty} "
            f"{latency_line} elapsed={elapsed:.1f}s",
            flush=True,
        )


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("LIBRETILES_RUN_BENCHMARKS") != "1",
    reason="set LIBRETILES_RUN_BENCHMARKS=1 to run full game simulation benchmarks",
)
def test_default_paired_benchmark_terminates_and_engages_the_late_game() -> None:
    pairs = _run_pairs(_DEFAULT_SEEDS, label="endgame-ab-default")

    for off, on in pairs:
        assert off.end_reason in _ALLOWED_END_REASONS
        assert on.end_reason in _ALLOWED_END_REASONS
        assert 0 < off.plies <= _MAX_PLIES
        assert 0 < on.plies <= _MAX_PLIES
    # The strategic path must actually engage somewhere in the cohort.
    assert any(on.strategic_decisions > 0 for _off, on in pairs)
    # BAG_EMPTY_AND_PLAYER_OUT completions exist in the late-game arm.
    assert any(
        on.end_reason == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name
        for _off, on in pairs
    )


test_default_paired_endgame_benchmark_terminates_and_reaches_player_out = (
    test_default_paired_benchmark_terminates_and_engages_the_late_game
)


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get("LIBRETILES_RUN_BENCHMARKS") != "1",
    reason="set LIBRETILES_RUN_BENCHMARKS=1 to run full game simulation benchmarks",
)
def test_default_paired_benchmark_is_deterministic() -> None:
    first = _play("english", 300, 0, late_game=True)
    second = _play("english", 300, 0, late_game=True)
    # Wall-clock milliseconds are load-sensitive; every machine-independent
    # field of the paired sample must still match byte-for-byte.
    assert first.strategic_elapsed_ms != ()
    assert second.strategic_elapsed_ms != ()
    assert len(first.strategic_elapsed_ms) == len(second.strategic_elapsed_ms)
    assert first == replace(second, strategic_elapsed_ms=first.strategic_elapsed_ms)


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get(_OPT_IN_ENV) != "1",
    reason=f"set {_OPT_IN_ENV}=1 for the 100-seed late-game acceptance",
)
def test_paired_acceptance_shows_spread_expansion() -> None:
    pairs = _run_pairs(_WIDE_SEEDS, label="endgame-ab-acceptance")

    assert len(pairs) == 100
    for off, on in pairs:
        assert off.end_reason in _ALLOWED_END_REASONS
        assert on.end_reason in _ALLOWED_END_REASONS
    on_total = sum(on.spread for _off, on in pairs)
    off_total = sum(off.spread for off, _on in pairs)
    on_outs = sum(
        on.end_reason == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name
        for _off, on in pairs
    )
    assert on_total > 0
    assert on_outs > 0
    # The whole point of the slice: strategic late-game play expands the
    # aggregate spread of the ranked seat against the fixed witness baseline.
    assert on_total > off_total
