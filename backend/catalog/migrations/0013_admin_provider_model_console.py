from typing import Any

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_catalog_admin_control(apps: Any, schema_editor: Any) -> None:
    CatalogAdminControl = apps.get_model("catalog", "CatalogAdminControl")
    CatalogAdminControl.objects.get_or_create(
        pk=1,
        defaults={"revision": 0, "ordering_reviewed": False, "probe_not_before_at": None},
    )


def unseed_catalog_admin_control(apps: Any, schema_editor: Any) -> None:
    CatalogAdminControl = apps.get_model("catalog", "CatalogAdminControl")
    CatalogAdminControl.objects.filter(pk=1).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0012_multi_provider_free_rivals"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterModelOptions(
            name="aimodel",
            options={
                "ordering": ["sort_order", "display_name"],
                "permissions": [("probe_aimodel", "Can probe AI model capability")],
            },
        ),
        migrations.CreateModel(
            name="CatalogAdminControl",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("revision", models.PositiveIntegerField(default=0)),
                ("ordering_reviewed", models.BooleanField(default=False)),
                ("probe_not_before_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "catalog_admin_control",
            },
        ),
        migrations.CreateModel(
            name="CapabilityProbe",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("probed_at", models.DateTimeField()),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("provider_snapshot", models.CharField(max_length=50)),
                ("model_id_snapshot", models.CharField(max_length=200)),
                ("status", models.CharField(max_length=32)),
                ("latency_ms", models.PositiveIntegerField(blank=True, null=True)),
                ("outbound_count", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("executed_runtime_mode", models.CharField(max_length=8)),
                ("reason_code", models.CharField(max_length=32)),
                ("summary", models.CharField(max_length=200)),
                (
                    "ai_model",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="capability_probes",
                        to="catalog.aimodel",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="capability_probes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "catalog_capability_probe",
                "ordering": ["-probed_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="capabilityprobe",
            index=models.Index(
                fields=["ai_model", "-probed_at", "-id"],
                name="catalog_probe_recent_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="capabilityprobe",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "status__in",
                        [
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
                        ],
                    )
                ),
                name="catalog_capability_probe_status",
            ),
        ),
        migrations.AddConstraint(
            model_name="capabilityprobe",
            constraint=models.CheckConstraint(
                condition=models.Q(("executed_runtime_mode__in", ["fake", "live"])),
                name="catalog_capability_probe_mode",
            ),
        ),
        migrations.AddConstraint(
            model_name="capabilityprobe",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    (
                        "reason_code__in",
                        [
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
                        ],
                    )
                ),
                name="catalog_capability_probe_reason",
            ),
        ),
        migrations.AddConstraint(
            model_name="capabilityprobe",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("latency_ms__isnull", True),
                    models.Q(("latency_ms__gte", 0), ("latency_ms__lte", 300000)),
                    _connector="OR",
                ),
                name="catalog_capability_probe_latency",
            ),
        ),
        migrations.AddConstraint(
            model_name="capabilityprobe",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("outbound_count__isnull", True),
                    models.Q(("outbound_count__gte", 0), ("outbound_count__lte", 4)),
                    _connector="OR",
                ),
                name="catalog_capability_probe_outbound",
            ),
        ),
        migrations.AddConstraint(
            model_name="capabilityprobe",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("executed_runtime_mode", "fake"), _negated=True),
                    ("outbound_count", 0),
                    _connector="OR",
                ),
                name="catalog_capability_probe_fake_zero",
            ),
        ),
        migrations.RunPython(seed_catalog_admin_control, unseed_catalog_admin_control),
    ]
