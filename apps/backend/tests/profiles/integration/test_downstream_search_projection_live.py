"""Eventual-consistency integration test (P-11 Validation Checklist: "the badge event
demonstrably drives search's verified-badge flag -- eventual-consistency integration test
passes"): search's own already-built `handle_verified_badge_applied`/`dispatch_search_event`
(`search/infrastructure/event_projection.py`, unmodified by this task, written under Task P-08
against the frozen `BusinessVerified`/`VerificationRejected`/`VerifiedBadgeExpired` event
contracts) demonstrably reacts to the REAL event `profiles.application.VerificationUseCases.
decide_verification` publishes -- proving the badge event drives search's consumer end-to-end.

Uses an in-memory `SearchIndexPort` stand-in rather than a real OpenSearch cluster: this
sandbox's `deployment/compose/docker-compose.yml` `opensearch:2.19.0` image rejects search's own
`flattened`-typed index mapping (`RequestError(400, 'mapper_parsing_exception', 'No handler for
type [flattened]...')`) -- confirmed to be a pre-existing environment/version issue by running
`apps/backend/tests/search/integration/test_opensearch_index_live.py` directly (fails identically,
unrelated to this task's own code). Mirrors the same "fast-tier equivalent" precedent `apps/
backend/tests/search/integration/test_event_projection_live.py`'s own docstring documents for its
`_NullSearchIndex` stand-in -- this one is a real (not null) in-memory index so `apply_verified_
badge`'s fan-out actually has something to flip, proving the real projection logic runs, not just
that the event was accepted.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from profiles.application import ProfileUseCases, VerificationUseCases
from profiles.application.ports import VerificationEligibilitySnapshot
from profiles.domain import CaseStatus, ProfileType
from profiles.infrastructure.persistence.repository import (
    SqlalchemyBusinessProfileRepository,
    SqlalchemyVerificationCaseRepository,
    SqlalchemyVerificationEligibilityRepository,
)
from search.application.indexing_use_cases import IndexingUseCases
from search.domain import ListingType
from search.domain.search_document import ListingSearchDocument
from search.infrastructure.event_projection import dispatch_search_event
from search.infrastructure.persistence import (
    models as search_models,  # noqa: F401  registers ORM classes
)
from search.infrastructure.persistence.base import SearchBase
from shared_kernel import EventEnvelope, GeoLocation, LocalizedText, Money, UserId

NOW = datetime(2026, 7, 13, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _ensure_search_schema(engine: AsyncEngine) -> AsyncIterator[None]:
    """This is the one test in profiles/integration/ that crosses into `search`'s schema
    (`dispatch_search_event` -- search's own, unmodified idempotency bookkeeping -- writes to
    `search.processed_event`). `profiles/integration/conftest.py`'s `engine` fixture only
    provisions the `profiles` schema (correctly -- no other test here needs `search`'s), so this
    test provisions `search`'s schema itself rather than widening the shared conftest for
    everyone else. Mirrors `apps/backend/tests/search/integration/conftest.py`'s own setup.
    """
    async with engine.begin() as conn:
        await conn.execute(text('CREATE SCHEMA IF NOT EXISTS "search"'))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await conn.run_sync(SearchBase.metadata.create_all, checkfirst=True)
    yield


class _FakeSearchIndex:
    """A minimal in-memory `SearchIndexPort` stand-in -- implements exactly the four methods
    `IndexingUseCases.apply_verified_badge` needs (`get_document`/`index_document`/
    `find_listing_ids_by_owner_profile`), mirroring `apps/backend/tests/search/conftest.py.
    FakeSearchIndex`'s own role."""

    def __init__(self) -> None:
        self.documents: dict[UUID, ListingSearchDocument] = {}

    async def index_document(self, document: ListingSearchDocument) -> None:
        self.documents[document.listing_id] = document

    async def delete_document(self, listing_id: UUID) -> None:
        self.documents.pop(listing_id, None)

    async def get_document(self, listing_id: UUID) -> ListingSearchDocument | None:
        return self.documents.get(listing_id)

    async def find_listing_ids_by_owner_profile(self, owner_profile_id: UUID) -> tuple[UUID, ...]:
        return tuple(
            doc.listing_id
            for doc in self.documents.values()
            if doc.owner_profile_id == owner_profile_id
        )


class _FakeFallbackIndex:
    async def upsert_document(self, document: ListingSearchDocument) -> None:
        return None


class _FakeOutbox:
    def __init__(self) -> None:
        self.events: list[EventEnvelope] = []

    async def append(self, event: EventEnvelope) -> None:
        self.events.append(event)


class _NullMediaAdapter:
    async def get_media_asset(self, media_asset_id: object) -> None:
        return None


async def test_business_verified_sets_the_verified_badge_flag_on_the_owners_listings(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_user = UserId(value=uuid4())
    entitlement_id = uuid4()
    index = _FakeSearchIndex()

    async with session_factory() as session:
        profiles = SqlalchemyBusinessProfileRepository(session)
        eligibility = SqlalchemyVerificationEligibilityRepository(session)
        cases = SqlalchemyVerificationCaseRepository(session)
        outbox = _FakeOutbox()

        profile_use_cases = ProfileUseCases(
            profiles=profiles, media=_NullMediaAdapter(), outbox=outbox
        )
        profile = await profile_use_cases.create_profile(
            owner_user_id=owner_user,
            profile_type=ProfileType.ARCHITECT,
            name=LocalizedText(uz_latn="Downstream Test Co"),
            description=None,
            contacts=None,
            address=None,
            now=NOW,
        )
        await eligibility.upsert(
            VerificationEligibilitySnapshot(
                entitlement_id=entitlement_id,
                business_profile_id=profile.id,
                valid_from=NOW,
                valid_until=NOW + timedelta(days=365),
                activation_state="ACTIVE",
                source_event_id=uuid4(),
            )
        )
        await session.commit()

        # A listing already indexed for this profile (as if published by catalog earlier) --
        # search's `apply_verified_badge` fans out to every listing owned by this profile.
        listing_id = uuid4()
        await index.index_document(
            ListingSearchDocument.project(
                listing_id=listing_id,
                owner_profile_id=profile.id.value,
                title="Villa design services",
                description=None,
                category_id=uuid4(),
                category_path="/services/architecture",
                listing_type=ListingType.SERVICE,
                attributes={},
                price=Money(amount=Decimal("0"), currency="UZS"),
                location=GeoLocation(latitude=41.3, longitude=69.24),
                verified_badge=False,
                publicly_visible=True,
                slug="villa-design-services",
                published_at=NOW,
                updated_at=NOW,
            )
        )

        verification_use_cases = VerificationUseCases(
            profiles=profiles,
            cases=cases,
            eligibility=eligibility,
            media=_NullMediaAdapter(),
            outbox=outbox,
        )
        media_asset_id = uuid4()
        case = await verification_use_cases.request_verification(
            profile.id,
            owner_user_id=owner_user,
            entitlement_id=entitlement_id,
            documents=[(media_asset_id, "business_license")],
            now=NOW,
        )
        await session.commit()

        before = await index.get_document(listing_id)
        assert before is not None
        assert before.verified_badge is False

        decided = await verification_use_cases.decide_verification(
            case.id, reviewer_user_id=uuid4(), outcome=CaseStatus.APPROVED, reason=None, now=NOW
        )
        await session.commit()
        assert decided.status is CaseStatus.APPROVED

    business_verified_events = [e for e in outbox.events if e.event_type == "BusinessVerified"]
    assert len(business_verified_events) == 1, (
        "decide_verification(APPROVED) must publish BusinessVerified"
    )
    real_event = business_verified_events[0]
    assert real_event.payload["businessProfileId"] == str(profile.id.value)

    async with session_factory() as search_session:
        # THIS is the real profiles event driving search's real, unmodified consumer (X-03) --
        # search's own IndexingUseCases/dispatch_search_event, not reimplemented here.
        use_cases = IndexingUseCases(index=index, fallback=_FakeFallbackIndex())  # type: ignore[arg-type]
        await dispatch_search_event(search_session, real_event, use_cases)

    after = await index.get_document(listing_id)
    assert after is not None
    assert after.verified_badge is True, (
        "search's verified_badge flag must flip to True after the real BusinessVerified event"
    )


async def test_verification_rejected_never_sets_the_badge(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner_user = UserId(value=uuid4())
    entitlement_id = uuid4()
    index = _FakeSearchIndex()

    async with session_factory() as session:
        profiles = SqlalchemyBusinessProfileRepository(session)
        eligibility = SqlalchemyVerificationEligibilityRepository(session)
        cases = SqlalchemyVerificationCaseRepository(session)
        outbox = _FakeOutbox()

        profile = await ProfileUseCases(
            profiles=profiles, media=_NullMediaAdapter(), outbox=outbox
        ).create_profile(
            owner_user_id=owner_user,
            profile_type=ProfileType.BUILDER,
            name=LocalizedText(uz_latn="Rejected Co"),
            description=None,
            contacts=None,
            address=None,
            now=NOW,
        )
        await eligibility.upsert(
            VerificationEligibilitySnapshot(
                entitlement_id=entitlement_id,
                business_profile_id=profile.id,
                valid_from=NOW,
                valid_until=NOW + timedelta(days=365),
                activation_state="ACTIVE",
                source_event_id=uuid4(),
            )
        )
        await session.commit()

        listing_id = uuid4()
        await index.index_document(
            ListingSearchDocument.project(
                listing_id=listing_id,
                owner_profile_id=profile.id.value,
                title="Building services",
                description=None,
                category_id=uuid4(),
                category_path="/services/building",
                listing_type=ListingType.SERVICE,
                attributes={},
                price=Money(amount=Decimal("0"), currency="UZS"),
                location=None,
                verified_badge=False,
                publicly_visible=True,
                slug="building-services",
                published_at=NOW,
                updated_at=NOW,
            )
        )

        verification_use_cases = VerificationUseCases(
            profiles=profiles,
            cases=cases,
            eligibility=eligibility,
            media=_NullMediaAdapter(),
            outbox=outbox,
        )
        case = await verification_use_cases.request_verification(
            profile.id,
            owner_user_id=owner_user,
            entitlement_id=entitlement_id,
            documents=[(uuid4(), "business_license")],
            now=NOW,
        )
        await session.commit()

        await verification_use_cases.decide_verification(
            case.id,
            reviewer_user_id=uuid4(),
            outcome=CaseStatus.REJECTED,
            reason="incomplete",
            now=NOW,
        )
        await session.commit()

    rejected_events = [e for e in outbox.events if e.event_type == "VerificationRejected"]
    assert len(rejected_events) == 1

    async with session_factory() as search_session:
        use_cases = IndexingUseCases(index=index, fallback=_FakeFallbackIndex())  # type: ignore[arg-type]
        await dispatch_search_event(search_session, rejected_events[0], use_cases)

    after = await index.get_document(listing_id)
    assert after is not None
    assert after.verified_badge is False
