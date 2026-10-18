"""Contract of the `EventPublisher` port (LSP, P4.6): the test double and the HTTP adapter take a batch or raise
`PublishFailedError`; nothing else escapes."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from typing import Any

import httpx
import pytest
import respx

from src.app.outbox_relay import EventPublisher, HttpEventPublisher, PublishFailedError

URL = "http://ingest-api:8084/api/v1/events"
BATCH = [{"event_id": "e1", "event_type": "scope_decision"}]


class RecordingPublisher:
    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.batches: list[list[dict[str, Any]]] = []

    def publish(self, envelopes: Sequence[dict[str, Any]]) -> None:
        if self.fail:
            raise PublishFailedError("down")
        self.batches.append(list(envelopes))


class EventPublisherContract:
    @pytest.fixture
    def working(self) -> Iterator[EventPublisher]:
        raise NotImplementedError

    @pytest.fixture
    def failing(self) -> Iterator[EventPublisher]:
        raise NotImplementedError

    def test_a_batch_is_taken(self, working: EventPublisher) -> None:
        working.publish(BATCH)

    def test_a_failure_is_publish_failed_and_nothing_else(self, failing: EventPublisher) -> None:
        with pytest.raises(PublishFailedError):
            failing.publish(BATCH)


class TestRecordingPublisher(EventPublisherContract):
    @pytest.fixture
    def working(self) -> Iterator[EventPublisher]:
        yield RecordingPublisher(fail=False)

    @pytest.fixture
    def failing(self) -> Iterator[EventPublisher]:
        yield RecordingPublisher(fail=True)


class TestHttpPublisher(EventPublisherContract):
    @pytest.fixture
    def working(self) -> Iterator[EventPublisher]:
        publisher = HttpEventPublisher(URL, 1)
        with respx.mock() as mock:
            mock.post(URL).mock(return_value=httpx.Response(202))
            yield publisher
        publisher.close()

    @pytest.fixture
    def failing(self) -> Iterator[EventPublisher]:
        publisher = HttpEventPublisher(URL, 1)
        with respx.mock() as mock:
            mock.post(URL).mock(side_effect=httpx.ConnectError("refused"))
            yield publisher
        publisher.close()
