"""Ring 2: the scope classifier (FR-14). Model B (P7.5, D-343, D-344d) and, for the baseline measurement only, the
interim embedding topic gate it replaced (D-246).

**Model B (`OnnxScopeClassifier`).** The request is embedded with the local embedding model (the one Model B was trained
on, D-14) and the ONNX classifier head (`models/scope_classifier-v1.onnx`, ml P7.3) gives the probability that it is out
of scope. The band of the thresholds file decides (D-332c):

- `p_out < unsure_low`: ALLOW, confidence `1 - p_out`;
- `p_out >= unsure_high`: DENY, confidence `p_out`;
- in between: UNSURE, and the LLM self-check (ring 3) decides.

The confidence is the classifier's probability (four decimals, as agent_db stores it). Before its first answer the ring
checks that the embedding model's Ollama digest is the one Model B was trained with; a different model (the same tag
pulled again) would change the vectors, so a mismatch, an unreachable model server or a probability outside 0..1 raise
and the chain denies (FAIL_CLOSED).

**Interim topic gate (`EmbeddingTopicGate`, D-246).** The request is compared with fixed in-scope anchor sentences;
below the cosine threshold the ring is DENY, otherwise UNSURE. It never allows. It stays only so that the baseline of
the evaluation can be measured on the same stack (`guardrails.scope_classifier: topic_gate`).
"""

from __future__ import annotations

import logging
import math
import os
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.guardrails.chain import GuardRequest, RingName, RingVerdict
from src.llm.provider import EmbeddingProvider

_LOG = logging.getLogger("src.guardrails")
SCOPE_INPUT = "embedding"  # the ONNX input name of Model B's head (ml scope_onnx.INPUT)
OUT_OF_SCOPE_COLUMN = 1  # the head was trained on 0 = IN_SCOPE, 1 = OUT_OF_SCOPE (ml scope_trainer)


def _no_onnx_telemetry() -> None:
    """onnxruntime 1.30 uploads telemetry over HTTPS to a Microsoft collector unless ORT_DISABLE_TELEMETRY is set before
    it is imported (measured in the image, D-347); Phase 1 is local (guardrails-security section 1)."""
    os.environ["ORT_DISABLE_TELEMETRY"] = "1"


@dataclass(frozen=True)
class ScopeBand:
    """The bounds of the thresholds file: below `low` ALLOW, from `high` DENY, UNSURE in between."""

    low: float
    high: float

    def __post_init__(self) -> None:
        if not 0 <= self.low <= self.high <= 1:
            raise ValueError("the band needs 0 <= unsure_low <= unsure_high <= 1")


class ScopeHead(Protocol):
    """Out-of-scope probabilities of embedding vectors (the ONNX classifier head)."""

    def p_out(self, vectors: Sequence[Sequence[float]]) -> list[float]: ...


class OnnxScopeHead:
    """Model B's classifier head with onnxruntime (CPU). The session is opened once, from the bytes the caller hashed
    (no second read of the file, and no external data resolved next to it, D-346c)."""

    def __init__(self, content: bytes, dimensions: int) -> None:
        import numpy as np

        _no_onnx_telemetry()
        import onnxruntime as rt

        self._np = np
        self._session = rt.InferenceSession(content, providers=["CPUExecutionProvider"])
        inputs = self._session.get_inputs()
        if [i.name for i in inputs] != [SCOPE_INPUT] or inputs[0].shape[-1] != dimensions:
            raise ValueError("the scope model's input is not one embedding of the configured size")

    def p_out(self, vectors: Sequence[Sequence[float]]) -> list[float]:
        values = self._np.asarray(vectors, dtype=self._np.float64)
        outputs = self._session.run(None, {SCOPE_INPUT: values})
        probabilities = self._np.asarray(outputs[1], dtype=self._np.float64)
        return [float(p) for p in probabilities[:, OUT_OF_SCOPE_COLUMN]]


class OnnxScopeClassifier:
    def __init__(
        self,
        embeddings: EmbeddingProvider,
        head: ScopeHead,
        band: ScopeBand,
        expected_digest: str,
        installed_digest: Callable[[], str | None],
    ) -> None:
        if not expected_digest:
            raise ValueError("the scope model needs the digest of its embedding model")
        self._embeddings = embeddings
        self._head = head
        self._band = band
        self._expected_digest = expected_digest
        self._installed_digest = installed_digest
        self._digest_checked = False
        self._lock = threading.Lock()
        _LOG.info("scope classifier ring is Model B (ONNX)")

    @property
    def name(self) -> RingName:
        return "SCOPE_CLASSIFIER"

    def check(self, request: GuardRequest) -> RingVerdict:
        self._check_digest()
        vector = self._embeddings.embed([request.text]).vectors[0]
        [p] = self._head.p_out([vector])
        if not 0.0 <= p <= 1.0:  # also false for NaN
            raise ValueError("the scope model gave a probability outside 0..1")
        if p < self._band.low:
            return RingVerdict("ALLOW", round(1.0 - p, 4))
        if p >= self._band.high:
            return RingVerdict("DENY", round(p, 4))
        return RingVerdict("UNSURE")

    def _check_digest(self) -> None:
        with self._lock:
            if self._digest_checked:
                return
            installed = self._installed_digest()
            if installed is None:
                raise RuntimeError("the embedding model's digest cannot be read")
            if installed != self._expected_digest:
                raise RuntimeError("the embedding model is not the one the scope model was trained with")
            self._digest_checked = True


class EmbeddingTopicGate:
    def __init__(self, embeddings: EmbeddingProvider, anchors: Sequence[str], threshold: float) -> None:
        if not anchors:
            raise ValueError("the topic gate needs at least one anchor sentence")
        if not 0 <= threshold <= 1:
            raise ValueError("the topic threshold is a cosine similarity between 0 and 1")
        self._embeddings = embeddings
        self._anchors = tuple(anchors)
        self._threshold = threshold
        self._anchor_vectors: tuple[tuple[float, ...], ...] | None = None
        self._lock = threading.Lock()
        _LOG.info("scope classifier ring is the interim embedding topic gate (baseline measurement)")

    @property
    def name(self) -> RingName:
        return "SCOPE_CLASSIFIER"

    def check(self, request: GuardRequest) -> RingVerdict:
        vector = self._embeddings.embed([request.text]).vectors[0]
        similarity = max(_cosine(vector, anchor) for anchor in self._vectors())
        if similarity < self._threshold:
            return RingVerdict("DENY", round(min(1.0, 1.0 - max(0.0, similarity)), 4))
        return RingVerdict("UNSURE")

    def _vectors(self) -> tuple[tuple[float, ...], ...]:
        # Embedded once, on first use: building the service must not need the model server.
        with self._lock:
            if self._anchor_vectors is None:
                self._anchor_vectors = tuple(self._embeddings.embed(list(self._anchors)).vectors)
            return self._anchor_vectors


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    if len(a) != len(b):
        raise ValueError("embedding sizes differ")
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b, strict=True)) / norm if norm else 0.0
