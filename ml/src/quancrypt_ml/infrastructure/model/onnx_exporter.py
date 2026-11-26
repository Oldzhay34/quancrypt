"""OnnxExporter with skl2onnx, onnxmltools and onnxruntime (P7.2, ml-pipeline section 7, D-328).

Two converters are registered: the `Log1p` step (Add + Log, in the input's float type) and the XGBoost wrapper
(onnxmltools' converter). Parity compares the probabilities and their arg-max with the scikit-learn pipeline on the
given rows."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as rt
from onnxmltools.convert.xgboost.operator_converters.XGBoost import convert_xgboost
from skl2onnx import convert_sklearn, update_registered_converter
from skl2onnx.common.data_types import DoubleTensorType, StringTensorType
from skl2onnx.common.shape_calculator import calculate_linear_classifier_output_shapes

from quancrypt_ml.domain.risk_features import CATEGORICAL, NUMERIC, RiskRow
from quancrypt_ml.infrastructure.model.pipeline import Log1p, PresentClassXGB, frame
from quancrypt_ml.infrastructure.model.trainer import SklearnTrainedModel
from quancrypt_ml.port.outbound.risk import Parity, TrainedModel

TARGET_OPSET = {"": 17, "ai.onnx.ml": 3}
_DOUBLE, _FLOAT = 11, 1  # onnx TensorProto element types


def _log1p_shape(operator: Any) -> None:
    operator.outputs[0].type = operator.inputs[0].type.__class__([None, operator.inputs[0].type.shape[1]])


def _log1p_converter(scope: Any, operator: Any, container: Any) -> None:
    one = scope.get_unique_variable_name("one")
    element = _DOUBLE if isinstance(operator.inputs[0].type, DoubleTensorType) else _FLOAT
    container.add_initializer(one, element, [], [1.0])
    added = scope.get_unique_variable_name("plus_one")
    container.add_node("Add", [operator.inputs[0].full_name, one], added, name=scope.get_unique_operator_name("Add"))
    container.add_node("Log", added, operator.outputs[0].full_name, name=scope.get_unique_operator_name("Log"))


update_registered_converter(Log1p, "QuancryptLog1p", _log1p_shape, _log1p_converter)
update_registered_converter(
    PresentClassXGB, "QuancryptPresentClassXGB", calculate_linear_classifier_output_shapes, convert_xgboost,
    options={"nocl": [True, False], "zipmap": [True, False, "columns"]},
)  # fmt: skip


def _staged(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".tmp")


def _feeds(rows: Sequence[RiskRow]) -> dict[str, Any]:
    data = frame(rows)
    feeds: dict[str, Any] = {c: data[[c]].to_numpy(dtype=np.float64) for c in NUMERIC}
    feeds.update({c: data[[c]].to_numpy(dtype=object).astype(str) for c in CATEGORICAL})
    return feeds


class SklearnOnnxExporter:
    def export(self, model: TrainedModel, rows: Sequence[RiskRow], path: Path) -> Parity:
        if not isinstance(model, SklearnTrainedModel):
            raise TypeError("only scikit-learn pipelines are exported")
        estimator = model.estimator
        initial = [(c, DoubleTensorType([None, 1])) for c in NUMERIC] + [
            (c, StringTensorType([None, 1])) for c in CATEGORICAL
        ]
        clf = estimator.named_steps["clf"]
        onx = convert_sklearn(
            estimator, initial_types=initial, target_opset=TARGET_OPSET, options={id(clf): {"zipmap": False}}
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        content = onx.SerializeToString()
        _staged(path).write_bytes(content)
        # Parity is measured on the staged bytes themselves; the file reaches `path` only through promote() (D-346c).
        session = rt.InferenceSession(content, providers=["CPUExecutionProvider"])
        outputs = session.run(None, _feeds(rows))
        onnx_probabilities = np.asarray(outputs[1], dtype=np.float64)
        reference = estimator.predict_proba(frame(rows))
        same = bool(np.array_equal(np.argmax(onnx_probabilities, axis=1), np.argmax(reference, axis=1)))
        difference = float(np.abs(onnx_probabilities - reference).max()) if len(rows) else 0.0
        rounded = tuple(tuple(float(p) for p in row) for row in np.asarray(reference, dtype=np.float64))
        return Parity(len(rows), same, difference, rounded, hashlib.sha256(content).hexdigest())

    def promote(self, path: Path) -> None:
        _staged(path).replace(path)

    def discard(self, path: Path) -> None:
        _staged(path).unlink(missing_ok=True)
