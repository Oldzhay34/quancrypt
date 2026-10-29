"""JSON logging on stdout (hexagonal-service section 6): timestamp, level, service, traceId, message.

Log calls carry no request bodies, record data or paths: they write fixed messages with counts and class names, which is
why there is no redaction filter here (the sender already redacts and anonymises; D-296)."""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime

from quancrypt_data.trace import trace_id_var

SERVICE = "ingest-api"


class JsonFormatter(logging.Formatter):
    def __init__(self, service: str = SERVICE) -> None:
        super().__init__()
        self._service = service

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "service": self._service,
            "traceId": trace_id_var.get(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            # The class name only: a traceback can carry record data.
            entry["exception"] = record.exc_info[0].__name__ if record.exc_info[0] else "unknown"
        return json.dumps(entry, ensure_ascii=False)


def configure_logging(level: str, service: str = SERVICE) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter(service))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn installs its own handlers before the app is imported; route its records through the JSON handler instead.
    for name in ("uvicorn", "uvicorn.error"):
        logger = logging.getLogger(name)
        logger.handlers[:] = []
        logger.propagate = True
    # The access log carries client addresses and paths; the request middleware writes the one allowed line instead.
    access = logging.getLogger("uvicorn.access")
    access.handlers[:] = []
    access.propagate = False
    # The HTTP client logs every request line (method and address) at INFO; the corpus tooling reports its own progress.
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
