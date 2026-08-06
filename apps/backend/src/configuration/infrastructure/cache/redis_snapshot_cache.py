"""Redis-backed `SnapshotCachePort` adapter (Config Framework Sec 2.4: consumer-facing snapshot
distribution; DDD Sec 8.3.3 "the platform keeps serving the last good snapshot if BC-04 is
briefly unavailable"). One key per (entity_type, code); a per-entity-type set tracks all codes
currently published, for `list_current` (used by the public `listCategories` operation).
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from configuration.domain import ConfigEntityType

_KEY_PREFIX = "configuration:snapshot"


def _snapshot_key(entity_type: ConfigEntityType, code: str) -> str:
    return f"{_KEY_PREFIX}:{entity_type.value}:{code}"


def _index_key(entity_type: ConfigEntityType) -> str:
    return f"{_KEY_PREFIX}:index:{entity_type.value}"


class RedisSnapshotCache:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def put(self, entity_type: ConfigEntityType, code: str, snapshot: dict[str, Any]) -> None:
        await self._redis.set(_snapshot_key(entity_type, code), json.dumps(snapshot, default=str))
        await self._redis.sadd(_index_key(entity_type), code)

    async def get(self, entity_type: ConfigEntityType, code: str) -> dict[str, Any] | None:
        raw = await self._redis.get(_snapshot_key(entity_type, code))
        if raw is None:
            return None
        result: dict[str, Any] = json.loads(raw)
        return result

    async def invalidate(self, entity_type: ConfigEntityType, code: str) -> None:
        await self._redis.delete(_snapshot_key(entity_type, code))
        await self._redis.srem(_index_key(entity_type), code)

    async def list_current(self, entity_type: ConfigEntityType) -> list[dict[str, Any]]:
        codes = await self._redis.smembers(_index_key(entity_type))
        results: list[dict[str, Any]] = []
        for code in codes:
            code_str = code.decode() if isinstance(code, bytes) else code
            snapshot = await self.get(entity_type, code_str)
            if snapshot is not None:
                results.append(snapshot)
        return results
