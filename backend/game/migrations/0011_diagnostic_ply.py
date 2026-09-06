"""Persist per-ply diagnostic metrics as DiagnosticPly rows."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("game", "0010_diagnostic_service_account"),
    ]

    operations = [
        migrations.CreateModel(
            name="DiagnosticPly",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("ply_index", models.IntegerField(help_text="0-based ply ordinal within the run")),
                (
                    "position_index",
                    models.IntegerField(
                        blank=True,
                        help_text="Position-set ordinal; None for full-game plies",
                        null=True,
                    ),
                ),
                ("seat_index", models.IntegerField()),
                ("model_id", models.CharField(max_length=200)),
                ("assist_mode", models.CharField(max_length=16)),
                ("score_authority", models.CharField(max_length=16)),
                ("model_authored", models.BooleanField(blank=True, null=True)),
                ("first_validate_valid", models.BooleanField(blank=True, null=True)),
                ("valid_candidate_count", models.IntegerField(blank=True, null=True)),
                ("model_legal_score", models.IntegerField(blank=True, null=True)),
                ("ranked_best_score", models.IntegerField(blank=True, null=True)),
                ("ranked_search_complete", models.BooleanField(blank=True, null=True)),
                ("give_up_while_legal", models.BooleanField(blank=True, null=True)),
                ("playability_status", models.CharField(blank=True, max_length=32, null=True)),
                ("completion_source", models.CharField(blank=True, max_length=64, null=True)),
                ("terminal_cause", models.CharField(blank=True, max_length=64, null=True)),
                ("provider_requests_used", models.IntegerField(blank=True, null=True)),
                ("steps_consumed", models.IntegerField(blank=True, null=True)),
                ("wall_clock_ms", models.IntegerField(blank=True, null=True)),
                ("malformed_or_non_tool", models.BooleanField(blank=True, null=True)),
                ("fallback_attempt_index", models.IntegerField(blank=True, null=True)),
                ("earlier_attempt_failures", models.JSONField(blank=True, null=True)),
                ("executed_runtime_mode", models.CharField(blank=True, max_length=16, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "run",
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name="plies",
                        to="game.diagnosticrun",
                    ),
                ),
            ],
            options={
                "db_table": "game_diagnostic_ply",
                "ordering": ["ply_index"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("run", "ply_index"),
                        name="unique_diagnostic_ply_index",
                    ),
                ],
            },
        ),
    ]
