"""One throw-away PostgreSQL for all integration tests of the session, migrated to the head of ml/migrations."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from quancrypt_ml.infrastructure.persistence import database
from tests.support.postgres import MIGRATIONS_DIR, PostgresInstance, start_postgres


@pytest.fixture(scope="session")
def pg() -> Iterator[PostgresInstance]:
    instance = start_postgres()
    database.migrate(instance.settings(migrator=True), MIGRATIONS_DIR)
    yield instance
