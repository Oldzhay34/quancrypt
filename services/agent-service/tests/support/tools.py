"""A tool registry wired like the container, but with test endpoints (respx intercepts the HTTP calls)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from functools import cache

from src.guardrails.redaction import Redactor
from src.memory.long_term import EmbeddingKnowledgeBase
from src.tools.analyzer_tool import analyzer_tools
from src.tools.api_tool import InternalHttpClient, ServiceEndpoint
from src.tools.base_tool import SchemaStore, Tool
from src.tools.core_tool import core_tools
from src.tools.kb_search_tool import KbSearchTool
from src.tools.registry import ToolRegistry
from src.tools.risk_model_tool import RuleBaselineRiskModel, ScoreFindingsTool
from tests.support.embedding import DIMENSIONS, MODEL, BagOfWordsEmbedder
from tests.support.memory_fakes import InMemoryKnowledgeRepository
from tests.support.postgres import REPO_ROOT

CONTRACTS = REPO_ROOT / "contracts"
CORE_URL = "http://127.0.0.1:8081"
ANALYZER_URL = "http://127.0.0.1:8082"
TOKEN = "unit-test-internal-token-0123456789abcdef"
TRACE = "0123456789abcdef0123456789abcdef"
LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "core-service", "analyzer-service"})

APPROVED_ALLOW_LISTS: Mapping[str, Sequence[str]] = {
    "supervisor": (),
    "discovery": (
        "analyze_crypto",
        "get_snippet",
        "start_scan",
        "record_findings",
        "record_scan_artifact",
        "complete_scan",
    ),
    "topology": ("build_topology", "record_topology", "list_findings"),
    "planner": (
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
    ),
}


def endpoint(name: str, url: str, *, attempts: int = 2, fail_max: int = 5) -> ServiceEndpoint:
    return ServiceEndpoint(
        name=name,
        base_url=url,
        internal_token=TOKEN,
        allowed_hosts=LOCAL_HOSTS,
        connect_timeout_s=1,
        timeout_s=2,
        retry_max_attempts=attempts,
        retry_wait_initial_s=0.01,
        retry_wait_max_s=0.02,
        breaker_fail_max=fail_max,
        breaker_reset_timeout_s=60,
    )


def _no_sleep(_: float) -> None:
    return None


@cache
def schemas() -> SchemaStore:
    """One store per test session: it only caches parsed contract files and compiled validators."""
    return SchemaStore(CONTRACTS)


@cache
def redactor() -> Redactor:
    return Redactor.from_file(CONTRACTS / "redaction-rules.yaml")


def all_tools(store: SchemaStore, *, attempts: int = 2, fail_max: int = 5) -> list[Tool]:
    core = InternalHttpClient(endpoint("core-service", CORE_URL, attempts=attempts, fail_max=fail_max), sleep=_no_sleep)
    analyzer = InternalHttpClient(
        endpoint("analyzer-service", ANALYZER_URL, attempts=attempts, fail_max=fail_max), sleep=_no_sleep
    )
    repository = InMemoryKnowledgeRepository()
    knowledge = EmbeddingKnowledgeBase(repository, BagOfWordsEmbedder(), MODEL, DIMENSIONS, 5)
    return [
        *core_tools(core, store),
        *analyzer_tools(analyzer, store),
        KbSearchTool(knowledge, store),
        ScoreFindingsTool(RuleBaselineRiskModel(), store),
    ]


def build_registry(
    allow_lists: Mapping[str, Sequence[str]] = APPROVED_ALLOW_LISTS, *, attempts: int = 2, fail_max: int = 5
) -> ToolRegistry:
    store = schemas()
    return ToolRegistry(all_tools(store, attempts=attempts, fail_max=fail_max), allow_lists, store, redactor())
