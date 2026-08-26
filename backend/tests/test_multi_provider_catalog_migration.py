import importlib

from django.apps import apps
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from catalog.models import AIModel
from game.models import GameSession

_migration = importlib.import_module(
    "catalog.migrations.0012_multi_provider_free_rivals"
)
PREPARED_MODELS = _migration.PREPARED_MODELS
prepare_free_rivals = _migration.prepare_free_rivals
deactivate_prepared_free_rivals = _migration.deactivate_prepared_free_rivals


def _prepared_ids() -> list[str]:
    return [metadata["model_id"] for metadata in PREPARED_MODELS]


class MultiProviderCatalogMigrationTests(TestCase):
    def test_forward_creates_only_missing_rows_and_preserves_existing_owner_state(
        self,
    ) -> None:
        AIModel.objects.filter(model_id__in=_prepared_ids()).delete()
        exact_metadata = PREPARED_MODELS[0]
        exact = AIModel.objects.create(
            provider=exact_metadata["provider"],
            model_id=exact_metadata["model_id"],
            display_name="Operator-owned display",
            description="Operator-owned description",
            openrouter_managed=True,
            openrouter_available=True,
            model_type="image",
            tags=["operator"],
            is_active=True,
            sort_order=999,
        )
        collision_metadata = PREPARED_MODELS[-1]
        collision = AIModel.objects.create(
            provider="owner-provider",
            model_id=collision_metadata["model_id"],
            display_name="Provider collision",
            is_active=True,
        )

        prepare_free_rivals(apps, None)

        exact.refresh_from_db()
        collision.refresh_from_db()
        assert exact.display_name == "Operator-owned display"
        assert exact.description == "Operator-owned description"
        assert exact.openrouter_managed is True
        assert exact.openrouter_available is True
        assert exact.model_type == "image"
        assert exact.tags == ["operator"]
        assert exact.is_active is True
        assert exact.sort_order == 999
        assert collision.provider == "owner-provider"
        assert collision.display_name == "Provider collision"
        assert collision.is_active is True
        assert not AIModel.objects.filter(
            provider=collision_metadata["provider"],
            model_id=collision_metadata["model_id"],
        ).exists()

        for metadata in PREPARED_MODELS[1:-1]:
            row = AIModel.objects.get(
                provider=metadata["provider"], model_id=metadata["model_id"]
            )
            assert row.display_name == metadata["display_name"]
            assert row.description == metadata["description"]
            assert row.quality_tier == metadata["quality_tier"]
            assert row.sort_order == metadata["sort_order"]
            assert row.openrouter_managed is False
            assert row.openrouter_available is False
            assert row.model_type == "language"
            assert row.tags == ["tools"]
            assert row.is_active is False

    def test_reverse_preserves_rows_and_foreign_keys_while_deactivating_exact_pairs(
        self,
    ) -> None:
        prepare_free_rivals(apps, None)
        exact_rows = []
        for metadata in PREPARED_MODELS:
            row = AIModel.objects.get(
                provider=metadata["provider"], model_id=metadata["model_id"]
            )
            row.is_active = True
            row.save(update_fields=["is_active"])
            exact_rows.append(row)
        unrelated = AIModel.objects.create(
            provider="local",
            model_id="local/unrelated-model",
            display_name="Unrelated",
            is_active=True,
        )
        session = GameSession.objects.create(game_mode="vs_ai", ai_model=exact_rows[0])
        before_ids = {row.id for row in exact_rows}

        deactivate_prepared_free_rivals(apps, None)

        assert set(
            AIModel.objects.filter(model_id__in=_prepared_ids()).values_list(
                "id", flat=True
            )
        ) == before_ids
        assert not AIModel.objects.filter(
            model_id__in=_prepared_ids(), is_active=True
        ).exists()
        unrelated.refresh_from_db()
        session.refresh_from_db()
        assert unrelated.is_active is True
        assert session.ai_model_id == exact_rows[0].id


class MultiProviderCatalogMigrateCommandTests(TransactionTestCase):
    def test_backward_and_forward_preserve_rows_and_do_not_reactivate(self) -> None:
        # Other migration tests deliberately exercise older catalog targets.
        # Establish this test's declared migration baseline explicitly.
        call_command(
            "migrate",
            "catalog",
            "0012_multi_provider_free_rivals",
            verbosity=0,
        )
        metadata = PREPARED_MODELS[0]
        row = AIModel.objects.get(
            provider=metadata["provider"], model_id=metadata["model_id"]
        )
        row.is_active = True
        row.save(update_fields=["is_active"])
        row_id = row.id

        try:
            call_command(
                "migrate",
                "catalog",
                "0011_playable_seeded_prompts",
                verbosity=0,
            )
            row = AIModel.objects.get(pk=row_id)
            assert row.is_active is False

            call_command(
                "migrate",
                "catalog",
                "0012_multi_provider_free_rivals",
                verbosity=0,
            )
            row.refresh_from_db()
            assert row.is_active is False
            assert AIModel.objects.filter(pk=row_id).exists()
        finally:
            call_command("migrate", "catalog", verbosity=0)
