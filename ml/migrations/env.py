"""Alembic environment of the labels schema (P7.1, D-322): online only, with the URL the command line passes as an
attribute (the migrator password never goes through a string option). The version table is ml_alembic_version, so this
chain and the data-platform chain (public.alembic_version) never meet in one table."""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool, text

# A fixed key: two runs that start at once migrate one after the other (the lock is released at commit).
_MIGRATION_LOCK_KEY = 7_1_0_0_1_0_1


def run_migrations_online() -> None:
    url = context.config.attributes["sqlalchemy_url"]
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None, version_table="ml_alembic_version")
        with context.begin_transaction():
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _MIGRATION_LOCK_KEY})
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported; run them against the database.")
run_migrations_online()
