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
from dataclasses import dataclass
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
from gamecore.board import Board
from gamecore.game import Game, GameEndReason, PlayerState
from gamecore.legality import evaluate_scoring_move
from gamecore.move_search import (
    DEFAULT_MAX_NODES,
    DEFAULT_RANKED_MAX_ELAPSED_MS,
    DEFAULT_RANKED_MAX_NODES,
    DEFAULT_RANKED_TOP_K,
    RankedMoveCandidate,
    RankedSearchResult,
    find_legal_scoring_move,
    find_ranked_scoring_moves,
)
from gamecore.tiles import TileBag, get_tile_distribution, get_tile_points
from gamecore.types import Placement, WordFound
from gamecore.word_authority import WordAuthority

POLICY_WITNESS = "witness-first"
POLICY_RANKED_BEST = "ranked-best"
POLICY_RANKED_RACK = "ranked-rack-aware"
POLICY_IDS = (POLICY_WITNESS, POLICY_RANKED_BEST, POLICY_RANKED_RACK)
VARIANT_SLUGS = ("slovak", "english")
DEFAULT_SEEDS = (0,)
WIDE_SEEDS = (1, 2, 3)
OPT_IN_ENV = "LIBRETILES_RUN_ENDGAME_MATRIX"
MAX_PLIES = 200
WITNESS_MAX_ELAPSED_MS = 10_000
RARE_BONUS = 5
SCORE_LOSS_THRESHOLD = 8
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


@dataclass(frozen=True)
class _Decision:
    status: str
    complete: bool
    nodes: int
    elapsed_ms: int
    placements: tuple[Placement, ...] | None
    words: tuple[str, ...]
    total_score: int


def _tile_counter(game: Game) -> Counter[str]:
    tiles = Counter(game.bag.tiles)
    for player in game.players:
        tiles.update(player.rack)
    for row in game.board.cells:
        for cell in row:
            if cell.letter:
                tiles.update(["?" if cell.is_blank else cell.letter])
    return tiles


def _fingerprint(game: Game) -> tuple[object, ...]:
    board = tuple(
        (cell.letter, cell.is_blank, cell.premium, cell.premium_used)
        for row in game.board.cells
        for cell in row
    )
    return (
        board,
        tuple(game.bag.tiles),
        tuple(tuple(player.rack) for player in game.players),
        tuple(player.score for player in game.players),
        game.current_index,
        game.consecutive_scoreless_turns,
    )


def _rack_points(variant_slug: str, rack: Sequence[str]) -> int:
    points = _TILE_POINTS[variant_slug]
    return sum(points.get(tile, 0) for tile in rack)


def _rare_consumed(placements: Sequence[Placement], rare: frozenset[str]) -> int:
    return sum(1 for item in placements if item.letter in rare)


def _ranked_search(
    game: Game,
    rack: Sequence[str],
    context: VariantProbeContext,
) -> RankedSearchResult:
    return find_ranked_scoring_moves(
        game.board,
        rack,
        authority=context.authority,
        bag_count=game.bag.remaining(),
        top_k=DEFAULT_RANKED_TOP_K,
        max_nodes=DEFAULT_RANKED_MAX_NODES,
        max_elapsed_ms=DEFAULT_RANKED_MAX_ELAPSED_MS,
        tile_points=_TILE_POINTS[context.variant.slug],
        blank_letters=context.variant.playable_letters,
        variant=context.variant.slug,
    )


def _from_ranked(
    result: RankedSearchResult,
    candidate: RankedMoveCandidate | None,
) -> _Decision:
    return _Decision(
        status=result.status,
        complete=result.complete,
        nodes=result.nodes,
        elapsed_ms=result.elapsed_ms,
        placements=None if candidate is None else candidate.placements,
        words=() if candidate is None else candidate.words,
        total_score=0 if candidate is None else candidate.total_score,
    )


def _select_rack_aware(
    candidates: Sequence[RankedMoveCandidate],
    rare: frozenset[str],
) -> RankedMoveCandidate:
    if not rare:
        return candidates[0]
    best_score = max(item.total_score for item in candidates)

    def rare_count(item: RankedMoveCandidate) -> int:
        return _rare_consumed(item.placements, rare)

    eligible = [
        item for item in candidates if best_score - item.total_score <= SCORE_LOSS_THRESHOLD
    ]
    if not any(rare_count(item) for item in eligible):
        return candidates[0]

    def sort_key(item: RankedMoveCandidate) -> tuple[object, ...]:
        consumed = rare_count(item)
        heuristic = item.total_score + RARE_BONUS * consumed
        return (-heuristic, -consumed, -item.total_score, item.canonical_key)

    return min(eligible, key=sort_key)


def _choose(
    policy_id: str,
    game: Game,
    rack: Sequence[str],
    context: VariantProbeContext,
) -> _Decision:
    if policy_id == POLICY_WITNESS:
        search = find_legal_scoring_move(
            game.board,
            rack,
            authority=context.authority,
            max_nodes=DEFAULT_MAX_NODES,
            max_elapsed_ms=WITNESS_MAX_ELAPSED_MS,
            blank_letters=context.variant.playable_letters,
            variant=context.variant.slug,
        )
        return _Decision(
            status=search.status,
            complete=search.complete,
            nodes=search.nodes,
            elapsed_ms=search.elapsed_ms,
            placements=search.witness,
            words=search.words,
            total_score=search.total_score,
        )

    ranked = _ranked_search(game, rack, context)
    if ranked.status == "indeterminate":
        return _from_ranked(ranked, None)
    if not ranked.candidates:
        return _from_ranked(ranked, None)
    if policy_id == POLICY_RANKED_BEST:
        chosen = ranked.candidates[0]
    elif policy_id == POLICY_RANKED_RACK:
        chosen = _select_rack_aware(ranked.candidates, _RARE_TILES[context.variant.slug])
    else:
        raise ValueError(f"unknown policy {policy_id}")
    return _from_ranked(ranked, chosen)


def _unplayed_rare(game: Game, rare: frozenset[str]) -> int:
    pool = list(game.bag.tiles)
    for player in game.players:
        pool.extend(player.rack)
    return sum(1 for tile in pool if tile in rare)


def _on_board_rare(game: Game, rare: frozenset[str]) -> int:
    count = 0
    for row in game.board.cells:
        for cell in row:
            if cell.letter in rare and not cell.is_blank:
                count += 1
    return count


def _simulate(variant_slug: str, policy_id: str, seed: int) -> PolicyComparisonSample:
    context = _CONTEXTS[variant_slug]
    expected = _EXPECTED_TILES[variant_slug]
    rare = _RARE_TILES[variant_slug]
    bag = TileBag(seed=seed, variant=variant_slug)
    players = [
        PlayerState(name="P0", rack=bag.draw(7)),
        PlayerState(name="P1", rack=bag.draw(7)),
    ]
    game = Game(
        board=Board(get_premiums_path()),
        bag=bag,
        players=players,
        starting_index=seed % 2,
    )
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

    for ply in range(1, MAX_PLIES + 1):
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

        decision = _choose(policy_id, game, rack_before, context)
        decisions += 1
        nodes_sum += decision.nodes
        elapsed_sum += decision.elapsed_ms
        context_label = (
            f"{variant_slug} policy={policy_id} seed={seed} ply={ply} "
            f"status={decision.status} nodes={decision.nodes} elapsed_ms={decision.elapsed_ms}"
        )
        if decision.status == "indeterminate":
            pytest.fail(f"{context_label}: bounded search must not authorize a non-scoring action")

        if decision.placements is not None:
            assert decision.status == "found", context_label
            legality = evaluate_scoring_move(
                game.board,
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
            awarded = game.play_move(decision.placements)
            assert awarded == legality.total_score, context_label
            placement_scores[acting.name] += awarded
            assert game.consecutive_scoreless_turns == 0, context_label
            assert acting.pass_streak == 0, context_label
            if not game.ended:
                assert acting.score - score_before[acting_index] == awarded, context_label
        elif bag_before >= 7:
            assert decision.status == "none" and decision.complete is True, context_label
            game.exchange_turn(rack_before)
            exchanges += 1
            assert game.consecutive_scoreless_turns == scoreless_before + 1, context_label
            assert acting.pass_streak == 0, context_label
            if not game.ended:
                assert tuple(player.score for player in players) == score_before, context_label
        else:
            assert decision.status == "none" and decision.complete is True, context_label
            game.pass_turn()
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
            leftovers = [_rack_points(variant_slug, player.rack) for player in players]
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
            _RECORDS_CACHE[(variant_slug, policy_id, seed)] = tuple(formed_records)
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
        sample = _simulate(variant_slug, policy_id, seed)
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


def test_slovak_endgame_metrics_are_deterministic_for_a_fixed_seed() -> None:
    first = _simulate("slovak", POLICY_WITNESS, 0)
    second = _simulate("slovak", POLICY_WITNESS, 0)
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
    simulate_source = inspect.getsource(_simulate)
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
