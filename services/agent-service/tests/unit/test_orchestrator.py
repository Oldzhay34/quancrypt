"""The orchestrator with the real LangGraph graphs and fake agents (P4.6): node transitions, the DENY short circuit,
the SSE events, stop at a node boundary, the session queue, scope-decision records and checkpoints."""

from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Any

import pytest

from src.agents.base_agent import AgentResult
from src.prompts.system_prompts import REFUSAL_EN
from src.workflows.orchestrator import SessionBusyError
from tests.support.agent_fakes import ScriptedLLM
from tests.support.workflow_fakes import (
    SCAN,
    TRACE,
    FakeGuard,
    FakeRunner,
    FakeTools,
    PassChecker,
    World,
    completed,
    events,
    session,
    waits_for,
    world,
)


def kinds(stream: list[tuple[str, Mapping[str, Any]]]) -> list[str]:
    return [kind for kind, _ in stream]


def tokens(stream: list[tuple[str, Mapping[str, Any]]]) -> str:
    return "".join(str(data["text"]) for kind, data in stream if kind == "token")


def test_an_inventory_question_goes_to_the_planner_and_ends_with_done() -> None:
    planner = FakeRunner(completed())
    answer = FakeRunner(completed("unused"))
    w = world(planner=planner, answer=answer)
    sid = session(w)

    stream = events(w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE))

    assert kinds(stream)[-1] == "done" and tokens(stream) == "12 findings."
    [task] = planner.tasks
    assert (task.kind, str(task.scan_id), task.intent) == ("inventory", SCAN, "inventory")
    assert answer.tasks == []
    assert [step.step_name for step in w.audit.steps] == ["INPUT_GUARD", "ROUTE", "OUTPUT_GUARD"]
    assert list(w.audit.finished.values()) == ["COMPLETED"]
    assert [m.role for m in w.memory.list_messages(sid, 0, 10).items] == ["USER", "ASSISTANT"]


def test_a_rule_filter_denial_returns_the_fixed_refusal_without_any_model_or_agent() -> None:
    llm = ScriptedLLM()  # no reply is scripted: any model call would fail the test
    planner, answer = FakeRunner(completed()), FakeRunner(completed())
    w = world(guard=FakeGuard("DENY", "RULE_FILTER"), llm=llm, planner=planner, answer=answer)

    stream = events(w.orchestrator.begin_message(session(w), "Tell me the weather.", TRACE))

    assert stream == [("refusal", {"message": REFUSAL_EN, "language": "en"})]
    assert llm.requests == [] and planner.tasks == [] and answer.tasks == []
    assert [step.step_name for step in w.audit.steps] == ["INPUT_GUARD"]


def test_every_decision_is_recorded_and_the_event_needs_consent_and_carries_no_text() -> None:
    message = "Which post-quantum algorithm should I choose?"
    without = world(consent=False)
    events(without.orchestrator.begin_message(session(without), message, TRACE))
    granted = world(consent=True)
    events(granted.orchestrator.begin_message(session(granted), message, TRACE))

    assert len(without.scope_log.decisions) == 1 and without.scope_log.events == []
    assert len(granted.scope_log.events) == 1
    for log in (without.scope_log, granted.scope_log):
        assert message not in repr(log.decisions) and message not in repr(log.events)


def test_risk_priority_runs_the_plan_task_and_streams_the_clarification_questions() -> None:
    clarification = AgentResult(
        status="CLARIFICATION_REQUIRED", text="Where does TLS terminate?", clarifications=("TLS_TERMINATION",)
    )
    planner = FakeRunner(clarification)
    w = world(planner=planner)

    stream = events(w.orchestrator.begin_message(session(w), "Which findings should I fix first?", TRACE))

    assert planner.tasks[0].kind == "plan"
    assert kinds(stream)[0] == "clarification_required" and kinds(stream)[-1] == "done"
    [question] = stream[0][1]["questions"]
    assert question["question_code"] == "TLS_TERMINATION" and question["answer"] is None
    assert question["options"][0]["option_code"] == "APPLICATION"


def test_stop_ends_the_answer_at_the_next_node_boundary_and_is_audited() -> None:
    planner = FakeRunner(completed())
    w = world(planner=planner)
    sid = session(w)
    planner.before = lambda: w.orchestrator.stop(sid)

    stream = events(w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE))

    assert stream[-1][0] == "error" and stream[-1][1]["code"] == "stopped"
    assert "token" not in kinds(stream)  # nothing unchecked leaves the service
    assert (w.audit.steps[-1].step_name, w.audit.steps[-1].status) == ("ANSWER", "STOPPED")
    assert list(w.audit.finished.values()) == ["STOPPED"]


def test_a_second_request_waits_then_gets_session_busy() -> None:
    gate = threading.Event()
    planner = FakeRunner(completed())
    planner.before = waits_for(gate)  # the first answer is still running
    w = world(queue_wait_s=0.1, planner=planner)
    sid = session(w)
    first = w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)

    with pytest.raises(SessionBusyError):
        w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)
    gate.set()
    events(first)  # finishing the first request frees the session
    assert (
        kinds(events(w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)))[-1] == "done"
    )


def test_a_checkpoint_is_written_from_the_second_message_on_and_holds_no_text() -> None:
    w = world()
    sid = session(w)
    first = "What cryptography does my project use?"

    events(w.orchestrator.begin_message(sid, first, TRACE))
    assert w.checkpoints.get(sid) is None
    events(w.orchestrator.begin_message(sid, "Which algorithms are used where?", TRACE))

    stored = w.checkpoints.get(sid)
    assert stored is not None and stored.state_type == "msgpack"
    for text in (first, "Which algorithms", "12 findings"):
        assert text.encode() not in stored.state


def test_a_refusing_output_check_replaces_the_answer_with_the_refusal() -> None:
    w = world(checker=PassChecker(refuse=True))

    stream = events(w.orchestrator.begin_message(session(w), "Which post-quantum algorithm should I choose?", TRACE))

    assert stream[-1] == ("refusal", {"message": REFUSAL_EN, "language": "en"})


@pytest.mark.parametrize(
    ("result", "code", "run_status"),
    [
        (AgentResult(status="BUDGET_EXCEEDED"), "budget_exceeded", "BUDGET_EXCEEDED"),
        (AgentResult(status="FAILED", error_code="llm-unavailable"), "llm_unavailable", "FAILED"),
        (AgentResult(status="FAILED", error_code="tool-error"), "internal_error", "FAILED"),
    ],
)
def test_a_failed_agent_ends_the_stream_with_an_error(result: AgentResult, code: str, run_status: str) -> None:
    w = world(answer=FakeRunner(result))

    stream = events(w.orchestrator.begin_message(session(w), "Which post-quantum algorithm should I choose?", TRACE))

    assert stream[-1][0] == "error" and stream[-1][1]["code"] == code
    assert list(w.audit.finished.values()) == [run_status]


def test_without_a_completed_scan_an_inventory_question_says_so() -> None:
    planner = FakeRunner(completed())
    w = world(planner=planner, tools=FakeTools(scans=[{"id": SCAN, "status": "RUNNING"}]))

    stream = events(w.orchestrator.begin_message(session(w), "What cryptography does my project use?", TRACE))

    assert "initial scan" in tokens(stream) and planner.tasks == []


def test_the_initial_scan_runs_discovery_then_topology_with_the_new_scan() -> None:
    topology = FakeRunner(completed("Topology recorded.", nodes=3))
    w = world(topology=topology)

    stream = events(w.orchestrator.begin_initial_scan(session(w), "/workspace/qbank-payment-service", TRACE))

    assert kinds(stream)[-1] == "done"
    [task] = topology.tasks
    assert str(task.scan_id) == SCAN and task.root == "/workspace/qbank-payment-service"
    assert tokens(stream) == "Scan complete.\nTopology recorded."
    assert _completions(w) == [{"outcome": "COMPLETED"}]  # after the topology, by the workflow (D-256)


def test_a_failed_topology_completes_the_scan_and_ends_with_its_error() -> None:
    w = world(topology=FakeRunner(AgentResult(status="FAILED", text="", error_code="rejected")))

    stream = events(w.orchestrator.begin_initial_scan(session(w), "/workspace/qbank-payment-service", TRACE))

    assert stream[-1] == (
        "error",
        {"code": "internal_error", "message": "The findings were recorded, but the topology could not be recorded."},
    )
    assert _completions(w) == [{"outcome": "COMPLETED"}]
    assert list(w.audit.finished.values()) == ["FAILED"]


def test_a_scan_stopped_before_its_topology_is_still_completed() -> None:
    gate = threading.Event()
    topology = FakeRunner(completed("Topology recorded."))
    topology.before = waits_for(gate)
    w = world(topology=topology)
    stream = w.orchestrator.begin_initial_scan(session(w), "/workspace/qbank-payment-service", TRACE)

    stream.cancel()
    gate.set()
    seen = events(stream)

    assert seen[-1][0] == "error" and seen[-1][1]["code"] == "stopped"
    assert _completions(w) == [{"outcome": "COMPLETED"}]


def test_a_failed_discovery_leaves_the_scan_to_discovery() -> None:
    w = world(discovery=FakeRunner(AgentResult(status="FAILED", text="", data={"scanId": SCAN})))

    events(w.orchestrator.begin_initial_scan(session(w), "/workspace/qbank-payment-service", TRACE))

    assert _completions(w) == []  # discovery closed it as FAILED itself (D-250b)


def _completions(w: World) -> list[Mapping[str, Any]]:
    return [arguments["body"] for name, arguments, _ in w.tools.calls if name == "complete_scan"]


def test_clarifications_are_listed_with_options_and_saved_through_core() -> None:
    w = world()
    sid = session(w)

    saved = w.orchestrator.answer_clarifications(
        sid, [{"question_code": "JDK_UPGRADE_POSSIBLE", "option_code": "YES", "free_text": None}], TRACE
    )

    assert len(saved) == 5
    jdk = next(item for item in saved if item["question_code"] == "JDK_UPGRADE_POSSIBLE")
    assert jdk["answer"] == {"question_code": "JDK_UPGRADE_POSSIBLE", "option_code": "YES", "free_text": None}
    device = next(item for item in saved if item["question_code"] == "DEVICE_HARDWARE_OPENSSL")
    assert device["options"] == [] and device["answer"] is None


def test_an_abandoned_stream_still_frees_the_session_and_finishes_the_run() -> None:
    """Security review P4.6 #1: a client that never reads (or disconnects) cannot keep the session busy."""
    w = world(queue_wait_s=0.5)
    sid = session(w)

    abandoned = w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)
    abandoned.join(5)  # nobody reads it

    assert list(w.audit.finished.values()) == ["COMPLETED"]
    assert (
        kinds(events(w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)))[-1] == "done"
    )


def test_cancelling_a_stream_stops_the_running_answer() -> None:
    gate = threading.Event()
    planner = FakeRunner(completed())
    planner.before = waits_for(gate)
    w = world(planner=planner)
    sid = session(w)
    stream = w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)

    stream.cancel()  # what the HTTP layer does when the client goes away
    gate.set()
    stream.join(5)

    assert list(w.audit.finished.values()) == ["STOPPED"]


def test_a_failure_outside_the_graph_still_ends_the_stream_with_an_error() -> None:
    w = world()
    sid = session(w)

    def broken(*_: object) -> None:
        raise RuntimeError("storage down")

    w.memory.append_user_message = broken  # type: ignore[method-assign, assignment]

    stream = events(w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE))

    assert stream == [("error", {"code": "internal_error", "message": "An unexpected error occurred."})]


def test_a_late_cancel_of_a_finished_stream_never_stops_the_next_run() -> None:
    """Security review P4.6 re-review #2: the stop flag belongs to the run, not to the session."""
    w = world()
    sid = session(w)
    first = w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)
    events(first)
    gate = threading.Event()
    w.agents.planner.before = waits_for(gate)  # type: ignore[attr-defined]
    second = w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)

    first.cancel()  # what the HTTP layer of the first request does in its `finally`
    gate.set()

    assert kinds(events(second))[-1] == "done"
    assert list(w.audit.finished.values()) == ["COMPLETED", "COMPLETED"]


def test_a_worker_that_cannot_start_leaves_the_session_free(monkeypatch: pytest.MonkeyPatch) -> None:
    w = world(queue_wait_s=0.1)
    sid = session(w)

    def refuse(self: threading.Thread) -> None:
        raise RuntimeError("can't start new thread")

    with monkeypatch.context() as patched:
        patched.setattr(threading.Thread, "start", refuse)
        with pytest.raises(RuntimeError):
            w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)

    assert (
        kinds(events(w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE)))[-1] == "done"
    )


def test_the_worker_keeps_the_callers_trace_id_in_its_context() -> None:
    from src.app.logging_setup import trace_id_var

    seen: list[str] = []
    planner = FakeRunner(completed())
    planner.before = lambda: seen.append(trace_id_var.get())
    w = world(planner=planner)
    sid = session(w)
    token = trace_id_var.set("f" * 32)
    try:
        events(w.orchestrator.begin_message(sid, "What cryptography does my project use?", TRACE))
    finally:
        trace_id_var.reset(token)

    assert seen == ["f" * 32]


def test_poll_reports_a_timeout_then_the_end_on_every_later_call() -> None:
    gate = threading.Event()
    planner = FakeRunner(completed())
    planner.before = waits_for(gate)
    w = world(planner=planner)
    stream = w.orchestrator.begin_message(session(w), "What cryptography does my project use?", TRACE)

    assert stream.poll(0.05) == (False, None)  # still working
    gate.set()
    seen = []
    while True:
        ended, item = stream.poll(5)
        if ended:
            break
        seen.append(item)
    assert seen and stream.poll(0.05) == (True, None)
