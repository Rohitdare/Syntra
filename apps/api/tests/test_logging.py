"""Tests for structured JSON logging and redaction."""

import json
import logging

from research_desk.core.logging import JsonFormatter, RedactionFilter


def test_redaction_filter_removes_secrets() -> None:
    filter_ = RedactionFilter()

    # Log record with bearer token and password
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Connecting with Bearer eyJhbGciOiJIUzI1Ni... and password=supersecret123",
        args=(),
        exc_info=None,
    )
    filter_.filter(record)
    assert "supersecret123" not in record.msg
    assert "***REDACTED***" in record.msg


def test_json_formatter_outputs_valid_json() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="research_desk.test",
        level=logging.INFO,
        pathname="test.py",
        lineno=20,
        msg="Sample structured event",
        args=(),
        exc_info=None,
    )
    record.request_id = "req_12345"  # type: ignore[attr-defined]

    formatted = formatter.format(record)
    data = json.loads(formatted)
    assert data["level"] == "INFO"
    assert data["message"] == "Sample structured event"
    assert data["request_id"] == "req_12345"
    assert "ts" in data
