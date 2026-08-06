"""ads: create banner_campaign, entitlement_projection, outbox_event, processed_event

Revision ID: 7e41075d53f8
Revises:
Create Date: 2026-07-13 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate` -- same reason as billing's/catalog's/
# search's first migrations: with `include_schemas=True` (Physical DB Sec 13), autogenerate
# against the shared dev database diffs against every schema it can see and proposes dropping
# already-applied tables from other modules. Written by hand against `ads.infrastructure.
# persistence.models` instead.
#
# `ads.banner_campaign` carries NO impression/click counter columns (Physical Database Design's
# own explicit note: "No impression/click counters here -- engagement is analytics.metric_event
# only", Database Architecture's counters-correction note, I-23). `ads.entitlement_projection` is
# ads' own local, event-projected cache of billing's `BANNER_SLOT_BOOKING` entitlements -- not a
# foreign key (billing is fully forbidden by `cross-module-ads`), just a locally-owned table.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7e41075d53f8"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("ads",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "banner_campaign",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("placement_slot_id", sa.UUID(), nullable=False),
        sa.Column("placement_slot_version_id", sa.UUID(), nullable=False),
        sa.Column("slot_key", sa.Text(), nullable=False),
        sa.Column("creative_media_asset_id", sa.UUID(), nullable=False),
        sa.Column("creative_status", sa.Text(), server_default="PENDING", nullable=False),
        sa.Column("entitlement_id", sa.UUID(), nullable=False),
        sa.Column("schedule_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("schedule_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("targeting", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.Text(), server_default="DRAFT", nullable=False),
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
            "status IN ('DRAFT', 'SCHEDULED', 'RUNNING', 'PAUSED', 'ENDED')",
            name="ck_banner_campaign_status",
        ),
        sa.CheckConstraint(
            "creative_status IN ('PENDING', 'CLEAN', 'QUARANTINED')",
            name="ck_banner_campaign_creative_status",
        ),
        sa.CheckConstraint(
            "schedule_end > schedule_start", name="ck_banner_campaign_schedule_ordering"
        ),
        sa.CheckConstraint("priority >= 0", name="ck_banner_campaign_priority_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_banner_campaign"),
        schema="ads",
    )
    op.create_index(
        "ix_banner_campaign_slot_key_status",
        "banner_campaign",
        ["slot_key", "status", "priority"],
        schema="ads",
        postgresql_where=sa.text("status IN ('SCHEDULED', 'RUNNING')"),
    )
    op.create_index(
        "ix_banner_campaign_creative_media_asset_id",
        "banner_campaign",
        ["creative_media_asset_id"],
        schema="ads",
    )
    op.create_index(
        "ix_banner_campaign_status_schedule_start",
        "banner_campaign",
        ["status", "schedule_start"],
        schema="ads",
        postgresql_where=sa.text("status = 'SCHEDULED'"),
    )
    op.create_index(
        "ix_banner_campaign_status_schedule_end",
        "banner_campaign",
        ["status", "schedule_end"],
        schema="ads",
        postgresql_where=sa.text("status IN ('SCHEDULED', 'RUNNING', 'PAUSED')"),
    )

    op.create_table(
        "entitlement_projection",
        sa.Column("entitlement_id", sa.UUID(), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=False),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("activation_state", sa.Text(), server_default="ACTIVE", nullable=False),
        sa.CheckConstraint(
            "activation_state IN ('ACTIVE', 'EXPIRED', 'REVOKED')",
            name="ck_entitlement_projection_activation_state",
        ),
        sa.PrimaryKeyConstraint("entitlement_id", name="pk_entitlement_projection"),
        schema="ads",
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
        schema="ads",
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
        schema="ads",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table("processed_event", schema="ads")  # approved-destructive: dev-only rollback
    op.drop_table("outbox_event", schema="ads")  # approved-destructive: fresh-install rollback
    op.drop_table(
        "entitlement_projection", schema="ads"
    )  # approved-destructive: fresh-install rollback
    op.drop_table("banner_campaign", schema="ads")  # approved-destructive: dev-only rollback
