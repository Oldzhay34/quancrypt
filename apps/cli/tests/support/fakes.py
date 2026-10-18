"""Test doubles of the outbound ports (test doubles are free; production code has none)."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from quancrypt_cli.domain.project import ProjectConfig
from quancrypt_cli.domain.services import ServiceEndpoint, ServiceHealth
from quancrypt_cli.domain.session_token import SessionToken
from quancrypt_cli.port.outbound.core_api_client import RegisteredProject
from quancrypt_cli.port.outbound.errors import ComposeError, CoreApiError, StateStoreError

NOW = datetime(2026, 10, 19, 9, 0, tzinfo=UTC)
ROOT = Path("/work/qbank")
PROJECT_ID = "00000000-0000-0000-0000-00000000a001"


def token(seed: int = 1) -> SessionToken:
    """A valid token whose text differs per seed."""
    return SessionToken(f"{seed:043d}".replace("0", "A"))


class FakeFileSystem:
    """Directories as a mapping path -> names inside; text files as a mapping path -> lines."""

    def __init__(
        self, directories: dict[Path, frozenset[str]] | None = None, files: dict[Path, list[str]] | None = None
    ):
        self.directories = directories if directories is not None else {ROOT: frozenset({"pom.xml", "src"})}
        self.files = files if files is not None else {}

    def absolute(self, path: str) -> Path:
        return ROOT if path in (".", "") else Path(path)

    def is_directory(self, path: Path) -> bool:
        return path in self.directories

    def entries(self, path: Path) -> frozenset[str]:
        return self.directories[path]

    def read_lines(self, path: Path) -> list[str] | None:
        return self.files.get(path)


class InMemoryStateStore:
    def __init__(self, protected: bool = True) -> None:
        self.configs: dict[Path, ProjectConfig] = {}
        self.tokens: dict[Path, SessionToken] = {}
        self.protected = protected
        self.writes: list[str] = []
        self.fail_with: StateStoreError | None = None

    def load_config(self, root: Path) -> ProjectConfig | None:
        if self.fail_with:
            raise self.fail_with
        return self.configs.get(root)

    def save_config(self, root: Path, config: ProjectConfig) -> None:
        self.writes.append("config")
        self.configs[root] = config

    def save_token(self, root: Path, token: SessionToken) -> bool:
        self.writes.append("token")
        self.tokens[root] = token
        return self.protected

    def load_token(self, root: Path) -> SessionToken | None:
        return self.tokens.get(root)


class CountingTokenGenerator:
    def __init__(self) -> None:
        self.count = 0

    def generate(self) -> SessionToken:
        self.count += 1
        return token(self.count)


class FakeCompose:
    def __init__(self, error: ComposeError | None = None) -> None:
        self.error = error
        self.up_calls: list[tuple[Path, SessionToken, int]] = []
        self.down_calls = 0

    def up(self, project_root: Path, token: SessionToken, wait_timeout_s: int) -> None:
        self.up_calls.append((project_root, token, wait_timeout_s))
        if self.error:
            raise self.error

    def down(self) -> None:
        self.down_calls += 1
        if self.error:
            raise self.error


class FakeProbe:
    """Every service healthy except the named ones; `ready_after` makes the backend ready after that many rounds."""

    def __init__(self, down: Sequence[str] = (), ready_after: int = 0) -> None:
        self.down = set(down)
        self.ready_after = ready_after
        self.calls: list[str] = []
        self._rounds: dict[str, int] = {}

    def check(self, endpoint: ServiceEndpoint) -> ServiceHealth:
        self.calls.append(endpoint.name)
        rounds = self._rounds.get(endpoint.name, 0)
        self._rounds[endpoint.name] = rounds + 1
        healthy = endpoint.name not in self.down and rounds >= self.ready_after
        return ServiceHealth(endpoint.name, healthy, "HTTP 200" if healthy else "not reachable")


class FakeCore:
    def __init__(self, created: bool = True, error: CoreApiError | None = None) -> None:
        self.created = created
        self.error = error
        self.calls: list[tuple[SessionToken, str, str]] = []

    def register_project(self, token: SessionToken, identity: str, display_name: str) -> RegisteredProject:
        self.calls.append((token, identity, display_name))
        if self.error:
            raise self.error
        return RegisteredProject(PROJECT_ID, self.created)


class FakeBrowser:
    def __init__(self, succeeds: bool = True) -> None:
        self.succeeds = succeeds
        self.urls: list[str] = []

    def open(self, url: str) -> bool:
        self.urls.append(url)
        return self.succeeds


class FakeClock:
    def __init__(self) -> None:
        self.time = 0.0
        self.sleeps: list[float] = []

    def now(self) -> datetime:
        return NOW

    def monotonic(self) -> float:
        return self.time

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.time += seconds
