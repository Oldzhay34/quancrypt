"""Configuration of the ml command line from the environment (hexagonal-service section 6). It runs on the host
(docker-local section 2) and reaches warehouse_db and the analyzer over loopback only (D-301c). Messages name keys and
reasons, never values."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

LOOPBACK = frozenset({"localhost", "127.0.0.1", "::1"})
WAREHOUSE_DB_NAME = "warehouse_db"
APP_ROLE = "warehouse_db_app"
MIGRATOR_ROLE = "warehouse_db_migrator"
MIN_SECRET_CHARS = 32
# ml/src/quancrypt_ml/infrastructure/settings.py -> ml
ML_ROOT = Path(__file__).resolve().parents[3]
REPO_ROOT = ML_ROOT.parent


class ConfigError(Exception):
    """The configuration is missing or invalid; the message never contains a value."""


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    password: str = field(repr=False)


@dataclass(frozen=True)
class AnalyzerSettings:
    url: str
    token: str = field(repr=False)
    timeout_s: float = 30.0


@dataclass(frozen=True)
class Paths:
    labeling_dir: Path
    reports_dir: Path
    manifest: Path
    scope_dir: Path
    agent_scope_set: Path
    migrations_dir: Path


def _db_problems(name: str, value: str, role: str) -> list[str]:
    try:
        url = make_url(value)
    except ArgumentError:
        return [f"{name}: not a database URL"]
    reasons = []
    if url.drivername != "postgresql+psycopg":
        reasons.append("the driver must be postgresql+psycopg")
    if url.host not in LOOPBACK:
        reasons.append("the host must be one of: " + ", ".join(sorted(LOOPBACK)))
    if url.database != WAREHOUSE_DB_NAME:
        reasons.append(f"the database must be {WAREHOUSE_DB_NAME}")
    if url.username != role:
        reasons.append(f"the role must be {role}")
    if url.password is not None:
        reasons.append("the URL must not carry the password (it has its own variable)")
    if url.query:
        reasons.append("the URL must not carry a query string")
    return [f"{name}: " + "; ".join(reasons)] if reasons else []


def _secret_problems(name: str, value: str) -> list[str]:
    if len(value) < MIN_SECRET_CHARS or "CHANGE_ME" in value:
        return [f"{name}: missing, shorter than {MIN_SECRET_CHARS} characters or still the placeholder"]
    return []


def _raise(problems: list[str]) -> None:
    if problems:
        raise ConfigError("; ".join(problems))


def load_database(source: Mapping[str, str], migrator: bool = False) -> DatabaseSettings:
    """The application role (labels, the sample) or, for `ml migrate`, the migrator role (DDL of the labels schema)."""
    prefix, role = ("WAREHOUSE_DB_MIGRATOR", MIGRATOR_ROLE) if migrator else ("WAREHOUSE_DB", APP_ROLE)
    url_key = f"{prefix}_URL"
    password_key = "WAREHOUSE_DB_MIGRATOR_PASSWORD" if migrator else "WAREHOUSE_DB_APP_PASSWORD"
    problems = _db_problems(url_key, source.get(url_key, ""), role)
    password = source.get(password_key, "")
    if not password or "CHANGE_ME" in password:
        problems.append(f"{password_key}: missing or still the placeholder")
    _raise(problems)
    return DatabaseSettings(source[url_key], password)


def load_analyzer(source: Mapping[str, str]) -> AnalyzerSettings:
    url = source.get("CORPUS_ANALYZER_URL", "http://127.0.0.1:8082")
    problems = _secret_problems("INTERNAL_SERVICE_TOKEN", source.get("INTERNAL_SERVICE_TOKEN", ""))
    parts = urlsplit(url)
    try:
        port = parts.port
    except ValueError:
        port = -1
    if parts.scheme != "http" or parts.hostname not in LOOPBACK or parts.username or parts.password or port == -1:
        problems.append("CORPUS_ANALYZER_URL: an http address on loopback, without credentials")
    elif parts.path not in ("", "/") or parts.query or parts.fragment:
        problems.append("CORPUS_ANALYZER_URL: the bare address, without a path")
    _raise(problems)
    return AnalyzerSettings(url.rstrip("/"), source["INTERNAL_SERVICE_TOKEN"])


def load_salt(source: Mapping[str, str]) -> str:
    salt = source.get("QUANCRYPT_ANON_SALT", "")
    _raise(_secret_problems("QUANCRYPT_ANON_SALT", salt))
    return salt


def load_paths(source: Mapping[str, str]) -> Paths:
    def path(key: str, default: Path) -> Path:
        value = source.get(key, "")
        return Path(value) if value else default

    return Paths(
        labeling_dir=path("ML_LABELING_DIR", ML_ROOT / "labeling"),
        reports_dir=path("ML_REPORTS_DIR", ML_ROOT / "reports"),
        manifest=path("CORPUS_MANIFEST", REPO_ROOT / "data-platform" / "reports" / "corpus_manifest.csv"),
        scope_dir=ML_ROOT / "data" / "scope",
        agent_scope_set=REPO_ROOT / "services" / "agent-service" / "data" / "examples" / "scope_set.jsonl",
        migrations_dir=ML_ROOT / "migrations",
    )
