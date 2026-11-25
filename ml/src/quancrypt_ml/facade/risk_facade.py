"""The entry point of `ml train-risk` (P7.2): builds the command and hands back the result. It knows the inbound port
only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quancrypt_ml.facade.labeling_facade import MlCommandError
from quancrypt_ml.port.inbound.risk import RiskTrainingError, TrainRiskCommand, TrainRiskModelUseCase, TrainRiskResult


@dataclass(frozen=True)
class RiskPaths:
    reports_dir: Path
    model_cards_dir: Path
    models_dir: Path


class RiskFacade:
    def __init__(self, train: TrainRiskModelUseCase, paths: RiskPaths) -> None:
        self._train = train
        self._paths = paths

    def train(self, label_source: str, version: str, with_llm: bool, seed: int) -> TrainRiskResult:
        dry = label_source.upper() != "GOLD"
        command = TrainRiskCommand(
            label_source=label_source.upper(),
            version=version,
            report=self._paths.reports_dir / ("model_a_dry_run.md" if dry else "model_a.md"),
            model_card=self._paths.reports_dir / f"risk_model-{version}-dry_run.md"
            if dry
            else self._paths.model_cards_dir / f"risk_model-{version}.md",
            onnx=self._paths.models_dir
            / (f"risk_model-{version}-dry_run.onnx" if dry else f"risk_model-{version}.onnx"),
            artifacts_dir=self._paths.reports_dir / "model_a_artifacts",
            with_llm=with_llm,
            seed=seed,
        )
        try:
            return self._train.execute(command)
        except RiskTrainingError as error:
            raise MlCommandError(str(error)) from None
