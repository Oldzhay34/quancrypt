"""The agent outbox relay (D-252g, D-232a): consent is read again before sending and an event without it is dropped; a
failed send keeps the events and doubles the wait; a successful round resets it; the envelope is core-service's."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import respx

from src.app.outbox_relay import Backoff, HttpEventPublisher, OutboxRelay, PublishFailedError, relay_work
from src.memory.short_term import PendingEvent

KEY_OK = "a" * 64
KEY_GONE = "b" * 64
PROJECT_OK = uuid4()
PROJECT_GONE = uuid4()


def event(key: str) -> PendingEvent:
    return PendingEvent(
        uuid4(),
        "scope_decision",
        1,
        key,
        datetime(2026, 10, 18, 12, 0, tzinfo=UTC),
        {"decision": "DENY", "deciding_ring": "RULE_FILTER", "confidence": None, "latency_ms": 2, "language": "tr"},
    )


class Store:
    def __init__(self, events: Sequence[PendingEvent]) -> None:
        self.events = list(events)
        self.published: list[UUID] = []
        self.discarded: list[UUID] = []

    def pending(self, limit: int) -> tuple[PendingEvent, ...]:
        return tuple(e for e in self.events if e.id not in self.published and e.id not in self.discarded)[:limit]

    def publish_locked(self, event_ids: Sequence[UUID], send: Callable[[tuple[PendingEvent, ...]], None]) -> int:
        locked = tuple(e for e in self.pending(len(self.events)) if e.id in event_ids)
        send(locked)
        self.published.extend(e.id for e in locked)
        return len(locked)

    def discard(self, event_ids: Sequence[UUID]) -> int:
        self.discarded.extend(event_ids)
        return len(event_ids)

    def project_ids(self, project_key: str) -> tuple[UUID, ...]:
        return {KEY_OK: (PROJECT_OK,), KEY_GONE: (PROJECT_GONE,)}.get(project_key, ())


class Consent:
    def warehouse_consent(self, project_id: UUID, trace_id: str) -> bool:
        return project_id == PROJECT_OK


class Publisher:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.batches: list[list[dict[str, Any]]] = []

    def publish(self, envelopes: Sequence[dict[str, Any]]) -> None:
        if self.fail:
            raise PublishFailedError("HTTP 503")
        self.batches.append(list(envelopes))


def test_events_without_consent_are_dropped_and_the_rest_sent_in_core_envelopes() -> None:
    ok, gone = event(KEY_OK), event(KEY_GONE)
    store, publisher = Store([ok, gone]), Publisher()

    round_ = OutboxRelay(store, Consent(), publisher, 100).relay_once()

    assert (round_.sent, round_.discarded, round_.failed) == (1, 1, False)
    assert store.discarded == [gone.id] and store.published == [ok.id]
    [[envelope]] = publisher.batches
    assert set(envelope) == {"event_id", "event_type", "schema_version", "occurred_at", "project_key", "payload"}
    assert (envelope["event_id"], envelope["occurred_at"]) == (str(ok.id), "2026-10-18T12:00:00Z")


def test_a_failed_send_keeps_the_events_pending() -> None:
    store = Store([event(KEY_OK)])

    round_ = OutboxRelay(store, Consent(), Publisher(fail=True), 100).relay_once()

    assert round_.failed and store.published == [] and len(store.pending(10)) == 1


def test_the_wait_doubles_after_failures_up_to_the_cap_and_resets_after_success() -> None:
    backoff = Backoff(5, 30)

    assert [backoff.after(True) for _ in range(4)] == [10, 20, 30, 30]
    assert backoff.after(False) == 5


def test_a_crashing_round_counts_as_a_failure() -> None:
    class Broken(Store):
        def pending(self, limit: int) -> tuple[PendingEvent, ...]:
            raise RuntimeError("database down")

    work = relay_work(OutboxRelay(Broken([]), Consent(), Publisher(), 100), Backoff(5, 300))

    assert work() == 10


@pytest.mark.parametrize("status", [500, 404, 302])
def test_the_http_publisher_fails_on_anything_but_2xx(status: int) -> None:
    publisher = HttpEventPublisher("http://ingest-api:8084/api/v1/events", 1)
    with respx.mock() as mock:
        mock.post("http://ingest-api:8084/api/v1/events").mock(return_value=httpx.Response(status))
        with pytest.raises(PublishFailedError):
            publisher.publish([{"event_id": "x"}])
    publisher.close()


def test_the_http_publisher_posts_a_json_array() -> None:
    publisher = HttpEventPublisher("http://ingest-api:8084/api/v1/events", 1)
    with respx.mock() as mock:
        route = mock.post("http://ingest-api:8084/api/v1/events").mock(return_value=httpx.Response(202))
        publisher.publish([{"event_id": "x"}])
    assert route.calls.last.request.read() == b'[{"event_id":"x"}]'
    publisher.close()
