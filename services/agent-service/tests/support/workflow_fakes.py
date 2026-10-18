"""Test doubles for the workflow layer (P4.6): a scripted guard, agents, consent reader, tool caller and an orchestrator
built on the in-memory memory doubles. Production code never imports this module."""

from __future__ import annotations

import threading
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

from src.agents.base_agent import AgentContext, AgentResult, AgentTask
from src.guardrails.chain import DecidingRing, GuardDecision, GuardRequest
from src.guardrails.output_checker import OutputCheckResult
from src.llm.provider import LLMProvider
from src.memory.short_term import ConversationWindow
from src.tools.base_tool import ToolContext, ToolError
from src.workflows.agent_graph import LangGraphWorkflows
from src.workflows.orchestrator import AgentSet, Orchestrator
from tests.support.agent_fakes import RecordingAuditLog, ScriptedLLM
from tests.support.memory_fakes import InMemoryCheckpointStore, InMemoryConversationMemory, InMemoryScopeDecisionLog

PROJECT = UUID("00000000-0000-0000-0000-00000000a001")
SCAN = "00000000-0000-0000-0000-00000000b001"
KEY = "a" * 64
TRACE = "0123456789abcdef0123456789abcdef"


class FakeGuard:
    def __init__(self, decision: str = "ALLOW", ring: DecidingRing = "LLM_SELF_CHECK") -> None:
        self._decision = decision
        self._ring = ring
        self.requests: list[GuardRequest] = []

    def decide(self, request: GuardRequest) -> GuardDecision:
        self.requests.append(request)
        confidence = 0.9 if self._ring == "SCOPE_CLASSIFIER" else None
        return GuardDecision(self._decision, confidence, self._ring, 3, request.language)  # type: ignore[arg-type]


class PassChecker:
    """Returns the answer unchanged (the real checker has its own tests); records what it was given."""

    def __init__(self, refuse: bool = False) -> None:
        self._refuse = refuse
        self.calls: list[tuple[str, Sequence[Mapping[str, Any]]]] = []

    def check(self, text: str, language: str, tool_outputs: Sequence[Mapping[str, Any]]) -> OutputCheckResult:
        self.calls.append((text, tool_outputs))
        return OutputCheckResult(text=text, refused=self._refuse, unverified_count=0, redacted=False)


@dataclass
class FakeRunner:
    result: AgentResult
    tasks: list[AgentTask] = field(default_factory=list)
    before: Callable[[], None] | None = None

    def run(self, task: AgentTask, context: AgentContext) -> AgentResult:
        self.tasks.append(task)
        if self.before is not None:
            self.before()
        return self.result


class FakeConsent:
    def __init__(self, granted: bool) -> None:
        self.granted = granted
        self.calls: list[UUID] = []

    def warehouse_consent(self, project_id: UUID, trace_id: str) -> bool:
        self.calls.append(project_id)
        return self.granted


class FakeTools:
    """The workflow layer's tool caller: get_project, list_scans, complete_scan, get_project_profile and
    save_clarification_answers."""

    def __init__(self, *, scans: Sequence[Mapping[str, Any]] | None = None) -> None:
        self.calls: list[tuple[str, Mapping[str, Any], ToolContext]] = []
        self.scans = list(scans if scans is not None else [{"id": SCAN, "status": "COMPLETED"}])
        self.answers: list[dict[str, Any]] = []
        self.fail: dict[str, ToolError] = {}

    def __call__(self, name: str, arguments: Mapping[str, Any], context: ToolContext) -> tuple[Mapping[str, Any], int]:
        self.calls.append((name, arguments, context))
        if name in self.fail:
            raise self.fail[name]
        if name == "get_project":
            return {"project": {"id": str(PROJECT), "projectKey": KEY}, "currentRuntimeProfile": None}, 1
        if name == "list_scans":
            return {"items": self.scans, "page": 0, "size": 20, "totalElements": len(self.scans)}, 1
        if name == "get_project_profile":
            return {"runtimeProfile": None, "answers": self.answers}, 1
        if name == "complete_scan":
            return {"id": arguments["scanId"], "status": arguments["body"]["outcome"]}, 1
        if name == "save_clarification_answers":
            self.answers = list(arguments["body"]["answers"])
            return {"answers": self.answers}, 1
        raise AssertionError(f"unexpected tool {name}")


def completed(text: str = "12 findings.", **data: Any) -> AgentResult:
    return AgentResult(status="COMPLETED", text=text, data=data or {"findings": 12})


@dataclass
class World:
    orchestrator: Orchestrator
    memory: InMemoryConversationMemory
    audit: RecordingAuditLog
    scope_log: InMemoryScopeDecisionLog
    checkpoints: InMemoryCheckpointStore
    consent: FakeConsent
    tools: FakeTools
    guard: FakeGuard
    checker: PassChecker
    agents: AgentSet


def world(
    *,
    guard: FakeGuard | None = None,
    llm: LLMProvider | None = None,
    planner: FakeRunner | None = None,
    answer: FakeRunner | None = None,
    discovery: FakeRunner | None = None,
    topology: FakeRunner | None = None,
    consent: bool = False,
    checker: PassChecker | None = None,
    queue_wait_s: float = 0.2,
    tools: FakeTools | None = None,
) -> World:
    memory = InMemoryConversationMemory(ConversationWindow(max_messages=12, token_budget=3000, chars_per_token=4))
    audit = RecordingAuditLog()
    scope_log = InMemoryScopeDecisionLog(memory)
    checkpoints = InMemoryCheckpointStore(memory)
    agent_set = AgentSet(
        discovery=discovery or FakeRunner(completed("Scan complete.", scanId=SCAN)),
        topology=topology or FakeRunner(completed("Topology recorded.", nodes=3)),
        planner=planner or FakeRunner(completed()),
        answer=answer or FakeRunner(completed("ML-KEM is the FIPS 203 KEM.", intent="algorithm_choice")),
    )
    fake_consent = FakeConsent(consent)
    fake_tools = tools or FakeTools()
    fake_guard = guard or FakeGuard()
    fake_checker = checker or PassChecker()
    orchestrator = Orchestrator(
        conversation=memory,
        audit=audit,
        scope_log=scope_log,
        consent=fake_consent,
        call_tool=fake_tools,
        guard=fake_guard,
        output_checker=fake_checker,
        llm=llm or ScriptedLLM(disabled=True),
        agents=lambda _llm: agent_set,
        workflows=LangGraphWorkflows(checkpoints),
        queue_wait_s=queue_wait_s,
    )
    return World(
        orchestrator,
        memory,
        audit,
        scope_log,
        checkpoints,
        fake_consent,
        fake_tools,
        fake_guard,
        fake_checker,
        agent_set,
    )


def session(w: World, language: str = "en") -> UUID:
    return w.memory.create_session(PROJECT, KEY, language).session.id  # type: ignore[arg-type]


def events(iterator: Any) -> list[tuple[str, Mapping[str, Any]]]:
    return [(event.event, event.data) for event in iterator]


def new_trace() -> str:
    return uuid4().hex


def waits_for(gate: threading.Event) -> Callable[[], None]:
    """A `FakeRunner.before` hook that holds the run until the test releases the gate (at most 5 s)."""

    def wait() -> None:
        gate.wait(5)

    return wait
