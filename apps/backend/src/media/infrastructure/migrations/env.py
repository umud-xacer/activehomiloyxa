"""Alembic environment for the media module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from media.infrastructure.persistence import models  # noqa: F401  (registers all tables)
from media.infrastructure.persistence.base import MediaBase

run_migrations(module_name="media", target_metadata=MediaBase.metadata)
