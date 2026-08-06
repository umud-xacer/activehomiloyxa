"""Concrete adapters for identity's two PUBLIC in-process ports (`identity.interfaces.ports`):
`AuthorizationPort` (every other module's permission gate) and `ContactPolicyPort` (messaging's
phone-reveal check). Both are wired at the composition root and handed to whichever future
module's own DI needs them -- this file has no FastAPI/HTTP surface of its own.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from identity.application.authorization_service import ApplicationAuthorizationService
from identity.application.ports import SessionTokenGeneratorPort, UserAccountRepository
from shared_kernel import BusinessProfileId, UserId


class AuthorizationPortAdapter:
    """Implements `identity.interfaces.ports.AuthorizationPort`. Hashes the raw `session_token`
    another module received (from the cookie/Bearer header it forwarded) before delegating to
    `ApplicationAuthorizationService` -- the hashing pepper never leaves this layer."""

    def __init__(
        self,
        *,
        authorization_service: ApplicationAuthorizationService,
        token_generator: SessionTokenGeneratorPort,
    ) -> None:
        self._authorization_service = authorization_service
        self._token_generator = token_generator

    async def authorize(
        self,
        *,
        session_token: str,
        required_permission: str,
        owner_account_id: UserId | None = None,
        owner_profile_id: BusinessProfileId | None = None,
    ) -> UserId:
        token_hash = self._token_generator.hash_token(session_token)
        context = await self._authorization_service.authorize(
            token_hash=token_hash,
            required_permission=required_permission,
            now=datetime.now(UTC),
            owner_account_id=owner_account_id,
            owner_profile_id=owner_profile_id,
        )
        return context.account_id

    async def get_effective_permissions(self, *, session_token: str) -> frozenset[str]:
        token_hash = self._token_generator.hash_token(session_token)
        _account, _session, context = await self._authorization_service.resolve_acting_context(
            token_hash=token_hash, now=datetime.now(UTC)
        )
        return context.effective_permissions


class ContactPolicyPortAdapter:
    """Implements `identity.interfaces.ports.ContactPolicyPort`."""

    def __init__(self, accounts: UserAccountRepository) -> None:
        self._accounts = accounts

    async def get_phone_reveal_mode(
        self, account_id: UserId
    ) -> Literal["ALWAYS", "ON_REQUEST", "NEVER"]:
        account = await self._accounts.get_by_id(account_id)
        if account is None:
            return "NEVER"
        return account.privacy_settings.phone_reveal_mode.value

    async def reveal_phone(self, account_id: UserId) -> str | None:
        account = await self._accounts.get_by_id(account_id)
        if account is None or account.phone is None:
            return None
        if account.privacy_settings.phone_reveal_mode.value == "NEVER":
            return None
        return account.phone.value
