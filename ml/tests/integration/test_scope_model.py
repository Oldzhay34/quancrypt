"""Model B end to end with the real scikit-learn heads, ONNX, the file cache and the report writer (the embedding model
is the scripted fake; the real one is the `ollama` check): the ONNX parity of both algorithms and two identical runs
(ml-pipeline sections 7 and 8)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import onnxruntime as rt
import pytest

from quancrypt_ml.infrastructure.files.embedding_cache import NpyEmbeddingCache
from quancrypt_ml.infrastructure.files.text_files import FileReportWriter
from quancrypt_ml.infrastructure.llm.ollama_embedding import OllamaEmbeddingProvider
from quancrypt_ml.infrastructure.model.analysis import MatplotlibCharts
from quancrypt_ml.infrastructure.model.scope_onnx import SklearnScopeOnnxExporter
from quancrypt_ml.infrastructure.model.scope_trainer import LINEAR_SVM, LOGISTIC_REGRESSION, SklearnScopeTrainer
from quancrypt_ml.port.inbound.scope_model import TrainScopeCommand, TrainScopeResult
from quancrypt_ml.usecase.export_scope_onnx_service import ExportScopeOnnxService
from quancrypt_ml.usecase.train_scope_classifier_service import ScopeTrainingPorts, TrainScopeClassifierService
from tests.support.fakes import FixedClock
from tests.support.risk_fakes import FakeRegistry, FakeSink
from tests.support.scope_fakes import DIMENSIONS, FakeEmbeddings, FakeScopeFiles, scope_sets


def _run(tmp: Path) -> tuple[TrainScopeResult, FakeRegistry, FakeSink]:
    registry, sink = FakeRegistry(), FakeSink()
    ports = ScopeTrainingPorts(
        files=FakeScopeFiles(scope_sets()), embeddings=FakeEmbeddings(), cache=NpyEmbeddingCache(tmp / "cache"),
        trainer=SklearnScopeTrainer(), export=ExportScopeOnnxService(SklearnScopeOnnxExporter(DIMENSIONS), FileReportWriter()),
        charts=MatplotlibCharts(), registry=registry, sink=sink, reports=FileReportWriter(), clock=FixedClock(),
    )  # fmt: skip
    command = TrainScopeCommand(
        "v1", tmp / "train.jsonl", tmp / "val.jsonl", tmp / "test.jsonl", tmp / "model_b.md", tmp / "card.md",
        tmp / "models" / "scope_classifier-v1.onnx", tmp / "models" / "scope_classifier-v1.thresholds.json",
        tmp / "artifacts", 42,
    )  # fmt: skip
    return TrainScopeClassifierService(ports).execute(command), registry, sink


def test_the_real_heads_train_export_and_report(tmp_path: Path) -> None:
    result, registry, sink = _run(tmp_path)
    assert result.onnx_parity and result.selected in (LOGISTIC_REGRESSION, LINEAR_SVM)
    onnx = tmp_path / "models" / "scope_classifier-v1.onnx"
    session = rt.InferenceSession(str(onnx), providers=["CPUExecutionProvider"])
    assert [i.name for i in session.get_inputs()] == ["embedding"]
    probabilities = session.run(None, {"embedding": np.zeros((1, DIMENSIONS), dtype=np.float64)})[1]
    assert np.asarray(probabilities).shape == (1, 2)
    thresholds = json.loads((tmp_path / "models" / "scope_classifier-v1.thresholds.json").read_text(encoding="utf-8"))
    assert thresholds["onnx"] == onnx.name and thresholds["input_dimensions"] == DIMENSIONS
    assert thresholds["onnx_sha256"] == hashlib.sha256(onnx.read_bytes()).hexdigest()
    fixture = json.loads((tmp_path / "models" / "scope_classifier-v1.parity.json").read_text(encoding="utf-8"))
    assert fixture["onnx_sha256"] == thresholds["onnx_sha256"] and fixture["rows"]
    assert (tmp_path / "artifacts" / "score_histogram.png").stat().st_size > 0
    assert "## H4" in (tmp_path / "model_b.md").read_text(encoding="utf-8")
    assert sink.stored[0].model_name == "scope_classifier"


def test_both_heads_keep_onnx_parity(tmp_path: Path) -> None:
    vectors = [[0.1 * i, float(i % 2), float(i), 1.0] for i in range(40)]
    labels = ["OUT_OF_SCOPE" if i % 2 else "IN_SCOPE" for i in range(40)]
    groups = [f"g{i // 2}" for i in range(40)]
    trainer, exporter = SklearnScopeTrainer(), SklearnScopeOnnxExporter(DIMENSIONS)
    for algorithm in trainer.algorithms:
        model = trainer.fit(algorithm, {"C": 1.0}, vectors, labels, groups, 42)
        parity = exporter.export(model, vectors, tmp_path / f"{algorithm}.onnx")
        assert parity.classes_equal and parity.max_probability_difference <= 1e-4


def test_two_runs_on_the_same_data_give_the_same_metrics(tmp_path: Path) -> None:
    first, first_registry, _ = _run(tmp_path / "a")
    second, second_registry, _ = _run(tmp_path / "b")
    assert first == second
    assert first_registry.runs[-1][1].metrics == second_registry.runs[-1][1].metrics


@pytest.mark.ollama
def test_the_local_embedding_model_answers_like_agent_service_expects() -> None:
    """Needs the host Ollama with embeddinggemma (D-68); outside `make verify` (`make ollama-check`)."""
    provider = OllamaEmbeddingProvider("http://127.0.0.1:11434", "embeddinggemma:latest", 768)
    assert provider.digest().strip()
    vectors = provider.embed(["Projemde RSA hangi dosyalarda kullanılıyor?", "What is the weather today?"])
    assert len(vectors) == 2 and all(len(v) == 768 for v in vectors)
