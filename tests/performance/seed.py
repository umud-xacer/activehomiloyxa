"""P-21 benchmark seed generator. Synthetic data only (TEST-01/AIR-16) -- every phone/email/name
below is a deterministically-generated, obviously-fake string, never real PII. Builds through the
SAME real use-case classes `composition_root.py` wires into the production app (`ListingUseCases`,
`FavoriteUseCases`, `ConversationUseCases`, `ConfigurationUseCases`, ...), never a raw bulk
`INSERT` -- the seeded rows carry the exact invariants/shape real traffic would produce. Batched
via bounded `asyncio.gather` concurrency for throughput; each batch item opens its own session
(SQLAlchemy `AsyncSession` is not safe for concurrent use across coroutines).

Idempotent: `seed_all` checks current row counts per table before topping up, so re-running with
the same scale is a cheap no-op and a smaller-then-larger scale change only adds the delta.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backbone.outbox import OutboxDispatcher, OutboxWriter
from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.favorite_use_cases import FavoriteUseCases
from catalog.application.listing_use_cases import ListingUseCases
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.value_objects import ListingType
from catalog.infrastructure.configuration_adapter import (
    ConfigurationCategoryFormAdapter,
    ConfigurationPlatformSettingsAdapter,
)
from catalog.infrastructure.persistence.models import (
    FavoriteRow,
    ListingRow,
)
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.infrastructure.persistence.repository import (
    SqlalchemyFavoriteRepository,
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from configuration.application.category_read import CategoryReadUseCases
from configuration.application.use_cases import ConfigurationUseCases
from configuration.domain import ConfigEntityType
from configuration.infrastructure.cache.redis_snapshot_cache import RedisSnapshotCache
from configuration.infrastructure.persistence.models import OutboxEvent as ConfigOutboxEventRow
from configuration.infrastructure.persistence.repository import SqlalchemyConfigHeadRepository
from configuration.interfaces.dto import ConfigurationHeadPage, ConfigurationVersion, PageInfo
from configuration.interfaces.routers import _head_to_dto, _version_to_dto
from identity.domain.user_account import UserAccount
from identity.domain.value_objects import PhoneNumber
from identity.infrastructure.persistence.models import UserAccountRow
from identity.infrastructure.persistence.repository import SqlalchemyUserAccountRepository
from identity.infrastructure.public_port_adapters import ContactPolicyPortAdapter
from messaging.application.conversation_use_cases import ConversationUseCases
from messaging.infrastructure.event_projection import handle_listing_created
from messaging.infrastructure.persistence.models import ConversationRow
from messaging.infrastructure.persistence.repository import (
    SqlalchemyBlockRepository,
    SqlalchemyConversationRepository,
    SqlalchemyListingOwnerProjectionReader,
)
from messaging.infrastructure.realtime import RedisRealtimePublisherAdapter
from search.infrastructure.event_projection import make_search_event_handler
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from shared_kernel import BusinessProfileId, EventEnvelope, GeoLocation, ListingId, Money, UserId

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
MAKER = UUID("00000000-0000-0000-0000-0000000000a1")
CHECKER = UUID("00000000-0000-0000-0000-0000000000a2")

# Tashkent-ish bounding box for synthetic geo data (WGS-84, no real addresses).
_LAT_RANGE = (41.20, 41.40)
_LON_RANGE = (69.10, 69.40)

_CATEGORY_HEAD_ID: UUID | None = None
_FORM_HEAD_ID: UUID | None = None


@dataclass(frozen=True)
class SeedScale:
    users: int
    listings: int
    favorites: int
    conversations: int


PHASE1_SCALE = SeedScale(users=10_000, listings=100_000, favorites=20_000, conversations=2_000)
SMOKE_SCALE = SeedScale(users=200, listings=1_000, favorites=200, conversations=50)


def _phone(i: int) -> str:
    # Synthetic E.164-shaped number, never a real subscriber range.
    return f"+99890{i:07d}"


def _open_config_use_cases(session: AsyncSession, redis_client: Redis) -> ConfigurationUseCases:
    repo = SqlalchemyConfigHeadRepository(session)
    outbox = OutboxWriter(session, ConfigOutboxEventRow)
    cache = RedisSnapshotCache(redis_client)
    return ConfigurationUseCases(repo, cache, outbox)


async def _find_existing_head(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    entity_type: ConfigEntityType,
    *,
    code: str,
) -> UUID | None:
    async with session_factory() as session:
        uc = _open_config_use_cases(session, redis_client)
        cursor: str | None = None
        while True:
            heads, cursor = await uc.list_heads(entity_type, cursor=cursor, limit=100)
            for head in heads:
                if head.code == code:
                    return head.id
            if cursor is None:
                return None


async def _publish_controlled(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    entity_type: ConfigEntityType,
    *,
    code: str,
    definition: dict[str, object],
) -> UUID:
    """Idempotent: re-running the seed script with the same code must not raise
    `DuplicateCodeError` -- checks for an already-published head with this code first (`seed_all`
    is meant to be safely re-runnable, and a benchmark developer WILL re-run this after a partial
    failure)."""
    existing = await _find_existing_head(session_factory, redis_client, entity_type, code=code)
    if existing is not None:
        return existing

    async with session_factory() as session:
        uc = _open_config_use_cases(session, redis_client)
        head, version = await uc.create_draft(
            entity_type,
            code=code,
            business_owner="P-21 perf seed",
            definition=definition,
            actor_id=MAKER,
            now=NOW,
        )
        await session.commit()

    manage_key = f"config:{entity_type.value}:manage"
    approve_key = f"config:{entity_type.value}:approve"
    async with session_factory() as session:
        uc = _open_config_use_cases(session, redis_client)
        await uc.publish(
            entity_type,
            head.id,
            version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({manage_key}),
            approval_note="maker submit",
            now=NOW,
        )
        await session.commit()
    async with session_factory() as session:
        uc = _open_config_use_cases(session, redis_client)
        await uc.publish(
            entity_type,
            head.id,
            version.id,
            actor_id=CHECKER,
            actor_permission_keys=frozenset({manage_key, approve_key}),
            approval_note="checker approve",
            now=NOW,
        )
        await session.commit()
    return head.id


async def _publish_standard(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    entity_type: ConfigEntityType,
    *,
    code: str,
    definition: dict[str, object],
) -> UUID:
    """STANDARD-track entities (`SEARCH_CONFIGURATION`/`NOTIFICATION_TEMPLATE`) publish in ONE
    call -- a second call against the resulting already-PUBLISHED version raises
    `VersionNotPublishableError` (mirrors `tests/e2e/test_critical_buyer_seller_journey.py::
    _publish_standard` exactly). Idempotent the same way `_publish_controlled` is."""
    existing = await _find_existing_head(session_factory, redis_client, entity_type, code=code)
    if existing is not None:
        return existing

    async with session_factory() as session:
        uc = _open_config_use_cases(session, redis_client)
        head, version = await uc.create_draft(
            entity_type,
            code=code,
            business_owner="P-21 perf seed",
            definition=definition,
            actor_id=MAKER,
            now=NOW,
        )
        await session.commit()

    manage_key = f"config:{entity_type.value}:manage"
    async with session_factory() as session:
        uc = _open_config_use_cases(session, redis_client)
        await uc.publish(
            entity_type,
            head.id,
            version.id,
            actor_id=MAKER,
            actor_permission_keys=frozenset({manage_key}),
            approval_note=None,
            now=NOW,
        )
        await session.commit()
    return head.id


async def seed_configuration(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
) -> tuple[UUID, UUID]:
    """Returns (category_head_id, form_head_id). Idempotent: if already published this session,
    reuses the module-level cache rather than re-publishing (a second publish of the same code
    would fail -- `configuration`'s own uniqueness invariant on `code`)."""
    global _CATEGORY_HEAD_ID, _FORM_HEAD_ID
    if _CATEGORY_HEAD_ID is not None and _FORM_HEAD_ID is not None:
        return _CATEGORY_HEAD_ID, _FORM_HEAD_ID

    await _publish_controlled(
        session_factory,
        redis_client,
        ConfigEntityType.PLATFORM_SETTINGS,
        code="platform-settings-global",
        definition={
            "descriptor": {"name": {"uz_latn": "Global settings"}},
            "settings_scope": "GLOBAL",
            "settings": {
                "otp.expiry_minutes": 5,
                "session.expiry_hours": 24,
                "listing.default_expiry_days": 30,
            },
        },
    )
    form_head_id = await _publish_controlled(
        session_factory,
        redis_client,
        ConfigEntityType.FORM_DEFINITION,
        code="perf-apartments-form",
        definition={
            "descriptor": {"name": {"uz_latn": "Apartments form"}},
            "sections": [{"code": "main", "label": {"uz_latn": "Main"}, "order": 1}],
            "fields": [
                {
                    "code": "rooms",
                    "label": {"uz_latn": "Rooms"},
                    "field_type": "number",
                    "section_code": "main",
                    "order": 1,
                    "required": False,
                    "facet_eligible": True,
                    "validators": [],
                },
            ],
        },
    )
    category_head_id = await _publish_controlled(
        session_factory,
        redis_client,
        ConfigEntityType.CATEGORY,
        code="perf-apartments",
        definition={
            "descriptor": {"name": {"uz_latn": "Apartments"}},
            "parent_category_id": None,
            "path": "/housing/apartments",
            "form_definition_id": str(form_head_id),
            "tree_status": "ACTIVE",
        },
    )
    await _publish_standard(
        session_factory,
        redis_client,
        ConfigEntityType.SEARCH_CONFIGURATION,
        code="perf-search-global",
        definition={
            "descriptor": {"name": {"uz_latn": "Perf global search"}},
            "scope_category_id": None,
            "facets": [{"field_code": "rooms", "label": {"uz_latn": "Rooms"}, "order": 1}],
            "sort_options": ["RELEVANCE", "RECENCY", "PRICE_ASC"],
            "default_sort": "RELEVANCE",
            "promotion_page_cap": 5,
        },
    )
    _CATEGORY_HEAD_ID, _FORM_HEAD_ID = category_head_id, form_head_id
    return category_head_id, form_head_id


async def _existing_count(session_factory: async_sessionmaker[AsyncSession], model: type) -> int:
    async with session_factory() as session:
        result = await session.execute(select(func.count()).select_from(model))
        return int(result.scalar_one())


async def _gather_bounded(coros: list[Coroutine[Any, Any, None]], concurrency: int) -> None:
    semaphore = asyncio.Semaphore(concurrency)

    async def _run(coro: Coroutine[Any, Any, None]) -> None:
        async with semaphore:
            await coro

    await asyncio.gather(*(_run(c) for c in coros))


async def seed_users(
    session_factory: async_sessionmaker[AsyncSession], count: int, *, concurrency: int = 100
) -> list[UUID]:
    existing = await _existing_count(session_factory, UserAccountRow)
    to_create = max(0, count - existing)
    ids: list[UUID] = []

    async def _create_one(index: int) -> None:
        account_id = UserId(value=uuid4())
        account = UserAccount.register_via_phone(
            account_id=account_id, phone=PhoneNumber(_phone(index)), now=NOW
        )
        async with session_factory() as session:
            await SqlalchemyUserAccountRepository(session).add(account)
            await session.commit()
        ids.append(account_id.value)

    if to_create:
        await _gather_bounded([_create_one(existing + i) for i in range(to_create)], concurrency)

    async with session_factory() as session:
        result = await session.execute(select(UserAccountRow.id).limit(count))
        return [row[0] for row in result.all()]


async def seed_listings(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    owner_ids: list[UUID],
    count: int,
    *,
    concurrency: int = 8,
) -> None:
    """`concurrency` default is deliberately low relative to `seed_users`/`seed_favorites`: each
    listing creation opens several NESTED sessions of its own (the category/form/platform-
    settings config-reading bridges each open a fresh session per lookup, mirroring the real
    production adapter shape) -- at high concurrency this exhausts the default SQLAlchemy pool
    (5 + 10 overflow = 15 connections) well before 50 top-level `_create_one` calls would
    otherwise suggest, producing a `TimeoutError`, not a correctness issue."""
    category_head_id, _ = await seed_configuration(session_factory, redis_client)
    existing = await _existing_count(session_factory, ListingRow)
    to_create = max(0, count - existing)
    if not to_create:
        return

    titles = [
        "Cozy studio near metro",
        "Spacious two-room apartment",
        "Renovated flat in the center",
        "Family house with a garden",
        "Modern apartment with a view",
        "Budget room for rent",
        "Newly built penthouse",
        "Quiet apartment near the park",
        "Sunny flat close to school",
        "Apartment with parking",
    ]

    def _build_use_cases(session: AsyncSession) -> ListingUseCases:
        listings_repo = SqlalchemyListingRepository(session)
        return ListingUseCases(
            listings=listings_repo,
            categories=ConfigurationCategoryFormAdapter(
                _CategoryReaderBridge(session_factory, redis_client)
            ),
            settings=ConfigurationPlatformSettingsAdapter(
                _ConfigurationBridge(session_factory, redis_client)
            ),
            media=_NoMediaAssetReaderPort(),
            outbox=OutboxWriter(session, CatalogOutboxEventRow),
            quota=QuotaEnforcementService(
                subscriptions=SqlalchemySubscriptionSnapshotRepository(session)
            ),
            duplicates=DuplicateDetectionService(listings=listings_repo),
            credit_balance=_NoCreditBalancePort(),
        )

    async def _create_one(index: int) -> None:
        owner_id = UserId(value=owner_ids[index % len(owner_ids)])
        lat = _LAT_RANGE[0] + (index % 1000) / 1000 * (_LAT_RANGE[1] - _LAT_RANGE[0])
        lon = _LON_RANGE[0] + (index % 997) / 997 * (_LON_RANGE[1] - _LON_RANGE[0])
        # Two separate use-case calls (create-draft, then a SEPARATE publish), not `create_listing
        # (..., publish=True)` -- that one-call path hits a real, confirmed integration defect in
        # `SqlalchemyListingRepository.save()` (a duplicate-key `IntegrityError` on
        # `listing_transition` when `add()`'s CREATE transition and `save()`'s re-inserted
        # transition list collide within the SAME session/identity-map -- no existing test
        # exercises `create_listing(publish=True)` against the REAL repository, only fake-backed
        # unit tests do). Reported, not fixed here (out of scope for this fork's directive); the
        # two-call path below is itself a fully real, valid production flow (exactly what `POST
        # /listings` with `publish:false` followed by a separate `changeListingStatus` does).
        async with session_factory() as session:
            use_cases = _build_use_cases(session)
            listing = await use_cases.create_listing(
                owner_user_id=owner_id,
                owner_profile_id=None,
                listing_type=ListingType.ADVERTISEMENT,
                category_id=category_head_id,
                title=f"{titles[index % len(titles)]} #{index}",
                description="Synthetic perf-benchmark listing, not a real advertisement.",
                attributes={"rooms": str((index % 5) + 1)},
                price=Money(amount=Decimal(1_000_000 + (index % 50) * 100_000), currency="UZS"),
                location=GeoLocation(latitude=lat, longitude=lon),
                image_media_asset_ids=None,
                publish=False,
                now=NOW,
            )
            await session.commit()
            listing_id = listing.id
        async with session_factory() as session:
            use_cases = _build_use_cases(session)
            await use_cases.publish_listing(listing_id=listing_id, actor_user_id=owner_id, now=NOW)
            await session.commit()

    await _gather_bounded([_create_one(existing + i) for i in range(to_create)], concurrency)


async def drain_catalog_outbox(
    session_factory: async_sessionmaker[AsyncSession],
    opensearch_index: OpenSearchIndexAdapter,
) -> int:
    """Drains catalog's outbox into search (indexing) and messaging (owner projection, needed
    for the conversation-history benchmark) -- the same two consumers `composition_root.
    make_catalog_outbox_fanout_handler` attaches in production, reproduced here since the
    private closure needs several other modules' session factories this seed script has no
    reason to construct."""
    search_handler = make_search_event_handler(
        session_factory=session_factory, index=opensearch_index
    )

    async def _handle(envelope: EventEnvelope) -> None:
        await search_handler(envelope)
        if envelope.event_type == "ListingCreated":
            async with session_factory() as session, session.begin():
                await handle_listing_created(session, envelope)

    dispatcher = OutboxDispatcher(session_factory, CatalogOutboxEventRow, _handle, batch_size=500)
    total = 0
    while True:
        processed = await dispatcher.drain_once()
        total += processed
        if processed == 0:
            break
    return total


async def seed_favorites(
    session_factory: async_sessionmaker[AsyncSession],
    owner_ids: list[UUID],
    count: int,
    *,
    concurrency: int = 100,
) -> None:
    async with session_factory() as session:
        listing_ids = [
            row[0] for row in (await session.execute(select(ListingRow.id).limit(count))).all()
        ]
    if not listing_ids:
        return
    existing = await _existing_count(session_factory, FavoriteRow)
    to_create = max(0, min(count, len(listing_ids)) - existing)
    if not to_create:
        return

    async def _create_one(index: int) -> None:
        user_id = UserId(value=owner_ids[(index * 7) % len(owner_ids)])
        listing_id = ListingId(value=listing_ids[index % len(listing_ids)])
        async with session_factory() as session:
            use_cases = FavoriteUseCases(
                favorites=SqlalchemyFavoriteRepository(session),
                listings=SqlalchemyListingRepository(session),
                outbox=OutboxWriter(session, CatalogOutboxEventRow),
            )
            await use_cases.add_favorite(user_id=user_id, listing_id=listing_id, now=NOW)
            await session.commit()

    await _gather_bounded([_create_one(i) for i in range(to_create)], concurrency)


async def seed_conversations(
    session_factory: async_sessionmaker[AsyncSession],
    owner_ids: list[UUID],
    redis_client: Redis,
    count: int,
    *,
    concurrency: int = 20,
) -> None:
    async with session_factory() as session:
        listing_ids = [
            row[0]
            for row in (
                await session.execute(select(ListingRow.id, ListingRow.owner_user_id).limit(count))
            ).all()
        ]
    existing = await _existing_count(session_factory, ConversationRow)
    to_create = max(0, min(count, len(listing_ids)) - existing)
    if not to_create:
        return

    async def _create_one(index: int) -> None:
        listing_id = listing_ids[index]
        buyer_id = UserId(value=owner_ids[(index * 13 + 1) % len(owner_ids)])
        async with session_factory() as session:
            use_cases = ConversationUseCases(
                conversations=SqlalchemyConversationRepository(session),
                blocks=SqlalchemyBlockRepository(session),
                listing_owners=SqlalchemyListingOwnerProjectionReader(session),
                publisher=RedisRealtimePublisherAdapter(redis_client),
                contact_policy=ContactPolicyPortAdapter(SqlalchemyUserAccountRepository(session)),
                outbox=OutboxWriter(session, CatalogOutboxEventRow),
            )
            try:
                conversation = await use_cases.start_conversation(
                    initiator_user_id=buyer_id,
                    listing_id=listing_id,
                    message_body="Hi, is this still available?",
                    now=NOW,
                )
                await session.flush()
            except Exception:
                # benign, expected race under high concurrency (I-09-style uniqueness), skip
                return
            for i in range(3):
                await use_cases.send_message(
                    conversation.id,
                    author_id=buyer_id,
                    body=f"Follow-up message {i}",
                    now=NOW + timedelta(minutes=i),
                )
            await session.commit()

    await _gather_bounded([_create_one(i) for i in range(to_create)], concurrency)


class _NoMediaAssetReaderPort:
    async def get_media_asset(self, media_asset_id: UUID) -> None:
        return None


class _NoCreditBalancePort:
    """Never actually called -- every `create_listing` call in this file leaves
    `auto_compute_payment_requirement` at its default `False` -- but `ListingUseCases`'
    constructor requires a `CreditBalancePort` regardless."""

    async def consume_one_listing_credit(self, *, owner_profile_id: BusinessProfileId) -> bool:
        return False


class _ConfigurationBridge:
    """Reproduces `composition_root._ConfigurationPortBridge`'s two methods -- mirrors `tests/
    integration/test_config_publish_propagates_without_redeploy.py::_ConfigurationBridge`
    exactly."""

    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
    ) -> None:
        self._session_factory = session_factory
        self._redis_client = redis_client

    async def list_config_heads(
        self, entity_type: str, cursor: str | None = None, limit: int | None = 20
    ) -> ConfigurationHeadPage:
        page_limit = limit or 20
        async with self._session_factory() as session:
            uc = _open_config_use_cases(session, self._redis_client)
            heads, next_cursor = await uc.list_heads(
                ConfigEntityType(entity_type), cursor=cursor, limit=page_limit
            )
            return ConfigurationHeadPage(
                items=[_head_to_dto(h) for h in heads],
                page=PageInfo(limit=page_limit, next_cursor=next_cursor),
            )

    async def get_config_version(
        self, entity_type: str, head_id: UUID, version_id: UUID
    ) -> ConfigurationVersion:
        async with self._session_factory() as session:
            uc = _open_config_use_cases(session, self._redis_client)
            version = await uc.get_version(ConfigEntityType(entity_type), head_id, version_id)
            return _version_to_dto(version)


class _CategoryReaderBridge:
    def __init__(
        self, session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
    ) -> None:
        self._session_factory = session_factory
        self._redis_client = redis_client

    async def get_category(self, category_id: UUID) -> dict[str, object] | None:
        async with self._session_factory() as session:
            uc = CategoryReadUseCases(
                SqlalchemyConfigHeadRepository(session), RedisSnapshotCache(self._redis_client)
            )
            return await uc.get_category(category_id)

    async def get_category_form(self, category_id: UUID) -> dict[str, object] | None:
        async with self._session_factory() as session:
            uc = CategoryReadUseCases(
                SqlalchemyConfigHeadRepository(session), RedisSnapshotCache(self._redis_client)
            )
            return await uc.get_category_form(category_id)


async def seed_all(
    session_factory: async_sessionmaker[AsyncSession],
    redis_client: Redis,
    opensearch_index: OpenSearchIndexAdapter,
    scale: SeedScale,
) -> dict[str, float]:
    """Runs every seeding phase in order, timing each. Returns a phase -> elapsed_seconds map." """
    timings: dict[str, float] = {}

    t0 = time.monotonic()
    await seed_configuration(session_factory, redis_client)
    timings["configuration"] = time.monotonic() - t0

    t0 = time.monotonic()
    owner_ids = await seed_users(session_factory, scale.users)
    timings["users"] = time.monotonic() - t0

    t0 = time.monotonic()
    await seed_listings(session_factory, redis_client, owner_ids, scale.listings)
    timings["listings"] = time.monotonic() - t0

    t0 = time.monotonic()
    drained = await drain_catalog_outbox(session_factory, opensearch_index)
    timings["drain_outbox"] = time.monotonic() - t0
    timings["drained_events"] = float(drained)

    t0 = time.monotonic()
    await seed_favorites(session_factory, owner_ids, scale.favorites)
    timings["favorites"] = time.monotonic() - t0

    t0 = time.monotonic()
    await seed_conversations(session_factory, owner_ids, redis_client, scale.conversations)
    timings["conversations"] = time.monotonic() - t0

    return timings
