"""The FastAPI dependency shape resolved by `interfaces/di.py::get_acting_operator`. Mirrors
`ads.interfaces.auth.ActingOperator`'s own docstring exactly -- the concrete resolution logic
lives at the composition root; admin's own source never imports identity's internals.

Backs `getAdminDashboard` -- gated by the new `admin:dashboard:read` permission key (this
module's own, since the dashboard maps to no single owning aggregate and no existing module's
permission key fits)."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import UserId


@dataclass(frozen=True)
class ActingOperator:
    account_id: UserId
