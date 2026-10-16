"""OllamaProvider against a scripted HTTP transport: request shape, token counts, retries, circuit breaker and health.

No Ollama server is involved; the tests marked `ollama` live in tests/contract.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from src.llm.ollama_provider import OllamaProvider, OllamaProviderConfig
from src.llm.provider import (
    ChatMessage,
    GenerationRequest,
    LLMProtocolError,
    LLMRequestError,
    LLMStreamInterruptedError,
    LLMUnavailableError,
)

REQUEST = GenerationRequest(messages=(ChatMessage("system", "be brief"), ChatMessage("user", "hello")))

Step = Callable[[httpx.Request], httpx.Response | Exception] | httpx.Response | Exception


def make_config(**overrides: Any) -> OllamaProviderConfig:
    values: dict[str, Any] = {
        "base_url": "http://127.0.0.1:11434",
        "chat_model": "gemma3:4b",
        "embedding_model": "embeddinggemma:latest",
        "embedding_dimensions": 3,
        "temperature": 0.2,
        "num_ctx": 8192,
        "num_predict": 1024,
        "connect_timeout_s": 1,
        "timeout_s": 5,
        "retry_max_attempts": 3,
        "retry_wait_initial_s": 0.001,
        "retry_wait_max_s": 0.002,
        "breaker_fail_max": 3,
        "breaker_reset_timeout_s": 0.3,
        "health_timeout_s": 1,
        "health_cache_s": 5,
    }
    values.update(overrides)
    return OllamaProviderConfig(**values)


class Server:
    """Scripted transport: each call pops the next step (the last step repeats); every request is recorded."""

    def __init__(self, *script: Step) -> None:
        self._script = list(script)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        step = self._script.pop(0) if len(self._script) > 1 else self._script[0]
        outcome = step(request) if callable(step) else step
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def provider(self, **overrides: Any) -> OllamaProvider:
        return OllamaProvider(make_config(**overrides), transport=httpx.MockTransport(self), sleep=lambda _: None)


def chat_ok(text: str = "hi", prompt: int = 7, completion: int = 2) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "message": {"role": "assistant", "content": text},
            "done": True,
            "prompt_eval_count": prompt,
            "eval_count": completion,
        },
    )


def ndjson(*objects: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, content="".join(json.dumps(o) + "\n" for o in objects).encode())


# ---- generate ----


def test_generate_sends_the_model_messages_and_explicit_limits_and_reads_the_token_counts() -> None:
    server = Server(chat_ok("pong", prompt=11, completion=3))

    result = server.provider().generate(REQUEST)

    assert (result.text, result.model) == ("pong", "gemma3:4b")
    assert (result.usage.prompt_tokens, result.usage.completion_tokens) == (11, 3)
    body = json.loads(server.requests[0].content)
    assert server.requests[0].url.path == "/api/chat"
    assert body["model"] == "gemma3:4b"
    assert body["stream"] is False
    assert body["messages"] == [{"role": "system", "content": "be brief"}, {"role": "user", "content": "hello"}]
    assert body["options"] == {"temperature": 0.2, "num_ctx": 8192, "num_predict": 1024}


def test_a_request_overrides_temperature_and_output_limit() -> None:
    server = Server(chat_ok())

    server.provider().generate(GenerationRequest(messages=REQUEST.messages, temperature=0.0, max_tokens=16))

    options = json.loads(server.requests[0].content)["options"]
    assert (options["temperature"], options["num_predict"]) == (0.0, 16)


def test_a_missing_token_count_is_zero_and_never_an_estimate() -> None:
    server = Server(httpx.Response(200, json={"message": {"role": "assistant", "content": "x"}, "done": True}))

    usage = server.provider().generate(REQUEST).usage

    assert (usage.prompt_tokens, usage.completion_tokens) == (0, 0)


@pytest.mark.parametrize(
    "request_",
    [
        GenerationRequest(messages=()),
        GenerationRequest(messages=REQUEST.messages, max_tokens=0),
        GenerationRequest(messages=REQUEST.messages, max_tokens=8193),
        GenerationRequest(messages=REQUEST.messages, temperature=-0.1),
        GenerationRequest(messages=REQUEST.messages, temperature=2.5),
    ],
)
def test_an_invalid_request_is_rejected_before_any_call(request_: GenerationRequest) -> None:
    server = Server(chat_ok())

    with pytest.raises(LLMRequestError):
        server.provider().generate(request_)

    assert server.requests == []


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, json=[1, 2]),
        httpx.Response(200, json={"done": True}),
        httpx.Response(200, json={"message": {"content": 5}}),
    ],
)
def test_an_answer_in_the_wrong_shape_is_a_protocol_error(response: httpx.Response) -> None:
    with pytest.raises(LLMProtocolError):
        Server(response).provider().generate(REQUEST)


# ---- retry ----


def test_a_server_error_is_retried_and_the_next_answer_is_used() -> None:
    server = Server(httpx.Response(503), httpx.ConnectError("refused"), chat_ok("third time"))

    result = server.provider().generate(REQUEST)

    assert result.text == "third time"
    assert len(server.requests) == 3


def test_retries_stop_at_the_configured_attempts() -> None:
    server = Server(httpx.Response(500))

    with pytest.raises(LLMUnavailableError):
        server.provider(retry_max_attempts=2).generate(REQUEST)

    assert len(server.requests) == 2


def test_a_read_timeout_is_not_retried() -> None:
    server = Server(httpx.ReadTimeout("slow"))

    with pytest.raises(LLMUnavailableError, match="in time"):
        server.provider().generate(REQUEST)

    assert len(server.requests) == 1


def test_a_client_error_is_not_retried_and_does_not_copy_the_server_text() -> None:
    server = Server(httpx.Response(400, json={"error": "template error near: my-secret-prompt-text"}))

    with pytest.raises(LLMRequestError, match="rejected the request") as raised:
        server.provider().generate(REQUEST)

    assert "secret" not in str(raised.value)

    assert len(server.requests) == 1


# ---- circuit breaker ----


def test_the_breaker_opens_after_fail_max_failed_operations_and_then_fails_fast() -> None:
    server = Server(httpx.ConnectError("refused"))
    provider = server.provider(breaker_fail_max=2, retry_max_attempts=1)

    for _ in range(2):
        with pytest.raises(LLMUnavailableError):
            provider.generate(REQUEST)
    calls_when_open = len(server.requests)

    with pytest.raises(LLMUnavailableError, match="circuit breaker is open"):
        provider.generate(REQUEST)

    assert len(server.requests) == calls_when_open


def test_the_breaker_closes_again_after_the_reset_timeout_when_the_server_is_back() -> None:
    server = Server(httpx.ConnectError("refused"), httpx.ConnectError("refused"), chat_ok("back"))
    provider = server.provider(breaker_fail_max=2, retry_max_attempts=1, breaker_reset_timeout_s=0.2)
    for _ in range(2):
        with pytest.raises(LLMUnavailableError):
            provider.generate(REQUEST)

    time.sleep(0.3)

    assert provider.generate(REQUEST).text == "back"
    assert provider.generate(REQUEST).text == "back"


def test_rejected_requests_do_not_open_the_breaker() -> None:
    server = Server(httpx.Response(400, json={"error": "bad"}))
    provider = server.provider(breaker_fail_max=2)

    for _ in range(5):
        with pytest.raises(LLMRequestError):
            provider.generate(REQUEST)

    assert len(server.requests) == 5


# ---- stream ----


def test_stream_yields_text_chunks_and_a_final_chunk_with_the_token_counts() -> None:
    server = Server(
        ndjson(
            {"message": {"role": "assistant", "content": "Hel"}, "done": False},
            {"message": {"role": "assistant", "content": "lo"}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True, "prompt_eval_count": 5, "eval_count": 2},
        )
    )

    chunks = list(server.provider().stream(REQUEST))

    assert [c.text for c in chunks] == ["Hel", "lo", ""]
    assert [c.done for c in chunks] == [False, False, True]
    assert chunks[-1].usage is not None
    assert (chunks[-1].usage.prompt_tokens, chunks[-1].usage.completion_tokens) == (5, 2)
    assert json.loads(server.requests[0].content)["stream"] is True


def test_opening_a_stream_is_retried_but_a_stream_that_ends_early_is_an_error() -> None:
    server = Server(httpx.Response(502), ndjson({"message": {"content": "a"}, "done": False}))

    stream: Iterator[Any] = server.provider().stream(REQUEST)

    assert next(stream).text == "a"
    with pytest.raises(LLMStreamInterruptedError, match="without a final chunk"):
        next(stream)
    assert len(server.requests) == 2


def test_an_error_line_inside_a_stream_ends_it_as_interrupted() -> None:
    server = Server(ndjson({"message": {"content": "a"}, "done": False}, {"error": "out of memory"}))

    with pytest.raises(LLMStreamInterruptedError):
        list(server.provider().stream(REQUEST))


def test_a_stream_the_server_rejects_raises_the_request_error_on_first_iteration() -> None:
    server = Server(httpx.Response(404, json={"error": "model not found"}))

    with pytest.raises(LLMRequestError, match="rejected the request"):
        list(server.provider().stream(REQUEST))


# ---- embeddings ----


def test_embed_sends_untruncated_input_and_returns_one_vector_per_text() -> None:
    server = Server(httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3], [1, 2, 3]], "prompt_eval_count": 9}))

    result = server.provider().embed(["a", "b"])

    assert result.vectors == ((0.1, 0.2, 0.3), (1.0, 2.0, 3.0))
    assert (result.model, result.prompt_tokens) == ("embeddinggemma:latest", 9)
    body = json.loads(server.requests[0].content)
    assert body == {"model": "embeddinggemma:latest", "input": ["a", "b"], "truncate": False}


def test_embed_of_nothing_makes_no_call() -> None:
    server = Server(httpx.Response(200, json={}))

    assert server.provider().embed([]).vectors == ()
    assert server.requests == []


@pytest.mark.parametrize(
    "answer",
    [
        {"embeddings": [[0.1, 0.2]]},
        {"embeddings": []},
        {"embeddings": [[0.1, 0.2, "x"]]},
        {"embeddings": [[True, False, True]]},
        {},
    ],
)
def test_an_embedding_of_the_wrong_size_or_type_is_a_protocol_error(answer: dict[str, Any]) -> None:
    with pytest.raises(LLMProtocolError):
        Server(httpx.Response(200, json=answer)).provider().embed(["a"])


# ---- health ----


def tags(*names: str) -> httpx.Response:
    return httpx.Response(200, json={"models": [{"name": n} for n in names]})


def test_status_is_ok_when_ollama_answers_and_both_models_are_installed() -> None:
    assert Server(tags("gemma3:4b", "embeddinggemma:latest", "qwen3:4b")).provider().status() == "ok"


def test_status_is_degraded_when_a_model_is_missing_or_ollama_is_down_or_answers_garbage() -> None:
    assert Server(tags("gemma3:4b")).provider().status() == "degraded"
    assert Server(httpx.ConnectError("refused")).provider().status() == "degraded"
    assert Server(httpx.Response(500)).provider().status() == "degraded"
    assert Server(httpx.Response(200, content=b"nope")).provider().status() == "degraded"
    assert Server(httpx.Response(200, json={"models": "x"})).provider().status() == "degraded"


def test_status_is_cached_for_the_configured_time_and_probed_again_afterwards() -> None:
    now = [100.0]
    server = Server(tags("gemma3:4b", "embeddinggemma:latest"), httpx.ConnectError("gone"))
    provider = OllamaProvider(
        make_config(health_cache_s=5),
        transport=httpx.MockTransport(server),
        clock=lambda: now[0],
        sleep=lambda _: None,
    )

    assert provider.status() == "ok"
    now[0] = 104.0
    assert provider.status() == "ok"
    assert len(server.requests) == 1
    now[0] = 105.5
    assert provider.status() == "degraded"
    assert len(server.requests) == 2


def test_status_recovers_even_while_the_breaker_is_open() -> None:
    server = Server(httpx.ConnectError("refused"), tags("gemma3:4b", "embeddinggemma:latest"))
    provider = server.provider(breaker_fail_max=1, retry_max_attempts=1, health_cache_s=0)
    with pytest.raises(LLMUnavailableError):
        provider.generate(REQUEST)

    assert provider.status() == "ok"


def test_concurrent_status_callers_do_not_pile_up_behind_a_hung_probe() -> None:
    import threading

    started, release = threading.Event(), threading.Event()

    def slow(_: httpx.Request) -> httpx.Response:
        started.set()
        release.wait(5)
        return tags("gemma3:4b", "embeddinggemma:latest")

    provider = Server(slow).provider(health_cache_s=0)
    first: list[str] = []
    thread = threading.Thread(target=lambda: first.append(provider.status()))
    thread.start()
    assert started.wait(5)

    # A second caller does not wait for the running probe; before any result it reports degraded.
    assert provider.status() == "degraded"

    release.set()
    thread.join(5)
    assert first == ["ok"]
