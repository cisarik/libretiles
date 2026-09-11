"""Pytest hooks for Libre Tiles backend (pytest-django)."""

from __future__ import annotations

import os

from tests.opt_in import (
    BENCHMARK_ONLY_FILES,
    any_opt_in_enabled,
)


def pytest_ignore_collect(collection_path, config) -> bool | None:  # noqa: ARG001
    """Do not import pure-benchmark modules unless their own env var is set."""
    name = collection_path.name
    if name not in BENCHMARK_ONLY_FILES:
        return None
    if os.environ.get("LIBRETILES_RUN_BENCHMARKS") == "1":
        return False
    if name == "test_board_defense_benchmark.py" and (
        os.environ.get("LIBRETILES_RUN_BOARD_DEFENSE_ACCEPTANCE") == "1"
    ):
        return False
    if name == "test_endgame_benchmark.py" and (
        os.environ.get("LIBRETILES_RUN_ENDGAME_ACCEPTANCE") == "1"
    ):
        return False
    return True


def pytest_collection_modifyitems(config, items) -> None:
    """Deselect ``slow`` tests in the default run so they never execute.

    Opt-in env vars restore them; each test still has its own skipif. This is
    not ``addopts = -m 'not slow'``, which would combine with ``-m slow`` into
    an empty selection.
    """
    if any_opt_in_enabled():
        return
    remaining = []
    deselected = []
    for item in items:
        if "slow" in item.keywords:
            deselected.append(item)
        else:
            remaining.append(item)
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = remaining
