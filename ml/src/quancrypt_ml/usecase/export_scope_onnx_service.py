"""ExportScopeOnnx (P7.3, ml-pipeline section 7, D-333d): the classifier head as ONNX, with the mandatory parity check
and the same three-way decision under the chosen band. The model reaches its path only when the parity passes, so a
failed run leaves the previous model and threshold file as they were."""

from __future__ import annotations

from quancrypt_ml.domain.scope_model import decide
from quancrypt_ml.port.inbound.scope_model import ExportScopeOnnxCommand, ScopeTrainingError
from quancrypt_ml.port.outbound.scope_model import ScopeOnnxExporter, ScopeParity

MAX_PROBABILITY_DIFFERENCE = 1e-4


class ExportScopeOnnxService:
    def __init__(self, exporter: ScopeOnnxExporter) -> None:
        self._exporter = exporter

    def execute(self, command: ExportScopeOnnxCommand) -> ScopeParity:
        parity = self._exporter.export(command.model, command.vectors, command.path)
        reference = command.reference
        same_decisions = len(reference) == len(parity.onnx_p_out) and all(
            decide(a, command.band) == decide(b, command.band)
            for a, b in zip(reference, parity.onnx_p_out, strict=True)
        )
        if (
            not parity.classes_equal
            or parity.max_probability_difference > MAX_PROBABILITY_DIFFERENCE
            or not same_decisions
        ):
            self._exporter.discard(command.path)
            raise ScopeTrainingError("the ONNX model does not answer like the trained head (parity failed)")
        self._exporter.promote(command.path)
        return parity
