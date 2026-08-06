"""messaging: create conversation, message, block, outbox_event, processed_event

Revision ID: 98f4e9a7713f
Revises:
Create Date: 2026-07-12 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate` -- same reason as every prior module's own
# first migration: with `include_schemas=True` (Physical DB Sec 13), autogenerate against the
# shared dev database diffs against every schema it can see and proposes dropping already-applied
# tables from other modules. Written by hand against `messaging.infrastructure.persistence.
# models`, kept in sync by manual `alembic upgrade head` / `alembic downgrade base` verification
# against a real database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "98f4e9a7713f"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = "messaging"
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS messaging")

    op.create_table(
        "conversation",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("initiator_user_id", sa.UUID(), nullable=False),
        sa.Column("recipient_user_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), server_default="ACTIVE", nullable=False),
        sa.Column("last_message_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
        sa.Column("lock_version", sa.Integer(), server_default="0", nullable=False),
        sa.CheckConstraint(
            "status IN ('INITIATED', 'ACTIVE', 'ARCHIVED')", name="ck_conversation_status"
        ),
        sa.CheckConstraint(
            "initiator_user_id <> recipient_user_id", name="ck_conversation_distinct_participants"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_conversation"),
        sa.UniqueConstraint(
            "listing_id", "initiator_user_id", name="ux_conversation_listing_initiator"
        ),
        schema="messaging",
    )
    op.create_index(
        "ix_conversation_initiator_last_message",
        "conversation",
        ["initiator_user_id", "last_message_at"],
        schema="messaging",
    )
    op.create_index(
        "ix_conversation_recipient_last_message",
        "conversation",
        ["recipient_user_id", "last_message_at"],
        schema="messaging",
    )

    op.create_table(
        "message",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("conversation_id", sa.UUID(), nullable=False),
        sa.Column("author_user_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "sent_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("delivered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["messaging.conversation.id"],
            name="fk_message_conversation",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_message"),
        schema="messaging",
    )
    op.create_index(
        "ix_message_conversation_sent",
        "message",
        ["conversation_id", "sent_at"],
        schema="messaging",
    )

    op.create_table(
        "block",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("blocker_user_id", sa.UUID(), nullable=False),
        sa.Column("blocked_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("blocker_user_id <> blocked_user_id", name="ck_block_distinct_users"),
        sa.PrimaryKeyConstraint("id", name="pk_block"),
        sa.UniqueConstraint("blocker_user_id", "blocked_user_id", name="ux_block_blocker_blocked"),
        schema="messaging",
    )
    op.create_index("ix_block_blocked_user", "block", ["blocked_user_id"], schema="messaging")

    op.create_table(
        "listing_owner_projection",
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("listing_id", name="pk_listing_owner_projection"),
        schema="messaging",
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
        schema="messaging",
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
        schema="messaging",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table("processed_event", schema="messaging")  # approved-destructive: dev-only rollback
    op.drop_table("outbox_event", schema="messaging")  # approved-destructive: dev-only rollback
    op.drop_table("listing_owner_projection", schema="messaging")  # approved-destructive: dev-only
    op.drop_table("block", schema="messaging")  # approved-destructive: fresh-install rollback
    op.drop_table("message", schema="messaging")  # approved-destructive: fresh-install rollback
    op.drop_table("conversation", schema="messaging")  # approved-destructive: dev-only rollback
