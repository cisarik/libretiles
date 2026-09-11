"""Opt-in gates for engine self-play, diagnostic search, and long matrices.

Default ``pytest`` must stay a development loop, not a multi-minute self-play
harness. These markers skip the expensive tests unless the matching env var is
``1``. Code stays in the tree; it is not commented out.
"""

from __future__ import annotations

import os

import pytest

SIMULATION_ENV = "LIBRETILES_RUN_SIMULATION"

# Any of these un-hides ``slow`` tests during collection. Individual tests still
# enforce their own skipif (benchmarks, wide acceptance, postgres, …).
OPT_IN_ENVS: tuple[str, ...] = (
    SIMULATION_ENV,
    "LIBRETILES_RUN_BENCHMARKS",
    "LIBRETILES_RUN_ENDGAME_ACCEPTANCE",
    "LIBRETILES_RUN_BOARD_DEFENSE_ACCEPTANCE",
    "LIBRETILES_RUN_STRENGTH_ACCEPTANCE",
    "LIBRETILES_RUN_ENDGAME_MATRIX",
    "LIBRETILES_RUN_SLOVAK_FULL_GAME",
)

# Files whose every test is already env-gated. Skipping collection avoids
# loading Collins/Slovak lexicons on every default pytest.
BENCHMARK_ONLY_FILES: frozenset[str] = frozenset(
    {
        "test_board_defense_benchmark.py",
        "test_endgame_benchmark.py",
        "test_slovak_strength.py",
    }
)


def simulation_opt_in_enabled() -> bool:
    return os.environ.get(SIMULATION_ENV) == "1"


def any_opt_in_enabled() -> bool:
    return any(os.environ.get(name) == "1" for name in OPT_IN_ENVS)


requires_simulation = pytest.mark.skipif(
    not simulation_opt_in_enabled(),
    reason=(
        "engine self-play and diagnostic search matrices are deactivated; "
        f"set {SIMULATION_ENV}=1 to run them"
    ),
)
