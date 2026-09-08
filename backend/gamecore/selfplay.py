"""Pure, injected engine self-play with preserved harness policy semantics.

Snapshots are opt-in audit evidence, separate from the live game. A caller can
re-certify each placement and reconstruct scores without trusting the sample's
aggregate counters. Nothing here imports the application or a test framework.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace
from typing import Literal

from .board import Board
from .game import Game, GameEndReason, PlayerState
from .legality import evaluate_scoring_move
from .move_search import (
    RankedMoveCandidate,
    RankedSearchResult,
    find_legal_scoring_move,
    find_ranked_scoring_moves,
)
from .tile_tracking import LateGameContext, late_game_context_for_game
from .tiles import TileBag, get_tile_distribution, get_tile_points
from .types import Placement, WordFound
from .word_authority import WordAuthority

POLICY_WITNESS = "witness-first"
POLICY_RANKED_BEST = "ranked-best"
POLICY_RANKED_RACK = "ranked-rack-aware"
POLICY_RANKED_WITNESS_SAFE = "ranked-witness-safe"
# The original matrix cohort; the strength policy is intentionally separate.
POLICY_IDS = (POLICY_WITNESS, POLICY_RANKED_BEST, POLICY_RANKED_RACK)
RARE_BONUS = 5
SCORE_LOSS_THRESHOLD = 8
ALLOWED_END_REASONS = frozenset({
    GameEndReason.BAG_EMPTY_AND_PLAYER_OUT,
    GameEndReason.SIX_CONSECUTIVE_ZERO_SCORES,
})


class SelfPlayInvariantError(Exception):
    """A bounded search or game cannot supply a certified terminal sample."""


@dataclass(frozen=True)
class SelfPlayConfig:
    variant_slug: str
    seed: int
    policy_id: str
    max_plies: int
    witness_max_elapsed_ms: int
    witness_max_nodes: int
    ranked_max_elapsed_ms: int
    ranked_max_nodes: int
    ranked_top_k: int
    ranked_max_unique_placements: int
    include_pass_streak: bool
    # None preserves callers that have no independent rack reconstruction.
    strict_unknown_tile: bool | None
    player_policy_ids: tuple[str, str] | None = None
    record_trace: bool = False
    # Strategic late-game play (pre-endgame equity + exact endgame solver).
    # Callers pinning byte-exact legacy outcomes disable it explicitly.
    late_game_enabled: bool = True
    # Midgame board defense. The per-seat tuple overrides the global flag.
    board_defense_enabled: bool = False
    player_board_defense_enabled: tuple[bool, bool] | None = None


@dataclass(frozen=True)
class SelfPlayContext:
    authority: WordAuthority
    letters: frozenset[str]
    blank_letters: tuple[str, ...]
    premiums_path: str
    rare_tiles: frozenset[str] = frozenset()


@dataclass(frozen=True)
class SelfPlaySearchCost:
    nodes_sum: int
    elapsed_ms_sum: int
    decision_count: int


@dataclass(frozen=True)
class SelfPlayPly:
    ply: int
    before: Game
    after: Game
    decision: _Decision
    awarded: int


@dataclass(frozen=True)
class SelfPlaySample:
    variant_slug: str
    policy_id: str
    seed: int
    plies: int
    end_reason: str
    bag_remaining: int
    rack_remaining: dict[str, tuple[str, ...]]
    stranded_total: int
    rare_unplayed: int
    rare_total: int
    exchanges: int
    passes: int
    placement_scores: dict[str, int]
    final_scores: dict[str, int]
    leftover_points: dict[str, int]
    search_cost: SelfPlaySearchCost
    formed_words: tuple[str, ...]
    rejected_two_letter_words: tuple[str, ...]
    formed_records: tuple[WordFound, ...]
    initial_state: Game | None
    trace: tuple[SelfPlayPly, ...]
    verdict: Literal["pass"] = "pass"
    reason_code: str = "ok"


def _rejected_two_tile_words(
    words: Sequence[WordFound], *, authority: WordAuthority,
) -> tuple[str, ...]:
    return tuple(
        word.word for word in words
        if len(word.tokens) == 2 and not authority.accepts_tokens(word.tokens)
    )


@dataclass(frozen=True)
class _Decision:
    status: str
    complete: bool
    nodes: int
    elapsed_ms: int
    placements: tuple[Placement, ...] | None
    words: tuple[str, ...]
    total_score: int
    # Optional late-game / board-control diagnostics carried into traces.
    strategy_mode: str | None = None
    defense_penalty_cp: int = 0


def _tile_counter(game: Game) -> Counter[str]:
    tiles = Counter(game.bag.tiles)
    for player in game.players:
        tiles.update(player.rack)
    for row in game.board.cells:
        for cell in row:
            if cell.letter:
                tiles.update(["?" if cell.is_blank else cell.letter])
    return tiles


def _fingerprint(game: Game, *, include_pass_streak: bool) -> tuple[object, ...]:
    board = tuple(
        (cell.letter, cell.is_blank, cell.premium, cell.premium_used)
        for row in game.board.cells
        for cell in row
    )
    player_state: tuple[object, ...]
    if include_pass_streak:
        player_state = tuple((player.score, player.pass_streak) for player in game.players)
    else:
        player_state = tuple(player.score for player in game.players)
    return (
        board,
        tuple(game.bag.tiles),
        tuple(tuple(player.rack) for player in game.players),
        player_state,
        game.current_index,
        game.consecutive_scoreless_turns,
    )


def _rack_points(
    rack: Sequence[str], points: Mapping[str, int], *, strict_unknown_tile: bool,
) -> int:
    if strict_unknown_tile:
        return sum(points[tile] for tile in rack)
    return sum(points.get(tile, 0) for tile in rack)


def _rare_consumed(placements: Sequence[Placement], rare: frozenset[str]) -> int:
    return sum(1 for item in placements if item.letter in rare)


def _late_game_context(game: Game, config: SelfPlayConfig) -> LateGameContext | None:
    if not config.late_game_enabled:
        return None
    return late_game_context_for_game(
        game,
        acting_index=game.current_index,
        variant=config.variant_slug,
        opponent_action_rules="ai_scoring",
    )


def _seat_board_defense_enabled(config: SelfPlayConfig, acting_index: int) -> bool:
    if config.player_board_defense_enabled is not None:
        return config.player_board_defense_enabled[acting_index]
    return config.board_defense_enabled


def _score_differential(game: Game) -> int:
    players = game.players
    if len(players) != 2:
        return 0
    acting = game.current_index
    return players[acting].score - players[1 - acting].score


def _ranked_search(
    game: Game,
    rack: Sequence[str],
    context: SelfPlayContext,
    config: SelfPlayConfig,
) -> RankedSearchResult:
    return find_ranked_scoring_moves(
        game.board,
        rack,
        authority=context.authority,
        bag_count=game.bag.remaining(),
        top_k=config.ranked_top_k,
        max_nodes=config.ranked_max_nodes,
        max_elapsed_ms=config.ranked_max_elapsed_ms,
        max_unique_placements=config.ranked_max_unique_placements,
        tile_points=get_tile_points(config.variant_slug),
        blank_letters=context.blank_letters,
        variant=config.variant_slug,
        late_game_context=_late_game_context(game, config),
        score_differential=_score_differential(game),
        board_defense_enabled=_seat_board_defense_enabled(config, game.current_index),
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
        strategy_mode=result.strategy_mode,
        defense_penalty_cp=0 if candidate is None else candidate.defense_penalty_cp,
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
    context: SelfPlayContext,
    config: SelfPlayConfig,
) -> _Decision:
    if policy_id == POLICY_WITNESS:
        search = find_legal_scoring_move(
            game.board,
            rack,
            authority=context.authority,
            max_nodes=config.witness_max_nodes,
            max_elapsed_ms=config.witness_max_elapsed_ms,
            blank_letters=context.blank_letters,
            variant=config.variant_slug,
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

    ranked = _ranked_search(game, rack, context, config)
    if policy_id == POLICY_RANKED_WITNESS_SAFE:
        if ranked.candidates:
            assert ranked.status == "found"
            return _from_ranked(ranked, ranked.candidates[0])
        # Ranked is a quality path only. Only witness safety search authorizes
        # exchange/pass when ranked has no candidate (including indeterminate).
        safety = _choose(POLICY_WITNESS, game, rack, context, config)
        return replace(
            safety, nodes=ranked.nodes + safety.nodes,
            elapsed_ms=ranked.elapsed_ms + safety.elapsed_ms,
        )
    if ranked.status == "indeterminate":
        return _from_ranked(ranked, None)
    if not ranked.candidates:
        return _from_ranked(ranked, None)
    if policy_id == POLICY_RANKED_BEST:
        chosen = ranked.candidates[0]
    elif policy_id == POLICY_RANKED_RACK:
        # A strategic late-game ordering (exact/bounded solver or pre-endgame
        # valuation) outranks the rare-tile bonus: honor its first candidate.
        if ranked.strategy_mode is not None:
            chosen = ranked.candidates[0]
        else:
            chosen = _select_rack_aware(ranked.candidates, context.rare_tiles)
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


def simulate_engine_game(
    config: SelfPlayConfig, *, context: SelfPlayContext,
) -> SelfPlaySample:
    """Run one isolated engine game; optional snapshots let callers audit actions.

    Complete two-tile words are checked through physical token sequences.
    Longer words are never searched for two-letter substrings.
    Search budgets belong to the caller; this module supplies no search defaults.
    """
    variant_slug, policy_id, seed = config.variant_slug, config.policy_id, config.seed
    expected = Counter(get_tile_distribution(variant_slug))
    rare = context.rare_tiles
    bag = TileBag(seed=seed, variant=variant_slug)
    players = [
        PlayerState(name="P0", rack=bag.draw(7)),
        PlayerState(name="P1", rack=bag.draw(7)),
    ]
    game = Game(
        board=Board(context.premiums_path),
        bag=bag,
        players=players,
        starting_index=seed % 2,
    )
    initial_state = deepcopy(game) if config.record_trace else None
    previous_state = initial_state
    trace: list[SelfPlayPly] = []
    placement_scores = {"P0": 0, "P1": 0}
    fingerprints = {_fingerprint(game, include_pass_streak=config.include_pass_streak)}
    terminal_transitions = 0
    exchanges = 0
    passes = 0
    formed_words: list[str] = []
    formed_records: list[WordFound] = []
    nodes_sum = 0
    elapsed_sum = 0
    decisions = 0

    assert _tile_counter(game) == expected, f"{variant_slug} seed={seed} initial conservation"

    for ply in range(1, config.max_plies + 1):
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

        acting_policy = (
            config.player_policy_ids[acting_index]
            if config.player_policy_ids is not None else policy_id
        )
        decision = _choose(acting_policy, game, rack_before, context, config)
        awarded = 0
        decisions += 1
        nodes_sum += decision.nodes
        elapsed_sum += decision.elapsed_ms
        context_label = (
            f"{variant_slug} policy={policy_id} seed={seed} ply={ply} "
            f"status={decision.status} nodes={decision.nodes} elapsed_ms={decision.elapsed_ms}"
        )
        if decision.status == "indeterminate":
            raise SelfPlayInvariantError(f"{context_label}: bounded search must not authorize a non-scoring action")

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
            rejected = _rejected_two_tile_words(
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

        fingerprint = _fingerprint(game, include_pass_streak=config.include_pass_streak)
        assert fingerprint not in fingerprints, f"{context_label}: repeated full position"
        fingerprints.add(fingerprint)

        if config.record_trace:
            assert previous_state is not None
            after = deepcopy(game)
            trace.append(SelfPlayPly(ply, previous_state, after, decision, awarded))
            previous_state = after

        if game.ended:
            assert terminal_transitions == 1, context_label
            assert game.end_reason in ALLOWED_END_REASONS, context_label
            assert game.end_reason is not None, context_label
            if config.strict_unknown_tile is not None:
                expected_scores = [placement_scores[player.name] for player in players]
                leftovers = [_rack_points(
                        player.rack, get_tile_points(variant_slug),
                        strict_unknown_tile=config.strict_unknown_tile,
                    ) for player in players]
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
            rejected = _rejected_two_tile_words(
                tuple(formed_records),
                authority=context.authority,
            )
            assert rejected == ()
            return SelfPlaySample(
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
                search_cost=SelfPlaySearchCost(
                    nodes_sum=nodes_sum,
                    elapsed_ms_sum=elapsed_sum,
                    decision_count=decisions,
                ),
                formed_words=tuple(formed_words),
                rejected_two_letter_words=rejected,
                formed_records=tuple(formed_records),
                initial_state=initial_state,
                trace=tuple(trace),
            )

    raise SelfPlayInvariantError(f"{variant_slug} policy={policy_id} seed={seed}: did not terminate in {config.max_plies}")
