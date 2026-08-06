"""`profiles.application.ProfileUseCases` (Task P-11) -- exercised against the in-memory fakes in
`conftest.py`. Covers profile CRUD, portfolio management, the moderation-invoked commands, and
the badge-expiry sweep.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from profiles.application.exceptions import (
    MediaAssetNotFoundError,
    NotProfileOwnerError,
    ProfileNotFoundError,
)
from profiles.application.profile_use_cases import ProfileUseCases
from profiles.domain import ApprovedVerificationProof, BadgeStatus, CaseStatus, ProfileType
from profiles.domain.exceptions import IllegalBadgeTransitionError
from profiles.domain.submitted_document import SubmittedDocument
from profiles.domain.verification_case import VerificationCase
from shared_kernel import BusinessProfileId, LocalizedText, UserId

from .conftest import FakeBusinessProfileRepository, FakeMediaAssetReaderPort, FakeOutbox

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _use_cases(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> ProfileUseCases:
    return ProfileUseCases(profiles=fake_profiles, media=fake_media, outbox=fake_outbox)


@pytest.mark.asyncio
async def test_create_profile_activates_immediately_and_publishes_event(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="Builder Co", ru="Билдер Ко"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    assert profile.status.value == "ACTIVE"
    assert len(fake_outbox.events) == 1
    assert fake_outbox.events[0].event_type == "BusinessProfileCreated"


@pytest.mark.asyncio
async def test_update_profile_refuses_non_owner(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    profile = await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.ARCHITECT,
        name=LocalizedText(uz_latn="A"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    with pytest.raises(NotProfileOwnerError):
        await use_cases.update_profile(
            profile.id,
            owner_user_id=UserId(value=uuid4()),
            name=LocalizedText(uz_latn="Renamed"),
            description=None,
            contacts=None,
            address=None,
            now=NOW,
        )


@pytest.mark.asyncio
async def test_get_profile_not_found(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    with pytest.raises(ProfileNotFoundError):
        await use_cases.get_profile(BusinessProfileId(value=uuid4()))


@pytest.mark.asyncio
async def test_add_portfolio_item_requires_owner_and_existing_media(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.SUPPLIER,
        name=LocalizedText(uz_latn="S"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    media_asset_id = uuid4()

    with pytest.raises(MediaAssetNotFoundError):
        await use_cases.add_portfolio_item(
            profile.id, owner_user_id=owner, media_asset_id=media_asset_id, caption=None, now=NOW
        )

    fake_media.seed(media_asset_id)
    updated = await use_cases.add_portfolio_item(
        profile.id, owner_user_id=owner, media_asset_id=media_asset_id, caption=None, now=NOW
    )
    assert len(updated.portfolio) == 1


@pytest.mark.asyncio
async def test_moderation_archive_profile_needs_no_ownership_check(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    profile = await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.CONTRACTOR,
        name=LocalizedText(uz_latn="C"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    archived = await use_cases.moderation_archive_profile(profile.id, now=NOW)
    assert archived.status.value == "ARCHIVED"


@pytest.mark.asyncio
async def test_moderation_revoke_badge_publishes_verified_badge_expired(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    profile = await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.INTERIOR_DESIGNER,
        name=LocalizedText(uz_latn="ID"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
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
    ).decide(outcome=CaseStatus.APPROVED, reason=None, reviewer_user_id=uuid4(), now=NOW)
    proof = ApprovedVerificationProof.from_case(case)
    badged = profile.issue_badge(proof=proof, valid_until=NOW + timedelta(days=365), now=NOW)
    await fake_profiles.save(badged)

    revoked = await use_cases.moderation_revoke_badge(profile.id, now=NOW)
    assert revoked.badge is not None
    assert revoked.badge.status is BadgeStatus.REVOKED
    assert any(event.event_type == "VerifiedBadgeExpired" for event in fake_outbox.events)


@pytest.mark.asyncio
async def test_moderation_revoke_badge_without_valid_badge_raises(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    profile = await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.MANUFACTURER,
        name=LocalizedText(uz_latn="M"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    with pytest.raises(IllegalBadgeTransitionError):
        await use_cases.moderation_revoke_badge(profile.id, now=NOW)


@pytest.mark.asyncio
async def test_sweep_expired_badges_expires_all_due_and_publishes_events(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    profile = await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.SERVICE_PROVIDER,
        name=LocalizedText(uz_latn="SP"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
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
    ).decide(outcome=CaseStatus.APPROVED, reason=None, reviewer_user_id=uuid4(), now=NOW)
    proof = ApprovedVerificationProof.from_case(case)
    badged = profile.issue_badge(proof=proof, valid_until=NOW - timedelta(days=1), now=NOW)
    await fake_profiles.save(badged)

    swept = await use_cases.sweep_expired_badges(now=NOW, batch_size=10)
    assert swept == 1
    reloaded = await fake_profiles.get_by_id(profile.id)
    assert reloaded is not None
    assert reloaded.badge is not None
    assert reloaded.badge.status is BadgeStatus.EXPIRED
    assert any(event.event_type == "VerifiedBadgeExpired" for event in fake_outbox.events)


# --- query surfaces ---------------------------------------------------------------------------


async def test_list_my_profiles_scopes_to_owner(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    other = UserId(value=uuid4())
    await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.ARCHITECT,
        name=LocalizedText(uz_latn="Mine"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    await use_cases.create_profile(
        owner_user_id=other,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="Not mine"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )

    mine, _ = await use_cases.list_my_profiles(owner, cursor=None, limit=10)
    assert len(mine) == 1
    assert mine[0].owner_user_id == owner


async def test_list_public_profiles_filters_by_type_and_verified_only(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.ARCHITECT,
        name=LocalizedText(uz_latn="Arch"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="Build"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )

    architects, _ = await use_cases.list_public_profiles(
        profile_type=ProfileType.ARCHITECT, verified_only=False, cursor=None, limit=10
    )
    assert len(architects) == 1
    assert architects[0].profile_type is ProfileType.ARCHITECT

    verified_only, _ = await use_cases.list_public_profiles(
        profile_type=None, verified_only=True, cursor=None, limit=10
    )
    assert verified_only == []


async def test_update_profile_persists_partial_changes(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.CONTRACTOR,
        name=LocalizedText(uz_latn="Old Name"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )

    updated = await use_cases.update_profile(
        profile.id,
        owner_user_id=owner,
        name=LocalizedText(uz_latn="New Name"),
        description=None,
        contacts=None,
        address="New Address",
        now=NOW,
    )
    assert updated.name.uz_latn == "New Name"
    assert updated.address == "New Address"


# --- media asset-status projection (X-06) -----------------------------------------------------


async def test_apply_portfolio_media_rejection_noop_when_no_profile_holds_the_asset(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    await use_cases.apply_portfolio_media_rejection(uuid4(), now=NOW)  # no-op, no error


async def test_apply_portfolio_media_rejection_removes_the_item(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.SUPPLIER,
        name=LocalizedText(uz_latn="S"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)
    profile = await use_cases.add_portfolio_item(
        profile.id, owner_user_id=owner, media_asset_id=media_asset_id, caption=None, now=NOW
    )
    assert len(profile.portfolio) == 1

    await use_cases.apply_portfolio_media_rejection(media_asset_id, now=NOW)
    reloaded = await fake_profiles.get_by_id(profile.id)
    assert reloaded is not None
    assert len(reloaded.portfolio) == 0
