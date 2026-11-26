"""Risk scoring (`score_findings`): the `RiskModel` port, Model A (`OnnxRiskModel`, P7.5) and the rule baseline
(`RuleBaselineRiskModel`, P4.3, D-238c, D-239). `model_config.yaml` `risk_model` picks one (D-343a); every score
carries the `model_id` of the model that made it.

Rule table (crypto-domain, "Risk sınıfı"):
1. P0 outside test code → CRITICAL
2. P1 on an inter-service path or a field-device link → HIGH
3. P1 not on a network path, or P2 → MEDIUM
4. P3 → LOW
5. In test code (`locationKind = TEST_CODE`) one class lower (at least LOW).

A finding is on a path when a topology link lists it in `findingIds`; a link is a device link when one of its ends is a
`DEVICE` node. The score is the middle of the class range of core-service's thresholds (D-128), so core derives the same

class back: CRITICAL 0.90, HIGH 0.70, MEDIUM 0.475, LOW 0.175. These four values are chosen constants (D-238c), not a
measurement. A baseline has no feature contributions, so `riskFactors` is empty (nothing invented).

**Model A (`OnnxRiskModel`).** The ONNX pipeline of ml (P7.2) takes the 19 inputs of `ml/domain/risk_features.py` by
name: 9 numbers (double) and 10 categories (string). Core-service's finding has no `mode`, `padding`, `hash` or
`library` and a user project has no outlier flag, so these are `~MISSING` and 0 (D-343b): a known difference from the
training data, stated in the model card. `quantum_status` and `hndl_exposure` follow the rule the warehouse uses (dbt
seed `quantum_status.csv`, `fact_crypto_finding`); `project_finding_count` is the number of findings scored together
(one scan); `java_major` and `spring_boot_minor` come from the project's runtime profile, a missing Spring Boot version
being `UNKNOWN` as in the warehouse. The score is the expected class score (D-328d) and the class the most likely one
(D-330a).

The reasons are an approximation, not SHAP (D-343c): each feature in turn is replaced by its "unknown" value (0 for a
number or flag, `~MISSING` for a category) and the drop of the predicted class's probability is its contribution; the
three strongest (by size, zero ones left out) become `riskFactors`. All variants of all findings go through one run.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from src.tools.base_tool import SchemaStore, ToolCode, ToolContext

RiskClass = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]

BASELINE_MODEL_ID = "rule_baseline_v1"
CLASS_SCORES: Mapping[RiskClass, float] = {"CRITICAL": 0.90, "HIGH": 0.70, "MEDIUM": 0.475, "LOW": 0.175}
_ORDER: tuple[RiskClass, ...] = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


@dataclass(frozen=True)
class RiskScore:
    finding_id: str
    risk_class: RiskClass
    risk_score: float
    rule: str
    factors: tuple[tuple[str, float], ...] = ()  # (feature, contribution), strongest first


class RiskModel(Protocol):
    @property
    def model_id(self) -> str: ...

    def score(
        self,
        findings: Sequence[Mapping[str, Any]],
        topology: Mapping[str, Any] | None,
        runtime: Mapping[str, Any] | None = None,
    ) -> list[RiskScore]: ...


class RuleBaselineRiskModel:
    @property
    def model_id(self) -> str:
        return BASELINE_MODEL_ID

    def score(
        self,
        findings: Sequence[Mapping[str, Any]],
        topology: Mapping[str, Any] | None,
        runtime: Mapping[str, Any] | None = None,
    ) -> list[RiskScore]:
        on_path, on_device = _paths(topology)
        scores: list[RiskScore] = []
        for finding in findings:
            finding_id = str(finding["id"])
            risk_class, rule = _base_class(str(finding["priority"]), finding_id in on_path, finding_id in on_device)
            if finding.get("locationKind") == "TEST_CODE":
                risk_class = _ORDER[max(0, _ORDER.index(risk_class) - 1)]
                rule += "_test_code"
            scores.append(RiskScore(finding_id, risk_class, CLASS_SCORES[risk_class], rule))
        return scores


def _base_class(priority: str, on_path: bool, on_device: bool) -> tuple[RiskClass, str]:
    if priority == "P0":
        return "CRITICAL", "p0"
    if priority == "P1":
        if on_device:
            return "HIGH", "p1_device_link"
        return ("HIGH", "p1_service_path") if on_path else ("MEDIUM", "p1_off_path")
    if priority == "P2":
        return "MEDIUM", "p2"
    return "LOW", "p3"


def _paths(topology: Mapping[str, Any] | None) -> tuple[frozenset[str], frozenset[str]]:
    """Finding ids on any link, and those on a link with a DEVICE end."""
    if not topology:
        return frozenset(), frozenset()
    devices = {node["name"] for node in topology.get("nodes", []) if node.get("nodeKind") == "DEVICE"}
    on_path: set[str] = set()
    on_device: set[str] = set()
    for link in topology.get("links", []):
        ids = {str(finding_id) for finding_id in link.get("findingIds", [])}
        on_path |= ids
        if link.get("source") in devices or link.get("target") in devices:
            on_device |= ids
    return frozenset(on_path), frozenset(on_device)


# ---------------------------------------------------------------- Model A

# The class order of the probability columns and the feature groups of ml (risk_features.py; the ONNX inputs by name).
MODEL_CLASSES: tuple[RiskClass, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
NUMERIC = (
    "project_finding_count", "key_size_bits", "confidence", "java_major", "in_test_code", "hndl_exposure",
    "is_outlier_project", "key_size_known", "java_major_known",
)  # fmt: skip
CATEGORICAL = (
    "algorithm_family", "usage_context", "location_kind", "priority", "quantum_status", "mode", "padding", "hash",
    "library", "spring_boot_minor",
)  # fmt: skip
FEATURES = (*NUMERIC, *CATEGORICAL)
MISSING = "~MISSING"
# crypto-domain section 1 (the warehouse's dbt seed quantum_status.csv; a test keeps them equal).
QUANTUM_STATUS: Mapping[str, str] = {
    **dict.fromkeys(("RSA", "ECDSA", "ECDH", "EDDSA", "DH", "DSA", "X25519"), "VULNERABLE"),
    **dict.fromkeys(("ML_KEM", "ML_DSA", "SLH_DSA", "HYBRID_X25519_MLKEM768"), "RESISTANT"),
    **dict.fromkeys(
        ("AES", "DES", "TRIPLE_DES", "CHACHA20", "SHA1", "SHA2", "SHA3", "MD5", "HMAC"), "SYMMETRIC_OR_HASH"
    ),
    "UNKNOWN": "UNKNOWN",
}
# fact_crypto_finding.hndl_exposure: harvest now, decrypt later.
HNDL_CONTEXTS = frozenset({"TLS_KEY_EXCHANGE", "KEY_AGREEMENT", "ENCRYPTION", "KEY_WRAP"})
FACTORS = 3
_JAVA_LEGACY = re.compile(r"^1\.([0-9]+)")
_JAVA = re.compile(r"^([0-9]+)")

Features = dict[str, float | str]


def java_major(version: str | None) -> int | None:
    """The warehouse's rule (dim_service): `1.8` is 8, `21.0.2` is 21, anything else unknown."""
    if not version:
        return None
    match = _JAVA_LEGACY.match(version) or _JAVA.match(version)
    return int(match.group(1)) if match else None


def spring_boot_minor(version: str | None) -> str:
    """ml's `_minor` of the warehouse value (a missing version is `UNKNOWN` there): `3.3.1` is `3.3`."""
    value = version or "UNKNOWN"
    parts = value.split(".")
    return ".".join(parts[:2]) if len(parts) >= 2 and all(p.isdigit() for p in parts[:2]) else value


def features(finding: Mapping[str, Any], runtime: Mapping[str, Any] | None, finding_count: int) -> Features:
    family = str(finding["algorithmFamily"])
    context = str(finding["usageContext"])
    key_size = finding.get("keySizeBits")
    java = java_major((runtime or {}).get("javaVersion"))
    quantum = QUANTUM_STATUS.get(family, "UNKNOWN")
    return {
        "project_finding_count": float(finding_count),
        "key_size_bits": float(key_size or 0),
        "confidence": float(finding.get("confidence") or 0.0),
        "java_major": float(java or 0),
        "in_test_code": float(finding["locationKind"] == "TEST_CODE"),
        "hndl_exposure": float(quantum == "VULNERABLE" and context in HNDL_CONTEXTS),
        "is_outlier_project": 0.0,  # a corpus statistic; a user project has none (D-343b)
        "key_size_known": float(key_size is not None),
        "java_major_known": float(java is not None),
        "algorithm_family": family,
        "usage_context": context,
        "location_kind": str(finding["locationKind"]),
        "priority": str(finding["priority"]),
        "quantum_status": quantum,
        "mode": MISSING,  # not in core-service's finding (D-343b)
        "padding": MISSING,
        "hash": MISSING,
        "library": MISSING,
        "spring_boot_minor": spring_boot_minor((runtime or {}).get("springBootVersion")),
    }


def occluded(row: Features) -> list[Features]:
    """One variant per feature, that feature set to its unknown value."""
    return [{**row, name: (MISSING if name in CATEGORICAL else 0.0)} for name in FEATURES]


class RiskSession(Protocol):
    """Class probabilities (MODEL_CLASSES order) of feature rows."""

    def probabilities(self, rows: Sequence[Features]) -> list[list[float]]: ...


def _no_onnx_telemetry() -> None:
    """onnxruntime 1.30 uploads telemetry over HTTPS to a Microsoft collector unless ORT_DISABLE_TELEMETRY is set before
    it is imported (measured in the image, D-347); Phase 1 is local (guardrails-security section 1)."""
    os.environ["ORT_DISABLE_TELEMETRY"] = "1"


class OnnxRiskSession:
    """Model A's pipeline with onnxruntime (CPU); one input per feature, shape [n, 1]. The session is opened once, from
    the bytes the caller hashed (D-346c)."""

    def __init__(self, content: bytes) -> None:
        import numpy as np

        _no_onnx_telemetry()
        import onnxruntime as rt

        self._np = np
        self._session = rt.InferenceSession(content, providers=["CPUExecutionProvider"])
        if sorted(i.name for i in self._session.get_inputs()) != sorted(FEATURES):
            raise ValueError("the risk model's inputs are not the features of Model A")

    def probabilities(self, rows: Sequence[Features]) -> list[list[float]]:
        np = self._np
        feeds = {name: np.asarray([[float(r[name])] for r in rows], dtype=np.float64) for name in NUMERIC}
        feeds.update({name: np.asarray([[str(r[name])] for r in rows]) for name in CATEGORICAL})
        outputs = self._session.run(None, feeds)
        return [[float(p) for p in row] for row in np.asarray(outputs[1], dtype=np.float64)]


class OnnxRiskModel:
    def __init__(self, session: RiskSession, model_id: str) -> None:
        self._session = session
        self._model_id = model_id

    @property
    def model_id(self) -> str:
        return self._model_id

    def score(
        self,
        findings: Sequence[Mapping[str, Any]],
        topology: Mapping[str, Any] | None,
        runtime: Mapping[str, Any] | None = None,
    ) -> list[RiskScore]:
        rows = [features(f, runtime, len(findings)) for f in findings]
        batch = [variant for row in rows for variant in (row, *occluded(row))]
        probabilities = self._session.probabilities(batch) if batch else []
        width = 1 + len(FEATURES)
        scores: list[RiskScore] = []
        for index, finding in enumerate(findings):
            block = probabilities[index * width : (index + 1) * width]
            own = block[0]
            if len(own) != len(MODEL_CLASSES) or not all(0.0 <= p <= 1.0 for p in own):
                raise ValueError("the risk model gave probabilities that are not four classes in 0..1")
            best = max(range(len(MODEL_CLASSES)), key=lambda c: (own[c], -c))
            contributions = [
                (name, own[best] - variant[best]) for name, variant in zip(FEATURES, block[1:], strict=True)
            ]
            strongest = sorted((c for c in contributions if c[1] != 0.0), key=lambda c: (-abs(c[1]), c[0]))[:FACTORS]
            expected = sum(CLASS_SCORES[c] * own[i] for i, c in enumerate(MODEL_CLASSES))
            scores.append(
                RiskScore(
                    str(finding["id"]),
                    MODEL_CLASSES[best],
                    round(expected, 4),
                    "onnx",
                    tuple((name, round(value, 6)) for name, value in strongest),
                )  # fmt: skip
            )
        return scores


class ScoreFindingsTool:
    """`score_findings`: findings as `list_findings` returns them, optionally the scan topology (`get_topology`)."""

    name = "score_findings"

    def __init__(self, model: RiskModel, schemas: SchemaStore) -> None:
        self._model = model
        self._input_schema = schemas.part(self.name, "input")
        self._output_schema = schemas.part(self.name, "output")

    @property
    def tool_code(self) -> ToolCode:
        return "RISK_MODEL"

    @property
    def input_schema(self) -> Mapping[str, Any]:
        return self._input_schema

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return self._output_schema

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Mapping[str, Any]:
        scores = self._model.score(arguments["findings"], arguments.get("topology"), arguments.get("runtime"))
        return {
            "model_id": self._model.model_id,
            "scores": [
                {
                    "findingId": score.finding_id,
                    "riskClass": score.risk_class,
                    "riskScore": score.risk_score,
                    "rule": score.rule,
                    "riskFactors": [{"featureName": name, "shapValue": value} for name, value in score.factors],
                }
                for score in scores
            ],
        }
