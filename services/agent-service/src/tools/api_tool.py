"""The shared HTTP base of the service tools (P4.3): one client per internal service.

Only the configured base URL of the service is ever called: a path must be a relative `/api/v1/...` path and the final
URL must keep the base URL's scheme, host and port, so no tool can reach another host (guardrails-security section 1).
No proxy variables (`trust_env=False`) and no redirects.

Every request has a timeout and carries `X-Trace-Id` and `X-Internal-Token`. `tenacity` retries a connection failure, a
5xx and a 429, and only when repeating is safe (GET, PUT, or a POST with an `Idempotency-Key`); a timeout on a started
request is not retried. The retry sits inside a `pybreaker` circuit breaker per service (OllamaProvider pattern, P4.1).
Error messages carry the status and the problem code at most, never a response body or a header value.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import quote

import httpx
import pybreaker
from pydantic import BaseModel, ValidationError
from tenacity import RetryCallState, Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.tools.base_tool import (
    SchemaStore,
    ToolCode,
    ToolContext,
    ToolError,
    ToolOutputError,
    ToolRejectedError,
    ToolUnavailableError,
)

_LOG = logging.getLogger("src.tools")

Method = Literal["GET", "POST", "PUT"]
_PATH = re.compile(r"^/api/v1(?:/[A-Za-z0-9._~%-]+)+$")
_PROBLEM_TYPE = re.compile(r"^https://quancrypt\.local/problems/([a-z][a-z0-9-]{0,63})$")
_TRACE_ID = re.compile(r"^[0-9a-f]{32}$")


@dataclass(frozen=True)
class ServiceEndpoint:
    """Plain connection values of one internal service (the tools do not import the application settings)."""

    name: str
    base_url: str
    internal_token: str = field(repr=False)
    allowed_hosts: frozenset[str]
    connect_timeout_s: float
    timeout_s: float
    retry_max_attempts: int
    retry_wait_initial_s: float
    retry_wait_max_s: float
    breaker_fail_max: int
    breaker_reset_timeout_s: float


@dataclass(frozen=True)
class HttpReply:
    status: int
    content_type: str
    body: bytes

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError as exc:
            raise ToolError("the service answered with a body that is not JSON") from exc

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


class _TransientError(ToolUnavailableError):
    """Worth a retry: the connection failed or the service answered 5xx or 429."""


class _BreakerLogger(pybreaker.CircuitBreakerListener):
    def state_change(self, cb: pybreaker.CircuitBreaker, old_state: Any, new_state: Any) -> None:
        _LOG.warning("Circuit breaker %s: %s -> %s", cb.name, old_state.name, new_state.name)


def path_param(value: str) -> str:
    """Encode one path segment (an id never changes the path's structure)."""
    encoded = quote(value, safe="")
    if not encoded or encoded in (".", ".."):
        raise ToolError("a path parameter must not be empty or a dot segment")
    return encoded


class InternalHttpClient:
    def __init__(
        self,
        endpoint: ServiceEndpoint,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        base = httpx.URL(endpoint.base_url)
        if base.scheme not in ("http", "https") or base.host not in endpoint.allowed_hosts:
            raise ToolError(f"the base URL of {endpoint.name} is not an allowed internal address")
        if base.userinfo or base.query or base.fragment or base.path not in ("", "/"):
            raise ToolError(f"the base URL of {endpoint.name} must be a bare origin")
        self._endpoint = endpoint
        self._base = base
        self._client = httpx.Client(
            timeout=httpx.Timeout(endpoint.timeout_s, connect=endpoint.connect_timeout_s),
            transport=transport,
            trust_env=False,
            follow_redirects=False,
        )
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=endpoint.breaker_fail_max,
            reset_timeout=endpoint.breaker_reset_timeout_s,
            # A rejected request (4xx) says nothing about availability.
            exclude=[ToolRejectedError],
            listeners=[_BreakerLogger()],
            name=endpoint.name,
        )
        self._retrying = Retrying(
            stop=stop_after_attempt(endpoint.retry_max_attempts),
            wait=wait_exponential(multiplier=endpoint.retry_wait_initial_s, max=endpoint.retry_wait_max_s),
            retry=retry_if_exception_type(_TransientError),
            before_sleep=self._log_retry,
            sleep=sleep,
            reraise=True,
        )

    @property
    def name(self) -> str:
        return self._endpoint.name

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: Method,
        path: str,
        context: ToolContext,
        *,
        params: Mapping[str, str | int | bool] | None = None,
        body: Any = None,
        idempotency_key: str | None = None,
        accept: str = "application/json",
        extra_headers: Mapping[str, str] | None = None,
        side_effect_free: bool = False,
    ) -> HttpReply:
        url = self._url(path)
        headers = {
            "Accept": accept,
            "X-Internal-Token": self._endpoint.internal_token,
            "X-Trace-Id": context.trace_id if _TRACE_ID.fullmatch(context.trace_id) else context.call_id.hex,
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        for name, value in (extra_headers or {}).items():
            headers.setdefault(name, value)
        query = {key: _query_value(value) for key, value in (params or {}).items()}
        # Repeating is safe for GET and PUT, a command with an Idempotency-Key and a POST the contract declares free of
        # side effects (analyzer, D-178a).
        repeatable = method in ("GET", "PUT") or idempotency_key is not None or side_effect_free

        def send() -> HttpReply:
            try:
                response = self._client.request(method, url, headers=headers, params=query, json=body)
            except httpx.HTTPError as exc:
                raise _translate(exc, self.name, repeatable) from None
            return _reply(response, self.name, repeatable)

        try:
            reply: HttpReply = self._breaker.call(self._retrying, send)
        except pybreaker.CircuitBreakerError:
            raise ToolUnavailableError(f"the {self.name} circuit breaker is open") from None
        return reply

    def _url(self, path: str) -> httpx.URL:
        if not _PATH.fullmatch(path) or any(part in (".", "..") for part in path.split("/")):
            raise ToolError("a service path must be a relative /api/v1/... path without dot segments")
        url = self._base.join(path)
        if (url.scheme, url.host, url.port) != (self._base.scheme, self._base.host, self._base.port):
            raise ToolError("a request may only go to the configured service address")
        return url

    def _log_retry(self, state: RetryCallState) -> None:
        outcome = state.outcome
        error = type(outcome.exception()).__name__ if outcome is not None and outcome.failed else "unknown"
        _LOG.warning("%s call failed (%s); attempt %d, retrying", self.name, error, state.attempt_number)


def _query_value(value: str | int | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _translate(exc: httpx.HTTPError, service: str, repeatable: bool) -> ToolUnavailableError:
    """A connection failure is retried (when repeating is safe); a timeout on a started request never is."""
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout) and repeatable:
        return _TransientError(f"{service} is not reachable")
    if isinstance(exc, httpx.TimeoutException):
        return ToolUnavailableError(f"{service} did not answer in time", timed_out=True)
    return ToolUnavailableError(f"the request to {service} failed")


def _reply(response: httpx.Response, service: str, repeatable: bool) -> HttpReply:
    status = response.status_code
    if 200 <= status < 300:
        return HttpReply(status, response.headers.get("content-type", ""), response.content)
    if status == 429 or status >= 500:
        error = (_TransientError if repeatable else ToolUnavailableError)(f"{service} answered HTTP {status}")
        raise error
    if 400 <= status < 500:
        raise ToolRejectedError(status, _problem_code(response))
    raise ToolUnavailableError(f"{service} answered an unexpected HTTP {status}")


def _problem_code(response: httpx.Response) -> str | None:
    if not response.headers.get("content-type", "").startswith("application/problem+json"):
        return None
    try:
        problem = json.loads(response.content)
    except ValueError:
        return None
    kind = problem.get("type") if isinstance(problem, dict) else None
    match = _PROBLEM_TYPE.fullmatch(kind) if isinstance(kind, str) else None
    return match.group(1) if match else None


# ---- endpoint tools ----


@dataclass(frozen=True)
class EndpointSpec:
    """How one tool maps onto one endpoint of a service contract.

    Arguments: path parameters and query parameters are top-level arguments named as in the OpenAPI document; the
    request body, when there is one, is the `body` argument. `command` sends the call id as `Idempotency-Key`.
    """

    name: str
    method: Method
    path: str
    path_params: tuple[str, ...] = ()
    query_params: tuple[str, ...] = ()
    header_params: tuple[tuple[str, str], ...] = ()
    has_body: bool = False
    command: bool = False
    side_effect_free: bool = False
    reply: Literal["json", "markdown"] = "json"
    response_model: type[BaseModel] | None = None


class EndpointTool:
    """A `Tool` that calls one endpoint; the reply is parsed with the generated contract model when there is one."""

    def __init__(
        self, spec: EndpointSpec, client: InternalHttpClient, schemas: SchemaStore, tool_code: ToolCode
    ) -> None:
        self._spec = spec
        self._client = client
        self._tool_code = tool_code
        self._input_schema = schemas.part(spec.name, "input")
        self._output_schema = schemas.part(spec.name, "output")

    @property
    def name(self) -> str:
        return self._spec.name

    @property
    def tool_code(self) -> ToolCode:
        return self._tool_code

    @property
    def input_schema(self) -> Mapping[str, Any]:
        return self._input_schema

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return self._output_schema

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Mapping[str, Any]:
        spec = self._spec
        path = spec.path
        for name in spec.path_params:
            path = path.replace("{" + name + "}", path_param(str(arguments[name])))
        params = {name: arguments[name] for name in spec.query_params if name in arguments}
        headers = {header: str(arguments[name]) for name, header in spec.header_params if name in arguments}
        reply = self._client.request(
            spec.method,
            path,
            context,
            params=params,
            body=arguments.get("body") if spec.has_body else None,
            idempotency_key=str(context.call_id) if spec.command else None,
            accept="text/markdown" if spec.reply == "markdown" else "application/json",
            extra_headers=headers,
            side_effect_free=spec.side_effect_free,
        )
        if spec.reply == "markdown":
            return {"markdown": reply.text()}
        payload = reply.json()
        if not isinstance(payload, dict):
            raise ToolOutputError(f"{spec.name}: the service answered with a JSON value that is not an object")
        if spec.response_model is not None:
            try:
                spec.response_model.model_validate(payload)
            except ValidationError:
                raise ToolOutputError(f"{spec.name}: the reply does not fit the service contract") from None
        return payload
