"""ExportScopeOnnx (P7.3, ml-pipeline section 7, D-333d): the classifier head as ONNX, with the mandatory parity check
and the same three-way decision under the chosen band. The model reaches its path only when the parity passes, so a
failed run leaves the previous model and threshold file as they were.

After the model reached its path the fixed set is written beside it (`<model>.parity.json`, P7.5, D-344a): at most
PARITY_ROWS of the parity vectors, chosen round-robin over the three-way decisions (`domain.parity`), the trained
head's out-of-scope probabilities and their decisions, so that agent-service checks its own ONNX runtime against the
same numbers; `covered` names every decision on the parity vectors. Vectors are embeddings, not request texts."""

from __future__ import annotations

import json

from quancrypt_ml.domain.parity import balanced_rows, parity_path
from quancrypt_ml.domain.scope_model import decide
from quancrypt_ml.port.inbound.scope_model import ExportScopeOnnxCommand, ScopeTrainingError
from quancrypt_ml.port.outbound.labeling import ReportWriter
from quancrypt_ml.port.outbound.scope_model import ScopeOnnxExporter, ScopeParity

MAX_PROBABILITY_DIFFERENCE = 1e-4
PARITY_ROWS = 20


class ExportScopeOnnxService:
    def __init__(self, exporter: ScopeOnnxExporter, reports: ReportWriter) -> None:
        self._exporter = exporter
        self._reports = reports

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
        band = command.band
        decisions = [decide(p, band) for p in reference]
        rows = [
            {
                "embedding": [float(v) for v in command.vectors[i]],
                "p_out": float(reference[i]),
                "decision": decisions[i],
            }
            for i in balanced_rows(decisions, PARITY_ROWS)
        ]
        fixture = {
            "model": command.path.name, "onnx_sha256": parity.sha256, "covered": sorted(set(decisions)),
            "band": {"low": band.low, "threshold": band.threshold, "high": band.high},
            "max_probability_difference": MAX_PROBABILITY_DIFFERENCE, "rows": rows,
        }  # fmt: skip
        self._reports.write(parity_path(command.path), json.dumps(fixture, indent=1, sort_keys=True) + "\n")
        return parity
