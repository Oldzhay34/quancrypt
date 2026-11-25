"""The Ollama zero-shot adapter (stand-in server), the MLflow registry (a file store) and the Model A configuration."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from quancrypt_ml.infrastructure.llm.ollama_zero_shot import OllamaZeroShotClassifier, finding_text, parse
from quancrypt_ml.infrastructure.llm.prompts import PROMPT_VERSION, SYSTEM
from quancrypt_ml.infrastructure.registry.mlflow_registry import MlflowModelRegistry
from quancrypt_ml.infrastructure.settings import ConfigError, load_risk
from quancrypt_ml.port.outbound.risk import RunRecord, ZeroShotUnavailableError
from tests.support.risk_rows import synthetic_rows

ROW = synthetic_rows(1)[0]


def test_the_classifier_asks_with_the_fixed_prompt_temperature_zero_and_reads_tokens() -> None:
    seen: list[dict[str, object]] = []

    def answer(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content))
        return httpx.Response(200, json={"message": {"content": " high.\n"}, "prompt_eval_count": 210, "eval_count": 3})

    classifier = OllamaZeroShotClassifier("http://127.0.0.1:11434", "gemma3:4b", transport=httpx.MockTransport(answer))
    result = classifier.classify(ROW)
    assert (result.label, result.prompt_tokens, result.output_tokens) == ("HIGH", 210, 3)
    body = seen[0]
    assert body["model"] == "gemma3:4b" and body["stream"] is False
    assert body["options"] == {"temperature": 0, "seed": 42, "num_predict": 8}
    assert body["messages"] == [{"role": "system", "content": SYSTEM}, {"role": "user", "content": finding_text(ROW)}]
    assert classifier.prompt_version == PROMPT_VERSION


def test_only_one_of_the_four_class_words_is_an_answer() -> None:
    assert parse("LOW") == "LOW" and parse(" critical. ") == "CRITICAL"
    assert parse("HIGH because TLS") is None and parse("") is None and parse("SEVERE") is None


def test_an_unreachable_or_failing_llm_is_reported() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    for transport in (httpx.MockTransport(refuse), httpx.MockTransport(lambda r: httpx.Response(404, json={}))):
        with pytest.raises(ZeroShotUnavailableError):
            OllamaZeroShotClassifier("http://127.0.0.1:11434", "gemma3:4b", transport=transport).classify(ROW)


def test_the_registry_logs_a_run_with_params_metrics_tags_and_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mlflow.tracking import MlflowClient

    # A file store keeps the test inside tmp_path (MLflow 3 asks for this opt-in; the real server uses PostgreSQL).
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    uri = (tmp_path / "mlruns").as_uri()
    artifact = tmp_path / "calibration.png"
    artifact.write_bytes(b"png")
    registry = MlflowModelRegistry(uri)
    parent = registry.log_run(
        "model_a_risk",
        RunRecord("risk_model-v1", {"C": 1.0}, {"macro_f1": 0.8}, {"label_source": "SILVER"}, [artifact]),
    )
    child = registry.log_run("model_a_risk", RunRecord("cv-X", {}, {"m": 1.0}, {}, []), parent_run_id=parent)
    client = MlflowClient(tracking_uri=uri)
    run = client.get_run(parent)
    assert run.data.params == {"C": "1.0"} and run.data.metrics == {"macro_f1": 0.8}
    assert run.data.tags["label_source"] == "SILVER" and run.info.status == "FINISHED"
    assert [a.path for a in client.list_artifacts(parent)] == ["calibration.png"]
    assert client.get_run(child).data.tags["mlflow.parentRunId"] == parent


def test_the_risk_configuration_allows_loopback_only() -> None:
    settings = load_risk({})
    assert (settings.mlflow_uri, settings.ollama_url, settings.ollama_model) == (
        "http://127.0.0.1:5000", "http://127.0.0.1:11434", "gemma3:4b",
    )  # fmt: skip
    for key, value in (("MLFLOW_TRACKING_URI", "http://mlflow:5000"), ("OLLAMA_BASE_URL", "https://127.0.0.1:11434"),
                       ("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000/api"), ("ML_ZERO_SHOT_MODEL", "gemma 3")):  # fmt: skip
        with pytest.raises(ConfigError):
            load_risk({key: value})
