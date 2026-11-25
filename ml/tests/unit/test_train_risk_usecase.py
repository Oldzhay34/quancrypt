"""TrainRiskModel against fakes: the split check, selection, the baselines, the dry run and the gold run."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from quancrypt_ml.domain.split import ProjectSplit
from quancrypt_ml.port.inbound.risk import RiskTrainingError, TrainRiskCommand
from quancrypt_ml.port.outbound.risk import Parity
from quancrypt_ml.usecase.export_onnx_service import ExportOnnxService
from quancrypt_ml.usecase.train_risk_model_service import RiskTrainingPorts, TrainRiskModelService
from tests.support.fakes import FakeReports, FixedClock
from tests.support.risk_fakes import (
    FakeCharts,
    FakeData,
    FakeExplainer,
    FakeExporter,
    FakeRegistry,
    FakeSink,
    FakeTrainer,
    FixedSplitter,
    ScriptedLLM,
)
from tests.support.risk_rows import synthetic_rows


class World:
    def __init__(self, tmp: Path, **overrides: object) -> None:
        self.rows = synthetic_rows()
        self.sink, self.registry, self.reports, self.llm = FakeSink(), FakeRegistry(), FakeReports(), ScriptedLLM()
        self.trainer = FakeTrainer()
        ports = {
            "data": FakeData(self.rows), "splitter": FixedSplitter(), "trainer": self.trainer,
            "explainer": FakeExplainer(), "charts": FakeCharts(), "zero_shot": self.llm, "registry": self.registry,
            "export": ExportOnnxService(FakeExporter()), "sink": self.sink, "reports": self.reports, "clock": FixedClock(),
        }  # fmt: skip
        ports.update(overrides)
        self.service = TrainRiskModelService(RiskTrainingPorts(**ports))  # type: ignore[arg-type]
        self.tmp = tmp

    def command(self, source: str = "GOLD", llm: bool = True) -> TrainRiskCommand:
        return TrainRiskCommand(
            source, "v1", self.tmp / "model_a.md", self.tmp / "card.md", self.tmp / "m.onnx", self.tmp / "art", llm, 42
        )


def test_the_gold_run_selects_by_cv_macro_f1_and_stores_the_model_and_both_baselines(tmp_path: Path) -> None:
    world = World(tmp_path)
    result = world.service.execute(world.command())
    assert result.selected == "XGBOOST" and world.trainer.fitted == ["XGBOOST"]
    assert result.stored and result.h3_met is not None and result.onnx_parity
    names = sorted((m.model_name, m.version) for m in world.sink.stored)
    assert names == [("llm_zero_shot", "gemma3:4b-risk-zero-shot-v1"), ("risk_model", "v1"), ("rule_baseline", "v1")]
    model = next(m for m in world.sink.stored if m.model_name == "risk_model")
    assert model.publish and len(model.predictions) == len(world.rows)
    assert all(len(p.explanation) <= 3 for p in model.predictions)
    assert {m.scope for m in model.metrics} == {"CV_MEAN", "CV_STD", "TEST"}
    assert "Cohen" not in world.reports.texts[tmp_path / "model_a.md"]  # the report is about Model A, not labelling
    assert "## H3" in world.reports.texts[tmp_path / "model_a.md"]


def test_the_llm_is_asked_twice_and_its_invalid_answers_count_as_wrong(tmp_path: Path) -> None:
    world = World(tmp_path)
    result = world.service.execute(world.command())
    test_rows = result.test_rows
    assert world.llm.calls == 2 * test_rows
    llm = next(m for m in world.sink.stored if m.model_name == "llm_zero_shot")
    metric = {(m.metric, m.label): m.value for m in llm.metrics}
    assert metric[("INVALID_ANSWERS", "ALL")] == test_rows // 3
    assert metric[("TOKENS_PER_FINDING", "ALL")] == 202.0
    assert 0.0 <= metric[("RUN_AGREEMENT", "ALL")] <= 1.0


def test_a_dry_run_with_silver_labels_writes_nothing_to_ml_outputs_and_judges_no_h3(tmp_path: Path) -> None:
    world = World(tmp_path)
    result = world.service.execute(world.command("SILVER", llm=False))
    assert not result.stored and world.sink.stored == []
    assert result.h3_met is None and result.llm_macro_f1 is None
    assert "Deneme koşusu" in world.reports.texts[tmp_path / "model_a.md"]
    # One run per algorithm and the parent run, all in MLflow.
    assert [record.name for _, record in world.registry.runs] == [
        "cv-LOGISTIC_REGRESSION",
        "cv-XGBOOST",
        "risk_model-v1",
    ]
    parent = world.registry.runs[-1][1]
    assert parent.tags["label_source"] == "SILVER" and len(parent.tags["data_sha256"]) == 64


def test_a_split_that_leaks_a_project_is_refused(tmp_path: Path) -> None:
    rows = synthetic_rows()
    projects = frozenset(r.project_key for r in rows)
    leaking = ProjectSplit(projects, frozenset([next(iter(projects))]))
    with pytest.raises(RiskTrainingError, match="both sides"):
        World(tmp_path, splitter=FixedSplitter(leaking)).service.execute(World(tmp_path).command())


def test_no_gold_labels_and_a_failed_parity_and_an_unreachable_llm_stop_the_run(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.service = TrainRiskModelService(
        RiskTrainingPorts(
            FakeData([replace(r, gold_label=None) for r in world.rows]), FixedSplitter(), FakeTrainer(), FakeExplainer(),
            FakeCharts(), ScriptedLLM(), FakeRegistry(), ExportOnnxService(FakeExporter()), FakeSink(), FakeReports(),
            FixedClock(),
        )
    )  # fmt: skip
    with pytest.raises(RiskTrainingError, match="no gold labels"):
        world.service.execute(world.command())
    with pytest.raises(RiskTrainingError, match="parity"):
        World(tmp_path, export=ExportOnnxService(FakeExporter(Parity(3, True, 1e-3)))).service.execute(world.command())
    with pytest.raises(RiskTrainingError, match="local LLM"):
        World(tmp_path, zero_shot=ScriptedLLM(down=True)).service.execute(world.command())
    with pytest.raises(RiskTrainingError, match="GOLD or SILVER"):
        world.service.execute(replace(world.command(), label_source="BRONZE"))


def test_the_gold_run_stores_its_three_versions_in_one_call(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.service.execute(world.command())
    assert world.sink.calls == [3]  # the model, the rule baseline and the LLM in one transaction (D-329)


def test_a_project_erased_while_the_model_trained_is_not_stored_and_is_counted(tmp_path: Path) -> None:
    world = World(tmp_path)
    erased = world.rows[0].project_key
    world.sink.present([(r.finding_id, r.project_key) for r in world.rows])
    world.sink.erase(erased)  # while the model trained: its findings left the warehouse
    result = world.service.execute(world.command())
    model = next(m for m in world.sink.stored if m.model_name == "risk_model")
    assert result.erased_skipped == sum(1 for r in world.rows if r.project_key == erased) > 0
    assert all(p.project_key != erased for p in model.predictions)


def test_the_parent_run_carries_per_class_metrics_and_the_confusion_matrices(tmp_path: Path) -> None:
    world = World(tmp_path)
    result = world.service.execute(world.command())
    parent = world.registry.runs[-1][1]
    for prefix in ("test", "rule", "llm"):
        for label in ("critical", "high", "medium", "low"):
            assert {f"{prefix}_{label}_{m}" for m in ("precision", "recall", "f1")} <= set(parent.metrics)
    names = {a.name for a in parent.artifacts}
    assert {"confusion_XGBOOST.json", "confusion_rule_baseline_v1.json", "confusion_gemma3_4b.json"} <= names
    matrix = json.loads(world.reports.texts[tmp_path / "art" / "confusion_XGBOOST.json"])
    assert matrix["classes"] == ["CRITICAL", "HIGH", "MEDIUM", "LOW"]
    assert sum(map(sum, matrix["matrix"])) == result.test_rows


def test_the_report_lists_the_global_importance_of_the_explainer(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.service.execute(world.command())
    report = world.reports.texts[tmp_path / "model_a.md"]
    assert "- onehot__priority_P0: 0.5000" in report and "- flags__in_test_code: 0.1000" in report
