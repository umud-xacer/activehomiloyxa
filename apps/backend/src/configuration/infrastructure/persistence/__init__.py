"""configuration/infrastructure/persistence -- SQLAlchemy adapters (Task P-04)."""

from __future__ import annotations

from configuration.infrastructure.persistence.base import ConfigurationBase
from configuration.infrastructure.persistence.repository import SqlalchemyConfigHeadRepository

__all__ = ["ConfigurationBase", "SqlalchemyConfigHeadRepository"]
