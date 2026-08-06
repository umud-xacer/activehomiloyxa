"""admin/domain -- `OperatorSessionContext`, the ONLY concept this module owns (DDD Sec 5.12:
"its only owned concept is the operator work-session context"; Physical DB Sec 2.12:
`admin.operator_session_context`). Deliberately minimal: work-session state (queue positions,
filters) is opaque JSON the operator's own UI reads/writes back verbatim -- admin has no business
reason to interpret it, so there is no invariant to guard beyond "one context per operator"
(enforced by the repository's own upsert-by-`operator_user_id` semantics, matching the physical
schema's own `UNIQUE` constraint). No FastAPI operation exists for this in v1 (no `contracts/
openapi.yaml` operation reads or writes it) -- it exists as a real, tested capability for the
future frontend session to call in-process once one exists, not manufactured domain logic to
fill out this layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from shared_kernel import UserId


@dataclass(frozen=True)
class OperatorSessionContext:
    """`id`, `operator_user_id` (xref identity, UNIQUE), `context` (opaque JSONB), `updated_at`
    -- the exact four columns of `admin.operator_session_context`, no more."""

    id: UUID
    operator_user_id: UserId
    context: dict[str, Any]
    updated_at: datetime

    @staticmethod
    def create(
        *, operator_user_id: UserId, context: dict[str, Any], now: datetime
    ) -> OperatorSessionContext:
        return OperatorSessionContext(
            id=uuid4(), operator_user_id=operator_user_id, context=context, updated_at=now
        )

    def with_context(self, *, context: dict[str, Any], now: datetime) -> OperatorSessionContext:
        """Replaces the stored work-session state wholesale (queue positions/filters are
        client-authored UI state, not merged server-side)."""
        return OperatorSessionContext(
            id=self.id, operator_user_id=self.operator_user_id, context=context, updated_at=now
        )
