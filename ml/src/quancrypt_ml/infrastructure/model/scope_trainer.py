"""ScopeTrainer with scikit-learn (P7.3, D-333c): the logistic regression and the sigmoid-calibrated linear SVM heads
over the embedding vectors.

Pipeline: StandardScaler (double), a float32 cast and the classifier (the ONNX parity of P7.2, D-328a). The grid is
searched by hand rather than with GridSearchCV: the SVM's calibration needs its own group-aware folds inside every
training part, and the groups are the paraphrase groups (`seed_id`), so no paraphrase of a request is calibrated or
scored against itself. The folds are StratifiedGroupKFold (groups and label), so every fold holds both classes."""

from __future__ import annotations

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from skl2onnx.sklapi import CastTransformer
from sklearn.base import BaseEstimator
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from quancrypt_ml.domain.scope import OUT_OF_SCOPE
from quancrypt_ml.port.outbound.scope_model import SearchResult, Vector

LOGISTIC_REGRESSION, LINEAR_SVM = "LOGISTIC_REGRESSION", "LINEAR_SVM"
GRIDS: dict[str, dict[str, tuple[object, ...]]] = {
    LOGISTIC_REGRESSION: {"C": (0.1, 1.0, 10.0)},
    LINEAR_SVM: {"C": (0.1, 1.0, 10.0)},
}
CALIBRATION_FOLDS = 3


def _folds(y: np.ndarray, groups: Sequence[str], count: int, seed: int) -> list[tuple[np.ndarray, np.ndarray]]:
    """Group-aware and stratified by the label, so no fold holds a single class (its ROC AUC would be undefined)."""
    k = min(count, len(set(groups)))
    splitter = StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed)
    folds = list(splitter.split(np.zeros(len(groups)), y, groups=list(groups)))
    if any(len(set(y[train].tolist())) < 2 or len(set(y[held].tolist())) < 2 for train, held in folds):
        raise ValueError("a fold holds a single class")
    return folds


def _classifier(
    algorithm: str, params: Mapping[str, object], y: np.ndarray, groups: Sequence[str], seed: int
) -> BaseEstimator:
    c = float(params["C"])  # type: ignore[arg-type]
    if algorithm == LOGISTIC_REGRESSION:
        return LogisticRegression(C=c, class_weight="balanced", max_iter=5000, random_state=seed)
    if algorithm == LINEAR_SVM:
        svm = LinearSVC(C=c, class_weight="balanced", max_iter=20000, random_state=seed)
        return CalibratedClassifierCV(svm, method="sigmoid", cv=_folds(y, groups, CALIBRATION_FOLDS, seed))
    raise ValueError(f"unknown algorithm {algorithm}")


def _pipeline(
    algorithm: str, params: Mapping[str, object], y: np.ndarray, groups: Sequence[str], seed: int
) -> Pipeline:
    return Pipeline([
        ("scale", StandardScaler()), ("cast", CastTransformer(dtype=np.float32)),
        ("clf", _classifier(algorithm, params, y, groups, seed)),
    ])  # fmt: skip


def _y(labels: Sequence[str]) -> np.ndarray:
    return np.asarray([1 if label == OUT_OF_SCOPE else 0 for label in labels], dtype=np.int64)


def _x(vectors: Sequence[Vector]) -> np.ndarray:
    return np.asarray(vectors, dtype=np.float64)


@dataclass(frozen=True)
class SklearnScopeModel:
    algorithm: str
    params: Mapping[str, object]
    estimator: Any  # the fitted Pipeline

    def p_out(self, vectors: Sequence[Vector]) -> list[float]:
        if not vectors:
            return []
        column = list(self.estimator.classes_).index(1)
        return [float(p) for p in self.estimator.predict_proba(_x(vectors))[:, column]]


class SklearnScopeTrainer:
    algorithms = (LOGISTIC_REGRESSION, LINEAR_SVM)  # the default (D-332b) first

    def grid(self, algorithm: str) -> Mapping[str, Sequence[object]]:
        return GRIDS[algorithm]

    def search(
        self,
        algorithm: str,
        vectors: Sequence[Vector],
        labels: Sequence[str],
        groups: Sequence[str],
        folds: int,
        seed: int,
    ) -> SearchResult:
        x, y, g = _x(vectors), _y(labels), list(groups)
        splits = _folds(y, g, folds, seed)
        best: tuple[float, dict[str, object], tuple[float, ...]] | None = None
        for c in GRIDS[algorithm]["C"]:
            params: dict[str, object] = {"C": c}
            scores = []
            for train, held_out in splits:
                model = _pipeline(algorithm, params, y[train], [g[i] for i in train], seed).fit(x[train], y[train])
                probability = model.predict_proba(x[held_out])[:, list(model.classes_).index(1)]
                scores.append(float(roc_auc_score(y[held_out], probability)))
            mean = statistics.fmean(scores)
            if best is None or mean > best[0]:  # a tie keeps the smaller C (the grid is ascending)
                best = (mean, params, tuple(scores))
        if best is None:
            raise ValueError("the grid is empty")
        return SearchResult(algorithm, best[1], best[2])

    def fit(
        self,
        algorithm: str,
        params: Mapping[str, object],
        vectors: Sequence[Vector],
        labels: Sequence[str],
        groups: Sequence[str],
        seed: int,
    ) -> SklearnScopeModel:
        y = _y(labels)
        estimator = _pipeline(algorithm, params, y, groups, seed).fit(_x(vectors), y)
        return SklearnScopeModel(algorithm, dict(params), estimator)
