"""Redis-backed `OwnerAdminLockoutPort` adapter -- thin wrapper over `backbone.rate_limit`'s
shared `RedisWindowCounter` primitive, kept out of `interfaces/` per DEC-18 (see
`configuration.application.ports.OwnerAdminLockoutPort`'s own docstring for why).
"""

from __future__ import annotations

from backbone.rate_limit.tracker import RedisWindowCounter


class RedisOwnerAdminLockoutCounter:
    def __init__(self, counter: RedisWindowCounter) -> None:
        self._counter = counter

    async def record_failure(self, *, identifier: str, window_seconds: int) -> int:
        return await self._counter.increment(identifier, window_seconds=window_seconds, rearm=True)

    async def get_failure_count(self, *, identifier: str) -> int:
        return await self._counter.get_count(identifier)

    async def get_retry_after_seconds(self, *, identifier: str) -> int:
        return await self._counter.get_retry_after_seconds(identifier)

    async def reset(self, *, identifier: str) -> None:
        await self._counter.reset(identifier)
