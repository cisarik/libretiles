from django.contrib import admin

from .models import AIModel


@admin.register(AIModel)
class AIModelAdmin(admin.ModelAdmin):
    list_display = (
        "display_name",
        "provider",
        "model_id",
        "quality_tier",
        "cost_per_game",
        "is_active",
        "sort_order",
    )
    list_filter = ("provider", "quality_tier", "is_active")
    list_editable = ("cost_per_game", "is_active", "sort_order")
    search_fields = ("display_name", "model_id")
    ordering = ("sort_order", "display_name")
