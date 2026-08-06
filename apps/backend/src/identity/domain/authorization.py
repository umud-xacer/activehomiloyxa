"""identity -- the AuthorizationService domain policy (Security Sec 4: "the platform's
highest-stakes security property"; I-10, I-11). This is the reference every later module's API
layer and the cross-module authorization matrix (QG-08) is tested against, so precision matters
more here than anywhere else in the module.

Deliberately pure and I/O-free: resolving *which* session/account/permission-set applies is an
application-layer/infrastructure concern (Redis session lookup, configuration RoleDefinition
lookup -- Security Sec 4.2 Gates 1-2). This module only implements Gates 3-4 -- the actual
allow/deny decision once the acting context and its flattened permission set are already known --
because that decision is exactly the part that must be provably deterministic and side-effect
free for the default-deny invariant to hold.
"""

from __future__ import annotations

from dataclasses import dataclass

from identity.domain.exceptions import PermissionDeniedError, WrongActingProfileError
from shared_kernel import BusinessProfileId, UserId


@dataclass(frozen=True)
class ActingContext:
    """The already-resolved acting identity for one authorization decision: which account, which
    profile it is acting as (`None` = personal context), and the flattened permission set for
    that exact scope (`UserAccount.role_assignments_for_scope(...)` unioned with each
    RoleDefinition's published `permission_keys` -- Config Framework Sec 7.2: identity consumes
    the flattened set as-is, it never re-flattens or walks a hierarchy itself)."""

    account_id: UserId
    acting_profile_id: BusinessProfileId | None
    effective_permissions: frozenset[str]


class AuthorizationService:
    """Security Sec 4.2's four-gate model. Gates 1 (authenticated) and 2 (acting context
    resolved) happen before an `ActingContext` can even be constructed -- an unresolvable session
    never reaches this service. This service enforces Gates 3 and 4 as one inseparable check:
    default-deny, with no code path that can allow a permission that was never explicitly
    granted (I-11), and no code path that can let a permission held in one acting profile leak
    into another (I-10)."""

    def authorize(
        self,
        context: ActingContext,
        required_permission: str,
        *,
        owner_account_id: UserId | None = None,
        owner_profile_id: BusinessProfileId | None = None,
    ) -> None:
        """Raises on denial; returns `None` on success. There is exactly one path to success --
        every other path raises. This is what makes default-deny structural rather than
        incidental: removing the single `if` that grants access does not need to happen for a
        new operation to be denied by default, because denial is every branch that is not that
        one `if`.

        Gate 3 (permission held): `required_permission` must be a member of
        `context.effective_permissions`, checked as plain set membership -- no runtime
        inheritance, no wildcard, no implicit escalation path exists in this method (I-11).

        Gate 4 (ownership/target scope, I-10): when the operation names an owning profile or
        account, the acting context must match it exactly. `owner_profile_id` not equal to
        `context.acting_profile_id` denies even if the account owns that other profile under a
        *different* acting context -- a permission granted while acting as profile A must not
        leak into profile B, or into the personal context, or vice versa.
        """
        if required_permission not in context.effective_permissions:
            raise PermissionDeniedError(required_permission)

        if owner_profile_id is not None and owner_profile_id != context.acting_profile_id:
            raise WrongActingProfileError(
                acting_profile_id=context.acting_profile_id.value
                if context.acting_profile_id
                else None,
                target_profile_id=owner_profile_id.value,
            )

        if (
            owner_account_id is not None
            and context.acting_profile_id is None
            and owner_account_id != context.account_id
        ):
            raise WrongActingProfileError(
                acting_profile_id=None,
                target_profile_id=None,
            )
