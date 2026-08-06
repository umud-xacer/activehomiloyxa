"""SQLAlchemy models for search's Postgres-owned schema (Physical DB Sec 2.5 "search schema
(read model -- no business tables)"). Three tables, none an aggregate:

- `search.projection_checkpoint` -- "last processed event position per stream"; used only by the
  rebuild flow (reset checkpoint + replay, DB Architecture Sec 12/Physical DB Sec 2.5). Redelivery
  safety for a single event is `ProcessedEventRow`'s job, not this table's.
- `search.processed_event` -- the standard idempotency ledger (`backbone.idempotency`).
- `search.listing_fallback_document` -- search's OWN denormalised copy of `ListingSearchDocument`,
  the PostgreSQL degradation path (QR-05/NFR-REL-002). NOT a copy of `catalog.listing`: Physical
  DB Design's own text says the fallback "queries the catalog owner's own data through catalog's
  interface" and that the trigram/geo indexes live "on catalog.listing" -- this task's own
  CRITICAL BOUNDARY RULE ("must NOT import catalog... not even their interfaces/") and its
  Excluded-scope line ("any import of catalog") make that literal placement impossible without
  violating AIR-01 (this is a search task, not a catalog task) and ABSOLUTE ARCHITECTURE RULE 3
  ("No cross-module database access, ever"). Resolution (see `search/README.md` for the full
  reasoning): search owns a small fallback copy, populated by the SAME idempotent indexing
  pipeline that writes to OpenSearch -- one projection, two sinks, not a second source of truth.
  The trigram GIN and geo btree indexes are relocated here, matching the Physical DB Design's own
  INDEX STRATEGY exactly, just on search's own table instead of catalog's.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, BigInteger, Boolean, Index, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backbone.idempotency import make_processed_event_model
from search.infrastructure.persistence.base import SearchBase


class ProjectionCheckpointRow(SearchBase):  # type: ignore[misc,valid-type]
    __tablename__ = "projection_checkpoint"

    projection_name: Mapped[str] = mapped_column(Text, primary_key=True)
    last_event_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    last_position: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )


class ListingFallbackDocumentRow(SearchBase):  # type: ignore[misc,valid-type]
    __tablename__ = "listing_fallback_document"

    listing_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    owner_profile_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    title_normalized_latin: Mapped[str] = mapped_column(Text, nullable=False)
    title_normalized_cyrillic: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    category_path: Mapped[str] = mapped_column(Text, nullable=False)
    listing_type: Mapped[str] = mapped_column(Text, nullable=False)
    attributes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    latitude: Mapped[float | None] = mapped_column(nullable=True)
    longitude: Mapped[float | None] = mapped_column(nullable=True)
    promotion_kind: Mapped[str | None] = mapped_column(Text, nullable=True)
    promotion_valid_until: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    promotion_entitlement_id: Mapped[PyUUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    verified_badge: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    publicly_visible: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    slug: Mapped[str] = mapped_column(Text, nullable=False)
    primary_image_thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )

    __table_args__ = (
        Index(
            "ix_listing_fallback_document_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": "gin_trgm_ops"},
            postgresql_where=(publicly_visible.is_(True)),
        ),
        Index(
            "ix_listing_fallback_document_geo",
            "latitude",
            "longitude",
            postgresql_where=(publicly_visible.is_(True)),
        ),
        Index("ix_listing_fallback_document_owner_profile_id", "owner_profile_id"),
    )


ProcessedEventRow: Any = make_processed_event_model(SearchBase)
