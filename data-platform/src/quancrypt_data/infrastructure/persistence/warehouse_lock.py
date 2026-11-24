"""The build lock (P6.6, D-319d): a session level advisory lock on a connection of its own, held while dbt runs.
ingest-api's erasure of a warehouse table takes the same lock as a transaction lock first
(repositories.WAREHOUSE_BUILD_LOCK)."""

from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, text

from quancrypt_data.infrastructure.persistence.repositories import WAREHOUSE_BUILD_LOCK
from quancrypt_data.infrastructure.settings import DatabaseSettings
from quancrypt_data.port.outbound.warehouse import WarehouseBusyError

_POLL_S = 0.5


class PostgresWarehouseBuildLock:
    def __init__(self, settings: DatabaseSettings, wait_s: float = 30.0) -> None:
        self._settings = settings
        self._wait_s = wait_s

    @contextmanager
    def held(self) -> Iterator[None]:
        # The application role connects (an advisory lock needs no privilege); the password stays out of the URL string.
        from sqlalchemy.engine import make_url

        url = make_url(self._settings.url).set(password=self._settings.app_password)
        engine = create_engine(url, hide_parameters=True, isolation_level="AUTOCOMMIT", pool_size=1, max_overflow=0)
        try:
            with engine.connect() as connection:
                deadline = time.monotonic() + self._wait_s
                while not connection.execute(
                    text("SELECT pg_try_advisory_lock(hashtextextended(:name, 0))"), {"name": WAREHOUSE_BUILD_LOCK}
                ).scalar_one():
                    if time.monotonic() >= deadline:
                        raise WarehouseBusyError("the warehouse build lock is taken (an erasure or another build runs)")
                    time.sleep(_POLL_S)
                try:
                    yield
                    # The lock lives as long as this connection: a restart of PostgreSQL in the middle of the build
                    # would have dropped it without a word, and an erasure could have run next to dbt (D-319d).
                    held = connection.execute(
                        text(
                            "SELECT EXISTS (SELECT 1 FROM pg_locks WHERE locktype = 'advisory' AND granted "
                            "AND pid = pg_backend_pid())"
                        )
                    ).scalar_one()
                    if not held:
                        raise WarehouseBusyError("the warehouse build lock was lost while dbt ran")
                finally:
                    connection.execute(
                        text("SELECT pg_advisory_unlock(hashtextextended(:name, 0))"), {"name": WAREHOUSE_BUILD_LOCK}
                    )
        finally:
            engine.dispose()
