"""The preprocessing pipeline and the three classifiers of Model A (P7.2, ml-pipeline section 3, D-328).

ONNX parity shaped the pipeline (measured on synthetic data, D-328): numeric inputs are doubles, `log1p` is a small
transformer with its own ONNX converter (Add + Log), there is no imputer (missing values are filled in the domain with a
flag), one-hot output is dense (XGBoost reads a sparse zero as missing, ONNX as zero) and the features are cast to
float32 right before the classifier (scikit-learn trees cast to float32 themselves; ONNX must see the same values)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
import pandas as pd
from numpy.typing import NDArray
from skl2onnx.sklapi import CastTransformer
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler, OneHotEncoder, StandardScaler
from xgboost import XGBClassifier

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.risk_features import CATEGORICAL, FLAGS, LOG_SCALED, MIN_MAX, NUMERIC, RiskRow, features

LOGISTIC_REGRESSION, RANDOM_FOREST, XGBOOST = "LOGISTIC_REGRESSION", "RANDOM_FOREST", "XGBOOST"
ALGORITHMS = (LOGISTIC_REGRESSION, RANDOM_FOREST, XGBOOST)
SEED = 42

# The small fixed grids of the plan (D-327, logged to MLflow).
GRIDS: Mapping[str, Mapping[str, Sequence[object]]] = {
    LOGISTIC_REGRESSION: {"C": (0.1, 1.0, 10.0)},
    RANDOM_FOREST: {"n_estimators": (200,), "max_depth": (None, 6)},
    XGBOOST: {"max_depth": (3, 5), "n_estimators": (200,), "learning_rate": (0.1,)},
}


class Log1p(BaseEstimator, TransformerMixin):  # type: ignore[misc]
    """log(1 + x) for non-negative counts (the ONNX converter is registered in onnx_exporter.py)."""

    def fit(self, x: Any, y: Any = None) -> Log1p:
        return self

    def transform(self, x: Any) -> NDArray[np.float64]:
        return np.log1p(np.asarray(x, dtype=np.float64))

    def get_feature_names_out(self, input_features: Any = None) -> NDArray[np.str_]:
        return np.asarray(input_features if input_features is not None else [], dtype=str)


def frame(rows: Sequence[RiskRow]) -> pd.DataFrame:
    """The model input as a frame: numeric columns as float64, categorical columns as str (column order fixed)."""
    records = [features(r) for r in rows]
    data = pd.DataFrame.from_records(records, columns=[*NUMERIC, *CATEGORICAL])
    for column in NUMERIC:
        data[column] = data[column].astype("float64")
    for column in CATEGORICAL:
        data[column] = data[column].astype(str)
    return data


def preprocessor() -> ColumnTransformer:
    return ColumnTransformer(
        [
            ("log", Pipeline([("log1p", Log1p()), ("scale", StandardScaler())]), list(LOG_SCALED)),
            ("minmax", MinMaxScaler(), list(MIN_MAX)),
            ("flags", "passthrough", list(FLAGS)),
            ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False), list(CATEGORICAL)),
        ],
        verbose_feature_names_out=True,
    )


class PresentClassXGB(XGBClassifier):
    """XGBoost with scikit-learn's class handling: it learns the classes present in `y` (a fold may miss a rare class)
    and weighs them like `class_weight="balanced"`. `classes_` holds the original codes and the probability columns
    follow it, as for the other two classifiers."""

    def fit(self, x: Any, y: Any, sample_weight: Any = None, **kwargs: Any) -> PresentClassXGB:
        codes = np.asarray(y, dtype=np.int64)
        present = np.unique(codes)
        weights = balanced_weights(codes) if sample_weight is None else sample_weight
        self.__dict__.pop("present_classes_", None)  # XGBoost reads `classes_` (0..m-1) while it fits
        super().fit(x, np.searchsorted(present, codes), sample_weight=weights, **kwargs)
        self.present_classes_ = present
        return self

    @property
    def classes_(self) -> NDArray[np.int64]:
        """The original class codes after fitting; XGBoost's own 0..m-1 while it fits."""
        present = self.__dict__.get("present_classes_")
        return np.arange(self.n_classes_) if present is None else np.asarray(present)

    def predict(self, x: Any, **kwargs: Any) -> NDArray[np.int64]:
        return np.asarray(self.classes_)[np.asarray(super().predict(x, **kwargs), dtype=np.int64)]


def classifier(algorithm: str, params: Mapping[str, Any]) -> Any:
    if algorithm == LOGISTIC_REGRESSION:
        return LogisticRegression(class_weight="balanced", max_iter=5000, random_state=SEED, **params)
    if algorithm == RANDOM_FOREST:
        return RandomForestClassifier(class_weight="balanced", random_state=SEED, n_jobs=1, **params)
    if algorithm == XGBOOST:
        # Class weights are sample weights here (`balanced_weights`); one thread keeps the result reproducible.
        return PresentClassXGB(random_state=SEED, n_jobs=1, tree_method="hist", eval_metric="mlogloss", **params)
    raise ValueError(f"unknown algorithm {algorithm}")


def pipeline(algorithm: str, params: Mapping[str, Any]) -> Pipeline:
    return Pipeline(
        [("pre", preprocessor()), ("cast", CastTransformer(dtype=np.float32)), ("clf", classifier(algorithm, params))]
    )


def encode(labels: Sequence[str]) -> NDArray[np.int64]:
    """Risk classes as integers in RISK_CLASSES order (XGBoost wants 0..k-1; the same encoding for every algorithm keeps
    the probability columns in one order)."""
    return np.asarray([RISK_CLASSES.index(label) for label in labels], dtype=np.int64)


def balanced_weights(encoded: NDArray[np.int64]) -> NDArray[np.float64]:
    """n / (k * count(class)) per sample, scikit-learn's `class_weight="balanced"` rule, for XGBoost."""
    counts = np.bincount(encoded, minlength=len(RISK_CLASSES)).astype(np.float64)
    present = np.count_nonzero(counts)
    weights = np.where(counts > 0, len(encoded) / (present * np.maximum(counts, 1.0)), 0.0)
    return weights[encoded]
