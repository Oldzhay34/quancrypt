"""RunClustering (P7.4, D-338): K-Means with k chosen by the silhouette (the elbow is reported), HDBSCAN beside it,
archetype names from the cluster centres; one MLflow run, then both clusterings into ml_outputs in one transaction."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from quancrypt_ml.domain import mining
from quancrypt_ml.domain.mining import FeatureMatrix, ProjectProfile
from quancrypt_ml.domain.mining_report import KEY_DIGITS, Assignment, ClusteringFacts, PlanProposal
from quancrypt_ml.port.inbound.mining import ClusterCommand, ClusteringResult
from quancrypt_ml.port.outbound.labeling import ReportWriter
from quancrypt_ml.port.outbound.mining import (
    ClusterAssignment,
    Clusterer,
    Clustering,
    ClusterSink,
    MiningCharts,
    MiningRun,
    TechniqueClusters,
)
from quancrypt_ml.port.outbound.risk import ModelRegistry
from quancrypt_ml.port.outbound.system import Clock
from quancrypt_ml.usecase.mining_runs import log_facts


@dataclass(frozen=True)
class ClusteringPorts:
    clusterer: Clusterer
    charts: MiningCharts
    registry: ModelRegistry
    sink: ClusterSink
    reports: ReportWriter
    clock: Clock


@dataclass(frozen=True)
class _Outcome:
    """The two clusterings of one run: cluster numbers per matrix row."""

    silhouettes: Mapping[int, float]
    inertias: Mapping[int, float]
    chosen_k: int
    kmeans: Clustering
    hdbscan: Clustering
    kmeans_numbers: Sequence[int | None]
    hdbscan_numbers: Sequence[int | None]
    adjusted_rand: float | None
    charts: Sequence[Path]


class RunClusteringService:
    def __init__(self, ports: ClusteringPorts) -> None:
        self._ports = ports

    def execute(self, command: ClusterCommand) -> ClusteringResult:
        ports = self._ports
        profiles = sorted(command.data.profiles, key=lambda p: p.project_key)
        matrix = mining.feature_matrix(profiles)
        outcome, skipped = None, None
        if len(profiles) < mining.MIN_PROJECTS:
            skipped = f"{len(profiles)} proje var, en az {mining.MIN_PROJECTS} gerekir"
        else:
            outcome = self._cluster(matrix, command)
            if outcome is None:
                skipped = "hiçbir k için siluet hesaplanamadı: proje profilleri ayrışmıyor"
        facts = self._facts(command, profiles, matrix, outcome, skipped)
        run_id = log_facts(
            ports.registry, ports.reports, "clustering", facts,
            {"seed": command.seed, "hdbscan_min_cluster_size": mining.HDBSCAN_MIN_CLUSTER_SIZE, "max_k": mining.MAX_K},
            self._metrics(facts), command.artifacts_dir, outcome.charts if outcome else (),
        )  # fmt: skip
        return ClusteringResult(facts, run_id, self._store(profiles, facts, outcome, run_id, command))

    def _cluster(self, matrix: FeatureMatrix, command: ClusterCommand) -> _Outcome | None:
        """None when no k gives a silhouette (every project looks the same)."""
        clusterer, charts = self._ports.clusterer, self._ports.charts
        runs = {k: clusterer.kmeans(matrix, k, command.seed) for k in mining.candidate_ks(len(matrix.keys))}
        silhouettes = {k: r.silhouette for k, r in runs.items() if r.silhouette is not None}
        if not silhouettes:
            return None
        inertias = {k: r.inertia for k, r in runs.items() if r.inertia is not None and k in silhouettes}
        chosen = mining.best_k(silhouettes)
        kmeans, hdbscan = runs[chosen], clusterer.hdbscan(matrix, mining.HDBSCAN_MIN_CLUSTER_SIZE)
        numbers = mining.number_clusters(kmeans.labels)
        clustered = [i for i, label in enumerate(hdbscan.labels) if label >= 0]
        rand = (
            clusterer.adjusted_rand([kmeans.labels[i] for i in clustered], [hdbscan.labels[i] for i in clustered])
            if clustered
            else None
        )
        k_chart = command.artifacts_dir / "k_selection.png"
        map_chart = command.artifacts_dir / "cluster_map.png"
        charts.k_selection(silhouettes, inertias, k_chart)
        charts.cluster_map(clusterer.project_2d(matrix), numbers, map_chart)
        return _Outcome(
            silhouettes, inertias, chosen, kmeans, hdbscan, numbers, mining.number_clusters(hdbscan.labels), rand,
            (k_chart, map_chart),
        )  # fmt: skip

    @staticmethod
    def _facts(
        command: ClusterCommand,
        profiles: Sequence[ProjectProfile],
        matrix: FeatureMatrix,
        outcome: _Outcome | None,
        skipped: str | None,
    ) -> ClusteringFacts:
        found, dense = [], []
        if outcome:
            found = mining.archetypes(profiles, dict(zip(matrix.keys, outcome.kmeans_numbers, strict=True)))
            dense = mining.archetypes(profiles, dict(zip(matrix.keys, outcome.hdbscan_numbers, strict=True)))
        assignments = [
            Assignment(key[:KEY_DIGITS], outcome.kmeans_numbers[i], outcome.hdbscan_numbers[i])
            for i, key in enumerate(matrix.keys)
            if outcome
        ]
        unknown = [p.family_shares.get(mining.UNKNOWN, 0.0) for p in profiles]
        return ClusteringFacts(
            data_sha256=mining.data_digest(profiles),
            seed=command.seed,
            projects_with_findings=command.data.projects_with_findings,
            projects=len(profiles),
            features=matrix.columns,
            skipped=skipped,
            silhouettes={str(k): v for k, v in outcome.silhouettes.items()} if outcome else {},
            inertias={str(k): v for k, v in outcome.inertias.items()} if outcome else {},
            chosen_k=outcome.chosen_k if outcome else 0,
            elbow_k=mining.elbow_k(outcome.inertias) if outcome else 0,
            kmeans_silhouette=(outcome.kmeans.silhouette or 0.0) if outcome else 0.0,
            hdbscan_min_cluster_size=mining.HDBSCAN_MIN_CLUSTER_SIZE,
            hdbscan_clusters=len(dense),
            hdbscan_noise=sum(1 for n in outcome.hdbscan_numbers if n is None) if outcome else 0,
            hdbscan_silhouette=outcome.hdbscan.silhouette if outcome else None,
            adjusted_rand=outcome.adjusted_rand if outcome else None,
            archetypes=found,
            hdbscan_archetypes=dense,
            assignments=assignments,
            mean_unknown_share=sum(unknown) / len(unknown) if unknown else 0.0,
            plans=[PlanProposal(a.name, mining.plan_template(a)) for a in found],
        )

    @staticmethod
    def _metrics(facts: ClusteringFacts) -> dict[str, float]:
        metrics = {
            "projects": facts.projects, "projects_with_findings": facts.projects_with_findings,
            "chosen_k": facts.chosen_k, "elbow_k": facts.elbow_k, "kmeans_silhouette": facts.kmeans_silhouette,
            "hdbscan_clusters": facts.hdbscan_clusters, "hdbscan_noise": facts.hdbscan_noise,
            "mean_unknown_share": facts.mean_unknown_share,
        }  # fmt: skip
        metrics.update({f"silhouette_k{k}": v for k, v in facts.silhouettes.items()})
        metrics.update({f"inertia_k{k}": v for k, v in facts.inertias.items()})
        if facts.hdbscan_silhouette is not None:
            metrics["hdbscan_silhouette"] = facts.hdbscan_silhouette
        if facts.adjusted_rand is not None:
            metrics["adjusted_rand"] = facts.adjusted_rand
        return {k: float(v) for k, v in metrics.items()}

    def _store(
        self,
        profiles: Sequence[ProjectProfile],
        facts: ClusteringFacts,
        outcome: _Outcome | None,
        run_id: str,
        command: ClusterCommand,
    ) -> int:
        keys = [p.project_key for p in profiles]
        at = self._ports.clock.now()
        clusterings = []
        for technique, found, numbers, parameters in (
            ("KMEANS", facts.archetypes, outcome.kmeans_numbers if outcome else [], {"k": str(facts.chosen_k)}),
            (
                "HDBSCAN",
                facts.hdbscan_archetypes,
                outcome.hdbscan_numbers if outcome else [],
                {"min_cluster_size": str(facts.hdbscan_min_cluster_size)},
            ),
        ):
            run = MiningRun(run_id, at, len(keys), {**parameters, "seed": str(command.seed)})
            assigned = [ClusterAssignment(key, number) for key, number in zip(keys, numbers, strict=False)]
            clusterings.append(TechniqueClusters(technique, run, found, assigned))
        return self._ports.sink.store_clusters(clusterings)
