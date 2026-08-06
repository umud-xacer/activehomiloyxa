"""Fail-closed required-environment-variable lookup (Security Sec 14: "a misconfigured deploy
fails safe rather than running degraded"), shared by every connection-URL builder in this
package (Postgres, Redis, ...) rather than duplicated per datastore.
"""

from __future__ import annotations

import os


class MissingInfraConfigError(RuntimeError):
    """Raised at startup when a required infrastructure connection setting is absent."""


def required_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise MissingInfraConfigError(f"required environment variable {name} is not set")
    return value
