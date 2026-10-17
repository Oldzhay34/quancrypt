"""Health endpoints and request tracing, through the real application factory (no Ollama needed)."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.app.api import build_health_router
from src.app.container import build_container
from src.app.main import create_app
from src.app.settings import CONFIG_DIR_ENV, load_settings
from tests.support.containers import inert_container
from tests.support.fakes import FakeProvider

CONFIG = Path(__file__).resolve().parents[2] / "config"
TRACE = "42424242424242424242424242424242"


def _app() -> FastAPI:
    """The real application with the database switched off (no migrations, no readiness check on agent_db)."""
    settings = load_settings()
    return create_app(settings, inert_container(settings))


@pytest.fixture(autouse=True)
def _environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(CONFIG))
    for name in ("OLLAMA_BASE_URL", "LLM_PROVIDER", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def client_without_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("LLM_PROVIDER", "null")
    with TestClient(_app()) as client:
        yield client


@pytest.fixture
def client_with_ollama_down(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # Port 1 on localhost refuses connections immediately: Ollama is configured but not reachable.
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:1")
    with TestClient(_app()) as client:
        yield client


def test_liveness_is_alive(client_without_llm: TestClient) -> None:
    response = client_without_llm.get("/health/liveness")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_without_an_llm_is_ready_and_reports_it_disabled(client_without_llm: TestClient) -> None:
    response = client_without_llm.get("/health/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "llm": "disabled"}


def test_readiness_stays_ready_and_reports_degraded_when_ollama_is_unreachable(
    client_with_ollama_down: TestClient,
) -> None:
    response = client_with_ollama_down.get("/health/readiness")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "llm": "degraded"}


def test_a_failing_dependency_makes_the_service_not_ready_but_not_alive_false() -> None:
    class Down:
        name = "database"

        def is_ready(self) -> bool:
            return False

    app = FastAPI()
    app.include_router(build_health_router(FakeProvider(status="ok"), checks=[Down()]))
    client = TestClient(app)

    readiness = client.get("/health/readiness")

    assert readiness.status_code == 503
    assert readiness.json() == {"status": "not_ready", "failed": ["database"], "llm": "ok"}
    assert client.get("/health/liveness").status_code == 200


def test_a_degraded_llm_alone_never_makes_the_service_not_ready() -> None:
    app = FastAPI()
    app.include_router(build_health_router(FakeProvider(status="degraded"), checks=[]))

    response = TestClient(app).get("/health/readiness")

    assert (response.status_code, response.json()["llm"]) == (200, "degraded")


def test_a_valid_trace_id_is_echoed_and_an_invalid_one_is_replaced(client_without_llm: TestClient) -> None:
    valid = "0123456789abcdef0123456789abcdef"
    echoed = client_without_llm.get("/health/liveness", headers={"X-Trace-Id": valid})
    generated = client_without_llm.get("/health/liveness")

    assert echoed.headers["X-Trace-Id"] == valid
    assert re.fullmatch(r"[0-9a-f]{32}", generated.headers["X-Trace-Id"])
    # Free text, uppercase, a wrong length and a 33rd digit never reach the audit trail: the server makes its own.
    for bad in (
        "abc-123.x_y",
        "bad id with spaces	",
        valid.upper(),
        valid[:31],
        valid + "0",
        "ad.soyad_tc1234567890",
    ):
        replaced = client_without_llm.get("/health/liveness", headers={"X-Trace-Id": bad})
        assert replaced.headers["X-Trace-Id"] != bad
        assert re.fullmatch(r"[0-9a-f]{32}", replaced.headers["X-Trace-Id"])


def test_the_interactive_docs_and_the_schema_endpoint_are_off(client_without_llm: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client_without_llm.get(path).status_code == 404


def test_logs_are_json_with_the_required_fields_and_no_request_path(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    # The log handler binds sys.stdout when the app is created, so the app is created after capsys is active.
    monkeypatch.setenv("LLM_PROVIDER", "null")
    with TestClient(_app()) as client:
        client.get("/no-such-path?secret=1", headers={"X-Trace-Id": TRACE})

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")]
    request_logs = [entry for entry in lines if entry["traceId"] == TRACE]
    assert request_logs
    assert set(request_logs[0]) == {"timestamp", "level", "service", "traceId", "message"}
    assert request_logs[0]["service"] == "agent-service"
    assert "secret" not in json.dumps(request_logs)
    assert "no-such-path" not in json.dumps(request_logs)


def test_the_uvicorn_access_log_and_the_httpx_request_log_stay_silent(monkeypatch: pytest.MonkeyPatch) -> None:
    # The access log carries client addresses and paths; httpx logs request URLs at INFO.
    monkeypatch.setenv("LLM_PROVIDER", "null")
    _app()

    assert logging.getLogger("uvicorn.access").propagate is False
    assert logging.getLogger("uvicorn.error").propagate is True
    assert logging.getLogger("httpx").level == logging.WARNING


def test_fastapi_telemetry_stays_off_even_when_an_exporter_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    # FastAPI 0.142 reads OTEL_* at startup; the service must neither fail nor start exporting.
    monkeypatch.setenv("LLM_PROVIDER", "null")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://collector.invalid:4318")
    monkeypatch.setenv("OTEL_TRACES_EXPORTER", "otlp")

    with TestClient(_app()) as client:
        assert client.get("/health/liveness").status_code == 200


def test_readiness_is_503_when_agent_db_is_unreachable_and_liveness_stays_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Port 1 refuses at once. Startup (migrations) is switched off here; the real readiness check stays on.
    monkeypatch.setenv("LLM_PROVIDER", "null")
    monkeypatch.setenv("AGENT_DB_URL", "postgresql+psycopg://agent_db_app@127.0.0.1:1/agent_db")
    settings = load_settings()
    container = inert_container(settings)
    container.readiness_checks = build_container(settings).readiness_checks

    with TestClient(create_app(settings, container)) as client:
        readiness = client.get("/health/readiness")
        liveness = client.get("/health/liveness")

    assert readiness.status_code == 503
    assert readiness.json() == {"status": "not_ready", "failed": ["database"], "llm": "disabled"}
    assert liveness.status_code == 200


def test_a_failing_startup_stops_the_service_and_the_container_is_still_closed() -> None:
    settings = load_settings()
    container = inert_container(settings)
    closed: list[bool] = []

    def failing_migration() -> None:
        raise RuntimeError("migration failed")

    container.startup = failing_migration
    container._closers.append(lambda: closed.append(True))  # noqa: SLF001 - the test watches the shutdown

    with pytest.raises(RuntimeError, match="migration failed"), TestClient(create_app(settings, container)):
        pass

    assert closed == [True]
