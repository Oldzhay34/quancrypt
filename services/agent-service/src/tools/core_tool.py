"""core-service tools (contracts/openapi/core-service.yaml): the shared blackboard of the agents
(agent-service-layout §5).

Every command that the contract gives an `Idempotency-Key` sends the call id as that key, so a retried call cannot
create
a second scan, a second batch of findings or a second plan. `get_consents` is on no agent's allow-list (D-238a); the
workflow layer reads the warehouse consent through `CoreConsentReader` (`ConsentReader`, P4.6).
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from src.tools.api_tool import EndpointSpec, EndpointTool, InternalHttpClient
from src.tools.base_tool import SchemaStore, ToolContext, ToolError
from src.tools.contracts.core_service import (
    ClarificationAnswerSet,
    ConsentList,
    FindingBatchResult,
    FindingPage,
    Plan,
    PlanPage,
    Project,
    ProjectDetail,
    ProjectProfile,
    Scan,
    ScanArtifact,
    Topology,
)

_LOG = logging.getLogger("src.tools")

_PROJECT = "/api/v1/projects/{projectId}"
_SCAN = "/api/v1/scans/{scanId}"

SPECS = (
    EndpointSpec("register_project", "POST", "/api/v1/projects", has_body=True, command=True, response_model=Project),
    EndpointSpec("get_project", "GET", _PROJECT, path_params=("projectId",), response_model=ProjectDetail),
    EndpointSpec(
        "start_scan", "POST", f"{_PROJECT}/scans", path_params=("projectId",), command=True, response_model=Scan
    ),
    EndpointSpec(
        "record_findings",
        "POST",
        f"{_SCAN}/findings",
        path_params=("scanId",),
        has_body=True,
        command=True,
        response_model=FindingBatchResult,
    ),
    EndpointSpec(
        "record_scan_artifact",
        "PUT",
        f"{_SCAN}/artifact",
        path_params=("scanId",),
        has_body=True,
        response_model=ScanArtifact,
    ),
    EndpointSpec(
        "record_topology", "PUT", f"{_SCAN}/topology", path_params=("scanId",), has_body=True, response_model=Topology
    ),
    EndpointSpec(
        "complete_scan",
        "POST",
        f"{_SCAN}/completion",
        path_params=("scanId",),
        has_body=True,
        command=True,
        response_model=Scan,
    ),
    EndpointSpec(
        "list_findings",
        "GET",
        f"{_SCAN}/findings",
        path_params=("scanId",),
        query_params=("page", "size", "priority", "algorithmFamily", "usageContext", "locationKind", "classifiedBy"),
        response_model=FindingPage,
    ),
    EndpointSpec("get_topology", "GET", f"{_SCAN}/topology", path_params=("scanId",), response_model=Topology),
    EndpointSpec(
        "get_project_profile", "GET", f"{_PROJECT}/profile", path_params=("projectId",), response_model=ProjectProfile
    ),
    EndpointSpec(
        "save_clarification_answers",
        "PUT",
        f"{_PROJECT}/clarification-answers",
        path_params=("projectId",),
        has_body=True,
        response_model=ClarificationAnswerSet,
    ),
    EndpointSpec(
        "create_plan",
        "POST",
        f"{_SCAN}/plan",
        path_params=("scanId",),
        has_body=True,
        command=True,
        response_model=Plan,
    ),
    EndpointSpec(
        "get_plan",
        "GET",
        f"{_SCAN}/plan",
        path_params=("scanId",),
        query_params=("page", "size", "state"),
        response_model=PlanPage,
    ),
    EndpointSpec(
        "get_plan_report",
        "GET",
        f"{_SCAN}/plan/report",
        path_params=("scanId",),
        header_params=(("language", "Accept-Language"),),
        reply="markdown",
    ),
    EndpointSpec("get_consents", "GET", f"{_PROJECT}/consents", path_params=("projectId",), response_model=ConsentList),
)


def core_tools(client: InternalHttpClient, schemas: SchemaStore) -> list[EndpointTool]:
    return [EndpointTool(spec, client, schemas, "CORE") for spec in SPECS]


ToolCaller = Callable[[str, Mapping[str, Any], ToolContext], tuple[Mapping[str, Any], int]]


class CoreConsentReader:
    """`ConsentReader` over the `get_consents` tool: the warehouse consent is valid only if core says so (fail-closed).

    The tool is called through `ToolRegistry.call` (the workflow layer's way to tools outside every allow-list, D-240j),
    so input and output are checked against the tool contract and the call is logged. Any failure (service down,
    rejected, malformed answer) reads as "no consent": an event is then simply not written (D-228, D-232a).
    """

    def __init__(self, call: ToolCaller) -> None:
        self._call = call

    def warehouse_consent(self, project_id: uuid.UUID, trace_id: str) -> bool:
        try:
            reply, _ = self._call("get_consents", {"projectId": str(project_id)}, ToolContext(trace_id=trace_id))
        except ToolError as exc:
            _LOG.warning("consent could not be read (%s); treated as not given", type(exc).__name__)
            return False
        return _warehouse_granted(reply)


def _warehouse_granted(reply: Mapping[str, Any]) -> bool:
    """Granted and not revoked (`revokedAt` null means the consent is valid)."""
    items = reply.get("items")
    if not isinstance(items, list):
        return False
    for consent in items:
        if isinstance(consent, Mapping) and consent.get("consentType") == "WAREHOUSE_ANALYTICS":
            return "revokedAt" in consent and consent["revokedAt"] is None
    return False
