"""Alembic environment for the admin module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from admin.infrastructure.persistence import models  # noqa: F401  registers all ORM classes
from admin.infrastructure.persistence.base import AdminBase
from backbone.migrations.env_support import run_migrations

run_migrations(module_name="admin", target_metadata=AdminBase.metadata)
