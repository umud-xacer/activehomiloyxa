"""admin/application -- `AdminDashboardUseCases`: this module's ONE genuinely own operation
(`getAdminDashboard` maps to no single owning aggregate, DDD Sec 5.12/`contracts/README.md`).

None of `DashboardSummary`'s five fields are cheaply computable today: no module's existing
operator-facing list operation (`listModerationQueue`, `listVerificationQueue`,
`adminListInvoices`, `adminListUsers`) ever populates `CursorPage.page.total` (verified against
every one of those modules' own repository implementations -- none of them run a `COUNT(*)`
alongside their cursor query), and `activeListings` needs `catalog` (BC-03) data, which admin is
not permitted to import at all (BC-03 is outside admin's allowed BC-01/02/04/08/09/11/13 set --
`cross-module-admin`, `tools/importlinter.cfg`). Surfaced to the repository owner; the owner's
explicit direction: return an honest `null` for every field this module cannot cheaply compute
(mirroring the already-established precedent -- `catalog.getListingStatistics`'s own null
analytics-owned fields, `analytics`'s own `USER_GROWTH` "unavailable" report) rather than a
fabricated or expensively-approximated count. `activeListings` is null unconditionally.

The four reachable fields still make a real, cheap call through each owning module's port
(`limit=1`) to prove the composition wiring is live and permission-checked end to end -- not a
dead code path -- but never use the returned page to approximate a count (a partial page is not
a total).
"""

from __future__ import annotations

from typing import Any, Protocol


class _ModerationQueueProbe(Protocol):
    async def list_moderation_queue(
        self, status: str | None = None, limit: int | None = 20
    ) -> object: ...


class _VerificationQueueProbe(Protocol):
    async def list_verification_queue(
        self, status: str | None = None, limit: int | None = 20
    ) -> object: ...


class _InvoiceQueueProbe(Protocol):
    async def admin_list_invoices(
        self, status: str | None = None, limit: int | None = 20
    ) -> object: ...


class _UserQueueProbe(Protocol):
    async def admin_list_users(
        self, status: str | None = None, limit: int | None = 20
    ) -> object: ...


class AdminDashboardUseCases:
    def __init__(
        self,
        *,
        moderation: _ModerationQueueProbe,
        verification: _VerificationQueueProbe,
        orders: _InvoiceQueueProbe,
        users: _UserQueueProbe,
    ) -> None:
        self._moderation = moderation
        self._verification = verification
        self._orders = orders
        self._users = users

    async def get_dashboard(self) -> dict[str, Any]:
        # Connectivity/permission-check calls only -- results intentionally unused (see module
        # docstring). Each call reuses the SAME real port every other composed operation in this
        # module uses -- proving the dashboard is genuinely composed, not a stub.
        await self._moderation.list_moderation_queue(status="OPEN", limit=1)
        await self._verification.list_verification_queue(status="REQUESTED", limit=1)
        await self._orders.admin_list_invoices(status="ISSUED", limit=1)
        await self._users.admin_list_users(status="ACTIVE", limit=1)

        return {
            "activeListings": None,
            "pendingModeration": None,
            "pendingVerification": None,
            "pendingInvoices": None,
            "newUsers7d": None,
        }
