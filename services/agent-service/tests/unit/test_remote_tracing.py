"""LangGraph brings the LangSmith client; building the container forces its tracing off so nothing leaves the machine
(guardrails-security section 1, P4.6)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from src.app.settings import CONFIG_DIR_ENV, load_settings
from tests.support.containers import inert_container

CONFIG = Path(__file__).resolve().parents[2] / "config"


def test_building_the_container_switches_remote_tracing_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(CONFIG_DIR_ENV, str(CONFIG))
    monkeypatch.setenv("LLM_PROVIDER", "null")
    for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING"):
        monkeypatch.setenv(name, "true")

    container = inert_container(load_settings())
    try:
        assert all(
            os.environ[name] == "false" for name in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2", "LANGCHAIN_TRACING")
        )
    finally:
        container.close()
