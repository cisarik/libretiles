"""
Seed the curated OpenRouter free-rival catalog.

Usage:
    python manage.py seed_models
"""

from django.core.management.base import BaseCommand

from catalog.models import AIModel
from catalog.selection import DEFAULT_FREE_MODEL_ID, FREE_RIVAL_IDS, SHORTLIST_SORT_ORDER

CURATED_MODELS = [
    {
        "model_id": "google/gemma-4-31b-it:free",
        "display_name": "Gemma 4 31B IT",
        "description": "Default free OpenRouter rival for Libre Tiles.",
    },
    {
        "model_id": "nvidia/nemotron-3-super-120b-a12b:free",
        "display_name": "Nemotron 3 Super 120B",
        "description": "NVIDIA free OpenRouter rival with tool calling.",
    },
    {
        "model_id": "z-ai/glm-5.2:free",
        "display_name": "GLM 5.2",
        "description": "Z.AI free OpenRouter rival with tool calling.",
    },
    {
        "model_id": "google/gemma-4-26b-a4b-it:free",
        "display_name": "Gemma 4 26B A4B IT",
        "description": "Smaller Gemma 4 free OpenRouter rival.",
    },
]


class Command(BaseCommand):
    help = "Idempotently seed the four curated OpenRouter free rivals"

    def handle(self, *args: object, **options: object) -> None:
        created = 0
        updated = 0
        for data in CURATED_MODELS:
            model_id = data["model_id"]
            defaults = {
                "provider": "openrouter",
                "display_name": data["display_name"],
                "description": data["description"],
                "quality_tier": "standard",
                "cost_per_game": 0,
                "openrouter_managed": True,
                "openrouter_available": True,
                "model_type": "language",
                "tags": ["tools"],
                "pricing": {"input": "0", "output": "0"},
                "is_active": True,
                "sort_order": SHORTLIST_SORT_ORDER[model_id],
            }
            _, was_created = AIModel.objects.update_or_create(
                model_id=model_id,
                defaults=defaults,
            )
            if was_created:
                created += 1
            else:
                updated += 1

        assert {item["model_id"] for item in CURATED_MODELS} == set(FREE_RIVAL_IDS)
        assert CURATED_MODELS[0]["model_id"] == DEFAULT_FREE_MODEL_ID
        self.stdout.write(
            self.style.SUCCESS(f"Done: {created} created, {updated} updated.")
        )
