"""SQLAlchemy model for admin's Postgres-owned schema (Physical DB Sec 2.12): exactly ONE table,
`admin.operator_session_context` -- "sole BC-12 datum". No `AggregateMixin` (no optimistic
lock/`lock_version`): a plain last-write-wins upsert row, mirroring `notifications.infrastructure.
persistence.models.OrderRecipientProjectionRow`'s own shape for a single-owner, non-aggregate
table. No `outbox_event`/`processed_event` tables here at all -- admin publishes no events and
consumes no events (SAD Sec 8: "admin — shared_kernel (composition only)"; it is a leaf consumer
of OTHER modules' interfaces, not an event participant).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from admin.infrastructure.persistence.base import AdminBase


class OperatorSessionContextRow(AdminBase):  # type: ignore[misc,valid-type]
    __tablename__ = "operator_session_context"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    operator_user_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    context: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default="now()"
    )

    __table_args__ = (
        UniqueConstraint("operator_user_id", name="ux_operator_session_context_operator_user_id"),
    )
