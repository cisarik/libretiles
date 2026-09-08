"""Seeded, node-bound engine position-set generator (provider-free).

Captures byte-stable board snapshots with ranked-search engine baselines.
Phase occupancy is a fraction of the variant tile pool, not of the 225 squares:
English has 100 tiles, so a 60% board-square threshold is unreachable. The
rule is stated in PHASE_RULE and hashed into every snapshot's conditions_digest.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from game.diagnostics import (
    UINT32_MAX,
    DiagnosticInputError,
    VariantProbeContext,
    dump_report_json,
    installed_variant_slugs,
    load_variant_context,
    observe_source_revision,
)
from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.board import BOARD_SIZE, Board
from gamecore.game import Game, GameEndReason, PlayerState
from gamecore.move_search import (
    DEFAULT_MAX_NODES,
    DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
    DEFAULT_RANKED_TOP_K,
    RankedSearchResult,
    find_ranked_scoring_moves,
)
from gamecore.selfplay import (
    POLICY_RANKED_BEST,
    SelfPlayConfig,
    SelfPlayContext,
    SelfPlayInvariantError,
    SelfPlayPly,
    simulate_engine_game,
)
from gamecore.tile_tracking import late_game_context_for_game
from gamecore.tiles import TileBag, get_tile_distribution, get_tile_points
from gamecore.types import BLANK_TOKEN
from gamecore.variant_store import VariantDefinition, _variant_path, load_variant

ARTIFACT_ID = "libretiles.position-set/v1"
DEFAULT_SEEDS: tuple[int, ...] = (300, 301, 302)
DEFAULT_POSITIONS_PER_PHASE = 8
DEFAULT_RANKED_MAX_NODES = 20_000
DEFAULT_RANKED_MAX_ELAPSED_MS = 10_000_000
DEFAULT_MAX_PLIES = 60
TOTAL_MIN = 1
TOTAL_MAX = 64
PHASES: tuple[str, ...] = ("opening", "mid", "late")
# Occupancy percents of the variant tile pool (integer compare: occupied * 100 ? N * pool).
OPENING_MAX_PERCENT = 25
MID_MAX_PERCENT = 60
PHASE_RULE: dict[str, str] = {
    "occupancy": "occupied_cells / tile_pool",
    "opening": "occupancy < 0.25",
    "mid": "0.25 <= occupancy <= 0.60",
    "late": "occupancy > 0.60",
}
PhaseName = Literal["opening", "mid", "late"]
WitnessStatus = Literal["found", "none", "indeterminate"]
PositionSetAsset = dict[str, Any]


class PositionSetError(Exception):
    """The generator could not produce a complete, conservative position set."""


@dataclass(frozen=True)
class PositionSetConfig:
    variant_slug: str
    seeds: tuple[int, ...] = DEFAULT_SEEDS
    positions_per_phase: int = DEFAULT_POSITIONS_PER_PHASE
    ranked_max_nodes: int = DEFAULT_RANKED_MAX_NODES
    ranked_max_elapsed_ms: int = DEFAULT_RANKED_MAX_ELAPSED_MS
    max_plies: int = DEFAULT_MAX_PLIES


def default_position_set_dir() -> Path:
    return get_assets_path() / "diagnostics" / "position_sets"


def default_output_path(variant_slug: str, set_digest: str) -> Path:
    return default_position_set_dir() / f"{variant_slug}-{set_digest[:8]}.json"


def config_to_dict(config: PositionSetConfig) -> dict[str, Any]:
    return {
        "variant_slug": config.variant_slug,
        "seeds": list(config.seeds),
        "positions_per_phase": config.positions_per_phase,
        "ranked_max_nodes": config.ranked_max_nodes,
        "ranked_max_elapsed_ms": config.ranked_max_elapsed_ms,
        "max_plies": config.max_plies,
    }


def positions_per_phase_for_total(total: int) -> int:
    if total < TOTAL_MIN or total > TOTAL_MAX:
        raise DiagnosticInputError(f"--total must be in {TOTAL_MIN}..{TOTAL_MAX}")
    return (total + len(PHASES) - 1) // len(PHASES)


def classify_phase(occupied: int, tile_pool: int) -> PhaseName:
    if tile_pool <= 0:
        raise PositionSetError("tile pool must be positive")
    if occupied * 100 < OPENING_MAX_PERCENT * tile_pool:
        return "opening"
    if occupied * 100 <= MID_MAX_PERCENT * tile_pool:
        return "mid"
    return "late"


def collect_asset_digests(variant_slug: str) -> dict[str, str]:
    """conditions_digest binds configuration + every content asset resolved through the asset
    helpers. Code identity is pinned by generator_source_revision, not by this digest.
    """
    return _asset_digests_for_variant(load_variant(variant_slug))


def generate_position_set(config: PositionSetConfig) -> PositionSetAsset:
    """Run node-bound ranked-best games and capture structured snapshots."""
    _validate_config(config)
    context = load_variant_context(config.variant_slug)
    tile_pool = sum(get_tile_distribution(config.variant_slug).values())
    asset_digests = _asset_digests_for_variant(context.variant)
    conditions_digest = _conditions_digest(config, asset_digests)
    by_seed: dict[int, dict[str, list[dict[str, Any]]]] = {}
    for seed in config.seeds:
        by_seed[seed] = _candidates_for_seed(
            config,
            seed=seed,
            probe=context,
            tile_pool=tile_pool,
            conditions_digest=conditions_digest,
        )
    snapshots = _allocate_across_seeds(config, by_seed)
    config_payload = config_to_dict(config)
    return {
        "artifact": ARTIFACT_ID,
        "variant_slug": config.variant_slug,
        "config": config_payload,
        "asset_digests": dict(asset_digests),
        "generator_source_revision": observe_source_revision(),
        "positions": snapshots,
        "set_digest": _set_digest(config_payload, snapshots),
    }


def dump_position_set_json(asset: Mapping[str, Any]) -> str:
    return dump_report_json(asset)


def game_from_snapshot(snapshot: Mapping[str, Any]) -> Game:
    """Rebuild a live Game from snapshot fields alone. No DB, no session."""
    variant_slug = snapshot.get("variant_slug")
    if not isinstance(variant_slug, str) or not variant_slug:
        raise PositionSetError("snapshot variant_slug must be a string")
    board = _board_from_snapshot(snapshot, premiums_path=get_premiums_path())
    bag_tiles = snapshot.get("bag_tiles")
    if not isinstance(bag_tiles, list) or not all(isinstance(tile, str) for tile in bag_tiles):
        raise PositionSetError("snapshot bag_tiles must be a list of tokens")
    # TileBag.__post_init__ refills an empty ``tiles`` list as a brand-new bag;
    # an explicitly empty snapshot bag must stay empty, so construct with a
    # placeholder and assign the true (possibly empty) sequence afterwards.
    bag = TileBag(tiles=list(bag_tiles) or ["?"], variant=variant_slug)
    bag.tiles = list(bag_tiles)
    getattr(bag, "_rng").setstate(_rng_state_from_json(snapshot.get("bag_rng_state")))
    to_move = snapshot.get("to_move_seat_index")
    if to_move not in {0, 1}:
        raise PositionSetError("snapshot to_move_seat_index must be 0 or 1")
    names = _string_pair(snapshot.get("seat_names"), "seat_names")
    scores = _int_pair(snapshot.get("seat_scores"), "seat_scores")
    streaks = _int_pair(snapshot.get("seat_pass_streaks"), "seat_pass_streaks")
    acting_rack = snapshot.get("rack")
    opponent_rack = snapshot.get("opponent_rack")
    if not isinstance(acting_rack, list) or not all(
        isinstance(tile, str) for tile in acting_rack
    ):
        raise PositionSetError("snapshot rack must be a list of tokens")
    if not isinstance(opponent_rack, list) or not all(
        isinstance(tile, str) for tile in opponent_rack
    ):
        raise PositionSetError("snapshot opponent_rack must be a list of tokens")
    racks: list[list[str]] = [[], []]
    racks[to_move] = list(acting_rack)
    racks[1 - to_move] = list(opponent_rack)
    players = [
        PlayerState(name=names[0], rack=racks[0], score=scores[0], pass_streak=streaks[0]),
        PlayerState(name=names[1], rack=racks[1], score=scores[1], pass_streak=streaks[1]),
    ]
    game = Game(board=board, bag=bag, players=players, starting_index=to_move)
    scoreless = snapshot.get("consecutive_scoreless_turns")
    if isinstance(scoreless, bool) or not isinstance(scoreless, int) or scoreless < 0:
        raise PositionSetError("snapshot consecutive_scoreless_turns must be a UINT")
    game.consecutive_scoreless_turns = scoreless
    ended = snapshot.get("ended")
    if not isinstance(ended, bool):
        raise PositionSetError("snapshot ended must be a boolean")
    game.ended = ended
    game.end_reason = _end_reason_from_json(snapshot.get("end_reason"))
    leftover = snapshot.get("leftover_points")
    if leftover is None:
        leftover = {}
    if not isinstance(leftover, dict) or not all(
        isinstance(key, str) and isinstance(value, int) and not isinstance(value, bool)
        for key, value in leftover.items()
    ):
        raise PositionSetError("snapshot leftover_points must be a string-to-int map")
    game.leftover_points = dict(leftover)
    winner = snapshot.get("winner_name")
    if winner is not None and not isinstance(winner, str):
        raise PositionSetError("snapshot winner_name must be a string or null")
    game.winner_name = winner
    no_moves = snapshot.get("no_moves_available")
    if not isinstance(no_moves, bool):
        raise PositionSetError("snapshot no_moves_available must be a boolean")
    game._no_moves_available = no_moves
    return game


def trim_position_set(asset: Mapping[str, Any], total: int) -> PositionSetAsset:
    """Keep the first ``total`` positions (opening, then mid, then late) and rehash."""
    if total < TOTAL_MIN or total > TOTAL_MAX:
        raise DiagnosticInputError(f"--total must be in {TOTAL_MIN}..{TOTAL_MAX}")
    positions = asset["positions"]
    if not isinstance(positions, list):
        raise PositionSetError("asset positions must be a list")
    if len(positions) < total:
        raise PositionSetError(
            f"position set has {len(positions)} snapshot(s); --total {total} cannot be filled"
        )
    trimmed = [_reindex_snapshot(item, index) for index, item in enumerate(positions[:total])]
    config = asset["config"]
    if not isinstance(config, dict):
        raise PositionSetError("asset config must be an object")
    asset_digests = asset.get("asset_digests")
    if asset_digests is not None and not isinstance(asset_digests, dict):
        raise PositionSetError("asset asset_digests must be an object")
    payload: PositionSetAsset = {
        "artifact": ARTIFACT_ID,
        "variant_slug": asset["variant_slug"],
        "config": dict(config),
        "generator_source_revision": asset["generator_source_revision"],
        "positions": trimmed,
        "set_digest": _set_digest(dict(config), trimmed),
    }
    if isinstance(asset_digests, dict):
        payload["asset_digests"] = dict(asset_digests)
    return payload


def _validate_config(config: PositionSetConfig) -> None:
    if not isinstance(config.variant_slug, str) or not config.variant_slug:
        raise DiagnosticInputError("--variant-slug is required")
    if config.variant_slug not in installed_variant_slugs():
        raise DiagnosticInputError(f"unknown variant '{config.variant_slug}'")
    if not config.seeds:
        raise DiagnosticInputError("--seeds must contain at least one integer")
    seen: set[int] = set()
    for seed in config.seeds:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise DiagnosticInputError("--seeds must be a comma-separated list of integers")
        if seed < 0 or seed > UINT32_MAX:
            raise DiagnosticInputError("--seeds values must be in 0..4294967295")
        if seed in seen:
            raise DiagnosticInputError("--seeds must not contain duplicates")
        seen.add(seed)
    if (
        isinstance(config.positions_per_phase, bool)
        or not isinstance(config.positions_per_phase, int)
        or config.positions_per_phase < 1
        or config.positions_per_phase > TOTAL_MAX
    ):
        raise DiagnosticInputError("positions_per_phase must be in 1..64")
    if (
        isinstance(config.ranked_max_nodes, bool)
        or not isinstance(config.ranked_max_nodes, int)
        or config.ranked_max_nodes < 1
    ):
        raise DiagnosticInputError("ranked_max_nodes must be a positive integer")
    if (
        isinstance(config.ranked_max_elapsed_ms, bool)
        or not isinstance(config.ranked_max_elapsed_ms, int)
        or config.ranked_max_elapsed_ms < 1
    ):
        raise DiagnosticInputError("ranked_max_elapsed_ms must be a positive integer")
    if (
        isinstance(config.max_plies, bool)
        or not isinstance(config.max_plies, int)
        or config.max_plies < 1
    ):
        raise DiagnosticInputError("max_plies must be a positive integer")


def _selfplay_config(config: PositionSetConfig, seed: int) -> SelfPlayConfig:
    return SelfPlayConfig(
        variant_slug=config.variant_slug,
        seed=seed,
        policy_id=POLICY_RANKED_BEST,
        max_plies=config.max_plies,
        witness_max_elapsed_ms=config.ranked_max_elapsed_ms,
        witness_max_nodes=DEFAULT_MAX_NODES,
        ranked_max_elapsed_ms=config.ranked_max_elapsed_ms,
        ranked_max_nodes=config.ranked_max_nodes,
        ranked_top_k=DEFAULT_RANKED_TOP_K,
        ranked_max_unique_placements=DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
        include_pass_streak=False,
        strict_unknown_tile=False,
        record_trace=True,
        # Explicit: reconstruction (_ranked_on_game) builds the SAME context,
        # otherwise mount equivalence would compare different policies.
        late_game_enabled=True,
        # Historical diagnostic assets pin ranked traces without board defense.
        board_defense_enabled=False,
    )


def _selfplay_context(probe: VariantProbeContext) -> SelfPlayContext:
    return SelfPlayContext(
        authority=probe.authority,
        letters=probe.letters,
        blank_letters=tuple(probe.variant.playable_letters),
        premiums_path=get_premiums_path(),
        rare_tiles=frozenset(),
    )


def _candidates_for_seed(
    config: PositionSetConfig,
    *,
    seed: int,
    probe: VariantProbeContext,
    tile_pool: int,
    conditions_digest: str,
) -> dict[str, list[dict[str, Any]]]:
    expected = Counter(get_tile_distribution(config.variant_slug))
    try:
        sample = simulate_engine_game(
            _selfplay_config(config, seed),
            context=_selfplay_context(probe),
        )
    except SelfPlayInvariantError as exc:
        raise PositionSetError(str(exc)) from exc
    grouped: dict[str, list[dict[str, Any]]] = {phase: [] for phase in PHASES}
    for event in sample.trace:
        snapshot = _snapshot_from_ply(
            event,
            config=config,
            probe=probe,
            seed=seed,
            tile_pool=tile_pool,
            expected=expected,
            conditions_digest=conditions_digest,
        )
        grouped[snapshot["phase"]].append(snapshot)
    return grouped


def _snapshot_from_ply(
    event: SelfPlayPly,
    *,
    config: PositionSetConfig,
    probe: VariantProbeContext,
    seed: int,
    tile_pool: int,
    expected: Counter[str],
    conditions_digest: str,
) -> dict[str, Any]:
    game = event.before
    variant_slug = config.variant_slug
    inventory = _tile_inventory(game)
    if inventory != expected:
        raise PositionSetError(
            f"{variant_slug} seed={seed} ply={event.ply}: tile conservation failed"
        )
    occupied = _occupied_count(game.board)
    phase = classify_phase(occupied, tile_pool)
    if len(game.players) != 2:
        raise PositionSetError("position snapshots require exactly two seats")
    acting = game.current_player()
    opponent = game.players[1 - game.current_index]
    bag_tiles = list(game.bag.tiles)
    bag_remaining = game.bag.remaining()
    if len(bag_tiles) != bag_remaining:
        raise PositionSetError(
            f"{variant_slug} seed={seed} ply={event.ply}: "
            f"bag sequence length {len(bag_tiles)} != bag_remaining {bag_remaining}"
        )
    decision = event.decision
    status = decision.status
    if status not in {"found", "none", "indeterminate"}:
        raise PositionSetError(f"unexpected search status {status!r}")
    ranked_best: int | None
    if status == "found":
        ranked_best = decision.total_score
    else:
        ranked_best = None
    end_reason = game.end_reason.name if game.end_reason is not None else None
    snapshot = {
        "position_index": 0,
        "phase": phase,
        "variant_slug": variant_slug,
        "seed": seed,
        "ply": event.ply,
        "board": _board_payload(game.board),
        "rack": list(acting.rack),
        "opponent_rack": list(opponent.rack),
        "to_move_seat_index": game.current_index,
        "seat_names": [player.name for player in game.players],
        "seat_scores": [player.score for player in game.players],
        "seat_pass_streaks": [player.pass_streak for player in game.players],
        "bag_remaining": bag_remaining,
        "bag_tiles": bag_tiles,
        "bag_rng_state": _rng_state_to_json(getattr(game.bag, "_rng")),
        "consecutive_scoreless_turns": game.consecutive_scoreless_turns,
        "ended": game.ended,
        "end_reason": end_reason,
        "leftover_points": dict(game.leftover_points),
        "winner_name": game.winner_name,
        "no_moves_available": game._no_moves_available,
        "engine_baseline": {
            "ranked_best_score": ranked_best,
            "ranked_search_complete": decision.complete,
            "witness_status": status,
        },
        "conditions_digest": conditions_digest,
    }
    reconstructed = _inventory_from_snapshot(snapshot)
    if reconstructed != expected:
        raise PositionSetError(
            f"{variant_slug} seed={seed} ply={event.ply}: "
            "snapshot field conservation failed"
        )
    _assert_mount_equivalence(snapshot, event, config=config, probe=probe)
    return snapshot


def _allocate_across_seeds(
    config: PositionSetConfig,
    by_seed: Mapping[int, Mapping[str, Sequence[dict[str, Any]]]],
) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    quota = config.positions_per_phase
    for phase in PHASES:
        cursors = {seed: 0 for seed in config.seeds}
        taken = 0
        while taken < quota:
            progressed = False
            for seed in config.seeds:
                if taken >= quota:
                    break
                pool = by_seed[seed][phase]
                index = cursors[seed]
                if index < len(pool):
                    snapshots.append(pool[index])
                    cursors[seed] = index + 1
                    taken += 1
                    progressed = True
            if not progressed:
                raise PositionSetError(
                    f"phase {phase}: need {quota} snapshot(s), found {taken}"
                )
    return [_reindex_snapshot(item, index) for index, item in enumerate(snapshots)]


def _reindex_snapshot(item: Mapping[str, Any], index: int) -> dict[str, Any]:
    payload = dict(item)
    payload["position_index"] = index
    return payload


def _board_payload(board: Board) -> list[list[dict[str, str | bool | None]]]:
    rows: list[list[dict[str, str | bool | None]]] = []
    for row in board.cells:
        payload_row: list[dict[str, str | bool | None]] = []
        for cell in row:
            if cell.is_malformed:
                raise PositionSetError("malformed board cell")
            token = cell.token if cell.token is not None else ""
            payload_row.append(
                {
                    "token": token,
                    "blank_as": cell.blank_as,
                    "premium_used": cell.premium_used,
                }
            )
        rows.append(payload_row)
    if len(rows) != BOARD_SIZE or any(len(row) != BOARD_SIZE for row in rows):
        raise PositionSetError("board must be 15x15 structured cells")
    return rows


def _board_from_snapshot(snapshot: Mapping[str, Any], *, premiums_path: str) -> Board:
    raw = snapshot.get("board")
    if not isinstance(raw, list) or len(raw) != BOARD_SIZE:
        raise PositionSetError("snapshot board must be 15x15")
    board = Board(premiums_path)
    for row_index, row in enumerate(raw):
        if not isinstance(row, list) or len(row) != BOARD_SIZE:
            raise PositionSetError("snapshot board must be 15x15")
        for col_index, cell in enumerate(row):
            if not isinstance(cell, dict):
                raise PositionSetError("snapshot cell must be an object")
            token_raw = cell.get("token")
            blank_raw = cell.get("blank_as")
            used = cell.get("premium_used")
            if not isinstance(token_raw, str):
                raise PositionSetError("snapshot cell token must be a string")
            if blank_raw is not None and not isinstance(blank_raw, str):
                raise PositionSetError("snapshot cell blank_as must be a string or null")
            if not isinstance(used, bool):
                raise PositionSetError("snapshot cell premium_used must be a boolean")
            target = board.cells[row_index][col_index]
            target.token = token_raw if token_raw else None
            target.blank_as = blank_raw
            target.premium_used = used
            if target.is_malformed:
                raise PositionSetError("reconstructed board cell is malformed")
    return board


def _assert_mount_equivalence(
    snapshot: Mapping[str, Any],
    event: SelfPlayPly,
    *,
    config: PositionSetConfig,
    probe: VariantProbeContext,
) -> None:
    mounted = game_from_snapshot(snapshot)
    result = _ranked_on_game(mounted, config=config, probe=probe)
    recorded = event.decision
    top = result.candidates[0] if result.candidates else None
    if result.status != recorded.status:
        raise PositionSetError(
            f"mount-equivalence status {result.status!r} != {recorded.status!r} "
            f"at ply {event.ply}"
        )
    if result.complete != recorded.complete:
        raise PositionSetError(
            f"mount-equivalence complete {result.complete} != {recorded.complete} "
            f"at ply {event.ply}"
        )
    if result.nodes != recorded.nodes:
        raise PositionSetError(
            f"mount-equivalence nodes {result.nodes} != {recorded.nodes} "
            f"at ply {event.ply}"
        )
    mounted_score = None if top is None else top.total_score
    recorded_score = recorded.total_score if recorded.status == "found" else None
    if mounted_score != recorded_score:
        raise PositionSetError(
            f"mount-equivalence score {mounted_score} != {recorded_score} "
            f"at ply {event.ply}"
        )
    mounted_placements = None if top is None else top.placements
    if mounted_placements != recorded.placements:
        raise PositionSetError(
            f"mount-equivalence placements differ at ply {event.ply}"
        )
    mounted_words = () if top is None else top.words
    if mounted_words != recorded.words:
        raise PositionSetError(
            f"mount-equivalence words {mounted_words} != {recorded.words} "
            f"at ply {event.ply}"
        )


def _ranked_on_game(
    game: Game,
    *,
    config: PositionSetConfig,
    probe: VariantProbeContext,
) -> RankedSearchResult:
    return find_ranked_scoring_moves(
        game.board,
        game.current_player().rack,
        authority=probe.authority,
        bag_count=game.bag.remaining(),
        top_k=DEFAULT_RANKED_TOP_K,
        max_nodes=config.ranked_max_nodes,
        max_elapsed_ms=config.ranked_max_elapsed_ms,
        max_unique_placements=DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
        tile_points=get_tile_points(config.variant_slug),
        blank_letters=tuple(probe.variant.playable_letters),
        variant=config.variant_slug,
        # Mount equivalence: identical late-game policy to the generating
        # self-play search (SelfPlayConfig.late_game_enabled=True).
        late_game_context=late_game_context_for_game(
            game,
            acting_index=game.current_index,
            variant=config.variant_slug,
            opponent_action_rules="ai_scoring",
        ),
        # Explicit: a default differential of zero still changes ranking
        # under the enabled evaluator. Generation and remount stay off.
        board_defense_enabled=False,
        score_differential=0,
    )


def _rng_state_to_json(rng: object) -> list[object]:
    getstate = getattr(rng, "getstate", None)
    if getstate is None:
        raise PositionSetError("bag RNG has no getstate")
    version, mt, gauss = getstate()
    if not isinstance(mt, tuple):
        raise PositionSetError("bag RNG state is not serializable")
    return [version, list(mt), gauss]


def _rng_state_from_json(payload: object) -> tuple[object, ...]:
    if not isinstance(payload, list) or len(payload) != 3:
        raise PositionSetError("bag_rng_state must be a 3-element list")
    version, mt, gauss = payload
    if not isinstance(mt, list) or not all(isinstance(item, int) for item in mt):
        raise PositionSetError("bag_rng_state mt must be a list of ints")
    return (version, tuple(mt), gauss)


def _string_pair(payload: object, name: str) -> tuple[str, str]:
    if not isinstance(payload, list) or len(payload) != 2:
        raise PositionSetError(f"snapshot {name} must be a 2-string list")
    left, right = payload
    if not isinstance(left, str) or not isinstance(right, str):
        raise PositionSetError(f"snapshot {name} must be a 2-string list")
    return (left, right)


def _int_pair(payload: object, name: str) -> tuple[int, int]:
    if not isinstance(payload, list) or len(payload) != 2:
        raise PositionSetError(f"snapshot {name} must be a 2-int list")
    left, right = payload
    if isinstance(left, bool) or isinstance(right, bool):
        raise PositionSetError(f"snapshot {name} must be a 2-int list")
    if not isinstance(left, int) or not isinstance(right, int):
        raise PositionSetError(f"snapshot {name} must be a 2-int list")
    return (left, right)


def _end_reason_from_json(payload: object) -> GameEndReason | None:
    if payload is None:
        return None
    if not isinstance(payload, str):
        raise PositionSetError("snapshot end_reason must be a string or null")
    try:
        return GameEndReason[payload]
    except KeyError as exc:
        raise PositionSetError(f"unknown end_reason {payload!r}") from exc


def _occupied_count(board: Board) -> int:
    return sum(1 for row in board.cells for cell in row if cell.token is not None)


def _tile_inventory(game: Game) -> Counter[str]:
    tiles: Counter[str] = Counter(game.bag.tiles)
    for player in game.players:
        tiles.update(player.rack)
    for row in game.board.cells:
        for cell in row:
            if cell.token:
                tiles.update([BLANK_TOKEN if cell.token == BLANK_TOKEN else cell.token])
    return tiles


def _inventory_from_snapshot(snapshot: Mapping[str, Any]) -> Counter[str]:
    board = snapshot["board"]
    rack = snapshot["rack"]
    opponent_rack = snapshot["opponent_rack"]
    bag_tiles = snapshot["bag_tiles"]
    if not isinstance(board, list) or not isinstance(rack, list):
        raise PositionSetError("snapshot racks and board must be lists")
    if not isinstance(opponent_rack, list) or not isinstance(bag_tiles, list):
        raise PositionSetError("snapshot opponent_rack and bag_tiles must be lists")
    tiles: Counter[str] = Counter(token for token in bag_tiles if isinstance(token, str))
    tiles.update(token for token in rack if isinstance(token, str))
    tiles.update(token for token in opponent_rack if isinstance(token, str))
    for row in board:
        if not isinstance(row, list):
            raise PositionSetError("snapshot board row must be a list")
        for cell in row:
            if not isinstance(cell, dict):
                raise PositionSetError("snapshot cell must be an object")
            token = cell.get("token")
            if isinstance(token, str) and token:
                tiles.update([BLANK_TOKEN if token == BLANK_TOKEN else token])
    return tiles


def _conditions_payload(
    config: PositionSetConfig, asset_digests: Mapping[str, str]
) -> dict[str, Any]:
    payload = config_to_dict(config)
    payload["policy_id"] = POLICY_RANKED_BEST
    payload["phase_rule"] = dict(PHASE_RULE)
    payload["asset_digests"] = dict(asset_digests)
    return payload


def _conditions_digest(
    config: PositionSetConfig, asset_digests: Mapping[str, str]
) -> str:
    return _sha256_canonical(_conditions_payload(config, asset_digests))


def _resolved_content_asset_paths(variant: VariantDefinition) -> tuple[Path, ...]:
    """Every content file the generation path resolves through asset helpers.

    Board loads premiums via get_premiums_path; load_variant / tile points and
    distribution via _variant_path; WordAuthority via Path properties on the
    VariantDefinition (lexicon and two-tile file when present). A future Path
    property on the definition is hashed automatically.
    """
    ordered: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path | str | None) -> None:
        if path is None:
            return
        candidate = Path(path)
        key = candidate.resolve()
        if key in seen:
            return
        seen.add(key)
        ordered.append(candidate)

    add(get_premiums_path())
    add(_variant_path(variant.slug))
    for field in vars(type(variant)).values():
        if isinstance(field, property):
            value = field.__get__(variant, type(variant))
            if isinstance(value, Path):
                add(value)
    return tuple(ordered)


def _asset_digests_for_variant(variant: VariantDefinition) -> dict[str, str]:
    return {
        _asset_identity(path): _sha256_file(path)
        for path in _resolved_content_asset_paths(variant)
    }


def _asset_identity(path: Path) -> str:
    assets = get_assets_path().resolve()
    resolved = path.resolve()
    try:
        return resolved.relative_to(assets).as_posix()
    except ValueError as exc:
        raise PositionSetError(f"hashed asset is not under assets/: {path}") from exc


def _sha256_file(path: Path) -> str:
    if not path.is_file():
        raise PositionSetError(f"hashed asset missing: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _set_digest(config: Mapping[str, Any], positions: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_canonical({"config": config, "positions": list(positions)})


def _sha256_canonical(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
