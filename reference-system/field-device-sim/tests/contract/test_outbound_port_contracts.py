"""Contracts of the small outbound ports (LSP): the test double and the real adapter pass the same tests."""

from __future__ import annotations

import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from field_device_sim.infrastructure.file_status_reporter import FileStatusReporter
from field_device_sim.infrastructure.system_clock import SystemClock
from field_device_sim.infrastructure.system_random_source import SystemRandomSource
from field_device_sim.infrastructure.uuid_id_generator import UuidIdGenerator
from field_device_sim.port.outbound.clock import Clock
from field_device_sim.port.outbound.id_generator import IdGenerator
from field_device_sim.port.outbound.random_source import RandomSource
from field_device_sim.port.outbound.status_reporter import StatusReporter
from support.fakes import FixedClock, RecordingStatusReporter, ScriptedRandomSource, SequentialIdGenerator


@pytest.fixture(params=["fixed", "system"])
def clock(request: pytest.FixtureRequest) -> Clock:
    return FixedClock() if request.param == "fixed" else SystemClock()


def test_a_clock_returns_a_timezone_aware_utc_time(clock: Clock) -> None:
    now = clock.now()

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


@pytest.fixture(params=["sequential", "uuid4", "seeded-uuid4"])
def ids(request: pytest.FixtureRequest) -> IdGenerator:
    if request.param == "sequential":
        return SequentialIdGenerator()
    if request.param == "uuid4":
        return UuidIdGenerator()
    return UuidIdGenerator(random.Random(1))  # noqa: S311 - reproducible demo values


def test_an_id_generator_returns_distinct_canonical_lower_case_version_4_uuids(ids: IdGenerator) -> None:
    generated = [ids.new_id() for _ in range(20)]

    assert len(set(generated)) == 20
    for identifier in generated:
        parsed = uuid.UUID(identifier)
        assert str(parsed) == identifier
        assert parsed.version == 4


@pytest.fixture(params=["scripted", "system", "seeded"])
def source(request: pytest.FixtureRequest) -> RandomSource:
    if request.param == "scripted":
        return ScriptedRandomSource()
    if request.param == "system":
        return SystemRandomSource()
    return SystemRandomSource(random.Random(3))  # noqa: S311 - reproducible demo values


def test_a_random_source_picks_one_of_the_options_and_an_integer_in_range(source: RandomSource) -> None:
    options = ("acc-001", "acc-002", "acc-003")

    for _ in range(30):
        assert source.pick(options) in options
        assert 100 <= source.integer(100, 105) <= 105

    assert source.integer(7, 7) == 7


@pytest.fixture(params=["recording", "file"])
def status(request: pytest.FixtureRequest, tmp_path: Path) -> StatusReporter:
    if request.param == "recording":
        return RecordingStatusReporter()
    return FileStatusReporter(tmp_path / "status")


def test_a_status_reporter_has_no_success_until_one_is_recorded(status: StatusReporter) -> None:
    assert status.last_success() is None


def test_a_status_reporter_remembers_the_latest_success(status: StatusReporter) -> None:
    first = datetime(2026, 10, 7, 10, 15, 30, tzinfo=timezone.utc)
    second = first + timedelta(seconds=5)

    status.record_success(first)
    assert status.last_success() == first
    status.record_success(second)
    assert status.last_success() == second
