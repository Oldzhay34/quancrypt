"""Test doubles for the LLM ports. Allowed in tests; production code never imports this module."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator, Sequence

from src.llm.provider import (
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    LLMRequestError,
    LLMStatus,
    StreamChunk,
    TokenUsage,
)


class FakeProvider:
    """Deterministic provider: echoes the last message word by word and embeds by hashing."""

    def __init__(self, dimensions: int = 8, status: LLMStatus = "ok") -> None:
        self._dimensions = dimensions
        self._status: LLMStatus = status

    def generate(self, request: GenerationRequest) -> GenerationResult:
        words = self._words(request)
        return GenerationResult(
            text=" ".join(words),
            usage=TokenUsage(
                prompt_tokens=sum(len(m.content.split()) for m in request.messages), completion_tokens=len(words)
            ),
            model="fake",
        )

    def stream(self, request: GenerationRequest) -> Iterator[StreamChunk]:
        words = self._words(request)
        for index, word in enumerate(words):
            yield StreamChunk(text=word if index == 0 else f" {word}")
        yield StreamChunk(
            text="",
            done=True,
            usage=TokenUsage(
                prompt_tokens=sum(len(m.content.split()) for m in request.messages), completion_tokens=len(words)
            ),
        )

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        vectors = tuple(self._vector(text) for text in texts)
        return EmbeddingResult(
            vectors=vectors, model="fake-embedding", prompt_tokens=sum(len(t.split()) for t in texts)
        )

    def status(self) -> LLMStatus:
        return self._status

    def _words(self, request: GenerationRequest) -> list[str]:
        if not request.messages:
            raise LLMRequestError("A generation request needs at least one message.")
        return ["fake", *request.messages[-1].content.split()][: request.max_tokens or 64]

    def _vector(self, text: str) -> tuple[float, ...]:
        digest = hashlib.sha256(text.encode()).digest()
        return tuple(digest[i % len(digest)] / 255 for i in range(self._dimensions))
