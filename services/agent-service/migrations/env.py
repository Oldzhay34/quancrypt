"""Alembic environment (D-08, D-233): runs migrations online with the URL the application passes as an attribute.

There is no alembic.ini (not in the agent-service tree, D-04): `apply_migrations` in `src/memory/memory_store.py` builds the
`Config` in code and hands over a SQLAlchemy URL object that carries the migrator password (it never goes through a string
option that a log could show). Offline mode (SQL scripts) is not supported on purpose.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import create_engine, pool, text

# A fixed key: two replicas that start at once migrate one after the other (the lock is released at commit).
_MIGRATION_LOCK_KEY = 4_2_0_1_0_0_1


def run_migrations_online() -> None:
    url = context.config.attributes["sqlalchemy_url"]
    engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _MIGRATION_LOCK_KEY})
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    raise RuntimeError("Offline migrations are not supported; run them against the database.")
run_migrations_online()
