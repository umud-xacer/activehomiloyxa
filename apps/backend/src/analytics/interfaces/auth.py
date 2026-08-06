"""The FastAPI dependency shape resolved by `interfaces/di.py::get_acting_operator`. Mirrors
`ads.interfaces.auth.ActingOperator`'s own docstring exactly -- the concrete resolution logic
(reading the `ah_session` cookie, hashing it, calling identity's real `AuthorizationService`)
lives at the composition root, the one place allowed to see both modules' internals; analytics'
own source never imports identity.

Backs both operations this module owns (`queryAuditLog`, `getAdminReports`) -- by the time this
dependency resolves, the composition root has already run the real Gate-3 permission check
(`analytics:audit:read`/`analytics:reports:read`); the router itself never needs the operator's
account id beyond proving a permission check happened.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import UserId


@dataclass(frozen=True)
class ActingOperator:
    account_id: UserId
