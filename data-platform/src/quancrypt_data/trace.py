"""The trace id of the request being served. Neutral on purpose: the API layer sets it and the logging adapter reads it,
and neither may import the other (hexagonal-service section 2)."""

from __future__ import annotations

from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")
