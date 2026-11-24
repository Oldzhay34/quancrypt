"""BuildWarehouse (P6.6): the use case with fake ports, the facade, the command and the dbt child process."""

from __future__ import annotations

import json
import os
import stat
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quancrypt_data.api import cli
from quancrypt_data.api.cli import app
from quancrypt_data.facade.warehouse_facade import WarehouseBuildError, WarehouseFacade
from quancrypt_data.infrastructure.warehouse.dbt_cli_builder import DbtCliBuilder, DbtConnection, DbtError
from quancrypt_data.port.inbound.build_warehouse import BuildWarehouseResult
from quancrypt_data.port.outbound.warehouse import BuildOutcome, WarehouseBusyError
from quancrypt_data.usecase.build_warehouse_service import BuildWarehouseService

OK = BuildOutcome(True, {"seed": 2, "snapshot": 2, "model": 33}, 120, 0, 1, 0, (), 12.5)


class RecordingLock:
    def __init__(self, events: list[str], busy: bool = False) -> None:
        self._events = events
        self._busy = busy

    @contextmanager
    def held(self) -> Iterator[None]:
        if self._busy:
            raise WarehouseBusyError("busy")
        self._events.append("lock")
        try:
            yield
        finally:
            self._events.append("unlock")


class FakeBuilder:
    def __init__(self, events: list[str], outcome: BuildOutcome = OK, error: Exception | None = None) -> None:
        self._events = events
        self._outcome = outcome
        self._error = error

    def build(self) -> BuildOutcome:
        self._events.append("build")
        if self._error is not None:
            raise self._error
        return self._outcome


class TestService:
    def test_dbt_runs_while_the_lock_is_held(self) -> None:
        events: list[str] = []

        result = BuildWarehouseService(RecordingLock(events), FakeBuilder(events)).execute()

        assert events == ["lock", "build", "unlock"]
        assert result.ok and result.built == {"seed": 2, "snapshot": 2, "model": 33} and result.tests_passed == 120

    def test_the_lock_is_released_when_dbt_fails(self) -> None:
        events: list[str] = []

        with pytest.raises(DbtError):
            BuildWarehouseService(RecordingLock(events), FakeBuilder(events, error=DbtError("x"))).execute()

        assert events == ["lock", "build", "unlock"]

    def test_a_busy_lock_means_dbt_never_starts(self) -> None:
        events: list[str] = []

        with pytest.raises(WarehouseBusyError):
            BuildWarehouseService(RecordingLock(events, busy=True), FakeBuilder(events)).execute()

        assert events == []


class StubUseCase:
    def __init__(self, ok: bool) -> None:
        self._ok = ok

    def execute(self) -> BuildWarehouseResult:
        failed = () if self._ok else ("test.quancrypt_dw.not_null_x",)
        return BuildWarehouseResult(self._ok, {"model": 3}, 5, 0 if self._ok else 1, 0, 0, failed, 3.2)


class TestFacadeAndCommand:
    def test_a_failed_node_is_an_error_that_names_it(self) -> None:
        with pytest.raises(WarehouseBuildError, match="not_null_x"):
            WarehouseFacade(StubUseCase(False)).build()

    def test_counts_are_shown(self) -> None:
        view = WarehouseFacade(StubUseCase(True)).build()

        assert view.counts["built_model"] == 3 and view.counts["tests_failed"] == 0

    @pytest.mark.parametrize(("ok", "exit_code"), [(True, 0), (False, 1)])
    def test_the_build_command_fails_when_dbt_fails(
        self, monkeypatch: pytest.MonkeyPatch, ok: bool, exit_code: int
    ) -> None:
        class Container:
            warehouse = WarehouseFacade(StubUseCase(ok))

            def close(self) -> None:
                pass

        monkeypatch.setattr(cli, "bootstrap", lambda **_: Container())

        result = CliRunner().invoke(app, ["warehouse", "build"])

        assert result.exit_code == exit_code, result.output
        assert ("WarehouseBuildError" in result.output) is (not ok)


FAKE_DBT = """#!{python}
import json, os, pathlib, sys

# A stand-in for dbt: records its environment and arguments and writes the run_results.json a build would leave.
project = pathlib.Path(sys.argv[sys.argv.index("--project-dir") + 1])
(project / "target").mkdir(exist_ok=True)
config = json.loads(pathlib.Path(__file__).with_name("fake-dbt.json").read_text())
pathlib.Path(config["seen"]).write_text(json.dumps({{"argv": sys.argv[1:], "env": dict(os.environ)}}))
profile = pathlib.Path(sys.argv[sys.argv.index("--profiles-dir") + 1]) / "profiles.yml"
assert profile.is_file()
(project / "target" / "run_results.json").write_text(json.dumps({{"results": config["results"]}}))
sys.exit(config["exit"])
"""


def project(tmp_path: Path) -> Path:
    directory = tmp_path / "dbt"
    (directory / "dbt_packages" / "dbt_utils").mkdir(parents=True)
    (directory / "profiles.yml.example").write_text("quancrypt_dw: {}\n")
    return directory


def fake_dbt(tmp_path: Path) -> Path:
    script = tmp_path / "fake-dbt"
    script.write_text(FAKE_DBT.format(python=sys.executable))
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return script


def builder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, results: list[dict[str, str]], exit_code: int = 0
) -> DbtCliBuilder:
    script = fake_dbt(tmp_path)
    (tmp_path / "fake-dbt.json").write_text(
        json.dumps({"seen": str(tmp_path / "seen.json"), "results": results, "exit": exit_code})
    )
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("QUANCRYPT_ANON_SALT", "s" * 40)
    connection = DbtConnection("127.0.0.1", 5432, "warehouse_db_migrator", "pw-of-the-test", "warehouse_db")
    return DbtCliBuilder(project(tmp_path), [str(script)], connection, timeout_s=60)


def node(kind: str, name: str, status: str) -> dict[str, str]:
    return {"unique_id": f"{kind}.quancrypt_dw.{name}", "status": status}


class TestDbtCliBuilder:
    def test_results_are_counted_by_kind_and_failures_are_named(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        results = [
            node("seed", "strategy", "success"), node("snapshot", "dim_project_snapshot", "success"),
            node("model", "dim_date", "success"), node("model", "fact_x", "error"), node("model", "mart_y", "skipped"),
            node("test", "unique_a", "pass"), node("test", "not_null_b", "fail"), node("test", "warned_c", "warn"),
        ]  # fmt: skip
        outcome = builder(tmp_path, monkeypatch, results, exit_code=1).build()

        assert not outcome.ok
        assert outcome.built == {"seed": 1, "snapshot": 1, "model": 1}
        assert (outcome.tests_passed, outcome.tests_failed, outcome.tests_warned, outcome.skipped) == (1, 1, 1, 1)
        assert outcome.failed == ("model.quancrypt_dw.fact_x", "test.quancrypt_dw.not_null_b")

    def test_a_run_that_built_nothing_is_no_success(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        outcome = builder(tmp_path, monkeypatch, []).build()

        assert not outcome.ok

    def test_a_clean_run_is_ok(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        outcome = builder(
            tmp_path, monkeypatch, [node("model", "dim_date", "success"), node("test", "u", "pass")]
        ).build()

        assert outcome.ok and outcome.failed == ()

    def test_the_child_gets_the_connection_and_no_telemetry_and_nothing_else_of_the_parent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        builder(tmp_path, monkeypatch, [node("model", "m", "success")]).build()

        seen = json.loads((tmp_path / "seen.json").read_text())
        env = seen["env"]
        assert (env["DBT_USER"], env["DBT_PASSWORD"], env["DBT_HOST"], env["DBT_PORT"]) == (
            "warehouse_db_migrator", "pw-of-the-test", "127.0.0.1", "5432",
        )  # fmt: skip
        assert env["DBT_SEND_ANONYMOUS_USAGE_STATS"] == "false" and env["DO_NOT_TRACK"] == "1"
        assert "HTTPS_PROXY" not in env and "QUANCRYPT_ANON_SALT" not in env
        assert seen["argv"][0] == "build" and "--no-use-colors" in seen["argv"]
        profiles = seen["argv"][seen["argv"].index("--profiles-dir") + 1]
        assert not os.path.exists(profiles), "the temporary profile directory is removed"

    def test_a_non_zero_exit_without_a_failed_node_is_a_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        outcome = builder(tmp_path, monkeypatch, [node("model", "dim_date", "success")], exit_code=2).build()

        assert not outcome.ok and outcome.failed == ("dbt ended with exit code 2",)

    def test_missing_packages_are_reported_without_running_dbt(self, tmp_path: Path) -> None:
        directory = tmp_path / "dbt"
        directory.mkdir()
        (directory / "profiles.yml.example").write_text("x: {}\n")

        with pytest.raises(DbtError, match="make warehouse-deps"):
            DbtCliBuilder(directory, ["/nonexistent"], DbtConnection("h", 1, "u", "p", "d")).build()

    def test_a_missing_command_is_reported(self, tmp_path: Path) -> None:
        with pytest.raises(DbtError, match="not found"):
            DbtCliBuilder(project(tmp_path), ["/nonexistent/dbt"], DbtConnection("h", 1, "u", "p", "d")).build()

    def test_the_connection_password_is_not_in_repr(self) -> None:
        assert "pw-of-the-test" not in repr(DbtConnection("127.0.0.1", 5432, "u", "pw-of-the-test", "d"))


HANGING_DBT = """#!{python}
import os, pathlib, subprocess, sys, time

# A stand-in for `uv run dbt`: it starts a worker of its own and neither ends.
worker = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"])
pathlib.Path(sys.argv[0]).with_name("worker.pid").write_text(str(worker.pid))
time.sleep(120)
"""


def alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


class TestProcessGroup:
    def test_a_timeout_kills_the_grandchildren_too_before_the_lock_can_be_released(self, tmp_path: Path) -> None:
        script = tmp_path / "hanging-dbt"
        script.write_text(HANGING_DBT.format(python=sys.executable))
        script.chmod(script.stat().st_mode | stat.S_IEXEC)
        connection = DbtConnection("127.0.0.1", 5432, "u", "p", "d")

        with pytest.raises(DbtError, match="timed out"):
            DbtCliBuilder(project(tmp_path), [str(script)], connection, timeout_s=2).build()

        worker = int((tmp_path / "worker.pid").read_text())
        assert not alive(worker), "a dbt worker outlived the build"
