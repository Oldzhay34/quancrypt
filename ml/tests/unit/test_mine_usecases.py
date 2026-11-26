"""The mining use cases, the report, the facade and the `ml mine` command over fake ports."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from quancrypt_ml.api.cli import app
from quancrypt_ml.domain.mining import FeatureMatrix, ProjectLibraries
from quancrypt_ml.facade.labeling_facade import MlCommandError
from quancrypt_ml.facade.mining_facade import MiningFacade, MiningPaths
from quancrypt_ml.infrastructure import container
from quancrypt_ml.port.inbound.mining import MineCorpusCommand, MiningError
from quancrypt_ml.port.outbound.mining import Clustering
from quancrypt_ml.usecase.detect_anomalies_service import AnomalyPorts, DetectAnomaliesService
from quancrypt_ml.usecase.mine_association_rules_service import MineAssociationRulesService, RulePorts
from quancrypt_ml.usecase.mine_corpus_service import MineCorpusService
from quancrypt_ml.usecase.run_clustering_service import ClusteringPorts, RunClusteringService
from tests.support.fakes import FakeReports, FixedClock
from tests.support.mining_fakes import (
    FakeAnomalyDetector,
    FakeClusterer,
    FakeMiningCharts,
    FakeMiningData,
    FakeMiningSink,
    FakeRuleMiner,
    corpus,
    key,
    profile,
)
from tests.support.risk_fakes import FakeRegistry


class World:
    def __init__(
        self, tmp_path: Path, data: FakeMiningData | None = None, clusterer: FakeClusterer | None = None
    ) -> None:
        self.data = data or FakeMiningData(with_findings=12)
        self.charts, self.sink = FakeMiningCharts(), FakeMiningSink()
        self.registry, self.reports, clock = FakeRegistry(), FakeReports(), FixedClock()
        self.tmp = tmp_path
        shared = (self.charts, self.registry, self.sink, self.reports, clock)
        self.service = MineCorpusService(
            self.data,
            RunClusteringService(ClusteringPorts(clusterer or FakeClusterer(), *shared)),
            MineAssociationRulesService(RulePorts(FakeRuleMiner(), *shared)),
            DetectAnomaliesService(AnomalyPorts(FakeAnomalyDetector(), *shared)),
            self.reports,
        )

    def command(self, **changes: object) -> MineCorpusCommand:
        values: dict[str, object] = {
            "report": self.tmp / "mining.md", "artifacts_dir": self.tmp / "mining_artifacts",
            "min_support_projects": 3, "min_confidence": 0.6, "contamination": 0.1, "seed": 42,
        }  # fmt: skip
        values.update(changes)
        return MineCorpusCommand(**values)  # type: ignore[arg-type]

    def document(self, name: str) -> dict[str, object]:
        found: dict[str, object] = json.loads(self.reports.texts[self.tmp / "mining_artifacts" / name / "facts.json"])
        return found


def test_the_three_techniques_are_logged_stored_and_reported(tmp_path: Path) -> None:
    world = World(tmp_path)
    result = world.service.execute(world.command())

    assert (result.projects, result.clustering_skipped, result.erased_skipped) == (9, None, 0)
    assert (result.rules_skipped, result.anomalies_skipped, world.data.reads) == (None, None, 1)
    assert result.chosen_k >= 2 and result.rules > 0 and result.flagged == 1
    assert [experiment for experiment, _ in world.registry.runs] == ["mining"] * 3
    assert [record.name for _, record in world.registry.runs] == ["clustering", "association_rules", "anomalies"]
    assert all(
        record.artifacts[0].name == "facts.json" and record.tags["data_sha256"] for _, record in world.registry.runs
    )
    assert set(world.sink.runs) == {"KMEANS", "HDBSCAN", "FP_GROWTH", "ISOLATION_FOREST"}
    assert world.sink.runs["KMEANS"].parameters["k"] == str(result.chosen_k)
    assert len(world.sink.assignments["KMEANS"]) == 9 and len(world.sink.anomalies) == 9
    assert world.sink.runs["FP_GROWTH"].parameters == {
        "min_support_projects": "3", "min_confidence": "0.6", "min_lift": "1.0",
    }  # fmt: skip
    text = world.reports.texts[tmp_path / "mining.md"]
    for heading in ("## 1. Kümeleme", "## 2. Birliktelik", "## 3. Anomali", "ÖNERİ, onaylanmadı"):
        assert heading in text
    assert "`lib:jjwt`" in text and "CVEfixes yüklü değil" in text
    assert key(9)[:12] in text and key(9)[:13] not in text  # only the first digits of a project key


def _numbers(value: object) -> Iterator[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, int | float):
        yield float(value)
    elif isinstance(value, dict):
        yield float(len(value))
        for k, v in value.items():
            if str(k).isdigit():
                yield float(k)
            yield from _numbers(v)
    elif isinstance(value, list):
        yield float(len(value))
        for v in value:
            yield from _numbers(v)
    elif isinstance(value, str):
        yield from (float(n) for n in re.findall(r"(?<![\w.])\d+(?:\.\d+)?(?![\w.])", value))


def test_every_number_of_the_report_is_in_the_logged_facts(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.service.execute(world.command())
    facts = [world.document(name) for name in ("clustering", "association_rules", "anomalies")]
    values = [n for document in facts for n in _numbers(document)]
    values.append(float(len([s for s in facts[2]["scores"] if s["is_flagged"]])))  # type: ignore[attr-defined]
    allowed = {f"{v:.3f}" for v in values} | {f"%{100 * v:.0f}" for v in values}
    allowed |= {str(int(v)) for v in values if v == int(v)}
    allowed |= {"12"}  # the digits of a project key the report prints (stated in the header)

    text = world.reports.texts[tmp_path / "mining.md"]
    body = re.sub(
        r"`[^`]*`|!\[[^\]]*\]\([^)]*\)|\bD-\d+\w?|§\d+|^#+ .*$|P[0-9]|Isolation|K-Means", " ", text, flags=re.M
    )
    printed = re.findall(r"%\d+|(?<![\w.])\d+(?:\.\d+)?(?![\w.])", body)

    assert printed and not [n for n in printed if n not in allowed]


def test_the_same_data_gives_the_same_facts_twice(tmp_path: Path) -> None:
    first, second = World(tmp_path / "a"), World(tmp_path / "b")
    first.service.execute(first.command())
    second.service.execute(second.command())
    for name in ("clustering", "association_rules", "anomalies"):
        assert first.document(name) == second.document(name)


def test_too_few_projects_are_not_clustered_and_old_results_are_replaced(tmp_path: Path) -> None:
    world = World(tmp_path, FakeMiningData(corpus()[:3], [], 3))
    result = world.service.execute(world.command())
    assert result.clustering_skipped is not None and result.chosen_k == 0 and result.flagged == 0
    assert world.sink.assignments == {"KMEANS": [], "HDBSCAN": []} and world.sink.rules == []
    assert world.sink.anomalies == []
    text = world.reports.texts[tmp_path / "mining.md"]
    assert "Kümeleme yapılmadı" in text and "Küme olmadığı için öneri yok" in text
    assert "Kural madenciliği yapılmadı" in text and "Anomali tespiti yapılmadı" in text
    assert "İnceleme kuyruğu" not in text and "ağaç" not in text  # nothing that did not run is described
    assert "kural adayı" not in text and "(1.000)" not in text
    assert result.rules_skipped is not None and result.anomalies_skipped is not None
    assert "min_support" not in world.registry.runs[1][1].metrics


def test_an_erased_project_is_counted(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.sink.present = {p.project_key for p in corpus()[1:]}
    assert world.service.execute(world.command()).erased_skipped == 1


@pytest.mark.parametrize(
    "changes",
    [{"min_support_projects": 0}, {"min_confidence": 0.0}, {"min_confidence": 1.5}, {"contamination": 0.6}],
)
def test_a_bad_option_changes_nothing(tmp_path: Path, changes: dict[str, object]) -> None:
    world = World(tmp_path)
    with pytest.raises(MiningError):
        world.service.execute(world.command(**changes))
    assert world.registry.runs == [] and world.sink.runs == {}


def test_an_empty_warehouse_changes_nothing_and_reaches_the_user(tmp_path: Path) -> None:
    world = World(tmp_path, FakeMiningData([], [], 0))
    facade = MiningFacade(world.service, MiningPaths(tmp_path))
    with pytest.raises(MlCommandError, match="build the warehouse"):
        facade.mine(3, 0.6, 0.1, 42)
    assert world.sink.runs == {}


def test_the_command_prints_the_result(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = World(tmp_path)
    monkeypatch.setattr(container, "mining", lambda: MiningFacade(world.service, MiningPaths(tmp_path)))
    result = CliRunner().invoke(app, ["mine"])
    assert result.exit_code == 0, result.output
    assert "9 corpus projects" in result.output and "review queue: 1" in result.output
    assert (tmp_path / "mining.md") in world.reports.texts
    failed = CliRunner().invoke(app, ["mine", "--contamination", "0.9"])
    assert failed.exit_code == 1


def test_the_command_needs_the_warehouse_settings() -> None:
    result = CliRunner().invoke(app, ["mine"], env={"WAREHOUSE_DB_URL": "", "WAREHOUSE_DB_APP_PASSWORD": ""})
    assert result.exit_code == 2


def test_enough_projects_without_a_shared_item_give_no_rule_and_say_so(tmp_path: Path) -> None:
    apart = [ProjectLibraries(key(i), [(f"lib{i}", "UNKNOWN")]) for i in range(1, 6)]
    world = World(tmp_path, FakeMiningData(usages=apart))
    assert world.service.execute(world.command()).rules == 0
    assert "Eşikleri geçen kural yok" in world.reports.texts[tmp_path / "mining.md"]


def test_the_unknown_comment_appears_only_for_a_cluster_led_by_the_unknown_family(tmp_path: Path) -> None:
    world = World(tmp_path)
    world.service.execute(world.command())
    assert "merkezinde en yüksek aile payı `UNKNOWN`" in world.reports.texts[tmp_path / "mining.md"]
    known = [profile(i, {"RSA": 1.0}, {"SIGNATURE" if i < 4 else "ENCRYPTION": 1.0}) for i in range(1, 8)]
    other = World(tmp_path / "b", FakeMiningData(known, []))
    other.service.execute(other.command())
    assert "merkezinde en yüksek aile payı" not in other.reports.texts[tmp_path / "b" / "mining.md"]


def test_profiles_that_do_not_separate_are_not_clustered(tmp_path: Path) -> None:
    class OneCluster(FakeClusterer):
        def kmeans(self, matrix: FeatureMatrix, k: int, seed: int) -> Clustering:
            return Clustering(tuple(0 for _ in matrix.keys), None, 0.0)

    world = World(tmp_path, clusterer=OneCluster())
    result = world.service.execute(world.command())
    assert result.clustering_skipped is not None and "ayrışmıyor" in result.clustering_skipped
    assert world.sink.assignments == {"KMEANS": [], "HDBSCAN": []}
    assert "Kümeleme yapılmadı" in world.reports.texts[tmp_path / "mining.md"]


def test_the_command_says_which_steps_were_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    world = World(tmp_path, FakeMiningData(corpus()[:3], [], 3))
    monkeypatch.setattr(container, "mining", lambda: MiningFacade(world.service, MiningPaths(tmp_path)))
    output = CliRunner().invoke(app, ["mine"]).output
    for line in ("clustering skipped:", "association rules skipped:", "anomaly detection skipped:"):
        assert line in output
    assert "review queue: 0" not in output


def test_the_report_calls_the_structure_weak_only_when_hdbscan_finds_no_cluster(tmp_path: Path) -> None:
    class AllNoise(FakeClusterer):
        def hdbscan(self, matrix: FeatureMatrix, min_cluster_size: int) -> Clustering:
            return Clustering(tuple(-1 for _ in matrix.keys), None, None)

    none = World(tmp_path / "none", clusterer=AllNoise())
    none.service.execute(none.command())
    text = none.reports.texts[tmp_path / "none" / "mining.md"]
    assert "HDBSCAN küme bulmadı (9 proje gürültü): kümeleme yapısı zayıftır" in text
    found = World(tmp_path / "found")
    assert found.service.execute(found.command()).hdbscan_clusters > 0
    assert "kümeleme yapısı zayıftır" not in found.reports.texts[tmp_path / "found" / "mining.md"]
