"""identity/application -- self-service account use cases (FR-USER-001..003, FR-USER-005,
FR-AUTH-005 device management). Every method takes the caller's own `account_id`/`session_id` --
authorization (session validity, ownership) is resolved by the router via
`ApplicationAuthorizationService` before any of these run; these methods trust their inputs the
same way `configuration.application.use_cases.ConfigurationUseCases` trusts its `actor_id`.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from contracts.events.identity import AccountClosed
from identity.application.exceptions import AccountNotFoundError, SessionNotFoundError
from identity.application.ports import PasswordHasherPort, SessionRepository, UserAccountRepository
from identity.domain import (
    AuthMethodType,
    DuplicateContactError,
    EmailAddress,
    InvalidCredentialsError,
    NotificationPreferences,
    PrivacySettings,
    Session,
    UserAccount,
)
from shared_kernel import BusinessProfileId, OutboxPort, UserId


class AccountUseCases:
    def __init__(
        self,
        *,
        accounts: UserAccountRepository,
        sessions: SessionRepository,
        outbox: OutboxPort,
        password_hasher: PasswordHasherPort,
    ) -> None:
        self._accounts = accounts
        self._sessions = sessions
        self._outbox = outbox
        self._password_hasher = password_hasher

    async def get_me(self, account_id: UserId) -> UserAccount:
        return await self._require_account(account_id)

    async def update_me(
        self,
        account_id: UserId,
        *,
        display_name: str | None,
        email: EmailAddress | None,
        now: datetime,
    ) -> UserAccount:
        """updateMe (FR-USER-001)."""
        account = await self._require_account(account_id)
        if email is not None and email != account.email:
            existing = await self._accounts.get_by_email(email)
            if existing is not None and existing.id != account.id:
                raise DuplicateContactError("email", email.value)
        updated = account.update_profile(display_name=display_name, email=email, now=now)
        await self._accounts.save(updated)
        return updated

    async def change_password(
        self,
        account_id: UserId,
        *,
        current_password: str,
        new_password: str,
        now: datetime,
    ) -> None:
        """changePassword. Security Sec 3.3: "password change ... trigger[s] bulk session
        revocation server-side" -- every session for this account is dropped, including the
        one making this request (the client must re-authenticate)."""
        account = await self._require_account(account_id)
        method = account.authentication_method(AuthMethodType.EMAIL)
        if method.password_hash is None or not self._password_hasher.verify_password(
            password=current_password, password_hash=method.password_hash
        ):
            raise InvalidCredentialsError()

        new_hash = self._password_hasher.hash_password(new_password)
        updated = account.change_password(new_password_hash=new_hash, now=now)
        await self._accounts.save(updated)
        await self._sessions.delete_all_for_account(account_id)

    async def update_preferences(
        self,
        account_id: UserId,
        *,
        privacy_settings: PrivacySettings | None,
        notification_preferences: NotificationPreferences | None,
        now: datetime,
    ) -> UserAccount:
        """updatePreferences (FR-USER-003, BRULE-13)."""
        account = await self._require_account(account_id)
        updated = account.update_preferences(
            privacy_settings=privacy_settings,
            notification_preferences=notification_preferences,
            now=now,
        )
        await self._accounts.save(updated)
        return updated

    async def close_account(self, account_id: UserId, *, now: datetime) -> None:
        """closeAccount (FR-USER-005): anonymise, revoke every session, publish `AccountClosed`."""
        account = await self._require_account(account_id)
        closed = account.close(now=now)
        await self._accounts.save(closed)
        await self._sessions.delete_all_for_account(account_id)
        event = AccountClosed(
            event_id=uuid4(),
            occurred_at=now,
            actor=account_id.value,
            aggregate_type="UserAccount",
            aggregate_id=account_id.value,
            payload={"accountId": str(account_id.value)},
        )
        await self._outbox.append(event)

    async def list_sessions(self, account_id: UserId) -> list[Session]:
        return await self._sessions.list_for_account(account_id)

    async def revoke_session(self, account_id: UserId, session_id: UUID) -> None:
        session = await self._require_own_session(account_id, session_id)
        await self._sessions.delete(session.id)

    async def link_owned_profile(
        self, account_id: UserId, *, profile_id: BusinessProfileId, now: datetime
    ) -> UserAccount:
        """The reaction driving `identity.infrastructure.event_projection.handle_profiles_event`
        (`profiles.BusinessProfileCreated` -> this account owning its new profile, P-20 fix)."""
        account = await self._require_account(account_id)
        updated = account.link_owned_profile(profile_id=profile_id, now=now)
        await self._accounts.save(updated)
        return updated

    async def switch_acting_profile(
        self,
        account_id: UserId,
        session_id: UUID,
        *,
        new_acting_profile_id: BusinessProfileId | None,
        now: datetime,
    ) -> Session:
        """switchActingProfile (FR-USER-002). `Session.switch_acting_profile` raises
        `ProfileNotOwnedError` if the account does not own the target profile."""
        account = await self._require_account(account_id)
        session = await self._require_own_session(account_id, session_id)
        updated = session.switch_acting_profile(
            new_acting_profile_id=new_acting_profile_id,
            owned_profile_ids=account.owned_profile_ids,
            now=now,
        )
        await self._sessions.save(updated)
        return updated

    async def _require_account(self, account_id: UserId) -> UserAccount:
        account = await self._accounts.get_by_id(account_id)
        if account is None:
            raise AccountNotFoundError(account_id.value)
        return account

    async def _require_own_session(self, account_id: UserId, session_id: UUID) -> Session:
        session = await self._sessions.get_by_id(session_id)
        if session is None or session.account_id != account_id:
            raise SessionNotFoundError(session_id)
        return session
