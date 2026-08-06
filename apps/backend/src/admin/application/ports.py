"""admin/application -- ports. Exactly ONE repository port: `OperatorSessionRepository`, for
admin's own sole owned datum. `AdminDashboardUseCases` (the only other use case this module
declares) depends on narrow, LOCAL "probe" Protocols defined next to it in
`dashboard_use_cases.py`, not on a shared port here -- each is a single-method subset of another
module's own `interfaces/ports.py` Protocol used only to prove the dashboard's composition wiring
is live (Absolute Architecture Rule 4: admin declares no second, redundant port for a capability
it doesn't own).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from admin.domain import OperatorSessionContext
from shared_kernel import UserId


class OperatorSessionRepository(Protocol):
    """One row per operator (`UNIQUE operator_user_id`, Physical DB Sec 2.12)."""

    async def get_by_operator(self, operator_user_id: UserId) -> OperatorSessionContext | None: ...

    async def upsert(
        self, *, operator_user_id: UserId, context: dict[str, Any], now: datetime
    ) -> OperatorSessionContext: ...
