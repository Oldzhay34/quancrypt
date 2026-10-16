"""LLM ports: the only way the rest of the service talks to a language model (D-12, DIP).

This module imports nothing from the service. Adapters (`ollama_provider`, `null_provider`) implement the protocols
and are built in
`src/app/container.py` only.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

Role = Literal["system", "user", "assistant"]
LLMStatus = Literal["ok", "degraded", "disabled"]


class LLMError(Exception):
    """Base class of every error a provider raises."""


class LLMUnavailableError(LLMError):
    """The model server cannot be reached, answered with a server error, or the circuit breaker is open."""


class LLMRequestError(LLMError):
    """The model server rejected the request (4xx, for example an unknown model). Retrying cannot help."""


class LLMProtocolError(LLMError):
    """The model server answered, but not in the shape this adapter expects."""


class LLMStreamInterruptedError(LLMError):
    """A stream broke after it had started. Partial output is not retried (it would repeat tokens)."""


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str


@dataclass(frozen=True)
class GenerationRequest:
    messages: tuple[ChatMessage, ...]
    temperature: float | None = None
    max_tokens: int | None = None


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int


@dataclass(frozen=True)
class GenerationResult:
    text: str
    usage: TokenUsage
    model: str
    # True when no language model produced `text` (NullProvider); callers must show the note as such.
    llm_disabled: bool = False


@dataclass(frozen=True)
class StreamChunk:
    text: str
    done: bool = False
    # Set on the last chunk only.
    usage: TokenUsage | None = None
    llm_disabled: bool = False


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    model: str
    prompt_tokens: int


class LLMProvider(Protocol):
    def generate(self, request: GenerationRequest) -> GenerationResult:
        """Return the complete answer. Raises `LLMError` subclasses."""
        ...

    def stream(self, request: GenerationRequest) -> Iterator[StreamChunk]:
        """Yield text chunks and end with a chunk that has `done=True` and the token usage."""
        ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        """Return one vector per text, in order. Raises `LLMError` subclasses."""
        ...


class LLMHealth(Protocol):
    def status(self) -> LLMStatus:
        """`ok` (usable), `degraded` (configured but not usable) or `disabled` (no model by configuration). Never
        raises."""
        ...
