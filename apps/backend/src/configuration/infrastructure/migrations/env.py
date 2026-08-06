"""Alembic environment for the configuration module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from configuration.infrastructure.persistence import models  # noqa: F401  (registers all tables)
from configuration.infrastructure.persistence.base import ConfigurationBase

run_migrations(module_name="configuration", target_metadata=ConfigurationBase.metadata)
