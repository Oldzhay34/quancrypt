"""Shared contracts of the mining outbound ports (LSP, hexagonal-service section 7): every port with a fake runs the
same cases against the fake and the real adapter."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from quancrypt_ml.domain import mining
from quancrypt_ml.domain.mining import AnomalyScore, Archetype, ProjectLibraries, ProjectProfile, Rule
from quancrypt_ml.port.outbound.mining import (
    AnomalyDetector,
    AnomalySink,
    ClusterAssignment,
    Clusterer,
    ClusterSink,
    MiningCharts,
    MiningDataSource,
    MiningRun,
    RuleMiner,
    RuleSink,
    TechniqueClusters,
)
from tests.support.mining_fakes import corpus, key, libraries

# ---------------------------------------------------------------- MiningDataSource
# factory(profiles, libraries, with_findings): a source that holds exactly these.
DataFactory = Callable[[list[ProjectProfile], list[ProjectLibraries], int], MiningDataSource]


def data_case_profiles_and_libraries_come_back_per_project(factory: DataFactory) -> None:
    profiles, usages = corpus()[:3], libraries()[:3]
    source = factory(profiles, usages, 5)
    data = source.snapshot()
    found = {p.project_key: p for p in data.profiles}
    assert set(found) == {p.project_key for p in profiles}
    for expected in profiles:
        got = found[expected.project_key]
        assert (got.analysis_unit_count, got.finding_count) == (expected.analysis_unit_count, expected.finding_count)
        assert got.findings_per_unit == expected.findings_per_unit
        assert got.family_shares == dict(expected.family_shares)
        assert got.context_shares == dict(expected.context_shares)
        assert got.priority_shares == dict(expected.priority_shares)
    items = {p.project_key: mining.transaction(p) for p in data.libraries}
    assert items == {p.project_key: mining.transaction(p) for p in usages}
    assert data.projects_with_findings == 5


def data_case_an_empty_source_has_no_projects(factory: DataFactory) -> None:
    data = factory([], [], 0).snapshot()
    assert list(data.profiles) == [] and list(data.libraries) == [] and data.projects_with_findings == 0


DATA_CASES = [data_case_profiles_and_libraries_come_back_per_project, data_case_an_empty_source_has_no_projects]

# ---------------------------------------------------------------- Clusterer


def clusterer_case_two_clear_groups_are_separated(clusterer: Clusterer) -> None:
    matrix = mining.feature_matrix(corpus()[:8])
    found = clusterer.kmeans(matrix, 2, 42)
    group = dict(zip(matrix.keys, found.labels, strict=True))
    assert len({group[key(i)] for i in range(1, 5)}) == 1 and len({group[key(i)] for i in range(5, 9)}) == 1
    assert group[key(1)] != group[key(5)]
    assert found.silhouette is not None and 0.5 < found.silhouette <= 1.0
    assert found.inertia is not None and found.inertia >= 0
    assert clusterer.kmeans(matrix, 2, 42) == found
    dense = clusterer.hdbscan(matrix, 3)
    assert len(dense.labels) == 8 and all(label >= -1 for label in dense.labels) and dense.inertia is None


def clusterer_case_agreement_and_projection(clusterer: Clusterer) -> None:
    assert clusterer.adjusted_rand([0, 0, 1, 1], [1, 1, 0, 0]) == 1.0
    assert clusterer.adjusted_rand([0, 0, 1, 1], [0, 1, 0, 1]) < 0.5
    matrix = mining.feature_matrix(corpus())
    assert len(clusterer.project_2d(matrix)) == len(matrix.keys)


CLUSTERER_CASES = [clusterer_case_two_clear_groups_are_separated, clusterer_case_agreement_and_projection]

# ---------------------------------------------------------------- RuleMiner


def miner_case_support_confidence_and_lift_of_every_rule(miner: RuleMiner) -> None:
    transactions = [frozenset({"lib:a", "alg:RSA"})] * 3 + [frozenset({"lib:b"})]
    found = {(r.antecedent, r.consequent): r for r in miner.mine(transactions, 0.5)}
    assert set(found) == {(("alg:RSA",), ("lib:a",)), (("lib:a",), ("alg:RSA",))}
    rule = found[(("lib:a",), ("alg:RSA",))]
    assert (rule.support, rule.confidence) == (0.75, 1.0) and abs(rule.lift - 4 / 3) < 1e-9
    assert miner.mine(transactions, 0.9) == []
    assert miner.mine([], 0.5) == [] or miner.mine([frozenset()], 0.5) == []


MINER_CASES = [miner_case_support_confidence_and_lift_of_every_rule]

# ---------------------------------------------------------------- AnomalyDetector


def detector_case_the_odd_project_is_the_most_unusual(detector: AnomalyDetector) -> None:
    matrix = mining.feature_matrix(corpus())
    scores = detector.score(matrix, 0.1, 100, 42)
    assert [s.project_key for s in scores] == list(matrix.keys)
    assert min(scores, key=lambda s: s.score).project_key == key(9)
    assert [s.project_key for s in scores if s.is_flagged] == [key(9)]
    assert all(s.is_flagged == (s.score < 0) for s in scores)
    assert detector.score(matrix, 0.1, 100, 42) == scores


DETECTOR_CASES = [detector_case_the_odd_project_is_the_most_unusual]

# ---------------------------------------------------------------- MiningCharts


def charts_case_every_chart_is_a_png(charts: MiningCharts, folder: Path) -> None:
    charts.k_selection({2: 0.5, 3: 0.4}, {2: 10.0, 3: 6.0}, folder / "a" / "k.png")
    charts.cluster_map([(0.0, 0.0), (1.0, 1.0)], [1, None], folder / "map.png")
    charts.rules([Rule(("lib:a",), ("alg:RSA",), 0.5, 1.0, 1.5)], folder / "rules.png")
    charts.anomaly_scores([AnomalyScore(key(1), -0.1, True), AnomalyScore(key(2), 0.2, False)], folder / "scores.png")
    for name in ("a/k.png", "map.png", "rules.png", "scores.png"):
        assert (folder / name).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


CHART_CASES = [charts_case_every_chart_is_a_png]

# ---------------------------------------------------------------- ClusterSink, RuleSink, AnomalySink

AT = datetime(2026, 11, 26, 12, 0, tzinfo=UTC)


@dataclass(frozen=True)
class SinkState:
    """What the sink holds: runs per technique, clusters, assignments, rules and anomaly rows."""

    runs: dict[str, int]  # technique -> project_count
    archetypes: set[tuple[str, int, str]]
    assignments: set[tuple[str, str, int | None]]
    rules: list[tuple[tuple[str, ...], tuple[str, ...]]]
    anomalies: set[tuple[str, bool]]


class Sink(ClusterSink, RuleSink, AnomalySink):  # the one adapter implements the three ports
    pass


@dataclass(frozen=True)
class SinkHarness:
    sink: Sink
    read: Callable[[], SinkState]
    present: Callable[[list[str]], None]  # from now on only these projects have findings


def _run(projects: int) -> MiningRun:
    return MiningRun(uuid.uuid4().hex, AT, projects, {"seed": "42"})


def _archetype(number: int, name: str) -> Archetype:
    return Archetype(number, name, "r", 1, {}, {}, {}, 1.0)


def _clusters(
    technique: str, run: MiningRun, archetypes: list[Archetype], assigned: list[ClusterAssignment]
) -> TechniqueClusters:
    return TechniqueClusters(technique, run, archetypes, assigned)


def sink_case_a_run_replaces_the_previous_one(harness: SinkHarness) -> None:
    harness.present([key(1), key(2)])
    harness.sink.store_clusters(
        [
            _clusters(
                "KMEANS", _run(2), [_archetype(1, "RSA / SIGNATURE")],
                [ClusterAssignment(key(1), 1), ClusterAssignment(key(2), 1)],
            ),
            _clusters("HDBSCAN", _run(2), [], [ClusterAssignment(key(1), None)]),
        ]
    )  # fmt: skip
    skipped = harness.sink.store_clusters(
        [_clusters("KMEANS", _run(1), [_archetype(1, "UNKNOWN / HASH")], [ClusterAssignment(key(2), 1)])]
    )
    rule = Rule(("lib:a",), ("alg:RSA",), 0.5, 1.0, 1.5)
    harness.sink.store_rules(_run(4), [rule, Rule(("alg:RSA",), ("lib:a",), 0.5, 0.8, 1.2)])
    harness.sink.store_rules(_run(4), [rule])
    harness.sink.store_anomalies(_run(2), [AnomalyScore(key(1), -0.2, True)])
    harness.sink.store_anomalies(_run(2), [AnomalyScore(key(2), 0.1, False)])

    state = harness.read()

    assert skipped == 0
    assert state.runs == {"KMEANS": 1, "HDBSCAN": 2, "FP_GROWTH": 4, "ISOLATION_FOREST": 2}
    assert state.archetypes == {("KMEANS", 1, "UNKNOWN / HASH")}
    assert state.assignments == {("KMEANS", key(2), 1), ("HDBSCAN", key(1), None)}
    assert state.rules == [(("lib:a",), ("alg:RSA",))]
    assert state.anomalies == {(key(2), False)}


def sink_case_an_erased_project_is_not_written(harness: SinkHarness) -> None:
    harness.present([key(1)])
    both = [ClusterAssignment(key(1), 1), ClusterAssignment(key(2), 1)]
    skipped_clusters = harness.sink.store_clusters(
        [
            _clusters("KMEANS", _run(2), [_archetype(1, "n")], both),
            _clusters("HDBSCAN", _run(2), [_archetype(1, "n")], both),
        ]
    )
    skipped_scores = harness.sink.store_anomalies(
        _run(2), [AnomalyScore(key(1), 0.1, False), AnomalyScore(key(2), -0.1, True)]
    )
    state = harness.read()
    assert (skipped_clusters, skipped_scores) == (1, 1)
    assert state.assignments == {("KMEANS", key(1), 1), ("HDBSCAN", key(1), 1)}
    assert state.anomalies == {(key(1), False)}


SINK_CASES = [sink_case_a_run_replaces_the_previous_one, sink_case_an_erased_project_is_not_written]
