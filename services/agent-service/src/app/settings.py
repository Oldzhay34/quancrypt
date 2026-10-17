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
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

CONFIG_DIR_ENV = "QUANCRYPT_CONFIG_DIR"
DEFAULT_CONFIG_DIR = "config"

# Phase 1 is local (guardrails-security section 1): the model server is on this machine or is the compose service
# `ollama`.
LOCAL_OLLAMA_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "host.docker.internal", "ollama"})

# agent_db lives on this machine or is the compose service `postgres` (D-09; phase 1 is local).
LOCAL_DB_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "postgres"})
AGENT_DB_NAME = "agent_db"
AGENT_DB_APP_ROLE = "agent_db_app"
AGENT_DB_MIGRATOR_ROLE = "agent_db_migrator"

AGENT_NAMES = ("supervisor", "discovery", "topology", "planner")
# The internal services the tools may call (P4.3, D-239): their compose names and this machine.
LOCAL_SERVICE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1", "core-service", "analyzer-service"})

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def bare_local_origin(value: str, hosts: frozenset[str]) -> str:
    """A bare http(s) origin on one of the allowed local hosts (phase 1 is local, guardrails-security section 1).

    The clients (httpx) parse the address the same way, so what is checked here is what is called.
    """
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
    if url.host not in hosts:
        raise ValueError(f"base_url host must be one of: {', '.join(sorted(hosts))} (phase 1 is local)")
    return str(url).rstrip("/")


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


class LanguageWords(_Strict):
    """Phrase lists per language; both languages apply to every request (a request may mix them)."""

    tr: tuple[str, ...] = Field(min_length=1, max_length=500)
    en: tuple[str, ...] = Field(min_length=1, max_length=500)

    @field_validator("tr", "en")
    @classmethod
    def _plain_phrases(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for phrase in value:
            if not phrase.strip() or len(phrase) > 100 or not phrase.isprintable():
                raise ValueError("a phrase is 1 to 100 characters on one line")
        return value


class LanguageDetection(_Strict):
    tr_words: tuple[str, ...] = Field(min_length=1, max_length=500)
    en_words: tuple[str, ...] = Field(min_length=1, max_length=500)


class GuardrailsSettings(_Strict):
    """The scope keeper (P4.4, D-242): ring order, the rule filter's lists and the language rule."""

    rings: tuple[Literal["rule_filter", "scope_classifier", "llm_self_check"], ...] = Field(min_length=1)
    max_request_chars: int = Field(ge=100, le=100_000)
    self_check_max_tokens: int = Field(ge=1, le=64)
    # Interim ring 2 (D-246): in-scope anchor sentences and the cosine similarity a request must reach to pass.
    topic_anchors: LanguageWords
    topic_threshold: float = Field(ge=0, le=1)
    jailbreak_phrases: LanguageWords
    out_of_scope_keywords: LanguageWords
    in_scope_keywords: LanguageWords
    language: LanguageDetection

    @field_validator("rings")
    @classmethod
    def _distinct(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            raise ValueError("a ring is listed twice")
        return value


class OutputCheckSettings(_Strict):
    on_mismatch: Literal["strip", "flag"]


class HistorySettings(_Strict):
    """Short-term memory: the last N messages, then trimmed to a token budget (D-231c)."""

    max_messages: int = Field(ge=1, le=200)
    token_budget: int = Field(ge=100, le=100_000)
    # An ESTIMATE, not a measurement: Ollama reports the token count of a whole request, not of one message. The real
    # ratio
    # differs by language and model (unsourced assumption, D-231c).
    chars_per_token: float = Field(gt=0, le=16)


class KnowledgeBaseSettings(_Strict):
    """Chunking of `data/raw` notes and default search size. The embedding model reads at most 2048 tokens (D-217)."""

    chunk_chars: int = Field(ge=200, le=8000)
    chunk_overlap: int = Field(ge=0)
    top_k: int = Field(ge=1, le=50)
    embed_batch: int = Field(ge=1, le=256)

    @model_validator(mode="after")
    def _overlap_below_chunk(self) -> KnowledgeBaseSettings:
        if self.chunk_overlap >= self.chunk_chars:
            raise ValueError("chunk_overlap must be smaller than chunk_chars")
        return self


class DatabaseSettings(_Strict):
    """agent_db connection (D-09). The application role does DML only; migrations run as the migrator role."""

    url: str
    migrator_url: str
    app_password: SecretStr
    migrator_password: SecretStr
    pool_size: int = Field(ge=1, le=50)
    connect_timeout_s: int = Field(ge=1, le=60)

    @field_validator("url", "migrator_url")
    @classmethod
    def _agent_db_url(cls, value: str) -> str:
        try:
            url = make_url(value)
        except ArgumentError as exc:
            raise ValueError("the database URL is not valid") from exc
        if url.drivername != "postgresql+psycopg":
            raise ValueError("the database URL must use the driver postgresql+psycopg")
        if url.password is not None:
            raise ValueError("the database URL must not carry a password (it comes from its own setting)")
        if url.host not in LOCAL_DB_HOSTS:
            raise ValueError(
                f"the database host must be one of: {', '.join(sorted(LOCAL_DB_HOSTS))} (phase 1 is local)"
            )
        if url.database != AGENT_DB_NAME:
            raise ValueError(f"the database must be {AGENT_DB_NAME} (a service uses only its own database, D-09)")
        if url.query:
            # The driver applies query options on top of the checked fields (host, dbname, user, password).
            raise ValueError("the database URL must not carry query options")
        return value

    @model_validator(mode="after")
    def _roles(self) -> DatabaseSettings:
        if make_url(self.url).username != AGENT_DB_APP_ROLE:
            raise ValueError(f"url must connect as {AGENT_DB_APP_ROLE}")
        if make_url(self.migrator_url).username != AGENT_DB_MIGRATOR_ROLE:
            raise ValueError(f"migrator_url must connect as {AGENT_DB_MIGRATOR_ROLE}")
        for secret in (self.app_password, self.migrator_password):
            if len(secret.get_secret_value()) < 8 or "CHANGE_ME" in secret.get_secret_value():
                raise ValueError("database passwords must be real values (at least 8 characters, no CHANGE_ME)")
        return self


class MemorySettings(_Strict):
    history: HistorySettings
    knowledge_base: KnowledgeBaseSettings
    database: DatabaseSettings


class ServiceSettings(_Strict):
    """One internal service the tools call (core-service, analyzer-service)."""

    base_url: str
    connect_timeout_s: float = Field(gt=0, le=60)
    timeout_s: float = Field(gt=0, le=3600)
    retry: RetrySettings
    circuit_breaker: CircuitBreakerSettings

    @field_validator("base_url")
    @classmethod
    def _local_service_url(cls, value: str) -> str:
        return bare_local_origin(value, LOCAL_SERVICE_HOSTS)


class ServicesSettings(_Strict):
    """The tools' peers (P4.3): contracts directory, the internal service token and the two services."""

    contracts_dir: str = Field(min_length=1)
    internal_token: SecretStr
    core: ServiceSettings
    analyzer: ServiceSettings

    @field_validator("internal_token")
    @classmethod
    def _real_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value()
        if len(token) < 32 or "CHANGE_ME" in token or not token.isascii() or any(ch.isspace() for ch in token):
            raise ValueError("internal_token must be a real token (at least 32 characters, no CHANGE_ME, no spaces)")
        return value


class AgentsConfig(_Strict):
    agents: dict[str, AgentSettings]
    guardrails: GuardrailsSettings
    output_check: OutputCheckSettings
    memory: MemorySettings
    services: ServicesSettings

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
        return bare_local_origin(value, LOCAL_OLLAMA_HOSTS)

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
