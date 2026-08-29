"""Variant loading adapted for Django (reads from settings.VARIANTS_DIR)."""

from __future__ import annotations

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .assets import get_assets_path

log = logging.getLogger("libretiles.variants")

_VARIANTS_SUBDIR = "variants"
_DICTS_SUBDIR = "dicts"
_DEFAULT_VARIANT_SLUG = "english"
_DICTIONARY_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.txt$")


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
    dictionary_file: str
    source: str = "builtin"
    fetched_at: str | None = None
    variant_name: str | None = None
    language_code: str | None = None
    source_url: str | None = None
    two_letter_allowlist_file: str | None = None

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

    @property
    def dictionary_path(self) -> Path:
        return get_assets_path() / _DICTS_SUBDIR / self.dictionary_file

    @property
    def two_letter_allowlist_path(self) -> Path | None:
        if self.two_letter_allowlist_file is None:
            return None
        return get_assets_path() / _DICTS_SUBDIR / self.two_letter_allowlist_file

    @property
    def playable_letters(self) -> tuple[str, ...]:
        return tuple(lt.letter for lt in self.letters if lt.letter != "?")


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in ascii_only.lower())
    cleaned = "-".join(filter(None, cleaned.split("-")))
    return cleaned or "variant"


def normalise_letter(letter: str) -> str:
    if not letter:
        return ""
    letter = unicodedata.normalize("NFC", letter)
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


def validate_dictionary_file(value: object) -> str:
    """Require a basename-only ``*.txt`` that exists under ``assets/dicts/``."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("dictionary_file is required")
    name = value.strip()
    if "/" in name or "\\" in name or ".." in name:
        raise ValueError(f"dictionary_file must be a basename: {name!r}")
    if _DICTIONARY_FILE_RE.fullmatch(name) is None:
        raise ValueError(f"dictionary_file has invalid shape: {name!r}")
    path = get_assets_path() / _DICTS_SUBDIR / name
    if not path.is_file():
        raise FileNotFoundError(f"dictionary file not found: {path}")
    return name


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
    dictionary_file = validate_dictionary_file(data.get("dictionary_file"))
    two_letter_raw = data.get("two_letter_allowlist_file")
    two_letter_allowlist_file = (
        validate_dictionary_file(two_letter_raw) if two_letter_raw is not None else None
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
        dictionary_file=dictionary_file,
        source=source,
        fetched_at=str(fetched_at) if fetched_at else None,
        variant_name=variant_name,
        language_code=language_code,
        source_url=source_url,
        two_letter_allowlist_file=two_letter_allowlist_file,
    )


def load_variant(slug: str) -> VariantDefinition:
    path = _variant_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"Variant '{slug}' not found")
    return _load_variant_from_path(path)


def load_two_letter_allowlist(variant: VariantDefinition) -> frozenset[str] | None:
    """NFC-casefold two-letter set, or None when the variant has no allowlist file."""
    path = variant.two_letter_allowlist_path
    if path is None:
        return None
    words: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            continue
        word = unicodedata.normalize("NFC", line.strip()).casefold()
        if word:
            words.add(word)
    return frozenset(words)


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
