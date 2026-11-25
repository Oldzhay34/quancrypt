"""ExportOnnx (P7.2, ml-pipeline section 7): the trained pipeline as ONNX, with the mandatory parity check (classes
identical, probability difference <= 1e-4) on the given rows."""

from __future__ import annotations

from quancrypt_ml.port.inbound.risk import ExportOnnxCommand, RiskTrainingError
from quancrypt_ml.port.outbound.risk import OnnxExporter, Parity

MAX_PROBABILITY_DIFFERENCE = 1e-4


class ExportOnnxService:
    def __init__(self, exporter: OnnxExporter) -> None:
        self._exporter = exporter

    def execute(self, command: ExportOnnxCommand) -> Parity:
        parity = self._exporter.export(command.model, command.rows, command.path)
        if not parity.classes_equal or parity.max_probability_difference > MAX_PROBABILITY_DIFFERENCE:
            raise RiskTrainingError("the ONNX model does not answer like the trained model (parity failed)")
        return parity
