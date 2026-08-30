"""Mechanical guard: shipped game app code must not import the Poetry dev group."""

from __future__ import annotations

import ast
from pathlib import Path

_FORBIDDEN = frozenset({"pytest", "pytest_django", "_pytest", "ruff", "mypy"})
_GAME_ROOT = Path(__file__).resolve().parents[1] / "game"


def _imported_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".", 1)[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".", 1)[0])
    return names


def test_game_app_modules_do_not_import_dev_group_packages() -> None:
    offenders: list[str] = []
    for path in sorted(_GAME_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
        imported = _imported_names(tree) & _FORBIDDEN
        if imported:
            relative = path.relative_to(_GAME_ROOT.parent)
            offenders.append(f"{relative}: {sorted(imported)}")
    assert offenders == []
