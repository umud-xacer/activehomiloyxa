"""Structured JSON logging (Playbook Sec 6 "Structured JSON logs with the traceId ... Logging is
observation, never control flow."). Every record carries `traceId` when the emitting code is
inside a request (via `extra={"trace_id": ...}`, matching `backbone.errors.middleware`'s
`request.state.trace_id`); records outside a request simply omit it.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

from backbone.logging.redaction import RedactingFilter

_RESERVED_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None))) | {"message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED_ATTRS:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str | None = None) -> None:
    """Idempotent: safe to call more than once (e.g. once from the app factory, once from a
    worker entrypoint in the same process during tests) -- clears and re-installs rather than
    stacking duplicate handlers."""
    root = logging.getLogger()
    root.handlers.clear()

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())
    root.addHandler(handler)
    root.setLevel((level or os.environ.get("LOG_LEVEL", "info")).upper())
