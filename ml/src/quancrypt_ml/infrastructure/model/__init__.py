"""Model adapters (scikit-learn, XGBoost, SHAP, skl2onnx, onnxruntime).

onnxruntime 1.30 has a telemetry system that uploads over HTTPS to a Microsoft collector unless ORT_DISABLE_TELEMETRY
is set before onnxruntime is imported (measured in the image, D-347). Phase 1 is local (guardrails-security
section 1), so it is forced here, before any module of this package imports onnxruntime."""

import os

os.environ["ORT_DISABLE_TELEMETRY"] = "1"
