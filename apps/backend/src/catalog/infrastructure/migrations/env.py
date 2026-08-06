"""Alembic environment for the catalog module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from catalog.infrastructure.persistence import models  # noqa: F401  (registers all tables)
from catalog.infrastructure.persistence.base import CatalogBase

run_migrations(module_name="catalog", target_metadata=CatalogBase.metadata)
