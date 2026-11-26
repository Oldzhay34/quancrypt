"""The real ONNX files of ml in the root models/ folder against ml's fixed parity sets (P7.5, D-344a). Outside
`make verify` (`models` marker, `make models-check`): the files are git-ignored build outputs of `ml train-risk` and
`ml train-scope`. A missing file fails, it never skips."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.guardrails.scope_classifier import OnnxScopeHead, ScopeBand
from src.tools.risk_model_tool import FEATURES, MODEL_CLASSES, OnnxRiskSession

pytestmark = pytest.mark.models

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT.parent.parent / "models"
CONFIG = (ROOT / "config" / "model_config.yaml").read_text(encoding="utf-8")


def _configured(key: str) -> str:
    line = next(line for line in CONFIG.splitlines() if line.strip().startswith(f"{key}:"))
    return line.split(":", 1)[1].strip()


def _fixture(model: Path) -> dict[str, Any]:
    path = model.with_name(model.name.removesuffix(".onnx") + ".parity.json")
    if not path.is_file():
        pytest.fail(f"{path.name} is missing: run ml train-risk / train-scope again (they write it beside the model)")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    assert data["onnx_sha256"] == hashlib.sha256(model.read_bytes()).hexdigest(), "the fixed set is of another model"
    return data


def test_model_a_answers_like_ml_on_its_fixed_set() -> None:
    model = MODELS / _configured("risk_model_file")
    fixture = _fixture(model)
    assert fixture["features"] == list(FEATURES) and fixture["classes"] == list(MODEL_CLASSES)
    session = OnnxRiskSession(model.read_bytes())
    rows = fixture["rows"]
    assert rows
    # The fixed set shows every class the model gives on ml's parity rows (D-346c), not only the first rows' class.
    assert {MODEL_CLASSES[max(range(4), key=lambda c: r["probabilities"][c])] for r in rows} == set(fixture["covered"])
    got = session.probabilities([row["inputs"] for row in rows])
    for row, probabilities in zip(rows, got, strict=True):
        expected = row["probabilities"]
        assert max(range(4), key=lambda c: probabilities[c]) == max(range(4), key=lambda c: expected[c])
        assert (
            max(abs(a - b) for a, b in zip(probabilities, expected, strict=True))
            <= fixture["max_probability_difference"]
        )


def test_model_b_answers_like_ml_on_its_fixed_set_and_matches_its_thresholds() -> None:
    model = MODELS / _configured("scope_model_file")
    thresholds = json.loads((MODELS / _configured("scope_thresholds_file")).read_text(encoding="utf-8"))
    fixture = _fixture(model)
    assert thresholds["onnx_sha256"] == fixture["onnx_sha256"]
    band = ScopeBand(thresholds["unsure_low"], thresholds["unsure_high"])
    assert (band.low, band.high) == (fixture["band"]["low"], fixture["band"]["high"])
    head = OnnxScopeHead(model.read_bytes(), thresholds["input_dimensions"])
    rows = fixture["rows"]
    assert {row["decision"] for row in rows} == set(fixture["covered"])
    got = head.p_out([row["embedding"] for row in rows])
    for row, p in zip(rows, got, strict=True):
        assert abs(p - row["p_out"]) <= fixture["max_probability_difference"]
        decision = "ALLOW" if p < band.low else "DENY" if p >= band.high else "UNSURE"
        assert decision == row["decision"]
