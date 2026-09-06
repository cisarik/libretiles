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
from gamecore.game import Game
from gamecore.move_search import (
    DEFAULT_MAX_NODES,
    DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
    DEFAULT_RANKED_TOP_K,
)
from gamecore.selfplay import (
    POLICY_RANKED_BEST,
    SelfPlayConfig,
    SelfPlayContext,
    SelfPlayInvariantError,
    SelfPlayPly,
    simulate_engine_game,
)
from gamecore.tiles import get_tile_distribution
from gamecore.types import BLANK_TOKEN

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


def generate_position_set(config: PositionSetConfig) -> PositionSetAsset:
    """Run node-bound ranked-best games and capture structured snapshots."""
    _validate_config(config)
    context = load_variant_context(config.variant_slug)
    tile_pool = sum(get_tile_distribution(config.variant_slug).values())
    conditions_digest = _conditions_digest(config)
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
        "generator_source_revision": observe_source_revision(),
        "positions": snapshots,
        "set_digest": _set_digest(config_payload, snapshots),
    }


def dump_position_set_json(asset: Mapping[str, Any]) -> str:
    return dump_report_json(asset)


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
    payload: PositionSetAsset = {
        "artifact": ARTIFACT_ID,
        "variant_slug": asset["variant_slug"],
        "config": dict(config),
        "generator_source_revision": asset["generator_source_revision"],
        "positions": trimmed,
        "set_digest": _set_digest(dict(config), trimmed),
    }
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
            variant_slug=config.variant_slug,
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
    variant_slug: str,
    seed: int,
    tile_pool: int,
    expected: Counter[str],
    conditions_digest: str,
) -> dict[str, Any]:
    game = event.before
    inventory = _tile_inventory(game)
    if inventory != expected:
        raise PositionSetError(
            f"{variant_slug} seed={seed} ply={event.ply}: tile conservation failed"
        )
    occupied = _occupied_count(game.board)
    phase = classify_phase(occupied, tile_pool)
    acting = game.current_player()
    decision = event.decision
    status = decision.status
    if status not in {"found", "none", "indeterminate"}:
        raise PositionSetError(f"unexpected search status {status!r}")
    ranked_best: int | None
    if status == "found":
        ranked_best = decision.total_score
    else:
        ranked_best = None
    return {
        "position_index": 0,
        "phase": phase,
        "variant_slug": variant_slug,
        "seed": seed,
        "ply": event.ply,
        "board": _board_payload(game.board),
        "rack": list(acting.rack),
        "to_move_seat_index": game.current_index,
        "bag_remaining": game.bag.remaining(),
        "engine_baseline": {
            "ranked_best_score": ranked_best,
            "ranked_search_complete": decision.complete,
            "witness_status": status,
        },
        "conditions_digest": conditions_digest,
    }


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


def _board_payload(board: Board) -> list[list[dict[str, str | None]]]:
    rows: list[list[dict[str, str | None]]] = []
    for row in board.cells:
        payload_row: list[dict[str, str | None]] = []
        for cell in row:
            if cell.is_malformed:
                raise PositionSetError("malformed board cell")
            token = cell.token if cell.token is not None else ""
            payload_row.append({"token": token, "blank_as": cell.blank_as})
        rows.append(payload_row)
    if len(rows) != BOARD_SIZE or any(len(row) != BOARD_SIZE for row in rows):
        raise PositionSetError("board must be 15x15 structured cells")
    return rows


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


def _conditions_payload(config: PositionSetConfig) -> dict[str, Any]:
    payload = config_to_dict(config)
    payload["policy_id"] = POLICY_RANKED_BEST
    payload["phase_rule"] = dict(PHASE_RULE)
    return payload


def _conditions_digest(config: PositionSetConfig) -> str:
    return _sha256_canonical(_conditions_payload(config))


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
