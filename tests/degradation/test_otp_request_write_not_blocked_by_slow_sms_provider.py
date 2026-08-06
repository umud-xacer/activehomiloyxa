"""P-21 fix regression proof: `AuthenticationUseCases.request_otp` no longer holds a Postgres
transaction open across the (real, network-bound, up-to-10s-timeout) Eskiz SMS call. Confirmed
bug (found by this task's own static audit, traced precisely): before this fix, `request_otp`
called `self._otp_challenges.add(challenge, ...)` and `self._otp_sms_provider.send_otp(...)` on
the SAME ambient session, committed only when the whole HTTP request's dependency scope closed --
so every `POST /auth/otp` held a connection idle for the entire SMS round-trip (Playbook Sec 6:
"a transaction is never held open across a provider port call"). Fixed via `OtpChallengeUnitOfWork`
(`identity/application/ports.py`) -- a dedicated, independently-committed transaction for the
throttle-check + persistence step, released before the SMS provider is ever called.

Proven here exactly like `tests/degradation/test_outbox_write_not_blocked_by_slow_consumer.py`
proves the analogous outbox case: a deliberately slow fake SMS provider blocks on an `asyncio.
Event`, and WHILE it is still blocked (the SMS call has not returned), a SEPARATE database
connection can already see the committed `OtpChallenge` row -- proof the write's own transaction
ended before the slow call began, not just that the overall method eventually completes.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from identity.application.auth_use_cases import AuthenticationUseCases
from identity.application.ports import IdentityPlatformSettings
from identity.domain import OtpPurpose, PhoneNumber
from identity.infrastructure.persistence.base import IdentityBase
from identity.infrastructure.persistence.models import (
    OtpChallengeRow,
)
from identity.infrastructure.persistence.models import (
    OutboxEventRow as IdentityOutboxEventRow,
)
from identity.infrastructure.persistence.repository import (
    SqlalchemyOtpChallengeRepository,
    SqlalchemyOtpChallengeUnitOfWork,
    SqlalchemyUserAccountRepository,
)
from identity.infrastructure.security import Argon2PasswordHasherAdapter
from tests.integration.conftest import ensure_clean_schema

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _identity_schema(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "identity", IdentityBase)


class _UnusedProvider:
    """`AuthenticationUseCases.sessions`/`google_provider`/`email_provider`/`session_token_
    generator` are constructed but never exercised by `request_otp` -- a fake that raises on ANY
    attribute access catches a future accidental dependency instead of silently succeeding."""

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"not exercised by this test: {name}")


class _FixedPlatformSettings:
    async def get_identity_settings(self) -> IdentityPlatformSettings:
        return IdentityPlatformSettings(otp_expiry_minutes=5, session_expiry_hours=720)


class _FixedOtpCodeGenerator:
    def generate_code(self) -> str:
        return "123456"

    def hash_code(self, code: str) -> str:
        return f"hash:{code}"


async def test_request_otp_commits_the_challenge_before_the_slow_sms_call_returns(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    sms_send_started = asyncio.Event()
    release_sms_send = asyncio.Event()

    class _SlowSmsProvider:
        async def send_otp(self, *, phone: PhoneNumber, code: str) -> None:
            sms_send_started.set()
            await release_sms_send.wait()

    async with session_factory() as session:
        use_cases = AuthenticationUseCases(
            accounts=SqlalchemyUserAccountRepository(session),
            sessions=_UnusedProvider(),  # type: ignore[arg-type]
            otp_challenges=SqlalchemyOtpChallengeRepository(session),
            otp_challenge_unit_of_work=SqlalchemyOtpChallengeUnitOfWork(session_factory),
            outbox=OutboxWriter(session, IdentityOutboxEventRow),
            otp_sms_provider=_SlowSmsProvider(),
            email_provider=_UnusedProvider(),  # type: ignore[arg-type]
            google_provider=_UnusedProvider(),  # type: ignore[arg-type]
            password_hasher=Argon2PasswordHasherAdapter(),
            otp_code_generator=_FixedOtpCodeGenerator(),
            session_token_generator=_UnusedProvider(),  # type: ignore[arg-type]
            platform_settings=_FixedPlatformSettings(),
        )

        request_task = asyncio.create_task(
            use_cases.request_otp(
                phone=PhoneNumber("+998901234567"),
                purpose=OtpPurpose.REGISTRATION,
                ip_address="1.2.3.4",
                now=NOW,
            )
        )

        await asyncio.wait_for(sms_send_started.wait(), timeout=5.0)

        # The SMS call is now blocked (has not returned) -- prove the challenge row is already
        # committed and visible from a SEPARATE connection, not still pending on some open
        # transaction the slow call happens to be holding.
        async with session_factory() as verification_session:
            rows = (
                (
                    await verification_session.execute(
                        select(OtpChallengeRow).where(OtpChallengeRow.phone == "+998901234567")
                    )
                )
                .scalars()
                .all()
            )
        assert len(rows) == 1, (
            "the OtpChallenge write must already be committed while the SMS call is still in "
            "flight -- if this is empty, the transaction is still open, exactly the P-21 bug"
        )

        release_sms_send.set()
        await asyncio.wait_for(request_task, timeout=5.0)
