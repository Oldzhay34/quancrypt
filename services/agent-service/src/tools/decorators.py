"""Tool decorators (Decorator pattern): output redaction, timing and logging. The registry wraps every tool with all
three.

Order (outermost first): logged → timed → redacted → tool. Redaction runs on the raw output before anything else sees
it; timing covers the call and the redaction; the log line carries only the tool name, the outcome and the duration
(never arguments or output: they can hold project data).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Mapping
from typing import Any

from src.guardrails.redaction import Redactor
from src.tools.base_tool import Tool, ToolCode, ToolContext, ToolError, elapsed_ms

_LOG = logging.getLogger("src.tools")


class _Delegating:
    def __init__(self, inner: Tool) -> None:
        self._inner = inner

    @property
    def name(self) -> str:
        return self._inner.name

    @property
    def tool_code(self) -> ToolCode:
        return self._inner.tool_code

    @property
    def input_schema(self) -> Mapping[str, Any]:
        return self._inner.input_schema

    @property
    def output_schema(self) -> Mapping[str, Any]:
        return self._inner.output_schema


class RedactedTool(_Delegating):
    """Every string in the output passes the shared redactor (secrets in a code snippet, a path or a message)."""

    def __init__(self, inner: Tool, redactor: Redactor) -> None:
        super().__init__(inner)
        self._redactor = redactor

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Mapping[str, Any]:
        output = self._redactor.redact_value(self._inner.invoke(arguments, context))
        if not isinstance(output, Mapping):
            raise ToolError("a tool output must be an object")
        return output


class TimedTool(_Delegating):
    """Measures each call; the duration of the caller's latest call is kept per thread."""

    def __init__(self, inner: Tool) -> None:
        super().__init__(inner)
        self._local = threading.local()

    @property
    def last_duration_ms(self) -> int:
        return int(getattr(self._local, "duration_ms", 0))

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Mapping[str, Any]:
        started = time.monotonic()
        try:
            return self._inner.invoke(arguments, context)
        finally:
            self._local.duration_ms = elapsed_ms(started)


class LoggedTool(_Delegating):
    """One log line per call: tool name, outcome (or the error class) and duration."""

    def __init__(self, inner: TimedTool) -> None:
        super().__init__(inner)
        self._timed = inner

    @property
    def last_duration_ms(self) -> int:
        return self._timed.last_duration_ms

    def invoke(self, arguments: Mapping[str, Any], context: ToolContext) -> Mapping[str, Any]:
        try:
            output = self._timed.invoke(arguments, context)
        except Exception as exc:
            _LOG.info("tool %s failed (%s) in %d ms", self.name, type(exc).__name__, self.last_duration_ms)
            raise
        _LOG.info("tool %s succeeded in %d ms", self.name, self.last_duration_ms)
        return output


def decorate(tool: Tool, redactor: Redactor) -> LoggedTool:
    """The standard wrapping every registered tool gets."""
    return LoggedTool(TimedTool(RedactedTool(tool, redactor)))
