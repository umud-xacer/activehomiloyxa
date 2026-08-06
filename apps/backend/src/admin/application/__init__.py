"""admin/application -- exactly two use-case classes. `OperatorSessionUseCases` backs admin's
one owned datum (`OperatorSessionContext`). `AdminDashboardUseCases` backs `getAdminDashboard`,
the one HTTP operation that maps to no single owning aggregate (`contracts/README.md`'s tag-
routing rule) and so is genuinely admin's own to compose.

Every other `Administration`-tagged operation in `contracts/openapi.yaml` (moderation queue,
verification queue, invoices, users/roles, audit log/reports) is already implemented, tested, and
mounted on its OWNING module's own router (`moderation`/`profiles`/`billing`/`identity`/
`analytics` respectively) -- admin builds no wrapper/bridge use case for any of them, since doing
so would just be a second, unused implementation of a capability the owning module already
exposes end-to-end (Absolute Architecture Rule 4)."""

from __future__ import annotations

from admin.application.dashboard_use_cases import AdminDashboardUseCases
from admin.application.operator_session_use_cases import OperatorSessionUseCases
from admin.application.ports import OperatorSessionRepository

__all__ = [
    "AdminDashboardUseCases",
    "OperatorSessionRepository",
    "OperatorSessionUseCases",
]
