"""Harness-only endgame policy matrix. No production search or scoring change.

Policies share one interface and identical exchange/pass rules:
nothing found and bag >= 7 -> exchange; nothing found and bag < 7 -> pass;
indeterminate fails the test.

Policy C (measurement candidate, not a product heuristic):
  Let S* be max(total_score) over the ranked candidate list.
  Eligible candidates satisfy S* - total_score <= SCORE_LOSS_THRESHOLD.
  Score each eligible candidate as
    total_score + RARE_BONUS * (physical single-copy diacritic tiles consumed).
  Blanks never count as rare consumption (placement.letter == '?').
  Choose the maximum of that key, then rare count, then raw score, then
  canonical_key. When the rare set is empty, C is identical to ranked-best.
"""

from __future__ import annotations

import inspect
import json
import os
from collections import Counter
from collections.abc import Sequence
from functools import partial
from pathlib import Path
from statistics import median
from time import perf_counter

import pytest

from game.diagnostics import (
    ARTIFACT_ID,
    REPORT_KIND_POLICY_COMPARISON,
    PolicyComparisonSample,
    PolicySearchCost,
    VariantProbeContext,
    build_policy_comparison_report,
    classify_complete_formed_words,
    dump_report_json,
    format_policy_metric_line,
    is_diacritic_letter,
    load_variant_context,
    observe_source_revision,
    write_report_atomically,
)
from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.game import GameEndReason
from gamecore.legality import evaluate_scoring_move
from gamecore.move_search import (
    DEFAULT_MAX_NODES,
    DEFAULT_RANKED_MAX_ELAPSED_MS,
    DEFAULT_RANKED_MAX_NODES,
    DEFAULT_RANKED_TOP_K,
    DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
)
from gamecore.tiles import get_tile_distribution, get_tile_points
from gamecore.types import WordFound
from gamecore.word_authority import WordAuthority
from gamecore.selfplay import (
    SelfPlayConfig, SelfPlayContext, simulate_engine_game,
    POLICY_WITNESS, _tile_counter, _fingerprint as fingerprint,
    _rack_points as rack_points,
    POLICY_IDS, POLICY_RANKED_BEST, POLICY_RANKED_RACK, RARE_BONUS, SCORE_LOSS_THRESHOLD,
    _choose, _unplayed_rare, _on_board_rare,
)

VARIANT_SLUGS = ("slovak", "english")
DEFAULT_SEEDS = (0,)
WIDE_SEEDS = (1, 2, 3)
OPT_IN_ENV = "LIBRETILES_RUN_ENDGAME_MATRIX"
MAX_PLIES = 200
WITNESS_MAX_ELAPSED_MS = 10_000

# Exact tuple pins use node bounds; production's wall-clock cap is load-sensitive.
_PARITY_RANKED_MAX_NODES = 20_000
_PARITY_MAX_ELAPSED_MS = 10_000_000
DECLARED_SLOVAK_RARE = frozenset("ÁÄÉÍÓÔÚÝČĎĹĽŇŔŠŤŽ")
ALLOWED_END_REASONS = {
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES,
}
_SCHEMA_REQUIRED = {
    "artifact",
    "report_kind",
    "generated_at",
    "source_revision",
    "requested",
    "variant",
    "samples",
    "summary",
}

_CONTEXTS: dict[str, VariantProbeContext] = {
    slug: load_variant_context(slug) for slug in VARIANT_SLUGS
}
_EXPECTED_TILES = {slug: Counter(get_tile_distribution(slug)) for slug in VARIANT_SLUGS}
_TILE_POINTS = {slug: get_tile_points(slug) for slug in VARIANT_SLUGS}
_RARE_TILES = {
    slug: frozenset(
        letter
        for letter, count in get_tile_distribution(slug).items()
        if count == 1 and is_diacritic_letter(letter)
    )
    for slug in VARIANT_SLUGS
}
assert _RARE_TILES["slovak"] == DECLARED_SLOVAK_RARE
assert len(_RARE_TILES["slovak"]) == 17
assert _RARE_TILES["english"] == frozenset()

_RESULT_CACHE: dict[tuple[str, str, int], PolicyComparisonSample] = {}
# Physical tile evidence for every played move, kept beside the serializable
# sample so the two-letter policy can be re-checked over TOKEN SEQUENCES instead
# of reverse-segmenting the report's lexical strings.
_RECORDS_CACHE: dict[tuple[str, str, int], tuple[WordFound, ...]] = {}


_fingerprint = partial(fingerprint, include_pass_streak=False)


def _run_sample(
    variant_slug: str, policy_id: str, seed: int, *, node_bound: bool = False,
) -> PolicyComparisonSample:
    context = _CONTEXTS[variant_slug]
    expected = _EXPECTED_TILES[variant_slug]
    rare = _RARE_TILES[variant_slug]
    sample = simulate_engine_game(
        SelfPlayConfig(
            variant_slug=variant_slug, seed=seed, policy_id=policy_id, max_plies=MAX_PLIES,
            witness_max_elapsed_ms=(
                _PARITY_MAX_ELAPSED_MS if node_bound else WITNESS_MAX_ELAPSED_MS
            ),
            witness_max_nodes=DEFAULT_MAX_NODES,
            ranked_max_elapsed_ms=(
                _PARITY_MAX_ELAPSED_MS if node_bound else DEFAULT_RANKED_MAX_ELAPSED_MS
            ),
            ranked_max_nodes=(
                _PARITY_RANKED_MAX_NODES if node_bound else DEFAULT_RANKED_MAX_NODES
            ),
            ranked_top_k=DEFAULT_RANKED_TOP_K,
            ranked_max_unique_placements=DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
            include_pass_streak=False, strict_unknown_tile=False,
            record_trace=True,
        ),
        context=SelfPlayContext(
            authority=context.authority, letters=context.letters,
            blank_letters=tuple(context.variant.playable_letters),
            premiums_path=get_premiums_path(), rare_tiles=rare,
        ),
    )
    if node_bound:
        assert all(event.decision.elapsed_ms < _PARITY_MAX_ELAPSED_MS for event in sample.trace)
        capped = [event for event in sample.trace if not event.decision.complete]
        assert all(event.decision.nodes == _PARITY_RANKED_MAX_NODES for event in capped)
        if policy_id != POLICY_WITNESS:
            assert capped, "ranked parity must exercise the node bound"
    game = sample.initial_state
    assert game is not None
    players = game.players
    placement_scores = {"P0": 0, "P1": 0}
    fingerprints = {_fingerprint(game)}
    terminal_transitions = 0
    exchanges = 0
    passes = 0
    formed_words: list[str] = []
    formed_records: list[WordFound] = []
    nodes_sum = 0
    elapsed_sum = 0
    decisions = 0

    assert _tile_counter(game) == expected, f"{variant_slug} seed={seed} initial conservation"

    for event in sample.trace:
        ply = event.ply
        game = event.before
        players = game.players
        assert not game.ended, f"{variant_slug} seed={seed} ply={ply} post-terminal"
        acting_index = game.current_index
        acting = game.current_player()
        score_before = tuple(player.score for player in players)
        rack_before = acting.rack.copy()
        bag_before = game.bag.remaining()
        scoreless_before = game.consecutive_scoreless_turns
        pass_streak_before = acting.pass_streak
        assert _tile_counter(game) == expected, (
            f"{variant_slug} seed={seed} ply={ply} pre-action conservation"
        )

        decision = event.decision
        decisions += 1
        nodes_sum += decision.nodes
        elapsed_sum += decision.elapsed_ms
        context_label = (
            f"{variant_slug} policy={policy_id} seed={seed} ply={ply} "
            f"status={decision.status} nodes={decision.nodes} elapsed_ms={decision.elapsed_ms}"
        )
        if decision.status == "indeterminate":
            pytest.fail(f"{context_label}: bounded search must not authorize a non-scoring action")

        game = event.after
        players = game.players
        acting = players[acting_index]

        if decision.placements is not None:
            assert decision.status == "found", context_label
            legality = evaluate_scoring_move(
                event.before.board,
                rack_before,
                decision.placements,
                authority=context.authority,
                letters=context.letters,
                variant=variant_slug,
            )
            assert legality.ok, f"{context_label}: candidate failed re-certification: {legality}"
            assert legality.total_score == decision.total_score, context_label
            rejected = classify_complete_formed_words(
                legality.words_found,
                authority=context.authority,
            )
            assert rejected == (), f"{context_label}: two-letter policy rejected {rejected}"
            formed_words.extend(legality.words)
            formed_records.extend(legality.words_found)
            awarded = event.awarded
            assert awarded == legality.total_score, context_label
            placement_scores[acting.name] += awarded
            assert game.consecutive_scoreless_turns == 0, context_label
            assert acting.pass_streak == 0, context_label
            if not game.ended:
                assert acting.score - score_before[acting_index] == awarded, context_label
        elif bag_before >= 7:
            assert decision.status == "none" and decision.complete is True, context_label
            exchanges += 1
            assert game.consecutive_scoreless_turns == scoreless_before + 1, context_label
            assert acting.pass_streak == 0, context_label
            if not game.ended:
                assert tuple(player.score for player in players) == score_before, context_label
        else:
            assert decision.status == "none" and decision.complete is True, context_label
            passes += 1
            assert game.consecutive_scoreless_turns == scoreless_before + 1, context_label
            assert acting.pass_streak == pass_streak_before + 1, context_label
            if not game.ended:
                assert tuple(player.score for player in players) == score_before, context_label

        assert _tile_counter(game) == expected, f"{context_label}: conservation"
        assert _unplayed_rare(game, rare) + _on_board_rare(game, rare) == len(rare), (
            f"{context_label}: rare-tile conservation"
        )
        if game.ended:
            terminal_transitions += 1
            assert game.current_index == acting_index, context_label
        else:
            assert game.current_index == (acting_index + 1) % len(players), context_label

        fingerprint = _fingerprint(game)
        assert fingerprint not in fingerprints, f"{context_label}: repeated full position"
        fingerprints.add(fingerprint)

        if game.ended:
            assert terminal_transitions == 1, context_label
            assert game.end_reason in ALLOWED_END_REASONS, context_label
            assert game.end_reason is not None, context_label
            expected_scores = [placement_scores[player.name] for player in players]
            leftovers = [rack_points(player.rack, _TILE_POINTS[variant_slug], strict_unknown_tile=False) for player in players]
            for index, leftover in enumerate(leftovers):
                expected_scores[index] -= leftover
            if game.end_reason is GameEndReason.BAG_EMPTY_AND_PLAYER_OUT:
                finishers = [index for index, player in enumerate(players) if not player.rack]
                assert len(finishers) == 1, context_label
                finisher = finishers[0]
                expected_scores[finisher] += sum(
                    leftover for index, leftover in enumerate(leftovers) if index != finisher
                )
            else:
                assert all(player.rack for player in players), context_label
            assert [player.score for player in players] == expected_scores, context_label
            bag_remaining = game.bag.remaining()
            rack_remaining = {player.name: tuple(player.rack) for player in players}
            stranded = bag_remaining + sum(len(tiles) for tiles in rack_remaining.values())
            rejected = classify_complete_formed_words(
                tuple(formed_records),
                authority=context.authority,
            )
            assert rejected == ()
            assert sample.plies == ply
            assert sample.end_reason == game.end_reason.name
            assert sample.final_scores == game.scores()
            assert sample.placement_scores == placement_scores
            assert sample.leftover_points == game.leftover_points
            assert sample.bag_remaining == bag_remaining
            assert sample.rack_remaining == rack_remaining
            assert sample.stranded_total == stranded
            assert sample.rare_unplayed == _unplayed_rare(game, rare)
            assert sample.rare_total == len(rare)
            assert sample.exchanges == exchanges
            assert sample.passes == passes
            assert sample.formed_words == tuple(formed_words)
            assert sample.formed_records == tuple(formed_records)
            assert sample.rejected_two_letter_words == rejected
            assert sample.search_cost.nodes_sum == nodes_sum
            assert sample.search_cost.elapsed_ms_sum == elapsed_sum
            assert sample.search_cost.decision_count == decisions
            if not node_bound:
                _RECORDS_CACHE[(variant_slug, policy_id, seed)] = tuple(formed_records)
            print(
                "selfplay-node-bound" if node_bound else "selfplay-production",
                (variant_slug, policy_id, seed, ply,
                 game.end_reason.name, tuple(game.scores().values())), flush=True,
            )
            return PolicyComparisonSample(
                variant_slug=variant_slug,
                policy_id=policy_id,
                seed=seed,
                plies=ply,
                end_reason=game.end_reason.name,
                bag_remaining=bag_remaining,
                rack_remaining=rack_remaining,
                stranded_total=stranded,
                rare_unplayed=_unplayed_rare(game, rare),
                rare_total=len(rare),
                exchanges=exchanges,
                passes=passes,
                placement_scores=dict(placement_scores),
                final_scores=game.scores(),
                leftover_points=dict(game.leftover_points),
                search_cost=PolicySearchCost(
                    nodes_sum=nodes_sum,
                    elapsed_ms_sum=elapsed_sum,
                    decision_count=decisions,
                ),
                formed_words=tuple(formed_words),
                rejected_two_letter_words=rejected,
                verdict="pass",
                reason_code="ok",
            )

    pytest.fail(f"{variant_slug} policy={policy_id} seed={seed}: did not terminate in {MAX_PLIES}")


def _cached(variant_slug: str, policy_id: str, seed: int) -> PolicyComparisonSample:
    key = (variant_slug, policy_id, seed)
    sample = _RESULT_CACHE.get(key)
    if sample is None:
        sample = _run_sample(variant_slug, policy_id, seed)
        _RESULT_CACHE[key] = sample
    return sample


def _matrix(
    seeds: Sequence[int],
    *,
    variants: Sequence[str] = VARIANT_SLUGS,
    policies: Sequence[str] = POLICY_IDS,
) -> list[PolicyComparisonSample]:
    return [
        _cached(variant_slug, policy_id, seed)
        for variant_slug in variants
        for policy_id in policies
        for seed in seeds
    ]


def _print_sample(sample: PolicyComparisonSample) -> None:
    print(format_policy_metric_line(sample), flush=True)


def _print_aggregate(label: str, samples: Sequence[PolicyComparisonSample]) -> None:
    grouped: dict[tuple[str, str], list[PolicyComparisonSample]] = {}
    for sample in samples:
        grouped.setdefault((sample.variant_slug, sample.policy_id), []).append(sample)
    for (variant_slug, policy_id), rows in grouped.items():
        reasons = Counter(row.end_reason for row in rows)
        plies = [row.plies for row in rows]
        stranded = [row.stranded_total for row in rows]
        rare = [row.rare_unplayed for row in rows]
        exchanges = [row.exchanges for row in rows]
        passes = [row.passes for row in rows]
        nodes = [row.search_cost.nodes_sum / max(row.search_cost.decision_count, 1) for row in rows]
        elapsed = [
            row.search_cost.elapsed_ms_sum / max(row.search_cost.decision_count, 1) for row in rows
        ]
        print(
            f"{label} {variant_slug} policy={policy_id} games={len(rows)} "
            f"end_reasons={dict(sorted(reasons.items()))} "
            f"plies=min/med/max={min(plies)}/{median(plies):g}/{max(plies)} "
            f"stranded=min/med/max={min(stranded)}/{median(stranded):g}/{max(stranded)} "
            f"rare_unplayed=min/med/max={min(rare)}/{median(rare):g}/{max(rare)} "
            f"exchanges=min/med/max={min(exchanges)}/{median(exchanges):g}/{max(exchanges)} "
            f"passes=min/med/max={min(passes)}/{median(passes):g}/{max(passes)} "
            f"search_nodes_per_decision={sum(nodes) / len(nodes):.1f} "
            f"search_ms_per_decision={sum(elapsed) / len(elapsed):.1f}",
            flush=True,
        )


def _requested_fields(seeds: Sequence[int]) -> dict[str, str | int]:
    return {
        "variant_slug": "slovak",
        "control_variant_slug": "english",
        "policies": ",".join(POLICY_IDS),
        "seeds": ",".join(str(seed) for seed in seeds),
        "rare_bonus": RARE_BONUS,
        "score_loss_threshold": SCORE_LOSS_THRESHOLD,
        "witness_max_elapsed_ms": WITNESS_MAX_ELAPSED_MS,
        "ranked_max_elapsed_ms": DEFAULT_RANKED_MAX_ELAPSED_MS,
        "ranked_max_nodes": DEFAULT_RANKED_MAX_NODES,
        "ranked_top_k": DEFAULT_RANKED_TOP_K,
    }


def test_policy_matrix_default_run_reports_all_three_policies() -> None:
    started = perf_counter()
    samples = _matrix(DEFAULT_SEEDS)
    elapsed = perf_counter() - started
    print(
        f"endgame-default games={len(samples)} seeds={list(DEFAULT_SEEDS)} "
        f"elapsed={elapsed:.3f}s rare_bonus={RARE_BONUS} "
        f"score_loss_threshold={SCORE_LOSS_THRESHOLD}",
        flush=True,
    )
    for sample in samples:
        _print_sample(sample)
    _print_aggregate("endgame-default", samples)
    assert {sample.policy_id for sample in samples} == set(POLICY_IDS)
    assert {sample.variant_slug for sample in samples} == set(VARIANT_SLUGS)
    assert len(samples) == len(VARIANT_SLUGS) * len(POLICY_IDS) * len(DEFAULT_SEEDS)


def test_node_bound_matrix_regression_tuples() -> None:
    """New candidate baselines under node bounds, separate from extraction-equivalence evidence."""
    samples = [
        _run_sample(variant, policy, seed, node_bound=True)
        for variant in VARIANT_SLUGS for policy in POLICY_IDS for seed in DEFAULT_SEEDS
    ]
    assert [
        (sample.policy_id, sample.variant_slug, sample.plies,
         sample.end_reason, tuple(sample.final_scores.values()))
        for sample in samples
    ] == [
        (POLICY_WITNESS, "slovak", 55, "SIX_CONSECUTIVE_ZERO_SCORES", (303, 243)),
        (POLICY_RANKED_BEST, "slovak", 26, "BAG_EMPTY_AND_PLAYER_OUT", (586, 533)),
        (POLICY_RANKED_RACK, "slovak", 31, "BAG_EMPTY_AND_PLAYER_OUT", (494, 365)),
        (POLICY_WITNESS, "english", 69, "SIX_CONSECUTIVE_ZERO_SCORES", (375, 138)),
        (POLICY_RANKED_BEST, "english", 22, "BAG_EMPTY_AND_PLAYER_OUT", (511, 418)),
        (POLICY_RANKED_RACK, "english", 22, "BAG_EMPTY_AND_PLAYER_OUT", (511, 418)),
    ]


def test_slovak_endgame_metrics_are_deterministic_for_a_fixed_seed() -> None:
    first = _run_sample("slovak", POLICY_WITNESS, 0)
    second = _run_sample("slovak", POLICY_WITNESS, 0)
    assert first.plies == second.plies
    assert first.end_reason == second.end_reason
    assert first.bag_remaining == second.bag_remaining
    assert first.rack_remaining == second.rack_remaining
    assert first.stranded_total == second.stranded_total
    assert first.rare_unplayed == second.rare_unplayed
    assert first.exchanges == second.exchanges
    assert first.passes == second.passes
    assert first.placement_scores == second.placement_scores
    assert first.final_scores == second.final_scores
    print(
        f"slovak-deterministic seed=0 plies={first.plies} "
        f"end_reason={first.end_reason} stranded={first.stranded_total} "
        f"rare_unplayed={first.rare_unplayed}/{first.rare_total}",
        flush=True,
    )


def test_english_control_matrix_has_no_ascii_only_predicate() -> None:
    english = _CONTEXTS["english"]
    word_source = inspect.getsource(type(english).is_word)
    choose_source = inspect.getsource(_choose)
    simulate_source = inspect.getsource(simulate_engine_game)
    # Migrated target, same invariant: the word verdict now lives on the one
    # authority, so the ASCII-only lock is asserted over that whole module.
    authority_source = inspect.getsource(WordAuthority)
    banned = "is" + "ascii"
    assert "authority" in word_source
    assert banned not in choose_source
    assert banned not in simulate_source
    assert banned not in authority_source
    assert english.allowlist is None
    assert english.authority.two_tile_words is None
    assert english.is_word("QI")
    assert not english.is_word("QZ")
    assert english.authority.accepts_tokens(("Q", "I"))
    assert not english.authority.accepts_tokens(("Q", "Z"))
    assert _RARE_TILES["english"] == frozenset()


def test_every_game_terminates_with_an_allowed_end_reason() -> None:
    samples = _matrix(DEFAULT_SEEDS)
    allowed = {reason.name for reason in ALLOWED_END_REASONS}
    for sample in samples:
        assert sample.end_reason in allowed
        assert sample.plies >= 1
        assert sample.plies <= MAX_PLIES


def test_two_letter_policy_holds_for_every_played_move_in_every_policy() -> None:
    classifier_source = inspect.getsource(classify_complete_formed_words)
    assert ".find(" not in classifier_source
    samples = _matrix(DEFAULT_SEEDS)
    for sample in samples:
        context = _CONTEXTS[sample.variant_slug]
        records = _RECORDS_CACHE[
            (sample.variant_slug, sample.policy_id, sample.seed)
        ]
        # ⚠ Classified over the retained TOKEN SEQUENCES. The report's lexical
        # strings are never reverse-segmented to manufacture tile evidence.
        rejected = classify_complete_formed_words(
            records,
            authority=context.authority,
        )
        assert tuple(record.word for record in records) == sample.formed_words
        assert sample.rejected_two_letter_words == ()
        assert rejected == ()


def test_tile_conservation_holds_for_every_policy() -> None:
    samples = _matrix(DEFAULT_SEEDS)
    for sample in samples:
        expected_total = sum(_EXPECTED_TILES[sample.variant_slug].values())
        rack_tiles = sum(len(tiles) for tiles in sample.rack_remaining.values())
        assert sample.bag_remaining + rack_tiles <= expected_total
        assert sample.stranded_total == sample.bag_remaining + rack_tiles
        assert sample.rare_unplayed <= sample.rare_total
        if sample.variant_slug == "slovak":
            assert sample.rare_total == 17
        else:
            assert sample.rare_total == 0
            assert sample.rare_unplayed == 0


def test_policy_comparison_report_matches_v1_conventions(tmp_path: Path) -> None:
    samples = _matrix(DEFAULT_SEEDS)
    report = build_policy_comparison_report(
        requested=_requested_fields(DEFAULT_SEEDS),
        context=_CONTEXTS["slovak"],
        samples=samples,
        source_revision=observe_source_revision(),
    )
    missing = _SCHEMA_REQUIRED - report.keys()
    assert not missing
    assert report["artifact"] == ARTIFACT_ID
    assert report["report_kind"] == REPORT_KIND_POLICY_COMPARISON
    assert isinstance(report["generated_at"], str)
    assert report["generated_at"].endswith("Z")
    assert report["source_revision"] == observe_source_revision()
    assert report["requested"]["variant_slug"] == "slovak"
    assert report["variant"]["slug"] == "slovak"
    assert {"slug", "lexicon_id", "two_letter_lexicon_size"} <= report["variant"].keys()
    assert report["summary"]["sample_count"] == len(samples)
    assert report["summary"]["pass_count"] + report["summary"]["fail_count"] == len(samples)
    schema_path = get_assets_path() / "diagnostics" / "ai_play_report_v1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert schema["properties"]["artifact"]["const"] == ARTIFACT_ID
    assert REPORT_KIND_POLICY_COMPARISON in schema["properties"]["report_kind"]["enum"]
    assert set(schema["required"]) == _SCHEMA_REQUIRED
    for sample in report["samples"]:
        assert isinstance(sample, dict)
        assert sample["policy_id"] in POLICY_IDS
        assert sample["verdict"] in {"pass", "fail"}
        assert "search_cost" in sample
        policy = sample["two_letter_policy"]
        assert "complete_formed_words" in policy
        assert "rejected" in policy
        assert policy["rejected"] == []

    payload = dump_report_json(report)
    out_path = tmp_path / "policy-comparison.json"
    write_report_atomically(out_path, payload)
    reloaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert reloaded["report_kind"] == REPORT_KIND_POLICY_COMPARISON


@pytest.mark.slow
@pytest.mark.skipif(
    os.environ.get(OPT_IN_ENV) != "1",
    reason=f"set {OPT_IN_ENV}=1 for the wide endgame policy matrix",
)
def test_policy_matrix_wide_run() -> None:
    started = perf_counter()
    samples = _matrix(WIDE_SEEDS)
    elapsed = perf_counter() - started
    print(
        f"endgame-wide games={len(samples)} seeds={list(WIDE_SEEDS)} elapsed={elapsed:.3f}s",
        flush=True,
    )
    for sample in samples:
        _print_sample(sample)
    _print_aggregate("endgame-wide", samples)
    assert len(samples) == len(VARIANT_SLUGS) * len(POLICY_IDS) * len(WIDE_SEEDS)
    for sample in samples:
        assert sample.end_reason in {reason.name for reason in ALLOWED_END_REASONS}
        assert sample.rejected_two_letter_words == ()


def test_shared_rack_aware_selector_keeps_threshold_bonus_and_physical_tiles() -> None:
    from gamecore.move_search import RankedMoveCandidate
    from gamecore.selfplay import _rare_consumed, _select_rack_aware
    from gamecore.types import Placement

    def candidate(score, placements):
        return RankedMoveCandidate(
            placements=tuple(placements), words=(), total_score=score,
            tiles_used=len(placements), leave_value=0, rack_out=False,
            canonical_key=tuple((p.row, p.col, p.letter, p.blank_as or "") for p in placements),
        )

    rare = frozenset({"Á", "Ľ"})
    best = candidate(100, [Placement(7, 7, "A")])
    bonus = candidate(97, [Placement(7, 7, "Á")])
    outside_threshold = candidate(91, [Placement(7, 7, "Á"), Placement(7, 8, "Ľ")])
    blank = candidate(99, [Placement(7, 7, "?", "Á")])
    assert RARE_BONUS == 5 and SCORE_LOSS_THRESHOLD == 8
    assert _select_rack_aware([best, bonus, outside_threshold], rare) == bonus
    assert _select_rack_aware([best, outside_threshold], rare) == best
    assert _select_rack_aware([best, blank], rare) == best
    assert _rare_consumed(blank.placements, rare) == 0
    assert _select_rack_aware([best, bonus], frozenset()) == best


def test_shared_two_tile_check_uses_complete_physical_sequences() -> None:
    from gamecore.selfplay import _rejected_two_tile_words

    authority = WordAuthority.from_words(["OSAMENIU"], two_tile_words=frozenset({"ács"}))
    words = (
        WordFound("ÁCS", [(0, 0), (0, 1)], ["Á", "CS"]),
        WordFound("AM", [(1, 0), (1, 1)], ["A", "M"]),
        WordFound("OSAMENIU", [(2, col) for col in range(8)], list("OSAMENIU")),
    )
    assert _rejected_two_tile_words(words, authority=authority) == ("AM",)
    assert classify_complete_formed_words(words, authority=authority) == ("AM",)
