"""Prepare direct free rivals without bypassing operator activation."""

from typing import Any

from django.db import migrations
from django.db.models import Q

# Frozen migration-time metadata. Runtime ownership lives in catalog.selection.
PREPARED_MODELS = (
    {
        "provider": "groq",
        "model_id": "openai/gpt-oss-120b",
        "display_name": "GPT-OSS 120B (Groq)",
        "description": "Direct Groq free rival with tool calling.",
        "quality_tier": "elite",
        "sort_order": 1,
    },
    {
        "provider": "google-gemini",
        "model_id": "gemini-3.7-flash",
        "display_name": "Gemini 3.7 Flash",
        "description": "Direct Google Gemini free rival with tool calling.",
        "quality_tier": "premium",
        "sort_order": 2,
    },
    {
        "provider": "cloudflare-workers-ai",
        "model_id": "@cf/zai-org/glm-4.7-flash",
        "display_name": "GLM 4.7 Flash (Cloudflare)",
        "description": "Direct Cloudflare Workers AI free rival with tool calling.",
        "quality_tier": "standard",
        "sort_order": 3,
    },
    {
        "provider": "mistral",
        "model_id": "mistral-small-2603",
        "display_name": "Mistral Small 2603",
        "description": "Direct Mistral free rival with tool calling.",
        "quality_tier": "premium",
        "sort_order": 4,
    },
    {
        "provider": "ibm-watsonx",
        "model_id": "ibm/granite-4-h-small",
        "display_name": "Granite 4 H Small (watsonx.ai)",
        "description": "Direct IBM watsonx.ai Lite rival with tool calling.",
        "quality_tier": "standard",
        "sort_order": 5,
    },
    {
        "provider": "aion",
        "model_id": "aion-labs/aion-3.0-mini",
        "display_name": "Aion 3.0 Mini (Watchlist)",
        "description": "Prepared Aion rival; keep inactive pending capability acceptance.",
        "quality_tier": "standard",
        "sort_order": 100,
    },
    {
        "provider": "huggingface",
        "model_id": "openai/gpt-oss-120b:groq",
        "display_name": "GPT-OSS 120B (Hugging Face Watchlist)",
        "description": (
            "Prepared Hugging Face routed rival; keep inactive pending capability "
            "acceptance."
        ),
        "quality_tier": "standard",
        "sort_order": 110,
    },
)


def prepare_free_rivals(apps: Any, schema_editor: Any) -> None:
    AIModel = apps.get_model("catalog", "AIModel")
    for metadata in PREPARED_MODELS:
        # model_id is globally unique. A same-id provider collision is owner data,
        # so this migration must fail closed and leave it untouched.
        if AIModel.objects.filter(model_id=metadata["model_id"]).exists():
            continue
        AIModel.objects.create(
            **metadata,
            openrouter_managed=False,
            openrouter_available=False,
            model_type="language",
            tags=["tools"],
            is_active=False,
        )


def deactivate_prepared_free_rivals(apps: Any, schema_editor: Any) -> None:
    AIModel = apps.get_model("catalog", "AIModel")
    for metadata in PREPARED_MODELS:
        AIModel.objects.filter(
            Q(provider=metadata["provider"]) & Q(model_id=metadata["model_id"])
        ).update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0011_playable_seeded_prompts"),
    ]

    operations = [
        migrations.RunPython(
            prepare_free_rivals,
            deactivate_prepared_free_rivals,
        ),
    ]
