"""JSON logging on stdout (hexagonal-service section 6): timestamp, level, service, traceId, message.

Every message passes the shared `Redactor` (contracts/redaction-rules.yaml) before it is written (guardrails-security
section 5, D-242f). Log calls still carry no prompts, answers or request bodies; the redaction is the safety net.
"""

from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

from src.app.settings import LoggingSettings
from src.guardrails.redaction import Redactor

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="-")


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str, redactor: Redactor) -> None:
        super().__init__()
        self._service = service
        self._redactor = redactor

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self._service,
            "traceId": trace_id_var.get(),
            "message": self._redactor.redact(record.getMessage()),
        }
        if record.exc_info:
            # The class name only: a traceback can carry request data.
            entry["exception"] = record.exc_info[0].__name__ if record.exc_info[0] else "unknown"
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(settings: LoggingSettings, redactor: Redactor) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(settings.service, redactor))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(settings.level)
    # uvicorn installs its own handlers before the app is imported; route its records through the JSON handler instead.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True
    # The access log carries client addresses and paths; the request middleware writes the one allowed line instead.
    access = logging.getLogger("uvicorn.access")
    access.handlers[:] = []
    access.propagate = False
    # httpx logs every request URL at INFO; the Ollama calls are traced by the service itself.
    for name in ("httpx", "httpcore"):
        logging.getLogger(name).setLevel(logging.WARNING)
