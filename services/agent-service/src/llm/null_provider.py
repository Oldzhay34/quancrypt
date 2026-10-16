"""LLM-less mode (NFR-05): the inventory and the plan are still produced, the explanation text carries a fixed note."""

from __future__ import annotations

from collections.abc import Iterator, Sequence

from src.llm.provider import (
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    LLMStatus,
    LLMUnavailableError,
    StreamChunk,
    TokenUsage,
)

LLM_DISABLED_NOTE = (
    "[LLM kapalı] Bu metin bir dil modeli olmadan üretildi. / "
    "[LLM disabled] This text was produced without a language model."
)

_NO_USAGE = TokenUsage(prompt_tokens=0, completion_tokens=0)


class NullProvider:
    """Implements `LLMProvider`, `EmbeddingProvider` and `LLMHealth` without any model."""

    def generate(self, request: GenerationRequest) -> GenerationResult:
        return GenerationResult(text=LLM_DISABLED_NOTE, usage=_NO_USAGE, model="null", llm_disabled=True)

    def stream(self, request: GenerationRequest) -> Iterator[StreamChunk]:
        yield StreamChunk(text=LLM_DISABLED_NOTE, llm_disabled=True)
        yield StreamChunk(text="", done=True, usage=_NO_USAGE, llm_disabled=True)

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        # There is no honest vector without a model; callers (knowledge base search) must handle the missing capability.
        raise LLMUnavailableError("Embedding is disabled: the LLM provider is 'null'.")

    def status(self) -> LLMStatus:
        return "disabled"
