"""Unit tests for `AuthenticationUseCases` (FR-AUTH-001..006) against in-memory fakes
(`conftest.py`)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from identity.application import AuthenticationUseCases, InvalidGoogleCredentialError
from identity.application.exceptions import OtpChallengeNotFoundError, RecoveryTargetRequiredError
from identity.application.ports import GoogleIdentity
from identity.domain import (
    DuplicateContactError,
    EmailAddress,
    InvalidCredentialsError,
    OtpCodeMismatchError,
    OtpPurpose,
    OtpPurposeMismatchError,
    OtpThrottledError,
    PhoneNumber,
)

from .conftest import (
    FakeEmailProvider,
    FakeGoogleOAuthProvider,
    FakeOtpSmsProvider,
    FakeSessionRepository,
    FakeUserAccountRepository,
)

NOW = datetime(2026, 7, 11, tzinfo=UTC)
PHONE = PhoneNumber("+998901234567")


# --- FR-AUTH-001: phone OTP -------------------------------------------------------------------


async def test_request_otp_sends_code_via_sms_provider(
    auth_use_cases: AuthenticationUseCases, fake_otp_sms_provider: FakeOtpSmsProvider
) -> None:
    await auth_use_cases.request_otp(
        phone=PHONE, purpose=OtpPurpose.REGISTRATION, ip_address="1.2.3.4", now=NOW
    )
    assert len(fake_otp_sms_provider.sent) == 1
    assert fake_otp_sms_provider.sent[0][0] == PHONE


async def test_I_otp_throttle_request_otp_denies_after_limit(
    auth_use_cases: AuthenticationUseCases,
) -> None:
    """P-05 "dedicated ... throttle test" at the application/use-case level (NFR-SEC-004)."""
    for _ in range(3):
        await auth_use_cases.request_otp(
            phone=PHONE, purpose=OtpPurpose.REGISTRATION, ip_address="1.2.3.4", now=NOW
        )
    with pytest.raises(OtpThrottledError):
        await auth_use_cases.request_otp(
            phone=PHONE, purpose=OtpPurpose.REGISTRATION, ip_address="1.2.3.4", now=NOW
        )


async def test_verify_otp_registration_creates_new_account(
    auth_use_cases: AuthenticationUseCases, fake_otp_sms_provider: FakeOtpSmsProvider
) -> None:
    await auth_use_cases.request_otp(
        phone=PHONE, purpose=OtpPurpose.REGISTRATION, ip_address="1.2.3.4", now=NOW
    )
    code = fake_otp_sms_provider.sent[0][1]
    account, session, raw_token = await auth_use_cases.verify_otp(
        phone=PHONE,
        code=code,
        purpose=OtpPurpose.REGISTRATION,
        ip_address="1.2.3.4",
        user_agent="pytest",
        now=NOW,
    )
    assert account.phone == PHONE
    assert session.account_id == account.id
    assert raw_token


async def test_I_otp_single_use_verify_otp_rejects_second_attempt_with_same_code(
    auth_use_cases: AuthenticationUseCases, fake_otp_sms_provider: FakeOtpSmsProvider
) -> None:
    """P-05 "dedicated single-use-OTP test" at the application/use-case level."""
    await auth_use_cases.request_otp(
        phone=PHONE, purpose=OtpPurpose.REGISTRATION, ip_address="1.2.3.4", now=NOW
    )
    code = fake_otp_sms_provider.sent[0][1]
    await auth_use_cases.verify_otp(
        phone=PHONE,
        code=code,
        purpose=OtpPurpose.REGISTRATION,
        ip_address="1.2.3.4",
        user_agent="pytest",
        now=NOW,
    )
    with pytest.raises(OtpChallengeNotFoundError):
        await auth_use_cases.verify_otp(
            phone=PHONE,
            code=code,
            purpose=OtpPurpose.REGISTRATION,
            ip_address="1.2.3.4",
            user_agent="pytest",
            now=NOW,
        )


async def test_verify_otp_wrong_code_raises_mismatch(
    auth_use_cases: AuthenticationUseCases,
) -> None:
    await auth_use_cases.request_otp(
        phone=PHONE, purpose=OtpPurpose.REGISTRATION, ip_address="1.2.3.4", now=NOW
    )
    with pytest.raises(OtpCodeMismatchError):
        await auth_use_cases.verify_otp(
            phone=PHONE,
            code="000000",
            purpose=OtpPurpose.REGISTRATION,
            ip_address="1.2.3.4",
            user_agent="pytest",
            now=NOW,
        )


async def test_verify_otp_no_active_challenge_raises_not_found(
    auth_use_cases: AuthenticationUseCases,
) -> None:
    with pytest.raises(OtpChallengeNotFoundError):
        await auth_use_cases.verify_otp(
            phone=PHONE,
            code="123456",
            purpose=OtpPurpose.LOGIN,
            ip_address="1.2.3.4",
            user_agent="pytest",
            now=NOW,
        )


async def test_verify_otp_registration_existing_phone_authenticates_existing_account(
    auth_use_cases: AuthenticationUseCases, fake_otp_sms_provider: FakeOtpSmsProvider
) -> None:
    await auth_use_cases.request_otp(
        phone=PHONE, purpose=OtpPurpose.REGISTRATION, ip_address="1.2.3.4", now=NOW
    )
    code = fake_otp_sms_provider.sent[0][1]
    first_account, _, _ = await auth_use_cases.verify_otp(
        phone=PHONE,
        code=code,
        purpose=OtpPurpose.REGISTRATION,
        ip_address="1.2.3.4",
        user_agent="pytest",
        now=NOW,
    )

    await auth_use_cases.request_otp(
        phone=PHONE, purpose=OtpPurpose.LOGIN, ip_address="1.2.3.4", now=NOW
    )
    code = fake_otp_sms_provider.sent[-1][1]
    second_account, _, _ = await auth_use_cases.verify_otp(
        phone=PHONE,
        code=code,
        purpose=OtpPurpose.LOGIN,
        ip_address="1.2.3.4",
        user_agent="pytest",
        now=NOW,
    )
    assert second_account.id == first_account.id


async def test_verify_otp_login_purpose_no_account_raises_purpose_mismatch(
    auth_use_cases: AuthenticationUseCases, fake_otp_sms_provider: FakeOtpSmsProvider
) -> None:
    await auth_use_cases.request_otp(
        phone=PHONE, purpose=OtpPurpose.LOGIN, ip_address="1.2.3.4", now=NOW
    )
    code = fake_otp_sms_provider.sent[0][1]
    with pytest.raises(OtpPurposeMismatchError):
        await auth_use_cases.verify_otp(
            phone=PHONE,
            code=code,
            purpose=OtpPurpose.LOGIN,
            ip_address="1.2.3.4",
            user_agent="pytest",
            now=NOW,
        )


# --- FR-AUTH-002: email + password --------------------------------------------------------------


async def test_register_email_creates_account(
    auth_use_cases: AuthenticationUseCases, fake_accounts: FakeUserAccountRepository
) -> None:
    await auth_use_cases.register_email(
        email=EmailAddress("test@example.com"), password="s3cret123", display_name="Test", now=NOW
    )
    account = await fake_accounts.get_by_email(EmailAddress("test@example.com"))
    assert account is not None


async def test_register_email_duplicate_raises(auth_use_cases: AuthenticationUseCases) -> None:
    email = EmailAddress("test@example.com")
    await auth_use_cases.register_email(
        email=email, password="s3cret123", display_name=None, now=NOW
    )
    with pytest.raises(DuplicateContactError):
        await auth_use_cases.register_email(
            email=email, password="other-secret", display_name=None, now=NOW
        )


async def test_login_email_success(auth_use_cases: AuthenticationUseCases) -> None:
    email = EmailAddress("test@example.com")
    await auth_use_cases.register_email(
        email=email, password="s3cret123", display_name=None, now=NOW
    )
    account, _session, raw_token = await auth_use_cases.login_email(
        email=email, password="s3cret123", ip_address="1.2.3.4", user_agent="pytest", now=NOW
    )
    assert account.email == email
    assert raw_token


async def test_login_email_wrong_password_raises_invalid_credentials(
    auth_use_cases: AuthenticationUseCases,
) -> None:
    email = EmailAddress("test@example.com")
    await auth_use_cases.register_email(
        email=email, password="s3cret123", display_name=None, now=NOW
    )
    with pytest.raises(InvalidCredentialsError):
        await auth_use_cases.login_email(
            email=email, password="wrong", ip_address="1.2.3.4", user_agent="pytest", now=NOW
        )


async def test_login_email_unknown_account_raises_invalid_credentials(
    auth_use_cases: AuthenticationUseCases,
) -> None:
    with pytest.raises(InvalidCredentialsError):
        await auth_use_cases.login_email(
            email=EmailAddress("nobody@example.com"),
            password="whatever",
            ip_address="1.2.3.4",
            user_agent="pytest",
            now=NOW,
        )


# --- FR-AUTH-003: Google federated -----------------------------------------------------------


async def test_login_google_creates_account_when_none_exists(
    auth_use_cases: AuthenticationUseCases, fake_google_provider: FakeGoogleOAuthProvider
) -> None:
    fake_google_provider.identity = GoogleIdentity(
        subject="google-sub-1", email="new@example.com", email_verified=True, display_name="New"
    )
    account, _session, _raw_token = await auth_use_cases.login_google(
        authorization_code="code",
        redirect_uri="https://app/callback",
        ip_address="1.2.3.4",
        user_agent="pytest",
        now=NOW,
    )
    assert account.email == EmailAddress("new@example.com")


async def test_login_google_links_existing_account_by_verified_email(
    auth_use_cases: AuthenticationUseCases,
    fake_accounts: FakeUserAccountRepository,
    fake_google_provider: FakeGoogleOAuthProvider,
) -> None:
    email = EmailAddress("test@example.com")
    await auth_use_cases.register_email(
        email=email, password="s3cret123", display_name=None, now=NOW
    )
    existing = await fake_accounts.get_by_email(email)
    assert existing is not None

    fake_google_provider.identity = GoogleIdentity(
        subject="google-sub-1", email="test@example.com", email_verified=True, display_name=None
    )
    account, _, _ = await auth_use_cases.login_google(
        authorization_code="code",
        redirect_uri="https://app/callback",
        ip_address="1.2.3.4",
        user_agent="pytest",
        now=NOW,
    )
    assert account.id == existing.id  # I-09: linked, not duplicated


async def test_login_google_unverified_email_raises(
    auth_use_cases: AuthenticationUseCases, fake_google_provider: FakeGoogleOAuthProvider
) -> None:
    fake_google_provider.identity = GoogleIdentity(
        subject="google-sub-1", email="new@example.com", email_verified=False, display_name=None
    )
    with pytest.raises(InvalidGoogleCredentialError):
        await auth_use_cases.login_google(
            authorization_code="code",
            redirect_uri="https://app/callback",
            ip_address="1.2.3.4",
            user_agent="pytest",
            now=NOW,
        )


# --- FR-AUTH-005: logout -------------------------------------------------------------------


async def test_logout_deletes_session(
    auth_use_cases: AuthenticationUseCases, fake_sessions: FakeSessionRepository
) -> None:
    email = EmailAddress("test@example.com")
    await auth_use_cases.register_email(
        email=email, password="s3cret123", display_name=None, now=NOW
    )
    _account, session, raw_token = await auth_use_cases.login_email(
        email=email, password="s3cret123", ip_address="1.2.3.4", user_agent="pytest", now=NOW
    )
    await auth_use_cases.logout(raw_token=raw_token, now=NOW)
    assert await fake_sessions.get_by_id(session.id) is None


async def test_logout_unknown_token_is_a_no_op(auth_use_cases: AuthenticationUseCases) -> None:
    await auth_use_cases.logout(raw_token="not-a-real-token", now=NOW)  # does not raise


# --- FR-AUTH-006: recovery -------------------------------------------------------------------


async def test_start_recovery_requires_phone_or_email(
    auth_use_cases: AuthenticationUseCases,
) -> None:
    with pytest.raises(RecoveryTargetRequiredError):
        await auth_use_cases.start_recovery(phone=None, email=None, ip_address="1.2.3.4", now=NOW)


async def test_start_recovery_by_phone_issues_otp(
    auth_use_cases: AuthenticationUseCases, fake_otp_sms_provider: FakeOtpSmsProvider
) -> None:
    await auth_use_cases.start_recovery(phone=PHONE, email=None, ip_address="1.2.3.4", now=NOW)
    assert len(fake_otp_sms_provider.sent) == 1


async def test_start_recovery_by_email_never_reveals_existence(
    auth_use_cases: AuthenticationUseCases, fake_email_provider: FakeEmailProvider
) -> None:
    """Contract: "Response does not reveal account existence" -- registered and unregistered
    emails both return normally (no exception either way)."""
    await auth_use_cases.start_recovery(
        phone=None, email=EmailAddress("nobody@example.com"), ip_address="1.2.3.4", now=NOW
    )  # does not raise, no notice sent (no matching account)
    assert fake_email_provider.recovery_notices == []

    registered_email = EmailAddress("test@example.com")
    await auth_use_cases.register_email(
        email=registered_email, password="s3cret123", display_name=None, now=NOW
    )
    await auth_use_cases.start_recovery(
        phone=None, email=registered_email, ip_address="1.2.3.4", now=NOW
    )
    assert fake_email_provider.recovery_notices == [registered_email]
