"""Repo-root pytest hooks.

Exists for one reason: to make the `integration` marker actually apply to the tests it describes.

Every module's `integration/conftest.py` declared `pytestmark = pytest.mark.integration`, which
looks like it marks that directory's tests and does not: `pytestmark` applies only to tests
declared in the *same module*, and a `conftest.py` declares none. The marker therefore matched
nothing -- `pytest -m integration` collected 0 items across 50 such files, while
`pytest -m "not integration"` collected every one of them.

That inverted the safety instruction the project documents. `CLAUDE.md` tells you to "select
unit-only with `-m 'not integration'`" when you don't want real datastores, and these suites
`TRUNCATE`/`ensure_clean_schema` the schemas they exercise. The autouse skip on `POSTGRES_HOST`
hides it whenever that variable is unset -- which is why it went unnoticed -- but once you have
run `scripts/dev-up.sh` and exported the env, as the same documentation tells you to, the
"unit-only" command wipes your database.

Marking by location rather than declaration also means a new file dropped into one of these
directories is covered the day it is written, with nothing to remember.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REAL_DATASTORE_DIRS = frozenset(
    {
        # Per-module suites against real PostgreSQL/Redis/OpenSearch/MinIO.
        "integration",
        # Cross-module suites that also open real engines. Each of these calls
        # `ensure_clean_schema` (or `delete_index`) directly, so they are exactly as destructive
        # as `integration/` despite not being named for it -- `tests/e2e` and `tests/performance`
        # between them cleared `identity`, `catalog` and the search index during what was
        # supposed to be a unit-only run.
        "e2e",
        "performance",
        "degradation",
        "idempotency",
    }
)
"""Directory names whose tests need real datastores. `tests/authorization` is deliberately
absent: it runs against fakes and is safe in the default selection. (`tests/acceptance` was
never a test directory -- it held the requirement-to-test mapping, now under
`docs/assessments/2026-07-24-acceptance/`.)"""


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Marks every test under one of `REAL_DATASTORE_DIRS` as `integration`.

    Additive: a test already carrying the marker is unaffected, since pytest de-duplicates
    identical markers.
    """
    for item in items:
        if REAL_DATASTORE_DIRS.intersection(Path(str(item.fspath)).parts):
            item.add_marker(pytest.mark.integration)
