"""Alembic environment for the ads module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from ads.infrastructure.persistence import models  # noqa: F401  registers all ORM classes
from ads.infrastructure.persistence.base import AdsBase
from backbone.migrations.env_support import run_migrations

run_migrations(module_name="ads", target_metadata=AdsBase.metadata)
