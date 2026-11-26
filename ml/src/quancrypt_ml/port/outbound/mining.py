"""Outbound ports of data mining (P7.4, ml-pipeline sections 1 and 5). scikit-learn, mlxtend and matplotlib live behind
them, in infrastructure only."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Protocol

from quancrypt_ml.domain.mining import (
    AnomalyScore,
    Archetype,
    FeatureMatrix,
    MiningSnapshot,
    Rule,
)


class MiningDataSource(Protocol):
    """The corpus rows of marts.mart_archetypes and marts.mart_risk_features (D-337)."""

    def snapshot(self) -> MiningSnapshot:
        """The profiles, the non-test (library, family) pairs per project and the number of corpus projects with any
        finding, all from one consistent read."""
        ...


@dataclass(frozen=True)
class Clustering:
    labels: tuple[int, ...]  # one per matrix row, -1 is noise
    silhouette: float | None  # None: fewer than two clusters among the non-noise rows
    inertia: float | None  # K-Means only


class Clusterer(Protocol):
    def kmeans(self, matrix: FeatureMatrix, k: int, seed: int) -> Clustering: ...

    def hdbscan(self, matrix: FeatureMatrix, min_cluster_size: int) -> Clustering: ...

    def adjusted_rand(self, first: Sequence[int], second: Sequence[int]) -> float: ...

    def project_2d(self, matrix: FeatureMatrix) -> list[tuple[float, float]]:
        """The scaled features on their two main axes, for the plot."""
        ...


class RuleMiner(Protocol):
    def mine(self, transactions: Sequence[frozenset[str]], min_support: float) -> list[Rule]:
        """Every rule of the frequent itemsets (FP-Growth), whatever its confidence and lift."""
        ...


class AnomalyDetector(Protocol):
    def score(self, matrix: FeatureMatrix, contamination: float, trees: int, seed: int) -> list[AnomalyScore]:
        """One score per matrix row, in the matrix order."""
        ...


class MiningCharts(Protocol):
    def k_selection(self, silhouettes: Mapping[int, float], inertias: Mapping[int, float], path: Path) -> None: ...

    def cluster_map(self, points: Sequence[tuple[float, float]], numbers: Sequence[int | None], path: Path) -> None: ...

    def rules(self, rules: Sequence[Rule], path: Path) -> None: ...

    def anomaly_scores(self, scores: Sequence[AnomalyScore], path: Path) -> None: ...


@dataclass(frozen=True)
class MiningRun:
    mlflow_run_id: str
    run_at: datetime
    project_count: int
    parameters: Mapping[str, str]


@dataclass(frozen=True)
class ClusterAssignment:
    project_key: str
    cluster_no: int | None  # None: HDBSCAN noise


@dataclass(frozen=True)
class TechniqueClusters:
    technique: str  # KMEANS or HDBSCAN
    run: MiningRun
    archetypes: Sequence[Archetype]
    assignments: Sequence[ClusterAssignment]


class ClusterSink(Protocol):
    def store_clusters(self, clusterings: Sequence[TechniqueClusters]) -> int:
        """Replaces the run of every given technique as a whole, all in one transaction. Returns the projects not
        written because they were erased (KVKK) after they were read."""
        ...


class RuleSink(Protocol):
    def store_rules(self, run: MiningRun, rules: Sequence[Rule]) -> None:
        """Replaces the FP-Growth run as a whole; rules are numbered from 1 in the given order."""
        ...


class AnomalySink(Protocol):
    def store_anomalies(self, run: MiningRun, scores: Sequence[AnomalyScore]) -> int:
        """Replaces the Isolation Forest run as a whole. Returns the scores not written (erased projects)."""
        ...
