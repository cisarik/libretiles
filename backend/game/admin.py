import os
import random
import re
import subprocess
import sys
import uuid as uuid_module
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import EmptyPage, Paginator
from django.db import IntegrityError
from django.db.models import Count, QuerySet
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils import timezone

from accounts.models import User
from .diagnostic_admin_reports import (
    AVAILABILITY_COPY,
    AVAILABILITY_EMPTY,
    ReportReadResult,
    comparison_metrics_summary,
    floor_violations,
    present_report,
    read_diagnostic_report,
)
from .diagnostics import COMPLETION_SOURCE_VOCABULARY
from .models import ChatMessage, DiagnosticRun, GameSession, Move, PlayerSlot
from .services import (
    DIAGNOSTIC_MAX_PLIES_ADMIN_MAX,
    DIAGNOSTIC_MAX_PLIES_DEFAULT,
    DIAGNOSTIC_MAX_PROVIDER_REQUESTS_ADMIN_MAX,
    DIAGNOSTIC_MAX_PROVIDER_REQUESTS_DEFAULT,
    DIAGNOSTIC_MAX_WALL_CLOCK_SECONDS_ADMIN_MAX,
    DIAGNOSTIC_MAX_WALL_CLOCK_SECONDS_DEFAULT,
    DiagnosticSessionError,
    abandon_stale_diagnostic_runs,
    abort_diagnostic_run,
    cancel_diagnostic_run,
    configure_diagnostic_run,
    create_diagnostic_game,
)

if TYPE_CHECKING:
    _PlayerSlotInline = admin.TabularInline[PlayerSlot, GameSession]
    _MoveInline = admin.TabularInline[Move, GameSession]
    _GameSessionAdmin = admin.ModelAdmin[GameSession]
    _MoveAdmin = admin.ModelAdmin[Move]
    _ChatMessageAdmin = admin.ModelAdmin[ChatMessage]
    _DiagnosticRunAdmin = admin.ModelAdmin[DiagnosticRun]
else:
    _PlayerSlotInline = admin.TabularInline
    _MoveInline = admin.TabularInline
    _GameSessionAdmin = admin.ModelAdmin
    _MoveAdmin = admin.ModelAdmin
    _ChatMessageAdmin = admin.ModelAdmin
    _DiagnosticRunAdmin = admin.ModelAdmin

def _extract_usage(ai_metadata: Any) -> dict[str, int]:
    if not isinstance(ai_metadata, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    usage = ai_metadata.get("usage")
    if not isinstance(usage, dict):
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}

    nested_input = usage.get("inputTokens")
    nested_output = usage.get("outputTokens")

    input_tokens = (
        int(nested_input.get("total") or 0)
        if isinstance(nested_input, dict)
        else int(usage.get("inputTokens") or 0)
    )
    output_tokens = (
        int(nested_output.get("total") or 0)
        if isinstance(nested_output, dict)
        else int(usage.get("outputTokens") or 0)
    )
    total_tokens = int(usage.get("totalTokens") or (input_tokens + output_tokens))

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _resolve_model_id(move: Move) -> str:
    ai_metadata = move.ai_metadata if isinstance(move.ai_metadata, dict) else {}
    return (
        ai_metadata.get("response_model")
        or ai_metadata.get("model")
        or ai_metadata.get("session_model")
        or (move.game.ai_model.model_id if move.game.ai_model else "—")
    )


def _slot_snapshot(game: GameSession) -> tuple[str, int, str, int]:
    slots = list(game.slots.all().order_by("slot"))
    slot0 = next((slot for slot in slots if slot.slot == 0), None)
    slot1 = next((slot for slot in slots if slot.slot == 1), None)
    slot0_name = "AI" if slot0 and slot0.is_ai else (slot0.user.username if slot0 and slot0.user else "Waiting")
    slot1_name = "AI" if slot1 and slot1.is_ai else (slot1.user.username if slot1 and slot1.user else "Waiting")
    slot0_score = slot0.score if slot0 else 0
    slot1_score = slot1.score if slot1 else 0
    return slot0_name, slot0_score, slot1_name, slot1_score


class PlayerSlotInline(_PlayerSlotInline):
    model = PlayerSlot
    extra = 0
    readonly_fields = ("slot", "user", "is_ai", "ai_model", "ai_prompt", "rack", "score", "pass_streak")


class MoveInline(_MoveInline):
    model = Move
    extra = 0
    readonly_fields = ("seq", "player_slot", "kind", "points", "placements", "created_at")
    ordering = ("seq",)


@admin.register(GameSession)
class GameSessionAdmin(_GameSessionAdmin):
    change_list_template = "admin/game/gamesession/change_list.html"
    list_display = (
        "public_id_short",
        "players",
        "scoreline",
        "game_mode",
        "is_diagnostic",
        "status",
        "ai_model",
        "move_count_display",
        "game_over",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "game_mode", "is_diagnostic", "game_over", "variant_slug", "ai_model")
    search_fields = ("public_id", "slots__user__username", "ai_model__model_id")
    inlines = [PlayerSlotInline, MoveInline]
    readonly_fields = (
        "public_id",
        "is_diagnostic",
        "board_state",
        "premium_used",
        "bag_tiles",
        "bag_rng_state",
        "created_at",
        "updated_at",
        "finished_at",
    )
    date_hierarchy = "created_at"

    def get_queryset(self, request: HttpRequest) -> QuerySet[GameSession]:
        return (
            super()
            .get_queryset(request)
            .select_related("ai_model")
            .prefetch_related("slots__user")
            .annotate(move_count_total=Count("moves"))
        )

    def get_urls(self) -> list[URLPattern]:
        custom_urls = [
            path(
                "dashboard/",
                self.admin_site.admin_view(self.dashboard_view),
                name="game_gamesession_dashboard",
            )
        ]
        return custom_urls + super().get_urls()

    @admin.display(description="Game ID")
    def public_id_short(self, obj: GameSession) -> str:
        return obj.public_id.hex[:8]

    @admin.display(description="Players")
    def players(self, obj: GameSession) -> str:
        human_name, _, ai_name, _ = _slot_snapshot(obj)
        return f"{human_name} vs {ai_name}"

    @admin.display(description="Score")
    def scoreline(self, obj: GameSession) -> str:
        _, human_score, _, ai_score = _slot_snapshot(obj)
        return f"{human_score} : {ai_score}"

    @admin.display(description="Moves", ordering="move_count_total")
    def move_count_display(self, obj: GameSession) -> int:
        return int(getattr(obj, "move_count_total", 0))

    def dashboard_view(self, request: HttpRequest) -> HttpResponse:
        recent_games = list(
            GameSession.objects.select_related("ai_model")
            .prefetch_related("slots__user")
            .annotate(move_count_total=Count("moves"))[:12]
        )
        ai_moves = list(
            Move.objects.select_related("game__ai_model", "player_slot__user")
            .exclude(ai_metadata__isnull=True)
            .filter(game__is_diagnostic=False)
            .order_by("-created_at")
        )

        token_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        per_model_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "moves": 0,
                "games": set(),
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
            }
        )
        recent_ai_rows: list[dict[str, Any]] = []

        for index, move in enumerate(ai_moves):
            usage = _extract_usage(move.ai_metadata)
            model_id = _resolve_model_id(move)

            token_totals["input_tokens"] += usage["input_tokens"]
            token_totals["output_tokens"] += usage["output_tokens"]
            token_totals["total_tokens"] += usage["total_tokens"]

            model_stats = per_model_stats[model_id]
            model_stats["moves"] += 1
            model_stats["games"].add(move.game_id)
            model_stats["input_tokens"] += usage["input_tokens"]
            model_stats["output_tokens"] += usage["output_tokens"]
            model_stats["total_tokens"] += usage["total_tokens"]

            if index < 12:
                recent_ai_rows.append(
                    {
                        "game_id": move.game.public_id.hex[:8],
                        "seq": move.seq,
                        "model_id": model_id,
                        "input_tokens": usage["input_tokens"],
                        "output_tokens": usage["output_tokens"],
                        "total_tokens": usage["total_tokens"],
                        "created_at": move.created_at,
                    }
                )

        model_rows = [
            {
                "model_id": model_id,
                "moves": stats["moves"],
                "games": len(stats["games"]),
                "input_tokens": stats["input_tokens"],
                "output_tokens": stats["output_tokens"],
                "total_tokens": stats["total_tokens"],
            }
            for model_id, stats in per_model_stats.items()
        ]
        model_rows.sort(
            key=lambda row: (row["total_tokens"], row["moves"]),
            reverse=True,
        )

        recent_game_rows = []
        for game in recent_games:
            human_name, human_score, ai_name, ai_score = _slot_snapshot(game)
            recent_game_rows.append(
                {
                    "public_id": game.public_id.hex[:8],
                    "players": f"{human_name} vs {ai_name}",
                    "scoreline": f"{human_score} : {ai_score}",
                    "status": game.status,
                    "model": game.ai_model.display_name if game.ai_model else "—",
                    "moves": int(getattr(game, "move_count_total", 0)),
                    "updated_at": game.updated_at,
                }
            )

        product_sessions = GameSession.objects.filter(is_diagnostic=False)
        summary_cards = [
            {"label": "Users", "value": User.objects.count()},
            {"label": "Games", "value": product_sessions.count()},
            {"label": "Active games", "value": product_sessions.filter(status="active").count()},
            {"label": "Finished games", "value": product_sessions.filter(game_over=True).count()},
            {"label": "AI turns", "value": len(ai_moves)},
            {"label": "Total tokens", "value": f"{token_totals['total_tokens']:,}"},
        ]

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Operations dashboard",
            "summary_cards": summary_cards,
            "token_totals": token_totals,
            "recent_game_rows": recent_game_rows,
            "recent_ai_rows": recent_ai_rows,
            "model_rows": model_rows[:12],
            "users_url": reverse("admin:accounts_user_changelist"),
            "model_sync_url": reverse("admin:catalog_aimodel_sync"),
            "model_catalog_url": reverse("admin:catalog_aimodel_changelist"),
        }
        return TemplateResponse(request, "admin/game/dashboard.html", context)


@admin.register(Move)
class MoveAdmin(_MoveAdmin):
    list_display = (
        "game_short",
        "seq",
        "player_slot",
        "kind",
        "points",
        "model_id",
        "token_total",
        "created_at",
    )
    list_filter = ("kind", "game__ai_model")
    search_fields = ("game__public_id", "game__slots__user__username", "ai_metadata")
    readonly_fields = ("placements", "words_formed", "ai_metadata", "created_at")
    date_hierarchy = "created_at"

    @admin.display(description="Game")
    def game_short(self, obj: Move) -> str:
        return obj.game.public_id.hex[:8]

    @admin.display(description="Model")
    def model_id(self, obj: Move) -> str:
        return str(_resolve_model_id(obj))

    @admin.display(description="Tokens")
    def token_total(self, obj: Move) -> int:
        return _extract_usage(obj.ai_metadata)["total_tokens"]


@admin.register(ChatMessage)
class ChatMessageAdmin(_ChatMessageAdmin):
    list_display = ("game", "user", "body", "created_at")
    search_fields = ("game__public_id", "user__username", "body")
    readonly_fields = ("created_at",)


def spawn_diagnostic_runner(run_id: Any) -> None:
    """Spawn the detached fake-mode runner process for one run.

    The child env is os.environ minus the AppImage harness names. ⛔ No JWT in
    this env: the runner mints its own access-only token after start. ⛔ No
    user string on argv besides the UUID of the run this function was handed.
    Tests monkeypatch this module attribute instead of spawning processes.
    """
    backend_root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    for name in ("APPIMAGE", "ARGV0", "APPDIR"):
        env.pop(name, None)
    subprocess.Popen(
        [
            sys.executable,
            str(backend_root / "manage.py"),
            "run_diagnostic_match",
            "--run-id",
            str(run_id),
        ],
        cwd=str(backend_root),
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        env=env,
    )


_TERMINAL_DIAGNOSTIC_STATUSES = ("completed", "failed", "cancelled", "abandoned", "blocked_dependency")
_COMPARE_PAGE_SIZE = 20
_DIGEST_FILTER_PATTERN = re.compile(r"^[0-9a-f]{64}$")

# CSS classes come ONLY from these closed maps of DiagnosticRun literals.
_STATUS_CLASSES = {
    "queued": "diag-status-queued",
    "running": "diag-status-running",
    "completed": "diag-status-completed",
    "failed": "diag-status-failed",
    "cancelled": "diag-status-cancelled",
    "abandoned": "diag-status-abandoned",
    "blocked_dependency": "diag-status-blocked-dependency",
}
_INSTRUMENT_CLASSES = {
    "position-set": "diag-instrument-position-set",
    "full-game": "diag-instrument-full-game",
}

_HEARTBEAT_CADENCE_COPY = (
    "The runner records a heartbeat at least every five plies or approximately "
    "every 30 seconds."
)
_NOT_MEASURED = "Not measured."
_LAUNCH_SUCCESS_COPY = (
    "Diagnostic run launched in fake mode. This page shows its heartbeat, "
    "recorded plies, and report when available."
)

_REASON_NOT_COMPLETED = "Run status is not completed."
_REASON_NOT_MODEL_POSITION = "Report is not a model-position report."
_REASON_IDENTITY = "Artifact identity does not agree with the run."
_REASON_MIXED_SEATS = "Mixed seats — attributed to neither model."
_REASON_SAMPLE_MODELS = "Sample model ids do not agree with the run seats."
_REASON_COUNTS = "Artifact counts are inconsistent."
_REASON_RUNTIME = "Executed runtime is not live; fake and mixed-runtime runs are never pooled."
_REASON_RUNTIME_SAMPLES = "Sample executed runtime is not consistently live."
_REASON_TRUNCATED = "Report is truncated."
_REASON_UNATTEMPTED = "Report records unattempted positions."
_REASON_FLOOR = "A displayed metric is below its sample floor."
_REASON_PROVENANCE = "Provenance is incomplete: {field}."

_COMPARE_NOTE_PAGE = (
    "This table covers only the runs displayed on this page and holds no rolling statistics."
)
_COMPARE_NOTE_PROMPT = "Persisted prompt IDs are not historical prompt-content fingerprints."
_POOL_EMPTY_COPY = "No measured comparison pool on this page."
_NO_RUNS_COPY = "No position-set terminal runs on this page."


def _samples_of(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("samples")
    if not isinstance(raw, list):
        return []
    return [sample for sample in raw if isinstance(sample, dict)]


def _d3_counts_consistent(summary: dict[str, Any], sample_count_total: int) -> bool:
    """D3 count consistency: sample_count equals the sample list length,
    position_count splits into attempted + unattempted, the completion-source
    histogram stays inside the six-word vocabulary, and histogram totals
    reconcile with the did-not-measure count."""
    sample_count = summary.get("sample_count")
    if not isinstance(sample_count, int) or isinstance(sample_count, bool):
        return False
    if sample_count != sample_count_total:
        return False
    position_count = summary.get("position_count")
    if not isinstance(position_count, int) or isinstance(position_count, bool):
        return False
    unattempted = summary.get("unattempted_count")
    if not isinstance(unattempted, int) or isinstance(unattempted, bool):
        return False
    if position_count != sample_count + unattempted:
        return False
    counts_raw = summary.get("completion_source_counts")
    if not isinstance(counts_raw, dict):
        return False
    if any(key not in COMPLETION_SOURCE_VOCABULARY for key in counts_raw):
        return False
    for value in counts_raw.values():
        if not isinstance(value, int) or isinstance(value, bool):
            return False
    did_not_measure = summary.get("completion_source_did_not_measure_count")
    if not isinstance(did_not_measure, int) or isinstance(did_not_measure, bool):
        return False
    return sum(counts_raw.values()) == sample_count - did_not_measure


def _comparison_pool_status(
    run: DiagnosticRun, result: ReportReadResult
) -> tuple[bool, str, dict[str, Any] | None]:
    """Measured-pool qualification for the comparison table.

    The pool requires completed + position-set + model-position, agreeing
    identities, one model on both seats and in every sample, consistent D3
    counts, a consistently LIVE executed runtime, no truncation, no
    unattempted positions, floors met, and complete provenance. Fake,
    insufficient, partial, failed, mismatched, and no-report runs stay
    visible with an explicit exclusion reason and are never pooled.
    """
    if run.status != "completed":
        return False, _REASON_NOT_COMPLETED, None
    if run.seat0_model_id != run.seat1_model_id:
        return False, _REASON_MIXED_SEATS, None
    if result.failure is not None:
        return False, AVAILABILITY_COPY[result.failure], None
    payload = result.payload
    assert payload is not None
    if payload.get("report_kind") != "model-position":
        return False, _REASON_NOT_MODEL_POSITION, None
    requested_raw = payload.get("requested")
    requested = requested_raw if isinstance(requested_raw, dict) else {}
    if (
        requested.get("instrument") != run.instrument
        or requested.get("position_set_digest") != run.position_set_digest
        or requested.get("variant_slug") != run.variant_slug
        or requested.get("assist_mode") != run.assist_mode
    ):
        return False, _REASON_IDENTITY, None
    model_id = run.seat0_model_id
    provider = requested.get("provider")
    if requested.get("model_id") != model_id:
        return False, _REASON_IDENTITY, None
    if not isinstance(provider, str) or not provider:
        return False, _REASON_IDENTITY, None
    samples = _samples_of(payload)
    if any(sample.get("model_id") != model_id for sample in samples):
        return False, _REASON_SAMPLE_MODELS, None
    indices: set[int] = set()
    for sample in samples:
        position_raw = sample.get("position")
        position = position_raw if isinstance(position_raw, dict) else {}
        index = position.get("position_index")
        if not isinstance(index, int) or isinstance(index, bool) or index in indices:
            return False, _REASON_COUNTS, None
        indices.add(index)
    summary_raw = payload.get("summary")
    if not isinstance(summary_raw, dict):
        return False, _REASON_COUNTS, None
    if not _d3_counts_consistent(summary_raw, len(samples)):
        return False, _REASON_COUNTS, None
    if run.executed_runtime_mode != "live" or requested.get("executed_runtime_mode") != "live":
        return False, _REASON_RUNTIME, None
    if any(sample.get("executed_runtime_mode") != "live" for sample in samples):
        return False, _REASON_RUNTIME_SAMPLES, None
    unattempted = summary_raw.get("unattempted_count")
    if not isinstance(unattempted, int) or isinstance(unattempted, bool) or unattempted != 0:
        return False, _REASON_UNATTEMPTED, None
    if summary_raw.get("truncated") is not False:
        return False, _REASON_TRUNCATED, None
    if floor_violations(samples, summary_raw):
        return False, _REASON_FLOOR, None
    source_revision = payload.get("source_revision")
    parameters = run.parameters_json if isinstance(run.parameters_json, dict) else {}
    script = parameters.get("script", requested.get("script"))
    queue_mode = parameters.get("queue_mode", requested.get("queue_mode"))
    provenance_fields = [
        ("source revision", isinstance(source_revision, str) and bool(source_revision)),
        ("persisted prompt id", run.prompt_id is not None),
        ("script", isinstance(script, str) and bool(script)),
        ("queue mode", isinstance(queue_mode, str) and bool(queue_mode)),
        ("configured caps", min(run.max_plies, run.max_provider_requests, run.max_wall_clock_seconds) > 0),
    ]
    for field, present in provenance_fields:
        if not present:
            return False, _REASON_PROVENANCE.format(field=field), None
    return True, "", payload


def _pool_group_parts(run: DiagnosticRun, payload: dict[str, Any]) -> tuple[str, str, str]:
    """(sort key, label, model identity) for one pooled comparison group."""
    requested_raw = payload.get("requested")
    requested = requested_raw if isinstance(requested_raw, dict) else {}
    source_revision = str(payload.get("source_revision") or "")
    script = str(requested.get("script") or "")
    queue_mode = str(requested.get("queue_mode") or "")
    sort_key = "|".join(
        (
            run.position_set_digest,
            run.variant_slug,
            run.assist_mode,
            run.executed_runtime_mode,
            source_revision,
            str(run.prompt_id),
            script,
            queue_mode,
        )
    )
    label = (
        f"digest {run.position_set_digest[:12]}… · variant {run.variant_slug} · "
        f"assist {run.assist_mode} · runtime {run.executed_runtime_mode} · "
        f"source revision {source_revision} · prompt #{run.prompt_id} · "
        f"script {script} · queue {queue_mode} · caps "
        f"{run.max_plies}/{run.max_provider_requests}/{run.max_wall_clock_seconds}"
    )
    provider = str(requested.get("provider") or "")
    model_id = str(requested.get("model_id") or "")
    return sort_key, label, f"{provider}|{model_id}"


@admin.register(DiagnosticRun)
class DiagnosticRunAdmin(_DiagnosticRunAdmin):
    change_list_template = "admin/game/diagnosticrun/change_list.html"
    list_display = (
        "id_short",
        "status",
        "instrument",
        "assist_mode",
        "seat0_model_id",
        "seat1_model_id",
        "variant_slug",
        "executed_runtime_mode",
        "inflight",
        "heartbeat_age",
        "diagnostic_end_reason",
        "created_at",
    )
    list_filter = ("status", "instrument", "assist_mode", "executed_runtime_mode")
    search_fields = ("id", "seat0_model_id", "seat1_model_id", "session__public_id")
    actions = ("cancel_selected_runs",)
    readonly_fields = (
        "id",
        "status",
        "assist_mode",
        "instrument",
        "variant_slug",
        "seat0_model_id",
        "seat1_model_id",
        "prompt",
        "session",
        "position_set_digest",
        "max_plies",
        "max_provider_requests",
        "max_wall_clock_seconds",
        "heartbeat_at",
        "pid",
        "diagnostic_end_reason",
        "executed_runtime_mode",
        "score_authority",
        "report_path",
        "log_path",
        "created_by",
        "parameters_json",
        "ended_at",
        "created_at",
        "updated_at",
    )

    def get_urls(self) -> list[URLPattern]:
        custom_urls = [
            path(
                "launch/",
                self.admin_site.admin_view(self.launch_view),
                name="game_diagnosticrun_launch",
            ),
            path(
                "compare/",
                self.admin_site.admin_view(self.compare_view),
                name="game_diagnosticrun_compare",
            ),
            path(
                "<uuid:run_id>/cancel/",
                self.admin_site.admin_view(self.cancel_view),
                name="game_diagnosticrun_cancel",
            ),
        ]
        return custom_urls + super().get_urls()

    @admin.display(description="Run")
    def id_short(self, obj: DiagnosticRun) -> str:
        return obj.id.hex[:8]

    @admin.display(description="In flight", boolean=True)
    def inflight(self, obj: DiagnosticRun) -> bool:
        return obj.status in ("queued", "running")

    @admin.display(description="Heartbeat")
    def heartbeat_age(self, obj: DiagnosticRun) -> str:
        if obj.status not in ("queued", "running") or obj.heartbeat_at is None:
            return "—"
        age = int((timezone.now() - obj.heartbeat_at).total_seconds())
        return f"{age}s"

    def _guard_change_permission(self, request: HttpRequest) -> None:
        if not self.has_change_permission(request):
            raise PermissionDenied

    @admin.action(description="Cancel selected diagnostic runs")
    def cancel_selected_runs(self, request: HttpRequest, queryset: QuerySet[DiagnosticRun]) -> None:
        cancelled = 0
        refused = 0
        for run in queryset.filter(status__in=("queued", "running")).exclude(status="cancelled"):
            try:
                cancel_diagnostic_run(run_id=run.id)
            except DiagnosticSessionError:
                refused += 1
            else:
                cancelled += 1
        if cancelled:
            self.message_user(
                request,
                f"Cancelled {cancelled} diagnostic run(s). The runner observes the "
                "cancel at its next ply boundary; no Move rows were created.",
                level=messages.SUCCESS,
            )
        if refused:
            self.message_user(
                request,
                f"{refused} selected run(s) could not be cancelled.",
                level=messages.WARNING,
            )

    def change_view(
        self,
        request: HttpRequest,
        object_id: str,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        """Read-only live run page. GET only; never the default change form."""
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        run = self._get_run_or_404(object_id)
        if not self.has_view_permission(request, run):
            raise PermissionDenied
        return self._run_page(request, run)

    def _get_run_or_404(self, object_id: str) -> DiagnosticRun:
        try:
            run = DiagnosticRun.objects.filter(pk=object_id).first()
        except (TypeError, ValueError, ValidationError):
            raise Http404("Diagnostic run not found") from None
        if run is None:
            raise Http404("Diagnostic run not found")
        return run

    def _run_page(self, request: HttpRequest, run: DiagnosticRun) -> TemplateResponse:
        in_flight = run.status in ("queued", "running")
        if in_flight:
            # In-flight GET must not open a report file: no reader call at all.
            report_context: dict[str, Any] = {
                "state": "empty",
                "message": AVAILABILITY_EMPTY,
            }
        else:
            report_context = present_report(
                run.id,
                run.report_path,
                terminal=True,
                run_score_authority=run.score_authority,
            )
        # Query budget: the PK get above plus ONE bounded ply query. The 20
        # newest rows are fetched descending and reversed in memory; the
        # latest ply identity comes from this same list.
        ply_rows: list[Any] = list(
            run.plies.order_by("-ply_index")
            .values_list(
                "ply_index",
                "position_index",
                "seat_index",
                "model_id",
                "executed_runtime_mode",
                "score_authority",
                "completion_source",
                "terminal_cause",
                "model_legal_score",
                "ranked_best_score",
                "valid_candidate_count",
                "provider_requests_used",
                "wall_clock_ms",
                named=True,
            )[:20]
        )
        ply_rows.reverse()
        latest = ply_rows[-1] if ply_rows else None
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": f"Diagnostic run {run.id.hex[:8]}",
            "subtitle": (
                "Live run status, recorded plies, and finished report (fake mode only)."
            ),
            "run_id": str(run.id),
            "run_id_short": run.id.hex[:8],
            "status": run.status,
            "status_display": run.get_status_display(),
            "status_class": _STATUS_CLASSES.get(run.status, "diag-status-unknown"),
            "instrument": run.instrument,
            "instrument_display": run.get_instrument_display(),
            "instrument_class": _INSTRUMENT_CLASSES.get(
                run.instrument, "diag-instrument-unknown"
            ),
            "seat0_model_id": run.seat0_model_id,
            "seat1_model_id": run.seat1_model_id,
            "assist_mode_display": run.get_assist_mode_display(),
            "executed_runtime_mode": run.executed_runtime_mode or "not recorded",
            "variant_slug": run.variant_slug,
            "digest_short": run.position_set_digest[:12] if run.position_set_digest else "",
            "end_reason": run.diagnostic_end_reason,
            "has_heartbeat": run.heartbeat_at is not None,
            "heartbeat_at": timezone.localtime(run.heartbeat_at) if run.heartbeat_at else None,
            "heartbeat_age_seconds": (
                int((timezone.now() - run.heartbeat_at).total_seconds())
                if run.heartbeat_at
                else None
            ),
            "heartbeat_cadence": _HEARTBEAT_CADENCE_COPY,
            "max_plies": run.max_plies,
            "last_ply_index": ply_rows[-1].ply_index if ply_rows else None,
            "ply_rows": ply_rows,
            "latest_seat_index": latest.seat_index if latest else None,
            "latest_model_id": latest.model_id if latest else None,
            "latest_completion_source": (
                latest.completion_source
                if latest is not None and latest.completion_source
                else _NOT_MEASURED
            )
            if latest is not None
            else None,
            "in_flight": in_flight,
            "can_cancel": in_flight and self.has_change_permission(request, run),
            "cancel_url": reverse("admin:game_diagnosticrun_cancel", args=[run.id]),
            "change_url": reverse("admin:game_diagnosticrun_change", args=[run.id]),
            "compare_url": reverse("admin:game_diagnosticrun_compare"),
            "report": report_context,
        }
        response = TemplateResponse(
            request, "admin/game/diagnosticrun/change_form.html", context
        )
        if in_flight:
            response["Refresh"] = "2"
        return response

    def cancel_view(self, request: HttpRequest, run_id: uuid_module.UUID) -> HttpResponse:
        """POST-only cancel; delegates to cancel_diagnostic_run (cancelled,
        never failed). Terminal races are informational only; no retry."""
        try:
            run = DiagnosticRun.objects.get(pk=run_id)
        except DiagnosticRun.DoesNotExist:
            raise Http404("Diagnostic run not found") from None
        if not self.has_change_permission(request, run):
            raise PermissionDenied
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        try:
            cancel_diagnostic_run(run_id=run.id)
        except DiagnosticSessionError:
            self.message_user(
                request,
                f"Diagnostic run {run.id.hex[:8]} is not in flight; no cancel "
                "was applied.",
                level=messages.INFO,
            )
        else:
            self.message_user(
                request,
                f"Diagnostic run {run.id.hex[:8]} cancelled at its next ply "
                "boundary; no Move rows were created.",
                level=messages.SUCCESS,
            )
        return redirect(reverse("admin:game_diagnosticrun_change", args=[run.id]))

    def compare_view(self, request: HttpRequest) -> HttpResponse:
        """GET-only cross-model comparison over the displayed page of runs."""
        if not self.has_view_permission(request):
            raise PermissionDenied
        if request.method != "GET":
            return HttpResponseNotAllowed(["GET"])
        digest_raw = request.GET.get("digest", "").strip().lower()
        digest_filter = digest_raw if _DIGEST_FILTER_PATTERN.fullmatch(digest_raw) else ""
        queryset = DiagnosticRun.objects.filter(
            instrument="position-set",
            status__in=_TERMINAL_DIAGNOSTIC_STATUSES,
        )
        if digest_filter:
            queryset = queryset.filter(position_set_digest=digest_filter)
        paginator = Paginator(queryset.order_by("-created_at"), _COMPARE_PAGE_SIZE)
        page_raw = request.GET.get("page", "1")
        page_number = int(page_raw) if page_raw.isdigit() and int(page_raw) >= 1 else 1
        try:
            page = paginator.page(page_number)
        except EmptyPage:
            page = paginator.page(paginator.num_pages)

        # At most one artifact parse per run and at most 20 runs per page.
        excluded_rows: list[dict[str, Any]] = []
        pool: dict[str, dict[str, Any]] = {}
        for run in page.object_list:
            result = read_diagnostic_report(run.id, run.report_path)
            pooled, reason, payload = _comparison_pool_status(run, result)
            row: dict[str, Any] = {
                "run_id_short": run.id.hex[:8],
                "status_display": run.get_status_display(),
                "status_class": _STATUS_CLASSES.get(run.status, "diag-status-unknown"),
                "seat0_model_id": run.seat0_model_id,
                "seat1_model_id": run.seat1_model_id,
                "mixed_seats": run.seat0_model_id != run.seat1_model_id,
                "created_at": run.created_at,
            }
            if not pooled:
                row["reason"] = reason
                excluded_rows.append(row)
                continue
            assert payload is not None
            metrics = comparison_metrics_summary(_samples_of(payload), payload["summary"])
            row["metrics"] = metrics
            sort_key, label, model_identity = _pool_group_parts(run, payload)
            entry = pool.setdefault(sort_key, {"label": label, "models": {}})
            model_entry = entry["models"].setdefault(
                model_identity,
                {
                    "provider": model_identity.split("|", 1)[0],
                    "model_id": model_identity.split("|", 1)[1],
                    "runs": [],
                },
            )
            model_entry["runs"].append(row)

        groups: list[dict[str, Any]] = []
        for entry in pool.values():
            models = [
                {
                    "provider": model["provider"],
                    "model_id": model["model_id"],
                    "runs": model["runs"],
                }
                for model in sorted(
                    entry["models"].values(), key=lambda model: model["model_id"]
                )
            ]
            groups.append({"label": entry["label"], "models": models})
        groups.sort(key=lambda group: group["label"])

        base_url = reverse("admin:game_diagnosticrun_compare")

        def _page_url(number: int) -> str:
            url = f"{base_url}?page={number}"
            return f"{url}&digest={digest_filter}" if digest_filter else url

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Diagnostic model comparison",
            "subtitle": (
                "Cross-model comparison over the displayed page of finished "
                "position-set runs. Fake-mode runs are shown but never pooled."
            ),
            "groups": groups,
            "excluded_rows": excluded_rows,
            "pool_empty": not groups,
            "pool_empty_copy": _POOL_EMPTY_COPY,
            "no_runs": paginator.count == 0,
            "no_runs_copy": _NO_RUNS_COPY,
            "note_page": _COMPARE_NOTE_PAGE,
            "note_prompt": _COMPARE_NOTE_PROMPT,
            "digest_filter": digest_filter,
            "page_number": page.number,
            "num_pages": paginator.num_pages,
            "prev_url": _page_url(page.previous_page_number()) if page.has_previous() else None,
            "next_url": _page_url(page.next_page_number()) if page.has_next() else None,
        }
        return TemplateResponse(request, "admin/game/diagnosticrun/comparison.html", context)

    def launch_view(self, request: HttpRequest) -> HttpResponse:
        self._guard_change_permission(request)
        if request.method == "POST":
            return self._launch_post(request)
        return self._launch_form(request)

    def _launch_form(
        self, request: HttpRequest, error: str | None = None
    ) -> HttpResponse:
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Launch fake-mode diagnostic run",
            "subtitle": (
                "Creates a two-AI diagnostic session and spawns the detached "
                "run_diagnostic_match runner. This slice is FAKE ONLY: script "
                "generic_unchanged, selected-only queue, zero provider calls."
            ),
            "launch_url": reverse("admin:game_diagnosticrun_launch"),
            "changelist_url": reverse("admin:game_diagnosticrun_changelist"),
            "defaults": {
                "instrument": "full-game",
                "assist_mode": "assisted",
                "variant_slug": "english",
                "max_plies": DIAGNOSTIC_MAX_PLIES_DEFAULT,
                "max_provider_requests": DIAGNOSTIC_MAX_PROVIDER_REQUESTS_DEFAULT,
                "max_wall_clock_seconds": DIAGNOSTIC_MAX_WALL_CLOCK_SECONDS_DEFAULT,
            },
            "maxima": {
                "max_plies": DIAGNOSTIC_MAX_PLIES_ADMIN_MAX,
                "max_provider_requests": DIAGNOSTIC_MAX_PROVIDER_REQUESTS_ADMIN_MAX,
                "max_wall_clock_seconds": DIAGNOSTIC_MAX_WALL_CLOCK_SECONDS_ADMIN_MAX,
            },
            "error": error,
        }
        return TemplateResponse(request, "admin/game/diagnosticrun/launch.html", context)

    def _int_field(self, raw: str, default: int, maximum: int) -> int | None:
        text = raw.strip()
        if not text:
            return default
        if not text.isdigit():
            return None
        value = int(text)
        if not 1 <= value <= maximum:
            return None
        return value

    def _launch_post(self, request: HttpRequest) -> HttpResponse:
        instrument = request.POST.get("instrument", "")
        assist_mode = request.POST.get("assist_mode", "")
        seat0_model_id = request.POST.get("seat0_model_id", "").strip()
        seat1_model_id = request.POST.get("seat1_model_id", "").strip()
        variant_slug = request.POST.get("variant_slug", "").strip() or "english"
        position_set_digest = request.POST.get("position_set_digest", "").strip().lower()
        prompt_raw = request.POST.get("prompt_id", "").strip()
        prompt_id = int(prompt_raw) if prompt_raw.isdigit() else None
        seed_raw = request.POST.get("seed", "").strip()
        seed = int(seed_raw) if seed_raw.isdigit() else random.randint(0, 2**31 - 1)
        created_by_id = request.user.id

        max_plies = self._int_field(
            request.POST.get("max_plies", ""),
            DIAGNOSTIC_MAX_PLIES_DEFAULT,
            DIAGNOSTIC_MAX_PLIES_ADMIN_MAX,
        )
        max_provider_requests = self._int_field(
            request.POST.get("max_provider_requests", ""),
            DIAGNOSTIC_MAX_PROVIDER_REQUESTS_DEFAULT,
            DIAGNOSTIC_MAX_PROVIDER_REQUESTS_ADMIN_MAX,
        )
        max_wall_clock_seconds = self._int_field(
            request.POST.get("max_wall_clock_seconds", ""),
            DIAGNOSTIC_MAX_WALL_CLOCK_SECONDS_DEFAULT,
            DIAGNOSTIC_MAX_WALL_CLOCK_SECONDS_ADMIN_MAX,
        )

        errors: list[str] = []
        if instrument not in ("full-game", "position-set"):
            errors.append("Choose an instrument.")
        if assist_mode not in ("assisted", "authorship"):
            errors.append("Choose an assist mode.")
        if not seat0_model_id or not seat1_model_id:
            errors.append("Both seat model ids are required.")
        if max_plies is None:
            errors.append(f"max_plies must be 1..{DIAGNOSTIC_MAX_PLIES_ADMIN_MAX}.")
        if max_provider_requests is None:
            errors.append(
                f"max_provider_requests must be 1..{DIAGNOSTIC_MAX_PROVIDER_REQUESTS_ADMIN_MAX}."
            )
        if max_wall_clock_seconds is None:
            errors.append(
                "max_wall_clock_seconds must be 1.."
                f"{DIAGNOSTIC_MAX_WALL_CLOCK_SECONDS_ADMIN_MAX}."
            )
        if instrument == "position-set" and len(position_set_digest) != 64:
            errors.append("position-set requires a 64-hex position_set_digest.")
        if created_by_id is None:
            errors.append("Launch requires an authenticated staff user.")
        if errors:
            return self._launch_form(request, error=" ".join(errors))

        assert max_plies is not None
        assert max_provider_requests is not None
        assert max_wall_clock_seconds is not None
        assert created_by_id is not None

        stale = abandon_stale_diagnostic_runs()
        if stale:
            self.message_user(
                request,
                f"Abandoned {len(stale)} stale in-flight diagnostic run(s) "
                "(stale heartbeat).",
                level=messages.WARNING,
            )

        try:
            created = create_diagnostic_game(
                variant_slug=variant_slug,
                seed=seed,
                seat0_model_id=seat0_model_id,
                seat1_model_id=seat1_model_id,
                prompt_id=prompt_id,
                created_by_id=created_by_id,
                assist_mode=assist_mode,
            )
        except IntegrityError:
            self.message_user(
                request,
                "A diagnostic run is already in flight. Cancel it or wait for it "
                "to finish before launching another.",
                level=messages.ERROR,
            )
            return redirect(reverse("admin:game_diagnosticrun_launch"))
        except DiagnosticSessionError as exc:
            return self._launch_form(request, error=str(exc))

        run = DiagnosticRun.objects.get(pk=created["run_id"])
        try:
            configure_diagnostic_run(
                run,
                instrument=instrument,
                position_set_digest=position_set_digest,
                max_plies=max_plies,
                max_provider_requests=max_provider_requests,
                max_wall_clock_seconds=max_wall_clock_seconds,
                extra_parameters={
                    "django_origin": request.build_absolute_uri("/").rstrip("/"),
                    "script": "generic_unchanged",
                    "queue_mode": "selected-only",
                    "launch_source": "django-admin",
                },
            )
        except DiagnosticSessionError as exc:
            abort_diagnostic_run(run_id=run.id, reason="launch_configuration_invalid")
            return self._launch_form(request, error=str(exc))

        if min(
            run.max_plies, run.max_provider_requests, run.max_wall_clock_seconds
        ) <= 0:
            abort_diagnostic_run(run_id=run.id, reason="launch_configuration_invalid")
            return self._launch_form(request, error="Refusing to spawn with a zero cap.")

        spawn_diagnostic_runner(run.id)
        self.message_user(request, _LAUNCH_SUCCESS_COPY, level=messages.SUCCESS)
        return redirect(reverse("admin:game_diagnosticrun_change", args=[run.id]))
