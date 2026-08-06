"""analytics: create audit_entry, metric_event, listing_statistics, projection_checkpoint,
processed_event schema

Revision ID: d8ee38154c92
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
# `audit_entry`/`metric_event` are created via raw DDL (`op.execute`), not `op.create_table`:
# Alembic/SQLAlchemy have no declarative helper for PostgreSQL's `PARTITION BY RANGE` -- Physical
# DB Sec 2's own text names these two (plus `notifications.notification`) as "the three
# highest-volume append-only tables ... declaratively range-partitioned by month from day one".
# A handful of partitions are precreated here for the months spanning this migration's own
# deploy window; `analytics.infrastructure.partition_worker.PartitionPrecreateWorker` is the
# ongoing scheduled job that keeps future months' partitions ahead of need (P-15's own explicit
# deliverable -- unlike `notifications.notification` in P-13, which deliberately deferred real
# partition precreation as out of scope at the time).
#
# Immutability guard triggers (Physical DB PD-07, `backbone.migrations.guard_trigger_ddl`) are
# applied to BOTH `audit_entry` and `metric_event` -- pure append-only, zero mutable columns,
# matching that helper's own docstring which names these two tables as its primary use case.
# `listing_statistics`/`projection_checkpoint` are NOT guarded -- both are rebuildable
# projections with no invariants (DB Architecture Sec 3.12), mutated freely by the projection
# builder and the rebuild flow.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

from backbone.migrations import (
    drop_guard_trigger_ddl,
    guard_trigger_ddl,
    upcoming_month_partition_ddls,
)

# revision identifiers, used by Alembic.
revision: str = "d8ee38154c92"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("analytics",)
depends_on: str | Sequence[str] | None = None

_METRIC_KEYS = (
    "'LISTING_VIEWED', 'CONTACT_BUTTON_CLICKED', 'PHONE_REVEALED', 'CHAT_INITIATED', "
    "'FAVORITE_ADDED', 'PREMIUM_LISTING_STAT', 'BANNER_IMPRESSION_RECORDED', "
    "'BANNER_CLICK_RECORDED'"
)

# Partitions precreated at migration time -- enough months to comfortably span the deploy window
# without relying on the worker having run yet. The worker keeps this rolling forward afterward.
_INITIAL_MONTHS_AHEAD = 3


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS analytics")

    op.execute(
        """
        CREATE TABLE analytics.audit_entry (
            id UUID NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            actor_user_id UUID,
            actor_context TEXT,
            action TEXT NOT NULL,
            target_type TEXT,
            target_id UUID,
            payload JSONB NOT NULL,
            source_event_id UUID NOT NULL,
            CONSTRAINT pk_audit_entry PRIMARY KEY (id, occurred_at),
            CONSTRAINT ux_audit_entry_source_event_id_occurred_at
                UNIQUE (source_event_id, occurred_at)
        ) PARTITION BY RANGE (occurred_at)
        """
    )
    op.execute(
        "CREATE INDEX ix_audit_entry_actor_user_id ON analytics.audit_entry (actor_user_id, occurred_at)"
    )
    op.execute("CREATE INDEX ix_audit_entry_action ON analytics.audit_entry (action, occurred_at)")
    op.execute(
        "CREATE INDEX ix_audit_entry_target ON analytics.audit_entry (target_type, target_id)"
    )

    op.execute(
        f"""
        CREATE TABLE analytics.metric_event (
            id UUID NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            metric_key TEXT NOT NULL,
            listing_id UUID,
            user_id UUID,
            campaign_id UUID,
            payload JSONB NOT NULL,
            source_event_id UUID NOT NULL,
            CONSTRAINT pk_metric_event PRIMARY KEY (id, occurred_at),
            CONSTRAINT ck_metric_event_metric_key CHECK (metric_key IN ({_METRIC_KEYS})),
            CONSTRAINT ux_metric_event_source_event_id_occurred_at
                UNIQUE (source_event_id, occurred_at)
        ) PARTITION BY RANGE (occurred_at)
        """
    )
    op.execute(
        "CREATE INDEX ix_metric_event_listing_id ON analytics.metric_event (listing_id, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_metric_event_metric_key ON analytics.metric_event (metric_key, occurred_at)"
    )
    op.execute(
        "CREATE INDEX ix_metric_event_campaign_id ON analytics.metric_event (campaign_id, occurred_at)"
    )

    now = datetime.now(UTC)
    for table in ("audit_entry", "metric_event"):
        for ddl in upcoming_month_partition_ddls(
            "analytics",
            table,
            from_year=now.year,
            from_month=now.month,
            months_ahead=_INITIAL_MONTHS_AHEAD,
        ):
            op.execute(ddl)

    for stmt in guard_trigger_ddl("analytics", "audit_entry"):
        op.execute(stmt)
    for stmt in guard_trigger_ddl("analytics", "metric_event"):
        op.execute(stmt)

    op.create_table(
        "listing_statistics",
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("views", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("contact_clicks", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("phone_reveals", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("chats_initiated", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("favorites", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column("as_of_position", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("listing_id", name="pk_listing_statistics"),
        schema="analytics",
    )

    op.create_table(
        "projection_checkpoint",
        sa.Column("projection_name", sa.Text(), nullable=False),
        sa.Column("last_position", sa.BigInteger(), server_default="0", nullable=False),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("projection_name", name="pk_projection_checkpoint"),
        schema="analytics",
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
            "result IN ('APPLIED', 'SKIPPED', 'FAILED')",
            name="ck_processed_event_result",
        ),
        sa.PrimaryKeyConstraint("event_id", "handler", name="pk_processed_event"),
        schema="analytics",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table(
        "processed_event", schema="analytics"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "projection_checkpoint", schema="analytics"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "listing_statistics", schema="analytics"
    )  # approved-destructive: fresh-install rollback
    for stmt in drop_guard_trigger_ddl("analytics", "metric_event"):
        op.execute(stmt)  # approved-destructive: fresh-install rollback
    for stmt in drop_guard_trigger_ddl("analytics", "audit_entry"):
        op.execute(stmt)  # approved-destructive: fresh-install rollback
    op.execute(
        "DROP TABLE analytics.metric_event"
    )  # approved-destructive: fresh-install rollback (cascades to all its partitions)
    op.execute(
        "DROP TABLE analytics.audit_entry"
    )  # approved-destructive: fresh-install rollback (cascades to all its partitions)
