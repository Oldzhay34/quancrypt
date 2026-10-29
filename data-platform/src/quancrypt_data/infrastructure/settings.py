"""Configuration from the environment (hexagonal-service section 6): validated at startup, so a service with a broken
configuration never starts. Error messages name keys and reasons, never values."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

# warehouse_db lives on this machine or is the compose service `postgres` (D-09; phase 1 is local).
LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres"})
WAREHOUSE_DB_NAME = "warehouse_db"
WAREHOUSE_DB_APP_ROLE = "warehouse_db_app"
WAREHOUSE_DB_MIGRATOR_ROLE = "warehouse_db_migrator"
MIN_TOKEN_CHARS = 32
LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR"})
# data-platform/src/quancrypt_data/infrastructure/settings.py -> data-platform (the image: /app).
_ROOT = Path(__file__).resolve().parents[3]


class ConfigError(Exception):
    """The configuration cannot be loaded or is invalid. The message never contains a configuration value."""


@dataclass(frozen=True)
class DatabaseSettings:
    """The URLs carry no password; the passwords stay out of `repr` and logs."""

    url: str
    migrator_url: str
    app_password: str = field(repr=False)
    migrator_password: str = field(repr=False)
    pool_size: int = 5
    connect_timeout_s: int = 5


@dataclass(frozen=True)
class Settings:
    database: DatabaseSettings
    internal_token: str = field(repr=False)
    schemas_dir: Path
    migrations_dir: Path
    log_level: str


def database_url_problems(name: str, value: str, role: str) -> list[str]:
    """What is wrong with a warehouse_db URL (empty when it is fine). Values are never repeated."""
    try:
        url = make_url(value)
    except ArgumentError:
        return [f"{name}: not a database URL"]
    reasons = []
    if url.drivername != "postgresql+psycopg":
        reasons.append("the driver must be postgresql+psycopg")
    if url.host not in LOCAL_DB_HOSTS:
        reasons.append("the host must be one of: " + ", ".join(sorted(LOCAL_DB_HOSTS)))
    if url.port is not None and not 1 <= url.port <= 65535:
        reasons.append("the port must be between 1 and 65535")
    if url.database != WAREHOUSE_DB_NAME:
        reasons.append(f"the database must be {WAREHOUSE_DB_NAME}")
    if url.username != role:
        reasons.append(f"the role must be {role}")
    if url.password is not None:
        reasons.append("the URL must not carry the password (it has its own variable)")
    if url.query:
        # The driver lets a query string override the very fields checked above (host, dbname, password).
        reasons.append("the URL must not carry a query string")
    return [f"{name}: " + "; ".join(reasons)] if reasons else []


def load_database_settings(source: Mapping[str, str]) -> DatabaseSettings:
    """The application role's connection only (the corpus command line writes labels; it never migrates)."""
    problems = database_url_problems("WAREHOUSE_DB_URL", source.get("WAREHOUSE_DB_URL", ""), WAREHOUSE_DB_APP_ROLE)
    password = source.get("WAREHOUSE_DB_APP_PASSWORD", "")
    if not password or "CHANGE_ME" in password:
        problems.append("WAREHOUSE_DB_APP_PASSWORD: missing or still the placeholder")
    if problems:
        raise ConfigError("Invalid configuration: " + " | ".join(problems))
    return DatabaseSettings(
        url=source["WAREHOUSE_DB_URL"], migrator_url="", app_password=password, migrator_password=""
    )


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    source = os.environ if env is None else env
    problems: list[str] = []

    def secret(name: str) -> str:
        value = source.get(name, "")
        if not value or "CHANGE_ME" in value:
            problems.append(f"{name}: missing or still the placeholder")
        return value

    def database_url(name: str, role: str) -> str:
        value = source.get(name, "")
        problems.extend(database_url_problems(name, value, role))
        return value

    url = database_url("WAREHOUSE_DB_URL", WAREHOUSE_DB_APP_ROLE)
    migrator_url = database_url("WAREHOUSE_DB_MIGRATOR_URL", WAREHOUSE_DB_MIGRATOR_ROLE)
    app_password = secret("WAREHOUSE_DB_APP_PASSWORD")
    migrator_password = secret("WAREHOUSE_DB_MIGRATOR_PASSWORD")
    token = source.get("INTERNAL_SERVICE_TOKEN", "")
    if (
        len(token) < MIN_TOKEN_CHARS
        or "CHANGE_ME" in token
        or not token.isascii()
        or not token.isprintable()
        or token != token.strip()
    ):
        problems.append(
            f"INTERNAL_SERVICE_TOKEN: at least {MIN_TOKEN_CHARS} printable ASCII characters, not the placeholder"
        )
    level = source.get("LOG_LEVEL", "INFO")
    if level not in LOG_LEVELS:
        problems.append("LOG_LEVEL: one of " + ", ".join(sorted(LOG_LEVELS)))
    schemas_dir = Path(source.get("EVENT_SCHEMAS_DIR") or _ROOT.parent / "contracts" / "schemas" / "events")
    migrations_dir = Path(source.get("MIGRATIONS_DIR") or _ROOT / "migrations")
    if problems:
        raise ConfigError("Invalid configuration: " + " | ".join(problems))
    return Settings(
        database=DatabaseSettings(
            url=url, migrator_url=migrator_url, app_password=app_password, migrator_password=migrator_password
        ),
        internal_token=token,
        schemas_dir=schemas_dir,
        migrations_dir=migrations_dir,
        log_level=level,
    )
