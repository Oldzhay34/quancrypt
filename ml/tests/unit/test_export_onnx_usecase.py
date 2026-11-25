"""ExportOnnx: the parity rule (classes identical, probability difference at most 1e-4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from quancrypt_ml.port.inbound.risk import ExportOnnxCommand, RiskTrainingError
from quancrypt_ml.port.outbound.risk import Parity
from quancrypt_ml.usecase.export_onnx_service import MAX_PROBABILITY_DIFFERENCE, ExportOnnxService
from tests.support.risk_fakes import FakeExporter, PriorityModel
from tests.support.risk_rows import synthetic_rows

ROWS = synthetic_rows(6, projects=2)


def _command(tmp: Path) -> ExportOnnxCommand:
    return ExportOnnxCommand(PriorityModel("XGBOOST", {}), ROWS, tmp / "m.onnx")


def test_a_difference_up_to_the_limit_passes_and_the_parity_is_returned(tmp_path: Path) -> None:
    parity = Parity(len(ROWS), True, MAX_PROBABILITY_DIFFERENCE)
    assert ExportOnnxService(FakeExporter(parity)).execute(_command(tmp_path)) == parity
    assert (tmp_path / "m.onnx").exists()


@pytest.mark.parametrize("parity", [Parity(6, True, 1.01e-4), Parity(6, False, 0.0)], ids=["difference", "classes"])
def test_a_larger_difference_or_other_classes_fail(tmp_path: Path, parity: Parity) -> None:
    with pytest.raises(RiskTrainingError, match="parity"):
        ExportOnnxService(FakeExporter(parity)).execute(_command(tmp_path))
