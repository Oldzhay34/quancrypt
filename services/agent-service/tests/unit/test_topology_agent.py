"""The topology agent (M5, UC1): it maps the analyzer graph to core-service, drops DATABASE nodes, renames EXTERNAL and
maps the finding references to core finding ids."""

from __future__ import annotations

from typing import Any
from uuid import UUID, uuid4

from src.agents.base_agent import AgentContext, AgentTask, Budget
from src.agents.topology_agent import TopologyAgent
from tests.support.agent_fakes import FakeClock, RecordingAuditLog, ScriptedToolbox, new_run

SCAN_ID = str(uuid4())
TOOLS = ["build_topology", "record_topology", "list_findings"]
FID = str(uuid4())


def topology() -> dict[str, Any]:
    return {
        "nodes": [
            {"id": "gateway", "name": "gateway", "kind": "GATEWAY", "evidence": []},
            {"id": "account", "name": "account", "kind": "SERVICE", "evidence": []},
            {"id": "client", "name": "client", "kind": "EXTERNAL", "evidence": []},
            {"id": "db", "name": "db", "kind": "DATABASE", "evidence": []},
        ],
        "edges": [
            {
                "source": "client",
                "target": "gateway",
                "protocol": "HTTP",
                "tls": True,
                "mtls": False,
                "evidence": [],
                "findings": [],
            },
            {
                "source": "gateway",
                "target": "account",
                "protocol": "HTTP",
                "tls": True,
                "mtls": True,
                "evidence": [],
                "findings": [
                    {
                        "file": "A.java",
                        "symbol": "A#m",
                        "algorithm_family": "RSA",
                        "usage_context": "MTLS_CLIENT_AUTH",
                        "line_start": 5,
                    },
                    {
                        "file": "Z.java",
                        "symbol": "Z#z",
                        "algorithm_family": "RSA",
                        "usage_context": "CERTIFICATE",
                        "line_start": 9,
                    },
                ],
            },
            {
                "source": "account",
                "target": "db",
                "protocol": "HTTP",
                "tls": False,
                "mtls": False,
                "evidence": [],
                "findings": [],
            },
        ],
    }


def findings_page() -> dict[str, Any]:
    return {
        "items": [
            {
                "id": FID,
                "path": "A.java",
                "symbol": "A#m",
                "algorithmFamily": "RSA",
                "usageContext": "MTLS_CLIENT_AUTH",
                "lineStart": 5,
            }
        ],
        "page": 0,
        "size": 200,
        "totalElements": 1,
    }


def toolbox() -> ScriptedToolbox:
    return ScriptedToolbox(
        TOOLS,
        {
            "build_topology": [topology()],
            "list_findings": [findings_page()],
            "record_topology": [{"scanId": SCAN_ID, "recordedAt": "2026-01-01T00:00:00Z", "nodes": [], "links": []}],
        },
    )


def run(box: ScriptedToolbox) -> Any:
    run_id, trace = new_run()
    ctx = AgentContext(trace_id=trace, run_id=run_id, clock=FakeClock())
    agent = TopologyAgent(box, RecordingAuditLog(), Budget(8, 0, 360))
    return agent.run(AgentTask(kind="topology", language="en", scan_id=UUID(SCAN_ID), root="/workspace"), ctx)


def test_it_drops_database_renames_external_and_keeps_the_other_nodes() -> None:
    box = toolbox()
    run(box)

    body = next(args for name, args in box.calls if name == "record_topology")["body"]
    nodes = {node["name"]: node["nodeKind"] for node in body["nodes"]}
    assert nodes == {"gateway": "GATEWAY", "account": "SERVICE", "client": "EXTERNAL_CLIENT"}


def test_an_edge_to_a_dropped_node_is_removed_and_mtls_needs_tls() -> None:
    box = toolbox()
    run(box)

    body = next(args for name, args in box.calls if name == "record_topology")["body"]
    links = {(link["source"], link["target"]): link for link in body["links"]}
    assert set(links) == {("client", "gateway"), ("gateway", "account")}  # account->db dropped (db is a DATABASE)
    assert links[("gateway", "account")]["mtls"] is True
    assert links[("client", "gateway")]["mtls"] is False


def test_finding_references_map_to_core_ids_and_unmatched_ones_are_counted() -> None:
    box = toolbox()
    result = run(box)

    body = next(args for name, args in box.calls if name == "record_topology")["body"]
    link = next(link for link in body["links"] if link["target"] == "account")
    assert link["findingIds"] == [FID]  # A#m matched; Z#z is not in the findings page
    assert result.data is not None and result.data["unmatchedFindingRefs"] == 1
    assert result.data["droppedNodes"] == 1


def test_the_summary_counts_nodes_edges_and_mtls() -> None:
    result = run(toolbox())

    assert result.status == "COMPLETED"
    data = result.data
    assert data is not None
    assert (data["nodes"], data["edges"], data["mtlsEdges"], data["tlsEdges"]) == (3, 2, 1, 1)
