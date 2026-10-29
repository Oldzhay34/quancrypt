"""Configuration of the corpus command line (host side), from the environment: validated at startup, messages name keys
and reasons, never values (the same rules as ingest-api's settings)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from quancrypt_data.infrastructure.settings import (
    LOG_LEVELS,
    MIN_TOKEN_CHARS,
    ConfigError,
    DatabaseSettings,
    load_database_settings,
)

# The command line runs on the host, where the compose service names do not resolve (or, with a search domain,
# could resolve
# elsewhere and receive the token): loopback only.
LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "[::1]"})
ANALYZER_HOSTS = LOOPBACK_HOSTS
INGEST_HOSTS = LOOPBACK_HOSTS
# data-platform/src/quancrypt_data/infrastructure/corpus/settings.py -> data-platform
_ROOT = Path(__file__).resolve().parents[4]


@dataclass(frozen=True)
class CorpusSettings:
    corpus_root: Path
    reference_dir: Path
    reports_dir: Path
    datasets_root: Path | None
    analyzer_url: str
    ingest_url: str
    internal_token: str = field(repr=False)
    anon_salt: str = field(repr=False)
    analyzer_mount: str
    git_timeout_s: int
    analysis_timeout_s: int
    ingest_timeout_s: int
    log_level: str
    database: DatabaseSettings | None


def load_corpus_settings(env: Mapping[str, str] | None = None, *, need_database: bool = False) -> CorpusSettings:
    source = os.environ if env is None else env
    problems: list[str] = []

    def directory(name: str, *, required: bool) -> Path | None:
        value = source.get(name, "")
        if not value:
            if required:
                problems.append(f"{name}: missing")
            return None
        path = Path(value)
        if not path.is_absolute():
            problems.append(f"{name}: must be an absolute path")
            return None
        return path

    def url(name: str, default: str, hosts: frozenset[str]) -> str:
        value = source.get(name, default)
        parts = urlsplit(value)
        host = f"[{parts.hostname}]" if parts.hostname and ":" in parts.hostname else (parts.hostname or "")
        reasons = []
        if parts.scheme not in {"http", "https"}:
            reasons.append("the scheme must be http or https")
        if host not in hosts:
            reasons.append("the host must be one of: " + ", ".join(sorted(hosts)))
        if parts.username is not None or parts.password is not None:
            reasons.append("the URL must not carry credentials")
        try:
            port_ok = parts.port is None or 1 <= parts.port <= 65535
        except ValueError:
            port_ok = False
        if not port_ok:
            reasons.append("the port must be between 1 and 65535")
        if parts.query or parts.fragment:
            reasons.append("the URL must not carry a query string or fragment")
        if reasons:
            problems.append(f"{name}: " + "; ".join(reasons))
        return value

    corpus_root = directory("CORPUS_ROOT", required=True)
    datasets_root = directory("DATASETS_ROOT", required=False)
    analyzer_url = url("CORPUS_ANALYZER_URL", "http://127.0.0.1:8082", ANALYZER_HOSTS)
    ingest_url = url("CORPUS_INGEST_URL", "http://127.0.0.1:8084/api/v1/events", INGEST_HOSTS)
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
    salt = source.get("QUANCRYPT_ANON_SALT", "")
    if len(salt) < MIN_TOKEN_CHARS or "CHANGE_ME" in salt:
        problems.append(f"QUANCRYPT_ANON_SALT: at least {MIN_TOKEN_CHARS} characters, not the placeholder")
    level = source.get("LOG_LEVEL", "INFO")
    if level not in LOG_LEVELS:
        problems.append("LOG_LEVEL: one of " + ", ".join(sorted(LOG_LEVELS)))
    database: DatabaseSettings | None = None
    if need_database:
        try:
            database = load_database_settings(source)
        except ConfigError as exc:
            problems.append(str(exc).removeprefix("Invalid configuration: "))
    if problems or corpus_root is None:
        raise ConfigError("Invalid configuration: " + " | ".join(problems))
    return CorpusSettings(
        corpus_root=corpus_root,
        reference_dir=Path(source.get("CORPUS_REFERENCE_DIR") or _ROOT / "reference"),
        reports_dir=Path(source.get("CORPUS_REPORTS_DIR") or _ROOT / "reports"),
        datasets_root=datasets_root,
        analyzer_url=analyzer_url,
        ingest_url=ingest_url,
        internal_token=token,
        anon_salt=salt,
        analyzer_mount="/corpus",
        git_timeout_s=600,
        analysis_timeout_s=330,
        ingest_timeout_s=60,
        log_level=level,
        database=database,
    )
