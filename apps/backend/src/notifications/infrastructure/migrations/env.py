"""Alembic environment for the notifications module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from notifications.infrastructure.persistence import models  # noqa: F401  (registers all tables)
from notifications.infrastructure.persistence.base import NotificationsBase

run_migrations(module_name="notifications", target_metadata=NotificationsBase.metadata)
