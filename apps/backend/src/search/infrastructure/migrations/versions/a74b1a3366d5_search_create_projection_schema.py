"""search: create projection_checkpoint, listing_fallback_document, processed_event

Revision ID: a74b1a3366d5
Revises:
Create Date: 2026-07-12 00:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first; a destructive operation (DROP TABLE/COLUMN, non-additive TYPE change) needs an
# explicit marker comment `# approved-destructive: <reason>` on the same line, checked by
# tools/check_migration_safety.py (QG-09). An applied migration is never edited (AIR-14) --
# corrections are a new migration.
#
# Hand-written, not `alembic revision --autogenerate` -- same reason as catalog's/media's/
# identity's first migrations: with `include_schemas=True` (Physical DB Sec 13), autogenerate
# against the shared dev database diffs against every schema it can see and proposes dropping
# already-applied tables from other modules. Written by hand against `search.infrastructure.
# persistence.models` instead, kept in sync by a static model/migration parity test plus manual
# `alembic upgrade head` / `alembic downgrade base` verification against a real database.
#
# No table for the OpenSearch index itself (Physical DB Sec 2.5 "search schema (read model -- no
# business tables)"; DB Architecture BC-05: "the search index itself lives in OpenSearch not
# PostgreSQL") -- `search.listing_fallback_document` is search's OWN small Postgres-owned
# degradation-path copy, not a projection of `catalog.listing` (see `models.py`'s own docstring
# and `search/README.md` "Known gaps" for why the literal Physical DB Design text describing the
# fallback as querying `catalog.listing` directly could not be followed as written without
# violating this task's CRITICAL BOUNDARY RULE / ABSOLUTE ARCHITECTURE RULE 3).
#
# `pg_trgm` is enabled here, guarded by IF NOT EXISTS: no other already-merged module needs it
# (grep confirms zero prior references), and the trigram GIN index below is search's own,
# first-in-the-codebase use of it (Physical DB Design's own INDEX STRATEGY for the fallback path).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a74b1a3366d5"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = ("search",)
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "projection_checkpoint",
        sa.Column("projection_name", sa.Text(), nullable=False),
        sa.Column("last_event_id", sa.UUID(), nullable=True),
        sa.Column("last_position", sa.BigInteger(), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("projection_name", name="pk_projection_checkpoint"),
        schema="search",
    )

    op.create_table(
        "listing_fallback_document",
        sa.Column("listing_id", sa.UUID(), nullable=False),
        sa.Column("owner_profile_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("title_normalized_latin", sa.Text(), nullable=False),
        sa.Column("title_normalized_cyrillic", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.UUID(), nullable=False),
        sa.Column("category_path", sa.Text(), nullable=False),
        sa.Column("listing_type", sa.Text(), nullable=False),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("price_amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_currency", sa.Text(), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=True),
        sa.Column("longitude", sa.Float(), nullable=True),
        sa.Column("promotion_kind", sa.Text(), nullable=True),
        sa.Column("promotion_valid_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("promotion_entitlement_id", sa.UUID(), nullable=True),
        sa.Column("verified_badge", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("publicly_visible", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("slug", sa.Text(), nullable=False),
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "listing_type IN ('ADVERTISEMENT', 'PRODUCT', 'SERVICE')",
            name="ck_listing_fallback_document_listing_type",
        ),
        sa.CheckConstraint(
            "promotion_kind IS NULL OR promotion_kind IN ('PREMIUM', 'FEATURED', 'TOP_PLACEMENT')",
            name="ck_listing_fallback_document_promotion_kind",
        ),
        sa.PrimaryKeyConstraint("listing_id", name="pk_listing_fallback_document"),
        schema="search",
    )
    op.create_index(
        "ix_listing_fallback_document_title_trgm",
        "listing_fallback_document",
        ["title"],
        schema="search",
        postgresql_using="gin",
        postgresql_ops={"title": "gin_trgm_ops"},
        postgresql_where=sa.text("publicly_visible"),
    )
    op.create_index(
        "ix_listing_fallback_document_geo",
        "listing_fallback_document",
        ["latitude", "longitude"],
        schema="search",
        postgresql_where=sa.text("publicly_visible"),
    )
    op.create_index(
        "ix_listing_fallback_document_owner_profile_id",
        "listing_fallback_document",
        ["owner_profile_id"],
        schema="search",
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
        schema="search",
    )


def downgrade() -> (
    None
):  # approved-destructive: dev-only fresh-install rollback, never run against applied data
    op.drop_table(
        "processed_event", schema="search"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "listing_fallback_document", schema="search"
    )  # approved-destructive: fresh-install rollback
    op.drop_table(
        "projection_checkpoint", schema="search"
    )  # approved-destructive: fresh-install rollback
