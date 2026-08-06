"""identity: add account_kind and registration review columns

Revision ID: a1b2c3d4e5f6
Revises: 4e491febc40b
Create Date: 2026-08-03 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# ADR-0007: the 3-way account-role registration + admin review feature. Purely additive columns
# on `user_account` -- no existing column touched, no existing row invalidated (server defaults
# backfill every pre-existing row to INDIVIDUAL/PENDING, matching `UserAccount.account_kind`'s
# own default in the domain layer).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "4e491febc40b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_account",
        sa.Column(
            "account_kind", sa.Text(), nullable=False, server_default="INDIVIDUAL"
        ),
        schema="identity",
    )
    op.add_column(
        "user_account",
        sa.Column(
            "anketa",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        schema="identity",
    )
    op.add_column(
        "user_account",
        sa.Column("review_status", sa.Text(), nullable=False, server_default="PENDING"),
        schema="identity",
    )
    op.add_column(
        "user_account",
        sa.Column("review_decision_outcome", sa.Text(), nullable=True),
        schema="identity",
    )
    op.add_column(
        "user_account",
        sa.Column("review_decision_reason", sa.Text(), nullable=True),
        schema="identity",
    )
    op.add_column(
        "user_account",
        sa.Column("review_decision_reviewer_id", sa.UUID(), nullable=True),
        schema="identity",
    )
    op.add_column(
        "user_account",
        sa.Column(
            "review_decision_decided_at", sa.TIMESTAMP(timezone=True), nullable=True
        ),
        schema="identity",
    )
    op.create_check_constraint(
        "ck_user_account_account_kind",
        "user_account",
        "account_kind IN ('INDIVIDUAL', 'LEGAL_ENTITY', 'INVESTOR')",
        schema="identity",
    )
    op.create_check_constraint(
        "ck_user_account_review_status",
        "user_account",
        "review_status IN ('PENDING', 'APPROVED', 'REJECTED')",
        schema="identity",
    )
    op.create_index(
        "ix_user_account_review_status_created_at",
        "user_account",
        ["review_status", "created_at"],
        schema="identity",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_index(
        "ix_user_account_review_status_created_at", table_name="user_account", schema="identity"
    )  # approved-destructive: fresh-install rollback
    op.drop_constraint(
        "ck_user_account_review_status", "user_account", schema="identity", type_="check"
    )  # approved-destructive: fresh-install rollback
    op.drop_constraint(
        "ck_user_account_account_kind", "user_account", schema="identity", type_="check"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "user_account", "review_decision_decided_at", schema="identity"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "user_account", "review_decision_reviewer_id", schema="identity"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "user_account", "review_decision_reason", schema="identity"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "user_account", "review_decision_outcome", schema="identity"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "user_account", "review_status", schema="identity"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "user_account", "anketa", schema="identity"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "user_account", "account_kind", schema="identity"
    )  # approved-destructive: fresh-install rollback
