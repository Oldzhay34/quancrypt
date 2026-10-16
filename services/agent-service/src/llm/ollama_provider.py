"""Ollama adapter: `LLMProvider`, `EmbeddingProvider` and `LLMHealth` over the local Ollama HTTP API (D-12, NFR-05).

Every model call has a timeout, `tenacity` retries and a `pybreaker` circuit breaker (the health probe has a short
timeout only). The retry sits inside the breaker, so one failed operation (all attempts used) counts as one failure.
For a stream, the breaker and the retry cover opening the connection and the first response (status line and headers)
only: a stream that breaks later is not retried (that would repeat tokens) and ends with `LLMStreamInterruptedError`.
Token counts come from the response (`prompt_eval_count`, `eval_count`); a missing count is 0, never an estimate.
Prompts, answers and the server's own error texts are never logged or copied into messages.

The adapter takes plain values (`OllamaProviderConfig`) and imports nothing from the service except `src.llm.provider`.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
import pybreaker
from tenacity import RetryCallState, Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.llm.provider import (
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    LLMProtocolError,
    LLMRequestError,
    LLMStatus,
    LLMStreamInterruptedError,
    LLMUnavailableError,
    StreamChunk,
    TokenUsage,
)

_LOG = logging.getLogger("src.llm.ollama")


@dataclass(frozen=True)
class OllamaProviderConfig:
    base_url: str
    chat_model: str
    embedding_model: str
    embedding_dimensions: int
    temperature: float
    num_ctx: int
    num_predict: int
    connect_timeout_s: float
    timeout_s: float
    retry_max_attempts: int
    retry_wait_initial_s: float
    retry_wait_max_s: float
    breaker_fail_max: int
    breaker_reset_timeout_s: float
    health_timeout_s: float
    health_cache_s: float


class _TransientError(LLMUnavailableError):
    """A failure worth retrying: the connection failed or the server answered 5xx or 429."""


class _BreakerLogger(pybreaker.CircuitBreakerListener):
    def state_change(self, cb: pybreaker.CircuitBreaker, old_state: Any, new_state: Any) -> None:
        _LOG.warning("Circuit breaker %s: %s -> %s", cb.name, old_state.name, new_state.name)


class OllamaProvider:
    def __init__(
        self,
        config: OllamaProviderConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._clock = clock
        # No proxy variables (trust_env=False) and no redirects: the only peer is the configured Ollama address.
        self._client = httpx.Client(
            base_url=config.base_url,
            timeout=httpx.Timeout(config.timeout_s, connect=config.connect_timeout_s),
            transport=transport,
            trust_env=False,
            follow_redirects=False,
        )
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=config.breaker_fail_max,
            reset_timeout=config.breaker_reset_timeout_s,
            # A rejected or malformed request says nothing about availability.
            exclude=[LLMRequestError, LLMProtocolError],
            listeners=[_BreakerLogger()],
            name="ollama",
        )
        self._retrying = Retrying(
            stop=stop_after_attempt(config.retry_max_attempts),
            wait=wait_exponential(multiplier=config.retry_wait_initial_s, max=config.retry_wait_max_s),
            retry=retry_if_exception_type(_TransientError),
            before_sleep=self._log_retry,
            sleep=sleep,
            reraise=True,
        )
        self._health_lock = threading.Lock()
        self._probe_lock = threading.Lock()
        self._health_cached: tuple[float, LLMStatus] | None = None

    # ---- LLMProvider ----

    def generate(self, request: GenerationRequest) -> GenerationResult:
        data = self._call(self._post_json, "/api/chat", self._chat_payload(request, stream=False))
        message = data.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str):
            raise LLMProtocolError("Ollama chat response has no message content.")
        return GenerationResult(text=content, usage=_usage(data), model=self._config.chat_model)

    def stream(self, request: GenerationRequest) -> Iterator[StreamChunk]:
        payload = self._chat_payload(request, stream=True)
        response = self._call(self._open_stream, "/api/chat", payload)
        finished = False
        try:
            for line in response.iter_lines():
                if not line:
                    continue
                data = _parse_json_object(line)
                if "error" in data:
                    raise LLMStreamInterruptedError("Ollama reported an error during the stream.")
                message = data.get("message")
                text = message.get("content", "") if isinstance(message, dict) else ""
                if not isinstance(text, str):
                    raise LLMProtocolError("Ollama stream chunk has a non-text content.")
                if text:
                    yield StreamChunk(text=text)
                if data.get("done") is True:
                    finished = True
                    yield StreamChunk(text="", done=True, usage=_usage(data))
                    break
        except httpx.HTTPError as exc:
            raise LLMStreamInterruptedError("The connection to Ollama broke during the stream.") from exc
        finally:
            response.close()
        if not finished:
            raise LLMStreamInterruptedError("The Ollama stream ended without a final chunk.")

    # ---- EmbeddingProvider ----

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        items = list(texts)
        model = self._config.embedding_model
        if not items:
            return EmbeddingResult(vectors=(), model=model, prompt_tokens=0)
        # truncate=false: an input longer than the model context is an error, never a silently shortened vector.
        data = self._call(self._post_json, "/api/embed", {"model": model, "input": items, "truncate": False})
        raw = data.get("embeddings")
        if not isinstance(raw, list) or len(raw) != len(items):
            raise LLMProtocolError("Ollama embed response does not hold one vector per input.")
        vectors: list[tuple[float, ...]] = []
        for vector in raw:
            if (
                not isinstance(vector, list)
                or len(vector) != self._config.embedding_dimensions
                or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in vector)
            ):
                raise LLMProtocolError(
                    f"Ollama embed response has a vector that is not {self._config.embedding_dimensions} numbers long."
                )
            vectors.append(tuple(float(v) for v in vector))
        return EmbeddingResult(vectors=tuple(vectors), model=model, prompt_tokens=_count(data, "prompt_eval_count"))

    # ---- LLMHealth ----

    def status(self) -> LLMStatus:
        """Reachable and both configured models installed: `ok`; anything else: `degraded`.

        The result comes from a probe (`GET /api/tags`), not from the breaker state: a breaker only leaves `open` on a
        real call, so
        its state alone would never heal on an idle service. The probe result is cached for `health_cache_s` seconds.
        """
        now = self._clock()
        with self._health_lock:
            cached = self._health_cached
        if cached is not None and now - cached[0] < self._config.health_cache_s:
            return cached[1]
        # One probe at a time: concurrent callers that find a probe running return the last known value at once (or
        # `degraded` before the first probe), so a hung Ollama cannot pile up request threads on the readiness endpoint.
        if not self._probe_lock.acquire(blocking=False):
            return cached[1] if cached is not None else "degraded"
        try:
            result = self._probe()
            with self._health_lock:
                self._health_cached = (now, result)
            return result
        finally:
            self._probe_lock.release()

    def close(self) -> None:
        self._client.close()

    # ---- internals ----

    def _probe(self) -> LLMStatus:
        timeout = httpx.Timeout(self._config.health_timeout_s)
        try:
            response = self._client.get("/api/tags", timeout=timeout)
            response.raise_for_status()
            models = response.json().get("models", [])
            installed = {m.get("name") for m in models if isinstance(m, dict)}
        except (httpx.HTTPError, ValueError, AttributeError):
            return "degraded"
        wanted = {self._config.chat_model, self._config.embedding_model}
        return "ok" if wanted <= installed else "degraded"

    def _chat_payload(self, request: GenerationRequest, *, stream: bool) -> dict[str, Any]:
        if not request.messages:
            raise LLMRequestError("A generation request needs at least one message.")
        if request.max_tokens is not None and not 1 <= request.max_tokens <= self._config.num_ctx:
            raise LLMRequestError("max_tokens must be between 1 and the context size.")
        if request.temperature is not None and not 0 <= request.temperature <= 2:
            raise LLMRequestError("temperature must be between 0 and 2.")
        options = {
            "temperature": self._config.temperature if request.temperature is None else request.temperature,
            "num_ctx": self._config.num_ctx,
            "num_predict": self._config.num_predict if request.max_tokens is None else request.max_tokens,
        }
        return {
            "model": self._config.chat_model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "stream": stream,
            "options": options,
        }

    def _call(self, operation: Callable[[str, dict[str, Any]], Any], path: str, payload: dict[str, Any]) -> Any:
        try:
            return self._breaker.call(self._retrying, operation, path, payload)
        except pybreaker.CircuitBreakerError as exc:
            raise LLMUnavailableError("The Ollama circuit breaker is open.") from exc

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise _translate(exc) from exc
        _raise_for_status(response)
        return _parse_json_object(response.content)

    def _open_stream(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        request = self._client.build_request("POST", path, json=payload)
        try:
            response = self._client.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise _translate(exc) from exc
        try:
            _raise_for_status(response)
        except BaseException:
            response.close()
            raise
        return response

    def _log_retry(self, state: RetryCallState) -> None:
        outcome = state.outcome
        error = type(outcome.exception()).__name__ if outcome is not None and outcome.failed else "unknown"
        _LOG.warning("Ollama call failed (%s); attempt %d, retrying", error, state.attempt_number)


def _translate(exc: httpx.HTTPError) -> LLMUnavailableError:
    """A connection failure is retried; a timeout on a started request is not (it would multiply a long wait)."""
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout | httpx.RemoteProtocolError):
        return _TransientError("Ollama is not reachable.")
    if isinstance(exc, httpx.TimeoutException):
        return LLMUnavailableError("Ollama did not answer in time.")
    return _TransientError("The request to Ollama failed.")


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status < 400:
        return
    response.read()
    if status >= 500 or status == 429:
        raise _TransientError(f"Ollama answered {status}.")
    # The server's own error text is not copied: it can quote parts of the request (templates, parsing errors).
    raise LLMRequestError(f"Ollama rejected the request ({status}).")


def _parse_json_object(raw: str | bytes) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise LLMProtocolError("Ollama answered with invalid JSON.") from exc
    if not isinstance(data, dict):
        raise LLMProtocolError("Ollama answered with JSON that is not an object.")
    return data


def _count(data: dict[str, Any], key: str) -> int:
    value = data.get(key, 0)
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _usage(data: dict[str, Any]) -> TokenUsage:
    return TokenUsage(prompt_tokens=_count(data, "prompt_eval_count"), completion_tokens=_count(data, "eval_count"))
