"""SQLAlchemy models for analytics' Postgres-owned schema (Physical DB Sec 3.12/Sec 2.13). Three
business tables, none an aggregate-with-`AggregateMixin` (`audit_entry`/`metric_event` are
append-only facts with a composite `(id, occurred_at)` primary key -- no `lock_version`, no
optimistic locking, since a fact is never updated at all; `listing_statistics` is a rebuildable
projection). `audit_entry`/`metric_event` are monthly RANGE-partitioned on `occurred_at`
(Physical DB Sec 2 "the three highest-volume append-only tables ... are declaratively
range-partitioned by month from day one") -- partitioning is created via raw DDL in the Alembic
migration (SQLAlchemy has no declarative `PARTITION BY` helper), but the ORM mapping here is
ordinary; partitioning is transparent to INSERT/SELECT.

NO `outbox_event` table here -- Physical DB Sec 2.13's own per-module `outbox_event` table list
(`identity, profiles, catalog, configuration, media, messaging, billing, ads, moderation`)
excludes `analytics`: `MetricEventCaptured`/`AuditEntryRecorded` (`contracts/events/analytics.py`)
are in-process ingestion signals the application layer never actually dispatches through an
outbox, not events analytics publishes for another module to consume (nothing may import
analytics to begin with).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, BigInteger, CheckConstraint, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from analytics.infrastructure.persistence.base import AnalyticsBase
from backbone.idempotency import make_processed_event_model

_METRIC_KEYS = (
    "'LISTING_VIEWED', 'CONTACT_BUTTON_CLICKED', 'PHONE_REVEALED', 'CHAT_INITIATED', "
    "'FAVORITE_ADDED', 'PREMIUM_LISTING_STAT', 'BANNER_IMPRESSION_RECORDED', "
    "'BANNER_CLICK_RECORDED'"
)


class AuditEntryRow(AnalyticsBase):  # type: ignore[misc,valid-type]
    """Physical DB Sec 3.12 `analytics.audit_entry`: "append-only, partitioned, permanent
    (I-22)". `PRIMARY KEY (id, occurred_at)`; `occurred_at` is the monthly RANGE partition key."""

    __tablename__ = "audit_entry"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    actor_user_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    actor_context: Mapped[str | None] = mapped_column(Text, nullable=True)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    target_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    target_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_event_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "source_event_id", "occurred_at", name="ux_audit_entry_source_event_id_occurred_at"
        ),
    )


class MetricEventRow(AnalyticsBase):  # type: ignore[misc,valid-type]
    """Physical DB Sec 3.12 `analytics.metric_event`: "append-only, partitioned, highest write
    volume". `metric_key` CHECK is the closed v1 vocabulary (DEC-06/BRULE-20) -- codegen'd from
    `ClosedVocabularyPolicy`'s own literal set, mirrored here by hand (Physical DB Sec 2's own
    convention: "vocabulary CHECKs are codegen'd from the WhitelistRegistry... regenerated, not
    hand-edited" -- analytics' vocabulary is domain-code-closed, not `configuration`-owned, so
    this file IS the source, kept in lockstep with `domain.value_objects.MetricKey` by
    `test_value_objects.py`'s own db-vocabulary-parity test)."""

    __tablename__ = "metric_event"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), primary_key=True)
    metric_key: Mapped[str] = mapped_column(Text, nullable=False)
    listing_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    user_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    campaign_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    source_event_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    __table_args__ = (
        CheckConstraint(f"metric_key IN ({_METRIC_KEYS})", name="ck_metric_event_metric_key"),
        UniqueConstraint(
            "source_event_id", "occurred_at", name="ux_metric_event_source_event_id_occurred_at"
        ),
    )


class ListingStatisticsRow(AnalyticsBase):  # type: ignore[misc,valid-type]
    """Physical DB Sec 3.12 `analytics.listing_statistics` -- "rebuildable projection
    (FR-ANALYTICS-002)". No invariants beyond idempotent upsert (DB Architecture Sec 3.12: read
    models "may be discarded and reprojected")."""

    __tablename__ = "listing_statistics"

    listing_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    views: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    contact_clicks: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    phone_reveals: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    chats_initiated: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    favorites: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    as_of_position: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )


class ProjectionCheckpointRow(AnalyticsBase):  # type: ignore[misc,valid-type]
    """Same shape as `search.projection_checkpoint` (Physical DB Sec 3.12: "Same shape as
    search.projection_checkpoint") -- "last processed position per stream"; used only by the
    rebuild flow. Redelivery safety for a single event is `ProcessedEventRow`'s job, not this
    table's."""

    __tablename__ = "projection_checkpoint"

    projection_name: Mapped[str] = mapped_column(Text, primary_key=True)
    last_position: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )


ProcessedEventRow: Any = make_processed_event_model(AnalyticsBase)
