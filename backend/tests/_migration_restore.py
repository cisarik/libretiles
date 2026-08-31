"""Test-only teardown: restore Django apps to the current migration leaf.

Migration-test subjects keep their hardcoded migrate_from / migrate_to / reverse
targets. Teardown must never pin those names; it resolves the live graph leaf.
"""

from __future__ import annotations

from django.core.management import call_command


def restore_apps_to_leaf(*app_labels: str) -> None:
    """Migrate each app to its current leaf. Safe to call from a test finally."""
    for app_label in app_labels:
        call_command("migrate", app_label, verbosity=0)
