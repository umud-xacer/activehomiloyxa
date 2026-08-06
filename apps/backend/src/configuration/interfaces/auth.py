"""P-04 STAND-IN pending identity's (BC-01) real session-based `AuthorizationService` -- that
module is not yet implemented (Task P-04 scope excludes implementing other modules). Reads
plain headers for testability; a later task must replace `get_acting_admin` with a real
session-cookie-backed dependency (`ah_session` -> Redis session -> permission keys) WITHOUT
changing any router signature above it (Playbook Sec 6: "use cases receive their ports, never
construct concrete adapters"; CLAUDE.md "Transport-only concerns ... are composition-root/
FastAPI-dependency concerns", the same pattern documented for `X-Acting-Profile`).

Not a business endpoint and not an operationId -- purely a FastAPI dependency wired into the
real `configuration` admin router.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from fastapi import Header


@dataclass(frozen=True)
class ActingAdmin:
    """The caller's identity + flattened permission-key set, as identity's real
    `AuthorizationService` will eventually resolve it from the session (Config Framework Sec
    2.3/Security Architecture's permission model) -- carried here as a plain header pair."""

    actor_id: UUID
    permission_keys: frozenset[str]


class PermissionDeniedError(PermissionError):
    """The caller's `ActingAdmin.permission_keys` does not include the permission key the
    requested operation requires (Security Architecture's authz model; Config Framework Sec 2.1
    "permission keys ... resolved at request time")."""

    def __init__(self, permission_key: str) -> None:
        self.permission_key = permission_key
        super().__init__(f"caller lacks the {permission_key!r} permission")


async def get_acting_admin(
    x_actor_id: UUID = Header(..., alias="X-Actor-Id"),
    x_permission_keys: str = Header("", alias="X-Permission-Keys"),
) -> ActingAdmin:
    """STAND-IN: a real session-backed dependency resolves both fields from `ah_session` /
    identity's RBAC composition, never from client-supplied headers -- headers are acceptable
    only because this module task builds no session store of its own."""
    keys = frozenset(key.strip() for key in x_permission_keys.split(",") if key.strip())
    return ActingAdmin(actor_id=x_actor_id, permission_keys=keys)


def require_permission(admin: ActingAdmin, permission_key: str) -> None:
    """Coarse-grained interfaces-layer gate: does the caller have any authority over this
    entity type at all. The finer-grained, workflow-specific checks (approver must hold the
    distinct approve-permission key, approver must be a different principal from the author)
    live in `application`/`domain` because they are core maker-checker invariants (Config
    Framework Sec 2.3), not generic RBAC."""
    if permission_key not in admin.permission_keys:
        raise PermissionDeniedError(permission_key)
