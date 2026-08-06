"""Alembic environment for the messaging module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from messaging.infrastructure.persistence import models  # noqa: F401  registers all ORM classes
from messaging.infrastructure.persistence.base import MessagingBase

run_migrations(module_name="messaging", target_metadata=MessagingBase.metadata)
