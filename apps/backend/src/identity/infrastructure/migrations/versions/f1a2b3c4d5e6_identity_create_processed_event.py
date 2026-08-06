"""identity: create processed_event

Revision ID: f1a2b3c4d5e6
Revises: 3aec1ec32ea3
Create Date: 2026-07-14 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# P-20 fix: identity's first-ever inbound event consumer (`infrastructure/event_projection.py::
# handle_profiles_event`, reacting to `profiles.BusinessProfileCreated` to keep
# `owned_profile_ids` in sync -- a confirmed integration defect found by the E2E critical-journey
# suite) needs its own idempotency ledger, exactly like every other consuming module's
# `processed_event` table (mirrors moderation's own first migration, `2742dd06f884`, verbatim).
# A purely additive second migration on top of `3aec1ec32ea3` -- identity's existing tables are
# untouched.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1a2b3c4d5e6"
down_revision: str | None = "3aec1ec32ea3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
        schema="identity",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table(
        "processed_event", schema="identity"
    )  # approved-destructive: fresh-install rollback
