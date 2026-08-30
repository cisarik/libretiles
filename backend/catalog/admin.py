from io import StringIO
from typing import TYPE_CHECKING

from django.contrib import admin, messages
from django.core.management import call_command
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse

from .models import AIModel, AIPrompt

if TYPE_CHECKING:
    _AIModelAdmin = admin.ModelAdmin[AIModel]
    _AIPromptAdmin = admin.ModelAdmin[AIPrompt]
else:
    _AIModelAdmin = admin.ModelAdmin
    _AIPromptAdmin = admin.ModelAdmin


@admin.register(AIModel)
class AIModelAdmin(_AIModelAdmin):
    change_list_template = "admin/catalog/aimodel/change_list.html"
    list_display = (
        "display_name",
        "provider",
        "model_id",
        "openrouter_available",
        "openrouter_managed",
        "quality_tier",
        "is_active",
        "sort_order",
        "released_at",
        "last_synced_at",
    )
    list_filter = (
        "provider",
        "quality_tier",
        "is_active",
        "openrouter_available",
        "openrouter_managed",
    )
    list_editable = ("is_active", "sort_order")
    search_fields = ("display_name", "model_id")
    ordering = ("sort_order", "display_name")
    readonly_fields = ("created_at", "updated_at", "last_synced_at", "released_at")

    def get_urls(self) -> list[URLPattern]:
        custom_urls = [
            path(
                "sync/",
                self.admin_site.admin_view(self.sync_models_view),
                name="catalog_aimodel_sync",
            )
        ]
        return custom_urls + super().get_urls()

    def sync_models_view(self, request: HttpRequest) -> HttpResponse:
        if request.method == "POST":
            stdout = StringIO()
            try:
                call_command("sync_openrouter_models", stdout=stdout)
            except Exception as exc:  # pragma: no cover - defensive admin UX
                self.message_user(
                    request,
                    f"OpenRouter sync failed: {exc}",
                    level=messages.ERROR,
                )
            else:
                sync_output = stdout.getvalue().strip().splitlines()
                self.message_user(
                    request,
                    sync_output[-1] if sync_output else "OpenRouter sync complete.",
                    level=messages.SUCCESS,
                )
            return redirect(reverse("admin:catalog_aimodel_changelist"))

        latest_sync = (
            AIModel.objects.exclude(last_synced_at__isnull=True)
            .order_by("-last_synced_at")
            .first()
        )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Sync OpenRouter free catalog",
            "subtitle": (
                "Refresh the backend catalog from the OpenRouter free model list. "
                "is_active is the Admin kill switch; newly discovered eligible rows "
                "start active. Empty or >50% cohort drops abort without writes."
            ),
            "sync_url": reverse("admin:catalog_aimodel_sync"),
            "changelist_url": reverse("admin:catalog_aimodel_changelist"),
            "stats": {
                "total_models": AIModel.objects.count(),
                "active_models": AIModel.objects.filter(is_active=True).count(),
                "openrouter_available_models": AIModel.objects.filter(
                    openrouter_available=True
                ).count(),
                "openrouter_managed_models": AIModel.objects.filter(
                    openrouter_managed=True
                ).count(),
            },
            "latest_sync_at": latest_sync.last_synced_at if latest_sync else None,
        }
        return TemplateResponse(request, "admin/catalog/aimodel/sync_models.html", context)


@admin.register(AIPrompt)
class AIPromptAdmin(_AIPromptAdmin):
    list_display = ("name", "fitness", "is_active", "sort_order", "updated_at")
    list_editable = ("fitness", "is_active", "sort_order")
    search_fields = ("name", "prompt")
    ordering = ("sort_order", "name")
    readonly_fields = ("created_at", "updated_at")
