"""Inbound ports of data mining (P7.4)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from quancrypt_ml.domain.mining import MiningSnapshot
from quancrypt_ml.domain.mining_report import AnomalyFacts, ClusteringFacts, RuleFacts


class MiningError(Exception):
    """Mining could not run; the message carries no project data."""


@dataclass(frozen=True)
class ClusterCommand:
    data: MiningSnapshot
    artifacts_dir: Path
    seed: int


@dataclass(frozen=True)
class ClusteringResult:
    facts: ClusteringFacts
    run_id: str
    erased_skipped: int


@dataclass(frozen=True)
class RulesCommand:
    data: MiningSnapshot
    artifacts_dir: Path
    min_support_projects: int
    min_confidence: float


@dataclass(frozen=True)
class RulesResult:
    facts: RuleFacts
    run_id: str


@dataclass(frozen=True)
class AnomalyCommand:
    data: MiningSnapshot
    artifacts_dir: Path
    contamination: float
    seed: int


@dataclass(frozen=True)
class AnomalyResult:
    facts: AnomalyFacts
    run_id: str
    erased_skipped: int


class RunClusteringUseCase(Protocol):
    def execute(self, command: ClusterCommand) -> ClusteringResult: ...


class MineAssociationRulesUseCase(Protocol):
    def execute(self, command: RulesCommand) -> RulesResult: ...


class DetectAnomaliesUseCase(Protocol):
    def execute(self, command: AnomalyCommand) -> AnomalyResult: ...


@dataclass(frozen=True)
class MineCorpusCommand:
    report: Path
    artifacts_dir: Path
    min_support_projects: int
    min_confidence: float
    contamination: float
    seed: int


@dataclass(frozen=True)
class MineCorpusResult:
    projects: int
    clustering_skipped: str | None
    chosen_k: int
    archetype_names: tuple[str, ...]
    hdbscan_clusters: int
    hdbscan_noise: int
    rules: int
    rules_skipped: str | None
    flagged: int
    anomalies_skipped: str | None
    erased_skipped: int
    report: Path


class MineCorpusUseCase(Protocol):
    def execute(self, command: MineCorpusCommand) -> MineCorpusResult: ...
