"""Variant loading adapted for Django (reads from settings.VARIANTS_DIR)."""

from __future__ import annotations

import json
import logging
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .assets import get_assets_path

log = logging.getLogger("libretiles.variants")

_VARIANTS_SUBDIR = "variants"
_DEFAULT_VARIANT_SLUG = "english"


@dataclass(frozen=True)
class VariantLetter:
    letter: str
    count: int
    points: int


@dataclass(frozen=True)
class VariantDefinition:
    slug: str
    language: str
    letters: tuple[VariantLetter, ...]
    source: str = "builtin"
    fetched_at: str | None = None
    variant_name: str | None = None
    language_code: str | None = None
    source_url: str | None = None

    @property
    def distribution(self) -> dict[str, int]:
        return {lt.letter: lt.count for lt in self.letters}

    @property
    def tile_points(self) -> dict[str, int]:
        return {lt.letter: lt.points for lt in self.letters}

    @property
    def total_tiles(self) -> int:
        return sum(lt.count for lt in self.letters)

    @property
    def display_label(self) -> str:
        if self.variant_name:
            return f"{self.language} – {self.variant_name}"
        return self.language


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in ascii_only.lower())
    cleaned = "-".join(filter(None, cleaned.split("-")))
    return cleaned or "variant"


def normalise_letter(letter: str) -> str:
    if not letter:
        return ""
    upper = letter.upper().replace(" ", "")
    if upper in {"BLANK", "WILDCARD", "WILD", "JOKER", "BLANK TILE"}:
        return "?"
    if upper in {"?", "\u2047"}:
        return "?"
    return upper


def _variants_dir() -> Path:
    path = get_assets_path() / _VARIANTS_SUBDIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _variant_path(slug: str) -> Path:
    return _variants_dir() / f"{slugify(slug)}.json"


def _coerce_int(value: object) -> int:
    if value is None or isinstance(value, bool):
        raise TypeError("numeric value missing")
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"expected integer, got {value}")
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise ValueError("empty string cannot be converted to int")
        return int(stripped)
    raise TypeError(f"unsupported numeric value: {value!r}")


def _load_variant_from_path(path: Path) -> VariantDefinition:
    data = json.loads(path.read_text(encoding="utf-8"))
    language = str(data.get("language") or data.get("name") or "Unknown")
    language_code_raw = data.get("language_code") or data.get("code")
    language_code = (
        str(language_code_raw).strip()
        if isinstance(language_code_raw, str) and language_code_raw
        else None
    )
    variant_name_raw = data.get("variant_name") or data.get("variant")
    variant_name = (
        str(variant_name_raw).strip()
        if isinstance(variant_name_raw, str) and variant_name_raw
        else None
    )
    slug = slugify(str(data.get("slug") or path.stem))
    source = str(data.get("source", "builtin"))
    fetched_at = data.get("fetched_at")
    source_url_raw = data.get("source_url")
    source_url = (
        str(source_url_raw).strip()
        if isinstance(source_url_raw, str) and source_url_raw
        else None
    )
    letters_raw: Iterable[dict[str, object]] = data.get("letters", [])

    letters: list[VariantLetter] = []
    seen: set[str] = set()
    for idx, raw in enumerate(letters_raw):
        if not isinstance(raw, dict):
            continue
        letter = normalise_letter(str(raw.get("letter", "")).strip())
        if not letter or letter in seen:
            continue
        if letter != "?" and len(letter) != 1:
            continue
        try:
            count = _coerce_int(raw.get("count"))
            points = _coerce_int(raw.get("points"))
        except (TypeError, ValueError):
            continue
        letters.append(VariantLetter(letter=letter, count=count, points=points))
        seen.add(letter)

    if not letters:
        raise ValueError(f"Variant {path} contains no tiles")

    return VariantDefinition(
        slug=slug,
        language=language,
        letters=tuple(sorted(letters, key=lambda lt: lt.letter)),
        source=source,
        fetched_at=str(fetched_at) if fetched_at else None,
        variant_name=variant_name,
        language_code=language_code,
        source_url=source_url,
    )


def load_variant(slug: str) -> VariantDefinition:
    path = _variant_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"Variant '{slug}' not found")
    return _load_variant_from_path(path)


def get_default_variant() -> VariantDefinition:
    return load_variant(_DEFAULT_VARIANT_SLUG)


def list_installed_variants() -> list[VariantDefinition]:
    variants: list[VariantDefinition] = []
    for path in sorted(_variants_dir().glob("*.json")):
        try:
            variants.append(_load_variant_from_path(path))
        except Exception as exc:
            log.error("variant_load_failed path=%s error=%s", path, exc)
    return variants
