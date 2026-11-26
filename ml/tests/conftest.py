"""Test-wide settings: onnxruntime telemetry off before any test module imports onnxruntime (D-347)."""

import os

os.environ["ORT_DISABLE_TELEMETRY"] = "1"
