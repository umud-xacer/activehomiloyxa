"""admin: create operator_session_context

Revision ID: 5f292652bd4c
Revises:
Create Date: 2026-07-14 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate` -- same reason as every prior module's own
# first migration: with `include_schemas=True` (Physical DB Sec 13), autogenerate against the
# shared dev database proposes dropping other modules' already-applied tables.
#
# Exactly ONE table (Physical DB Sec 2.12 `admin.operator_session_context` -- "sole BC-12
# datum"): no outbox_event, no processed_event (admin publishes and consumes no events -- SAD
# Sec 8), no other business table (DDD Sec 5.12: "owns no marketplace aggregates").
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "5f292652bd4c"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("admin",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS admin")

    op.create_table(
        "operator_session_context",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("operator_user_id", sa.UUID(), nullable=False),
        sa.Column("context", JSONB(), nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_operator_session_context"),
        sa.UniqueConstraint(
            "operator_user_id", name="ux_operator_session_context_operator_user_id"
        ),
        schema="admin",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table(
        "operator_session_context", schema="admin"
    )  # approved-destructive: fresh-install rollback
