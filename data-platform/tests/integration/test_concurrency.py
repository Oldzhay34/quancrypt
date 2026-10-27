"""Concurrent requests against the real database: no lost or doubled rows, no deadlock, no silent retry (acid-3nf-database
section 7, test 4)."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pytest
from sqlalchemy import text

from quancrypt_data.port.inbound.ingest_events import IngestEventsCommand, IngestEventsResult
from tests.conftest import Stack
from tests.support.envelopes import KEY_A, KEY_B, envelope

pytestmark = pytest.mark.postgres

ROUNDS = 8


def scalar(stack: Stack, sql: str, **params: Any) -> Any:
    with stack.instance.migrator_engine().begin() as connection:
        return connection.execute(text(sql), params).scalar_one()


def deadlocks(stack: Stack) -> int:
    # The statistics are flushed about once a second.
    time.sleep(1.5)
    return int(scalar(stack, "SELECT deadlocks FROM pg_stat_database WHERE datname = 'warehouse_db'"))


def run_together(jobs: list[Callable[[], IngestEventsResult]]) -> list[IngestEventsResult]:
    barrier = threading.Barrier(len(jobs))

    def start(job: Callable[[], IngestEventsResult]) -> IngestEventsResult:
        barrier.wait(timeout=10)
        return job()

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        return [future.result(timeout=60) for future in [pool.submit(start, job) for job in jobs]]


def ingest(stack: Stack, *items: object) -> Callable[[], IngestEventsResult]:
    return lambda: stack.container.ingest_events.execute(IngestEventsCommand(items=items))


def test_the_same_event_sent_by_eight_requests_at_once_is_stored_exactly_once(stack: Stack) -> None:
    item = envelope()
    before = deadlocks(stack)

    results = run_together([ingest(stack, item) for _ in range(8)])

    assert sum(r.accepted for r in results) == 1
    assert sum(r.duplicate for r in results) == 7
    assert scalar(stack, "SELECT count(*) FROM raw.event") == 1
    assert scalar(stack, "SELECT count(*) FROM ingest.ingest_batch") == 8
    assert stack.container.database.retries == 0
    assert deadlocks(stack) == before


def test_many_requests_with_different_events_lose_nothing(stack: Stack) -> None:
    jobs = [ingest(stack, *[envelope() for _ in range(25)]) for _ in range(8)]

    results = run_together(jobs)

    assert sum(r.accepted for r in results) == 200
    assert scalar(stack, "SELECT count(*) FROM raw.event") == 200
    assert stack.container.database.retries == 0


def test_an_ingest_racing_a_revocation_always_ends_with_nothing_stored(stack: Stack) -> None:
    before = deadlocks(stack)
    for _ in range(ROUNDS):
        events = [envelope(occurred_at="2026-10-27T10:00:00Z") for _ in range(10)]
        revocation = envelope("consent_revoked", occurred_at="2026-10-27T11:00:00Z")

        run_together([ingest(stack, *events), ingest(stack, revocation)])

        # Whichever request runs first, the events happened before the revocation: they are stored and then erased, or the
        # cut-off the revocation left drops them. Never some of them, never any.
        assert scalar(stack, "SELECT count(*) FROM raw.event") == 0
        with stack.instance.migrator_engine().begin() as connection:
            connection.execute(
                text(
                    "TRUNCATE ingest.ingest_audit_table, ingest.ingest_audit, raw.event, quarantine.event, ingest.ingest_batch"
                )
            )

    assert stack.container.database.retries == 0
    assert deadlocks(stack) == before


def test_batches_that_lock_the_same_keys_from_opposite_ends_do_not_deadlock(stack: Stack) -> None:
    before = deadlocks(stack)
    for _ in range(ROUNDS):
        forward = [envelope(project_key=KEY_A), envelope(project_key=KEY_B)]
        backward = [envelope(project_key=KEY_B), envelope(project_key=KEY_A)]
        revocation_b = envelope("consent_revoked", project_key=KEY_B, occurred_at="2026-10-27T11:00:00Z")

        results = run_together(
            [ingest(stack, *forward), ingest(stack, *backward), ingest(stack, revocation_b, *forward)]
        )

        assert all(r.received >= 2 for r in results)

    assert stack.container.database.retries == 0
    assert deadlocks(stack) == before


def test_two_revocations_of_one_key_with_different_ids_both_run_and_are_both_audited(stack: Stack) -> None:
    ingest(stack, envelope())()
    first = envelope("consent_revoked", event_id=str(uuid.uuid4()))
    second = envelope("consent_revoked", event_id=str(uuid.uuid4()))

    results = run_together([ingest(stack, first), ingest(stack, second)])

    assert sum(r.consent_revoked for r in results) == 2
    assert scalar(stack, "SELECT count(*) FROM ingest.ingest_audit") == 2
    assert scalar(stack, "SELECT count(*) FROM raw.event") == 0
    assert stack.container.database.retries == 0


def test_the_lock_of_a_project_key_makes_a_second_request_for_it_wait(stack: Stack) -> None:
    """The advisory lock is what serialises two requests of one project: while one transaction holds it, another that needs it
    waits, and goes on as soon as the first ends (the other tests cannot tell: every statement is atomic on its own)."""
    from quancrypt_data.infrastructure.persistence.repositories import PostgresProjectKeyLock

    database = stack.container.database
    lock = PostgresProjectKeyLock(database)
    holding = threading.Event()
    release = threading.Event()

    def hold() -> None:
        def work() -> None:
            lock.acquire([KEY_A])
            holding.set()
            release.wait(timeout=10)

        database.run(work)

    with ThreadPoolExecutor(max_workers=3) as pool:
        holder = pool.submit(hold)
        assert holding.wait(timeout=10)
        waiting = pool.submit(ingest(stack, envelope(project_key=KEY_A)))
        time.sleep(1.0)
        assert not waiting.done(), "the second request did not wait for the lock of its project"
        # Another project is not held up.
        other = pool.submit(ingest(stack, envelope(project_key=KEY_B)))
        assert other.result(timeout=10).accepted == 1
        release.set()
        holder.result(timeout=10)
        assert waiting.result(timeout=10).accepted == 1
