"""SQLAlchemy models for identity's Postgres-backed aggregates. `UserAccount` owns two child
tables (`authentication_method`, `role_assignment` -- DDD Sec 5.1 entities inside its aggregate
boundary, Clean Architecture rule: one aggregate = one repository = one work unit) and
`OtpChallenge` is its own small table. `Session` is Redis-backed (Security Sec 3.2) and has no
table here at all -- see `identity/infrastructure/session_store.py`.

Partial unique constraints on `phone`/`email` (P-05 prompt: "the documented uniqueness
constraints -- partial unique on phone, partial unique on email"): both columns are nullable
(cleared on anonymisation, `UserAccount.close`), so a plain `UniqueConstraint` would incorrectly
allow only one `NULL` row platform-wide once Postgres treats `NULL <> NULL`... in fact Postgres
already excludes `NULL` from standard unique constraints, but a partial index expressed
explicitly (`WHERE phone IS NOT NULL`) is used anyway to (a) match the physical-design
terminology in the P-05 prompt precisely, and (b) keep the index small (excludes anonymised
rows, Physical DB Sec 13 "small partial indexes over the hot subset").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID as PyUUID

from sqlalchemy import (
    TIMESTAMP,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from backbone.idempotency import make_processed_event_model
from backbone.outbox import make_outbox_event_model
from backbone.persistence import AggregateMixin, uuid7
from identity.infrastructure.persistence.base import IdentityBase


class UserAccountRow(IdentityBase, AggregateMixin):  # type: ignore[misc,valid-type]
    __tablename__ = "user_account"

    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    display_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    phone_reveal_mode: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="ON_REQUEST"
    )
    notify_email: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    notify_web_push: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    notify_sms: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    owned_profile_ids: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    account_kind: Mapped[str] = mapped_column(Text, nullable=False, server_default="INDIVIDUAL")
    """ADR-0007."""
    anketa: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb"), default=dict
    )
    """ADR-0007: freeform signup questionnaire answers, mirrors `business_profile.contacts`."""
    review_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="PENDING")
    """ADR-0007."""
    review_decision_outcome: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_decision_reviewer_id: Mapped[PyUUID | None] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )
    review_decision_decided_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        Index(
            "ux_user_account_phone",
            "phone",
            unique=True,
            postgresql_where=text("phone IS NOT NULL"),
        ),
        Index(
            "ux_user_account_email",
            "email",
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )


class AuthenticationMethodRow(IdentityBase):  # type: ignore[misc,valid-type]
    """Child entity of `UserAccount` (DDD Sec 5.1) -- no repository of its own; persisted as part
    of `UserAccountRepository`'s unit of work."""

    __tablename__ = "authentication_method"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    account_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.user_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    method_type: Mapped[str] = mapped_column(Text, nullable=False)
    identifier: Mapped[str] = mapped_column(Text, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    added_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("account_id", "method_type", name="ux_authentication_method_account_type"),
    )


class RoleAssignmentRow(IdentityBase):  # type: ignore[misc,valid-type]
    """Child entity of `UserAccount` (DDD Sec 5.1 "RoleAssignment [C-ref]"). References
    configuration's RoleDefinition by id only (`role_definition_head_id`/`_version_id`) -- never
    a foreign key, since that would be cross-module database access (AIR-03)."""

    __tablename__ = "role_assignment"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    account_id: Mapped[PyUUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("identity.user_account.id", ondelete="CASCADE"),
        nullable=False,
    )
    role_definition_head_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    role_definition_version_id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    role_code: Mapped[str] = mapped_column(Text, nullable=False)
    acting_profile_id: Mapped[PyUUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    assigned_by: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)

    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "role_definition_head_id",
            "acting_profile_id",
            name="ux_role_assignment_account_role_profile",
        ),
    )


class OtpChallengeRow(IdentityBase):  # type: ignore[misc,valid-type]
    __tablename__ = "otp_challenge"

    id: Mapped[PyUUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid7)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    code_hash: Mapped[str] = mapped_column(Text, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    ip_address: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_otp_challenge_phone_purpose_consumed", "phone", "purpose", "consumed_at"),
        Index("ix_otp_challenge_ip_created", "ip_address", "created_at"),
    )


OutboxEventRow: Any = make_outbox_event_model(IdentityBase)

ProcessedEventRow: Any = make_processed_event_model(IdentityBase)
"""P-20: identity's first-ever inbound event consumer (`infrastructure/event_projection.py::
handle_profiles_event`, reacting to `profiles.BusinessProfileCreated`) -- every other module
that consumes events already has one of these; identity never needed one until now since it was
previously only ever a producer, never a consumer, of cross-module events."""
