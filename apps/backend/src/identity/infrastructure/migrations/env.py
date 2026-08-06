"""Alembic environment for the identity module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from identity.infrastructure.persistence import models  # noqa: F401  (registers all tables)
from identity.infrastructure.persistence.base import IdentityBase

run_migrations(module_name="identity", target_metadata=IdentityBase.metadata)
