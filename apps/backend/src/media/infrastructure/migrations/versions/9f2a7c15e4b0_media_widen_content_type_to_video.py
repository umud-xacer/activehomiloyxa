"""media: widen content_type CHECK to admit video/mp4 and video/webm

Revision ID: 9f2a7c15e4b0
Revises: 6b3430390d1c
Create Date: 2026-08-04 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# ADR-0008: media intake was image-only (DEC-10) across four layers -- this migration is the
# database layer's half (alongside `domain/value_objects.py`'s `ContentType` enum,
# `interfaces/dto.py`'s Literal, and `contracts/openapi.yaml`). Purely additive: widens the
# allowed-values CHECK, no column type change, no data migration (no existing row's content_type
# could already violate the new, larger set).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9f2a7c15e4b0"
down_revision: str | None = "6b3430390d1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CONTENT_TYPES = "('image/jpeg', 'image/png', 'image/webp')"
_NEW_CONTENT_TYPES = "('image/jpeg', 'image/png', 'image/webp', 'video/mp4', 'video/webm')"


def upgrade() -> None:
    op.drop_constraint("ck_media_asset_content_type", "media_asset", schema="media", type_="check")
    op.create_check_constraint(
        "ck_media_asset_content_type",
        "media_asset",
        f"content_type IN {_NEW_CONTENT_TYPES}",
        schema="media",
    )


def downgrade() -> None:
    # approved-destructive: narrowing the CHECK back would break any row inserted with a video
    # content_type in the meantime; dev-only fresh-install rollback, never run against applied
    # data carrying real video assets.
    op.drop_constraint("ck_media_asset_content_type", "media_asset", schema="media", type_="check")
    op.create_check_constraint(
        "ck_media_asset_content_type",
        "media_asset",
        f"content_type IN {_OLD_CONTENT_TYPES}",
        schema="media",
    )
