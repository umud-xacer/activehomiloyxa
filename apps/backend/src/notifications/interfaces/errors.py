"""Registers notifications' typed application exception onto the shared `backbone.errors.
ExceptionMapper` (the same registry every other module extends). Called once from the
composition root (`apps/backend/src/main.py`).
"""

from __future__ import annotations

from backbone.errors import ExceptionMapper, simple_problem_builder
from notifications.application import NotificationNotFoundError


def register_notifications_exception_mappings(mapper: ExceptionMapper) -> None:
    mapper.register(
        NotificationNotFoundError,
        simple_problem_builder(
            status=404, code="RESOURCE_NOT_FOUND", title="Notification not found"
        ),
    )
