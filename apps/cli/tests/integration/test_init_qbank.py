"""`quancrypt init` end to end on a temporary copy of QBank (P5.1 acceptance, `make integration`).

Needs Docker, ports 8080-8083 free and a Quancrypt installation directory: `QUANCRYPT_HOME` is the repository root
(or any directory with docker-compose.yml and a filled `.env`, no CHANGE_ME). The first run builds the images. The
tests fail, never skip, when the prerequisites are missing. The web UI (P5.2) does not exist yet: a stub server on
127.0.0.1:8080 stands in for it, so that the test shows the CLI neither trusts it nor starts a browser.

    QUANCRYPT_HOME=/path/to/quancrypt make integration
"""

from __future__ import annotations

import hashlib
import http.server
import os
import shutil
import stat
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.integration

REPO = Path(__file__).resolve().parents[4]
QBANK = REPO / "reference-system" / "qbank-payment-service"
CLI_SOURCE = Path(__file__).resolve().parents[2] / "src"
UI_PORT = 8080
READINESS = ("http://127.0.0.1:8081", "http://127.0.0.1:8082", "http://127.0.0.1:8083")


class _Stub(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"stub web ui")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002 - signature of the base class
        return


@pytest.fixture
def stub_ui() -> Iterator[None]:
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", UI_PORT), _Stub)
    except OSError as error:
        pytest.fail(f"port {UI_PORT} must be free for the stand-in web UI: {error}")
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield
    server.shutdown()
    server.server_close()


@pytest.fixture
def quancrypt_home() -> str:
    home = os.environ.get("QUANCRYPT_HOME", "")
    if not home or not (Path(home) / "docker-compose.yml").is_file() or not (Path(home) / ".env").is_file():
        pytest.fail("QUANCRYPT_HOME must name a directory with docker-compose.yml and .env (see this file's docstring)")
    return home


@pytest.fixture
def qbank_copy(tmp_path: Path) -> Path:
    copy = tmp_path / "qbank"
    shutil.copytree(QBANK, copy, ignore=shutil.ignore_patterns("build", ".gradle", ".quancrypt"))
    return copy


@pytest.fixture
def capture_browser(tmp_path: Path) -> tuple[str, Path]:
    """A `BROWSER` command that writes the address it is given to a file instead of opening a window."""
    log = tmp_path / "browser.log"
    script = tmp_path / "capture-browser.sh"
    script.write_text(f'#!/bin/sh\nprintf "%s" "$1" > "{log}"\n')
    script.chmod(0o755)
    return f"{script} %s", log


def quancrypt(arguments: list[str], home: str, browser: str, *, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = {
        **os.environ,
        "QUANCRYPT_HOME": home,
        "BROWSER": browser,
        "QUANCRYPT_LANG": "en",
        "PYTHONPATH": str(CLI_SOURCE),
    }
    return subprocess.run(
        [sys.executable, "-m", "quancrypt_cli", *arguments],
        capture_output=True,
        text=True,
        env=environment,
        cwd=cwd,
        timeout=3600,
        check=False,
    )


def tree_digest(root: Path) -> dict[str, str]:
    """Every file of the project (except `.quancrypt/`) with a hash of its content."""
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".quancrypt" not in path.relative_to(root).parts
    }


def test_init_sets_up_a_qbank_copy_end_to_end(
    stub_ui: None, quancrypt_home: str, qbank_copy: Path, capture_browser: tuple[str, Path]
) -> None:
    browser, browser_log = capture_browser
    before_tree = tree_digest(qbank_copy)
    before_names = {path.name for path in qbank_copy.iterdir()}
    was_running = quancrypt(["status"], quancrypt_home, browser, cwd=qbank_copy).returncode == 0
    try:
        first = quancrypt(["init", "--path", str(qbank_copy)], quancrypt_home, browser, cwd=qbank_copy)
        assert first.returncode == 0, first.stdout + first.stderr

        token_file = qbank_copy / ".quancrypt" / "session.token"
        token = token_file.read_text().strip()
        # Acceptance: the token file is mode 600 and the token is in no output.
        assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
        assert len(token) == 43
        # (booleans, so that a failure does not print the token through the assertion rewrite)
        leaked = token in first.stdout or token in first.stderr
        assert not leaked, "the session token appeared in the output"
        # D-279: the address is printed without the token and no browser is started, although something
        # (the stub) answers on 8080.
        assert f"Web UI address: http://127.0.0.1:{UI_PORT}" in first.stdout
        assert not browser_log.exists(), "a browser was started"
        # The user's project got `.quancrypt/` and nothing else changed (D-272).
        assert {path.name for path in qbank_copy.iterdir()} - before_names == {".quancrypt"}
        assert sorted(entry.name for entry in (qbank_copy / ".quancrypt").iterdir()) == ["config.yaml", "session.token"]
        assert tree_digest(qbank_copy) == before_tree
        # The QBank copy has no .gitignore: the CLI advises, it does not write one.
        assert "Add this line yourself: .quancrypt/" in first.stdout
        assert not (qbank_copy / ".gitignore").exists()

        # The services are healthy ...
        for base in READINESS:
            assert httpx.get(f"{base}/health/readiness", timeout=5, trust_env=False).status_code == 200
        assert quancrypt(["status"], quancrypt_home, browser, cwd=qbank_copy).returncode == 0

        # ... and the project is registered in core-service with the session token.
        listing = httpx.get(
            "http://127.0.0.1:8081/api/v1/projects",
            params={"size": 200},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            trust_env=False,
        )
        assert listing.status_code == 200
        assert any(item["displayName"] == "qbank" for item in listing.json()["items"])

        # A second init makes a new token, keeps the config and finds the project registered (D-273, D-129).
        config_before = (qbank_copy / ".quancrypt" / "config.yaml").read_text()
        second = quancrypt(["init", "--path", str(qbank_copy)], quancrypt_home, browser, cwd=qbank_copy)
        assert second.returncode == 0, second.stdout + second.stderr
        new_token = token_file.read_text().strip()
        renewed = new_token != token
        assert renewed
        assert (qbank_copy / ".quancrypt" / "config.yaml").read_text() == config_before
        assert "already registered" in second.stdout
    finally:
        if not was_running:
            quancrypt(["down"], quancrypt_home, browser, cwd=qbank_copy)


def test_init_in_a_directory_without_a_build_file_writes_nothing(
    quancrypt_home: str, tmp_path: Path, capture_browser: tuple[str, Path]
) -> None:
    empty = tmp_path / "not-a-project"
    empty.mkdir()
    (empty / "README.md").write_text("hello")

    result = quancrypt(["init", "--path", str(empty)], quancrypt_home, capture_browser[0], cwd=empty)

    assert result.returncode == 1 and "pom.xml" in result.stderr
    assert sorted(path.name for path in empty.iterdir()) == ["README.md"]
