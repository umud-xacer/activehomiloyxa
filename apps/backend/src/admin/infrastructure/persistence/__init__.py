"""admin/infrastructure/persistence -- SQLAlchemy model + repository adapter for admin's sole
owned table."""

from __future__ import annotations

from admin.infrastructure.persistence.base import AdminBase
from admin.infrastructure.persistence.models import OperatorSessionContextRow
from admin.infrastructure.persistence.repository import SqlalchemyOperatorSessionRepository

__all__ = ["AdminBase", "OperatorSessionContextRow", "SqlalchemyOperatorSessionRepository"]
