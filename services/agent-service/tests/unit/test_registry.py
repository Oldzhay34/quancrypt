"""Tool registry and per-agent toolboxes: allow-lists, the call journal and fail-fast construction (D-238a, D-238d)."""

from __future__ import annotations

import logging
import uuid

import httpx
import pytest
import respx

from src.tools.base_tool import ToolContext, ToolError, ToolNotAllowedError, ToolRejectedError, ToolUnavailableError
from src.tools.registry import ToolRegistry
from tests.support.tool_samples import SAMPLES, SCAN
from tests.support.tools import APPROVED_ALLOW_LISTS, CORE_URL, TRACE, all_tools, build_registry, redactor, schemas


@pytest.fixture
def registry() -> ToolRegistry:
    return build_registry()


def test_a_toolbox_shows_only_the_tools_on_its_agents_list(registry: ToolRegistry) -> None:
    for agent, names in APPROVED_ALLOW_LISTS.items():
        assert registry.scoped(agent).names() == frozenset(names)
    assert registry.scoped("supervisor").names() == frozenset()


def test_no_agent_may_register_projects_or_read_consents(registry: ToolRegistry) -> None:
    workflow_only = {"register_project", "get_project", "get_consents", "list_scans"}
    for agent in APPROVED_ALLOW_LISTS:
        assert not workflow_only & registry.scoped(agent).names()


def test_an_allowed_call_succeeds_and_is_journaled(registry: ToolRegistry) -> None:
    toolbox = registry.scoped("planner")
    arguments, _, path, status, reply, _ = SAMPLES["get_topology"]
    context = ToolContext(trace_id=TRACE)
    with respx.mock() as mock:
        mock.get(CORE_URL + path).respond(status, json=reply)
        result = toolbox.invoke("get_topology", arguments, context)

    assert (result.status, result.tool_code, result.call_id, result.output) == (
        "SUCCEEDED",
        "CORE",
        context.call_id,
        reply,
    )
    [record] = toolbox.records()
    assert (record.id, record.tool_code, record.status) == (context.call_id, "CORE", "SUCCEEDED")


def test_a_call_outside_the_allow_list_is_refused_journaled_as_denied_and_logged(
    registry: ToolRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    toolbox = registry.scoped("topology")
    context = ToolContext(trace_id=TRACE)
    with (
        respx.mock(assert_all_mocked=True) as mock,
        caplog.at_level(logging.WARNING, logger="src.tools"),
        pytest.raises(ToolNotAllowedError),
    ):
        toolbox.invoke("create_plan", SAMPLES["create_plan"][0], context)
    assert mock.calls.call_count == 0  # the service never sees the call

    [record] = toolbox.records()
    assert (record.id, record.tool_code, record.status, record.duration_ms) == (context.call_id, "CORE", "DENIED", 0)
    assert any("topology" in message and "create_plan" in message for message in caplog.messages)


def test_an_unregistered_tool_name_is_journaled_as_unknown_and_denied(
    registry: ToolRegistry, caplog: pytest.LogCaptureFixture
) -> None:
    toolbox = registry.scoped("planner")
    with caplog.at_level(logging.WARNING, logger="src.tools"), pytest.raises(ToolNotAllowedError):
        toolbox.invoke("run_shell\n\x1b[2Jrm -rf /", {}, ToolContext(trace_id=TRACE))

    [record] = toolbox.records()
    assert (record.tool_code, record.status) == ("UNKNOWN", "DENIED")
    assert all("\n" not in message and "\x1b" not in message for message in caplog.messages)  # no log injection


def test_a_rejected_call_is_journaled_as_failed(registry: ToolRegistry) -> None:
    toolbox = registry.scoped("planner")
    with respx.mock() as mock:
        mock.get(f"{CORE_URL}/api/v1/scans/{SCAN}/topology").respond(404)
        with pytest.raises(ToolRejectedError):
            toolbox.invoke("get_topology", {"scanId": SCAN}, ToolContext(trace_id=TRACE))

    assert [record.status for record in toolbox.records()] == ["FAILED"]


def test_a_read_timeout_is_journaled_as_timed_out(registry: ToolRegistry) -> None:
    toolbox = registry.scoped("planner")
    with respx.mock() as mock:
        route = mock.get(f"{CORE_URL}/api/v1/scans/{SCAN}/topology").mock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(ToolUnavailableError) as caught:
            toolbox.invoke("get_topology", {"scanId": SCAN}, ToolContext(trace_id=TRACE))

    assert caught.value.timed_out
    assert route.call_count == 1  # a started request is never repeated
    assert [record.status for record in toolbox.records()] == ["TIMED_OUT"]


def test_toolboxes_keep_separate_journals(registry: ToolRegistry) -> None:
    planner, topology = registry.scoped("planner"), registry.scoped("topology")
    with pytest.raises(ToolNotAllowedError):
        topology.invoke("kb_search", {"query": "x"}, ToolContext(trace_id=TRACE))
    planner.invoke("kb_search", {"query": "ml kem"}, ToolContext(trace_id=TRACE, call_id=uuid.uuid4()))

    assert [record.status for record in topology.records()] == ["DENIED"]
    assert [(record.tool_code, record.status) for record in planner.records()] == [("KB_SEARCH", "SUCCEEDED")]


def test_an_agent_without_an_allow_list_gets_no_toolbox(registry: ToolRegistry) -> None:
    with pytest.raises(ToolError):
        registry.scoped("attacker")


def test_an_allow_list_naming_an_unregistered_tool_stops_the_service() -> None:
    with pytest.raises(ToolError, match="not registered"):
        build_registry({"planner": ("kb_search", "web_search")})


def test_registering_a_tool_twice_stops_the_service() -> None:
    store = schemas()
    tools = all_tools(store)
    with pytest.raises(ToolError, match="twice"):
        ToolRegistry([*tools, tools[0]], {}, store, redactor())
