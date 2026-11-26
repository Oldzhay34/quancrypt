"""Mining ports: the fake and the real adapter pass the same cases (tests/support/mining_port_cases.py). The PostgreSQL
data source and sink run them in tests/integration/test_mining_postgres.py."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from quancrypt_ml.domain.mining import ProjectLibraries, ProjectProfile
from quancrypt_ml.infrastructure.model.mining import MlxtendRuleMiner, SklearnAnomalyDetector, SklearnClusterer
from quancrypt_ml.infrastructure.model.mining_charts import MatplotlibMiningCharts
from quancrypt_ml.port.outbound.mining import AnomalyDetector, Clusterer, MiningCharts, RuleMiner
from tests.support.mining_fakes import (
    FakeAnomalyDetector,
    FakeClusterer,
    FakeMiningCharts,
    FakeMiningData,
    FakeMiningSink,
    FakeRuleMiner,
)
from tests.support.mining_port_cases import (
    CHART_CASES,
    CLUSTERER_CASES,
    DATA_CASES,
    DETECTOR_CASES,
    MINER_CASES,
    SINK_CASES,
    DataFactory,
    SinkHarness,
    SinkState,
)

CLUSTERERS: dict[str, Callable[[], Clusterer]] = {"fake": FakeClusterer, "sklearn": SklearnClusterer}
MINERS: dict[str, Callable[[], RuleMiner]] = {"fake": FakeRuleMiner, "mlxtend": MlxtendRuleMiner}
DETECTORS: dict[str, Callable[[], AnomalyDetector]] = {"fake": FakeAnomalyDetector, "sklearn": SklearnAnomalyDetector}
CHARTS: dict[str, Callable[[], MiningCharts]] = {"fake": FakeMiningCharts, "matplotlib": MatplotlibMiningCharts}


@pytest.mark.parametrize("case", DATA_CASES, ids=lambda c: c.__name__)
def test_the_fake_data_source_keeps_the_contract(case: Callable[[DataFactory], None]) -> None:
    def factory(profiles: list[ProjectProfile], usages: list[ProjectLibraries], count: int) -> FakeMiningData:
        return FakeMiningData(profiles, usages, count)

    case(factory)


@pytest.mark.parametrize("name", CLUSTERERS)
@pytest.mark.parametrize("case", CLUSTERER_CASES, ids=lambda c: c.__name__)
def test_clusterers_keep_the_contract(case: Callable[[Clusterer], None], name: str) -> None:
    case(CLUSTERERS[name]())


@pytest.mark.parametrize("name", MINERS)
@pytest.mark.parametrize("case", MINER_CASES, ids=lambda c: c.__name__)
def test_rule_miners_keep_the_contract(case: Callable[[RuleMiner], None], name: str) -> None:
    case(MINERS[name]())


@pytest.mark.parametrize("name", DETECTORS)
@pytest.mark.parametrize("case", DETECTOR_CASES, ids=lambda c: c.__name__)
def test_anomaly_detectors_keep_the_contract(case: Callable[[AnomalyDetector], None], name: str) -> None:
    case(DETECTORS[name]())


@pytest.mark.parametrize("name", CHARTS)
@pytest.mark.parametrize("case", CHART_CASES, ids=lambda c: c.__name__)
def test_mining_charts_keep_the_contract(case: Callable[[MiningCharts, Path], None], name: str, tmp_path: Path) -> None:
    case(CHARTS[name](), tmp_path)


def _fake_harness() -> SinkHarness:
    sink = FakeMiningSink()

    def read() -> SinkState:
        return SinkState(
            {t: r.project_count for t, r in sink.runs.items()},
            {(t, a.cluster_no, a.name) for t, found in sink.archetypes.items() for a in found},
            {(t, a.project_key, a.cluster_no) for t, found in sink.assignments.items() for a in found},
            [(r.antecedent, r.consequent) for r in sink.rules],
            {(s.project_key, s.is_flagged) for s in sink.anomalies},
        )

    def present(keys: list[str]) -> None:
        sink.present = set(keys)

    return SinkHarness(sink, read, present)  # type: ignore[arg-type]  # structurally the three sink ports


@pytest.mark.parametrize("case", SINK_CASES, ids=lambda c: c.__name__)
def test_the_fake_sink_keeps_the_contract(case: Callable[[SinkHarness], None]) -> None:
    case(_fake_harness())
