"""Test configuration shared by every test.

The service reads its database passwords from the environment (fail-fast when missing); the tests set throwaway
values at import,
before any test module imports `src.app.main` (which builds the application at import). They are not secrets and
never reach a
real database: the PostgreSQL tests start their own container with random passwords.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from src.memory.memory_store import Database, DatabaseConfig, apply_migrations
from tests.support.postgres import PostgresInstance, start_postgres, stop_postgres

os.environ.setdefault("AGENT_DB_APP_PASSWORD", "unit-test-app-password")
os.environ.setdefault("AGENT_DB_MIGRATOR_PASSWORD", "unit-test-migrator-password")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "unit-test-internal-token-0123456789abcdef")

_ENTITY_TABLES = (
    "project_ref, chat_session, chat_message, message_evidence, agent_run, agent_step, tool_call, scope_decision, "
    "kb_document, kb_document_applicability, kb_chunk, outbox_event, idempotency_record, audit_log"
)


@pytest.fixture(scope="session")
def postgres_instance() -> Iterator[PostgresInstance]:
    """One pgvector container per test session (started on first use; Docker missing = failure, never a skip)."""
    instance = start_postgres()
    yield instance
    stop_postgres(instance.name)


@pytest.fixture(scope="session")
def migrated_config(postgres_instance: PostgresInstance) -> DatabaseConfig:
    config = postgres_instance.config()
    apply_migrations(config)
    return config


@pytest.fixture
def database(migrated_config: DatabaseConfig) -> Iterator[Database]:
    """The application-role database with every entity table emptied (lookup tables keep their migration data)."""
    migrator = create_engine(make_url(migrated_config.migrator_url).set(password=migrated_config.migrator_password))
    with migrator.begin() as connection:
        connection.execute(text(f"TRUNCATE {_ENTITY_TABLES} CASCADE"))
    migrator.dispose()
    db = Database(migrated_config)
    yield db
    db.close()
