from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from quancrypt_data.domain.events import ProjectKeyTable


@dataclass(frozen=True)
class ErasureRecord:
    id: UUID
    performed_at: datetime
    # The consent_revoked event that asked for the erasure (unique: a repeat is recognised by it).
    event_id: UUID
    project_key: str
    # When the revocation happened (the event's occurred_at): the cut-off for what may still be stored for the key.
    revoked_at: datetime
    deleted: Mapping[str, int]


class ProjectKeyTableRegistry(Protocol):
    """Every table that holds rows of a project key. P6.1 lists raw and quarantine; P6.4 and P6.6 extend it (D-295d)."""

    def tables(self) -> Sequence[ProjectKeyTable]: ...


class ProjectDataEraser(Protocol):
    def delete(self, table: ProjectKeyTable, project_key: str) -> int:
        """Delete the key's rows of a registered table; returns how many."""
        ...


class ErasureAudit(Protocol):
    def is_recorded(self, event_id: UUID) -> bool: ...

    def record(self, record: ErasureRecord) -> None: ...

    def latest_revocation(self, project_key: str) -> datetime | None:
        """The latest revocation time recorded for the key, None when there is none."""
        ...


class ProjectKeyLock(Protocol):
    def acquire(self, project_keys: Sequence[str]) -> None:
        """Hold a lock per key until the transaction ends. Always taken in sorted order, so two transactions cannot
        deadlock; it serialises an ingest and an erasure of the same key."""
        ...
