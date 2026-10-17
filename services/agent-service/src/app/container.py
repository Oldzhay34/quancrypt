"""Composition root: the only place where concrete classes are built (agent-service-layout section 3).

P4.1 built the LLM side; P4.2 adds the database and the memory ports. Later phases add tools, agents and the workflow.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from src.app.api import ReadinessCheck
from src.app.settings import AppSettings, DatabaseSettings, OllamaSettings
from src.llm.null_provider import NullProvider
from src.llm.ollama_provider import OllamaProvider, OllamaProviderConfig
from src.llm.provider import EmbeddingProvider, LLMHealth, LLMProvider
from src.memory.long_term import EmbeddingKnowledgeBase, KnowledgeBase, KnowledgeIndex
from src.memory.memory_store import (
    Database,
    DatabaseConfig,
    DatabaseReadiness,
    PostgresAuditLog,
    PostgresConversationMemory,
    PostgresIdempotencyMaintenance,
    PostgresKnowledgeRepository,
    PostgresScopeDecisionLog,
    utc_now,
)
from src.memory.short_term import (
    AuditLog,
    ConversationMemory,
    ConversationWindow,
    IdempotencyMaintenance,
    ScopeDecisionLog,
)


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
    # Readiness falls only when one of these fails (the LLM never decides readiness, NFR-05).
    readiness_checks: Sequence[ReadinessCheck]
    # Runs once at startup (lifespan): the migrations. A failure stops the service (acid-3nf-database section 4).
    startup: Callable[[], None]
    # Called once at shutdown, in reverse order of registration.
    _closers: list[Callable[[], None]] = field(default_factory=list)

    def close(self) -> None:
        while self._closers:
            self._closers.pop()()


def build_container(settings: AppSettings) -> Container:
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
    return Container(
        settings=settings,
        llm=llm,
        embeddings=embeddings,
        llm_health=llm_health,
        database=database,
        conversation=PostgresConversationMemory(database, window, utc_now, uuid.uuid4),
        audit=PostgresAuditLog(database, utc_now, uuid.uuid4),
        scope_decisions=PostgresScopeDecisionLog(database, utc_now, uuid.uuid4),
        idempotency=PostgresIdempotencyMaintenance(database, utc_now),
        knowledge=knowledge,
        knowledge_index=knowledge,
        readiness_checks=(DatabaseReadiness(database),),
        startup=database.migrate,
        _closers=closers,
    )


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
