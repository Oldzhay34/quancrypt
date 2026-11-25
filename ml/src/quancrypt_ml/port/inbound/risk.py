"""Inbound port of Model A (P7.2): train, compare with the baselines, explain, export and report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from quancrypt_ml.domain.risk_features import RiskRow
from quancrypt_ml.port.outbound.risk import Parity, TrainedModel


class RiskTrainingError(Exception):
    """The training cannot run (no labels, a leaking split, a failed parity). The message names no data value."""


@dataclass(frozen=True)
class TrainRiskCommand:
    label_source: str  # GOLD or SILVER (a dry run, D-327a)
    version: str
    report: Path
    model_card: Path
    onnx: Path
    artifacts_dir: Path
    with_llm: bool
    seed: int


@dataclass(frozen=True)
class TrainRiskResult:
    label_source: str
    train_rows: int
    test_rows: int
    test_projects: int
    selected: str
    cv_macro_f1: Mapping[str, float]
    test_macro_f1: float
    rule_macro_f1: float
    llm_macro_f1: float | None
    h3_met: bool | None  # None on a dry run
    onnx_parity: bool
    stored: bool
    erased_skipped: int = 0  # predictions not written: their finding was erased (KVKK) while the model trained


@dataclass(frozen=True)
class ExportOnnxCommand:
    model: TrainedModel
    rows: Sequence[RiskRow]  # the rows the parity is checked on
    path: Path


class ExportOnnxUseCase(Protocol):
    """ExportOnnx (ml-pipeline section 7): writes the ONNX file and checks parity (classes identical, probability
    difference <= 1e-4); a failed parity is a RiskTrainingError."""

    def execute(self, command: ExportOnnxCommand) -> Parity: ...


class TrainRiskModelUseCase(Protocol):
    def execute(self, command: TrainRiskCommand) -> TrainRiskResult: ...
