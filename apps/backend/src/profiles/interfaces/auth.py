"""The FastAPI dependency shapes resolved by `interfaces/di.py::get_acting_user`/
`get_acting_reviewer` (Security Sec 4.2 Gates 1-2/3). Mirrors `billing.interfaces.auth`'s own
docstring exactly -- the concrete resolution logic (reading the `ah_session` cookie, hashing it,
calling identity's `AuthorizationPort`) lives at the composition root, the one place allowed to
see both modules' internals; profiles' own source never imports identity beyond its `interfaces/`
package.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import BusinessProfileId, UserId


@dataclass(frozen=True)
class ActingUser:
    account_id: UserId
    acting_profile_id: BusinessProfileId | None


@dataclass(frozen=True)
class ActingReviewer:
    """Backs `listVerificationQueue`/`decideVerification` -- the one place a real Security Sec
    4.2 Gate-3 permission check (`profiles:verification:review`) runs, mirroring `billing.
    interfaces.auth.ActingOperator`'s own "the real check, not merely declared" precedent."""

    account_id: UserId


@dataclass(frozen=True)
class ActingProfileManager:
    """Backs `adminListBusinessProfiles`/`adminArchiveBusinessProfile` -- the owner-admin panel's
    direct company-management surface, gated by `profiles:profile:manage` (distinct from
    `ActingReviewer`'s `profiles:verification:review`)."""

    account_id: UserId
