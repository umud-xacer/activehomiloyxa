"""SQLAlchemy models for ads' Postgres-backed `BannerCampaign` aggregate (Physical Database
Design's `ads.banner_campaign` table) plus ads' own local `EntitlementProjectionRow` (event-only
projection of billing's `BANNER_SLOT_BOOKING` entitlements -- `billing` is fully forbidden by
`cross-module-ads`, so this is NOT a foreign key, just a locally-owned cache table, mirroring
`notifications.infrastructure.persistence.models.OrderRecipientProjectionRow`'s exact role).

NO impression/click counter columns anywhere in this file (Database Architecture's own
counters-correction note; I-23) -- engagement is `ads.outbox_event` metric rows only.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, CheckConstraint, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ads.infrastructure.persistence.base import AdsBase
from backbone.idempotency import make_processed_event_model
from backbone.outbox import make_outbox_event_model
from backbone.persistence import AggregateMixin

_CAMPAIGN_STATUSES = "('DRAFT', 'SCHEDULED', 'RUNNING', 'PAUSED', 'ENDED')"
_CREATIVE_STATUSES = "('PENDING', 'CLEAN', 'QUARANTINED')"
_ACTIVATION_STATES = "('ACTIVE', 'EXPIRED', 'REVOKED')"


class BannerCampaignRow(AdsBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "banner_campaign"

    placement_slot_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    placement_slot_version_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    slot_key: Mapped[str] = mapped_column(Text, nullable=False)
    creative_media_asset_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    creative_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")
    """ads' own cached projection of media's `scan_status` (I-20, X-06) -- refreshed
    synchronously at create/update/schedule time (`CreativeReaderPort`) and, when wired, by
    `infrastructure.event_projection.handle_media_event`'s late-arriving projection (see
    `ads/README.md` "Known gaps")."""
    entitlement_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    schedule_start: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    schedule_end: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    targeting: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="DRAFT")

    __table_args__ = (
        CheckConstraint(f"status IN {_CAMPAIGN_STATUSES}", name="ck_banner_campaign_status"),
        CheckConstraint(
            f"creative_status IN {_CREATIVE_STATUSES}", name="ck_banner_campaign_creative_status"
        ),
        CheckConstraint(
            "schedule_end > schedule_start", name="ck_banner_campaign_schedule_ordering"
        ),
        CheckConstraint("priority >= 0", name="ck_banner_campaign_priority_non_negative"),
    )


class EntitlementProjectionRow(AdsBase):  # type: ignore[misc,valid-type]
    """ads' own local, event-projected cache of a `BANNER_SLOT_BOOKING` billing `Entitlement`
    (I-15/I-21) -- not an aggregate root of ads' own (no `AggregateMixin`: no optimistic lock, no
    `lock_version`; a plain last-write-wins projection row, mirroring `notifications.
    infrastructure.persistence.models.OrderRecipientProjectionRow`'s exact shape)."""

    __tablename__ = "entitlement_projection"

    entitlement_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    target_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    valid_from: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    activation_state: Mapped[str] = mapped_column(Text, nullable=False, server_default="ACTIVE")

    __table_args__ = (
        CheckConstraint(
            f"activation_state IN {_ACTIVATION_STATES}",
            name="ck_entitlement_projection_activation_state",
        ),
    )


OutboxEventRow: Any = make_outbox_event_model(AdsBase)
ProcessedEventRow: Any = make_processed_event_model(AdsBase)
