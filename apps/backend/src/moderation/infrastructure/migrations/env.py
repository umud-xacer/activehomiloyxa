"""Alembic environment for the moderation module (Physical DB Sec 13). Thin by design -- the
real logic is shared across every module in backbone.migrations.env_support."""

from backbone.migrations.env_support import run_migrations
from moderation.infrastructure.persistence import models  # noqa: F401  (registers all tables)
from moderation.infrastructure.persistence.base import ModerationBase

run_migrations(module_name="moderation", target_metadata=ModerationBase.metadata)
