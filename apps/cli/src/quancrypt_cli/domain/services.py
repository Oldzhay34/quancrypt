"""The services of the `app` profile the CLI waits for and the web UI it opens (docs/ports.md)."""

from __future__ import annotations

from dataclasses import dataclass

from quancrypt_cli.domain.session_token import SessionToken

UI_URL = "http://127.0.0.1:8080"
# The only hosts the CLI calls (guardrails-security section 1).
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


@dataclass(frozen=True)
class ServiceEndpoint:
    """One health target. `required` services must be ready before `init` goes on; the web UI is optional until P5.2.
    `strict` means only HTTP 200 counts (a readiness endpoint); otherwise any answer below 500 shows it is serving."""

    name: str
    url: str
    required: bool
    strict: bool


@dataclass(frozen=True)
class ServiceHealth:
    name: str
    healthy: bool
    detail: str


CORE = ServiceEndpoint("core-service", "http://127.0.0.1:8081/health/readiness", True, True)
ANALYZER = ServiceEndpoint("analyzer-service", "http://127.0.0.1:8082/health/readiness", True, True)
AGENT = ServiceEndpoint("agent-service", "http://127.0.0.1:8083/health/readiness", True, True)
# TODO(P5.1-1): the web UI arrives in P5.2; then it becomes `required=True` and the "not installed yet" note
# goes (D-275).
WEB_UI = ServiceEndpoint("web-ui", UI_URL + "/", False, False)

BACKEND_SERVICES = (CORE, ANALYZER, AGENT)
ALL_SERVICES = (*BACKEND_SERVICES, WEB_UI)
CORE_BASE_URL = "http://127.0.0.1:8081"


def ui_open_url(token: SessionToken) -> str:
    """The address the browser opens: the token travels in the URL fragment, which a browser never sends to a server."""
    return f"{UI_URL}/#token={token.value}"
