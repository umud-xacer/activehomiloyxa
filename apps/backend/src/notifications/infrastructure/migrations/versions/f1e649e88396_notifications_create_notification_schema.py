"""notifications: create notification schema

Revision ID: f1e649e88396
Revises:
Create Date: 2026-07-13 17:04:55.649543

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate` -- same reason as every prior module's own
# first migration: with `include_schemas=True` (Physical DB Sec 13), autogenerate against the
# shared dev database proposes dropping other modules' already-applied tables. Written by hand
# against `notifications.infrastructure.persistence.models`, kept in sync by manual `alembic
# upgrade head` / `alembic downgrade base` verification against a real database.
#
# `notification` is created via raw DDL (`op.execute`), not `op.create_table`: Alembic/SQLAlchemy
# have no declarative helper for PostgreSQL's `PARTITION BY RANGE` -- Physical DB Sec 2.10 names
# `notifications.notification` as monthly RANGE-partitioned on `created_at` (PD-04), the first
# partitioned table any module in this codebase has needed. A single `DEFAULT` partition is
# created here (catches every row regardless of date) -- provisioning real monthly partitions
# ahead of time is deployment/ops tooling (a scheduled job creating next month's partition
# before it's needed), out of this task's application-code scope, the same "operational,
# not per-request business logic" reasoning the Physical DB Design's own "bounded retention ->
# partition drop is the purge mechanism" note already treats as an ops concern.
#
# `read_at` is not in the documented Physical Database Design's own column list for
# `notification` -- added because the already-frozen `contracts/openapi.yaml` (Task P-01)
# requires it (`Notification.readAt`, `setNotificationRead`, `markAllNotificationsRead`) -- a
# "locally necessary addition" serving an already-frozen contract, the same class of gap
# `profiles`'s own local projection table already resolved without an ADR.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f1e649e88396"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("notifications",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS notifications")

    op.execute(
        """
        CREATE TABLE notifications.notification (
            id UUID NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            recipient_user_id UUID NOT NULL,
            event_key TEXT NOT NULL,
            channel TEXT NOT NULL,
            template_id UUID NOT NULL,
            template_version_id UUID NOT NULL,
            locale TEXT NOT NULL,
            rendered_subject TEXT,
            rendered_body TEXT NOT NULL,
            delivery_status TEXT NOT NULL DEFAULT 'QUEUED',
            attempts SMALLINT NOT NULL DEFAULT 0,
            provider_message_ref TEXT,
            sent_at TIMESTAMPTZ,
            read_at TIMESTAMPTZ,
            CONSTRAINT pk_notification PRIMARY KEY (id, created_at),
            CONSTRAINT ck_notification_channel CHECK (channel IN ('EMAIL', 'WEB_PUSH', 'SMS')),
            CONSTRAINT ck_notification_locale CHECK (locale IN ('uz_latn', 'uz_cyrl', 'ru', 'en')),
            CONSTRAINT ck_notification_delivery_status
                CHECK (delivery_status IN ('QUEUED', 'SENT', 'DELIVERED', 'FAILED'))
        ) PARTITION BY RANGE (created_at)
        """
    )
    op.execute(
        "CREATE INDEX ix_notification_recipient ON notifications.notification "
        "(recipient_user_id, created_at)"
    )
    op.execute(
        "CREATE TABLE notifications.notification_default "
        "PARTITION OF notifications.notification DEFAULT"
    )

    op.create_table(
        "order_recipient_projection",
        sa.Column("order_id", sa.UUID(), nullable=False),
        sa.Column("purchaser_profile_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("order_id", name="pk_order_recipient_projection"),
        schema="notifications",
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
        schema="notifications",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table(
        "processed_event", schema="notifications"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "order_recipient_projection", schema="notifications"
    )  # approved-destructive: fresh-install rollback
    op.execute(
        "DROP TABLE notifications.notification_default"
    )  # approved-destructive: fresh-install rollback
    op.execute(
        "DROP TABLE notifications.notification"
    )  # approved-destructive: fresh-install rollback
