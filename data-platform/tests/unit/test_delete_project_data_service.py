from __future__ import annotations

from uuid import UUID

import pytest

from quancrypt_data.domain.events import ProjectKeyTable
from quancrypt_data.port.inbound.delete_project_data import DeleteProjectDataCommand
from quancrypt_data.usecase.delete_project_data_service import DeleteProjectDataService
from tests.support.envelopes import KEY_A
from tests.support.fakes import (
    NOW,
    FakeAudit,
    FakeDatabase,
    FakeEraser,
    FakeLocks,
    FakeRegistry,
    FixedClock,
    SequentialIds,
)

EVENT = UUID("00000000-0000-4000-8000-0000000000aa")


def service(database: FakeDatabase, tables: list[ProjectKeyTable]) -> DeleteProjectDataService:
    return DeleteProjectDataService(
        transactions=database,
        registry=FakeRegistry(tables),
        eraser=FakeEraser(database),
        audit=FakeAudit(database),
        locks=FakeLocks(database),
        clock=FixedClock(),
        ids=SequentialIds(),
    )


def test_every_registered_table_is_erased_and_the_counts_are_audited() -> None:
    database = FakeDatabase()

    result = service(database, [ProjectKeyTable("raw", "event"), ProjectKeyTable("quarantine", "event")]).execute(
        DeleteProjectDataCommand(project_key=KEY_A, event_id=EVENT, occurred_at=NOW)
    )

    assert result.erased
    assert dict(result.deleted) == {"raw.event": 0, "quarantine.event": 0}
    record = database.state.audit[EVENT]
    assert (record.project_key, record.performed_at) == (KEY_A, NOW)
    assert database.state.lock_calls == [[KEY_A]]


def test_a_repeat_of_the_same_event_does_nothing() -> None:
    database = FakeDatabase()
    use_case = service(database, [ProjectKeyTable("raw", "event")])
    use_case.execute(DeleteProjectDataCommand(project_key=KEY_A, event_id=EVENT, occurred_at=NOW))

    again = use_case.execute(DeleteProjectDataCommand(project_key=KEY_A, event_id=EVENT, occurred_at=NOW))

    assert not again.erased
    assert dict(again.deleted) == {}
    assert len(database.state.audit) == 1


def test_a_registry_that_grows_is_covered_without_a_change_to_the_use_case() -> None:
    database = FakeDatabase()
    use_case = service(database, [ProjectKeyTable("raw", "event")])
    assert dict(use_case.execute(DeleteProjectDataCommand(KEY_A, EVENT, NOW)).deleted) == {"raw.event": 0}


def test_a_command_with_a_bad_key_cannot_be_built() -> None:
    with pytest.raises(ValueError, match="project_key"):
        DeleteProjectDataCommand(project_key="short", event_id=EVENT, occurred_at=NOW)
