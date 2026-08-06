"""The FastAPI dependency shape resolved by `interfaces/di.py::get_acting_user` (Security Sec
4.2 Gates 1-2: authenticated, acting context resolved). Mirrors `media.interfaces.auth.
ActingUser`'s own docstring exactly: messaging is purely per-user (no `BusinessProfileId` acting
context -- a `Conversation`'s `ParticipantPair` is always two personal `UserId`s, never a business
profile), so this carries only the resolved account id. The concrete resolution logic (reading
the `ah_session` cookie, hashing it, calling identity's `AuthorizationPort`) lives at the
composition root, the one place allowed to see both modules' internals; messaging's own source
never imports `identity.domain`/`identity.infrastructure` (only `identity.interfaces`, AIR-02)."""

from __future__ import annotations

from dataclasses import dataclass

from shared_kernel import UserId


@dataclass(frozen=True)
class ActingUser:
    account_id: UserId
