"""ProjectSplitter, Explainer and Charts with scikit-learn, SHAP and matplotlib (P7.2, D-327f, ml-pipeline section 4).

Charts are drawn on `matplotlib.figure.Figure` objects (no pyplot, no global state), like the data-platform profiling.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
import shap
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from numpy.typing import NDArray
from sklearn.calibration import calibration_curve
from sklearn.model_selection import StratifiedGroupKFold

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.risk_features import SILVER, RiskRow
from quancrypt_ml.domain.split import ProjectSplit
from quancrypt_ml.infrastructure.model.pipeline import LOGISTIC_REGRESSION, frame
from quancrypt_ml.infrastructure.model.trainer import SklearnTrainedModel
from quancrypt_ml.port.outbound.risk import Attribution, TrainedModel

TEST_FOLDS = 5
_UNSAFE = re.compile(r"[^A-Za-z0-9_.:~-]")
NO_LABEL = "~NONE"


class StratifiedProjectSplitter:
    """One fold of StratifiedGroupKFold(5, shuffle, seed) is the fixed test set. Stratified by the silver label, so the
    split does not depend on the gold labels and stays the same while they are being written (D-327f)."""

    def split(self, rows: Sequence[RiskRow], seed: int) -> ProjectSplit:
        groups = np.asarray([r.project_key for r in rows], dtype=str)
        strata = np.asarray([r.label(SILVER) or NO_LABEL for r in rows], dtype=str)
        folds = StratifiedGroupKFold(
            n_splits=min(TEST_FOLDS, len(set(groups.tolist()))), shuffle=True, random_state=seed
        )
        _, test = next(folds.split(np.zeros(len(rows)), strata, groups))
        test_projects = frozenset(groups[test].tolist())
        return ProjectSplit(frozenset(groups.tolist()) - test_projects, test_projects)


def _save(figure: Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    FigureCanvasAgg(figure)
    figure.savefig(path, dpi=110, bbox_inches="tight")


def _model(model: TrainedModel) -> SklearnTrainedModel:
    if not isinstance(model, SklearnTrainedModel):
        raise TypeError("the explainer reads scikit-learn models only")
    return model


class ShapExplainer:
    """SHAP values of the classifier on the preprocessed features: TreeExplainer for the forests, LinearExplainer (the
    training data as background) for logistic regression. A row's attribution is the one of its predicted class."""

    def _values(self, model: SklearnTrainedModel, rows: Sequence[RiskRow]) -> tuple[NDArray[np.float64], list[str]]:
        steps = model.estimator
        transformed = np.asarray(steps[:-1].transform(frame(rows)), dtype=np.float64)
        # Feature names carry category values; anything outside the ml_outputs pattern becomes `_`.
        names = [_UNSAFE.sub("_", str(n))[:128] for n in steps.named_steps["pre"].get_feature_names_out()]
        classifier = steps.named_steps["clf"]
        if model.algorithm == LOGISTIC_REGRESSION:
            # Every row is background (no random subsample): the attributions stay reproducible (ml-pipeline §8).
            masker = shap.maskers.Independent(transformed, max_samples=transformed.shape[0])
            explainer: Any = shap.LinearExplainer(classifier, masker)
        else:
            explainer = shap.TreeExplainer(classifier)
        raw = explainer.shap_values(transformed)
        values = np.stack(raw, axis=-1) if isinstance(raw, list) else np.asarray(raw)
        if values.ndim == 2:  # a binary or single-output explanation
            values = values[:, :, np.newaxis]
        return values, names

    def top_features(self, model: TrainedModel, rows: Sequence[RiskRow], k: int) -> list[list[Attribution]]:
        sk = _model(model)
        values, names = self._values(sk, rows)
        predicted = np.argmax(sk.estimator.predict_proba(frame(rows)), axis=1)
        result = []
        for i, column in enumerate(predicted):
            contribution = values[i, :, min(int(column), values.shape[2] - 1)]
            order = np.argsort(-np.abs(contribution), kind="stable")[:k]
            result.append([Attribution(names[j], float(contribution[j])) for j in order])
        return result

    def global_importance(self, model: TrainedModel, rows: Sequence[RiskRow], k: int) -> list[Attribution]:
        """Mean |SHAP| over the rows and all classes, highest first; the chart shows these same numbers."""
        values, names = self._values(_model(model), rows)
        importance = np.abs(values).mean(axis=(0, 2))
        order = np.argsort(-importance, kind="stable")[:k]
        return [Attribution(names[j], float(importance[j])) for j in order]

    def summary_chart(self, model: TrainedModel, rows: Sequence[RiskRow], path: Path) -> None:
        top = self.global_importance(model, rows, 15)[::-1]
        figure = Figure(figsize=(7, 5))
        axes = figure.add_subplot()
        axes.barh([a.feature for a in top], [a.value for a in top])
        axes.set_xlabel("mean |SHAP| (all classes)")
        axes.set_title("Model A: global feature importance")
        _save(figure, path)


class MatplotlibCharts:
    def calibration(self, truth: Sequence[str], probabilities: Sequence[Mapping[str, float]], path: Path) -> None:
        """One-vs-rest reliability curve per class present in the truth (5 uniform bins; few test findings)."""
        figure = Figure(figsize=(6, 5))
        axes = figure.add_subplot()
        axes.plot([0, 1], [0, 1], linestyle="--", color="grey", label="perfect")
        for label in RISK_CLASSES:
            positive = np.asarray([t == label for t in truth], dtype=int)
            if positive.sum() == 0 or positive.sum() == len(positive):
                continue
            scores = np.asarray([p[label] for p in probabilities], dtype=np.float64)
            observed, mean_predicted = calibration_curve(positive, scores, n_bins=5, strategy="uniform")
            axes.plot(mean_predicted, observed, marker="o", label=label)
        axes.set_xlabel("predicted probability")
        axes.set_ylabel("observed share")
        axes.set_title("Model A: calibration (test projects)")
        axes.legend()
        _save(figure, path)

    def score_histogram(
        self, labels: Sequence[str], p_out: Sequence[float], bounds: Mapping[str, float], path: Path
    ) -> None:
        """Model B (P7.3): the out-of-scope probability per true class, with the threshold and the UNSURE band."""
        figure = Figure(figsize=(7, 4))
        axes = figure.add_subplot()
        bins = [i / 20 for i in range(21)]
        for label in sorted(set(labels)):
            values = [p for p, t in zip(p_out, labels, strict=True) if t == label]
            axes.hist(values, bins=bins, alpha=0.6, label=label)
        for name, value in sorted(bounds.items()):
            axes.axvline(value, linestyle="--", linewidth=1, color="black")
            axes.annotate(name, (value, axes.get_ylim()[1]), rotation=90, va="top", ha="right", fontsize=7)
        axes.set_xlabel("out-of-scope probability")
        axes.set_ylabel("requests")
        axes.set_title("Model B: scores (test set)")
        axes.legend()
        _save(figure, path)
