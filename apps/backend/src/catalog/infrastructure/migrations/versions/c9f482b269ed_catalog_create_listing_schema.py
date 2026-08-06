"""catalog: create listing, image_attachment, listing_transition, favorite,
subscription_projection, outbox_event, processed_event

Revision ID: c9f482b269ed
Revises:
Create Date: 2026-07-11 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate` -- same reason as media's/identity's first
# migrations: with `include_schemas=True` (Physical DB Sec 13), autogenerate against the shared
# dev database diffs against every schema it can see and proposes dropping already-applied tables
# from other modules. Written by hand against `catalog.infrastructure.persistence.models`
# instead, kept in sync by a static model/migration parity test plus manual
# `alembic upgrade head` / `alembic downgrade base` verification against a real database.
#
# NO GIN index on `attribute_document` (DM-02/Physical DB "catalog schema" section) -- faceting/
# filtering on AttributeSet content is BC-05/search's job, out of this task's scope.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c9f482b269ed"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("catalog",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "listing",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("listing_type", sa.Text(), nullable=False),
        sa.Column("owner_user_id", sa.UUID(), nullable=False),
        sa.Column("owner_profile_id", sa.UUID(), nullable=True),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("category_path", sa.Text(), nullable=False),
        sa.Column("form_definition_id", sa.UUID(), nullable=False),
        sa.Column("form_definition_version_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("attribute_document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("price_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_currency", sa.Text(), nullable=True),
        sa.Column("location_lat", sa.Float(), nullable=True),
        sa.Column("location_long", sa.Float(), nullable=True),
        sa.Column("lifecycle_state", sa.Text(), server_default="DRAFT", nullable=False),
        sa.Column("is_flagged", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("promotion_kind", sa.Text(), nullable=True),
        sa.Column("promotion_valid_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("promotion_entitlement_id", sa.UUID(), nullable=True),
        sa.Column("slug", sa.Text(), nullable=False),
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
            "listing_type IN ('ADVERTISEMENT', 'PRODUCT', 'SERVICE')",
            name="ck_listing_listing_type",
        ),
        sa.CheckConstraint(
            "lifecycle_state IN ('DRAFT', 'PENDING_VERIFICATION', 'PUBLISHED', 'EDITED', "
            "'SUSPENDED', 'ARCHIVED', 'DELETED')",
            name="ck_listing_lifecycle_state",
        ),
        sa.CheckConstraint(
            "promotion_kind IS NULL OR promotion_kind IN ('PREMIUM', 'FEATURED', 'TOP_PLACEMENT')",
            name="ck_listing_promotion_kind",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_listing"),
        schema="catalog",
    )
    op.create_index("ix_listing_owner_user_id", "listing", ["owner_user_id"], schema="catalog")
    op.create_index("ix_listing_category_id", "listing", ["category_id"], schema="catalog")
    op.create_index(
        "ix_listing_visible",
        "listing",
        ["lifecycle_state", "is_flagged"],
        schema="catalog",
        postgresql_where=sa.text("lifecycle_state IN ('PUBLISHED', 'EDITED') AND NOT is_flagged"),
    )

    op.create_table(
        "image_attachment",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("media_asset_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("asset_status_snapshot", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("position BETWEEN 1 AND 10", name="ck_image_attachment_position"),
        sa.CheckConstraint(
            "asset_status_snapshot IN ('PENDING', 'CLEAN', 'QUARANTINED')",
            name="ck_image_attachment_status",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["catalog.listing.id"],
            name="fk_image_attachment_listing",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_image_attachment"),
        sa.UniqueConstraint("listing_id", "position", name="ux_image_attachment_listing_position"),
        schema="catalog",
    )

    op.create_table(
        "listing_transition",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("from_state", sa.Text(), nullable=True),
        sa.Column("to_state", sa.Text(), nullable=False),
        sa.Column("transition_kind", sa.Text(), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "occurred_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "transition_kind IN ('CREATE', 'PUBLISH', 'EDIT', 'SUSPEND', 'ARCHIVE', 'DELETE', "
            "'EXPIRE', 'RENEW', 'FLAG', 'UNFLAG', 'RESTORE')",
            name="ck_listing_transition_kind",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["catalog.listing.id"],
            name="fk_listing_transition_listing",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_listing_transition"),
        schema="catalog",
    )
    op.create_index(
        "ix_listing_transition_listing_id", "listing_transition", ["listing_id"], schema="catalog"
    )

    op.create_table(
        "favorite",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"], ["catalog.listing.id"], name="fk_favorite_listing", ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_favorite"),
        sa.UniqueConstraint("user_id", "listing_id", name="ux_favorite_user_listing"),
        schema="catalog",
    )

    op.create_table(
        "subscription_projection",
        sa.Column("owner_profile_id", sa.UUID(), nullable=False),
        sa.Column("entitlement_id", sa.UUID(), nullable=False),
        sa.Column("product_definition_id", sa.UUID(), nullable=True),
        sa.Column("quota_document", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("source_event_id", sa.UUID(), nullable=False),
        sa.PrimaryKeyConstraint("owner_profile_id", name="pk_subscription_projection"),
        schema="catalog",
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
        schema="catalog",
    )

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
            "result IN ('APPLIED', 'SKIPPED', 'FAILED')", name="ck_processed_event_result"
        ),
        sa.PrimaryKeyConstraint("event_id", "handler", name="pk_processed_event"),
        schema="catalog",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table(
        "processed_event", schema="catalog"
    )  # approved-destructive: fresh-install rollback
    op.drop_table("outbox_event", schema="catalog")  # approved-destructive: fresh-install rollback
    op.drop_table(
        "subscription_projection", schema="catalog"
    )  # approved-destructive: fresh-install rollback
    op.drop_table("favorite", schema="catalog")  # approved-destructive: fresh-install rollback
    op.drop_table(
        "listing_transition", schema="catalog"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "image_attachment", schema="catalog"
    )  # approved-destructive: fresh-install rollback
    op.drop_table("listing", schema="catalog")  # approved-destructive: fresh-install rollback
