import importlib

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from catalog.models import AIModel
from catalog.selection import (
    DEFAULT_FREE_MODEL_ID,
    NVIDIA_NIM_MODEL_ID,
    NVIDIA_NIM_PROVIDER,
    OPENROUTER_PROVIDER,
)
from game.models import GameSession
from tests._migration_restore import restore_apps_to_leaf

_migration = importlib.import_module("catalog.migrations.0009_dynamic_free_catalog")
reenable = _migration.reenable_code_disabled_non_curated
reverse_reenable = _migration.reverse_reenable_code_disabled_non_curated


class DynamicFreeCatalogMigrationTests(TestCase):
    def test_reenable_skips_killed_curated_and_nim_and_preserves_game_fk(self) -> None:
        killed_curated = AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id=DEFAULT_FREE_MODEL_ID,
            display_name="Killed gemma",
            openrouter_managed=True,
            openrouter_available=True,
            is_active=False,
            model_type="language",
            tags=["tools"],
        )
        killed_nim = AIModel.objects.create(
            provider=NVIDIA_NIM_PROVIDER,
            model_id=NVIDIA_NIM_MODEL_ID,
            display_name="Killed NIM",
            openrouter_managed=False,
            openrouter_available=False,
            is_active=False,
            model_type="language",
            tags=["tools"],
        )
        extra = AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id="meta-llama/llama-3.3-70b-instruct:free",
            display_name="Code-disabled extra",
            openrouter_managed=False,
            openrouter_available=False,
            is_active=False,
            model_type="language",
            tags=["tools"],
        )
        openai_legacy = AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="Legacy leftover",
            openrouter_managed=False,
            openrouter_available=False,
            is_active=False,
            model_type="language",
            tags=["tools"],
        )
        session = GameSession.objects.create(game_mode="vs_ai", ai_model=extra)
        before_ids = set(AIModel.objects.values_list("id", flat=True))

        reenable(apps, None)

        assert set(AIModel.objects.values_list("id", flat=True)) == before_ids
        killed_curated.refresh_from_db()
        killed_nim.refresh_from_db()
        extra.refresh_from_db()
        openai_legacy.refresh_from_db()
        session.refresh_from_db()
        assert killed_curated.is_active is False
        assert killed_nim.is_active is False
        assert extra.is_active is True
        assert extra.openrouter_managed is True
        assert openai_legacy.is_active is False
        assert session.ai_model_id == extra.id

        reverse_reenable(apps, None)
        extra.refresh_from_db()
        killed_curated.refresh_from_db()
        killed_nim.refresh_from_db()
        assert extra.is_active is False
        assert killed_curated.is_active is False
        assert killed_nim.is_active is False
        session.refresh_from_db()
        assert session.ai_model_id == extra.id
        assert AIModel.objects.filter(pk=extra.pk).exists()


class DynamicFreeCatalogMigrateCommandTests(TransactionTestCase):
    def test_forward_and_backward_via_migrate(self) -> None:
        extra = AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id="meta-llama/llama-3.3-70b-instruct:free",
            display_name="Extra",
            openrouter_managed=False,
            openrouter_available=False,
            is_active=False,
        )
        killed = AIModel.objects.create(
            provider=OPENROUTER_PROVIDER,
            model_id=DEFAULT_FREE_MODEL_ID,
            display_name="Killed",
            openrouter_managed=True,
            openrouter_available=True,
            is_active=False,
        )
        extra_id = extra.id
        killed_id = killed.id

        try:
            call_command("migrate", "catalog", "0008_remove_aimodel_money_fields", verbosity=0)
            extra = AIModel.objects.get(pk=extra_id)
            killed = AIModel.objects.get(pk=killed_id)
            assert extra.is_active is False
            assert killed.is_active is False

            call_command("migrate", "catalog", "0009_dynamic_free_catalog", verbosity=0)
            extra.refresh_from_db()
            killed.refresh_from_db()
            assert extra.is_active is True
            assert extra.openrouter_managed is True
            assert killed.is_active is False
            assert AIModel.objects.filter(pk=extra_id).exists()
            assert AIModel.objects.filter(pk=killed_id).exists()
        finally:
            restore_apps_to_leaf("catalog")
