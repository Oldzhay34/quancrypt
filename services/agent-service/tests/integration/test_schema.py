"""The agent_db schema as the migration builds it: shape, behaviour (constraints, cascades) and role privileges.

PostgreSQL tests (marker `postgres`): they start a throw-away pgvector container with the project's init scripts.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError, ProgrammingError

from src.memory.memory_store import Database, DatabaseConfig, apply_migrations
from tests.support.postgres import PostgresInstance

pytestmark = pytest.mark.postgres

CHECKS = Path(__file__).with_name("agent_db_checks.sql")


def _scalar(database: Database, statement: str) -> Any:
    with database.engine.connect() as connection:
        return connection.execute(text(statement)).scalar_one()


def _migrator(config: DatabaseConfig) -> Engine:
    return create_engine(make_url(config.migrator_url).set(password=config.migrator_password))


def test_the_migration_builds_the_approved_schema_shape(database: Database) -> None:
    assert (
        _scalar(
            database,
            "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public' "
            "AND table_type = 'BASE TABLE' AND table_name <> 'alembic_version'",
        )
        == 32  # P4.6 added graph_checkpoint (D-253)
    )
    with database.engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT contype, count(*) FROM pg_constraint c JOIN pg_namespace n "
                "ON n.oid = c.connamespace WHERE n.nspname = 'public' GROUP BY contype"
            )
        ).all()
    constraints: dict[str, int] = {str(row[0]): int(row[1]) for row in rows}
    assert constraints["f"] == 29
    assert constraints["c"] == 47
    assert constraints["u"] == 21
    explicit_indexes = _scalar(
        database,
        "SELECT count(*) FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid JOIN pg_namespace n ON n.oid = "
        "c.relnamespace "
        "WHERE n.nspname = 'public' AND NOT i.indisprimary AND NOT EXISTS "
        "(SELECT 1 FROM pg_constraint k WHERE k.conindid = i.indexrelid)",
    )
    assert explicit_indexes == 12
    assert _scalar(database, "SELECT count(*) FROM pg_type WHERE typtype = 'e'") == 0  # no ENUM (acid-3nf-database)
    assert (
        _scalar(
            database,
            "SELECT atttypmod FROM pg_attribute WHERE attrelid = 'kb_chunk'::regclass AND attname = 'embedding'",
        )
        == 768
    )  # vector(768): embeddinggemma (D-68)


def test_lookup_tables_carry_their_migration_data(database: Database) -> None:
    assert _scalar(database, "SELECT count(*) FROM scope_ring") == 4
    assert _scalar(database, "SELECT count(*) FROM tool WHERE code = 'UNKNOWN'") == 1
    assert _scalar(database, "SELECT count(*) FROM language") == 2
    assert _scalar(database, "SELECT string_agg(code, ',' ORDER BY code) FROM audit_action") == (
        "PROJECT_DATA_DELETED,SESSION_DELETED"
    )


def test_applying_the_migrations_twice_changes_nothing(migrated_config: DatabaseConfig) -> None:
    engine = _migrator(migrated_config)
    with engine.connect() as connection:
        before = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    apply_migrations(migrated_config)

    with engine.connect() as connection:
        after = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
        tables = connection.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'")
        ).scalar_one()
    engine.dispose()
    assert before == after == "0002"
    assert tables == 33  # 32 schema tables + alembic_version


def test_the_schema_behaves_as_designed(postgres_instance: PostgresInstance, database: Database) -> None:
    """About 90 checks in SQL: constraints, cascades, restrict rules, the vector query and the version filter."""
    del database  # the fixture empties the entity tables first
    result = subprocess.run(  # noqa: S603
        ["docker", "exec", "-i", postgres_instance.name, "psql", "-U", "postgres", "-d", "agent_db", "-q", "-f", "-"],  # noqa: S607
        input=CHECKS.read_text(encoding="utf-8"),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )

    outcomes = re.findall(r"NOTICE:  (ok  |FAIL)\s+(.*)", result.stderr)
    failures = [label for state, label in outcomes if state == "FAIL"]
    assert not failures, failures
    assert result.returncode == 0, result.stderr[-1500:]
    assert len(outcomes) == 86, f"only {len(outcomes)} checks ran:\n{result.stderr[-800:]}"


def test_the_application_role_does_dml_but_never_ddl_and_never_changes_code_lists(database: Database) -> None:
    with database.engine.begin() as connection:
        connection.execute(text("INSERT INTO project_ref VALUES (gen_random_uuid(), repeat('a', 64), now())"))
        assert connection.execute(text("SELECT count(*) FROM language")).scalar_one() == 2
    forbidden = [
        "CREATE TABLE intruder (id int)",
        "CREATE TEMPORARY TABLE intruder (id int)",
        "INSERT INTO language VALUES ('de', 'Deutsch', 3)",
        "UPDATE language SET description = 'x'",
        "DELETE FROM language",
        "TRUNCATE language",
        "ALTER TABLE project_ref ADD COLUMN extra int",
        "DROP TABLE audit_log",
    ]
    for statement in forbidden:
        with pytest.raises(ProgrammingError) as caught, database.engine.begin() as connection:
            connection.execute(text(statement))
        assert getattr(caught.value.orig, "sqlstate", None) == "42501", statement


def test_the_migrator_role_owns_the_schema_and_can_do_ddl(migrated_config: DatabaseConfig) -> None:
    engine = _migrator(migrated_config)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE migrator_probe (id int)"))
        connection.execute(text("DROP TABLE migrator_probe"))
    engine.dispose()


def test_a_wrong_password_is_refused(migrated_config: DatabaseConfig) -> None:
    wrong = create_engine(make_url(migrated_config.url).set(password="not-the-password"))
    with pytest.raises(DBAPIError), wrong.connect():
        pass
    wrong.dispose()


def test_graph_checkpoint_constraints_and_cascade(database: Database) -> None:
    """D-253: each CHECK, the uuid type and the foreign key reject a bad row; the row goes with its session."""
    with database.engine.begin() as connection:
        connection.execute(
            text("INSERT INTO project_ref VALUES ('00000000-0000-0000-0000-0000000000a1', repeat('a', 64), now())")
        )
        connection.execute(
            text(
                "INSERT INTO chat_session VALUES ('00000000-0000-0000-0000-0000000000b1', "
                "'00000000-0000-0000-0000-0000000000a1', 'tr', now())"
            )
        )
    session = "'00000000-0000-0000-0000-0000000000b1'"
    good = f"{session}, gen_random_uuid(), 'msgpack', '\x81'::bytea, encode(sha256('\x81'::bytea), 'hex'), now()"
    bad_rows = {
        "ck_graph_checkpoint_type": f"{session}, gen_random_uuid(), 'pickle', '\x81'::bytea, repeat('a', 64), now()",
        "ck_graph_checkpoint_size": f"{session}, gen_random_uuid(), 'msgpack', ''::bytea, repeat('a', 64), now()",
        "ck_graph_checkpoint_sha": f"{session}, gen_random_uuid(), 'msgpack', '\x81'::bytea, 'not-a-digest', now()",
        "fk_graph_checkpoint_session": (
            "gen_random_uuid(), gen_random_uuid(), 'msgpack', '\x81'::bytea, repeat('a', 64), now()"
        ),
    }
    for constraint, values in bad_rows.items():
        with pytest.raises(DBAPIError) as caught, database.engine.begin() as connection:
            connection.execute(text(f"INSERT INTO graph_checkpoint VALUES ({values})"))
        assert getattr(getattr(caught.value.orig, "diag", None), "constraint_name", None) == constraint
    with pytest.raises(DBAPIError), database.engine.begin() as connection:
        connection.execute(
            text(
                f"INSERT INTO graph_checkpoint VALUES ({session}, 'not-a-uuid', 'msgpack', "
                f"'\x81'::bytea, repeat('a', 64), now())"
            )
        )
    with database.engine.begin() as connection:  # the application role writes it (D-54 default privileges)
        connection.execute(text(f"INSERT INTO graph_checkpoint VALUES ({good})"))
        connection.execute(text(f"DELETE FROM chat_session WHERE id = {session}"))
        assert connection.execute(text("SELECT count(*) FROM graph_checkpoint")).scalar_one() == 0
