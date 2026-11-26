"""ExportOnnx: the parity rule (classes identical, probability difference at most 1e-4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.risk_features import FEATURES, features
from quancrypt_ml.port.inbound.risk import ExportOnnxCommand, RiskTrainingError
from quancrypt_ml.port.outbound.risk import Parity
from quancrypt_ml.usecase.export_onnx_service import MAX_PROBABILITY_DIFFERENCE, PARITY_ROWS, ExportOnnxService
from tests.support.fakes import FakeReports
from tests.support.risk_fakes import FakeExporter, PriorityModel
from tests.support.risk_rows import synthetic_rows

ROWS = synthetic_rows(6, projects=2)


def _command(tmp: Path) -> ExportOnnxCommand:
    return ExportOnnxCommand(PriorityModel("XGBOOST", {}), ROWS, tmp / "m.onnx")


def test_a_difference_up_to_the_limit_passes_and_the_parity_is_returned(tmp_path: Path) -> None:
    parity = Parity(len(ROWS), True, MAX_PROBABILITY_DIFFERENCE)
    exporter = FakeExporter(parity)
    assert ExportOnnxService(exporter, FakeReports()).execute(_command(tmp_path)) == parity
    assert (tmp_path / "m.onnx").exists() and exporter.promoted == [tmp_path / "m.onnx"]


@pytest.mark.parametrize("parity", [Parity(6, True, 1.01e-4), Parity(6, False, 0.0)], ids=["difference", "classes"])
def test_a_larger_difference_or_other_classes_fail_and_the_previous_model_stays(tmp_path: Path, parity: Parity) -> None:
    (tmp_path / "m.onnx").write_bytes(b"previous")
    exporter = FakeExporter(parity)
    with pytest.raises(RiskTrainingError, match="parity"):
        ExportOnnxService(exporter, FakeReports()).execute(_command(tmp_path))
    assert exporter.promoted == [] and (tmp_path / "m.onnx").read_bytes() == b"previous"


def test_a_passed_parity_writes_the_fixed_set_beside_the_model_and_a_failed_one_does_not(tmp_path: Path) -> None:
    reference = tuple((0.7, 0.1, 0.1, 0.1) for _ in ROWS)
    reports = FakeReports()
    ExportOnnxService(FakeExporter(Parity(len(ROWS), True, 0.0, reference, "a" * 64)), reports).execute(
        _command(tmp_path)
    )
    fixture = json.loads(reports.texts[tmp_path / "m.parity.json"])
    assert fixture["classes"] == list(RISK_CLASSES) and fixture["features"] == list(FEATURES)
    assert fixture["onnx_sha256"] == "a" * 64 and fixture["model"] == "m.onnx"
    assert [r["inputs"] for r in fixture["rows"]] == [features(row) for row in ROWS]
    assert fixture["covered"] == ["CRITICAL"]
    assert fixture["rows"][0]["probabilities"] == [0.7, 0.1, 0.1, 0.1]
    assert "project_key" not in json.dumps(fixture) and ROWS[0].project_key not in json.dumps(fixture)
    failing = FakeReports()
    with pytest.raises(RiskTrainingError):
        ExportOnnxService(FakeExporter(Parity(6, False, 0.0)), failing).execute(_command(tmp_path))
    assert failing.texts == {}


def test_the_fixed_set_keeps_every_class_the_model_gives_even_past_the_first_rows(tmp_path: Path) -> None:
    rows = synthetic_rows(80, projects=4)
    critical, low = (0.7, 0.1, 0.1, 0.1), (0.1, 0.1, 0.1, 0.7)
    reference = tuple(low if i == 79 else critical for i in range(len(rows)))  # the only LOW row is the last one
    reports = FakeReports()
    command = ExportOnnxCommand(PriorityModel("XGBOOST", {}), rows, tmp_path / "m.onnx")
    ExportOnnxService(FakeExporter(Parity(len(rows), True, 0.0, reference, "a" * 64)), reports).execute(command)
    fixture = json.loads(reports.texts[tmp_path / "m.parity.json"])
    assert len(fixture["rows"]) == PARITY_ROWS and fixture["covered"] == ["CRITICAL", "LOW"]
    assert [0.1, 0.1, 0.1, 0.7] in [r["probabilities"] for r in fixture["rows"]]
