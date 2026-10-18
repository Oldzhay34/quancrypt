"""The workflow on the real agent_db (marker `postgres`): the request text is in no table but the chat itself, the
warehouse event needs consent, checkpoints hold no text, and the relay store reads, marks and drops events (P4.6)."""

from __future__ import annotations

import threading
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text

from src.memory.memory_store import (
    Database,
    PostgresAuditLog,
    PostgresCheckpointStore,
    PostgresConversationMemory,
    PostgresOutboxRelayStore,
    PostgresScopeDecisionLog,
    utc_now,
)
from src.memory.short_term import ConversationWindow, ScopeDecisionRecord
from src.workflows.agent_graph import LangGraphWorkflows
from src.workflows.orchestrator import AgentSet, Orchestrator
from tests.support.agent_fakes import ScriptedLLM
from tests.support.workflow_fakes import (
    KEY,
    PROJECT,
    TRACE,
    FakeConsent,
    FakeGuard,
    FakeRunner,
    FakeTools,
    PassChecker,
    completed,
    events,
)

pytestmark = pytest.mark.postgres

WINDOW = ConversationWindow(max_messages=12, token_budget=3000, chars_per_token=4)
SECRET_QUESTION = "Which post-quantum algorithm should I choose for the zebra-umbrella-42 service?"


def orchestrator(database: Database, *, consent: bool) -> tuple[Orchestrator, PostgresConversationMemory]:
    memory = PostgresConversationMemory(database, WINDOW, utc_now, uuid4)
    agents = AgentSet(
        discovery=FakeRunner(completed()),
        topology=FakeRunner(completed()),
        planner=FakeRunner(completed()),
        answer=FakeRunner(completed("Use ML-KEM for key establishment.")),
    )
    built = Orchestrator(
        conversation=memory,
        audit=PostgresAuditLog(database, utc_now, uuid4),
        scope_log=PostgresScopeDecisionLog(database, utc_now, uuid4),
        consent=FakeConsent(consent),
        call_tool=FakeTools(),
        guard=FakeGuard(),
        output_checker=PassChecker(),
        llm=ScriptedLLM(disabled=True),
        agents=lambda _llm: agents,
        workflows=LangGraphWorkflows(PostgresCheckpointStore(database, utc_now)),
        queue_wait_s=1,
    )
    return built, memory


def _all_text(database: Database, exclude: set[str]) -> str:
    """Every text-like column of every table but the excluded ones, as one string (bytea decoded leniently)."""
    with database.engine.connect() as connection:
        columns = connection.execute(
            text(
                "SELECT table_name, column_name, data_type FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND data_type IN ('text', 'character varying', 'character', 'jsonb', 'bytea')"
            )
        ).all()
        dump: list[str] = []
        for table, column, data_type in columns:
            if table in exclude:
                continue
            for (value,) in connection.execute(text(f'SELECT "{column}" FROM "{table}"')).all():  # noqa: S608
                if value is None:
                    continue
                dump.append(bytes(value).decode("utf-8", "replace") if data_type == "bytea" else str(value))
    return "\n".join(dump)


@pytest.mark.parametrize("consent", [False, True])
def test_the_request_text_is_only_in_the_chat_and_the_event_needs_consent(database: Database, consent: bool) -> None:
    built, memory = orchestrator(database, consent=consent)
    session = memory.create_session(PROJECT, KEY, "en").session.id

    events(built.begin_message(session, SECRET_QUESTION, TRACE))
    events(built.begin_message(session, SECRET_QUESTION, TRACE))  # the second message writes a checkpoint

    assert "zebra-umbrella-42" not in _all_text(database, exclude={"chat_message"})
    with database.engine.connect() as connection:
        decisions = connection.execute(text("SELECT count(*) FROM scope_decision")).scalar_one()
        outbox = connection.execute(text("SELECT count(*) FROM outbox_event")).scalar_one()
        checkpoints = connection.execute(text("SELECT count(*) FROM graph_checkpoint")).scalar_one()
    assert decisions == 2 and outbox == (2 if consent else 0) and checkpoints == 1


def test_the_relay_store_reads_oldest_first_marks_and_drops(database: Database) -> None:
    memory = PostgresConversationMemory(database, WINDOW, utc_now, uuid4)
    session = memory.create_session(PROJECT, KEY, "tr").session.id
    log = PostgresScopeDecisionLog(database, utc_now, uuid4)
    record = ScopeDecisionRecord(session, "DENY", None, "RULE_FILTER", 2, "tr")
    for _ in range(3):
        log.record(record, warehouse_consent=True)
    store = PostgresOutboxRelayStore(database, utc_now)

    pending = store.pending(10)
    assert len(pending) == 3 and [e.occurred_at for e in pending] == sorted(e.occurred_at for e in pending)
    assert pending[0].project_key == KEY and pending[0].payload["deciding_ring"] == "RULE_FILTER"
    assert store.project_ids(KEY) == (PROJECT,)

    assert store.publish_locked([pending[0].id], lambda _: None) == 1
    assert store.publish_locked([pending[0].id], lambda _: None) == 0  # already sent
    assert store.discard([pending[1].id]) == 1
    remaining: list[Any] = [e.id for e in store.pending(10)]
    assert remaining == [pending[2].id]


def test_delete_project_data_waits_for_a_send_in_progress_and_never_follows_it(database: Database) -> None:
    """DB review P4.6 #5 (D-254): DeleteProjectData that starts while the relay sends waits for the send; the sent
    event stays marked (published rows are not deleted); a later round finds nothing to send."""
    memory = PostgresConversationMemory(database, WINDOW, utc_now, uuid4)
    session = memory.create_session(PROJECT, KEY, "tr").session.id
    PostgresScopeDecisionLog(database, utc_now, uuid4).record(
        ScopeDecisionRecord(session, "DENY", None, "RULE_FILTER", 2, "tr"), warehouse_consent=True
    )
    store = PostgresOutboxRelayStore(database, utc_now)
    [event] = store.pending(10)
    deleter: list[threading.Thread] = []

    def send(_: tuple[Any, ...]) -> None:
        thread = threading.Thread(target=memory.delete_project_data, args=(PROJECT,))
        thread.start()
        thread.join(1.5)
        assert thread.is_alive()  # DeleteProjectData waits on the locked row
        deleter.append(thread)

    assert store.publish_locked([event.id], send) == 1
    deleter[0].join(5)
    assert not deleter[0].is_alive()
    with database.engine.connect() as connection:
        rows = connection.execute(text("SELECT published_at IS NOT NULL FROM outbox_event")).scalars().all()
        refs = connection.execute(text("SELECT count(*) FROM project_ref")).scalar_one()
    assert rows == [True] and refs == 0
    assert database.retries == 0


def test_an_event_deleted_before_the_send_is_not_sent(database: Database) -> None:
    memory = PostgresConversationMemory(database, WINDOW, utc_now, uuid4)
    session = memory.create_session(PROJECT, KEY, "tr").session.id
    PostgresScopeDecisionLog(database, utc_now, uuid4).record(
        ScopeDecisionRecord(session, "DENY", None, "RULE_FILTER", 2, "tr"), warehouse_consent=True
    )
    store = PostgresOutboxRelayStore(database, utc_now)
    [event] = store.pending(10)  # the relay read it (and consent) before ...
    memory.delete_project_data(PROJECT)  # ... the project was deleted
    sent: list[Any] = []

    assert store.publish_locked([event.id], sent.append) == 0
    assert sent == []


def test_a_send_longer_than_the_hold_loses_the_lock_but_marks_nothing_and_never_blocks_a_deletion(
    database: Database,
) -> None:
    """DB review P4.6 round 3: Postgres ends a relay session idle in its transaction for 4 s; the event stays pending
    and a waiting DeleteProjectData gets the row instead of failing on its 5 s lock_timeout."""
    memory = PostgresConversationMemory(database, WINDOW, utc_now, uuid4)
    session = memory.create_session(PROJECT, KEY, "tr").session.id
    PostgresScopeDecisionLog(database, utc_now, uuid4).record(
        ScopeDecisionRecord(session, "DENY", None, "RULE_FILTER", 2, "tr"), warehouse_consent=True
    )
    store = PostgresOutboxRelayStore(database, utc_now)
    [event] = store.pending(10)
    deletion: list[Any] = []

    def slow_send(_: tuple[Any, ...]) -> None:
        thread = threading.Thread(target=lambda: deletion.append(memory.delete_project_data(PROJECT)))
        thread.start()
        threading.Event().wait(4.5)
        thread.join(5)

    with pytest.raises(Exception):  # noqa: B017 - the server ended the session; the driver's error class varies
        store.publish_locked([event.id], slow_send)

    assert deletion and deletion[0].project_ref_deleted
    with database.engine.connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM outbox_event")).scalar_one() == 0
