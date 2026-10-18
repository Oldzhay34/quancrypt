"""The agent_db outbox relay and the housekeeping task (P4.6, D-252g; core-service D-155/D-156 rules).

The relay sends pending `scope_decision` events to ingest-api as a JSON array of envelopes (`event_id`, `event_type`,
`schema_version`, `occurred_at`, `project_key`, `payload`; core-service's envelope). Right before sending it reads the
WAREHOUSE_ANALYTICS consent again for every project key and drops the events whose project has none or whose consent
cannot be read (fail-closed, D-232a). The send itself happens while the store holds the rows' lock, so an event whose
project is being deleted is never sent after the deletion committed (D-254). There is no `failed` state: a failed send
leaves the events pending and doubles the wait (from `interval_s` up to `max_backoff_s`); a successful round resets
it. Off by default until ingest-api exists (P6.1). Only the event ids, counts and error classes are logged.

The housekeeping task runs hourly: idempotency records older than 24 hours (D-136 analogue) and checkpoints idle for 24
hours (D-252e) are deleted.
"""

from __future__ import annotations

import logging
import threading
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from src.memory.short_term import CheckpointStore, ConsentReader, IdempotencyMaintenance, OutboxRelayStore, PendingEvent

_LOG = logging.getLogger("src.app")

HOUSEKEEPING_INTERVAL_S = 3600.0


class PublishFailedError(Exception):
    """ingest-api did not take the batch (unreachable, timeout or a non-2xx answer)."""


class EventPublisher(Protocol):
    def publish(self, envelopes: Sequence[dict[str, Any]]) -> None: ...


class HttpEventPublisher:
    """POSTs the envelopes to ingest-api; no proxy from the environment, no redirects (phase 1 is local)."""

    def __init__(self, url: str, timeout_s: float) -> None:
        self._url = url
        self._client = httpx.Client(timeout=timeout_s, trust_env=False, follow_redirects=False)

    def publish(self, envelopes: Sequence[dict[str, Any]]) -> None:
        try:
            response = self._client.post(self._url, json=list(envelopes))
        except httpx.HTTPError as exc:
            raise PublishFailedError(type(exc).__name__) from None
        if not 200 <= response.status_code < 300:
            raise PublishFailedError(f"HTTP {response.status_code}")

    def close(self) -> None:
        self._client.close()


@dataclass(frozen=True)
class RelayRound:
    sent: int
    discarded: int
    failed: bool


class OutboxRelay:
    def __init__(
        self, store: OutboxRelayStore, consent: ConsentReader, publisher: EventPublisher, batch_size: int
    ) -> None:
        self._store = store
        self._consent = consent
        self._publisher = publisher
        self._batch_size = batch_size

    def relay_once(self) -> RelayRound:
        events = self._store.pending(self._batch_size)
        if not events:
            return RelayRound(0, 0, False)
        trace_id = uuid.uuid4().hex
        consented: dict[str, bool] = {}
        keep: list[PendingEvent] = []
        drop: list[uuid.UUID] = []
        for event in events:
            if event.project_key not in consented:
                ids = self._store.project_ids(event.project_key)
                consented[event.project_key] = any(self._consent.warehouse_consent(pid, trace_id) for pid in ids)
            (keep.append(event) if consented[event.project_key] else drop.append(event.id))
        discarded = self._store.discard(drop)
        if not keep:
            return RelayRound(0, discarded, False)

        def send(locked: tuple[PendingEvent, ...]) -> None:
            self._publisher.publish([_envelope(event) for event in locked])

        try:
            # The send happens under the rows' lock: an event deleted meanwhile (DeleteProjectData) is not sent (D-254).
            sent = self._store.publish_locked([event.id for event in keep], send)
        except PublishFailedError as exc:
            _LOG.warning("outbox relay could not send %d events (%s)", len(keep), exc)
            return RelayRound(0, discarded, True)
        return RelayRound(sent, discarded, False)


def _envelope(event: PendingEvent) -> dict[str, Any]:
    return {
        "event_id": str(event.id),
        "event_type": event.event_type,
        "schema_version": event.schema_version,
        "occurred_at": event.occurred_at.isoformat().replace("+00:00", "Z"),
        "project_key": event.project_key,
        "payload": dict(event.payload),
    }


class Backoff:
    """The wait before the next round: `interval_s`, doubled after every failed round up to `max_s` (D-156)."""

    def __init__(self, interval_s: float, max_s: float) -> None:
        self._interval = interval_s
        self._max = max_s
        self.current = interval_s

    def after(self, failed: bool) -> float:
        self.current = min(self.current * 2, self._max) if failed else self._interval
        return self.current


class PeriodicTask:
    """A daemon thread that runs `work` and then waits the delay it returns; `stop()` ends it promptly."""

    def __init__(self, name: str, work: Callable[[], float], first_delay_s: float) -> None:
        self._work = work
        self._first = first_delay_s
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name=name, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)

    def _loop(self) -> None:
        delay = self._first
        while not self._stop.wait(delay):
            delay = self._work()


def relay_work(relay: OutboxRelay, backoff: Backoff) -> Callable[[], float]:
    def run() -> float:
        try:
            round_ = relay.relay_once()
        except Exception as exc:  # the database or core-service failed: count it as a failed round
            _LOG.warning("outbox relay round failed (%s)", type(exc).__name__)
            return backoff.after(True)
        if round_.sent or round_.discarded:
            _LOG.info("outbox relay sent %d and dropped %d events", round_.sent, round_.discarded)
        return backoff.after(round_.failed)

    return run


def housekeeping_work(idempotency: IdempotencyMaintenance, checkpoints: CheckpointStore) -> Callable[[], float]:
    def run() -> float:
        try:
            purged = idempotency.purge_idempotency_records()
            idle = checkpoints.purge_idle()
            if purged or idle:
                _LOG.info("housekeeping removed %d idempotency records and %d idle checkpoints", purged, idle)
        except Exception as exc:
            _LOG.warning("housekeeping failed (%s)", type(exc).__name__)
        return HOUSEKEEPING_INTERVAL_S

    return run
