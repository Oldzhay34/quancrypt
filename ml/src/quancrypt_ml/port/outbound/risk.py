"""Outbound ports of Model A (P7.2, ml-pipeline section 1). The model libraries (scikit-learn, XGBoost, SHAP, ONNX,
MLflow) live behind them, in infrastructure only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from quancrypt_ml.domain.risk_features import RiskRow
from quancrypt_ml.domain.split import ProjectSplit


class TrainingDataSource(Protocol):
    """marts.mart_risk_features with its gold and silver labels (corpus and benchmark rows only, D-317h)."""

    def rows(self) -> list[RiskRow]: ...


class ProjectSplitter(Protocol):
    """The fixed test projects: one fold of a project-grouped split, stratified by the silver label (D-327f)."""

    def split(self, rows: Sequence[RiskRow], seed: int) -> ProjectSplit: ...


class TrainedModel(Protocol):
    """A fitted pipeline (preprocessing + classifier). It is opaque: the Explainer and the OnnxExporter of a family read
    the models of that family's ModelTrainer only (a precondition of their contracts; another model is a TypeError)."""

    @property
    def algorithm(self) -> str: ...

    @property
    def params(self) -> Mapping[str, object]: ...

    def probabilities(self, rows: Sequence[RiskRow]) -> list[dict[str, float]]:
        """One probability per risk class for every row."""
        ...


@dataclass(frozen=True)
class FoldResult:
    fold: int
    truth: tuple[str, ...]
    predicted: tuple[str, ...]
    params: Mapping[str, object]


class ModelTrainer(Protocol):
    """Grid search with an inner project-grouped CV; class weights balanced; fixed seed."""

    @property
    def algorithms(self) -> tuple[str, ...]: ...

    def grid(self, algorithm: str) -> Mapping[str, Sequence[object]]: ...

    def cross_validate(
        self, algorithm: str, rows: Sequence[RiskRow], labels: Sequence[str], folds: int
    ) -> list[FoldResult]:
        """The outer GroupKFold over the training projects: each fold searches the grid on its training part and
        predicts its validation part."""
        ...

    def fit(self, algorithm: str, rows: Sequence[RiskRow], labels: Sequence[str]) -> TrainedModel: ...


@dataclass(frozen=True)
class Attribution:
    feature: str
    value: float


class Explainer(Protocol):
    """SHAP: the three strongest features of each row's predicted class, the global importance (mean |SHAP| over the
    given rows and all classes) and a chart of that same importance."""

    def top_features(self, model: TrainedModel, rows: Sequence[RiskRow], k: int) -> list[list[Attribution]]:
        """One list per row, strongest first by |value|."""
        ...

    def global_importance(self, model: TrainedModel, rows: Sequence[RiskRow], k: int) -> list[Attribution]:
        """The k features with the highest mean |SHAP|, highest first (`value` is the mean |SHAP|)."""
        ...

    def summary_chart(self, model: TrainedModel, rows: Sequence[RiskRow], path: Path) -> None: ...


class Charts(Protocol):
    def calibration(self, truth: Sequence[str], probabilities: Sequence[Mapping[str, float]], path: Path) -> None: ...


@dataclass(frozen=True)
class ZeroShotAnswer:
    label: str | None  # None: the answer was not one of the four classes
    seconds: float
    prompt_tokens: int
    output_tokens: int


class ZeroShotUnavailableError(Exception):
    """The local LLM cannot be reached or does not have the model."""


class ZeroShotClassifier(Protocol):
    """The local LLM's zero-shot classification of a finding from its canonical fields (fixed prompt, temperature 0)."""

    @property
    def model_id(self) -> str: ...

    @property
    def prompt_version(self) -> str: ...

    def classify(self, row: RiskRow) -> ZeroShotAnswer: ...


@dataclass(frozen=True)
class RunRecord:
    name: str
    params: Mapping[str, object]
    metrics: Mapping[str, float]
    tags: Mapping[str, str]
    artifacts: Sequence[Path]


class ModelRegistry(Protocol):
    """MLflow: every training is a run; the parent run gets the child runs' ids as tags."""

    def log_run(self, experiment: str, record: RunRecord, parent_run_id: str | None = None) -> str: ...


@dataclass(frozen=True)
class Parity:
    rows: int
    classes_equal: bool
    max_probability_difference: float
    # The trained model's probabilities of the rows, in RISK_CLASSES order (the fixed set agent-service checks its ONNX
    # runtime against, P7.5) and the SHA-256 of the written model file.
    reference: tuple[tuple[float, ...], ...] = ()
    sha256: str = ""


class OnnxExporter(Protocol):
    def export(self, model: TrainedModel, rows: Sequence[RiskRow], path: Path) -> Parity:
        """Stages the ONNX model of `path` beside it and compares the staged content's answers with the model's on the
        given rows. `path` itself is not touched."""
        ...

    def promote(self, path: Path) -> None:
        """The staged model becomes `path` (only after its parity passed, D-346c)."""
        ...

    def discard(self, path: Path) -> None:
        """Removes the staged model; `path` stays as it was."""
        ...


@dataclass(frozen=True)
class MetricValue:
    scope: str  # CV_FOLD, CV_MEAN, CV_STD, TEST
    fold: int  # 0 unless scope is CV_FOLD
    metric: str
    label: str  # a risk class or ALL
    value: float


@dataclass(frozen=True)
class Prediction:
    finding_id: str
    project_key: str
    risk_class: str
    risk_score: float
    explanation: Sequence[Attribution]


@dataclass(frozen=True)
class StoredModel:
    model_name: str
    version: str
    algorithm: str
    label_source: str
    mlflow_run_id: str | None
    trained_at: datetime
    metrics: Sequence[MetricValue]
    predictions: Sequence[Prediction]
    publish: bool


class FindingConflictError(Exception):
    """A scored finding is already stored with another project key (one finding, one project); nothing is written."""


class PublishedVersionError(Exception):
    """A published version would be written again unpublished (the marts would lose their scores); nothing is
    written."""


class ResultSink(Protocol):
    """warehouse_db.ml_outputs (ml/migrations 0002): one model version with its metrics and predictions, replaced as a
    whole in one transaction; a published version is what the warehouse marts read."""

    def store(self, models: Sequence[StoredModel]) -> int:
        """The versions of one training run, in one transaction (all or none).

        A prediction whose finding is no longer in the warehouse (erased by KVKK, consent_revoked, while the model
        trained) is not written: it would bring back data the erasure took. Returns the number of predictions left out
        this way. A published version written again with `publish=False` raises PublishedVersionError."""
        ...
