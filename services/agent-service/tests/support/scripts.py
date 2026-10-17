"""Loads `scripts/build_index.py` as a module (scripts is a folder of tools, not a package)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

SERVICE_ROOT = Path(__file__).resolve().parents[2]


def load_build_index() -> ModuleType:
    name = "build_index_script"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, SERVICE_ROOT / "scripts" / "build_index.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
