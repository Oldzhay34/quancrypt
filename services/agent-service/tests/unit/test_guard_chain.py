"""The scope keeper chain: the first ALLOW or DENY decides, everything else is DENY by FAIL_CLOSED (guardrails-security
section 2); the decision never carries the request text."""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Iterator

import pytest

from src.guardrails.chain import (
    GuardChain,
    GuardDecision,
    GuardRequest,
    RingName,
    RingVerdict,
    Verdict,
    detect_language,
)

SECRET_REQUEST = "projemdeki RSA anahtarı hakkında gizli-istek-metni-123"


class StubRing:
    def __init__(self, name: RingName, verdict: Verdict, confidence: float | None = None) -> None:
        self._name = name
        self._verdict = RingVerdict(verdict, confidence)
        self.calls = 0

    @property
    def name(self) -> RingName:
        return self._name

    def check(self, request: GuardRequest) -> RingVerdict:
        self.calls += 1
        return self._verdict


class FailingRing:
    @property
    def name(self) -> RingName:
        return "LLM_SELF_CHECK"

    def check(self, request: GuardRequest) -> RingVerdict:
        raise RuntimeError(request.text)  # an error message that would leak the request if logged


def ticking_clock() -> Iterator[float]:
    value = 0.0
    while True:
        yield value
        value += 0.25


def decide(*rings: StubRing | FailingRing) -> GuardDecision:
    clock = ticking_clock()
    return GuardChain(rings, clock=lambda: next(clock)).decide(GuardRequest(SECRET_REQUEST, "tr"))


def test_every_ring_unsure_is_deny_by_fail_closed() -> None:
    decision = decide(StubRing("RULE_FILTER", "UNSURE"), StubRing("LLM_SELF_CHECK", "UNSURE"))

    assert (decision.decision, decision.deciding_ring, decision.confidence) == ("DENY", "FAIL_CLOSED", None)
    assert not decision.allowed


def test_no_rings_is_deny_by_fail_closed() -> None:
    assert decide().deciding_ring == "FAIL_CLOSED"


def test_the_first_certain_verdict_decides_and_later_rings_do_not_run() -> None:
    later = StubRing("LLM_SELF_CHECK", "ALLOW")
    decision = decide(StubRing("RULE_FILTER", "DENY"), later)

    assert (decision.decision, decision.deciding_ring) == ("DENY", "RULE_FILTER")
    assert later.calls == 0


def test_an_unsure_ring_passes_the_request_on() -> None:
    decision = decide(StubRing("RULE_FILTER", "UNSURE"), StubRing("SCOPE_CLASSIFIER", "ALLOW", 0.93))

    assert (decision.decision, decision.deciding_ring, decision.confidence) == ("ALLOW", "SCOPE_CLASSIFIER", 0.93)
    assert decision.allowed


def test_a_failing_ring_denies_and_logs_only_the_error_class(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.DEBUG):
        decision = decide(StubRing("RULE_FILTER", "UNSURE"), FailingRing())

    assert (decision.decision, decision.deciding_ring) == ("DENY", "FAIL_CLOSED")
    assert any("RuntimeError" in message for message in caplog.messages)
    assert all(SECRET_REQUEST not in message for message in caplog.messages)


def test_the_decision_carries_latency_and_language_but_never_the_request_text() -> None:
    decision = decide(StubRing("RULE_FILTER", "DENY"))

    assert decision.latency_ms == 250  # one tick of the test clock
    assert decision.language == "tr"
    assert {field.name for field in dataclasses.fields(GuardDecision)} == {
        "decision",
        "confidence",
        "deciding_ring",
        "latency_ms",
        "language",
    }
    assert SECRET_REQUEST not in repr(decision)
    assert SECRET_REQUEST not in repr(GuardRequest(SECRET_REQUEST, "tr"))


TR_WORDS = frozenset({"ve", "bir", "bu", "nedir", "nasıl", "projemde"})
EN_WORDS = frozenset({"the", "and", "is", "what", "how", "my", "project"})


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Projemde RSA hangi dosyalarda kullanılıyor?", "tr"),
        ("ML-KEM nedir", "tr"),
        ("What is ML-KEM and how is it used in my project?", "en"),
        ("TLS", "tr"),  # undecided is Turkish (D-242b)
        ("", "tr"),
        ("Which files use RSA in the project?", "en"),
        ("Şifreleme what", "tr"),  # a Turkish letter outweighs one English word
    ],
)
def test_language_detection(text: str, language: str) -> None:
    assert detect_language(text, TR_WORDS, EN_WORDS) == language


def test_a_chain_without_the_scope_classifier_logs_that_ring_2_is_absent(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="src.guardrails"):
        GuardChain([StubRing("RULE_FILTER", "UNSURE"), StubRing("LLM_SELF_CHECK", "UNSURE")])
        absent = list(caplog.messages)
        caplog.clear()
        GuardChain([StubRing("RULE_FILTER", "UNSURE"), StubRing("SCOPE_CLASSIFIER", "UNSURE")])

    assert any("scope classifier ring (Model B) is not in the chain" in message for message in absent)
    assert not any("scope classifier" in message for message in caplog.messages)
