"""Ring 2, interim: an embedding topic gate until Model B arrives (P7.5; user decision D-246).

The request is embedded with the local embedding model (the same one the knowledge base uses, D-14) and compared with a
fixed set of in-scope anchor sentences (`guardrails.topic_anchors`). If no anchor is close enough (highest cosine
similarity below `guardrails.topic_threshold`) the ring is DENY; otherwise UNSURE and the self-check decides. The ring
never allows: it only keeps requests whose topic is far from Quancrypt's away from the self-check, which a forged
dialogue can talk into saying IN_SCOPE (security review P4.4). If the embedding model cannot be reached the ring raises
and the chain denies (FAIL_CLOSED).

The confidence of a DENY is the dissimilarity, 1 minus the highest similarity (bounded to 0..1); it is a geometric
score, not a calibrated probability. P7.5 replaces this class with the ONNX classifier behind the same ring name.
"""

from __future__ import annotations

import logging
import math
import threading
from collections.abc import Sequence

from src.guardrails.chain import GuardRequest, RingName, RingVerdict
from src.llm.provider import EmbeddingProvider

_LOG = logging.getLogger("src.guardrails")


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
        _LOG.info("scope classifier ring is the interim embedding topic gate (Model B arrives in P7.5)")

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
