"""Redacts secret-shaped fields before a log record is emitted (Playbook Sec 6 / Security Sec
12: "never log secrets, OTP codes, session tokens, passwords, or PII beyond safe identifiers --
scrub at the logging boundary"). A denylist of field *names*, not a best-effort scan of message
text: reliably matching an unlabelled secret embedded in free text is not something a filter can
do safely (false negatives), whereas every call site that has a secret to log already has it as
a named value (`logger.info(..., extra={"otp_code": code})`) -- that name is exactly what this
catches, every time, with no guessing.
"""

from __future__ import annotations

import logging

SENSITIVE_FIELD_NAMES = frozenset(
    {
        "password",
        "otp",
        "otp_code",
        "session_token",
        "sessiontoken",
        "token",
        "access_token",
        "refresh_token",
        "secret",
        "client_secret",
        "api_key",
        "apikey",
        "private_key",
        "authorization",
        "auth_header",
    }
)
REDACTED_VALUE = "***REDACTED***"

# LogRecord's own built-in attributes -- never treated as "extra" fields to scan, since e.g.
# `msg`/`args` are the log message itself, not caller-supplied structured data.
_STANDARD_LOG_RECORD_ATTRS = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)))


class RedactingFilter(logging.Filter):
    """Attach to every handler (not just the root logger's own handlers -- a per-module logger
    with `propagate=False` would otherwise bypass it)."""

    def filter(self, record: logging.LogRecord) -> bool:
        for key in list(vars(record)):
            if key in _STANDARD_LOG_RECORD_ATTRS:
                continue
            if key.lower() in SENSITIVE_FIELD_NAMES:
                setattr(record, key, REDACTED_VALUE)
        return True
