"""`SqlalchemyFallbackIndexRepository` -- implements `search.application.ports.FallbackIndexPort`
against search's own `listing_fallback_document` table (never `catalog.listing`, see
`models.py`'s own docstring). `SqlalchemyProjectionCheckpointRepository` backs the rebuild flow
(reset + replay, DB Architecture Sec 12)."""

from __future__ import annotations

import math
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from search.application.ports import SearchHitResult, SearchResultPage
from search.domain import (
    GeoFilter,
    ListingSearchDocument,
    ListingType,
    PromotionKind,
    PromotionMarker,
    SearchQuery,
)
from search.infrastructure.persistence.models import (
    ListingFallbackDocumentRow,
    ProjectionCheckpointRow,
)
from shared_kernel import GeoLocation, Money

_EARTH_RADIUS_KM = 6371.0


def _row_to_document(row: ListingFallbackDocumentRow) -> ListingSearchDocument:
    price = (
        Money(amount=row.price_amount, currency=row.price_currency)
        if row.price_amount is not None and row.price_currency is not None
        else None
    )
    location = (
        GeoLocation(latitude=row.latitude, longitude=row.longitude)
        if row.latitude is not None and row.longitude is not None
        else None
    )
    promotion = (
        PromotionMarker(
            kind=PromotionKind(row.promotion_kind),
            valid_until=row.promotion_valid_until,
            entitlement_id=row.promotion_entitlement_id,  # type: ignore[arg-type]
        )
        if row.promotion_kind is not None
        else None
    )
    return ListingSearchDocument(
        listing_id=row.listing_id,
        owner_profile_id=row.owner_profile_id,
        title=row.title,
        title_normalized_latin=row.title_normalized_latin,
        title_normalized_cyrillic=row.title_normalized_cyrillic,
        description=row.description,
        category_id=row.category_id,
        category_path=row.category_path,
        listing_type=ListingType(row.listing_type),
        attributes=row.attributes,
        price=price,
        location=location,
        promotion=promotion,
        verified_badge=row.verified_badge,
        publicly_visible=row.publicly_visible,
        slug=row.slug,
        primary_image_thumbnail_url=row.primary_image_thumbnail_url,
        published_at=row.published_at,
        updated_at=row.updated_at,
    )


def _document_to_row_kwargs(document: ListingSearchDocument) -> dict[str, object]:
    return {
        "listing_id": document.listing_id,
        "owner_profile_id": document.owner_profile_id,
        "title": document.title,
        "title_normalized_latin": document.title_normalized_latin,
        "title_normalized_cyrillic": document.title_normalized_cyrillic,
        "description": document.description,
        "category_id": document.category_id,
        "category_path": document.category_path,
        "listing_type": document.listing_type.value,
        "attributes": document.attributes,
        "price_amount": document.price.amount if document.price else None,
        "price_currency": document.price.currency if document.price else None,
        "latitude": document.location.latitude if document.location else None,
        "longitude": document.location.longitude if document.location else None,
        "promotion_kind": document.promotion.kind.value if document.promotion else None,
        "promotion_valid_until": document.promotion.valid_until if document.promotion else None,
        "promotion_entitlement_id": (
            document.promotion.entitlement_id if document.promotion else None
        ),
        "verified_badge": document.verified_badge,
        "publicly_visible": document.publicly_visible,
        "slug": document.slug,
        "primary_image_thumbnail_url": document.primary_image_thumbnail_url,
        "published_at": document.published_at,
        "updated_at": document.updated_at,
    }


class SqlalchemyFallbackIndexRepository:
    """QR-05/NFR-REL-002's PostgreSQL degradation path. Trigram similarity on `title`
    (language-agnostic partial matching -- "cross-script matching is explicitly not a fallback
    requirement", Physical DB Design) and a plain bounding-box approximation for geo (no PostGIS,
    PD-08)."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_document(self, document: ListingSearchDocument) -> None:
        row = await self._session.get(ListingFallbackDocumentRow, document.listing_id)
        kwargs = _document_to_row_kwargs(document)
        if row is None:
            self._session.add(ListingFallbackDocumentRow(**kwargs))
            # P-20 fix (confirmed integration defect): the session factory this repository is
            # always constructed against runs with `autoflush=False` (backbone.persistence.
            # engine.make_session_factory), so a second `upsert_document` call for the SAME
            # `listing_id` on this SAME, still-open session (e.g. a content upsert immediately
            # followed by a promotion projection upsert, both within one event handler) would
            # find no row via `session.get()` -- the first `add()` is still only pending, not
            # yet visible as an existing row -- and attempt a second INSERT, raising a duplicate
            # primary key `IntegrityError`. Flushing immediately makes this method genuinely
            # idempotent-within-a-session, not just idempotent-across-transactions.
            await self._session.flush()
            return
        for key, value in kwargs.items():
            setattr(row, key, value)

    async def delete_document(self, listing_id: UUID) -> None:
        await self._session.execute(
            delete(ListingFallbackDocumentRow).where(
                ListingFallbackDocumentRow.listing_id == listing_id
            )
        )

    async def search(self, query: SearchQuery) -> SearchResultPage:
        stmt = select(ListingFallbackDocumentRow).where(
            ListingFallbackDocumentRow.publicly_visible.is_(True)
        )
        if query.category_id is not None:
            stmt = stmt.where(ListingFallbackDocumentRow.category_id == query.category_id)
        if query.category_path_prefix is not None:
            # Subtree match, mirrors the OpenSearch adapter's `prefix` filter -- `.startswith()`
            # compiles to a properly-escaped `LIKE 'prefix%'`.
            stmt = stmt.where(
                ListingFallbackDocumentRow.category_path.startswith(query.category_path_prefix)
            )
        if query.owner_profile_id is not None:
            stmt = stmt.where(ListingFallbackDocumentRow.owner_profile_id == query.owner_profile_id)
        if query.listing_type is not None:
            stmt = stmt.where(ListingFallbackDocumentRow.listing_type == query.listing_type.value)
        if query.q:
            like = f"%{query.q}%"
            stmt = stmt.where(
                or_(
                    ListingFallbackDocumentRow.title.ilike(like),
                    func.similarity(ListingFallbackDocumentRow.title, query.q) > 0.1,
                )
            )
        if query.price_min is not None:
            stmt = stmt.where(ListingFallbackDocumentRow.price_amount >= query.price_min)
        if query.price_max is not None:
            stmt = stmt.where(ListingFallbackDocumentRow.price_amount <= query.price_max)
        if query.verified_only:
            stmt = stmt.where(ListingFallbackDocumentRow.verified_badge.is_(True))
        if query.geo is not None:
            stmt = stmt.where(_geo_bounding_box(query.geo))
        stmt = stmt.order_by(ListingFallbackDocumentRow.updated_at.desc()).limit(query.limit + 1)

        result = await self._session.execute(stmt)
        rows = list(result.scalars().all())
        next_cursor = None
        if len(rows) > query.limit:
            rows = rows[: query.limit]
            next_cursor = str(rows[-1].listing_id)
        hits = tuple(SearchHitResult(document=_row_to_document(row)) for row in rows)
        return SearchResultPage(hits=hits, next_cursor=next_cursor, total=None)


def _geo_bounding_box(geo: GeoFilter) -> ColumnElement[bool]:
    """A plain lat/lng bounding-box approximation (Physical DB Design: "bounding-box radius
    approximation for fallback geo (full geo = OpenSearch; PD-08 keeps PostGIS out)") -- not a
    great-circle distance filter, deliberately: PD-08's own rationale is "the DB fallback needs
    only bounding-box arithmetic on plain numeric columns", not a PostGIS-grade radius query."""
    lat_delta = geo.radius_km / _EARTH_RADIUS_KM * (180 / math.pi)
    lng_delta = (
        geo.radius_km
        / (_EARTH_RADIUS_KM * math.cos(math.radians(geo.center.latitude)))
        * (180 / math.pi)
    )
    return ListingFallbackDocumentRow.latitude.between(
        geo.center.latitude - lat_delta, geo.center.latitude + lat_delta
    ) & ListingFallbackDocumentRow.longitude.between(
        geo.center.longitude - lng_delta, geo.center.longitude + lng_delta
    )


class SqlalchemyProjectionCheckpointRepository:
    """Backs the rebuild flow: `reset(projection_name)` clears the cursor so a fresh replay from
    the beginning of catalog's outbox stream re-derives the entire index from scratch (DB
    Architecture Sec 12: "full reindex = replay from the owners' data via their interfaces/
    events")."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_last_event_id(self, projection_name: str) -> UUID | None:
        row = await self._session.get(ProjectionCheckpointRow, projection_name)
        return row.last_event_id if row is not None else None

    async def advance(self, *, projection_name: str, last_event_id: UUID, now: datetime) -> None:
        row = await self._session.get(ProjectionCheckpointRow, projection_name)
        if row is None:
            self._session.add(
                ProjectionCheckpointRow(
                    projection_name=projection_name,
                    last_event_id=last_event_id,
                    last_position=None,
                    updated_at=now,
                )
            )
            return
        row.last_event_id = last_event_id
        row.updated_at = now

    async def reset(self, projection_name: str) -> None:
        await self._session.execute(
            delete(ProjectionCheckpointRow).where(
                ProjectionCheckpointRow.projection_name == projection_name
            )
        )
