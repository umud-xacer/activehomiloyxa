"""Eventual-consistency proof for the P-20 fix documented in `docs/assessments/2026-07-24-acceptance/gap_report.md`'s
"Finding 5": `profiles.createBusinessProfile` produces a real `BusinessProfileCreated` event on
profiles' own outbox -> drained through identity's REAL `handle_profiles_event` (the SAME closure
`composition_root.make_profiles_notification_projection_handler`'s fourth route attaches in
production) -> `UserAccount.owned_profile_ids` gains the new profile -> a real session can then
`switchActingProfile` to it, where it previously would have raised `ProfileNotOwnedError` every
time (the confirmed integration defect the E2E critical-journey suite bridged around rather than
silently accepting).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backbone.outbox import OutboxWriter
from backbone.persistence import redis_url
from identity.application.account_use_cases import AccountUseCases
from identity.domain.session import Session
from identity.domain.user_account import UserAccount
from identity.domain.value_objects import PhoneNumber
from identity.infrastructure.event_projection import handle_profiles_event
from identity.infrastructure.persistence.base import IdentityBase
from identity.infrastructure.persistence.models import (
    OutboxEventRow as IdentityOutboxEventRow,
)
from identity.infrastructure.persistence.repository import SqlalchemyUserAccountRepository
from identity.infrastructure.security import Argon2PasswordHasherAdapter
from identity.infrastructure.session_store import RedisSessionRepository
from profiles.application.profile_use_cases import ProfileUseCases
from profiles.domain import ProfileType
from profiles.infrastructure.persistence.base import ProfilesBase
from profiles.infrastructure.persistence.models import (
    OutboxEventRow as ProfilesOutboxEventRow,
)
from profiles.infrastructure.persistence.repository import SqlalchemyBusinessProfileRepository
from shared_kernel import BusinessProfileId, EventEnvelope, LocalizedText, UserId
from tests.integration.conftest import ensure_clean_schema

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


@pytest_asyncio.fixture(autouse=True)
async def _identity_and_profiles_schemas(engine: AsyncEngine) -> None:
    await ensure_clean_schema(engine, "identity", IdentityBase)
    await ensure_clean_schema(engine, "profiles", ProfilesBase)


@pytest_asyncio.fixture
async def redis_client() -> Redis:
    client: Redis = Redis.from_url(redis_url())
    await client.flushdb()
    return client


class _UnusedMediaAssetReaderPort:
    async def get_media_asset(self, media_asset_id: object) -> None:
        raise AssertionError("not exercised -- this test creates a profile with no portfolio item")


def _account_use_cases(session: AsyncSession, redis_client: Redis) -> AccountUseCases:
    return AccountUseCases(
        accounts=SqlalchemyUserAccountRepository(session),
        sessions=RedisSessionRepository(redis_client),
        outbox=OutboxWriter(session, IdentityOutboxEventRow),
        password_hasher=Argon2PasswordHasherAdapter(),
    )


async def test_a_newly_created_business_profile_becomes_switchable_to(
    session_factory: async_sessionmaker[AsyncSession], redis_client: Redis
) -> None:
    owner_id = UserId(value=uuid4())
    account = UserAccount.register_via_phone(
        account_id=owner_id, phone=PhoneNumber("+998901234567"), now=NOW
    )

    async with session_factory() as session:
        await SqlalchemyUserAccountRepository(session).add(account)
        await session.commit()

    async with session_factory() as session:
        profile_use_cases = ProfileUseCases(
            profiles=SqlalchemyBusinessProfileRepository(session),
            media=_UnusedMediaAssetReaderPort(),
            outbox=OutboxWriter(session, ProfilesOutboxEventRow),
        )
        profile = await profile_use_cases.create_profile(
            owner_user_id=owner_id,
            profile_type=ProfileType.CONSTRUCTION_COMPANY,
            name=LocalizedText(uz_latn="Quality Builders"),
            description=None,
            contacts=None,
            address=None,
            now=NOW,
        )
        await session.commit()

    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(ProfilesOutboxEventRow).where(
                        ProfilesOutboxEventRow.event_type == "BusinessProfileCreated"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        envelope = EventEnvelope(
            event_id=rows[0].id,
            event_type=rows[0].event_type,
            occurred_at=rows[0].occurred_at,
            actor=rows[0].actor,
            aggregate_type=rows[0].aggregate_type,
            aggregate_id=rows[0].aggregate_id,
            aggregate_version=rows[0].aggregate_version,
            payload=rows[0].payload,
        )

    async with session_factory() as session, session.begin():
        await handle_profiles_event(
            session, envelope, use_cases=_account_use_cases(session, redis_client)
        )

    async with session_factory() as session:
        reloaded = await SqlalchemyUserAccountRepository(session).get_by_id(owner_id)
        assert reloaded is not None
        assert reloaded.owns_profile(profile.id)

    session_repo = RedisSessionRepository(redis_client)
    real_session = Session.issue(
        session_id=uuid4(),
        account_id=owner_id,
        token_hash="hash",
        ip_address="1.2.3.4",
        user_agent="pytest",
        now=NOW,
        expires_at=NOW,
    )
    await session_repo.save(real_session)

    async with session_factory() as session:
        use_cases = _account_use_cases(session, redis_client)
        updated = await use_cases.switch_acting_profile(
            owner_id, real_session.id, new_acting_profile_id=profile.id, now=NOW
        )

    assert updated.acting_profile_id == profile.id

    # Redelivery of the SAME BusinessProfileCreated event must not duplicate the entry (I-23-style
    # idempotency, proven here for identity's first-ever inbound event consumer).
    async with session_factory() as session, session.begin():
        await handle_profiles_event(
            session, envelope, use_cases=_account_use_cases(session, redis_client)
        )

    async with session_factory() as session:
        reloaded = await SqlalchemyUserAccountRepository(session).get_by_id(owner_id)
        assert reloaded is not None
        assert reloaded.owned_profile_ids.count(BusinessProfileId(value=profile.id.value)) == 1
