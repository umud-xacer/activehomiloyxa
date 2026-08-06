"""Marks every test needing real datastores as `integration`.

Duplicated from the repo-root `conftest.py` (see it for the full rationale) because conftest
discovery is cut at the rootdir: `scripts/test.sh` passes `--rootdir=.` so the root hook applies
there, but the ad-hoc invocation the project documents -- `pytest -c tools/pytest.ini
path/to/test_file.py::test_name` -- resolves a different rootdir and would never load it. Having
the hook at each test root means `-m "not integration"` excludes these suites however pytest is
invoked, which matters because they truncate the schemas they exercise.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REAL_DATASTORE_DIRS = frozenset({"integration", "e2e", "performance", "degradation", "idempotency"})


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if REAL_DATASTORE_DIRS.intersection(Path(str(item.fspath)).parts):
            item.add_marker(pytest.mark.integration)
