"""The PostgreSQL memory adapters under failure and concurrency: atomicity, races, idempotency and KVKK deletion.

Atomicity is proven with a trigger the test installs as the migrator: it makes one INSERT fail in the middle of a use
case, and
the test then looks at what the transaction left behind (nothing may remain).
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import timedelta
from functools import partial
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import DBAPIError

from src.memory.long_term import KnowledgeChunk, KnowledgeDocument
from src.memory.memory_store import (
    Database,
    DatabaseConfig,
    PostgresAuditLog,
    PostgresCheckpointStore,
    PostgresConversationMemory,
    PostgresIdempotencyMaintenance,
    PostgresKnowledgeRepository,
    PostgresScopeDecisionLog,
    utc_now,
)
from src.memory.short_term import (
    ConversationWindow,
    Evidence,
    IdempotencyKey,
    ScopeDecisionRecord,
    SessionNotFoundError,
)
from tests.support.embedding import MODEL, BagOfWordsEmbedder

pytestmark = pytest.mark.postgres

PROJECT = UUID("00000000-0000-0000-0000-0000000000b1")
KEY = "a" * 64
OTHER_KEY = "b" * 64
WINDOW = ConversationWindow(max_messages=12, token_budget=3000, chars_per_token=4)


@pytest.fixture
def migrator(migrated_config: DatabaseConfig) -> Iterator[Engine]:
    engine = create_engine(make_url(migrated_config.migrator_url).set(password=migrated_config.migrator_password))
    yield engine
    engine.dispose()


@pytest.fixture
def conversation(database: Database) -> PostgresConversationMemory:
    return PostgresConversationMemory(database, WINDOW, utc_now, uuid4)


@pytest.fixture
def knowledge(database: Database) -> PostgresKnowledgeRepository:
    return PostgresKnowledgeRepository(database, utc_now, uuid4)


def count(database: Database, table: str, where: str = "true") -> int:
    with database.engine.connect() as connection:
        return int(connection.execute(text(f"SELECT count(*) FROM {table} WHERE {where}")).scalar_one())


@contextmanager
def failing_insert(migrator: Engine, table: str) -> Iterator[None]:
    """Every INSERT into `table` raises while the block runs (fault injection for the atomicity tests)."""
    with migrator.begin() as connection:
        connection.execute(
            text(
                "CREATE FUNCTION inject_failure() RETURNS trigger LANGUAGE plpgsql AS "
                "$$ BEGIN RAISE EXCEPTION 'injected failure'; END $$"
            )
        )
        connection.execute(
            text(f"CREATE TRIGGER inject BEFORE INSERT ON {table} FOR EACH ROW EXECUTE FUNCTION inject_failure()")
        )
    try:
        yield
    finally:
        with migrator.begin() as connection:
            connection.execute(text(f"DROP TRIGGER inject ON {table}"))
            connection.execute(text("DROP FUNCTION inject_failure()"))


def document(doc_key: str, text_value: str, *, sha: str = "b" * 64) -> KnowledgeDocument:
    return KnowledgeDocument(
        doc_key=doc_key,
        title=f"Not {doc_key}",
        source_url=None,
        source_type="INTERNAL",
        version_tag="v1",
        language="tr",
        applicability=(),
        content_sha256=sha,
        embedding_model=MODEL,
        chunk_chars=1200,
        chunk_overlap=100,
        chunks=(KnowledgeChunk(1, text_value, BagOfWordsEmbedder().embed([text_value]).vectors[0]),),
    )


def run_threads(jobs: Sequence[Callable[[], object]]) -> list[Any]:
    """Run the jobs together (a barrier releases them at once); return each result or the exception it raised."""
    barrier = threading.Barrier(len(jobs))
    results: list[Any] = [None] * len(jobs)

    def runner(index: int) -> None:
        barrier.wait()
        try:
            results[index] = jobs[index]()
        except Exception as exc:  # noqa: BLE001 - the test inspects every outcome
            results[index] = exc

    threads = [threading.Thread(target=runner, args=(index,)) for index in range(len(jobs))]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a use case did not finish (lock wait or deadlock)"
    return results


def deadlocks(database: Database) -> int:
    with database.engine.connect() as connection:
        return int(
            connection.execute(text("SELECT deadlocks FROM pg_stat_database WHERE datname = 'agent_db'")).scalar_one()
        )


# ---- atomicity ----


def test_a_failing_outbox_insert_rolls_back_the_scope_decision(
    database: Database, conversation: PostgresConversationMemory, migrator: Engine
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr").session.id
    log = PostgresScopeDecisionLog(database, utc_now, uuid4)
    decision = ScopeDecisionRecord(session, "ALLOW", 0.9, "SCOPE_CLASSIFIER", 10, "tr")

    with failing_insert(migrator, "outbox_event"), pytest.raises(DBAPIError):
        log.record(decision, warehouse_consent=True)

    assert count(database, "scope_decision") == 0
    assert count(database, "outbox_event") == 0
    assert log.record(decision, warehouse_consent=True).event_written is True  # the failure left nothing behind


def test_a_failing_evidence_insert_rolls_back_the_assistant_message(
    database: Database, conversation: PostgresConversationMemory, migrator: Engine
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr").session.id

    with failing_insert(migrator, "message_evidence"), pytest.raises(DBAPIError):
        conversation.append_assistant_message(session, "yanıt", (Evidence("CODE_LOCATION", "A.java:3"),))

    assert count(database, "chat_message") == 0
    assert conversation.append_user_message(session, "soru").ordinal == 1  # the ordinal was not consumed


def test_a_failing_audit_row_rolls_back_the_session_deletion(
    database: Database, conversation: PostgresConversationMemory, migrator: Engine
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr", IdempotencyKey("k1", "c" * 64)).session.id
    conversation.append_user_message(session, "soru")

    with failing_insert(migrator, "audit_log"), pytest.raises(DBAPIError):
        conversation.delete_session(session)

    assert conversation.get_session(session) is not None
    assert count(database, "chat_message") == 1
    assert count(database, "idempotency_record") == 1  # the idempotency record delete rolled back too
    assert count(database, "audit_log") == 0


def test_a_failing_audit_row_rolls_back_the_project_data_deletion(
    database: Database, conversation: PostgresConversationMemory, migrator: Engine
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr").session.id
    conversation.append_user_message(session, "soru")

    with failing_insert(migrator, "audit_log"), pytest.raises(DBAPIError):
        conversation.delete_project_data(PROJECT)

    assert count(database, "project_ref") == 1
    assert count(database, "chat_session") == 1
    assert count(database, "chat_message") == 1


def test_a_failing_chunk_insert_rolls_back_a_new_and_an_updated_document(
    database: Database, knowledge: PostgresKnowledgeRepository, migrator: Engine
) -> None:
    with failing_insert(migrator, "kb_chunk"), pytest.raises(DBAPIError):
        knowledge.upsert_document(document("yeni", "ilk metin"))
    assert count(database, "kb_document") == 0

    knowledge.upsert_document(document("var", "eski metin"))
    with failing_insert(migrator, "kb_chunk"), pytest.raises(DBAPIError):
        knowledge.upsert_document(document("var", "yeni metin", sha="c" * 64))

    # The update rolled back as a whole: the old digest and the old chunk are still there.
    assert count(database, "kb_document", "doc_key = 'var' AND content_sha256 = repeat('b', 64)") == 1
    assert count(database, "kb_chunk", "text = 'eski metin'") == 1


# ---- concurrency ----


def test_concurrent_appends_to_one_session_get_gapless_unique_ordinals(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr").session.id
    baseline = deadlocks(database)

    jobs = [partial(conversation.append_user_message, session, f"mesaj {n}") for n in range(24)]
    results = run_threads(jobs)

    assert not [r for r in results if isinstance(r, Exception)], results
    ordinals = sorted(message.ordinal for message in results)
    assert ordinals == list(range(1, 25))
    assert deadlocks(database) == baseline
    assert database.retries == 0  # a deadlock would have been retried silently once


def test_deleting_a_session_while_messages_arrive_loses_nothing_and_never_deadlocks(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    baseline = deadlocks(database)
    for round_number in range(8):
        session = conversation.create_session(PROJECT, KEY, "tr").session.id
        jobs: list[Callable[[], object]] = [partial(conversation.append_user_message, session, "x") for _ in range(4)]
        jobs.append(partial(conversation.delete_session, session))

        results = run_threads(jobs)

        unexpected = [r for r in results if isinstance(r, Exception) and not isinstance(r, SessionNotFoundError)]
        assert not unexpected, (round_number, unexpected)
        assert conversation.get_session(session) is None
        assert count(database, "chat_message", f"session_id = '{session}'") == 0
    assert count(database, "audit_log", "action_code = 'SESSION_DELETED'") == 8
    assert deadlocks(database) == baseline
    assert database.retries == 0  # a deadlock would have been retried silently once


def test_project_data_deletion_races_with_new_sessions_messages_and_decisions_without_deadlock(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    log = PostgresScopeDecisionLog(database, utc_now, uuid4)
    baseline = deadlocks(database)
    for _ in range(8):
        existing = conversation.create_session(PROJECT, KEY, "tr").session.id
        decision = ScopeDecisionRecord(existing, "ALLOW", 0.8, "SCOPE_CLASSIFIER", 5, "tr")
        jobs: list[Callable[[], object]] = [
            partial(conversation.delete_project_data, PROJECT),
            partial(conversation.create_session, PROJECT, KEY, "en"),
            partial(conversation.append_user_message, existing, "soru"),
            partial(log.record, decision, warehouse_consent=True),
        ]

        results = run_threads(jobs)

        unexpected = [r for r in results if isinstance(r, Exception) and not isinstance(r, SessionNotFoundError)]
        assert not unexpected, unexpected
        conversation.delete_project_data(PROJECT)  # leave the project clean for the next round
    assert deadlocks(database) == baseline
    assert database.retries == 0  # a deadlock would have been retried silently once


def test_concurrent_upserts_of_one_document_create_it_once(
    database: Database, knowledge: PostgresKnowledgeRepository
) -> None:
    jobs = [lambda: knowledge.upsert_document(document("ortak", "ayni metin")) for _ in range(6)]

    results = run_threads(jobs)

    assert not [r for r in results if isinstance(r, Exception)], results
    assert sorted(r.action for r in results) == ["created"] + ["unchanged"] * 5
    assert count(database, "kb_document", "doc_key = 'ortak'") == 1
    assert count(database, "kb_chunk") == 1


def test_one_idempotency_key_used_concurrently_opens_exactly_one_session(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    key = IdempotencyKey("ayni-anahtar", "d" * 64)
    jobs = [lambda: conversation.create_session(PROJECT, KEY, "tr", key) for _ in range(6)]

    results = run_threads(jobs)

    assert not [r for r in results if isinstance(r, Exception)], results
    assert len({r.session.id for r in results}) == 1
    assert sorted(r.replayed for r in results) == [False] + [True] * 5
    assert count(database, "chat_session") == 1


# ---- KVKK deletion ----


def test_deleting_a_session_keeps_the_anonymous_audit_trail(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr").session.id
    conversation.append_user_message(session, "soru")
    conversation.append_assistant_message(session, "yanıt", (Evidence("CODE_LOCATION", "A.java:3"),))
    audit = PostgresAuditLog(database, utc_now, uuid4)
    run = audit.start_run(session, "MESSAGE", "1" * 32)
    PostgresScopeDecisionLog(database, utc_now, uuid4).record(
        ScopeDecisionRecord(session, "ALLOW", 0.9, "SCOPE_CLASSIFIER", 5, "tr"), warehouse_consent=True
    )

    conversation.delete_session(session)

    assert count(database, "chat_message") == 0
    assert count(database, "message_evidence") == 0
    assert count(database, "agent_run", f"id = '{run}' AND session_id IS NULL") == 1
    assert count(database, "scope_decision", "session_id IS NULL") == 1
    assert count(database, "outbox_event") == 1  # an anonymous event may already be on its way (D-225)
    assert count(database, "audit_log", f"action_code = 'SESSION_DELETED' AND project_key = '{KEY}'") == 1


def test_deleting_project_data_removes_pending_events_of_that_key_only(
    database: Database, conversation: PostgresConversationMemory, migrator: Engine
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr").session.id
    PostgresScopeDecisionLog(database, utc_now, uuid4).record(
        ScopeDecisionRecord(session, "ALLOW", 0.9, "SCOPE_CLASSIFIER", 5, "tr"), warehouse_consent=True
    )
    with migrator.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO outbox_event (id, event_type, schema_version, project_key, occurred_at, payload, "
                "published_at) VALUES (gen_random_uuid(), 'scope_decision', 1, :key, now(), '{}', NULL), "
                "(gen_random_uuid(), 'scope_decision', 1, :key, now() - interval '1 minute', '{}', now())"
            ),
            {"key": OTHER_KEY},
        )
        connection.execute(
            text(
                "INSERT INTO outbox_event (id, event_type, schema_version, project_key, occurred_at, payload, "
                "published_at) VALUES (gen_random_uuid(), 'scope_decision', 1, :key, now() - interval '1 minute', "
                "'{}', now())"
            ),
            {"key": KEY},
        )

    result = conversation.delete_project_data(PROJECT)

    assert (result.sessions_deleted, result.outbox_events_deleted, result.project_ref_deleted) == (1, 1, True)
    assert count(database, "outbox_event", f"project_key = '{OTHER_KEY}'") == 2
    assert count(database, "outbox_event", f"project_key = '{KEY}'") == 1  # a published row is not pending
    assert count(database, "audit_log", "action_code = 'PROJECT_DATA_DELETED'") == 1


def test_purging_idempotency_records_removes_only_the_expired_ones(
    database: Database, conversation: PostgresConversationMemory, migrator: Engine
) -> None:
    conversation.create_session(PROJECT, KEY, "tr", IdempotencyKey("taze", "e" * 64))
    with migrator.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO idempotency_record (idempotency_key, operation, request_sha256, status_code, resource_id, "
                "created_at) VALUES ('eski', 'CREATE_SESSION', repeat('f', 64), 201, NULL, now() - interval '25 hours')"
            )
        )

    removed = PostgresIdempotencyMaintenance(database, utc_now).purge_idempotency_records()

    assert removed == 1
    assert count(database, "idempotency_record") == 1
    assert count(database, "idempotency_record", "idempotency_key = 'taze'") == 1


def test_a_purge_with_a_clock_a_day_ahead_removes_fresh_records_too(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    conversation.create_session(PROJECT, KEY, "tr", IdempotencyKey("taze", "e" * 64))
    later = PostgresIdempotencyMaintenance(database, lambda: utc_now() + timedelta(hours=25))

    assert later.purge_idempotency_records() == 1
    assert count(database, "idempotency_record") == 0


def test_deleting_a_session_and_the_whole_project_at_once_never_deadlocks(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    # Both use cases lock the session first and its idempotency record second (the order DeleteProjectData once broke).
    for round_number in range(10):
        keys = [IdempotencyKey(f"anahtar-{round_number}-{n}", f"{n}".rjust(64, "e")) for n in range(3)]
        sessions = [conversation.create_session(PROJECT, KEY, "tr", key).session.id for key in keys]
        jobs: list[Callable[[], object]] = [partial(conversation.delete_session, s) for s in sessions]
        jobs.append(partial(conversation.delete_project_data, PROJECT))

        results = run_threads(jobs)

        unexpected = [r for r in results if isinstance(r, Exception) and not isinstance(r, SessionNotFoundError)]
        assert not unexpected, (round_number, unexpected)
        conversation.delete_project_data(PROJECT)
        assert count(database, "idempotency_record") == 0
    assert database.retries == 0


def test_deleting_project_data_removes_everything_that_belongs_to_the_project_and_keeps_the_anonymous_trail(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr", IdempotencyKey("proje-anahtari", "a" * 64)).session.id
    conversation.append_user_message(session, "soru")
    conversation.append_assistant_message(session, "yanıt", (Evidence("CODE_LOCATION", "A.java:3"),))
    run = PostgresAuditLog(database, utc_now, uuid4).start_run(session, "MESSAGE", "2" * 32)
    PostgresScopeDecisionLog(database, utc_now, uuid4).record(
        ScopeDecisionRecord(session, "ALLOW", 0.9, "SCOPE_CLASSIFIER", 5, "tr"), warehouse_consent=True
    )
    PostgresCheckpointStore(database, utc_now).put(session, uuid4(), "msgpack", b"\x81")

    result = conversation.delete_project_data(PROJECT)

    assert (result.sessions_deleted, result.outbox_events_deleted, result.project_ref_deleted) == (1, 1, True)
    tables = (
        "project_ref",
        "chat_session",
        "chat_message",
        "message_evidence",
        "idempotency_record",
        "outbox_event",
        "graph_checkpoint",
    )
    for table in tables:
        assert count(database, table) == 0, table
    assert count(database, "agent_run", f"id = '{run}' AND session_id IS NULL") == 1
    assert count(database, "scope_decision", "session_id IS NULL") == 1
    assert count(database, "audit_log", f"action_code = 'PROJECT_DATA_DELETED' AND project_key = '{KEY}'") == 1
    # The same key may be used again afterwards: nothing of the old project blocks it.
    assert conversation.create_session(PROJECT, KEY, "tr", IdempotencyKey("proje-anahtari", "a" * 64)).replayed is False


def test_the_rolled_back_project_deletion_keeps_the_pending_event_and_the_idempotency_record(
    database: Database, conversation: PostgresConversationMemory, migrator: Engine
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr", IdempotencyKey("kalsin", "b" * 64)).session.id
    PostgresScopeDecisionLog(database, utc_now, uuid4).record(
        ScopeDecisionRecord(session, "ALLOW", 0.9, "SCOPE_CLASSIFIER", 5, "tr"), warehouse_consent=True
    )
    PostgresCheckpointStore(database, utc_now).put(session, uuid4(), "msgpack", b"\x81")

    with failing_insert(migrator, "audit_log"), pytest.raises(DBAPIError):
        conversation.delete_project_data(PROJECT)

    assert count(database, "outbox_event") == 1
    assert count(database, "idempotency_record") == 1
    assert count(database, "project_ref") == 1
    assert count(database, "graph_checkpoint") == 1


def test_the_outbox_payload_equals_the_stored_decision_and_fits_the_event_contract(database: Database) -> None:
    log = PostgresScopeDecisionLog(database, utc_now, uuid4)
    conversation = PostgresConversationMemory(database, WINDOW, utc_now, uuid4)
    session = conversation.create_session(PROJECT, KEY, "en").session.id

    log.record(ScopeDecisionRecord(session, "ALLOW", 0.12345, "SCOPE_CLASSIFIER", 7, "en"), warehouse_consent=True)
    log.record(ScopeDecisionRecord(session, "DENY", None, "RULE_FILTER", 1, "en"), warehouse_consent=True)

    with database.engine.connect() as connection:
        rows = connection.execute(text("SELECT payload FROM outbox_event ORDER BY occurred_at, id"))
        payloads = [row[0] for row in rows]
        query = "SELECT confidence FROM scope_decision WHERE confidence IS NOT NULL"
        stored = float(connection.execute(text(query)).scalar_one())
    assert stored == 0.1235  # numeric(5,4), rounded half up
    by_ring = {p["deciding_ring"]: p for p in payloads}
    assert by_ring["SCOPE_CLASSIFIER"]["confidence"] == stored
    assert by_ring["RULE_FILTER"]["confidence"] is None
    for payload in payloads:
        assert set(payload) == {"decision", "confidence", "deciding_ring", "latency_ms", "language"}
        assert payload["decision"] in ("ALLOW", "DENY") and payload["language"] in ("tr", "en")
        assert isinstance(payload["latency_ms"], int) and payload["latency_ms"] >= 0


def test_a_database_error_message_never_carries_the_bound_values(database: Database) -> None:
    marker = "gizli-sohbet-metni-12345"

    with pytest.raises(DBAPIError) as caught, database.engine.begin() as connection:
        connection.execute(text("INSERT INTO message_role VALUES (:code, 'x', 9)"), {"code": marker})

    assert marker not in str(caught.value) and marker not in repr(caught.value)


def test_a_run_for_a_missing_session_is_a_session_not_found_error(database: Database) -> None:
    audit = PostgresAuditLog(database, utc_now, uuid4)

    with pytest.raises(SessionNotFoundError):
        audit.start_run(uuid4(), "MESSAGE", "3" * 32)


def test_a_request_behind_a_stuck_lock_gives_up_after_the_lock_timeout(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    session = conversation.create_session(PROJECT, KEY, "tr").session.id

    with database.engine.begin() as holder:
        holder.execute(text("SELECT id FROM chat_session WHERE id = :id FOR UPDATE"), {"id": session})
        with pytest.raises(DBAPIError) as caught:
            conversation.append_user_message(session, "bekleyen")

    assert getattr(caught.value.orig, "sqlstate", None) == "55P03"  # lock_not_available, not retried
    assert database.retries == 0
    assert conversation.append_user_message(session, "sonra").ordinal == 1


# ---- graph checkpoints (P4.6, D-253; acid-3nf-database §7.4) ----


def test_checkpoint_writes_racing_a_session_deletion_never_deadlock(
    database: Database, conversation: PostgresConversationMemory
) -> None:
    store = PostgresCheckpointStore(database, utc_now)
    baseline = deadlocks(database)
    for round_number in range(8):
        session = conversation.create_session(PROJECT, KEY, "tr").session.id
        store.put(session, uuid4(), "msgpack", b"first")  # half the writes take the update path
        jobs: list[Callable[[], object]] = [partial(store.put, session, uuid4(), "msgpack", b"next") for _ in range(3)]
        jobs.append(partial(conversation.delete_session, session))

        results = run_threads(jobs)

        unexpected = [r for r in results if isinstance(r, Exception) and not isinstance(r, SessionNotFoundError)]
        assert not unexpected, (round_number, unexpected)
        assert count(database, "graph_checkpoint", f"session_id = '{session}'") == 0  # gone with its session
    assert deadlocks(database) == baseline
    assert database.retries == 0


def test_the_purge_skips_a_locked_checkpoint_and_never_deletes_a_fresh_one(
    database: Database, conversation: PostgresConversationMemory, migrator: Engine
) -> None:
    store = PostgresCheckpointStore(database, utc_now)
    locked = conversation.create_session(PROJECT, KEY, "tr").session.id
    fresh = conversation.create_session(PROJECT, KEY, "tr").session.id
    store.put(locked, uuid4(), "msgpack", b"old")
    store.put(fresh, uuid4(), "msgpack", b"new")
    with migrator.begin() as connection:
        connection.execute(
            text("UPDATE graph_checkpoint SET updated_at = updated_at - interval '2 days' WHERE session_id = :s"),
            {"s": locked},
        )

    holder = database.engine.connect()
    transaction = holder.begin()
    holder.execute(text("SELECT 1 FROM graph_checkpoint WHERE session_id = :s FOR UPDATE"), {"s": locked})
    try:
        assert store.purge_idle() == 0  # the locked row is skipped (SKIP LOCKED), not waited for
    finally:
        transaction.rollback()
        holder.close()

    assert store.purge_idle() == 1
    assert count(database, "graph_checkpoint", f"session_id = '{fresh}'") == 1


def test_a_checkpoint_that_fails_its_digest_is_ignored(
    database: Database, conversation: PostgresConversationMemory, migrator: Engine
) -> None:
    store = PostgresCheckpointStore(database, utc_now)
    session = conversation.create_session(PROJECT, KEY, "tr").session.id
    store.put(session, uuid4(), "msgpack", b"genuine")
    with migrator.begin() as connection:
        connection.execute(
            text("UPDATE graph_checkpoint SET state = decode('ff', 'hex') WHERE session_id = :s"), {"s": session}
        )

    assert store.get(session) is None
