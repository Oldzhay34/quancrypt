"""The draft contract lists what the P4.1 prompt asks for. Structural validity (OpenAPI 3.1) is checked with
openapi-spec-validator in a scratch environment (D-77 precedent) and recorded in PROGRESS.md; this test needs only
PyYAML."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

CONTRACT = Path(__file__).resolve().parents[4] / "contracts" / "openapi" / "agent-service.yaml"

EXPECTED_OPERATIONS = {
    ("post", "/api/v1/sessions"),
    ("get", "/api/v1/sessions/{id}/messages"),
    ("post", "/api/v1/sessions/{id}/messages"),
    ("post", "/api/v1/sessions/{id}/initial-scan"),
    ("get", "/api/v1/sessions/{id}/clarifications"),
    ("post", "/api/v1/sessions/{id}/clarifications"),
    ("post", "/api/v1/sessions/{id}/stop"),
    ("delete", "/api/v1/sessions/{id}"),
}

SSE_EVENTS = {"token", "evidence", "clarification_required", "refusal", "done", "error"}


@pytest.fixture(scope="module")
def spec() -> dict[str, Any]:
    loaded = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def test_it_is_openapi_3_1(spec: dict[str, Any]) -> None:
    assert spec["openapi"].startswith("3.1")


def test_it_has_exactly_the_requested_operations(spec: dict[str, Any]) -> None:
    found = {(method, path) for path, item in spec["paths"].items() for method in item}

    assert found == EXPECTED_OPERATIONS


def test_every_operation_requires_the_bearer_token_and_has_an_id(spec: dict[str, Any]) -> None:
    assert spec["security"] == [{"bearerAuth": []}]
    bearer = spec["components"]["securitySchemes"]["bearerAuth"]
    assert (bearer["type"], bearer["scheme"]) == ("http", "bearer")
    operation_ids = [op["operationId"] for item in spec["paths"].values() for op in item.values()]
    assert len(operation_ids) == len(set(operation_ids))
    assert all("security" not in op for item in spec["paths"].values() for op in item.values())


def test_the_message_and_scan_responses_are_server_sent_events_with_the_six_event_types(spec: dict[str, Any]) -> None:
    for path in ("/api/v1/sessions/{id}/messages", "/api/v1/sessions/{id}/initial-scan"):
        content = spec["paths"][path]["post"]["responses"]["200"]["content"]
        assert set(content) == {"text/event-stream"}
        assert set(content["text/event-stream"]["x-sse-events"]) == SSE_EVENTS


def test_every_event_schema_exists_and_every_error_is_problem_json(spec: dict[str, Any]) -> None:
    schemas = spec["components"]["schemas"]
    for event in SSE_EVENTS:
        reference = spec["paths"]["/api/v1/sessions/{id}/messages"]["post"]["responses"]["200"]["content"][
            "text/event-stream"
        ]["x-sse-events"][event]["$ref"]
        assert reference.rsplit("/", 1)[-1] in schemas
    for name, response in spec["components"]["responses"].items():
        assert set(response["content"]) == {"application/problem+json"}, name


def test_commands_accept_an_idempotency_key_and_the_stream_does_not(spec: dict[str, Any]) -> None:
    def parameter_refs(path: str, method: str) -> set[str]:
        return {p["$ref"].rsplit("/", 1)[-1] for p in spec["paths"][path][method]["parameters"] if "$ref" in p}

    assert "IdempotencyKey" in parameter_refs("/api/v1/sessions", "post")
    assert "IdempotencyKey" in parameter_refs("/api/v1/sessions/{id}/clarifications", "post")
    assert "IdempotencyKey" not in parameter_refs("/api/v1/sessions/{id}/messages", "post")


def test_every_reference_resolves(spec: dict[str, Any]) -> None:
    def walk(node: Any) -> Iterator[str]:
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref":
                    yield value
                else:
                    yield from walk(value)
        elif isinstance(node, list):
            for item in node:
                yield from walk(item)

    for reference in set(walk(spec)):
        assert reference.startswith("#/")
        target: Any = spec
        for part in reference[2:].split("/"):
            target = target[part]
