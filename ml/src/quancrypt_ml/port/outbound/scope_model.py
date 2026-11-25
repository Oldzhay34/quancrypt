"""Outbound ports of Model B (P7.3, ml-pipeline section 1): the embedding model, the embedding cache, the classifier
head and its ONNX export. Ollama, NumPy, scikit-learn and ONNX live behind them, in infrastructure only. MLflow, the
reports, ml_outputs and the clock are Model A's ports (port/outbound/risk.py, system.py)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

Vector = Sequence[float]


class EmbeddingUnavailableError(Exception):
    """The local embedding model cannot be reached, does not have the model or answered outside its contract."""


class EmbeddingProvider(Protocol):
    """The local Ollama embedding model (D-14): the same model, request and raw text as agent-service, so the vectors
    the head is trained on are the vectors it sees at inference."""

    @property
    def model_id(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def digest(self) -> str:
        """The installed model's digest (its exact build behind the tag)."""
        ...

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        """One vector of `dimensions` numbers per text, in order."""
        ...


class EmbeddingCache(Protocol):
    """Vectors of one model build, by the SHA-256 of their text (the cache files are git-ignored)."""

    def get(self, model: str, digest: str, keys: Sequence[str]) -> dict[str, list[float]]:
        """The cached vectors among `keys`; a cache of another model or digest holds none."""
        ...

    def put(self, model: str, digest: str, vectors: Mapping[str, Vector]) -> None:
        """Adds the vectors; a cache of another model or digest is replaced."""
        ...


class ScopeModel(Protocol):
    """A fitted head (scaling + classifier). Opaque: only its own family's exporter reads it (another one is a
    TypeError)."""

    @property
    def algorithm(self) -> str: ...

    @property
    def params(self) -> Mapping[str, object]: ...

    def p_out(self, vectors: Sequence[Vector]) -> list[float]:
        """The out-of-scope probability of every vector."""
        ...


@dataclass(frozen=True)
class SearchResult:
    algorithm: str
    params: Mapping[str, object]  # the best of the grid
    fold_auc: tuple[float, ...]  # the inner folds' ROC AUC at the best parameters


class ScopeTrainer(Protocol):
    """A fixed grid searched with an inner group-aware, label-stratified k-fold on the training set (groups: the
    paraphrase groups, `seed_id`); class weights balanced; fixed seed. Labels are IN_SCOPE or OUT_OF_SCOPE."""

    @property
    def algorithms(self) -> tuple[str, ...]: ...

    def grid(self, algorithm: str) -> Mapping[str, Sequence[object]]: ...

    def search(
        self,
        algorithm: str,
        vectors: Sequence[Vector],
        labels: Sequence[str],
        groups: Sequence[str],
        folds: int,
        seed: int,
    ) -> SearchResult: ...

    def fit(
        self,
        algorithm: str,
        params: Mapping[str, object],
        vectors: Sequence[Vector],
        labels: Sequence[str],
        groups: Sequence[str],
        seed: int,
    ) -> ScopeModel: ...


@dataclass(frozen=True)
class ScopeParity:
    rows: int
    classes_equal: bool  # the classifier's own class output
    max_probability_difference: float
    onnx_p_out: tuple[float, ...]  # the ONNX model's out-of-scope probabilities, for the decision check
    sha256: str = ""  # of the staged model file


class ScopeOnnxExporter(Protocol):
    def export(self, model: ScopeModel, vectors: Sequence[Vector], path: Path) -> ScopeParity:
        """Stages the ONNX model of `path` (one input `embedding`, `dimensions` doubles) beside it and compares the
        staged content with the model. `path` itself is not touched."""
        ...

    def promote(self, path: Path) -> None:
        """The staged model becomes `path` (only after its parity passed)."""
        ...

    def discard(self, path: Path) -> None:
        """Removes the staged model; `path` stays as it was."""
        ...


class ScoreCharts(Protocol):
    def score_histogram(
        self, labels: Sequence[str], p_out: Sequence[float], bounds: Mapping[str, float], path: Path
    ) -> None:
        """The out-of-scope probability of each class, with the threshold and band bounds marked."""
        ...
