"""EmbeddingCache over two files per model (P7.3, D-333b): `embeddings_<model>.npy` (one row per vector, float64) and
`embeddings_<model>.index.json` (the model, its digest, the dimensions and the text SHA-256 of every row, in row order).
A cache of another digest holds nothing and is replaced on the next write. Both files are git-ignored and each is
written through a temporary file; a crash between the two leaves a pair that fails the checks and is rebuilt."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np

from quancrypt_ml.port.outbound.scope_model import Vector

_KEY = re.compile(r"^[0-9a-f]{64}$")


def _safe(model: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", model)


class NpyEmbeddingCache:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def _paths(self, model: str) -> tuple[Path, Path]:
        stem = f"embeddings_{_safe(model)}"
        return self._directory / f"{stem}.npy", self._directory / f"{stem}.index.json"

    def _load(self, model: str, digest: str) -> dict[str, list[float]]:
        vectors_path, index_path = self._paths(model)
        if not vectors_path.exists() or not index_path.exists():
            return {}
        try:
            index = json.loads(index_path.read_text(encoding="utf-8"))
            matrix = np.load(vectors_path, allow_pickle=False)
        except (OSError, ValueError):
            return {}  # a damaged cache is rebuilt
        keys = index.get("keys") if isinstance(index, dict) else None
        if (
            not isinstance(keys, list)
            or index.get("model") != model
            or index.get("digest") != digest
            or matrix.ndim != 2
            or matrix.shape[0] != len(keys)
            or matrix.shape[1] != index.get("dimensions")
            or not all(isinstance(k, str) and _KEY.match(k) for k in keys)
        ):
            return {}
        return {k: [float(v) for v in row] for k, row in zip(keys, matrix, strict=True)}

    def get(self, model: str, digest: str, keys: Sequence[str]) -> dict[str, list[float]]:
        cached = self._load(model, digest)
        return {k: cached[k] for k in keys if k in cached}

    def put(self, model: str, digest: str, vectors: Mapping[str, Vector]) -> None:
        if not vectors:
            return
        merged = {**self._load(model, digest), **{k: [float(v) for v in vec] for k, vec in vectors.items()}}
        keys = sorted(merged)
        sizes = {len(merged[k]) for k in keys}
        if len(sizes) != 1 or not all(_KEY.match(k) for k in keys):
            raise ValueError("the cached vectors must have one size and SHA-256 keys")
        vectors_path, index_path = self._paths(model)
        self._directory.mkdir(parents=True, exist_ok=True)
        temporary = vectors_path.with_suffix(".tmp.npy")
        np.save(temporary, np.asarray([merged[k] for k in keys], dtype=np.float64), allow_pickle=False)
        index = {"model": model, "digest": digest, "dimensions": sizes.pop(), "keys": keys}
        index_temporary = index_path.with_suffix(".tmp")
        index_temporary.write_text(json.dumps(index, indent=1) + "\n", encoding="utf-8")
        temporary.replace(vectors_path)
        index_temporary.replace(index_path)
