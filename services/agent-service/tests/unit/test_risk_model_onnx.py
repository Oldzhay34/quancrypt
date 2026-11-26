"""Model A behind the RiskModel port (P7.5, D-343b, D-343c, D-344e): the 19 features, the warehouse rules they mirror,
the score, the class and the occlusion reasons. The ONNX session is a test double here; the real model and ml's fixed
parity set run in tests/integration/test_onnx_models.py."""

from __future__ import annotations

import csv
import os
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from src.tools.risk_model_tool import (
    CATEGORICAL,
    FEATURES,
    HNDL_CONTEXTS,
    MISSING,
    NUMERIC,
    QUANTUM_STATUS,
    Features,
    OnnxRiskModel,
    features,
    java_major,
    occluded,
    spring_boot_minor,
)

REPO = Path(__file__).resolve().parents[4]
FINDING: Mapping[str, Any] = {
    "id": "00000000-0000-0000-0000-00000000f001", "priority": "P1", "locationKind": "CODE",
    "algorithmFamily": "RSA", "usageContext": "TLS_KEY_EXCHANGE", "keySizeBits": 2048, "confidence": 0.8,
}  # fmt: skip


def test_the_features_are_ml_s_in_the_same_groups() -> None:
    assert (*NUMERIC, *CATEGORICAL) == FEATURES and len(FEATURES) == 19
    row = features(FINDING, {"javaVersion": "21.0.2", "springBootVersion": "3.3.1"}, 7)
    assert set(row) == set(FEATURES)
    assert row == {
        "project_finding_count": 7.0, "key_size_bits": 2048.0, "confidence": 0.8, "java_major": 21.0,
        "in_test_code": 0.0, "hndl_exposure": 1.0, "is_outlier_project": 0.0, "key_size_known": 1.0,
        "java_major_known": 1.0, "algorithm_family": "RSA", "usage_context": "TLS_KEY_EXCHANGE",
        "location_kind": "CODE",
        "priority": "P1", "quantum_status": "VULNERABLE", "mode": MISSING, "padding": MISSING, "hash": MISSING,
        "library": MISSING, "spring_boot_minor": "3.3",
    }  # fmt: skip


def test_missing_values_are_zero_with_their_flag_and_test_code_is_flagged() -> None:
    finding = {
        **FINDING,
        "keySizeBits": None,
        "confidence": 0.0,
        "locationKind": "TEST_CODE",
        "usageContext": "SIGNATURE",
    }
    row = features(finding, None, 1)
    assert (row["key_size_bits"], row["key_size_known"], row["java_major"], row["java_major_known"]) == (
        0.0,
        0.0,
        0.0,
        0.0,
    )
    assert (row["in_test_code"], row["hndl_exposure"], row["spring_boot_minor"]) == (1.0, 0.0, "UNKNOWN")


@pytest.mark.parametrize(
    ("version", "major"), [("1.8", 8), ("1.8.0_402", 8), ("21", 21), ("21.0.2", 21), ("UNKNOWN", None), (None, None)]
)
def test_the_java_major_follows_the_warehouse_rule(version: str | None, major: int | None) -> None:
    assert java_major(version) == major


@pytest.mark.parametrize(
    ("version", "minor"), [("3.3.1", "3.3"), ("3.3", "3.3"), ("UNKNOWN", "UNKNOWN"), (None, "UNKNOWN")]
)
def test_the_spring_boot_minor_follows_ml(version: str | None, minor: str) -> None:
    assert spring_boot_minor(version) == minor


def test_the_quantum_status_table_is_the_warehouse_seed() -> None:
    seed = REPO / "data-platform" / "dbt" / "quancrypt_dw" / "seeds" / "quantum_status.csv"
    with seed.open(encoding="utf-8") as handle:
        rows = {row["algorithm_family"]: row["quantum_status"] for row in csv.DictReader(handle)}
    assert dict(QUANTUM_STATUS) == rows


def test_the_hndl_contexts_are_the_warehouse_rule() -> None:
    sql = (REPO / "data-platform" / "dbt" / "quancrypt_dw" / "models" / "core" / "fact_crypto_finding.sql").read_text(
        encoding="utf-8"
    )
    rule = re.search(r"usage_context in \(([^)]*)\)\) as hndl_exposure", sql)
    assert rule is not None, "the HNDL rule moved in fact_crypto_finding.sql"
    assert set(re.findall(r"'([A-Z_]+)'", rule.group(1))) == HNDL_CONTEXTS


def test_occlusion_sets_one_feature_at_a_time_to_its_unknown_value() -> None:
    row = features(FINDING, None, 3)
    variants = occluded(row)
    assert len(variants) == len(FEATURES)
    for name, variant in zip(FEATURES, variants, strict=True):
        changed = {k for k in FEATURES if variant[k] != row[k]}
        assert changed <= {name}
        assert variant[name] == (MISSING if name in CATEGORICAL else 0.0)


class Scripted:
    """CRITICAL unless priority is unknown (then LOW); key size unknown lowers CRITICAL a little."""

    def __init__(self) -> None:
        self.batches: list[int] = []

    def probabilities(self, rows: Sequence[Features]) -> list[list[float]]:
        self.batches.append(len(rows))
        out = []
        for r in rows:
            if r["priority"] == MISSING:
                out.append([0.1, 0.1, 0.1, 0.7])
            elif r["key_size_bits"] == 0.0:
                out.append([0.6, 0.2, 0.1, 0.1])
            else:
                out.append([0.8, 0.1, 0.05, 0.05])
        return out


def test_the_score_class_and_three_reasons_come_from_one_run() -> None:
    session = Scripted()
    model = OnnxRiskModel(session, "risk_model_v1_dry_run")
    [score] = model.score([FINDING], None, {"javaVersion": "21", "springBootVersion": None})
    assert session.batches == [1 + len(FEATURES)]
    assert (score.risk_class, score.rule, model.model_id) == ("CRITICAL", "onnx", "risk_model_v1_dry_run")
    assert score.risk_score == round(0.8 * 0.90 + 0.1 * 0.70 + 0.05 * 0.475 + 0.05 * 0.175, 4)
    # priority unknown: 0.8 -> 0.1; key size unknown: 0.8 -> 0.6; every other feature changes nothing (left out)
    assert score.factors == (("priority", 0.7), ("key_size_bits", 0.2))


def test_the_tool_writes_the_reasons_as_risk_factors() -> None:
    from src.tools.base_tool import SchemaStore, ToolContext
    from src.tools.risk_model_tool import ScoreFindingsTool

    tool = ScoreFindingsTool(OnnxRiskModel(Scripted(), "risk_model_v1_dry_run"), SchemaStore(REPO / "contracts"))
    output = tool.invoke({"findings": [FINDING], "topology": None, "runtime": None}, ToolContext(trace_id="0" * 32))
    assert output["model_id"] == "risk_model_v1_dry_run"
    assert output["scores"][0]["riskFactors"] == [
        {"featureName": "priority", "shapValue": 0.7}, {"featureName": "key_size_bits", "shapValue": 0.2},
    ]  # fmt: skip


class Broken:
    def probabilities(self, rows: Sequence[Features]) -> list[list[float]]:
        return [[0.5, 0.5, float("nan"), 0.0] for _ in rows]


def test_probabilities_that_are_not_four_classes_in_zero_to_one_are_an_error() -> None:
    with pytest.raises(ValueError, match="four classes"):
        OnnxRiskModel(Broken(), "risk_model_v1").score([FINDING], None)


def test_no_findings_need_no_run() -> None:
    session = Scripted()
    assert OnnxRiskModel(session, "risk_model_v1").score([], None) == [] and session.batches == []


def test_onnxruntime_telemetry_is_switched_off_before_the_runtime_is_imported(monkeypatch: pytest.MonkeyPatch) -> None:
    # onnxruntime 1.30 uploads telemetry unless ORT_DISABLE_TELEMETRY is set before its import (D-347).
    from src.guardrails import scope_classifier
    from src.tools import risk_model_tool

    for module in (risk_model_tool, scope_classifier):
        monkeypatch.delenv("ORT_DISABLE_TELEMETRY", raising=False)
        module._no_onnx_telemetry()
        assert os.environ["ORT_DISABLE_TELEMETRY"] == "1"
