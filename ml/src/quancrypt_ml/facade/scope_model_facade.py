"""The entry point of `ml train-scope` (P7.3): builds the command from the fixed file layout and hands back the result.
It knows the inbound port only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quancrypt_ml.facade.labeling_facade import MlCommandError
from quancrypt_ml.port.inbound.scope_model import (
    ScopeTrainingError,
    TrainScopeClassifierUseCase,
    TrainScopeCommand,
    TrainScopeResult,
)


@dataclass(frozen=True)
class ScopeModelPaths:
    scope_dir: Path  # ml/data/scope: train.jsonl, val.jsonl, test.jsonl
    reports_dir: Path
    model_cards_dir: Path
    models_dir: Path


class ScopeModelFacade:
    def __init__(self, train: TrainScopeClassifierUseCase, paths: ScopeModelPaths) -> None:
        self._train = train
        self._paths = paths

    def train(self, version: str, seed: int) -> TrainScopeResult:
        p = self._paths
        name = f"scope_classifier-{version}"
        command = TrainScopeCommand(
            version=version,
            train=p.scope_dir / "train.jsonl",
            val=p.scope_dir / "val.jsonl",
            test=p.scope_dir / "test.jsonl",
            report=p.reports_dir / "model_b.md",
            model_card=p.model_cards_dir / f"{name}.md",
            onnx=p.models_dir / f"{name}.onnx",
            thresholds=p.models_dir / f"{name}.thresholds.json",
            artifacts_dir=p.reports_dir / "model_b_artifacts",
            seed=seed,
        )
        try:
            return self._train.execute(command)
        except ScopeTrainingError as error:
            raise MlCommandError(str(error)) from None
