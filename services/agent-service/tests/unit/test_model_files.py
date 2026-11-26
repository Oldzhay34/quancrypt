"""The shipped model configuration (P7.5, D-343a, D-344b): onnx by default, and a missing or foreign model file stops
the service; nothing falls back to the baseline on its own."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.app import container
from src.app.settings import CONFIG_DIR_ENV, AppSettings, ConfigError, load_settings
from src.llm.null_provider import NullProvider

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def settings_for(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> AppSettings:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(ROOT / "config"))
    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.delenv("RISK_MODEL", raising=False)
    monkeypatch.delenv("GUARD_SCOPE_CLASSIFIER", raising=False)
    return load_settings()


def test_the_shipped_default_is_model_a_and_model_b(settings_for: AppSettings) -> None:
    assert settings_for.models.risk_model == "onnx"
    assert settings_for.agents.guardrails.scope_classifier == "onnx"


def test_a_missing_model_file_stops_the_service(settings_for: AppSettings) -> None:
    with pytest.raises(ConfigError, match="risk_model_file") as error:
        container.build_risk_model(settings_for.models)
    assert str(settings_for.models.onnx.models_dir) not in str(error.value)
    with pytest.raises(ConfigError, match="scope_model_file"):
        container.build_scope_ring(settings_for, NullProvider(), lambda: None)


def _risk_files(tmp_path: Path, settings: AppSettings, sha256: str | None = None) -> None:
    model = tmp_path / settings.models.onnx.risk_model_file
    model.write_bytes(b"not a model")
    parity = model.with_name(model.name.removesuffix(".onnx") + ".parity.json")
    parity.write_text(json.dumps({"onnx_sha256": sha256 or hashlib.sha256(b"not a model").hexdigest()}), "utf-8")


def test_a_file_that_is_not_an_onnx_model_stops_the_service(settings_for: AppSettings, tmp_path: Path) -> None:
    _risk_files(tmp_path, settings_for)
    with pytest.raises(ConfigError, match="not Model A"):
        container.build_risk_model(settings_for.models)


def test_model_a_without_its_parity_file_stops_the_service(settings_for: AppSettings, tmp_path: Path) -> None:
    # ml writes the parity set only after the parity check passed (D-346c): no parity file, no model.
    (tmp_path / settings_for.models.onnx.risk_model_file).write_bytes(b"not a model")
    with pytest.raises(ConfigError, match="risk_model_file"):
        container.build_risk_model(settings_for.models)


def test_model_a_whose_parity_file_names_another_file_stops_the_service(
    settings_for: AppSettings, tmp_path: Path
) -> None:
    _risk_files(tmp_path, settings_for, sha256="0" * 64)
    with pytest.raises(ConfigError, match="SHA-256"):
        container.build_risk_model(settings_for.models)


def _scope_files(tmp_path: Path, settings: AppSettings, **changes: object) -> None:
    onnx = settings.models.onnx
    model = tmp_path / onnx.scope_model_file
    model.write_bytes(b"not a model")
    thresholds = {
        "onnx": onnx.scope_model_file, "onnx_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "positive_class": "OUT_OF_SCOPE", "unsure_low": 0.03, "unsure_high": 0.43,
        "embedding_model": settings.models.ollama.embedding_model, "embedding_digest": "a" * 64,
        "input_dimensions": settings.models.ollama.embedding_dimensions,
    }  # fmt: skip
    thresholds.update(changes)
    (tmp_path / onnx.scope_thresholds_file).write_text(json.dumps(thresholds), encoding="utf-8")


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"onnx_sha256": "0" * 64}, "SHA-256"),
        ({"onnx": "other.onnx"}, "SHA-256"),
        ({"embedding_model": "bge-m3:latest"}, "another embedding model"),
        ({"input_dimensions": 1024}, "another embedding model"),
        ({"embedding_digest": "sha256:" + "a" * 64}, "64 hex digits"),
        ({"embedding_digest": None}, "64 hex digits"),
        ({}, "not Model B"),  # the files agree, but the model file is not an ONNX head
    ],
)
def test_a_thresholds_file_that_does_not_describe_the_model_stops_the_service(
    settings_for: AppSettings, tmp_path: Path, changes: dict[str, object], message: str
) -> None:
    _scope_files(tmp_path, settings_for, **changes)
    with pytest.raises(ConfigError, match=message):
        container.build_scope_ring(settings_for, NullProvider(), lambda: None)


def test_the_baselines_need_no_model_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(ROOT / "config"))
    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    monkeypatch.setenv("RISK_MODEL", "rule_baseline")
    monkeypatch.setenv("GUARD_SCOPE_CLASSIFIER", "topic_gate")
    settings = load_settings()
    assert container.build_risk_model(settings.models).model_id == "rule_baseline_v1"
    assert container.build_scope_ring(settings, NullProvider(), lambda: None)().name == "SCOPE_CLASSIFIER"


def test_an_unknown_choice_is_refused(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(ROOT / "config"))
    monkeypatch.setenv("RISK_MODEL", "xgboost")
    with pytest.raises(ConfigError, match="risk_model"):
        load_settings()
