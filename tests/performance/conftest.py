"""Reuses `tests/integration/conftest.py`'s fixtures verbatim (the same pattern `tests/
degradation/conftest.py`/`tests/idempotency/conftest.py`/`tests/e2e/conftest.py` already
established for this repo's cross-cutting suites)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.persistence import make_engine, make_session_factory
from tests.integration.conftest import (  # noqa: F401  re-exported as fixtures for this directory
    _skip_without_postgres,
    ensure_analytics_schema_via_migration,
    ensure_clean_schema,
)

pytestmark = pytest.mark.integration

OPENSEARCH_AVAILABLE = bool(os.environ.get("OPENSEARCH_HOST"))

_DEFAULT_ENV: dict[str, str] = {
    "SESSION_COOKIE_NAME": "ah_session",
    "SESSION_SIGNING_KEY": "perf-test-signing-key-not-a-real-secret",
    "ESKIZ_API_BASE_URL": "https://example.invalid/eskiz",
    "ESKIZ_EMAIL": "perf-test@example.invalid",
    "ESKIZ_PASSWORD": "unused-perf-test-value",
    "ESKIZ_SENDER_NICKNAME": "unused-perf-test-value",
    "SMTP_HOST": "example.invalid",
    "SMTP_PORT": "587",
    "SMTP_USER": "unused-perf-test-value",
    "SMTP_PASSWORD": "unused-perf-test-value",
    "WEB_PUSH_VAPID_PUBLIC_KEY": "unused-perf-test-value",
    "WEB_PUSH_VAPID_PRIVATE_KEY": "unused-perf-test-value",
    "GOOGLE_OAUTH_CLIENT_ID": "unused-perf-test-value",
    "GOOGLE_OAUTH_CLIENT_SECRET": "unused-perf-test-value",
    "YANDEX_MAPS_API_KEY": "unused-perf-test-value",
    "MINIO_ENDPOINT": "localhost:9000",
    "MINIO_ROOT_USER": "active_home",
    "MINIO_ROOT_PASSWORD": "active_home_local_dev_only",
    "MINIO_MEDIA_BUCKET": "active-home-media",
    "MINIO_USE_TLS": "false",
    "MEDIA_CDN_BASE_URL": "http://localhost:8080/media",
    "MEDIA_PRESIGN_EXPIRY_SECONDS": "900",
    "CLAMAV_HOST": "localhost",
    "CLAMAV_PORT": "3310",
}


@pytest.fixture(scope="session", autouse=True)
def _app_environment() -> Iterator[None]:
    """Same process-global-leak guard `tests/e2e/conftest.py::_app_environment` already
    established -- only restore keys THIS fixture actually introduced."""
    previously_unset = [key for key in _DEFAULT_ENV if key not in os.environ]
    for key, value in _DEFAULT_ENV.items():
        os.environ.setdefault(key, value)
    yield
    for key in previously_unset:
        os.environ.pop(key, None)


@pytest.fixture(autouse=True)
def _skip_without_opensearch() -> None:
    if not OPENSEARCH_AVAILABLE:
        pytest.skip("OPENSEARCH_HOST not set -- no real OpenSearch cluster to benchmark against")


@pytest_asyncio.fixture(scope="module")
async def engine() -> AsyncIterator[AsyncEngine]:
    """Module-scoped, deliberately shadowing `tests/integration/conftest.py`'s function-scoped
    `engine` -- this suite reads PRE-SEEDED, shared data across one benchmark run (`python -m
    tests.performance.seed_cli` populates it once, ahead of time) rather than needing per-test
    schema isolation, and a module-scoped fixture like `sample_listing_id` below cannot depend on
    a function-scoped one (`ScopeMismatch`)."""
    eng = make_engine()
    yield eng
    await eng.dispose()


@pytest.fixture(scope="module")
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return make_session_factory(engine)
