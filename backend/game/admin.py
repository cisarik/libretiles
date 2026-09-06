import os
import random
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError
from django.db.models import Count, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils import timezone

from accounts.models import User
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
        self.message_user(
            request,
            f"Diagnostic run {run.id.hex[:8]} launched (fake mode). Heartbeat and "
            "plies appear on the run's change page.",
            level=messages.SUCCESS,
        )
        return redirect(reverse("admin:game_diagnosticrun_changelist"))
