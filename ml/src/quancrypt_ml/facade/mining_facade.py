"""The entry point of `ml mine` (P7.4): builds the command from the fixed file layout and hands back the result. It
knows the inbound port only."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from quancrypt_ml.facade.labeling_facade import MlCommandError
from quancrypt_ml.port.inbound.mining import MineCorpusCommand, MineCorpusResult, MineCorpusUseCase, MiningError


@dataclass(frozen=True)
class MiningPaths:
    reports_dir: Path


class MiningFacade:
    def __init__(self, mine: MineCorpusUseCase, paths: MiningPaths) -> None:
        self._mine = mine
        self._paths = paths

    def mine(
        self, min_support_projects: int, min_confidence: float, contamination: float, seed: int
    ) -> MineCorpusResult:
        command = MineCorpusCommand(
            report=self._paths.reports_dir / "mining.md",
            artifacts_dir=self._paths.reports_dir / "mining_artifacts",
            min_support_projects=min_support_projects,
            min_confidence=min_confidence,
            contamination=contamination,
            seed=seed,
        )
        try:
            return self._mine.execute(command)
        except MiningError as error:
            raise MlCommandError(str(error)) from None
