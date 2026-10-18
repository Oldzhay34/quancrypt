"""Source-level rules that import-linter cannot express (docker-local, guardrails-security, D-272, D-277)."""

from __future__ import annotations

import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "src" / "quancrypt_cli"
STATE_STORE = "infrastructure/file_project_state_store.py"


def sources() -> list[Path]:
    return sorted(SOURCE.rglob("*.py"))


def test_no_source_file_uses_a_shell() -> None:
    pattern = re.compile(r"shell\s*=\s*True|os\.system|os\.popen|subprocess\.(call|getoutput|getstatusoutput)\b")

    assert [str(p) for p in sources() if pattern.search(p.read_text())] == []


def test_only_the_state_store_writes_to_the_disk() -> None:
    writers = re.compile(
        r"\.write_text|\.write_bytes|os\.open\(|\.mkdir\(|\.unlink\(|os\.replace|os\.remove|shutil\.|open\([^)]*[\"'][wax]"
    )
    offenders = [p.relative_to(SOURCE).as_posix() for p in sources() if writers.search(p.read_text())]

    assert offenders == [STATE_STORE]  # D-272: the user's project is written nowhere else


def test_the_state_store_only_names_the_quancrypt_directory() -> None:
    text = (SOURCE / STATE_STORE).read_text()

    assert 'STATE_DIR = ".quancrypt"' in text
    assert "root /" not in text.replace("root / STATE_DIR", "")  # every path under the project goes through STATE_DIR


def test_only_the_compose_runner_imports_subprocess_and_only_the_opener_the_browser() -> None:
    for module, owner in (("subprocess", "docker_compose_runner.py"), ("webbrowser", "webbrowser_opener.py")):
        users = [p.name for p in sources() if re.search(rf"^\s*import {module}\b", p.read_text(), re.MULTILINE)]
        assert users == [owner]


def test_the_session_token_value_is_read_in_adapters_and_the_domain_only() -> None:
    allowed = {
        "domain/session_token.py",
        "domain/services.py",  # the UI address carries it in the fragment
        "infrastructure/docker_compose_runner.py",
        "infrastructure/file_project_state_store.py",
        "infrastructure/http_core_api_client.py",
    }
    users = {
        p.relative_to(SOURCE).as_posix()
        for p in sources()
        if re.search(r"\btoken\.value\b|\.value\b.*token", p.read_text())
    }

    assert users - allowed == set()
