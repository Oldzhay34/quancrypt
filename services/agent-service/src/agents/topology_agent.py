"""The topology agent (M5, UC1): it maps the service graph and records it against the scan (P4.5).

It builds the topology from static analysis, lists the scan's findings to turn the analyzer's natural finding keys into
core finding ids (D-208), drops the `DATABASE` nodes and maps `EXTERNAL` to `EXTERNAL_CLIENT` (D-170), then records the
topology. It makes no language-model call (max_tokens 0).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.agents.base_agent import AgentContext, AgentResult, AgentState, AgentTask, BaseAgent, Budget, RunMeter, Toolbox
from src.memory.short_term import AuditLog
from src.tools.base_tool import ToolError, ToolResult

_NODE_KIND = {"EXTERNAL": "EXTERNAL_CLIENT"}
_DROPPED_KIND = "DATABASE"
_PAGE_SIZE = 200


@dataclass
class TopologyState(AgentState):
    topology: Mapping[str, Any] | None = None
    core_topology: dict[str, Any] | None = None
    dropped_nodes: int = 0
    unmatched_refs: int = 0


class TopologyAgent(BaseAgent[TopologyState]):
    def __init__(self, toolbox: Toolbox, audit: AuditLog, budget: Budget) -> None:
        super().__init__("TOPOLOGY", budget, audit, toolbox=toolbox)

    def _new_state(self, task: AgentTask, meter: RunMeter) -> TopologyState:
        return TopologyState(meter=meter, task=task)

    def gather_context(self, context: AgentContext, state: TopologyState) -> None:
        if state.task.scan_id is None or state.task.root is None:
            raise ToolError("topology needs a scan id and a root")
        built = self._call_tool(state, "build_topology", {"body": {"root": state.task.root}}, self._context(context))
        state.topology = _out(built)

    def plan(self, context: AgentContext, state: TopologyState) -> None:
        ids = self._finding_ids(context, state)
        topology = state.topology or {"nodes": [], "edges": []}
        kept: dict[str, str] = {}
        for node in topology["nodes"]:
            if node["kind"] == _DROPPED_KIND:
                state.dropped_nodes += 1
                continue
            kept[node["id"]] = _NODE_KIND.get(node["kind"], node["kind"])
        links = []
        for edge in topology["edges"]:
            if edge["source"] not in kept or edge["target"] not in kept:
                continue
            finding_ids = self._map_refs(edge.get("findings", []), ids, state)
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
        nodes = [{"name": name, "nodeKind": kind} for name, kind in kept.items()]
        state.core_topology = {"nodes": nodes, "links": links}

    def act(self, context: AgentContext, state: TopologyState) -> None:
        self._call_tool(
            state,
            "record_topology",
            {"scanId": str(state.task.scan_id), "body": state.core_topology},
            self._context(context),
        )

    def report(self, context: AgentContext, state: TopologyState) -> AgentResult:
        core = state.core_topology or {"nodes": [], "links": []}
        mtls = sum(1 for link in core["links"] if link["mtls"])
        tls_no_mtls = sum(1 for link in core["links"] if link["tls"] and not link["mtls"])
        plaintext = sum(1 for link in core["links"] if not link["tls"])
        data = {
            "scanId": str(state.task.scan_id),
            "nodes": len(core["nodes"]),
            "edges": len(core["links"]),
            "mtlsEdges": mtls,
            "tlsEdges": tls_no_mtls,
            "plaintextEdges": plaintext,
            "droppedNodes": state.dropped_nodes,
            "unmatchedFindingRefs": state.unmatched_refs,
        }
        if state.task.language == "en":
            text = (
                f"Topology recorded: {len(core['nodes'])} nodes, {len(core['links'])} edges "
                f"({mtls} mutual TLS, {tls_no_mtls} TLS, {plaintext} plaintext)."
            )
        else:
            text = (
                f"Topoloji kaydedildi: {len(core['nodes'])} düğüm, {len(core['links'])} kenar "
                f"({mtls} karşılıklı TLS, {tls_no_mtls} TLS, {plaintext} düz)."
            )
        return AgentResult(status="COMPLETED", text=text, data=data)

    def _finding_ids(self, context: AgentContext, state: TopologyState) -> dict[tuple[Any, ...], str]:
        ids: dict[tuple[Any, ...], str] = {}
        page = 0
        while True:
            result = self._call_tool(
                state,
                "list_findings",
                {"scanId": str(state.task.scan_id), "page": page, "size": _PAGE_SIZE},
                self._context(context),
            )
            body = _out(result)
            for finding in body["items"]:
                key = (
                    finding["path"],
                    finding["symbol"],
                    finding["algorithmFamily"],
                    finding["usageContext"],
                    finding["lineStart"],
                )
                ids[key] = finding["id"]
            if (page + 1) * _PAGE_SIZE >= int(body["totalElements"]):
                break
            page += 1
        return ids

    def _map_refs(
        self, refs: list[Mapping[str, Any]], ids: Mapping[tuple[Any, ...], str], state: TopologyState
    ) -> list[str]:
        matched: set[str] = set()
        for ref in refs:
            key = (ref["file"], ref["symbol"], ref["algorithm_family"], ref["usage_context"], ref["line_start"])
            core_id = ids.get(key)
            if core_id is None:
                state.unmatched_refs += 1
            else:
                matched.add(core_id)
        return sorted(matched)


def _out(result: ToolResult) -> Mapping[str, Any]:
    if result.output is None:
        raise ToolError("a tool returned no output")
    return result.output
