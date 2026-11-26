"""`ml mine` (P7.4): one read of the corpus data, the three mining use cases over it and the one report built from their
facts. The clusterings, the rules and the anomalies are each stored in their own transaction."""

from __future__ import annotations

from quancrypt_ml.domain.mining_report import build_report
from quancrypt_ml.port.inbound.mining import (
    AnomalyCommand,
    ClusterCommand,
    DetectAnomaliesUseCase,
    MineAssociationRulesUseCase,
    MineCorpusCommand,
    MineCorpusResult,
    MiningError,
    RulesCommand,
    RunClusteringUseCase,
)
from quancrypt_ml.port.outbound.labeling import ReportWriter
from quancrypt_ml.port.outbound.mining import MiningDataSource


class MineCorpusService:
    def __init__(
        self,
        data: MiningDataSource,
        clustering: RunClusteringUseCase,
        rules: MineAssociationRulesUseCase,
        anomalies: DetectAnomaliesUseCase,
        reports: ReportWriter,
    ) -> None:
        self._data = data
        self._clustering = clustering
        self._rules = rules
        self._anomalies = anomalies
        self._reports = reports

    def execute(self, command: MineCorpusCommand) -> MineCorpusResult:
        # Checked first, so that a bad option or an empty warehouse changes nothing.
        if command.min_support_projects < 1 or not 0 < command.min_confidence <= 1:
            raise MiningError("the support is at least one project and the confidence is in (0, 1]")
        if not 0 < command.contamination <= 0.5:
            raise MiningError("the contamination is in (0, 0.5]")
        data = self._data.snapshot()  # one read: the three techniques see the same warehouse
        if not data.profiles:
            raise MiningError("marts.mart_archetypes has no corpus project; build the warehouse first")
        clustering = self._clustering.execute(ClusterCommand(data, command.artifacts_dir, command.seed))
        rules = self._rules.execute(
            RulesCommand(data, command.artifacts_dir, command.min_support_projects, command.min_confidence)
        )
        anomalies = self._anomalies.execute(
            AnomalyCommand(data, command.artifacts_dir, command.contamination, command.seed)
        )
        run_ids = {"clustering": clustering.run_id, "rules": rules.run_id, "anomalies": anomalies.run_id}
        self._reports.write(command.report, build_report(clustering.facts, rules.facts, anomalies.facts, run_ids))
        facts = clustering.facts
        return MineCorpusResult(
            projects=facts.projects,
            clustering_skipped=facts.skipped,
            chosen_k=facts.chosen_k,
            archetype_names=tuple(a.name for a in facts.archetypes),
            hdbscan_clusters=facts.hdbscan_clusters,
            hdbscan_noise=facts.hdbscan_noise,
            rules=len(rules.facts.rules),
            rules_skipped=rules.facts.skipped,
            flagged=len(anomalies.facts.queue),
            anomalies_skipped=anomalies.facts.skipped,
            erased_skipped=max(clustering.erased_skipped, anomalies.erased_skipped),
            report=command.report,
        )
