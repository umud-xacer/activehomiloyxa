"""Seed data (Task P-04 deliverable): the two bootstrap `RoleDefinition`s that reference the
permission-key catalogue, and default `PlatformSettings`. Run once against a fresh database
(idempotent -- skips any head whose code already exists).

Scope note: this seeds the *role definitions* (Config Framework Sec 2.1 "Roles ... Super
Administrator" is a configuration concern, owned by BC-04); it does not create a `UserAccount`
or assign a role to one -- that is identity's (BC-01) own bootstrap concern in its own task, not
yet implemented (Task P-04 excludes implementing other modules). "Super-Admin bootstrap path"
within this module's scope means: the `super-admin` role exists, Published, and ready for
identity to assign once it exists.

Invocable directly: `python -m configuration.infrastructure.seed` (needs the same
POSTGRES_*/REDIS_* environment as every other backbone entrypoint).
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

from redis.asyncio import Redis

from backbone.outbox import OutboxWriter
from backbone.persistence import make_engine, make_session_factory, redis_url, session_scope
from configuration.application import ConfigurationUseCases
from configuration.application.exceptions import GateFailedError
from configuration.domain import (
    SUPER_ADMIN_APPROVAL_ENTITIES,
    ConfigEntityType,
    DuplicateCodeError,
)
from configuration.domain.whitelist import PERMISSION_KEYS, WhitelistRegistry
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence.models import OutboxEvent
from configuration.infrastructure.persistence.repository import SqlalchemyConfigHeadRepository

SEED_MAKER_ID = UUID("00000000-0000-0000-0000-000000000001")
"""Fixed system-actor id for the seed script's authoring step -- distinct from
`SEED_CHECKER_ID` so the maker-checker "different principal" rule (Config Framework Sec 2.3)
is satisfied even for bootstrap data, not bypassed for it."""
SEED_CHECKER_ID = UUID("00000000-0000-0000-0000-000000000002")

_registry = WhitelistRegistry()


def _administrator_permission_keys() -> list[str]:
    """Every catalogue key except the two Super-Admin-only approve keys (Config Framework
    Sec 2.3: "role and settings changes require Super-Administrator approval")."""
    super_admin_only = {
        _registry.approve_permission_key(entity_type.value)
        for entity_type in SUPER_ADMIN_APPROVAL_ENTITIES
    }
    return sorted(PERMISSION_KEYS - super_admin_only)


def _super_admin_permission_keys() -> list[str]:
    """The full catalogue (SRS Sec 4: "All Administrator rights plus role/permission management
    and platform settings")."""
    return sorted(PERMISSION_KEYS)


async def _seed_role(
    use_cases: ConfigurationUseCases,
    *,
    code: str,
    role_name: str,
    permission_keys: list[str],
    now: datetime,
) -> None:
    try:
        _head, version = await use_cases.create_draft(
            ConfigEntityType.ROLE_DEFINITION,
            code=code,
            business_owner="Super Administrator",
            definition={
                "descriptor": {"name": {"uz_latn": role_name}},
                "role_name": role_name,
                "permission_keys": permission_keys,
            },
            actor_id=SEED_MAKER_ID,
            now=now,
        )
    except DuplicateCodeError:
        return

    head = await use_cases.get_head(ConfigEntityType.ROLE_DEFINITION, version.head_id)
    # Bootstrap authority, not the *candidate* role's own grant -- defining the "administrator"
    # role does not itself carry role-definition:approve, but the operator running this seed
    # script (standing in for the platform bootstrap process) acts with full catalogue
    # authority regardless of which role is being authored.
    bootstrap_authority = frozenset(_super_admin_permission_keys())
    step1 = await use_cases.publish(
        ConfigEntityType.ROLE_DEFINITION,
        head.id,
        version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=bootstrap_authority,
        approval_note="seed: bootstrap role",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.ROLE_DEFINITION,
            head.id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=bootstrap_authority,
            approval_note="seed: bootstrap approval",
            now=now,
        )


async def _seed_platform_settings(use_cases: ConfigurationUseCases, *, now: datetime) -> None:
    definition = {
        "descriptor": {"name": {"uz_latn": "Default platform settings"}},
        "settings_scope": "GLOBAL",
        "settings": {
            "listing.default_expiry_days": 30,
            "feature_flag.banners_enabled": True,
            "feature_flag.messaging_enabled": True,
            "otp.expiry_minutes": 5,
            "session.expiry_hours": 720,
            "search.default_page_size": 20,
        },
        "homepage_zones": [],
        "navigation_items": [],
        "seo_templates": [],
        "static_pages": [],
    }
    try:
        _head, version = await use_cases.create_draft(
            ConfigEntityType.PLATFORM_SETTINGS,
            code="platform-settings-global",
            business_owner="Super Administrator",
            definition=definition,
            actor_id=SEED_MAKER_ID,
            now=now,
        )
    except DuplicateCodeError:
        return

    approve_key = _registry.approve_permission_key(ConfigEntityType.PLATFORM_SETTINGS.value)
    manage_key = _registry.manage_permission_key(ConfigEntityType.PLATFORM_SETTINGS.value)
    step1 = await use_cases.publish(
        ConfigEntityType.PLATFORM_SETTINGS,
        version.head_id,
        version.id,
        actor_id=SEED_MAKER_ID,
        actor_permission_keys=frozenset({manage_key}),
        approval_note="seed: bootstrap settings",
        now=now,
    )
    if step1.status.value == "APPROVAL":
        await use_cases.publish(
            ConfigEntityType.PLATFORM_SETTINGS,
            version.head_id,
            step1.id,
            actor_id=SEED_CHECKER_ID,
            actor_permission_keys=frozenset({approve_key}),
            approval_note="seed: bootstrap settings approval",
            now=now,
        )


async def run_seed() -> None:
    engine = make_engine()
    session_factory = make_session_factory(engine)
    redis = Redis.from_url(redis_url())
    cache = RedisSnapshotCache(redis)
    now = datetime.now(UTC)

    try:
        async with session_scope(session_factory) as session:
            repo = SqlalchemyConfigHeadRepository(session)
            outbox = OutboxWriter(session, OutboxEvent)
            use_cases = ConfigurationUseCases(repo, cache, outbox)

            try:
                await _seed_role(
                    use_cases,
                    code="super-admin",
                    role_name="Super Administrator",
                    permission_keys=_super_admin_permission_keys(),
                    now=now,
                )
                await _seed_role(
                    use_cases,
                    code="administrator",
                    role_name="Administrator",
                    permission_keys=_administrator_permission_keys(),
                    now=now,
                )
                await _seed_platform_settings(use_cases, now=now)
            except GateFailedError as exc:
                raise RuntimeError(
                    f"seed data failed the validation gate: {exc.result.errors}"
                ) from exc
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(run_seed())


if __name__ == "__main__":
    main()
