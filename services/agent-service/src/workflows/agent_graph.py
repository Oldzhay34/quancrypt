"""The LangGraph graphs (D-11: the only module that imports LangGraph) and the session checkpointer (D-252e, D-253).

Message graph (D-252b):
    input_guard ─DENY→ respond
        └ALLOW→ route ─inventory | risk_priority→ planner ─┐
                      └─────────── every other intent → answer ─┴→ output_guard → respond
Initial scan graph: discovery → topology → summary.

The graph is rebuilt for every request (stateless service); the nodes get their agents and guards as Protocols. The
orchestrator streams the graph node by node (`stream_mode="updates"`) and stops at a node boundary when the user asks.
A refusal is the fixed text (`refusal`) and never passes a language model; the answer the user sees has passed the
output checker.

`SessionCheckpointer` keeps the latest checkpoint of a session in agent_db through the `CheckpointStore` port: only the
allow-listed channels (codes and ids, no chat text) and the `source`/`step`/`parents` metadata, the checkpoint id only
in
its column, msgpack in strict mode, one write per call (`durability="exit"`), never above 64 KiB.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol, TypedDict
from uuid import UUID

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import (
    BaseCheckpointSaver,
    ChannelVersions,
    Checkpoint,
    CheckpointMetadata,
    CheckpointTuple,
)
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.base_agent import AgentContext, AgentResult, AgentRunner, AgentTask
from src.guardrails.chain import GuardDecision, GuardRequest
from src.guardrails.output_checker import OutputCheckResult
from src.llm.provider import TokenUsage
from src.memory.short_term import (
    CHECKPOINT_MAX_BYTES,
    CHECKPOINT_STATE_TYPE,
    CheckpointStore,
    SessionNotFoundError,
    StepName,
    StepStatus,
)
from src.prompts.system_prompts import refusal
from src.prompts.templates import no_scan_note
from src.workflows.task_router import RoutedIntent

_LOG = logging.getLogger("src.workflows")

Outcome = Literal["COMPLETED", "FAILED", "BUDGET_EXCEEDED", "CLARIFICATION_REQUIRED", "REFUSED"]
PLANNER_INTENTS = frozenset({"inventory", "risk_priority"})
# Channels a checkpoint may keep (D-252e): codes and ids only; message, draft, final and every other text is dropped.
PERSISTED_CHANNELS = frozenset({"last_intent", "scan_id", "plan_exists", "evidence", "budget"})
PERSISTED_METADATA = frozenset({"source", "step", "parents"})


class AgentState(TypedDict, total=False):
    # The prompt's fields (P4.6) ...
    session_id: str
    trace_id: str
    message: str
    lang: Literal["tr", "en"]
    guard_decision: dict[str, Any] | None
    intent: str
    tool_results: list[dict[str, Any]]
    draft: str
    final: str
    evidence: list[dict[str, Any]]
    budget: dict[str, int]
    # ... and what the workflow needs besides.
    project_id: str
    scan_id: str | None
    root: str | None
    outcome: Outcome
    clarifications: list[str]
    error_code: str | None
    scan_open: bool
    llm_disabled: bool
    last_intent: str
    plan_exists: bool


class Guard(Protocol):
    def decide(self, request: GuardRequest) -> GuardDecision: ...


class Router(Protocol):
    def route(self, text: str) -> RoutedIntent: ...


class AnswerChecker(Protocol):
    def check(
        self, text: str, language: Literal["tr", "en"], tool_outputs: Sequence[Mapping[str, Any]]
    ) -> OutputCheckResult: ...


NodeRecorder = Callable[[StepName, StepStatus, datetime, TokenUsage], None]


@dataclass(frozen=True)
class GraphDeps:
    """What the nodes need, built per request by the orchestrator (fresh agents and toolboxes, this run's context)."""

    context: AgentContext
    clock: Callable[[], datetime]
    record_node: NodeRecorder
    output_checker: AnswerChecker
    guard: Guard | None = None
    on_decision: Callable[[GuardDecision], None] | None = None
    router: Router | None = None
    planner: AgentRunner | None = None
    answer: AgentRunner | None = None
    discovery: AgentRunner | None = None
    topology: AgentRunner | None = None
    # Completes the initial scan in core-service (COMPLETED); called after the topology step (D-256).
    close_scan: Callable[[str], None] | None = None


_ZERO = TokenUsage(prompt_tokens=0, completion_tokens=0)


# ---- message graph ----


def build_message_graph(
    deps: GraphDeps, checkpointer: BaseCheckpointSaver[Any] | None = None
) -> CompiledStateGraph[Any]:
    graph: StateGraph[Any] = StateGraph(AgentState)
    graph.add_node("input_guard", lambda state: _input_guard(deps, state))
    graph.add_node("route", lambda state: _route(deps, state))
    graph.add_node("planner", lambda state: _planner(deps, state))
    graph.add_node("answer", lambda state: _answer(deps, state))
    graph.add_node("output_guard", lambda state: _output_guard(deps, state))
    graph.add_node("respond", _respond)
    graph.add_edge(START, "input_guard")
    graph.add_conditional_edges(
        "input_guard", lambda state: "respond" if state.get("outcome") == "REFUSED" else "route", ["respond", "route"]
    )
    graph.add_conditional_edges(
        "route", lambda state: "planner" if state.get("intent") in PLANNER_INTENTS else "answer", ["planner", "answer"]
    )
    graph.add_edge("planner", "output_guard")
    graph.add_edge("answer", "output_guard")
    graph.add_edge("output_guard", "respond")
    graph.add_edge("respond", END)
    return graph.compile(checkpointer=checkpointer)


def _input_guard(deps: GraphDeps, state: AgentState) -> dict[str, Any]:
    if deps.guard is None:
        raise RuntimeError("the message graph needs a guard")
    started = deps.clock()
    decision = deps.guard.decide(GuardRequest(state["message"], state["lang"]))
    if deps.on_decision is not None:
        deps.on_decision(decision)
    deps.record_node("INPUT_GUARD", "SUCCEEDED", started, _ZERO)
    update: dict[str, Any] = {
        "guard_decision": {
            "decision": decision.decision,
            "deciding_ring": decision.deciding_ring,
            "confidence": decision.confidence,
            "latency_ms": decision.latency_ms,
        }
    }
    if not decision.allowed:
        update["outcome"] = "REFUSED"
    return update


def _route(deps: GraphDeps, state: AgentState) -> dict[str, Any]:
    if deps.router is None:
        raise RuntimeError("the message graph needs a router")
    started = deps.clock()
    routed = deps.router.route(state["message"])
    deps.record_node("ROUTE", "SUCCEEDED", started, routed.usage)
    return {"intent": routed.intent, "last_intent": routed.intent, "budget": _add(state, routed.usage)}


def _planner(deps: GraphDeps, state: AgentState) -> dict[str, Any]:
    if deps.planner is None:
        raise RuntimeError("the message graph needs a planner")
    if not state.get("scan_id"):
        return {"outcome": "COMPLETED", "draft": no_scan_note(state["lang"])}
    intent = state.get("intent", "inventory")
    task = AgentTask(
        kind="plan" if intent == "risk_priority" else "inventory",
        language=state["lang"],
        project_id=UUID(state["project_id"]),
        scan_id=UUID(str(state["scan_id"])),
        question=state["message"],
        intent=intent,
    )
    result = deps.planner.run(task, deps.context)
    update = _from_result(result)
    if task.kind == "plan" and result.status == "COMPLETED":
        update["plan_exists"] = True
    return update


def _answer(deps: GraphDeps, state: AgentState) -> dict[str, Any]:
    if deps.answer is None:
        raise RuntimeError("the message graph needs an answer agent")
    scan = state.get("scan_id")
    task = AgentTask(
        kind="answer",
        language=state["lang"],
        project_id=UUID(state["project_id"]),
        scan_id=UUID(str(scan)) if scan else None,
        question=state["message"],
        intent=state.get("intent", "unknown"),
    )
    return _from_result(deps.answer.run(task, deps.context))


def _output_guard(deps: GraphDeps, state: AgentState) -> dict[str, Any]:
    started = deps.clock()
    draft = state.get("draft", "")
    if state.get("outcome") not in ("COMPLETED", "CLARIFICATION_REQUIRED") or not draft:
        deps.record_node("OUTPUT_GUARD", "SUCCEEDED", started, _ZERO)
        return {"final": draft}
    checked = deps.output_checker.check(draft, state["lang"], state.get("tool_results", []))
    deps.record_node("OUTPUT_GUARD", "SUCCEEDED", started, _ZERO)
    if checked.refused:  # out-of-scope content was produced: the answer is suppressed (guardrails-security section 4)
        return {"outcome": "REFUSED", "final": refusal(state["lang"]), "evidence": []}
    return {"final": checked.text}


def _respond(state: AgentState) -> dict[str, Any]:
    if state.get("outcome") == "REFUSED":
        return {"final": refusal(state["lang"]), "evidence": []}
    return {}


# ---- initial scan graph ----


def build_initial_scan_graph(deps: GraphDeps) -> CompiledStateGraph[Any]:
    graph: StateGraph[Any] = StateGraph(AgentState)
    graph.add_node("discovery", lambda state: _discovery(deps, state))
    graph.add_node("topology", lambda state: _topology(deps, state))
    graph.add_node("close_scan", lambda state: _close_scan(deps, state))
    graph.add_node("summary", lambda state: _summary(deps, state))
    graph.add_edge(START, "discovery")
    graph.add_conditional_edges(
        "discovery",
        lambda state: "topology" if state.get("outcome") == "COMPLETED" and state.get("scan_id") else "summary",
        ["topology", "summary"],
    )
    graph.add_edge("topology", "close_scan")
    graph.add_edge("close_scan", "summary")
    graph.add_edge("summary", END)
    return graph.compile()


def _discovery(deps: GraphDeps, state: AgentState) -> dict[str, Any]:
    if deps.discovery is None:
        raise RuntimeError("the initial scan graph needs a discovery agent")
    task = AgentTask(
        kind="initial_scan", language=state["lang"], project_id=UUID(state["project_id"]), root=state.get("root")
    )
    result = deps.discovery.run(task, deps.context)
    update = _from_result(result)
    scan = (result.data or {}).get("scanId")
    update["scan_id"] = str(scan) if scan else None
    # A successful discovery leaves its scan RUNNING for the topology; it must be closed from here on (D-256).
    update["scan_open"] = result.status == "COMPLETED" and bool(scan)
    return update


def _topology(deps: GraphDeps, state: AgentState) -> dict[str, Any]:
    if deps.topology is None:
        raise RuntimeError("the initial scan graph needs a topology agent")
    task = AgentTask(
        kind="topology",
        language=state["lang"],
        project_id=UUID(state["project_id"]),
        scan_id=UUID(str(state["scan_id"])),
        root=state.get("root"),
    )
    result = deps.topology.run(task, deps.context)
    update = _from_result(result)
    update["draft"] = "\n".join(part for part in (state.get("draft", ""), result.text) if part)
    update["evidence"] = state.get("evidence", []) + update["evidence"]
    update["tool_results"] = state.get("tool_results", []) + update["tool_results"]
    return update


def _close_scan(deps: GraphDeps, state: AgentState) -> dict[str, Any]:
    """Complete the scan whatever the topology step did: the findings are recorded and usable (D-256). A failed
    topology keeps its outcome, so the run still ends with an error event."""
    if deps.close_scan is None:
        raise RuntimeError("the initial scan graph needs a scan closer")
    deps.close_scan(str(state["scan_id"]))
    update: dict[str, Any] = {"scan_open": False}
    if state.get("outcome") not in (None, "COMPLETED"):
        update["error_code"] = "topology-failed"
    return update


def _summary(deps: GraphDeps, state: AgentState) -> dict[str, Any]:
    return _output_guard(deps, state)


# ---- helpers ----


def _from_result(result: AgentResult) -> dict[str, Any]:
    return {
        "outcome": result.status,
        "draft": result.text,
        "evidence": [
            {"kind": e.kind, "reference": e.reference, "source_version": e.source_version} for e in result.evidence
        ],
        "tool_results": [dict(result.data)] if result.data else [],
        "clarifications": list(result.clarifications),
        "error_code": result.error_code,
    }


def _add(state: AgentState, usage: TokenUsage) -> dict[str, int]:
    budget = dict(state.get("budget") or {"prompt_tokens": 0, "completion_tokens": 0})
    budget["prompt_tokens"] = budget.get("prompt_tokens", 0) + usage.prompt_tokens
    budget["completion_tokens"] = budget.get("completion_tokens", 0) + usage.completion_tokens
    return budget


# ---- the session checkpointer (D-252e, D-253) ----


class SessionCheckpointer(BaseCheckpointSaver[int]):
    """`BaseCheckpointSaver` over `CheckpointStore`: one latest checkpoint per session, codes and ids only.

    `configurable.persist` decides whether this call writes (from the session's second message on, D-252e); reading is
    always allowed. Pending writes are not kept (a graph is never resumed after an interruption).
    """

    def __init__(self, store: CheckpointStore) -> None:
        # Strict msgpack: no pickle fallback and no extension types beyond the safe set.
        super().__init__(serde=JsonPlusSerializer(pickle_fallback=False, allowed_msgpack_modules=None))
        self._store = store

    def get_tuple(self, config: RunnableConfig) -> CheckpointTuple | None:
        session_id = _session(config)
        stored = self._store.get(session_id)
        if stored is None:
            return None
        try:
            body = self.serde.loads_typed((stored.state_type, stored.state))
        except Exception:  # an unreadable checkpoint is only a lost speed-up, never a failed request
            _LOG.warning("A graph checkpoint could not be read and is ignored")
            return None
        checkpoint = dict(body["checkpoint"])
        checkpoint["id"] = str(stored.checkpoint_id)
        own = {"configurable": {"thread_id": str(session_id), "checkpoint_ns": "", "checkpoint_id": checkpoint["id"]}}
        return CheckpointTuple(own, checkpoint, body["metadata"], None, [])  # type: ignore[arg-type]

    def list(
        self,
        config: RunnableConfig | None,
        *,
        filter: dict[str, Any] | None = None,  # noqa: A002 - the base class names it so
        before: RunnableConfig | None = None,
        limit: int | None = None,
    ) -> Iterator[CheckpointTuple]:
        if config is None:
            return
        found = self.get_tuple(config)
        if found is not None and limit != 0:
            yield found

    def put(
        self,
        config: RunnableConfig,
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
        new_versions: ChannelVersions,
    ) -> RunnableConfig:
        session_id = _session(config)
        own: RunnableConfig = {
            "configurable": {"thread_id": str(session_id), "checkpoint_ns": "", "checkpoint_id": checkpoint["id"]}
        }
        if not config.get("configurable", {}).get("persist", False):
            return own
        stored_checkpoint = {key: value for key, value in checkpoint.items() if key != "id"}
        stored_checkpoint["channel_values"] = {
            key: value for key, value in checkpoint["channel_values"].items() if key in PERSISTED_CHANNELS
        }
        stored_metadata = {key: value for key, value in metadata.items() if key in PERSISTED_METADATA}
        state_type, state = self.serde.dumps_typed({"checkpoint": stored_checkpoint, "metadata": stored_metadata})
        if state_type != CHECKPOINT_STATE_TYPE or len(state) > CHECKPOINT_MAX_BYTES:
            _LOG.warning("A graph checkpoint was not stored (type or size); the request goes on without it")
            return own
        # The session may have been deleted meanwhile; there is nothing to keep then.
        with contextlib.suppress(SessionNotFoundError):
            self._store.put(session_id, UUID(checkpoint["id"]), state_type, state)
        return own

    def put_writes(
        self, config: RunnableConfig, writes: Sequence[tuple[str, Any]], task_id: str, task_path: str = ""
    ) -> None:
        return None  # pending writes are not kept (D-253)

    def delete_thread(self, thread_id: str) -> None:
        raise NotImplementedError("checkpoints are deleted with their session (CASCADE), D-253")


def _session(config: RunnableConfig) -> UUID:
    configurable = config.get("configurable", {})
    if configurable.get("checkpoint_ns", "") != "":
        raise ValueError("only the root namespace is checkpointed (D-253)")
    return UUID(str(configurable["thread_id"]))


def checkpoint_config(session_id: UUID, *, persist: bool) -> RunnableConfig:
    return {"configurable": {"thread_id": str(session_id), "checkpoint_ns": "", "persist": persist}}


# ---- the framework-free entry (D-11): the orchestrator sees only these ----


class Workflow(Protocol):
    """One graph built for one request; `run` yields each node's state change in order (the stop point)."""

    def run(self, state: Mapping[str, Any], session_id: UUID | None, persist: bool) -> Iterator[Mapping[str, Any]]: ...


class WorkflowFactory(Protocol):
    def message(self, deps: GraphDeps) -> Workflow: ...

    def initial_scan(self, deps: GraphDeps) -> Workflow: ...


class _CompiledWorkflow:
    def __init__(self, graph: CompiledStateGraph[Any], *, checkpointed: bool) -> None:
        self._graph = graph
        self._checkpointed = checkpointed

    def run(self, state: Mapping[str, Any], session_id: UUID | None, persist: bool) -> Iterator[Mapping[str, Any]]:
        if self._checkpointed and session_id is not None:
            updates = self._graph.stream(
                dict(state), checkpoint_config(session_id, persist=persist), stream_mode="updates", durability="exit"
            )
        else:
            updates = self._graph.stream(dict(state), stream_mode="updates")
        for update in updates:
            for delta in update.values():
                yield delta or {}


class LangGraphWorkflows:
    """`WorkflowFactory` over LangGraph; built once in the container with the checkpoint store (D-253)."""

    def __init__(self, checkpoints: CheckpointStore) -> None:
        self._saver = SessionCheckpointer(checkpoints)

    def message(self, deps: GraphDeps) -> Workflow:
        return _CompiledWorkflow(build_message_graph(deps, self._saver), checkpointed=True)

    def initial_scan(self, deps: GraphDeps) -> Workflow:
        return _CompiledWorkflow(build_initial_scan_graph(deps), checkpointed=False)
