"""profiles: add business_profile logo/banner columns, create subscription_entitlement_projection

Revision ID: a4c1f9e7d203
Revises: 263d17ce5ef6
Create Date: 2026-08-05 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Monetization task: `logo_media_asset_id`/`banner_media_asset_id` are nullable, additive columns
# on `business_profile` (the B2B landing-page identity fields). `subscription_entitlement_
# projection` is not in the documented Physical Database Design -- a locally-necessary projection
# table this task adds, the same precedent `verification_entitlement_projection` set in this
# module's own first migration (023d4efe95eb) for I-12.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4c1f9e7d203"
down_revision: str | None = "263d17ce5ef6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "business_profile",
        sa.Column("logo_media_asset_id", sa.UUID(), nullable=True),
        schema="profiles",
    )
    op.add_column(
        "business_profile",
        sa.Column("banner_media_asset_id", sa.UUID(), nullable=True),
        schema="profiles",
    )

    op.create_table(
        "subscription_entitlement_projection",
        sa.Column("business_profile_id", sa.UUID(), nullable=False),
        sa.Column("entitlement_id", sa.UUID(), nullable=False),
        sa.Column("valid_from", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("valid_until", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("activation_state", sa.Text(), nullable=False),
        sa.Column("source_event_id", sa.UUID(), nullable=False),
        sa.CheckConstraint(
            "activation_state IN ('ACTIVE', 'EXPIRED', 'REVOKED')",
            name="ck_subscription_entitlement_projection_state",
        ),
        sa.PrimaryKeyConstraint(
            "business_profile_id", name="pk_subscription_entitlement_projection"
        ),
        schema="profiles",
    )
    op.create_index(
        "ix_subscription_entitlement_projection_state",
        "subscription_entitlement_projection",
        ["activation_state", "valid_until"],
        schema="profiles",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_index(
        "ix_subscription_entitlement_projection_state",
        table_name="subscription_entitlement_projection",
        schema="profiles",
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "subscription_entitlement_projection", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "business_profile", "banner_media_asset_id", schema="profiles"
    )  # approved-destructive: fresh-install rollback
    op.drop_column(
        "business_profile", "logo_media_asset_id", schema="profiles"
    )  # approved-destructive: fresh-install rollback
