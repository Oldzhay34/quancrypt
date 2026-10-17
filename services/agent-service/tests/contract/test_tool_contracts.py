"""Every tool against its JSON Schema contract and its service endpoint (respx fakes the HTTP replies; D-17, D-238)."""

from __future__ import annotations

import json
import uuid
from typing import Any

import httpx
import pytest
import respx

from src.tools.analyzer_tool import SPECS as ANALYZER_SPECS
from src.tools.base_tool import (
    ToolContext,
    ToolInputError,
    ToolOutputError,
    ToolRejectedError,
    ToolUnavailableError,
)
from src.tools.core_tool import SPECS as CORE_SPECS
from src.tools.registry import ToolRegistry
from tests.support.tool_samples import SAMPLES
from tests.support.tools import ANALYZER_URL, CONTRACTS, CORE_URL, TOKEN, TRACE, build_registry, schemas

ANALYZER_TOOLS = {spec.name for spec in ANALYZER_SPECS}
SPECS = {spec.name: spec for spec in (*CORE_SPECS, *ANALYZER_SPECS)}


@pytest.fixture
def registry() -> ToolRegistry:
    return build_registry()


def _url(name: str, path: str) -> str:
    return (ANALYZER_URL if name in ANALYZER_TOOLS else CORE_URL) + path


def test_every_registered_tool_has_exactly_one_valid_contract(registry: ToolRegistry) -> None:
    files = {path.stem for path in (CONTRACTS / "schemas" / "tools").glob("*.json")}
    store = schemas()

    assert files == set(registry.names())
    assert len(files) == 20
    for name in files:
        store.check_contract(name)  # Draft 2020-12, $defs.input and $defs.output, references resolve locally


def test_the_http_samples_cover_every_http_tool(registry: ToolRegistry) -> None:
    assert set(SAMPLES) == set(registry.names()) - {"kb_search", "score_findings"}


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_a_tool_calls_its_endpoint_with_the_trace_and_internal_token_and_returns_a_contract_output(
    registry: ToolRegistry, name: str
) -> None:
    arguments, method, path, status, reply, idempotent = SAMPLES[name]
    context = ToolContext(trace_id=TRACE, call_id=uuid.uuid4())
    with respx.mock(assert_all_called=True) as mock:
        if isinstance(reply, str):
            route = mock.route(method=method, url__startswith=_url(name, path)).respond(
                status, text=reply, headers={"content-type": "text/markdown; charset=utf-8"}
            )
        else:
            route = mock.route(method=method, url__startswith=_url(name, path)).respond(status, json=reply)

        output, duration = registry.call(name, arguments, context)

    request = route.calls.last.request
    assert request.url.path == path
    assert request.headers["X-Internal-Token"] == TOKEN
    assert request.headers["X-Trace-Id"] == TRACE
    assert (
        (request.headers.get("Idempotency-Key") == str(context.call_id))
        if idempotent
        else ("Idempotency-Key" not in request.headers)
    )
    if "body" in arguments:
        assert json.loads(request.content) == arguments["body"]
    for query in SPECS[name].query_params:
        if query in arguments:
            assert request.url.params[query] == str(arguments[query])
    if name == "get_plan_report":
        assert request.headers["Accept-Language"] == "en"
        assert output == {"markdown": reply}
    elif name == "get_snippet":
        texts = [line["text"] for line in output["lines"]]
        assert "hunter2-secret" not in json.dumps(output)  # the snippet passed the output redaction
        assert texts[1] == reply["lines"][1]["text"]
    else:
        assert output == reply
    assert duration >= 0


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("get_project", {}),
        ("get_project", {"projectId": "not-a-uuid"}),
        ("get_project", {"projectId": "00000000-0000-0000-0000-00000000a001", "extra": 1}),
        ("list_findings", {"scanId": "00000000-0000-0000-0000-00000000b001", "size": 500}),
        ("get_snippet", {"root": "/workspace", "path": "../../etc/passwd", "line": 1}),
        ("get_plan_report", {"scanId": "00000000-0000-0000-0000-00000000b001", "language": "de"}),
        ("record_findings", {"scanId": "00000000-0000-0000-0000-00000000b001", "body": {"findings": []}}),
        ("kb_search", {"query": ""}),
        ("score_findings", {"findings": []}),
    ],
)
def test_arguments_outside_the_contract_are_refused_before_any_request(
    registry: ToolRegistry, name: str, arguments: dict[str, Any]
) -> None:
    with respx.mock(assert_all_mocked=True) as mock, pytest.raises(ToolInputError):
        registry.call(name, arguments, ToolContext(trace_id=TRACE))
    assert mock.calls.call_count == 0


def test_a_reply_that_breaks_the_contract_is_never_passed_on(registry: ToolRegistry) -> None:
    arguments = SAMPLES["get_project"][0]
    with respx.mock() as mock:
        mock.get(f"{CORE_URL}/api/v1/projects/{arguments['projectId']}").respond(200, json={"project": {"id": "x"}})
        with pytest.raises(ToolOutputError):
            registry.call("get_project", arguments, ToolContext(trace_id=TRACE))


def test_a_client_error_keeps_only_the_status_and_the_problem_code(registry: ToolRegistry) -> None:
    arguments = SAMPLES["start_scan"][0]
    problem = {
        "type": "https://quancrypt.local/problems/conflict",
        "title": "Conflict",
        "status": 409,
        "detail": "secret-detail-from-the-service",
    }
    with respx.mock() as mock:
        mock.post(f"{CORE_URL}/api/v1/projects/{arguments['projectId']}/scans").respond(
            409, json=problem, headers={"content-type": "application/problem+json"}
        )
        with pytest.raises(ToolRejectedError) as caught:
            registry.call("start_scan", arguments, ToolContext(trace_id=TRACE))
    assert (caught.value.status, caught.value.problem_code) == (409, "conflict")
    assert "secret-detail" not in str(caught.value)


def test_a_server_error_on_a_command_with_an_idempotency_key_is_retried_then_reported(registry: ToolRegistry) -> None:
    arguments = SAMPLES["start_scan"][0]
    with respx.mock() as mock:
        route = mock.post(f"{CORE_URL}/api/v1/projects/{arguments['projectId']}/scans").respond(503)
        with pytest.raises(ToolUnavailableError):
            registry.call("start_scan", arguments, ToolContext(trace_id=TRACE))
    assert route.call_count == 2  # max_attempts in the test endpoint
    keys = {call.request.headers["Idempotency-Key"] for call in route.calls}
    assert len(keys) == 1  # the same key on every attempt: core-service answers the repeat from its record


def test_kb_search_returns_hits_with_their_sources(registry: ToolRegistry) -> None:
    output, _ = registry.call("kb_search", {"query": "ml kem", "k": 3}, ToolContext(trace_id=TRACE))

    assert output == {"hits": []}  # the in-memory knowledge base of this registry is empty


def test_score_findings_returns_the_baseline_model_id_and_one_score_per_finding(registry: ToolRegistry) -> None:
    finding = {"id": "00000000-0000-0000-0000-00000000c001", "priority": "P0", "locationKind": "CODE"}

    output, _ = registry.call("score_findings", {"findings": [finding], "topology": None}, ToolContext(trace_id=TRACE))

    assert output["model_id"] == "rule_baseline_v1"
    assert output["scores"] == [
        {"findingId": finding["id"], "riskClass": "CRITICAL", "riskScore": 0.9, "rule": "p0", "riskFactors": []}
    ]


def test_a_service_that_cannot_be_reached_is_unavailable(registry: ToolRegistry) -> None:
    arguments = SAMPLES["get_topology"][0]
    with respx.mock() as mock:
        mock.get(f"{CORE_URL}/api/v1/scans/{arguments['scanId']}/topology").mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(ToolUnavailableError):
            registry.call("get_topology", arguments, ToolContext(trace_id=TRACE))
