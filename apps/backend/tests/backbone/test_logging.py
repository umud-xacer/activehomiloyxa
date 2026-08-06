"""Structured logging + redaction (Playbook Sec 6 / Security Sec 12: "never log secrets, OTP
codes, session tokens, passwords, or PII beyond safe identifiers")."""

from __future__ import annotations

import json
import logging
from typing import cast

from backbone.logging import JsonFormatter, RedactingFilter, configure_logging


def _emit_and_capture(
    logger_name: str, message: str, extra: dict[str, object]
) -> dict[str, object]:
    import io

    buf = io.StringIO()
    handler = logging.StreamHandler(stream=buf)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactingFilter())

    logger = logging.getLogger(logger_name)
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)

    logger.info(message, extra=extra)
    return cast(dict[str, object], json.loads(buf.getvalue().strip()))


def test_I09_secret_like_fields_are_redacted() -> None:
    """# enforces Playbook Sec 6: never log secrets, OTP codes, session tokens, passwords."""
    record = _emit_and_capture(
        "test.redaction.secrets",
        "otp requested",
        {
            "otp_code": "123456",
            "password": "hunter2",
            "session_token": "sess_abc123",
            "access_token": "tok_xyz",
            "api_key": "key_123",
        },
    )
    assert record["otp_code"] == "***REDACTED***"
    assert record["password"] == "***REDACTED***"
    assert record["session_token"] == "***REDACTED***"
    assert record["access_token"] == "***REDACTED***"
    assert record["api_key"] == "***REDACTED***"


def test_safe_identifiers_are_not_redacted() -> None:
    record = _emit_and_capture(
        "test.redaction.safe",
        "user action",
        {"phone_number": "+998901234567", "trace_id": "abc-123", "user_id": "u-1"},
    )
    assert record["phone_number"] == "+998901234567"
    assert record["trace_id"] == "abc-123"
    assert record["user_id"] == "u-1"


def test_redaction_is_case_insensitive_on_field_name() -> None:
    record = _emit_and_capture("test.redaction.case", "x", {"OTP_Code": "999999"})
    assert record["OTP_Code"] == "***REDACTED***"


def test_json_formatter_includes_standard_fields() -> None:
    record = _emit_and_capture("test.redaction.shape", "hello world", {})
    assert record["message"] == "hello world"
    assert record["level"] == "INFO"
    assert record["logger"] == "test.redaction.shape"
    assert "timestamp" in record


def test_configure_logging_is_idempotent() -> None:
    configure_logging(level="debug")
    first_handler_count = len(logging.getLogger().handlers)
    configure_logging(level="debug")
    second_handler_count = len(logging.getLogger().handlers)
    assert first_handler_count == second_handler_count == 1
