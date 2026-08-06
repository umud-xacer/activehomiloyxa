"""Reuses `tests/integration/conftest.py`'s `engine`/`session_factory`/`_skip_without_postgres`
fixtures and `ensure_clean_schema` helper verbatim (pytest picks up fixtures re-exported into a
test module's or conftest's own namespace) rather than duplicating the bare Postgres-connection
plumbing a second time for this directory."""

from __future__ import annotations

import pytest

from tests.integration.conftest import (  # noqa: F401  re-exported as fixtures for this directory
    _skip_without_postgres,
    engine,
    ensure_clean_schema,
    session_factory,
)

pytestmark = pytest.mark.integration
