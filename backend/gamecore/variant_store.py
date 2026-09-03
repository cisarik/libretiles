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
from .types import TileToken

log = logging.getLogger("libretiles.variants")

_VARIANTS_SUBDIR = "variants"
_DICTS_SUBDIR = "dicts"
_DEFAULT_VARIANT_SLUG = "english"
_DICTIONARY_FILE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*\.txt$")
MAX_TILE_TOKEN_CODEPOINTS = 16
_DEFAULT_VOWELS: tuple[TileToken, ...] = ("A", "E", "I", "O", "U")
_BLANK_ALIASES = frozenset(
    {"BLANK", "WILDCARD", "WILD", "JOKER", "BLANKTILE", "\u2047"}
)


class VariantManifestError(ValueError):
    """Distinguishable variant-manifest failure. ``code`` is the stable key."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class VariantLetter:
    letter: TileToken
    count: int
    points: int


@dataclass(frozen=True)
class VariantDefinition:
    slug: str
    language: str
    # Internal construction order: tuple(sorted(letters, key=lambda lt: lt.letter)).
    # This order feeds ``distribution``, which is the pre-shuffle tile sequence
    # consumed by TileBag. It has no game meaning. Do not sort by
    # alphabet_order — that would change every seeded bag in the repository.
    letters: tuple[VariantLetter, ...]
    dictionary_file: str
    source: str = "builtin"
    fetched_at: str | None = None
    variant_name: str | None = None
    language_code: str | None = None
    source_url: str | None = None
    two_tile_words_file: str | None = None
    # Deterministic total order for the engine (tile order, starting draw,
    # blank picker). Not a dictionary collation. Nobody may later reuse it as
    # a universal word sorter.
    alphabet_order: tuple[TileToken, ...] = ()
    vowels: tuple[TileToken, ...] = _DEFAULT_VOWELS
    forbidden_token_sequences: tuple[tuple[TileToken, ...], ...] = ()

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
    def two_tile_words_path(self) -> Path | None:
        if self.two_tile_words_file is None:
            return None
        return get_assets_path() / _DICTS_SUBDIR / self.two_tile_words_file

    @property
    def playable_letters(self) -> tuple[str, ...]:
        """Tile tokens only (blank excluded), ordered by alphabet_order index.

        This is the property that carries game meaning. Blank targets come
        from the TILE SET ordered by alphabet index, never from
        ``alphabet_order`` itself — Slovak ``CH`` is an alphabet letter that
        is not a tile.
        """
        index = {token: i for i, token in enumerate(self.alphabet_order)}
        tiles = [lt.letter for lt in self.letters if lt.letter != "?"]
        return tuple(sorted(tiles, key=lambda token: index[token]))

    def lexical_contribution(self, token: TileToken) -> TileToken:
        """Identity extension point: a non-blank token contributes itself."""
        return token

    def tile_display(self, token: TileToken) -> TileToken:
        """Identity extension point: display form equals the token string."""
        return token

    def starting_draw_order_key(self, token: TileToken) -> tuple[int, int]:
        """Blank lowest, then alphabet_order index.

        Naive code-point order happens to rank Hungarian digraphs correctly
        (``SZ`` < ``T``, ``CS`` < ``D``, ``GY`` < ``H``, ``ZS`` > ``Z``)
        while being wrong for every accented vowel in SK/CS/PL/HU. The live
        defect is ``uii-01-F07`` (``Á`` vs ``Z``); F2 wires this key into
        ``_perform_starting_draw``. This helper is the pure half only.
        """
        if token == "?":
            return (0, 0)
        try:
            return (1, self.alphabet_order.index(token))
        except ValueError:
            return (1, len(self.alphabet_order))

    def slot0_wins_starting_draw(self, slot0_tile: TileToken, slot1_tile: TileToken) -> bool:
        """True if slot 0 opens. Equal keys resolve to slot 0."""
        return self.starting_draw_order_key(slot0_tile) <= self.starting_draw_order_key(
            slot1_tile
        )


def slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = "".join(ch if ch.isalnum() else "-" for ch in ascii_only.lower())
    cleaned = "-".join(filter(None, cleaned.split("-")))
    return cleaned or "variant"


def canonicalize_tile_token(raw: str) -> str:
    """Atomic-token canonicalization: trim → NFC → uppercase → NFC.

    The second NFC is required because uppercasing can decompose.
    ``len(str)`` here is the resource bound, never a tile count.
    """
    trimmed = raw.strip()
    nfc = unicodedata.normalize("NFC", trimmed)
    upper = nfc.upper()
    return unicodedata.normalize("NFC", upper)


def normalise_letter(letter: str) -> str:
    """Service-layer letter ingest. Keep blank-synonym mapping for callers."""
    if not letter:
        return ""
    letter = unicodedata.normalize("NFC", letter)
    upper = letter.upper().replace(" ", "")
    if upper in {"BLANK", "WILDCARD", "WILD", "JOKER", "BLANK TILE"}:
        return "?"
    if upper in {"?", "\u2047"}:
        return "?"
    return unicodedata.normalize("NFC", upper)


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


def _parse_asset_token(raw: object, *, kind: str) -> TileToken:
    if not isinstance(raw, str):
        raise VariantManifestError(
            "malformed_token", f"{kind} token must be a string, got {raw!r}"
        )
    if any(ch.isspace() for ch in raw):
        raise VariantManifestError(
            "whitespace", f"{kind} token contains whitespace: {raw!r}"
        )
    if any(unicodedata.category(ch).startswith("C") for ch in raw):
        raise VariantManifestError(
            "control", f"{kind} token contains a control character: {raw!r}"
        )
    if raw == "":
        raise VariantManifestError("empty_token", f"{kind} token is empty")
    nfc = unicodedata.normalize("NFC", raw)
    if raw != nfc:
        raise VariantManifestError(
            "non_nfc", f"{kind} token {raw!r} is not NFC; expected {nfc!r}"
        )
    canonical = canonicalize_tile_token(raw)
    if raw != canonical:
        raise VariantManifestError(
            "noncanonical",
            f"{kind} token {raw!r} is not canonical; expected {canonical!r}",
        )
    if len(canonical) > MAX_TILE_TOKEN_CODEPOINTS:
        raise VariantManifestError(
            "too_long",
            f"{kind} token {canonical!r} exceeds {MAX_TILE_TOKEN_CODEPOINTS} code points",
        )
    if canonical != "?" and canonical in _BLANK_ALIASES:
        raise VariantManifestError(
            "blank_alias",
            f"{kind} token {canonical!r} is reserved for a physical blank; use '?'",
        )
    return canonical


def _parse_alphabet_order(raw: object) -> tuple[TileToken, ...]:
    if not isinstance(raw, list):
        raise VariantManifestError(
            "missing_alphabet_order",
            "alphabet_order must be a JSON array of canonical tokens",
        )
    tokens: list[TileToken] = []
    seen: set[TileToken] = set()
    for idx, item in enumerate(raw):
        token = _parse_asset_token(item, kind="alphabet_order")
        if token == "?":
            raise VariantManifestError(
                "blank_in_alphabet",
                "alphabet_order must not contain the blank token",
            )
        if token in seen:
            raise VariantManifestError(
                "duplicate_alphabet",
                f"alphabet_order contains duplicate token {token!r} at index {idx}",
            )
        seen.add(token)
        tokens.append(token)
    if not tokens:
        raise VariantManifestError(
            "missing_alphabet_order", "alphabet_order must not be empty"
        )
    return tuple(tokens)


def _parse_vowels(raw: object) -> tuple[TileToken, ...]:
    if isinstance(raw, str):
        items: list[object] = list(raw)
    elif isinstance(raw, list):
        items = list(raw)
    else:
        raise VariantManifestError("malformed_vowels", "vowels must be a string or array")
    return tuple(_parse_asset_token(item, kind="vowel") for item in items)


def _parse_forbidden(raw: object) -> tuple[tuple[TileToken, ...], ...]:
    if not isinstance(raw, list):
        raise VariantManifestError(
            "malformed_forbidden",
            "forbidden_token_sequences must be an array of token arrays",
        )
    sequences: list[tuple[TileToken, ...]] = []
    for item in raw:
        if not isinstance(item, list):
            raise VariantManifestError(
                "malformed_forbidden",
                "each forbidden sequence must be an array of tokens",
            )
        sequences.append(tuple(_parse_asset_token(tok, kind="forbidden") for tok in item))
    return tuple(sequences)


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
    # Fail closed when the declared slug disagrees with the manifest's own filename:
    # ``list_installed_variants`` advertises this computed slug while ``load_variant``
    # resolves ``_variant_path`` -> ``f"{slugify(slug)}.json"``, so a divergent manifest
    # would be selectable and unloadable at the same time. Compare against
    # ``slugify(path.stem)``, never the raw stem: ``slugify("De_Ch") == "de-ch"``, a pair
    # ``load_variant`` already handles correctly today. Comparing two canonical values also
    # closes the reverse direction for free — a filename that is not itself in canonical
    # slug form can no longer be loaded even when its declared slug equals its raw stem.
    # That second property is deliberate, not redundant. Keep this check BEFORE
    # ``validate_dictionary_file`` below: that call raises ``FileNotFoundError``, which
    # ``game/views.py`` reports as readiness "unavailable", whereas an unloadable variant
    # must be omitted from the public catalog entirely.
    stem_slug = slugify(path.stem)
    if slug != stem_slug:
        raise VariantManifestError(
            "slug_stem_mismatch",
            f"manifest {path.name} declares slug {slug!r} but its filename resolves to "
            f"{stem_slug!r}; load_variant() resolves the filename, so only {stem_slug!r} "
            "could ever be loaded",
        )
    source = str(data.get("source", "builtin"))
    fetched_at = data.get("fetched_at")
    source_url_raw = data.get("source_url")
    source_url = (
        str(source_url_raw).strip()
        if isinstance(source_url_raw, str) and source_url_raw
        else None
    )
    dictionary_file = validate_dictionary_file(data.get("dictionary_file"))
    two_tile_raw = data.get("two_tile_words_file")
    two_tile_words_file = (
        validate_dictionary_file(two_tile_raw) if two_tile_raw is not None else None
    )
    if "alphabet_order" not in data:
        raise VariantManifestError(
            "missing_alphabet_order",
            "alphabet_order is required and must be declared, not derived from letters",
        )
    alphabet_order = _parse_alphabet_order(data.get("alphabet_order"))
    vowels = (
        _parse_vowels(data["vowels"]) if "vowels" in data else _DEFAULT_VOWELS
    )
    forbidden = (
        _parse_forbidden(data["forbidden_token_sequences"])
        if "forbidden_token_sequences" in data
        else ()
    )
    letters_raw: Iterable[object] = data.get("letters", [])

    letters: list[VariantLetter] = []
    seen: set[str] = set()
    for idx, raw in enumerate(letters_raw):
        if not isinstance(raw, dict):
            raise VariantManifestError(
                "malformed_letter", f"letters[{idx}] is not an object"
            )
        token = _parse_asset_token(raw.get("letter", ""), kind="tile")
        if token in seen:
            raise VariantManifestError(
                "duplicate_token", f"duplicate tile token {token!r}"
            )
        try:
            count = _coerce_int(raw.get("count"))
            points = _coerce_int(raw.get("points"))
        except (TypeError, ValueError) as exc:
            raise VariantManifestError(
                "malformed_letter",
                f"letters[{idx}] has invalid count/points: {exc}",
            ) from exc
        letters.append(VariantLetter(letter=token, count=count, points=points))
        seen.add(token)

    if not letters:
        raise ValueError(f"Variant {path} contains no tiles")

    tile_tokens = {lt.letter for lt in letters if lt.letter != "?"}
    alphabet_set = set(alphabet_order)
    missing = sorted(tile_tokens - alphabet_set)
    if missing:
        raise VariantManifestError(
            "tile_not_in_alphabet",
            "every non-blank tile token must appear exactly once in alphabet_order; "
            f"missing {missing}",
        )

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
        two_tile_words_file=two_tile_words_file,
        alphabet_order=alphabet_order,
        vowels=vowels,
        forbidden_token_sequences=forbidden,
    )


def load_variant(slug: str) -> VariantDefinition:
    path = _variant_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"Variant '{slug}' not found")
    return _load_variant_from_path(path)


def load_two_tile_words(variant: VariantDefinition) -> frozenset[str] | None:
    """NFC-casefold two-tile set, or None when the variant has no two-tile file."""
    path = variant.two_tile_words_path
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
