"""S6 admin surface: live run page, finished report, and comparison table.

Fake-mode only. No runner spawn, no mint, no provider calls, no browser MCP.
Artifacts are handcrafted fixtures under git-ignored backend/var/diagnostics or
pytest tmp directories.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid as uuid_module
from pathlib import Path
from typing import Any
from unittest import mock

from django.contrib.auth.models import Permission
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from catalog.models import AIModel, AIPrompt
from catalog.selection import DEFAULT_FREE_MODEL_ID, FREE_RIVAL_IDS, FREE_RIVAL_PAIRS
from game import admin as admin_module
from game.diagnostics import COMPLETION_SOURCE_VOCABULARY, ARTIFACT_ID
from game.models import DiagnosticPly, DiagnosticRun
from game.services import configure_diagnostic_run, create_diagnostic_game

POSITION_SET_DIGEST = "aaac5c27282a67fbe3d3fabd202098181b5101d66598e35bf79ebb746226773a"
_CLOSED_ORIGIN = "http://127.0.0.1:9"

_PROVIDER_BY_ID = {model_id: provider for provider, model_id in FREE_RIVAL_PAIRS}

_LAUNCH_SUCCESS = (
    "Diagnostic run launched in fake mode. This page shows its heartbeat, "
    "recorded plies, and report when available."
)
_CADENCE_COPY = (
    "The runner records a heartbeat at least every five plies or approximately "
    "every 30 seconds."
)
_PLY_CAPTION = "Showing the latest 20 recorded plies."
_NOT_MEASURED = "Not measured."
_AVAILABILITY_EMPTY = "No report is available for this run."
_AVAILABILITY_RACE = "A report may become available after finalization. Reload to check."
_AVAILABILITY_MISMATCH = (
    "The recorded report location for this run is not the expected report file; "
    "it was not opened."
)
_AVAILABILITY_MISSING = "The report file for this run is not present; no report is shown."
_AVAILABILITY_UNSAFE = (
    "The report file for this run could not be read safely; it was not opened."
)
_AVAILABILITY_OVERSIZE = (
    "The stored report file exceeds the 2 MiB presentation cap and was not read."
)
_AVAILABILITY_UNSUPPORTED = "This platform cannot no-follow-open files; the report was not read."
_AVAILABILITY_MALFORMED = "The stored report file is malformed and was not rendered."
_AVAILABILITY_IDENTITY = "The stored report does not match this run and was not rendered."

_REASON_RUNTIME = (
    "Executed runtime is not live; fake and mixed-runtime runs are never pooled."
)
_REASON_RUNTIME_SAMPLES = "Sample executed runtime is not consistently live."
_REASON_MIXED_SEATS = "Mixed seats — attributed to neither model."
_COMPARE_NOTE_PAGE = (
    "This table covers only the runs displayed on this page and holds no rolling statistics."
)
_COMPARE_NOTE_PROMPT = "Persisted prompt IDs are not historical prompt-content fingerprints."
_POOL_EMPTY = "No measured comparison pool on this page."
_NO_RUNS = "No position-set terminal runs on this page."

_FAKE_WARNING_24 = (
    "Fake diagnostic run — model quality was not measured. All 24 position scores "
    "are null; did_not_measure = 24. The 24 recorded ‘fail’ verdicts describe the "
    "generic_unchanged test path. They do not show that this model plays well or "
    "badly. score_authority = engine does not change this."
)


def _var_dir() -> Path:
    return Path(admin_module.__file__).resolve().parents[1] / "var" / "diagnostics"


def _make_rival(*, model_id: str = DEFAULT_FREE_MODEL_ID, **overrides: Any) -> AIModel:
    index = list(FREE_RIVAL_IDS).index(model_id) if model_id in FREE_RIVAL_IDS else 0
    provider = _PROVIDER_BY_ID.get(model_id, "openrouter")
    defaults: dict[str, Any] = {
        "provider": provider,
        "display_name": f"Rival {index + 1}",
        "openrouter_available": provider != "nvidia-nim",
        "openrouter_managed": provider != "nvidia-nim",
        "is_active": True,
        "model_type": "language",
        "tags": ["tools"],
        "sort_order": (index + 1) * 10,
    }
    defaults.update(overrides)
    rival, _ = AIModel.objects.get_or_create(model_id=model_id, defaults=defaults)
    return rival


def _create_run(
    *,
    instrument: str = "full-game",
    seat0_model_id: str | None = None,
    seat1_model_id: str | None = None,
    max_plies: int = 60,
) -> DiagnosticRun:
    seat0 = _make_rival(model_id=seat0_model_id or DEFAULT_FREE_MODEL_ID)
    seat1 = _make_rival(model_id=seat1_model_id or FREE_RIVAL_IDS[1])
    admin = User.objects.create_user(username=f"owner-{uuid_module.uuid4().hex[:8]}")
    created = create_diagnostic_game(
        variant_slug="english",
        seed=1234,
        seat0_model_id=seat0.model_id,
        seat1_model_id=seat1.model_id,
        prompt_id=None,
        created_by_id=admin.id,
        assist_mode="assisted",
    )
    run = DiagnosticRun.objects.get(pk=created["run_id"])
    return configure_diagnostic_run(
        run,
        instrument=instrument,
        position_set_digest=POSITION_SET_DIGEST if instrument == "position-set" else "",
        max_plies=max_plies,
        max_provider_requests=200,
        max_wall_clock_seconds=3600,
        extra_parameters={"django_origin": _CLOSED_ORIGIN},
    )


def _set_terminal(
    run: DiagnosticRun, *, status: str = "completed", end_reason: str = "position_set_exhausted"
) -> DiagnosticRun:
    run.status = status
    run.diagnostic_end_reason = end_reason
    run.ended_at = timezone.now()
    if status == "completed":
        run.score_authority = "engine"
    run.save()
    return run


def _add_ply(run: DiagnosticRun, index: int, model_id: str, **overrides: Any) -> DiagnosticPly:
    fields: dict[str, Any] = {
        "position_index": None,
        "seat_index": 0,
        "assist_mode": "assisted",
        "score_authority": "engine",
        "completion_source": None,
        "terminal_cause": None,
        "provider_requests_used": 1,
        "wall_clock_ms": 100,
        "executed_runtime_mode": "fake",
    }
    fields.update(overrides)
    return DiagnosticPly.objects.create(
        run=run, ply_index=index, model_id=model_id, **fields
    )


def _position_payload(run: DiagnosticRun, *, model_id: str, **overrides: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "n": 24,
        "runtime": "fake",
        "provider": "openrouter",
        "script": "generic_unchanged",
        "reason_code": "generic_unchanged_turn",
        "verdict": "fail",
        "score": None,
        "source_revision": "sourcerev001",
        "valid_candidate_count": None,
        "model_authored": None,
        "first_validate_valid": None,
        "give_up_while_legal": None,
        "malformed_or_non_tool": None,
        "model_legal_score": None,
        "ranked_best_score": None,
        "completion_source": None,
        "extra_counts": {},
    }
    options.update(overrides)
    n = int(options["n"])
    runtime = str(options["runtime"])
    samples: list[dict[str, Any]] = []
    for index in range(n):
        ply = {
            "seat_index": 0,
            "model_id": model_id,
            "assist_mode": "assisted",
            "score_authority": "engine",
            "model_authored": options["model_authored"],
            "first_validate_valid": options["first_validate_valid"],
            "valid_candidate_count": options["valid_candidate_count"],
            "model_legal_score": options["model_legal_score"],
            "ranked_best_score": options["ranked_best_score"],
            "ranked_search_complete": None,
            "give_up_while_legal": options["give_up_while_legal"],
            "playability_status": None,
            "completion_source": options["completion_source"],
            "terminal_cause": None,
            "provider_requests_used": 1,
            "steps_consumed": None,
            "wall_clock_ms": 7,
            "malformed_or_non_tool": options["malformed_or_non_tool"],
            "fallback_attempt_index": None,
            "earlier_attempt_failures": None,
            "executed_runtime_mode": runtime,
        }
        sample = {
            **ply,
            "position": {"set_digest": run.position_set_digest, "position_index": index},
            "score": options["score"],
            "verdict": options["verdict"],
            "reason_code": options["reason_code"],
        }
        if options["model_authored"] is True and options["ranked_best_score"]:
            sample["move_quality_ratio"] = (
                options["model_legal_score"] / options["ranked_best_score"]
            )
        samples.append(sample)
    ratios = [s["move_quality_ratio"] for s in samples if "move_quality_ratio" in s]
    counts: dict[str, int] = {source: 0 for source in COMPLETION_SOURCE_VOCABULARY}
    source = options["completion_source"]
    if isinstance(source, str):
        counts[source] = n
    counts.update(dict(options["extra_counts"]))
    summary: dict[str, Any] = {
        "sample_count": n,
        "pass_count": 0,
        "fail_count": n,
        "position_count": n,
        "unattempted_count": 0,
        "end_reason": "position_set_exhausted",
        "truncated": False,
        "move_quality_sample_count": len(ratios),
        "did_not_measure": n - len(ratios),
        "completion_source_counts": counts,
        "completion_source_did_not_measure_count": n if source is None else 0,
        "total_provider_requests": n,
    }
    if ratios:
        summary["move_quality_ratio"] = sum(ratios) / len(ratios)
    requested = {
        "run_id": str(run.id),
        "instrument": "position-set",
        "variant_slug": run.variant_slug,
        "assist_mode": "assisted",
        "executed_runtime_mode": runtime,
        "driver": "django-runner",
        "position_set_digest": run.position_set_digest,
        "provider": options["provider"],
        "model_id": model_id,
        "script": options["script"],
        "queue_mode": "selected-only",
        "max_plies": run.max_plies,
        "max_provider_requests": run.max_provider_requests,
        "max_wall_clock_seconds": run.max_wall_clock_seconds,
    }
    return {
        "artifact": ARTIFACT_ID,
        "report_kind": "model-position",
        "generated_at": "2026-09-01T00:00:00Z",
        "source_revision": options["source_revision"],
        "requested": requested,
        "variant": {
            "slug": run.variant_slug,
            "lexicon_id": "collins2019",
            "two_letter_lexicon_size": None,
        },
        "samples": samples,
        "summary": summary,
    }


class DiagnosticAdminS6Base(TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.admin = User.objects.create_superuser(
            username="s6-admin",
            email="s6-admin@example.com",
            password="s6-admin-pass",
        )
        self.client.force_login(self.admin)
        self.launch_url = reverse("admin:game_diagnosticrun_launch")
        self.compare_url = reverse("admin:game_diagnosticrun_compare")

    def change_url(self, run: DiagnosticRun) -> str:
        return reverse("admin:game_diagnosticrun_change", args=[run.id])

    def cancel_url(self, run: DiagnosticRun) -> str:
        return reverse("admin:game_diagnosticrun_cancel", args=[run.id])

    def _write_artifact(self, run: DiagnosticRun, payload: dict[str, Any]) -> None:
        directory = _var_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{run.id}-report.json"
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        run.report_path = str(path)
        run.save(update_fields=["report_path", "updated_at"])
        self.addCleanup(self._safe_unlink, path)

    @staticmethod
    def _safe_unlink(path: Path) -> None:
        try:
            path.unlink()
        except OSError:
            pass


class TestLaunchRedirectAndLivePage(DiagnosticAdminS6Base):
    def test_f01_launch_redirects_to_run_page_with_ply_progress(self) -> None:
        _make_rival()
        _make_rival(model_id=FREE_RIVAL_IDS[1])
        spawns: list[Any] = []
        with mock.patch.object(
            admin_module, "spawn_diagnostic_runner", side_effect=spawns.append
        ):
            response = self.client.post(
                self.launch_url,
                {
                    "instrument": "full-game",
                    "assist_mode": "assisted",
                    "variant_slug": "english",
                    "seat0_model_id": DEFAULT_FREE_MODEL_ID,
                    "seat1_model_id": FREE_RIVAL_IDS[1],
                    "seed": "4242",
                    "max_plies": "60",
                    "max_provider_requests": "200",
                    "max_wall_clock_seconds": "3600",
                    "position_set_digest": "",
                },
            )
        self.assertEqual(response.status_code, 302)
        run = DiagnosticRun.objects.order_by("-created_at").first()
        assert run is not None
        self.assertEqual(response["Location"], self.change_url(run))
        self.assertEqual(spawns, [run.id])

        _add_ply(run, 0, "ply-zero-model")
        _add_ply(run, 1, "ply-one-model")
        _add_ply(run, 2, "ply-two-model")
        page = self.client.get(self.change_url(run))
        self.assertEqual(page.status_code, 200)
        content = page.content.decode()
        self.assertIn(_LAUNCH_SUCCESS, content)
        self.assertIn("Recorded plies", content)
        self.assertIn(_PLY_CAPTION, content)
        self.assertIn("ply-two-model", content)
        self.assertIn("No heartbeat recorded", content)
        self.assertIn(_CADENCE_COPY, content)
        self.assertIn("zero-based", content)
        self.assertIn("max_plies cap 60", content)

    def test_f01_run_page_links_compare_and_hides_cancel_for_viewer(self) -> None:
        run = _set_terminal(_create_run())
        page = self.client.get(self.change_url(run))
        self.assertEqual(page.status_code, 200)
        content = page.content.decode()
        self.assertIn(self.compare_url, content)
        self.assertNotIn(self.cancel_url(run), content)


class TestInFlightRefreshAndQueryBudget(DiagnosticAdminS6Base):
    def test_f02_inflight_refresh_header_and_query_budget(self) -> None:
        run = _create_run(max_plies=60)
        run.status = "running"
        run.heartbeat_at = timezone.now()
        run.save()
        for index in range(25):
            _add_ply(run, index, f"ply-{index}-model")

        with CaptureQueriesContext(connection) as baseline:
            self.assertEqual(self.client.get(self.launch_url).status_code, 200)

        with CaptureQueriesContext(connection) as captured:
            response = self.client.get(self.change_url(run))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("Refresh"), "2")
        content = response.content.decode()
        self.assertIn(_PLY_CAPTION, content)
        self.assertIn("ply-24-model", content)
        self.assertNotIn("ply-4-model", content)
        self.assertIn(_NOT_MEASURED, content)

        # Documented subtraction: every query NOT touching the two diagnostic
        # tables is ordinary auth/session/admin chrome (session row, user row,
        # content types, admin app list, permission lookups). The chrome-only
        # baseline above is an authenticated GET of the launch form page, and
        # the run page may spend at most baseline + 2 total queries.
        ply_queries = [q for q in captured.captured_queries if "game_diagnostic_ply" in q["sql"]]
        run_queries = [q for q in captured.captured_queries if "game_diagnostic_run" in q["sql"]]
        self.assertEqual(len(run_queries), 1)
        self.assertEqual(len(ply_queries), 1)
        joined = " ".join(q["sql"] for q in captured.captured_queries)
        self.assertNotIn("game_session", joined)
        self.assertNotIn("catalog_aimodel", joined)
        self.assertLessEqual(len(captured.captured_queries), len(baseline.captured_queries) + 2)

    def test_f02_terminal_page_has_no_refresh(self) -> None:
        run = _set_terminal(_create_run(instrument="position-set"))
        response = self.client.get(self.change_url(run))
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.headers.get("Refresh"))
        self.assertIn(_AVAILABILITY_RACE, response.content.decode())


class TestFinishedReport(DiagnosticAdminS6Base):
    def _fake_completed_run(self, **payload_overrides: Any) -> DiagnosticRun:
        run = _create_run(instrument="position-set")
        _set_terminal(run)
        self._write_artifact(run, _position_payload(run, model_id=DEFAULT_FREE_MODEL_ID))
        return run

    def test_f03_fake_run_warning_copy(self) -> None:
        run = self._fake_completed_run()
        content = self.client.get(self.change_url(run)).content.decode()
        self.assertIn(_FAKE_WARNING_24, content)
        self.assertIn("Recorded diagnostic verdicts.", content)
        self.assertIn("pass: 0", content)
        self.assertIn("fail: 24", content)

    def test_f04_d3_and_ltai_presentation(self) -> None:
        run = self._fake_completed_run()
        content = self.client.get(self.change_url(run)).content.decode()
        for label in (
            "Tool-valid rate",
            "First-call-valid rate",
            "Give-up-when-legal rate",
            "Authorship rate",
            "Malformed rate",
            "Move-quality ratio",
        ):
            self.assertIn(label, content)
        self.assertIn("Insufficient sample (0/20).", content)
        self.assertIn("Not recorded.", content)
        self.assertIn("LTAI composite: not available in this report.", content)
        for key in (
            "position_count",
            "unattempted_count",
            "end_reason",
            "truncated",
            "move_quality_sample_count",
            "did_not_measure",
            "total_provider_requests",
        ):
            self.assertIn(key, content)
        order = [content.index(source) for source in COMPLETION_SOURCE_VOCABULARY]
        self.assertEqual(order, sorted(order))
        self.assertIn("Not measured (null source)", content)
        self.assertLess(
            content.index(COMPLETION_SOURCE_VOCABULARY[-1]),
            content.index("Not measured (null source)"),
        )
        self.assertEqual(content.count("<details>"), 24)
        self.assertIn("Position 0 — verdict fail (generic_unchanged_turn)", content)

    def test_f04_unknown_completion_source_is_escaped_text(self) -> None:
        run = _create_run(instrument="position-set")
        _set_terminal(run)
        payload = _position_payload(
            run,
            model_id=DEFAULT_FREE_MODEL_ID,
            extra_counts={"<script>alert(9)</script>": 5},
        )
        self._write_artifact(run, payload)
        content = self.client.get(self.change_url(run)).content.decode()
        self.assertIn("&lt;script&gt;alert(9)&lt;/script&gt;", content)
        self.assertIn("not vocabulary-clean", content)

    def test_f05_empty_report_paths(self) -> None:
        inflight = _create_run(instrument="position-set")
        inflight.status = "running"
        inflight.save()
        content = self.client.get(self.change_url(inflight)).content.decode()
        self.assertIn(_AVAILABILITY_EMPTY, content)

        finished = _set_terminal(inflight)
        page = self.client.get(self.change_url(finished))
        content = page.content.decode()
        self.assertIn(_AVAILABILITY_RACE, content)
        self.assertIsNone(page.headers.get("Refresh"))

    def test_f05_report_location_and_read_failures(self) -> None:
        run = _create_run(instrument="position-set")
        _set_terminal(run)
        run.report_path = "/tmp/libretiles-s6-not-the-report.json"
        run.save(update_fields=["report_path"])
        content = self.client.get(self.change_url(run)).content.decode()
        self.assertIn(_AVAILABILITY_MISMATCH, content)

        other = _create_run(instrument="position-set")
        _set_terminal(other)
        self._write_artifact(other, _position_payload(other, model_id=DEFAULT_FREE_MODEL_ID))
        marker_run = _create_run(instrument="position-set")
        _set_terminal(marker_run)
        marker_path = _var_dir() / f"{other.id}-report.json"
        run.report_path = str(marker_path)
        run.save(update_fields=["report_path"])
        content = self.client.get(self.change_url(run)).content.decode()
        self.assertIn(_AVAILABILITY_MISMATCH, content)
        self.assertNotIn("generic_unchanged test path", content)

        malformed = _create_run(instrument="position-set")
        _set_terminal(malformed)
        self._write_artifact(malformed, _position_payload(malformed, model_id=DEFAULT_FREE_MODEL_ID))
        path = _var_dir() / f"{malformed.id}-report.json"
        path.write_text("{not json at all", encoding="utf-8")
        content = self.client.get(self.change_url(malformed)).content.decode()
        self.assertIn(_AVAILABILITY_MALFORMED, content)


class TestXssSafety(DiagnosticAdminS6Base):
    def test_f06_xss_strings_remain_text(self) -> None:
        payload_model = "<script>alert(1)</script>"
        run = _create_run(instrument="position-set")
        run.seat0_model_id = payload_model
        run.seat1_model_id = payload_model
        run.save(update_fields=["seat0_model_id", "seat1_model_id", "updated_at"])
        _add_ply(
            run,
            0,
            payload_model,
            terminal_cause="<img src=x onerror=alert(2)>",
            completion_source="<b>x</b>",
        )
        _set_terminal(run, end_reason="<script>er</script>")
        payload = _position_payload(run, model_id=payload_model)
        payload["summary"]["completion_source_counts"]["<script>alert(9)</script>"] = 5
        self._write_artifact(run, payload)

        page = self.client.get(self.change_url(run))
        self.assertEqual(page.status_code, 200)
        content = page.content.decode()
        self.assertIn("Recorded plies", content)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", content)
        self.assertNotIn("<script>alert(1)</script>", content)
        self.assertNotIn("<img src=x onerror=alert(2)>", content)
        self.assertIn("&lt;b&gt;x&lt;/b&gt;", content)
        self.assertIn("&lt;script&gt;alert(9)&lt;/script&gt;", content)

        compare = self.client.get(self.compare_url)
        self.assertEqual(compare.status_code, 200)
        compare_content = compare.content.decode()
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", compare_content)
        self.assertNotIn("<script>alert(1)</script>", compare_content)


class TestConfinedReaderS6(TestCase):
    """F07: the reader refuses every unsafe shape without opening it."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.base = Path(self._tmp.name)
        self.directory = self.base / "diagnostics"
        self.directory.mkdir()
        self.run_id = uuid_module.uuid4()

    def _reader(self) -> Any:
        from game.diagnostic_admin_reports import read_diagnostic_report

        return read_diagnostic_report

    def _canonical(self) -> Path:
        return self.directory / f"{self.run_id}-report.json"

    def _valid_payload(self) -> dict[str, Any]:
        return {
            "artifact": ARTIFACT_ID,
            "report_kind": "model-position",
            "requested": {"run_id": str(self.run_id)},
            "summary": {"sample_count": 0},
            "samples": [],
        }

    def _read(self, report_path: str) -> Any:
        return self._reader()(self.run_id, report_path, directory=self.directory)

    def test_reads_valid_artifact(self) -> None:
        self._canonical().write_text(json.dumps(self._valid_payload()), encoding="utf-8")
        result = self._read(str(self._canonical()))
        self.assertIsNone(result.failure)
        assert result.payload is not None
        self.assertEqual(result.payload["requested"]["run_id"], str(self.run_id))

    def test_refuses_stored_path_mismatch_and_traversal(self) -> None:
        self._canonical().write_text(json.dumps(self._valid_payload()), encoding="utf-8")
        for bogus in (
            str(self.base / "other.json"),
            "/etc/passwd",
            "../escape.json",
            str(self.directory / f"../{self.run_id}-report.json"),
        ):
            result = self._read(bogus)
            self.assertEqual(result.failure, "path_mismatch", bogus)
            self.assertIsNone(result.payload)

    def test_refuses_other_run_filename(self) -> None:
        other = self.directory / f"{uuid_module.uuid4()}-report.json"
        other.write_text(json.dumps(self._valid_payload()), encoding="utf-8")
        result = self._read(str(other))
        self.assertEqual(result.failure, "path_mismatch")

    def test_refuses_symlink_file(self) -> None:
        real = self.directory / "real-report.json"
        real.write_text(json.dumps(self._valid_payload()), encoding="utf-8")
        os.symlink(real, self._canonical())
        result = self._read(str(self._canonical()))
        self.assertEqual(result.failure, "unsafe")

    def test_refuses_symlink_directory(self) -> None:
        real_dir = self.base / "real-diagnostics"
        real_dir.mkdir()
        self.directory.rmdir()
        os.symlink(real_dir, self.directory)
        (real_dir / f"{self.run_id}-report.json").write_text(
            json.dumps(self._valid_payload()), encoding="utf-8"
        )
        result = self._read(str(self._canonical()))
        self.assertEqual(result.failure, "unsafe")

    def test_refuses_fifo(self) -> None:
        os.mkfifo(self._canonical())
        result = self._read(str(self._canonical()))
        self.assertEqual(result.failure, "unsafe")

    def test_refuses_directory_named_report(self) -> None:
        self._canonical().mkdir()
        result = self._read(str(self._canonical()))
        self.assertEqual(result.failure, "unsafe")

    def test_refuses_oversize(self) -> None:
        self._canonical().write_bytes(b"x" * (2 * 1024 * 1024 + 1))
        result = self._read(str(self._canonical()))
        self.assertEqual(result.failure, "oversize")

    def test_refuses_malformed_json(self) -> None:
        self._canonical().write_text("{not json at all", encoding="utf-8")
        self.assertEqual(self._read(str(self._canonical())).failure, "malformed")

    def test_refuses_duplicate_keys(self) -> None:
        self._canonical().write_text(
            '{"requested": {"run_id": "x"}, "summary": {"a": 1, "a": 2}}', encoding="utf-8"
        )
        self.assertEqual(self._read(str(self._canonical())).failure, "malformed")

    def test_refuses_nan_constant(self) -> None:
        self._canonical().write_text('{"summary": {"x": NaN}}', encoding="utf-8")
        self.assertEqual(self._read(str(self._canonical())).failure, "malformed")

    def test_refuses_identity_mismatch(self) -> None:
        payload = self._valid_payload()
        payload["requested"]["run_id"] = str(uuid_module.uuid4())
        self._canonical().write_text(json.dumps(payload), encoding="utf-8")
        self.assertEqual(self._read(str(self._canonical())).failure, "identity")

    def test_refuses_missing_file_and_directory(self) -> None:
        self.assertEqual(self._read(str(self._canonical())).failure, "missing")
        absent = self.base / "absent" / "diagnostics"
        result = self._reader()(
            self.run_id, str(absent / f"{self.run_id}-report.json"), directory=absent
        )
        self.assertEqual(result.failure, "missing")

    def test_refuses_without_nofollow_support(self) -> None:
        self._canonical().write_text(json.dumps(self._valid_payload()), encoding="utf-8")
        with mock.patch.object(os, "O_NOFOLLOW", None):
            self.assertEqual(self._read(str(self._canonical())).failure, "unsupported")
        with mock.patch.object(os, "O_DIRECTORY", None):
            self.assertEqual(self._read(str(self._canonical())).failure, "unsupported")

    def test_empty_path_is_reported(self) -> None:
        self.assertEqual(self._read("").failure, "empty_path")


class TestDiagnosticAdminPermissionsS6(TestCase):
    def setUp(self) -> None:
        self.superuser = User.objects.create_superuser(
            username="s6-perm-admin",
            email="s6-perm-admin@example.com",
            password="s6-perm-admin-pass",
        )
        self.staff_none = User.objects.create_user(username="s6-staff-none")
        self.staff_none.is_staff = True
        self.staff_none.save()
        self.staff_view = User.objects.create_user(username="s6-staff-view")
        self.staff_view.is_staff = True
        self.staff_view.save()
        self.staff_view.user_permissions.add(
            Permission.objects.get(content_type__app_label="game", codename="view_diagnosticrun")
        )
        self.staff_change = User.objects.create_user(username="s6-staff-change")
        self.staff_change.is_staff = True
        self.staff_change.save()
        self.staff_change.user_permissions.add(
            Permission.objects.get(content_type__app_label="game", codename="view_diagnosticrun")
        )
        self.staff_change.user_permissions.add(
            Permission.objects.get(content_type__app_label="game", codename="change_diagnosticrun")
        )
        self.run = _create_run()
        self.run.status = "running"
        self.run.save()
        self.change_url = reverse("admin:game_diagnosticrun_change", args=[self.run.id])
        self.cancel_url = reverse("admin:game_diagnosticrun_cancel", args=[self.run.id])

    def test_f08_anonymous_and_nonstaff_cannot_see_run_page(self) -> None:
        response = Client().get(self.change_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response["Location"])
        nonstaff = User.objects.create_user(username="s6-plain-user")
        client = Client()
        client.force_login(nonstaff)
        response = client.get(self.change_url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response["Location"])

    def test_f08_staff_without_view_permission_denied(self) -> None:
        client = Client()
        client.force_login(self.staff_none)
        response = client.get(self.change_url)
        self.assertEqual(response.status_code, 403)

    def test_f08_view_only_staff_gets_page_without_cancel(self) -> None:
        client = Client()
        client.force_login(self.staff_view)
        response = client.get(self.change_url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(self.cancel_url, response.content.decode())

    def test_f08_cancel_requires_change_permission_and_csrf(self) -> None:
        client = Client()
        client.force_login(self.staff_view)
        self.assertEqual(client.post(self.cancel_url).status_code, 403)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "running")

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.staff_change)
        self.assertEqual(csrf_client.post(self.cancel_url).status_code, 403)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "running")

        client.force_login(self.staff_change)
        response = client.post(self.cancel_url)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], self.change_url)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "cancelled")

    def test_f08_get_on_cancel_url_is_405(self) -> None:
        client = Client()
        client.force_login(self.staff_change)
        response = client.get(self.cancel_url)
        self.assertEqual(response.status_code, 405)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "running")


class TestComparisonS6(DiagnosticAdminS6Base):
    def _finished_position_run(self, *, model_id: str, **payload_overrides: Any) -> DiagnosticRun:
        run = _create_run(instrument="position-set", seat0_model_id=model_id, seat1_model_id=model_id)
        _set_terminal(run)
        self._write_artifact(run, _position_payload(run, model_id=model_id, **payload_overrides))
        return run

    def _live_ready_run(self, model_id: str) -> DiagnosticRun:
        run = _create_run(instrument="position-set", seat0_model_id=model_id, seat1_model_id=model_id)
        run.executed_runtime_mode = "live"
        run.prompt = AIPrompt.objects.create(
            name=f"s6-live-prompt-{uuid_module.uuid4().hex[:8]}", prompt="prompt text"
        )
        _set_terminal(run)
        self._write_artifact(
            run,
            _position_payload(
                run,
                model_id=model_id,
                n=20,
                runtime="live",
                valid_candidate_count=2,
                model_authored=True,
                first_validate_valid=True,
                give_up_while_legal=False,
                malformed_or_non_tool=False,
                model_legal_score=8,
                ranked_best_score=10,
                completion_source="provider_candidate",
            ),
        )
        return run

    def test_f09_comparison_does_not_pool_fake_live_or_mixed(self) -> None:
        fake = self._finished_position_run(model_id=DEFAULT_FREE_MODEL_ID)
        live = self._live_ready_run(DEFAULT_FREE_MODEL_ID)
        mixed = self._live_ready_run(DEFAULT_FREE_MODEL_ID)
        mixed_payload = _position_payload(
            mixed,
            model_id=DEFAULT_FREE_MODEL_ID,
            n=20,
            runtime="live",
            valid_candidate_count=2,
            model_authored=True,
            first_validate_valid=True,
            give_up_while_legal=False,
            malformed_or_non_tool=False,
            model_legal_score=8,
            ranked_best_score=10,
            completion_source="provider_candidate",
        )
        for index in range(10, 20):
            mixed_payload["samples"][index]["executed_runtime_mode"] = "fake"
        self._write_artifact(mixed, mixed_payload)

        content = self.client.get(self.compare_url).content.decode()
        self.assertIn(fake.id.hex[:8], content)
        self.assertIn(_REASON_RUNTIME, content)
        self.assertIn(live.id.hex[:8], content)
        self.assertIn(mixed.id.hex[:8], content)
        self.assertIn(_REASON_RUNTIME_SAMPLES, content)
        self.assertIn("move_quality mean 0.800", content)
        self.assertNotIn(_POOL_EMPTY, content)

    def test_f09_fake_only_page_has_no_pool(self) -> None:
        first = self._finished_position_run(model_id=DEFAULT_FREE_MODEL_ID)
        second = self._finished_position_run(model_id=DEFAULT_FREE_MODEL_ID)
        content = self.client.get(self.compare_url).content.decode()
        self.assertIn(first.id.hex[:8], content)
        self.assertIn(second.id.hex[:8], content)
        self.assertEqual(content.count(_REASON_RUNTIME), 2)
        self.assertIn(_POOL_EMPTY, content)
        self.assertNotIn("diag-compare-model", content)
        self.assertIn(_COMPARE_NOTE_PAGE, content)
        self.assertIn(_COMPARE_NOTE_PROMPT, content)

    def test_f09_mixed_seats_attributed_to_neither(self) -> None:
        run = _create_run(instrument="position-set")
        _set_terminal(run)
        content = self.client.get(self.compare_url).content.decode()
        self.assertIn(run.seat0_model_id, content)
        self.assertIn(run.seat1_model_id, content)
        self.assertIn(_REASON_MIXED_SEATS, content)

    def test_f09_full_game_runs_not_listed(self) -> None:
        run = _set_terminal(_create_run(instrument="full-game"))
        content = self.client.get(self.compare_url).content.decode()
        self.assertNotIn(run.id.hex[:8], content)

    def test_f09_digest_filter_is_exact_and_lenient(self) -> None:
        matching = self._finished_position_run(model_id=DEFAULT_FREE_MODEL_ID)
        other = self._finished_position_run(model_id=FREE_RIVAL_IDS[1])
        other.position_set_digest = "b" * 64
        other.save(update_fields=["position_set_digest", "updated_at"])

        content = self.client.get(self.compare_url, {"digest": POSITION_SET_DIGEST}).content.decode()
        self.assertIn(matching.id.hex[:8], content)
        self.assertNotIn(other.id.hex[:8], content)

        invalid = self.client.get(self.compare_url, {"digest": "zz"}).content.decode()
        self.assertIn(matching.id.hex[:8], invalid)
        self.assertIn(other.id.hex[:8], invalid)

        empty = self.client.get(self.compare_url, {"digest": "c" * 64}).content.decode()
        self.assertIn(_NO_RUNS, empty)


class TestGetIsInertS6(DiagnosticAdminS6Base):
    def test_f10_get_does_not_spawn_mint_or_mutate(self) -> None:
        run = _create_run(instrument="position-set")
        _add_ply(run, 0, DEFAULT_FREE_MODEL_ID)
        _set_terminal(run)
        self._write_artifact(run, _position_payload(run, model_id=DEFAULT_FREE_MODEL_ID))
        artifact_path = _var_dir() / f"{run.id}-report.json"
        before_bytes = artifact_path.read_bytes()
        before_listing = sorted(p.name for p in _var_dir().iterdir())
        before_plies = DiagnosticPly.objects.filter(run=run).count()
        before_runs = DiagnosticRun.objects.count()

        def _fail(*args: Any, **kwargs: Any) -> None:
            raise AssertionError("GET must not mint tokens")

        with (
            mock.patch.object(admin_module, "spawn_diagnostic_runner", side_effect=_fail),
            mock.patch("game.services.mint_diagnostic_access_token", side_effect=_fail),
            mock.patch.object(admin_module, "cancel_diagnostic_run", side_effect=_fail),
            mock.patch("game.diagnostics.write_report_atomically", side_effect=_fail),
        ):
            change = self.client.get(self.change_url(run))
            compare = self.client.get(self.compare_url)
        self.assertEqual(change.status_code, 200)
        self.assertEqual(compare.status_code, 200)
        self.assertIn("Recorded plies", change.content.decode())
        self.assertIn(run.id.hex[:8], compare.content.decode())

        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertEqual(DiagnosticPly.objects.filter(run=run).count(), before_plies)
        self.assertEqual(artifact_path.read_bytes(), before_bytes)
        self.assertEqual(sorted(p.name for p in _var_dir().iterdir()), before_listing)
        self.assertEqual(DiagnosticRun.objects.count(), before_runs)


# ---------------------------------------------------------------------------
# S7 diagnostic targets: add-host surface, target admin, launch form (F03/F11)
# ---------------------------------------------------------------------------

from django.contrib.admin.models import LogEntry  # noqa: E402
from game import diagnostic_targets as diagnostic_targets_module  # noqa: E402
from game import services  # noqa: E402
from game.models import DiagnosticAllowedHost, DiagnosticTarget  # noqa: E402

PUBLIC_ADDRESS = "8.8.8.8"


def _patch_target_dns(addresses: list[str]) -> Any:
    return mock.patch.object(
        diagnostic_targets_module, "resolve_host_addresses", mock.MagicMock(return_value=addresses)
    )


class DiagnosticTargetAdminS7Base(TestCase):
    def setUp(self) -> None:
        self.superuser = User.objects.create_superuser(
            username="s7-admin",
            email="s7-admin@example.com",
            password="s7-admin-pass",
        )
        self.client.force_login(self.superuser)
        self.host_add_url = reverse("admin:game_diagnosticallowedhost_add")
        self.host_changelist_url = reverse("admin:game_diagnosticallowedhost_changelist")
        self.target_add_url = reverse("admin:game_diagnostictarget_add")
        self.target_changelist_url = reverse("admin:game_diagnostictarget_changelist")
        self.launch_url = reverse("admin:game_diagnosticrun_launch")


class DiagnosticAllowedHostAddSurfaceTests(DiagnosticTargetAdminS7Base):
    def test_f03_get_add_form_is_form_only(self) -> None:
        with mock.patch.object(
            diagnostic_targets_module,
            "resolve_host_addresses",
            side_effect=AssertionError("add-host must not resolve DNS"),
        ):
            response = self.client.get(self.host_add_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("hostname", response.content.decode())

    def test_f03_post_adds_host_without_dns_or_http(self) -> None:
        with mock.patch.object(
            diagnostic_targets_module,
            "resolve_host_addresses",
            side_effect=AssertionError("add-host must not resolve DNS"),
        ):
            response = self.client.post(
                self.host_add_url,
                {"hostname": "rival.example.com", "is_active": "on"},
            )
        self.assertEqual(response.status_code, 302)
        host = DiagnosticAllowedHost.objects.filter(hostname="rival.example.com").first()
        self.assertIsNotNone(host)
        entry = LogEntry.objects.filter(
            object_id=str(host.pk), action_flag=1  # ADDITION
        ).first()
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertEqual(entry.user_id, self.superuser.id)
        self.assertIn("hostname", entry.change_message.lower())

    def test_f03_post_rejects_noncanonical_hostname(self) -> None:
        for bad in ("Rival.Example.Com", "rival.example.com.", "-bad.example.com"):
            with self.subTest(hostname=bad):
                response = self.client.post(
                    self.host_add_url, {"hostname": bad, "is_active": "on"}
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    DiagnosticAllowedHost.objects.filter(
                        hostname__iexact=bad.lower()
                    ).count(),
                    0,
                )

    def test_f03_staff_without_add_and_change_perms_cannot_add(self) -> None:
        staffer = User.objects.create_user(
            username="s7-staffer", password="s7-staffer-pass", is_staff=True
        )
        add_permission = Permission.objects.get(
            content_type__app_label="game", codename="add_diagnosticallowedhost"
        )
        change_permission = Permission.objects.get(
            content_type__app_label="game", codename="change_diagnosticallowedhost"
        )
        delete_permission = Permission.objects.get(
            content_type__app_label="game", codename="delete_diagnosticallowedhost"
        )
        view_permission = Permission.objects.get(
            content_type__app_label="game", codename="view_diagnosticallowedhost"
        )
        staffer.user_permissions.add(add_permission, delete_permission, view_permission)
        self.client.force_login(staffer)
        response = self.client.post(
            self.host_add_url, {"hostname": "rival.example.com", "is_active": "on"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            DiagnosticAllowedHost.objects.filter(hostname="rival.example.com").count(), 0
        )

        staffer.user_permissions.add(change_permission)
        response = self.client.post(
            self.host_add_url, {"hostname": "rival.example.com", "is_active": "on"}
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            DiagnosticAllowedHost.objects.filter(hostname="rival.example.com").count(), 1
        )

    def test_f03_csrf_is_required_for_add(self) -> None:
        enforcing = Client(enforce_csrf_checks=True)
        enforcing.force_login(self.superuser)
        response = enforcing.post(
            self.host_add_url, {"hostname": "rival.example.com", "is_active": "on"}
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(
            DiagnosticAllowedHost.objects.filter(hostname="rival.example.com").count(), 0
        )

    def test_f11_deactivate_action_logs_field_names_only(self) -> None:
        host = DiagnosticAllowedHost.objects.create(hostname="rival.example.com")
        response = self.client.post(
            self.host_changelist_url,
            {
                "action": "deactivate_selected_hosts",
                "_selected_action": [str(host.pk)],
            },
        )
        self.assertEqual(response.status_code, 302)
        host.refresh_from_db()
        self.assertFalse(host.is_active)
        entry = LogEntry.objects.filter(object_id=str(host.pk)).order_by("-id").first()
        self.assertIsNotNone(entry)
        assert entry is not None
        self.assertIn("is_active", entry.change_message)
        self.assertNotIn("https://", entry.change_message)


class DiagnosticTargetAdminSurfaceTests(DiagnosticTargetAdminS7Base):
    def _host(self) -> DiagnosticAllowedHost:
        return DiagnosticAllowedHost.objects.create(hostname="rival.example.com")

    def test_f02_add_target_success_and_loopback_refusal(self) -> None:
        host = self._host()
        with _patch_target_dns([PUBLIC_ADDRESS]):
            response = self.client.post(
                self.target_add_url,
                {
                    "name": "Rival target",
                    "base_url": f"https://{host.hostname}/api/v1",
                    "allowed_host": str(host.pk),
                    "model_id": "vendor/target-model",
                    "credential_env_name": "OPENROUTER_API_KEY",
                    "is_active": "on",
                },
            )
        self.assertEqual(response.status_code, 302)
        target = DiagnosticTarget.objects.filter(name="Rival target").first()
        self.assertIsNotNone(target)

        before = DiagnosticTarget.objects.count()
        with _patch_target_dns(["127.0.0.1"]):
            response = self.client.post(
                self.target_add_url,
                {
                    "name": "Loopback target",
                    "base_url": "https://metadata.invalid/api/v1",
                    "allowed_host": str(host.pk),
                    "model_id": "vendor/target-model",
                    "credential_env_name": "OPENROUTER_API_KEY",
                    "is_active": "on",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn("refused", response.content.decode().lower())
        self.assertEqual(DiagnosticTarget.objects.count(), before)
        self.assertFalse(
            LogEntry.objects.filter(
                object_repr__contains="Loopback target", action_flag=1
            ).exists()
        )

    def test_f04_credential_env_name_closed_choices(self) -> None:
        host = self._host()
        with _patch_target_dns([PUBLIC_ADDRESS]):
            response = self.client.post(
                self.target_add_url,
                {
                    "name": "Secret thief",
                    "base_url": f"https://{host.hostname}/api/v1",
                    "allowed_host": str(host.pk),
                    "model_id": "vendor/target-model",
                    "credential_env_name": "DJANGO_SECRET_KEY",
                    "is_active": "on",
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            DiagnosticTarget.objects.filter(credential_env_name="DJANGO_SECRET_KEY").count(),
            0,
        )

    def test_f11_credential_presence_is_never_a_value(self) -> None:
        host = self._host()
        with _patch_target_dns([PUBLIC_ADDRESS]):
            self.client.post(
                self.target_add_url,
                {
                    "name": "Presence probe",
                    "base_url": f"https://{host.hostname}/api/v1",
                    "allowed_host": str(host.pk),
                    "model_id": "vendor/target-model",
                    "credential_env_name": "OPENROUTER_API_KEY",
                    "is_active": "on",
                },
            )
        response = self.client.get(self.target_changelist_url)
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        self.assertIn("credential present", page.lower())
        self.assertIn("openrouter_api_key", page.lower())
        self.assertNotIn("your-openrouter-api-key", page.lower())

    def test_f11_frozen_target_refuses_edit_via_admin(self) -> None:
        host = self._host()
        with _patch_target_dns([PUBLIC_ADDRESS]):
            self.client.post(
                self.target_add_url,
                {
                    "name": "Freeze me",
                    "base_url": f"https://{host.hostname}/api/v1",
                    "allowed_host": str(host.pk),
                    "model_id": "vendor/target-model",
                    "credential_env_name": "OPENROUTER_API_KEY",
                    "is_active": "on",
                },
            )
        target = DiagnosticTarget.objects.get(name="Freeze me")
        admin = services.ensure_diagnostic_service_user()
        services.create_diagnostic_game(
            variant_slug="english",
            seed=1,
            seat0_model_id="vendor/target-model",
            seat1_model_id="vendor/target-model",
            prompt_id=None,
            created_by_id=admin.id,
            assist_mode="assisted",
            seat0_target_id=str(target.id),
            seat1_target_id=str(target.id),
        )
        with _patch_target_dns([PUBLIC_ADDRESS]):
            response = self.client.post(
                reverse("admin:game_diagnostictarget_change", args=[target.pk]),
                {
                    "name": "Freeze me",
                    "base_url": f"https://{host.hostname}/api/v2",
                    "allowed_host": str(host.pk),
                    "model_id": "vendor/target-model",
                    "credential_env_name": "OPENROUTER_API_KEY",
                    "is_active": "on",
                },
            )
        self.assertEqual(response.status_code, 200)
        target.refresh_from_db()
        self.assertEqual(target.base_url, f"https://{host.hostname}/api/v1")


class DiagnosticBulkActionPermissionS7Tests(DiagnosticTargetAdminS7Base):
    """F02: view-only staff must not run activation/deactivation actions."""

    def _view_only_client(self, model_name: str) -> Client:
        staffer = User.objects.create_user(
            username=f"s7-viewer-{uuid_module.uuid4().hex[:8]}",
            password="s7-viewer-pass",
            is_staff=True,
        )
        staffer.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="game",
                codename=f"view_{model_name}",
            )
        )
        client = Client()
        client.force_login(staffer)
        return client

    @staticmethod
    def _post_action(client: Client, changelist: str, action: str, pk: Any) -> Any:
        return client.post(changelist, {"action": action, "_selected_action": [str(pk)]})

    def test_f02_view_only_staff_cannot_activate_or_deactivate_hosts(self) -> None:
        active = DiagnosticAllowedHost.objects.create(hostname="active.example.com")
        inactive = DiagnosticAllowedHost.objects.create(
            hostname="inactive.example.com", is_active=False
        )
        client = self._view_only_client("diagnosticallowedhost")

        self._post_action(
            client, self.host_changelist_url, "deactivate_selected_hosts", active.pk
        )
        active.refresh_from_db()
        self.assertTrue(active.is_active)

        self._post_action(
            client, self.host_changelist_url, "activate_selected_hosts", inactive.pk
        )
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)

    def test_f02_view_only_staff_cannot_activate_or_deactivate_targets(self) -> None:
        host = DiagnosticAllowedHost.objects.create(hostname="rival.example.com")
        with _patch_target_dns([PUBLIC_ADDRESS]):
            active = DiagnosticTarget.objects.create(
                name="Active target",
                base_url=f"https://{host.hostname}/api/v1",
                allowed_host=host,
                model_id="vendor/target-model",
                credential_env_name="OPENROUTER_API_KEY",
            )
            inactive = DiagnosticTarget.objects.create(
                name="Inactive target",
                base_url=f"https://{host.hostname}/api/v1",
                allowed_host=host,
                model_id="vendor/target-model",
                credential_env_name="OPENROUTER_API_KEY",
                is_active=False,
            )
        client = self._view_only_client("diagnostictarget")

        self._post_action(
            client, self.target_changelist_url, "deactivate_selected_targets", active.pk
        )
        active.refresh_from_db()
        self.assertTrue(active.is_active)

        self._post_action(
            client, self.target_changelist_url, "activate_selected_targets", inactive.pk
        )
        inactive.refresh_from_db()
        self.assertFalse(inactive.is_active)


class DiagnosticLaunchTargetTests(DiagnosticTargetAdminS7Base):
    def setUp(self) -> None:
        super().setUp()
        self.seat0 = _make_rival()
        self.seat1 = _make_rival(model_id=FREE_RIVAL_IDS[1])
        self.host = DiagnosticAllowedHost.objects.create(hostname="rival.example.com")
        self.spawns: list[Any] = []
        self._original_spawn = admin_module.spawn_diagnostic_runner

        def _capture_spawn(run_id: Any) -> None:
            self.spawns.append(run_id)

        admin_module.spawn_diagnostic_runner = _capture_spawn
        self.addCleanup(self._restore_spawn)

    def _restore_spawn(self) -> None:
        admin_module.spawn_diagnostic_runner = self._original_spawn

    def _target(self, name: str) -> DiagnosticTarget:
        with _patch_target_dns([PUBLIC_ADDRESS]):
            return DiagnosticTarget.objects.create(
                name=name,
                base_url=f"https://{self.host.hostname}/api/v1",
                allowed_host=self.host,
                model_id="vendor/target-model",
                credential_env_name="OPENROUTER_API_KEY",
            )

    def _post(self, **overrides: Any) -> Any:
        payload: dict[str, Any] = {
            "instrument": "full-game",
            "assist_mode": "assisted",
            "variant_slug": "english",
            "seat0_model_id": self.seat0.model_id,
            "seat1_model_id": self.seat1.model_id,
            "seat0_target": "",
            "seat1_target": "",
            "prompt_id": "",
            "seed": "42",
            "position_set_digest": "",
            "max_plies": "2",
            "max_provider_requests": "5",
            "max_wall_clock_seconds": "60",
        }
        payload.update(overrides)
        with _patch_target_dns([PUBLIC_ADDRESS]):
            return self.client.post(self.launch_url, payload)

    def test_f05_launch_form_lists_active_targets(self) -> None:
        target = self._target("Shown target")
        response = self.client.get(self.launch_url)
        self.assertEqual(response.status_code, 200)
        page = response.content.decode()
        self.assertIn(str(target.id), page)
        self.assertIn("Shown target", page)

    def test_f05_full_game_seat0_target_creates_target_seat(self) -> None:
        target = self._target("Seat0 target")
        response = self._post(
            seat0_model_id="",
            seat0_target=str(target.id),
            seat1_model_id=self.seat1.model_id,
        )
        self.assertEqual(response.status_code, 302)
        run = DiagnosticRun.objects.get(pk=self.spawns[-1])
        slot0 = run.session.slots.get(slot=0)
        slot1 = run.session.slots.get(slot=1)
        self.assertIsNone(slot0.ai_model)
        self.assertEqual(slot0.diagnostic_target_id, target.id)
        self.assertEqual(slot1.ai_model_id, self.seat1.id)
        self.assertIsNone(slot1.diagnostic_target)
        self.assertEqual(run.seat0_model_id, "vendor/target-model")
        self.assertEqual(run.seat1_model_id, self.seat1.model_id)
        self.assertEqual(run.parameters_json.get("seat0_target_id"), str(target.id))

    def test_f05_seat_with_both_choices_is_refused(self) -> None:
        target = self._target("Ambiguous")
        response = self._post(seat0_target=str(target.id))
        self.assertEqual(response.status_code, 200)
        self.assertIn("exactly one", response.content.decode().lower())
        self.assertEqual(DiagnosticRun.objects.count(), 0)

    def test_f05_position_set_requires_same_target_both_seats(self) -> None:
        target = self._target("Pair target")
        other = self._target("Other target")
        response = self._post(
            instrument="position-set",
            position_set_digest=POSITION_SET_DIGEST,
            seat0_model_id="",
            seat1_model_id="",
            seat0_target=str(target.id),
            seat1_target=str(other.id),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("same", response.content.decode().lower())
        self.assertEqual(DiagnosticRun.objects.count(), 0)

        response = self._post(
            instrument="position-set",
            position_set_digest=POSITION_SET_DIGEST,
            seat0_model_id="",
            seat1_model_id="",
            seat0_target=str(target.id),
            seat1_target=str(target.id),
        )
        self.assertEqual(response.status_code, 302)
        run = DiagnosticRun.objects.get(pk=self.spawns[-1])
        self.assertEqual(
            run.session.slots.get(slot=0).diagnostic_target_id, target.id
        )
        self.assertEqual(
            run.session.slots.get(slot=1).diagnostic_target_id, target.id
        )
