from django.core.management.base import BaseCommand, CommandError

from catalog.openrouter_sync import (
    OPENROUTER_MODELS_URL,
    CatalogSyncAborted,
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
        parser.add_argument(
            "--allow-large-drop",
            action="store_true",
            help=(
                "Write even when the eligible OpenRouter cohort falls by more than "
                "50%% versus the last available catalog. Empty results still abort."
            ),
        )

    def handle(self, *args: object, **options: object) -> None:
        url = options.get("url") or OPENROUTER_MODELS_URL
        if not isinstance(url, str):
            url = OPENROUTER_MODELS_URL
        allow_large_drop = bool(options.get("allow_large_drop"))
        models = fetch_openrouter_models(url=url)
        try:
            stats = sync_openrouter_models(
                models=models,
                allow_large_drop=allow_large_drop,
            )
        except CatalogSyncAborted as exc:
            raise CommandError(str(exc)) from exc
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
