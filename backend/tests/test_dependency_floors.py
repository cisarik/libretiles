"""Declared floors for patched Django, Daphne, and a direct redis dependency.

These tests assert declared floors and locked versions, NOT that there are
no known vulnerabilities. A test that claims a clean advisory state will
silently rot into a lie the next time an advisory is published. Only a
re-audit can establish the advisory state.
"""

from __future__ import annotations

import tomllib
from importlib import metadata
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_PYPROJECT = _BACKEND_DIR / "pyproject.toml"
_LOCK = _BACKEND_DIR / "poetry.lock"

_DJANGO_FLOOR = (5, 2, 17)
_DAPHNE_FLOOR = (4, 2, 2)


def _parse_version(text: str) -> tuple[int, ...]:
    parts: list[int] = []
    for raw in text.split("."):
        digits = ""
        for char in raw:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _pad(left: tuple[int, ...], right: tuple[int, ...]) -> tuple[tuple[int, ...], tuple[int, ...]]:
    width = max(len(left), len(right))
    return left + (0,) * (width - len(left)), right + (0,) * (width - len(right))


def _at_least(actual: tuple[int, ...], floor: tuple[int, ...]) -> bool:
    left, right = _pad(actual, floor)
    return left >= right


def _constraint_spec(raw: object) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if isinstance(raw, dict) and isinstance(raw.get("version"), str):
        return raw["version"].strip()
    raise AssertionError(f"unsupported constraint value: {raw!r}")


def _constraint_floor(constraint: str) -> tuple[int, ...]:
    if constraint.startswith("^"):
        return _parse_version(constraint[1:])
    if constraint.startswith(">="):
        minimum = constraint[2:].split(",", 1)[0].strip()
        return _parse_version(minimum)
    if constraint.startswith("=="):
        return _parse_version(constraint[2:].strip())
    raise AssertionError(f"unrecognized constraint syntax: {constraint}")


def _pyproject_dependencies() -> dict[str, object]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    deps = data["tool"]["poetry"]["dependencies"]
    assert isinstance(deps, dict)
    return deps


def _lock_version(package_name: str) -> str:
    data = tomllib.loads(_LOCK.read_text(encoding="utf-8"))
    matches = [
        package["version"]
        for package in data["package"]
        if package["name"] == package_name
    ]
    assert matches, f"{package_name} missing from poetry.lock"
    assert len(matches) == 1, f"{package_name} appears more than once in poetry.lock"
    version = matches[0]
    assert isinstance(version, str)
    return version


def test_django_constraint_and_lock_meet_patched_floor() -> None:
    constraint = _constraint_spec(_pyproject_dependencies()["django"])
    assert _at_least(_constraint_floor(constraint), _DJANGO_FLOOR)
    assert _at_least(_parse_version(_lock_version("django")), _DJANGO_FLOOR)


def test_daphne_constraint_and_lock_meet_patched_floor() -> None:
    constraint = _constraint_spec(_pyproject_dependencies()["daphne"])
    assert _at_least(_constraint_floor(constraint), _DAPHNE_FLOOR)
    assert _at_least(_parse_version(_lock_version("daphne")), _DAPHNE_FLOOR)


def test_redis_is_a_direct_main_group_dependency() -> None:
    deps = _pyproject_dependencies()
    assert "redis" in deps
    constraint = _constraint_spec(deps["redis"])
    assert constraint, "redis constraint must not be empty"


def test_installed_django_daphne_redis_match_the_lock() -> None:
    for dist_name, lock_name in (
        ("Django", "django"),
        ("daphne", "daphne"),
        ("redis", "redis"),
    ):
        installed = metadata.version(dist_name)
        locked = _lock_version(lock_name)
        assert installed == locked, f"{lock_name}: installed {installed} != locked {locked}"
