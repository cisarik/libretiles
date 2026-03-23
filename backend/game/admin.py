from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.contrib import admin
from django.db.models import Count, Sum
from django.http import HttpRequest, HttpResponse
from django.template.response import TemplateResponse
from django.urls import path, reverse

from accounts.models import User
from billing.models import CreditBalance, Transaction

from .models import ChatMessage, GameSession, Move, PlayerSlot

_ZERO = Decimal("0")
_CENT = Decimal("0.01")
_USD_PRECISION = Decimal("0.0001")


def _as_decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return _ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return _ZERO


def _format_decimal(value: Decimal, precision: Decimal = _CENT) -> str:
    return format(value.quantize(precision, rounding=ROUND_HALF_UP), "f")


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


def _extract_billing(ai_metadata: Any) -> dict[str, Decimal]:
    if not isinstance(ai_metadata, dict):
        return {"charged_usd": _ZERO, "charged_credits": _ZERO}
    billing = ai_metadata.get("billing")
    if not isinstance(billing, dict):
        return {"charged_usd": _ZERO, "charged_credits": _ZERO}
    return {
        "charged_usd": _as_decimal(billing.get("charged_usd")),
        "charged_credits": _as_decimal(billing.get("charged_credits")),
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
    slot0_name = "AI" if slot0 and slot0.is_ai else (slot0.user.username if slot0 and slot0.user else "Waiting")  # type: ignore[union-attr]
    slot1_name = "AI" if slot1 and slot1.is_ai else (slot1.user.username if slot1 and slot1.user else "Waiting")  # type: ignore[union-attr]
    slot0_score = slot0.score if slot0 else 0
    slot1_score = slot1.score if slot1 else 0
    return slot0_name, slot0_score, slot1_name, slot1_score


class PlayerSlotInline(admin.TabularInline):
    model = PlayerSlot
    extra = 0
    readonly_fields = ("slot", "user", "is_ai", "rack", "score", "pass_streak")


class MoveInline(admin.TabularInline):
    model = Move
    extra = 0
    readonly_fields = ("seq", "player_slot", "kind", "points", "placements", "created_at")
    ordering = ("seq",)


@admin.register(GameSession)
class GameSessionAdmin(admin.ModelAdmin):
    change_list_template = "admin/game/gamesession/change_list.html"
    list_display = (
        "public_id_short",
        "players",
        "scoreline",
        "game_mode",
        "status",
        "ai_model",
        "move_count_display",
        "game_over",
        "created_at",
        "updated_at",
    )
    list_filter = ("status", "game_mode", "game_over", "variant_slug", "ai_model")
    search_fields = ("public_id", "slots__user__username", "ai_model__model_id")
    inlines = [PlayerSlotInline, MoveInline]
    readonly_fields = (
        "public_id",
        "board_state",
        "blanks",
        "premium_used",
        "bag_tiles",
        "created_at",
        "updated_at",
        "finished_at",
    )
    date_hierarchy = "created_at"

    def get_queryset(self, request: HttpRequest):
        return (
            super()
            .get_queryset(request)
            .select_related("ai_model")
            .prefetch_related("slots__user")
            .annotate(move_count_total=Count("moves"))
        )

    def get_urls(self):
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
            .order_by("-created_at")
        )

        token_totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        billed_usd_total = _ZERO
        billed_credits_total = _ZERO
        per_model_stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "moves": 0,
                "games": set(),
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "charged_usd": _ZERO,
                "charged_credits": _ZERO,
            }
        )
        recent_ai_rows: list[dict[str, Any]] = []

        for index, move in enumerate(ai_moves):
            usage = _extract_usage(move.ai_metadata)
            billing = _extract_billing(move.ai_metadata)
            model_id = _resolve_model_id(move)

            token_totals["input_tokens"] += usage["input_tokens"]
            token_totals["output_tokens"] += usage["output_tokens"]
            token_totals["total_tokens"] += usage["total_tokens"]
            billed_usd_total += billing["charged_usd"]
            billed_credits_total += billing["charged_credits"]

            model_stats = per_model_stats[model_id]
            model_stats["moves"] += 1
            model_stats["games"].add(move.game_id)
            model_stats["input_tokens"] += usage["input_tokens"]
            model_stats["output_tokens"] += usage["output_tokens"]
            model_stats["total_tokens"] += usage["total_tokens"]
            model_stats["charged_usd"] += billing["charged_usd"]
            model_stats["charged_credits"] += billing["charged_credits"]

            if index < 12:
                recent_ai_rows.append(
                    {
                        "game_id": move.game.public_id.hex[:8],
                        "seq": move.seq,
                        "model_id": model_id,
                        "input_tokens": usage["input_tokens"],
                        "output_tokens": usage["output_tokens"],
                        "total_tokens": usage["total_tokens"],
                        "charged_usd": _format_decimal(
                            billing["charged_usd"], _USD_PRECISION
                        ),
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
                "charged_usd": _format_decimal(stats["charged_usd"], _USD_PRECISION),
                "charged_credits": _format_decimal(stats["charged_credits"]),
                "_sort_usd": stats["charged_usd"],
            }
            for model_id, stats in per_model_stats.items()
        ]
        model_rows.sort(
            key=lambda row: (row["_sort_usd"], row["total_tokens"], row["moves"]),
            reverse=True,
        )
        for row in model_rows:
            row.pop("_sort_usd", None)

        balances_total = CreditBalance.objects.aggregate(total=Sum("balance"))["total"] or _ZERO
        game_charge_total = (
            Transaction.objects.filter(type="game_charge").aggregate(total=Sum("amount"))["total"]
            or _ZERO
        )
        total_credits_spent = abs(game_charge_total)

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

        summary_cards = [
            {"label": "Users", "value": User.objects.count()},
            {"label": "Games", "value": GameSession.objects.count()},
            {"label": "Active games", "value": GameSession.objects.filter(status="active").count()},
            {"label": "Finished games", "value": GameSession.objects.filter(game_over=True).count()},
            {"label": "AI turns", "value": len(ai_moves)},
            {"label": "Total tokens", "value": f"{token_totals['total_tokens']:,}"},
            {
                "label": "AI spend",
                "value": f"${_format_decimal(billed_usd_total, _USD_PRECISION)}",
            },
            {
                "label": "Outstanding balances",
                "value": f"${_format_decimal(_as_decimal(balances_total))}",
            },
        ]

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Operations dashboard",
            "summary_cards": summary_cards,
            "token_totals": token_totals,
            "total_credits_spent": _format_decimal(total_credits_spent),
            "total_usd_spent": _format_decimal(billed_usd_total, _USD_PRECISION),
            "recent_game_rows": recent_game_rows,
            "recent_ai_rows": recent_ai_rows,
            "model_rows": model_rows[:12],
            "balances_url": reverse("admin:billing_creditbalance_changelist"),
            "users_url": reverse("admin:accounts_user_changelist"),
            "model_sync_url": reverse("admin:catalog_aimodel_sync"),
            "model_catalog_url": reverse("admin:catalog_aimodel_changelist"),
        }
        return TemplateResponse(request, "admin/game/dashboard.html", context)


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = (
        "game_short",
        "seq",
        "player_slot",
        "kind",
        "points",
        "model_id",
        "token_total",
        "charged_usd",
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

    @admin.display(description="Charged USD")
    def charged_usd(self, obj: Move) -> str:
        billing = _extract_billing(obj.ai_metadata)
        return f"${_format_decimal(billing['charged_usd'], _USD_PRECISION)}"


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("game", "user", "body", "created_at")
    search_fields = ("game__public_id", "user__username", "body")
    readonly_fields = ("created_at",)
