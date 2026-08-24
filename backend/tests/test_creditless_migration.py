import importlib
from io import StringIO

from django.apps import apps
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.exceptions import IrreversibleError
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import AIModel
from catalog.selection import (
    DEFAULT_FREE_MODEL_ID,
    FREE_RIVAL_IDS,
    FREE_RIVAL_PAIRS,
    NVIDIA_NIM_MODEL_ID,
    get_selectable_models,
    is_selectable_model,
)
from game.models import GameSession, Move, PlayerSlot

_game_money = importlib.import_module("game.migrations.0005_remove_money_state")

_MONEY_JSON_KEYS = {
    "cost_per_game",
    "pricing",
    "input_cost_per_million",
    "output_cost_per_million",
    "cache_read_cost_per_million",
    "cache_write_cost_per_million",
    "combined_cost_per_million",
}


def _table_names() -> set[str]:
    return set(connection.introspection.table_names())


def _column_names(table: str) -> set[str]:
    with connection.cursor() as cursor:
        return {column.name for column in connection.introspection.get_table_description(cursor, table)}


def _create_legacy_billing_tables() -> None:
    vendor = connection.vendor
    with connection.cursor() as cursor:
        if vendor == "postgresql":
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_credit_balance (
                    id BIGSERIAL PRIMARY KEY,
                    balance NUMERIC(12, 6) NOT NULL,
                    updated_at TIMESTAMPTZ NOT NULL,
                    user_id INTEGER NOT NULL UNIQUE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_transaction (
                    id BIGSERIAL PRIMARY KEY,
                    type VARCHAR(20) NOT NULL,
                    amount NUMERIC(12, 6) NOT NULL,
                    description TEXT NOT NULL,
                    stripe_payment_id VARCHAR(200) NOT NULL,
                    created_at TIMESTAMPTZ NOT NULL,
                    game_id INTEGER NULL,
                    user_id INTEGER NOT NULL
                )
                """
            )
        else:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_credit_balance (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    balance DECIMAL(12, 6) NOT NULL,
                    updated_at DATETIME NOT NULL,
                    user_id INTEGER NOT NULL UNIQUE
                )
                """
            )
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS billing_transaction (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type VARCHAR(20) NOT NULL,
                    amount DECIMAL(12, 6) NOT NULL,
                    description TEXT NOT NULL,
                    stripe_payment_id VARCHAR(200) NOT NULL,
                    created_at DATETIME NOT NULL,
                    game_id INTEGER NULL,
                    user_id INTEGER NOT NULL
                )
                """
            )


class FreshCreditlessSchemaTests(TransactionTestCase):
    def test_fresh_sqlite_migrate_has_no_billing_storage(self) -> None:
        tables = _table_names()
        assert "billing_transaction" not in tables
        assert "billing_credit_balance" not in tables
        assert "cost_per_game" not in _column_names("catalog_ai_model")
        assert "pricing" not in _column_names("catalog_ai_model")
        assert "total_cost_usd" not in _column_names("game_session")
        assert not ContentType.objects.filter(app_label="billing").exists()
        assert not Permission.objects.filter(content_type__app_label="billing").exists()

    def test_cleanup_migrations_are_irreversible(self) -> None:
        with self.assertRaises((CommandError, IrreversibleError)):
            call_command("migrate", "catalog", "0007_provider_neutral_model_help", verbosity=0)
        with self.assertRaises((CommandError, IrreversibleError)):
            call_command("migrate", "game", "0004_gamesession_ai_prompt_alter_move_kind", verbosity=0)


class UpgradeCreditlessCleanupTests(TransactionTestCase):
    def test_upgrade_cleanup_scrubs_legacy_rows_and_preserves_unrelated_data(self) -> None:
        user = User.objects.create_user(username="legacy-player", password="pass1234")
        curated = AIModel.objects.create(
            provider="openrouter",
            model_id=DEFAULT_FREE_MODEL_ID,
            display_name="Gemma default",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        extra = AIModel.objects.create(
            provider="openrouter",
            model_id="meta-llama/llama-3.3-70b-instruct:free",
            display_name="Non-curated extra",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        session = GameSession.objects.create(game_mode="vs_ai", ai_model=curated)
        slot = PlayerSlot.objects.create(game=session, slot=0, user=user, rack=["A", "B"])
        billed = Move.objects.create(
            game=session,
            player_slot=slot,
            seq=1,
            kind="pass",
            ai_metadata={
                "billing": {"amount": "1.25", "credits": 1},
                "usage": {"totalTokens": 42},
                "nested": {"billing": "keep"},
            },
        )
        unrelated_move = Move.objects.create(
            game=session,
            player_slot=slot,
            seq=2,
            kind="pass",
            ai_metadata={"usage": {"totalTokens": 7}},
        )

        _create_legacy_billing_tables()
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO billing_credit_balance (balance, updated_at, user_id)
                VALUES (12.5, '2026-01-01 00:00:00', %s)
                """,
                [user.id],
            )
            cursor.execute(
                """
                INSERT INTO billing_transaction
                    (type, amount, description, stripe_payment_id, created_at, game_id, user_id)
                VALUES ('game_charge', 1.25, 'legacy charge', 'pi_legacy', '2026-01-01 00:00:00', %s, %s)
                """,
                [session.id, user.id],
            )

        balance_ct = ContentType.objects.create(app_label="billing", model="creditbalance")
        tx_ct = ContentType.objects.create(app_label="billing", model="transaction")
        view_perm = Permission.objects.create(
            content_type=balance_ct,
            codename="view_creditbalance",
            name="Can view credit balance",
        )
        Permission.objects.create(
            content_type=tx_ct,
            codename="view_transaction",
            name="Can view transaction",
        )

        assert "billing_transaction" in _table_names()
        assert "billing_credit_balance" in _table_names()

        with connection.schema_editor() as schema_editor:
            _game_money.scrub_move_billing_metadata(apps, schema_editor)
            _game_money.drop_billing_tables(apps, schema_editor)
            _game_money.delete_billing_permissions_and_content_types(apps, schema_editor)

        billed.refresh_from_db()
        unrelated_move.refresh_from_db()
        session.refresh_from_db()
        extra.refresh_from_db()
        assert billed.ai_metadata is not None
        assert "billing" not in billed.ai_metadata
        assert billed.ai_metadata["usage"]["totalTokens"] == 42
        assert billed.ai_metadata["nested"]["billing"] == "keep"
        assert unrelated_move.ai_metadata == {"usage": {"totalTokens": 7}}
        assert session.ai_model_id == curated.id
        assert User.objects.filter(pk=user.pk).exists()
        assert AIModel.objects.filter(pk=extra.pk).exists()
        assert is_selectable_model(extra.model_id) is False
        assert is_selectable_model(curated.model_id) is True

        tables = _table_names()
        assert "billing_transaction" not in tables
        assert "billing_credit_balance" not in tables
        assert not ContentType.objects.filter(app_label="billing").exists()
        assert not Permission.objects.filter(pk=view_perm.pk).exists()
        assert not Permission.objects.filter(content_type__app_label="billing").exists()


class CreditlessEligibilityTests(TestCase):
    def test_seeded_shortlist_is_selectable_and_catalog_omits_money_fields(self) -> None:
        call_command("seed_models", stdout=StringIO())
        assert [(model.provider, model.model_id) for model in get_selectable_models()] == list(
            FREE_RIVAL_PAIRS
        )

        nim = AIModel.objects.get(model_id=NVIDIA_NIM_MODEL_ID)
        nim.is_active = False
        nim.save(update_fields=["is_active"])
        assert is_selectable_model(NVIDIA_NIM_MODEL_ID) is False
        nim.is_active = True
        nim.save(update_fields=["is_active"])
        assert is_selectable_model(NVIDIA_NIM_MODEL_ID) is True

        extra = AIModel.objects.create(
            provider="openrouter",
            model_id="meta-llama/llama-3.3-70b-instruct:free",
            display_name="Non-curated extra",
            openrouter_available=True,
            is_active=True,
            model_type="language",
            tags=["tools"],
        )
        assert is_selectable_model(extra.model_id) is False

        resp = APIClient().get("/api/catalog/models/")
        assert resp.status_code == 200
        payload = resp.json()
        assert [item["model_id"] for item in payload] == list(FREE_RIVAL_IDS)
        for item in payload:
            assert _MONEY_JSON_KEYS.isdisjoint(item)
