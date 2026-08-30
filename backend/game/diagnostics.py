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
REPORT_KIND_TURN = "turn"
SCENARIO_ASSET_NAME = "ai_play_scenarios_v1.json"
UINT32_MAX = 4_294_967_295
PROBE_COUNT_MIN = 1
PROBE_COUNT_MAX = 300
TURN_COUNT_MIN = 1
TURN_COUNT_MAX = 300
TIMEOUT_SECONDS_MIN = 1
TIMEOUT_SECONDS_MAX = 600
MAX_STEPS_MIN = 5
MAX_STEPS_MAX = 100
DEFAULT_TIMEOUT_SECONDS = 120
DEFAULT_MAX_STEPS = 50
DEFAULT_TURN_COUNT = 1
DEFAULT_RUNTIME_MODE = "fake"
DEFAULT_QUEUE_MODE = "selected-only"
RUNTIME_MODES = frozenset({"fake", "live"})
QUEUE_MODES = frozenset({"selected-only", "catalog-fallback"})
LIVE_SENTINEL = "LIBRETILES_AI_PLAY_LIVE"
HANDOFF_ENV = "LIBRETILES_AI_PLAY_HANDOFF"
TURN_PROBE_NODE = "tests/diagnostics/test_turn_probe.py::test_run_turn_from_handoff"
MESSAGE_LIMIT = 200
SOURCE_REVISION_UNKNOWN = "unknown"
REASON_OK = "ok"
REASON_ILLEGAL_TWO_LETTER = "illegal_two_letter_formed_word"
REASON_LEGALITY_MISMATCH = "legality_mismatch"
REASON_INVALID_PLACEMENT_LETTER = "invalid_placement_letter"
REASON_MISSING_TOP_CANDIDATE = "missing_top_candidate"
REASON_FOUND_NONSCORING_ACTION = "found_or_indeterminate_pass_or_exchange"
REASON_SSE_DONE_WITHOUT_MOVE = "sse_done_without_matching_move"
REASON_STATE_ADVANCED_MORE_THAN_ONCE = "state_advanced_more_than_once"
REASON_GENERIC_UNCHANGED = "generic_unchanged_turn"
REASON_UNICODE_MISMATCH = "unicode_or_formed_word_mismatch"
REASON_CODED_PROVIDER_UNCHANGED = "coded_provider_unchanged"
REASON_PERSIST_LOST_TERMINAL = "persist_then_lost_terminal"
REASON_LIVE_REFUSED = "live_mode_requires_opt_in"
SECRET_KEY_FRAGMENTS = (
    "authorization",
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "bearer",
    "cookie",
    "prompt",
    "raw_body",
    "env",
)
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
TurnVerdict = Literal["pass", "pass_with_telemetry", "fail", "external_incomplete"]
PlayabilityStatus = Literal["found", "none", "indeterminate"]


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


@dataclass(frozen=True)
class TurnAttemptRecord:
    provider: str
    model_id: str
    timeout_seconds: int
    step_grant: int
    provider_requests_used: int


@dataclass(frozen=True)
class TurnPersistenceEvidence:
    move_id: int | None
    move_count_delta: int
    state_version_delta: int
    action_matches_sse: bool
    words_match_sse: bool
    score_matches_sse: bool


@dataclass(frozen=True)
class TurnSample:
    playability_status: str
    witness: dict[str, object] | None
    action: str | None
    placements: list[dict[str, object]]
    formed_words: tuple[str, ...]
    score: int
    completion_source: str | None
    probe_status: str | None
    repair_attempted: bool | None
    terminal_cause: str | None
    attempts: tuple[TurnAttemptRecord, ...]
    turn_provider_requests_used: int
    queue_length: int
    unresolved_in_flight: int
    persistence: TurnPersistenceEvidence
    rejected_two_letter_words: tuple[str, ...]
    terminal_kind: str
    lost_terminal: bool
    external_provider_invocations: int
    backend_origins: tuple[str, ...]
    foreign_origins: tuple[str, ...]
    verdict: TurnVerdict
    reason_code: str


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


def nfc_upper(value: str) -> str:
    return unicodedata.normalize("NFC", value).upper()


def _ascii_letter(ch: str) -> bool:
    return len(ch) == 1 and "A" <= ch <= "Z"


def is_diacritic_letter(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    folded = nfc_upper(value.strip())
    return len(folded) == 1 and folded.isalpha() and not _ascii_letter(folded)


def formed_words_from_payload(payload: object) -> tuple[str, ...]:
    if isinstance(payload, str) and payload:
        return (payload,)
    if not isinstance(payload, list):
        return ()
    words: list[str] = []
    for item in payload:
        if isinstance(item, str) and item:
            words.append(item)
        elif isinstance(item, dict):
            word = item.get("word")
            if isinstance(word, str) and word:
                words.append(word)
    return tuple(words)


def placements_from_payload(payload: object) -> list[dict[str, object]]:
    if not isinstance(payload, list):
        return []
    result: list[dict[str, object]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        row = item.get("row")
        col = item.get("col")
        letter_raw = item.get("letter")
        if not isinstance(row, int) or isinstance(row, bool):
            continue
        if not isinstance(col, int) or isinstance(col, bool):
            continue
        if not isinstance(letter_raw, str):
            continue
        entry: dict[str, object] = {
            "row": row,
            "col": col,
            "letter": nfc_upper(letter_raw),
        }
        blank_raw = item.get("blank_as")
        if isinstance(blank_raw, str) and blank_raw:
            entry["blank_as"] = nfc_upper(blank_raw)
        result.append(entry)
    return result


def _placement_key(item: Mapping[str, object]) -> tuple[int, int, str, str]:
    letter = item.get("letter")
    blank = item.get("blank_as")
    row = item.get("row")
    col = item.get("col")
    return (
        row if isinstance(row, int) else -1,
        col if isinstance(col, int) else -1,
        nfc_upper(letter) if isinstance(letter, str) else "",
        nfc_upper(blank) if isinstance(blank, str) else "",
    )


def placements_nfc_equal(
    left: Sequence[Mapping[str, object]],
    right: Sequence[Mapping[str, object]],
) -> bool:
    return sorted(_placement_key(item) for item in left) == sorted(
        _placement_key(item) for item in right
    )


def formed_words_nfc_equal(left: Sequence[str], right: Sequence[str]) -> bool:
    return sorted(nfc_upper(word) for word in left) == sorted(
        nfc_upper(word) for word in right
    )


def live_opt_in_enabled(environ: Mapping[str, str] | None = None) -> bool:
    source = environ if environ is not None else os.environ
    return source.get(LIVE_SENTINEL) == "1"


def redacted_copy(value: object) -> object:
    if isinstance(value, dict):
        redacted: dict[str, object] = {}
        for key, inner in value.items():
            lowered = key.lower()
            if any(fragment in lowered for fragment in SECRET_KEY_FRAGMENTS):
                continue
            if isinstance(inner, str) and (
                inner.startswith("Bearer ") or "/home/" in inner or "/Users/" in inner
            ):
                continue
            redacted[key] = redacted_copy(inner)
        return redacted
    if isinstance(value, list):
        return [redacted_copy(item) for item in value]
    if isinstance(value, str) and len(value) > MESSAGE_LIMIT:
        return bound_text(value)
    return value


def attempt_record_to_dict(record: TurnAttemptRecord) -> dict[str, Any]:
    return {
        "provider": record.provider,
        "model_id": record.model_id,
        "timeout_seconds": record.timeout_seconds,
        "step_grant": record.step_grant,
        "provider_requests_used": record.provider_requests_used,
    }


def persistence_to_dict(evidence: TurnPersistenceEvidence) -> dict[str, Any]:
    return {
        "move_id": evidence.move_id,
        "move_count_delta": evidence.move_count_delta,
        "state_version_delta": evidence.state_version_delta,
        "action_matches_sse": evidence.action_matches_sse,
        "words_match_sse": evidence.words_match_sse,
        "score_matches_sse": evidence.score_matches_sse,
    }


def turn_sample_to_dict(sample: TurnSample) -> dict[str, Any]:
    return {
        "playability": {
            "status": sample.playability_status,
            "witness": sample.witness,
        },
        "action": sample.action,
        "placements": sample.placements,
        "formed_words": list(sample.formed_words),
        "score": sample.score,
        "completion_source": sample.completion_source,
        "probe_status": sample.probe_status,
        "repair_attempted": sample.repair_attempted,
        "terminal_cause": sample.terminal_cause,
        "attempts": [attempt_record_to_dict(item) for item in sample.attempts],
        "turn_provider_requests_used": sample.turn_provider_requests_used,
        "queue_length": sample.queue_length,
        "unresolved_in_flight": sample.unresolved_in_flight,
        "persistence": persistence_to_dict(sample.persistence),
        "two_letter_policy": {
            "complete_formed_words": list(sample.formed_words),
            "rejected": list(sample.rejected_two_letter_words),
        },
        "terminal_kind": sample.terminal_kind,
        "lost_terminal": sample.lost_terminal,
        "external_provider_invocations": sample.external_provider_invocations,
        "backend_origins": list(sample.backend_origins),
        "foreign_origins": list(sample.foreign_origins),
        "verdict": sample.verdict,
        "reason_code": sample.reason_code,
    }


def _bounded_terminal_cause(cause: str | None) -> bool:
    if not cause:
        return False
    return cause not in {"error", "AI move failed"}


def classify_turn_sample(
    *,
    playability_status: str,
    action: str | None,
    formed_words: Sequence[str],
    sse_words: Sequence[str],
    persisted_words: Sequence[str],
    sse_placements: Sequence[Mapping[str, object]],
    persisted_placements: Sequence[Mapping[str, object]],
    rejected_two_letter_words: Sequence[str],
    terminal_kind: str,
    completion_source: str | None,
    terminal_cause: str | None,
    coded_provider_error: bool,
    move_count_delta: int,
    move_id: int | None,
    lost_terminal: bool,
    variant_letters: frozenset[str] | None = None,
) -> tuple[TurnVerdict, str]:
    if rejected_two_letter_words:
        return ("fail", REASON_ILLEGAL_TWO_LETTER)
    if sse_words and persisted_words and not formed_words_nfc_equal(sse_words, persisted_words):
        return ("fail", REASON_UNICODE_MISMATCH)
    if formed_words and persisted_words and not formed_words_nfc_equal(
        formed_words, persisted_words
    ):
        return ("fail", REASON_UNICODE_MISMATCH)
    if sse_placements and persisted_placements and not placements_nfc_equal(
        sse_placements, persisted_placements
    ):
        return ("fail", REASON_UNICODE_MISMATCH)
    if variant_letters:
        for item in list(sse_placements) + list(persisted_placements):
            letter = item.get("letter")
            blank = item.get("blank_as")
            if not _is_nfc_unicode_letter_tile(letter, blank, variant_letters):
                return ("fail", REASON_UNICODE_MISMATCH)
    if playability_status in {"found", "indeterminate"} and action in {
        "pass",
        "exchange",
    }:
        return ("fail", REASON_FOUND_NONSCORING_ACTION)
    if move_count_delta > 1:
        return ("fail", REASON_STATE_ADVANCED_MORE_THAN_ONCE)
    if terminal_kind == "done" and (move_id is None or move_count_delta != 1):
        return ("fail", REASON_SSE_DONE_WITHOUT_MOVE)
    if (
        move_id is not None
        and move_count_delta == 1
        and lost_terminal
        and _bounded_terminal_cause(terminal_cause)
    ):
        return ("pass_with_telemetry", REASON_PERSIST_LOST_TERMINAL)
    if (
        move_id is not None
        and move_count_delta == 1
        and lost_terminal
        and completion_source in COMPLETION_SOURCE_VOCABULARY
    ):
        return ("pass_with_telemetry", REASON_PERSIST_LOST_TERMINAL)
    unchanged = move_count_delta == 0 and move_id is None
    if coded_provider_error and unchanged:
        return ("external_incomplete", REASON_CODED_PROVIDER_UNCHANGED)
    if unchanged and terminal_kind in {"generic_error", "no_terminal"}:
        if not coded_provider_error and not _bounded_terminal_cause(terminal_cause):
            return ("fail", REASON_GENERIC_UNCHANGED)
    if (
        playability_status == "found"
        and action == "place"
        and move_id is not None
        and move_count_delta == 1
        and terminal_kind == "done"
        and completion_source in COMPLETION_SOURCE_VOCABULARY
    ):
        return ("pass", REASON_OK)
    if (
        playability_status == "none"
        and action in {"exchange", "pass"}
        and move_id is not None
        and move_count_delta == 1
        and terminal_kind == "done"
    ):
        return ("pass", REASON_OK)
    if move_id is not None and move_count_delta == 1 and terminal_kind == "done":
        return ("pass", REASON_OK)
    if unchanged and terminal_kind in {"generic_error", "no_terminal"}:
        return ("fail", REASON_GENERIC_UNCHANGED)
    return ("fail", REASON_GENERIC_UNCHANGED)


def format_turn_metric_line(
    variant_slug: str,
    label: str,
    sample: TurnSample,
) -> str:
    words = ",".join(sample.formed_words) if sample.formed_words else "-"
    source = sample.completion_source or "-"
    return (
        f"{variant_slug} turn {label} action={sample.action or '-'} "
        f"source={source} score={sample.score} words={words} "
        f"persisted={sample.persistence.move_count_delta} "
        f"verdict={sample.verdict}"
    )


def build_turn_report(
    *,
    requested: Mapping[str, str | int],
    context: VariantProbeContext,
    samples: Sequence[TurnSample],
    generated_at: datetime | None = None,
    source_revision: str | None = None,
) -> dict[str, Any]:
    stamp = generated_at or datetime.now(timezone.utc)
    generated = stamp.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    pass_count = sum(1 for sample in samples if sample.verdict == "pass")
    fail_count = sum(1 for sample in samples if sample.verdict == "fail")
    telemetry_count = sum(
        1 for sample in samples if sample.verdict == "pass_with_telemetry"
    )
    incomplete_count = sum(
        1 for sample in samples if sample.verdict == "external_incomplete"
    )
    allowlist_size = len(context.allowlist) if context.allowlist is not None else None
    total_requests = sum(sample.turn_provider_requests_used for sample in samples)
    unresolved = sum(sample.unresolved_in_flight for sample in samples)
    external = sum(sample.external_provider_invocations for sample in samples)
    payload = {
        "artifact": ARTIFACT_ID,
        "report_kind": REPORT_KIND_TURN,
        "generated_at": generated,
        "source_revision": source_revision or observe_source_revision(),
        "requested": dict(requested),
        "variant": {
            "slug": context.variant.slug,
            "lexicon_id": _lexicon_id(context.variant),
            "two_letter_lexicon_size": allowlist_size,
        },
        "samples": [turn_sample_to_dict(sample) for sample in samples],
        "summary": {
            "sample_count": len(samples),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "pass_with_telemetry_count": telemetry_count,
            "external_incomplete_count": incomplete_count,
            "total_provider_requests": total_requests,
            "unresolved_in_flight_count": unresolved,
            "external_provider_invocations": external,
        },
    }
    redacted = redacted_copy(payload)
    assert isinstance(redacted, dict)
    return redacted


def turn_exit_code(samples: Sequence[TurnSample], *, runtime_mode: str) -> int:
    if any(sample.verdict == "fail" for sample in samples):
        return 1
    if any(sample.verdict == "external_incomplete" for sample in samples):
        if runtime_mode == "fake":
            return 1
        return 3
    return 0


def samples_from_result_payload(payload: Mapping[str, Any]) -> list[TurnSample]:
    raw_samples = payload.get("samples")
    if not isinstance(raw_samples, list):
        raise DiagnosticInputError("turn result samples must be a list")
    samples: list[TurnSample] = []
    for item in raw_samples:
        if not isinstance(item, dict):
            raise DiagnosticInputError("turn result sample must be an object")
        samples.append(_turn_sample_from_dict(item))
    return samples


def _turn_sample_from_dict(item: Mapping[str, Any]) -> TurnSample:
    playability = item.get("playability")
    playability_status = "indeterminate"
    witness: dict[str, object] | None = None
    if isinstance(playability, dict):
        status = playability.get("status")
        if isinstance(status, str):
            playability_status = status
        raw_witness = playability.get("witness")
        if isinstance(raw_witness, dict):
            witness = dict(raw_witness)
    action_raw = item.get("action")
    action = action_raw if isinstance(action_raw, str) else None
    formed = formed_words_from_payload(item.get("formed_words"))
    placements = placements_from_payload(item.get("placements"))
    score_raw = item.get("score")
    score = score_raw if isinstance(score_raw, int) and not isinstance(score_raw, bool) else 0
    source = item.get("completion_source")
    completion_source = source if isinstance(source, str) else None
    probe = item.get("probe_status")
    probe_status = probe if isinstance(probe, str) else None
    repair = item.get("repair_attempted")
    repair_attempted = repair if isinstance(repair, bool) else None
    cause = item.get("terminal_cause")
    terminal_cause = cause if isinstance(cause, str) else None
    attempts_raw = item.get("attempts")
    attempts: list[TurnAttemptRecord] = []
    if isinstance(attempts_raw, list):
        for attempt in attempts_raw:
            if not isinstance(attempt, dict):
                continue
            provider = attempt.get("provider")
            model_id = attempt.get("model_id")
            timeout = attempt.get("timeout_seconds")
            grant = attempt.get("step_grant")
            used = attempt.get("provider_requests_used")
            if not isinstance(provider, str) or not isinstance(model_id, str):
                continue
            attempts.append(
                TurnAttemptRecord(
                    provider=provider,
                    model_id=model_id,
                    timeout_seconds=timeout if isinstance(timeout, int) else 0,
                    step_grant=grant if isinstance(grant, int) else 0,
                    provider_requests_used=used if isinstance(used, int) else 0,
                )
            )
    used_raw = item.get("turn_provider_requests_used")
    queue_raw = item.get("queue_length")
    unresolved_raw = item.get("unresolved_in_flight")
    persistence_raw = item.get("persistence")
    persistence = TurnPersistenceEvidence(
        move_id=None,
        move_count_delta=0,
        state_version_delta=0,
        action_matches_sse=False,
        words_match_sse=False,
        score_matches_sse=False,
    )
    if isinstance(persistence_raw, dict):
        move_id_raw = persistence_raw.get("move_id")
        delta_raw = persistence_raw.get("move_count_delta")
        state_raw = persistence_raw.get("state_version_delta")
        persistence = TurnPersistenceEvidence(
            move_id=move_id_raw if isinstance(move_id_raw, int) else None,
            move_count_delta=delta_raw if isinstance(delta_raw, int) else 0,
            state_version_delta=state_raw if isinstance(state_raw, int) else 0,
            action_matches_sse=bool(persistence_raw.get("action_matches_sse")),
            words_match_sse=bool(persistence_raw.get("words_match_sse")),
            score_matches_sse=bool(persistence_raw.get("score_matches_sse")),
        )
    policy = item.get("two_letter_policy")
    rejected: tuple[str, ...] = ()
    if isinstance(policy, dict):
        rejected = formed_words_from_payload(policy.get("rejected"))
    terminal_kind_raw = item.get("terminal_kind")
    terminal_kind = terminal_kind_raw if isinstance(terminal_kind_raw, str) else "no_terminal"
    lost = bool(item.get("lost_terminal"))
    external_raw = item.get("external_provider_invocations")
    backend_raw = item.get("backend_origins")
    foreign_raw = item.get("foreign_origins")
    verdict_raw = item.get("verdict")
    verdict: TurnVerdict = (
        verdict_raw
        if verdict_raw in {"pass", "pass_with_telemetry", "fail", "external_incomplete"}
        else "fail"
    )
    reason_raw = item.get("reason_code")
    reason = reason_raw if isinstance(reason_raw, str) and reason_raw else REASON_GENERIC_UNCHANGED
    return TurnSample(
        playability_status=playability_status,
        witness=witness,
        action=action,
        placements=placements,
        formed_words=formed,
        score=score,
        completion_source=completion_source,
        probe_status=probe_status,
        repair_attempted=repair_attempted,
        terminal_cause=terminal_cause,
        attempts=tuple(attempts),
        turn_provider_requests_used=used_raw if isinstance(used_raw, int) else 0,
        queue_length=queue_raw if isinstance(queue_raw, int) else 0,
        unresolved_in_flight=unresolved_raw if isinstance(unresolved_raw, int) else 0,
        persistence=persistence,
        rejected_two_letter_words=rejected,
        terminal_kind=terminal_kind,
        lost_terminal=lost,
        external_provider_invocations=external_raw if isinstance(external_raw, int) else 0,
        backend_origins=tuple(
            origin for origin in backend_raw if isinstance(origin, str)
        )
        if isinstance(backend_raw, list)
        else (),
        foreign_origins=tuple(
            origin for origin in foreign_raw if isinstance(origin, str)
        )
        if isinstance(foreign_raw, list)
        else (),
        verdict=verdict,
        reason_code=reason,
    )
