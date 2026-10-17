"""The supervisor (Mediator): it reads the intent (model, else keyword fallback), dispatches inventory and
risk-priority to the planner and answers other intents from the knowledge base, with a fixed "not sure" when there is
no source."""

from __future__ import annotations

from uuid import UUID, uuid4

from src.agents.base_agent import AgentContext, AgentResult, AgentTask, Budget
from src.agents.supervisor_agent import SupervisorAgent
from src.memory.long_term import KnowledgeUnavailableError
from src.prompts.system_prompts import UNSURE_EN
from tests.support.agent_fakes import FakeClock, RecordingAuditLog, ScriptedKnowledgeBase, ScriptedLLM, hit, new_run

PROJECT_ID = uuid4()
SCAN_ID = str(uuid4())


class FakeRunner:
    def __init__(self, result: AgentResult) -> None:
        self._result = result
        self.tasks: list[AgentTask] = []

    def run(self, task: AgentTask, context: AgentContext) -> AgentResult:
        self.tasks.append(task)
        return self._result


def context() -> AgentContext:
    run_id, trace = new_run()
    return AgentContext(trace_id=trace, run_id=run_id, clock=FakeClock())


def supervisor(llm: ScriptedLLM, knowledge: ScriptedKnowledgeBase, runner: FakeRunner | None = None) -> SupervisorAgent:
    runners = {"planner": runner} if runner is not None else {}
    return SupervisorAgent(llm, knowledge, RecordingAuditLog(), Budget(6, 2048, 120), runners)


def ask(question: str) -> AgentTask:
    return AgentTask(kind="answer", language="en", project_id=PROJECT_ID, scan_id=UUID(SCAN_ID), question=question)


def test_an_inventory_intent_is_dispatched_to_the_planner() -> None:
    sub = AgentResult(status="COMPLETED", text="12 findings.", data={"findings": 12})
    runner = FakeRunner(sub)
    agent = supervisor(ScriptedLLM(["inventory"]), ScriptedKnowledgeBase(), runner)

    result = agent.run(ask("What cryptography does my project use?"), context())

    assert [task.kind for task in runner.tasks] == ["inventory"]
    assert runner.tasks[0].project_id == PROJECT_ID and runner.tasks[0].scan_id == UUID(SCAN_ID)
    assert result.text == "12 findings."
    assert result.data is not None and result.data["intent"] == "inventory"


def test_a_knowledge_intent_is_answered_from_the_knowledge_base_with_a_source() -> None:
    knowledge = ScriptedKnowledgeBase(
        [(hit("fips-203", "FIPS 203", "2024", "ML-KEM standard", url="https://doi.org/10.6028/NIST.FIPS.203"),)]
    )
    agent = supervisor(ScriptedLLM(["algorithm_choice", "Use ML-KEM for key establishment."]), knowledge)

    result = agent.run(ask("Which post-quantum algorithm should I choose?"), context())

    assert result.text == "Use ML-KEM for key establishment."
    assert result.evidence and result.evidence[0].reference == "https://doi.org/10.6028/NIST.FIPS.203"
    assert result.evidence[0].source_version == "2024"


def test_no_source_gives_the_fixed_not_sure_answer() -> None:
    agent = supervisor(ScriptedLLM(["qkd"]), ScriptedKnowledgeBase([()]))

    result = agent.run(ask("Can I use QKD in the project?"), context())

    assert result.text == UNSURE_EN
    assert result.evidence == ()


def test_an_unavailable_knowledge_base_gives_the_not_sure_answer() -> None:
    agent = supervisor(ScriptedLLM(["qkd"]), ScriptedKnowledgeBase([KnowledgeUnavailableError("no embeddings")]))

    result = agent.run(ask("Can I use QKD?"), context())

    assert result.text == UNSURE_EN


def test_an_out_of_list_intent_becomes_unknown() -> None:
    agent = supervisor(ScriptedLLM(["banana"]), ScriptedKnowledgeBase([()]))

    result = agent.run(ask("Tell me a joke."), context())

    assert result.data is not None and result.data["intent"] == "unknown"


def test_without_a_model_the_intent_falls_back_to_keywords() -> None:
    sub = AgentResult(status="COMPLETED", text="priorities", data={})
    runner = FakeRunner(sub)
    agent = supervisor(ScriptedLLM(disabled=True), ScriptedKnowledgeBase(), runner)

    result = agent.run(ask("Which findings should I fix first?"), context())

    assert result.data is not None and result.data["intent"] == "risk_priority"
    assert [task.kind for task in runner.tasks] == ["inventory"]  # risk_priority dispatches read-only to the planner
