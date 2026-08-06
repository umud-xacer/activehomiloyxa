"""identity/application -- resolves Security Sec 4.2 Gates 1-2 (authenticated, acting context
resolved) against the session/account repositories and configuration's flattened RoleDefinition
snapshots, then delegates Gates 3-4 to the pure `identity.domain.AuthorizationService`. This is
the concrete class `interfaces/di.py` wires behind the public `AuthorizationPort` -- every other
module's API layer, and the future cross-module authorization matrix (QG-08), is tested against
this exact resolution path.
"""

from __future__ import annotations

from datetime import datetime

from identity.application.exceptions import AccountNotFoundError, InvalidSessionTokenError
from identity.application.ports import (
    RoleDefinitionReaderPort,
    SessionRepository,
    UserAccountRepository,
)
from identity.domain import ActingContext, AuthorizationService, Session, UserAccount
from shared_kernel import BusinessProfileId, UserId


class ApplicationAuthorizationService:
    def __init__(
        self,
        *,
        session_repo: SessionRepository,
        account_repo: UserAccountRepository,
        role_reader: RoleDefinitionReaderPort,
    ) -> None:
        self._sessions = session_repo
        self._accounts = account_repo
        self._roles = role_reader
        self._domain_service = AuthorizationService()

    async def resolve_acting_context(
        self, *, token_hash: str, now: datetime
    ) -> tuple[UserAccount, Session, ActingContext]:
        """Gates 1-2. Raises `InvalidSessionTokenError` / a domain `SessionExpiredError` /
        `SessionRevokedError` / `AccountNotActiveError` on failure -- there is no path here that
        returns a context for an unresolved session."""
        session = await self._sessions.get_by_token_hash(token_hash)
        if session is None:
            raise InvalidSessionTokenError()
        session.require_valid(now=now)

        account = await self._accounts.get_by_id(session.account_id)
        if account is None:
            raise AccountNotFoundError(session.account_id.value)
        account.require_active()

        permissions = await self.effective_permissions(account, session.acting_profile_id)
        context = ActingContext(
            account_id=account.id,
            acting_profile_id=session.acting_profile_id,
            effective_permissions=permissions,
        )
        return account, session, context

    async def effective_permissions(
        self, account: UserAccount, acting_profile_id: BusinessProfileId | None
    ) -> frozenset[str]:
        """Config Framework Sec 7.2: unions the already-flattened `permission_keys` of every
        `RoleAssignment` in scope for `acting_profile_id` (I-10) -- never re-flattens, never
        walks a hierarchy (I-11)."""
        assignments = account.role_assignments_for_scope(acting_profile_id)
        permissions: set[str] = set()
        for assignment in assignments:
            keys = await self._roles.get_permission_keys(
                head_id=assignment.role_definition_head_id,
                version_id=assignment.role_definition_version_id,
            )
            permissions |= keys
        return frozenset(permissions)

    async def authorize(
        self,
        *,
        token_hash: str,
        required_permission: str,
        now: datetime,
        owner_account_id: UserId | None = None,
        owner_profile_id: BusinessProfileId | None = None,
    ) -> ActingContext:
        """The full four-gate check other modules call in-process through `AuthorizationPort`.
        Raises on denial (a domain `PermissionDeniedError`/`WrongActingProfileError`, or one of
        the Gate-1/2 exceptions above); returns the resolved `ActingContext` only on success."""
        _account, _session, context = await self.resolve_acting_context(
            token_hash=token_hash, now=now
        )
        self._domain_service.authorize(
            context,
            required_permission,
            owner_account_id=owner_account_id,
            owner_profile_id=owner_profile_id,
        )
        return context
