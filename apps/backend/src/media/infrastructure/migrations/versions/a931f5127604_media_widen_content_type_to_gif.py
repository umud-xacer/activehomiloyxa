"""media: widen content_type CHECK to admit image/gif

Revision ID: a931f5127604
Revises: 9f2a7c15e4b0
Create Date: 2026-08-11 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Widens media intake to animated GIF (banner-creative "short looping clip" use case), same
# additive shape as 9f2a7c15e4b0's image->video widening: only the allowed-values CHECK grows,
# no column type change, no data migration (no existing row's content_type could already violate
# the new, larger set).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a931f5127604"
down_revision: str | None = "9f2a7c15e4b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CONTENT_TYPES = "('image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'video/webm')"
_NEW_CONTENT_TYPES = (
    "('image/jpeg', 'image/png', 'image/webp', 'image/gif', 'video/mp4', 'video/webm')"
)


def upgrade() -> None:
    op.drop_constraint("ck_media_asset_content_type", "media_asset", schema="media", type_="check")
    op.create_check_constraint(
        "ck_media_asset_content_type",
        "media_asset",
        f"content_type IN {_NEW_CONTENT_TYPES}",
        schema="media",
    )


def downgrade() -> None:
    # approved-destructive: narrowing the CHECK back would break any row inserted with a GIF
    # content_type in the meantime; dev-only fresh-install rollback, never run against applied
    # data carrying real GIF assets.
    op.drop_constraint("ck_media_asset_content_type", "media_asset", schema="media", type_="check")
    op.create_check_constraint(
        "ck_media_asset_content_type",
        "media_asset",
        f"content_type IN {_OLD_CONTENT_TYPES}",
        schema="media",
    )
