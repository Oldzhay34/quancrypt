"""The agent base (Template Method): every agent runs the same lifecycle and records every step (P4.5).

`run(task, context)` is `@final` and calls `gather_context`, `plan`, `act`, `verify`, `report` in that order. Each
lifecycle step is written to `AuditLog` with its duration, token counts and the tool calls it made; a step that runs out
of budget is written as `BUDGET_EXCEEDED` and the agent stops, a tool failure as `FAILED`. The run itself (start and
finish) belongs to the workflow layer (P4.6); an agent only records its steps under the run id it is given.

An agent takes only Protocols in its constructor (agent-service-layout section 3): a `Toolbox` (its own allow-list,
`ToolRegistry.scoped`), an `LLMProvider`, an `AuditLog` and, when it needs one, a `KnowledgeBase`. It never imports a
concrete adapter (lint-imports). The subclass fills a typed `AgentState` across the steps and `report` turns it into an
`AgentResult`.

A step for the budget (D-248) is one tool call or one LLM call; the five lifecycle phases are the audit steps. The
budget bounds the number of calls, the tokens and the elapsed time; `RunMeter` enforces all three.
"""

from __future__ import annotations

import itertools
import logging
import typing
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from src.llm.provider import ChatMessage, GenerationRequest, GenerationResult, LLMError, LLMProvider
from src.memory.short_term import (
    AgentCode,
    AuditLog,
    Clock,
    StepName,
    StepRecord,
    StepStatus,
    ToolCallRecord,
)
from src.tools.base_tool import ToolContext, ToolError, ToolResult

_LOG = logging.getLogger("src.agents")

Language = Literal["tr", "en"]
TaskKind = Literal["initial_scan", "topology", "plan", "inventory", "answer"]
ResultStatus = Literal["COMPLETED", "FAILED", "BUDGET_EXCEEDED", "CLARIFICATION_REQUIRED"]
EvidenceKind = Literal["code_location", "tool_call", "knowledge_base"]

# The lifecycle phases in order; `report` is the last and builds the result.
_PHASES: tuple[StepName, ...] = ("GATHER_CONTEXT", "PLAN", "ACT", "VERIFY", "REPORT")


# ---- values ----


@dataclass(frozen=True)
class AgentTask:
    """What an agent is asked to do. Which fields matter depends on `kind` (the agent states its needs)."""

    kind: TaskKind
    language: Language = "tr"
    project_id: UUID | None = None
    scan_id: UUID | None = None
    root: str | None = None
    question: str | None = None


@dataclass
class AgentContext:
    """Shared across the agents of one run (P4.6): the trace id, the run id and the step ordinal counter.

    The ordinal is the same sequence for every agent in the run (`uq_agent_step_order`), so a supervisor and the agent
    it dispatches to write consecutive step numbers.
    """

    trace_id: str
    run_id: UUID
    clock: Clock = field(default=lambda: datetime.now(UTC))
    _counter: Iterator[int] = field(default_factory=lambda: itertools.count(1), repr=False)

    def next_ordinal(self) -> int:
        return next(self._counter)


@dataclass(frozen=True)
class Evidence:
    """A citation an answer carries (contract names, D-248c). `source_version` only for knowledge-base evidence."""

    kind: EvidenceKind
    reference: str
    source_version: str | None = None


@dataclass(frozen=True)
class AgentResult:
    status: ResultStatus
    text: str = ""
    data: Mapping[str, Any] | None = None
    evidence: tuple[Evidence, ...] = ()
    # Missing clarification question codes (CLARIFICATION_REQUIRED only).
    clarifications: tuple[str, ...] = ()
    # The tool error code when the status is FAILED.
    error_code: str | None = None


# ---- budget ----


class BudgetExceeded(Exception):
    """A call would pass the step, token or time budget. The agent stops and reports `BUDGET_EXCEEDED`."""

    def __init__(self, dimension: Literal["steps", "tokens", "time"]) -> None:
        super().__init__(f"the {dimension} budget is exhausted")
        self.dimension = dimension


@dataclass(frozen=True)
class Budget:
    max_steps: int
    max_tokens: int
    timeout_s: int


class RunMeter:
    """Counts the calls, tokens and time of one agent run and reads the toolbox journal by step (P4.5)."""

    def __init__(self, budget: Budget, clock: Clock, toolbox: Toolbox | None) -> None:
        self._budget = budget
        self._clock = clock
        self._started = clock()
        self._toolbox = toolbox
        self._steps = 0
        self._tokens = 0
        self._cursor = 0
        self._phase_prompt = 0
        self._phase_completion = 0

    def before_call(self) -> None:
        """Count one call (a tool or an LLM call) and check the step and time budgets. Raises `BudgetExceeded`."""
        if self._steps >= self._budget.max_steps:
            raise BudgetExceeded("steps")
        if self._elapsed_s() > self._budget.timeout_s:
            raise BudgetExceeded("time")
        self._steps += 1

    def add_tokens(self, prompt_tokens: int, completion_tokens: int) -> None:
        self._phase_prompt += prompt_tokens
        self._phase_completion += completion_tokens
        self._tokens += prompt_tokens + completion_tokens
        if self._tokens > self._budget.max_tokens:
            raise BudgetExceeded("tokens")

    def start_phase(self) -> None:
        self._phase_prompt = 0
        self._phase_completion = 0

    def phase_tokens(self) -> tuple[int, int]:
        return self._phase_prompt, self._phase_completion

    def new_tool_calls(self) -> tuple[ToolCallRecord, ...]:
        """The tool calls journaled since the previous phase (the step's own calls)."""
        if self._toolbox is None:
            return ()
        records = self._toolbox.records()
        fresh = records[self._cursor :]
        self._cursor = len(records)
        return fresh

    def remaining_steps(self) -> int:
        return max(0, self._budget.max_steps - self._steps)

    def remaining_tokens(self) -> int:
        return max(0, self._budget.max_tokens - self._tokens)

    def time_left_share(self) -> float:
        """The share of the time budget still left (0 when spent)."""
        return max(0.0, 1 - self._elapsed_s() / self._budget.timeout_s)

    def out_of_time(self) -> bool:
        return self._elapsed_s() > self._budget.timeout_s

    def _elapsed_s(self) -> float:
        return (self._clock() - self._started).total_seconds()


# ---- state ----


@dataclass
class AgentState:
    """The subclass workspace carried across the lifecycle steps. Subclasses add their own typed fields."""

    meter: RunMeter
    task: AgentTask
    result: AgentResult | None = None
    # When a step sets this, the remaining steps (including report) are skipped; `result` must already be set.
    short_circuit: bool = False
    evidence: list[Evidence] = field(default_factory=list)


# ---- protocols ----


class Toolbox(typing.Protocol):
    """An agent's own tools (`ToolRegistry.scoped`): it can see only its allow-list and its own call journal."""

    def names(self) -> frozenset[str]: ...

    def invoke(self, name: str, arguments: Mapping[str, Any], context: ToolContext) -> ToolResult: ...

    def records(self) -> tuple[ToolCallRecord, ...]: ...


class AgentRunner(typing.Protocol):
    """One agent as the supervisor sees it (Mediator, D-249): it runs a task and returns a result."""

    def run(self, task: AgentTask, context: AgentContext) -> AgentResult: ...


class BaseAgent[S: AgentState](ABC):
    def __init__(
        self,
        agent_code: AgentCode,
        budget: Budget,
        audit: AuditLog,
        toolbox: Toolbox | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        self._agent_code = agent_code
        self._budget = budget
        self._audit = audit
        self._toolbox = toolbox
        self._llm = llm

    @property
    def agent_code(self) -> AgentCode:
        return self._agent_code

    @typing.final
    def run(self, task: AgentTask, context: AgentContext) -> AgentResult:
        """The Template Method: the five lifecycle steps, each audited. Subclasses cannot override it."""
        meter = RunMeter(self._budget, context.clock, self._toolbox)
        state = self._new_state(task, meter)
        status: StepStatus = "SUCCEEDED"
        error_code: str | None = None
        final_status: ResultStatus = "COMPLETED"

        for step_name in _PHASES:
            if state.short_circuit:
                break
            meter.start_phase()
            started = context.clock()
            try:
                self._phase(step_name)(context, state)
            except BudgetExceeded:
                status, final_status = "BUDGET_EXCEEDED", "BUDGET_EXCEEDED"
            except ToolError as exc:
                status, final_status, error_code = "FAILED", "FAILED", exc.code
                _LOG.warning("agent %s failed in %s (%s)", self._agent_code, step_name, exc.code)
            except LLMError as exc:
                status, final_status, error_code = "FAILED", "FAILED", "llm-unavailable"
                _LOG.warning("agent %s failed in %s (%s)", self._agent_code, step_name, type(exc).__name__)
            self._write_step(context, state, meter, step_name, status, started)
            if status != "SUCCEEDED":
                break

        if final_status == "COMPLETED":
            if state.result is None:  # report must set it; a missing result is a programming error
                raise RuntimeError(f"agent {self._agent_code} produced no result")
            return state.result
        self._cleanup_after_failure(context, state, meter)
        partial = state.result
        return AgentResult(
            status=final_status,
            text=partial.text if partial else "",
            data=partial.data if partial else self._partial_data(state),
            evidence=tuple(state.evidence),
            error_code=error_code,
        )

    def _cleanup_after_failure(self, context: AgentContext, state: S, meter: RunMeter) -> None:
        """Run the subclass cleanup (outside the budget) and audit it as a closing REPORT step if it did anything."""
        meter.start_phase()
        started = context.clock()
        if self._on_failure(context, state):
            self._write_step(context, state, meter, "REPORT", "FAILED", started)

    def _phase(self, step_name: StepName) -> Callable[[AgentContext, S], None]:
        if step_name == "GATHER_CONTEXT":
            return self.gather_context
        if step_name == "PLAN":
            return self.plan
        if step_name == "ACT":
            return self.act
        if step_name == "VERIFY":
            return self.verify
        return self._report_phase

    def _report_phase(self, context: AgentContext, state: S) -> None:
        state.result = self.report(context, state)

    def _write_step(
        self,
        context: AgentContext,
        state: S,
        meter: RunMeter,
        step_name: StepName,
        status: StepStatus,
        started: datetime,
    ) -> None:
        prompt_tokens, completion_tokens = meter.phase_tokens()
        duration_ms = max(0, round((context.clock() - started).total_seconds() * 1000))
        self._audit.record_step(
            StepRecord(
                run_id=context.run_id,
                ordinal=context.next_ordinal(),
                step_name=step_name,
                agent_code=self._agent_code,
                status=status,
                duration_ms=duration_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                started_at=started,
                tool_calls=meter.new_tool_calls(),
            )
        )

    # ---- helpers for subclasses ----

    def _call_tool(self, state: S, name: str, arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        """Count the call against the budget, then invoke the tool. A `ToolError` is already journaled by the box."""
        if self._toolbox is None:
            raise RuntimeError(f"agent {self._agent_code} has no toolbox")
        state.meter.before_call()
        return self._toolbox.invoke(name, arguments, context)

    def _generate(
        self,
        state: S,
        messages: Sequence[ChatMessage],
        *,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> GenerationResult:
        """Count the call, generate, and add the tokens to the budget (and the step)."""
        if self._llm is None:
            raise RuntimeError(f"agent {self._agent_code} has no language model")
        state.meter.before_call()
        result = self._llm.generate(GenerationRequest(tuple(messages), temperature=temperature, max_tokens=max_tokens))
        state.meter.add_tokens(result.usage.prompt_tokens, result.usage.completion_tokens)
        return result

    def _context(self, context: AgentContext) -> ToolContext:
        return ToolContext(trace_id=context.trace_id)

    def _call_tool_unbudgeted(self, name: str, arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        """A cleanup call that must run even when the budget is spent (for example closing a scan as FAILED)."""
        if self._toolbox is None:
            raise RuntimeError(f"agent {self._agent_code} has no toolbox")
        return self._toolbox.invoke(name, arguments, context)

    # ---- template steps ----

    def _on_failure(self, context: AgentContext, state: S) -> bool:
        """Undo what a failed run left open; return True if a tool was called. Default hook: nothing to do."""
        return False

    def _partial_data(self, state: S) -> Mapping[str, Any] | None:
        """What a failed or budget-stopped run still tells its caller (for example the scan id). Default: nothing."""
        return None

    @abstractmethod
    def _new_state(self, task: AgentTask, meter: RunMeter) -> S: ...

    def gather_context(self, context: AgentContext, state: S) -> None:
        """Read what the task needs (profile, findings, topology). Default hook: nothing to do."""
        return

    def plan(self, context: AgentContext, state: S) -> None:
        """Decide what to do. Default hook: nothing to do."""
        return

    def act(self, context: AgentContext, state: S) -> None:
        """Do the work (tool calls, LLM calls). Default hook: nothing to do."""
        return

    def verify(self, context: AgentContext, state: S) -> None:
        """Check the outcome. Default hook: nothing to do."""
        return

    @abstractmethod
    def report(self, context: AgentContext, state: S) -> AgentResult:
        """Turn the state into the agent's result. Always runs unless an earlier step short-circuited."""


def new_run_id() -> UUID:
    return uuid4()
