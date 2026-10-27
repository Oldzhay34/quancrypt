"""Use case DeleteProjectData (D-295d): erase the rows of one project key from every registered table."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID

from quancrypt_data.domain.events import require_project_key


@dataclass(frozen=True)
class DeleteProjectDataCommand:
    project_key: str
    # The id of the consent_revoked event that asked for it: a repeated command is recognised by it and does nothing.
    event_id: UUID
    # When the revocation happened: records of the key that happened at or before it are never stored again (D-296).
    occurred_at: datetime
    # False when an earlier revocation already covers this one: only the audit is written (D-297a).
    erase_rows: bool = True

    def __post_init__(self) -> None:
        require_project_key(self.project_key)


@dataclass(frozen=True)
class DeleteProjectDataResult:
    erased: bool
    # Rows deleted per table (`schema.table`); empty when the command was a repeat.
    deleted: Mapping[str, int] = field(default_factory=dict)


class DeleteProjectDataUseCase(Protocol):
    def execute(self, command: DeleteProjectDataCommand) -> DeleteProjectDataResult: ...
