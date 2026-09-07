"""Confined reader and text presentation for diagnostic-run admin pages.

This module is presentation-only over already-landed runner artifacts:

- It reads ONLY ``{run.id}-report.json`` from the runner's report directory
  (``backend/var/diagnostics``, derived from this module's installed path).
- It NEVER ``open()``s the stored ``report_path`` string: the stored string is
  compared against the canonical expected path and otherwise refused.
- Directory and file opens are no-follow (``O_NOFOLLOW`` / ``O_DIRECTORY``);
  the file must be a regular file (``fstat``); reads are capped at 2 MiB.
- JSON is strict UTF-8 with duplicate-key and non-standard-constant rejection.
- It never reads a log, never follows a name inside the JSON, never runs the
  diagnostic command, and never calls ``build_*_report``.

Everything returned is a plain Python scalar (or lists/dicts of scalars) that
Django templates render through autoescaped text nodes.
"""

from __future__ import annotations

import errno
import json
import os
import stat
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from game.diagnostics import COMPLETION_SOURCE_VOCABULARY

_READ_LIMIT_BYTES = 2 * 1024 * 1024
_MQR_FLOOR = 8

AVAILABILITY_EMPTY = "No report is available for this run."
AVAILABILITY_RACE = "A report may become available after finalization. Reload to check."
AVAILABILITY_MISMATCH = (
    "The recorded report location for this run is not the expected report file; "
    "it was not opened."
)
AVAILABILITY_MISSING = "The report file for this run is not present; no report is shown."
AVAILABILITY_UNSAFE = (
    "The report file for this run could not be read safely; it was not opened."
)
AVAILABILITY_OVERSIZE = (
    "The stored report file exceeds the 2 MiB presentation cap and was not read."
)
AVAILABILITY_UNSUPPORTED = "This platform cannot no-follow-open files; the report was not read."
AVAILABILITY_MALFORMED = "The stored report file is malformed and was not rendered."
AVAILABILITY_IDENTITY = "The stored report does not match this run and was not rendered."
AVAILABILITY_UNKNOWN_KIND = "This report kind is not displayed on this page."

AVAILABILITY_COPY: dict[str, str] = {
    "path_mismatch": AVAILABILITY_MISMATCH,
    "missing": AVAILABILITY_MISSING,
    "unsafe": AVAILABILITY_UNSAFE,
    "oversize": AVAILABILITY_OVERSIZE,
    "unsupported": AVAILABILITY_UNSUPPORTED,
    "malformed": AVAILABILITY_MALFORMED,
    "identity": AVAILABILITY_IDENTITY,
    "empty_path": AVAILABILITY_EMPTY,
}

FAKE_SCRIPT = "generic_unchanged"
FAKE_REASON_CODE = "generic_unchanged_turn"
LTAI_COMPOSITE_COPY = "LTAI composite: not available in this report."
AI_MATCH_COPY = (
    "Full-game diagnostic. Final scores are engine results. This report describes "
    "the executed game and assistance; it does not establish a model-strength ranking."
)

_LTAI_RATE_COMPONENTS: tuple[tuple[str, str, int], ...] = (
    ("Tool-valid rate", "valid_candidate_count", 20),
    ("First-call-valid rate", "first_validate_valid", 20),
    ("Give-up-when-legal rate", "give_up_while_legal", 20),
    ("Authorship rate", "model_authored", 20),
    ("Malformed rate", "malformed_or_non_tool", 20),
)


@dataclass(frozen=True)
class ReportReadResult:
    """Reader outcome: a parsed payload or one closed failure code."""

    failure: str | None
    payload: dict[str, Any] | None


def default_report_directory() -> Path:
    """The runner's report directory, derived from this module's install path.

    ``game/diagnostic_admin_reports.py`` → parents[1] is the backend root, so
    the directory is ``backend/var/diagnostics`` — the same directory the
    runner's ``run_diagnostic_match`` command publishes into.
    """
    return Path(__file__).resolve().parents[1] / "var" / "diagnostics"


def expected_report_path(run_id: uuid.UUID, *, directory: Path | None = None) -> Path:
    base = directory if directory is not None else default_report_directory()
    return base / f"{run_id}-report.json"


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(name: str) -> Any:
    raise ValueError(f"non-standard JSON constant: {name}")


def _fs_failure_code(exc: OSError) -> str:
    if exc.errno == errno.ENOENT:
        return "missing"
    # ELOOP (symlink) and ENOTDIR (symlink-to-dir under O_DIRECTORY|O_NOFOLLOW)
    # are unexpected shapes, refused as unsafe — never followed.
    return "unsafe"


def read_diagnostic_report(
    run_id: uuid.UUID,
    report_path: str,
    *,
    directory: Path | None = None,
) -> ReportReadResult:
    """Read the ONE expected report file for ``run_id`` under ``directory``.

    The stored ``report_path`` string is only compared, never opened. Every
    descriptor is closed on every path. Failure codes are closed and are
    rendered as fixed English by ``present_report`` — never exception text.
    """
    expected = expected_report_path(run_id, directory=directory)
    if not report_path:
        return ReportReadResult("empty_path", None)
    if Path(report_path) != expected:
        return ReportReadResult("path_mismatch", None)
    nofollow = getattr(os, "O_NOFOLLOW", None)
    o_directory = getattr(os, "O_DIRECTORY", None)
    o_nonblock = getattr(os, "O_NONBLOCK", 0)
    if nofollow is None or o_directory is None:
        return ReportReadResult("unsupported", None)
    var_fd: int | None = None
    diag_fd: int | None = None
    file_fd: int | None = None
    try:
        var_dir = expected.parent.parent
        try:
            var_fd = os.open(str(var_dir), os.O_RDONLY | o_directory | nofollow)
        except OSError as exc:
            return ReportReadResult(_fs_failure_code(exc), None)
        try:
            diag_fd = os.open(
                expected.parent.name, os.O_RDONLY | o_directory | nofollow, dir_fd=var_fd
            )
        except OSError as exc:
            return ReportReadResult(_fs_failure_code(exc), None)
        try:
            file_fd = os.open(
                expected.name,
                os.O_RDONLY | nofollow | o_nonblock,
                dir_fd=diag_fd,
            )
        except OSError as exc:
            return ReportReadResult(_fs_failure_code(exc), None)
        info = os.fstat(file_fd)
        if not stat.S_ISREG(info.st_mode):
            return ReportReadResult("unsafe", None)
        if info.st_size > _READ_LIMIT_BYTES:
            return ReportReadResult("oversize", None)
        blocks: list[bytes] = []
        remaining = _READ_LIMIT_BYTES + 1
        while remaining > 0:
            block = os.read(file_fd, remaining)
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        raw = b"".join(blocks)
        if len(raw) > _READ_LIMIT_BYTES:
            return ReportReadResult("oversize", None)
        try:
            text = raw.decode("utf-8")
            payload = json.loads(
                text,
                object_pairs_hook=_reject_duplicate_keys,
                parse_constant=_reject_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return ReportReadResult("malformed", None)
        if not isinstance(payload, dict):
            return ReportReadResult("malformed", None)
        requested = payload.get("requested")
        if not isinstance(requested, dict):
            return ReportReadResult("malformed", None)
        if str(requested.get("run_id", "")) != str(run_id):
            return ReportReadResult("identity", None)
        summary = payload.get("summary")
        if summary is not None and not isinstance(summary, dict):
            return ReportReadResult("malformed", None)
        samples = payload.get("samples")
        if samples is not None and not isinstance(samples, list):
            return ReportReadResult("malformed", None)
        return ReportReadResult(None, payload)
    finally:
        for fd in (file_fd, diag_fd, var_fd):
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass


def present_report(
    run_id: uuid.UUID,
    report_path: str,
    *,
    terminal: bool,
    run_score_authority: str,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Availability state plus kind-specific presentation blocks.

    ``terminal`` gates the publication-race copy for a terminal run whose
    report has not landed yet. ``run_score_authority`` is displayed as-is and
    stays absent when the run column is absent — never filled from a sample.
    """
    if not report_path:
        if terminal:
            return {"state": "race", "message": AVAILABILITY_RACE}
        return {"state": "empty", "message": AVAILABILITY_EMPTY}
    result = read_diagnostic_report(run_id, report_path, directory=directory)
    if result.failure is not None:
        return {"state": result.failure, "message": AVAILABILITY_COPY[result.failure]}
    payload = result.payload
    assert payload is not None
    kind = payload.get("report_kind")
    if kind == "model-position":
        return {
            "state": "ok",
            "message": "",
            "kind": "model-position",
            **_present_model_position(payload, run_score_authority=run_score_authority),
        }
    if kind == "ai-match":
        return {
            "state": "ok",
            "message": "",
            "kind": "ai-match",
            **_present_ai_match(payload, run_score_authority=run_score_authority),
        }
    return {"state": "unknown_kind", "message": AVAILABILITY_UNKNOWN_KIND}


def _display(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    return str(value)


def _or_not_recorded(value: Any) -> str:
    if value is None or value == "":
        return "not recorded"
    return _display(value)


def _requested(payload: dict[str, Any]) -> dict[str, Any]:
    requested = payload.get("requested")
    return requested if isinstance(requested, dict) else {}


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary")
    return summary if isinstance(summary, dict) else {}


def _samples(payload: dict[str, Any]) -> list[dict[str, Any]]:
    samples = payload.get("samples")
    if isinstance(samples, list):
        return [sample for sample in samples if isinstance(sample, dict)]
    return []


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def is_plain_int(value: Any) -> bool:
    """A JSON int that is not a bool masquerading as one."""
    return _is_int(value)


def is_plain_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_bool(value: Any) -> bool:
    return isinstance(value, bool)


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _measured_counts(samples: list[dict[str, Any]], field: str, kind: str) -> tuple[int, int]:
    measured = 0
    successes = 0
    for sample in samples:
        value = sample.get(field)
        if kind == "int_positive":
            if not isinstance(value, int) or isinstance(value, bool):
                continue
            measured += 1
            if value > 0:
                successes += 1
        else:
            if not isinstance(value, bool):
                continue
            measured += 1
            if value is True:
                successes += 1
    return measured, successes


def _mqr_state(
    samples: list[dict[str, Any]], summary: dict[str, Any]
) -> tuple[int, float | None]:
    """(recorded ratio count, report mean). 'Not recorded' vs 'recorded,
    insufficient' must stay distinguishable; measured 0 and ratios > 1 are
    preserved."""
    ratio_count = sum(
        1 for sample in samples if _is_number(sample.get("move_quality_ratio"))
    )
    mean = summary.get("move_quality_ratio")
    if ratio_count == 0:
        recorded = summary.get("move_quality_sample_count")
        if isinstance(recorded, int) and not isinstance(recorded, bool):
            ratio_count = recorded
        if ratio_count == 0:
            return 0, None
    return ratio_count, mean if _is_number(mean) else None


def ltai_rows(samples: list[dict[str, Any]], summary: dict[str, Any]) -> list[dict[str, str]]:
    """LTAI components as text observations. Null is not false; a bool is not
    an int; unattempted is not did_not_measure. No composite is computed."""
    rows: list[dict[str, str]] = []
    for label, field, floor in _LTAI_RATE_COMPONENTS:
        kind = "int_positive" if field == "valid_candidate_count" else "bool_true"
        measured, successes = _measured_counts(samples, field, kind)
        if measured < floor:
            observation = f"Insufficient sample ({measured}/{floor})."
        else:
            pct = round(100.0 * successes / measured, 1)
            observation = f"{successes}/{measured} measured ({pct:g}%)."
        rows.append({"component": label, "observation": observation, "floor": str(floor)})
    ratio_count, mean = _mqr_state(samples, summary)
    if ratio_count == 0:
        observation = "Not recorded."
    elif ratio_count < _MQR_FLOOR:
        observation = f"Recorded, insufficient sample ({ratio_count}/{_MQR_FLOOR})."
    elif mean is None:
        observation = f"{ratio_count} recorded ratios; report mean not recorded."
    else:
        observation = f"{ratio_count} recorded ratios; report mean {mean:.3f}."
    rows.append(
        {
            "component": "Move-quality ratio",
            "observation": observation,
            "floor": str(_MQR_FLOOR),
        }
    )
    return rows


def floor_violations(samples: list[dict[str, Any]], summary: dict[str, Any]) -> list[str]:
    """Component labels whose measured sample count is below its floor."""
    violations: list[str] = []
    for label, field, floor in _LTAI_RATE_COMPONENTS:
        kind = "int_positive" if field == "valid_candidate_count" else "bool_true"
        measured, _successes = _measured_counts(samples, field, kind)
        if measured < floor:
            violations.append(label)
    ratio_count, _mean = _mqr_state(samples, summary)
    if ratio_count < _MQR_FLOOR:
        violations.append("Move-quality ratio")
    return violations


def fake_warning(payload: dict[str, Any]) -> str | None:
    """Exact fake copy when the artifact is the fake generic_unchanged path.

    Count-aware wording keeps the required 24-sample sentence byte-identical
    while staying honest for shorter complete fixtures.
    """
    requested = _requested(payload)
    summary = _summary(payload)
    samples = _samples(payload)
    if not samples or requested.get("script") != FAKE_SCRIPT:
        return None
    for sample in samples:
        if (
            sample.get("verdict") != "fail"
            or sample.get("score") is not None
            or sample.get("reason_code") != FAKE_REASON_CODE
        ):
            return None
    if summary.get("did_not_measure") != len(samples):
        return None
    count = len(samples)
    return (
        f"Fake diagnostic run — model quality was not measured. All {count} position "
        f"scores are null; did_not_measure = {count}. The {count} recorded ‘fail’ "
        "verdicts describe the generic_unchanged test path. They do not show that "
        "this model plays well or badly. score_authority = engine does not change this."
    )


def _metadata_rows(
    payload: dict[str, Any], *, run_score_authority: str, with_digest: bool
) -> list[list[str]]:
    requested = _requested(payload)
    variant_raw = payload.get("variant")
    variant: dict[str, Any] = variant_raw if isinstance(variant_raw, dict) else {}
    rows: list[list[str]] = [
        ["Artifact", _or_not_recorded(payload.get("artifact"))],
        ["Report kind", _or_not_recorded(payload.get("report_kind"))],
        ["Generated at", _or_not_recorded(payload.get("generated_at"))],
        ["Source revision", _or_not_recorded(payload.get("source_revision"))],
    ]
    if with_digest:
        rows.append(["Provider", _or_not_recorded(requested.get("provider"))])
        rows.append(["Model", _or_not_recorded(requested.get("model_id"))])
        rows.append(["Position-set digest", _or_not_recorded(requested.get("position_set_digest"))])
    rows.append(["Variant", _or_not_recorded(variant.get("slug"))])
    rows.append(["Lexicon", _or_not_recorded(variant.get("lexicon_id"))])
    rows.append(["Assist mode", _or_not_recorded(requested.get("assist_mode"))])
    rows.append(["Executed runtime mode", _or_not_recorded(requested.get("executed_runtime_mode"))])
    rows.append(
        [
            "Run score authority",
            run_score_authority if run_score_authority else "not recorded",
        ]
    )
    return rows


def _histogram_rows(summary: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    counts_raw = summary.get("completion_source_counts")
    counts = counts_raw if isinstance(counts_raw, dict) else {}
    did_not_measure = summary.get("completion_source_did_not_measure_count")
    rows: list[dict[str, Any]] = [
        {"source": source, "count": _display(counts.get(source, 0))}
        for source in COMPLETION_SOURCE_VOCABULARY
    ]
    unknown = sorted(str(key) for key in counts if key not in COMPLETION_SOURCE_VOCABULARY)
    for key in unknown:
        rows.append({"source": key, "count": _display(counts.get(key, 0))})
    rows.append(
        {
            "source": "Not measured (null source)",
            "count": _display(did_not_measure),
        }
    )
    return rows, bool(unknown)


_SUMMARY_ROW_ORDER: tuple[tuple[str, str], ...] = (
    ("sample_count", "sample_count"),
    ("pass_count", "pass_count"),
    ("fail_count", "fail_count"),
    ("position_count", "position_count"),
    ("unattempted_count", "unattempted_count"),
    ("end_reason", "end_reason"),
    ("truncated", "truncated"),
    ("move_quality_sample_count", "move_quality_sample_count"),
    ("did_not_measure", "did_not_measure"),
    ("move_quality_ratio", "move_quality_ratio"),
    ("completion_source_did_not_measure_count", "completion_source_did_not_measure_count"),
    ("total_provider_requests", "total_provider_requests"),
)


def _summary_rows(summary: dict[str, Any]) -> list[list[str]]:
    rows: list[list[str]] = []
    for key, label in _SUMMARY_ROW_ORDER:
        if key in summary:
            rows.append([label, _display(summary[key])])
    return rows


def _sample_details(sample: dict[str, Any]) -> dict[str, str]:
    position_raw = sample.get("position")
    position: dict[str, Any] = position_raw if isinstance(position_raw, dict) else {}
    title = (
        f"Position {_display(position.get('position_index'))} — verdict "
        f"{_display(sample.get('verdict'))} ({_display(sample.get('reason_code'))})"
    )
    field_order = (
        "model_id",
        "seat_index",
        "executed_runtime_mode",
        "completion_source",
        "terminal_cause",
        "score",
        "valid_candidate_count",
        "model_legal_score",
        "ranked_best_score",
        "move_quality_ratio",
        "provider_requests_used",
        "wall_clock_ms",
        "set_digest",
        "position_index",
    )
    lines: list[str] = []
    for field in field_order:
        if field == "set_digest":
            lines.append(f"set_digest: {_display(position.get('set_digest'))}")
            continue
        if field == "position_index":
            lines.append(f"position_index: {_display(position.get('position_index'))}")
            continue
        lines.append(f"{field}: {_display(sample.get(field))}")
    return {"title": title, "body": "\n".join(lines)}


def _present_model_position(
    payload: dict[str, Any], *, run_score_authority: str
) -> dict[str, Any]:
    summary = _summary(payload)
    samples = _samples(payload)
    histogram_rows, histogram_unknown = _histogram_rows(summary)
    return {
        "fake_warning": fake_warning(payload),
        "metadata_rows": _metadata_rows(
            payload, run_score_authority=run_score_authority, with_digest=True
        ),
        "verdict_pass": _display(summary.get("pass_count", 0)),
        "verdict_fail": _display(summary.get("fail_count", 0)),
        "histogram_rows": histogram_rows,
        "histogram_unknown": histogram_unknown,
        "summary_rows": _summary_rows(summary),
        "ltai_rows": ltai_rows(samples, summary),
        "ltai_composite": LTAI_COMPOSITE_COPY,
        "samples": [_sample_details(sample) for sample in samples],
    }


def _ai_match_sample(payload: dict[str, Any]) -> dict[str, Any]:
    samples = _samples(payload)
    return samples[0] if samples else {}


def _ai_match_rows(payload: dict[str, Any]) -> list[list[str]]:
    summary = _summary(payload)
    sample = _ai_match_sample(payload)
    rack_raw = sample.get("rack_remaining")
    rack: dict[str, Any] = rack_raw if isinstance(rack_raw, dict) else {}
    finals_raw = sample.get("final_scores")
    finals: dict[str, Any] = finals_raw if isinstance(finals_raw, dict) else {}
    rows: list[list[str]] = [
        ["End reason", _or_not_recorded(sample.get("end_reason"))],
        ["Match samples (report sample_count)", _display(summary.get("sample_count", 0))],
        ["Recorded plies (per-sample plies)", _display(sample.get("plies"))],
        ["Engine score authority", _or_not_recorded(sample.get("score_authority"))],
        ["Bag remaining", _display(sample.get("bag_remaining"))],
    ]
    for name in sorted(rack):
        rows.append([f"Rack remaining {name}", _display(rack.get(name))])
    for name in sorted(finals):
        rows.append([f"Engine final score {name}", _display(finals.get(name))])
    rows.append(["Verdict", _or_not_recorded(sample.get("verdict"))])
    rows.append(["Reason code", _or_not_recorded(sample.get("reason_code"))])
    return rows


def _present_ai_match(payload: dict[str, Any], *, run_score_authority: str) -> dict[str, Any]:
    sample = _ai_match_sample(payload)
    records_raw = sample.get("ply_records")
    records: list[Any] = records_raw if isinstance(records_raw, list) else []
    lines: list[str] = []
    for index, record in enumerate(record for record in records if isinstance(record, dict)):
        lines.append(
            f"ply {index}: seat {_display(record.get('seat_index'))} "
            f"model {_display(record.get('model_id'))} "
            f"source {_display(record.get('completion_source'))} "
            f"cause {_display(record.get('terminal_cause'))} "
            f"wall_ms {_display(record.get('wall_clock_ms'))} "
            f"runtime {_display(record.get('executed_runtime_mode'))}"
        )
    body = "\n".join(lines) if lines else "No ply records in this sample."
    return {
        "match_copy": AI_MATCH_COPY,
        "metadata_rows": _metadata_rows(
            payload, run_score_authority=run_score_authority, with_digest=False
        ),
        "match_rows": _ai_match_rows(payload),
        "samples": [{"title": "Executed game plies (engine results)", "body": body}],
    }


def comparison_metrics_summary(samples: list[dict[str, Any]], summary: dict[str, Any]) -> str:
    """Per-run metrics text for one comparison row. Values come from that
    run's artifact only; no pooling or averaging across runs."""
    parts: list[str] = []
    for label, field, floor in _LTAI_RATE_COMPONENTS:
        kind = "int_positive" if field == "valid_candidate_count" else "bool_true"
        measured, successes = _measured_counts(samples, field, kind)
        if measured < floor:
            parts.append(f"{label.lower()} below floor ({measured}/{floor})")
        else:
            pct = round(100.0 * successes / measured, 1)
            parts.append(f"{_pool_component_key(label)} {successes}/{measured} ({pct:g}%)")
    ratio_count, mean = _mqr_state(samples, summary)
    if ratio_count == 0:
        parts.append("move_quality not recorded")
    elif ratio_count < _MQR_FLOOR:
        parts.append(f"move_quality insufficient ({ratio_count}/{_MQR_FLOOR})")
    elif mean is None:
        parts.append(f"move_quality {ratio_count} ratios")
    else:
        parts.append(f"move_quality mean {mean:.3f} over {ratio_count} ratios")
    return "; ".join(parts)


def _pool_component_key(label: str) -> str:
    keys = {
        "Tool-valid rate": "tool_valid",
        "First-call-valid rate": "first_call_valid",
        "Give-up-when-legal rate": "give_up_when_legal",
        "Authorship rate": "authorship",
        "Malformed rate": "malformed",
    }
    return keys[label]
