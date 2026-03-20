"""Asset path resolution for Libre Tiles.

Resolves paths relative to the backend/assets/ directory, or via Django settings
when available.
"""

from __future__ import annotations

from pathlib import Path

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def get_assets_path() -> Path:
    try:
        from django.conf import settings

        return Path(settings.ASSETS_DIR)
    except Exception:
        return _ASSETS_DIR


def get_premiums_path() -> str:
    return str(get_assets_path() / "premiums.json")
