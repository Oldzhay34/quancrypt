"""JSON log lines on stdout with the fields timestamp, level, service, traceId and message."""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

SERVICE = "field-device-sim"


class JsonFormatter(logging.Formatter):
    """One JSON object per line. A logged exception contributes only its class name, never its message or trace."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info and record.exc_info[0] is not None:
            message = f"{message} [{record.exc_info[0].__name__}]"
        return json.dumps(
            {
                "timestamp": datetime.fromtimestamp(record.created, timezone.utc)
                .isoformat(timespec="milliseconds")
                .replace("+00:00", "Z"),
                "level": record.levelname,
                "service": SERVICE,
                "traceId": None,
                "message": message,
            },
            separators=(",", ":"),
        )


def configure_logging(level: int = logging.INFO) -> None:
    """Send all logs to stdout as JSON."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
