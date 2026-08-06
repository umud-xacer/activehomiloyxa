"""`profiles.application.VerificationUseCases` (Task P-11) -- exercised against the in-memory
fakes in `conftest.py`. Covers I-12 (paid-verification gate, learned exclusively from a locally
projected billing event -- never a synchronous billing read, since profiles has no static
dependency on billing), I-13 (badge issuance end-to-end through the use-case layer), reviewer
queue ordering (SLA), and the entitlement/media-status projections.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from profiles.application.exceptions import (
    NotProfileOwnerError,
    ProfileNotFoundError,
    VerificationCaseNotFoundError,
    VerificationNotEligibleError,
)
from profiles.application.ports import VerificationEligibilitySnapshot
from profiles.application.profile_use_cases import ProfileUseCases
from profiles.application.verification_use_cases import VerificationUseCases
from profiles.domain import BadgeStatus, BusinessProfile, CaseStatus, ProfileType
from shared_kernel import BusinessProfileId, LocalizedText, UserId

from .conftest import (
    FakeBusinessProfileRepository,
    FakeMediaAssetReaderPort,
    FakeOutbox,
    FakeVerificationCaseRepository,
    FakeVerificationEligibilityRepository,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _verification_use_cases(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> VerificationUseCases:
    return VerificationUseCases(
        profiles=fake_profiles,
        cases=fake_cases,
        eligibility=fake_eligibility,
        media=fake_media,
        outbox=fake_outbox,
    )


async def _create_profile(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    *,
    owner: UserId,
) -> BusinessProfile:
    use_cases = ProfileUseCases(profiles=fake_profiles, media=fake_media, outbox=fake_outbox)
    return await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.CONSTRUCTION_COMPANY,
        name=LocalizedText(uz_latn="CC"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )


def _grant_eligibility(
    fake_eligibility: FakeVerificationEligibilityRepository,
    *,
    profile_id: BusinessProfileId,
    entitlement_id: UUID,
    valid_until: datetime,
    activation_state: str = "ACTIVE",
) -> None:
    fake_eligibility.snapshots[entitlement_id] = VerificationEligibilitySnapshot(
        entitlement_id=entitlement_id,
        business_profile_id=profile_id,
        valid_from=NOW,
        valid_until=valid_until,
        activation_state=activation_state,  # type: ignore[arg-type]
        source_event_id=uuid4(),
    )


# --- I-12: paid-verification gate ---------------------------------------------------------------


async def test_I12_request_verification_refused_without_active_entitlement(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)

    with pytest.raises(VerificationNotEligibleError):
        await use_cases.request_verification(
            profile.id,
            owner_user_id=owner,
            entitlement_id=uuid4(),
            documents=[(media_asset_id, "license")],
            now=NOW,
        )


async def test_I12_request_verification_refused_with_expired_entitlement(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    entitlement_id = uuid4()
    _grant_eligibility(
        fake_eligibility,
        profile_id=profile.id,
        entitlement_id=entitlement_id,
        valid_until=NOW - timedelta(days=1),
    )
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)

    with pytest.raises(VerificationNotEligibleError):
        await use_cases.request_verification(
            profile.id,
            owner_user_id=owner,
            entitlement_id=entitlement_id,
            documents=[(media_asset_id, "license")],
            now=NOW,
        )


async def test_request_verification_succeeds_with_active_entitlement(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    entitlement_id = uuid4()
    _grant_eligibility(
        fake_eligibility,
        profile_id=profile.id,
        entitlement_id=entitlement_id,
        valid_until=NOW + timedelta(days=365),
    )
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)

    case = await use_cases.request_verification(
        profile.id,
        owner_user_id=owner,
        entitlement_id=entitlement_id,
        documents=[(media_asset_id, "license")],
        now=NOW,
    )
    assert case.status is CaseStatus.REQUESTED
    assert any(event.event_type == "VerificationRequested" for event in fake_outbox.events)


async def test_request_verification_refuses_non_owner(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )

    with pytest.raises(NotProfileOwnerError):
        await use_cases.request_verification(
            profile.id,
            owner_user_id=UserId(value=uuid4()),
            entitlement_id=uuid4(),
            documents=[(uuid4(), "license")],
            now=NOW,
        )


async def test_request_verification_profile_not_found(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    with pytest.raises(ProfileNotFoundError):
        await use_cases.request_verification(
            BusinessProfileId(value=uuid4()),
            owner_user_id=UserId(value=uuid4()),
            entitlement_id=uuid4(),
            documents=[(uuid4(), "license")],
            now=NOW,
        )


# --- I-13: full request -> decide -> badge flow through the use-case layer ---------------------


async def test_I13_decide_verification_approved_issues_badge_with_entitlement_validity(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    entitlement_id = uuid4()
    entitlement_valid_until = NOW + timedelta(days=365)
    _grant_eligibility(
        fake_eligibility,
        profile_id=profile.id,
        entitlement_id=entitlement_id,
        valid_until=entitlement_valid_until,
    )
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)
    case = await use_cases.request_verification(
        profile.id,
        owner_user_id=owner,
        entitlement_id=entitlement_id,
        documents=[(media_asset_id, "license")],
        now=NOW,
    )

    decided = await use_cases.decide_verification(
        case.id, reviewer_user_id=uuid4(), outcome=CaseStatus.APPROVED, reason=None, now=NOW
    )
    assert decided.status is CaseStatus.APPROVED

    reloaded_profile = await fake_profiles.get_by_id(profile.id)
    assert reloaded_profile is not None
    assert reloaded_profile.badge is not None
    assert reloaded_profile.badge.status is BadgeStatus.VALID
    assert reloaded_profile.badge.valid_until == entitlement_valid_until
    assert any(event.event_type == "BusinessVerified" for event in fake_outbox.events)


async def test_decide_verification_rejected_never_touches_the_badge(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    entitlement_id = uuid4()
    _grant_eligibility(
        fake_eligibility,
        profile_id=profile.id,
        entitlement_id=entitlement_id,
        valid_until=NOW + timedelta(days=365),
    )
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)
    case = await use_cases.request_verification(
        profile.id,
        owner_user_id=owner,
        entitlement_id=entitlement_id,
        documents=[(media_asset_id, "license")],
        now=NOW,
    )

    decided = await use_cases.decide_verification(
        case.id, reviewer_user_id=uuid4(), outcome=CaseStatus.REJECTED, reason="bad docs", now=NOW
    )
    assert decided.status is CaseStatus.REJECTED

    reloaded_profile = await fake_profiles.get_by_id(profile.id)
    assert reloaded_profile is not None
    assert reloaded_profile.badge is None
    assert any(event.event_type == "VerificationRejected" for event in fake_outbox.events)
    assert not any(event.event_type == "BusinessVerified" for event in fake_outbox.events)


async def test_decide_verification_case_not_found(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    with pytest.raises(VerificationCaseNotFoundError):
        await use_cases.decide_verification(
            uuid4(), reviewer_user_id=uuid4(), outcome=CaseStatus.APPROVED, reason=None, now=NOW
        )


# --- reviewer queue ordering (SLA) --------------------------------------------------------------


async def test_list_queue_orders_by_sla_due_at_ascending(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    owner = UserId(value=uuid4())

    for offset_hours in (48, 12, 72):
        profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
        entitlement_id = uuid4()
        _grant_eligibility(
            fake_eligibility,
            profile_id=profile.id,
            entitlement_id=entitlement_id,
            valid_until=NOW + timedelta(days=365),
        )
        media_asset_id = uuid4()
        fake_media.seed(media_asset_id)
        case = await use_cases.request_verification(
            profile.id,
            owner_user_id=owner,
            entitlement_id=entitlement_id,
            documents=[(media_asset_id, "license")],
            now=NOW,
        )
        fake_cases.cases[case.id] = replace(case, sla_due_at=NOW + timedelta(hours=offset_hours))

    queue, _ = await use_cases.list_queue(status=None, cursor=None, limit=10)
    due_ats = [case.sla_due_at for case in queue]
    assert due_ats == sorted(due_ats)


# --- entitlement projection idempotency (X-03) ---------------------------------------------------


async def test_apply_entitlement_projection_upserts_by_entitlement_id(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    profile_id = BusinessProfileId(value=uuid4())
    entitlement_id = uuid4()
    snapshot = VerificationEligibilitySnapshot(
        entitlement_id=entitlement_id,
        business_profile_id=profile_id,
        valid_from=NOW,
        valid_until=NOW + timedelta(days=365),
        activation_state="ACTIVE",
        source_event_id=uuid4(),
    )
    await use_cases.apply_entitlement_projection(snapshot)
    stored = await fake_eligibility.get_by_entitlement_id(entitlement_id)
    assert stored is not None
    assert stored.activation_state == "ACTIVE"

    expired_snapshot = VerificationEligibilitySnapshot(
        entitlement_id=entitlement_id,
        business_profile_id=profile_id,
        valid_from=NOW,
        valid_until=NOW + timedelta(days=365),
        activation_state="EXPIRED",
        source_event_id=uuid4(),
    )
    await use_cases.apply_entitlement_projection(expired_snapshot)
    stored_again = await fake_eligibility.get_by_entitlement_id(entitlement_id)
    assert stored_again is not None
    assert stored_again.activation_state == "EXPIRED"


# --- media asset-status projection (X-06) ---------------------------------------------------------


async def test_apply_document_media_rejection_removes_document(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    entitlement_id = uuid4()
    _grant_eligibility(
        fake_eligibility,
        profile_id=profile.id,
        entitlement_id=entitlement_id,
        valid_until=NOW + timedelta(days=365),
    )
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)
    case = await use_cases.request_verification(
        profile.id,
        owner_user_id=owner,
        entitlement_id=entitlement_id,
        documents=[(media_asset_id, "license")],
        now=NOW,
    )
    assert len(case.documents) == 1

    await use_cases.apply_document_media_rejection(media_asset_id, now=NOW)
    reloaded_case = await fake_cases.get_by_id(case.id)
    assert reloaded_case is not None
    assert len(reloaded_case.documents) == 0


async def test_apply_document_media_rejection_noop_when_no_case_holds_the_asset(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    await use_cases.apply_document_media_rejection(uuid4(), now=NOW)  # no-op, no error


# --- get_current_case ---------------------------------------------------------------------------


async def test_get_current_case_profile_not_found(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    with pytest.raises(ProfileNotFoundError):
        await use_cases.get_current_case(
            BusinessProfileId(value=uuid4()), owner_user_id=UserId(value=uuid4())
        )


async def test_get_current_case_refuses_non_owner(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    with pytest.raises(NotProfileOwnerError):
        await use_cases.get_current_case(profile.id, owner_user_id=UserId(value=uuid4()))


async def test_get_current_case_not_found_when_never_requested(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    with pytest.raises(VerificationCaseNotFoundError):
        await use_cases.get_current_case(profile.id, owner_user_id=owner)


# --- claim_case (reviewer "claim" capability) ---------------------------------------------------


async def test_claim_case_marks_in_review(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    entitlement_id = uuid4()
    _grant_eligibility(
        fake_eligibility,
        profile_id=profile.id,
        entitlement_id=entitlement_id,
        valid_until=NOW + timedelta(days=365),
    )
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)
    case = await use_cases.request_verification(
        profile.id,
        owner_user_id=owner,
        entitlement_id=entitlement_id,
        documents=[(media_asset_id, "license")],
        now=NOW,
    )

    claimed = await use_cases.claim_case(case.id, now=NOW)
    assert claimed.status is CaseStatus.IN_REVIEW


async def test_claim_case_not_found(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    with pytest.raises(VerificationCaseNotFoundError):
        await use_cases.claim_case(uuid4(), now=NOW)


# --- decide_verification's fail-closed defensive guards -----------------------------------------


async def test_decide_verification_approved_fails_closed_if_entitlement_projection_vanished(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    """Adversarial state: the entitlement projection that gated `request_verification` is no
    longer resolvable by the time a reviewer decides (should not happen given I-12's own
    precondition, but `decide_verification` must fail closed, not guess a validity period)."""
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    entitlement_id = uuid4()
    _grant_eligibility(
        fake_eligibility,
        profile_id=profile.id,
        entitlement_id=entitlement_id,
        valid_until=NOW + timedelta(days=365),
    )
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)
    case = await use_cases.request_verification(
        profile.id,
        owner_user_id=owner,
        entitlement_id=entitlement_id,
        documents=[(media_asset_id, "license")],
        now=NOW,
    )

    del fake_eligibility.snapshots[entitlement_id]

    with pytest.raises(VerificationNotEligibleError):
        await use_cases.decide_verification(
            case.id, reviewer_user_id=uuid4(), outcome=CaseStatus.APPROVED, reason=None, now=NOW
        )


async def test_decide_verification_approved_fails_closed_if_profile_vanished(
    fake_profiles: FakeBusinessProfileRepository,
    fake_cases: FakeVerificationCaseRepository,
    fake_eligibility: FakeVerificationEligibilityRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    owner = UserId(value=uuid4())
    profile = await _create_profile(fake_profiles, fake_media, fake_outbox, owner=owner)
    entitlement_id = uuid4()
    _grant_eligibility(
        fake_eligibility,
        profile_id=profile.id,
        entitlement_id=entitlement_id,
        valid_until=NOW + timedelta(days=365),
    )
    use_cases = _verification_use_cases(
        fake_profiles, fake_cases, fake_eligibility, fake_media, fake_outbox
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)
    case = await use_cases.request_verification(
        profile.id,
        owner_user_id=owner,
        entitlement_id=entitlement_id,
        documents=[(media_asset_id, "license")],
        now=NOW,
    )

    del fake_profiles.profiles[profile.id.value]

    with pytest.raises(ProfileNotFoundError):
        await use_cases.decide_verification(
            case.id, reviewer_user_id=uuid4(), outcome=CaseStatus.APPROVED, reason=None, now=NOW
        )
