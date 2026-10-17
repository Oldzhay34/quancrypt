"""Short-term memory ports and values (D-233d): everything that belongs to a session or a run, is local and can be
deleted.

`ConversationMemory` keeps chat sessions and messages, `AuditLog` the run, step and tool-call audit (metadata only,
NFR-09),
`ScopeDecisionLog` the scope decisions (no request text, D-226) and `IdempotencyMaintenance` the housekeeping of
`idempotency_record`. The Postgres implementations live in `memory_store.py` (the only place with SQL); agents and
workflows
see only these Protocols (agent-service-layout section 3).

The values validate their own invariants (`InvalidRecordError`), the same rules the database enforces with CHECK
constraints
(domain and database both, acid-3nf-database section 5).
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol
from uuid import UUID

Role = Literal["USER", "ASSISTANT"]
Language = Literal["tr", "en"]
EvidenceKind = Literal["CODE_LOCATION", "TOOL_CALL", "KNOWLEDGE_BASE"]
RunTrigger = Literal["MESSAGE", "INITIAL_SCAN", "PLAN"]
FinalRunStatus = Literal["COMPLETED", "FAILED", "STOPPED", "BUDGET_EXCEEDED"]
RunStatus = Literal["RUNNING", "COMPLETED", "FAILED", "STOPPED", "BUDGET_EXCEEDED"]
StepName = Literal[
    "INPUT_GUARD", "ROUTE", "GATHER_CONTEXT", "PLAN", "ACT", "VERIFY", "REPORT", "ANSWER", "OUTPUT_GUARD"
]
StepStatus = Literal["SUCCEEDED", "FAILED", "STOPPED", "BUDGET_EXCEEDED"]
AgentCode = Literal["SUPERVISOR", "DISCOVERY", "TOPOLOGY", "PLANNER"]
ToolCode = Literal["ANALYZER", "CORE", "KB_SEARCH", "RISK_MODEL", "UNKNOWN"]
ToolCallStatus = Literal["SUCCEEDED", "FAILED", "DENIED", "TIMED_OUT"]
ScopeVerdict = Literal["ALLOW", "DENY"]
ScopeRing = Literal["RULE_FILTER", "SCOPE_CLASSIFIER", "LLM_SELF_CHECK", "FAIL_CLOSED"]

Clock = Callable[[], datetime]
IdGenerator = Callable[[], UUID]

# Workflow nodes carry no agent; lifecycle steps do (ERD, ck_agent_step_workflow_node).
WORKFLOW_NODES: frozenset[str] = frozenset({"INPUT_GUARD", "ROUTE", "ANSWER", "OUTPUT_GUARD"})

TRACE_ID = re.compile(r"^[0-9a-f]{32}$")
PROJECT_KEY = re.compile(r"^[0-9a-f]{64}$")
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class MemoryStoreError(Exception):
    """Base class of every error the memory ports raise. Messages never contain chat text."""


class InvalidRecordError(MemoryStoreError, ValueError):
    """A value breaks an invariant the database would reject as well."""


class SessionNotFoundError(MemoryStoreError):
    """The session does not exist (never created, or deleted)."""


class RunNotFoundError(MemoryStoreError):
    """The run does not exist."""


class RunNotRunningError(MemoryStoreError):
    """The run is already finished (a run can be finished once)."""


class IdempotencyConflictError(MemoryStoreError):
    """The Idempotency-Key was used with a different request."""


class ProjectKeyMismatchError(MemoryStoreError):
    """The same project id arrived with a different project key (the key is a deterministic function of the project)."""


class DuplicateRecordError(MemoryStoreError):
    """A record with the same natural key exists (for example a step ordinal that was recorded twice)."""


# ---- values ----


@dataclass(frozen=True)
class Evidence:
    kind: EvidenceKind
    reference: str
    # Only knowledge-base evidence carries the source's version tag (snapshot at answer time).
    source_version: str | None = None

    def __post_init__(self) -> None:
        if not self.reference or len(self.reference) > 1024 or "\x00" in self.reference:
            raise InvalidRecordError("evidence reference must be 1 to 1024 characters without NUL characters")
        if self.source_version is not None and self.kind != "KNOWLEDGE_BASE":
            raise InvalidRecordError("only knowledge-base evidence carries a source version")
        if self.source_version is not None and not 0 < len(self.source_version) <= 64:
            raise InvalidRecordError("source version must be 1 to 64 characters")


@dataclass(frozen=True)
class ChatSession:
    id: UUID
    project_id: UUID
    language: Language
    created_at: datetime


@dataclass(frozen=True)
class ChatMessage:
    id: UUID
    session_id: UUID
    ordinal: int
    role: Role
    content: str
    created_at: datetime
    evidence: tuple[Evidence, ...] = ()


@dataclass(frozen=True)
class SessionCreated:
    session: ChatSession
    # True when the same Idempotency-Key replayed an earlier request.
    replayed: bool


@dataclass(frozen=True)
class IdempotencyKey:
    key: str
    request_sha256: str

    def __post_init__(self) -> None:
        if not self.key.strip() or len(self.key) > 128:
            raise InvalidRecordError("the idempotency key must be 1 to 128 characters and not blank")
        if not SHA256_HEX.fullmatch(self.request_sha256):
            raise InvalidRecordError("the request digest must be 64 lowercase hexadecimal digits")


@dataclass(frozen=True)
class MessagePage:
    items: tuple[ChatMessage, ...]
    page: int
    size: int
    total: int


@dataclass(frozen=True)
class ProjectDataDeletion:
    sessions_deleted: int
    outbox_events_deleted: int
    # False when the project had no reference (nothing to delete).
    project_ref_deleted: bool


@dataclass(frozen=True)
class ToolCallRecord:
    id: UUID
    tool_code: ToolCode
    status: ToolCallStatus
    duration_ms: int
    called_at: datetime

    def __post_init__(self) -> None:
        if self.duration_ms < 0:
            raise InvalidRecordError("tool call duration must not be negative")
        if self.tool_code == "UNKNOWN" and self.status != "DENIED":
            raise InvalidRecordError("an unregistered tool name can only be recorded as DENIED")


@dataclass(frozen=True)
class StepRecord:
    run_id: UUID
    ordinal: int
    step_name: StepName
    agent_code: AgentCode | None
    status: StepStatus
    duration_ms: int
    prompt_tokens: int
    completion_tokens: int
    started_at: datetime
    tool_calls: tuple[ToolCallRecord, ...] = ()

    def __post_init__(self) -> None:
        if self.ordinal < 1:
            raise InvalidRecordError("step ordinal starts at 1")
        if self.duration_ms < 0 or self.prompt_tokens < 0 or self.completion_tokens < 0:
            raise InvalidRecordError("step duration and token counts must not be negative")
        if (self.step_name in WORKFLOW_NODES) != (self.agent_code is None):
            raise InvalidRecordError("workflow nodes carry no agent, lifecycle steps carry one")


@dataclass(frozen=True)
class RunSummary:
    id: UUID
    session_id: UUID | None
    trigger: RunTrigger
    trace_id: str
    status: RunStatus
    started_at: datetime
    finished_at: datetime | None


@dataclass(frozen=True)
class ScopeDecisionRecord:
    session_id: UUID | None
    decision: ScopeVerdict
    # Only the scope classifier (ring 2) produces a score; every other ring has none (ck_scope_decision_score).
    confidence: float | None
    deciding_ring: ScopeRing
    latency_ms: int
    language: Language

    def __post_init__(self) -> None:
        if (self.deciding_ring == "SCOPE_CLASSIFIER") != (self.confidence is not None):
            raise InvalidRecordError("a confidence score belongs to the scope classifier and to no other ring")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise InvalidRecordError("confidence must be between 0 and 1")
        if self.deciding_ring == "FAIL_CLOSED" and self.decision != "DENY":
            raise InvalidRecordError("the fail-closed ring can only deny")
        if self.latency_ms < 0:
            raise InvalidRecordError("latency must not be negative")


@dataclass(frozen=True)
class ScopeDecisionResult:
    id: UUID
    # True when the event went into the outbox (warehouse consent, a known session and project key).
    event_written: bool


# ---- the conversation window ----


@dataclass(frozen=True)
class ConversationWindow:
    """What a model call may see of a conversation: the last `max_messages`, then trimmed to `token_budget`.

    `chars_per_token` is an ESTIMATE (D-231c), not a measurement.
    """

    max_messages: int
    token_budget: int
    chars_per_token: float


def estimate_tokens(text: str, chars_per_token: float) -> int:
    return max(1, math.ceil(len(text) / chars_per_token))


def trim_to_window(messages: Sequence[ChatMessage], window: ConversationWindow) -> tuple[ChatMessage, ...]:
    """Keep the newest messages that fit: at most `max_messages`, then drop the oldest until the estimate fits the
    budget.

    `messages` is oldest first and so is the result. The newest message is always kept (even when it alone exceeds the
    budget): a request without its latest question would be meaningless.
    """
    recent = list(messages[-window.max_messages :])
    kept: list[ChatMessage] = []
    used = 0
    for message in reversed(recent):
        cost = estimate_tokens(message.content, window.chars_per_token)
        if kept and used + cost > window.token_budget:
            break
        kept.append(message)
        used += cost
    kept.reverse()
    return tuple(kept)


# ---- ports ----


class ConversationMemory(Protocol):
    def create_session(
        self, project_id: UUID, project_key: str, language: Language, idempotency: IdempotencyKey | None = None
    ) -> SessionCreated:
        """Open a session. `project_key` comes from core-service; the caller validated the project (D-229, D-233d)."""
        ...

    def get_session(self, session_id: UUID) -> ChatSession | None: ...

    def delete_session(self, session_id: UUID) -> None:
        """Delete the session, its messages and evidence; audit rows stay anonymous (D-225). Raises
        `SessionNotFoundError`."""
        ...

    def delete_project_data(self, project_id: UUID) -> ProjectDataDeletion:
        """Delete everything agent-service holds for a project (D-232b); audit rows stay anonymous."""
        ...

    def append_user_message(self, session_id: UUID, content: str) -> ChatMessage: ...

    def append_assistant_message(
        self, session_id: UUID, content: str, evidence: Sequence[Evidence] = ()
    ) -> ChatMessage: ...

    def list_messages(self, session_id: UUID, page: int, size: int) -> MessagePage:
        """Oldest first; `size` at most 200. Raises `SessionNotFoundError`."""
        ...

    def recent_messages(self, session_id: UUID) -> tuple[ChatMessage, ...]:
        """The conversation window (`ConversationWindow`), oldest first, without evidence."""
        ...


class AuditLog(Protocol):
    def start_run(self, session_id: UUID | None, trigger: RunTrigger, trace_id: str) -> UUID: ...

    def record_step(self, step: StepRecord) -> UUID:
        """Write the step and its tool calls (metadata only) in one transaction."""
        ...

    def finish_run(self, run_id: UUID, status: FinalRunStatus) -> None:
        """Raises `RunNotRunningError` when the run is already finished or does not exist."""
        ...

    def list_runs_by_trace(self, trace_id: str) -> tuple[RunSummary, ...]: ...


class ScopeDecisionLog(Protocol):
    def record(self, decision: ScopeDecisionRecord, *, warehouse_consent: bool) -> ScopeDecisionResult:
        """Write the decision and, when `warehouse_consent` is true and the session is known, the outbox event
        atomically.

        The caller read the consent from core-service before the call (D-228); the relay re-checks it before sending
        (D-232a).
        """
        ...


class IdempotencyMaintenance(Protocol):
    def purge_idempotency_records(self) -> int:
        """Delete idempotency records older than 24 hours; returns how many (D-136)."""
        ...
