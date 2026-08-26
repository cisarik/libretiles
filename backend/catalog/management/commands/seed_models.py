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
    DIRECT_FREE_RIVALS,
    FREE_RIVAL_PAIRS,
    NVIDIA_NIM_PROVIDER,
    PREPARED_FREE_RIVAL_PAIRS,
    SHORTLIST_SORT_ORDER,
    WATCHLIST_FREE_RIVALS,
)


class CuratedModel(TypedDict):
    provider: str
    model_id: str
    display_name: str
    description: str
    openrouter_managed: bool
    openrouter_available: bool
    quality_tier: str
    sort_order: int
    is_active_on_create: bool


CURATED_MODELS: list[CuratedModel] = [
    {
        "provider": "openrouter",
        "model_id": "google/gemma-4-31b-it:free",
        "display_name": "Gemma 4 31B IT",
        "description": "Default free OpenRouter rival for Libre Tiles.",
        "openrouter_managed": True,
        "openrouter_available": True,
        "quality_tier": "standard",
        "sort_order": SHORTLIST_SORT_ORDER["google/gemma-4-31b-it:free"],
        "is_active_on_create": True,
    },
    {
        "provider": "nvidia-nim",
        "model_id": "nvidia/nemotron-3-super-120b-a12b",
        "display_name": "Nemotron 3 Super 120B",
        "description": "NVIDIA NIM chat rival with tool calling.",
        "openrouter_managed": False,
        "openrouter_available": False,
        "quality_tier": "standard",
        "sort_order": SHORTLIST_SORT_ORDER["nvidia/nemotron-3-super-120b-a12b"],
        "is_active_on_create": True,
    },
    {
        "provider": "openrouter",
        "model_id": "nvidia/nemotron-3-super-120b-a12b:free",
        "display_name": "Nemotron 3 Super 120B",
        "description": "NVIDIA free OpenRouter rival with tool calling.",
        "openrouter_managed": True,
        "openrouter_available": True,
        "quality_tier": "standard",
        "sort_order": SHORTLIST_SORT_ORDER[
            "nvidia/nemotron-3-super-120b-a12b:free"
        ],
        "is_active_on_create": True,
    },
    {
        "provider": "openrouter",
        "model_id": "z-ai/glm-5.2:free",
        "display_name": "GLM 5.2",
        "description": "Z.AI free OpenRouter rival with tool calling.",
        "openrouter_managed": True,
        "openrouter_available": True,
        "quality_tier": "standard",
        "sort_order": SHORTLIST_SORT_ORDER["z-ai/glm-5.2:free"],
        "is_active_on_create": True,
    },
    {
        "provider": "openrouter",
        "model_id": "google/gemma-4-26b-a4b-it:free",
        "display_name": "Gemma 4 26B A4B IT",
        "description": "Smaller Gemma 4 free OpenRouter rival.",
        "openrouter_managed": True,
        "openrouter_available": True,
        "quality_tier": "standard",
        "sort_order": SHORTLIST_SORT_ORDER["google/gemma-4-26b-a4b-it:free"],
        "is_active_on_create": True,
    },
]

PREPARED_MODELS: list[CuratedModel] = [
    {
        **rival,
        "openrouter_managed": False,
        "openrouter_available": False,
        "is_active_on_create": False,
    }
    for rival in (*DIRECT_FREE_RIVALS, *WATCHLIST_FREE_RIVALS)
]
SEEDED_MODELS: list[CuratedModel] = [*CURATED_MODELS, *PREPARED_MODELS]


class Command(BaseCommand):
    help = "Idempotently seed curated and prepared free rivals"

    def handle(self, *args: object, **options: object) -> None:
        created = 0
        updated = 0
        skipped = 0
        for data in SEEDED_MODELS:
            model_id = data["model_id"]
            provider = data["provider"]
            existing = AIModel.objects.filter(model_id=model_id).first()
            if existing is not None and existing.provider != provider:
                skipped += 1
                continue
            fields = {
                "provider": provider,
                "display_name": data["display_name"],
                "description": data["description"],
                "quality_tier": data["quality_tier"],
                "openrouter_managed": data["openrouter_managed"],
                "openrouter_available": data["openrouter_available"],
                "model_type": "language",
                "tags": ["tools"],
                "sort_order": data["sort_order"],
            }
            if existing is None:
                AIModel.objects.create(
                    model_id=model_id,
                    is_active=data["is_active_on_create"],
                    **fields,
                )
                created += 1
                continue
            for field_name, value in fields.items():
                setattr(existing, field_name, value)
            existing.save()
            updated += 1

        assert {(item["provider"], item["model_id"]) for item in CURATED_MODELS} == set(
            FREE_RIVAL_PAIRS
        )
        assert CURATED_MODELS[0]["model_id"] == DEFAULT_FREE_MODEL_ID
        assert CURATED_MODELS[1]["provider"] == NVIDIA_NIM_PROVIDER
        assert {
            (item["provider"], item["model_id"]) for item in PREPARED_MODELS
        } == set(PREPARED_FREE_RIVAL_PAIRS)
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {created} created, {updated} updated, {skipped} skipped."
            )
        )
