"""Alembic environment for the billing module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from billing.infrastructure.persistence import models  # noqa: F401  registers all ORM classes
from billing.infrastructure.persistence.base import BillingBase

run_migrations(module_name="billing", target_metadata=BillingBase.metadata)
