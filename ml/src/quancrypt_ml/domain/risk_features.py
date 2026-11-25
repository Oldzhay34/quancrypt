"""The features of Model A (P7.2, ml-pipeline section 3, D-327, D-328): one row of marts.mart_risk_features, the feature
groups of the preprocessing pipeline and the filling of missing values. Pure: no I/O, no model library.

Missing values are filled here, not in the pipeline: ONNX's Imputer runs on float only, and the double pipeline must
keep its values bit for bit (D-328). A flag (`*_known`) says when a value was missing; nothing is estimated (D-308c)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from quancrypt_ml.domain.labels import RISK_CLASSES

# log1p, then StandardScaler (skewed counts).
LOG_SCALED = ("project_finding_count", "key_size_bits")
# MinMaxScaler (bounded values).
MIN_MAX = ("confidence", "java_major")
# 0/1 flags, passed through.
FLAGS = ("in_test_code", "hndl_exposure", "is_outlier_project", "key_size_known", "java_major_known")
# One-hot (handle_unknown="ignore"); `library` has 7 values, so no target encoding (D-327g).
CATEGORICAL = (
    "algorithm_family", "usage_context", "location_kind", "priority", "quantum_status", "mode", "padding", "hash",
    "library", "spring_boot_minor",
)  # fmt: skip
NUMERIC = (*LOG_SCALED, *MIN_MAX, *FLAGS)
FEATURES = (*NUMERIC, *CATEGORICAL)
MISSING = "~MISSING"

# The class score of a prediction, as in the rule baseline (agent-service D-238c): the midpoint of the class range of
# D-128. A model's risk score is the expected value over its class probabilities.
CLASS_SCORES = {"CRITICAL": 0.90, "HIGH": 0.70, "MEDIUM": 0.475, "LOW": 0.175}


@dataclass(frozen=True)
class RiskRow:
    """A finding of the mart with its labels (gold: the user's, silver: the rule table; either may be missing)."""

    finding_id: str
    project_key: str
    algorithm_family: str
    quantum_status: str
    usage_context: str
    location_kind: str
    priority: str
    key_size_bits: int | None
    mode: str | None
    padding: str | None
    hash: str | None
    library: str | None
    confidence: float | None
    in_test_code: bool
    hndl_exposure: bool
    is_outlier_project: bool
    java_major: int | None
    spring_boot_version: str | None
    project_finding_count: int
    gold_label: str | None
    silver_label: str | None

    def label(self, source: str) -> str | None:
        value = self.gold_label if source == GOLD else self.silver_label
        return value if value in RISK_CLASSES else None


GOLD, SILVER = "GOLD", "SILVER"
LABEL_SOURCES = (GOLD, SILVER)


def _minor(version: str | None) -> str:
    """`3.3.1` -> `3.3`; anything else (UNKNOWN, empty) stays as it is."""
    if not version:
        return MISSING
    parts = version.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 and all(p.isdigit() for p in parts[:2]) else version


def features(row: RiskRow) -> dict[str, float | str]:
    """The model input of a row: numbers as floats (missing ones 0 with their flag), categories as text."""
    numbers: Mapping[str, float] = {
        "project_finding_count": float(row.project_finding_count),
        "key_size_bits": float(row.key_size_bits or 0),
        "confidence": float(row.confidence or 0.0),
        "java_major": float(row.java_major or 0),
        "in_test_code": float(row.in_test_code),
        "hndl_exposure": float(row.hndl_exposure),
        "is_outlier_project": float(row.is_outlier_project),
        "key_size_known": float(row.key_size_bits is not None),
        "java_major_known": float(row.java_major is not None),
    }
    texts: Mapping[str, str] = {
        "algorithm_family": row.algorithm_family,
        "usage_context": row.usage_context,
        "location_kind": row.location_kind,
        "priority": row.priority,
        "quantum_status": row.quantum_status,
        "mode": row.mode or MISSING,
        "padding": row.padding or MISSING,
        "hash": row.hash or MISSING,
        "library": row.library or MISSING,
        "spring_boot_minor": _minor(row.spring_boot_version),
    }
    return {**numbers, **texts}


def risk_score(probabilities: Mapping[str, float]) -> float:
    """Expected class score, rounded to the 4 decimals of ml_outputs.risk_prediction.risk_score."""
    return round(sum(CLASS_SCORES[c] * probabilities.get(c, 0.0) for c in RISK_CLASSES), 4)
