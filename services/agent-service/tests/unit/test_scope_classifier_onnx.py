"""Ring 2 with Model B (P7.5, D-344d): the band of the thresholds file, the confidence, the digest check and the ring's
place in the chain. The ONNX head is a test double here; tests/integration/test_onnx_models.py runs the real one."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from src.guardrails.chain import GuardChain, GuardRequest, RingVerdict
from src.guardrails.scope_classifier import OnnxScopeClassifier, ScopeBand
from src.llm.provider import EmbeddingResult, LLMUnavailableError

DIGEST = "a" * 64
BAND = ScopeBand(0.03, 0.43)


class FixedHead:
    def __init__(self, p: float) -> None:
        self.p = p
        self.seen: list[Sequence[Sequence[float]]] = []

    def p_out(self, vectors: Sequence[Sequence[float]]) -> list[float]:
        self.seen.append(vectors)
        return [self.p for _ in vectors]


class Embeddings:
    def __init__(self, down: bool = False) -> None:
        self.down = down
        self.texts: list[str] = []

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        if self.down:
            raise LLMUnavailableError("embedding model down")
        self.texts.extend(texts)
        return EmbeddingResult(tuple((0.1, 0.2, 0.3) for _ in texts), "embeddinggemma:latest", 3)


def ring(p: float, installed: str | None = DIGEST, embeddings: Embeddings | None = None) -> OnnxScopeClassifier:
    return OnnxScopeClassifier(embeddings or Embeddings(), FixedHead(p), BAND, DIGEST, lambda: installed)


def request(text: str = "Projemde RSA nerede?") -> GuardRequest:
    return GuardRequest(text=text, language="tr")


@pytest.mark.parametrize(
    ("p", "verdict"),
    [
        (0.0, RingVerdict("ALLOW", 1.0)),
        (0.02999, RingVerdict("ALLOW", 0.97)),
        (0.03, RingVerdict("UNSURE")),  # the lower bound itself is in the band
        (0.2, RingVerdict("UNSURE")),
        (0.42999, RingVerdict("UNSURE")),
        (0.43, RingVerdict("DENY", 0.43)),  # the upper bound denies
        (0.98765, RingVerdict("DENY", 0.9877)),
    ],
)
def test_the_band_decides_and_only_a_decision_carries_a_confidence(p: float, verdict: RingVerdict) -> None:
    assert ring(p).check(request()) == verdict


def test_the_request_text_is_embedded_and_given_to_the_head() -> None:
    embeddings = Embeddings()
    classifier = OnnxScopeClassifier(embeddings, FixedHead(0.5), BAND, DIGEST, lambda: DIGEST)
    classifier.check(request("Hangi servisler TLS kullanıyor?"))
    assert embeddings.texts == ["Hangi servisler TLS kullanıyor?"]
    assert classifier.name == "SCOPE_CLASSIFIER"


@pytest.mark.parametrize("p", [float("nan"), -0.01, 1.01])
def test_a_probability_outside_zero_to_one_is_an_error(p: float) -> None:
    with pytest.raises(ValueError, match="outside 0..1"):
        ring(p).check(request())


def test_another_embedding_model_or_an_unreadable_digest_is_an_error_until_the_right_one_answers() -> None:
    with pytest.raises(RuntimeError, match="not the one"):
        ring(0.0, installed="b" * 64).check(request())
    with pytest.raises(RuntimeError, match="cannot be read"):
        ring(0.0, installed=None).check(request())
    answers = iter([None, DIGEST])
    classifier = OnnxScopeClassifier(Embeddings(), FixedHead(0.0), BAND, DIGEST, lambda: next(answers))
    with pytest.raises(RuntimeError):
        classifier.check(request())
    assert classifier.check(request()).verdict == "ALLOW"
    assert classifier.check(request()).verdict == "ALLOW"  # checked once; the iterator would be exhausted otherwise


class Ring:
    def __init__(self, name: str, verdict: RingVerdict) -> None:
        self._name = name
        self._verdict = verdict
        self.calls = 0

    @property
    def name(self) -> str:
        return self._name

    def check(self, request: GuardRequest) -> RingVerdict:
        self.calls += 1
        return self._verdict


def test_in_the_chain_model_b_decides_after_the_rule_filter_and_before_the_self_check() -> None:
    rule, self_check = Ring("RULE_FILTER", RingVerdict("UNSURE")), Ring("LLM_SELF_CHECK", RingVerdict("ALLOW"))
    decided = GuardChain([rule, ring(0.01), self_check]).decide(request())  # type: ignore[list-item]
    assert (decided.decision, decided.deciding_ring, decided.confidence) == ("ALLOW", "SCOPE_CLASSIFIER", 0.99)
    assert (rule.calls, self_check.calls) == (1, 0)

    unsure = GuardChain([rule, ring(0.2), self_check]).decide(request())  # type: ignore[list-item]
    assert (unsure.deciding_ring, self_check.calls) == ("LLM_SELF_CHECK", 1)

    denied = GuardChain([Ring("RULE_FILTER", RingVerdict("DENY")), ring(0.01), self_check]).decide(request())  # type: ignore[list-item]
    assert denied.deciding_ring == "RULE_FILTER"


def test_an_unreachable_embedding_model_makes_the_chain_fail_closed() -> None:
    decided = GuardChain([ring(0.01, embeddings=Embeddings(down=True))]).decide(request())
    assert (decided.decision, decided.deciding_ring, decided.confidence) == ("DENY", "FAIL_CLOSED", None)


def test_a_band_must_be_ordered_inside_zero_to_one() -> None:
    with pytest.raises(ValueError):
        ScopeBand(0.5, 0.4)
    with pytest.raises(ValueError):
        ScopeBand(-0.1, 0.4)
