"""The HTTP API against contracts/openapi/agent-service.yaml (P4.6): every endpoint's status codes and bodies, the SSE
events, bearer authentication, CORS and the trace id. The real application factory runs with the orchestrator on the
in-memory doubles and fake agents (no database, no model)."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
import yaml
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from src.app.api import ROOT_PATTERN
from src.app.main import create_app
from src.app.settings import CONFIG_DIR_ENV, load_settings
from tests.support.containers import inert_container
from tests.support.workflow_fakes import PROJECT, World, waits_for, world

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT.parents[1] / "contracts" / "openapi" / "agent-service.yaml"
TOKEN = "unit-test-session-token-0123456789abcdef"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
UI = "http://127.0.0.1:8080"

_DOCUMENT = yaml.safe_load(CONTRACT.read_text("utf-8"))
_REGISTRY: Registry[Any] = Registry().with_resource(
    "urn:agent-service", Resource.from_contents(_DOCUMENT, default_specification=DRAFT202012)
)


def assert_fits(name: str, instance: Any) -> None:
    validator = Draft202012Validator({"$ref": f"urn:agent-service#/components/schemas/{name}"}, registry=_REGISTRY)
    errors = sorted(error.message for error in validator.iter_errors(instance))
    assert errors == [], (name, errors)


def sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    frames = []
    for block in body.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        frames.append((lines["event"], json.loads(lines["data"])))
    return frames


_EVENT_SCHEMAS = {
    "token": "TokenEvent",
    "evidence": "EvidenceEvent",
    "clarification_required": "ClarificationRequiredEvent",
    "refusal": "RefusalEvent",
    "done": "DoneEvent",
    "error": "ErrorEvent",
}


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[TestClient, World]]:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(ROOT / "config"))
    monkeypatch.setenv("LLM_PROVIDER", "null")
    monkeypatch.setenv("QUANCRYPT_SESSION_TOKEN", TOKEN)
    settings = load_settings()
    container = inert_container(settings)
    w = world(queue_wait_s=0.1)
    container.orchestrator = w.orchestrator
    container.background = ()
    with TestClient(create_app(settings, container)) as client:
        yield client, w


def new_session(client: TestClient) -> str:
    response = client.post("/api/v1/sessions", json={"project_id": str(PROJECT), "language": "en"}, headers=AUTH)
    assert response.status_code == 201
    return str(response.json()["id"])


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("POST", "/api/v1/sessions"),
        ("DELETE", f"/api/v1/sessions/{uuid4()}"),
        ("GET", f"/api/v1/sessions/{uuid4()}/messages"),
        ("POST", f"/api/v1/sessions/{uuid4()}/messages"),
        ("POST", f"/api/v1/sessions/{uuid4()}/initial-scan"),
        ("GET", f"/api/v1/sessions/{uuid4()}/clarifications"),
        ("POST", f"/api/v1/sessions/{uuid4()}/clarifications"),
        ("POST", f"/api/v1/sessions/{uuid4()}/stop"),
    ],
)
def test_every_endpoint_needs_the_session_token(setup: tuple[TestClient, World], method: str, path: str) -> None:
    client, _ = setup
    for headers in ({}, {"Authorization": "Bearer wrong-token-wrong-token-wrong-token"}, {"Authorization": TOKEN}):
        response = client.request(method, path, headers=headers, json={})
        assert response.status_code == 401
        assert response.headers["content-type"] == "application/problem+json"
        assert response.json()["type"] == "https://quancrypt.local/problems/unauthorized"
        assert_fits("Problem", response.json())


def test_health_stays_open(setup: tuple[TestClient, World]) -> None:
    client, _ = setup
    assert client.get("/health/liveness").status_code == 200


def test_create_session_fits_the_contract_and_replays_with_the_same_key(setup: tuple[TestClient, World]) -> None:
    client, _ = setup
    body = {"project_id": str(PROJECT), "language": "en"}
    headers = {**AUTH, "Idempotency-Key": "key-1"}

    first = client.post("/api/v1/sessions", json=body, headers=headers)
    again = client.post("/api/v1/sessions", json=body, headers=headers)
    other = client.post("/api/v1/sessions", json={**body, "language": "tr"}, headers=headers)

    assert first.status_code == 201 and first.headers["X-Trace-Id"]
    assert_fits("Session", first.json())
    assert again.json()["id"] == first.json()["id"]
    assert other.status_code == 409 and other.json()["type"].endswith("/idempotency-conflict")


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"project_id": "not-a-uuid"},
        {"project_id": str(PROJECT), "language": "de"},
        {"project_id": str(PROJECT), "x": 1},
    ],
)
def test_a_bad_session_body_is_a_400_problem_without_the_value(
    setup: tuple[TestClient, World], body: dict[str, Any]
) -> None:
    client, _ = setup
    response = client.post("/api/v1/sessions", json=body, headers=AUTH)

    assert response.status_code == 400 and response.json()["type"].endswith("/validation-failed")
    assert "not-a-uuid" not in response.text
    assert_fits("Problem", response.json())


def test_messages_stream_sse_events_that_fit_the_contract(setup: tuple[TestClient, World]) -> None:
    client, _ = setup
    sid = new_session(client)

    response = client.post(
        f"/api/v1/sessions/{sid}/messages", json={"content": "What cryptography does my project use?"}, headers=AUTH
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream") and response.headers["X-Trace-Id"]
    frames = sse(response.text)
    for event, data in frames:
        assert_fits(_EVENT_SCHEMAS[event], data)
    assert frames[-1][0] == "done"

    page = client.get(f"/api/v1/sessions/{sid}/messages", params={"page": 0, "size": 10}, headers=AUTH)
    assert page.status_code == 200
    assert_fits("MessagePage", page.json())
    assert [item["role"] for item in page.json()["items"]] == ["user", "assistant"]


def test_a_busy_session_gets_409_session_busy(setup: tuple[TestClient, World]) -> None:
    client, w = setup
    sid = new_session(client)
    gate = threading.Event()
    w.agents.planner.before = lambda: gate.wait(5)  # type: ignore[attr-defined]
    held = w.orchestrator.begin_message(UUID(sid), "What cryptography does my project use?", "0" * 32)

    response = client.post(f"/api/v1/sessions/{sid}/messages", json={"content": "hello"}, headers=AUTH)

    assert response.status_code == 409 and response.json()["type"].endswith("/session-busy")
    gate.set()
    list(held)


def test_an_unknown_or_malformed_session_is_404(setup: tuple[TestClient, World]) -> None:
    client, _ = setup
    for sid in (str(uuid4()), "not-a-uuid"):
        for method, path in (("DELETE", ""), ("GET", "/messages"), ("POST", "/stop"), ("GET", "/clarifications")):
            response = client.request(method, f"/api/v1/sessions/{sid}{path}", headers=AUTH)
            assert response.status_code == 404, (method, path)
            assert response.json()["type"].endswith("/not-found")


def test_delete_and_stop_answer_204(setup: tuple[TestClient, World]) -> None:
    client, w = setup
    sid = new_session(client)

    assert client.post(f"/api/v1/sessions/{sid}/stop", headers=AUTH).status_code == 204
    assert client.delete(f"/api/v1/sessions/{sid}", headers=AUTH).status_code == 204
    assert client.delete(f"/api/v1/sessions/{sid}", headers=AUTH).status_code == 404


def test_the_initial_scan_checks_the_root_and_streams(setup: tuple[TestClient, World]) -> None:
    client, _ = setup
    sid = new_session(client)

    bad = client.post(f"/api/v1/sessions/{sid}/initial-scan", json={"root": "/etc"}, headers=AUTH)
    good = client.post(
        f"/api/v1/sessions/{sid}/initial-scan", json={"root": "/workspace/qbank-payment-service"}, headers=AUTH
    )

    assert bad.status_code == 400
    assert good.status_code == 200
    frames = sse(good.text)
    for event, data in frames:
        assert_fits(_EVENT_SCHEMAS[event], data)
    assert frames[-1][0] == "done"


def test_clarifications_fit_the_contract(setup: tuple[TestClient, World]) -> None:
    client, _ = setup
    sid = new_session(client)

    listed = client.get(f"/api/v1/sessions/{sid}/clarifications", headers=AUTH)
    answered = client.post(
        f"/api/v1/sessions/{sid}/clarifications",
        json={"answers": [{"question_code": "TLS_TERMINATION", "option_code": "INGRESS"}]},
        headers={**AUTH, "Idempotency-Key": "answers-1"},
    )
    bad = client.post(
        f"/api/v1/sessions/{sid}/clarifications", json={"answers": [{"question_code": "OTHER"}]}, headers=AUTH
    )

    assert listed.status_code == 200 and answered.status_code == 200 and bad.status_code == 400
    assert_fits("ClarificationList", listed.json())
    assert_fits("ClarificationList", answered.json())
    tls = next(item for item in answered.json()["items"] if item["question_code"] == "TLS_TERMINATION")
    assert tls["answer"]["option_code"] == "INGRESS"


def test_cors_admits_only_the_ui_origin(setup: tuple[TestClient, World]) -> None:
    client, _ = setup
    preflight = {"Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "authorization"}

    allowed = client.options("/api/v1/sessions", headers={"Origin": UI, **preflight})
    refused = client.options("/api/v1/sessions", headers={"Origin": "http://evil.example", **preflight})

    assert allowed.headers.get("access-control-allow-origin") == UI
    assert "access-control-allow-origin" not in refused.headers


def test_the_root_pattern_is_the_contracts() -> None:
    assert _DOCUMENT["components"]["schemas"]["Root"]["pattern"] == ROOT_PATTERN


def test_problem_bodies_never_echo_the_message(setup: tuple[TestClient, World]) -> None:
    client, _ = setup
    sid = new_session(client)
    secret = "AKIAIOSFODNN7EXAMPLE"
    response = client.post(f"/api/v1/sessions/{sid}/messages", json={"content": secret, "extra": 1}, headers=AUTH)

    assert response.status_code == 400 and secret not in response.text


def test_the_gate_refuses_a_request_without_the_token_before_reading_its_body(setup: tuple[TestClient, World]) -> None:
    """Security review P4.6 #2: an unauthenticated request gets 401 even with a body that is not JSON at all."""
    client, _ = setup
    response = client.post("/api/v1/sessions", content=b"{not json", headers={"Content-Type": "application/json"})

    assert response.status_code == 401 and response.json()["type"].endswith("/unauthorized")


def test_a_body_above_64_kib_is_refused_before_parsing(setup: tuple[TestClient, World]) -> None:
    client, _ = setup
    sid = new_session(client)
    big = json.dumps({"content": "x" * (65 * 1024)})

    response = client.post(
        f"/api/v1/sessions/{sid}/messages", content=big, headers={**AUTH, "Content-Type": "application/json"}
    )

    assert response.status_code == 400 and response.json()["type"].endswith("/validation-failed")


def test_a_message_above_the_scope_keepers_limit_is_400_and_not_stored(setup: tuple[TestClient, World]) -> None:
    client, w = setup
    sid = new_session(client)

    response = client.post(f"/api/v1/sessions/{sid}/messages", json={"content": "y" * 4001}, headers=AUTH)

    assert response.status_code == 400
    assert w.memory.list_messages(UUID(sid), 0, 10).total == 0


def test_a_client_that_disconnects_stops_the_running_answer(setup: tuple[TestClient, World]) -> None:
    """Security review P4.6 re-review #1: the disconnect is noticed while the run still works (ASGI level)."""
    import asyncio

    client, w = setup
    sid = new_session(client)
    gate = threading.Event()
    w.agents.planner.before = waits_for(gate)  # type: ignore[attr-defined]
    body = json.dumps({"content": "What cryptography does my project use?"}).encode()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.4"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": f"/api/v1/sessions/{sid}/messages",
        "raw_path": f"/api/v1/sessions/{sid}/messages".encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [
            (b"authorization", AUTH["Authorization"].encode()),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 50000),
        "server": ("127.0.0.1", 8083),
    }
    sent_body = False
    gone_at = time.monotonic() + 0.2  # the client is gone shortly after the response started

    async def receive() -> dict[str, object]:
        # Like a server's receive: after the body it waits until the client goes away.
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.sleep(max(0.0, gone_at - time.monotonic()))
        return {"type": "http.disconnect"}

    async def send(_: dict[str, object]) -> None:
        return None

    async def run() -> None:
        await asyncio.wait_for(client.app(scope, receive, send), timeout=10)  # type: ignore[arg-type]

    asyncio.run(run())
    gate.set()
    for _ in range(100):
        if w.audit.finished:
            break
        threading.Event().wait(0.05)

    assert list(w.audit.finished.values()) == ["STOPPED"]


def test_a_chunked_body_above_64_kib_is_refused_and_a_401_carries_cors_headers(
    setup: tuple[TestClient, World],
) -> None:
    client, _ = setup
    sid = new_session(client)

    def chunks() -> Iterator[bytes]:
        yield b'{"content": "'
        for _ in range(70):
            yield b"x" * 1024
        yield b'"}'

    big = client.post(
        f"/api/v1/sessions/{sid}/messages", content=chunks(), headers={**AUTH, "Content-Type": "application/json"}
    )
    refused = client.post("/api/v1/sessions", json={}, headers={"Origin": "http://127.0.0.1:8080"})

    assert big.status_code == 400 and big.json()["type"].endswith("/validation-failed")
    assert refused.status_code == 401
    assert refused.headers["access-control-allow-origin"] == "http://127.0.0.1:8080"
