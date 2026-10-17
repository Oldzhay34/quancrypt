"""analyzer-service tools (contracts/openapi/analyzer-service.yaml): analysis, topology and redacted snippets.

The analyzer is stateless and its POST endpoints have no side effects (D-178a), so they may be repeated after a
transient failure. Arguments and outputs mirror the contract (snake_case, D-175); mapping onto core-service is the
agents' job (P4.5).
"""

from __future__ import annotations

from src.tools.api_tool import EndpointSpec, EndpointTool, InternalHttpClient
from src.tools.base_tool import SchemaStore
from src.tools.contracts.analyzer_service import AnalysisResult, Snippet

SPECS = (
    EndpointSpec(
        "analyze_crypto",
        "POST",
        "/api/v1/analyses",
        has_body=True,
        side_effect_free=True,
        response_model=AnalysisResult,
    ),
    EndpointSpec("build_topology", "POST", "/api/v1/topologies", has_body=True, side_effect_free=True),
    EndpointSpec(
        "get_snippet",
        "GET",
        "/api/v1/snippets",
        query_params=("root", "path", "line", "context"),
        response_model=Snippet,
    ),
)


def analyzer_tools(client: InternalHttpClient, schemas: SchemaStore) -> list[EndpointTool]:
    return [EndpointTool(spec, client, schemas, "ANALYZER") for spec in SPECS]
