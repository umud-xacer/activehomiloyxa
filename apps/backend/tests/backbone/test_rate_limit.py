"""Unit tests for `backbone.rate_limit`: `RedisWindowCounter`'s fixed/rearm-window semantics and
`GlobalRateLimitMiddleware`'s throttle, exempt-path, and fail-open behavior. A minimal in-memory
fake stands in for `redis.asyncio.Redis` (only the 5 methods `RedisWindowCounter` actually calls),
keeping this suite in the same "no real datastore needed" class as every other module's
`test_api.py` -- there was no coverage at all for either file before this suite."""

from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from backbone.rate_limit.middleware import GlobalRateLimitMiddleware
from backbone.rate_limit.tracker import RedisWindowCounter


class _FakeRedis:
    """In-memory stand-in for the 5 `redis.asyncio.Redis` methods `RedisWindowCounter` calls."""

    def __init__(self) -> None:
        self.counts: dict[str, int] = {}
        self.ttls: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.ttls[key] = seconds

    async def get(self, key: str) -> str | None:
        count = self.counts.get(key)
        return str(count) if count is not None else None

    async def ttl(self, key: str) -> int:
        return self.ttls.get(key, -2)

    async def delete(self, key: str) -> None:
        self.counts.pop(key, None)
        self.ttls.pop(key, None)


class _RedisDown:
    """Every method raises, simulating an unreachable Redis (connection refused/timeout)."""

    async def incr(self, key: str) -> int:
        raise ConnectionError("redis unavailable")


# --- RedisWindowCounter -------------------------------------------------------------------------


async def test_increment_counts_up_per_identifier() -> None:
    counter = RedisWindowCounter(_FakeRedis(), key_prefix="test")
    assert await counter.increment("a", window_seconds=60, rearm=False) == 1
    assert await counter.increment("a", window_seconds=60, rearm=False) == 2
    assert await counter.increment("b", window_seconds=60, rearm=False) == 1


async def test_reset_clears_the_counter() -> None:
    counter = RedisWindowCounter(_FakeRedis(), key_prefix="test")
    await counter.increment("a", window_seconds=60, rearm=False)
    await counter.reset("a")
    assert await counter.get_count("a") == 0


async def test_rearm_true_re_arms_ttl_on_every_call() -> None:
    redis = _FakeRedis()
    counter = RedisWindowCounter(redis, key_prefix="test")
    await counter.increment("a", window_seconds=100, rearm=True)
    await counter.increment("a", window_seconds=50, rearm=True)
    assert redis.ttls["test:a"] == 50


async def test_rearm_false_only_sets_ttl_on_the_first_call() -> None:
    redis = _FakeRedis()
    counter = RedisWindowCounter(redis, key_prefix="test")
    await counter.increment("b", window_seconds=100, rearm=False)
    await counter.increment("b", window_seconds=50, rearm=False)
    assert redis.ttls["test:b"] == 100


async def test_get_retry_after_seconds_is_zero_with_no_counter() -> None:
    counter = RedisWindowCounter(_FakeRedis(), key_prefix="test")
    assert await counter.get_retry_after_seconds("nobody") == 0


# --- GlobalRateLimitMiddleware -------------------------------------------------------------------


def _app_with_middleware(
    redis: object, *, max_requests: int = 2, window_seconds: int = 60
) -> Starlette:
    async def _ok(request: object) -> PlainTextResponse:
        return PlainTextResponse("ok")

    app = Starlette(routes=[Route("/x", _ok), Route("/health", _ok)])
    app.add_middleware(
        GlobalRateLimitMiddleware,
        redis=redis,
        max_requests=max_requests,
        window_seconds=window_seconds,
    )
    return app


def test_requests_under_the_limit_pass_through() -> None:
    client = TestClient(_app_with_middleware(_FakeRedis(), max_requests=2))
    assert client.get("/x").status_code == 200
    assert client.get("/x").status_code == 200


def test_requests_over_the_limit_get_429_with_retry_after() -> None:
    client = TestClient(_app_with_middleware(_FakeRedis(), max_requests=1))
    assert client.get("/x").status_code == 200
    response = client.get("/x")
    assert response.status_code == 429
    assert response.json()["code"] == "RATE_LIMITED"
    assert "retry-after" in response.headers


def test_exempt_paths_are_never_throttled() -> None:
    client = TestClient(_app_with_middleware(_FakeRedis(), max_requests=1))
    for _ in range(5):
        assert client.get("/health").status_code == 200


def test_different_ips_get_independent_budgets() -> None:
    client = TestClient(
        _app_with_middleware(_FakeRedis(), max_requests=1),
        headers={},
    )
    first = client.get("/x", headers={"cf-connecting-ip": "1.1.1.1"})
    second = client.get("/x", headers={"cf-connecting-ip": "2.2.2.2"})
    assert first.status_code == 200
    assert second.status_code == 200


def test_fails_open_when_redis_is_unreachable() -> None:
    """A Redis outage must not turn into a site-wide 500 -- see the middleware's own docstring
    on why this wraps EVERY request, unlike login/OTP's own narrower lockouts."""
    client = TestClient(_app_with_middleware(_RedisDown(), max_requests=1))
    response = client.get("/x")
    assert response.status_code == 200
    assert response.text == "ok"
