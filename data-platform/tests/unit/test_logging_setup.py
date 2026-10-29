"""The JSON log line carries the five agreed fields, the trace id, and only the class name of an exception."""

from __future__ import annotations

import json
import logging

from quancrypt_data.infrastructure.logging_setup import JsonFormatter
from quancrypt_data.trace import trace_id_var


def record(message: str = "hello", exc_info: object = None) -> logging.LogRecord:
    return logging.LogRecord("x", logging.INFO, __file__, 1, message, None, exc_info)  # type: ignore[arg-type]


def test_a_line_has_exactly_the_agreed_fields() -> None:
    token = trace_id_var.set("a" * 32)
    try:
        entry = json.loads(JsonFormatter().format(record()))
    finally:
        trace_id_var.reset(token)

    assert set(entry) == {"timestamp", "level", "service", "traceId", "message"}
    assert (entry["service"], entry["traceId"], entry["message"], entry["level"]) == (
        "ingest-api",
        "a" * 32,
        "hello",
        "INFO",
    )


def test_an_exception_is_logged_by_class_name_only() -> None:
    try:
        raise ValueError("secret-record-data")
    except ValueError:
        import sys

        line = JsonFormatter().format(record("failed", sys.exc_info()))

    assert json.loads(line)["exception"] == "ValueError"
    assert "secret-record-data" not in line


def test_the_service_name_of_a_line_is_the_one_the_process_was_configured_with() -> None:
    entry = json.loads(JsonFormatter("quancrypt-data").format(record()))

    assert entry["service"] == "quancrypt-data"
