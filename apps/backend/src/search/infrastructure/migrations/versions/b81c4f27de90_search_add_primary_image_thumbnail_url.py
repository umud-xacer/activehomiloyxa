"""search: add primary_image_thumbnail_url to listing_fallback_document

Revision ID: b81c4f27de90
Revises: a74b1a3366d5
Create Date: 2026-07-27 06:00:00.000000

# Message format is "<module>: <verb> <object>" (DevSecOps Sec 7). Expand/contract only:
# additive-first -- this is a nullable ADD COLUMN with no default backfill, so it needs no
# `# approved-destructive:` marker (QG-09) and is safe to apply ahead of the code that reads it.
#
# `SearchHit.thumbnailUrl` has been in the frozen contract since P-01, but the read model carried
# no image field at all, so `search.interfaces.routers._to_search_hit` hardcoded `None` and every
# result card on the home and search pages rendered a placeholder. This column is the fallback
# path's half of carrying the ref; the OpenSearch mapping gains the matching `keyword` field in
# `search.infrastructure.opensearch_index.INDEX_MAPPING`.
#
# Holds the resolved THUMBNAIL delivery URL, not a `MediaAssetRef`: the variant's extension
# follows the source image's format (thumbnail.png vs thumbnail.jpg), so a ref could only be
# turned back into a URL by guessing. Catalog resolves it once at emit time through the
# `MediaAssetReaderPort` it already owns. No foreign key: search owns its own schema and never
# references another module's tables (no cross-module database access, enforced by QG-05).
#
# Existing rows keep NULL until their listing is re-projected from catalog's outbox, which is the
# ordinary "no thumbnail yet" state the interface already renders a placeholder for.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b81c4f27de90"
down_revision = "a74b1a3366d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "listing_fallback_document",
        sa.Column("primary_image_thumbnail_url", sa.Text(), nullable=True),
        schema="search",
    )


def downgrade() -> None:
    # Reverses this migration's own additive column; what it holds is a projection, rebuildable
    # in full by replaying catalog's outbox. The marker trails the call because QG-09 scans
    # forward from the destructive statement, not backward (tools/check_migration_safety.py).
    op.drop_column(
        "listing_fallback_document",
        "primary_image_thumbnail_url",
        schema="search",
    )  # approved-destructive: reverses this revision's own ADD COLUMN; rebuildable projection
