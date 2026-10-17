"""A refused tool call reaches the audit trail: the toolbox journal written with a step by the real `PostgresAuditLog`
(guardrails-security section 3, D-238d; the agent does this in P4.5)."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

from src.memory.memory_store import Database, PostgresAuditLog, utc_now
from src.memory.short_term import StepRecord
from src.tools.base_tool import ToolContext, ToolNotAllowedError
from tests.support.tool_samples import SAMPLES
from tests.support.tools import TRACE, build_registry

pytestmark = pytest.mark.postgres


def test_denied_and_unknown_tool_calls_are_stored_with_their_step(database: Database) -> None:
    toolbox = build_registry().scoped("discovery")
    denied, unknown = ToolContext(trace_id=TRACE), ToolContext(trace_id=TRACE)
    with pytest.raises(ToolNotAllowedError):
        toolbox.invoke("create_plan", SAMPLES["create_plan"][0], denied)
    with pytest.raises(ToolNotAllowedError):
        toolbox.invoke("shell_exec", {}, unknown)

    audit = PostgresAuditLog(database, utc_now, uuid4)
    run = audit.start_run(None, "INITIAL_SCAN", TRACE)
    step = audit.record_step(
        StepRecord(run, 1, "ACT", "DISCOVERY", "FAILED", 1, 0, 0, utc_now(), tool_calls=toolbox.records())
    )

    with database.engine.connect() as connection:
        rows = connection.execute(
            text("SELECT id, tool_code, status, duration_ms FROM tool_call WHERE step_id = :step"),
            {"step": step},
        ).all()
    assert {(row.id, row.tool_code, row.status, row.duration_ms) for row in rows} == {
        (denied.call_id, "CORE", "DENIED", 0),
        (unknown.call_id, "UNKNOWN", "DENIED", 0),
    }
