"""profiles: create business_profile, portfolio_item, verification_case, submitted_document,
verification_entitlement_projection, outbox_event, processed_event

Revision ID: 023d4efe95eb
Revises:
Create Date: 2026-07-13 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate` -- same reason as every prior module's own
# first migration: with `include_schemas=True` (Physical DB Sec 13), autogenerate against the
# shared dev database diffs against every schema it can see and proposes dropping already-applied
# tables from other modules. Written by hand against `profiles.infrastructure.persistence.models`,
# kept in sync by manual `alembic upgrade head` / `alembic downgrade base` verification against a
# real database.
#
# `verification_entitlement_projection` is not in the documented Physical Database Design -- a
# locally-necessary projection table this task adds (I-12), the same precedent `catalog`'s own
# first migration set for `subscription_projection` (I-08).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "023d4efe95eb"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("profiles",)
depends_on: str | Sequence[str] | None = None

_PROFILE_TYPES = (
    "'CONSTRUCTION_COMPANY', 'MANUFACTURER', 'BUILDER', 'SUPPLIER', 'CONTRACTOR', 'ARCHITECT', "
    "'INTERIOR_DESIGNER', 'SERVICE_PROVIDER'"
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS profiles")

    op.create_table(
        "business_profile",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("profile_type", sa.Text(), nullable=False),
        sa.Column("name_localized", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("description_localized", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "contacts",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("address", sa.Text(), nullable=True),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), server_default="ACTIVE", nullable=False),
        sa.Column("badge_status", sa.Text(), nullable=True),
        sa.Column("badge_issued_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("badge_valid_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(f"profile_type IN ({_PROFILE_TYPES})", name="ck_business_profile_type"),
        sa.CheckConstraint(
            "status IN ('CREATED', 'ACTIVE', 'ARCHIVED')", name="ck_business_profile_status"
        ),
        sa.CheckConstraint(
            "badge_status IS NULL OR badge_status IN ('VALID', 'EXPIRED', 'REVOKED')",
            name="ck_business_profile_badge_status",
        ),
        sa.CheckConstraint(
            "(badge_status IS NULL) = (badge_issued_at IS NULL)", name="ck_badge_shape"
        ),
        sa.CheckConstraint(
            "name_localized ? 'uz_latn' OR name_localized ? 'ru'",
            name="ck_profile_name_canonical",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_business_profile"),
        schema="profiles",
    )
    op.create_index(
        "ix_business_profile_owner_user_id",
        "business_profile",
        ["owner_user_id"],
        schema="profiles",
    )

    op.create_table(
        "portfolio_item",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("business_profile_id", sa.UUID(), nullable=False),
        sa.Column("media_asset_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("caption_localized", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("position BETWEEN 1 AND 50", name="ck_portfolio_item_position"),
        sa.ForeignKeyConstraint(
            ["business_profile_id"],
            ["profiles.business_profile.id"],
            name="fk_portfolio_item_business_profile",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_portfolio_item"),
        sa.UniqueConstraint(
            "business_profile_id", "position", name="ux_portfolio_item_profile_position"
        ),
        schema="profiles",
    )

    op.create_table(
        "verification_case",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("business_profile_id", sa.UUID(), nullable=False),
        sa.Column("entitlement_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default="REQUESTED", nullable=False),
        sa.Column("sla_due_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("decision_outcome", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("reviewer_user_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('REQUESTED', 'IN_REVIEW', 'APPROVED', 'REJECTED')",
            name="ck_verification_case_status",
        ),
        sa.CheckConstraint(
            "decision_outcome IS NULL OR decision_outcome IN ('APPROVED', 'REJECTED')",
            name="ck_verification_case_decision_outcome",
        ),
        sa.CheckConstraint(
            "(status IN ('APPROVED','REJECTED')) = "
            "(decision_outcome IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_decision_shape",
        ),
        sa.ForeignKeyConstraint(
            ["business_profile_id"],
            ["profiles.business_profile.id"],
            name="fk_verification_case_business_profile",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_verification_case"),
        schema="profiles",
    )
    op.create_index(
        "ix_verification_case_business_profile_id",
        "verification_case",
        ["business_profile_id"],
        schema="profiles",
    )
    op.create_index(
        "ix_verification_case_status", "verification_case", ["status"], schema="profiles"
    )

    op.create_table(
        "submitted_document",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("verification_case_id", sa.UUID(), nullable=False),
        sa.Column("media_asset_id", sa.UUID(), nullable=False),
        sa.Column("document_kind", sa.Text(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["verification_case_id"],
            ["profiles.verification_case.id"],
            name="fk_submitted_document_verification_case",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_submitted_document"),
        sa.UniqueConstraint(
            "verification_case_id", "position", name="ux_submitted_document_case_position"
        ),
        schema="profiles",
    )

    op.create_table(
        "verification_entitlement_projection",
        sa.Column("entitlement_id", sa.UUID(), nullable=False),
        sa.Column("business_profile_id", sa.UUID(), nullable=False),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("activation_state", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "activation_state IN ('ACTIVE', 'EXPIRED', 'REVOKED')",
            name="ck_verification_entitlement_projection_state",
        ),
        sa.PrimaryKeyConstraint("entitlement_id", name="pk_verification_entitlement_projection"),
        schema="profiles",
    )
    op.create_index(
        "ix_verification_entitlement_projection_profile",
        "verification_entitlement_projection",
        ["business_profile_id", "activation_state", "valid_until"],
        schema="profiles",
    )

    op.create_table(
        "outbox_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("actor", sa.UUID(), nullable=True),
        sa.Column("aggregate_type", sa.String(), nullable=False),
        sa.Column("aggregate_id", sa.UUID(), nullable=False),
        sa.Column("aggregate_version", sa.Integer(), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("dispatch_status", sa.String(), server_default="PENDING", nullable=False),
        sa.Column("attempts", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("dispatched_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "dispatch_status IN ('PENDING', 'DISPATCHED', 'DEAD')",
            name="ck_outbox_event_dispatch_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_event"),
        schema="profiles",
    )

    op.create_table(
        "processed_event",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("handler", sa.String(), nullable=False),
        sa.Column(
            "processed_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("result", sa.String(), nullable=False),
        sa.CheckConstraint(
            "result IN ('APPLIED', 'SKIPPED', 'FAILED')", name="ck_processed_event_result"
        ),
        sa.PrimaryKeyConstraint("event_id", "handler", name="pk_processed_event"),
        schema="profiles",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table(
        "processed_event", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_table("outbox_event", schema="profiles")  # approved-destructive: fresh-install rollback
    op.drop_table(
        "verification_entitlement_projection", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "submitted_document", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "verification_case", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "portfolio_item", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "business_profile", schema="profiles"
    )  # approved-destructive: fresh-install rollback
