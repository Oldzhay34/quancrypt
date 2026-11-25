"""ScopeOnnxExporter with skl2onnx and onnxruntime (P7.3, ml-pipeline section 7, D-333d): the classifier head only
(StandardScaler + classifier), one input `embedding` of `dimensions` doubles, the class and the probabilities as
outputs. Parity: the class output equals the scikit-learn prediction and the probabilities differ by at most the
returned difference on the given vectors."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import onnxruntime as rt
from skl2onnx import convert_sklearn
from skl2onnx.common.data_types import DoubleTensorType

from quancrypt_ml.infrastructure.model.scope_trainer import SklearnScopeModel
from quancrypt_ml.port.outbound.scope_model import ScopeModel, ScopeParity, Vector

TARGET_OPSET = {"": 17, "ai.onnx.ml": 3}
INPUT = "embedding"


def _staged(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".tmp")


class SklearnScopeOnnxExporter:
    def __init__(self, dimensions: int) -> None:
        self._dimensions = dimensions

    def export(self, model: ScopeModel, vectors: Sequence[Vector], path: Path) -> ScopeParity:
        if not isinstance(model, SklearnScopeModel):
            raise TypeError("only scikit-learn scope heads are exported")
        estimator = model.estimator
        clf = estimator.named_steps["clf"]
        onx = convert_sklearn(
            estimator,
            initial_types=[(INPUT, DoubleTensorType([None, self._dimensions]))],
            target_opset=TARGET_OPSET,
            options={id(clf): {"zipmap": False}},
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        content = onx.SerializeToString()
        _staged(path).write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        if not vectors:
            return ScopeParity(0, True, 0.0, (), digest)
        x = np.asarray(vectors, dtype=np.float64)
        session = rt.InferenceSession(content, providers=["CPUExecutionProvider"])
        labels, probabilities = session.run(None, {INPUT: x})
        column = list(estimator.classes_).index(1)
        onnx_p = np.asarray(probabilities, dtype=np.float64)[:, column]
        reference = estimator.predict_proba(x)[:, column]
        same = bool(np.array_equal(np.asarray(labels), estimator.predict(x)))
        out = tuple(float(p) for p in onnx_p)
        return ScopeParity(len(vectors), same, float(np.abs(onnx_p - reference).max()), out, digest)

    def promote(self, path: Path) -> None:
        _staged(path).replace(path)

    def discard(self, path: Path) -> None:
        _staged(path).unlink(missing_ok=True)
