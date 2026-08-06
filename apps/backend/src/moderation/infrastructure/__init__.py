"""moderation/infrastructure -- the SQLAlchemy repository and idempotent cross-module event
projection handlers (Task P-12). Never imported by `moderation.interfaces`/`application`/
`domain` -- only the composition root (outside every module's package tree) wires these concrete
classes behind the ports `application/` declares. Contains no adapter classes bridging to
catalog/identity/profiles -- see `application/ports.py`'s own docstring for why those bridges
live entirely in `composition_root.py` instead (SAD Sec 8.1: moderation may statically import
`shared_kernel` only, stricter than every other module).
"""

from __future__ import annotations

from moderation.infrastructure.event_projection import (
    handle_content_reported,
    handle_listing_flagged,
)
from moderation.infrastructure.persistence import SqlalchemyModerationCaseRepository

__all__ = [
    "SqlalchemyModerationCaseRepository",
    "handle_content_reported",
    "handle_listing_flagged",
]
