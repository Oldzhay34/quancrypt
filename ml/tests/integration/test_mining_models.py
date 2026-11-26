"""`ml mine` end to end with the real scikit-learn, mlxtend, matplotlib and report writer over synthetic profiles: the
two groups are found and two runs on the same data give the same facts (ml-pipeline section 8)."""

from __future__ import annotations

import json
from pathlib import Path

from quancrypt_ml.infrastructure.files.text_files import FileReportWriter
from quancrypt_ml.infrastructure.model.mining import MlxtendRuleMiner, SklearnAnomalyDetector, SklearnClusterer
from quancrypt_ml.infrastructure.model.mining_charts import MatplotlibMiningCharts
from quancrypt_ml.port.inbound.mining import MineCorpusCommand, MineCorpusResult
from quancrypt_ml.usecase.detect_anomalies_service import AnomalyPorts, DetectAnomaliesService
from quancrypt_ml.usecase.mine_association_rules_service import MineAssociationRulesService, RulePorts
from quancrypt_ml.usecase.mine_corpus_service import MineCorpusService
from quancrypt_ml.usecase.run_clustering_service import ClusteringPorts, RunClusteringService
from tests.support.fakes import FixedClock
from tests.support.mining_fakes import FakeMiningData, FakeMiningSink, profile
from tests.support.risk_fakes import FakeRegistry


def _run(folder: Path, data: FakeMiningData | None = None) -> tuple[MineCorpusResult, FakeRegistry]:
    data, charts, sink = data or FakeMiningData(), MatplotlibMiningCharts(), FakeMiningSink()
    registry, reports, clock = FakeRegistry(), FileReportWriter(), FixedClock()
    shared = (charts, registry, sink, reports, clock)
    service = MineCorpusService(
        data,
        RunClusteringService(ClusteringPorts(SklearnClusterer(), *shared)),
        MineAssociationRulesService(RulePorts(MlxtendRuleMiner(), *shared)),
        DetectAnomaliesService(AnomalyPorts(SklearnAnomalyDetector(), *shared)),
        reports,
    )
    command = MineCorpusCommand(folder / "mining.md", folder / "mining_artifacts", 3, 0.6, 0.1, 42)
    return service.execute(command), registry


def test_the_real_engines_find_the_groups_rules_and_the_odd_project(tmp_path: Path) -> None:
    result, registry = _run(tmp_path)
    assert result.projects == 9 and result.chosen_k >= 2
    centres = {name.split(",")[0] for name in result.archetype_names}
    assert {"RSA / TOKEN_SIGNATURE", "UNKNOWN / TLS_KEY_EXCHANGE"} <= centres
    assert all("birim başına" in name for name in result.archetype_names)
    assert result.rules > 0 and result.flagged >= 1
    assert "`lib:spring-security-oauth2-jose`" in (tmp_path / "mining.md").read_text(encoding="utf-8")
    for chart in ("k_selection", "cluster_map", "rules", "anomaly_scores"):
        assert (tmp_path / "mining_artifacts" / f"{chart}.png").stat().st_size > 0
    logged = {path.name for _, record in registry.runs for path in record.artifacts}
    assert logged == {"facts.json", "k_selection.png", "cluster_map.png", "rules.png", "anomaly_scores.png"}


def test_two_runs_on_the_same_data_give_the_same_facts(tmp_path: Path) -> None:
    _run(tmp_path / "a")
    _run(tmp_path / "b")
    for name in ("clustering", "association_rules", "anomalies"):
        first, second = (
            json.loads((tmp_path / side / "mining_artifacts" / name / "facts.json").read_text(encoding="utf-8"))
            for side in ("a", "b")
        )
        assert first == second


def test_identical_profiles_are_reported_not_clustered_by_the_real_engines(tmp_path: Path) -> None:
    same = [profile(i, {"RSA": 1.0}, {"SIGNATURE": 1.0}) for i in range(1, 7)]
    result, _ = _run(tmp_path, FakeMiningData(same, []))
    assert result.clustering_skipped is not None and "ayrışmıyor" in result.clustering_skipped
