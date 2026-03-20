from django.contrib import admin

from .models import GameSession, Move, PlayerSlot


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
    list_display = (
        "public_id_short",
        "game_mode",
        "status",
        "ai_model",
        "game_over",
        "created_at",
    )
    list_filter = ("status", "game_mode", "game_over", "variant_slug")
    search_fields = ("public_id",)
    inlines = [PlayerSlotInline, MoveInline]
    readonly_fields = ("public_id", "board_state", "blanks", "premium_used", "bag_tiles")

    @admin.display(description="Game ID")
    def public_id_short(self, obj: GameSession) -> str:
        return obj.public_id.hex[:8]


@admin.register(Move)
class MoveAdmin(admin.ModelAdmin):
    list_display = ("game", "seq", "player_slot", "kind", "points", "created_at")
    list_filter = ("kind",)
    readonly_fields = ("placements", "words_formed", "ai_metadata")
