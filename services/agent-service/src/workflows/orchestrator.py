"""The orchestrator (P4.6): sessions, the per-session queue, stop, runs, scope-decision records and the SSE events.

A request on a session waits at most `queue_wait_s` for the session's previous request, then gets `SessionBusyError`
(409 session-busy, D-252f). The queue and the stop flags live in this process (single-replica assumption, ILERIDE).

A message: the user message is stored, a run starts (trace id from the HTTP layer), the message graph is built for this
request with fresh agents (D-252b) and streamed node by node; between nodes the stop flag is checked (`stop`: the run is
closed as STOPPED with a STOPPED step, the stream ends with `error{code: stopped}`). Every guard decision is written
through `ScopeDecisionLog` with the warehouse consent read from core-service just before (D-21, D-228); the request text
is never written there. The answer the user sees has passed the output checker; tokens are streamed after that check.
"""

from __future__ import annotations

import contextvars
import logging
import queue
import threading
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID

from src.agents.base_agent import AgentContext, AgentRunner, Evidence
from src.guardrails.chain import GuardDecision
from src.llm.provider import GenerationRequest, GenerationResult, LLMProvider, StreamChunk, TokenUsage
from src.memory.short_term import (
    AuditLog,
    ChatMessage,
    ChatSession,
    ConsentReader,
    ConversationMemory,
    IdempotencyKey,
    MessagePage,
    ScopeDecisionLog,
    ScopeDecisionRecord,
    SessionCreated,
    SessionNotFoundError,
    StepName,
    StepRecord,
    StepStatus,
)
from src.memory.short_term import Evidence as StoredEvidence
from src.prompts.system_prompts import refusal
from src.prompts.templates import CLARIFICATION_ANSWER_KINDS, CLARIFICATION_OPTIONS, CLARIFICATION_QUESTIONS
from src.tools.base_tool import ToolContext, ToolError, ToolRejectedError, ToolUnavailableError
from src.workflows.agent_graph import (
    AnswerChecker,
    GraphDeps,
    Guard,
    WorkflowFactory,
)
from src.workflows.task_router import TaskRouter

_LOG = logging.getLogger("src.workflows")

Language = Literal["tr", "en"]
ToolCaller = Callable[[str, Mapping[str, Any], ToolContext], tuple[Mapping[str, Any], int]]

# Fixed texts of the error events (no claim, no detail).
_ERRORS: dict[str, tuple[str, str]] = {
    "stopped": ("Yanıt kullanıcı isteğiyle durduruldu.", "The answer was stopped at the user's request."),
    "budget_exceeded": ("Bütçe aşıldı; yanıt tamamlanamadı.", "The budget was exceeded; the answer is incomplete."),
    "llm_unavailable": ("Dil modeline ulaşılamadı.", "The language model could not be reached."),
    "internal_error": ("Beklenmeyen bir hata oluştu.", "An unexpected error occurred."),
}
# The fixed message of a failed topology step: the scan is completed with its findings (D-256), the code stays
# `internal_error` (the contract's error codes are unchanged).
_TOPOLOGY_FAILED = (
    "Bulgular kaydedildi, ancak topoloji kaydedilemedi.",
    "The findings were recorded, but the topology could not be recorded.",
)
_TOKEN_CHUNK = 64
_TITLE_MAX = 200  # the contract's Evidence.title limit


class SessionBusyError(Exception):
    """The session's previous request did not finish within the queue wait (409 session-busy)."""


class ProjectNotFoundError(Exception):
    """core-service does not know the project."""


class UpstreamUnavailableError(Exception):
    """core-service or analyzer-service cannot be reached (503 upstream-unavailable)."""


@dataclass(frozen=True)
class SseEvent:
    event: Literal["token", "evidence", "clarification_required", "refusal", "done", "error"]
    data: Mapping[str, Any]


@dataclass(frozen=True)
class AgentSet:
    discovery: AgentRunner
    topology: AgentRunner
    planner: AgentRunner
    answer: AgentRunner


# Builds fresh agents (fresh toolboxes, so each run has its own call journal) around the given model.
AgentFactory = Callable[[LLMProvider], AgentSet]


class UsageMeter:
    """`LLMProvider` that adds up the tokens of one request (the `done` event's usage)."""

    def __init__(self, inner: LLMProvider) -> None:
        self._inner = inner
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.llm_disabled = False
        self._lock = threading.Lock()

    def generate(self, request: GenerationRequest) -> GenerationResult:
        result = self._inner.generate(request)
        with self._lock:
            self.prompt_tokens += result.usage.prompt_tokens
            self.completion_tokens += result.usage.completion_tokens
            self.llm_disabled = self.llm_disabled or result.llm_disabled
        return result

    def stream(self, request: GenerationRequest) -> Iterator[StreamChunk]:
        return self._inner.stream(request)

    def usage(self) -> dict[str, int]:
        with self._lock:
            return {"prompt_tokens": self.prompt_tokens, "completion_tokens": self.completion_tokens}


@dataclass
class _Slot:
    """A session's queue lock and the stop flag of its current run. Every run gets a fresh flag (in `_acquire`, under
    the lock), so a late `cancel()` of a finished stream can only set its own, old flag and never stops the next run."""

    lock: threading.Lock = field(default_factory=threading.Lock)
    stop: threading.Event = field(default_factory=threading.Event)


_DONE = object()


class EventStream:
    """The events of one run, produced by the run's own worker thread (security review P4.6 #1).

    The worker owns the session lock and releases it when the run ends, whatever the HTTP side does: a client that
    never starts reading cannot keep the session busy. `cancel()` (called by the HTTP layer when the client
    disconnects, which it notices within a second through `poll`) asks the run to stop at its next node boundary; it
    sets this run's own stop flag only. A failure outside the graph ends the stream with `error{internal_error}`, so
    every stream still ends with a terminal event. The worker runs in a copy of the caller's context, so its log lines
    keep the request's trace id.
    """

    def __init__(self, slot: _Slot, events: Iterator[SseEvent], language: Language) -> None:
        self._slot = slot
        self._stop = slot.stop  # this run's flag
        self._queue: queue.Queue[object] = queue.Queue()
        context = contextvars.copy_context()
        self._worker = threading.Thread(
            target=context.run, args=(self._work, events, language), name="agent-run", daemon=True
        )
        try:
            self._worker.start()
        except BaseException:  # no worker: nobody else would ever release the session
            slot.lock.release()
            raise

    def _work(self, events: Iterator[SseEvent], language: Language) -> None:
        try:
            for event in events:
                self._queue.put(event)
        except Exception as exc:  # outside the graph (storage, audit): logged by class only
            _LOG.warning("a run failed outside its graph (%s)", type(exc).__name__)
            self._queue.put(_error("internal_error", language))
        finally:
            self._queue.put(_DONE)
            self._slot.lock.release()

    def __iter__(self) -> Iterator[SseEvent]:
        while True:
            ended, item = self.poll(None)
            if ended:
                return
            if item is not None:
                yield item

    def poll(self, timeout: float | None) -> tuple[bool, SseEvent | None]:
        """The next event: `(False, event)`, `(False, None)` when nothing came within `timeout` seconds, or `(True,
        None)` once the stream has ended (and on every later call)."""
        try:
            item = self._queue.get(timeout=timeout)
        except queue.Empty:
            return False, None
        if isinstance(item, SseEvent):
            return False, item
        self._queue.put(_DONE)  # the end marker stays for any later poll
        return True, None

    def cancel(self) -> None:
        self._stop.set()  # this run's flag: harmless once the run has ended

    def join(self, timeout: float | None = None) -> None:
        self._worker.join(timeout)


class Orchestrator:
    def __init__(
        self,
        *,
        conversation: ConversationMemory,
        audit: AuditLog,
        scope_log: ScopeDecisionLog,
        consent: ConsentReader,
        call_tool: ToolCaller,
        guard: Guard,
        output_checker: AnswerChecker,
        llm: LLMProvider,
        agents: AgentFactory,
        workflows: WorkflowFactory,
        queue_wait_s: float,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._conversation = conversation
        self._audit = audit
        self._scope_log = scope_log
        self._consent = consent
        self._call_tool = call_tool
        self._guard = guard
        self._checker = output_checker
        self._llm = llm
        self._agents = agents
        self._workflows = workflows
        self._queue_wait_s = queue_wait_s
        self._clock = clock
        self._slots: dict[UUID, _Slot] = {}
        self._slots_lock = threading.Lock()

    # ---- sessions ----

    def create_session(
        self, project_id: UUID, language: Language, idempotency: IdempotencyKey | None, trace_id: str
    ) -> SessionCreated:
        project = self._tool("get_project", {"projectId": str(project_id)}, trace_id, not_found=ProjectNotFoundError)
        key = str(project["project"]["projectKey"])
        return self._conversation.create_session(project_id, key, language, idempotency)

    def delete_session(self, session_id: UUID) -> None:
        self._session(session_id)
        self._slot(session_id).stop.set()  # a running answer stops at its next node boundary
        self._conversation.delete_session(session_id)

    def list_messages(self, session_id: UUID, page: int, size: int) -> MessagePage:
        return self._conversation.list_messages(session_id, page, size)

    def stop(self, session_id: UUID) -> None:
        """Idempotent: with no running answer it does nothing (the next run starts with a fresh flag)."""
        self._session(session_id)
        slot = self._slot(session_id)
        if slot.lock.locked():
            slot.stop.set()

    # ---- messages and scans (SSE) ----

    def begin_message(self, session_id: UUID, content: str, trace_id: str) -> EventStream:
        session = self._session(session_id)
        slot = self._acquire(session_id)
        return EventStream(slot, self._message_events(session, content, trace_id, slot), session.language)

    def begin_initial_scan(self, session_id: UUID, root: str, trace_id: str) -> EventStream:
        session = self._session(session_id)
        slot = self._acquire(session_id)
        return EventStream(slot, self._scan_events(session, root, trace_id, slot), session.language)

    def _message_events(self, session: ChatSession, content: str, trace_id: str, slot: _Slot) -> Iterator[SseEvent]:
        # D-252e: a checkpoint is written from the session's second user message on (one-off sessions write none).
        persist = any(message.role == "USER" for message in self._conversation.recent_messages(session.id))
        self._conversation.append_user_message(session.id, content)
        run_id = self._audit.start_run(session.id, "MESSAGE", trace_id)
        context = AgentContext(trace_id=trace_id, run_id=run_id, clock=self._clock)
        meter = UsageMeter(self._llm)
        agents = self._agents(meter)
        deps = GraphDeps(
            context=context,
            clock=self._clock,
            record_node=self._recorder(context),
            output_checker=self._checker,
            guard=self._guard,
            on_decision=lambda decision: self._record_decision(session, decision, trace_id),
            router=TaskRouter(meter),
            planner=agents.planner,
            answer=agents.answer,
        )
        workflow = self._workflows.message(deps)
        state: dict[str, Any] = {
            "session_id": str(session.id),
            "trace_id": trace_id,
            "message": content,
            "lang": session.language,
            "project_id": str(session.project_id),
            "scan_id": self._latest_scan(session.project_id, trace_id),
            "guard_decision": None,
            "draft": "",
            "final": "",
            "evidence": [],
            "tool_results": [],
            "clarifications": [],
            "error_code": None,
        }
        yield from self._run(workflow.run(state, session.id, persist), state, session, context, meter, slot)

    def _scan_events(self, session: ChatSession, root: str, trace_id: str, slot: _Slot) -> Iterator[SseEvent]:
        run_id = self._audit.start_run(session.id, "INITIAL_SCAN", trace_id)
        context = AgentContext(trace_id=trace_id, run_id=run_id, clock=self._clock)
        meter = UsageMeter(self._llm)
        agents = self._agents(meter)
        deps = GraphDeps(
            context=context,
            clock=self._clock,
            record_node=self._recorder(context),
            output_checker=self._checker,
            discovery=agents.discovery,
            topology=agents.topology,
            close_scan=lambda scan_id: self._complete_scan(scan_id, trace_id),
        )
        state: dict[str, Any] = {
            "session_id": str(session.id),
            "trace_id": trace_id,
            "message": "",
            "lang": session.language,
            "project_id": str(session.project_id),
            "root": root,
            "draft": "",
            "final": "",
            "evidence": [],
            "tool_results": [],
            "clarifications": [],
            "error_code": None,
        }
        workflow = self._workflows.initial_scan(deps)
        try:
            yield from self._run(workflow.run(state, None, False), state, session, context, meter, slot)
        finally:
            # Stopped or failed after discovery: the scan still holds the findings and must not stay RUNNING (it
            # would block the project's next scan), so it is completed like a finished one (D-256).
            if state.get("scan_open") and state.get("scan_id"):
                try:
                    self._complete_scan(str(state["scan_id"]), trace_id)
                except ToolError as exc:
                    _LOG.warning("the scan could not be completed (%s)", type(exc).__name__)

    def _complete_scan(self, scan_id: str, trace_id: str) -> None:
        self._call_tool("complete_scan", {"scanId": scan_id, "body": {"outcome": "COMPLETED"}}, ToolContext(trace_id))

    def _run(
        self,
        updates: Iterator[Mapping[str, Any]],
        state: dict[str, Any],
        session: ChatSession,
        context: AgentContext,
        meter: UsageMeter,
        slot: _Slot,
    ) -> Iterator[SseEvent]:
        lang: Language = session.language
        stopped = False
        try:
            for delta in updates:
                state.update(delta)
                if slot.stop.is_set():
                    stopped = True
                    break
        except Exception as exc:  # the node raised: the request fails, its cause is logged by class only
            _LOG.warning("a workflow failed (%s)", type(exc).__name__)
            self._finish(context, "FAILED")
            yield _error("internal_error", lang)
            return
        if stopped:
            self._recorder(context)("ANSWER", "STOPPED", self._clock(), TokenUsage(0, 0))
            self._finish(context, "STOPPED")
            yield _error("stopped", lang)
            return
        yield from self._events(state, session, context, meter)

    def _events(
        self, state: Mapping[str, Any], session: ChatSession, context: AgentContext, meter: UsageMeter
    ) -> Iterator[SseEvent]:
        lang: Language = session.language
        outcome = state.get("outcome", "COMPLETED")
        if outcome == "REFUSED":
            text = refusal(lang)
            self._store_answer(session.id, text, ())
            self._finish(context, "COMPLETED")
            yield SseEvent("refusal", {"message": text, "language": lang})
            return
        if outcome == "BUDGET_EXCEEDED":
            self._finish(context, "BUDGET_EXCEEDED")
            yield _error("budget_exceeded", lang)
            return
        if outcome == "FAILED":
            self._finish(context, "FAILED")
            if state.get("error_code") == "topology-failed":
                tr, en = _TOPOLOGY_FAILED
                yield SseEvent("error", {"code": "internal_error", "message": en if lang == "en" else tr})
                return
            yield _error("llm_unavailable" if state.get("error_code") == "llm-unavailable" else "internal_error", lang)
            return
        if outcome == "CLARIFICATION_REQUIRED":
            yield SseEvent("clarification_required", {"questions": _questions(state.get("clarifications", []), {})})
        text = str(state.get("final") or "")
        evidence = tuple(_evidence(item) for item in state.get("evidence", []))
        for start in range(0, len(text), _TOKEN_CHUNK):
            yield SseEvent("token", {"text": text[start : start + _TOKEN_CHUNK]})
        for item in evidence:
            yield SseEvent("evidence", {"evidence": _evidence_data(item)})
        message = self._store_answer(session.id, text, evidence)
        self._finish(context, "COMPLETED")
        if message is None:  # the session was deleted while the answer ran
            yield _error("stopped", lang)
            return
        yield SseEvent(
            "done", {"message_id": str(message.id), "usage": meter.usage(), "llm_disabled": meter.llm_disabled}
        )

    # ---- clarifications ----

    def list_clarifications(self, session_id: UUID, trace_id: str) -> list[dict[str, Any]]:
        session = self._session(session_id)
        profile = self._tool("get_project_profile", {"projectId": str(session.project_id)}, trace_id)
        answers = {answer["questionCode"]: answer for answer in profile.get("answers", [])}
        return _questions(list(CLARIFICATION_QUESTIONS), answers)

    def answer_clarifications(
        self, session_id: UUID, answers: Sequence[Mapping[str, Any]], trace_id: str
    ) -> list[dict[str, Any]]:
        session = self._session(session_id)
        body = {
            "answers": [
                {
                    "questionCode": answer["question_code"],
                    "optionCode": answer.get("option_code"),
                    "freeText": answer.get("free_text"),
                }
                for answer in answers
            ]
        }
        self._tool("save_clarification_answers", {"projectId": str(session.project_id), "body": body}, trace_id)
        return self.list_clarifications(session_id, trace_id)

    # ---- internals ----

    def _session(self, session_id: UUID) -> ChatSession:
        session = self._conversation.get_session(session_id)
        if session is None:
            raise SessionNotFoundError("the session does not exist")
        return session

    def _slot(self, session_id: UUID) -> _Slot:
        with self._slots_lock:
            return self._slots.setdefault(session_id, _Slot())

    def _acquire(self, session_id: UUID) -> _Slot:
        slot = self._slot(session_id)
        if not slot.lock.acquire(timeout=self._queue_wait_s):
            raise SessionBusyError("the session is busy")
        slot.stop = threading.Event()  # a fresh flag per run (see `_Slot`)
        return slot

    def _recorder(self, context: AgentContext) -> Callable[[StepName, StepStatus, datetime, TokenUsage], None]:
        def record(name: StepName, status: StepStatus, started: datetime, usage: TokenUsage) -> None:
            duration = max(0, round((self._clock() - started).total_seconds() * 1000))
            self._audit.record_step(
                StepRecord(
                    run_id=context.run_id,
                    ordinal=context.next_ordinal(),
                    step_name=name,
                    agent_code=None,
                    status=status,
                    duration_ms=duration,
                    prompt_tokens=usage.prompt_tokens,
                    completion_tokens=usage.completion_tokens,
                    started_at=started,
                )
            )

        return record

    def _record_decision(self, session: ChatSession, decision: GuardDecision, trace_id: str) -> None:
        # Network first (D-228): the consent is read before the transaction that writes the decision.
        consent = self._consent.warehouse_consent(session.project_id, trace_id)
        self._scope_log.record(
            ScopeDecisionRecord(
                session_id=session.id,
                decision=decision.decision,
                confidence=decision.confidence,
                deciding_ring=decision.deciding_ring,
                latency_ms=decision.latency_ms,
                language=decision.language,
            ),
            warehouse_consent=consent,
        )

    def _latest_scan(self, project_id: UUID, trace_id: str) -> str | None:
        """The newest COMPLETED scan of the project (D-252d), or None when there is none or core cannot say."""
        try:
            page, _ = self._call_tool(
                "list_scans", {"projectId": str(project_id), "page": 0, "size": 20}, ToolContext(trace_id=trace_id)
            )
        except ToolError as exc:
            _LOG.warning("the latest scan could not be read (%s)", type(exc).__name__)
            return None
        for scan in page.get("items", []):
            if scan.get("status") == "COMPLETED":
                return str(scan["id"])
        return None

    def _tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
        trace_id: str,
        *,
        not_found: type[Exception] = SessionNotFoundError,
    ) -> Mapping[str, Any]:
        try:
            output, _ = self._call_tool(name, arguments, ToolContext(trace_id=trace_id))
        except ToolRejectedError as exc:
            if exc.status == 404:
                raise not_found("not found") from None
            raise
        except ToolUnavailableError:
            raise UpstreamUnavailableError("upstream unavailable") from None
        return output

    def _store_answer(self, session_id: UUID, text: str, evidence: Sequence[Evidence]) -> ChatMessage | None:
        stored = tuple(
            StoredEvidence(
                kind=item.kind.upper(),  # type: ignore[arg-type]
                reference=item.reference,
                source_version=item.source_version if item.kind == "knowledge_base" else None,
            )
            for item in evidence
        )
        try:
            return self._conversation.append_assistant_message(session_id, text or "-", stored)
        except SessionNotFoundError:
            return None

    def _finish(
        self, context: AgentContext, status: Literal["COMPLETED", "FAILED", "STOPPED", "BUDGET_EXCEEDED"]
    ) -> None:
        try:
            self._audit.finish_run(context.run_id, status)
        except Exception as exc:  # the run row may be gone with a deleted session; the answer still ends cleanly
            _LOG.warning("a run could not be finished (%s)", type(exc).__name__)


def _error(code: str, language: Language) -> SseEvent:
    tr, en = _ERRORS[code]
    return SseEvent("error", {"code": code, "message": en if language == "en" else tr})


def _evidence(item: Mapping[str, Any]) -> Evidence:
    title = item.get("title")
    return Evidence(
        kind=item["kind"],
        reference=str(item["reference"])[:1024],
        source_version=item.get("source_version"),
        title=str(title)[:_TITLE_MAX] if title else None,
    )


def _evidence_data(item: Evidence) -> dict[str, Any]:
    """The `evidence` event's payload; `title` only for knowledge-base evidence that has one (D-291g)."""
    data: dict[str, Any] = {"kind": item.kind, "reference": item.reference, "source_version": item.source_version}
    if item.kind == "knowledge_base" and item.title:
        data["title"] = item.title
    return data


def _questions(codes: Sequence[str], answers: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    items = []
    for code in codes:
        if code not in CLARIFICATION_QUESTIONS:
            continue
        tr, en = CLARIFICATION_QUESTIONS[code]
        answer = answers.get(code)
        items.append(
            {
                "question_code": code,
                "text": {"tr": tr, "en": en},
                "options": [{"option_code": o, "text": {"tr": o, "en": o}} for o in CLARIFICATION_OPTIONS[code]],
                "answer_kind": CLARIFICATION_ANSWER_KINDS[code],
                "answer": None
                if answer is None
                else {
                    "question_code": code,
                    "option_code": answer.get("optionCode"),
                    "free_text": answer.get("freeText"),
                },
            }
        )
    return items
