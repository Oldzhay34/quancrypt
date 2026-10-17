"""A deterministic bag-of-words embedder (test double): similar texts get close vectors, no model needed."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence

from src.llm.provider import EmbeddingResult

DIMENSIONS = 768
MODEL = "bag-of-words-test"
_TOKEN = re.compile(r"[a-z0-9çğıöşü]+")


class BagOfWordsEmbedder:
    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple(self._vector(t) for t in texts), model=MODEL, prompt_tokens=0)

    @staticmethod
    def _vector(text: str) -> tuple[float, ...]:
        values = [0.0] * DIMENSIONS
        for token in _TOKEN.findall(text.lower()):
            values[int.from_bytes(hashlib.sha256(token.encode()).digest()[:4], "big") % DIMENSIONS] += 1.0
        if not any(values):
            values[0] = 1.0
        return tuple(values)
