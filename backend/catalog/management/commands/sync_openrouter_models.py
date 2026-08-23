from django.core.management.base import BaseCommand

from catalog.openrouter_sync import (
    OPENROUTER_MODELS_URL,
    fetch_openrouter_models,
    sync_openrouter_models,
)


class Command(BaseCommand):
    help = "Sync free OpenRouter catalog models into the local registry"

    def add_arguments(self, parser) -> None:  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--url",
            default=None,
            help="Override the OpenRouter models endpoint",
        )

    def handle(self, *args: object, **options: object) -> None:
        url = options.get("url") or OPENROUTER_MODELS_URL
        if not isinstance(url, str):
            url = OPENROUTER_MODELS_URL
        models = fetch_openrouter_models(url=url)
        stats = sync_openrouter_models(models=models)
        self.stdout.write(
            self.style.SUCCESS(
                "OpenRouter sync complete: "
                f"{stats['created']} created, "
                f"{stats['updated']} updated, "
                f"{stats['unchanged']} unchanged, "
                f"{stats['disabled']} marked unavailable, "
                f"{stats['total_seen']} eligible models seen."
            )
        )
