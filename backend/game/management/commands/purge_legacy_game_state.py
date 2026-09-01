"""Fail-closed one-time purge of development game-state rows.

Usage:
    python manage.py purge_legacy_game_state --dry-run
    ALLOW_DESTRUCTIVE_GAME_STATE_RESET=true python manage.py purge_legacy_game_state
"""

from __future__ import annotations

import logging

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.db import transaction

from game.models import ChatMessage, ConsumedWsTicket, GameSession, Move, PlayerSlot

logger = logging.getLogger("game")

_FLAG_NAME = "ALLOW_DESTRUCTIVE_GAME_STATE_RESET"
_PURGE_MODELS = (
    ChatMessage,
    Move,
    PlayerSlot,
    GameSession,
    ConsumedWsTicket,
)
_TABLE_NAMES = ", ".join(model._meta.db_table for model in _PURGE_MODELS)


def _table_counts() -> dict[str, int]:
    return {model._meta.db_table: int(model.objects.count()) for model in _PURGE_MODELS}


class Command(BaseCommand):
    help = (
        "Delete development rows from the five game-state tables, fail-closed. "
        "Does not change schema and does not run during migrate."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report pre counts and the intended action; delete nothing.",
        )

    def handle(self, *args: object, **options: object) -> None:
        from django.conf import settings

        dry_run = bool(options.get("dry_run"))
        pre = _table_counts()
        self.stdout.write(f"pre-purge counts: {pre}")
        logger.info("purge_legacy_game_state pre-purge counts: %s", pre)

        if all(count == 0 for count in pre.values()):
            self.stdout.write(
                "no-op: all five game-state tables already empty; nothing deleted."
            )
            logger.info("purge_legacy_game_state no-op: all five already empty")
            return

        if dry_run:
            self.stdout.write(
                "dry-run: would delete rows from "
                f"{_TABLE_NAMES} in order ChatMessage, Move, PlayerSlot, "
                "GameSession, ConsumedWsTicket; no rows deleted."
            )
            logger.info("purge_legacy_game_state dry-run; no rows deleted")
            return

        if not getattr(settings, _FLAG_NAME, False):
            raise CommandError(
                f"Refusing to purge non-empty game state because {_FLAG_NAME} is "
                f"false. Tables: {_TABLE_NAMES}."
            )

        with transaction.atomic():
            for model in _PURGE_MODELS:
                deleted, _per_table = model.objects.all().delete()
                line = f"deleted {deleted} rows from {model.__name__}"
                self.stdout.write(line)
                logger.info("purge_legacy_game_state %s", line)
            post = _table_counts()
            self.stdout.write(f"post-purge counts: {post}")
            logger.info("purge_legacy_game_state post-purge counts: %s", post)
            if any(count != 0 for count in post.values()):
                raise CommandError(f"purge left non-empty tables: {post}")
