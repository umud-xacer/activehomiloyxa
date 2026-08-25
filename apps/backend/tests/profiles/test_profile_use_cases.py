"""`profiles.application.ProfileUseCases` (Task P-11) -- exercised against the in-memory fakes in
`conftest.py`. Covers profile CRUD, portfolio management, the moderation-invoked commands, and
the badge-expiry sweep.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from profiles.application.exceptions import (
    MediaAssetNotFoundError,
    NotProfileOwnerError,
    ProfileNotFoundError,
    ProfileNotPubliclyVisibleError,
    PromoVideoNotReadyError,
    PromoVideoNotVideoError,
    PromoVideoTooLongError,
)
from profiles.application.profile_use_cases import ProfileUseCases
from profiles.domain import (
    ApprovedVerificationProof,
    BadgeStatus,
    BusinessProfile,
    CaseStatus,
    ProfileType,
)
from profiles.domain.exceptions import IllegalBadgeTransitionError, PromoVideoNotFoundError
from profiles.domain.submitted_document import SubmittedDocument
from profiles.domain.value_objects import MainCategory
from profiles.domain.verification_case import VerificationCase
from shared_kernel import BusinessProfileId, LocalizedText, UserId

from .conftest import (
    FakeBusinessProfileRepository,
    FakeMediaAssetReaderPort,
    FakeOutbox,
    FakeSubscriptionEligibilityRepository,
)

NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


def _use_cases(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository | None = None,
) -> ProfileUseCases:
    return ProfileUseCases(
        profiles=fake_profiles,
        media=fake_media,
        outbox=fake_outbox,
        subscriptions=fake_subscriptions,
    )


async def _onboardable_profile(
    use_cases: ProfileUseCases,
    fake_media: FakeMediaAssetReaderPort,
    *,
    owner: UserId,
) -> BusinessProfileId:
    """Creates, brands, and portfolios a profile up to `complete_onboarding`'s own mandatory-field
    checklist -- mirrors `test_business_profile.py`'s `_onboardable_profile` at the domain layer,
    but driven through the use-case layer (owner checks, media-asset validation) instead."""
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="Onboard Co"),
        description=LocalizedText(uz_latn="Biz haqimizda"),
        contacts={"phones": ["+998901234567"]},
        address="Tashkent",
        now=NOW,
        main_category=MainCategory.FINANCE_MORTGAGE,
    )
    logo_id = uuid4()
    fake_media.seed(logo_id)
    await use_cases.update_branding(
        profile.id,
        owner_user_id=owner,
        logo_media_asset_id=logo_id,
        banner_media_asset_id=None,
        now=NOW,
    )
    portfolio_media_id = uuid4()
    fake_media.seed(portfolio_media_id)
    await use_cases.add_portfolio_item(
        profile.id, owner_user_id=owner, media_asset_id=portfolio_media_id, caption=None, now=NOW
    )
    return profile.id


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


async def test_apply_portfolio_media_rejection_is_idempotent_noop_on_a_stale_lookup(
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    """Docstring's own claim: "idempotent no-op otherwise". `get_by_portfolio_media_asset_id`'s
    real-repository query and this method's own `remove_portfolio_item_for_media_asset` call are
    not in the same transaction snapshot, so a lookup that finds a profile whose matching item was
    removed a moment later (concurrent redelivery) must not error -- reproduced here with a
    repository double whose lookup intentionally disagrees with the profile's own current
    portfolio, since the in-memory fake's own consistent-by-construction lookup can never produce
    this race naturally."""

    class _StaleLookupRepository(FakeBusinessProfileRepository):
        async def get_by_portfolio_media_asset_id(self, media_asset_id: UUID) -> BusinessProfile:
            return next(iter(self.profiles.values()))

    fake_profiles = _StaleLookupRepository()
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
    save_calls_before = len(fake_profiles.profiles)

    await use_cases.apply_portfolio_media_rejection(uuid4(), now=NOW)

    reloaded = await fake_profiles.get_by_id(profile.id)
    assert reloaded is not None
    assert reloaded.updated_at == profile.updated_at  # unchanged: save() was never reached
    assert len(fake_profiles.profiles) == save_calls_before


# --- get_public_profile_by_slug (ADR-0010) ------------------------------------------------------


async def test_get_public_profile_by_slug_404s_when_no_profile_has_that_slug(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    with pytest.raises(ProfileNotPubliclyVisibleError):
        await use_cases.get_public_profile_by_slug("no-such-slug", now=NOW)


async def test_get_public_profile_by_slug_404s_without_an_active_subscription(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    """No `subscriptions` repository wired -> `get_subscription_status` always reports "NONE"
    (never purchased) -> the profile is not publicly visible, matching ADR-0010's own "a visitor
    cannot distinguish 'never existed' from 'not currently entitled'" reasoning."""
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    profile = await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    with pytest.raises(ProfileNotPubliclyVisibleError):
        await use_cases.get_public_profile_by_slug(profile.slug, now=NOW)


async def test_get_public_profile_by_slug_succeeds_with_an_active_subscription(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository,
) -> None:
    from profiles.application.ports import SubscriptionEligibilitySnapshot

    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox, fake_subscriptions)
    profile = await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    await fake_subscriptions.upsert(
        SubscriptionEligibilitySnapshot(
            business_profile_id=profile.id,
            entitlement_id=uuid4(),
            valid_from=NOW,
            valid_until=NOW + timedelta(days=30),
            activation_state="ACTIVE",
            source_event_id=uuid4(),
        )
    )
    found = await use_cases.get_public_profile_by_slug(profile.slug, now=NOW)
    assert found.id == profile.id


# --- update_branding -----------------------------------------------------------------------------


async def test_update_branding_sets_logo_and_banner_after_validating_both_assets(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    logo_id, banner_id = uuid4(), uuid4()
    fake_media.seed(logo_id)
    fake_media.seed(banner_id)
    updated = await use_cases.update_branding(
        profile.id,
        owner_user_id=owner,
        logo_media_asset_id=logo_id,
        banner_media_asset_id=banner_id,
        now=NOW,
    )
    assert updated.logo_media_asset_id == logo_id
    assert updated.banner_media_asset_id == banner_id


async def test_update_branding_refuses_non_owner(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    profile = await use_cases.create_profile(
        owner_user_id=UserId(value=uuid4()),
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    with pytest.raises(NotProfileOwnerError):
        await use_cases.update_branding(
            profile.id,
            owner_user_id=UserId(value=uuid4()),
            logo_media_asset_id=None,
            banner_media_asset_id=None,
            now=NOW,
        )


async def test_update_branding_rejects_an_unknown_media_asset(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    with pytest.raises(MediaAssetNotFoundError):
        await use_cases.update_branding(
            profile.id,
            owner_user_id=owner,
            logo_media_asset_id=uuid4(),
            banner_media_asset_id=None,
            now=NOW,
        )


# --- complete_onboarding / trial (ADR-0010) -------------------------------------------------------


async def test_complete_onboarding_requires_a_real_subscriptions_repository(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    """A composition-root wiring bug (built without `subscriptions`) must fail loudly here, not as
    an `AttributeError` on `None.upsert(...)` a few lines down."""
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    with pytest.raises(RuntimeError, match="subscriptions"):
        await use_cases.complete_onboarding(
            BusinessProfileId(value=uuid4()), owner_user_id=UserId(value=uuid4()), now=NOW
        )


async def test_complete_onboarding_starts_the_trial_and_publishes_event(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox, fake_subscriptions)
    owner = UserId(value=uuid4())
    profile_id = await _onboardable_profile(use_cases, fake_media, owner=owner)

    completed = await use_cases.complete_onboarding(profile_id, owner_user_id=owner, now=NOW)
    assert completed.onboarding_completed_at == NOW
    assert completed.trial_ends_at is not None

    snapshot = await fake_subscriptions.get_for_profile(profile_id)
    assert snapshot is not None
    assert snapshot.activation_state == "ACTIVE"
    assert any(event.event_type == "TrialSubscriptionStarted" for event in fake_outbox.events)


async def test_complete_onboarding_refuses_non_owner(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox, fake_subscriptions)
    owner = UserId(value=uuid4())
    profile_id = await _onboardable_profile(use_cases, fake_media, owner=owner)
    with pytest.raises(NotProfileOwnerError):
        await use_cases.complete_onboarding(
            profile_id, owner_user_id=UserId(value=uuid4()), now=NOW
        )


# --- sweep_expired_trials (ADR-0010) ---------------------------------------------------------------


async def test_sweep_expired_trials_requires_a_real_subscriptions_repository(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    with pytest.raises(RuntimeError, match="subscriptions"):
        await use_cases.sweep_expired_trials(now=NOW, batch_size=10)


async def test_sweep_expired_trials_expires_due_trials_and_publishes_events(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox, fake_subscriptions)
    owner = UserId(value=uuid4())
    profile_id = await _onboardable_profile(use_cases, fake_media, owner=owner)
    completed = await use_cases.complete_onboarding(
        profile_id, owner_user_id=owner, now=NOW - timedelta(days=10)
    )
    assert completed.trial_ends_at is not None and completed.trial_ends_at < NOW

    swept = await use_cases.sweep_expired_trials(now=NOW, batch_size=10)
    assert swept == 1
    snapshot = await fake_subscriptions.get_for_profile(profile_id)
    assert snapshot is not None
    assert snapshot.activation_state == "EXPIRED"
    assert any(event.event_type == "TrialSubscriptionEnded" for event in fake_outbox.events)


async def test_sweep_expired_trials_raises_if_the_join_and_lookup_disagree(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository,
) -> None:
    """`list_trials_expiring`'s own real-repository join guarantees a subscriptions snapshot
    exists for every candidate it returns -- this defends against that guarantee itself being
    broken, which the fake can reproduce directly (a trial-ended profile with no snapshot ever
    upserted for it, since this fake's `list_trials_expiring` has no such join to enforce it)."""
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox, fake_subscriptions)
    owner = UserId(value=uuid4())
    profile_id = await _onboardable_profile(use_cases, fake_media, owner=owner)
    profile = await fake_profiles.get_by_id(profile_id)
    assert profile is not None
    from dataclasses import replace

    stale = replace(
        profile,
        onboarding_completed_at=NOW - timedelta(days=10),
        trial_starts_at=NOW - timedelta(days=10),
        trial_ends_at=NOW - timedelta(days=5),
    )
    await fake_profiles.save(stale)

    with pytest.raises(RuntimeError, match="disagree"):
        await use_cases.sweep_expired_trials(now=NOW, batch_size=10)


# --- promo video (landing-page promo-video business rule) ------------------------------------------


async def test_add_promo_video_happy_path(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id, content_type="video/mp4", duration_seconds=15.0)
    updated = await use_cases.add_promo_video(
        profile.id, owner_user_id=owner, media_asset_id=media_asset_id, now=NOW
    )
    assert updated.promo_video_media_asset_ids == (media_asset_id,)


async def test_add_promo_video_rejects_an_unknown_media_asset(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    with pytest.raises(MediaAssetNotFoundError):
        await use_cases.add_promo_video(
            profile.id, owner_user_id=owner, media_asset_id=uuid4(), now=NOW
        )


async def test_add_promo_video_rejects_a_not_yet_scanned_asset(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    media_asset_id = uuid4()
    fake_media.seed(
        media_asset_id, scan_status="PENDING", content_type="video/mp4", duration_seconds=15.0
    )
    with pytest.raises(PromoVideoNotReadyError):
        await use_cases.add_promo_video(
            profile.id, owner_user_id=owner, media_asset_id=media_asset_id, now=NOW
        )


async def test_add_promo_video_rejects_a_non_video_asset(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id, content_type="image/png")
    with pytest.raises(PromoVideoNotVideoError):
        await use_cases.add_promo_video(
            profile.id, owner_user_id=owner, media_asset_id=media_asset_id, now=NOW
        )


async def test_add_promo_video_rejects_a_too_long_video(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id, content_type="video/mp4", duration_seconds=45.0)
    with pytest.raises(PromoVideoTooLongError):
        await use_cases.add_promo_video(
            profile.id, owner_user_id=owner, media_asset_id=media_asset_id, now=NOW
        )


async def test_add_promo_video_fails_closed_on_an_unreadable_duration(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    """`duration_seconds=None` means "could not be determined", not "unlimited" -- must be
    rejected exactly like a too-long video, not treated as within the cap."""
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id, content_type="video/mp4", duration_seconds=None)
    with pytest.raises(PromoVideoTooLongError):
        await use_cases.add_promo_video(
            profile.id, owner_user_id=owner, media_asset_id=media_asset_id, now=NOW
        )


async def test_remove_promo_video_happy_path(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id, content_type="video/mp4", duration_seconds=15.0)
    profile = await use_cases.add_promo_video(
        profile.id, owner_user_id=owner, media_asset_id=media_asset_id, now=NOW
    )
    updated = await use_cases.remove_promo_video(
        profile.id, media_asset_id, owner_user_id=owner, now=NOW
    )
    assert updated.promo_video_media_asset_ids == ()


async def test_remove_promo_video_refuses_non_owner(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id, content_type="video/mp4", duration_seconds=15.0)
    profile = await use_cases.add_promo_video(
        profile.id, owner_user_id=owner, media_asset_id=media_asset_id, now=NOW
    )
    with pytest.raises(NotProfileOwnerError):
        await use_cases.remove_promo_video(
            profile.id, media_asset_id, owner_user_id=UserId(value=uuid4()), now=NOW
        )


async def test_remove_promo_video_raises_for_an_unattached_asset(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    owner = UserId(value=uuid4())
    profile = await use_cases.create_profile(
        owner_user_id=owner,
        profile_type=ProfileType.BUILDER,
        name=LocalizedText(uz_latn="B"),
        description=None,
        contacts=None,
        address=None,
        now=NOW,
    )
    with pytest.raises(PromoVideoNotFoundError):
        await use_cases.remove_promo_video(profile.id, uuid4(), owner_user_id=owner, now=NOW)


# --- subscription entitlement projection (Monetization task) --------------------------------------


async def test_apply_subscription_projection_requires_a_real_subscriptions_repository(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    from profiles.application.ports import SubscriptionEligibilitySnapshot

    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    with pytest.raises(RuntimeError, match="subscriptions"):
        await use_cases.apply_subscription_projection(
            SubscriptionEligibilitySnapshot(
                business_profile_id=BusinessProfileId(value=uuid4()),
                entitlement_id=uuid4(),
                valid_from=NOW,
                valid_until=NOW + timedelta(days=30),
                activation_state="ACTIVE",
                source_event_id=uuid4(),
            )
        )


async def test_apply_subscription_projection_upserts(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository,
) -> None:
    from profiles.application.ports import SubscriptionEligibilitySnapshot

    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox, fake_subscriptions)
    profile_id = BusinessProfileId(value=uuid4())
    await use_cases.apply_subscription_projection(
        SubscriptionEligibilitySnapshot(
            business_profile_id=profile_id,
            entitlement_id=uuid4(),
            valid_from=NOW,
            valid_until=NOW + timedelta(days=30),
            activation_state="ACTIVE",
            source_event_id=uuid4(),
        )
    )
    snapshot = await fake_subscriptions.get_for_profile(profile_id)
    assert snapshot is not None
    assert snapshot.activation_state == "ACTIVE"


# --- get_subscription_status -----------------------------------------------------------------------


async def test_get_subscription_status_is_none_without_a_subscriptions_repository(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox)
    status, valid_until = await use_cases.get_subscription_status(
        BusinessProfileId(value=uuid4()), now=NOW
    )
    assert status == "NONE"
    assert valid_until is None


async def test_get_subscription_status_is_none_with_no_snapshot(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository,
) -> None:
    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox, fake_subscriptions)
    status, valid_until = await use_cases.get_subscription_status(
        BusinessProfileId(value=uuid4()), now=NOW
    )
    assert status == "NONE"
    assert valid_until is None


async def test_get_subscription_status_is_active_within_the_validity_window(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository,
) -> None:
    from profiles.application.ports import SubscriptionEligibilitySnapshot

    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox, fake_subscriptions)
    profile_id = BusinessProfileId(value=uuid4())
    await fake_subscriptions.upsert(
        SubscriptionEligibilitySnapshot(
            business_profile_id=profile_id,
            entitlement_id=uuid4(),
            valid_from=NOW,
            valid_until=NOW + timedelta(days=30),
            activation_state="ACTIVE",
            source_event_id=uuid4(),
        )
    )
    status, valid_until = await use_cases.get_subscription_status(profile_id, now=NOW)
    assert status == "ACTIVE"
    assert valid_until == NOW + timedelta(days=30)


async def test_get_subscription_status_is_expired_past_the_validity_window(
    fake_profiles: FakeBusinessProfileRepository,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionEligibilityRepository,
) -> None:
    from profiles.application.ports import SubscriptionEligibilitySnapshot

    use_cases = _use_cases(fake_profiles, fake_media, fake_outbox, fake_subscriptions)
    profile_id = BusinessProfileId(value=uuid4())
    await fake_subscriptions.upsert(
        SubscriptionEligibilitySnapshot(
            business_profile_id=profile_id,
            entitlement_id=uuid4(),
            valid_from=NOW - timedelta(days=60),
            valid_until=NOW - timedelta(days=30),
            activation_state="ACTIVE",
            source_event_id=uuid4(),
        )
    )
    status, valid_until = await use_cases.get_subscription_status(profile_id, now=NOW)
    assert status == "EXPIRED"
    assert valid_until == NOW - timedelta(days=30)
