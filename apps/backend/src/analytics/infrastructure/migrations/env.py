"""Alembic environment for the analytics module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from analytics.infrastructure.persistence import models  # noqa: F401  registers all ORM classes
from analytics.infrastructure.persistence.base import AnalyticsBase
from backbone.migrations.env_support import run_migrations

run_migrations(module_name="analytics", target_metadata=AnalyticsBase.metadata)
