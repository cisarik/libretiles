"""Provider-free engine diagnostic helpers (Slice E).

Search timings and node counts are observational. They never enter a verdict.
Two-letter policy is set membership over complete formed words only.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from game.services import _lexicon_id, _word_passes_dictionary
from gamecore.assets import get_assets_path, get_premiums_path
from gamecore.board import Board
from gamecore.fastdict import PrefixIndex, load_prefix_index
from gamecore.legality import evaluate_scoring_move, placements_to_dicts
from gamecore.move_search import RankedMoveCandidate, find_ranked_scoring_moves
from gamecore.tiles import TileBag, get_tile_points
from gamecore.types import Placement
from gamecore.variant_store import (
    VariantDefinition,
    list_installed_variants,
    load_two_letter_allowlist,
    load_variant,
)

ARTIFACT_ID = "libretiles.ai-play-diagnostic/v1"
REPORT_KIND_ENGINE = "engine"
SCENARIO_ASSET_NAME = "ai_play_scenarios_v1.json"
UINT32_MAX = 4_294_967_295
PROBE_COUNT_MIN = 1
PROBE_COUNT_MAX = 300
MESSAGE_LIMIT = 200
SOURCE_REVISION_UNKNOWN = "unknown"
REASON_OK = "ok"
REASON_ILLEGAL_TWO_LETTER = "illegal_two_letter_formed_word"
REASON_LEGALITY_MISMATCH = "legality_mismatch"
REASON_INVALID_PLACEMENT_LETTER = "invalid_placement_letter"
REASON_MISSING_TOP_CANDIDATE = "missing_top_candidate"
COMPLETION_SOURCE_VOCABULARY = (
    "provider_candidate",
    "backend_ranked_candidate",
    "repair_candidate",
    "backend_witness_rescue",
    "genuine_no_move_exchange",
    "genuine_no_move_pass",
)


def reserved_completion_sources() -> tuple[str, ...]:
    """Turn-layer vocabulary reserved by v1; engine reports do not populate it."""
    return COMPLETION_SOURCE_VOCABULARY

Verdict = Literal["pass", "fail"]


class DiagnosticInputError(Exception):
    """Invalid CLI input rejected before dictionary load or search."""


@dataclass(frozen=True)
class DiagnosticScenario:
    fixture_id: str | None
    seed: int | None
    variant_slug: str
    rack: tuple[str, ...]
    board_letters: tuple[tuple[int, int, str], ...]


@dataclass(frozen=True)
class VariantProbeContext:
    variant: VariantDefinition
    index: PrefixIndex
    allowlist: frozenset[str] | None
    letters: frozenset[str]

    def is_word(self, word: str) -> bool:
        return _word_passes_dictionary(
            self.index.contains,
            word,
            two_letter_allowlist=self.allowlist,
        )

    def has_prefix(self, prefix: str) -> bool:
        if self.index.has_prefix(prefix):
            return True
        if self.allowlist is None:
            return False
        folded = unicodedata.normalize("NFC", prefix).casefold()
        return len(folded) == 2 and folded in self.allowlist


@dataclass(frozen=True)
class EngineSample:
    search_status: str
    complete: bool
    nodes: int
    elapsed_ms: int
    rack: str
    formed_words: tuple[str, ...]
    score: int
    placements: list[dict[str, object]]
    rejected_two_letter_words: tuple[str, ...]
    verdict: Verdict
    reason_code: str
    top_candidate: dict[str, object] | None


def bound_text(value: str, limit: int = MESSAGE_LIMIT) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def installed_variant_slugs() -> frozenset[str]:
    return frozenset(item.slug for item in list_installed_variants())


def observe_source_revision() -> str:
    root = Path(__file__).resolve().parents[2]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except OSError:
        return SOURCE_REVISION_UNKNOWN
    sha = completed.stdout.strip()
    hex_ok = len(sha) == 40 and all(ch in "0123456789abcdef" for ch in sha)
    if completed.returncode != 0 or not hex_ok:
        return SOURCE_REVISION_UNKNOWN
    return sha


def scenario_asset_path() -> Path:
    return get_assets_path() / "diagnostics" / SCENARIO_ASSET_NAME


def load_scenario_asset() -> dict[str, Any]:
    raw = json.loads(scenario_asset_path().read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise DiagnosticInputError("scenario asset is not an object")
    return raw


def _nfc_tiles(raw: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFC", raw)
    tiles = tuple(unicodedata.normalize("NFC", tile).upper() for tile in normalized)
    if not tiles:
        raise DiagnosticInputError("rack must contain at least one tile")
    return tiles


def _board_letters_from_payload(
    payload: object,
) -> tuple[tuple[int, int, str], ...]:
    if payload in (None, []):
        return ()
    if not isinstance(payload, list):
        raise DiagnosticInputError("fixture board must be a list")
    letters: list[tuple[int, int, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise DiagnosticInputError("fixture board cell must be an object")
        row = item.get("row")
        col = item.get("col")
        letter = item.get("letter")
        if not isinstance(row, int) or isinstance(row, bool):
            raise DiagnosticInputError("fixture board row must be an integer")
        if not isinstance(col, int) or isinstance(col, bool):
            raise DiagnosticInputError("fixture board col must be an integer")
        if not isinstance(letter, str) or not letter:
            raise DiagnosticInputError("fixture board letter must be a string")
        nfc = unicodedata.normalize("NFC", letter).upper()
        letters.append((row, col, nfc))
    return tuple(letters)


def load_named_scenario(fixture_id: str) -> DiagnosticScenario:
    asset = load_scenario_asset()
    fixtures = asset.get("fixtures")
    if not isinstance(fixtures, list):
        raise DiagnosticInputError("scenario asset fixtures must be a list")
    for item in fixtures:
        if not isinstance(item, dict):
            continue
        if item.get("id") != fixture_id:
            continue
        variant_slug = item.get("variant_slug")
        rack = item.get("rack")
        if not isinstance(variant_slug, str) or not isinstance(rack, str):
            raise DiagnosticInputError("fixture is missing variant_slug or rack")
        return DiagnosticScenario(
            fixture_id=fixture_id,
            seed=None,
            variant_slug=variant_slug,
            rack=_nfc_tiles(rack),
            board_letters=_board_letters_from_payload(item.get("board")),
        )
    raise DiagnosticInputError(f"unknown fixture id '{bound_text(fixture_id, 64)}'")


def build_seeded_scenario(variant_slug: str, seed: int) -> DiagnosticScenario:
    variant = load_variant(variant_slug)
    bag = TileBag(seed=seed, variant=variant)
    rack = tuple(unicodedata.normalize("NFC", tile).upper() for tile in bag.draw(7))
    return DiagnosticScenario(
        fixture_id=None,
        seed=seed,
        variant_slug=variant.slug,
        rack=rack,
        board_letters=(),
    )


def load_variant_context(variant_slug: str) -> VariantProbeContext:
    variant = load_variant(variant_slug)
    return VariantProbeContext(
        variant=variant,
        index=load_prefix_index(variant.dictionary_path),
        allowlist=load_two_letter_allowlist(variant),
        letters=frozenset(variant.playable_letters),
    )


def classify_complete_formed_words(
    words: Sequence[str],
    *,
    contains: Callable[[str], bool],
    two_letter_allowlist: frozenset[str] | None,
) -> tuple[str, ...]:
    """Return complete formed words of length 2 rejected by the variant lexicon.

    Membership is over the complete-word list only. Longer words are never
    scanned for two-letter substrings.
    """
    rejected: list[str] = []
    for word in words:
        folded = unicodedata.normalize("NFC", word.strip()).casefold()
        if len(folded) != 2:
            continue
        if not _word_passes_dictionary(
            contains,
            word,
            two_letter_allowlist=two_letter_allowlist,
        ):
            rejected.append(word)
    return tuple(rejected)


def _is_nfc_unicode_letter_tile(
    letter: object,
    blank_as: object,
    playable: frozenset[str],
) -> bool:
    if not isinstance(letter, str):
        return False
    normalized = unicodedata.normalize("NFC", letter.strip()).upper()
    if normalized == "?":
        if not isinstance(blank_as, str):
            return False
        blank = unicodedata.normalize("NFC", blank_as.strip()).upper()
        return len(blank) == 1 and blank.isalpha() and blank in playable
    return len(normalized) == 1 and normalized.isalpha()


def _placements_are_unicode(
    payload: Sequence[Mapping[str, object]],
    playable: frozenset[str],
) -> bool:
    return all(
        _is_nfc_unicode_letter_tile(item.get("letter"), item.get("blank_as"), playable)
        for item in payload
    )


def _board_from_scenario(scenario: DiagnosticScenario) -> Board:
    board = Board(get_premiums_path())
    for row, col, letter in scenario.board_letters:
        board.cells[row][col].letter = letter
    return board


def _candidate_payload(candidate: RankedMoveCandidate) -> dict[str, object]:
    return {
        "placements": placements_to_dicts(candidate.placements),
        "words": list(candidate.words),
        "score": candidate.total_score,
    }


def _placements_from_payload(payload: Sequence[Mapping[str, object]]) -> list[Placement]:
    placements: list[Placement] = []
    for item in payload:
        letter_raw = item.get("letter")
        letter = (
            unicodedata.normalize("NFC", letter_raw).upper()
            if isinstance(letter_raw, str)
            else ""
        )
        blank_raw = item.get("blank_as")
        blank_as = (
            unicodedata.normalize("NFC", blank_raw).upper()
            if isinstance(blank_raw, str)
            else None
        )
        row = item.get("row")
        col = item.get("col")
        if not isinstance(row, int) or isinstance(row, bool):
            continue
        if not isinstance(col, int) or isinstance(col, bool):
            continue
        placements.append(Placement(row=row, col=col, letter=letter, blank_as=blank_as))
    return placements


def _verdict_for_candidate(
    *,
    status: str,
    candidate: RankedMoveCandidate | None,
    context: VariantProbeContext,
    board: Board,
    rack: Sequence[str],
) -> tuple[Verdict, str, tuple[str, ...], list[dict[str, object]], int, dict[str, object] | None]:
    if candidate is None:
        if status == "found":
            return (
                "fail",
                REASON_MISSING_TOP_CANDIDATE,
                (),
                [],
                0,
                None,
            )
        return ("pass", REASON_OK, (), [], 0, None)

    payload = _candidate_payload(candidate)
    placements = payload["placements"]
    assert isinstance(placements, list)
    placement_dicts = [item for item in placements if isinstance(item, dict)]
    formed_words = tuple(candidate.words)
    rejected = classify_complete_formed_words(
        formed_words,
        contains=context.index.contains,
        two_letter_allowlist=context.allowlist,
    )
    if not _placements_are_unicode(placement_dicts, context.letters):
        return (
            "fail",
            REASON_INVALID_PLACEMENT_LETTER,
            formed_words,
            placement_dicts,
            candidate.total_score,
            payload,
        )
    if rejected:
        return (
            "fail",
            REASON_ILLEGAL_TWO_LETTER,
            formed_words,
            placement_dicts,
            candidate.total_score,
            payload,
        )
    rebuilt = _placements_from_payload(placement_dicts)
    legality = evaluate_scoring_move(
        board,
        rack,
        rebuilt,
        context.is_word,
        letters=context.letters,
        variant=context.variant.slug,
    )
    if not legality.ok or legality.total_score != candidate.total_score:
        return (
            "fail",
            REASON_LEGALITY_MISMATCH,
            formed_words,
            placement_dicts,
            candidate.total_score,
            payload,
        )
    return (
        "pass",
        REASON_OK,
        formed_words,
        placement_dicts,
        candidate.total_score,
        payload,
    )


def run_engine_probe(
    scenario: DiagnosticScenario,
    context: VariantProbeContext,
) -> EngineSample:
    board = _board_from_scenario(scenario)
    result = find_ranked_scoring_moves(
        board,
        scenario.rack,
        context.is_word,
        context.has_prefix,
        bag_count=100,
        tile_points=get_tile_points(context.variant),
        blank_letters=context.variant.playable_letters,
        variant=context.variant.slug,
    )
    top = result.candidates[0] if result.candidates else None
    verdict, reason, words, placements, score, payload = _verdict_for_candidate(
        status=result.status,
        candidate=top,
        context=context,
        board=board,
        rack=scenario.rack,
    )
    return EngineSample(
        search_status=result.status,
        complete=result.complete,
        nodes=result.nodes,
        elapsed_ms=result.elapsed_ms,
        rack="".join(scenario.rack),
        formed_words=words,
        score=score,
        placements=placements,
        rejected_two_letter_words=rejected_words(words, context),
        verdict=verdict,
        reason_code=reason,
        top_candidate=payload,
    )


def rejected_words(words: Sequence[str], context: VariantProbeContext) -> tuple[str, ...]:
    return classify_complete_formed_words(
        words,
        contains=context.index.contains,
        two_letter_allowlist=context.allowlist,
    )


def format_metric_line(
    variant_slug: str,
    label: str,
    sample: EngineSample,
) -> str:
    top_words = ",".join(sample.formed_words) if sample.formed_words else "-"
    return (
        f"{variant_slug} engine {label} status={sample.search_status} "
        f"complete={sample.complete} nodes={sample.nodes} "
        f"elapsed_ms={sample.elapsed_ms} top={top_words} score={sample.score}"
    )


def sample_to_dict(sample: EngineSample) -> dict[str, Any]:
    return {
        "search_status": sample.search_status,
        "complete": sample.complete,
        "nodes": sample.nodes,
        "elapsed_ms": sample.elapsed_ms,
        "rack": sample.rack,
        "top_candidate": sample.top_candidate,
        "formed_words": list(sample.formed_words),
        "score": sample.score,
        "two_letter_policy": {
            "complete_formed_words": list(sample.formed_words),
            "rejected": list(sample.rejected_two_letter_words),
        },
        "verdict": sample.verdict,
        "reason_code": sample.reason_code,
    }


def build_diagnostic_report(
    *,
    requested: Mapping[str, str | int],
    context: VariantProbeContext,
    samples: Sequence[EngineSample],
    generated_at: datetime | None = None,
    source_revision: str | None = None,
) -> dict[str, Any]:
    stamp = generated_at or datetime.now(timezone.utc)
    generated = stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pass_count = sum(1 for sample in samples if sample.verdict == "pass")
    fail_count = sum(1 for sample in samples if sample.verdict == "fail")
    allowlist_size = len(context.allowlist) if context.allowlist is not None else None
    return {
        "artifact": ARTIFACT_ID,
        "report_kind": REPORT_KIND_ENGINE,
        "generated_at": generated,
        "source_revision": source_revision or observe_source_revision(),
        "requested": dict(requested),
        "variant": {
            "slug": context.variant.slug,
            "lexicon_id": _lexicon_id(context.variant),
            "two_letter_lexicon_size": allowlist_size,
        },
        "samples": [sample_to_dict(sample) for sample in samples],
        "summary": {
            "sample_count": len(samples),
            "pass_count": pass_count,
            "fail_count": fail_count,
        },
    }


def dump_report_json(report: Mapping[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2) + "\n"


def write_report_atomically(path: Path, payload: str) -> None:
    if path.exists():
        raise DiagnosticInputError("output path already exists")
    parent = path.parent
    if not parent.is_dir():
        raise DiagnosticInputError("output directory does not exist")
    handle, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=parent,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def resolve_engine_scenario(
    *,
    variant_slug: str,
    fixture_id: str | None,
    seed: int | None,
) -> DiagnosticScenario:
    if (fixture_id is None) == (seed is None):
        raise DiagnosticInputError("exactly one of --fixture-id or --seed is required")
    installed = installed_variant_slugs()
    if variant_slug not in installed:
        raise DiagnosticInputError(
            f"unknown variant '{bound_text(variant_slug, 64)}'"
        )
    if fixture_id is not None:
        scenario = load_named_scenario(fixture_id)
        if scenario.variant_slug != variant_slug:
            raise DiagnosticInputError("fixture id does not match --variant-slug")
        return scenario
    assert seed is not None
    return build_seeded_scenario(variant_slug, seed)
