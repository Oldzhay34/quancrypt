"""Deterministic test doubles for the agents (P4.5): a scripted toolbox, a scripted LLM and a scripted knowledge base.

Allowed in tests only; production code never imports this module. The toolbox mirrors `AgentToolbox`: it enforces the
allow-list (a call outside it is journaled DENIED and raised), journals every call and keeps a cursor-friendly record
list, so the base agent's per-step tool-call delta can be checked.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from src.llm.provider import (
    EmbeddingResult,
    GenerationRequest,
    GenerationResult,
    LLMError,
    LLMStatus,
    TokenUsage,
)
from src.memory.long_term import KbHit, RuntimeVersions
from src.memory.short_term import FinalRunStatus, RunTrigger, StepRecord, ToolCallRecord, ToolCode
from src.tools.base_tool import (
    ToolContext,
    ToolError,
    ToolNotAllowedError,
    ToolResult,
    ToolUnavailableError,
)

TOOL_CODES: dict[str, ToolCode] = {
    "start_scan": "CORE",
    "record_findings": "CORE",
    "record_scan_artifact": "CORE",
    "complete_scan": "CORE",
    "list_findings": "CORE",
    "get_topology": "CORE",
    "get_project_profile": "CORE",
    "save_clarification_answers": "CORE",
    "create_plan": "CORE",
    "get_plan": "CORE",
    "get_plan_report": "CORE",
    "record_topology": "CORE",
    "register_project": "CORE",
    "get_project": "CORE",
    "get_consents": "CORE",
    "analyze_crypto": "ANALYZER",
    "build_topology": "ANALYZER",
    "get_snippet": "ANALYZER",
    "kb_search": "KB_SEARCH",
    "score_findings": "RISK_MODEL",
}


class FakeClock:
    """A monotonic clock that advances a fixed step each read; it is a `Callable[[], datetime]`."""

    def __init__(self, step_seconds: float = 0.0, start: datetime | None = None) -> None:
        self._step = timedelta(seconds=step_seconds)
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)

    def __call__(self) -> datetime:
        value = self._now
        self._now = self._now + self._step
        return value


@dataclass
class _Handler:
    outputs: list[Any] = field(default_factory=list)
    error: Exception | None = None


class ScriptedToolbox:
    """A toolbox whose tools return queued outputs (or raise). It enforces its allow-list and journals every call."""

    def __init__(
        self,
        names: Sequence[str],
        handlers: Mapping[str, Sequence[Mapping[str, Any]]] | None = None,
        *,
        errors: Mapping[str, Exception] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._names = frozenset(names)
        self._queues = {name: list(outputs) for name, outputs in (handlers or {}).items()}
        self._errors = dict(errors or {})
        self._clock = clock or FakeClock()
        self._records: list[ToolCallRecord] = []
        self.calls: list[tuple[str, Mapping[str, Any]]] = []

    def names(self) -> frozenset[str]:
        return self._names

    def invoke(self, name: str, arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        code = TOOL_CODES.get(name, "UNKNOWN")
        self.calls.append((name, arguments))
        if name not in self._names:
            self._record(context, code, "DENIED")
            raise ToolNotAllowedError(f"the agent may not call {name}")
        error = self._errors.get(name)
        if error is not None:
            status = "TIMED_OUT" if isinstance(error, ToolUnavailableError) and error.timed_out else "FAILED"
            self._record(context, code, status)
            raise error
        queue = self._queues.get(name)
        if not queue:
            raise AssertionError(f"no scripted output left for {name}")
        output = queue.pop(0)
        self._record(context, code, "SUCCEEDED")
        return ToolResult(context.call_id, name, code, "SUCCEEDED", 1, output)

    def records(self) -> tuple[ToolCallRecord, ...]:
        return tuple(self._records)

    def _record(self, context: ToolContext, code: ToolCode, status: str) -> None:
        self._records.append(ToolCallRecord(context.call_id, code, status, 1, self._clock()))  # type: ignore[arg-type]


class ScriptedLLM:
    """Returns queued texts (or `GenerationResult`s), or raises a queued error. `disabled` mimics NullProvider."""

    def __init__(self, replies: Sequence[str | GenerationResult | Exception] = (), *, disabled: bool = False) -> None:
        self._replies = list(replies)
        self._disabled = disabled
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GenerationResult:
        self.requests.append(request)
        if self._disabled:
            return GenerationResult(text="[disabled]", usage=TokenUsage(0, 0), model="null", llm_disabled=True)
        if not self._replies:
            raise AssertionError("no scripted reply left")
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if isinstance(reply, GenerationResult):
            return reply
        return GenerationResult(text=reply, usage=TokenUsage(3, 2), model="fake")

    def stream(self, request: GenerationRequest):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        raise LLMError("not used")

    def status(self) -> LLMStatus:
        return "disabled" if self._disabled else "ok"


class ScriptedKnowledgeBase:
    """Returns queued hit lists, or raises a queued error (for example `KnowledgeUnavailableError`)."""

    def __init__(self, replies: Sequence[tuple[KbHit, ...] | Exception] = ()) -> None:
        self._replies = list(replies)
        self.queries: list[str] = []

    def search(self, query: str, runtime: RuntimeVersions, k: int | None = None) -> tuple[KbHit, ...]:
        self.queries.append(query)
        if not self._replies:
            return ()
        reply = self._replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


def hit(doc_key: str, title: str, version: str, text: str, *, url: str | None = None) -> KbHit:
    return KbHit(
        doc_key=doc_key,
        title=title,
        source_url=url,
        version_tag=version,
        source_type="INTERNAL" if url is None else "STANDARD",
        language="en",
        ordinal=1,
        text=text,
        distance=0.1,
    )


class RecordingAuditLog:
    """Keeps every `StepRecord` (and the run status) so a test can read the audit trail an agent wrote."""

    def __init__(self) -> None:
        self.steps: list[StepRecord] = []
        self.finished: dict[UUID, FinalRunStatus] = {}

    def start_run(self, session_id: UUID | None, trigger: RunTrigger, trace_id: str) -> UUID:
        return uuid4()

    def record_step(self, step: StepRecord) -> UUID:
        self.steps.append(step)
        return uuid4()

    def finish_run(self, run_id: UUID, status: FinalRunStatus) -> None:
        self.finished[run_id] = status

    def list_runs_by_trace(self, trace_id: str) -> tuple[Any, ...]:
        return ()


def new_run(trace: str = "a" * 32) -> tuple[UUID, str]:
    return uuid4(), trace


def timed_error(timed_out: bool = True) -> ToolUnavailableError:
    return ToolUnavailableError("service timed out", timed_out=timed_out)


def tool_error(message: str = "boom") -> ToolError:
    return ToolError(message)
