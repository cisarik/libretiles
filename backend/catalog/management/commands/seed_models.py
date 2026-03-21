"""
Seed default AI models into the catalog.

Usage:
    python manage.py seed_models          # insert only (skip existing)
    python manage.py seed_models --reset  # delete all models, then re-insert

Models are configured for Vercel AI Gateway naming convention (provider/model).
Admins can further customize models via Django Admin (/admin/catalog/aimodel/).
"""

from django.core.management.base import BaseCommand

from catalog.models import AIModel

DEFAULT_MODELS = [
    {
        "provider": "openai",
        "model_id": "openai/gpt-5.4",
        "display_name": "GPT-5.4",
        "description": "Current flagship default for strongest general play.",
        "quality_tier": "elite",
        "cost_per_game": "3.50",
        "sort_order": 10,
    },
    {
        "provider": "openai",
        "model_id": "openai/gpt-5.4-mini",
        "display_name": "GPT-5.4 Mini",
        "description": "Cheaper GPT-5.4 family option with strong move quality.",
        "quality_tier": "standard",
        "cost_per_game": "1.50",
        "sort_order": 20,
    },
    {
        "provider": "openai",
        "model_id": "openai/gpt-5.4-pro",
        "display_name": "GPT-5.4 Pro",
        "description": "Premium tier for maximum strength at a much higher token price.",
        "quality_tier": "elite",
        "cost_per_game": "20.00",
        "sort_order": 30,
    },
    {
        "provider": "anthropic",
        "model_id": "anthropic/claude-opus-4.1",
        "display_name": "Claude Opus 4.1",
        "description": "Very expensive strategic model for long-form reasoning.",
        "quality_tier": "premium",
        "cost_per_game": "8.00",
        "sort_order": 40,
    },
    {
        "provider": "google",
        "model_id": "google/gemini-2.5-flash",
        "display_name": "Gemini 2.5 Flash",
        "description": "Fast Google model. Good value for money.",
        "quality_tier": "standard",
        "cost_per_game": "2.00",
        "sort_order": 50,
    },
    {
        "provider": "anthropic",
        "model_id": "anthropic/claude-sonnet-4.6",
        "display_name": "Claude Sonnet 4.6",
        "description": "Anthropic's balanced model. Thoughtful, creative play.",
        "quality_tier": "premium",
        "cost_per_game": "5.00",
        "sort_order": 60,
    },
]


class Command(BaseCommand):
    help = "Seed default AI models into the catalog"

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete all existing models before seeding",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if options["reset"]:
            deleted, _ = AIModel.objects.all().delete()
            self.stdout.write(f"Deleted {deleted} existing model(s).")

        created = 0
        skipped = 0
        for data in DEFAULT_MODELS:
            _, was_created = AIModel.objects.get_or_create(
                model_id=data["model_id"],
                defaults=data,
            )
            if was_created:
                created += 1
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(f"Done: {created} created, {skipped} skipped (already exist).")
        )
