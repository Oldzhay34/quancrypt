"""Test doubles of the Model B ports: a scripted embedding model, an in-memory cache, a trainer whose head reads the
first vector component, an exporter and charts. No model library."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from quancrypt_ml.domain.scope import IN_SCOPE, OUT_OF_SCOPE, ScopeRecord
from quancrypt_ml.port.outbound.scope_model import EmbeddingUnavailableError, ScopeParity, SearchResult, Vector

DIMENSIONS = 4


def record(index: int, label: str, score: float, lang: str = "tr", category: str = "general") -> ScopeRecord:
    """A request whose fake embedding puts `score` in the first component (the fake head's p_out)."""
    return ScopeRecord(
        f"r{index}", f"g{index // 2}", lang, f"{label}|{score:.6f}|{index}", label, category, "synthetic_reviewed"
    )


def score_of(text: str) -> float:
    return float(text.split("|")[1])


def scope_sets(shift: float = 0.0) -> dict[str, list[ScopeRecord]]:
    """train / val / test: out-of-scope requests score 0.55-0.93, in-scope ones 0.05-0.715 (they overlap: at the
    threshold 0.55 five in-scope requests are rejected)."""
    sets: dict[str, list[ScopeRecord]] = {}
    for offset, split in ((0, "train"), (1000, "val"), (2000, "test")):
        rows = []
        for i in range(20):
            lang, category = ("tr", "jailbreak") if i % 5 == 0 else ("en", "general") if i % 2 else ("tr", "general")
            rows.append(record(offset + i, OUT_OF_SCOPE, min(0.99, 0.55 + i * 0.02 + shift), lang, category))
        for i in range(20):
            lang, category = ("en", "boundary") if i % 4 == 0 else ("tr", "inventory") if i % 2 else ("en", "risk")
            rows.append(record(offset + 100 + i, IN_SCOPE, max(0.01, 0.05 + i * 0.035 + shift), lang, category))
        sets[split] = rows
    return sets


@dataclass
class FakeScopeFiles:
    sets: dict[str, list[ScopeRecord]]

    def read(self, path: Path) -> list[ScopeRecord]:
        return list(self.sets[path.stem])

    def write(self, path: Path, records: Sequence[ScopeRecord]) -> None:
        self.sets[path.stem] = list(records)


class FakeEmbeddings:
    model_id = "embeddinggemma:latest"
    dimensions = DIMENSIONS

    def __init__(self, digest: str = "sha256:" + "a" * 64, down: bool = False) -> None:
        self._digest = digest
        self.down = down
        self.embedded: list[str] = []

    def digest(self) -> str:
        if self.down:
            raise EmbeddingUnavailableError("the local embedding model cannot be reached")
        return self._digest

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if self.down:
            raise EmbeddingUnavailableError("the local embedding model cannot be reached")
        self.embedded.extend(texts)
        # [score, 1 if out of scope, the record index, 1]: unique per request; the fake heads may read the label
        return [[score_of(t), 1.0 if t.startswith(OUT_OF_SCOPE) else 0.0, float(t.split("|")[2]), 1.0] for t in texts]


@dataclass
class FakeEmbeddingCache:
    store: dict[tuple[str, str], dict[str, list[float]]] = field(default_factory=dict)

    def get(self, model: str, digest: str, keys: Sequence[str]) -> dict[str, list[float]]:
        cached = self.store.get((model, digest), {})
        return {k: cached[k] for k in keys if k in cached}

    def put(self, model: str, digest: str, vectors: Mapping[str, Vector]) -> None:
        if (model, digest) not in self.store:
            self.store = {}  # another model or digest replaces the cache
        self.store.setdefault((model, digest), {}).update({k: [float(x) for x in v] for k, v in vectors.items()})


Transform = Callable[[float, bool], float]  # (score, is out of scope) -> p_out


def identity(score: float, out_of_scope: bool) -> float:
    return score


@dataclass
class FirstComponentModel:
    """p_out = transform(first component, label flag); every vector it scores is counted."""

    algorithm: str
    params: Mapping[str, object]
    transform: Transform
    seen: Counter[tuple[float, ...]]

    def raw(self, vectors: Sequence[Vector]) -> list[float]:
        return [min(1.0, max(0.0, self.transform(v[0], v[1] > 0.5))) for v in vectors]

    def p_out(self, vectors: Sequence[Vector]) -> list[float]:
        self.seen.update(tuple(v) for v in vectors)
        return self.raw(vectors)


class FakeScopeTrainer:
    algorithms = ("LOGISTIC_REGRESSION", "LINEAR_SVM")

    def __init__(self, transforms: Mapping[str, Transform] | None = None) -> None:
        self.transforms = dict(transforms or {})
        self.seen: Counter[tuple[float, ...]] = Counter()
        self.fitted_on: list[int] = []

    def grid(self, algorithm: str) -> Mapping[str, Sequence[object]]:
        return {"C": (0.1, 1.0, 10.0)}

    def search(
        self,
        algorithm: str,
        vectors: Sequence[Vector],
        labels: Sequence[str],
        groups: Sequence[str],
        folds: int,
        seed: int,
    ) -> SearchResult:
        k = min(folds, len(set(groups)))
        return SearchResult(algorithm, {"C": 1.0}, tuple(0.9 + 0.01 * i for i in range(k)))

    def fit(
        self,
        algorithm: str,
        params: Mapping[str, object],
        vectors: Sequence[Vector],
        labels: Sequence[str],
        groups: Sequence[str],
        seed: int,
    ) -> FirstComponentModel:
        self.fitted_on.append(len(vectors))
        return FirstComponentModel(algorithm, dict(params), self.transforms.get(algorithm, identity), self.seen)


class FakeScopeExporter:
    """Answers like a FirstComponentModel (without scoring through the model), or with the given parity."""

    def __init__(self, parity: ScopeParity | None = None, drift: float = 0.0) -> None:
        self.promoted: list[Path] = []
        self._staged: set[Path] = set()
        self._parity = parity
        self._drift = drift

    def export(self, model: object, vectors: Sequence[Vector], path: Path) -> ScopeParity:
        self._staged.add(path)
        if self._parity is not None:
            return self._parity
        assert isinstance(model, FirstComponentModel)
        p = tuple(min(1.0, max(0.0, x + self._drift)) for x in model.raw(vectors))
        return ScopeParity(len(vectors), True, abs(self._drift) if vectors else 0.0, p, "f" * 64)

    def promote(self, path: Path) -> None:
        assert path in self._staged
        self._staged.discard(path)
        self.promoted.append(path)

    def discard(self, path: Path) -> None:
        self._staged.discard(path)


class FakeScoreCharts:
    def __init__(self) -> None:
        self.drawn: list[Path] = []

    def score_histogram(
        self, labels: Sequence[str], p_out: Sequence[float], bounds: Mapping[str, float], path: Path
    ) -> None:
        assert all(math.isfinite(b) for b in bounds.values())
        self.drawn.append(path)
