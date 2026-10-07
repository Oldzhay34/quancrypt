"""Layer rules of hexagonal-service (D-05): the import-linter contracts of pyproject.toml plus a stdlib-only domain."""

from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
PACKAGE = PROJECT / "src" / "field_device_sim"
ROOT_NAME = "field_device_sim"


def test_the_import_linter_contracts_hold() -> None:
    # In a child process: import-linter changes the global logging state of the interpreter it runs in.
    result = subprocess.run(
        [sys.executable, "-c", "from importlinter.cli import lint_imports; raise SystemExit(lint_imports())"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        env={**os.environ, "PYTHONPATH": str(PROJECT / "src")},
    )

    assert result.returncode == 0, result.stdout + result.stderr


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0] if node.module.split(".")[0] != ROOT_NAME else node.module)
    return modules


def test_the_domain_imports_only_the_standard_library_and_itself() -> None:
    allowed_internal = {f"{ROOT_NAME}.domain.terminal_transaction", f"{ROOT_NAME}.domain"}
    for path in (PACKAGE / "domain").glob("*.py"):
        for module in _imported_modules(path):
            assert module in sys.stdlib_module_names or module in allowed_internal, f"{path.name} imports {module}"


def test_ports_and_use_cases_import_no_third_party_package() -> None:
    for layer in ("port", "usecase", "facade", "api"):
        for path in (PACKAGE / layer).rglob("*.py"):
            for module in _imported_modules(path):
                assert module in sys.stdlib_module_names or module.startswith(ROOT_NAME), f"{path} imports {module}"
