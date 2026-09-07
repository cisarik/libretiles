from django.conf import settings
from django.db import models
from django.db.models import CheckConstraint, Q


PROVIDER_CAPABILITY_STATUSES = (
    "pass",
    "not_configured",
    "auth_failed",
    "rate_limited",
    "model_unavailable",
    "named_tool_unsupported",
    "tool_continuation_failed",
    "schema_failed",
    "timeout",
    "unknown",
)
CAPABILITY_PROBE_MODES = ("fake", "live")
CAPABILITY_PROBE_REASON_CODES = (
    "simulated",
    "incomplete",
    "live_disabled",
    "not_configured",
    "request_limit",
    "timeout",
    "worker_unavailable",
    "malformed_output",
    "pair_mismatch",
    "mode_mismatch",
    "capability",
    "throttled",
    "unknown",
)
MAX_PROBE_LATENCY_MS = 300_000
MAX_PROBE_OUTBOUND_COUNT = 4
MAX_PROBES_PER_MODEL = 100


class AIModel(models.Model):
    """AI model available for gameplay, configured by admin."""

    QUALITY_CHOICES = [
        ("basic", "Basic"),
        ("standard", "Standard"),
        ("premium", "Premium"),
        ("elite", "Elite"),
    ]

    provider = models.CharField(max_length=50)
    model_id = models.CharField(
        max_length=200,
        unique=True,
        help_text=(
            "Native model id for this provider, "
            "e.g. 'google/gemma-4-31b-it:free' or 'nvidia/nemotron-3-super-120b-a12b'"
        ),
    )
    display_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    quality_tier = models.CharField(max_length=20, choices=QUALITY_CHOICES, default="standard")
    openrouter_managed = models.BooleanField(
        default=False,
        help_text="If enabled, sync updates display name and description from OpenRouter.",
    )
    openrouter_available = models.BooleanField(
        default=True,
        help_text="True when the model exists in the latest OpenRouter free catalog sync.",
    )
    model_type = models.CharField(max_length=20, blank=True, default="language")
    context_window = models.PositiveIntegerField(null=True, blank=True)
    max_tokens = models.PositiveIntegerField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    released_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "display_name"]
        db_table = "catalog_ai_model"
        permissions = [
            ("probe_aimodel", "Can probe AI model capability"),
        ]

    def __str__(self) -> str:
        return f"{self.display_name} ({self.provider})"


class AIPrompt(models.Model):
    """Prompt preset available for AI move generation."""

    name = models.CharField(max_length=100, unique=True)
    prompt = models.TextField()
    fitness = models.FloatField(default=0.0)
    is_active = models.BooleanField(default=True)
    sort_order = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name"]
        db_table = "catalog_ai_prompt"

    def __str__(self) -> str:
        return self.name


class CatalogAdminControl(models.Model):
    """Singleton write-coordination row for reviewed catalog mutations."""

    SINGLETON_PK = 1

    revision = models.PositiveIntegerField(default=0)
    ordering_reviewed = models.BooleanField(default=False)
    probe_not_before_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "catalog_admin_control"

    def __str__(self) -> str:
        return f"CatalogAdminControl(revision={self.revision})"


class CapabilityProbe(models.Model):
    """Bounded capability observation for one catalog AIModel row."""

    ai_model = models.ForeignKey(
        AIModel,
        on_delete=models.PROTECT,
        related_name="capability_probes",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capability_probes",
    )
    probed_at = models.DateTimeField()
    completed_at = models.DateTimeField(null=True, blank=True)
    provider_snapshot = models.CharField(max_length=50)
    model_id_snapshot = models.CharField(max_length=200)
    status = models.CharField(max_length=32)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    outbound_count = models.PositiveSmallIntegerField(null=True, blank=True)
    executed_runtime_mode = models.CharField(max_length=8)
    reason_code = models.CharField(max_length=32)
    summary = models.CharField(max_length=200)

    class Meta:
        db_table = "catalog_capability_probe"
        ordering = ["-probed_at", "-id"]
        indexes = [
            models.Index(
                fields=["ai_model", "-probed_at", "-id"],
                name="catalog_probe_recent_idx",
            ),
        ]
        constraints = [
            CheckConstraint(
                condition=Q(status__in=PROVIDER_CAPABILITY_STATUSES),
                name="catalog_capability_probe_status",
            ),
            CheckConstraint(
                condition=Q(executed_runtime_mode__in=CAPABILITY_PROBE_MODES),
                name="catalog_capability_probe_mode",
            ),
            CheckConstraint(
                condition=Q(reason_code__in=CAPABILITY_PROBE_REASON_CODES),
                name="catalog_capability_probe_reason",
            ),
            CheckConstraint(
                condition=Q(latency_ms__isnull=True)
                | Q(latency_ms__gte=0, latency_ms__lte=MAX_PROBE_LATENCY_MS),
                name="catalog_capability_probe_latency",
            ),
            CheckConstraint(
                condition=Q(outbound_count__isnull=True)
                | Q(
                    outbound_count__gte=0,
                    outbound_count__lte=MAX_PROBE_OUTBOUND_COUNT,
                ),
                name="catalog_capability_probe_outbound",
            ),
            CheckConstraint(
                condition=~Q(executed_runtime_mode="fake")
                | Q(outbound_count=0),
                name="catalog_capability_probe_fake_zero",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.provider_snapshot}/{self.model_id_snapshot} "
            f"{self.status} ({self.executed_runtime_mode})"
        )
