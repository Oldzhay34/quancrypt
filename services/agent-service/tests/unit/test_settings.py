"""Configuration validation (fail-fast): a broken configuration never produces settings."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from src.app.settings import CONFIG_DIR_ENV, AppSettings, ConfigError, load_settings

REAL_CONFIG = Path(__file__).resolve().parents[2] / "config"


@pytest.fixture
def config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "config"
    shutil.copytree(REAL_CONFIG, target)
    monkeypatch.setenv(CONFIG_DIR_ENV, str(target))
    for name in ("OLLAMA_BASE_URL", "LLM_PROVIDER", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)
    return target


def _replace(directory: Path, filename: str, old: str, new: str) -> None:
    path = directory / filename
    text = path.read_text(encoding="utf-8")
    assert old in text, f"{old!r} not in {filename}"
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_the_shipped_configuration_is_valid(config_dir: Path) -> None:
    settings = load_settings()

    assert settings.models.ollama.chat_model == "gemma3:4b"
    assert settings.models.ollama.embedding_model == "embeddinggemma:latest"
    assert settings.models.ollama.embedding_dimensions == 768
    assert settings.models.ollama.num_ctx == 8192
    assert settings.models.ollama.num_predict == 1024
    assert settings.models.onnx.risk_model_path is None
    assert {name: agent.budget.max_steps for name, agent in settings.agents.agents.items()} == {
        "supervisor": 6,
        "discovery": 8,
        "topology": 8,
        "planner": 10,
    }
    assert all(agent.tools == () for agent in settings.agents.agents.values())
    assert settings.agents.output_check.on_mismatch == "flag"
    assert settings.logging.format == "json"


def test_placeholders_use_the_environment_and_fall_back_to_the_default(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert load_settings().models.ollama.base_url == "http://127.0.0.1:11434"

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    settings = load_settings()

    assert settings.models.ollama.base_url == "http://host.docker.internal:11434"
    assert settings.logging.level == "DEBUG"


def test_a_placeholder_without_value_or_default_stops_the_load_and_names_only_the_variable(
    config_dir: Path,
) -> None:
    _replace(config_dir, "model_config.yaml", "${OLLAMA_BASE_URL:-http://127.0.0.1:11434}", "${NO_SUCH_VARIABLE}")

    with pytest.raises(ConfigError, match="NO_SUCH_VARIABLE"):
        load_settings()


@pytest.mark.parametrize(
    ("filename", "old", "new", "reason"),
    [
        ("model_config.yaml", "provider: ${LLM_PROVIDER:-ollama}", "provider: cloud", "models.llm.provider"),
        ("model_config.yaml", "num_predict: 1024", "num_predict: 9000", "num_predict"),
        ("model_config.yaml", "max_attempts: 3", "max_attempts: 0", "retry.max_attempts"),
        ("model_config.yaml", "wait_max_s: 4", "wait_max_s: 0.1", "wait_max_s"),
        ("model_config.yaml", "temperature: 0.2", "temperature: 5", "temperature"),
        ("model_config.yaml", "  chat_model: gemma3:4b", "  chat_model: gemma3:4b\n  surprise: 1", "surprise"),
        ("agent_config.yaml", "on_mismatch: flag", "on_mismatch: ignore", "on_mismatch"),
        ("agent_config.yaml", "guardrails: {}", "guardrails: {max_length: 4000}", "max_length"),
        ("agent_config.yaml", "max_steps: 6", "max_steps: 0", "max_steps"),
        ("agent_config.yaml", "  planner:", "  planer:", "agents"),
        (
            "agent_config.yaml",
            "    tools: []\n    budget:\n      max_steps: 6",
            "    tools: [a, a]\n    budget:\n      max_steps: 6",
            "tools",
        ),
        ("logging_config.yaml", "format: json", "format: text", "logging.format"),
        ("logging_config.yaml", "level: ${LOG_LEVEL:-INFO}", "level: LOUD", "logging.level"),
    ],
)
def test_an_invalid_value_is_rejected_with_its_key(
    config_dir: Path, filename: str, old: str, new: str, reason: str
) -> None:
    _replace(config_dir, filename, old, new)

    with pytest.raises(ConfigError, match=reason):
        load_settings()


@pytest.mark.parametrize(
    "url",
    [
        "https://api.example.com",
        "http://10.0.0.5:11434",
        "http://user:secret@127.0.0.1:11434",
        "http://127.0.0.1:11434/v1",
        "http://127.0.0.1:11434?x=1",
        "ftp://127.0.0.1:11434",
        "http://127.0.0.1:notaport",
        "127.0.0.1:11434",
        " http://127.0.0.1:11434",
        "http://127.0.0.1:11434	",
        "http://127.0.0.1:0",
        "http://host.docKer.internal:11434",
    ],
)
def test_the_ollama_address_must_be_a_bare_local_origin(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", url)

    with pytest.raises(ConfigError, match="base_url") as raised:
        load_settings()

    assert "secret" not in str(raised.value)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "[::1]", "host.docker.internal", "ollama"])
def test_local_hosts_are_accepted(config_dir: Path, monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    monkeypatch.setenv("OLLAMA_BASE_URL", f"http://{host}:11434")

    assert load_settings().models.ollama.base_url == f"http://{host}:11434"


def test_a_missing_file_stops_the_load(config_dir: Path) -> None:
    (config_dir / "logging_config.yaml").unlink()

    with pytest.raises(ConfigError, match="logging_config.yaml"):
        load_settings()


def test_invalid_yaml_stops_the_load(config_dir: Path) -> None:
    (config_dir / "agent_config.yaml").write_text("agents: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigError, match="not valid YAML"):
        load_settings()


def test_settings_are_immutable(config_dir: Path) -> None:
    settings = load_settings()

    assert isinstance(settings, AppSettings)
    with pytest.raises(ValueError, match="frozen"):
        settings.logging = settings.logging


def test_a_rejected_secret_never_reaches_the_traceback(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import traceback

    monkeypatch.setenv("OLLAMA_BASE_URL", "http://admin:S3cretPass@evil.example:11434")

    with pytest.raises(ConfigError) as raised:
        load_settings()

    # The whole chain, as a process crash would print it: ValidationError inputs must not be chained in.
    printed = "".join(traceback.format_exception(raised.value))
    assert "S3cretPass" not in printed
    assert raised.value.__cause__ is None
