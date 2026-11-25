"""Model A ports: the fake and the real adapter pass the same cases (tests/support/risk_port_cases.py). The PostgreSQL
adapters of TrainingDataSource and ResultSink run the same cases in tests/integration/test_ml_outputs_postgres.py."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import httpx
import pytest

from quancrypt_ml.domain.risk_features import RiskRow
from quancrypt_ml.infrastructure.llm.ollama_zero_shot import OllamaZeroShotClassifier
from quancrypt_ml.infrastructure.model.analysis import MatplotlibCharts, ShapExplainer
from quancrypt_ml.infrastructure.model.onnx_exporter import SklearnOnnxExporter
from quancrypt_ml.infrastructure.model.trainer import SklearnModelTrainer
from quancrypt_ml.infrastructure.registry.mlflow_registry import MlflowModelRegistry
from quancrypt_ml.port.outbound.risk import Charts, ModelRegistry, ResultSink, TrainingDataSource, ZeroShotClassifier
from tests.support.risk_fakes import (
    FakeCharts,
    FakeData,
    FakeExplainer,
    FakeExporter,
    FakeRegistry,
    FakeSink,
    FakeTrainer,
    PriorityModel,
    ScriptedLLM,
)
from tests.support.risk_port_cases import (
    CHART_CASES,
    DATA_CASES,
    ERASURE_CASES,
    FAMILY_CASES,
    FAMILY_FILE_CASES,
    REGISTRY_CASES,
    SINK_CASES,
    ZERO_SHOT_CASES,
    DataFactory,
    ModelFamily,
    Reader,
    Warehouse,
    ZeroShotFactory,
)
from tests.support.risk_rows import synthetic_rows

FAMILIES = {
    "fake": lambda: ModelFamily(FakeTrainer(), FakeExplainer(), FakeExporter()),
    "sklearn": lambda: ModelFamily(SklearnModelTrainer(), ShapExplainer(), SklearnOnnxExporter()),
}


@pytest.mark.parametrize("family", FAMILIES, ids=str)
@pytest.mark.parametrize("case", FAMILY_CASES, ids=lambda c: c.__name__)
def test_model_families_keep_the_contract(case: Callable[[ModelFamily], None], family: str) -> None:
    case(FAMILIES[family]())


@pytest.mark.parametrize("family", FAMILIES, ids=str)
@pytest.mark.parametrize("case", FAMILY_FILE_CASES, ids=lambda c: c.__name__)
def test_model_families_keep_the_file_contract(
    case: Callable[[ModelFamily, Path], None], family: str, tmp_path: Path
) -> None:
    case(FAMILIES[family](), tmp_path)


@pytest.mark.parametrize("make", [FakeCharts, MatplotlibCharts], ids=["fake", "matplotlib"])
@pytest.mark.parametrize("case", CHART_CASES, ids=lambda c: c.__name__)
def test_charts_keep_the_contract(
    case: Callable[[Charts, Path], None], make: Callable[[], Charts], tmp_path: Path
) -> None:
    case(make(), tmp_path)


def _fake_llm(answer: str | None) -> ZeroShotClassifier:
    return ScriptedLLM(down=answer is None, answer=answer)


def _ollama(answer: str | None) -> ZeroShotClassifier:
    def respond(request: httpx.Request) -> httpx.Response:
        if answer is None:
            raise httpx.ConnectError("refused", request=request)
        return httpx.Response(200, json={"message": {"content": answer}, "prompt_eval_count": 200, "eval_count": 2})

    return OllamaZeroShotClassifier("http://127.0.0.1:11434", "gemma3:4b", transport=httpx.MockTransport(respond))


@pytest.mark.parametrize("make", [_fake_llm, _ollama], ids=["fake", "ollama"])
@pytest.mark.parametrize("case", ZERO_SHOT_CASES, ids=lambda c: c.__name__)
def test_zero_shot_classifiers_keep_the_contract(
    case: Callable[[ZeroShotFactory], None], make: ZeroShotFactory
) -> None:
    case(make)


@pytest.mark.parametrize("case", REGISTRY_CASES, ids=lambda c: c.__name__)
def test_registries_keep_the_contract(
    case: Callable[[ModelRegistry, Path], None], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    case(FakeRegistry(), tmp_path)
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")  # a file store keeps the test inside tmp_path
    case(MlflowModelRegistry((tmp_path / "mlruns").as_uri()), tmp_path)


@pytest.mark.parametrize("case", DATA_CASES, ids=lambda c: c.__name__)
def test_the_fake_training_data_keeps_the_contract(case: Callable[[DataFactory], None]) -> None:
    def factory(rows: Sequence[RiskRow]) -> TrainingDataSource:
        return FakeData(rows)

    case(factory)


@pytest.mark.parametrize("case", SINK_CASES, ids=lambda c: c.__name__)
def test_the_fake_sink_keeps_the_contract(case: Callable[[ResultSink, Reader], None]) -> None:
    sink = FakeSink()
    case(sink, sink.read)


@pytest.mark.parametrize("case", ERASURE_CASES, ids=lambda c: c.__name__)
def test_the_fake_sink_keeps_the_erasure_contract(case: Callable[[ResultSink, Reader, Warehouse], None]) -> None:
    sink = FakeSink()
    case(sink, sink.read, Warehouse(sink.present, sink.erase))


def test_the_real_explainer_and_exporter_refuse_a_model_of_another_family(tmp_path: Path) -> None:
    """The TrainedModel precondition (port/outbound/risk.py): a family reads only its own trainer's models."""
    foreign = PriorityModel("XGBOOST", {})
    rows = synthetic_rows(4, projects=2)
    with pytest.raises(TypeError):
        ShapExplainer().top_features(foreign, rows, 2)
    with pytest.raises(TypeError):
        SklearnOnnxExporter().export(foreign, rows, tmp_path / "m.onnx")
