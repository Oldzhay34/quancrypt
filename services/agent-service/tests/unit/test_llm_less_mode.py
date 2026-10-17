"""NFR-05: with the language model off (NullProvider behaviour) the inventory (UC1: discovery and topology) and the
plan (UC3) are still produced; only the explanation text carries the fixed 'LLM disabled' note."""

from __future__ import annotations

from uuid import UUID

from src.agents.base_agent import AgentContext, AgentTask, Budget
from src.agents.discovery_agent import DiscoveryAgent
from src.agents.planner_agent import PlannerAgent
from src.agents.topology_agent import TopologyAgent
from tests.support.agent_fakes import FakeClock, RecordingAuditLog, ScriptedKnowledgeBase, ScriptedLLM, new_run
from tests.unit import test_discovery_agent as d
from tests.unit import test_planner_agent as p
from tests.unit import test_topology_agent as t


def _context() -> AgentContext:
    run_id, trace = new_run()
    return AgentContext(trace_id=trace, run_id=run_id, clock=FakeClock())


def test_uc1_the_inventory_and_the_topology_are_produced_without_a_model() -> None:
    audit = RecordingAuditLog()
    llm = ScriptedLLM(disabled=True)
    ctx = _context()

    discovery = DiscoveryAgent(
        d.toolbox([d.finding(), d.finding(symbol="B#m", algorithm_family="UNKNOWN", confidence=0.2)], snippets=1),
        llm,
        audit,
        Budget(40, 8192, 420),
        uncertain_below=0.6,
        llm_confidence=0.5,
    ).run(d.task(), ctx)
    topology = TopologyAgent(t.toolbox(), audit, Budget(8, 0, 360)).run(
        AgentTask(kind="topology", language="en", scan_id=UUID(t.SCAN_ID), root="/workspace"), ctx
    )

    assert discovery.status == "COMPLETED" and topology.status == "COMPLETED"
    assert discovery.data is not None and discovery.data["findingsRecorded"] == 2
    assert topology.data is not None and topology.data["nodes"] == 3
    # One shared ordinal sequence across the agents of the run.
    ordinals = [step.ordinal for step in audit.steps]
    assert ordinals == list(range(1, len(ordinals) + 1))


def test_uc3_the_plan_is_produced_without_a_model_and_says_so() -> None:
    hits = [
        {
            "doc_key": "jep-496",
            "title": "JEP 496",
            "source_url": "https://openjdk.org/jeps/496",
            "source_type": "JEP",
            "version_tag": "JDK24",
            "language": "en",
            "ordinal": 1,
            "text": "ML-KEM",
            "distance": 0.1,
        }
    ]
    agent = PlannerAgent(
        p.toolbox(kb_hits=hits),
        ScriptedLLM(disabled=True),
        ScriptedKnowledgeBase(),
        RecordingAuditLog(),
        Budget(40, 16384, 300),
    )

    result = agent.run(
        AgentTask(kind="plan", language="en", project_id=p.PROJECT_ID, scan_id=UUID(p.SCAN_ID)), _context()
    )

    assert result.status == "COMPLETED"
    assert result.data is not None and result.data["itemCount"] == 1
    assert "[LLM disabled]" in result.data["explanations"][0]["text"]
