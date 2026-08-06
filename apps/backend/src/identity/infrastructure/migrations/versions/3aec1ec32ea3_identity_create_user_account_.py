"""identity: create user_account, authentication_method, role_assignment, otp_challenge, outbox_event

Revision ID: 3aec1ec32ea3
Revises:
Create Date: 2026-07-11 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate`: with `include_schemas=True` (Physical DB
# Sec 13, needed so each module's own migrations only ever see their own schema at steady state),
# autogenerate against this shared dev database diffs against *every* schema it can see,
# including `configuration`'s already-applied tables, and proposes dropping them. Written by hand
# against `identity.infrastructure.persistence.models` instead -- the two are kept in sync by a
# static model/migration parity test (`apps/backend/tests/identity/test_models.py`) plus manual
# `alembic upgrade head` / `alembic downgrade base` verification against a real database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "3aec1ec32ea3"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("identity",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_account",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("phone_reveal_mode", sa.Text(), server_default="ON_REQUEST", nullable=False),
        sa.Column("notify_email", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("notify_web_push", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("notify_sms", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "owned_profile_ids",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("lock_version", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE','SUSPENDED','CLOSED')", name="ck_user_account_status"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_user_account"),
        schema="identity",
    )
    op.create_index(
        "ux_user_account_phone",
        "user_account",
        ["phone"],
        unique=True,
        schema="identity",
        postgresql_where=sa.text("phone IS NOT NULL"),
    )
    op.create_index(
        "ux_user_account_email",
        "user_account",
        ["email"],
        unique=True,
        schema="identity",
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    op.create_table(
        "authentication_method",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("method_type", sa.Text(), nullable=False),
        sa.Column("identifier", sa.Text(), nullable=False),
        sa.Column("verified_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("added_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "method_type IN ('PHONE_OTP','EMAIL','GOOGLE')",
            name="ck_authentication_method_method_type",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["identity.user_account.id"],
            name="fk_authentication_method_user_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_authentication_method"),
        sa.UniqueConstraint(
            "account_id", "method_type", name="ux_authentication_method_account_type"
        ),
        schema="identity",
    )

    op.create_table(
        "role_assignment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("role_definition_head_id", sa.UUID(), nullable=False),
        sa.Column("role_definition_version_id", sa.UUID(), nullable=False),
        sa.Column("role_code", sa.Text(), nullable=False),
        sa.Column("acting_profile_id", sa.UUID(), nullable=True),
        sa.Column("assigned_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("assigned_by", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["account_id"],
            ["identity.user_account.id"],
            name="fk_role_assignment_user_account",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_role_assignment"),
        sa.UniqueConstraint(
            "account_id",
            "role_definition_head_id",
            "acting_profile_id",
            name="ux_role_assignment_account_role_profile",
        ),
        schema="identity",
    )

    op.create_table(
        "otp_challenge",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("code_hash", sa.Text(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("ip_address", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('REGISTRATION','LOGIN','RECOVERY')", name="ck_otp_challenge_purpose"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_otp_challenge"),
        schema="identity",
    )
    op.create_index(
        "ix_otp_challenge_phone_purpose_consumed",
        "otp_challenge",
        ["phone", "purpose", "consumed_at"],
        unique=False,
        schema="identity",
    )
    op.create_index(
        "ix_otp_challenge_ip_created",
        "otp_challenge",
        ["ip_address", "created_at"],
        unique=False,
        schema="identity",
    )

    op.create_table(
        "outbox_event",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column(
            "occurred_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
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
            "created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "dispatch_status IN ('PENDING', 'DISPATCHED', 'DEAD')",
            name="ck_outbox_event_dispatch_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_outbox_event"),
        schema="identity",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table("outbox_event", schema="identity")  # approved-destructive: fresh-install rollback
    op.drop_index(
        "ix_otp_challenge_ip_created", table_name="otp_challenge", schema="identity"
    )
    op.drop_index(
        "ix_otp_challenge_phone_purpose_consumed", table_name="otp_challenge", schema="identity"
    )
    op.drop_table("otp_challenge", schema="identity")  # approved-destructive: fresh-install rollback
    op.drop_table("role_assignment", schema="identity")  # approved-destructive: fresh-install rollback
    op.drop_table("authentication_method", schema="identity")  # approved-destructive: fresh-install rollback
    op.drop_index("ux_user_account_email", table_name="user_account", schema="identity")
    op.drop_index("ux_user_account_phone", table_name="user_account", schema="identity")
    op.drop_table("user_account", schema="identity")  # approved-destructive: fresh-install rollback
