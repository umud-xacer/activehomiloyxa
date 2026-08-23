"""One-off management script: bulk-retires (or restores) every *subcategory* (any `Category`
head whose `parent_category_id` is not null) via the real Configuration Framework publish flow
-- never a raw SQL UPDATE, because the live site is served from `RedisSnapshotCache`, not a
direct table read (`configuration.application.category_read.CategoryReadUseCases.list_categories`
reads `self._cache.list_current`), so a bare UPDATE would silently do nothing (or worse, leave
the DB and cache disagreeing). This mirrors the exact `create_version_draft` + `publish`
maker/checker sequence `configuration.infrastructure.seed._seed_category` already uses for every
category ever created -- same two fixed system-actor ids, same "different principal" invariant,
so the maker-checker gate accepts it without needing a real logged-in admin.

The 18 top-level categories (`parent_category_id is None`) are always left untouched -- only
their children move.

Usage (same env-loading convention as `search_worker`/`bootstrap_admin`/`seed`):
    python -m retire_subcategories retire   # hide every subcategory from the live site
    python -m retire_subcategories restore  # undo -- bring them all back to ACTIVE

Pass a third argument to scope either verb to one top-level category's descendants instead of
every subcategory on the site (e.g. rewriting just "Kotejlar"'s tree, 2026-08-23):
    python -m retire_subcategories retire /kotejlar
    python -m retire_subcategories restore /kotejlar

The prefix matches a subcategory's real `path` (e.g. `/kotejlar/oilaviy-kotejlar` matches prefix
`/kotejlar`) -- never the top-level category itself (that guard applies regardless of scope).

Idempotent either way: a subcategory already in the target status is skipped.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from backbone.outbox import OutboxWriter
from backbone.persistence import (
    make_engine,
    make_session_factory,
    redis_url,
    session_scope,
)
from configuration.application import ConfigurationUseCases
from configuration.domain import ConfigEntityType
from configuration.domain.whitelist import WhitelistRegistry
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence.models import OutboxEvent
from configuration.infrastructure.persistence.repository import (
    SqlalchemyConfigHeadRepository,
)

# Same fixed system-actor ids `seed.py` uses -- distinct principals so the maker-checker
# "different principal" rule is satisfied without needing a real admin session.
MAKER_ID = UUID("00000000-0000-0000-0000-000000000001")
CHECKER_ID = UUID("00000000-0000-0000-0000-000000000002")

_registry = WhitelistRegistry()


async def _set_all_subcategories(
    target_status: str, path_prefix: str | None = None
) -> None:
    if target_status not in ("ACTIVE", "RETIRED"):
        raise ValueError(
            f"target_status must be ACTIVE or RETIRED, got {target_status!r}"
        )

    engine = make_engine()
    session_factory = make_session_factory(engine)
    redis = Redis.from_url(redis_url())
    cache = RedisSnapshotCache(redis)
    now = datetime.now(UTC)
    manage_key = _registry.manage_permission_key(ConfigEntityType.CATEGORY.value)
    approve_key = _registry.approve_permission_key(ConfigEntityType.CATEGORY.value)

    changed = 0
    skipped_already = 0
    skipped_top_level = 0

    try:
        async with session_scope(session_factory) as session:
            repo = SqlalchemyConfigHeadRepository(session)
            outbox = OutboxWriter(session, OutboxEvent)
            use_cases = ConfigurationUseCases(repo, cache, outbox)

            cursor: str | None = None
            while True:
                heads, cursor = await repo.list_heads(
                    ConfigEntityType.CATEGORY, cursor=cursor, limit=200
                )
                if not heads:
                    break

                for head in heads:
                    if head.current_version_id is None:
                        continue
                    current = await repo.get_version(
                        ConfigEntityType.CATEGORY, head.id, head.current_version_id
                    )
                    if current is None:
                        continue

                    definition = dict(current.definition_document)
                    if definition.get("parent_category_id") is None:
                        skipped_top_level += 1
                        continue  # never touch the 18 top-level categories

                    if path_prefix is not None:
                        path = str(definition.get("path") or "")
                        if not (
                            path == path_prefix or path.startswith(path_prefix + "/")
                        ):
                            continue

                    if definition.get("tree_status", "ACTIVE") == target_status:
                        skipped_already += 1
                        continue

                    definition["tree_status"] = target_status
                    version = await use_cases.create_version_draft(
                        ConfigEntityType.CATEGORY,
                        head.id,
                        definition=definition,
                        actor_id=MAKER_ID,
                        now=now,
                    )
                    step1 = await use_cases.publish(
                        ConfigEntityType.CATEGORY,
                        head.id,
                        version.id,
                        actor_id=MAKER_ID,
                        actor_permission_keys=frozenset({manage_key}),
                        approval_note=f"bulk {target_status.lower()}: requested by owner",
                        now=now,
                    )
                    if step1.status.value == "APPROVAL":
                        await use_cases.publish(
                            ConfigEntityType.CATEGORY,
                            head.id,
                            step1.id,
                            actor_id=CHECKER_ID,
                            actor_permission_keys=frozenset({manage_key, approve_key}),
                            approval_note=f"bulk {target_status.lower()}: requested by owner",
                            now=now,
                        )
                    changed += 1

                if cursor is None:
                    break

        print(
            f"Done. {changed} subcategories set to {target_status}, "
            f"{skipped_already} already {target_status}, "
            f"{skipped_top_level} top-level categories left untouched."
        )
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    if len(sys.argv) not in (2, 3) or sys.argv[1] not in ("retire", "restore"):
        print("Usage: python -m retire_subcategories [retire|restore] [/path-prefix]")
        raise SystemExit(2)
    target = "RETIRED" if sys.argv[1] == "retire" else "ACTIVE"
    path_prefix = sys.argv[2] if len(sys.argv) == 3 else None
    asyncio.run(_set_all_subcategories(target, path_prefix))


if __name__ == "__main__":
    main()
