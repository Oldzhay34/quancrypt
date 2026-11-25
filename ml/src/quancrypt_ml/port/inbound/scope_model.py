"""Inbound port of Model B (P7.3): embed the scope data set, train the head, choose the threshold and the UNSURE band
on the validation set, evaluate once on the test set, export ONNX and report."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from quancrypt_ml.domain.scope_model import Band
from quancrypt_ml.port.outbound.scope_model import ScopeModel, ScopeParity, Vector


class ScopeTrainingError(Exception):
    """The training cannot run (a missing split, an unreachable embedding model, a failed parity). The message names
    no request text."""


@dataclass(frozen=True)
class TrainScopeCommand:
    version: str
    train: Path
    val: Path
    test: Path
    report: Path
    model_card: Path
    onnx: Path
    thresholds: Path
    artifacts_dir: Path
    seed: int


@dataclass(frozen=True)
class TrainScopeResult:
    selected: str
    embedding_model: str
    embedding_digest: str
    cv_auc: Mapping[str, float]  # mean inner-CV ROC AUC per algorithm
    band: Band
    test_recall: float
    test_false_reject_rate: float
    test_unsure_rate: float
    h4_met: bool
    onnx_parity: bool
    stored: bool


@dataclass(frozen=True)
class ExportScopeOnnxCommand:
    model: ScopeModel
    vectors: Sequence[Vector]  # the vectors the parity is checked on (the test set)
    reference: Sequence[float]  # the model's out-of-scope probabilities of those vectors (computed once, by the caller)
    band: Band
    path: Path


class ExportScopeOnnxUseCase(Protocol):
    """The head as ONNX (ml-pipeline section 7) with its parity: the classes identical, the probability difference
    <= 1e-4 and the same ALLOW / UNSURE / DENY decision for every vector under the chosen band (D-333d). A failed
    parity is a ScopeTrainingError."""

    def execute(self, command: ExportScopeOnnxCommand) -> ScopeParity: ...


class TrainScopeClassifierUseCase(Protocol):
    def execute(self, command: TrainScopeCommand) -> TrainScopeResult: ...
