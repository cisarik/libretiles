"""Paired A/B board-defense benchmark against an equal-strength ranked opponent.

Both seats use ``POLICY_RANKED_WITNESS_SAFE``. The control strategy seat keeps
board defense off; the treatment seat turns it on. The opponent is always
ranked without defense. ``late_game_enabled=True`` isolates Slice 4 from the
Slice 3 stack.

The default suite runs one paired seed per variant. The wide acceptance
(English seeds 300-349 both seats, Slovak seeds 0-9 both seats) is opt-in via
``LIBRETILES_RUN_BOARD_DEFENSE_ACCEPTANCE=1``.
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass
from functools import lru_cache
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
    SelfPlayConfig,
    SelfPlayContext,
    SelfPlaySample,
    simulate_engine_game,
)
from gamecore.variant_store import load_variant
from gamecore.word_authority import WordAuthority

_OPT_IN_ENV = "LIBRETILES_RUN_BOARD_DEFENSE_ACCEPTANCE"
_PARITY_RANKED_MAX_NODES = 20_000
_PARITY_MAX_ELAPSED_MS = 10_000_000
_MAX_PLIES = 200
_BOOTSTRAP_SEED = 4004
_BOOTSTRAP_RESAMPLES = 10_000
_ALLOWED_END_REASONS = {
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES.name,
}

_DEFAULT_SEEDS = {"english": (300,), "slovak": (0,)}
_WIDE_SEEDS = {"english": tuple(range(300, 350)), "slovak": tuple(range(0, 10))}


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
class ArmGame:
    variant_slug: str
    seed: int
    strategy_slot: int
    defense: bool
    plies: int
    spread: int
    end_reason: str
    board_control_decisions: int
    nonzero_defense_decisions: int
    own_ppt: float
    opponent_ppt: float
    leading_replies: tuple[int, ...]
    neutral_replies: tuple[int, ...]
    trailing_replies: tuple[int, ...]
    own_points: int
    opponent_points: int
    passes: int
    exchanges: int
    search_elapsed_ms: int
    search_nodes: int
    ranked_out: bool


def _defense_flags(strategy_slot: int, defense: bool) -> tuple[bool, bool]:
    flags = [False, False]
    if defense:
        flags[strategy_slot] = True
    return (flags[0], flags[1])


def _play(variant_slug: str, seed: int, strategy_slot: int, defense: bool) -> ArmGame:
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
            player_policy_ids=(POLICY_RANKED_WITNESS_SAFE, POLICY_RANKED_WITNESS_SAFE),
            record_trace=True,
            late_game_enabled=True,
            board_defense_enabled=False,
            player_board_defense_enabled=_defense_flags(strategy_slot, defense),
        ),
        context=_context(variant_slug),
    )
    return _summarize(sample, variant_slug, seed, strategy_slot, defense)


def _play_metrics(sample: SelfPlaySample, strategy_slot: int) -> tuple[
    float,
    float,
    tuple[int, ...],
    tuple[int, ...],
    tuple[int, ...],
    int,
    int,
    int,
    int,
]:
    own_points = 0
    opp_points = 0
    own_turns = 0
    opp_turns = 0
    leading: list[int] = []
    neutral: list[int] = []
    trailing: list[int] = []
    board_control = 0
    nonzero = 0
    for index, event in enumerate(sample.trace):
        acting = event.before.current_index
        awarded = event.awarded
        if acting == strategy_slot:
            own_turns += 1
            own_points += awarded
            if event.decision.strategy_mode == "board_control":
                board_control += 1
                if event.decision.defense_penalty_cp != 0:
                    nonzero += 1
                if index + 1 < len(sample.trace):
                    reply = sample.trace[index + 1]
                    if reply.before.current_index != strategy_slot:
                        players = event.before.players
                        differential = (
                            players[strategy_slot].score - players[1 - strategy_slot].score
                        )
                        if differential >= 30:
                            leading.append(reply.awarded)
                        elif differential <= -30:
                            trailing.append(reply.awarded)
                        else:
                            neutral.append(reply.awarded)
        else:
            opp_turns += 1
            opp_points += awarded
    own_ppt = own_points / own_turns if own_turns else 0.0
    opp_ppt = opp_points / opp_turns if opp_turns else 0.0
    return (
        own_ppt,
        opp_ppt,
        tuple(leading),
        tuple(neutral),
        tuple(trailing),
        board_control,
        nonzero,
        own_points,
        opp_points,
    )


def _summarize(
    sample: SelfPlaySample,
    variant_slug: str,
    seed: int,
    strategy_slot: int,
    defense: bool,
) -> ArmGame:
    (
        own_ppt,
        opp_ppt,
        leading,
        neutral,
        trailing,
        board_control,
        nonzero,
        own_points,
        opp_points,
    ) = _play_metrics(sample, strategy_slot)
    if not defense:
        assert board_control == 0, "control arm must never emit board_control"
        assert nonzero == 0
    final = sample.trace[-1].after
    scores = [final.players[0].score, final.players[1].score]
    ranked_out = (
        sample.end_reason == GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name
        and not final.players[strategy_slot].rack
    )
    return ArmGame(
        variant_slug=variant_slug,
        seed=seed,
        strategy_slot=strategy_slot,
        defense=defense,
        plies=sample.plies,
        spread=scores[strategy_slot] - scores[1 - strategy_slot],
        end_reason=sample.end_reason,
        board_control_decisions=board_control,
        nonzero_defense_decisions=nonzero,
        own_ppt=own_ppt,
        opponent_ppt=opp_ppt,
        leading_replies=leading,
        neutral_replies=neutral,
        trailing_replies=trailing,
        own_points=own_points,
        opponent_points=opp_points,
        passes=sample.passes,
        exchanges=sample.exchanges,
        search_elapsed_ms=sample.search_cost.elapsed_ms_sum,
        search_nodes=sample.search_cost.nodes_sum,
        ranked_out=ranked_out,
    )


def _run_pairs(
    seeds_by_variant: dict[str, tuple[int, ...]],
    *,
    label: str,
    both_seats: bool,
) -> list[tuple[ArmGame, ArmGame]]:
    started = perf_counter()
    pairs: list[tuple[ArmGame, ArmGame]] = []
    for variant_slug, seeds in seeds_by_variant.items():
        for seed in seeds:
            slots = (0, 1) if both_seats else (seed % 2,)
            for slot in slots:
                off = _play(variant_slug, seed, slot, defense=False)
                on = _play(variant_slug, seed, slot, defense=True)
                pairs.append((off, on))
                print(
                    f"{label} {variant_slug} seed={seed} slot={slot} "
                    f"spread_off={off.spread:+d} spread_on={on.spread:+d} "
                    f"delta={on.spread - off.spread:+d} "
                    f"end_off={off.end_reason} end_on={on.end_reason} "
                    f"board_control={on.board_control_decisions} "
                    f"nonzero={on.nonzero_defense_decisions} "
                    f"opp_ppt_off={off.opponent_ppt:.2f} opp_ppt_on={on.opponent_ppt:.2f}",
                    flush=True,
                )
    _print_summary(label, pairs, elapsed=perf_counter() - started)
    return pairs


def _bootstrap_mean_ci(seed_groups: list[list[int]]) -> tuple[float, float, float]:
    rng = random.Random(_BOOTSTRAP_SEED)
    n = len(seed_groups)
    samples: list[float] = []
    for _ in range(_BOOTSTRAP_RESAMPLES):
        chosen = [seed_groups[rng.randrange(n)] for _ in range(n)]
        flat = [delta for group in chosen for delta in group]
        samples.append(sum(flat) / len(flat))
    samples.sort()
    mean = sum(delta for group in seed_groups for delta in group) / sum(
        len(group) for group in seed_groups
    )
    return mean, samples[249], samples[9749]


def _print_summary(
    label: str, pairs: list[tuple[ArmGame, ArmGame]], *, elapsed: float
) -> None:
    for variant_slug in sorted({off.variant_slug for off, _on in pairs}):
        rows = [(off, on) for off, on in pairs if off.variant_slug == variant_slug]
        off_total = sum(off.spread for off, _on in rows)
        on_total = sum(on.spread for _off, on in rows)
        off_wins = sum(off.spread > 0 for off, _on in rows)
        on_wins = sum(on.spread > 0 for _off, on in rows)
        off_draws = sum(off.spread == 0 for off, _on in rows)
        on_draws = sum(on.spread == 0 for _off, on in rows)
        off_losses = sum(off.spread < 0 for off, _on in rows)
        on_losses = sum(on.spread < 0 for _off, on in rows)
        off_wr = (off_wins + 0.5 * off_draws) / len(rows)
        on_wr = (on_wins + 0.5 * on_draws) / len(rows)
        off_opp = sum(off.opponent_ppt for off, _on in rows) / len(rows)
        on_opp = sum(on.opponent_ppt for _off, on in rows) / len(rows)
        off_lead = [score for off, _on in rows for score in off.leading_replies]
        on_lead = [score for _off, on in rows for score in on.leading_replies]
        groups: dict[int, list[int]] = {}
        for off, on in rows:
            groups.setdefault(off.seed, []).append(on.spread - off.spread)
        mean, lo, hi = _bootstrap_mean_ci(list(groups.values()))
        print(
            f"{label}-summary {variant_slug} games={len(rows)}x2 "
            f"WDL_off={off_wins}/{off_draws}/{off_losses} "
            f"WDL_on={on_wins}/{on_draws}/{on_losses} "
            f"winrate_off/on={off_wr:.3f}/{on_wr:.3f} "
            f"total_spread_off={off_total:+d} total_spread_on={on_total:+d} "
            f"delta={on_total - off_total:+d} mean_paired={mean:+.2f} "
            f"ci95=[{lo:+.2f},{hi:+.2f}] "
            f"opp_ppt_off/on={off_opp:.2f}/{on_opp:.2f} "
            f"lead_reply_n_off/on={len(off_lead)}/{len(on_lead)} "
            f"lead_reply_mean_off/on="
            f"{(sum(off_lead) / len(off_lead) if off_lead else 0):.2f}/"
            f"{(sum(on_lead) / len(on_lead) if on_lead else 0):.2f} "
            f"board_control={sum(on.board_control_decisions for _off, on in rows)} "
            f"nonzero={sum(on.nonzero_defense_decisions for _off, on in rows)} "
            f"elapsed={elapsed:.1f}s",
            flush=True,
        )


def _assert_smoke(pairs: list[tuple[ArmGame, ArmGame]]) -> None:
    assert pairs
    for off, on in pairs:
        assert off.end_reason in _ALLOWED_END_REASONS
        assert on.end_reason in _ALLOWED_END_REASONS
        assert 0 < on.plies <= _MAX_PLIES
        assert on.board_control_decisions > 0
    assert sum(on.spread for _off, on in pairs) > 0


def test_default_paired_benchmark_terminates_and_engages_board_control() -> None:
    pairs = _run_pairs(_DEFAULT_SEEDS, label="board-defense-ab-default", both_seats=False)
    _assert_smoke(pairs)


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get(_OPT_IN_ENV) != "1",
    reason=f"set {_OPT_IN_ENV}=1 for the board-defense acceptance cohort",
)
def test_paired_board_defense_acceptance() -> None:
    pairs = _run_pairs(_WIDE_SEEDS, label="board-defense-ab-acceptance", both_seats=True)
    for variant_slug in ("english", "slovak"):
        rows = [(off, on) for off, on in pairs if off.variant_slug == variant_slug]
        assert rows
        paired = [on.spread - off.spread for off, on in rows]
        assert sum(paired) / len(rows) > 0
        off_wins = sum(off.spread > 0 for off, _on in rows)
        on_wins = sum(on.spread > 0 for _off, on in rows)
        off_draws = sum(off.spread == 0 for off, _on in rows)
        on_draws = sum(on.spread == 0 for _off, on in rows)
        off_wr = (off_wins + 0.5 * off_draws) / len(rows)
        on_wr = (on_wins + 0.5 * on_draws) / len(rows)
        assert on_wr >= off_wr
        off_opp = sum(off.opponent_ppt for off, _on in rows) / len(rows)
        on_opp = sum(on.opponent_ppt for _off, on in rows) / len(rows)
        assert on_opp <= off_opp
        off_lead = [score for off, _on in rows for score in off.leading_replies]
        on_lead = [score for _off, on in rows for score in on.leading_replies]
        assert on_lead
        assert sum(on_lead) / len(on_lead) < (
            sum(off_lead) / len(off_lead) if off_lead else float("inf")
        )
