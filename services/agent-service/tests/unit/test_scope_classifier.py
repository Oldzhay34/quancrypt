"""The interim ring 2, the embedding topic gate (D-246): far from every anchor is DENY, near is UNSURE, never ALLOW;
an unreachable embedding model ends the chain in FAIL_CLOSED."""

from __future__ import annotations

from collections.abc import Sequence

import pytest

from src.guardrails.chain import GuardChain, GuardRequest
from src.guardrails.scope_classifier import EmbeddingTopicGate
from src.llm.null_provider import NullProvider
from src.llm.provider import EmbeddingResult

VECTORS = {
    "anchor crypto": (1.0, 0.0, 0.0),
    "anchor tls": (0.0, 1.0, 0.0),
    "RSA question": (0.9, 0.1, 0.0),
    "football question": (0.0, 0.0, 1.0),
    "borderline": (0.4, 0.0, 0.9),
}


class TableEmbeddings:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        self.calls.append(tuple(texts))
        return EmbeddingResult(tuple(VECTORS[text] for text in texts), "table", 0)


def gate(threshold: float = 0.4) -> tuple[EmbeddingTopicGate, TableEmbeddings]:
    embeddings = TableEmbeddings()
    return EmbeddingTopicGate(embeddings, ["anchor crypto", "anchor tls"], threshold), embeddings


def test_a_request_near_an_anchor_is_unsure_and_left_to_the_next_ring() -> None:
    ring, _ = gate()

    assert ring.check(GuardRequest("RSA question", "en")).verdict == "UNSURE"


def test_a_request_far_from_every_anchor_is_denied_with_its_dissimilarity() -> None:
    ring, _ = gate()

    verdict = ring.check(GuardRequest("football question", "en"))

    assert (verdict.verdict, verdict.confidence) == ("DENY", 1.0)


def test_the_threshold_decides_a_borderline_request() -> None:
    # cosine("borderline", "anchor crypto") is about 0.406
    assert gate(0.40)[0].check(GuardRequest("borderline", "en")).verdict == "UNSURE"
    assert gate(0.45)[0].check(GuardRequest("borderline", "en")).verdict == "DENY"


def test_the_ring_never_allows() -> None:
    ring, _ = gate(0.0)

    assert {ring.check(GuardRequest(text, "en")).verdict for text in ("RSA question", "football question")} == {
        "UNSURE"
    }


def test_the_anchors_are_embedded_once_and_only_on_first_use() -> None:
    ring, embeddings = gate()
    assert embeddings.calls == []  # building the ring needs no model server

    ring.check(GuardRequest("RSA question", "en"))
    ring.check(GuardRequest("football question", "en"))

    assert embeddings.calls.count(("anchor crypto", "anchor tls")) == 1


def test_without_an_embedding_model_the_chain_fails_closed() -> None:
    chain = GuardChain([EmbeddingTopicGate(NullProvider(), ["anchor"], 0.4)])

    decision = chain.decide(GuardRequest("Projemde RSA nerede?", "tr"))

    assert (decision.decision, decision.deciding_ring) == ("DENY", "FAIL_CLOSED")


@pytest.mark.parametrize(("anchors", "threshold"), [([], 0.4), (["a"], 1.5), (["a"], -0.1)])
def test_an_invalid_gate_configuration_is_refused(anchors: list[str], threshold: float) -> None:
    with pytest.raises(ValueError):
        EmbeddingTopicGate(TableEmbeddings(), anchors, threshold)
