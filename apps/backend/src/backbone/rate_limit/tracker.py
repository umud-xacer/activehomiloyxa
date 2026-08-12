"""Generic Redis `INCR`+TTL window counter -- the same primitive `identity`'s own
`RedisLoginAttemptTracker` (`identity/infrastructure/login_attempt_tracker.py`) already uses for
login/OTP brute-force lockout, reimplemented here in `backbone` so any module's `interfaces`/
`infrastructure` layer can reuse it for its OWN IP-scoped throttling without a forbidden
cross-module import (`tools/importlinter.cfg`'s `backbone-imports-only-shared-kernel` contract).
`identity`'s own tracker is left as-is (untouched, still tested) rather than rewritten on top of
this -- not worth the churn/risk on already-working brute-force-critical code for this task; new
consumers (the owner-admin-access oracle lockout, the global rate-limit middleware) build on this
one instead.
"""

from __future__ import annotations

from redis.asyncio import Redis


class RedisWindowCounter:
    """One counter key per `identifier` under `key_prefix`, TTL-bounded to `window_seconds`.

    `rearm` (passed per-call, not fixed at construction -- the two consumers this backs need
    opposite semantics from the same primitive):
    - `rearm=True` (lockout counters: owner-admin-access oracle, OTP-verify-by-IP): the TTL is
      re-armed to `window_seconds` on every increment, so "N failures" means N *consecutive*
      failures close enough together to keep re-arming the window -- an attacker who pauses long
      enough for the TTL to lapse starts counting from zero again, matching
      `identity.domain.policies.LoginLockoutPolicy`'s own documented reasoning exactly.
    - `rearm=False` (the global request-rate counter): the TTL is set once, on the first
      increment, and never touched again -- a plain fixed window ("at most N requests per rolling
      `window_seconds`"). Re-arming here would mean a sustained high-frequency caller (a busy
      legitimate IP, not just an attacker) never sees its count reset as long as requests keep
      arriving, which is the wrong shape for a generic throughput cap.
    """

    def __init__(self, redis: Redis, *, key_prefix: str) -> None:
        self._redis = redis
        self._key_prefix = key_prefix

    def _key(self, identifier: str) -> str:
        return f"{self._key_prefix}:{identifier}"

    async def increment(self, identifier: str, *, window_seconds: int, rearm: bool) -> int:
        key = self._key(identifier)
        count = await self._redis.incr(key)
        if rearm or count == 1:
            await self._redis.expire(key, window_seconds)
        return count

    async def get_count(self, identifier: str) -> int:
        raw = await self._redis.get(self._key(identifier))
        return int(raw) if raw is not None else 0

    async def get_retry_after_seconds(self, identifier: str) -> int:
        ttl = await self._redis.ttl(self._key(identifier))
        return ttl if ttl and ttl > 0 else 0

    async def reset(self, identifier: str) -> None:
        await self._redis.delete(self._key(identifier))
