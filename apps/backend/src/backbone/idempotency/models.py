"""`<schema>.processed_event` ORM mapping factory (Physical DB Sec 2.13). One call per consuming
module against that module's own `Base` -- the ledger lives in the module's own schema, per
PD-06/DM-01.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID as PyUUID

from sqlalchemy import TIMESTAMP, CheckConstraint, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

RESULTS = ("APPLIED", "SKIPPED", "FAILED")


def make_processed_event_model(base: type[DeclarativeBase]) -> type[DeclarativeBase]:
    """Returns a `ProcessedEventRow` ORM class mapped to `<base's schema>.processed_event`.
    Composite primary key `(event_id, handler)`: the same event may be legitimately processed
    by more than one handler in the same module, but never twice by the same handler (Logical
    Sec 18 "idempotency is data")."""

    class ProcessedEventRow(base):  # type: ignore[misc,valid-type]
        __tablename__ = "processed_event"
        __table_args__ = (
            CheckConstraint(f"result IN {RESULTS}", name="ck_processed_event_result"),
        )

        event_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
        handler: Mapped[str] = mapped_column(String, primary_key=True)
        processed_at: Mapped[datetime] = mapped_column(
            TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
        )
        result: Mapped[str] = mapped_column(String, nullable=False)

    return ProcessedEventRow
