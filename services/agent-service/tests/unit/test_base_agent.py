"""The agent base (Template Method): the five steps run in order, each is audited with its tool calls, the budget stops
the agent, and a tool failure reports FAILED. `run` cannot be overridden."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from src.agents.base_agent import (
    AgentContext,
    AgentResult,
    AgentState,
    AgentTask,
    BaseAgent,
    Budget,
    RunMeter,
)
from src.llm.provider import ChatMessage
from src.tools.base_tool import ToolContext
from tests.support.agent_fakes import FakeClock, RecordingAuditLog, ScriptedLLM, ScriptedToolbox, new_run, tool_error

TASK = AgentTask(kind="initial_scan", language="en", root="/workspace")


@dataclass
class ProbeState(AgentState):
    seen: list[str] = field(default_factory=list)


class ProbeAgent(BaseAgent[ProbeState]):
    """Records the phase order; each phase may call a tool and/or the model, driven by the constructor."""

    def __init__(
        self,
        toolbox: ScriptedToolbox | None,
        llm: ScriptedLLM | None,
        audit: RecordingAuditLog,
        budget: Budget,
        *,
        actions: dict[str, Callable[[ProbeAgent, AgentContext, ProbeState], None]] | None = None,
    ) -> None:
        super().__init__("DISCOVERY", budget, audit, toolbox=toolbox, llm=llm)
        self._actions = actions or {}

    def _new_state(self, task: AgentTask, meter: RunMeter) -> ProbeState:
        return ProbeState(meter=meter, task=task)

    def _step(self, name: str, context: AgentContext, state: ProbeState) -> None:
        state.seen.append(name)
        action = self._actions.get(name)
        if action is not None:
            action(self, context, state)

    def gather_context(self, context: AgentContext, state: ProbeState) -> None:
        self._step("gather", context, state)

    def plan(self, context: AgentContext, state: ProbeState) -> None:
        self._step("plan", context, state)

    def act(self, context: AgentContext, state: ProbeState) -> None:
        self._step("act", context, state)

    def verify(self, context: AgentContext, state: ProbeState) -> None:
        self._step("verify", context, state)

    def report(self, context: AgentContext, state: ProbeState) -> AgentResult:
        state.seen.append("report")
        return AgentResult(status="COMPLETED", text="done", data={"seen": list(state.seen)})

    def call(self, context: AgentContext, state: ProbeState, name: str) -> None:
        self._call_tool(state, name, {}, ToolContext(trace_id=context.trace_id))

    def ask(self, context: AgentContext, state: ProbeState) -> None:
        self._generate(state, (ChatMessage(role="user", content="hi"),), temperature=0, max_tokens=8)


def context() -> AgentContext:
    run_id, trace = new_run()
    return AgentContext(trace_id=trace, run_id=run_id, clock=FakeClock())


def budget(steps: int = 20, tokens: int = 1000, timeout: int = 60) -> Budget:
    return Budget(max_steps=steps, max_tokens=tokens, timeout_s=timeout)


def test_the_five_steps_run_in_order_and_each_is_audited() -> None:
    audit = RecordingAuditLog()
    agent = ProbeAgent(None, None, audit, budget())

    result = agent.run(TASK, context())

    assert result.status == "COMPLETED"
    assert result.data == {"seen": ["gather", "plan", "act", "verify", "report"]}
    assert [step.step_name for step in audit.steps] == [
        "GATHER_CONTEXT",
        "PLAN",
        "ACT",
        "VERIFY",
        "REPORT",
    ]
    assert [step.ordinal for step in audit.steps] == [1, 2, 3, 4, 5]
    assert all(step.agent_code == "DISCOVERY" and step.status == "SUCCEEDED" for step in audit.steps)


def test_run_is_final_and_cannot_be_overridden() -> None:
    assert getattr(BaseAgent.run, "__final__", False) is True


def test_each_step_records_only_its_own_tool_calls() -> None:
    audit = RecordingAuditLog()
    toolbox = ScriptedToolbox(["start_scan", "complete_scan"], {"start_scan": [{}], "complete_scan": [{}]})
    actions = {
        "act": lambda self, ctx, st: self.call(ctx, st, "start_scan"),
        "verify": lambda self, ctx, st: self.call(ctx, st, "complete_scan"),
    }
    agent = ProbeAgent(toolbox, None, audit, budget(), actions=actions)

    agent.run(TASK, context())

    by_name = {step.step_name: step for step in audit.steps}
    assert [call.tool_code for call in by_name["ACT"].tool_calls] == ["CORE"]
    assert [call.tool_code for call in by_name["VERIFY"].tool_calls] == ["CORE"]
    assert by_name["GATHER_CONTEXT"].tool_calls == ()


def test_a_step_counts_its_llm_tokens() -> None:
    audit = RecordingAuditLog()
    llm = ScriptedLLM(["one two three"])
    agent = ProbeAgent(None, llm, audit, budget(), actions={"plan": lambda self, ctx, st: self.ask(ctx, st)})

    agent.run(TASK, context())

    plan_step = next(step for step in audit.steps if step.step_name == "PLAN")
    assert (plan_step.prompt_tokens, plan_step.completion_tokens) == (3, 2)


def test_the_step_budget_stops_the_agent() -> None:
    audit = RecordingAuditLog()
    toolbox = ScriptedToolbox(["start_scan"], {"start_scan": [{}, {}, {}]})

    def three_calls(self: ProbeAgent, ctx: AgentContext, st: ProbeState) -> None:
        for _ in range(3):
            self.call(ctx, st, "start_scan")

    agent = ProbeAgent(toolbox, None, audit, budget(steps=2), actions={"act": three_calls})

    result = agent.run(TASK, context())

    assert result.status == "BUDGET_EXCEEDED"
    assert audit.steps[-1].step_name == "ACT"
    assert audit.steps[-1].status == "BUDGET_EXCEEDED"
    assert not any(step.step_name == "REPORT" for step in audit.steps)


def test_the_token_budget_stops_the_agent() -> None:
    audit = RecordingAuditLog()
    llm = ScriptedLLM(["a b c d e"])  # 3 prompt + 2 completion tokens, over a budget of 4
    agent = ProbeAgent(None, llm, audit, budget(tokens=4), actions={"plan": lambda self, ctx, st: self.ask(ctx, st)})

    result = agent.run(TASK, context())

    assert result.status == "BUDGET_EXCEEDED"
    assert audit.steps[-1].step_name == "PLAN"


def test_the_time_budget_stops_the_agent() -> None:
    audit = RecordingAuditLog()
    toolbox = ScriptedToolbox(["start_scan"], {"start_scan": [{}, {}]})
    run_id, trace = new_run()
    # The clock jumps 100 s each read, so the second call is past a 60 s budget.
    ctx = AgentContext(trace_id=trace, run_id=run_id, clock=FakeClock(step_seconds=100))

    def two_calls(self: ProbeAgent, c: AgentContext, st: ProbeState) -> None:
        self.call(c, st, "start_scan")
        self.call(c, st, "start_scan")

    agent = ProbeAgent(toolbox, None, audit, budget(timeout=60), actions={"act": two_calls})

    result = agent.run(TASK, ctx)

    assert result.status == "BUDGET_EXCEEDED"


def test_a_tool_failure_reports_failed_with_its_code() -> None:
    audit = RecordingAuditLog()
    toolbox = ScriptedToolbox(["start_scan"], errors={"start_scan": tool_error("down")})
    agent = ProbeAgent(
        toolbox, None, audit, budget(), actions={"act": lambda self, ctx, st: self.call(ctx, st, "start_scan")}
    )

    result = agent.run(TASK, context())

    assert result.status == "FAILED"
    assert result.error_code == "tool-error"
    assert audit.steps[-1].step_name == "ACT"
    assert audit.steps[-1].status == "FAILED"


def test_a_model_error_reports_failed_without_leaking_the_exception() -> None:
    from src.llm.provider import LLMUnavailableError

    audit = RecordingAuditLog()
    llm = ScriptedLLM([LLMUnavailableError("down")])
    agent = ProbeAgent(None, llm, audit, budget(), actions={"plan": lambda self, ctx, st: self.ask(ctx, st)})

    result = agent.run(TASK, context())

    assert result.status == "FAILED"
    assert result.error_code == "llm-unavailable"
    assert audit.steps[-1].step_name == "PLAN" and audit.steps[-1].status == "FAILED"
