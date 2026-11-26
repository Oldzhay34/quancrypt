"""DetectAnomalies (P7.4, D-337d, D-338f): Isolation Forest over the clustering features; the flagged projects are the
review queue; one MLflow run, then ml_outputs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from quancrypt_ml.domain import mining
from quancrypt_ml.domain.mining_report import KEY_DIGITS, AnomalyFacts, ScoredProject
from quancrypt_ml.port.inbound.mining import AnomalyCommand, AnomalyResult, MiningError
from quancrypt_ml.port.outbound.labeling import ReportWriter
from quancrypt_ml.port.outbound.mining import (
    AnomalyDetector,
    AnomalySink,
    MiningCharts,
    MiningRun,
)
from quancrypt_ml.port.outbound.risk import ModelRegistry
from quancrypt_ml.port.outbound.system import Clock
from quancrypt_ml.usecase.mining_runs import log_facts


@dataclass(frozen=True)
class AnomalyPorts:
    detector: AnomalyDetector
    charts: MiningCharts
    registry: ModelRegistry
    sink: AnomalySink
    reports: ReportWriter
    clock: Clock


def _top(shares: Mapping[str, float]) -> tuple[str, float]:
    if not shares:
        return "-", 0.0
    code = min(shares, key=lambda c: (-shares[c], c))
    return code, shares[code]


class DetectAnomaliesService:
    def __init__(self, ports: AnomalyPorts) -> None:
        self._ports = ports

    def execute(self, command: AnomalyCommand) -> AnomalyResult:
        if not 0 < command.contamination <= 0.5:
            raise MiningError("the contamination is in (0, 0.5]")
        ports = self._ports
        profiles = {p.project_key: p for p in command.data.profiles}
        matrix = mining.feature_matrix(list(profiles.values()))
        scores = (
            ports.detector.score(matrix, command.contamination, mining.ISOLATION_TREES, command.seed)
            if len(matrix.keys) >= mining.MIN_PROJECTS
            else []
        )
        skipped = None
        if len(matrix.keys) < mining.MIN_PROJECTS:
            skipped = f"{len(matrix.keys)} proje var, en az {mining.MIN_PROJECTS} gerekir"
        scored = []
        for item in sorted(scores, key=lambda s: (s.score, s.project_key)):
            profile = profiles[item.project_key]
            family, family_share = _top(profile.family_shares)
            context, context_share = _top(profile.context_shares)
            scored.append(
                ScoredProject(
                    item.project_key[:KEY_DIGITS],
                    item.score,
                    item.is_flagged,
                    profile.finding_count,
                    family,
                    family_share,
                    context,
                    context_share,
                )  # fmt: skip
            )
        facts = AnomalyFacts(
            mining.data_digest(list(profiles.values())), command.seed, len(profiles), command.contamination,
            mining.ISOLATION_TREES, scored, skipped,
        )  # fmt: skip
        charts = []
        if scores:
            chart = command.artifacts_dir / "anomaly_scores.png"
            ports.charts.anomaly_scores(scores, chart)
            charts.append(chart)
        run_id = log_facts(
            ports.registry, ports.reports, "anomalies", facts,
            {"contamination": command.contamination, "trees": mining.ISOLATION_TREES, "seed": command.seed},
            {"projects": float(len(profiles)), "flagged": float(len(mining.review_queue(scores)))},
            command.artifacts_dir, charts,
        )  # fmt: skip
        parameters = {
            "contamination": str(command.contamination),
            "trees": str(mining.ISOLATION_TREES),
            "seed": str(command.seed),
        }
        run = MiningRun(run_id, ports.clock.now(), len(profiles), parameters)
        return AnomalyResult(facts, run_id, ports.sink.store_anomalies(run, scores))
