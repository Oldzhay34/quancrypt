"""The tools against the real core-service and analyzer-service on QBank's payment service (`make integration`, D-238f).

Needs a running stack (postgres, core-service, analyzer-service) with `PROJECT_ROOT=reference-system`; the analysis root
is a single QBank service because `reference-system/` itself has no build file (D-203). Addresses and the token come
from the environment: `CORE_SERVICE_URL`, `ANALYZER_SERVICE_URL`, `INTERNAL_SERVICE_TOKEN`, optionally
`QUANCRYPT_ANALYSIS_ROOT`. Without the stack the test fails; it never skips.

The snake_case → camelCase mapping of findings and the topology mapping (D-170, D-175) are written out here; in the
product the agents do it (P4.5).
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping
from typing import Any

import pytest

from src.memory.long_term import EmbeddingKnowledgeBase
from src.tools.analyzer_tool import analyzer_tools
from src.tools.api_tool import InternalHttpClient, ServiceEndpoint
from src.tools.base_tool import Tool, ToolContext
from src.tools.core_tool import core_tools
from src.tools.kb_search_tool import KbSearchTool
from src.tools.registry import ToolRegistry
from src.tools.risk_model_tool import RuleBaselineRiskModel, ScoreFindingsTool
from tests.support.embedding import DIMENSIONS, MODEL, BagOfWordsEmbedder
from tests.support.memory_fakes import InMemoryKnowledgeRepository
from tests.support.tools import APPROVED_ALLOW_LISTS, LOCAL_HOSTS, redactor, schemas

pytestmark = pytest.mark.integration

ROOT = os.environ.get("QUANCRYPT_ANALYSIS_ROOT", "/workspace/qbank-payment-service")
TRACE = uuid.uuid4().hex


def _endpoint(name: str, variable: str, timeout_s: float) -> ServiceEndpoint:
    return ServiceEndpoint(
        name=name,
        base_url=os.environ[variable],
        internal_token=os.environ["INTERNAL_SERVICE_TOKEN"],
        allowed_hosts=LOCAL_HOSTS,
        connect_timeout_s=3,
        timeout_s=timeout_s,
        retry_max_attempts=2,
        retry_wait_initial_s=0.5,
        retry_wait_max_s=2,
        breaker_fail_max=5,
        breaker_reset_timeout_s=30,
    )


@pytest.fixture(scope="module")
def registry() -> ToolRegistry:
    store = schemas()
    core = InternalHttpClient(_endpoint("core-service", "CORE_SERVICE_URL", 30))
    analyzer = InternalHttpClient(_endpoint("analyzer-service", "ANALYZER_SERVICE_URL", 310))
    knowledge = EmbeddingKnowledgeBase(InMemoryKnowledgeRepository(), BagOfWordsEmbedder(), MODEL, DIMENSIONS, 5)
    tools: list[Tool] = [
        *core_tools(core, store),
        *analyzer_tools(analyzer, store),
        KbSearchTool(knowledge, store),
        ScoreFindingsTool(RuleBaselineRiskModel(), store),
    ]
    return ToolRegistry(tools, APPROVED_ALLOW_LISTS, store, redactor())


def call(registry: ToolRegistry, name: str, arguments: Mapping[str, Any]) -> Any:
    output, _ = registry.call(name, arguments, ToolContext(trace_id=TRACE))  # input and output validated by contract
    return output


def to_core_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    mapped: dict[str, Any] = {
        "path": finding["file"],
        "symbol": finding["symbol"],
        "algorithmFamily": finding["algorithm_family"],
        "usageContext": finding["usage_context"],
        "locationKind": finding["location_kind"],
        "priority": finding["priority"],
        "keySizeBits": finding["key_size_bits"],
        "confidence": finding["confidence"],
        "classifiedBy": "STATIC",
    }
    if finding["line_start"] is not None:
        mapped["lineStart"], mapped["lineEnd"] = finding["line_start"], finding["line_end"]
    return mapped


def finding_key(path: str, symbol: str, family: str, context: str, line: int | None) -> tuple[Any, ...]:
    return (path, symbol, family, context, line)


def to_core_topology(topology: Mapping[str, Any], ids: Mapping[tuple[Any, ...], str]) -> dict[str, Any]:
    kinds = {"EXTERNAL": "EXTERNAL_CLIENT"}
    kept = {
        node["id"]: kinds.get(node["kind"], node["kind"]) for node in topology["nodes"] if node["kind"] != "DATABASE"
    }
    links = []
    for edge in topology["edges"]:
        if edge["source"] not in kept or edge["target"] not in kept:
            continue
        refs = edge.get("findings", [])
        finding_ids = sorted(
            {
                ids[key]
                for ref in refs
                if (
                    key := finding_key(
                        ref["file"], ref["symbol"], ref["algorithm_family"], ref["usage_context"], ref["line_start"]
                    )
                )
                in ids
            }
        )
        links.append(
            {
                "source": edge["source"],
                "target": edge["target"],
                "protocol": edge["protocol"],
                "tls": edge["tls"],
                "mtls": edge["tls"] and edge["mtls"],
                "callSites": [],
                "findingIds": finding_ids,
            }
        )
    return {"nodes": [{"name": name, "nodeKind": kind} for name, kind in kept.items()], "links": links}


def test_qbank_payment_service_from_discovery_to_plan_report(registry: ToolRegistry) -> None:
    project = call(
        registry,
        "register_project",
        {"body": {"identity": f"integration-test/{uuid.uuid4()}", "displayName": "QBank payment (integration)"}},
    )
    scan = call(registry, "start_scan", {"projectId": project["id"]})
    assert scan["status"] == "RUNNING"

    analysis = call(registry, "analyze_crypto", {"body": {"root": ROOT, "include_tests": True}})
    findings = analysis["findings"]
    assert findings, "QBank's payment service uses RSA-OAEP and SHA1withRSA; the analyzer must find them"
    created = 0
    for start in range(0, len(findings), 500):
        batch = [to_core_finding(finding) for finding in findings[start : start + 500]]
        result = call(registry, "record_findings", {"scanId": scan["id"], "body": {"findings": batch}})
        assert result["createdCount"] + result["existingCount"] == len(batch)
        created += result["createdCount"]
    call(registry, "record_scan_artifact", {"scanId": scan["id"], "body": analysis["cbom"]})

    recorded: list[dict[str, Any]] = []
    page = 0
    while True:
        listing = call(registry, "list_findings", {"scanId": scan["id"], "page": page, "size": 200})
        recorded.extend(listing["items"])
        if len(recorded) >= listing["totalElements"]:
            break
        page += 1
    assert len(recorded) == created
    ids = {
        finding_key(f["path"], f["symbol"], f["algorithmFamily"], f["usageContext"], f["lineStart"]): f["id"]
        for f in recorded
    }

    topology = call(registry, "build_topology", {"body": {"root": ROOT}})
    call(registry, "record_topology", {"scanId": scan["id"], "body": to_core_topology(topology, ids)})
    completed = call(registry, "complete_scan", {"scanId": scan["id"], "body": {"outcome": "COMPLETED"}})
    assert completed["status"] == "COMPLETED"

    stored_topology = call(registry, "get_topology", {"scanId": scan["id"]})
    scores = call(registry, "score_findings", {"findings": recorded, "topology": stored_topology})
    assert scores["model_id"] == "rule_baseline_v1"
    assert len(scores["scores"]) == len(recorded)
    assert "CRITICAL" in {score["riskClass"] for score in scores["scores"]}  # SHA1withRSA receipt signature is P0

    items = [
        {"findingId": score["findingId"], "riskScore": score["riskScore"], "riskFactors": score["riskFactors"]}
        for score in scores["scores"]
    ]
    plan = call(registry, "create_plan", {"scanId": scan["id"], "body": {"items": items}})
    assert plan["itemCount"] == len(recorded)

    fetched = call(registry, "get_plan", {"scanId": scan["id"], "page": 0, "size": 200})
    assert fetched["plan"]["id"] == plan["id"]
    assert fetched["totalElements"] == len(recorded)

    for language in ("tr", "en"):
        report = call(registry, "get_plan_report", {"scanId": scan["id"], "language": language})
        assert report["markdown"].strip()

    snippet_source = next(f for f in findings if f["line_start"] is not None)
    snippet = call(
        registry,
        "get_snippet",
        {"root": ROOT, "path": snippet_source["file"], "line": snippet_source["line_start"], "context": 2},
    )
    assert any(line["number"] == snippet_source["line_start"] for line in snippet["lines"])
