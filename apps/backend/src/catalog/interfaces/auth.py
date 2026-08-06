"""The FastAPI dependency shape resolved by `interfaces/di.py::get_acting_user`/
`get_optional_acting_user` (Security Sec 4.2 Gates 1-2: authenticated, acting context resolved).
Mirrors `media.interfaces.auth.ActingUser`'s own docstring exactly -- the concrete resolution
logic (reading the `ah_session` cookie, hashing it, calling identity's `AuthorizationPort`) lives
at the composition root, the one place allowed to see both modules' internals; catalog's own
source never imports identity.

`acting_profile_id` carries `Session.acting_context` (`null` = personal context) -- `Listing.
create`'s `owner_profile_id` and `QuotaEnforcementService`'s scoping both come from this field,
never re-derived elsewhere."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import BusinessProfileId, UserId


@dataclass(frozen=True)
class ActingUser:
    account_id: UserId
    acting_profile_id: BusinessProfileId | None
