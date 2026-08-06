"""The FastAPI dependency shape resolved by `interfaces/di.py::get_acting_operator`. Mirrors
`billing.interfaces.auth.ActingOperator`'s own docstring exactly -- the concrete resolution logic
(reading the `ah_session` cookie, hashing it, calling identity's real `AuthorizationService`)
lives at the composition root, the one place allowed to see both modules' internals; ads' own
source never imports identity.

Backs every `/admin/campaigns*` operation -- by the time this dependency resolves, the
composition root has already run the real Gate-3 permission check (`ads:campaign:manage`); the
router only ever needs the operator's own account id (event `actor` fields)."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import UserId


@dataclass(frozen=True)
class ActingOperator:
    """The admin-facing acting identity (all seven `/admin/campaigns*` operations). `/banners/*`
    (public serving/engagement capture) needs no acting identity at all -- `security: []` in
    `contracts/openapi.yaml`."""

    account_id: UserId
