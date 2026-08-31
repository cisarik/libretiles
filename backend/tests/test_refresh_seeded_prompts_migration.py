import importlib
import re

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from catalog.models import AIModel, AIPrompt
from game.models import GameSession
from tests._migration_restore import restore_apps_to_leaf

_migration = importlib.import_module("catalog.migrations.0010_refresh_seeded_prompts")
refresh = _migration.refresh_seeded_prompts
restore = _migration.restore_prior_prompts
NEW_PROMPTS = _migration.NEW_PROMPTS
PRIOR_PROMPTS = _migration.PRIOR_PROMPTS

_CUSTOM_FAST_SEARCH = "Admin customized this preset long ago."
_ADMIN_EDIT = "Admin edited Short Hooks."
_MONEY_PATTERN = re.compile(r"USD|\$\d|sponsor|credit|bonus", re.I)


def _reset_rows_to_prior() -> None:
    for name, prior_text in PRIOR_PROMPTS.items():
        AIPrompt.objects.filter(name=name).update(prompt=prior_text)


def _ensure_rows_at_prior() -> None:
    """Self-sufficient seeding: earlier TransactionTestCase tests may have
    flushed the seeded prompt rows from the shared test database."""
    for name, prior_text in PRIOR_PROMPTS.items():
        AIPrompt.objects.update_or_create(name=name, defaults={"prompt": prior_text})


def _customize_one_row() -> None:
    AIPrompt.objects.filter(name="Fast Search").update(prompt=_CUSTOM_FAST_SEARCH)


class RefreshSeededPromptsForwardTests(TestCase):
    def test_forward_updates_only_hash_matched_seeded_rows(self) -> None:
        _reset_rows_to_prior()
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

    def test_forward_is_a_noop_when_all_rows_diverged(self) -> None:
        AIPrompt.objects.all().update(prompt="Rewritten by admin.")
        before = list(AIPrompt.objects.order_by("name").values_list("name", "prompt"))

        refresh(apps, None)

        after = list(AIPrompt.objects.order_by("name").values_list("name", "prompt"))
        self.assertEqual(after, before)


class RefreshSeededPromptsRoundTripTests(TestCase):
    def test_reverse_restores_prior_text_only_for_updated_rows(self) -> None:
        _reset_rows_to_prior()
        _customize_one_row()

        refresh(apps, None)
        restore(apps, None)

        for name in NEW_PROMPTS:
            row = AIPrompt.objects.get(name=name)
            if name == "Fast Search":
                self.assertEqual(row.prompt, _CUSTOM_FAST_SEARCH)
            else:
                self.assertEqual(row.prompt, PRIOR_PROMPTS[name])

    def test_roundtrip_preserves_prompt_rows_and_game_foreign_keys(self) -> None:
        _reset_rows_to_prior()
        model_row = AIModel.objects.create(
            provider="openrouter",
            model_id="google/gemma-4-31b-it:free",
            display_name="Gemma default",
            openrouter_managed=True,
            openrouter_available=True,
            model_type="language",
            tags=["tools"],
        )
        initial_row = AIPrompt.objects.get(name="Initial")
        session = GameSession.objects.create(
            game_mode="vs_ai",
            ai_model=model_row,
            ai_prompt=initial_row,
        )
        ids_before = set(AIPrompt.objects.values_list("id", flat=True))

        refresh(apps, None)
        restore(apps, None)

        session.refresh_from_db()
        initial_row.refresh_from_db()
        self.assertEqual(session.ai_prompt_id, initial_row.id)
        self.assertEqual(session.ai_model_id, model_row.id)
        self.assertEqual(set(AIPrompt.objects.values_list("id", flat=True)), ids_before)
        self.assertEqual(initial_row.prompt, PRIOR_PROMPTS["Initial"])


class RefreshedLivePresetContentTests(TestCase):
    """0010 NEW_PROMPTS remain money-free and floor/budget-aware.

    Live HEAD rows are owned by later prompt-refresh migrations; these
    assertions pin the 0010 constants themselves, not the latest catalog.
    """

    def test_0010_prompt_constants_remain_money_free_and_authoritative(self) -> None:
        for name, text in NEW_PROMPTS.items():
            self.assertIsNone(_MONEY_PATTERN.search(text), name)
            self.assertIn('"action"', text)  # strict JSON output contract
            self.assertRegex(text, r"OUTPUT FORMAT \(strict JSON")
            self.assertTrue(
                re.search(r"backend (is the )?(only |source of truth )?authority", text, re.I)
                or "Backend validation decides legality" in text
                or "Backend validation is the source of truth" in text
                or "Backend validation is the only authority" in text
                or "the ONLY authority" in text,
                f"{name} lacks backend-authority language",
            )
            self.assertIn("step budget", text.lower())

    def test_0010_prompt_constants_keep_floor_and_budget_language(self) -> None:
        for name, text in NEW_PROMPTS.items():
            self.assertIn("floor", text.lower(), f"{name} lacks scoring-floor language")
            self.assertNotIn("at least 4", text)
            self.assertNotIn("at least 5", text)
            self.assertNotIn("at least 4-6", text)


class RefreshSeededPromptsMigrateCommandTests(TransactionTestCase):
    def test_backward_then_forward_via_migrate_is_reversible(self) -> None:
        _ensure_rows_at_prior()

        # Forward semantics first (the migration is already recorded as
        # applied by the fixture), then exercise the real reverse path.
        refresh(apps, None)
        for name, text in NEW_PROMPTS.items():
            self.assertEqual(AIPrompt.objects.get(name=name).prompt, text)
        AIPrompt.objects.filter(name="Short Hooks").update(prompt=_ADMIN_EDIT)

        try:
            call_command("migrate", "catalog", "0009_dynamic_free_catalog", verbosity=0)
            for name in NEW_PROMPTS:
                row = AIPrompt.objects.get(name=name)
                if name == "Short Hooks":
                    self.assertEqual(row.prompt, _ADMIN_EDIT)
                else:
                    self.assertEqual(row.prompt, PRIOR_PROMPTS[name])

            call_command("migrate", "catalog", "0010_refresh_seeded_prompts", verbosity=0)
            for name, text in NEW_PROMPTS.items():
                row = AIPrompt.objects.get(name=name)
                if name == "Short Hooks":
                    self.assertEqual(row.prompt, _ADMIN_EDIT)
                else:
                    self.assertEqual(row.prompt, text)

            self.assertTrue(AIPrompt.objects.filter(name="Grandmaster").exists())
        finally:
            restore_apps_to_leaf("catalog")
