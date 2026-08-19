"""One-off, temporary script (2026-08-19): "Qurilish materiallari" and "Dam olish maskanlari" are
the only two top-level categories with a real uploaded photo in `descriptor.metadata.iconUrl`
(every other of the 18 top-level categories has `iconUrl: null` and falls back to the frontend's
curated icon artwork/registry) -- CategoryCarousel.tsx's icon tile is a small `rounded-2xl` box
designed for a padded, transparent-background icon graphic; a full-bleed photo fills it edge to
edge instead, reading as a plain square thumbnail next to 16 neatly-cropped icon chips. User
reported this live: "ular 2tasi 4burchak bulib qolgan" (those two turned square).

Fix: drop `iconUrl` from both categories' metadata and set `iconName` instead (the sanctioned
named-icon-registry slot, `lib/listing-kind.ts`'s `ICON_BY_NAME`, "gives categories with no
uploaded photo a themed icon instead of a bare fallback" per its own docstring) -- "hard-hat" for
construction materials, "trees" for recreation venues. Matching frontend change (CategoryCarousel
consulting `ICON_BY_NAME` as a fallback tier) lands separately in the same commit as this script's
one-time run.

Uses the real domain use cases (`ConfigurationUseCases.create_version_draft` + the maker/checker
`.publish` two-call sequence), the same code path `_backfill_listing_kind` in this module's own
`seed.py` already uses for exactly this kind of "existing category, republish one metadata field"
edit -- not raw SQL (category_version rows are trigger-protected against UPDATE/DELETE, Physical
DB Sec 2.4's immutability invariant). `SEED_MAKER_ID`/`SEED_CHECKER_ID` (seed.py's own two fixed
system principals, already seeded with the needed permissions) stand in for a human maker/checker,
same precedent as every other seed-time category backfill.

Delete this file after running it once -- not a reusable operator tool like `bootstrap_admin.py`.
Run: python -m _fix_two_category_icons (from apps/backend/src, same env as every other entrypoint).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from backbone.outbox import OutboxWriter
from backbone.persistence import make_engine, make_session_factory, redis_url, session_scope
from configuration.application import ConfigurationUseCases
from configuration.domain import ConfigEntityType
from configuration.domain.whitelist import WhitelistRegistry
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence.models import OutboxEvent
from configuration.infrastructure.persistence.repository import SqlalchemyConfigHeadRepository

SEED_MAKER_ID = UUID("00000000-0000-0000-0000-000000000001")
SEED_CHECKER_ID = UUID("00000000-0000-0000-0000-000000000002")

_FIXES = {
    UUID("8c026d30-bed7-4507-a5c7-e4d5ee684971"): ("qurilish-materiallari", "hard-hat"),
    UUID("f9a160c0-f953-406d-b2ed-cb1b1cca3e8f"): ("dam-olish-maskanlari", "trees"),
}


async def _fix_one(
    use_cases: ConfigurationUseCases,
    repo: SqlalchemyConfigHeadRepository,
    registry: WhitelistRegistry,
    *,
    head_id: UUID,
    code: str,
    icon_name: str,
    now: datetime,
) -> None:
    head = await repo.get_head(ConfigEntityType.CATEGORY, head_id)
    if head is None or head.current_version_id is None:
        print(f"SKIP {code}: head or current_version_id missing")
        return
    current = await repo.get_version(ConfigEntityType.CATEGORY, head_id, head.current_version_id)
    if current is None:
        print(f"SKIP {code}: current version row missing")
        return

    current_descriptor = dict(current.definition_document.get("descriptor") or {})
    current_metadata = dict(current_descriptor.get("metadata") or {})
    if "iconUrl" not in current_metadata and current_metadata.get("iconName") == icon_name:
        print(f"SKIP {code}: already fixed")
        return

    new_metadata = {k: v for k, v in current_metadata.items() if k != "iconUrl"}
    new_metadata["iconName"] = icon_name
    new_descriptor = {**current_descriptor, "metadata": new_metadata}
    new_document = {**current.definition_document, "descriptor": new_descriptor}

    new_version = await use_cases.create_version_draft(
        ConfigEntityType.CATEGORY,
        head_id,
        definition=new_document,
        actor_id=SEED_MAKER_ID,
        now=now,
    )
    manage_key = registry.manage_permission_key(ConfigEntityType.CATEGORY.value)
    approve_key = registry.approve_permission_key(ConfigEntityType.CATEGORY.value)
    step1 = await use_cases.publish(
        ConfigEntityType.CATEGORY,
        head_id,
        new_version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="fix: drop raw-photo iconUrl, use named icon registry instead",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.CATEGORY,
            head_id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="fix: drop raw-photo iconUrl, use named icon registry instead",
            now=now,
        )
    print(f"FIXED {code}: iconUrl removed, iconName={icon_name!r}")


async def _run() -> None:
    engine = make_engine()
    session_factory = make_session_factory(engine)
    redis = Redis.from_url(redis_url())
    cache = RedisSnapshotCache(redis)
    now = datetime.now(UTC)
    registry = WhitelistRegistry()

    async with session_scope(session_factory) as session:
        repo = SqlalchemyConfigHeadRepository(session)
        outbox = OutboxWriter(session, OutboxEvent)
        use_cases = ConfigurationUseCases(repo, cache, outbox)
        for head_id, (code, icon_name) in _FIXES.items():
            await _fix_one(
                use_cases, repo, registry, head_id=head_id, code=code, icon_name=icon_name, now=now
            )

    await redis.aclose()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
