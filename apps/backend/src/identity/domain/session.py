"""identity -- the Session aggregate (DDD Sec 5.1: "Separate root: sessions churn at a different
rate and consistency need than accounts"). Server-side only (Security Sec 3.2): the token is an
opaque reference, hashed at rest (`token_hash`) -- never a JWT, no refresh-token mechanism
anywhere in this aggregate (SDR-01).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from identity.domain.exceptions import (
    ProfileNotOwnedError,
    SessionExpiredError,
    SessionRevokedError,
)
from shared_kernel import BusinessProfileId, UserId


@dataclass(frozen=True)
class Session:
    """DDD Sec 5.1 aggregate root `Session [P]`. `acting_context` (FR-USER-002) is
    `acting_profile_id=None` for the personal context, or a specific owned `BusinessProfileId`."""

    id: UUID
    account_id: UserId
    token_hash: str
    acting_profile_id: BusinessProfileId | None
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    @staticmethod
    def issue(
        *,
        session_id: UUID,
        account_id: UserId,
        token_hash: str,
        ip_address: str | None,
        user_agent: str | None,
        now: datetime,
        expires_at: datetime,
        acting_profile_id: BusinessProfileId | None = None,
    ) -> Session:
        """FR-AUTH-005: issued on any successful authentication, regardless of method. Starts in
        the personal acting context unless the caller specifies otherwise."""
        return Session(
            id=session_id,
            account_id=account_id,
            token_hash=token_hash,
            acting_profile_id=acting_profile_id,
            ip_address=ip_address,
            user_agent=user_agent,
            created_at=now,
            expires_at=expires_at,
        )

    def require_valid(self, *, now: datetime) -> None:
        """Security Sec 4.2 Gate 1 (authenticated): raises unless the session both resolves and
        has not expired or been revoked."""
        if self.revoked_at is not None:
            raise SessionRevokedError()
        if now >= self.expires_at:
            raise SessionExpiredError()

    def switch_acting_profile(
        self,
        *,
        new_acting_profile_id: BusinessProfileId | None,
        owned_profile_ids: tuple[BusinessProfileId, ...],
        now: datetime,
    ) -> Session:
        """FR-USER-002 `ProfileScopingPolicy`: a session may only act as a profile the account
        owns (`None` = personal context, always allowed). This is the mechanism gate-2 (Security
        Sec 4.2 "acting context resolved") is built on -- a session can never resolve an acting
        context the account does not own."""
        if new_acting_profile_id is not None and new_acting_profile_id not in owned_profile_ids:
            raise ProfileNotOwnedError(new_acting_profile_id.value)
        return replace(self, acting_profile_id=new_acting_profile_id)

    def revoke(self, *, now: datetime) -> Session:
        return replace(self, revoked_at=now)
