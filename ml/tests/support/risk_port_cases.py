"""Shared contracts of the Model A outbound ports (LSP, hexagonal-service section 7, D-324f): every port with a fake runs
the same cases against the fake and the real adapter.

The trainer, explainer and exporter form a family: the explainer and the exporter read the models of their own family's
trainer only (a precondition of the TrainedModel port), so those cases take the three together."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.risk_features import RiskRow
from quancrypt_ml.port.outbound.risk import (
    Attribution,
    Charts,
    Explainer,
    FindingConflictError,
    MetricValue,
    ModelRegistry,
    ModelTrainer,
    OnnxExporter,
    Prediction,
    PublishedVersionError,
    ResultSink,
    RunRecord,
    StoredModel,
    TrainingDataSource,
    ZeroShotClassifier,
    ZeroShotUnavailableError,
)
from tests.support.risk_rows import synthetic_rows

ROWS = synthetic_rows(120, projects=10)

# ---------------------------------------------------------------- TrainingDataSource
DataFactory = Callable[[Sequence[RiskRow]], TrainingDataSource]


def data_case_every_row_comes_back_in_id_order(factory: DataFactory) -> None:
    rows = synthetic_rows(6, projects=3)
    assert factory(list(reversed(rows))).rows() == sorted(rows, key=lambda r: r.finding_id)


DATA_CASES = [data_case_every_row_comes_back_in_id_order]

# ---------------------------------------------------------------- ModelTrainer + Explainer + OnnxExporter


@dataclass(frozen=True)
class ModelFamily:
    trainer: ModelTrainer
    explainer: Explainer
    exporter: OnnxExporter


def _labels(rows: Sequence[RiskRow]) -> list[str]:
    return [r.gold_label or "" for r in rows]


def family_case_cross_validation_covers_every_row_once_without_mixing_projects(family: ModelFamily) -> None:
    algorithm = family.trainer.algorithms[0]
    folds = family.trainer.cross_validate(algorithm, ROWS, _labels(ROWS), 5)
    assert len(folds) == 5 and sum(len(f.truth) for f in folds) == len(ROWS)
    assert all(set(f.predicted) <= set(RISK_CLASSES) and len(f.predicted) == len(f.truth) for f in folds)
    assert dict(family.trainer.grid(algorithm))


def family_case_a_fitted_model_gives_one_distribution_over_the_four_classes_per_row(family: ModelFamily) -> None:
    model = family.trainer.fit(family.trainer.algorithms[0], ROWS, _labels(ROWS))
    probabilities = model.probabilities(ROWS[:7])
    assert len(probabilities) == 7
    assert all(set(p) == set(RISK_CLASSES) and abs(sum(p.values()) - 1.0) < 1e-6 for p in probabilities)


def family_case_attributions_are_strongest_first(family: ModelFamily, folder: Path) -> None:
    model = family.trainer.fit(family.trainer.algorithms[0], ROWS, _labels(ROWS))
    top = family.explainer.top_features(model, ROWS[:4], 2)
    assert len(top) == 4 and all(len(row) <= 2 for row in top)
    assert all(abs(row[i].value) >= abs(row[i + 1].value) for row in top for i in range(len(row) - 1))
    importance = family.explainer.global_importance(model, ROWS, 3)
    assert 0 < len(importance) <= 3 and all(isinstance(a, Attribution) for a in importance)
    assert [a.value for a in importance] == sorted((a.value for a in importance), reverse=True)
    family.explainer.summary_chart(model, ROWS, folder / "summary.png")
    assert (folder / "summary.png").stat().st_size > 0


def family_case_the_exported_model_answers_like_the_trained_one(family: ModelFamily, folder: Path) -> None:
    model = family.trainer.fit(family.trainer.algorithms[0], ROWS, _labels(ROWS))
    parity = family.exporter.export(model, ROWS[:9], folder / "model.onnx")
    assert not (folder / "model.onnx").exists()  # staged only, until the parity passed (D-346c)
    family.exporter.promote(folder / "model.onnx")
    assert (folder / "model.onnx").stat().st_size > 0
    assert parity.rows == 9 and parity.classes_equal and parity.max_probability_difference <= 1e-4


FAMILY_CASES = [
    family_case_cross_validation_covers_every_row_once_without_mixing_projects,
    family_case_a_fitted_model_gives_one_distribution_over_the_four_classes_per_row,
]
FAMILY_FILE_CASES = [
    family_case_attributions_are_strongest_first,
    family_case_the_exported_model_answers_like_the_trained_one,
]

# ---------------------------------------------------------------- Charts


def charts_case_a_calibration_chart_is_written(charts: Charts, folder: Path) -> None:
    truth = ["HIGH", "LOW", "LOW", "CRITICAL"]
    probabilities: list[Mapping[str, float]] = [
        {"CRITICAL": 0.1, "HIGH": 0.7, "MEDIUM": 0.1, "LOW": 0.1},
        {"CRITICAL": 0.0, "HIGH": 0.1, "MEDIUM": 0.1, "LOW": 0.8},
        {"CRITICAL": 0.0, "HIGH": 0.3, "MEDIUM": 0.1, "LOW": 0.6},
        {"CRITICAL": 0.6, "HIGH": 0.3, "MEDIUM": 0.1, "LOW": 0.0},
    ]
    charts.calibration(truth, probabilities, folder / "calibration.png")
    assert (folder / "calibration.png").stat().st_size > 0


CHART_CASES = [charts_case_a_calibration_chart_is_written]

# ---------------------------------------------------------------- ZeroShotClassifier
# A factory builds a classifier whose LLM always answers the given text, or is unreachable when the text is None.
ZeroShotFactory = Callable[[str | None], ZeroShotClassifier]


def zero_shot_case_a_class_word_is_an_answer_and_anything_else_is_invalid(factory: ZeroShotFactory) -> None:
    row = ROWS[0]
    assert factory("HIGH").classify(row).label == "HIGH"
    assert factory(" low. ").classify(row).label == "LOW"
    answer = factory("It is HIGH risk").classify(row)
    assert answer.label is None and answer.seconds >= 0 and answer.prompt_tokens >= 0


def zero_shot_case_an_unreachable_llm_is_reported(factory: ZeroShotFactory) -> None:
    with pytest.raises(ZeroShotUnavailableError):
        factory(None).classify(ROWS[0])


ZERO_SHOT_CASES = [
    zero_shot_case_a_class_word_is_an_answer_and_anything_else_is_invalid,
    zero_shot_case_an_unreachable_llm_is_reported,
]

# ---------------------------------------------------------------- ModelRegistry


def registry_case_each_run_gets_its_own_32_hex_id(registry: ModelRegistry, folder: Path) -> None:
    artifact = folder / "a.json"
    artifact.write_text("{}", encoding="utf-8")
    parent = registry.log_run("model_a_risk", RunRecord("parent", {"C": 1.0}, {"m": 0.5}, {"t": "x"}, [artifact]))
    child = registry.log_run("model_a_risk", RunRecord("child", {}, {}, {}, []), parent_run_id=parent)
    assert parent != child
    assert all(len(i) == 32 and all(c in "0123456789abcdef" for c in i) for i in (parent, child))


REGISTRY_CASES = [registry_case_each_run_gets_its_own_32_hex_id]

# ---------------------------------------------------------------- ResultSink
# The second callable reads the stored state: (model name, version) -> predictions, published flag, metric count.
Reader = Callable[[], dict[tuple[str, str], dict[str, object]]]
AT = datetime(2026, 11, 25, tzinfo=UTC)
KEY_A, KEY_B = "a" * 64, "b" * 64


def _prediction(finding: str, key: str = KEY_A, label: str = "HIGH") -> Prediction:
    return Prediction(finding, key, label, 0.7, [Attribution("onehot__priority_P1", 0.4)])


def _stored(predictions: list[Prediction], version: str = "v1", publish: bool = True) -> StoredModel:
    metrics = [MetricValue("TEST", 0, "MACRO_F1", "ALL", 0.8)]
    return StoredModel("risk_model", version, "XGBOOST", "GOLD", None, AT, metrics, predictions, publish)


def sink_case_a_version_is_replaced_as_a_whole(sink: ResultSink, read: Reader) -> None:
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    sink.store([_stored([_prediction(a), _prediction(b)])])
    sink.store([_stored([_prediction(a, label="LOW")])])
    state = read()
    assert state[("risk_model", "v1")]["predictions"] == {a: "LOW"}
    assert state[("risk_model", "v1")]["published"] is True and state[("risk_model", "v1")]["metrics"] == 1


def sink_case_one_version_per_name_is_published_and_a_baseline_is_not(sink: ResultSink, read: Reader) -> None:
    sink.store([_stored([_prediction(str(uuid.uuid4()))], "v1")])
    sink.store([_stored([], "v2")])
    sink.store([StoredModel("rule_baseline", "v1", "RULE_BASELINE", "GOLD", None, AT, [], [], False)])
    state = read()
    assert (state[("risk_model", "v1")]["published"], state[("risk_model", "v2")]["published"]) == (False, True)
    assert state[("rule_baseline", "v1")]["published"] is False


def sink_case_a_finding_under_another_project_key_is_refused_and_nothing_is_written(
    sink: ResultSink, read: Reader
) -> None:
    finding = str(uuid.uuid4())
    sink.store([_stored([_prediction(finding, KEY_A)])])
    with pytest.raises(FindingConflictError):
        sink.store([_stored([_prediction(finding, KEY_B)], "v2")])
    assert ("risk_model", "v2") not in read()


def sink_case_one_run_is_stored_all_or_nothing(sink: ResultSink, read: Reader) -> None:
    """A failure in the run's second version leaves the first one (and every earlier version) as it was."""
    kept, finding = str(uuid.uuid4()), str(uuid.uuid4())
    sink.store([_stored([_prediction(kept)]), _stored([_prediction(finding, KEY_A)], "v0", publish=False)])
    before = read()
    baseline = StoredModel(
        "rule_baseline", "v1", "RULE_BASELINE", "GOLD", None, AT, [], [_prediction(finding, KEY_B)], False
    )
    with pytest.raises(FindingConflictError):
        sink.store([_stored([_prediction(kept, label="LOW")], "v2"), baseline])
    assert read() == before


def sink_case_a_published_version_is_not_written_again_unpublished(sink: ResultSink, read: Reader) -> None:
    sink.store([_stored([_prediction(str(uuid.uuid4()))])])
    before = read()
    with pytest.raises(PublishedVersionError):
        sink.store([_stored([], publish=False)])
    assert read() == before


SINK_CASES = [
    sink_case_a_version_is_replaced_as_a_whole,
    sink_case_a_published_version_is_not_written_again_unpublished,
    sink_case_one_run_is_stored_all_or_nothing,
    sink_case_one_version_per_name_is_published_and_a_baseline_is_not,
    sink_case_a_finding_under_another_project_key_is_refused_and_nothing_is_written,
]

# ---------------------------------------------------------------- ResultSink and the KVKK erasure (D-330, D-331)


@dataclass(frozen=True)
class Warehouse:
    """present((finding, key), ...): those findings are in the warehouse (prep.finding). erase(key): a committed KVKK
    erasure of the key (its findings and its ml_outputs rows are gone)."""

    present: Callable[[Sequence[tuple[str, str]]], None]
    erase: Callable[[str], None]


def erasure_case_a_finding_erased_while_the_model_trained_is_left_out(
    sink: ResultSink, read: Reader, warehouse: Warehouse
) -> None:
    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    warehouse.present([(a, KEY_A), (b, KEY_B)])  # the training data was read
    warehouse.erase(KEY_B)  # while the model trained
    assert sink.store([_stored([_prediction(a, KEY_A), _prediction(b, KEY_B)])]) == 1
    assert read()[("risk_model", "v1")]["predictions"] == {a: "HIGH"}


def erasure_case_a_key_that_came_back_is_written_with_its_new_findings(
    sink: ResultSink, read: Reader, warehouse: Warehouse
) -> None:
    old, new = str(uuid.uuid4()), str(uuid.uuid4())
    warehouse.present([(old, KEY_A)])
    warehouse.erase(KEY_A)
    warehouse.present([(new, KEY_A)])  # a new event of the key, preprocessed again (new finding ids)
    assert sink.store([_stored([_prediction(old, KEY_A), _prediction(new, KEY_A)])]) == 1
    assert read()[("risk_model", "v1")]["predictions"] == {new: "HIGH"}


ERASURE_CASES = [
    erasure_case_a_finding_erased_while_the_model_trained_is_left_out,
    erasure_case_a_key_that_came_back_is_written_with_its_new_findings,
]
