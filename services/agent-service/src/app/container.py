"""Composition root: the only place where concrete classes are built (agent-service-layout section 3).

P4.1 builds the LLM side only. Later phases add the database, tools, agents and the workflow here.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from src.app.settings import AppSettings, OllamaSettings
from src.llm.null_provider import NullProvider
from src.llm.ollama_provider import OllamaProvider, OllamaProviderConfig
from src.llm.provider import EmbeddingProvider, LLMHealth, LLMProvider


@dataclass
class Container:
    settings: AppSettings
    llm: LLMProvider
    embeddings: EmbeddingProvider
    llm_health: LLMHealth
    # Called once at shutdown, in reverse order of registration.
    _closers: list[Callable[[], None]] = field(default_factory=list)

    def close(self) -> None:
        while self._closers:
            self._closers.pop()()


def build_container(settings: AppSettings) -> Container:
    if settings.models.llm.provider == "null":
        null = NullProvider()
        return Container(settings=settings, llm=null, embeddings=null, llm_health=null)
    ollama = OllamaProvider(_ollama_config(settings.models.ollama))
    return Container(settings=settings, llm=ollama, embeddings=ollama, llm_health=ollama, _closers=[ollama.close])


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
