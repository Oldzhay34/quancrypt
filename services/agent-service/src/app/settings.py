"""Configuration models and loader (D-221): the three YAML files in `config/` become one validated `AppSettings`.

`${NAME}` and `${NAME:-default}` inside a YAML string are expanded from the environment; a name with neither a value
nor a default is a
validation error, so a service with a broken configuration never starts (fail-fast). The directory comes from
`QUANCRYPT_CONFIG_DIR`
(default `config`). Environment variables do not override single keys: only the explicit `${...}` placeholders read
them.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

import httpx
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

CONFIG_DIR_ENV = "QUANCRYPT_CONFIG_DIR"
DEFAULT_CONFIG_DIR = "config"

# Phase 1 is local (guardrails-security section 1): the model server is on this machine or is the compose service
# `ollama`.
LOCAL_OLLAMA_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"})

AGENT_NAMES = ("supervisor", "discovery", "topology", "planner")

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


class ConfigError(Exception):
    """The configuration cannot be loaded or is invalid. The message never contains a configuration value."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


# ---- agent_config.yaml ----


class Budget(_Strict):
    max_steps: int = Field(ge=1, le=100)
    # 0 means the agent never calls the language model (discovery and topology).
    max_tokens: int = Field(ge=0, le=131072)
    timeout_s: int = Field(ge=1, le=3600)


class AgentSettings(_Strict):
    # Allow-list of tool names; empty until P4.3.
    tools: tuple[str, ...] = ()
    budget: Budget

    @field_validator("tools")
    @classmethod
    def _unique_tools(cls, tools: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(tools)) != len(tools):
            raise ValueError("tools must not repeat a name")
        return tools


class GuardrailsSettings(_Strict):
    """Filled by P4.4; any key is rejected until then."""


class OutputCheckSettings(_Strict):
    on_mismatch: Literal["strip", "flag"]


class AgentsConfig(_Strict):
    agents: dict[str, AgentSettings]
    guardrails: GuardrailsSettings
    output_check: OutputCheckSettings

    @model_validator(mode="after")
    def _known_agents(self) -> AgentsConfig:
        if set(self.agents) != set(AGENT_NAMES):
            raise ValueError(f"agents must be exactly {', '.join(AGENT_NAMES)}")
        return self


# ---- model_config.yaml ----


class LLMSettings(_Strict):
    provider: Literal["ollama", "null"]


class RetrySettings(_Strict):
    max_attempts: int = Field(ge=1, le=10)
    wait_initial_s: float = Field(gt=0, le=60)
    wait_max_s: float = Field(gt=0, le=300)

    @model_validator(mode="after")
    def _ordered(self) -> RetrySettings:
        if self.wait_max_s < self.wait_initial_s:
            raise ValueError("wait_max_s must not be smaller than wait_initial_s")
        return self


class CircuitBreakerSettings(_Strict):
    fail_max: int = Field(ge=1, le=100)
    reset_timeout_s: int = Field(ge=1, le=3600)


class OllamaSettings(_Strict):
    base_url: str
    chat_model: str = Field(min_length=1, max_length=128)
    embedding_model: str = Field(min_length=1, max_length=128)
    embedding_dimensions: int = Field(ge=1, le=8192)
    temperature: float = Field(ge=0, le=2)
    num_ctx: int = Field(ge=512, le=131072)
    num_predict: int = Field(ge=1, le=131072)
    connect_timeout_s: float = Field(gt=0, le=60)
    timeout_s: float = Field(gt=0, le=3600)
    retry: RetrySettings
    circuit_breaker: CircuitBreakerSettings
    health_timeout_s: float = Field(gt=0, le=60)
    health_cache_s: float = Field(ge=0, le=300)

    @field_validator("base_url")
    @classmethod
    def _local_http_url(cls, value: str) -> str:
        # The client (httpx) parses the address the same way, so what is checked here is what is called.
        if not value.isascii() or any(ch.isspace() or ord(ch) < 0x20 or ord(ch) == 0x7F for ch in value):
            raise ValueError("base_url must be plain ASCII without spaces or control characters")
        try:
            url = httpx.URL(value)
        except httpx.InvalidURL as exc:
            raise ValueError("base_url is not a valid URL") from exc
        if url.scheme not in ("http", "https") or not url.host:
            raise ValueError("base_url must be an http or https URL with a host")
        if url.userinfo or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("base_url must be a bare origin without credentials, path, query or fragment")
        if url.port is not None and not 1 <= url.port <= 65535:
            raise ValueError("base_url port must be between 1 and 65535")
        if url.host not in LOCAL_OLLAMA_HOSTS:
            raise ValueError(
                f"base_url host must be one of: {', '.join(sorted(LOCAL_OLLAMA_HOSTS))} (phase 1 is local)"
            )
        return str(url).rstrip("/")

    @model_validator(mode="after")
    def _output_fits_context(self) -> OllamaSettings:
        if self.num_predict > self.num_ctx:
            raise ValueError("num_predict must not exceed num_ctx")
        return self


class OnnxSettings(_Strict):
    risk_model_path: str | None
    scope_model_path: str | None


class ModelsConfig(_Strict):
    llm: LLMSettings
    ollama: OllamaSettings
    onnx: OnnxSettings


# ---- logging_config.yaml ----


class LoggingSettings(_Strict):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"]
    format: Literal["json"]
    service: str = Field(pattern=r"^[a-z][a-z0-9-]{0,63}$")


# ---- the whole configuration ----


class _YamlDirectorySource(PydanticBaseSettingsSource):
    """Reads the three files of the configuration directory, expands `${...}` and returns one dictionary."""

    def __init__(self, settings_cls: type[BaseSettings], environ: Mapping[str, str]) -> None:
        super().__init__(settings_cls)
        self._environ = environ

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        return None, field_name, False  # the whole dictionary comes from __call__

    def __call__(self) -> dict[str, Any]:
        directory = Path(self._environ.get(CONFIG_DIR_ENV, DEFAULT_CONFIG_DIR))
        unresolved: set[str] = set()
        data = {
            "agents": _load(directory / "agent_config.yaml", self._environ, unresolved),
            "models": _load(directory / "model_config.yaml", self._environ, unresolved),
            "logging": _load(directory / "logging_config.yaml", self._environ, unresolved),
        }
        if unresolved:
            raise ConfigError("Unresolved environment variables in the configuration: " + ", ".join(sorted(unresolved)))
        return data


class AppSettings(BaseSettings):
    model_config = {"extra": "forbid", "frozen": True, "hide_input_in_errors": True}

    agents: AgentsConfig
    models: ModelsConfig
    logging: LoggingSettings

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # Explicit keyword arguments (tests) first, then the YAML files; the environment is read only through `${...}`.
        return init_settings, _YamlDirectorySource(settings_cls, os.environ)


def load_settings() -> AppSettings:
    """Load and validate the configuration. Raises `ConfigError`; the message lists keys and reasons, never values."""
    try:
        return AppSettings()  # type: ignore[call-arg]
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors(include_input=False)
        )
        # `from None`: the chained ValidationError carries the offending input values, and a traceback would print them.
        raise ConfigError(f"Invalid configuration: {problems}") from None


def _load(path: Path, environ: Mapping[str, str], unresolved: set[str]) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except OSError:
        raise ConfigError(f"Cannot read the configuration file {path.name}.") from None
    except yaml.YAMLError:
        raise ConfigError(f"The configuration file {path.name} is not valid YAML.") from None
    return _expand(raw, environ, unresolved)


def _expand(node: Any, environ: Mapping[str, str], unresolved: set[str]) -> Any:
    if isinstance(node, str):
        return _PLACEHOLDER.sub(lambda match: _substitute(match, environ, unresolved), node)
    if isinstance(node, dict):
        return {key: _expand(value, environ, unresolved) for key, value in node.items()}
    if isinstance(node, list):
        return [_expand(item, environ, unresolved) for item in node]
    return node


def _substitute(match: re.Match[str], environ: Mapping[str, str], unresolved: set[str]) -> str:
    name, default = match.group(1), match.group(2)
    value = environ.get(name)
    if value:
        return value
    if default is not None:
        return default
    unresolved.add(name)
    return ""
