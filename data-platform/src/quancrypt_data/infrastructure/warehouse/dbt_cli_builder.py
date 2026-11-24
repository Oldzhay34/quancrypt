"""Runs dbt as a child process (P6.6, D-319): `dbt build` over the project data-platform/dbt/quancrypt_dw.

- The connection (the migrator role: dbt creates the schemas and tables) reaches dbt through DBT_* variables of the
  child only; the profile file holds no secret (profiles.yml.example reads env_var) and lives in a temporary directory.
- The child gets a minimal environment: no proxy, no telemetry (DBT_SEND_ANONYMOUS_USAGE_STATS=false, DO_NOT_TRACK=1)
  and none of the other variables of the parent.
- The result is read from target/run_results.json; the output of dbt is not shown (it can name rows of tests), the
  failed nodes are named and the log stays in the project's logs/ directory."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from quancrypt_data.port.outbound.warehouse import BuildOutcome

_MAX_FAILED_NAMES = 30
_NODE_KINDS = ("seed", "snapshot", "model")
_OK_BUILD = frozenset({"success"})
_OK_TEST = frozenset({"pass"})
_BAD = frozenset({"error", "fail", "runtime error"})


def _kill_group(process: subprocess.Popen[bytes]) -> None:
    """SIGKILL to the process group of the child and a wait until the group is gone."""
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    process.wait()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            os.killpg(process.pid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    # A process that cannot be killed (stuck in the kernel): the lock must not be released as if dbt had stopped.
    raise DbtError("the dbt processes could not be stopped")


class DbtError(Exception):
    """dbt could not be run or left no result (the message names the reason, never an output of dbt)."""


@dataclass(frozen=True)
class DbtConnection:
    host: str
    port: int
    user: str
    password: str = field(repr=False)
    dbname: str


class DbtCliBuilder:
    def __init__(
        self, project_dir: Path, command: Sequence[str], connection: DbtConnection, timeout_s: int = 1800
    ) -> None:
        self._project_dir = project_dir
        self._command = tuple(command)
        self._connection = connection
        self._timeout_s = timeout_s

    def build(self) -> BuildOutcome:
        if not (self._project_dir / "dbt_packages" / "dbt_utils").is_dir():
            raise DbtError("dbt packages are not installed: run `make warehouse-deps` once")
        example = self._project_dir / "profiles.yml.example"
        if not example.is_file():
            raise DbtError("profiles.yml.example is missing")
        started = time.monotonic()
        with tempfile.TemporaryDirectory(prefix="dbt-profile-") as profiles_dir:
            shutil.copyfile(example, Path(profiles_dir) / "profiles.yml")
            run_results = self._project_dir / "target" / "run_results.json"
            run_results.unlink(missing_ok=True)
            returncode = self._run(profiles_dir)
        outcome = self._read(run_results, time.monotonic() - started)
        if returncode != 0 and outcome.ok:
            # dbt failed before it ran a node (a connection or a parse error): there is nothing to name.
            return replace(outcome, ok=False, failed=(f"dbt ended with exit code {returncode}",))
        return outcome

    def _run(self, profiles_dir: str) -> int:
        """Runs the child in a process group of its own and, however the wait ends (timeout, interrupt), kills the
        whole group before returning: `uv run dbt` is two processes, and a dbt left running would keep writing the
        tables after the build lock is released (KVKK, D-319d)."""
        try:
            process = subprocess.Popen(  # noqa: S603 (a fixed command line, no shell)
                [
                    *self._command,
                    "build",
                    "--project-dir",
                    str(self._project_dir),
                    "--profiles-dir",
                    profiles_dir,
                    "--no-use-colors",
                ],
                env=self._environment(),
                cwd=self._project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
            )
        except FileNotFoundError:
            raise DbtError("the dbt command was not found") from None
        try:
            process.communicate(timeout=self._timeout_s)
        except subprocess.TimeoutExpired:
            _kill_group(process)
            raise DbtError("dbt build timed out") from None
        except BaseException:
            _kill_group(process)
            raise
        # The child ended, but a grandchild it left behind (a worker) must not outlive the lock either.
        _kill_group(process)
        return process.returncode

    def _environment(self) -> dict[str, str]:
        base = {
            key: os.environ[key]
            for key in ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "UV_CACHE_DIR")
            if key in os.environ
        }
        return {
            **base,
            "DBT_HOST": self._connection.host,
            "DBT_PORT": str(self._connection.port),
            "DBT_USER": self._connection.user,
            "DBT_PASSWORD": self._connection.password,
            "DBT_DBNAME": self._connection.dbname,
            "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
            "DO_NOT_TRACK": "1",
        }

    @staticmethod
    def _read(path: Path, duration_s: float) -> BuildOutcome:
        if not path.is_file():
            raise DbtError("dbt left no run_results.json (it failed before it ran a node)")
        try:
            results = json.loads(path.read_text(encoding="utf-8"))["results"]
        except (OSError, ValueError, KeyError):
            raise DbtError("run_results.json cannot be read") from None
        built = dict.fromkeys(_NODE_KINDS, 0)
        passed = failed_tests = warned = skipped = 0
        failed: list[str] = []
        for result in results:
            unique_id = str(result.get("unique_id", ""))
            kind = unique_id.split(".", 1)[0]
            status = str(result.get("status", ""))
            if status == "skipped":
                skipped += 1
            elif kind == "test":
                if status in _OK_TEST:
                    passed += 1
                elif status == "warn":
                    warned += 1
                else:
                    failed_tests += 1
            elif kind in built and status in _OK_BUILD:
                built[kind] += 1
            if status in _BAD and len(failed) < _MAX_FAILED_NAMES:
                failed.append(unique_id)
        # A build that built nothing (no node selected) is no success.
        ok = not failed and failed_tests == 0 and sum(built.values()) > 0
        return BuildOutcome(ok, built, passed, failed_tests, warned, skipped, tuple(failed), duration_s)
