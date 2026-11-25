"""ModelTrainer with scikit-learn (P7.2, D-327): an outer project-grouped CV for the report and, inside each fold and
for the final fit, a grid search with an inner project-grouped CV scored by macro-F1. Splits are computed up front and
passed as index lists, so no project crosses a fold."""

from __future__ import annotations

import warnings
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.model_selection import GridSearchCV, GroupKFold
from sklearn.pipeline import Pipeline

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.risk_features import RiskRow
from quancrypt_ml.infrastructure.model.pipeline import (
    ALGORITHMS,
    GRIDS,
    SEED,
    encode,
    frame,
    pipeline,
)
from quancrypt_ml.port.outbound.risk import FoldResult

INNER_FOLDS = 3


def _splits(groups: NDArray[np.str_], folds: int) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    k = min(folds, len(set(groups.tolist())))
    if k < 2:
        raise ValueError("cross-validation needs at least two projects")
    return list(GroupKFold(n_splits=k).split(np.zeros(len(groups)), groups=groups))


@dataclass(frozen=True)
class SklearnTrainedModel:
    algorithm: str
    params: Mapping[str, object]
    estimator: Pipeline

    def probabilities(self, rows: Sequence[RiskRow]) -> list[dict[str, float]]:
        raw = self.estimator.predict_proba(frame(rows))
        classes = [RISK_CLASSES[int(c)] for c in self.estimator.classes_]
        return [{c: float(p[classes.index(c)]) if c in classes else 0.0 for c in RISK_CLASSES} for p in raw]


class SklearnModelTrainer:
    @property
    def algorithms(self) -> tuple[str, ...]:
        return ALGORITHMS

    def grid(self, algorithm: str) -> Mapping[str, Sequence[object]]:
        return GRIDS[algorithm]

    def _search(self, algorithm: str, x: Any, y: NDArray[np.int64], groups: NDArray[np.str_]) -> GridSearchCV:
        grid = {f"clf__{k}": list(v) for k, v in GRIDS[algorithm].items()}
        search = GridSearchCV(
            pipeline(algorithm, {}), grid, scoring="f1_macro", cv=_splits(groups, INNER_FOLDS), refit=True, n_jobs=1,
            error_score="raise",
        )  # fmt: skip
        with warnings.catch_warnings():
            # A fold without a rare class makes precision undefined for it; macro-F1 then counts it as 0 (intended).
            warnings.simplefilter("ignore", category=UserWarning)
            warnings.filterwarnings("ignore", message=".*ill-defined.*")
            search.fit(x, y)
        return search

    def cross_validate(
        self, algorithm: str, rows: Sequence[RiskRow], labels: Sequence[str], folds: int
    ) -> list[FoldResult]:
        x, y = frame(rows), encode(labels)
        groups = np.asarray([r.project_key for r in rows], dtype=str)
        results = []
        for number, (train, valid) in enumerate(_splits(groups, folds), start=1):
            search = self._search(algorithm, x.iloc[train], y[train], groups[train])
            predicted = search.predict(x.iloc[valid])
            results.append(
                FoldResult(
                    fold=number,
                    truth=tuple(RISK_CLASSES[int(c)] for c in y[valid]),
                    predicted=tuple(RISK_CLASSES[int(c)] for c in predicted),
                    params={k.removeprefix("clf__"): v for k, v in search.best_params_.items()},
                )
            )
        return results

    def fit(self, algorithm: str, rows: Sequence[RiskRow], labels: Sequence[str]) -> SklearnTrainedModel:
        x, y = frame(rows), encode(labels)
        groups = np.asarray([r.project_key for r in rows], dtype=str)
        search = self._search(algorithm, x, y, groups)
        params = {k.removeprefix("clf__"): v for k, v in search.best_params_.items()}
        return SklearnTrainedModel(algorithm, params, search.best_estimator_)


__all__ = ["SEED", "SklearnModelTrainer", "SklearnTrainedModel"]
