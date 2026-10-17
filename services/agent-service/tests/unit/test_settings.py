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
    # Budgets (D-248): step, token and time per agent.
    assert {
        name: (agent.budget.max_steps, agent.budget.max_tokens, agent.budget.timeout_s)
        for name, agent in settings.agents.agents.items()
    } == {
        "supervisor": (6, 2048, 120),
        "discovery": (40, 8192, 420),
        "topology": (8, 0, 360),
        "planner": (40, 16384, 300),
    }
    assert settings.agents.discovery.uncertain_below == 0.6  # D-248a
    assert settings.agents.discovery.llm_confidence == 0.5  # D-248g
    # The approved allow-lists (D-238a), exactly and in order.
    assert {name: agent.tools for name, agent in settings.agents.agents.items()} == {
        "supervisor": (),
        "discovery": (
            "analyze_crypto",
            "get_snippet",
            "start_scan",
            "record_findings",
            "record_scan_artifact",
            "complete_scan",
        ),
        "topology": ("build_topology", "record_topology", "list_findings"),
        "planner": (
            "list_findings",
            "get_topology",
            "get_project_profile",
            "save_clarification_answers",
            "score_findings",
            "create_plan",
            "get_plan",
            "get_plan_report",
            "kb_search",
            "get_snippet",
        ),
    }
    assert settings.agents.services.core.base_url == "http://127.0.0.1:8081"
    assert settings.agents.services.analyzer.base_url == "http://127.0.0.1:8082"
    assert settings.agents.output_check.on_mismatch == "flag"
    assert settings.agents.guardrails.rings == ("rule_filter", "scope_classifier", "llm_self_check")
    assert settings.agents.guardrails.topic_threshold == 0.40  # D-246
    assert settings.agents.guardrails.max_request_chars == 4000  # D-242a
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
        ("agent_config.yaml", "max_request_chars: 4000", "max_request_chars: 50", "max_request_chars"),
        (
            "agent_config.yaml",
            "rings: [rule_filter, scope_classifier, llm_self_check]",
            "rings: [rule_filter, oracle]",
            "rings",
        ),
        (
            "agent_config.yaml",
            "rings: [rule_filter, scope_classifier, llm_self_check]",
            "rings: [rule_filter, rule_filter]",
            "rings",
        ),
        ("agent_config.yaml", "rings: [rule_filter, scope_classifier, llm_self_check]", "rings: []", "rings"),
        ("agent_config.yaml", "topic_threshold: 0.40", "topic_threshold: 1.5", "topic_threshold"),
        ("agent_config.yaml", "self_check_max_tokens: 8", "self_check_max_tokens: 8\n  surprise: 1", "surprise"),
        ("agent_config.yaml", "      - jailbreak\n", '      - ""\n', "jailbreak_phrases"),
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


GOOD_APP_URL = "postgresql+psycopg://agent_db_app@127.0.0.1:5432/agent_db"


@pytest.mark.parametrize(
    "url",
    [
        "postgresql+psycopg://agent_db_app@127.0.0.1:5432/agent_db?host=db.example.com",
        "postgresql+psycopg://agent_db_app@127.0.0.1:5432/agent_db?dbname=core_db",
        "postgresql+psycopg://agent_db_app@127.0.0.1:5432/agent_db?password=sneaky-password",
        "postgresql+psycopg://agent_db_app@127.0.0.1:5432/agent_db?sslmode=disable",
        "postgresql+psycopg://agent_db_app:inline-password@127.0.0.1:5432/agent_db",
        "postgresql+psycopg://agent_db_app@db.example.com:5432/agent_db",
        "postgresql+psycopg://agent_db_app@127.0.0.1:5432/core_db",
        "postgresql+psycopg://core_db_app@127.0.0.1:5432/agent_db",
        "postgresql://agent_db_app@127.0.0.1:5432/agent_db",
        "not a url",
    ],
)
def test_the_application_database_url_must_be_a_plain_local_agent_db_address(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("AGENT_DB_URL", url)

    with pytest.raises(ConfigError) as raised:
        load_settings()

    printed = str(raised.value)
    assert "sneaky-password" not in printed and "inline-password" not in printed


def test_the_migrator_url_must_connect_as_the_migrator_role(config_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AGENT_DB_MIGRATOR_URL", GOOD_APP_URL)

    with pytest.raises(ConfigError, match="migrator"):
        load_settings()


@pytest.mark.parametrize("password", ["short", "CHANGE_ME-and-more-characters", ""])
@pytest.mark.parametrize("variable", ["AGENT_DB_APP_PASSWORD", "AGENT_DB_MIGRATOR_PASSWORD"])
def test_a_placeholder_or_short_database_password_stops_the_service(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch, variable: str, password: str
) -> None:
    monkeypatch.setenv(variable, password)

    with pytest.raises(ConfigError) as raised:
        load_settings()

    assert password not in str(raised.value) or password == ""


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "postgres"])
def test_local_database_hosts_are_accepted(config_dir: Path, monkeypatch: pytest.MonkeyPatch, host: str) -> None:
    monkeypatch.setenv("AGENT_DB_URL", f"postgresql+psycopg://agent_db_app@{host}:5432/agent_db")

    assert load_settings().agents.memory.database.url.endswith("/agent_db")


@pytest.mark.parametrize(
    ("old", "new", "reason"),
    [
        ("max_messages: 12", "max_messages: 0", "max_messages"),
        ("token_budget: 3000", "token_budget: 0", "token_budget"),
        ("chars_per_token: 4", "chars_per_token: 0", "chars_per_token"),
        ("chunk_chars: 1200", "chunk_chars: 0", "chunk_chars"),
        ("chunk_overlap: 150", "chunk_overlap: 1200", "chunk_overlap"),
        ("top_k: 5", "top_k: 0", "top_k"),
        ("embed_batch: 16", "embed_batch: 0", "embed_batch"),
    ],
)
def test_an_invalid_memory_setting_is_rejected_with_its_key(config_dir: Path, old: str, new: str, reason: str) -> None:
    _replace(config_dir, "agent_config.yaml", old, new)

    with pytest.raises(ConfigError, match=reason):
        load_settings()


@pytest.mark.parametrize("variable", ["AGENT_DB_APP_PASSWORD", "AGENT_DB_MIGRATOR_PASSWORD"])
def test_a_missing_database_password_stops_the_service_and_names_only_the_variable(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.delenv(variable)

    with pytest.raises(ConfigError, match=variable):
        load_settings()


# ---- services (P4.3) ----


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com:8081",
        "http://10.0.0.5:8081",
        "http://user:secret-in-url@core-service:8081",
        "http://core-service:8081/api",
        "http://core-service:8081?x=1",
        "file:///etc/passwd",
    ],
)
@pytest.mark.parametrize("variable", ["CORE_SERVICE_URL", "ANALYZER_SERVICE_URL"])
def test_a_service_address_must_be_a_bare_local_origin(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch, variable: str, url: str
) -> None:
    monkeypatch.setenv(variable, url)

    with pytest.raises(ConfigError) as raised:
        load_settings()

    assert "secret-in-url" not in str(raised.value)


@pytest.mark.parametrize(
    ("variable", "host"), [("CORE_SERVICE_URL", "core-service"), ("ANALYZER_SERVICE_URL", "analyzer-service")]
)
def test_the_compose_service_names_are_accepted(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch, variable: str, host: str
) -> None:
    monkeypatch.setenv(variable, f"http://{host}:8080")

    services = load_settings().agents.services
    assert f"http://{host}:8080" in (services.core.base_url, services.analyzer.base_url)


@pytest.mark.parametrize(
    "token",
    [
        "short-token",
        "CHANGE_ME-CHANGE_ME-CHANGE_ME-CHANGE_ME",
        "has spaces in the middle of a long token value",
        "ç" * 40,
    ],
)
def test_a_placeholder_or_short_internal_token_stops_the_service(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch, token: str
) -> None:
    monkeypatch.setenv("INTERNAL_SERVICE_TOKEN", token)

    with pytest.raises(ConfigError, match="internal_token") as raised:
        load_settings()

    assert token not in str(raised.value)


def test_a_missing_internal_token_stops_the_service_and_names_only_the_variable(
    config_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("INTERNAL_SERVICE_TOKEN")

    with pytest.raises(ConfigError, match="INTERNAL_SERVICE_TOKEN"):
        load_settings()


def test_the_internal_token_is_never_printed(config_dir: Path) -> None:
    settings = load_settings()

    assert settings.agents.services.internal_token.get_secret_value() not in repr(settings)
