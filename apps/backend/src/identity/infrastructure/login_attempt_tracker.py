"""Redis-backed `LoginAttemptTrackerPort` adapter (Security Sec 3.1 brute-force protection --
`LoginLockoutPolicy`). Mirrors `session_store.py`'s own key-prefix-plus-plain-client shape, but
each counter is a bare `INCR`-managed integer, not a JSON blob: there is nothing to deserialize,
just a count and the key's own TTL (which doubles as "how long until this counter forgets about
you" and, once the count crosses the threshold, "how long the lockout lasts" -- one number for
both, see `LoginLockoutPolicy`'s docstring for why that's intentional, not a simplification that
lost a distinction).
"""

from __future__ import annotations

from redis.asyncio import Redis

_KEY_PREFIX = "identity:login_lockout"


def _key(scope: str, identifier: str) -> str:
    return f"{_KEY_PREFIX}:{scope}:{identifier}"


class RedisLoginAttemptTracker:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def record_failure(self, *, scope: str, identifier: str, window_seconds: int) -> int:
        key = _key(scope, identifier)
        count = await self._redis.incr(key)
        # Re-armed on every failure (not just when the key is first created): a gap long enough
        # for the TTL to lapse resets the count to zero on the next INCR anyway, so refreshing it
        # here just makes "consecutive" mean what it sounds like -- failures close enough together
        # to still be within the window keep extending it, exactly like a failed-login streak
        # should.
        await self._redis.expire(key, window_seconds)
        return count

    async def get_failure_count(self, *, scope: str, identifier: str) -> int:
        raw = await self._redis.get(_key(scope, identifier))
        return int(raw) if raw is not None else 0

    async def get_retry_after_seconds(self, *, scope: str, identifier: str) -> int:
        ttl = await self._redis.ttl(_key(scope, identifier))
        return ttl if ttl and ttl > 0 else 0

    async def reset(self, *, scope: str, identifier: str) -> None:
        await self._redis.delete(_key(scope, identifier))
