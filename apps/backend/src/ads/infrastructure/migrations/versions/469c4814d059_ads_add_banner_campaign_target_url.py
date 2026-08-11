"""ads: add banner_campaign.target_url column

Revision ID: 469c4814d059
Revises: 34ee19f5a368
Create Date: 2026-08-11 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Nullable, additive column -- `BannerCampaign` (DDD Sec 5.9) previously carried no click-through
# destination at all (OpenAPI's `BannerCampaign`/`BannerServeView` only ever exposed
# `creativeMediaAssetId`), so a served banner rendered as a static, unclickable image. `NULL`
# means "no link" (renders as a plain, non-anchor creative) rather than any sentinel value --
# every pre-existing row backfills to `NULL` for free, no data migration needed.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "469c4814d059"
down_revision: str | None = "34ee19f5a368"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "banner_campaign",
        sa.Column("target_url", sa.Text(), nullable=True),
        schema="ads",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_column("banner_campaign", "target_url", schema="ads")  # approved-destructive: fresh-install rollback
