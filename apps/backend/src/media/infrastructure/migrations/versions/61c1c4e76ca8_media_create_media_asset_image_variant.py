"""media: create media_asset, image_variant, outbox_event

Revision ID: 61c1c4e76ca8
Revises:
Create Date: 2026-07-11 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate` -- same reason as identity's first
# migration (`identity/infrastructure/migrations/versions/3aec1ec32ea3_...py`): with
# `include_schemas=True` (Physical DB Sec 13), autogenerate against the shared dev database
# diffs against every schema it can see and proposes dropping already-applied tables from other
# modules. Written by hand against `media.infrastructure.persistence.models` instead, kept in
# sync by a static model/migration parity test plus manual `alembic upgrade head` /
# `alembic downgrade base` verification against a real database.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "61c1c4e76ca8"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("media",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media_asset",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("owner_context_type", sa.Text(), nullable=False),
        sa.Column("owner_context_id", sa.UUID(), nullable=True),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("scan_status", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column("processing_status", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column("exif_stripped", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("uploaded_by", sa.UUID(), nullable=False),
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
            "owner_context_type IN ('LISTING', 'PROFILE_PORTFOLIO', 'VERIFICATION_DOCUMENT', "
            "'BANNER_CREATIVE')",
            name="ck_media_asset_owner_context_type",
        ),
        sa.CheckConstraint(
            "content_type IN ('image/jpeg', 'image/png', 'image/webp')",
            name="ck_media_asset_content_type",
        ),
        sa.CheckConstraint("size_bytes > 0", name="ck_media_asset_size_bytes"),
        sa.CheckConstraint(
            "scan_status IN ('PENDING', 'CLEAN', 'QUARANTINED')", name="ck_media_asset_scan_status"
        ),
        sa.CheckConstraint(
            "processing_status IN ('PENDING', 'COMPLETED', 'FAILED')",
            name="ck_media_asset_processing_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_media_asset"),
        sa.UniqueConstraint("storage_key", name="ux_media_asset_storage_key"),
        schema="media",
    )

    op.create_table(
        "image_variant",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("media_asset_id", sa.UUID(), nullable=False),
        sa.Column("variant_kind", sa.Text(), nullable=False),
        sa.Column("storage_key", sa.Text(), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=False),
        sa.Column("height_px", sa.Integer(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.CheckConstraint(
            "variant_kind IN ('THUMBNAIL', 'OPTIMIZED')", name="ck_image_variant_variant_kind"
        ),
        sa.ForeignKeyConstraint(
            ["media_asset_id"],
            ["media.media_asset.id"],
            name="fk_image_variant_media_asset",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_variant"),
        sa.UniqueConstraint("storage_key", name="ux_image_variant_storage_key"),
        sa.UniqueConstraint("media_asset_id", "variant_kind", name="ux_image_variant_asset_kind"),
        schema="media",
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
        sa.Column("dispatch_status", sa.String(), server_default="PENDING", nullable=False),
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
        schema="media",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table("outbox_event", schema="media")  # approved-destructive: fresh-install rollback
    op.drop_table("image_variant", schema="media")  # approved-destructive: fresh-install rollback
    op.drop_table("media_asset", schema="media")  # approved-destructive: fresh-install rollback
