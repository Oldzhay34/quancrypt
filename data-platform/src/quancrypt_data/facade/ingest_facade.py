"""The coarse entry point of the API: turns the use case's commands and errors into what the HTTP layer needs."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from quancrypt_data.port.inbound.ingest_events import IngestEventsCommand, IngestEventsUseCase, InvalidBatchError


class BadRequestError(Exception):
    """The request cannot be processed as a whole (maps to 400 validation-failed)."""


@dataclass(frozen=True)
class IngestResultView:
    received: int
    accepted: int
    duplicate: int
    quarantined: int
    consent_revoked: int
    superseded: int


class IngestFacade:
    def __init__(self, ingest_events: IngestEventsUseCase) -> None:
        self._ingest_events = ingest_events

    def ingest(self, items: Sequence[object]) -> IngestResultView:
        try:
            result = self._ingest_events.execute(IngestEventsCommand(items=items))
        except InvalidBatchError as exc:
            raise BadRequestError(str(exc)) from exc
        return IngestResultView(
            received=result.received,
            accepted=result.accepted,
            duplicate=result.duplicate,
            quarantined=result.quarantined,
            consent_revoked=result.consent_revoked,
            superseded=result.superseded,
        )
