"""catalog: widen listing lifecycle_state / transition_kind CHECKs for SOLD

Revision ID: d4e1a9c2f6b7
Revises: a3f7c1e9b0d4
Create Date: 2026-08-25 00:00:01.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation needs an explicit `# approved-destructive:` marker
# (QG-09). An applied migration is never edited (AIR-14) -- corrections are a new migration.
#
# "Mark as Sold" feature (2026-08-25): `catalog.domain.value_objects.LifecycleState` gained a
# new value, `SOLD`, and `TransitionKind` gained `SELL`. Postgres cannot ALTER a CHECK constraint
# in place, so this drops and re-adds both constraints under the same names with widened value
# lists -- every value that satisfied the old constraints still satisfies the new ones, so this
# is a safe widening, not a narrowing (same pattern as billing's
# `b7d3f206a419_billing_widen_entitlement_type_check`).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d4e1a9c2f6b7"
down_revision: str | None = "a3f7c1e9b0d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_LIFECYCLE_CONSTRAINT = "ck_listing_lifecycle_state"
_LIFECYCLE_OLD_VALUES = (
    "'DRAFT', 'PENDING_VERIFICATION', 'PUBLISHED', 'EDITED', 'SUSPENDED', 'ARCHIVED', 'DELETED'"
)
_LIFECYCLE_NEW_VALUES = f"{_LIFECYCLE_OLD_VALUES}, 'SOLD'"

_TRANSITION_CONSTRAINT = "ck_listing_transition_kind"
_TRANSITION_OLD_VALUES = (
    "'CREATE', 'PUBLISH', 'EDIT', 'SUSPEND', 'ARCHIVE', 'DELETE', 'EXPIRE', 'RENEW', 'FLAG', "
    "'UNFLAG', 'RESTORE'"
)
_TRANSITION_NEW_VALUES = f"{_TRANSITION_OLD_VALUES}, 'SELL'"


def upgrade() -> None:
    op.drop_constraint(
        _LIFECYCLE_CONSTRAINT, "listing", schema="catalog", type_="check"
    )  # approved-destructive: immediately re-added below with a widened (not narrowed) value list
    op.create_check_constraint(
        _LIFECYCLE_CONSTRAINT,
        "listing",
        f"lifecycle_state IN ({_LIFECYCLE_NEW_VALUES})",
        schema="catalog",
    )
    op.drop_constraint(
        _TRANSITION_CONSTRAINT, "listing_transition", schema="catalog", type_="check"
    )  # approved-destructive: immediately re-added below with a widened (not narrowed) value list
    op.create_check_constraint(
        _TRANSITION_CONSTRAINT,
        "listing_transition",
        f"transition_kind IN ({_TRANSITION_NEW_VALUES})",
        schema="catalog",
    )


def downgrade() -> (
    None
):  # approved-destructive: fails if any row already uses SOLD/SELL
    op.drop_constraint(_TRANSITION_CONSTRAINT, "listing_transition", schema="catalog", type_="check")
    op.create_check_constraint(
        _TRANSITION_CONSTRAINT,
        "listing_transition",
        f"transition_kind IN ({_TRANSITION_OLD_VALUES})",
        schema="catalog",
    )
    op.drop_constraint(_LIFECYCLE_CONSTRAINT, "listing", schema="catalog", type_="check")
    op.create_check_constraint(
        _LIFECYCLE_CONSTRAINT,
        "listing",
        f"lifecycle_state IN ({_LIFECYCLE_OLD_VALUES})",
        schema="catalog",
    )
