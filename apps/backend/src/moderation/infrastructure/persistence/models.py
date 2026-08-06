"""SQLAlchemy models for moderation's Postgres-backed `ModerationCase` aggregate (Physical DB
"moderation schema" section, `moderation.moderation_case`). A single table -- no child entities
(unlike `catalog.listing`/`profiles.verification_case`, this aggregate has no ordered sub-list).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, CheckConstraint, Index, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backbone.idempotency import make_processed_event_model
from backbone.outbox import make_outbox_event_model
from backbone.persistence import AggregateMixin
from moderation.infrastructure.persistence.base import ModerationBase

_SUBJECT_TYPES = "('LISTING', 'CONVERSATION', 'USER', 'PROFILE')"
_ORIGIN_TYPES = "('USER_REPORT', 'AUTOMATED_FLAG')"
_CASE_STATUSES = "('OPEN', 'IN_REVIEW', 'RESOLVED')"
_RESOLUTION_ACTIONS = (
    "('HIDE', 'REJECT', 'SUSPEND', 'REQUEST_CORRECTION', 'REMOVE', 'SUSPEND_ACCOUNT', 'DISMISS', "
    "'REVOKE_BADGE', 'ARCHIVE_PROFILE')"
)


class ModerationCaseRow(ModerationBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "moderation_case"

    subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    subject_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    origin_type: Mapped[str] = mapped_column(Text, nullable=False)
    report_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    reporter_user_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="OPEN")
    resolution_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    moderator_user_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            f"subject_type IN {_SUBJECT_TYPES}", name="ck_moderation_case_subject_type"
        ),
        CheckConstraint(f"origin_type IN {_ORIGIN_TYPES}", name="ck_moderation_case_origin_type"),
        CheckConstraint(f"status IN {_CASE_STATUSES}", name="ck_moderation_case_status"),
        CheckConstraint(
            f"resolution_action IS NULL OR resolution_action IN {_RESOLUTION_ACTIONS}",
            name="ck_moderation_case_resolution_action",
        ),
        CheckConstraint(
            "(origin_type = 'USER_REPORT') = (report_reason IS NOT NULL)",
            name="ck_moderation_case_origin_shape",
        ),
        CheckConstraint(
            "(status = 'RESOLVED') = (resolution_action IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_moderation_case_resolved_shape",
        ),
        Index("ix_moderation_case_subject", "subject_type", "subject_id"),
        Index("ix_moderation_case_status", "status"),
    )


OutboxEventRow: Any = make_outbox_event_model(ModerationBase)
ProcessedEventRow: Any = make_processed_event_model(ModerationBase)
