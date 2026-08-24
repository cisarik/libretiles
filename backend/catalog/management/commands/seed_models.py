"""
Seed the curated free-rival catalog.

Usage:
    python manage.py seed_models
"""

from typing import TypedDict

from django.core.management.base import BaseCommand

from catalog.models import AIModel
from catalog.selection import (
    DEFAULT_FREE_MODEL_ID,
    FREE_RIVAL_PAIRS,
    NVIDIA_NIM_PROVIDER,
    SHORTLIST_SORT_ORDER,
)


class CuratedModel(TypedDict):
    provider: str
    model_id: str
    display_name: str
    description: str
    openrouter_managed: bool
    openrouter_available: bool


CURATED_MODELS: list[CuratedModel] = [
    {
        "provider": "openrouter",
        "model_id": "google/gemma-4-31b-it:free",
        "display_name": "Gemma 4 31B IT",
        "description": "Default free OpenRouter rival for Libre Tiles.",
        "openrouter_managed": True,
        "openrouter_available": True,
    },
    {
        "provider": "nvidia-nim",
        "model_id": "nvidia/nemotron-3-super-120b-a12b",
        "display_name": "Nemotron 3 Super 120B",
        "description": "NVIDIA NIM chat rival with tool calling.",
        "openrouter_managed": False,
        "openrouter_available": False,
    },
    {
        "provider": "openrouter",
        "model_id": "nvidia/nemotron-3-super-120b-a12b:free",
        "display_name": "Nemotron 3 Super 120B",
        "description": "NVIDIA free OpenRouter rival with tool calling.",
        "openrouter_managed": True,
        "openrouter_available": True,
    },
    {
        "provider": "openrouter",
        "model_id": "z-ai/glm-5.2:free",
        "display_name": "GLM 5.2",
        "description": "Z.AI free OpenRouter rival with tool calling.",
        "openrouter_managed": True,
        "openrouter_available": True,
    },
    {
        "provider": "openrouter",
        "model_id": "google/gemma-4-26b-a4b-it:free",
        "display_name": "Gemma 4 26B A4B IT",
        "description": "Smaller Gemma 4 free OpenRouter rival.",
        "openrouter_managed": True,
        "openrouter_available": True,
    },
]


class Command(BaseCommand):
    help = "Idempotently seed the five curated free rivals"

    def handle(self, *args: object, **options: object) -> None:
        created = 0
        updated = 0
        skipped = 0
        for data in CURATED_MODELS:
            model_id = data["model_id"]
            provider = data["provider"]
            existing = AIModel.objects.filter(model_id=model_id).first()
            if existing is not None and existing.provider != provider:
                skipped += 1
                continue
            defaults = {
                "provider": provider,
                "display_name": data["display_name"],
                "description": data["description"],
                "quality_tier": "standard",
                "cost_per_game": 0,
                "openrouter_managed": data["openrouter_managed"],
                "openrouter_available": data["openrouter_available"],
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

        assert {(item["provider"], item["model_id"]) for item in CURATED_MODELS} == set(
            FREE_RIVAL_PAIRS
        )
        assert CURATED_MODELS[0]["model_id"] == DEFAULT_FREE_MODEL_ID
        assert CURATED_MODELS[1]["provider"] == NVIDIA_NIM_PROVIDER
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created} created, {updated} updated, {skipped} skipped."
            )
        )
