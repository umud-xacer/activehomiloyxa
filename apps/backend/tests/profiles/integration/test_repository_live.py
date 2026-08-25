"""`SqlalchemyBusinessProfileRepository`/`SqlalchemyVerificationCaseRepository`/
`SqlalchemyVerificationEligibilityRepository` against real PostgreSQL: round-trips every field
(including the JSONB `LocalizedText`/badge sub-state), and proves I-13's full flow (request ->
approve -> badge issuance, then the negative guard) survives a real commit/reload cycle -- not
just the in-memory fakes `test_verification_use_cases.py` exercises.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from profiles.application.ports import VerificationEligibilitySnapshot
from profiles.domain import (
    ApprovedVerificationProof,
    BadgeStatus,
    BusinessProfile,
    CaseStatus,
    ProfileType,
    VerificationCase,
)
from profiles.domain.exceptions import BadgeNotIssuableWithoutApprovedCaseError
from profiles.domain.submitted_document import SubmittedDocument
from profiles.infrastructure.persistence.repository import (
    SqlalchemyBusinessProfileRepository,
    SqlalchemyVerificationCaseRepository,
    SqlalchemyVerificationEligibilityRepository,
)
from shared_kernel import BusinessProfileId, LocalizedText, UserId

NOW = datetime(2026, 7, 13, tzinfo=UTC)


async def test_business_profile_round_trips_localized_text_and_portfolio(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = UserId(value=uuid4())
    profile = (
        BusinessProfile.create(
            profile_id=BusinessProfileId(value=uuid4()),
            owner_user_id=owner,
            profile_type=ProfileType.ARCHITECT,
            name=LocalizedText(
                uz_latn="Arxitektor", uz_cyrl="Архитектор", ru="Архитектор", en="Architect"
            ),
            description=LocalizedText(uz_latn="Tavsif"),
            contacts={"phone": "+998901112233"},
            address="Tashkent, Chilanzar",
            slug="arxitektor-test",
            now=NOW,
        )
        .submit_for_review(now=NOW)
        .approve(now=NOW)
    )
    profile = profile.add_portfolio_item(
        item_id=uuid4(), media_asset_id=uuid4(), caption=None, now=NOW
    )

    async with session_factory() as session:
        repo = SqlalchemyBusinessProfileRepository(session)
        await repo.add(profile)
        await session.commit()

    async with session_factory() as session:
        repo = SqlalchemyBusinessProfileRepository(session)
        fetched = await repo.get_by_id(profile.id)
        assert fetched is not None
        assert fetched.name.uz_latn == "Arxitektor"
        assert fetched.name.ru == "Архитектор"
        assert fetched.contacts == {"phone": "+998901112233"}
        assert len(fetched.portfolio) == 1
        assert fetched.status is profile.status


async def test_I13_full_request_approve_badge_flow_survives_real_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    owner = UserId(value=uuid4())
    entitlement_id = uuid4()
    entitlement_valid_until = NOW + timedelta(days=365)

    async with session_factory() as session:
        profiles = SqlalchemyBusinessProfileRepository(session)
        eligibility = SqlalchemyVerificationEligibilityRepository(session)
        cases = SqlalchemyVerificationCaseRepository(session)

        profile = (
            BusinessProfile.create(
                profile_id=BusinessProfileId(value=uuid4()),
                owner_user_id=owner,
                profile_type=ProfileType.CONSTRUCTION_COMPANY,
                name=LocalizedText(uz_latn="QC"),
                description=None,
                contacts=None,
                address=None,
                slug="qc-test",
                now=NOW,
            )
            .submit_for_review(now=NOW)
            .approve(now=NOW)
        )
        await profiles.add(profile)

        await eligibility.upsert(
            VerificationEligibilitySnapshot(
                entitlement_id=entitlement_id,
                business_profile_id=profile.id,
                valid_from=NOW,
                valid_until=entitlement_valid_until,
                activation_state="ACTIVE",
                source_event_id=uuid4(),
            )
        )

        case = VerificationCase.create(
            case_id=uuid4(),
            business_profile_id=profile.id,
            entitlement_id=entitlement_id,
            documents=(
                SubmittedDocument(
                    id=uuid4(),
                    media_asset_id=uuid4(),
                    document_kind="business_license",
                    position=1,
                    created_at=NOW,
                ),
            ),
            sla_due_at=NOW + timedelta(hours=72),
            now=NOW,
        )
        await cases.add(case)
        await session.commit()

    async with session_factory() as session:
        cases = SqlalchemyVerificationCaseRepository(session)
        eligibility = SqlalchemyVerificationEligibilityRepository(session)
        profiles = SqlalchemyBusinessProfileRepository(session)

        fetched_case = await cases.get_by_id(case.id)
        assert fetched_case is not None
        decided = fetched_case.decide(
            outcome=CaseStatus.APPROVED, reason=None, reviewer_user_id=uuid4(), now=NOW
        )
        saved_case = await cases.save(decided)

        proof = ApprovedVerificationProof.from_case(saved_case)
        entitlement_snapshot = await eligibility.get_by_entitlement_id(proof.entitlement_id)
        assert entitlement_snapshot is not None

        fetched_profile = await profiles.get_by_id(profile.id)
        assert fetched_profile is not None
        badged = fetched_profile.issue_badge(
            proof=proof, valid_until=entitlement_snapshot.valid_until, now=NOW
        )
        await profiles.save(badged)
        await session.commit()

    async with session_factory() as session:
        profiles = SqlalchemyBusinessProfileRepository(session)
        reloaded = await profiles.get_by_id(profile.id)
        assert reloaded is not None
        assert reloaded.badge is not None
        assert reloaded.badge.status is BadgeStatus.VALID
        assert reloaded.badge.valid_until == entitlement_valid_until


async def test_I13_negative_direct_issue_badge_attempt_refused_after_reload(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Prove the negative half of I-13 against a case reloaded from a real database (not just an
    in-memory object): a REQUESTED case, hydrated fresh, still cannot produce an
    `ApprovedVerificationProof`."""
    owner = UserId(value=uuid4())
    async with session_factory() as session:
        profiles = SqlalchemyBusinessProfileRepository(session)
        cases = SqlalchemyVerificationCaseRepository(session)

        profile = (
            BusinessProfile.create(
                profile_id=BusinessProfileId(value=uuid4()),
                owner_user_id=owner,
                profile_type=ProfileType.BUILDER,
                name=LocalizedText(uz_latn="B"),
                description=None,
                contacts=None,
                address=None,
                slug="b-test",
                now=NOW,
            )
            .submit_for_review(now=NOW)
            .approve(now=NOW)
        )
        await profiles.add(profile)

        case = VerificationCase.create(
            case_id=uuid4(),
            business_profile_id=profile.id,
            entitlement_id=uuid4(),
            documents=(
                SubmittedDocument(
                    id=uuid4(),
                    media_asset_id=uuid4(),
                    document_kind="license",
                    position=1,
                    created_at=NOW,
                ),
            ),
            sla_due_at=NOW + timedelta(hours=72),
            now=NOW,
        )
        await cases.add(case)
        await session.commit()

    async with session_factory() as session:
        cases = SqlalchemyVerificationCaseRepository(session)
        reloaded_case = await cases.get_by_id(case.id)
        assert reloaded_case is not None
        assert reloaded_case.status is CaseStatus.REQUESTED

        with pytest.raises(BadgeNotIssuableWithoutApprovedCaseError):
            ApprovedVerificationProof.from_case(reloaded_case)
