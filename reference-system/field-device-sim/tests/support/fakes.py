"""Test doubles of the outbound ports."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta, timezone

from field_device_sim.domain.terminal_transaction import TerminalTransaction
from field_device_sim.port.outbound.message_publisher import PublishError

START = datetime(2026, 10, 7, 10, 15, 30, tzinfo=timezone.utc)


class FixedClock:
    """A clock that only moves when told to."""

    def __init__(self, now: datetime = START) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)


class SequentialIdGenerator:
    """Canonical lower case version 4 UUIDs from a counter: 00000000-0000-4000-8000-000000000001, ..."""

    def __init__(self) -> None:
        self._counter = 0

    def new_id(self) -> str:
        self._counter += 1
        return str(uuid.UUID(int=self._counter, version=4))


class ScriptedRandomSource:
    """Always picks the first option and the minimum integer unless a script says otherwise."""

    def __init__(self, picks: Sequence[int] = (), integers: Sequence[int] = ()) -> None:
        self._picks = list(picks)
        self._integers = list(integers)

    def pick(self, options: Sequence[str]) -> str:
        index = self._picks.pop(0) if self._picks else 0
        return options[index]

    def integer(self, low: int, high: int) -> int:
        value = self._integers.pop(0) if self._integers else low
        assert low <= value <= high
        return value


class RecordingStatusReporter:
    """Keeps the successes in memory."""

    def __init__(self) -> None:
        self.successes: list[datetime] = []

    def record_success(self, at: datetime) -> None:
        self.successes.append(at)

    def last_success(self) -> datetime | None:
        return self.successes[-1] if self.successes else None


class FakeMessagePublisher:
    """Keeps the published transactions in memory; can be made to fail."""

    def __init__(self, failing: bool = False) -> None:
        self.published: list[TerminalTransaction] = []
        self.failing = failing

    def publish(self, transaction: TerminalTransaction) -> None:
        if self.failing:
            raise PublishError("the broker is unavailable")
        self.published.append(transaction)
