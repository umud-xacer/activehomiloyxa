"""`<schema>.outbox_event` ORM mapping factory (Physical DB Sec 2.13). One call per emitting
module against that module's own `Base` (from `backbone.persistence.make_module_base`) -- the
table lives in the module's own schema, per PD-06/DM-01, not a shared table.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, CheckConstraint, SmallInteger, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

DISPATCH_STATUSES = ("PENDING", "DISPATCHED", "DEAD")


def make_outbox_event_model(base: type[DeclarativeBase]) -> type[DeclarativeBase]:
    """Returns an `OutboxEventRow` ORM class mapped to `<base's schema>.outbox_event`, columns
    matching Physical DB Sec 2.13 exactly (id, event_type, occurred_at, actor, aggregate_type,
    aggregate_id, aggregate_version, payload, dispatch_status, attempts, dispatched_at,
    created_at)."""

    class OutboxEventRow(base):  # type: ignore[misc,valid-type]
        __tablename__ = "outbox_event"
        __table_args__ = (
            CheckConstraint(
                f"dispatch_status IN {DISPATCH_STATUSES}",
                name="ck_outbox_event_dispatch_status",
            ),
        )

        id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
        event_type: Mapped[str] = mapped_column(String, nullable=False)
        occurred_at: Mapped[datetime] = mapped_column(
            TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
        )
        actor: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
        aggregate_type: Mapped[str] = mapped_column(String, nullable=False)
        aggregate_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
        aggregate_version: Mapped[int | None] = mapped_column(nullable=True)
        payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
        dispatch_status: Mapped[str] = mapped_column(
            String, nullable=False, server_default="PENDING"
        )
        attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0")
        dispatched_at: Mapped[datetime | None] = mapped_column(
            TIMESTAMP(timezone=True), nullable=True
        )
        created_at: Mapped[datetime] = mapped_column(
            TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
        )

    return OutboxEventRow
