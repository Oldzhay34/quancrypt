"""Composition root: the only place where concrete classes are built (agent-service-layout section 3).

P4.1 built the LLM side; P4.2 added the database and the memory ports; P4.3 the tools (registry, allow-lists, service
clients); P4.4 the scope keeper chain and the output checker; P4.6 the agents (built fresh per request by the agent
factory), the orchestrator, the outbox relay and the housekeeping task.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from src.agents.base_agent import Budget, Toolbox
from src.agents.discovery_agent import DiscoveryAgent
from src.agents.planner_agent import PlannerAgent
from src.agents.supervisor_agent import SupervisorAgent
from src.agents.topology_agent import TopologyAgent
from src.app.api import ReadinessCheck
from src.app.outbox_relay import (
    HOUSEKEEPING_INTERVAL_S,
    Backoff,
    HttpEventPublisher,
    OutboxRelay,
    PeriodicTask,
    housekeeping_work,
    relay_work,
)
from src.app.settings import (
    LOCAL_SERVICE_HOSTS,
    AppSettings,
    DatabaseSettings,
    GuardrailsSettings,
    OllamaSettings,
    ServiceSettings,
)
from src.guardrails.chain import GuardChain, GuardRing
from src.guardrails.llm_self_check import LLMSelfCheck
from src.guardrails.output_checker import OutputChecker
from src.guardrails.redaction import Redactor
from src.guardrails.rule_filter import RuleFilter, RuleFilterConfig
from src.guardrails.scope_classifier import EmbeddingTopicGate
from src.llm.null_provider import NullProvider
from src.llm.ollama_provider import OllamaProvider, OllamaProviderConfig
from src.llm.provider import EmbeddingProvider, LLMHealth, LLMProvider
from src.memory.long_term import EmbeddingKnowledgeBase, KnowledgeBase, KnowledgeIndex
from src.memory.memory_store import (
    Database,
    DatabaseConfig,
    DatabaseReadiness,
    PostgresAuditLog,
    PostgresCheckpointStore,
    PostgresConversationMemory,
    PostgresIdempotencyMaintenance,
    PostgresKnowledgeRepository,
    PostgresOutboxRelayStore,
    PostgresScopeDecisionLog,
    utc_now,
)
from src.memory.short_term import (
    AuditLog,
    CheckpointStore,
    ConsentReader,
    ConversationMemory,
    ConversationWindow,
    IdempotencyMaintenance,
    ScopeDecisionLog,
)
from src.tools.analyzer_tool import analyzer_tools
from src.tools.api_tool import EndpointTool, InternalHttpClient, ServiceEndpoint
from src.tools.base_tool import SchemaStore
from src.tools.core_tool import CoreConsentReader, core_tools
from src.tools.kb_search_tool import KbSearchTool
from src.tools.registry import ToolRegistry
from src.tools.risk_model_tool import RuleBaselineRiskModel, ScoreFindingsTool
from src.workflows.agent_graph import LangGraphWorkflows
from src.workflows.orchestrator import AgentSet, Orchestrator


class AgentBuilder(Protocol):
    """Fresh agents for one request. The orchestrator passes only the model; the evaluation (P4.7, D-268) also wraps the
    agents' toolboxes (`toolbox(agent name)`) and the supervisor's knowledge base, so it measures the agents exactly
    as the service builds them."""

    def __call__(
        self,
        llm: LLMProvider,
        toolbox: Callable[[str], Toolbox] | None = None,
        knowledge: KnowledgeBase | None = None,
    ) -> AgentSet: ...


@dataclass
class Container:
    settings: AppSettings
    llm: LLMProvider
    embeddings: EmbeddingProvider
    llm_health: LLMHealth
    database: Database
    conversation: ConversationMemory
    audit: AuditLog
    scope_decisions: ScopeDecisionLog
    idempotency: IdempotencyMaintenance
    knowledge: KnowledgeBase  # the read face (tools and agents)
    knowledge_index: KnowledgeIndex  # the write face (scripts/build_index.py only)
    redactor: Redactor
    tools: ToolRegistry  # agents get `tools.scoped(name)` (P4.5); the allow-lists come from agent_config.yaml
    consent_reader: ConsentReader  # the workflow layer reads the warehouse consent through it (P4.6), no agent does
    guard_chain: GuardChain  # every request passes it first (P4.4); the workflow records the decision (P4.6)
    output_checker: OutputChecker  # every answer passes it before the user sees it (P4.4)
    # Readiness falls only when one of these fails (the LLM never decides readiness, NFR-05).
    readiness_checks: Sequence[ReadinessCheck]
    # Runs once at startup (lifespan): the migrations. A failure stops the service (acid-3nf-database section 4).
    startup: Callable[[], None]
    checkpoints: CheckpointStore
    orchestrator: Orchestrator  # the HTTP layer's only entry to sessions, messages and scans (P4.6)
    agents: AgentBuilder  # the orchestrator's agent factory, open to the evaluation runner (D-268)
    # Background tasks started in the lifespan: the housekeeping task always, the outbox relay when enabled (D-252g).
    background: Sequence[PeriodicTask]
    # Called once at shutdown, in reverse order of registration.
    _closers: list[Callable[[], None]] = field(default_factory=list)

    def start_background(self) -> None:
        for task in self.background:
            task.start()
            self._closers.append(task.stop)

    def close(self) -> None:
        while self._closers:
            self._closers.pop()()


def build_container(settings: AppSettings) -> Container:
    _disable_remote_tracing()
    closers: list[Callable[[], None]] = []
    llm: LLMProvider
    embeddings: EmbeddingProvider
    llm_health: LLMHealth
    if settings.models.llm.provider == "null":
        null = NullProvider()
        llm, embeddings, llm_health = null, null, null
    else:
        ollama = OllamaProvider(_ollama_config(settings.models.ollama))
        llm, embeddings, llm_health = ollama, ollama, ollama
        closers.append(ollama.close)

    memory = settings.agents.memory
    database = Database(_database_config(memory.database))
    closers.append(database.close)
    history = memory.history
    window = ConversationWindow(history.max_messages, history.token_budget, history.chars_per_token)
    repository = PostgresKnowledgeRepository(database, utc_now, uuid.uuid4)
    knowledge = EmbeddingKnowledgeBase(
        repository,
        embeddings,
        settings.models.ollama.embedding_model,
        settings.models.ollama.embedding_dimensions,
        memory.knowledge_base.top_k,
    )
    services = settings.agents.services
    contracts_dir = Path(services.contracts_dir)
    redactor = build_redactor(settings)
    schemas = SchemaStore(contracts_dir)
    token = services.internal_token.get_secret_value()
    core_client = InternalHttpClient(_endpoint("core-service", services.core, token))
    analyzer_client = InternalHttpClient(_endpoint("analyzer-service", services.analyzer, token))
    closers.extend([core_client.close, analyzer_client.close])
    service_tools: list[EndpointTool] = [*core_tools(core_client, schemas), *analyzer_tools(analyzer_client, schemas)]
    rule_filter = _rule_filter(settings.agents.guardrails)
    registry = ToolRegistry(
        [*service_tools, KbSearchTool(knowledge, schemas), ScoreFindingsTool(RuleBaselineRiskModel(), schemas)],
        {name: agent.tools for name, agent in settings.agents.agents.items()},
        schemas,
        redactor,
    )
    audit = PostgresAuditLog(database, utc_now, uuid.uuid4)
    conversation = PostgresConversationMemory(database, window, utc_now, uuid.uuid4)
    scope_decisions = PostgresScopeDecisionLog(database, utc_now, uuid.uuid4)
    idempotency = PostgresIdempotencyMaintenance(database, utc_now)
    checkpoints = PostgresCheckpointStore(database, utc_now)
    consent_reader = CoreConsentReader(registry.call)
    guard_chain = GuardChain(_rings(settings.agents.guardrails, rule_filter, llm, embeddings))
    output_checker = OutputChecker(rule_filter, redactor, settings.agents.output_check.on_mismatch)
    agents = _agent_factory(settings, registry, knowledge, audit)
    orchestrator = Orchestrator(
        conversation=conversation,
        audit=audit,
        scope_log=scope_decisions,
        consent=consent_reader,
        call_tool=registry.call,
        guard=guard_chain,
        output_checker=output_checker,
        llm=llm,
        agents=agents,
        workflows=LangGraphWorkflows(checkpoints),
        queue_wait_s=settings.agents.session.queue_wait_s,
        clock=utc_now,
    )
    background = [PeriodicTask("housekeeping", housekeeping_work(idempotency, checkpoints), HOUSEKEEPING_INTERVAL_S)]
    relay_settings = settings.agents.relay
    if relay_settings.enabled and relay_settings.ingest_url is not None:
        publisher = HttpEventPublisher(relay_settings.ingest_url, token, relay_settings.timeout_s)
        closers.append(publisher.close)
        relay = OutboxRelay(
            PostgresOutboxRelayStore(database, utc_now), consent_reader, publisher, relay_settings.batch_size
        )
        backoff = Backoff(relay_settings.interval_s, relay_settings.max_backoff_s)
        background.append(PeriodicTask("outbox-relay", relay_work(relay, backoff), relay_settings.interval_s))
    return Container(
        settings=settings,
        llm=llm,
        embeddings=embeddings,
        llm_health=llm_health,
        database=database,
        conversation=conversation,
        audit=audit,
        scope_decisions=scope_decisions,
        idempotency=idempotency,
        knowledge=knowledge,
        knowledge_index=knowledge,
        redactor=redactor,
        tools=registry,
        consent_reader=consent_reader,
        guard_chain=guard_chain,
        output_checker=output_checker,
        readiness_checks=(DatabaseReadiness(database),),
        startup=database.migrate,
        checkpoints=checkpoints,
        orchestrator=orchestrator,
        agents=agents,
        background=background,
        _closers=closers,
    )


def _disable_remote_tracing() -> None:
    """LangGraph brings langchain-core, which brings the LangSmith client: it sends traces to a cloud service only when
    tracing is switched on in the environment. Phase 1 is local (guardrails-security section 1), so it is forced off."""
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        os.environ[name] = "false"


def _agent_factory(
    settings: AppSettings, registry: ToolRegistry, knowledge: KnowledgeBase, audit: AuditLog
) -> AgentBuilder:
    """Fresh agents and toolboxes per request (each run has its own tool-call journal); the model is the request's.
    `toolbox` and `knowledge` replace the registry's scoped toolboxes and the knowledge base (the evaluation, D-268)."""
    agents = settings.agents.agents
    discovery_settings = settings.agents.discovery
    default_knowledge = knowledge

    def budget(name: str) -> Budget:
        limits = agents[name].budget
        return Budget(max_steps=limits.max_steps, max_tokens=limits.max_tokens, timeout_s=limits.timeout_s)

    def build(
        llm: LLMProvider,
        toolbox: Callable[[str], Toolbox] | None = None,
        knowledge: KnowledgeBase | None = None,
    ) -> AgentSet:
        box = toolbox or registry.scoped
        kb = knowledge or default_knowledge
        planner = PlannerAgent(box("planner"), llm, kb, audit, budget("planner"))
        return AgentSet(
            discovery=DiscoveryAgent(
                box("discovery"),
                llm,
                audit,
                budget("discovery"),
                uncertain_below=discovery_settings.uncertain_below,
                llm_confidence=discovery_settings.llm_confidence,
            ),
            topology=TopologyAgent(box("topology"), audit, budget("topology")),
            planner=planner,
            answer=SupervisorAgent(llm, kb, audit, budget("supervisor"), {"planner": planner}),
        )

    return build


def build_redactor(settings: AppSettings) -> Redactor:
    """The shared redactor (contracts/redaction-rules.yaml); the logging setup gets one before the container exists."""
    return Redactor.from_file(Path(settings.agents.services.contracts_dir) / "redaction-rules.yaml")


def _rule_filter(guardrails: GuardrailsSettings) -> RuleFilter:
    return RuleFilter(
        RuleFilterConfig(
            max_request_chars=guardrails.max_request_chars,
            jailbreak_phrases={"tr": guardrails.jailbreak_phrases.tr, "en": guardrails.jailbreak_phrases.en},
            out_of_scope_keywords={
                "tr": guardrails.out_of_scope_keywords.tr,
                "en": guardrails.out_of_scope_keywords.en,
            },
            in_scope_keywords={"tr": guardrails.in_scope_keywords.tr, "en": guardrails.in_scope_keywords.en},
        )
    )


def _rings(
    guardrails: GuardrailsSettings, rule_filter: RuleFilter, llm: LLMProvider, embeddings: EmbeddingProvider
) -> list[GuardRing]:
    """The rings in configuration order (OCP: a new ring is a factory here and a name in the settings' ring list;
    P7.5 swaps the interim topic gate for the ONNX scope classifier, D-246)."""
    anchors = (*guardrails.topic_anchors.tr, *guardrails.topic_anchors.en)
    factories: dict[str, Callable[[], GuardRing]] = {
        "rule_filter": lambda: rule_filter,
        "scope_classifier": lambda: EmbeddingTopicGate(embeddings, anchors, guardrails.topic_threshold),
        "llm_self_check": lambda: LLMSelfCheck(llm, guardrails.self_check_max_tokens),
    }
    return [factories[name]() for name in guardrails.rings]


def _database_config(config: DatabaseSettings) -> DatabaseConfig:
    return DatabaseConfig(
        url=config.url,
        migrator_url=config.migrator_url,
        pool_size=config.pool_size,
        connect_timeout_s=config.connect_timeout_s,
        app_password=config.app_password.get_secret_value(),
        migrator_password=config.migrator_password.get_secret_value(),
    )


def _ollama_config(config: OllamaSettings) -> OllamaProviderConfig:
    return OllamaProviderConfig(
        base_url=config.base_url,
        chat_model=config.chat_model,
        embedding_model=config.embedding_model,
        embedding_dimensions=config.embedding_dimensions,
        temperature=config.temperature,
        num_ctx=config.num_ctx,
        num_predict=config.num_predict,
        connect_timeout_s=config.connect_timeout_s,
        timeout_s=config.timeout_s,
        retry_max_attempts=config.retry.max_attempts,
        retry_wait_initial_s=config.retry.wait_initial_s,
        retry_wait_max_s=config.retry.wait_max_s,
        breaker_fail_max=config.circuit_breaker.fail_max,
        breaker_reset_timeout_s=float(config.circuit_breaker.reset_timeout_s),
        health_timeout_s=config.health_timeout_s,
        health_cache_s=config.health_cache_s,
    )


def _endpoint(name: str, config: ServiceSettings, token: str) -> ServiceEndpoint:
    return ServiceEndpoint(
        name=name,
        base_url=config.base_url,
        internal_token=token,
        allowed_hosts=LOCAL_SERVICE_HOSTS,
        connect_timeout_s=config.connect_timeout_s,
        timeout_s=config.timeout_s,
        retry_max_attempts=config.retry.max_attempts,
        retry_wait_initial_s=config.retry.wait_initial_s,
        retry_wait_max_s=config.retry.wait_max_s,
        breaker_fail_max=config.circuit_breaker.fail_max,
        breaker_reset_timeout_s=float(config.circuit_breaker.reset_timeout_s),
    )
