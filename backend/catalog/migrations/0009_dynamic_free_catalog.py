from functools import reduce
from operator import or_
from typing import Any

from django.db import migrations
from django.db.models import Q

# Frozen at migration time; keep aligned with catalog.selection.FREE_RIVAL_PAIRS.
CURATED_PAIRS = (
    ("openrouter", "google/gemma-4-31b-it:free"),
    ("nvidia-nim", "nvidia/nemotron-3-super-120b-a12b"),
    ("openrouter", "nvidia/nemotron-3-super-120b-a12b:free"),
    ("openrouter", "z-ai/glm-5.2:free"),
    ("openrouter", "google/gemma-4-26b-a4b-it:free"),
)


def _curated_q() -> Q:
    return reduce(
        or_,
        [Q(provider=provider, model_id=model_id) for provider, model_id in CURATED_PAIRS],
    )


def _non_curated_openrouter_free(AIModel: Any) -> Any:
    return (
        AIModel.objects.exclude(_curated_q())
        .filter(provider="openrouter")
        .filter(model_id__endswith=":free")
        .exclude(model_id="openrouter/free")
    )


def reenable_code_disabled_non_curated(apps: Any, schema_editor: Any) -> None:
    AIModel = apps.get_model("catalog", "AIModel")
    for obj in _non_curated_openrouter_free(AIModel).iterator():
        changed_fields: list[str] = []
        if not obj.is_active:
            obj.is_active = True
            changed_fields.append("is_active")
        if not obj.openrouter_managed:
            obj.openrouter_managed = True
            changed_fields.append("openrouter_managed")
        if changed_fields:
            obj.save(update_fields=changed_fields)


def reverse_reenable_code_disabled_non_curated(apps: Any, schema_editor: Any) -> None:
    AIModel = apps.get_model("catalog", "AIModel")
    for obj in _non_curated_openrouter_free(AIModel).iterator():
        if obj.is_active:
            obj.is_active = False
            obj.save(update_fields=["is_active"])


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0008_remove_aimodel_money_fields"),
    ]

    operations = [
        migrations.RunPython(
            reenable_code_disabled_non_curated,
            reverse_reenable_code_disabled_non_curated,
        ),
    ]
