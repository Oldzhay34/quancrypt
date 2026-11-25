"""Shared contracts of the Model B outbound ports (LSP, hexagonal-service section 7): every port with a fake runs the
same cases against the fake and the real adapter. The trainer and the exporter form a family (the exporter reads its
own trainer's heads only)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pytest

from quancrypt_ml.port.outbound.scope import ScopeDatasetFiles
from quancrypt_ml.port.outbound.scope_model import (
    EmbeddingCache,
    EmbeddingProvider,
    EmbeddingUnavailableError,
    ScopeOnnxExporter,
    ScopeTrainer,
    ScoreCharts,
)
from tests.support.scope_fakes import scope_sets

# ---------------------------------------------------------------- EmbeddingProvider
# factory(up): an embedding model of 4 dimensions that answers (up) or cannot be reached.
EmbeddingFactory = Callable[[bool], EmbeddingProvider]


def embedding_case_one_vector_of_the_model_size_per_text(factory: EmbeddingFactory) -> None:
    provider = factory(True)
    assert provider.digest() and provider.model_id and provider.dimensions == 4
    vectors = provider.embed(["OUT_OF_SCOPE|0.9|1", "IN_SCOPE|0.1|2"])
    assert len(vectors) == 2 and all(len(v) == provider.dimensions for v in vectors)
    assert provider.embed([]) == []


def embedding_case_an_unreachable_model_is_reported(factory: EmbeddingFactory) -> None:
    provider = factory(False)
    with pytest.raises(EmbeddingUnavailableError):
        provider.digest()
    with pytest.raises(EmbeddingUnavailableError):
        provider.embed(["x"])


EMBEDDING_CASES = [
    embedding_case_one_vector_of_the_model_size_per_text,
    embedding_case_an_unreachable_model_is_reported,
]

# ---------------------------------------------------------------- EmbeddingCache
CacheFactory = Callable[[Path], EmbeddingCache]
K1, K2 = hashlib.sha256(b"one").hexdigest(), hashlib.sha256(b"two").hexdigest()
MODEL, D1, D2 = "embeddinggemma:latest", "sha256:" + "1" * 64, "sha256:" + "2" * 64


def cache_case_vectors_come_back_by_key_and_merge(factory: CacheFactory, folder: Path) -> None:
    cache = factory(folder)
    assert cache.get(MODEL, D1, [K1]) == {}
    cache.put(MODEL, D1, {K1: [0.5, 1.0]})
    assert cache.get(MODEL, D1, [K1, K2]) == {K1: [0.5, 1.0]}
    cache.put(MODEL, D1, {K2: [0.25, 2.0]})
    assert factory(folder).get(MODEL, D1, [K2, K1]) == {K1: [0.5, 1.0], K2: [0.25, 2.0]}


def cache_case_another_digest_holds_nothing_and_replaces_the_cache(factory: CacheFactory, folder: Path) -> None:
    cache = factory(folder)
    cache.put(MODEL, D1, {K1: [0.5, 1.0]})
    assert cache.get(MODEL, D2, [K1]) == {}
    cache.put(MODEL, D2, {K2: [0.1, 0.2]})
    assert cache.get(MODEL, D1, [K1]) == {} and cache.get(MODEL, D2, [K2]) == {K2: [0.1, 0.2]}


CACHE_CASES = [
    cache_case_vectors_come_back_by_key_and_merge,
    cache_case_another_digest_holds_nothing_and_replaces_the_cache,
]

# ---------------------------------------------------------------- ScopeTrainer + ScopeOnnxExporter


@dataclass(frozen=True)
class ScopeFamily:
    trainer: ScopeTrainer
    exporter: ScopeOnnxExporter


def _train() -> tuple[list[list[float]], list[str], list[str]]:
    rows = scope_sets()["train"]
    vectors = [[float(r.text.split("|")[1]), 1.0 if r.label == "OUT_OF_SCOPE" else 0.0, float(i % 7), 1.0]
               for i, r in enumerate(rows)]  # fmt: skip
    return vectors, [r.label for r in rows], [r.seed_id for r in rows]


def family_case_the_search_scores_every_inner_fold_and_picks_from_the_grid(family: ScopeFamily) -> None:
    vectors, labels, groups = _train()
    for algorithm in family.trainer.algorithms:
        result = family.trainer.search(algorithm, vectors, labels, groups, 5, 42)
        assert result.algorithm == algorithm and len(result.fold_auc) == 5
        assert all(0.0 <= a <= 1.0 for a in result.fold_auc)
        assert result.params["C"] in family.trainer.grid(algorithm)["C"]


def family_case_a_head_gives_a_probability_and_the_onnx_model_answers_alike(family: ScopeFamily, folder: Path) -> None:
    vectors, labels, groups = _train()
    model = family.trainer.fit(family.trainer.algorithms[0], {"C": 1.0}, vectors, labels, groups, 42)
    p = model.p_out(vectors)
    assert len(p) == len(vectors) and all(0.0 <= x <= 1.0 for x in p)
    parity = family.exporter.export(model, vectors[:9], folder / "head.onnx")
    assert not (folder / "head.onnx").exists()  # staged only
    family.exporter.promote(folder / "head.onnx")
    assert parity.rows == 9 and parity.classes_equal and parity.max_probability_difference <= 1e-4
    assert len(parity.onnx_p_out) == 9


FAMILY_CASES = [family_case_the_search_scores_every_inner_fold_and_picks_from_the_grid]
FAMILY_FILE_CASES = [family_case_a_head_gives_a_probability_and_the_onnx_model_answers_alike]

# ---------------------------------------------------------------- ScoreCharts


def charts_case_a_score_histogram_is_drawn(charts: ScoreCharts, folder: Path) -> None:
    path = folder / "hist" / "scores.png"
    charts.score_histogram(["OUT_OF_SCOPE", "IN_SCOPE"], [0.9, 0.1], {"threshold": 0.5, "unsure_low": 0.3}, path)


CHART_CASES = [charts_case_a_score_histogram_is_drawn]

# ---------------------------------------------------------------- ScopeDatasetFiles (port/outbound/scope.py)
# A factory of the files port; the cases use paths whose stem names the set, as the use cases do.
FilesFactory = Callable[[], ScopeDatasetFiles]


def files_case_written_records_are_read_back_in_order(factory: FilesFactory, folder: Path) -> None:
    files, rows = factory(), scope_sets()["val"][:5]
    files.write(folder / "val.jsonl", rows)
    assert files.read(folder / "val.jsonl") == rows


def files_case_each_path_keeps_its_own_records(factory: FilesFactory, folder: Path) -> None:
    files, sets = factory(), scope_sets()
    files.write(folder / "train.jsonl", sets["train"][:2])
    files.write(folder / "test.jsonl", sets["test"][:3])
    assert files.read(folder / "train.jsonl") == sets["train"][:2]
    assert files.read(folder / "test.jsonl") == sets["test"][:3]


FILES_CASES = [files_case_written_records_are_read_back_in_order, files_case_each_path_keeps_its_own_records]
