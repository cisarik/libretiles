"""Deterministic engine position-set generator."""

from __future__ import annotations

import ast
import json
from collections import Counter
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command, get_commands
from django.core.management.base import CommandError

from game.diagnostics import load_variant_context
from game.position_sets import (
    ARTIFACT_ID,
    DEFAULT_RANKED_MAX_ELAPSED_MS,
    DEFAULT_RANKED_MAX_NODES,
    PHASES,
    PositionSetConfig,
    classify_phase,
    collect_asset_digests,
    dump_position_set_json,
    game_from_snapshot,
    generate_position_set,
)
from gamecore.move_search import (
    DEFAULT_RANKED_MAX_ELAPSED_MS as PRODUCTION_ELAPSED_MS,
    DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
    DEFAULT_RANKED_TOP_K,
    find_ranked_scoring_moves,
)
from gamecore.tiles import get_tile_distribution, get_tile_points

_SMALL = PositionSetConfig(
    variant_slug="english",
    seeds=(300,),
    positions_per_phase=1,
)
_GAME_ROOT = Path(__file__).resolve().parents[1] / "game"
_FORBIDDEN = frozenset({"pytest", "pytest_django", "_pytest", "ruff", "mypy"})
_COMMITTED_DIR = (
    Path(__file__).resolve().parents[1] / "assets" / "diagnostics" / "position_sets"
)
_COMMITTED_SET_DIGEST = (
    "f5ae61b467b4f21e6fe9ee94024e9c3c06e09e0dbae7e6cc8954ff911dc86ef4"
)


@pytest.fixture(scope="module")
def small_pair() -> tuple[dict[str, object], dict[str, object]]:
    first = generate_position_set(_SMALL)
    second = generate_position_set(_SMALL)
    return first, second


def test_f3_same_config_is_byte_identical(
    small_pair: tuple[dict[str, object], dict[str, object]],
) -> None:
    first, second = small_pair
    assert dump_position_set_json(first) == dump_position_set_json(second)
    assert first["set_digest"] == second["set_digest"]
    assert isinstance(first["set_digest"], str)
    assert len(first["set_digest"]) == 64


def test_f4_structured_cells_and_conservation(
    small_pair: tuple[dict[str, object], dict[str, object]],
) -> None:
    asset, _ = small_pair
    positions = asset["positions"]
    assert isinstance(positions, list)
    assert [item["phase"] for item in positions] == list(PHASES)
    pool = Counter(get_tile_distribution("english"))
    pool_size = sum(pool.values())
    for snapshot in positions:
        assert isinstance(snapshot, dict)
        board = snapshot["board"]
        assert isinstance(board, list)
        assert len(board) == 15
        occupied = 0
        on_board: Counter[str] = Counter()
        for row in board:
            assert isinstance(row, list)
            assert len(row) == 15
            for cell in row:
                assert isinstance(cell, dict)
                assert set(cell) == {"token", "blank_as", "premium_used"}
                token = cell["token"]
                blank_as = cell["blank_as"]
                used = cell["premium_used"]
                assert isinstance(token, str)
                assert blank_as is None or isinstance(blank_as, str)
                assert isinstance(used, bool)
                if token == "":
                    assert blank_as is None
                    continue
                occupied += 1
                if token == "?":
                    assert isinstance(blank_as, str) and blank_as
                    on_board["?"] += 1
                else:
                    assert blank_as is None
                    on_board[token] += 1
        rack = snapshot["rack"]
        assert isinstance(rack, list)
        assert all(isinstance(tile, str) and tile for tile in rack)
        opponent_rack = snapshot["opponent_rack"]
        assert isinstance(opponent_rack, list)
        assert all(isinstance(tile, str) and tile for tile in opponent_rack)
        bag_tiles = snapshot["bag_tiles"]
        assert isinstance(bag_tiles, list)
        assert all(isinstance(tile, str) and tile for tile in bag_tiles)
        bag_remaining = snapshot["bag_remaining"]
        assert isinstance(bag_remaining, int)
        assert len(bag_tiles) == bag_remaining
        inventory = on_board + Counter(rack) + Counter(opponent_rack) + Counter(bag_tiles)
        assert inventory == pool
        assert snapshot["phase"] == classify_phase(occupied, pool_size)


def test_f5_node_bound_capture_is_stable(
    small_pair: tuple[dict[str, object], dict[str, object]],
) -> None:
    first, second = small_pair
    config = first["config"]
    assert isinstance(config, dict)
    assert config["ranked_max_nodes"] == DEFAULT_RANKED_MAX_NODES
    assert config["ranked_max_elapsed_ms"] == DEFAULT_RANKED_MAX_ELAPSED_MS
    assert PRODUCTION_ELAPSED_MS == 750
    assert config["ranked_max_elapsed_ms"] != PRODUCTION_ELAPSED_MS
    for left, right in zip(first["positions"], second["positions"], strict=True):
        assert isinstance(left, dict)
        assert isinstance(right, dict)
        assert left["engine_baseline"] == right["engine_baseline"]
        baseline = left["engine_baseline"]
        assert isinstance(baseline, dict)
        assert set(baseline) == {
            "ranked_best_score",
            "ranked_search_complete",
            "witness_status",
        }
        assert baseline["witness_status"] in {"found", "none", "indeterminate"}
        assert isinstance(baseline["ranked_search_complete"], bool)


def test_f8_snapshot_is_self_contained(
    small_pair: tuple[dict[str, object], dict[str, object]],
) -> None:
    asset, _ = small_pair
    envelope_digests = asset["asset_digests"]
    assert isinstance(envelope_digests, dict)
    assert envelope_digests == collect_asset_digests("english")
    positions = asset["positions"]
    assert isinstance(positions, list)
    for snapshot in positions:
        assert isinstance(snapshot, dict)
        assert "opponent_rack" in snapshot
        assert "bag_tiles" in snapshot
        assert snapshot["bag_remaining"] == len(snapshot["bag_tiles"])
        assert isinstance(snapshot["board"][0][0], dict)
        assert "premium_used" in snapshot["board"][0][0]
        assert "seat_scores" in snapshot
        assert "consecutive_scoreless_turns" in snapshot
        assert "bag_rng_state" in snapshot


def test_f9_mount_equivalence_from_json_roundtrip(
    small_pair: tuple[dict[str, object], dict[str, object]],
) -> None:
    asset, _ = small_pair
    payload = json.loads(dump_position_set_json(asset))
    probe = load_variant_context("english")
    positions = payload["positions"]
    assert isinstance(positions, list)
    for snapshot in positions:
        assert isinstance(snapshot, dict)
        mounted = game_from_snapshot(snapshot)
        result = find_ranked_scoring_moves(
            mounted.board,
            mounted.current_player().rack,
            authority=probe.authority,
            bag_count=mounted.bag.remaining(),
            top_k=DEFAULT_RANKED_TOP_K,
            max_nodes=DEFAULT_RANKED_MAX_NODES,
            max_elapsed_ms=DEFAULT_RANKED_MAX_ELAPSED_MS,
            max_unique_placements=DEFAULT_RANKED_MAX_UNIQUE_PLACEMENTS,
            tile_points=get_tile_points("english"),
            blank_letters=tuple(probe.variant.playable_letters),
            variant="english",
        )
        baseline = snapshot["engine_baseline"]
        assert isinstance(baseline, dict)
        assert result.status == baseline["witness_status"]
        assert result.complete == baseline["ranked_search_complete"]
        top = result.candidates[0] if result.candidates else None
        mounted_score = None if top is None else top.total_score
        assert mounted_score == baseline["ranked_best_score"]
        assert mounted.consecutive_scoreless_turns == snapshot["consecutive_scoreless_turns"]
        assert [player.score for player in mounted.players] == snapshot["seat_scores"]
        rng_state = snapshot["bag_rng_state"]
        restored = getattr(mounted.bag, "_rng").getstate()
        assert restored[0] == rng_state[0]
        assert list(restored[1]) == rng_state[1]
        assert restored[2] == rng_state[2]


def test_f10_conditions_digest_includes_asset_content_hashes() -> None:
    from game.position_sets import _conditions_digest

    assets = collect_asset_digests("english")
    assert "premiums.json" in assets
    assert any(name.startswith("dicts/") for name in assets)
    assert "variants/english.json" in assets
    for digest in assets.values():
        assert isinstance(digest, str) and len(digest) == 64
    baseline = _conditions_digest(_SMALL, assets)
    mutated = dict(assets)
    first_key = sorted(mutated)[0]
    mutated[first_key] = "0" * 64 if mutated[first_key] != "0" * 64 else "1" * 64
    moved = _conditions_digest(_SMALL, mutated)
    assert moved != baseline
    restored = _conditions_digest(_SMALL, collect_asset_digests("english"))
    assert restored == baseline


def test_f6_cli_writes_asset_and_rejects_bad_input(tmp_path: Path) -> None:
    stdout = StringIO()
    target = tmp_path / "english-sample.json"
    call_command(
        "generate_position_set",
        variant_slug="english",
        seeds="300",
        total=3,
        output=str(target),
        stdout=stdout,
        stderr=StringIO(),
    )
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["artifact"] == ARTIFACT_ID
    digest = payload["set_digest"]
    assert isinstance(digest, str)
    assert stdout.getvalue().strip().endswith(digest)
    assert "generate_position_set" in get_commands()

    with pytest.raises(CommandError) as unknown:
        call_command(
            "generate_position_set",
            variant_slug="klingon",
            seeds="300",
            total=3,
            output=str(tmp_path / "nope.json"),
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert unknown.value.returncode == 2

    with pytest.raises(CommandError) as bad_total:
        call_command(
            "generate_position_set",
            variant_slug="english",
            seeds="300",
            total=0,
            output=str(tmp_path / "zero.json"),
            stdout=StringIO(),
            stderr=StringIO(),
        )
    assert bad_total.value.returncode == 2


def test_f7_new_game_modules_do_not_import_dev_group_packages() -> None:
    offenders: list[str] = []
    paths = [
        _GAME_ROOT / "position_sets.py",
        _GAME_ROOT / "management" / "commands" / "generate_position_set.py",
    ]
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported.add(alias.name.split(".", 1)[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
        bad = imported & _FORBIDDEN
        if bad:
            offenders.append(f"{path.name}: {sorted(bad)}")
    assert offenders == []


def test_committed_sample_matches_generator_digest() -> None:
    files = sorted(_COMMITTED_DIR.glob("*.json"))
    assert len(files) == 1
    committed = json.loads(files[0].read_text(encoding="utf-8"))
    assert committed["artifact"] == ARTIFACT_ID
    config = committed["config"]
    assert isinstance(config, dict)
    assert config["variant_slug"] == "english"
    assert config["seeds"] == [300, 301, 302]
    assert config["positions_per_phase"] == 8
    asset_digests = committed["asset_digests"]
    assert isinstance(asset_digests, dict)
    assert asset_digests == collect_asset_digests("english")
    positions = committed["positions"]
    assert isinstance(positions, list)
    assert len(positions) == 24
    pool = Counter(get_tile_distribution("english"))
    for snapshot in positions:
        assert isinstance(snapshot, dict)
        assert "opponent_rack" in snapshot
        assert "bag_tiles" in snapshot
        on_board: Counter[str] = Counter()
        board = snapshot["board"]
        assert isinstance(board, list)
        for row in board:
            assert isinstance(row, list)
            for cell in row:
                assert isinstance(cell, dict)
                token = cell["token"]
                if isinstance(token, str) and token:
                    on_board["?" if token == "?" else token] += 1
                assert isinstance(cell.get("premium_used"), bool)
        rack = snapshot["rack"]
        opponent_rack = snapshot["opponent_rack"]
        bag_tiles = snapshot["bag_tiles"]
        assert isinstance(rack, list)
        assert isinstance(opponent_rack, list)
        assert isinstance(bag_tiles, list)
        assert snapshot["bag_remaining"] == len(bag_tiles)
        assert "seat_scores" in snapshot
        assert "consecutive_scoreless_turns" in snapshot
        assert "bag_rng_state" in snapshot
        inventory = (
            on_board + Counter(rack) + Counter(opponent_rack) + Counter(bag_tiles)
        )
        assert inventory == pool
    digest = committed["set_digest"]
    assert digest == _COMMITTED_SET_DIGEST
    assert isinstance(digest, str)
    assert files[0].name == f"english-{digest[:8]}.json"
