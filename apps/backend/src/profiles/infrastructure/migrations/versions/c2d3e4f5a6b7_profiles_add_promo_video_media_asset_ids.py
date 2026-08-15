"""profiles: add promo_video_media_asset_ids to business_profile

Revision ID: c2d3e4f5a6b7
Revises: 9d3f6a12b7e4
Create Date: 2026-08-15 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Additive JSONB column, NOT NULL DEFAULT '[]' -- landing-page promo-video business rule
# (site-owner spec): a business profile may attach up to 2 short promotional videos. Every
# existing row backfills to an empty array via the column default; no data migration needed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "c2d3e4f5a6b7"
down_revision: str | None = "9d3f6a12b7e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "business_profile",
        sa.Column(
            "promo_video_media_asset_ids",
            JSONB(),
            nullable=False,
            server_default="[]",
        ),
        schema="profiles",
    )


def downgrade() -> None:
    op.drop_column("business_profile", "promo_video_media_asset_ids", schema="profiles")
