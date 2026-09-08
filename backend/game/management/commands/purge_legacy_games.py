from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from game.models import GameSession


class Command(BaseCommand):
    help = "Delete legacy GameSession rows that predate replay state capture."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Delete without an interactive confirmation prompt.",
        )

    def handle(self, *args: object, **options: object) -> None:
        queryset = GameSession.objects.filter(replay_initial_state__isnull=True)
        count = queryset.count()
        if count == 0:
            self.stdout.write("No legacy games found.")
            return
        if not options["yes"]:
            answer = input(f"Delete {count} legacy game(s)? Type 'yes' to continue: ")
            if answer.strip().lower() != "yes":
                raise CommandError("Purge cancelled.")
        with transaction.atomic():
            deleted, _ = queryset.delete()
        self.stdout.write(self.style.SUCCESS(f"Purged {count} legacy game(s) ({deleted} rows)."))
