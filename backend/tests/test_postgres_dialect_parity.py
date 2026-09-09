"""SQLite (default) and opt-in PostgreSQL dialect parity tests.

Default pytest runs only the SQLite tests; tests marked ``postgres`` skip
with a message naming ``LIBRETILES_TEST_POSTGRES=1``. With that variable set
to ``1`` the PostgreSQL tests run against a disposable database named
``libretiles_pytest`` (alias ``postgres_test``) that the fixture creates and
drops. The compose/database name ``libretiles`` is never migrated, created,
or written by these tests. When ``LIBRETILES_TEST_POSTGRES=1`` a connect or
migrate failure is fail-closed: the tests error out, they never silently skip.

PostgreSQL tests carry the ``django_db`` mark so pytest-django sets up the
default (SQLite) test database: game migration 0008's guard counts rows on
the default alias, and an empty test database lets the alias migrate proceed.
"""

from __future__ import annotations

import os
from pathlib import Path

import psycopg
import pytest
from django.core.management import call_command
from django.db import IntegrityError, connections, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import CharField, Value
from django.db.models.functions import Cast, Replace
from django.db.utils import OperationalError
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from game.models import GameSession, PlaygroundSimulation

_BACKEND_DIR = Path(__file__).resolve().parents[1]
_POSTGRES_TEST_ALIAS = "postgres_test"
_POSTGRES_TEST_DB_NAME = "libretiles_pytest"
_POSTGRES_ENABLED = os.environ.get("LIBRETILES_TEST_POSTGRES") == "1"

requires_postgres = pytest.mark.skipif(
    not _POSTGRES_ENABLED,
    reason="PostgreSQL opt-in tests disabled; set LIBRETILES_TEST_POSTGRES=1 to enable.",
)

# JSON payload shared by both dialect round-trips: nested dict/list, ints,
# floats (exact binary fractions), bools, JSON null, and Slovak tokens.
_JSON_PAYLOAD: dict[str, object] = {
    "variant": "slovak",
    "tokens": ["Á", "Č", "Ť", "AM"],
    "racks": [["Á", "Č"], ["Ť", "S"]],
    "board": [[None, {"token": "Ť", "blank_as": None}], [1, 2, 3]],
    "meta": {
        "moves": 12,
        "ratio": 0.5,
        "premium": 1.25,
        "negative": -3.75,
        "confirmed": True,
        "exchanged": False,
        "note": None,
    },
}


def _postgres_server_settings() -> dict[str, str]:
    """Public compose defaults (host/port/user/password) from the environment.

    DB_NAME is deliberately ignored: the disposable database name is a
    constant and is never taken from the environment.
    """
    return {
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
        "USER": os.environ.get("DB_USER", "libretiles"),
        "PASSWORD": os.environ.get("DB_PASSWORD", "libretiles"),
    }


def _admin_connect(server: dict[str, str]) -> psycopg.Connection:
    # Connect to the maintenance database "postgres", never to "libretiles".
    return psycopg.connect(
        host=server["HOST"],
        port=server["PORT"],
        user=server["USER"],
        password=server["PASSWORD"],
        dbname="postgres",
        connect_timeout=5,
        autocommit=True,
    )


def _postgres_db_marker() -> pytest.MarkDecorator:
    # transaction=True: TransactionTestCase semantics (no atomic wrapping).
    # databases: declare both aliases so Django's test isolation patch allows
    # the dynamically registered postgres_test alias and flushes both.
    return pytest.mark.django_db(
        transaction=True, databases=["default", _POSTGRES_TEST_ALIAS]
    )


@pytest.fixture(scope="module")
def postgres_test_db(django_db_setup, django_db_blocker):  # noqa: ARG001
    """Create, migrate, and drop the disposable libretiles_pytest database.

    Module-scoped so the alias exists before each test's setUpClass
    validation and the database outlives the per-test flush. django_db_setup
    is requested first so the default (SQLite) test database exists before
    the alias migrate: game migration 0008's guard counts rows on the
    default alias and must see an empty database.
    """
    server = _postgres_server_settings()
    try:
        admin = _admin_connect(server)
    except Exception as exc:
        pytest.fail(
            f"LIBRETILES_TEST_POSTGRES=1 but PostgreSQL connect failed: {exc}"
        )
    try:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {_POSTGRES_TEST_DB_NAME}")
            cur.execute(f"CREATE DATABASE {_POSTGRES_TEST_DB_NAME}")
    finally:
        admin.close()

    connections.databases[_POSTGRES_TEST_ALIAS] = {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _POSTGRES_TEST_DB_NAME,
        "USER": server["USER"],
        "PASSWORD": server["PASSWORD"],
        "HOST": server["HOST"],
        "PORT": server["PORT"],
        "CONN_MAX_AGE": 600,
        "CONN_HEALTH_CHECKS": True,
        "ATOMIC_REQUESTS": False,
        "AUTOCOMMIT": True,
        "OPTIONS": {},
        "TIME_ZONE": None,
        "TEST": {
            "CHARSET": None,
            "COLLATION": None,
            "MIGRATE": True,
            "NAME": None,
            "MIRROR": None,
        },
    }

    try:
        # The module fixture runs before the per-test django_db helper, so
        # unblock here for the alias migrate only.
        with django_db_blocker.unblock():
            call_command(
                "migrate",
                database=_POSTGRES_TEST_ALIAS,
                verbosity=0,
                interactive=False,
            )
    except Exception as exc:
        # Fail closed, but do not leak a connection that would make every
        # later DROP DATABASE in this session fail with ObjectInUse.
        connections[_POSTGRES_TEST_ALIAS].close()
        connections.databases.pop(_POSTGRES_TEST_ALIAS, None)
        pytest.fail(
            f"PostgreSQL migrate-to-head failed on {_POSTGRES_TEST_ALIAS!r}: {exc}"
        )
    yield _POSTGRES_TEST_ALIAS
    connections[_POSTGRES_TEST_ALIAS].close()
    connections.databases.pop(_POSTGRES_TEST_ALIAS, None)
    try:
        admin = _admin_connect(server)
        try:
            with admin.cursor() as cur:
                cur.execute(f"DROP DATABASE IF EXISTS {_POSTGRES_TEST_DB_NAME}")
        finally:
            admin.close()
    except Exception:  # pragma: no cover - teardown best effort
        pass


# ---------------------------------------------------------------------------
# SQLite (always run, never postgres-marked)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_uuid_search_hyphenated_and_compact_sqlite() -> None:
    staff = User.objects.create_user(
        username="uuid-admin", password="pass1234", is_staff=True
    )
    session = GameSession.objects.create()
    public_id = str(session.public_id)
    client = APIClient()
    client.force_authenticate(user=staff)

    compact = public_id.replace("-", "")[:12]
    response = client.get("/api/admin/games/", {"search": compact})
    assert response.status_code == 200
    assert [item["game_id"] for item in response.json()["results"]] == [public_id]

    hyphenated = public_id[:14]
    assert "-" in hyphenated
    response = client.get("/api/admin/games/", {"search": hyphenated})
    assert response.status_code == 200
    assert [item["game_id"] for item in response.json()["results"]] == [public_id]


@pytest.mark.django_db
def test_jsonfield_complex_structure_roundtrip_sqlite() -> None:
    user = User.objects.create_user(username="json-user", password="pass1234")
    session = GameSession.objects.create()
    PlaygroundSimulation.objects.create(
        game=session, created_by=user, config_json=_JSON_PAYLOAD
    )
    reloaded = PlaygroundSimulation.objects.get(game=session)
    assert reloaded.config_json == _JSON_PAYLOAD


@pytest.mark.django_db(transaction=True)
def test_unique_unfinished_playground_simulation_sqlite() -> None:
    user_a = User.objects.create_user(username="sim-user-a", password="pass1234")
    user_b = User.objects.create_user(username="sim-user-b", password="pass1234")

    first = PlaygroundSimulation.objects.create(
        game=GameSession.objects.create(), created_by=user_a, config_json={}
    )
    with pytest.raises(IntegrityError):
        PlaygroundSimulation.objects.create(
            game=GameSession.objects.create(), created_by=user_a, config_json={}
        )

    PlaygroundSimulation.objects.create(
        game=GameSession.objects.create(), created_by=user_b, config_json={}
    )

    first.ended_at = timezone.now()
    first.save(update_fields=["ended_at"])
    PlaygroundSimulation.objects.create(
        game=GameSession.objects.create(), created_by=user_a, config_json={}
    )


def test_skip_locked_only_under_postgresql_vendor_guard() -> None:
    """Static check: skip_locked=True only inside a postgresql vendor guard.

    services.py calls select_for_update() unconditionally and re-applies
    skip_locked=True only when connection.vendor == "postgresql". The branch
    is read statically; join_matchmaking is never imported or executed.
    """
    source = (_BACKEND_DIR / "game" / "services.py").read_text(encoding="utf-8")
    lines = source.splitlines()
    occurrences = [
        index for index, line in enumerate(lines) if "skip_locked=True" in line
    ]
    assert len(occurrences) == 1, "skip_locked=True must appear exactly once"
    guarded_lines = lines[max(0, occurrences[0] - 4) : occurrences[0]]
    assert any(
        'connection.vendor == "postgresql"' in line for line in guarded_lines
    ), "skip_locked=True must only occur inside a postgresql vendor guard"


# ---------------------------------------------------------------------------
# PostgreSQL (opt-in via LIBRETILES_TEST_POSTGRES=1, alias postgres_test)
# ---------------------------------------------------------------------------


@requires_postgres
@pytest.mark.postgres
@_postgres_db_marker()
def test_postgres_migrate_zero_to_head(postgres_test_db: str) -> None:
    applied = MigrationRecorder(connections[postgres_test_db]).applied_migrations()
    assert ("accounts", "0005_service_account_flag") in applied
    assert ("catalog", "0014_strategic_seeded_prompts") in applied
    assert ("game", "0014_playground_simulation") in applied


@requires_postgres
@pytest.mark.postgres
@_postgres_db_marker()
def test_postgres_uuid_search_compact_and_hyphenated(postgres_test_db: str) -> None:
    alias = postgres_test_db
    target = GameSession.objects.using(alias).create()
    other = GameSession.objects.using(alias).create()

    base = GameSession.objects.using(alias).annotate(
        public_id_text=Replace(
            Cast("public_id", output_field=CharField()), Value("-"), Value("")
        )
    )

    compact = str(target.public_id).replace("-", "")[:12]
    assert [row.pk for row in base.filter(public_id_text__istartswith=compact)] == [
        target.pk
    ]

    hyphenated = str(target.public_id)[:14]
    assert "-" in hyphenated
    compact_of_hyphenated = hyphenated.replace("-", "")
    assert [
        row.pk
        for row in base.filter(public_id_text__istartswith=compact_of_hyphenated)
    ] == [target.pk]

    other_compact = str(other.public_id).replace("-", "")[:12]
    assert [
        row.pk for row in base.filter(public_id_text__istartswith=other_compact)
    ] == [other.pk]


@requires_postgres
@pytest.mark.postgres
@_postgres_db_marker()
def test_postgres_jsonfield_roundtrip_jsonb(postgres_test_db: str) -> None:
    alias = postgres_test_db
    user = User.objects.db_manager(alias).create_user(
        username="pg-json-user", password="pass1234"
    )
    session = GameSession.objects.using(alias).create()
    PlaygroundSimulation.objects.using(alias).create(
        game=session, created_by=user, config_json=_JSON_PAYLOAD
    )
    reloaded = PlaygroundSimulation.objects.using(alias).get(game=session)
    assert reloaded.config_json == _JSON_PAYLOAD


@requires_postgres
@pytest.mark.postgres
@_postgres_db_marker()
def test_postgres_unique_unfinished_playground_simulation(
    postgres_test_db: str,
) -> None:
    alias = postgres_test_db
    user_a = User.objects.db_manager(alias).create_user(
        username="pg-sim-user-a", password="pass1234"
    )
    user_b = User.objects.db_manager(alias).create_user(
        username="pg-sim-user-b", password="pass1234"
    )

    first = PlaygroundSimulation.objects.using(alias).create(
        game=GameSession.objects.using(alias).create(),
        created_by=user_a,
        config_json={},
    )
    with pytest.raises(IntegrityError):
        PlaygroundSimulation.objects.using(alias).create(
            game=GameSession.objects.using(alias).create(),
            created_by=user_a,
            config_json={},
        )

    PlaygroundSimulation.objects.using(alias).create(
        game=GameSession.objects.using(alias).create(),
        created_by=user_b,
        config_json={},
    )

    first.ended_at = timezone.now()
    first.save(using=alias, update_fields=["ended_at"])
    PlaygroundSimulation.objects.using(alias).create(
        game=GameSession.objects.using(alias).create(),
        created_by=user_a,
        config_json={},
    )


@requires_postgres
@pytest.mark.postgres
@_postgres_db_marker()
def test_postgres_select_for_update_skip_locked(postgres_test_db: str) -> None:
    alias = postgres_test_db
    locked_session = GameSession.objects.using(alias).create(
        game_mode="vs_human", status="waiting", variant_slug="english"
    )
    table = GameSession._meta.db_table
    pk_column = GameSession._meta.pk.column

    conn_b = connections.create_connection(alias)
    try:
        with conn_b.cursor() as cur:
            cur.execute("SET statement_timeout = 1000")

        with transaction.atomic(using=alias):
            # Connection A holds the row lock for this whole block.
            GameSession.objects.using(alias).select_for_update().get(
                pk=locked_session.pk
            )

            with conn_b.cursor() as cur:
                # SKIP LOCKED must return immediately without the locked row.
                cur.execute(
                    f'SELECT "{pk_column}" FROM "{table}" '
                    f'WHERE "{pk_column}" = %s FOR UPDATE SKIP LOCKED',
                    [locked_session.pk],
                )
                assert cur.fetchone() is None, (
                    "connection B must not return the row locked by connection A"
                )

            with conn_b.cursor() as cur:
                # Negative proof: without SKIP LOCKED the same read blocks
                # connection B until statement_timeout fires.
                with pytest.raises(OperationalError):
                    cur.execute(
                        f'SELECT "{pk_column}" FROM "{table}" '
                        f'WHERE "{pk_column}" = %s FOR UPDATE',
                        [locked_session.pk],
                    )
                    cur.fetchone()
                    pytest.fail("connection B acquired the lock held by connection A")

        with conn_b.cursor() as cur:
            # After connection A releases, connection B can take the lock.
            cur.execute(
                f'SELECT "{pk_column}" FROM "{table}" '
                f'WHERE "{pk_column}" = %s FOR UPDATE',
                [locked_session.pk],
            )
            assert cur.fetchone() is not None
    finally:
        conn_b.close()


@requires_postgres
@pytest.mark.postgres
@_postgres_db_marker()
def test_postgres_connection_health_probe(postgres_test_db: str) -> None:
    conn = connections[postgres_test_db]
    assert conn.settings_dict["CONN_MAX_AGE"] == 600
    assert conn.settings_dict["CONN_HEALTH_CHECKS"] is True
    # Establish the connection (TransactionTestCase force-closes connections
    # between tests, and the postgresql backend's is_usable() reports False
    # for a not-yet-connected wrapper instead of connecting).
    GameSession.objects.using(postgres_test_db).exists()
    assert conn.connection is not None
    assert conn.is_usable() is True
