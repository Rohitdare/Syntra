"""Structured JSON logging with secret redaction and privacy enforcement."""

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

# Sensitive patterns to redact
SECRET_PATTERNS = [
    re.compile(r"(Bearer\s+)[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[:=]\s*)[^\s,]+", re.IGNORECASE),
    re.compile(r"(password\s*[:=]\s*)[^\s,]+", re.IGNORECASE),
    re.compile(r"(postgres(?:ql)?://[^:]+:)([^@]+)(@)", re.IGNORECASE),
]


class RedactionFilter(logging.Filter):
    """Filter that sanitizes log records to prevent logging secrets, prompts, or raw source text."""

    FORBIDDEN_ATTRIBUTES = {"source_text", "prompt", "model_output", "raw_content"}

    def filter(self, record: logging.LogRecord) -> bool:
        # Check and redact message string
        if isinstance(record.msg, str):
            for pattern in SECRET_PATTERNS:
                record.msg = pattern.sub(r"\1***REDACTED***", record.msg)

        # Block any forbidden context attributes
        for attr in self.FORBIDDEN_ATTRIBUTES:
            if hasattr(record, attr):
                delattr(record, attr)

        return True


class JsonFormatter(logging.Formatter):
    """Formats log records as structured, single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include request_id if available on the log record
        request_id = getattr(record, "request_id", None)
        if request_id:
            log_payload["request_id"] = request_id

        # Include job_id if present
        job_id = getattr(record, "job_id", None)
        if job_id:
            log_payload["job_id"] = str(job_id)

        # Include exception info if logged
        if record.exc_info and record.exc_text:
            log_payload["exception"] = record.exc_text

        return json.dumps(log_payload)


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger to output structured JSON with redaction."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Clear existing handlers
    for handler in list(root.handlers):
        root.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JsonFormatter())
    console_handler.addFilter(RedactionFilter())
    root.addHandler(console_handler)
