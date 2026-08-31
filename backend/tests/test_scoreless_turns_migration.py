from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from tests._migration_restore import restore_apps_to_leaf


class ScorelessTurnsRenameMigrationTest(TransactionTestCase):
    migrate_from = [("game", "0005_remove_money_state")]
    migrate_to = [("game", "0006_rename_consecutive_scoreless_turns")]

    def test_forward_and_reverse_preserve_non_default_value(self) -> None:
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        OldSession = old_apps.get_model("game", "GameSession")
        old_session = OldSession.objects.create(consecutive_passes=5)

        try:
            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_to)
            new_apps = executor.loader.project_state(self.migrate_to).apps
            NewSession = new_apps.get_model("game", "GameSession")
            renamed = NewSession.objects.get(pk=old_session.pk)
            assert renamed.consecutive_scoreless_turns == 5

            executor = MigrationExecutor(connection)
            executor.migrate(self.migrate_from)
            reversed_apps = executor.loader.project_state(self.migrate_from).apps
            ReversedSession = reversed_apps.get_model("game", "GameSession")
            restored = ReversedSession.objects.get(pk=old_session.pk)
            assert restored.consecutive_passes == 5
        finally:
            restore_apps_to_leaf("game")
