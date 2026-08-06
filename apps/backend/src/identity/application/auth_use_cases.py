"""identity/application -- authentication use cases (FR-AUTH-001..006). Mirrors
`configuration.application.use_cases.ConfigurationUseCases`'s shape: one class, constructed only
from the ports it needs plus `shared_kernel.OutboxPort`, never a concrete adapter. Appends
exactly one outbox event per `UserAccount` mutation that has a row in the DDD Sec 6 event
catalogue (`UserRegistered` here; `AccountSuspended`/`AccountClosed` live in
`admin_use_cases.py`/`account_use_cases.py`).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from uuid import uuid4

from contracts.events.identity import UserRegistered
from identity.application.exceptions import (
    InvalidGoogleCredentialError,
    OtpChallengeNotFoundError,
    RecoveryTargetRequiredError,
)
from identity.application.ports import (
    EmailProviderPort,
    GoogleOAuthProviderPort,
    OtpChallengeRepository,
    OtpChallengeUnitOfWork,
    OtpCodeGeneratorPort,
    OtpSmsProviderPort,
    PasswordHasherPort,
    PlatformSettingsReaderPort,
    SessionRepository,
    SessionTokenGeneratorPort,
    UserAccountRepository,
)
from identity.domain import (
    AccountKind,
    AuthMethodType,
    DuplicateContactError,
    EmailAddress,
    InvalidCredentialsError,
    OtpChallenge,
    OtpCodeMismatchError,
    OtpPurpose,
    OtpPurposeMismatchError,
    OtpThrottlePolicy,
    PhoneNumber,
    Session,
    SessionExpiryPolicy,
    UserAccount,
)
from shared_kernel import OutboxPort, UserId

logger = logging.getLogger(__name__)


class AuthenticationUseCases:
    def __init__(
        self,
        *,
        accounts: UserAccountRepository,
        sessions: SessionRepository,
        otp_challenges: OtpChallengeRepository,
        otp_challenge_unit_of_work: OtpChallengeUnitOfWork,
        outbox: OutboxPort,
        otp_sms_provider: OtpSmsProviderPort,
        email_provider: EmailProviderPort,
        google_provider: GoogleOAuthProviderPort,
        password_hasher: PasswordHasherPort,
        otp_code_generator: OtpCodeGeneratorPort,
        session_token_generator: SessionTokenGeneratorPort,
        platform_settings: PlatformSettingsReaderPort,
        otp_throttle_policy: OtpThrottlePolicy | None = None,
    ) -> None:
        self._accounts = accounts
        self._sessions = sessions
        self._otp_challenges = otp_challenges
        self._otp_challenge_unit_of_work = otp_challenge_unit_of_work
        self._outbox = outbox
        self._otp_sms_provider = otp_sms_provider
        self._email_provider = email_provider
        self._google_provider = google_provider
        self._password_hasher = password_hasher
        self._otp_code_generator = otp_code_generator
        self._session_token_generator = session_token_generator
        self._platform_settings = platform_settings
        self._otp_throttle_policy = otp_throttle_policy or OtpThrottlePolicy()

    # --- FR-AUTH-001: phone OTP ---------------------------------------------------------------

    async def request_otp(
        self, *, phone: PhoneNumber, purpose: OtpPurpose, ip_address: str, now: datetime
    ) -> None:
        """requestOtp. Always dispatches (never reveals registration status -- contract:
        "no content reveals whether the phone is registered").

        P-21 fix: the throttle-check + `OtpChallenge` persistence runs inside `self._otp_
        challenge_unit_of_work`'s OWN independently-committed transaction (a fresh session, not
        `AuthenticationUseCases`' ambient one) -- it commits and its connection is released BEFORE
        `send_otp` (a real, network-bound Eskiz call) ever runs, never while it's in flight."""
        settings = await self._platform_settings.get_identity_settings()
        code = self._otp_code_generator.generate_code()
        async with self._otp_challenge_unit_of_work.open() as otp_challenges:
            window_start = now - timedelta(minutes=self._otp_throttle_policy.window_minutes)
            recent_by_phone = await otp_challenges.count_recent_requests_by_phone(
                phone, since=window_start
            )
            recent_by_ip = await otp_challenges.count_recent_requests_by_ip(
                ip_address, since=window_start
            )
            self._otp_throttle_policy.check(
                recent_requests_by_phone=recent_by_phone, recent_requests_by_ip=recent_by_ip
            )
            challenge = OtpChallenge.issue(
                challenge_id=uuid4(),
                phone=phone,
                purpose=purpose,
                code_hash=self._otp_code_generator.hash_code(code),
                now=now,
                expiry_minutes=settings.otp_expiry_minutes,
            )
            await otp_challenges.add(challenge, ip_address=ip_address)
        await self._otp_sms_provider.send_otp(phone=phone, code=code)

    async def verify_otp(
        self,
        *,
        phone: PhoneNumber,
        code: str,
        purpose: OtpPurpose,
        ip_address: str | None,
        user_agent: str | None,
        now: datetime,
        account_kind: AccountKind = AccountKind.INDIVIDUAL,
        anketa: dict[str, object] | None = None,
    ) -> tuple[UserAccount, Session, str]:
        """verifyOtp. REGISTRATION: creates the account if none exists for this phone, otherwise
        authenticates the existing one (idempotent from the caller's perspective). LOGIN/RECOVERY
        against a phone with no account raises `OtpPurposeMismatchError` (FR-AUTH-004 requires an
        already-registered user). ADR-0007: `account_kind`/`anketa` only apply on the REGISTRATION
        branch -- ignored for an already-existing account (its role was fixed at its own
        signup)."""
        challenge = await self._otp_challenges.get_active_for_phone(phone, purpose)
        if challenge is None:
            raise OtpChallengeNotFoundError()

        candidate_hash = self._otp_code_generator.hash_code(code)
        outcome = challenge.verify(candidate_code_hash=candidate_hash, now=now)
        await self._otp_challenges.save(outcome.challenge)
        if not outcome.matched:
            raise OtpCodeMismatchError()

        account = await self._accounts.get_by_phone(phone)
        if account is None:
            if purpose is not OtpPurpose.REGISTRATION:
                raise OtpPurposeMismatchError()
            account_id = UserId(value=uuid4())
            account = UserAccount.register_via_phone(
                account_id=account_id,
                phone=phone,
                now=now,
                account_kind=account_kind,
                anketa=anketa,
            )
            await self._accounts.add(account)
            await self._publish_user_registered(account, now=now)
        else:
            account.require_active()

        session, raw_token = await self._issue_session(
            account=account, ip_address=ip_address, user_agent=user_agent, now=now
        )
        return account, session, raw_token

    # --- FR-AUTH-002: email + password ---------------------------------------------------------

    async def register_email(
        self,
        *,
        email: EmailAddress,
        password: str,
        display_name: str | None,
        now: datetime,
        account_kind: AccountKind = AccountKind.INDIVIDUAL,
        anketa: dict[str, object] | None = None,
    ) -> None:
        """registerEmail. Duplicate email -> `DuplicateContactError` (409, I-09). See
        identity/README.md "Known gaps" for why the account is ACTIVE immediately rather than
        pending a confirmation-link click. ADR-0007: `account_kind`/`anketa` are the role picked
        and questionnaire filled in the signup wizard's earlier steps."""
        if await self._accounts.get_by_email(email) is not None:
            raise DuplicateContactError("email", email.value)

        account_id = UserId(value=uuid4())
        password_hash = self._password_hasher.hash_password(password)
        account = UserAccount.register_via_email(
            account_id=account_id,
            email=email,
            password_hash=password_hash,
            display_name=display_name,
            now=now,
            account_kind=account_kind,
            anketa=anketa,
        )
        await self._accounts.add(account)
        await self._publish_user_registered(account, now=now)

        confirmation_token = self._session_token_generator.generate_token()
        try:
            await self._email_provider.send_email_confirmation(
                email=email, token=confirmation_token
            )
        except Exception:
            # The account is already ACTIVE at this point (see the docstring above) -- the
            # confirmation email is a courtesy notification, not a registration gate, so a
            # provider outage must not fail (or worse, half-fail) an already-committed signup.
            logger.warning("failed to send registration confirmation email", exc_info=True)

    async def login_email(
        self,
        *,
        email: EmailAddress,
        password: str,
        ip_address: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> tuple[UserAccount, Session, str]:
        """loginEmail. Generic `InvalidCredentialsError` (401) for both "no such account" and
        "wrong password" -- Security Sec 3.1 enumeration control."""
        account = await self._accounts.get_by_email(email)
        if account is None or not account.has_authentication_method(AuthMethodType.EMAIL):
            raise InvalidCredentialsError()

        method = account.authentication_method(AuthMethodType.EMAIL)
        if method.password_hash is None or not self._password_hasher.verify_password(
            password=password, password_hash=method.password_hash
        ):
            raise InvalidCredentialsError()

        account.require_active()
        session, raw_token = await self._issue_session(
            account=account, ip_address=ip_address, user_agent=user_agent, now=now
        )
        return account, session, raw_token

    # --- FR-AUTH-003: Google federated -----------------------------------------------------

    async def login_google(
        self,
        *,
        authorization_code: str,
        redirect_uri: str,
        ip_address: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> tuple[UserAccount, Session, str]:
        """loginGoogle. Links by verified email if an account already exists, otherwise creates
        one -- I-09: link, never duplicate."""
        identity = await self._google_provider.exchange_authorization_code(
            authorization_code=authorization_code, redirect_uri=redirect_uri
        )
        if not identity.email_verified:
            raise InvalidGoogleCredentialError()

        email = EmailAddress(identity.email)
        account = await self._accounts.get_by_email(email)
        if account is not None:
            account = account.link_google_identity(google_subject=identity.subject, now=now)
            account.require_active()
            await self._accounts.save(account)
        else:
            account_id = UserId(value=uuid4())
            account = UserAccount.register_via_google(
                account_id=account_id,
                email=email,
                google_subject=identity.subject,
                display_name=identity.display_name,
                now=now,
            )
            await self._accounts.add(account)
            await self._publish_user_registered(account, now=now)

        session, raw_token = await self._issue_session(
            account=account, ip_address=ip_address, user_agent=user_agent, now=now
        )
        return account, session, raw_token

    # --- FR-AUTH-005: logout -------------------------------------------------------------------

    async def logout(self, *, raw_token: str, now: datetime) -> None:
        """FR-AUTH-005: "immediate global invalidation for that session" -- the Redis-backed
        `SessionRepository` deletes the key outright rather than persisting a revoked tombstone
        (`Session.revoke` still exists and is unit-tested as the domain concept; nothing here
        needs to read a revoked session back). Takes the raw token (not its hash): hashing stays
        entirely inside this use case, the one place that holds `SessionTokenGeneratorPort`."""
        token_hash = self._session_token_generator.hash_token(raw_token)
        session = await self._sessions.get_by_token_hash(token_hash)
        if session is None:
            return
        await self._sessions.delete(session.id)

    # --- FR-AUTH-006: recovery -------------------------------------------------------------------

    async def start_recovery(
        self,
        *,
        phone: PhoneNumber | None,
        email: EmailAddress | None,
        ip_address: str,
        now: datetime,
    ) -> None:
        """startRecovery. Response never reveals account existence either way. Phone recovery
        completes through the existing `requestOtp`/`verifyOtp(purpose=RECOVERY)` pair -- it is
        a real, contract-backed flow. Email recovery has no completion endpoint in
        contracts/openapi.yaml (see identity/README.md "Known gaps"): a notice is sent, best
        effort, with no token/link."""
        if phone is None and email is None:
            raise RecoveryTargetRequiredError()

        if phone is not None:
            await self.request_otp(
                phone=phone, purpose=OtpPurpose.RECOVERY, ip_address=ip_address, now=now
            )

        if email is not None:
            account = await self._accounts.get_by_email(email)
            if account is not None:
                await self._email_provider.send_recovery_notice(email=email)

    # --- shared helpers -------------------------------------------------------------------

    async def _issue_session(
        self,
        *,
        account: UserAccount,
        ip_address: str | None,
        user_agent: str | None,
        now: datetime,
    ) -> tuple[Session, str]:
        settings = await self._platform_settings.get_identity_settings()
        raw_token = self._session_token_generator.generate_token()
        session = Session.issue(
            session_id=uuid4(),
            account_id=account.id,
            token_hash=self._session_token_generator.hash_token(raw_token),
            ip_address=ip_address,
            user_agent=user_agent,
            now=now,
            expires_at=SessionExpiryPolicy.compute_expiry(
                now=now, session_expiry_hours=settings.session_expiry_hours
            ),
        )
        await self._sessions.save(session)
        return session, raw_token

    async def _publish_user_registered(self, account: UserAccount, *, now: datetime) -> None:
        event = UserRegistered(
            event_id=uuid4(),
            occurred_at=now,
            actor=account.id.value,
            aggregate_type="UserAccount",
            aggregate_id=account.id.value,
            aggregate_version=1,
            payload={"accountId": str(account.id.value), "status": account.status.value},
        )
        await self._outbox.append(event)
