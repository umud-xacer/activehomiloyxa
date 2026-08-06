"""Eventual-consistency proof for "profiles badge event (approved verification) -> search
verified-badge flag": profiles approves a real `VerificationCase` (issuing a real badge on a
real `BusinessProfile`) -> a real `BusinessVerified` event on profiles' own outbox -> drained
through search's real `make_search_event_handler` (the SAME closure `composition_root.
make_profiles_notification_projection_handler`'s own P-20 fix now attaches as its third route --
called directly here, rather than through the full production handler, to keep this test scoped
to the search hop; the notifications/analytics legs of that same handler are each other modules'
own concern, not re-proven here) -> indexed into a real OpenSearch document via search's own,
unmodified `handle_verified_badge_applied`.

Closes a confirmed integration defect: search's own `handle_verified_badge_applied` was built and
unit-tested in P-08 but never wired to any dispatcher at all (`profiles/README.md`'s own "Known
gaps") -- P-20 fixed the composition-root wiring; this test proves the fixed wiring actually
converges against a real database and a real OpenSearch cluster.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from opensearchpy import OpenSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from profiles.application.verification_use_cases import VerificationUseCases
from profiles.domain import BusinessProfile, CaseStatus, ProfileType
from profiles.infrastructure.persistence.base import ProfilesBase
from profiles.infrastructure.persistence.models import (
    OutboxEventRow as ProfilesOutboxEventRow,
)
from profiles.infrastructure.persistence.models import (
    VerificationEntitlementProjectionRow,
)
from profiles.infrastructure.persistence.repository import (
    SqlalchemyBusinessProfileRepository,
    SqlalchemyVerificationCaseRepository,
    SqlalchemyVerificationEligibilityRepository,
)
from search.domain import ListingType
from search.domain.search_document import ListingSearchDocument
from search.infrastructure.event_projection import make_search_event_handler
from search.infrastructure.opensearch_index import OpenSearchIndexAdapter
from shared_kernel import BusinessProfileId, EventEnvelope, LocalizedText, UserId
from tests.integration.conftest import ensure_clean_schema, poll_until

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
OPENSEARCH_AVAILABLE = bool(os.environ.get("OPENSEARCH_HOST"))
_INDEX_NAME = "listing_search_badge_test"


@pytest.fixture(autouse=True)
def _skip_without_opensearch() -> None:
    if not OPENSEARCH_AVAILABLE:
        pytest.skip("OPENSEARCH_HOST not set -- no real OpenSearch cluster to test against")


@pytest_asyncio.fixture(autouse=True)
async def _profiles_schema(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "profiles", ProfilesBase)


@pytest_asyncio.fixture
async def opensearch_index() -> AsyncIterator[OpenSearchIndexAdapter]:
    client = OpenSearch(
        hosts=[
            {
                "host": os.environ["OPENSEARCH_HOST"],
                "port": int(os.environ.get("OPENSEARCH_PORT", "9200")),
            }
        ]
    )
    adapter = OpenSearchIndexAdapter(client, index_name=_INDEX_NAME)
    await adapter.delete_index()
    await adapter.ensure_index()
    yield adapter
    await adapter.delete_index()


class _UnusedMediaAssetReaderPort:
    async def get_media_asset(self, media_asset_id: object) -> None:
        raise AssertionError("not exercised -- this test requests verification with no documents")


async def test_approved_verification_reaches_searchs_verified_badge_flag(
    session_factory: async_sessionmaker[AsyncSession],
    opensearch_index: OpenSearchIndexAdapter,
) -> None:
    owner = UserId(value=uuid4())
    entitlement_id = uuid4()
    profile_id = BusinessProfileId(value=uuid4())

    async with session_factory() as session:
        profile = BusinessProfile.create(
            profile_id=profile_id,
            owner_user_id=owner,
            profile_type=ProfileType.CONSTRUCTION_COMPANY,
            name=LocalizedText(uz_latn="Quality Builders"),
            description=None,
            contacts=None,
            address=None,
            slug="quality-builders",
            now=NOW,
        )
        await SqlalchemyBusinessProfileRepository(session).add(profile)
        session.add(
            VerificationEntitlementProjectionRow(
                entitlement_id=entitlement_id,
                business_profile_id=profile_id.value,
                valid_from=NOW,
                valid_until=NOW + timedelta(days=365),
                activation_state="ACTIVE",
                source_event_id=uuid4(),
            )
        )
        await session.commit()

    async with session_factory() as session:
        use_cases = VerificationUseCases(
            profiles=SqlalchemyBusinessProfileRepository(session),
            cases=SqlalchemyVerificationCaseRepository(session),
            eligibility=SqlalchemyVerificationEligibilityRepository(session),
            media=_UnusedMediaAssetReaderPort(),
            outbox=OutboxWriter(session, ProfilesOutboxEventRow),
        )
        case = await use_cases.request_verification(
            profile_id,
            owner_user_id=owner,
            entitlement_id=entitlement_id,
            documents=[(uuid4(), "license")],
            now=NOW,
        )
        await use_cases.decide_verification(
            case.id,
            reviewer_user_id=uuid4(),
            outcome=CaseStatus.APPROVED,
            reason=None,
            now=NOW,
        )
        await session.commit()

    # Index the listing's owner-profile document first (unverified), exactly as an existing
    # ListingPublished event already would have -- out of scope for this test (proven by
    # test_billing_promotion_to_catalog_and_search.py's sibling suite and search's own tests).
    document = ListingSearchDocument.project(
        listing_id=uuid4(),
        owner_profile_id=profile_id.value,
        title="Renovation services",
        description=None,
        category_id=uuid4(),
        category_path="/services/renovation",
        listing_type=ListingType.SERVICE,
        attributes={},
        price=None,
        location=None,
        verified_badge=False,
        publicly_visible=True,
        slug="renovation-services",
        published_at=NOW,
        updated_at=NOW,
    )
    await opensearch_index.index_document(document)
    # `index_document` indexes with `refresh=False` (deliberately, for write-path throughput);
    # `apply_verified_badge` (via `find_listing_ids_by_owner_profile`) queries by owner_profile_id
    # rather than a direct id lookup, so it needs the just-indexed document to already be
    # searchable, not merely stored -- force a refresh the same way the module's own
    # `integration/test_opensearch_index_live.py` does for its own search-based assertions.
    await asyncio.to_thread(
        opensearch_index._client.indices.refresh, index=opensearch_index._index_name
    )

    # Drain profiles' real outbox for the real BusinessVerified event, then feed it to search's
    # own real handler -- the exact closure composition_root's fixed `make_profiles_notification_
    # projection_handler` now also attaches, exercised directly here to keep this test scoped to
    # the search hop (see module docstring).
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(ProfilesOutboxEventRow).where(
                        ProfilesOutboxEventRow.event_type == "BusinessVerified"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )

    search_handler = make_search_event_handler(
        session_factory=session_factory, index=opensearch_index
    )
    await search_handler(envelope)

    async def _verified_in_search() -> bool:
        fetched = await opensearch_index.get_document(document.listing_id)
        return fetched is not None and fetched.verified_badge

    await poll_until(_verified_in_search, timeout_seconds=5.0)
    fetched = await opensearch_index.get_document(document.listing_id)
    assert fetched is not None
    assert fetched.verified_badge is True
