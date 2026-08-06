"""The FastAPI dependency shape resolved by `interfaces/di.py::get_authenticated_request`
(Security Sec 4.2 Gates 1-2: authenticated, acting context resolved). The concrete resolution
logic -- reading the `ah_session` cookie or `Authorization: Bearer` header, hashing it, and
calling `ApplicationAuthorizationService.resolve_acting_context` -- lives at the composition root
(`no-infra-inbound-identity`, tools/importlinter.cfg, forbids this package from importing
`identity.infrastructure`)."""

from __future__ import annotations

from dataclasses import dataclass

from identity.domain import Session, UserAccount
from shared_kernel import UserId

SESSION_COOKIE_NAME = "ah_session"
"""Security Sec 3.2: Secure, HttpOnly, SameSite=Lax."""


@dataclass(frozen=True)
class AuthenticatedRequest:
    """Gates 1-2 already resolved: a valid, unexpired session and the account it belongs to.
    None of identity's own 15 Authentication/Users operations require a specific granted
    PermissionKey beyond this -- they are inherently scoped to the authenticated account's own
    resources (self-service). Gate 3/4 permission checks for *other* modules' resources go
    through the separate `AuthorizationPort`."""

    account: UserAccount
    session: Session


@dataclass(frozen=True)
class ActingOperator:
    """Backs the four `Administration`-tagged operations on identity's own resource
    (`adminListUsers`/`adminChangeUserStatus`/`assignRole`/`revokeRole`, ADR-0006) -- mirrors
    `billing.interfaces.auth.ActingOperator`/`ads.interfaces.auth.ActingOperator`'s own docstring
    exactly. Two DIFFERENT permission keys gate this router's four operations
    (`identity:account:manage_status` vs `identity:role:assign`), so `interfaces/di.py` declares
    two distinct DI targets rather than one, mirroring `analytics.interfaces.di`'s own
    `get_audit_acting_operator`/`get_reports_acting_operator` split."""

    account_id: UserId
