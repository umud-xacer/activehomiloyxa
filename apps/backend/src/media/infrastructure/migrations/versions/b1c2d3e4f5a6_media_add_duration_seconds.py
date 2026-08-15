"""media: add duration_seconds to media_asset

Revision ID: b1c2d3e4f5a6
Revises: a931f5127604
Create Date: 2026-08-15 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Additive, nullable column: promo-video business rule support (`profiles` module) needs to read
# a video asset's declared duration to enforce a 30-second cap server-side. No existing row is
# affected -- every pre-existing asset (image or video) simply reads NULL here until the async
# processing worker (re-run of `run_processing_batch`, not backfilled retroactively) populates it
# for video content going forward.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a931f5127604"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_asset",
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        schema="media",
    )


def downgrade() -> None:
    op.drop_column("media_asset", "duration_seconds", schema="media")
