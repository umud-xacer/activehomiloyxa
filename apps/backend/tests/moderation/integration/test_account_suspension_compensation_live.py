"""End-to-end integration test for the `SUSPEND_ACCOUNT` compensation chain (DB Architecture Sec
14.4's own worked example: "account suspension -> listings hidden by catalog's own transition"),
against real PostgreSQL, spanning THREE modules' schemas: a resolved moderation `ModerationCase`
drives a real `AccountSuspensionCommandPort` implementation (delegating to identity's real
`AdminIdentityUseCases.change_user_status`, mirroring the shape of `composition_root.py`'s own
`_ModerationAccountSuspensionBridge` -- that bridge itself is private composition-root wiring,
already covered by mypy/import-linter; this test proves the REAL event chain it wires together
actually works), which publishes a real `AccountSuspended` event on identity's own outbox;
draining that event through catalog's already-built `handle_identity_event`
(`composition_root.make_identity_account_status_projection_handler`'s own logic, imported and
called directly here) suspends every one of that owner's currently-visible listings, appending
catalog's OWN `LifecycleTransitionRecord` -- never written by moderation or identity directly
(X-04: "compensations, not cascades", moderation/README.md).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import UUID, uuid4

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from backbone.persistence import redis_url
from catalog.domain.listing import Listing
from catalog.domain.value_objects import LifecycleState, ListingType
from catalog.infrastructure.event_projection import handle_identity_event
from catalog.infrastructure.persistence.base import CatalogBase
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.infrastructure.persistence.repository import SqlalchemyListingRepository
from identity.application.admin_use_cases import AdminIdentityUseCases
from identity.application.ports import ResolvedRoleDefinition
from identity.domain import UserAccount
from identity.domain.value_objects import PhoneNumber
from identity.infrastructure.persistence.base import IdentityBase
from identity.infrastructure.persistence.models import (
    OutboxEventRow as IdentityOutboxEventRow,
)
from identity.infrastructure.persistence.repository import (
    SqlalchemyUserAccountRepository,
)
from identity.infrastructure.session_store import RedisSessionRepository
from moderation.application.action_service import ModerationActionService
from moderation.application.moderation_use_cases import ModerationUseCases
from moderation.domain import ResolutionAction, SubjectType
from moderation.infrastructure.persistence.models import (
    OutboxEventRow as ModerationOutboxEventRow,
)
from moderation.infrastructure.persistence.repository import (
    SqlalchemyModerationCaseRepository,
)
from shared_kernel import EventEnvelope, ListingId, UserId

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


class _NullRoleDefinitionReader:
    """Never invoked by `change_user_status` (only `assign_role`/`revoke_role` touch it) -- a
    real `ConfigurationRoleDefinitionAdapter` would need a real `configuration` schema this test
    has no reason to stand up."""

    async def resolve_by_code(self, code: str) -> ResolvedRoleDefinition:
        raise AssertionError("not exercised by this test")

    async def get_permission_keys(self, *, head_id: UUID, version_id: UUID) -> frozenset[str]:
        raise AssertionError("not exercised by this test")


class _TestAccountSuspensionCommandPort:
    """The test's own narrow implementation of `moderation.application.ports.
    AccountSuspensionCommandPort`, delegating to a REAL `AdminIdentityUseCases.change_user_status`
    against real Postgres/Redis -- functionally identical to `composition_root.py`'s own private
    `_ModerationAccountSuspensionBridge`, defined locally here since that bridge is composition-
    root-internal wiring (mirrors `conftest.py`'s own fakes: a Protocol implementation, not the
    production adapter)."""

    def __init__(
        self, identity_session_factory: async_sessionmaker[AsyncSession], redis: Redis
    ) -> None:
        self._identity_session_factory = identity_session_factory
        self._redis = redis

    async def suspend_account(self, account_id: UUID, *, reason: str | None) -> None:
        async with self._identity_session_factory() as session:
            use_cases = AdminIdentityUseCases(
                accounts=SqlalchemyUserAccountRepository(session),
                sessions=RedisSessionRepository(self._redis),
                outbox=OutboxWriter(session, IdentityOutboxEventRow),
                role_reader=_NullRoleDefinitionReader(),
            )
            await use_cases.change_user_status(
                target_account_id=UserId(value=account_id),
                action="SUSPEND",
                reason=reason,
                now=NOW,
            )
            await session.commit()


@pytest_asyncio.fixture(autouse=True)
async def _identity_and_catalog_tables(engine: AsyncEngine) -> None:
    """This ONE test file needs THREE schemas -- `integration/conftest.py`'s own `engine` fixture
    only creates and cleans moderation's own tables (every other moderation integration test
    needs nothing else). Truncated on every run (not just created) so a fixed literal phone
    number/slug across repeated runs never collides with a leftover row from a previous run."""
    async with engine.begin() as conn:
        await conn.run_sync(IdentityBase.metadata.create_all, checkfirst=True)
        await conn.run_sync(CatalogBase.metadata.create_all, checkfirst=True)
        identity_tables = ", ".join(
            f'"identity"."{t.name}"' for t in IdentityBase.metadata.tables.values()
        )
        await conn.execute(text(f"TRUNCATE TABLE {identity_tables} RESTART IDENTITY CASCADE"))
        catalog_tables = ", ".join(
            f'"catalog"."{t.name}"' for t in CatalogBase.metadata.tables.values()
        )
        await conn.execute(text(f"TRUNCATE TABLE {catalog_tables} RESTART IDENTITY CASCADE"))


async def test_suspend_account_verb_suspends_every_visible_listing_via_catalogs_own_transition(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    import os

    if not os.environ.get("REDIS_HOST"):
        import pytest

        pytest.skip("REDIS_HOST not set -- no real Redis to test against")

    owner_account_id = uuid4()
    async with session_factory() as session:
        accounts = SqlalchemyUserAccountRepository(session)
        account = UserAccount.register_via_phone(
            account_id=UserId(value=owner_account_id),
            phone=PhoneNumber(value="+998901234567"),
            now=NOW,
        )
        await accounts.add(account)
        await session.commit()

    listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=UserId(value=owner_account_id),
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/x",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="Suspend-me listing",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="suspend-me-listing",
        now=NOW,
    ).publish(
        record_id=uuid4(),
        actor_user_id=owner_account_id,
        expires_at=NOW + timedelta(days=30),
        now=NOW,
    )
    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        await session.commit()

    draft_listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=UserId(value=owner_account_id),
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/x",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="Still-draft listing",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="still-draft-listing",
        now=NOW,
    )
    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(draft_listing)
        await session.commit()

    redis = Redis.from_url(redis_url())
    try:
        accounts_port = _TestAccountSuspensionCommandPort(session_factory, redis)

        async with session_factory() as session:
            cases = SqlalchemyModerationCaseRepository(session)
            action_service = ModerationActionService(
                listings=_UnusedListingCommandPort(),
                accounts=accounts_port,
                profiles=_UnusedProfileCommandPort(),
            )
            use_cases = ModerationUseCases(
                cases=cases,
                action_service=action_service,
                outbox=OutboxWriter(session, ModerationOutboxEventRow),
            )
            case = await use_cases.submit_report(
                subject_type=SubjectType.USER,
                subject_id=owner_account_id,
                reporter_user_id=uuid4(),
                reason="repeated fraud",
                now=NOW,
            )
            await use_cases.resolve_case(
                case.id,
                action=ResolutionAction.SUSPEND_ACCOUNT,
                note="repeated fraud",
                moderator_user_id=uuid4(),
                now=NOW,
            )
            await session.commit()

        # Drain identity's outbox for the real AccountSuspended event, exactly the way
        # `composition_root.make_identity_account_status_projection_handler`'s own closure does
        # (its logic reproduced directly here rather than importing the private composition-root
        # closure, mirroring the billing/catalog precedent in
        # `apps/backend/tests/billing/integration/test_downstream_catalog_projection_live.py`).
        async with session_factory() as session:
            from sqlalchemy import select

            rows = (
                (
                    await session.execute(
                        select(IdentityOutboxEventRow).where(
                            IdentityOutboxEventRow.event_type == "AccountSuspended"
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert len(rows) == 1, (
                "AdminIdentityUseCases.change_user_status must publish AccountSuspended"
            )
            row = rows[0]
            envelope = EventEnvelope(
                event_id=row.id,
                event_type=row.event_type,
                occurred_at=row.occurred_at,
                actor=row.actor,
                aggregate_type=row.aggregate_type,
                aggregate_id=row.aggregate_id,
                aggregate_version=row.aggregate_version,
                payload=row.payload,
            )

        async with session_factory() as catalog_session, catalog_session.begin():
            from catalog.application import ListingUseCases
            from catalog.application.duplicate_detection_service import (
                DuplicateDetectionService,
            )
            from catalog.application.quota_service import QuotaEnforcementService
            from catalog.infrastructure.persistence.repository import (
                SqlalchemySubscriptionSnapshotRepository,
            )

            listings_repo = SqlalchemyListingRepository(catalog_session)
            catalog_use_cases = ListingUseCases(
                listings=listings_repo,
                categories=_UnusedCategoryFormPort(),
                settings=_UnusedPlatformSettingsReaderPort(),
                media=_UnusedMediaAssetReaderPort(),
                outbox=OutboxWriter(catalog_session, CatalogOutboxEventRow),
                quota=QuotaEnforcementService(
                    subscriptions=SqlalchemySubscriptionSnapshotRepository(catalog_session)
                ),
                duplicates=DuplicateDetectionService(listings=listings_repo),
            )
            await handle_identity_event(catalog_session, envelope, catalog_use_cases)

        async with session_factory() as session:
            listings_repo = SqlalchemyListingRepository(session)
            reloaded_published = await listings_repo.get_by_id(listing.id)
            assert reloaded_published is not None
            assert reloaded_published.lifecycle_state is LifecycleState.SUSPENDED
            assert reloaded_published.transitions[-1].reason is not None
            assert "account suspended" in reloaded_published.transitions[-1].reason

            reloaded_draft = await listings_repo.get_by_id(draft_listing.id)
            assert reloaded_draft is not None
            assert reloaded_draft.lifecycle_state is LifecycleState.DRAFT, (
                "a DRAFT listing has nothing further to withhold -- suspend_all_by_owner only "
                "touches PUBLISHED/EDITED listings"
            )
    finally:
        await redis.aclose()


class _UnusedListingCommandPort:
    async def hide_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def reject_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def suspend_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def remove_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def unflag_listing(self, listing_id: UUID, *, reason: str | None) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedProfileCommandPort:
    async def revoke_badge(self, profile_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def archive_profile(self, profile_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedCategoryFormPort:
    async def get_category(self, category_id: UUID) -> NoReturn:
        raise AssertionError(
            "not exercised by this test (suspend_all_by_owner never reads categories)"
        )

    async def get_current_form_binding(self, category_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedPlatformSettingsReaderPort:
    async def get_catalog_settings(self) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedMediaAssetReaderPort:
    async def get_media_asset(self, media_asset_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")
