"""Integration tests: `SqlalchemyUserAccountRepository`/`SqlalchemyOtpChallengeRepository`
round-trips against real PostgreSQL, including the partial-unique constraints on phone/email
(P-05 prompt: "the documented uniqueness constraints") and the child-entity (authentication
method, role assignment) persistence."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from identity.domain import (
    AuthMethodType,
    EmailAddress,
    OtpChallenge,
    OtpPurpose,
    PhoneNumber,
    UserAccount,
)
from identity.infrastructure.persistence.repository import (
    SqlalchemyOtpChallengeRepository,
    SqlalchemyUserAccountRepository,
)
from shared_kernel import BusinessProfileId, UserId

NOW = datetime(2026, 7, 11, tzinfo=UTC)


async def test_add_and_get_by_id_round_trips(db_session: AsyncSession) -> None:
    repo = SqlalchemyUserAccountRepository(db_session)
    account = UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()), phone=PhoneNumber("+998901234567"), now=NOW
    )
    await repo.add(account)
    await db_session.flush()

    fetched = await repo.get_by_id(account.id)
    assert fetched is not None
    assert fetched.phone == account.phone
    assert fetched.authentication_method(AuthMethodType.PHONE_OTP).verified_at == NOW


async def test_get_by_phone_and_email(db_session: AsyncSession) -> None:
    repo = SqlalchemyUserAccountRepository(db_session)
    account = UserAccount.register_via_email(
        account_id=UserId(value=uuid4()),
        email=EmailAddress("test@example.com"),
        password_hash="hashed:x",
        display_name=None,
        now=NOW,
    )
    await repo.add(account)
    await db_session.flush()

    assert (await repo.get_by_email(EmailAddress("test@example.com"))) is not None
    assert (await repo.get_by_phone(PhoneNumber("+998901234567"))) is None


async def test_partial_unique_constraint_on_phone(db_session: AsyncSession) -> None:
    """P-05 prompt: partial unique on phone -- two ACTIVE accounts cannot share a phone."""
    repo = SqlalchemyUserAccountRepository(db_session)
    phone = PhoneNumber("+998901234567")
    await repo.add(
        UserAccount.register_via_phone(account_id=UserId(value=uuid4()), phone=phone, now=NOW)
    )

    with pytest.raises(IntegrityError):
        await repo.add(
            UserAccount.register_via_phone(account_id=UserId(value=uuid4()), phone=phone, now=NOW)
        )
    await db_session.rollback()  # required after a caught flush error before reusing the session


async def test_partial_unique_constraint_allows_multiple_null_phones_after_close(
    db_session: AsyncSession,
) -> None:
    """Anonymised (closed) accounts have `phone=NULL`; the partial index excludes NULL, so
    multiple closed accounts never collide."""
    repo = SqlalchemyUserAccountRepository(db_session)
    first = UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()), phone=PhoneNumber("+998901234567"), now=NOW
    ).close(now=NOW)
    second = UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()), phone=PhoneNumber("+998907654321"), now=NOW
    ).close(now=NOW)
    await repo.add(first)
    await repo.add(second)
    await db_session.flush()  # does not raise


async def test_save_updates_role_assignments_and_authentication_methods(
    db_session: AsyncSession,
) -> None:
    repo = SqlalchemyUserAccountRepository(db_session)
    account = UserAccount.register_via_phone(
        account_id=UserId(value=uuid4()), phone=PhoneNumber("+998901234567"), now=NOW
    )
    await repo.add(account)
    await db_session.flush()

    profile = BusinessProfileId(value=uuid4())
    updated = account.assign_role(
        role_definition_head_id=uuid4(),
        role_definition_version_id=uuid4(),
        role_code="administrator",
        acting_profile_id=profile,
        assigned_by=uuid4(),
        now=NOW,
    ).link_google_identity(google_subject="google-sub-1", now=NOW)
    await repo.save(updated)
    await db_session.flush()

    fetched = await repo.get_by_id(account.id)
    assert fetched is not None
    assert len(fetched.role_assignments) == 1
    assert fetched.role_assignments[0].role_code == "administrator"
    assert fetched.has_authentication_method(AuthMethodType.GOOGLE)


async def test_list_page_paginates_by_created_at(db_session: AsyncSession) -> None:
    repo = SqlalchemyUserAccountRepository(db_session)
    for i in range(3):
        await repo.add(
            UserAccount.register_via_phone(
                account_id=UserId(value=uuid4()),
                phone=PhoneNumber(f"+99890123456{i}"),
                now=NOW + timedelta(seconds=i),
            )
        )
    await db_session.flush()

    page_one, cursor = await repo.list_page(status=None, query=None, cursor=None, limit=2)
    assert len(page_one) == 2
    assert cursor is not None

    page_two, cursor_two = await repo.list_page(status=None, query=None, cursor=cursor, limit=2)
    assert len(page_two) == 1
    assert cursor_two is None


async def test_otp_challenge_round_trip_and_recent_counts(db_session: AsyncSession) -> None:
    repo = SqlalchemyOtpChallengeRepository(db_session)
    phone = PhoneNumber("+998901234567")
    challenge = OtpChallenge.issue(
        challenge_id=uuid4(),
        phone=phone,
        purpose=OtpPurpose.REGISTRATION,
        code_hash="hash",
        now=NOW,
        expiry_minutes=5,
    )
    await repo.add(challenge, ip_address="1.2.3.4")
    await db_session.flush()

    active = await repo.get_active_for_phone(phone, OtpPurpose.REGISTRATION)
    assert active is not None
    assert active.id == challenge.id

    count_phone = await repo.count_recent_requests_by_phone(phone, since=NOW - timedelta(minutes=1))
    assert count_phone == 1
    count_ip = await repo.count_recent_requests_by_ip("1.2.3.4", since=NOW - timedelta(minutes=1))
    assert count_ip == 1

    outcome = challenge.verify(candidate_code_hash="hash", now=NOW)
    await repo.save(outcome.challenge)
    await db_session.flush()

    assert await repo.get_active_for_phone(phone, OtpPurpose.REGISTRATION) is None
