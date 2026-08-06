"""Cross-module compensation proof (DB Architecture Sec 14.4: "Cross-boundary 'cascades' are
explicit event reactions with their own audit trail ... compensations, not cascades"; I-24: "the
target module performs its own state change and emits its own event"). Complements
`apps/backend/tests/moderation/integration/test_account_suspension_compensation_live.py`, which
already proves the ASYNC half of this rule (identity's `AccountSuspended` -> catalog's own
reaction, via the outbox). This file proves the SYNCHRONOUS half: moderation's `SUSPEND` verb on
a `LISTING` subject calls catalog's real `CatalogListingModerationAdapter` (Commands via explicit
interface / ACL, SAD Sec 9) against a real Postgres row, and catalog performs and records its OWN
transition -- moderation never mutates catalog's `listing` table directly, and no code path
exists by which it could (moderation cannot even statically import `catalog`,
`tools/importlinter.cfg`'s `cross-module-moderation`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import NoReturn
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from catalog.application import ListingUseCases
from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.listing import Listing
from catalog.domain.value_objects import LifecycleState, ListingType
from catalog.infrastructure.persistence.base import CatalogBase
from catalog.infrastructure.persistence.models import (
    OutboxEventRow as CatalogOutboxEventRow,
)
from catalog.infrastructure.persistence.repository import (
    SqlalchemyListingRepository,
    SqlalchemySubscriptionSnapshotRepository,
)
from catalog.interfaces.moderation_port import CatalogListingModerationAdapter
from moderation.application.action_service import ModerationActionService
from moderation.application.moderation_use_cases import ModerationUseCases
from moderation.domain import ResolutionAction, SubjectType
from moderation.infrastructure.persistence.base import ModerationBase
from moderation.infrastructure.persistence.models import (
    OutboxEventRow as ModerationOutboxEventRow,
)
from moderation.infrastructure.persistence.repository import (
    SqlalchemyModerationCaseRepository,
)
from shared_kernel import ListingId, UserId
from tests.integration.conftest import ensure_clean_schema

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
"""A fixed instant safely in the past relative to real wall-clock time: `moderator_suspend_listing`
(via `CatalogListingModerationAdapter`) times its own transition with real `datetime.now(UTC)`,
not a caller-supplied `now` (`catalog.interfaces.moderation_port`'s own port signature carries no
`now` parameter at all) -- `NOW` must stay in the past so `transitions` (ordered by `occurred_at`,
`SqlalchemyListingRepository`) sorts the listing's own `publish()` transition before the
moderator's later `suspend()` one, not the other way around."""


class _UnusedAccountSuspensionCommandPort:
    async def suspend_account(self, account_id: UUID, *, reason: str | None) -> NoReturn:
        raise AssertionError("not exercised by this test -- subject is a LISTING, not a USER")


class _UnusedProfileCommandPort:
    async def revoke_badge(self, profile_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def archive_profile(self, profile_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedCategoryFormPort:
    async def get_category(self, category_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")

    async def get_current_form_binding(self, category_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedPlatformSettingsReaderPort:
    async def get_catalog_settings(self) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _UnusedMediaAssetReaderPort:
    async def get_media_asset(self, media_asset_id: UUID) -> NoReturn:
        raise AssertionError("not exercised by this test")


class _ListingCommandBridge:
    """Mirrors `composition_root._ModerationListingCommandBridge` exactly (a fresh, short-lived
    catalog session per call) -- defined locally since that class is private composition-root
    wiring, the same "reproduce, don't import the private closure" precedent the account-
    suspension compensation test already established."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def _adapter(self, session: AsyncSession) -> CatalogListingModerationAdapter:
        listings_repo = SqlalchemyListingRepository(session)
        use_cases = ListingUseCases(
            listings=listings_repo,
            categories=_UnusedCategoryFormPort(),
            settings=_UnusedPlatformSettingsReaderPort(),
            media=_UnusedMediaAssetReaderPort(),
            outbox=OutboxWriter(session, CatalogOutboxEventRow),
            quota=QuotaEnforcementService(
                subscriptions=SqlalchemySubscriptionSnapshotRepository(session)
            ),
            duplicates=DuplicateDetectionService(listings=listings_repo),
        )
        return CatalogListingModerationAdapter(use_cases)

    async def hide_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        raise AssertionError("not exercised by this test")

    async def reject_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        raise AssertionError("not exercised by this test")

    async def suspend_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        async with self._session_factory() as session, session.begin():
            adapter = await self._adapter(session)
            await adapter.suspend_listing(
                listing_id, moderator_user_id=moderator_user_id, reason=reason
            )

    async def remove_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        raise AssertionError("not exercised by this test")

    async def unflag_listing(self, listing_id: UUID, *, reason: str | None) -> None:
        raise AssertionError("not exercised by this test")


@pytest_asyncio.fixture(autouse=True)
async def _moderation_and_catalog_schemas(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "moderation", ModerationBase)
    await ensure_clean_schema(engine, "catalog", CatalogBase)


async def test_suspend_verb_on_a_listing_subject_suspends_it_via_catalogs_own_transition(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_id = UserId(value=uuid4())
    listing = Listing.create(
        listing_id=ListingId(value=uuid4()),
        record_id=uuid4(),
        listing_type=ListingType.ADVERTISEMENT,
        owner_user_id=owner_id,
        owner_profile_id=None,
        category_id=uuid4(),
        category_path="/x",
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="Fraudulent listing",
        description=None,
        attributes={},
        price=None,
        location=None,
        slug="fraudulent-listing",
        now=NOW,
    ).publish(
        record_id=uuid4(),
        actor_user_id=owner_id.value,
        expires_at=NOW + timedelta(days=30),
        now=NOW,
    )

    async with session_factory() as session:
        await SqlalchemyListingRepository(session).add(listing)
        await session.commit()

    moderator_id = uuid4()
    listings_bridge = _ListingCommandBridge(session_factory)
    async with session_factory() as session:
        action_service = ModerationActionService(
            listings=listings_bridge,
            accounts=_UnusedAccountSuspensionCommandPort(),
            profiles=_UnusedProfileCommandPort(),
        )
        use_cases = ModerationUseCases(
            cases=SqlalchemyModerationCaseRepository(session),
            action_service=action_service,
            outbox=OutboxWriter(session, ModerationOutboxEventRow),
        )
        case = await use_cases.submit_report(
            subject_type=SubjectType.LISTING,
            subject_id=listing.id.value,
            reporter_user_id=uuid4(),
            reason="looks fraudulent",
            now=NOW,
        )
        await use_cases.resolve_case(
            case.id,
            action=ResolutionAction.SUSPEND,
            note="confirmed fraudulent",
            moderator_user_id=moderator_id,
            now=NOW,
        )
        await session.commit()

    async with session_factory() as session:
        reloaded = await SqlalchemyListingRepository(session).get_by_id(listing.id)
        assert reloaded is not None
        assert reloaded.lifecycle_state is LifecycleState.SUSPENDED, (
            "catalog must perform its OWN suspend transition in reaction to moderation's command"
        )
        assert reloaded.transitions[-1].reason == "confirmed fraudulent", (
            "catalog's own LifecycleTransitionRecord is the audit trail (DB Architecture Sec "
            "14.4) -- moderation never writes to catalog's tables directly"
        )
