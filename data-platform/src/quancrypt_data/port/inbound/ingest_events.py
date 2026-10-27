"""Use case IngestEvents (D-295): validate, store, quarantine; one request is one transaction."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


class InvalidBatchError(Exception):
    """The request as a whole cannot be processed (empty, or above the batch limit)."""


@dataclass(frozen=True)
class IngestEventsCommand:
    # Each item is whatever the sender put in the array: a bad item is quarantined, it does not fail the batch.
    items: Sequence[object]


@dataclass(frozen=True)
class IngestEventsResult:
    """received = accepted + duplicate + quarantined + consent_revoked + superseded. `superseded` counts the records
    of a
    project that happened at or before its latest consent revocation: they are dropped, never stored (D-296)."""

    received: int
    accepted: int
    duplicate: int
    quarantined: int
    consent_revoked: int
    superseded: int


class IngestEventsUseCase(Protocol):
    def execute(self, command: IngestEventsCommand) -> IngestEventsResult: ...
