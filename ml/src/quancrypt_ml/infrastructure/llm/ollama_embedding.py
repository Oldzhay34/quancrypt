"""EmbeddingProvider over the local Ollama (P7.3, D-14, D-333a). The request is agent-service's
(`services/agent-service/src/llm/ollama_provider.py`): `POST /api/embed` with the raw texts and `truncate: false`, so a
text longer than the model context is an error, never a silently shortened vector. The digest comes from
`GET /api/tags`. Loopback only, no proxy, no redirect (guardrails-security section 1)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from quancrypt_ml.port.outbound.scope_model import EmbeddingUnavailableError


class OllamaEmbeddingProvider:
    def __init__(
        self,
        base_url: str,
        model: str,
        dimensions: int,
        timeout_s: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._model = model
        self._dimensions = dimensions
        self._client = httpx.Client(
            base_url=base_url, timeout=timeout_s, trust_env=False, follow_redirects=False, transport=transport
        )

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        try:
            response = self._client.request(method, path, json=body)
        except httpx.HTTPError:
            raise EmbeddingUnavailableError("the local embedding model cannot be reached") from None
        if response.status_code != 200:
            # the body is not copied: an error text may quote the request
            raise EmbeddingUnavailableError(f"the local embedding model answered {response.status_code}")
        try:
            return response.json()
        except ValueError:
            raise EmbeddingUnavailableError("the local embedding model answer is not JSON") from None

    def digest(self) -> str:
        data = self._call("GET", "/api/tags")
        models = data.get("models") if isinstance(data, dict) else None
        for item in models if isinstance(models, list) else []:
            if isinstance(item, dict) and item.get("name") == self._model and isinstance(item.get("digest"), str):
                return str(item["digest"])
        raise EmbeddingUnavailableError("the embedding model is not installed in the local Ollama")

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        items = list(texts)
        if not items:
            return []
        data = self._call("POST", "/api/embed", {"model": self._model, "input": items, "truncate": False})
        raw = data.get("embeddings") if isinstance(data, dict) else None
        if not isinstance(raw, list) or len(raw) != len(items):
            raise EmbeddingUnavailableError("the embed answer does not hold one vector per text")
        vectors: list[list[float]] = []
        for vector in raw:
            if (
                not isinstance(vector, list)
                or len(vector) != self._dimensions
                or not all(isinstance(v, int | float) and not isinstance(v, bool) for v in vector)
            ):
                raise EmbeddingUnavailableError(f"the embed answer has a vector that is not {self._dimensions} numbers")
            vectors.append([float(v) for v in vector])
        return vectors
