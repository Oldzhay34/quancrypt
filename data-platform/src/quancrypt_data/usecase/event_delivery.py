"""Sending events to ingest-api in requests it accepts: at most 500 events and a body well below 8 MiB."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from quancrypt_data.domain.events import MAX_BATCH_EVENTS
from quancrypt_data.port.outbound.corpus import DeliveryResult, EventSink

# The body limit of ingest-api is 8 MiB (D-295a); a request stays at half of it. The size is measured on the serialised
# events, not estimated from the number of findings (a finding can be 2 KB when its names are long).
MAX_REQUEST_BYTES = 4 * 1024 * 1024


def deliver(sink: EventSink, events: Sequence[Mapping[str, object]]) -> tuple[DeliveryResult, int]:
    """Sends the events in as few requests as the limits allow; returns the summed answer and the number of requests."""
    totals = DeliveryResult()
    requests = 0
    batch: list[Mapping[str, object]] = []
    weight = 0

    def flush() -> None:
        nonlocal totals, requests, batch, weight
        if not batch:
            return
        answer = sink.send(batch)
        requests += 1
        totals = DeliveryResult(
            accepted=totals.accepted + answer.accepted,
            duplicate=totals.duplicate + answer.duplicate,
            quarantined=totals.quarantined + answer.quarantined,
            superseded=totals.superseded + answer.superseded,
            consent_revoked=totals.consent_revoked + answer.consent_revoked,
        )
        batch, weight = [], 0

    for event in events:
        size = _serialised_size(event)
        if batch and (len(batch) >= MAX_BATCH_EVENTS or weight + size > MAX_REQUEST_BYTES):
            flush()
        batch.append(event)
        weight += size
    flush()
    return totals, requests


def _serialised_size(event: Mapping[str, object]) -> int:
    return len(json.dumps(event, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
