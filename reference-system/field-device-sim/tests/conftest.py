"""Shared fixtures: one real Mosquitto broker for the whole test session (started on first use)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from support.mosquitto import MosquittoBroker


@pytest.fixture(scope="session")
def broker() -> Iterator[MosquittoBroker]:
    instance = MosquittoBroker()
    instance.start()
    try:
        yield instance
    finally:
        instance.stop()
