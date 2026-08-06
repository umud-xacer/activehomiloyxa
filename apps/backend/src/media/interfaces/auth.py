"""The FastAPI dependency shape resolved by `interfaces/di.py::get_acting_user` (Security Sec
4.2 Gates 1-2: authenticated, acting context resolved -- media's three operations are all
session-authenticated per `contracts/openapi.yaml`'s global `security: [{sessionCookie: []}]`;
none of the three declares a `security: []` override). Media's own self-service ops need only
"who is the caller", never a granted PermissionKey (`deleteMedia`'s "ownership validated" is an
equality check against `MediaAsset.uploaded_by`, not an `AuthorizationPort` gate -- see
`media.application.exceptions.NotAssetOwnerError`), so this carries only the resolved account id,
never a full domain `UserAccount`/`Session` -- media may not import `identity.domain`
(`cross-module-media`, tools/importlinter.cfg).

The concrete resolution logic (reading the `ah_session` cookie, hashing it, calling identity's
`ApplicationAuthorizationService.resolve_acting_context`) lives at the composition root, exactly
as `identity.interfaces.auth.AuthenticatedRequest`'s own docstring describes for identity's own
routers -- `composition_root.py` sits outside every module's package tree and is exempt from
`tools/importlinter.cfg`'s module-boundary contracts; media's own source never imports identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import UserId


@dataclass(frozen=True)
class ActingUser:
    account_id: UserId
