from django.apps import apps
from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from catalog.models import AIModel, CatalogAdminControl, CapabilityProbe
from catalog.selection import get_selectable_models
from tests._migration_restore import restore_apps_to_leaf


def _table_names() -> set[str]:
    from django.db import connection

    return set(connection.introspection.table_names())


class CatalogAdminConsoleMigrationTests(TestCase):
    def test_f15_forward_preserves_aimodel_values_and_baseline_order(self) -> None:
        before = list(
            AIModel.objects.order_by("id").values(
                "id",
                "provider",
                "model_id",
                "display_name",
                "is_active",
                "sort_order",
                "tags",
                "openrouter_managed",
                "openrouter_available",
            )
        )
        before_order = [(row.provider, row.model_id) for row in get_selectable_models()]
        control = CatalogAdminControl.objects.get(pk=1)
        assert control.ordering_reviewed is False
        assert control.revision == 0
        assert "catalog_capability_probe" in _table_names()
        assert "catalog_admin_control" in _table_names()
        after = list(
            AIModel.objects.order_by("id").values(
                "id",
                "provider",
                "model_id",
                "display_name",
                "is_active",
                "sort_order",
                "tags",
                "openrouter_managed",
                "openrouter_available",
            )
        )
        assert after == before
        assert [(row.provider, row.model_id) for row in get_selectable_models()] == before_order
        assert not CapabilityProbe.objects.exists()
        fields = {field.name for field in CapabilityProbe._meta.get_fields()}
        assert "diagnostic_target" not in fields
        assert apps.get_model("catalog", "CapabilityProbe") is CapabilityProbe


class CatalogAdminConsoleMigrateCommandTests(TransactionTestCase):
    def test_f15_reverse_on_disposable_data_then_forward(self) -> None:
        try:
            call_command("migrate", "catalog", "0012_multi_provider_free_rivals", verbosity=0)
            assert "catalog_capability_probe" not in _table_names()
            assert "catalog_admin_control" not in _table_names()
            remaining = AIModel.objects.count()
            call_command(
                "migrate",
                "catalog",
                "0013_admin_provider_model_console",
                verbosity=0,
            )
            assert remaining == AIModel.objects.count()
            control = CatalogAdminControl.objects.get(pk=1)
            assert control.ordering_reviewed is False
            assert "catalog_capability_probe" in _table_names()
        finally:
            restore_apps_to_leaf("catalog")
