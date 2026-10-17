"""A throw-away PostgreSQL with pgvector for the integration tests (docker CLI; D-231b, field-device-sim D-119
precedent).

The container runs the project's own `infra/postgres/init` scripts with random passwords, so the roles (migrator
owns, app
does DML) are exactly the production ones. Docker missing or the image absent is a test FAILURE, never a skip.
"""

from __future__ import annotations

import atexit
import secrets
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.memory.memory_store import DatabaseConfig

IMAGE = "pgvector/pgvector:0.8.7-pg16"
REPO_ROOT = Path(__file__).resolve().parents[4]
INIT_DIR = REPO_ROOT / "infra" / "postgres" / "init"
_PASSWORD_VARIABLES = (
    "POSTGRES_PASSWORD",
    "CORE_DB_MIGRATOR_PASSWORD",
    "CORE_DB_APP_PASSWORD",
    "AGENT_DB_MIGRATOR_PASSWORD",
    "AGENT_DB_APP_PASSWORD",
    "WAREHOUSE_DB_MIGRATOR_PASSWORD",
    "WAREHOUSE_DB_APP_PASSWORD",
    "WAREHOUSE_READER_PASSWORD",
    "MLFLOW_DB_MIGRATOR_PASSWORD",
    "MLFLOW_DB_APP_PASSWORD",
)


@dataclass(frozen=True)
class PostgresInstance:
    name: str
    port: int
    app_password: str
    migrator_password: str

    def config(self, *, pool_size: int = 5) -> DatabaseConfig:
        base = f"postgresql+psycopg://{{role}}@127.0.0.1:{self.port}/agent_db"
        return DatabaseConfig(
            url=base.format(role="agent_db_app"),
            migrator_url=base.format(role="agent_db_migrator"),
            pool_size=pool_size,
            connect_timeout_s=5,
            app_password=self.app_password,
            migrator_password=self.migrator_password,
        )


def _docker(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=check, timeout=120)  # noqa: S603, S607


def start_postgres() -> PostgresInstance:
    if _docker("info", check=False).returncode != 0:
        pytest.fail(
            "Docker is not reachable. Start Docker Desktop before `make verify` (the PostgreSQL tests need it)."
        )
    if _docker("image", "inspect", IMAGE, check=False).returncode != 0:
        pytest.fail(f"The image {IMAGE} is not present locally (D-45); pull it once before `make verify`.")
    passwords = {name: secrets.token_hex(16) for name in _PASSWORD_VARIABLES}
    name = f"quancrypt-agentdb-test-{uuid.uuid4().hex[:8]}"
    command = ["run", "-d", "--rm", "--name", name, "--pull", "never", "-p", "127.0.0.1::5432"]
    for variable, value in passwords.items():
        command += ["-e", f"{variable}={value}"]
    command += ["-v", f"{INIT_DIR}:/docker-entrypoint-initdb.d:ro", IMAGE]
    _docker(*command)
    atexit.register(stop_postgres, name)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        ready = _docker("exec", name, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "agent_db", check=False)
        if ready.returncode == 0:
            break
        time.sleep(1)
    else:
        logs = _docker("logs", "--tail", "20", name, check=False).stdout[-1500:]
        stop_postgres(name)
        pytest.fail(f"PostgreSQL did not become ready in 120 s. Last log lines:\n{logs}")
    mapping = _docker("port", name, "5432/tcp").stdout.strip().splitlines()[0]
    return PostgresInstance(
        name=name,
        port=int(mapping.rsplit(":", 1)[1]),
        app_password=passwords["AGENT_DB_APP_PASSWORD"],
        migrator_password=passwords["AGENT_DB_MIGRATOR_PASSWORD"],
    )


def stop_postgres(name: str) -> None:
    _docker("rm", "-f", name, check=False)
