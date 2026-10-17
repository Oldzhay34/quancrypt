"""Ring 3: temperature 0, the exact label or DENY; without a model UNSURE, so the chain denies (D-242c)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.guardrails.chain import GuardChain, GuardRequest
from src.guardrails.llm_self_check import LLMSelfCheck
from src.llm.null_provider import NullProvider
from src.llm.provider import (
    GenerationRequest,
    GenerationResult,
    LLMRequestError,
    LLMUnavailableError,
    StreamChunk,
    TokenUsage,
)
from src.prompts.system_prompts import SCOPE_SELF_CHECK

REQUEST = GuardRequest("Projemde RSA nerede kullanılıyor?", "tr")


class ScriptedLLM:
    """Answers with a fixed text or raises; remembers the requests it saw."""

    def __init__(self, answer: str | Exception) -> None:
        self._answer = answer
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if isinstance(self._answer, Exception):
            raise self._answer
        return GenerationResult(self._answer, TokenUsage(10, 1), "test-model")

    def stream(self, request: GenerationRequest) -> Iterator[StreamChunk]:
        raise NotImplementedError


@pytest.mark.parametrize(
    ("answer", "verdict"),
    [
        ("IN_SCOPE", "ALLOW"),
        ("OUT_OF_SCOPE", "DENY"),
        ("  IN_SCOPE\n", "ALLOW"),
        ("IN_SCOPE.", "DENY"),
        ("in_scope", "DENY"),
        ("IN_SCOPE because it is about RSA", "DENY"),
        ("Sure! IN_SCOPE", "DENY"),
        ("", "DENY"),
    ],
)
def test_only_the_exact_label_allows(answer: str, verdict: str) -> None:
    assert LLMSelfCheck(ScriptedLLM(answer), 8).check(REQUEST).verdict == verdict


def test_the_request_goes_as_the_user_message_at_temperature_zero() -> None:
    llm = ScriptedLLM("IN_SCOPE")
    LLMSelfCheck(llm, 8).check(REQUEST)

    [request] = llm.requests
    assert request.temperature == 0
    assert request.max_tokens == 8
    assert [(m.role, m.content) for m in request.messages] == [
        ("system", SCOPE_SELF_CHECK.text),
        ("user", REQUEST.text),
    ]


@pytest.mark.parametrize("error", [LLMUnavailableError("down"), LLMRequestError("unknown model")])
def test_an_unavailable_model_is_unsure(error: Exception) -> None:
    assert LLMSelfCheck(ScriptedLLM(error), 8).check(REQUEST).verdict == "UNSURE"


def test_without_a_model_the_ring_is_unsure_and_the_chain_denies() -> None:
    ring = LLMSelfCheck(NullProvider(), 8)

    assert ring.check(REQUEST).verdict == "UNSURE"
    decision = GuardChain([ring]).decide(REQUEST)
    assert (decision.decision, decision.deciding_ring) == ("DENY", "FAIL_CLOSED")
