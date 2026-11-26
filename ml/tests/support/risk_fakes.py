"""Test doubles of the Model A ports: a majority-class trainer, a fixed explainer, a scripted LLM, in-memory MLflow and
ml_outputs. No model library."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.risk_features import RiskRow
from quancrypt_ml.domain.split import ProjectSplit
from quancrypt_ml.port.outbound.risk import (
    Attribution,
    FindingConflictError,
    FoldResult,
    Parity,
    PublishedVersionError,
    RunRecord,
    StoredModel,
    TrainedModel,
    ZeroShotAnswer,
    ZeroShotUnavailableError,
)


class FakeData:
    def __init__(self, rows: Sequence[RiskRow]) -> None:
        self.rows_ = list(rows)

    def rows(self) -> list[RiskRow]:
        return sorted(self.rows_, key=lambda r: r.finding_id)


class FixedSplitter:
    """Every fifth project is a test project (or the given split, to test a leak)."""

    def __init__(self, split: ProjectSplit | None = None) -> None:
        self._split = split

    def split(self, rows: Sequence[RiskRow], seed: int) -> ProjectSplit:
        if self._split is not None:
            return self._split
        projects = sorted({r.project_key for r in rows})
        test = frozenset(projects[::5])
        return ProjectSplit(frozenset(projects) - test, test)


@dataclass
class PriorityModel:
    """Predicts the class the priority maps to (a perfect rule learner on the synthetic data)."""

    algorithm: str
    params: Mapping[str, object]

    def probabilities(self, rows: Sequence[RiskRow]) -> list[dict[str, float]]:
        mapping = {"P0": "CRITICAL", "P1": "HIGH", "P2": "MEDIUM", "P3": "LOW"}
        return [{c: 1.0 if c == mapping[r.priority] else 0.0 for c in RISK_CLASSES} for r in rows]


class FakeTrainer:
    algorithms = ("LOGISTIC_REGRESSION", "XGBOOST")

    def __init__(self) -> None:
        self.fitted: list[str] = []

    def grid(self, algorithm: str) -> Mapping[str, Sequence[object]]:
        return {"C": (1.0,)}

    def cross_validate(
        self, algorithm: str, rows: Sequence[RiskRow], labels: Sequence[str], folds: int
    ) -> list[FoldResult]:
        """Projects dealt round-robin into min(folds, projects) folds (no project in two folds)."""
        model = PriorityModel(algorithm, {})
        projects = sorted({r.project_key for r in rows})
        k = min(folds, len(projects))
        fold_of = {p: i % k for i, p in enumerate(projects)}
        majority = Counter(labels).most_common(1)[0][0]
        results = []
        for fold in range(k):
            picked = [i for i, r in enumerate(rows) if fold_of[r.project_key] == fold]
            truth = tuple(labels[i] for i in picked)
            if algorithm == "LOGISTIC_REGRESSION":
                predicted = tuple(majority for _ in picked)
            else:
                probabilities = model.probabilities([rows[i] for i in picked])
                predicted = tuple(max(p, key=p.__getitem__) for p in probabilities)
            results.append(FoldResult(fold + 1, truth, predicted, {"C": 1.0}))
        return results

    def fit(self, algorithm: str, rows: Sequence[RiskRow], labels: Sequence[str]) -> TrainedModel:
        self.fitted.append(algorithm)
        return PriorityModel(algorithm, {"C": 1.0})


class FakeExplainer:
    def top_features(self, model: TrainedModel, rows: Sequence[RiskRow], k: int) -> list[list[Attribution]]:
        return [
            [Attribution("onehot__priority_" + r.priority, 0.5), Attribution("flags__in_test_code", -0.1)][:k]
            for r in rows
        ]

    def global_importance(self, model: TrainedModel, rows: Sequence[RiskRow], k: int) -> list[Attribution]:
        return [Attribution("onehot__priority_P0", 0.5), Attribution("flags__in_test_code", 0.1)][:k]

    def summary_chart(self, model: TrainedModel, rows: Sequence[RiskRow], path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("chart", encoding="utf-8")


class FakeCharts:
    def calibration(self, truth: Sequence[str], probabilities: Sequence[Mapping[str, float]], path: Path) -> None:
        path.write_text("calibration", encoding="utf-8")


class ScriptedLLM:
    """Answers the silver label, except for every third finding (invalid) — or is unreachable."""

    model_id = "gemma3:4b"
    prompt_version = "risk-zero-shot-v1"

    def __init__(self, down: bool = False, answer: str | None = None) -> None:
        self.down = down
        self.answer = answer  # always this text, read with the adapter's rule (exactly one class word)
        self.calls = 0

    def classify(self, row: RiskRow) -> ZeroShotAnswer:
        if self.down:
            raise ZeroShotUnavailableError("down")
        self.calls += 1
        if self.answer is not None:
            word = self.answer.strip().strip(".").upper()
            return ZeroShotAnswer(word if word in RISK_CLASSES else None, 0.5, 200, 2)
        label = None if self.calls % 3 == 0 else row.silver_label
        return ZeroShotAnswer(label, 0.5, 200, 2)


@dataclass
class FakeRegistry:
    runs: list[tuple[str, RunRecord]] = field(default_factory=list)

    def log_run(self, experiment: str, record: RunRecord, parent_run_id: str | None = None) -> str:
        self.runs.append((experiment, record))
        return f"{len(self.runs):032x}"


class FakeExporter:
    """Stages like the real exporter: `path` is written only by promote() (D-346c)."""

    def __init__(self, parity: Parity | None = None) -> None:
        self._parity = parity
        self._staged: set[Path] = set()
        self.promoted: list[Path] = []

    def export(self, model: TrainedModel, rows: Sequence[RiskRow], path: Path) -> Parity:
        self._staged.add(path)
        return self._parity or Parity(len(rows), True, 1e-7)

    def promote(self, path: Path) -> None:
        assert path in self._staged
        self._staged.discard(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"onnx")
        self.promoted.append(path)

    def discard(self, path: Path) -> None:
        self._staged.discard(path)


@dataclass
class FakeSink:
    stored: list[StoredModel] = field(default_factory=list)
    # The warehouse's findings (finding -> project key); None: no warehouse, every prediction is written (as the
    # PostgreSQL sink without prep.finding).
    warehouse: dict[str, str] | None = None
    calls: list[int] = field(default_factory=list)  # the number of versions in each store call

    def present(self, findings: Sequence[tuple[str, str]]) -> None:
        self.warehouse = {**(self.warehouse or {}), **dict(findings)}

    def erase(self, project_key: str) -> None:
        """A KVKK erasure of the key: its findings leave the warehouse and its predictions ml_outputs."""
        self.warehouse = {f: k for f, k in (self.warehouse or {}).items() if k != project_key}
        self.stored = [
            replace(m, predictions=[p for p in m.predictions if p.project_key != project_key]) for m in self.stored
        ]

    def store(self, models: Sequence[StoredModel]) -> int:
        self.calls.append(len(models))
        published = {(m.model_name, m.version) for m in self.stored if m.publish}
        if any(not m.publish and (m.model_name, m.version) in published for m in models):
            raise PublishedVersionError("a published version cannot be written again unpublished")
        snapshot, skipped = list(self.stored), 0
        try:
            for model in models:
                kept = [p for p in model.predictions if self.warehouse is None or p.finding_id in self.warehouse]
                skipped += len(model.predictions) - len(kept)
                self._store_one(replace(model, predictions=kept))
        except BaseException:
            self.stored = snapshot
            raise
        return skipped

    def _store_one(self, model: StoredModel) -> None:
        keys = {p.finding_id: p.project_key for m in self.stored for p in m.predictions}
        if any(keys.get(p.finding_id, p.project_key) != p.project_key for p in model.predictions):
            raise FindingConflictError("a finding is stored with another project key")
        kept = [m for m in self.stored if (m.model_name, m.version) != (model.model_name, model.version)]
        if model.publish:
            kept = [replace(m, publish=False) if m.model_name == model.model_name else m for m in kept]
        self.stored = [*kept, model]

    def read(self) -> dict[tuple[str, str], dict[str, object]]:
        return {
            (m.model_name, m.version): {
                "predictions": {p.finding_id: p.risk_class for p in m.predictions},
                "published": m.publish,
                "metrics": len(m.metrics),
            }
            for m in self.stored
        }
