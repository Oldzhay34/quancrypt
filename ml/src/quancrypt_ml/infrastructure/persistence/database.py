"""The warehouse_db engine of the ml command line and the migration of the labels schema (acid-3nf-database sections 4,
5)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url

from quancrypt_ml.infrastructure.settings import DatabaseSettings

# A frozen lock must not hold the command for ever (the data-platform precedent).
_SESSION_OPTIONS = "-c lock_timeout=5000 -c statement_timeout=60000"


def engine(settings: DatabaseSettings) -> Engine:
    """READ COMMITTED; bound values never reach an error message (labels, notes and code context are in them)."""
    return create_engine(
        make_url(settings.url).set(password=settings.password),
        pool_size=2,
        pool_pre_ping=True,
        hide_parameters=True,
        isolation_level="READ COMMITTED",
        connect_args={"connect_timeout": 5, "options": _SESSION_OPTIONS},
    )


def migrate(settings: DatabaseSettings, migrations_dir: Path) -> None:
    """`alembic upgrade head` as warehouse_db_migrator, with its own version table (ml_alembic_version; data-platform
    keeps public.alembic_version)."""
    config = Config()
    config.set_main_option("script_location", str(migrations_dir))
    config.attributes["sqlalchemy_url"] = make_url(settings.url).set(password=settings.password)
    command.upgrade(config, "head")
