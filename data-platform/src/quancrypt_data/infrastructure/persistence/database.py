"""The warehouse_db engine and the transaction runner (acid-3nf-database section 5)."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from contextvars import ContextVar
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from quancrypt_data.infrastructure.settings import DatabaseSettings

_LOG = logging.getLogger("quancrypt_data.infrastructure")
_RETRYABLE_SQLSTATES = frozenset({"40P01", "40001"})
# A frozen lock must not hold a request for ever (agent_db precedent).
_SESSION_OPTIONS = "-c lock_timeout=5000 -c statement_timeout=30000"


def _sqlstate(exc: DBAPIError) -> str | None:
    state = getattr(exc.orig, "sqlstate", None)
    return state if isinstance(state, str) else None


class Database:
    """The engine (lazy: no connection until used) and the transaction runner.

    `run` executes the work in one transaction at READ COMMITTED and repeats it once after a deadlock or serialization
    failure (core D-157 analogue). A nested call joins the open transaction: the repositories find it through
    `connection()`, so a use case called from another use case's transaction takes part in it.
    """

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._current: ContextVar[Connection | None] = ContextVar("warehouse_transaction", default=None)
        self._retries = 0
        self._retry_lock = threading.Lock()
        app_url = make_url(settings.url).set(password=settings.app_password)
        self._engine: Engine = create_engine(
            app_url,
            pool_size=settings.pool_size,
            pool_pre_ping=True,
            # A database error message must never carry bound values (event payloads, quarantined records).
            hide_parameters=True,
            isolation_level="READ COMMITTED",
            connect_args={"connect_timeout": settings.connect_timeout_s, "options": _SESSION_OPTIONS},
        )

    @property
    def retries(self) -> int:
        """How many transactions were repeated after a deadlock or serialization failure (tests assert 0)."""
        with self._retry_lock:
            return self._retries

    def run[T](self, work: Callable[[], T]) -> T:
        if self._current.get() is not None:
            return work()
        attempts = 0
        while True:
            attempts += 1
            try:
                with self._engine.begin() as connection:
                    marker = self._current.set(connection)
                    try:
                        return work()
                    finally:
                        self._current.reset(marker)
            except DBAPIError as exc:
                if attempts < 2 and _sqlstate(exc) in _RETRYABLE_SQLSTATES:
                    _LOG.warning("Transaction retried after SQLSTATE %s", _sqlstate(exc))
                    with self._retry_lock:
                        self._retries += 1
                    continue
                raise

    def connection(self) -> Connection:
        connection = self._current.get()
        if connection is None:
            raise RuntimeError("no open transaction: a repository must be used inside TransactionRunner.run")
        return connection

    def is_ready(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return False
        return True

    def migrate(self, migrations_dir: Path) -> None:
        apply_migrations(self._settings, migrations_dir)

    def close(self) -> None:
        self._engine.dispose()


class DatabaseReadiness:
    """`ReadinessCheck`: the service is not ready while warehouse_db cannot be reached."""

    name = "database"

    def __init__(self, database: Database) -> None:
        self._database = database

    def is_ready(self) -> bool:
        return self._database.is_ready()


def apply_migrations(settings: DatabaseSettings, migrations_dir: Path) -> None:
    """Run `alembic upgrade head` as the migrator role. A failed migration raises and the service does not start."""
    url: URL = make_url(settings.migrator_url).set(password=settings.migrator_password)
    alembic_config = Config()
    alembic_config.set_main_option("script_location", str(migrations_dir))
    alembic_config.attributes["sqlalchemy_url"] = url
    command.upgrade(alembic_config, "head")
