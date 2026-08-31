import importlib

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from catalog.models import AIPrompt
from tests._migration_restore import restore_apps_to_leaf

_migration = importlib.import_module("catalog.migrations.0011_playable_seeded_prompts")
refresh = _migration.refresh_playable_seeded_prompts
restore = _migration.restore_0010_prompts
NEW_PROMPTS = _migration.NEW_PROMPTS
PRIOR_PROMPTS = _migration.PRIOR_PROMPTS

_CUSTOM_FAST_SEARCH = "Admin customized this preset long ago."
_MUTATED_AFTER_0010 = "Mutated after 0010 so the hash gate must skip this row."


def _reset_rows_to_0010() -> None:
    for name, prior_text in PRIOR_PROMPTS.items():
        AIPrompt.objects.update_or_create(name=name, defaults={"prompt": prior_text})


def _customize_one_row() -> None:
    AIPrompt.objects.filter(name="Fast Search").update(prompt=_CUSTOM_FAST_SEARCH)


class PlayableSeededPromptsForwardTests(TestCase):
    def test_forward_updates_only_hash_matched_0010_rows(self) -> None:
        _reset_rows_to_0010()
        _customize_one_row()
        house = AIPrompt.objects.create(
            name="House Rule", prompt="Custom house text.", sort_order=90
        )

        refresh(apps, None)

        for name, new_text in NEW_PROMPTS.items():
            row = AIPrompt.objects.get(name=name)
            expected = new_text if name != "Fast Search" else _CUSTOM_FAST_SEARCH
            self.assertEqual(row.prompt, expected)
        house.refresh_from_db()
        self.assertEqual(house.prompt, "Custom house text.")

    def test_forward_is_idempotent(self) -> None:
        _reset_rows_to_0010()

        refresh(apps, None)
        first = list(AIPrompt.objects.order_by("name").values_list("name", "prompt"))
        refresh(apps, None)
        second = list(AIPrompt.objects.order_by("name").values_list("name", "prompt"))

        self.assertEqual(second, first)
        for name, new_text in NEW_PROMPTS.items():
            self.assertEqual(AIPrompt.objects.get(name=name).prompt, new_text)

    def test_hash_gate_skips_row_mutated_after_0010(self) -> None:
        _reset_rows_to_0010()
        AIPrompt.objects.filter(name="Grandmaster").update(prompt=_MUTATED_AFTER_0010)

        refresh(apps, None)

        self.assertEqual(
            AIPrompt.objects.get(name="Grandmaster").prompt, _MUTATED_AFTER_0010
        )
        self.assertEqual(
            AIPrompt.objects.get(name="Initial").prompt, NEW_PROMPTS["Initial"]
        )


class PlayableSeededPromptsRoundTripTests(TestCase):
    def test_reverse_restores_0010_text_only_for_updated_rows(self) -> None:
        _reset_rows_to_0010()
        _customize_one_row()

        refresh(apps, None)
        restore(apps, None)

        for name in NEW_PROMPTS:
            row = AIPrompt.objects.get(name=name)
            if name == "Fast Search":
                self.assertEqual(row.prompt, _CUSTOM_FAST_SEARCH)
            else:
                self.assertEqual(row.prompt, PRIOR_PROMPTS[name])

    def test_customized_row_survives_round_trip(self) -> None:
        _reset_rows_to_0010()
        _customize_one_row()
        ids_before = set(AIPrompt.objects.values_list("id", flat=True))

        refresh(apps, None)
        restore(apps, None)

        self.assertEqual(set(AIPrompt.objects.values_list("id", flat=True)), ids_before)
        self.assertEqual(
            AIPrompt.objects.get(name="Fast Search").prompt, _CUSTOM_FAST_SEARCH
        )


class PlayableSeededPromptLiveContentTests(TestCase):
    def test_post_migrate_rows_hold_search_profiles(self) -> None:
        for name, text in NEW_PROMPTS.items():
            row = AIPrompt.objects.get(name=name)
            self.assertEqual(row.prompt, text)
            self.assertTrue(text.startswith("SEARCH PROFILE —"))
            self.assertNotIn('"action"', text)
            self.assertNotIn("OUTPUT FORMAT", text)


class PlayableSeededPromptsMigrateCommandTests(TransactionTestCase):
    def test_backward_then_forward_via_migrate_is_reversible(self) -> None:
        _reset_rows_to_0010()
        refresh(apps, None)
        for name, text in NEW_PROMPTS.items():
            self.assertEqual(AIPrompt.objects.get(name=name).prompt, text)
        AIPrompt.objects.filter(name="Short Hooks").update(prompt="Admin edited Short Hooks.")

        try:
            call_command("migrate", "catalog", "0010_refresh_seeded_prompts", verbosity=0)
            for name in NEW_PROMPTS:
                row = AIPrompt.objects.get(name=name)
                if name == "Short Hooks":
                    self.assertEqual(row.prompt, "Admin edited Short Hooks.")
                else:
                    self.assertEqual(row.prompt, PRIOR_PROMPTS[name])

            call_command("migrate", "catalog", verbosity=0)
            for name, text in NEW_PROMPTS.items():
                row = AIPrompt.objects.get(name=name)
                if name == "Short Hooks":
                    self.assertEqual(row.prompt, "Admin edited Short Hooks.")
                else:
                    self.assertEqual(row.prompt, text)
        finally:
            restore_apps_to_leaf("catalog")
