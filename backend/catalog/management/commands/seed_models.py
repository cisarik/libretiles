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
        "model_id": "openai/gpt-4o-mini",
        "display_name": "GPT-4o Mini",
        "description": "Fast and affordable. Great for casual games.",
        "quality_tier": "basic",
        "cost_per_game": "1.00",
        "sort_order": 10,
    },
    {
        "provider": "openai",
        "model_id": "openai/gpt-4o",
        "display_name": "GPT-4o",
        "description": "Strong all-rounder. Balanced speed and quality.",
        "quality_tier": "standard",
        "cost_per_game": "3.00",
        "sort_order": 20,
    },
    {
        "provider": "openai",
        "model_id": "openai/gpt-5.2",
        "display_name": "GPT-5.2",
        "description": "Latest flagship. Strongest play, longest thinking time.",
        "quality_tier": "elite",
        "cost_per_game": "10.00",
        "sort_order": 30,
    },
    {
        "provider": "google",
        "model_id": "google/gemini-2.5-pro",
        "display_name": "Gemini 2.5 Pro",
        "description": "Google's most capable model. Deep strategic reasoning.",
        "quality_tier": "premium",
        "cost_per_game": "5.00",
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
