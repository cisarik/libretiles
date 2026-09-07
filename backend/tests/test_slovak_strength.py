"""Slovak ranked-search strength checks against the first-witness baseline.

Engine-to-engine regression evidence for the Slovak tile set, mirroring the
English harness in ``test_strength_benchmark.py``. Node bounds keep every
game deterministic; production wall-clock caps stay load-sensitive and are
covered by the English matrices.
"""

from __future__ import annotations

from collections import Counter

from gamecore.assets import get_premiums_path
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
    SelfPlaySample,
    _tile_counter,
    simulate_engine_game,
)
from gamecore.tiles import get_tile_distribution
from gamecore.variant_store import load_variant
from gamecore.word_authority import WordAuthority

_VARIANT = load_variant("slovak")
_AUTHORITY = WordAuthority.for_variant(_VARIANT)
_EXPECTED_TILES = Counter(get_tile_distribution("slovak"))
_ALLOWED_END_REASONS = {
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT.name,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES.name,
}

# Exact node bounds keep the games deterministic; the huge elapsed cap makes
# the wall clock irrelevant, matching the English node-bound harness.
_PARITY_RANKED_MAX_NODES = 20_000
_PARITY_MAX_ELAPSED_MS = 10_000_000
_MAX_PLIES = 200


def _sample(
    seed: int,
    player_policy_ids: tuple[str, str],
    *,
    late_game: bool = False,
) -> SelfPlaySample:
    return simulate_engine_game(
        SelfPlayConfig(
            variant_slug="slovak",
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
            strict_unknown_tile=True,
            player_policy_ids=player_policy_ids,
            record_trace=True,
            # The pre-existing Slovak evidence pins the LEGACY policy; the
            # strategic late-game stack is exercised by its own test below.
            late_game_enabled=late_game,
        ),
        context=SelfPlayContext(
            authority=_AUTHORITY,
            letters=frozenset(_VARIANT.playable_letters),
            blank_letters=tuple(_VARIANT.playable_letters),
            premiums_path=get_premiums_path(),
        ),
    )


def test_slovak_ranked_strategy_beats_first_witness_on_balanced_seeds() -> None:
    spreads: list[int] = []
    for seed in (0, 1):
        for strategy_slot in (0, 1):
            policies = [POLICY_WITNESS, POLICY_WITNESS]
            policies[strategy_slot] = POLICY_RANKED_WITNESS_SAFE
            sample = _sample(seed, (policies[0], policies[1]))
            assert sample.end_reason in _ALLOWED_END_REASONS
            assert sample.rejected_two_letter_words == ()
            scores = [sample.final_scores["P0"], sample.final_scores["P1"]]
            spread = scores[strategy_slot] - scores[1 - strategy_slot]
            spreads.append(spread)
            print(
                "slovak-strength",
                (seed, strategy_slot, spread, sample.end_reason),
                flush=True,
            )
    wins = sum(spread > 0 for spread in spreads)
    losses = sum(spread < 0 for spread in spreads)
    assert sum(spreads) > 0
    assert wins > losses


def test_slovak_late_game_strategy_beats_first_witness_on_balanced_seeds() -> None:
    spreads: list[int] = []
    strategic_decisions = 0
    for seed in (0, 1):
        for strategy_slot in (0, 1):
            policies = [POLICY_WITNESS, POLICY_WITNESS]
            policies[strategy_slot] = POLICY_RANKED_WITNESS_SAFE
            sample = _sample(seed, (policies[0], policies[1]), late_game=True)
            assert sample.end_reason in _ALLOWED_END_REASONS
            assert sample.rejected_two_letter_words == ()
            strategic_decisions += sum(
                1 for event in sample.trace
                if event.decision.strategy_mode is not None
            )
            scores = [sample.final_scores["P0"], sample.final_scores["P1"]]
            spread = scores[strategy_slot] - scores[1 - strategy_slot]
            spreads.append(spread)
            print(
                "slovak-late-game-strength",
                (seed, strategy_slot, spread, sample.end_reason),
                flush=True,
            )
    wins = sum(spread > 0 for spread in spreads)
    losses = sum(spread < 0 for spread in spreads)
    assert sum(spreads) > 0
    assert wins > losses
    # The strategic window (bag <= 7) must actually have been entered.
    assert strategic_decisions > 0


def test_slovak_ranked_self_play_terminates_with_tile_conservation() -> None:
    sample = _sample(
        0, (POLICY_RANKED_WITNESS_SAFE, POLICY_RANKED_WITNESS_SAFE)
    )
    assert sample.end_reason in _ALLOWED_END_REASONS
    assert 0 < sample.plies <= _MAX_PLIES
    assert sample.trace
    final_game = sample.trace[-1].after
    assert final_game.ended
    assert _tile_counter(final_game) == _EXPECTED_TILES
    assert sample.stranded_total == sample.bag_remaining + sum(
        len(rack) for rack in sample.rack_remaining.values()
    )
    assert sample.rejected_two_letter_words == ()
    print(
        "slovak-ranked-selfplay",
        (sample.plies, sample.end_reason,
         (sample.final_scores["P0"], sample.final_scores["P1"]),
         sample.exchanges, sample.passes, sample.stranded_total),
        flush=True,
    )
