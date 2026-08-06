"""Alembic environment for the profiles module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from profiles.infrastructure.persistence import models  # noqa: F401  (registers all tables)
from profiles.infrastructure.persistence.base import ProfilesBase

run_migrations(module_name="profiles", target_metadata=ProfilesBase.metadata)
