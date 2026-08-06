"""Alembic environment for the search module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from search.infrastructure.persistence import models  # noqa: F401  (registers all tables)
from search.infrastructure.persistence.base import SearchBase

run_migrations(module_name="search", target_metadata=SearchBase.metadata)
