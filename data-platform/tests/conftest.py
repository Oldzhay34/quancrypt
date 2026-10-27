from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from sqlalchemy import text

from quancrypt_data.infrastructure.container import Container, build_container
from quancrypt_data.infrastructure.persistence.database import apply_migrations
from quancrypt_data.infrastructure.settings import Settings
from tests.support.postgres import MIGRATIONS_DIR, SCHEMAS_DIR, PostgresInstance, start_postgres, stop_postgres

_ENTITY_TABLES = "ingest.ingest_audit_table, ingest.ingest_audit, raw.event, quarantine.event, ingest.ingest_batch"


@pytest.fixture(scope="session")
def postgres_instance() -> Iterator[PostgresInstance]:
    instance = start_postgres()
    yield instance
    stop_postgres(instance.name)


@pytest.fixture(scope="session")
def migrated(postgres_instance: PostgresInstance) -> PostgresInstance:
    apply_migrations(postgres_instance.settings(), MIGRATIONS_DIR)
    return postgres_instance


@dataclass(frozen=True)
class Stack:
    instance: PostgresInstance
    container: Container


@pytest.fixture
def stack(migrated: PostgresInstance) -> Iterator[Stack]:
    """The real service wired to the real database, with empty entity tables."""
    with migrated.migrator_engine().begin() as connection:
        connection.execute(text(f"TRUNCATE {_ENTITY_TABLES}"))
    settings = Settings(
        database=migrated.settings(),
        internal_token="t" * 40,
        schemas_dir=SCHEMAS_DIR,
        migrations_dir=MIGRATIONS_DIR,
        log_level="WARNING",
    )
    container = build_container(settings)
    yield Stack(migrated, container)
    container.database.close()
