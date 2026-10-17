"""In-memory implementations of the memory ports (test doubles; production code never imports this module).

They follow the same contract as the Postgres adapters (tests/contract/test_memory_contract.py runs both through the
same
tests): ordinals, idempotency replay, deletion semantics, run states and the knowledge-base filter.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from uuid import UUID, uuid4

from src.memory.long_term import (
    Fingerprint,
    KbHit,
    KnowledgeDocument,
    RuntimeVersions,
    UpsertOutcome,
)
from src.memory.memory_store import utc_now
from src.memory.short_term import (
    TRACE_ID,
    ChatMessage,
    ChatSession,
    ConversationWindow,
    DuplicateRecordError,
    Evidence,
    FinalRunStatus,
    IdempotencyConflictError,
    IdempotencyKey,
    InvalidRecordError,
    Language,
    MessagePage,
    ProjectDataDeletion,
    ProjectKeyMismatchError,
    Role,
    RunNotFoundError,
    RunNotRunningError,
    RunSummary,
    RunTrigger,
    ScopeDecisionRecord,
    ScopeDecisionResult,
    SessionCreated,
    SessionNotFoundError,
    StepRecord,
    trim_to_window,
)


@dataclass
class _Run:
    summary: RunSummary
    ordinals: set[int] = field(default_factory=set)


class InMemoryConversationMemory:
    def __init__(self, window: ConversationWindow) -> None:
        self._window = window
        self.sessions: dict[UUID, ChatSession] = {}
        self.messages: dict[UUID, list[ChatMessage]] = {}
        self.project_keys: dict[UUID, str] = {}
        self.idempotency: dict[str, tuple[str, UUID]] = {}
        self.audit_actions: list[str] = []

    def create_session(
        self, project_id: UUID, project_key: str, language: Language, idempotency: IdempotencyKey | None = None
    ) -> SessionCreated:
        if len(project_key) != 64:
            raise InvalidRecordError("project_key must be 64 lowercase hexadecimal digits")
        if idempotency is not None and idempotency.key in self.idempotency:
            digest, session_id = self.idempotency[idempotency.key]
            if digest != idempotency.request_sha256:
                raise IdempotencyConflictError("the idempotency key was used with a different request")
            return SessionCreated(self.sessions[session_id], replayed=True)
        known = self.project_keys.get(project_id)
        if known is not None and known != project_key:
            raise ProjectKeyMismatchError("the project id is already registered with a different project key")
        self.project_keys[project_id] = project_key
        session = ChatSession(uuid4(), project_id, language, utc_now())
        self.sessions[session.id] = session
        self.messages[session.id] = []
        if idempotency is not None:
            self.idempotency[idempotency.key] = (idempotency.request_sha256, session.id)
        return SessionCreated(session, replayed=False)

    def get_session(self, session_id: UUID) -> ChatSession | None:
        return self.sessions.get(session_id)

    def delete_session(self, session_id: UUID) -> None:
        if session_id not in self.sessions:
            raise SessionNotFoundError("the session does not exist")
        session = self.sessions.pop(session_id)
        self.messages.pop(session_id)
        self.idempotency = {k: v for k, v in self.idempotency.items() if v[1] != session_id}
        self.audit_actions.append(f"SESSION_DELETED:{self.project_keys[session.project_id]}")

    def delete_project_data(self, project_id: UUID) -> ProjectDataDeletion:
        key = self.project_keys.get(project_id)
        if key is None:
            return ProjectDataDeletion(0, 0, project_ref_deleted=False)
        doomed = [s.id for s in self.sessions.values() if s.project_id == project_id]
        for session_id in doomed:
            del self.sessions[session_id]
            del self.messages[session_id]
        self.idempotency = {k: v for k, v in self.idempotency.items() if v[1] not in doomed}
        del self.project_keys[project_id]
        self.audit_actions.append(f"PROJECT_DATA_DELETED:{key}")
        return ProjectDataDeletion(len(doomed), 0, project_ref_deleted=True)

    def append_user_message(self, session_id: UUID, content: str) -> ChatMessage:
        return self._append(session_id, "USER", content, ())

    def append_assistant_message(
        self, session_id: UUID, content: str, evidence: Sequence[Evidence] = ()
    ) -> ChatMessage:
        return self._append(session_id, "ASSISTANT", content, tuple(evidence))

    def _append(self, session_id: UUID, role: Role, content: str, evidence: tuple[Evidence, ...]) -> ChatMessage:
        if not content or "\x00" in content:
            raise InvalidRecordError("a message needs content without NUL characters")
        if session_id not in self.sessions:
            raise SessionNotFoundError("the session does not exist")
        messages = self.messages[session_id]
        message = ChatMessage(uuid4(), session_id, len(messages) + 1, role, content, utc_now(), evidence)
        messages.append(message)
        return message

    def list_messages(self, session_id: UUID, page: int, size: int) -> MessagePage:
        if page < 0 or not 1 <= size <= 200:
            raise InvalidRecordError("page must be 0 or more and size between 1 and 200")
        if session_id not in self.sessions:
            raise SessionNotFoundError("the session does not exist")
        messages = self.messages[session_id]
        return MessagePage(tuple(messages[page * size : (page + 1) * size]), page, size, len(messages))

    def recent_messages(self, session_id: UUID) -> tuple[ChatMessage, ...]:
        if session_id not in self.sessions:
            raise SessionNotFoundError("the session does not exist")
        window = [replace(m, evidence=()) for m in self.messages[session_id][-self._window.max_messages :]]
        return trim_to_window(window, self._window)


class InMemoryAuditLog:
    def __init__(self, conversation: InMemoryConversationMemory | None = None) -> None:
        self._conversation = conversation
        self.runs: dict[UUID, _Run] = {}

    def start_run(self, session_id: UUID | None, trigger: RunTrigger, trace_id: str) -> UUID:
        if not TRACE_ID.fullmatch(trace_id):
            raise InvalidRecordError("trace_id must be 32 lowercase hexadecimal digits")
        if session_id is not None and self._conversation is not None and session_id not in self._conversation.sessions:
            raise SessionNotFoundError("the session does not exist")
        run_id = uuid4()
        self.runs[run_id] = _Run(RunSummary(run_id, session_id, trigger, trace_id, "RUNNING", utc_now(), None))
        return run_id

    def record_step(self, step: StepRecord) -> UUID:
        run = self.runs.get(step.run_id)
        if run is None:
            raise RunNotFoundError("the run does not exist")
        if step.ordinal in run.ordinals:
            raise DuplicateRecordError("this record was written before")
        run.ordinals.add(step.ordinal)
        return uuid4()

    def finish_run(self, run_id: UUID, status: FinalRunStatus) -> None:
        run = self.runs.get(run_id)
        if run is None or run.summary.status != "RUNNING":
            raise RunNotRunningError("the run is already finished or does not exist")
        finished: datetime = utc_now()
        run.summary = replace(run.summary, status=status, finished_at=finished)

    def list_runs_by_trace(self, trace_id: str) -> tuple[RunSummary, ...]:
        if not TRACE_ID.fullmatch(trace_id):
            raise InvalidRecordError("trace_id must be 32 lowercase hexadecimal digits")
        return tuple(
            sorted(
                (r.summary for r in self.runs.values() if r.summary.trace_id == trace_id), key=lambda s: s.started_at
            )
        )


class InMemoryScopeDecisionLog:
    def __init__(self, conversation: InMemoryConversationMemory) -> None:
        self._conversation = conversation
        self.decisions: list[ScopeDecisionRecord] = []
        self.events: list[dict[str, object]] = []

    def record(self, decision: ScopeDecisionRecord, *, warehouse_consent: bool) -> ScopeDecisionResult:
        session = None if decision.session_id is None else self._conversation.sessions.get(decision.session_id)
        stored = replace(decision, session_id=None if session is None else decision.session_id)
        self.decisions.append(stored)
        if not (warehouse_consent and session is not None):
            return ScopeDecisionResult(uuid4(), event_written=False)
        self.events.append({"decision": decision.decision, "deciding_ring": decision.deciding_ring})
        return ScopeDecisionResult(uuid4(), event_written=True)


class InMemoryKnowledgeRepository:
    """Exact cosine search over stored documents, with the same version filter as the SQL one."""

    def __init__(self) -> None:
        self.documents: dict[str, KnowledgeDocument] = {}

    def search_chunks(
        self, embedding: Sequence[float], embedding_model: str, runtime: RuntimeVersions, k: int
    ) -> tuple[KbHit, ...]:
        hits: list[KbHit] = []
        for document in self.documents.values():
            if document.embedding_model != embedding_model:
                continue
            if not all(rule.admits(runtime) for rule in document.applicability):
                continue
            for chunk in document.chunks:
                hits.append(
                    KbHit(
                        document.doc_key,
                        document.title,
                        document.source_url,
                        document.version_tag,
                        document.source_type,
                        document.language,
                        chunk.ordinal,
                        chunk.text,
                        _cosine_distance(embedding, chunk.embedding),
                    )
                )
        hits.sort(key=lambda h: (h.distance, h.doc_key, h.ordinal))
        return tuple(hits[:k])

    def is_current(self, fingerprint: Fingerprint) -> bool:
        document = self.documents.get(fingerprint.doc_key)
        return (
            document is not None
            and document.content_sha256 == fingerprint.content_sha256
            and document.embedding_model == fingerprint.embedding_model
            and document.chunk_chars == fingerprint.chunk_chars
            and document.chunk_overlap == fingerprint.chunk_overlap
            and bool(document.chunks)
        )

    def upsert_document(self, document: KnowledgeDocument, *, force: bool = False) -> UpsertOutcome:
        existing = self.documents.get(document.doc_key)
        if (
            not force
            and existing is not None
            and self.is_current(
                Fingerprint(
                    document.doc_key,
                    document.content_sha256,
                    document.embedding_model,
                    document.chunk_chars,
                    document.chunk_overlap,
                )
            )
        ):
            return UpsertOutcome("unchanged")
        self.documents[document.doc_key] = document
        return UpsertOutcome("created" if existing is None else "updated")

    def retire_documents(self, keep: Sequence[str]) -> int:
        if not keep:
            raise InvalidRecordError("an empty keep list would delete the whole knowledge base")
        doomed = [key for key in self.documents if key not in set(keep)]
        for key in doomed:
            del self.documents[key]
        return len(doomed)


def _cosine_distance(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return 1.0 - dot / norm
