"""configuration: allow NULL in draft-bearing promoted columns

Revision ID: c93f1a55e7d2
Revises: 167afda2c045
Create Date: 2026-07-27 08:20:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# DROP NOT NULL is a widening, backwards-compatible change -- every value that satisfied the old
# constraint still satisfies the new one -- so it needs no `# approved-destructive:` marker
# (QG-09) and can be applied ahead of the code that relies on it.
#
# `category_version.form_definition_id` and `placement_slot_version.slot_key` were NOT NULL on
# tables that hold DRAFTS. Config Framework Sec 9 (and `SqlalchemyConfigHeadRepository.
# _extra_version_columns`'s own docstring) require the opposite: "a maker can always save and get
# a precise rejection at validate/submit time". A half-finished category with no form chosen yet,
# or a slot with no key typed yet, is ordinary work-in-progress -- but saving it raised
# NotNullViolation, surfacing to the operator as a bare 500 with nothing naming the field.
#
# The promoted columns are a denormalised, indexable copy of `definition_document` (Physical DB
# Sec 2.4), never the source of truth. Requiredness belongs to the gate, which reads the document
# and reports per-field errors; enforcing it a second time in the physical schema only turned a
# reviewable gate error into an unreviewable crash. `slot_key` gets an empty-string sentinel from
# the repository rather than NULL, so its column stays NOT NULL; only the two genuinely
# reference-shaped columns are relaxed.
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c93f1a55e7d2"
down_revision: str | None = "167afda2c045"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.alter_column(
        "category_version",
        "form_definition_id",
        nullable=True,
        schema="configuration",
    )


def downgrade() -> None:
    # approved-destructive: restoring NOT NULL fails if any draft row legitimately holds NULL --
    # which is precisely the state the upgrade exists to allow. Reversible only on a database
    # whose category drafts all name an existing form.
    op.alter_column(
        "category_version",
        "form_definition_id",
        nullable=False,
        schema="configuration",
    )
