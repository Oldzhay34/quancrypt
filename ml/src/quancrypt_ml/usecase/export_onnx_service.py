"""ExportOnnx (P7.2, ml-pipeline section 7): the trained pipeline as ONNX, with the mandatory parity check (classes
identical, probability difference <= 1e-4) on the given rows.

The model is staged beside its path and reaches it only when the parity passes (D-346c, as Model B, D-335a), so a
failed run leaves the previous model as it was. Then the fixed set is written beside the model (`<model>.parity.json`,
P7.5, D-344a): the model inputs of at most PARITY_ROWS rows, chosen round-robin over the classes the model gives
(`domain.parity`), and the trained model's probabilities, so that agent-service checks its own ONNX runtime against the
same numbers; `covered` names every class the model gives on the parity rows. No project key, finding id or path is
written."""

from __future__ import annotations

import json

from quancrypt_ml.domain.labels import RISK_CLASSES
from quancrypt_ml.domain.parity import balanced_rows, parity_path
from quancrypt_ml.domain.risk_features import FEATURES, features
from quancrypt_ml.port.inbound.risk import ExportOnnxCommand, RiskTrainingError
from quancrypt_ml.port.outbound.labeling import ReportWriter
from quancrypt_ml.port.outbound.risk import OnnxExporter, Parity

MAX_PROBABILITY_DIFFERENCE = 1e-4
PARITY_ROWS = 50


class ExportOnnxService:
    def __init__(self, exporter: OnnxExporter, reports: ReportWriter) -> None:
        self._exporter = exporter
        self._reports = reports

    def execute(self, command: ExportOnnxCommand) -> Parity:
        parity = self._exporter.export(command.model, command.rows, command.path)
        if not parity.classes_equal or parity.max_probability_difference > MAX_PROBABILITY_DIFFERENCE:
            self._exporter.discard(command.path)
            raise RiskTrainingError("the ONNX model does not answer like the trained model (parity failed)")
        self._exporter.promote(command.path)
        answers = [RISK_CLASSES[max(range(len(p)), key=p.__getitem__)] for p in parity.reference]
        rows = [
            {"inputs": features(command.rows[i]), "probabilities": list(parity.reference[i])}
            for i in balanced_rows(answers, PARITY_ROWS)
        ]
        fixture = {
            "model": command.path.name, "onnx_sha256": parity.sha256, "classes": list(RISK_CLASSES),
            "covered": sorted(set(answers)), "features": list(FEATURES),
            "max_probability_difference": MAX_PROBABILITY_DIFFERENCE, "rows": rows,
        }  # fmt: skip
        self._reports.write(parity_path(command.path), json.dumps(fixture, indent=1, sort_keys=True) + "\n")
        return parity
