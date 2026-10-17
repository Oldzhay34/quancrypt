"""Containers for tests that need the application but neither a database nor migrations."""

from __future__ import annotations

from src.app.container import Container, build_container
from src.app.settings import AppSettings


def _no_startup() -> None:
    return None


def inert_container(settings: AppSettings) -> Container:
    """The real container with its startup (migrations) and readiness checks switched off: nothing connects to
    agent_db."""
    container = build_container(settings)
    container.startup = _no_startup
    container.readiness_checks = ()
    return container
