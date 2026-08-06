"""Reuses `tests/integration/conftest.py`'s fixtures verbatim (see `tests/degradation/conftest.py`
for the identical, already-established rationale -- pytest picks up fixtures re-exported into a
directory's own conftest namespace)."""

from __future__ import annotations

import pytest

from tests.integration.conftest import (  # noqa: F401  re-exported as fixtures for this directory
    _skip_without_postgres,
    engine,
    ensure_analytics_schema_via_migration,
    ensure_clean_schema,
    session_factory,
)

pytestmark = pytest.mark.integration
