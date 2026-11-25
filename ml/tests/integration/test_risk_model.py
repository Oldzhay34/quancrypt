"""Model A with the real libraries on synthetic findings: the project split (acceptance 1), the three algorithms, ONNX parity
(acceptance 3), SHAP and reproducibility (ml-pipeline section 8)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quancrypt_ml.domain.split import leaked_projects, partition
from quancrypt_ml.infrastructure.model.analysis import MatplotlibCharts, ShapExplainer, StratifiedProjectSplitter
from quancrypt_ml.infrastructure.model.onnx_exporter import SklearnOnnxExporter
from quancrypt_ml.infrastructure.model.pipeline import ALGORITHMS
from quancrypt_ml.infrastructure.model.trainer import SklearnModelTrainer
from tests.support.risk_rows import synthetic_rows

ROWS = synthetic_rows()


def _train_test() -> tuple[list, list]:  # type: ignore[type-arg]
    split = StratifiedProjectSplitter().split(ROWS, 42)
    return partition(ROWS, split)


def test_no_test_project_is_seen_in_training_and_the_split_is_fixed() -> None:
    splitter = StratifiedProjectSplitter()
    split = splitter.split(ROWS, 42)
    assert leaked_projects(split) == set()
    assert split.train_projects | split.test_projects == {r.project_key for r in ROWS}
    assert len(split.test_projects) == 5  # one of five folds of 25 projects
    assert splitter.split(ROWS, 42) == split  # fixed for a seed
    train, test = partition(ROWS, split)
    assert {r.project_key for r in train}.isdisjoint({r.project_key for r in test})


def test_the_split_ignores_the_gold_labels() -> None:
    from dataclasses import replace

    relabelled = [replace(r, gold_label="LOW") for r in ROWS]
    assert StratifiedProjectSplitter().split(relabelled, 42) == StratifiedProjectSplitter().split(ROWS, 42)


@pytest.mark.parametrize("algorithm", ALGORITHMS)
def test_each_algorithm_cross_validates_by_project_and_its_onnx_answers_like_it(algorithm: str, tmp_path: Path) -> None:
    train, test = _train_test()
    trainer = SklearnModelTrainer()
    labels = [r.gold_label or "" for r in train]
    folds = trainer.cross_validate(algorithm, train, labels, 5)
    assert len(folds) == 5 and sum(len(f.truth) for f in folds) == len(train)
    model = trainer.fit(algorithm, train, labels)
    probabilities = model.probabilities(test)
    assert all(abs(sum(p.values()) - 1.0) < 1e-6 for p in probabilities)
    parity = SklearnOnnxExporter().export(model, test, tmp_path / "risk_model.onnx")
    assert parity.classes_equal and parity.max_probability_difference <= 1e-4 and parity.rows == len(test)
    top = ShapExplainer().top_features(model, test[:5], 3)
    assert all(len(row) == 3 for row in top)
    assert all(abs(row[0].value) >= abs(row[1].value) >= abs(row[2].value) for row in top)
    ShapExplainer().summary_chart(model, train, tmp_path / "shap.png")
    MatplotlibCharts().calibration([r.gold_label or "" for r in test], probabilities, tmp_path / "calibration.png")
    assert (tmp_path / "shap.png").stat().st_size > 0 and (tmp_path / "calibration.png").stat().st_size > 0


def test_a_training_without_a_rare_class_still_predicts_every_class_column() -> None:
    train, test = _train_test()
    without_medium = [r for r in train if r.gold_label != "MEDIUM"]
    model = SklearnModelTrainer().fit("XGBOOST", without_medium, [r.gold_label or "" for r in without_medium])
    probabilities = model.probabilities(test)
    assert all(p["MEDIUM"] == 0.0 and set(p) == {"CRITICAL", "HIGH", "MEDIUM", "LOW"} for p in probabilities)


def test_two_trainings_on_the_same_data_give_the_same_folds_and_predictions() -> None:
    train, test = _train_test()
    labels = [r.gold_label or "" for r in train]
    for algorithm in ALGORITHMS:
        first, second = SklearnModelTrainer(), SklearnModelTrainer()
        assert first.cross_validate(algorithm, train, labels, 5) == second.cross_validate(algorithm, train, labels, 5)
        assert first.fit(algorithm, train, labels).probabilities(test) == second.fit(
            algorithm, train, labels
        ).probabilities(test)
