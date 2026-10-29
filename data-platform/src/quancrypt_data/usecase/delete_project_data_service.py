from __future__ import annotations

from quancrypt_data.port.inbound.delete_project_data import (
    DeleteProjectDataCommand,
    DeleteProjectDataResult,
    DeleteProjectDataUseCase,
)
from quancrypt_data.port.outbound.erasure import (
    ErasureAudit,
    ErasureRecord,
    ProjectDataEraser,
    ProjectKeyLock,
    ProjectKeyTableRegistry,
)
from quancrypt_data.port.outbound.system import Clock, IdGenerator
from quancrypt_data.port.outbound.transaction import TransactionRunner


class DeleteProjectDataService(DeleteProjectDataUseCase):
    """Erases a project key from every registered table in one transaction and audits it (KVKK, D-295d).

    Called from IngestEvents it joins the batch's transaction; called alone it runs in its own. A repeat of the same
    consent_revoked event (same `event_id`) is recognised by the audit and does nothing: a late repeat must not delete
    rows of a consent given again since."""

    def __init__(
        self,
        transactions: TransactionRunner,
        registry: ProjectKeyTableRegistry,
        eraser: ProjectDataEraser,
        audit: ErasureAudit,
        locks: ProjectKeyLock,
        clock: Clock,
        ids: IdGenerator,
    ) -> None:
        self._transactions = transactions
        self._registry = registry
        self._eraser = eraser
        self._audit = audit
        self._locks = locks
        self._clock = clock
        self._ids = ids

    def execute(self, command: DeleteProjectDataCommand) -> DeleteProjectDataResult:
        return self._transactions.run(lambda: self._erase(command))

    def _erase(self, command: DeleteProjectDataCommand) -> DeleteProjectDataResult:
        self._locks.acquire([command.project_key])
        if self._audit.is_recorded(command.event_id):
            return DeleteProjectDataResult(erased=False)
        deleted = (
            {table.qualified: self._eraser.delete(table, command.project_key) for table in self._registry.tables()}
            if command.erase_rows
            else {}
        )
        self._audit.record(
            ErasureRecord(
                id=self._ids.new_id(),
                performed_at=self._clock.now(),
                event_id=command.event_id,
                project_key=command.project_key,
                revoked_at=command.occurred_at,
                deleted=deleted,
            )
        )
        return DeleteProjectDataResult(erased=True, deleted=deleted)
