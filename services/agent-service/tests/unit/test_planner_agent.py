"""The planner agent (M6, UC3): it asks the five clarification questions when the profile is incomplete, otherwise
scores, creates the plan and explains the items (with sources, or a template note without a model, source or budget)."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from src.agents.base_agent import AgentContext, AgentTask, Budget, TaskKind
from src.agents.planner_agent import PlannerAgent
from src.prompts.templates import CLARIFICATION_QUESTIONS
from src.tools.base_tool import ToolRejectedError
from tests.support.agent_fakes import (
    FakeClock,
    RecordingAuditLog,
    ScriptedKnowledgeBase,
    ScriptedLLM,
    ScriptedToolbox,
    new_run,
)

SCAN_ID = str(uuid4())
PROJECT_ID = uuid4()
FID = str(uuid4())
TOOLS = [
    "list_findings",
    "get_topology",
    "get_project_profile",
    "save_clarification_answers",
    "score_findings",
    "create_plan",
    "get_plan",
    "get_plan_report",
    "kb_search",
    "get_snippet",
]


def profile(answered: list[str]) -> dict[str, Any]:
    answers = []
    for code in answered:
        if code == "DEVICE_HARDWARE_OPENSSL":
            answers.append({"questionCode": code, "optionCode": None, "freeText": "PYNQ-Z2, OpenSSL 3.5"})
        else:
            answers.append({"questionCode": code, "optionCode": "YES", "freeText": None})
    return {
        "runtimeProfile": {
            "sequenceNo": 1,
            "javaVersion": "25",
            "springBootVersion": "4.1.1",
            "recordedAt": "2026-01-01T00:00:00Z",
        },
        "answers": answers,
    }


def findings_page() -> dict[str, Any]:
    return {
        "items": [
            {
                "id": FID,
                "path": "A.java",
                "symbol": "A#m",
                "algorithmFamily": "RSA",
                "usageContext": "TLS_KEY_EXCHANGE",
                "priority": "P1",
                "locationKind": "CODE",
            }
        ],
        "page": 0,
        "size": 200,
        "totalElements": 1,
    }


def topology() -> dict[str, Any]:
    return {"scanId": SCAN_ID, "recordedAt": "2026-01-01T00:00:00Z", "nodes": [], "links": []}


def scores() -> dict[str, Any]:
    return {
        "model_id": "rule_baseline_v1",
        "scores": [
            {"findingId": FID, "riskClass": "MEDIUM", "riskScore": 0.475, "rule": "p1_off_path", "riskFactors": []}
        ],
    }


def plan_page() -> dict[str, Any]:
    return {
        "plan": {"id": str(uuid4()), "scanId": SCAN_ID, "createdAt": "2026-01-01T00:00:00Z", "itemCount": 1},
        "items": [
            {
                "id": str(uuid4()),
                "findingId": FID,
                "strategy": "HYBRID_TLS_KEX",
                "effort": "M",
                "riskScore": 0.475,
                "riskClass": "MEDIUM",
                "state": "PLANNED",
                "version": 0,
                "riskFactors": [],
            }
        ],
        "page": 0,
        "size": 200,
        "totalElements": 1,
    }


def toolbox(*, answered: list[str] | None = None, kb_hits: list[dict[str, Any]] | None = None) -> ScriptedToolbox:
    all_answered = answered if answered is not None else list(CLARIFICATION_QUESTIONS)
    return ScriptedToolbox(
        TOOLS,
        {
            "get_project_profile": [profile(all_answered)],
            "list_findings": [findings_page()],
            "get_topology": [topology()],
            "score_findings": [scores()],
            "create_plan": [
                {"id": str(uuid4()), "scanId": SCAN_ID, "createdAt": "2026-01-01T00:00:00Z", "itemCount": 1}
            ],
            # No plan yet (404), then the plan create_plan made (D-252c).
            "get_plan": [ToolRejectedError(404, "not-found"), plan_page()],
            "kb_search": [{"hits": kb_hits if kb_hits is not None else []}],
        },
    )


def run(box: ScriptedToolbox, llm: ScriptedLLM, *, kind: TaskKind = "plan", steps: int = 40) -> Any:
    run_id, trace = new_run()
    ctx = AgentContext(trace_id=trace, run_id=run_id, clock=FakeClock())
    agent = PlannerAgent(box, llm, ScriptedKnowledgeBase(), RecordingAuditLog(), Budget(steps, 16384, 300))
    task = AgentTask(kind=kind, language="en", project_id=PROJECT_ID, scan_id=UUID(SCAN_ID))
    return agent.run(task, ctx)


def test_an_incomplete_profile_asks_exactly_the_missing_questions() -> None:
    box = toolbox(answered=["TLS_TERMINATION", "JDK_UPGRADE_POSSIBLE"])

    result = run(box, ScriptedLLM())

    assert result.status == "CLARIFICATION_REQUIRED"
    assert result.clarifications == ("HYBRID_INCAPABLE_PARTNERS", "COMPLIANCE_REQUIREMENT", "DEVICE_HARDWARE_OPENSSL")
    assert [name for name, _ in box.calls] == ["get_project_profile"]  # nothing else runs


def test_a_full_profile_runs_the_planning_tools_in_order() -> None:
    box = toolbox(
        kb_hits=[
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
    )
    llm = ScriptedLLM(["Because RSA key exchange is quantum-vulnerable."])

    result = run(box, llm)

    assert result.status == "COMPLETED"
    assert [name for name, _ in box.calls] == [
        "get_project_profile",
        "list_findings",
        "get_topology",
        "score_findings",
        "get_plan",
        "create_plan",
        "get_plan",
        "kb_search",
    ]
    assert result.data is not None and result.data["itemCount"] == 1


def test_an_explanation_carries_a_knowledge_base_source() -> None:
    box = toolbox(
        kb_hits=[
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
    )
    llm = ScriptedLLM(["Hybrid key exchange protects today's traffic."])

    result = run(box, llm)

    assert result.evidence and result.evidence[0].kind == "knowledge_base"
    assert result.evidence[0].reference == "https://openjdk.org/jeps/496"
    assert result.evidence[0].source_version == "JDK24"
    explanation = result.data["explanations"][0]
    assert explanation["note"] is None and explanation["sources"] == ["https://openjdk.org/jeps/496"]


def test_without_a_knowledge_base_source_the_note_says_so() -> None:
    box = toolbox(kb_hits=[])  # no hits
    result = run(box, ScriptedLLM())

    explanation = result.data["explanations"][0]
    assert explanation["note"] == "no_source"
    assert "expert review is advised" in explanation["text"]


def test_without_a_model_the_explanation_is_a_template_note() -> None:
    box = toolbox(
        kb_hits=[
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
    )

    result = run(box, ScriptedLLM(disabled=True))

    explanation = result.data["explanations"][0]
    assert explanation["note"] == "llm_off"
    assert "[LLM disabled]" in explanation["text"]


def test_a_tight_budget_leaves_the_plan_but_marks_the_explanation() -> None:
    box = toolbox(kb_hits=[])
    # 7 steps: profile, list_findings, get_topology, score, get_plan (404), create_plan, get_plan -> none left for an
    # explanation.
    result = run(box, ScriptedLLM(), steps=7)

    assert result.status == "COMPLETED"
    explanation = result.data["explanations"][0]
    assert explanation["note"] == "budget"


def test_an_inventory_task_is_read_only() -> None:
    box = toolbox()
    result = run(box, ScriptedLLM(), kind="inventory")

    assert result.status == "COMPLETED"
    names = [name for name, _ in box.calls]
    assert "create_plan" not in names and "get_plan" not in names
    assert names == ["list_findings", "get_topology", "score_findings"]
    assert result.data is not None and result.data["findings"] == 1


def test_a_model_failure_leaves_the_plan_and_marks_the_explanation() -> None:
    from src.llm.provider import LLMUnavailableError

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

    result = run(toolbox(kb_hits=hits), ScriptedLLM([LLMUnavailableError("down")]))

    assert result.status == "COMPLETED"
    assert result.data["itemCount"] == 1
    assert result.data["explanations"][0]["note"] == "llm_off"


def test_running_out_of_tokens_keeps_the_plan_result() -> None:
    from src.llm.provider import GenerationResult, TokenUsage

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
    llm = ScriptedLLM([GenerationResult(text="x", usage=TokenUsage(20000, 5), model="fake")])

    result = run(toolbox(kb_hits=hits), llm)

    assert result.status == "COMPLETED"
    assert result.data["explanations"][0]["note"] == "budget"
