"""LLMProvider and EmbeddingProvider contract (LSP): every implementation passes the same tests.

`OllamaProvider` is tested against the real local Ollama (marker `ollama`). The tests run in `make verify` and FAIL,
never skip,
when Ollama is not reachable (P4.1).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from src.app.container import Container, build_container
from src.app.settings import CONFIG_DIR_ENV, load_settings
from src.llm.null_provider import NullProvider
from src.llm.provider import (
    ChatMessage,
    EmbeddingProvider,
    GenerationRequest,
    LLMProvider,
    LLMRequestError,
)
from tests.support.fakes import FakeProvider

CONFIG = Path(__file__).resolve().parents[2] / "config"


def unique_request(max_tokens: int = 16) -> GenerationRequest:
    # A unique prompt keeps Ollama from answering out of its prompt cache (which would report no prompt tokens).
    nonce = uuid.uuid4().hex
    return GenerationRequest(
        messages=(
            ChatMessage("system", "Answer with one short sentence."),
            ChatMessage("user", f"Say hello. Reference {nonce}."),
        ),
        max_tokens=max_tokens,
    )


class LLMProviderContract:
    """Subclasses provide the `provider` fixture."""

    @pytest.fixture
    def provider(self) -> Iterator[LLMProvider]:
        raise NotImplementedError

    def test_generate_returns_text_and_non_negative_token_counts(self, provider: LLMProvider) -> None:
        result = provider.generate(unique_request())

        assert result.text.strip()
        assert result.model
        assert result.usage.prompt_tokens >= 0
        assert result.usage.completion_tokens >= 0

    def test_stream_ends_with_exactly_one_done_chunk_that_carries_the_usage(self, provider: LLMProvider) -> None:
        chunks = list(provider.stream(unique_request()))

        assert chunks
        assert [c.done for c in chunks].count(True) == 1
        assert chunks[-1].done is True
        assert chunks[-1].usage is not None
        assert chunks[-1].usage.completion_tokens >= 0
        assert all(c.usage is None for c in chunks[:-1])
        assert "".join(c.text for c in chunks).strip()

    def test_stream_and_generate_mark_the_same_disabled_state(self, provider: LLMProvider) -> None:
        generated = provider.generate(unique_request())
        streamed = list(provider.stream(unique_request()))

        assert all(c.llm_disabled == generated.llm_disabled for c in streamed)


class RequestValidationContract:
    """Providers that call a model reject a request they cannot send. The null provider never calls one and is not in
    this group."""

    @pytest.fixture
    def provider(self) -> Iterator[LLMProvider]:
        raise NotImplementedError

    def test_a_request_without_messages_is_a_request_error(self, provider: LLMProvider) -> None:
        with pytest.raises(LLMRequestError):
            provider.generate(GenerationRequest(messages=()))


class EmbeddingProviderContract:
    DIMENSIONS: int

    @pytest.fixture
    def embedder(self) -> Iterator[EmbeddingProvider]:
        raise NotImplementedError

    def test_embed_returns_one_vector_of_the_expected_size_per_text_in_order(self, embedder: EmbeddingProvider) -> None:
        result = embedder.embed(["post-quantum migration", "TLS key exchange"])

        assert len(result.vectors) == 2
        assert all(len(v) == self.DIMENSIONS for v in result.vectors)
        assert result.vectors[0] != result.vectors[1]
        assert result.model
        assert result.prompt_tokens >= 0

    def test_embed_is_deterministic_for_the_same_text(self, embedder: EmbeddingProvider) -> None:
        first = embedder.embed(["same text"]).vectors[0]
        second = embedder.embed(["same text"]).vectors[0]

        assert first == pytest.approx(second, abs=1e-3)

    def test_embed_of_no_text_returns_no_vector(self, embedder: EmbeddingProvider) -> None:
        assert embedder.embed([]).vectors == ()


class TestFakeProviderIsAnLLMProvider(LLMProviderContract, RequestValidationContract):
    @pytest.fixture
    def provider(self) -> Iterator[LLMProvider]:
        yield FakeProvider()


class TestNullProviderIsAnLLMProvider(LLMProviderContract):
    @pytest.fixture
    def provider(self) -> Iterator[LLMProvider]:
        yield NullProvider()


class TestFakeProviderIsAnEmbeddingProvider(EmbeddingProviderContract):
    DIMENSIONS = 8

    @pytest.fixture
    def embedder(self) -> Iterator[EmbeddingProvider]:
        yield FakeProvider(dimensions=self.DIMENSIONS)


def _ollama(monkeypatch: pytest.MonkeyPatch) -> Iterator[Container]:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(CONFIG))
    settings = load_settings()
    container = build_container(settings)
    base_url = settings.models.ollama.base_url
    try:
        httpx.get(f"{base_url}/api/tags", timeout=3, trust_env=False).raise_for_status()
    except httpx.HTTPError:
        container.close()
        pytest.fail(f"Ollama is not reachable at {base_url}. Start it (ollama serve) before `make verify`.")
    try:
        yield container
    finally:
        container.close()


@pytest.mark.ollama
class TestOllamaProviderIsAnLLMProvider(LLMProviderContract, RequestValidationContract):
    @pytest.fixture
    def provider(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[LLMProvider]:
        for container in _ollama(monkeypatch):
            yield container.llm


@pytest.mark.ollama
class TestOllamaProviderIsAnEmbeddingProvider(EmbeddingProviderContract):
    DIMENSIONS = 768

    @pytest.fixture
    def embedder(self, monkeypatch: pytest.MonkeyPatch) -> Iterator[EmbeddingProvider]:
        for container in _ollama(monkeypatch):
            yield container.embeddings
