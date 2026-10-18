"""The discovery agent (M4, UC1): it scans, classifies the uncertain findings with the model, recomputes their
priority and records the inventory; without a model the inventory is still recorded."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from src.agents.base_agent import AgentContext, AgentTask, Budget
from src.agents.discovery_agent import DiscoveryAgent
from tests.support.agent_fakes import FakeClock, RecordingAuditLog, ScriptedLLM, ScriptedToolbox, new_run

SCAN_ID = str(uuid4())
PROJECT_ID = uuid4()
CBOM = {"bomFormat": "CycloneDX", "specVersion": "1.6", "components": []}
TOOLS = ["analyze_crypto", "get_snippet", "start_scan", "record_findings", "record_scan_artifact", "complete_scan"]


def finding(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "file": "src/main/java/A.java",
        "line_start": 10,
        "line_end": 10,
        "raw_name": "RSA",
        "symbol": "A#m",
        "algorithm_family": "RSA",
        "mode": None,
        "padding": None,
        "hash": None,
        "key_size_bits": 2048,
        "usage_context": "SIGNATURE",
        "location_kind": "CODE",
        "priority": "P2",
        "library": "JCA",
        "confidence": 0.9,
        "detector_id": "java.jca",
    }
    base.update(overrides)
    return base


def analysis(findings: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "analysis_id": str(uuid4()),
        "project_type": "GRADLE",
        "runtime": {"java_version": "25", "spring_boot_version": "4.1.1"},
        "findings": findings,
        "cbom": CBOM,
        "stats": {"files_scanned": 1, "findings_total": len(findings), "duration_ms": 1},
    }


def snippet() -> dict[str, Any]:
    return {"path": "src/main/java/A.java", "lines": [{"number": 10, "text": "Cipher.getInstance(x)"}]}


def toolbox(findings: list[dict[str, Any]], *, snippets: int = 0) -> ScriptedToolbox:
    return ScriptedToolbox(
        TOOLS,
        {
            "start_scan": [{"id": SCAN_ID}],
            "analyze_crypto": [analysis(findings)],
            "get_snippet": [snippet() for _ in range(snippets)],
            "record_findings": [{"createdCount": len(findings), "existingCount": 0, "createdIds": []}],
            "record_scan_artifact": [
                {
                    "scanId": SCAN_ID,
                    "contentType": "application/json",
                    "sha256": "0" * 64,
                    "createdAt": "2026-01-01T00:00:00Z",
                }
            ],
            "complete_scan": [{"id": SCAN_ID, "status": "COMPLETED"}],
        },
    )


def context() -> AgentContext:
    run_id, trace = new_run()
    return AgentContext(trace_id=trace, run_id=run_id, clock=FakeClock())


def agent(box: ScriptedToolbox, llm: ScriptedLLM, audit: RecordingAuditLog, *, steps: int = 40) -> DiscoveryAgent:
    return DiscoveryAgent(box, llm, audit, Budget(steps, 8192, 420), uncertain_below=0.6, llm_confidence=0.5)


def task() -> AgentTask:
    return AgentTask(kind="initial_scan", language="en", project_id=PROJECT_ID, root="/workspace")


def test_with_no_uncertain_findings_the_scan_runs_without_the_model() -> None:
    box = toolbox([finding(), finding(symbol="B#m")])
    llm = ScriptedLLM()
    audit = RecordingAuditLog()

    result = agent(box, llm, audit).run(task(), context())

    assert result.status == "COMPLETED"
    assert [name for name, _ in box.calls] == [
        "start_scan",
        "analyze_crypto",
        "record_findings",
        "record_scan_artifact",
    ]  # a successful scan stays RUNNING for the topology; the workflow completes it (D-256)
    assert result.data is not None and result.data["findingsRecorded"] == 2
    assert llm.requests == []


def test_an_uncertain_finding_is_classified_and_its_priority_recomputed() -> None:
    # UNKNOWN family in a TLS key-exchange context: the model picks RSA, the port derives P1.
    box = toolbox(
        [finding(algorithm_family="UNKNOWN", usage_context="TLS_KEY_EXCHANGE", confidence=0.3, priority="P2")],
        snippets=1,
    )
    llm = ScriptedLLM(["RSA"])
    audit = RecordingAuditLog()

    result = agent(box, llm, audit).run(task(), context())

    recorded = next(args for name, args in box.calls if name == "record_findings")
    [sent] = recorded["body"]["findings"]
    assert (sent["algorithmFamily"], sent["priority"], sent["classifiedBy"], sent["confidence"]) == (
        "RSA",
        "P1",
        "LLM",
        0.5,
    )
    assert result.data is not None and result.data["classifiedByLlm"] == 1


def test_the_snippet_reaches_the_model_inside_project_data_tags() -> None:
    box = toolbox([finding(algorithm_family="UNKNOWN", confidence=0.2)], snippets=1)
    llm = ScriptedLLM(["RSA"])
    agent(box, llm, RecordingAuditLog()).run(task(), context())

    [request] = llm.requests
    user = request.messages[-1].content
    assert user.startswith('<project_data source="src/main/java/A.java:10">')
    assert user.rstrip().endswith("</project_data>")


def test_an_out_of_list_answer_is_rejected_and_the_finding_stays_unknown() -> None:
    box = toolbox([finding(algorithm_family="UNKNOWN", confidence=0.2, priority="P2")], snippets=1)
    llm = ScriptedLLM(["definitely-rsa"])
    audit = RecordingAuditLog()

    result = agent(box, llm, audit).run(task(), context())

    [sent] = next(args for name, args in box.calls if name == "record_findings")["body"]["findings"]
    assert (sent["algorithmFamily"], sent["classifiedBy"]) == ("UNKNOWN", "STATIC")
    assert result.data is not None and result.data["classifiedByLlm"] == 0


def test_a_non_migration_family_leaves_the_finding_unchanged() -> None:
    box = toolbox([finding(algorithm_family="UNKNOWN", confidence=0.2, priority="P2")], snippets=1)
    llm = ScriptedLLM(["AES"])  # needs no migration: NotApplicable, finding stays as it was

    agent(box, llm, RecordingAuditLog()).run(task(), context())

    [sent] = next(args for name, args in box.calls if name == "record_findings")["body"]["findings"]
    assert (sent["algorithmFamily"], sent["classifiedBy"]) == ("UNKNOWN", "STATIC")


def test_without_a_model_the_inventory_is_still_recorded() -> None:
    box = toolbox([finding(algorithm_family="UNKNOWN", confidence=0.2), finding(symbol="B#m")], snippets=1)
    llm = ScriptedLLM(disabled=True)
    audit = RecordingAuditLog()

    result = agent(box, llm, audit).run(task(), context())

    assert result.status == "COMPLETED"
    assert "record_findings" in [name for name, _ in box.calls]
    assert result.data is not None
    assert result.data["classifiedByLlm"] == 0 and result.data["uncertainRemaining"] == 1


def test_a_small_step_budget_still_records_the_inventory() -> None:
    uncertain = [finding(symbol=f"U{i}#m", algorithm_family="UNKNOWN", confidence=0.2) for i in range(5)]
    box = toolbox(uncertain, snippets=5)
    llm = ScriptedLLM(["RSA"] * 5)
    audit = RecordingAuditLog()
    # 40 total; gather spends 2, reserve keeps 3 for the tail; only a few classification pairs fit.
    result = agent(box, llm, audit, steps=9).run(task(), context())

    assert result.status == "COMPLETED"
    assert "record_findings" in [name for name, _ in box.calls]
    assert result.data is not None and result.data["uncertainRemaining"] >= 1


def test_a_model_failure_does_not_stop_the_inventory() -> None:
    from src.llm.provider import LLMUnavailableError

    box = toolbox([finding(algorithm_family="UNKNOWN", confidence=0.2)], snippets=1)
    llm = ScriptedLLM([LLMUnavailableError("down")])

    result = agent(box, llm, RecordingAuditLog()).run(task(), context())

    assert result.status == "COMPLETED"
    assert "record_findings" in [name for name, _ in box.calls]
    assert result.data is not None and result.data["uncertainRemaining"] == 1


def test_running_out_of_tokens_while_classifying_still_records_the_inventory() -> None:
    from src.llm.provider import GenerationResult, TokenUsage

    box = toolbox([finding(algorithm_family="UNKNOWN", confidence=0.2)], snippets=1)
    llm = ScriptedLLM([GenerationResult(text="RSA", usage=TokenUsage(9000, 5), model="fake")])

    result = agent(box, llm, RecordingAuditLog()).run(task(), context())

    assert result.status == "COMPLETED"
    assert "record_findings" in [name for name, _ in box.calls]


def test_the_model_never_makes_a_finding_less_urgent_than_the_analyzer_found_it() -> None:
    # A trust-all TLS finding (UNKNOWN family, P0, D-188) that the model calls RSA would fall to P3: it stays STATIC.
    trust_all = finding(algorithm_family="UNKNOWN", usage_context="TLS_SERVER_AUTH", confidence=0.4, priority="P0")
    box = toolbox([trust_all], snippets=1)

    agent(box, ScriptedLLM(["RSA"]), RecordingAuditLog()).run(task(), context())

    [sent] = next(args for name, args in box.calls if name == "record_findings")["body"]["findings"]
    assert (sent["algorithmFamily"], sent["priority"], sent["classifiedBy"]) == ("UNKNOWN", "P0", "STATIC")


def test_a_failed_run_closes_the_started_scan_as_failed_and_returns_its_id() -> None:
    from src.tools.base_tool import ToolError

    box = toolbox([finding()])
    box._errors["record_findings"] = ToolError("boom")  # noqa: SLF001

    result = agent(box, ScriptedLLM(), RecordingAuditLog()).run(task(), context())

    assert result.status == "FAILED"
    assert result.data == {"scanId": SCAN_ID}
    completion = [args for name, args in box.calls if name == "complete_scan"]
    assert [call["body"] for call in completion] == [{"outcome": "FAILED"}]


def test_more_than_500_findings_record_the_most_urgent_500_and_count_the_rest() -> None:
    many = [finding(symbol=f"S{i}#m", priority="P3") for i in range(400)]
    many += [finding(symbol=f"U{i}#m", priority="P0", key_size_bits=1024) for i in range(101)]
    box = toolbox(many)

    result = agent(box, ScriptedLLM(), RecordingAuditLog()).run(task(), context())

    sent = next(args for name, args in box.calls if name == "record_findings")["body"]["findings"]
    assert len(sent) == 500
    assert sum(1 for f in sent if f["priority"] == "P0") == 101
    assert result.data is not None and result.data["droppedOverLimit"] == 1
