"""TrainScopeClassifier against fakes: validation-only choices, one use of the test set, the pick rule, the cache, the
stored metrics, the threshold file and the failures (P7.3, D-332, D-333)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quancrypt_ml.domain.scope_model import Scored, select_threshold
from quancrypt_ml.port.inbound.scope_model import ExportScopeOnnxCommand, ScopeTrainingError, TrainScopeCommand
from quancrypt_ml.port.outbound.scope_model import ScopeParity
from quancrypt_ml.usecase.export_scope_onnx_service import ExportScopeOnnxService
from quancrypt_ml.usecase.train_scope_classifier_service import ScopeTrainingPorts, TrainScopeClassifierService
from tests.support.fakes import FakeReports, FixedClock
from tests.support.risk_fakes import FakeRegistry, FakeSink
from tests.support.scope_fakes import (
    FakeEmbeddingCache,
    FakeEmbeddings,
    FakeScopeExporter,
    FakeScopeFiles,
    FakeScopeTrainer,
    FakeScoreCharts,
    FirstComponentModel,
    identity,
    scope_sets,
    score_of,
)


class World:
    def __init__(self, tmp: Path, **overrides: object) -> None:
        self.sets = scope_sets()
        self.files, self.embeddings, self.cache = FakeScopeFiles(self.sets), FakeEmbeddings(), FakeEmbeddingCache()
        self.trainer, self.registry, self.sink, self.reports = (
            FakeScopeTrainer(),
            FakeRegistry(),
            FakeSink(),
            FakeReports(),
        )
        ports = {
            "files": self.files, "embeddings": self.embeddings, "cache": self.cache, "trainer": self.trainer,
            "export": ExportScopeOnnxService(FakeScopeExporter(), FakeReports()), "charts": FakeScoreCharts(),
            "registry": self.registry, "sink": self.sink, "reports": self.reports, "clock": FixedClock(),
        }  # fmt: skip
        ports.update(overrides)
        self.ports = ports
        self.service = TrainScopeClassifierService(ScopeTrainingPorts(**ports))  # type: ignore[arg-type]
        self.tmp = tmp

    def command(self) -> TrainScopeCommand:
        t = self.tmp
        return TrainScopeCommand(
            "v1", t / "train.jsonl", t / "val.jsonl", t / "test.jsonl", t / "model_b.md", t / "card.md",
            t / "m.onnx", t / "m.thresholds.json", t / "art", 42,
        )  # fmt: skip


def _vectors(world: World, split: str) -> list[tuple[float, ...]]:
    return [tuple(world.embeddings.embed([r.text])[0]) for r in world.sets[split]]


def test_the_run_stores_the_published_head_with_its_metrics_and_writes_the_threshold_file(tmp_path: Path) -> None:
    world = World(tmp_path)
    result = world.service.execute(world.command())
    assert result.selected == "LOGISTIC_REGRESSION" and result.stored and result.onnx_parity
    assert world.sink.calls == [1]
    stored = world.sink.stored[0]
    assert (stored.model_name, stored.version, stored.label_source, stored.publish) == (
        "scope_classifier", "v1", "SCOPE_SET", True,
    )  # fmt: skip
    assert stored.predictions == [] and {m.scope for m in stored.metrics} == {"CV_MEAN", "CV_STD", "VALIDATION", "TEST"}
    keys = {(m.scope, m.metric, m.label) for m in stored.metrics}
    assert {("TEST", "OUT_OF_SCOPE_RECALL", s) for s in ("ALL", "TR", "EN", "JAILBREAK")} <= keys
    assert ("TEST", "FALSE_REJECT_RATE", "BOUNDARY") in keys and ("TEST", "FALSE_REJECT_RATE", "JAILBREAK") not in keys
    document = json.loads(world.reports.texts[tmp_path / "m.thresholds.json"])
    assert document["positive_class"] == "OUT_OF_SCOPE" and document["onnx"] == "m.onnx"
    assert document["unsure_low"] <= document["threshold"] <= document["unsure_high"]
    assert document["embedding_model"] == "embeddinggemma:latest" and document["input_dimensions"] == 4
    assert "## H4" in world.reports.texts[tmp_path / "model_b.md"]
    assert "embeddinggemma:latest" in world.reports.texts[tmp_path / "card.md"]


def test_the_threshold_comes_from_the_validation_set_and_the_test_set_is_scored_once(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.sets["test"] = scope_sets(shift=0.2)["test"]  # a test set that would choose another threshold
    result = world.service.execute(world.command())
    validation = [Scored(r.label, r.lang, r.category, score_of(r.text)) for r in world.sets["val"]]
    assert result.band.threshold == select_threshold(validation)
    test_vectors = _vectors(world, "test")
    assert all(world.trainer.seen[v] == 1 for v in test_vectors)  # once, by the selected head only
    assert world.trainer.fitted_on == [len(world.sets["train"])] * 2  # fitted on the training set only


def test_the_svm_is_picked_only_with_more_than_one_fewer_validation_false_reject(tmp_path: Path) -> None:
    # At the threshold 0.55 the logistic regression rejects 5 in-scope validation requests (the fake sets overlap).
    def one_fewer(score: float, out: bool) -> float:
        return score if out else score - 0.04  # 4 rejects

    def far_fewer(score: float, out: bool) -> float:
        return score if out else score * 0.5  # none

    world = World(tmp_path, trainer=FakeScopeTrainer({"LINEAR_SVM": one_fewer}))
    assert world.service.execute(world.command()).selected == "LOGISTIC_REGRESSION"
    world = World(tmp_path, trainer=FakeScopeTrainer({"LINEAR_SVM": far_fewer}))
    result = world.service.execute(world.command())
    assert result.selected == "LINEAR_SVM" and world.sink.stored[0].algorithm == "LINEAR_SVM"
    rejects = {r.name[3:]: r.metrics["val_false_rejects"] for _, r in world.registry.runs if r.name.startswith("cv-")}
    assert rejects == {"LOGISTIC_REGRESSION": 5.0, "LINEAR_SVM": 0.0}


def test_cached_vectors_are_not_embedded_again_and_another_digest_embeds_again(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.service.execute(world.command())
    first = len(world.embeddings.embedded)
    assert first == sum(len(s) for s in world.sets.values())
    world.service.execute(world.command())
    assert len(world.embeddings.embedded) == first  # all from the cache
    other = FakeEmbeddings(digest="sha256:" + "b" * 64)
    World(tmp_path, embeddings=other, cache=world.cache, files=world.files).service.execute(world.command())
    assert len(other.embedded) == first


def test_the_mlflow_runs_carry_the_children_the_digest_and_the_artifacts(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.service.execute(world.command())
    assert [r.name for _, r in world.registry.runs] == [
        "cv-LOGISTIC_REGRESSION",
        "cv-LINEAR_SVM",
        "scope_classifier-v1",
    ]
    parent = world.registry.runs[-1][1]
    assert parent.tags["embedding_digest"].startswith("sha256:") and len(parent.tags["data_sha256"]) == 64
    assert {"test_all_out_of_scope_recall", "test_tr_false_reject_rate", "threshold"} <= set(parent.metrics)
    assert {a.name for a in parent.artifacts} >= {"score_histogram.png", "confusion_LOGISTIC_REGRESSION.json", "m.onnx"}


@pytest.mark.parametrize(
    "overrides, message",
    [
        ({"embeddings": FakeEmbeddings(down=True)}, "embedding model"),
        ({"export": ExportScopeOnnxService(FakeScopeExporter(drift=1e-3), FakeReports())}, "parity"),
        (
            {
                "export": ExportScopeOnnxService(
                    FakeScopeExporter(ScopeParity(40, False, 0.0, (0.5,) * 40)), FakeReports()
                )
            },
            "parity",
        ),
    ],
    ids=["embedding-down", "probability-drift", "other-classes"],
)
def test_failures_stop_the_run_and_store_nothing(tmp_path: Path, overrides: dict[str, object], message: str) -> None:
    world = World(tmp_path, **overrides)
    with pytest.raises(ScopeTrainingError, match=message):
        world.service.execute(world.command())
    assert world.sink.stored == []


def test_a_split_without_both_labels_is_refused(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.sets["val"] = [r for r in world.sets["val"] if r.label == "IN_SCOPE"]
    with pytest.raises(ScopeTrainingError, match="val set must hold both labels"):
        world.service.execute(world.command())


def test_the_onnx_export_needs_the_same_three_way_decisions(tmp_path: Path) -> None:
    from quancrypt_ml.domain.scope_model import Band

    model = FirstComponentModel("LOGISTIC_REGRESSION", {}, identity, FakeScopeTrainer().seen)
    vectors = [[0.39, 0.0, 0.0, 1.0], [0.61, 0.0, 0.0, 1.0]]
    command = ExportScopeOnnxCommand(model, vectors, [0.39, 0.61], Band(0.4, 0.5, 0.6), tmp_path / "m.onnx")
    assert ExportScopeOnnxService(FakeScopeExporter(), FakeReports()).execute(command).rows == 2
    # within 1e-4 but across a band bound: 0.39 -> 0.40004 is UNSURE instead of ALLOW
    nudged = ScopeParity(2, True, 0.0, (0.40004, 0.61))
    with pytest.raises(ScopeTrainingError, match="parity"):
        ExportScopeOnnxService(FakeScopeExporter(nudged), FakeReports()).execute(command)


def test_a_model_reaches_its_path_only_when_the_parity_passes(tmp_path: Path) -> None:
    failed, passed = FakeScopeExporter(drift=1e-3), FakeScopeExporter()
    world = World(tmp_path, export=ExportScopeOnnxService(failed, FakeReports()))
    with pytest.raises(ScopeTrainingError, match="parity"):
        world.service.execute(world.command())
    assert failed.promoted == []
    world = World(tmp_path, export=ExportScopeOnnxService(passed, FakeReports()))
    world.service.execute(world.command())
    assert passed.promoted == [tmp_path / "m.onnx"]
    assert json.loads(world.reports.texts[tmp_path / "m.thresholds.json"])["onnx_sha256"] == "f" * 64


def test_the_fixed_set_is_written_only_after_the_model_reached_its_path(tmp_path: Path) -> None:
    from quancrypt_ml.domain.scope_model import Band

    model = FirstComponentModel("LOGISTIC_REGRESSION", {}, identity, FakeScopeTrainer().seen)
    vectors = [[0.1 * i, 0.0, 0.0, 1.0] for i in range(30)]
    reference = [0.1 * i for i in range(30)]
    command = ExportScopeOnnxCommand(model, vectors, reference, Band(0.2, 0.3, 0.5), tmp_path / "m.onnx")
    reports = FakeReports()
    ExportScopeOnnxService(FakeScopeExporter(), reports).execute(command)
    fixture = json.loads(reports.texts[tmp_path / "m.parity.json"])
    assert len(fixture["rows"]) == 20 and fixture["onnx_sha256"] == "f" * 64
    assert fixture["band"] == {"low": 0.2, "threshold": 0.3, "high": 0.5}
    assert [r["decision"] for r in fixture["rows"][:6]] == ["ALLOW", "ALLOW", "UNSURE", "UNSURE", "UNSURE", "DENY"]
    assert fixture["covered"] == ["ALLOW", "DENY", "UNSURE"]
    failing = FakeReports()
    with pytest.raises(ScopeTrainingError):
        ExportScopeOnnxService(FakeScopeExporter(drift=1e-3), failing).execute(command)
    assert failing.texts == {}
