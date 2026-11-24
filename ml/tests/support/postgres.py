"""A throw-away PostgreSQL for the integration tests (docker CLI; data-platform and agent-service precedent, D-231b).

The container runs the project's own `infra/postgres/init` scripts with random passwords, so the roles are the production
ones. Docker missing or the image absent is a test FAILURE, never a skip."""

from __future__ import annotations

import atexit
import secrets
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import URL

from quancrypt_ml.infrastructure.settings import DatabaseSettings

IMAGE = "pgvector/pgvector:0.8.7-pg16"
REPO_ROOT = Path(__file__).resolve().parents[3]
INIT_DIR = REPO_ROOT / "infra" / "postgres" / "init"
MIGRATIONS_DIR = REPO_ROOT / "ml" / "migrations"
_PASSWORDS = (
    "POSTGRES_PASSWORD", "CORE_DB_MIGRATOR_PASSWORD", "CORE_DB_APP_PASSWORD", "AGENT_DB_MIGRATOR_PASSWORD",
    "AGENT_DB_APP_PASSWORD", "WAREHOUSE_DB_MIGRATOR_PASSWORD", "WAREHOUSE_DB_APP_PASSWORD", "WAREHOUSE_READER_PASSWORD",
    "MLFLOW_DB_MIGRATOR_PASSWORD", "MLFLOW_DB_APP_PASSWORD",
)  # fmt: skip


@dataclass(frozen=True)
class PostgresInstance:
    name: str
    port: int
    passwords: dict[str, str]

    def settings(self, migrator: bool = False) -> DatabaseSettings:
        role = "warehouse_db_migrator" if migrator else "warehouse_db_app"
        key = "WAREHOUSE_DB_MIGRATOR_PASSWORD" if migrator else "WAREHOUSE_DB_APP_PASSWORD"
        return DatabaseSettings(f"postgresql+psycopg://{role}@127.0.0.1:{self.port}/warehouse_db", self.passwords[key])

    def engine(self, role: str) -> Engine:
        key = {"warehouse_db_app": "WAREHOUSE_DB_APP_PASSWORD", "warehouse_db_migrator": "WAREHOUSE_DB_MIGRATOR_PASSWORD",
               "warehouse_reader": "WAREHOUSE_READER_PASSWORD"}[role]  # fmt: skip
        url = URL.create("postgresql+psycopg", username=role, password=self.passwords[key], host="127.0.0.1",
                         port=self.port, database="warehouse_db")  # fmt: skip
        return create_engine(url, hide_parameters=True)


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=120)  # noqa: S603, S607


def start_postgres() -> PostgresInstance:
    if _docker("info", check=False).returncode != 0:
        pytest.fail(
            "Docker is not reachable. Start Docker Desktop before `make verify` (the PostgreSQL tests need it)."
        )
    if _docker("image", "inspect", IMAGE, check=False).returncode != 0:
        pytest.fail(f"The image {IMAGE} is not present locally (D-45); pull it once before `make verify`.")
    passwords = {name: secrets.token_hex(16) for name in _PASSWORDS}
    name = f"quancrypt-ml-test-{uuid.uuid4().hex[:8]}"
    command = ["run", "-d", "--rm", "--name", name, "--pull", "never", "-p", "127.0.0.1::5432"]
    for variable, value in passwords.items():
        command += ["-e", f"{variable}={value}"]
    command += ["-v", f"{INIT_DIR}:/docker-entrypoint-initdb.d:ro", IMAGE]
    _docker(*command)
    atexit.register(stop_postgres, name)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready = _docker(
            "exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "warehouse_db", check=False
        )
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        stop_postgres(name)
        pytest.fail("PostgreSQL did not become ready in 120 s.")
    mapping = _docker("port", name, "5432/tcp").stdout.strip().splitlines()[0]
    return PostgresInstance(name, int(mapping.rsplit(":", 1)[1]), passwords)


def stop_postgres(name: str) -> None:
    _docker("rm", "-f", name, check=False)
