"""Reuses `tests/integration/conftest.py`'s fixtures verbatim (see `tests/degradation/conftest.py`
for the identical, already-established rationale). Additionally sets every environment variable
`main.create_app()`/`composition_root.py` reads via `required_env` at dependency-resolution time
for the routes this suite's journey actually exercises (Eskiz/SMTP/ClamAV/MinIO are dummy values
-- this suite never calls a route that would construct those adapters for real, see `tests/e2e/
test_critical_buyer_seller_journey.py`'s own docstring for exactly which routes are exercised and
which are scoped down).
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from tests.integration.conftest import (  # noqa: F401  re-exported as fixtures for this directory
    _skip_without_postgres,
    engine,
    ensure_analytics_schema_via_migration,
    ensure_clean_schema,
    session_factory,
)

pytestmark = pytest.mark.integration

_DEFAULT_ENV: dict[str, str] = {
    "SESSION_COOKIE_NAME": "ah_session",
    "SESSION_SIGNING_KEY": "e2e-test-signing-key-not-a-real-secret",
    "ESKIZ_API_BASE_URL": "https://example.invalid/eskiz",
    "ESKIZ_EMAIL": "e2e-test@example.invalid",
    "ESKIZ_PASSWORD": "unused-e2e-test-value",
    "ESKIZ_SENDER_NICKNAME": "unused-e2e-test-value",
    "SMTP_HOST": "example.invalid",
    "SMTP_PORT": "587",
    "SMTP_USER": "unused-e2e-test-value",
    "SMTP_PASSWORD": "unused-e2e-test-value",
    "WEB_PUSH_VAPID_PUBLIC_KEY": "unused-e2e-test-value",
    "WEB_PUSH_VAPID_PRIVATE_KEY": "unused-e2e-test-value",
    "GOOGLE_OAUTH_CLIENT_ID": "unused-e2e-test-value",
    "GOOGLE_OAUTH_CLIENT_SECRET": "unused-e2e-test-value",
    "YANDEX_MAPS_API_KEY": "unused-e2e-test-value",
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
    """`os.environ` is process-global, so setting these unconditionally (even via `setdefault`)
    would otherwise leak past this suite's own tests into whatever else shares the same pytest
    process (confirmed: it makes `tests/authorization/test_no_route_grants_access.py`'s `logout`
    case pass for the WRONG reason once `ESKIZ_API_BASE_URL` becomes non-empty -- see that test's
    own module docstring). Real CI/default collection order runs `tests/authorization/` before
    `tests/e2e/`, so this was never actually triggered in a real run, but a session-scoped
    autouse fixture with no teardown is still a latent ordering hazard -- restore exactly the
    keys THIS fixture introduced (never touch a key that already had a value) once the session
    ends."""
    previously_unset = [key for key in _DEFAULT_ENV if key not in os.environ]
    for key, value in _DEFAULT_ENV.items():
        os.environ.setdefault(key, value)
    yield
    for key in previously_unset:
        os.environ.pop(key, None)
