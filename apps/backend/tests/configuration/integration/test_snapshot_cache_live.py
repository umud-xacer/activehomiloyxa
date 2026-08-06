"""`RedisSnapshotCache` against real Redis (Config Framework Sec 2.4: consumer-facing snapshot
distribution)."""

from __future__ import annotations

import pytest
from redis.asyncio import Redis

from configuration.domain.entity_types import ConfigEntityType
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache


@pytest.mark.asyncio
async def test_put_then_get_round_trips_snapshot(redis_client: Redis) -> None:
    cache = RedisSnapshotCache(redis_client)
    await cache.put(ConfigEntityType.CATEGORY, "housing", {"code": "housing", "path": "/housing"})
    result = await cache.get(ConfigEntityType.CATEGORY, "housing")
    assert result == {"code": "housing", "path": "/housing"}


@pytest.mark.asyncio
async def test_get_missing_key_returns_none(redis_client: Redis) -> None:
    cache = RedisSnapshotCache(redis_client)
    assert await cache.get(ConfigEntityType.CATEGORY, "does-not-exist") is None


@pytest.mark.asyncio
async def test_invalidate_removes_from_get_and_index(redis_client: Redis) -> None:
    cache = RedisSnapshotCache(redis_client)
    await cache.put(ConfigEntityType.CATEGORY, "housing", {"code": "housing"})
    await cache.invalidate(ConfigEntityType.CATEGORY, "housing")
    assert await cache.get(ConfigEntityType.CATEGORY, "housing") is None
    assert await cache.list_current(ConfigEntityType.CATEGORY) == []


@pytest.mark.asyncio
async def test_list_current_returns_every_put_snapshot_for_the_entity_type(
    redis_client: Redis,
) -> None:
    cache = RedisSnapshotCache(redis_client)
    await cache.put(ConfigEntityType.CATEGORY, "housing", {"code": "housing"})
    await cache.put(ConfigEntityType.CATEGORY, "commercial", {"code": "commercial"})
    await cache.put(ConfigEntityType.ROLE_DEFINITION, "editor", {"code": "editor"})

    categories = await cache.list_current(ConfigEntityType.CATEGORY)
    assert {c["code"] for c in categories} == {"housing", "commercial"}

    roles = await cache.list_current(ConfigEntityType.ROLE_DEFINITION)
    assert {r["code"] for r in roles} == {"editor"}
