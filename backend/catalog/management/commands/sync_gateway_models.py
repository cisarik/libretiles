from django.core.management.base import BaseCommand

from catalog.gateway_sync import GATEWAY_MODELS_URL, fetch_gateway_models, sync_gateway_models


class Command(BaseCommand):
    help = "Sync playable AI models from the Vercel AI Gateway catalog"

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--activate-new",
            action="store_true",
            help="Activate newly discovered models automatically",
        )
        parser.add_argument(
            "--url",
            default=None,
            help="Override the AI Gateway models endpoint",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        models = fetch_gateway_models(url=options["url"] or GATEWAY_MODELS_URL)
        stats = sync_gateway_models(
            models=models,
            activate_new=options["activate_new"],
        )
        self.stdout.write(
            self.style.SUCCESS(
                "Gateway sync complete: "
                f"{stats['created']} created, "
                f"{stats['updated']} updated, "
                f"{stats['unchanged']} unchanged, "
                f"{stats['disabled']} marked unavailable, "
                f"{stats['total_seen']} language models seen."
            )
        )
