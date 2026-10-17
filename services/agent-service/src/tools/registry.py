"""Tool registry and per-agent toolboxes (P4.3, D-238).

`ToolRegistry` holds every tool, wrapped by the standard decorators, and the allow-lists of `agent_config.yaml`.
`scoped(agent)` hands an agent an `AgentToolbox` that shows only the tools on its list (interface segregation): an agent
cannot even name another agent's tools.

Every call through a toolbox is recorded as a `ToolCallRecord` (the toolbox's call journal). A call outside the
allow-list raises `ToolNotAllowedError`, is recorded as DENIED (an unregistered name as UNKNOWN) and logged at WARNING;
the agent writes the journal to agent_db with its step (`StepRecord.tool_calls`, P4.5).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from src.guardrails.redaction import Redactor
from src.memory.short_term import ToolCallRecord, ToolCallStatus
from src.tools.base_tool import (
    SchemaStore,
    Tool,
    ToolCode,
    ToolContext,
    ToolError,
    ToolInputError,
    ToolNotAllowedError,
    ToolOutputError,
    ToolResult,
    ToolUnavailableError,
    elapsed_ms,
)
from src.tools.decorators import LoggedTool, decorate

_LOG = logging.getLogger("src.tools")

Clock = Callable[[], datetime]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ToolRegistry:
    """Every tool once, by name; the allow-lists name only registered tools (checked at construction: fail fast)."""

    def __init__(
        self,
        tools: Iterable[Tool],
        allow_lists: Mapping[str, Sequence[str]],
        schemas: SchemaStore,
        redactor: Redactor,
        clock: Clock = _utc_now,
    ) -> None:
        self._tools: dict[str, LoggedTool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ToolError(f"the tool {tool.name} is registered twice")
            schemas.check_contract(tool.name)
            self._tools[tool.name] = decorate(tool, redactor)
        unknown = sorted({name for names in allow_lists.values() for name in names} - set(self._tools))
        if unknown:
            raise ToolError(f"allow-lists name tools that are not registered: {', '.join(unknown)}")
        self._allow_lists = {agent: frozenset(names) for agent, names in allow_lists.items()}
        self._schemas = schemas
        self._clock = clock

    def names(self) -> frozenset[str]:
        return frozenset(self._tools)

    def allowed(self, agent: str) -> frozenset[str]:
        return self._allow_lists.get(agent, frozenset())

    def scoped(self, agent: str) -> AgentToolbox:
        if agent not in self._allow_lists:
            raise ToolError(f"no allow-list for the agent {agent}")
        return AgentToolbox(agent, self)

    def tool_code(self, name: str) -> ToolCode:
        tool = self._tools.get(name)
        return tool.tool_code if tool is not None else "UNKNOWN"

    def call(self, name: str, arguments: Mapping[str, Any], context: ToolContext) -> tuple[Mapping[str, Any], int]:
        """Validate, invoke the decorated tool and validate its output. Used by toolboxes and the workflow layer."""
        tool = self._tools.get(name)
        if tool is None:
            raise ToolNotAllowedError(f"there is no tool named {name}")
        violations = self._schemas.validate(name, "input", dict(arguments))
        if violations:
            raise ToolInputError(f"the input of {name} does not fit its contract: {'; '.join(violations[:5])}")
        output = tool.invoke(arguments, context)
        violations = self._schemas.validate(name, "output", _plain(output))
        if violations:
            raise ToolOutputError(f"the output of {name} does not fit its contract: {'; '.join(violations[:5])}")
        return output, tool.last_duration_ms

    def now(self) -> datetime:
        return self._clock()


class AgentToolbox:
    """The tools of one agent. Not shared between agents; the call journal is per toolbox (one agent run)."""

    def __init__(self, agent: str, registry: ToolRegistry) -> None:
        self._agent = agent
        self._registry = registry
        self._records: list[ToolCallRecord] = []
        self._lock = threading.Lock()

    @property
    def agent(self) -> str:
        return self._agent

    def names(self) -> frozenset[str]:
        return self._registry.allowed(self._agent)

    def invoke(self, name: str, arguments: Mapping[str, Any], context: ToolContext) -> ToolResult:
        code = self._registry.tool_code(name)
        if name not in self.names():
            self._record(context, code, "DENIED", 0)
            _LOG.warning("agent %s called a tool outside its allow-list: %s", self._agent, _safe_name(name))
            raise ToolNotAllowedError(f"the agent {self._agent} may not call {_safe_name(name)}")
        started = time.monotonic()
        try:
            output, duration = self._registry.call(name, arguments, context)
        except ToolUnavailableError as exc:
            status: ToolCallStatus = "TIMED_OUT" if exc.timed_out else "FAILED"
            self._record(context, code, status, elapsed_ms(started))
            raise
        except ToolError:
            self._record(context, code, "FAILED", elapsed_ms(started))
            raise
        self._record(context, code, "SUCCEEDED", duration)
        return ToolResult(context.call_id, name, code, "SUCCEEDED", duration, output)

    def records(self) -> tuple[ToolCallRecord, ...]:
        """The call journal (oldest first) that the agent writes with its step."""
        with self._lock:
            return tuple(self._records)

    def _record(self, context: ToolContext, code: ToolCode, status: ToolCallStatus, duration_ms: int) -> None:
        record = ToolCallRecord(context.call_id, code, status, duration_ms, self._registry.now())
        with self._lock:
            self._records.append(record)


def _safe_name(name: str) -> str:
    """A tool name as the agent (or a model) wrote it can be anything: log only a bounded, printable form."""
    printable = "".join(ch if ch.isascii() and (ch.isalnum() or ch == "_") else "?" for ch in name[:64])
    return printable or "?"


def _plain(value: Any) -> Any:
    """Mappings and sequences as plain dicts and lists, for the validator."""
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_plain(item) for item in value]
    return value
