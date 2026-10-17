"""The shared HTTP base of the service tools: only the configured internal address, safe retries, a circuit breaker and
error messages without bodies or secrets (guardrails-security section 1, D-239)."""

from __future__ import annotations

import dataclasses

import httpx
import pytest
import respx

from src.tools.api_tool import InternalHttpClient, path_param
from src.tools.base_tool import ToolContext, ToolError, ToolRejectedError, ToolUnavailableError
from tests.support.tools import CORE_URL, TOKEN, TRACE, endpoint


def client(*, attempts: int = 3, fail_max: int = 5, url: str = CORE_URL) -> InternalHttpClient:
    return InternalHttpClient(endpoint("core-service", url, attempts=attempts, fail_max=fail_max), sleep=lambda _: None)


CONTEXT = ToolContext(trace_id=TRACE)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:8081",
        "http://10.0.0.5:8081",
        "ftp://127.0.0.1:8081",
        "http://user:pass@127.0.0.1:8081",
        "http://127.0.0.1:8081/api",
        "http://127.0.0.1:8081?x=1",
    ],
)
def test_a_base_url_outside_the_internal_hosts_or_not_a_bare_origin_is_refused(url: str) -> None:
    with pytest.raises(ToolError):
        client(url=url)


@pytest.mark.parametrize(
    "path",
    [
        "http://example.com/api/v1/projects",
        "//example.com/api/v1/projects",
        "/api/v1/../../admin",
        "/api/v1/projects/./x",
        "/api/v2/projects",
        "/api/v1/projects?x=1",
        "/api/v1/projects#x",
        "/api/v1/",
        "api/v1/projects",
        "/api/v1/projects/a b",
    ],
)
def test_a_path_that_could_leave_the_service_is_refused_before_any_request(path: str) -> None:
    with respx.mock(assert_all_mocked=True) as mock, pytest.raises(ToolError):
        client().request("GET", path, CONTEXT)
    assert mock.calls.call_count == 0


@pytest.mark.parametrize(
    ("value", "encoded"), [("abc", "abc"), ("a/b", "a%2Fb"), ("a?b#c", "a%3Fb%23c"), ("../x", "..%2Fx")]
)
def test_a_path_parameter_is_one_segment(value: str, encoded: str) -> None:
    assert path_param(value) == encoded


@pytest.mark.parametrize("value", ["", ".", ".."])
def test_an_empty_or_dot_path_parameter_is_refused(value: str) -> None:
    with pytest.raises(ToolError):
        path_param(value)


def test_the_request_carries_the_token_and_the_trace_and_no_proxy_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid:3128")
    monkeypatch.setenv("ALL_PROXY", "http://proxy.invalid:3128")
    with respx.mock() as mock:
        route = mock.get(f"{CORE_URL}/api/v1/projects").respond(200, json={})
        client().request("GET", "/api/v1/projects", CONTEXT)

    request = route.calls.last.request
    assert request.url.host == "127.0.0.1"
    assert (request.headers["X-Internal-Token"], request.headers["X-Trace-Id"]) == (TOKEN, TRACE)


def test_a_trace_id_of_another_shape_is_replaced_by_the_call_id() -> None:
    context = ToolContext(trace_id="not a trace\r\nX-Evil: 1")
    with respx.mock() as mock:
        route = mock.get(f"{CORE_URL}/api/v1/projects").respond(200, json={})
        client().request("GET", "/api/v1/projects", context)

    assert route.calls.last.request.headers["X-Trace-Id"] == context.call_id.hex


def test_a_redirect_is_not_followed() -> None:
    with respx.mock(assert_all_called=False) as mock:
        mock.get(f"{CORE_URL}/api/v1/projects").respond(302, headers={"location": "http://example.com/"})
        elsewhere = mock.get("http://example.com/").respond(200, json={})
        with pytest.raises(ToolUnavailableError):
            client().request("GET", "/api/v1/projects", CONTEXT)
    assert elsewhere.call_count == 0


@pytest.mark.parametrize("status", [500, 502, 503, 429])
def test_a_get_is_retried_on_a_transient_answer(status: int) -> None:
    with respx.mock() as mock:
        route = mock.get(f"{CORE_URL}/api/v1/projects").mock(
            side_effect=[httpx.Response(status), httpx.Response(200, json={"ok": True})]
        )
        reply = client().request("GET", "/api/v1/projects", CONTEXT)

    assert (reply.status, route.call_count) == (200, 2)


def test_a_post_without_an_idempotency_key_is_never_repeated() -> None:
    with respx.mock() as mock:
        route = mock.post(f"{CORE_URL}/api/v1/projects").respond(503)
        with pytest.raises(ToolUnavailableError):
            client().request("POST", "/api/v1/projects", CONTEXT, body={})
    assert route.call_count == 1


def test_a_post_without_a_key_is_not_repeated_after_a_connection_error_either() -> None:
    with respx.mock() as mock:
        route = mock.post(f"{CORE_URL}/api/v1/projects").mock(side_effect=httpx.ConnectError("down"))
        with pytest.raises(ToolUnavailableError):
            client().request("POST", "/api/v1/projects", CONTEXT, body={})
    assert route.call_count == 1


def test_a_side_effect_free_post_is_retried() -> None:
    with respx.mock() as mock:
        route = mock.post(f"{CORE_URL}/api/v1/analyses").mock(
            side_effect=[httpx.ConnectError("down"), httpx.Response(200, json={})]
        )
        client().request("POST", "/api/v1/analyses", CONTEXT, body={}, side_effect_free=True)
    assert route.call_count == 2


def test_a_client_error_is_not_retried_and_does_not_open_the_breaker() -> None:
    http = client(attempts=3, fail_max=2)
    with respx.mock() as mock:
        route = mock.get(f"{CORE_URL}/api/v1/projects").respond(404)
        for _ in range(4):
            with pytest.raises(ToolRejectedError):
                http.request("GET", "/api/v1/projects", CONTEXT)
    assert route.call_count == 4


def test_the_breaker_opens_after_repeated_failures_and_stops_calling_the_service() -> None:
    http = client(attempts=1, fail_max=2)
    with respx.mock() as mock:
        route = mock.get(f"{CORE_URL}/api/v1/projects").respond(503)
        for _ in range(2):
            with pytest.raises(ToolUnavailableError):
                http.request("GET", "/api/v1/projects", CONTEXT)
        with pytest.raises(ToolUnavailableError, match="circuit breaker"):
            http.request("GET", "/api/v1/projects", CONTEXT)
    assert route.call_count == 2


def test_error_messages_carry_no_body_header_or_token() -> None:
    secret_body = {"type": "https://quancrypt.local/problems/forbidden", "detail": "the-body-secret"}
    with respx.mock() as mock:
        mock.get(f"{CORE_URL}/api/v1/projects").respond(
            403, json=secret_body, headers={"content-type": "application/problem+json", "x-leak": "header-secret"}
        )
        mock.get(f"{CORE_URL}/api/v1/scans").respond(500, text="stack trace with the-body-secret")
        with pytest.raises(ToolRejectedError) as rejected:
            client().request("GET", "/api/v1/projects", CONTEXT)
        with pytest.raises(ToolUnavailableError) as failed:
            client(attempts=1).request("GET", "/api/v1/scans", CONTEXT)

    for error in (rejected.value, failed.value):
        message = str(error)
        assert "the-body-secret" not in message and "header-secret" not in message and TOKEN not in message
    assert rejected.value.problem_code == "forbidden"


@pytest.mark.parametrize(
    ("content_type", "body"),
    [
        ("application/json", {"type": "https://quancrypt.local/problems/forbidden"}),
        ("application/problem+json", {"type": "https://evil.example/problems/forbidden"}),
        ("application/problem+json", {"type": "https://quancrypt.local/problems/" + "x" * 100}),
        ("application/problem+json", ["not", "an", "object"]),
    ],
)
def test_only_a_well_formed_problem_type_becomes_a_problem_code(content_type: str, body: object) -> None:
    with respx.mock() as mock:
        mock.get(f"{CORE_URL}/api/v1/projects").respond(403, json=body, headers={"content-type": content_type})
        with pytest.raises(ToolRejectedError) as caught:
            client().request("GET", "/api/v1/projects", CONTEXT)
    assert caught.value.problem_code is None


def test_the_internal_token_never_appears_in_the_endpoint_repr() -> None:
    assert TOKEN not in repr(endpoint("core-service", CORE_URL))
    assert "internal_token" in {field.name for field in dataclasses.fields(endpoint("core-service", CORE_URL))}
