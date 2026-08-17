"""Resets the global rate-limit counter before each test in this directory.

`main.create_app()` always wires the real `GlobalRateLimitMiddleware` against `REDIS_HOST`
(see `main.py`'s own comments) -- unlike `configuration`'s use cases, there is no
`dependency_overrides` seam for middleware, so every `TestClient` built here shares the SAME
Redis-backed per-IP counter as every other test in the whole pytest run that also builds a real
app via `create_app()`. Across the full suite (QG-03 runs ~1780 tests in one process) the counter
for the shared `TestClient` IP is long past the 300-requests/60s budget before this directory's
own assertions run, turning an expected 403 (wrong permission key -- the actual thing
`test_configuration_admin_default_deny.py` asserts) into an unrelated 429 (rate limited) --
the middleware doing exactly its documented job, just against a budget this directory's tests
never intended to share (root `conftest.py` calls this directory "safe in the default selection"
because it runs against fakes; the rate limiter is the one real dependency that slips through
that description). Flushing before each test gives it a clean budget regardless of run order or
position in the suite.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import redis

from backbone.persistence.redis_client import redis_url


@pytest.fixture(autouse=True)
def _reset_global_rate_limit() -> Iterator[None]:
    client = redis.Redis.from_url(redis_url())
    try:
        for key in client.scan_iter("backbone:rate_limit:global:*"):
            client.delete(key)
        yield
    finally:
        client.close()
