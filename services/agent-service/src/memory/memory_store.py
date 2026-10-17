"""Postgres adapters of the memory ports (D-08): SQLAlchemy Core and psycopg 3. The only module with SQL.

Every write is one transaction (`Database.run`): lock order, SQL patterns and isolation follow
docs/data/agent_db-transactions.md. Network calls (embedding, core-service) happen before a transaction, never inside
it.
`Clock` and the id generator are injected so tests are deterministic. Chat text is never logged and never put into an
error message.
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, TypeVar
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import URL, Row, make_url
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError

from src.memory.long_term import (
    Fingerprint,
    KbHit,
    KnowledgeDocument,
    RuntimeVersions,
    SourceType,
    UpsertOutcome,
)
from src.memory.short_term import (
    TRACE_ID,
    ChatMessage,
    ChatSession,
    Clock,
    ConversationWindow,
    DuplicateRecordError,
    Evidence,
    FinalRunStatus,
    IdempotencyConflictError,
    IdempotencyKey,
    IdGenerator,
    InvalidRecordError,
    Language,
    MemoryStoreError,
    MessagePage,
    ProjectDataDeletion,
    ProjectKeyMismatchError,
    Role,
    RunNotFoundError,
    RunNotRunningError,
    RunStatus,
    RunSummary,
    RunTrigger,
    ScopeDecisionRecord,
    ScopeDecisionResult,
    SessionCreated,
    SessionNotFoundError,
    StepRecord,
    trim_to_window,
)

_LOG = logging.getLogger("src.memory")

T = TypeVar("T")

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
_RETRYABLE_SQLSTATES = frozenset({"40P01", "40001"})
# A request waits at most 5 s for a row lock and a statement runs at most 30 s: a stuck transaction cannot hang callers.
_SESSION_OPTIONS = "-c lock_timeout=5000 -c statement_timeout=30000"
_IDEMPOTENCY_TTL = timedelta(hours=24)
_PROVISIONAL_STATUS = 202
_PROJECT_REF_ATTEMPTS = 3


def utc_now() -> datetime:
    return datetime.now(UTC)


# ---- database ----


@dataclass(frozen=True)
class DatabaseConfig:
    """Plain connection values (the adapter does not import the application settings, agent-service-layout section 3).

    The URLs carry no password; the passwords stay out of `repr` and logs.
    """

    url: str
    migrator_url: str
    pool_size: int
    connect_timeout_s: int
    app_password: str = field(repr=False)
    migrator_password: str = field(repr=False)


class Database:
    """The agent_db engine (lazy: no connection until used) and the transaction runner.

    `run` executes the work in one transaction at the default READ COMMITTED level and retries it once after a
    deadlock or
    serialization failure (`40P01`, `40001`; core D-157 analogue).
    """

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config
        self._retries = 0
        self._retry_lock = threading.Lock()
        app_url = make_url(config.url).set(password=config.app_password)
        self._engine = create_engine(
            app_url,
            pool_size=config.pool_size,
            pool_pre_ping=True,
            # A database error message must never carry bound values (chat text, evidence, idempotency keys).
            hide_parameters=True,
            isolation_level="READ COMMITTED",
            connect_args={"connect_timeout": config.connect_timeout_s, "options": _SESSION_OPTIONS},
        )

    @property
    def engine(self) -> Engine:
        return self._engine

    @property
    def retries(self) -> int:
        """How many transactions were repeated after a deadlock or serialization failure (tests assert 0)."""
        with self._retry_lock:
            return self._retries

    def run(self, work: Callable[[Connection], T]) -> T:
        attempts = 0
        while True:
            attempts += 1
            try:
                with self._engine.begin() as connection:
                    return work(connection)
            except DBAPIError as exc:
                if attempts < 2 and _sqlstate(exc) in _RETRYABLE_SQLSTATES:
                    _LOG.warning("Transaction retried after SQLSTATE %s", _sqlstate(exc))
                    with self._retry_lock:
                        self._retries += 1
                    continue
                raise

    def is_ready(self) -> bool:
        try:
            with self._engine.connect() as connection:
                connection.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return False
        return True

    def migrate(self) -> None:
        apply_migrations(self._config)

    def close(self) -> None:
        self._engine.dispose()


class DatabaseReadiness:
    """`ReadinessCheck`: the service is not ready while agent_db cannot be reached (NFR-05; LLM status is separate)."""

    name = "database"

    def __init__(self, database: Database) -> None:
        self._database = database

    def is_ready(self) -> bool:
        return self._database.is_ready()


def apply_migrations(config_: DatabaseConfig) -> None:
    """Run `alembic upgrade head` as the migrator role. A failed migration raises and the service does not start."""
    url: URL = make_url(config_.migrator_url).set(password=config_.migrator_password)
    alembic_config = Config()
    alembic_config.set_main_option("script_location", str(MIGRATIONS_DIR))
    alembic_config.attributes["sqlalchemy_url"] = url
    command.upgrade(alembic_config, "head")


def _sqlstate(exc: DBAPIError) -> str | None:
    state = getattr(exc.orig, "sqlstate", None)
    return state if isinstance(state, str) else None


def _constraint(exc: IntegrityError) -> str:
    diag = getattr(exc.orig, "diag", None)
    name = getattr(diag, "constraint_name", None)
    return name if isinstance(name, str) else ""


def _vector_literal(values: Sequence[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def _as_ids(rows: Sequence[Row[Any]]) -> list[UUID]:
    return [row[0] for row in rows]


# ---- conversation ----


class PostgresConversationMemory:
    def __init__(self, database: Database, window: ConversationWindow, clock: Clock, new_id: IdGenerator) -> None:
        self._db = database
        self._window = window
        self._clock = clock
        self._new_id = new_id

    # -- sessions --

    def create_session(
        self, project_id: UUID, project_key: str, language: Language, idempotency: IdempotencyKey | None = None
    ) -> SessionCreated:
        if not _is_project_key(project_key):
            raise InvalidRecordError("project_key must be 64 lowercase hexadecimal digits")
        session_id = self._new_id()
        now = self._clock()

        def work(conn: Connection) -> SessionCreated:
            if idempotency is not None:
                replay = self._reserve(conn, idempotency, now)
                if replay is not None:
                    return replay
            stored = self._register_project(conn, project_id, project_key, now)
            if stored != project_key:
                raise ProjectKeyMismatchError("the project id is already registered with a different project key")
            conn.execute(
                text("INSERT INTO chat_session (id, project_id, language, created_at) VALUES (:id, :pid, :lang, :now)"),
                {"id": session_id, "pid": project_id, "lang": language, "now": now},
            )
            if idempotency is not None:
                conn.execute(
                    text(
                        "UPDATE idempotency_record SET status_code = 201, resource_id = :sid "
                        "WHERE idempotency_key = :key AND operation = 'CREATE_SESSION'"
                    ),
                    {"sid": session_id, "key": idempotency.key},
                )
            return SessionCreated(ChatSession(session_id, project_id, language, now), replayed=False)

        return self._db.run(work)

    @staticmethod
    def _register_project(conn: Connection, project_id: UUID, project_key: str, now: datetime) -> str:
        """Make sure `project_ref` has the project and hold a key-share lock on it; return the stored key.

        A concurrent `DeleteProjectData` can remove the row between the insert (which then saw a conflict) and the
        lock: READ COMMITTED gives the next statement a fresh snapshot, so the insert is simply tried again.
        """
        for _ in range(_PROJECT_REF_ATTEMPTS):
            conn.execute(
                text(
                    "INSERT INTO project_ref (project_id, project_key, created_at) VALUES (:pid, :key, :now) "
                    "ON CONFLICT (project_id) DO NOTHING"
                ),
                {"pid": project_id, "key": project_key, "now": now},
            )
            stored = conn.execute(
                text("SELECT project_key FROM project_ref WHERE project_id = :pid FOR KEY SHARE"), {"pid": project_id}
            ).scalar_one_or_none()
            if stored is not None:
                return str(stored)
        raise MemoryStoreError("the project reference was deleted again and again while the session was created")

    def _reserve(self, conn: Connection, idempotency: IdempotencyKey, now: datetime) -> SessionCreated | None:
        """Write the provisional idempotency record; return the earlier result when the key was used before."""
        inserted = conn.execute(
            text(
                "INSERT INTO idempotency_record (idempotency_key, operation, request_sha256, status_code, resource_id, "
                "created_at) VALUES (:key, 'CREATE_SESSION', :sha, :status, NULL, :now) "
                "ON CONFLICT (idempotency_key, operation) DO NOTHING"
            ),
            {"key": idempotency.key, "sha": idempotency.request_sha256, "status": _PROVISIONAL_STATUS, "now": now},
        ).rowcount
        if inserted == 1:
            return None
        row = conn.execute(
            text(
                "SELECT request_sha256, resource_id FROM idempotency_record "
                "WHERE idempotency_key = :key AND operation = 'CREATE_SESSION'"
            ),
            {"key": idempotency.key},
        ).one()
        if row.request_sha256 != idempotency.request_sha256:
            raise IdempotencyConflictError("the idempotency key was used with a different request")
        session = self._select_session(conn, row.resource_id) if row.resource_id is not None else None
        if session is None:
            raise IdempotencyConflictError("the idempotency key belongs to a request that did not complete")
        return SessionCreated(session, replayed=True)

    def get_session(self, session_id: UUID) -> ChatSession | None:
        return self._db.run(lambda conn: self._select_session(conn, session_id))

    @staticmethod
    def _select_session(conn: Connection, session_id: UUID) -> ChatSession | None:
        row = conn.execute(
            text("SELECT id, project_id, language, created_at FROM chat_session WHERE id = :id"), {"id": session_id}
        ).first()
        return None if row is None else ChatSession(row.id, row.project_id, row.language, row.created_at)

    def delete_session(self, session_id: UUID) -> None:
        now = self._clock()
        audit_id = self._new_id()

        def work(conn: Connection) -> None:
            row = conn.execute(
                text("SELECT project_id FROM chat_session WHERE id = :id FOR UPDATE"), {"id": session_id}
            ).first()
            if row is None:
                raise SessionNotFoundError("the session does not exist")
            key = conn.execute(
                text("SELECT project_key FROM project_ref WHERE project_id = :pid"), {"pid": row.project_id}
            ).scalar_one()
            conn.execute(
                text("DELETE FROM idempotency_record WHERE operation = 'CREATE_SESSION' AND resource_id = :id"),
                {"id": session_id},
            )
            conn.execute(text("DELETE FROM chat_session WHERE id = :id"), {"id": session_id})
            self._audit(conn, audit_id, now, "SESSION_DELETED", key)

        self._db.run(work)

    def delete_project_data(self, project_id: UUID) -> ProjectDataDeletion:
        now = self._clock()
        audit_id = self._new_id()

        def work(conn: Connection) -> ProjectDataDeletion:
            key = conn.execute(
                text("SELECT project_key FROM project_ref WHERE project_id = :pid FOR UPDATE"), {"pid": project_id}
            ).scalar_one_or_none()
            if key is None:
                return ProjectDataDeletion(0, 0, project_ref_deleted=False)
            # The sessions are locked first (in id order), then their idempotency records: the same order as
            # DeleteSession (chat_session, then idempotency_record), so the two never wait for each other.
            session_ids = [
                row.id
                for row in conn.execute(
                    text("SELECT id FROM chat_session WHERE project_id = :pid ORDER BY id FOR UPDATE"),
                    {"pid": project_id},
                )
            ]
            conn.execute(
                text(
                    "DELETE FROM idempotency_record WHERE operation = 'CREATE_SESSION' "
                    "AND resource_id = ANY(CAST(:ids AS uuid[]))"
                ),
                {"ids": session_ids},
            )
            sessions = conn.execute(
                text("DELETE FROM chat_session WHERE project_id = :pid"), {"pid": project_id}
            ).rowcount
            events = conn.execute(
                text("DELETE FROM outbox_event WHERE project_key = :key AND published_at IS NULL"), {"key": key}
            ).rowcount
            conn.execute(text("DELETE FROM project_ref WHERE project_id = :pid"), {"pid": project_id})
            self._audit(conn, audit_id, now, "PROJECT_DATA_DELETED", key)
            return ProjectDataDeletion(sessions, events, project_ref_deleted=True)

        return self._db.run(work)

    @staticmethod
    def _audit(conn: Connection, audit_id: UUID, now: datetime, action: str, project_key: str) -> None:
        conn.execute(
            text("INSERT INTO audit_log (id, occurred_at, action_code, project_key) VALUES (:id, :now, :action, :key)"),
            {"id": audit_id, "now": now, "action": action, "key": project_key},
        )

    # -- messages --

    def append_user_message(self, session_id: UUID, content: str) -> ChatMessage:
        return self._append(session_id, "USER", content, ())

    def append_assistant_message(
        self, session_id: UUID, content: str, evidence: Sequence[Evidence] = ()
    ) -> ChatMessage:
        return self._append(session_id, "ASSISTANT", content, tuple(evidence))

    def _append(self, session_id: UUID, role: Role, content: str, evidence: tuple[Evidence, ...]) -> ChatMessage:
        if not content or "\x00" in content:
            raise InvalidRecordError("a message needs content without NUL characters")
        message_id = self._new_id()
        now = self._clock()

        def work(conn: Connection) -> ChatMessage:
            # FOR NO KEY UPDATE serializes appends and conflicts with DeleteSession's FOR UPDATE, but not with the
            # FOR KEY SHARE of a foreign-key check (StartRun, RecordScopeDecision in the same session).
            locked = conn.execute(
                text("SELECT id FROM chat_session WHERE id = :id FOR NO KEY UPDATE"), {"id": session_id}
            ).first()
            if locked is None:
                raise SessionNotFoundError("the session does not exist")
            ordinal = conn.execute(
                text("SELECT coalesce(max(ordinal), 0) + 1 FROM chat_message WHERE session_id = :id"),
                {"id": session_id},
            ).scalar_one()
            conn.execute(
                text(
                    "INSERT INTO chat_message (id, session_id, ordinal, role, content, created_at) "
                    "VALUES (:id, :sid, :ordinal, :role, :content, :now)"
                ),
                {"id": message_id, "sid": session_id, "ordinal": ordinal, "role": role, "content": content, "now": now},
            )
            if evidence:
                conn.execute(
                    text(
                        "INSERT INTO message_evidence (message_id, ordinal, kind, reference, source_version) "
                        "VALUES (:mid, :ordinal, :kind, :reference, :version)"
                    ),
                    [
                        {
                            "mid": message_id,
                            "ordinal": index,
                            "kind": item.kind,
                            "reference": item.reference,
                            "version": item.source_version,
                        }
                        for index, item in enumerate(evidence, start=1)
                    ],
                )
            return ChatMessage(message_id, session_id, ordinal, role, content, now, evidence)

        return self._db.run(work)

    def list_messages(self, session_id: UUID, page: int, size: int) -> MessagePage:
        if page < 0 or not 1 <= size <= 200:
            raise InvalidRecordError("page must be 0 or more and size between 1 and 200")

        def work(conn: Connection) -> MessagePage:
            if self._select_session(conn, session_id) is None:
                raise SessionNotFoundError("the session does not exist")
            total = conn.execute(
                text("SELECT count(*) FROM chat_message WHERE session_id = :id"), {"id": session_id}
            ).scalar_one()
            rows = conn.execute(
                text(
                    "SELECT id, session_id, ordinal, role, content, created_at FROM chat_message "
                    "WHERE session_id = :id ORDER BY ordinal LIMIT :size OFFSET :offset"
                ),
                {"id": session_id, "size": size, "offset": page * size},
            ).all()
            evidence = self._evidence(conn, _as_ids(rows))
            items = tuple(
                ChatMessage(r.id, r.session_id, r.ordinal, r.role, r.content, r.created_at, evidence.get(r.id, ()))
                for r in rows
            )
            return MessagePage(items, page, size, total)

        return self._db.run(work)

    @staticmethod
    def _evidence(conn: Connection, message_ids: list[UUID]) -> dict[UUID, tuple[Evidence, ...]]:
        if not message_ids:
            return {}
        rows = conn.execute(
            text(
                "SELECT message_id, kind, reference, source_version FROM message_evidence "
                "WHERE message_id = ANY(:ids) ORDER BY message_id, ordinal"
            ),
            {"ids": message_ids},
        ).all()
        grouped: dict[UUID, list[Evidence]] = {}
        for row in rows:
            grouped.setdefault(row.message_id, []).append(Evidence(row.kind, row.reference, row.source_version))
        return {key: tuple(value) for key, value in grouped.items()}

    def recent_messages(self, session_id: UUID) -> tuple[ChatMessage, ...]:
        def work(conn: Connection) -> tuple[ChatMessage, ...]:
            if self._select_session(conn, session_id) is None:
                raise SessionNotFoundError("the session does not exist")
            rows = conn.execute(
                text(
                    "SELECT id, session_id, ordinal, role, content, created_at FROM chat_message "
                    "WHERE session_id = :id ORDER BY ordinal DESC LIMIT :n"
                ),
                {"id": session_id, "n": self._window.max_messages},
            ).all()
            messages = [ChatMessage(r.id, r.session_id, r.ordinal, r.role, r.content, r.created_at) for r in rows]
            messages.reverse()
            return trim_to_window(messages, self._window)

        return self._db.run(work)


def _is_project_key(value: str) -> bool:
    return len(value) == 64 and all(c in "0123456789abcdef" for c in value)


# ---- audit ----


class PostgresAuditLog:
    def __init__(self, database: Database, clock: Clock, new_id: IdGenerator) -> None:
        self._db = database
        self._clock = clock
        self._new_id = new_id

    def start_run(self, session_id: UUID | None, trigger: RunTrigger, trace_id: str) -> UUID:
        if not TRACE_ID.fullmatch(trace_id):
            raise InvalidRecordError("trace_id must be 32 lowercase hexadecimal digits")
        run_id = self._new_id()
        now = self._clock()

        def work(conn: Connection) -> UUID:
            conn.execute(
                text(
                    "INSERT INTO agent_run (id, session_id, run_trigger, trace_id, status, started_at, finished_at) "
                    "VALUES (:id, :sid, :trigger, :trace, 'RUNNING', :now, NULL)"
                ),
                {"id": run_id, "sid": session_id, "trigger": trigger, "trace": trace_id, "now": now},
            )
            return run_id

        return self._run_integrity(work)

    def record_step(self, step: StepRecord) -> UUID:
        step_id = self._new_id()

        def work(conn: Connection) -> UUID:
            conn.execute(
                text(
                    "INSERT INTO agent_step (id, run_id, ordinal, step_name, agent_code, status, duration_ms, "
                    "prompt_tokens, completion_tokens, started_at) VALUES (:id, :run, :ordinal, :name, :agent, "
                    ":status, "
                    ":duration, :prompt, :completion, :started)"
                ),
                {
                    "id": step_id,
                    "run": step.run_id,
                    "ordinal": step.ordinal,
                    "name": step.step_name,
                    "agent": step.agent_code,
                    "status": step.status,
                    "duration": step.duration_ms,
                    "prompt": step.prompt_tokens,
                    "completion": step.completion_tokens,
                    "started": step.started_at,
                },
            )
            if step.tool_calls:
                # Metadata only: no arguments, no output (NFR-09, D-229).
                conn.execute(
                    text(
                        "INSERT INTO tool_call (id, step_id, tool_code, status, duration_ms, called_at) "
                        "VALUES (:id, :step, :tool, :status, :duration, :called)"
                    ),
                    [
                        {
                            "id": call.id,
                            "step": step_id,
                            "tool": call.tool_code,
                            "status": call.status,
                            "duration": call.duration_ms,
                            "called": call.called_at,
                        }
                        for call in step.tool_calls
                    ],
                )
            return step_id

        return self._run_integrity(work)

    def finish_run(self, run_id: UUID, status: FinalRunStatus) -> None:
        if status not in ("COMPLETED", "FAILED", "STOPPED", "BUDGET_EXCEEDED"):
            raise InvalidRecordError("a run is finished with COMPLETED, FAILED, STOPPED or BUDGET_EXCEEDED")
        now = self._clock()

        def work(conn: Connection) -> None:
            changed = conn.execute(
                text("UPDATE agent_run SET status = :status, finished_at = :now WHERE id = :id AND status = 'RUNNING'"),
                {"status": status, "now": now, "id": run_id},
            ).rowcount
            if changed == 0:
                raise RunNotRunningError("the run is already finished or does not exist")

        self._db.run(work)

    def list_runs_by_trace(self, trace_id: str) -> tuple[RunSummary, ...]:
        if not TRACE_ID.fullmatch(trace_id):
            raise InvalidRecordError("trace_id must be 32 lowercase hexadecimal digits")

        def work(conn: Connection) -> tuple[RunSummary, ...]:
            rows = conn.execute(
                text(
                    "SELECT id, session_id, run_trigger, trace_id, status, started_at, finished_at FROM agent_run "
                    "WHERE trace_id = :trace ORDER BY started_at, id"
                ),
                {"trace": trace_id},
            ).all()
            return tuple(
                RunSummary(
                    r.id,
                    r.session_id,
                    r.run_trigger,
                    r.trace_id,
                    _run_status(r.status),
                    r.started_at,
                    r.finished_at,
                )
                for r in rows
            )

        return self._db.run(work)

    def _run_integrity(self, work: Callable[[Connection], T]) -> T:
        try:
            return self._db.run(work)
        except IntegrityError as exc:
            name = _constraint(exc)
            if name == "fk_agent_step_run":
                raise RunNotFoundError("the run does not exist") from None
            if name == "fk_agent_run_session":
                raise SessionNotFoundError("the session does not exist") from None
            if name in ("uq_agent_step_order", "pk_agent_step", "pk_tool_call", "pk_agent_run"):
                raise DuplicateRecordError("this record was written before") from None
            raise


def _run_status(value: str) -> RunStatus:
    if value not in ("RUNNING", "COMPLETED", "FAILED", "STOPPED", "BUDGET_EXCEEDED"):
        raise InvalidRecordError("unexpected run status in the database")
    return value  # type: ignore[return-value]


# ---- scope decisions ----


class PostgresScopeDecisionLog:
    def __init__(self, database: Database, clock: Clock, new_id: IdGenerator) -> None:
        self._db = database
        self._clock = clock
        self._new_id = new_id

    def record(self, decision: ScopeDecisionRecord, *, warehouse_consent: bool) -> ScopeDecisionResult:
        decision_id = self._new_id()
        event_id = self._new_id()
        now = self._clock()
        # The stored value is rounded to four decimals (numeric(5,4)); the event carries the same rounded value.
        confidence = (
            None
            if decision.confidence is None
            else Decimal(str(decision.confidence)).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        )

        def work(conn: Connection) -> ScopeDecisionResult:
            session_id: UUID | None = None
            project_key: str | None = None
            if decision.session_id is not None:
                row = conn.execute(
                    text("SELECT project_id FROM chat_session WHERE id = :id FOR KEY SHARE"),
                    {"id": decision.session_id},
                ).first()
                if row is not None:
                    session_id = decision.session_id
                    # A plain read: taking a row lock on project_ref under a session lock would cross DeleteProjectData.
                    project_key = conn.execute(
                        text("SELECT project_key FROM project_ref WHERE project_id = :pid"), {"pid": row.project_id}
                    ).scalar_one_or_none()
            conn.execute(
                text(
                    "INSERT INTO scope_decision (id, session_id, decision, confidence, deciding_ring, latency_ms, "
                    "language, decided_at) VALUES (:id, :sid, :decision, :confidence, :ring, :latency, :lang, :now)"
                ),
                {
                    "id": decision_id,
                    "sid": session_id,
                    "decision": decision.decision,
                    "confidence": confidence,
                    "ring": decision.deciding_ring,
                    "latency": decision.latency_ms,
                    "lang": decision.language,
                    "now": now,
                },
            )
            if not (warehouse_consent and project_key is not None):
                return ScopeDecisionResult(decision_id, event_written=False)
            payload = {
                "decision": decision.decision,
                "confidence": None if confidence is None else float(confidence),
                "deciding_ring": decision.deciding_ring,
                "latency_ms": decision.latency_ms,
                "language": decision.language,
            }
            # TODO(P4.2-1): agent-service has no outbox relay yet. The relay (P6.1) must re-read the WAREHOUSE_ANALYTICS
            # consent from core-service right before it sends and drop the event when the consent is gone or unreadable
            # (fail-closed, D-232a); until then these events only accumulate.
            conn.execute(
                text(
                    "INSERT INTO outbox_event (id, event_type, schema_version, project_key, occurred_at, payload, "
                    "published_at) VALUES (:id, 'scope_decision', 1, :key, :now, CAST(:payload AS jsonb), NULL)"
                ),
                {"id": event_id, "key": project_key, "now": now, "payload": json.dumps(payload)},
            )
            return ScopeDecisionResult(decision_id, event_written=True)

        return self._db.run(work)


# ---- idempotency housekeeping ----


class PostgresIdempotencyMaintenance:
    def __init__(self, database: Database, clock: Clock) -> None:
        self._db = database
        self._clock = clock

    def purge_idempotency_records(self) -> int:
        cutoff = self._clock() - _IDEMPOTENCY_TTL

        def work(conn: Connection) -> int:
            return conn.execute(
                text("DELETE FROM idempotency_record WHERE created_at < :cutoff"), {"cutoff": cutoff}
            ).rowcount

        return self._db.run(work)


# ---- knowledge base ----


@dataclass(frozen=True)
class _RuntimeRow:
    component: str
    major: int
    minor: int


class PostgresKnowledgeRepository:
    def __init__(self, database: Database, clock: Clock, new_id: IdGenerator) -> None:
        self._db = database
        self._clock = clock
        self._new_id = new_id

    def search_chunks(
        self, embedding: Sequence[float], embedding_model: str, runtime: RuntimeVersions, k: int
    ) -> tuple[KbHit, ...]:
        rows: list[_RuntimeRow] = []
        if runtime.java_major is not None:
            rows.append(_RuntimeRow("JAVA", runtime.java_major, 0))
        if runtime.spring_boot is not None:
            rows.append(_RuntimeRow("SPRING_BOOT", runtime.spring_boot[0], runtime.spring_boot[1]))
        params: dict[str, Any] = {"q": _vector_literal(embedding), "model": embedding_model, "k": k}
        version_filter = ""
        if rows:
            values = ", ".join(
                f"(CAST(:c{i} AS varchar), CAST(:a{i} AS integer), CAST(:b{i} AS integer))" for i in range(len(rows))
            )
            for i, row in enumerate(rows):
                params[f"c{i}"], params[f"a{i}"], params[f"b{i}"] = row.component, row.major, row.minor
            # A note is hidden when ANY of its ranges excludes the runtime's version of that component (bounds
            # inclusive).
            version_filter = (
                "AND NOT EXISTS (SELECT 1 FROM kb_document_applicability a "
                f"JOIN (VALUES {values}) rt(component, major, minor) ON rt.component = a.component "
                "WHERE a.document_id = d.id AND ("
                "(a.min_major IS NOT NULL AND (rt.major, rt.minor) < (a.min_major, a.min_minor)) "
                "OR (a.max_major IS NOT NULL AND (rt.major, rt.minor) > (a.max_major, a.max_minor)))) "
            )
        sql = (
            "SELECT d.doc_key, d.title, d.source_url, d.version_tag, d.source_type, d.language, c.ordinal, c.text, "
            "c.embedding <=> CAST(:q AS vector) AS distance "
            "FROM kb_chunk c JOIN kb_document d ON d.id = c.document_id "
            "WHERE d.embedding_model = :model " + version_filter + "ORDER BY distance, d.doc_key, c.ordinal LIMIT :k"
        )

        def work(conn: Connection) -> tuple[KbHit, ...]:
            result = conn.execute(text(sql), params).all()
            return tuple(
                KbHit(
                    r.doc_key,
                    r.title,
                    r.source_url,
                    r.version_tag,
                    _source_type(r.source_type),
                    r.language,
                    r.ordinal,
                    r.text,
                    float(r.distance),
                )
                for r in result
            )

        return self._db.run(work)

    def is_current(self, fingerprint: Fingerprint) -> bool:
        def work(conn: Connection) -> bool:
            return bool(
                conn.execute(
                    text(
                        "SELECT EXISTS (SELECT 1 FROM kb_document d WHERE d.doc_key = :key "
                        "AND d.content_sha256 = :sha AND d.embedding_model = :model AND d.chunk_chars = :chars "
                        "AND d.chunk_overlap = :overlap AND EXISTS (SELECT 1 FROM kb_chunk c WHERE c.document_id = "
                        "d.id))"
                    ),
                    {
                        "key": fingerprint.doc_key,
                        "sha": fingerprint.content_sha256,
                        "model": fingerprint.embedding_model,
                        "chars": fingerprint.chunk_chars,
                        "overlap": fingerprint.chunk_overlap,
                    },
                ).scalar_one()
            )

        return self._db.run(work)

    def upsert_document(self, document: KnowledgeDocument, *, force: bool = False) -> UpsertOutcome:
        new_id = self._new_id()
        now = self._clock()
        params = {
            "id": new_id,
            "key": document.doc_key,
            "title": document.title,
            "url": document.source_url,
            "type": document.source_type,
            "version": document.version_tag,
            "lang": document.language,
            "sha": document.content_sha256,
            "model": document.embedding_model,
            "chars": document.chunk_chars,
            "overlap": document.chunk_overlap,
            "now": now,
        }

        def work(conn: Connection) -> UpsertOutcome:
            inserted = conn.execute(
                text(
                    "INSERT INTO kb_document (id, doc_key, title, source_url, source_type, version_tag, language, "
                    "content_sha256, embedding_model, chunk_chars, chunk_overlap, indexed_at) VALUES (:id, :key, "
                    ":title, "
                    ":url, :type, :version, :lang, :sha, :model, :chars, :overlap, :now) "
                    "ON CONFLICT (doc_key) DO NOTHING RETURNING id"
                ),
                params,
            ).first()
            if inserted is not None:
                document_id, action = inserted.id, "created"
            else:
                row = conn.execute(
                    text(
                        "SELECT d.id, d.content_sha256, d.embedding_model, d.chunk_chars, d.chunk_overlap, "
                        "(SELECT count(*) FROM kb_chunk c WHERE c.document_id = d.id) AS chunks "
                        "FROM kb_document d WHERE d.doc_key = :key FOR UPDATE"
                    ),
                    {"key": document.doc_key},
                ).one()
                same = (
                    row.content_sha256 == document.content_sha256
                    and row.embedding_model == document.embedding_model
                    and row.chunk_chars == document.chunk_chars
                    and row.chunk_overlap == document.chunk_overlap
                    and row.chunks > 0
                )
                if same and not force:
                    return UpsertOutcome("unchanged")
                document_id, action = row.id, "updated"
                conn.execute(
                    text(
                        "UPDATE kb_document SET title = :title, source_url = :url, source_type = :type, "
                        "version_tag = :version, language = :lang, content_sha256 = :sha, embedding_model = :model, "
                        "chunk_chars = :chars, chunk_overlap = :overlap, indexed_at = :now WHERE id = :doc"
                    ),
                    {**params, "doc": document_id},
                )
            self._write_children(conn, document_id, document)
            return UpsertOutcome("created" if action == "created" else "updated")

        return self._db.run(work)

    def _write_children(self, conn: Connection, document_id: UUID, document: KnowledgeDocument) -> None:
        conn.execute(text("DELETE FROM kb_document_applicability WHERE document_id = :doc"), {"doc": document_id})
        for rule in document.applicability:
            conn.execute(
                text(
                    "INSERT INTO kb_document_applicability (document_id, component, min_major, min_minor, max_major, "
                    "max_minor) VALUES (:doc, :component, :min_major, :min_minor, :max_major, :max_minor)"
                ),
                {
                    "doc": document_id,
                    "component": rule.component,
                    "min_major": None if rule.min_version is None else rule.min_version[0],
                    "min_minor": None if rule.min_version is None else rule.min_version[1],
                    "max_major": None if rule.max_version is None else rule.max_version[0],
                    "max_minor": None if rule.max_version is None else rule.max_version[1],
                },
            )
        for chunk in document.chunks:
            conn.execute(
                text(
                    "INSERT INTO kb_chunk (id, document_id, ordinal, text, embedding) "
                    "VALUES (:id, :doc, :ordinal, :text, CAST(:embedding AS vector)) "
                    "ON CONFLICT (document_id, ordinal) DO UPDATE SET text = EXCLUDED.text, embedding = "
                    "EXCLUDED.embedding"
                ),
                {
                    "id": self._new_id(),
                    "doc": document_id,
                    "ordinal": chunk.ordinal,
                    "text": chunk.text,
                    "embedding": _vector_literal(chunk.embedding),
                },
            )
        conn.execute(
            text("DELETE FROM kb_chunk WHERE document_id = :doc AND ordinal > :n"),
            {"doc": document_id, "n": len(document.chunks)},
        )

    def retire_documents(self, keep: Sequence[str]) -> int:
        if not keep:
            raise InvalidRecordError("an empty keep list would delete the whole knowledge base")

        def work(conn: Connection) -> int:
            return conn.execute(
                text("DELETE FROM kb_document WHERE doc_key <> ALL(:keep)"), {"keep": list(keep)}
            ).rowcount

        return self._db.run(work)


def _source_type(value: str) -> SourceType:
    if value not in ("STANDARD", "JEP", "VENDOR_DOC", "SPECIFICATION", "GOVERNMENT_GUIDANCE", "INTERNAL"):
        raise InvalidRecordError("unexpected source type in the database")
    return value  # type: ignore[return-value]
