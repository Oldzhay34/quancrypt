"""MineAssociationRules (P7.4, D-337e, D-338e): FP-Growth over the libraries and algorithm families of every project;
the thresholds are applied here, one MLflow run, then ml_outputs."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from quancrypt_ml.domain import mining
from quancrypt_ml.domain.mining import RuleThresholds
from quancrypt_ml.domain.mining_report import RuleFacts
from quancrypt_ml.port.inbound.mining import MiningError, RulesCommand, RulesResult
from quancrypt_ml.port.outbound.labeling import ReportWriter
from quancrypt_ml.port.outbound.mining import MiningCharts, MiningRun, RuleMiner, RuleSink
from quancrypt_ml.port.outbound.risk import ModelRegistry
from quancrypt_ml.port.outbound.system import Clock
from quancrypt_ml.usecase.mining_runs import log_facts


@dataclass(frozen=True)
class RulePorts:
    miner: RuleMiner
    charts: MiningCharts
    registry: ModelRegistry
    sink: RuleSink
    reports: ReportWriter
    clock: Clock


class MineAssociationRulesService:
    def __init__(self, ports: RulePorts) -> None:
        self._ports = ports

    def execute(self, command: RulesCommand) -> RulesResult:
        if command.min_support_projects < 1 or not 0 < command.min_confidence <= 1:
            raise MiningError("the support is at least one project and the confidence is in (0, 1]")
        ports = self._ports
        projects = command.data.libraries
        transactions = [t for t in (mining.transaction(p) for p in sorted(projects, key=lambda p: p.project_key)) if t]
        thresholds = RuleThresholds(command.min_support_projects, command.min_confidence)
        support, skipped = None, None
        if len(transactions) < command.min_support_projects:
            skipped = f"{len(transactions)} projede öğe var, destek eşiği {command.min_support_projects} proje ister"
        else:
            support = thresholds.min_support(len(transactions))
        candidates = [] if support is None else ports.miner.mine(transactions, support)
        rules = mining.keep_rules(candidates, thresholds, len(transactions))
        items = Counter(item for t in transactions for item in t)
        facts = RuleFacts(
            data_sha256=mining.data_digest([], projects),
            transactions=len(transactions),
            items=dict(sorted(items.items(), key=lambda x: (-x[1], x[0]))),
            min_support_projects=command.min_support_projects,
            min_support=support,
            min_confidence=command.min_confidence,
            min_lift=thresholds.min_lift,
            candidate_rules=len(candidates),
            rules=rules,
            skipped=skipped,
        )
        charts = []
        if rules:
            chart = command.artifacts_dir / "rules.png"
            ports.charts.rules(rules, chart)
            charts.append(chart)
        metrics = {
            "transactions": float(len(transactions)),
            "items": float(len(items)),
            "candidate_rules": float(len(candidates)),
            "rules": float(len(rules)),
        }
        if support is not None:
            metrics["min_support"] = support
        run_id = log_facts(
            ports.registry, ports.reports, "association_rules", facts,
            {
                "min_support_projects": command.min_support_projects, "min_confidence": command.min_confidence,
                "min_lift": thresholds.min_lift,
            },
            metrics,
            command.artifacts_dir, charts,
        )  # fmt: skip
        parameters = {
            "min_support_projects": str(command.min_support_projects),
            "min_confidence": str(command.min_confidence),
            "min_lift": str(thresholds.min_lift),
        }
        ports.sink.store_rules(MiningRun(run_id, ports.clock.now(), len(transactions), parameters), rules)
        return RulesResult(facts, run_id)
