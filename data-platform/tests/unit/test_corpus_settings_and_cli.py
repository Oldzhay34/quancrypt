"""The configuration and the command line of the corpus tooling (P6.2): what is refused at start, what the commands print."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quancrypt_data.api.cli import app
from quancrypt_data.infrastructure.corpus.settings import load_corpus_settings
from quancrypt_data.infrastructure.settings import ConfigError

TOKEN = "t" * 40
SALT = "s" * 40


@pytest.fixture(autouse=True)
def restore_logging() -> Iterator[None]:
    """A command configures the root logger for the stream of its own run (the runner's); a later test must not log into it."""
    root = logging.getLogger()
    handlers, level = root.handlers[:], root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def environment(tmp_path: Path, **overrides: str) -> dict[str, str]:
    base = {
        "CORPUS_ROOT": str(tmp_path / "corpus"),
        "CORPUS_REFERENCE_DIR": str(tmp_path / "reference"),
        "CORPUS_REPORTS_DIR": str(tmp_path / "reports"),
        "INTERNAL_SERVICE_TOKEN": TOKEN,
        "QUANCRYPT_ANON_SALT": SALT,
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v != ""}


class TestSettings:
    def test_the_defaults_point_at_the_services_on_this_machine(self, tmp_path: Path) -> None:
        settings = load_corpus_settings(environment(tmp_path))

        assert settings.analyzer_url == "http://127.0.0.1:8082"
        assert settings.ingest_url == "http://127.0.0.1:8084/api/v1/events"
        assert settings.analyzer_mount == "/corpus"
        assert settings.database is None
        assert TOKEN not in repr(settings) and SALT not in repr(settings)

    @pytest.mark.parametrize(
        ("name", "value"),
        [
            ("CORPUS_ROOT", ""),
            ("CORPUS_ROOT", "relative/path"),
            ("DATASETS_ROOT", "relative"),
            ("INTERNAL_SERVICE_TOKEN", "short"),
            ("INTERNAL_SERVICE_TOKEN", "CHANGE_ME" + "x" * 40),
            ("INTERNAL_SERVICE_TOKEN", " " + "t" * 40),
            ("QUANCRYPT_ANON_SALT", "short"),
            ("QUANCRYPT_ANON_SALT", "CHANGE_ME" + "s" * 40),
            ("CORPUS_ANALYZER_URL", "http://evil.example:8082"),
            ("CORPUS_ANALYZER_URL", "http://analyzer-service:8082"),
            ("CORPUS_INGEST_URL", "http://ingest-api:8084/api/v1/events"),
            ("CORPUS_INGEST_URL", "http://127.0.0.1:99999/api/v1/events"),
            ("CORPUS_ANALYZER_URL", "ftp://127.0.0.1:8082"),
            ("CORPUS_ANALYZER_URL", "http://user:secret-pw@127.0.0.1:8082"),
            ("CORPUS_INGEST_URL", "https://example.com/api/v1/events"),
            ("CORPUS_INGEST_URL", "http://127.0.0.1:8084/api/v1/events?x=1"),
            ("LOG_LEVEL", "TRACE"),
        ],
    )
    def test_a_value_that_is_wrong_stops_the_start_and_is_never_repeated(
        self, tmp_path: Path, name: str, value: str
    ) -> None:
        with pytest.raises(ConfigError) as raised:
            load_corpus_settings(environment(tmp_path, **{name: value}))

        assert name in str(raised.value)
        assert "secret-pw" not in str(raised.value) and "evil.example" not in str(raised.value)

    def test_only_loopback_addresses_are_accepted_ipv6_included(self, tmp_path: Path) -> None:
        settings = load_corpus_settings(
            environment(
                tmp_path,
                CORPUS_ANALYZER_URL="http://localhost:8082",
                CORPUS_INGEST_URL="http://[::1]:8084/api/v1/events",
            )
        )

        assert settings.analyzer_url.startswith("http://localhost")
        assert "[::1]" in settings.ingest_url

    def test_the_database_is_only_loaded_when_a_command_needs_it(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="WAREHOUSE_DB_URL"):
            load_corpus_settings(environment(tmp_path), need_database=True)

        settings = load_corpus_settings(
            environment(
                tmp_path,
                WAREHOUSE_DB_URL="postgresql+psycopg://warehouse_db_app@127.0.0.1:5432/warehouse_db",
                WAREHOUSE_DB_APP_PASSWORD="p" * 20,
            ),
            need_database=True,
        )
        assert settings.database is not None
        assert "p" * 20 not in repr(settings)


class TestCommandLine:
    def test_the_list_command_writes_the_list_from_a_dataset_below_the_datasets_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        datasets = tmp_path / "datasets"
        datasets.mkdir()
        (datasets / "msr.csv").write_text(
            "repo_url\nhttps://github.com/acme/one\nhttps://github.com/acme/two\nhttps://github.com/acme/one\n",
            encoding="utf-8",
        )
        for key, value in environment(tmp_path, DATASETS_ROOT=str(datasets)).items():
            monkeypatch.setenv(key, value)

        result = CliRunner().invoke(app, ["corpus", "list", "--dataset", "msr.csv", "--size", "5"])

        assert result.exit_code == 0, result.output
        assert "candidates: 3" in result.output and "selected: 2" in result.output
        assert "turned away by duplicate: 1" in result.output
        written = (tmp_path / "reference" / "corpus_projects.csv").read_text(encoding="utf-8")
        assert written.splitlines()[0] == "repo_url,default_branch,license_spdx,selection_reason"
        assert written.count("https://github.com/acme/") == 2

    def test_a_dataset_whose_columns_do_not_match_ends_with_a_message_and_a_non_zero_exit_code(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "bad.csv").write_text("name,stars\nx,1\n", encoding="utf-8")
        for key, value in environment(tmp_path).items():
            monkeypatch.setenv(key, value)

        result = CliRunner().invoke(app, ["corpus", "list", "--dataset", str(tmp_path / "bad.csv")])

        assert result.exit_code == 1
        assert "columns not found: repo_url" in result.output and "name, stars" in result.output

    def test_a_missing_setting_ends_with_its_name_and_never_a_traceback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for name in ("CORPUS_ROOT", "INTERNAL_SERVICE_TOKEN", "QUANCRYPT_ANON_SALT"):
            monkeypatch.delenv(name, raising=False)

        result = CliRunner().invoke(app, ["corpus", "report"])

        assert result.exit_code == 1
        assert "CORPUS_ROOT" in result.output
        assert "Traceback" not in result.output

    def test_the_report_command_writes_the_report_even_before_any_clone(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key, value in environment(tmp_path).items():
            monkeypatch.setenv(key, value)

        result = CliRunner().invoke(app, ["corpus", "report"])

        assert result.exit_code == 0, result.output
        text = (tmp_path / "reports" / "corpus_run.md").read_text(encoding="utf-8")
        assert "KARŞILANMADI" in text and "| Analiz edilen | 0 |" in text

    def test_a_window_with_nothing_to_clone_does_nothing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        for key, value in environment(tmp_path).items():
            monkeypatch.setenv(key, value)

        result = CliRunner().invoke(app, ["corpus", "clone", "--limit", "5"])

        assert result.exit_code == 0, result.output
        assert "attempted: 0" in result.output

    def test_a_benchmark_without_a_label_reader_is_refused_with_a_clear_message(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        env = environment(
            tmp_path,
            WAREHOUSE_DB_URL="postgresql+psycopg://warehouse_db_app@127.0.0.1:5432/warehouse_db",
            WAREHOUSE_DB_APP_PASSWORD="p" * 20,
        )
        for key, value in env.items():
            monkeypatch.setenv(key, value)

        result = CliRunner().invoke(app, ["benchmarks", "load", "owasp-benchmark", str(tmp_path)])

        assert result.exit_code == 1
        assert "no label reader for this benchmark" in result.output

    def test_the_run_command_runs_the_prefect_flow_in_local_mode_and_writes_the_report(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        datasets = tmp_path / "datasets"
        datasets.mkdir()
        (datasets / "msr.csv").write_text("repo_url\nhttps://github.com/acme/one\n", encoding="utf-8")
        for key, value in environment(tmp_path, DATASETS_ROOT=str(datasets)).items():
            monkeypatch.setenv(key, value)

        # The clone step finds nothing cloned and no git is started: the list has one project, `--limit 0` is refused by the
        # parser, so a window past the end of the list is used (nothing to clone or analyse; list and report still run).
        result = CliRunner().invoke(app, ["corpus", "run", "--dataset", "msr.csv", "--offset", "5", "--limit", "1"])

        assert result.exit_code == 0, result.output
        assert (tmp_path / "reference" / "corpus_projects.csv").read_text(encoding="utf-8").count(
            "https://github.com/acme/"
        ) == 1
        assert "KARŞILANMADI" in (tmp_path / "reports" / "corpus_run.md").read_text(encoding="utf-8")

    def test_the_flows_refuse_to_run_against_a_prefect_api_server(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from types import SimpleNamespace

        from quancrypt_data.api import flows

        monkeypatch.setattr(
            flows,
            "get_current_settings",
            lambda: SimpleNamespace(api=SimpleNamespace(url="https://api.prefect.cloud/x")),
        )

        with pytest.raises(RuntimeError, match="local mode only"):
            flows._require_local_mode()

    def test_the_flows_switch_every_telemetry_setting_off_even_when_the_environment_says_otherwise(self) -> None:
        import os

        from quancrypt_data.api import flows  # noqa: F401  (importing it sets the switches)

        assert os.environ["PREFECT_SERVER_ANALYTICS_ENABLED"] == "false"
        assert os.environ["PREFECT_CLOUD_ENABLE_ORCHESTRATION_TELEMETRY"] == "false"
        assert os.environ["PREFECT_TELEMETRY_ENABLE_RESOURCE_METRICS"] == "false"
        assert os.environ["DO_NOT_TRACK"] == "1"
        assert os.environ["PREFECT_API_URL"] == ""

    @pytest.mark.parametrize(
        "arguments", [["corpus", "clone", "--limit", "0"], ["corpus", "analyze", "--offset", "-1"]]
    )
    def test_arguments_out_of_range_are_refused_by_the_parser(self, arguments: list[str]) -> None:
        assert CliRunner().invoke(app, arguments).exit_code == 2
