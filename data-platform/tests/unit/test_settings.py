from __future__ import annotations

from pathlib import Path

import pytest

from quancrypt_data.infrastructure.settings import ConfigError, load_settings

SECRET = "s3cret-value-that-must-never-show-up"


def good_env(**overrides: str) -> dict[str, str]:
    env = {
        "WAREHOUSE_DB_URL": "postgresql+psycopg://warehouse_db_app@postgres:5432/warehouse_db",
        "WAREHOUSE_DB_MIGRATOR_URL": "postgresql+psycopg://warehouse_db_migrator@postgres:5432/warehouse_db",
        "WAREHOUSE_DB_APP_PASSWORD": "app-password",
        "WAREHOUSE_DB_MIGRATOR_PASSWORD": "migrator-password",
        "INTERNAL_SERVICE_TOKEN": "t" * 40,
    }
    env.update(overrides)
    return env


def test_a_valid_environment_loads_with_the_defaults() -> None:
    settings = load_settings(good_env())

    assert settings.log_level == "INFO"
    assert settings.schemas_dir.name == "events"
    assert settings.migrations_dir.name == "migrations"
    assert SECRET not in repr(settings)
    assert "app-password" not in repr(settings)
    assert "t" * 40 not in repr(settings)


def test_the_paths_can_be_overridden(tmp_path: Path) -> None:
    settings = load_settings(good_env(EVENT_SCHEMAS_DIR=str(tmp_path), MIGRATIONS_DIR=str(tmp_path), LOG_LEVEL="DEBUG"))

    assert settings.schemas_dir == tmp_path
    assert settings.log_level == "DEBUG"


@pytest.mark.parametrize(
    ("name", "value", "fragment"),
    [
        ("WAREHOUSE_DB_URL", "", "WAREHOUSE_DB_URL"),
        (
            "WAREHOUSE_DB_URL",
            "postgresql+psycopg://warehouse_db_app@evil.example.com:5432/warehouse_db",
            "the host must be",
        ),
        (
            "WAREHOUSE_DB_URL",
            "postgresql+psycopg://warehouse_db_app@postgres:5432/core_db",
            "the database must be warehouse_db",
        ),
        (
            "WAREHOUSE_DB_URL",
            "postgresql+psycopg://postgres@postgres:5432/warehouse_db",
            "the role must be warehouse_db_app",
        ),
        (
            "WAREHOUSE_DB_URL",
            "postgresql+psycopg://warehouse_db_app:pw@postgres:5432/warehouse_db",
            "must not carry the password",
        ),
        (
            "WAREHOUSE_DB_URL",
            "postgresql+psycopg://warehouse_db_app@postgres:5432/warehouse_db?host=evil",
            "query string",
        ),
        ("WAREHOUSE_DB_URL", "postgresql://warehouse_db_app@postgres:5432/warehouse_db", "driver"),
        (
            "WAREHOUSE_DB_MIGRATOR_URL",
            "postgresql+psycopg://warehouse_db_app@postgres:5432/warehouse_db",
            "the role must be warehouse_db_migrator",
        ),
        ("WAREHOUSE_DB_APP_PASSWORD", "", "WAREHOUSE_DB_APP_PASSWORD"),
        ("WAREHOUSE_DB_MIGRATOR_PASSWORD", "CHANGE_ME", "WAREHOUSE_DB_MIGRATOR_PASSWORD"),
        ("INTERNAL_SERVICE_TOKEN", "short", "INTERNAL_SERVICE_TOKEN"),
        ("INTERNAL_SERVICE_TOKEN", "CHANGE_ME" + "x" * 40, "INTERNAL_SERVICE_TOKEN"),
        ("INTERNAL_SERVICE_TOKEN", "é" * 40, "INTERNAL_SERVICE_TOKEN"),
        ("INTERNAL_SERVICE_TOKEN", " " + "t" * 40, "INTERNAL_SERVICE_TOKEN"),
        ("INTERNAL_SERVICE_TOKEN", "t" * 40 + " ", "INTERNAL_SERVICE_TOKEN"),
        ("LOG_LEVEL", "TRACE", "LOG_LEVEL"),
    ],
)
def test_an_invalid_value_stops_the_start_and_names_the_key_only(name: str, value: str, fragment: str) -> None:
    with pytest.raises(ConfigError, match=fragment) as caught:
        load_settings(good_env(**{name: value}))

    # The message names keys and reasons; it never repeats a configured value.
    assert "app-password" not in str(caught.value)
    assert "migrator-password" not in str(caught.value)


def test_every_problem_is_reported_at_once() -> None:
    with pytest.raises(ConfigError) as caught:
        load_settings({})

    for name in (
        "WAREHOUSE_DB_URL",
        "WAREHOUSE_DB_MIGRATOR_URL",
        "WAREHOUSE_DB_APP_PASSWORD",
        "INTERNAL_SERVICE_TOKEN",
    ):
        assert name in str(caught.value)
