"""moderation: create moderation_case, outbox_event, processed_event

Revision ID: 2742dd06f884
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
# shared dev database proposes dropping other modules' already-applied tables. Written by hand
# against `moderation.infrastructure.persistence.models`, kept in sync by manual `alembic upgrade
# head` / `alembic downgrade base` verification against a real database.
#
# `subject_type`'s `PROFILE` value and `resolution_action`'s `REVOKE_BADGE`/`ARCHIVE_PROFILE`
# values are not in the documented Physical Database Design's own CHECK constraint list -- added
# per `docs/adr/0003-moderation-profile-target-extension.md` (Task P-12).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "2742dd06f884"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("moderation",)
depends_on: str | Sequence[str] | None = None

_SUBJECT_TYPES = "'LISTING', 'CONVERSATION', 'USER', 'PROFILE'"
_ORIGIN_TYPES = "'USER_REPORT', 'AUTOMATED_FLAG'"
_CASE_STATUSES = "'OPEN', 'IN_REVIEW', 'RESOLVED'"
_RESOLUTION_ACTIONS = (
    "'HIDE', 'REJECT', 'SUSPEND', 'REQUEST_CORRECTION', 'REMOVE', 'SUSPEND_ACCOUNT', 'DISMISS', "
    "'REVOKE_BADGE', 'ARCHIVE_PROFILE'"
)


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS moderation")

    op.create_table(
        "moderation_case",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("subject_type", sa.Text(), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("origin_type", sa.Text(), nullable=False),
        sa.Column("report_reason", sa.Text(), nullable=True),
        sa.Column("rule_key", sa.Text(), nullable=True),
        sa.Column("reporter_user_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.Text(), server_default="OPEN", nullable=False),
        sa.Column("resolution_action", sa.Text(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("moderator_user_id", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
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
            f"subject_type IN ({_SUBJECT_TYPES})",
            name="ck_moderation_case_subject_type",
        ),
        sa.CheckConstraint(
            f"origin_type IN ({_ORIGIN_TYPES})", name="ck_moderation_case_origin_type"
        ),
        sa.CheckConstraint(
            f"status IN ({_CASE_STATUSES})", name="ck_moderation_case_status"
        ),
        sa.CheckConstraint(
            f"resolution_action IS NULL OR resolution_action IN ({_RESOLUTION_ACTIONS})",
            name="ck_moderation_case_resolution_action",
        ),
        sa.CheckConstraint(
            "(origin_type = 'USER_REPORT') = (report_reason IS NOT NULL)",
            name="ck_moderation_case_origin_shape",
        ),
        sa.CheckConstraint(
            "(status = 'RESOLVED') = (resolution_action IS NOT NULL AND resolved_at IS NOT NULL)",
            name="ck_moderation_case_resolved_shape",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_moderation_case"),
        schema="moderation",
    )
    op.create_index(
        "ix_moderation_case_subject",
        "moderation_case",
        ["subject_type", "subject_id"],
        schema="moderation",
    )
    op.create_index(
        "ix_moderation_case_status", "moderation_case", ["status"], schema="moderation"
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
        sa.Column(
            "dispatch_status", sa.String(), server_default="PENDING", nullable=False
        ),
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
        schema="moderation",
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
            "result IN ('APPLIED', 'SKIPPED', 'FAILED')",
            name="ck_processed_event_result",
        ),
        sa.PrimaryKeyConstraint("event_id", "handler", name="pk_processed_event"),
        schema="moderation",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table(
        "processed_event", schema="moderation"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "outbox_event", schema="moderation"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "moderation_case", schema="moderation"
    )  # approved-destructive: fresh-install rollback
