import importlib
from django.apps import apps
from django.core.management import call_command
from django.db import connection
from django.db.migrations.operations.fields import AlterField
from django.test import TestCase, TransactionTestCase

from catalog.models import AIModel
from catalog.selection import is_selectable_model
from game.models import GameSession

_migration = importlib.import_module("catalog.migrations.0006_openrouter_catalog")
SHORTLIST_IDS = _migration.SHORTLIST_IDS
deactivate_non_shortlist = _migration.deactivate_non_shortlist


class OpenRouterCatalogMigrationTests(TestCase):
    def test_schema_renames_gateway_fields_without_dropping_aimodel_table(self) -> None:
        column_names = {
            column.name
            for column in connection.introspection.get_table_description(
                connection.cursor(),
                "catalog_ai_model",
            )
        }
        assert "openrouter_managed" in column_names
        assert "openrouter_available" in column_names
        assert "gateway_managed" not in column_names
        assert "gateway_available" not in column_names

    def test_data_step_keeps_legacy_rows_and_makes_them_ineligible(self) -> None:
        legacy = AIModel.objects.create(
            provider="openai",
            model_id="openai/gpt-5-mini",
            display_name="GPT-5 Mini",
            openrouter_managed=True,
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
            pricing={"input": "0.000001", "output": "0.000002"},
        )
        extra_free = AIModel.objects.create(
            provider="openrouter",
            model_id="meta-llama/llama-3.3-70b-instruct:free",
            display_name="Llama extra",
            openrouter_managed=True,
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
            pricing={"input": "0", "output": "0"},
            cost_per_game=0,
        )
        shortlist = AIModel.objects.create(
            provider="openrouter",
            model_id=SHORTLIST_IDS[0],
            display_name="Gemma default",
            openrouter_managed=True,
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
            pricing={"input": "0", "output": "0"},
            cost_per_game=0,
        )
        session = GameSession.objects.create(
            game_mode="vs_ai",
            ai_model=legacy,
        )
        before_ids = set(AIModel.objects.values_list("id", flat=True))

        deactivate_non_shortlist(apps, None)

        assert set(AIModel.objects.values_list("id", flat=True)) == before_ids
        legacy.refresh_from_db()
        extra_free.refresh_from_db()
        shortlist.refresh_from_db()
        session.refresh_from_db()
        assert session.ai_model_id == legacy.id
        assert legacy.openrouter_managed is False
        assert legacy.openrouter_available is False
        assert legacy.is_active is False
        assert extra_free.is_active is False
        assert extra_free.openrouter_available is False
        assert shortlist.is_active is True
        assert shortlist.openrouter_available is True
        assert is_selectable_model(legacy.model_id) is False
        assert is_selectable_model(extra_free.model_id) is False
        assert is_selectable_model(shortlist.model_id) is True

    def test_accounts_help_text_migration_applies(self) -> None:
        migration = importlib.import_module("accounts.migrations.0002_openrouter_catalog")
        help_texts = [
            operation.field.help_text
            for operation in migration.Migration.operations
            if isinstance(operation, AlterField)
            and operation.name == "preferred_ai_model_id"
        ]
        assert help_texts
        assert "OpenRouter" in help_texts[0]
        assert "google/gemma-4-31b-it:free" in help_texts[0]

        from accounts.models import User

        field = User._meta.get_field("preferred_ai_model_id")
        assert "google/gemma-4-31b-it:free" in field.help_text
        assert "nvidia/nemotron-3-super-120b-a12b" in field.help_text
        assert "OpenRouter" not in field.help_text


class ProviderNeutralHelpTextMigrationTests(TransactionTestCase):
    def test_help_text_migrations_are_alter_field_only(self) -> None:
        catalog_migration = importlib.import_module(
            "catalog.migrations.0007_provider_neutral_model_help"
        )
        accounts_migration = importlib.import_module(
            "accounts.migrations.0003_provider_neutral_ai_model_help"
        )
        assert all(
            isinstance(operation, AlterField)
            for operation in catalog_migration.Migration.operations
        )
        assert all(
            isinstance(operation, AlterField)
            for operation in accounts_migration.Migration.operations
        )

    def test_provider_neutral_help_text_migrations_forward_and_reverse(self) -> None:
        call_command("migrate", "catalog", "0006_openrouter_catalog", verbosity=0)
        call_command("migrate", "accounts", "0002_openrouter_catalog", verbosity=0)
        call_command("migrate", "catalog", verbosity=0)
        call_command("migrate", "accounts", verbosity=0)

        from accounts.models import User
        from catalog.models import AIModel as LiveAIModel

        catalog_help = LiveAIModel._meta.get_field("model_id").help_text
        accounts_help = User._meta.get_field("preferred_ai_model_id").help_text
        assert "google/gemma-4-31b-it:free" in catalog_help
        assert "nvidia/nemotron-3-super-120b-a12b" in catalog_help
        assert "OpenRouter" not in catalog_help
        assert "google/gemma-4-31b-it:free" in accounts_help
        assert "nvidia/nemotron-3-super-120b-a12b" in accounts_help
        assert "OpenRouter" not in accounts_help

        survivor = AIModel.objects.create(
            provider="openrouter",
            model_id="google/gemma-4-31b-it:free",
            display_name="Survivor",
        )
        survivor_id = survivor.id
        call_command("migrate", "catalog", "0006_openrouter_catalog", verbosity=0)
        call_command("migrate", "accounts", "0002_openrouter_catalog", verbosity=0)
        assert AIModel.objects.filter(pk=survivor_id).exists()
        call_command("migrate", verbosity=0)
        assert AIModel.objects.filter(pk=survivor_id).exists()
