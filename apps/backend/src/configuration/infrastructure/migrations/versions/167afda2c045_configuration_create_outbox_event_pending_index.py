"""configuration: create outbox_event pending-dispatch partial index

Revision ID: 167afda2c045
Revises: 3a5779ed6064
Create Date: 2026-07-15 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# P-21 fix (confirmed via the P-21 static index audit against Physical Database Design Sec 8):
# EVERY module's `outbox_event` table was missing this exact index -- `backbone.outbox.
# OutboxDispatcher.drain_once` (`WHERE dispatch_status = 'PENDING' ORDER BY created_at ...`)
# was doing a full sequential scan of the module's ENTIRE outbox history on every poll interval,
# not just the small, bounded pending backlog the doc's own rationale names ("dispatcher poll
# touches only the undelivered tail"). A purely additive index -- no table/column change, no
# behaviour change, only a query-plan improvement for the dispatcher's own existing query.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "167afda2c045"
down_revision: str | None = "3a5779ed6064"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_outbox_event_pending_created_at",
        "outbox_event",
        ["created_at"],
        unique=False,
        schema="configuration",
        postgresql_where="dispatch_status = 'PENDING'",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_index(
        "ix_outbox_event_pending_created_at",
        table_name="outbox_event",
        schema="configuration",
    )  # approved-destructive: fresh-install rollback
