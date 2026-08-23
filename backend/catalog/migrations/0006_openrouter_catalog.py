from typing import Any

from django.db import migrations, models

# Frozen at migration time; keep aligned with catalog.selection.FREE_RIVAL_IDS.
SHORTLIST_IDS = [
    "google/gemma-4-31b-it:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
    "z-ai/glm-5.2:free",
    "google/gemma-4-26b-a4b-it:free",
]


def deactivate_non_shortlist(apps: Any, schema_editor: Any) -> None:
    AIModel = apps.get_model("catalog", "AIModel")
    AIModel.objects.exclude(model_id__in=SHORTLIST_IDS).update(
        openrouter_managed=False,
        openrouter_available=False,
        is_active=False,
    )


def noop_reverse(apps: Any, schema_editor: Any) -> None:
    # Prior flag values were not snapshotted. Reverse restores field names only.
    return


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0005_seed_grandmaster_prompt"),
    ]

    operations = [
        migrations.RenameField(
            model_name="aimodel",
            old_name="gateway_managed",
            new_name="openrouter_managed",
        ),
        migrations.RenameField(
            model_name="aimodel",
            old_name="gateway_available",
            new_name="openrouter_available",
        ),
        migrations.AlterField(
            model_name="aimodel",
            name="openrouter_managed",
            field=models.BooleanField(
                default=False,
                help_text="If enabled, sync updates display name and description from OpenRouter.",
            ),
        ),
        migrations.AlterField(
            model_name="aimodel",
            name="openrouter_available",
            field=models.BooleanField(
                default=True,
                help_text="True when the model exists in the latest OpenRouter free catalog sync.",
            ),
        ),
        migrations.AlterField(
            model_name="aimodel",
            name="model_id",
            field=models.CharField(
                help_text="Native OpenRouter id, e.g. 'google/gemma-4-31b-it:free'",
                max_length=200,
                unique=True,
            ),
        ),
        migrations.RunPython(deactivate_non_shortlist, noop_reverse),
    ]
