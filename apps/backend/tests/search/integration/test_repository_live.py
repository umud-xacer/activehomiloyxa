"""Integration tests: `SqlalchemyFallbackIndexRepository` round-trips against real PostgreSQL --
the QR-05/NFR-REL-002 degradation path. Covers trigram similarity search (`pg_trgm`, this
codebase's first use), the geo bounding-box approximation (FR-MAP-003), and
`SqlalchemyProjectionCheckpointRepository`'s rebuild-flow reset/advance."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from search.domain import GeoFilter, ListingType, SearchQuery, SortOption
from search.domain.search_document import ListingSearchDocument
from search.infrastructure.persistence.repository import (
    SqlalchemyFallbackIndexRepository,
    SqlalchemyProjectionCheckpointRepository,
)
from shared_kernel import GeoLocation

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _document(
    *, title: str, location: GeoLocation | None = None, **overrides: object
) -> ListingSearchDocument:
    kwargs: dict[str, object] = {
        "listing_id": uuid4(),
        "owner_profile_id": None,
        "title": title,
        "description": None,
        "category_id": uuid4(),
        "category_path": "/real-estate",
        "listing_type": ListingType.ADVERTISEMENT,
        "attributes": {},
        "price": None,
        "location": location,
        "verified_badge": False,
        "publicly_visible": True,
        "slug": title.lower().replace(" ", "-"),
        "published_at": NOW,
        "updated_at": NOW,
    }
    kwargs.update(overrides)
    return ListingSearchDocument.project(**kwargs)  # type: ignore[arg-type]


def _query(**overrides: object) -> SearchQuery:
    kwargs: dict[str, object] = {
        "q": None,
        "category_id": None,
        "owner_profile_id": None,
        "listing_type": None,
        "filters": {},
        "price_min": None,
        "price_max": None,
        "verified_only": False,
        "geo": None,
        "sort": SortOption.RELEVANCE,
        "cursor": None,
        "limit": 20,
    }
    kwargs.update(overrides)
    return SearchQuery(**kwargs)  # type: ignore[arg-type]


async def test_upsert_then_search_round_trips_a_document(db_session: AsyncSession) -> None:
    repo = SqlalchemyFallbackIndexRepository(db_session)
    document = _document(title="Kvartira sotiladi")
    await repo.upsert_document(document)
    await db_session.flush()

    page = await repo.search(_query())
    assert [hit.document.listing_id for hit in page.hits] == [document.listing_id]


async def test_upsert_is_idempotent_on_the_same_listing_id(db_session: AsyncSession) -> None:
    repo = SqlalchemyFallbackIndexRepository(db_session)
    document = _document(title="Kvartira")
    await repo.upsert_document(document)
    await db_session.flush()
    updated = document.with_content(
        title="Kvartira (edited)",
        description=document.description,
        category_id=document.category_id,
        category_path=document.category_path,
        attributes=document.attributes,
        price=document.price,
        location=document.location,
        publicly_visible=document.publicly_visible,
        updated_at=NOW,
    )
    await repo.upsert_document(updated)
    await db_session.flush()

    page = await repo.search(_query())
    assert len(page.hits) == 1
    assert page.hits[0].document.title == "Kvartira (edited)"


async def test_delete_removes_the_document(db_session: AsyncSession) -> None:
    repo = SqlalchemyFallbackIndexRepository(db_session)
    document = _document(title="Kvartira")
    await repo.upsert_document(document)
    await db_session.flush()

    await repo.delete_document(document.listing_id)
    await db_session.flush()

    page = await repo.search(_query())
    assert page.hits == ()


async def test_non_publicly_visible_documents_never_appear_in_results(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyFallbackIndexRepository(db_session)
    hidden = _document(title="Kvartira", publicly_visible=False)
    await repo.upsert_document(hidden)
    await db_session.flush()

    page = await repo.search(_query())
    assert page.hits == ()


async def test_trigram_search_matches_a_partial_misspelled_query(db_session: AsyncSession) -> None:
    repo = SqlalchemyFallbackIndexRepository(db_session)
    document = _document(title="Kvartira sotiladi")
    await repo.upsert_document(document)
    await db_session.flush()

    page = await repo.search(_query(q="kvartir"))
    assert [hit.document.listing_id for hit in page.hits] == [document.listing_id]


async def test_geo_bounding_box_includes_a_nearby_listing(db_session: AsyncSession) -> None:
    repo = SqlalchemyFallbackIndexRepository(db_session)
    tashkent = GeoLocation(latitude=41.2995, longitude=69.2401)
    nearby = _document(title="Nearby listing", location=tashkent)
    await repo.upsert_document(nearby)
    await db_session.flush()

    page = await repo.search(_query(geo=GeoFilter(center=tashkent, radius_km=5.0)))
    assert [hit.document.listing_id for hit in page.hits] == [nearby.listing_id]


async def test_geo_bounding_box_excludes_a_far_away_listing(db_session: AsyncSession) -> None:
    repo = SqlalchemyFallbackIndexRepository(db_session)
    tashkent = GeoLocation(latitude=41.2995, longitude=69.2401)
    samarkand = GeoLocation(latitude=39.6270, longitude=66.9750)  # ~275km from Tashkent
    far_away = _document(title="Far away listing", location=samarkand)
    await repo.upsert_document(far_away)
    await db_session.flush()

    page = await repo.search(_query(geo=GeoFilter(center=tashkent, radius_km=5.0)))
    assert page.hits == ()


async def test_verified_only_filters_out_unverified_listings(db_session: AsyncSession) -> None:
    repo = SqlalchemyFallbackIndexRepository(db_session)
    unverified = _document(title="Kvartira", verified_badge=False)
    await repo.upsert_document(unverified)
    await db_session.flush()

    page = await repo.search(_query(verified_only=True))
    assert page.hits == ()


async def test_projection_checkpoint_reset_clears_the_cursor(db_session: AsyncSession) -> None:
    repo = SqlalchemyProjectionCheckpointRepository(db_session)
    event_id = uuid4()
    await repo.advance(projection_name="listing_search", last_event_id=event_id, now=NOW)
    await db_session.flush()
    assert await repo.get_last_event_id("listing_search") == event_id

    await repo.reset("listing_search")
    await db_session.flush()
    assert await repo.get_last_event_id("listing_search") is None
