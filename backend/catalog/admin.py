import os
from io import StringIO
from typing import TYPE_CHECKING, Any

from django.conf import settings
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.management import call_command
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect
from django.template.response import TemplateResponse
from django.urls import URLPattern, path, reverse
from django.utils import timezone as django_timezone

from .admin_controls import (
    CatalogChange,
    CatalogControlError,
    apply_reviewed_token,
    catalog_fingerprint,
    ordering_reviewed,
    parse_review_changes,
    preview_review,
    sign_review_token,
)
from .models import AIModel, AIPrompt, CapabilityProbe, CatalogAdminControl
from .provider_probes import LIVE_SENTINEL, SIMULATED_SUMMARY, run_aimodel_probe
from .selection import get_selectable_models, select_models_from_rows

if TYPE_CHECKING:
    _AIModelAdmin = admin.ModelAdmin[AIModel]
    _AIPromptAdmin = admin.ModelAdmin[AIPrompt]
    _CapabilityProbeAdmin = admin.ModelAdmin[CapabilityProbe]
else:
    _AIModelAdmin = admin.ModelAdmin
    _AIPromptAdmin = admin.ModelAdmin
    _CapabilityProbeAdmin = admin.ModelAdmin

IDENTITY_READONLY = (
    "provider",
    "model_id",
    "is_active",
    "sort_order",
    "openrouter_managed",
    "openrouter_available",
    "model_type",
    "tags",
    "created_at",
    "updated_at",
    "last_synced_at",
    "released_at",
)


@admin.register(AIModel)
class AIModelAdmin(_AIModelAdmin):
    change_list_template = "admin/catalog/aimodel/change_list.html"
    change_form_template = "admin/catalog/aimodel/change_form.html"
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
    search_fields = ("display_name", "model_id")
    ordering = ("sort_order", "display_name")
    readonly_fields = IDENTITY_READONLY
    actions = None

    def get_urls(self) -> list[URLPattern]:
        custom_urls = [
            path(
                "sync/",
                self.admin_site.admin_view(self.sync_models_view),
                name="catalog_aimodel_sync",
            ),
            path(
                "controls/",
                self.admin_site.admin_view(self.controls_view),
                name="catalog_aimodel_controls",
            ),
            path(
                "controls/review/",
                self.admin_site.admin_view(self.controls_review_view),
                name="catalog_aimodel_controls_review",
            ),
            path(
                "controls/apply/",
                self.admin_site.admin_view(self.controls_apply_view),
                name="catalog_aimodel_controls_apply",
            ),
            path(
                "<int:object_id>/probe/",
                self.admin_site.admin_view(self.probe_view),
                name="catalog_aimodel_probe",
            ),
        ]
        return custom_urls + super().get_urls()

    def has_delete_permission(self, request: HttpRequest, obj: AIModel | None = None) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest) -> bool:
        return super().has_add_permission(request) and self.has_change_permission(request)

    def has_probe_permission(self, request: HttpRequest) -> bool:
        return self.has_change_permission(request) and request.user.has_perm(
            "catalog.probe_aimodel"
        )

    def save_model(
        self,
        request: HttpRequest,
        obj: AIModel,
        form: Any,
        change: bool,
    ) -> None:
        if not change:
            obj.is_active = False
        else:
            previous = AIModel.objects.get(pk=obj.pk)
            obj.is_active = previous.is_active
            obj.sort_order = previous.sort_order
            obj.provider = previous.provider
            obj.model_id = previous.model_id
            obj.openrouter_managed = previous.openrouter_managed
            obj.openrouter_available = previous.openrouter_available
            obj.model_type = previous.model_type
            obj.tags = previous.tags
        super().save_model(request, obj, form, change)

    def changelist_view(
        self,
        request: HttpRequest,
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        extra_context = extra_context or {}
        extra_context["controls_url"] = reverse("admin:catalog_aimodel_controls")
        return super().changelist_view(request, extra_context=extra_context)

    def changeform_view(
        self,
        request: HttpRequest,
        object_id: str | None = None,
        form_url: str = "",
        extra_context: dict[str, Any] | None = None,
    ) -> HttpResponse:
        extra_context = extra_context or {}
        if object_id is not None:
            model = get_object_or_404(AIModel, pk=object_id)
            probes = list(model.capability_probes.order_by("-probed_at", "-id")[:10])
            extra_context.update(
                {
                    "recent_probes": probes,
                    "probe_url": reverse(
                        "admin:catalog_aimodel_probe", args=[model.pk]
                    ),
                    "simulated_pass_label": SIMULATED_SUMMARY,
                    "can_probe": self.has_probe_permission(request),
                    "latest_live_probe": next(
                        (
                            probe
                            for probe in probes
                            if probe.executed_runtime_mode == "live"
                            and probe.completed_at is not None
                        ),
                        None,
                    ),
                    "history_url": (
                        reverse("admin:catalog_capabilityprobe_changelist")
                        + f"?ai_model__id__exact={model.pk}"
                    ),
                }
            )
        return super().changeform_view(request, object_id, form_url, extra_context)

    def sync_models_view(self, request: HttpRequest) -> HttpResponse:
        if not self.has_change_permission(request):
            raise PermissionDenied
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

    def controls_view(self, request: HttpRequest) -> HttpResponse:
        if not self.has_view_permission(request):
            raise PermissionDenied
        return self._controls_page(request)

    def controls_review_view(self, request: HttpRequest) -> HttpResponse:
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_change_permission(request):
            raise PermissionDenied
        try:
            changes = parse_review_changes(request.POST)
            preview = preview_review(changes)
        except CatalogControlError as exc:
            self.message_user(request, exc.message, level=messages.ERROR)
            response = self._controls_page(request, status=exc.status)
            return response
        control = CatalogAdminControl.objects.filter(
            pk=CatalogAdminControl.SINGLETON_PK
        ).first()
        if control is None:
            self.message_user(
                request,
                "Catalog coordination state is missing.",
                level=messages.ERROR,
            )
            return self._controls_page(request, status=409)
        actor_id = request.user.pk
        if actor_id is None:
            raise PermissionDenied
        token = sign_review_token(
            actor_id=actor_id,
            revision=control.revision,
            dynamic_enabled=bool(
                getattr(settings, "DYNAMIC_FREE_MODEL_CATALOG_ENABLED", False)
            ),
            changes=changes,
        )
        return self._controls_page(
            request,
            preview=preview,
            review_token=token,
            pending_changes=changes,
        )

    def controls_apply_view(self, request: HttpRequest) -> HttpResponse:
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_change_permission(request):
            raise PermissionDenied
        token = request.POST.get("review_token", "")
        actor_id = request.user.pk
        if actor_id is None:
            raise PermissionDenied
        try:
            apply_reviewed_token(
                token=token,
                actor_id=actor_id,
                has_row_change_permission=self.has_change_permission(request),
            )
        except CatalogControlError as exc:
            self.message_user(request, exc.message, level=messages.ERROR)
            response = self._controls_page(request, status=exc.status)
            return response
        self.message_user(
            request,
            "Reviewed catalog activation and fallback order were applied.",
            level=messages.SUCCESS,
        )
        return redirect(reverse("admin:catalog_aimodel_controls"))

    def probe_view(self, request: HttpRequest, object_id: int) -> HttpResponse:
        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        if not self.has_probe_permission(request):
            raise PermissionDenied
        model = get_object_or_404(AIModel, pk=object_id)
        requested_mode = request.POST.get("mode", "fake")
        if requested_mode not in {"fake", "live"}:
            requested_mode = "fake"
        try:
            probe = run_aimodel_probe(
                model=model,
                requested_mode=requested_mode,
                actor_id=request.user.pk,
                live_sentinel_value=os.environ.get(LIVE_SENTINEL),
            )
        except CatalogControlError as exc:
            self.message_user(request, exc.message, level=messages.ERROR)
            return self._probe_error_response(request, model, exc)
        self.message_user(request, probe.summary, level=messages.SUCCESS)
        return redirect(reverse("admin:catalog_aimodel_change", args=[model.pk]))

    def _probe_error_response(
        self,
        request: HttpRequest,
        model: AIModel,
        exc: CatalogControlError,
    ) -> HttpResponse:
        extra = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "original": model,
            "recent_probes": list(model.capability_probes.order_by("-probed_at", "-id")[:10]),
            "probe_url": reverse("admin:catalog_aimodel_probe", args=[model.pk]),
            "simulated_pass_label": SIMULATED_SUMMARY,
            "can_probe": self.has_probe_permission(request),
        }
        original_method = request.method
        request.method = "GET"
        try:
            rendered = super().changeform_view(request, str(model.pk), "", extra)
        finally:
            request.method = original_method
        rendered.status_code = exc.status
        return rendered

    def _controls_page(
        self,
        request: HttpRequest,
        *,
        preview: dict[str, Any] | None = None,
        review_token: str | None = None,
        pending_changes: list[CatalogChange] | None = None,
        status: int = 200,
    ) -> HttpResponse:
        rows = list(AIModel.objects.order_by("sort_order", "id")[:100])
        now = django_timezone.now()
        reviewed = ordering_reviewed()
        flag_off = select_models_from_rows(
            list(AIModel.objects.all()),
            dynamic_enabled=False,
            ordering_reviewed=reviewed,
            now=now,
        )
        flag_on = select_models_from_rows(
            list(AIModel.objects.all()),
            dynamic_enabled=True,
            ordering_reviewed=reviewed,
            now=now,
        )
        live = get_selectable_models()
        pending_by_id = {
            change.model_id: change for change in (pending_changes or [])
        }
        editor_rows = []
        for model in rows:
            change = pending_by_id.get(model.pk)
            editor_rows.append(
                {
                    "model": model,
                    "is_active": change.is_active if change is not None else model.is_active,
                    "sort_order": change.sort_order if change is not None else model.sort_order,
                }
            )
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "title": "Review fallback order and activation",
            "rows": editor_rows,
            "pending_by_id": pending_by_id,
            "flag_off": flag_off,
            "flag_on": flag_on,
            "live_selectable": live,
            "flagship_off": flag_off[0] if flag_off else None,
            "flagship_on": flag_on[0] if flag_on else None,
            "ordering_reviewed": reviewed,
            "preview": preview,
            "review_token": review_token,
            "can_change": self.has_change_permission(request),
            "review_url": reverse("admin:catalog_aimodel_controls_review"),
            "apply_url": reverse("admin:catalog_aimodel_controls_apply"),
            "changelist_url": reverse("admin:catalog_aimodel_changelist"),
            "fingerprint": catalog_fingerprint(
                revision=(
                    CatalogAdminControl.objects.filter(
                        pk=CatalogAdminControl.SINGLETON_PK
                    )
                    .values_list("revision", flat=True)
                    .first()
                    or 0
                )
            ),
        }
        response = TemplateResponse(
            request, "admin/catalog/aimodel/controls.html", context
        )
        response.status_code = status
        return response


@admin.register(CapabilityProbe)
class CapabilityProbeAdmin(_CapabilityProbeAdmin):
    list_display = (
        "probed_at",
        "ai_model",
        "status",
        "executed_runtime_mode",
        "reason_code",
        "latency_ms",
        "outbound_count",
        "summary",
    )
    list_filter = ("ai_model", "status", "executed_runtime_mode", "probed_at")
    ordering = ("-probed_at", "-id")
    list_per_page = 50
    readonly_fields = (
        "ai_model",
        "requested_by",
        "probed_at",
        "completed_at",
        "provider_snapshot",
        "model_id_snapshot",
        "status",
        "latency_ms",
        "outbound_count",
        "executed_runtime_mode",
        "reason_code",
        "summary",
    )
    actions = None

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self, request: HttpRequest, obj: CapabilityProbe | None = None
    ) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: CapabilityProbe | None = None
    ) -> bool:
        return False

    def has_view_permission(
        self, request: HttpRequest, obj: CapabilityProbe | None = None
    ) -> bool:
        return request.user.has_perm("catalog.view_capabilityprobe")


@admin.register(AIPrompt)
class AIPromptAdmin(_AIPromptAdmin):
    list_display = ("name", "fitness", "is_active", "sort_order", "updated_at")
    list_editable = ("fitness", "is_active", "sort_order")
    search_fields = ("name", "prompt")
    ordering = ("sort_order", "name")
    readonly_fields = ("created_at", "updated_at")
