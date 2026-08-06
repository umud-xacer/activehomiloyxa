"""`catalog.application.ListingUseCases` (Task P-07) -- exercised against the in-memory fakes in
`conftest.py`. Covers I-04/I-06/I-07/I-08, BRULE-17 (duplicate-detection flag withholds public
visibility, not the state transition), expiry sweep idempotency, the media asset-status
projection, and the moderation-invoked unflag command.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from catalog.application.duplicate_detection_service import DuplicateDetectionService
from catalog.application.exceptions import (
    CategoryFormUnavailableError,
    CategoryNotFoundError,
    ListingMediaAssetNotFoundError,
    ListingNotFoundError,
    StaleListingVersionError,
)
from catalog.application.listing_use_cases import ListingUseCases
from catalog.application.ports import SubscriptionSnapshot
from catalog.application.quota_service import QuotaEnforcementService
from catalog.domain.exceptions import (
    AttributeValidationError,
    NotListingOwnerError,
    QuotaExceededError,
)
from catalog.domain.listing import Listing
from catalog.domain.value_objects import ImageStatus, ListingType
from shared_kernel import BusinessProfileId, ListingId, UserId

from .conftest import (
    FakeCategoryFormPort,
    FakeListingRepository,
    FakeMediaAssetReaderPort,
    FakeOutbox,
    FakePlatformSettingsReaderPort,
    FakeSubscriptionSnapshotRepository,
)

NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _use_cases(
    fake_listings: FakeListingRepository,
    fake_categories: FakeCategoryFormPort,
    fake_settings: FakePlatformSettingsReaderPort,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionSnapshotRepository,
) -> ListingUseCases:
    return ListingUseCases(
        listings=fake_listings,
        categories=fake_categories,
        settings=fake_settings,
        media=fake_media,
        outbox=fake_outbox,
        quota=QuotaEnforcementService(subscriptions=fake_subscriptions),
        duplicates=DuplicateDetectionService(listings=fake_listings),
    )


@pytest.fixture
def use_cases(
    fake_listings: FakeListingRepository,
    fake_categories: FakeCategoryFormPort,
    fake_settings: FakePlatformSettingsReaderPort,
    fake_media: FakeMediaAssetReaderPort,
    fake_outbox: FakeOutbox,
    fake_subscriptions: FakeSubscriptionSnapshotRepository,
) -> ListingUseCases:
    return _use_cases(
        fake_listings, fake_categories, fake_settings, fake_media, fake_outbox, fake_subscriptions
    )


async def test_create_listing_draft_does_not_publish(
    use_cases: ListingUseCases, fake_outbox: FakeOutbox
) -> None:
    owner = UserId(value=uuid4())
    listing = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="Nice apartment",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    assert listing.lifecycle_state.value == "DRAFT"
    event_types = [e.event_type for e in fake_outbox.events]
    assert event_types == ["ListingCreated", "ListingDraftSaved"]


async def test_create_listing_with_publish_true_publishes_and_sets_expiry(
    use_cases: ListingUseCases, fake_outbox: FakeOutbox
) -> None:
    owner = UserId(value=uuid4())
    listing = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="Nice apartment",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=True,
        now=NOW,
    )
    assert listing.lifecycle_state.value == "PUBLISHED"
    assert listing.expires_at == NOW + timedelta(days=30)
    assert [e.event_type for e in fake_outbox.events] == ["ListingCreated", "ListingPublished"]


async def test_create_listing_rejects_invalid_attributes(use_cases: ListingUseCases) -> None:
    with pytest.raises(AttributeValidationError):
        await use_cases.create_listing(
            owner_user_id=UserId(value=uuid4()),
            owner_profile_id=None,
            listing_type=ListingType.ADVERTISEMENT,
            category_id=uuid4(),
            title="Bad listing",
            description=None,
            attributes={"rooms": 99},
            price=None,
            location=None,
            image_media_asset_ids=None,
            publish=False,
            now=NOW,
        )


async def test_create_listing_unknown_category_raises(
    use_cases: ListingUseCases, fake_categories: FakeCategoryFormPort
) -> None:
    category_id = uuid4()
    fake_categories.category_status[category_id] = "RETIRED"
    with pytest.raises(CategoryNotFoundError):
        await use_cases.create_listing(
            owner_user_id=UserId(value=uuid4()),
            owner_profile_id=None,
            listing_type=ListingType.ADVERTISEMENT,
            category_id=category_id,
            title="x",
            description=None,
            attributes={"rooms": 2},
            price=None,
            location=None,
            image_media_asset_ids=None,
            publish=False,
            now=NOW,
        )


async def test_create_listing_no_bound_form_raises(
    use_cases: ListingUseCases, fake_categories: FakeCategoryFormPort
) -> None:
    fake_categories.form_binding_available = False
    with pytest.raises(CategoryFormUnavailableError):
        await use_cases.create_listing(
            owner_user_id=UserId(value=uuid4()),
            owner_profile_id=None,
            listing_type=ListingType.ADVERTISEMENT,
            category_id=uuid4(),
            title="x",
            description=None,
            attributes={"rooms": 2},
            price=None,
            location=None,
            image_media_asset_ids=None,
            publish=False,
            now=NOW,
        )


async def test_create_listing_attaches_verified_images(
    use_cases: ListingUseCases, fake_media: FakeMediaAssetReaderPort
) -> None:
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id, scan_status="PENDING")
    listing = await use_cases.create_listing(
        owner_user_id=UserId(value=uuid4()),
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=[media_asset_id],
        publish=False,
        now=NOW,
    )
    assert len(listing.images) == 1
    assert listing.images[0].media_asset_id == media_asset_id


async def test_create_listing_unknown_media_asset_raises(use_cases: ListingUseCases) -> None:
    with pytest.raises(ListingMediaAssetNotFoundError):
        await use_cases.create_listing(
            owner_user_id=UserId(value=uuid4()),
            owner_profile_id=None,
            listing_type=ListingType.ADVERTISEMENT,
            category_id=uuid4(),
            title="x",
            description=None,
            attributes={"rooms": 2},
            price=None,
            location=None,
            image_media_asset_ids=[uuid4()],
            publish=False,
            now=NOW,
        )


# --- I-08: quota enforced from the locally projected subscription snapshot -----------------------


async def test_I08_no_snapshot_means_unlimited(use_cases: ListingUseCases) -> None:
    owner_profile_id = BusinessProfileId(value=uuid4())
    listing = await use_cases.create_listing(
        owner_user_id=UserId(value=uuid4()),
        owner_profile_id=owner_profile_id,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    assert listing.lifecycle_state.value == "DRAFT"


async def test_I08_quota_exceeded_blocks_creation(
    use_cases: ListingUseCases, fake_subscriptions: FakeSubscriptionSnapshotRepository
) -> None:
    owner_profile_id = BusinessProfileId(value=uuid4())
    fake_subscriptions.snapshots[owner_profile_id.value] = SubscriptionSnapshot(
        owner_profile_id=owner_profile_id,
        entitlement_id=uuid4(),
        product_definition_id=None,
        quota_document={"max_active_listings": 0},
        valid_until=None,
        source_event_id=uuid4(),
    )
    with pytest.raises(QuotaExceededError):
        await use_cases.create_listing(
            owner_user_id=UserId(value=uuid4()),
            owner_profile_id=owner_profile_id,
            listing_type=ListingType.ADVERTISEMENT,
            category_id=uuid4(),
            title="x",
            description=None,
            attributes={"rooms": 2},
            price=None,
            location=None,
            image_media_asset_ids=None,
            publish=False,
            now=NOW,
        )


async def test_I08_personal_owner_is_never_quota_checked(use_cases: ListingUseCases) -> None:
    """`owner_profile_id=None` (personal context) is unlimited in v1 -- see
    `QuotaEnforcementService.check_can_create`'s own docstring."""
    listing = await use_cases.create_listing(
        owner_user_id=UserId(value=uuid4()),
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    assert listing.lifecycle_state.value == "DRAFT"


# --- BRULE-17/DEC-14: duplicate detection flags at creation, doesn't block publish --------------


async def test_duplicate_detection_flags_a_repeat_title_same_owner_category(
    use_cases: ListingUseCases, fake_outbox: FakeOutbox
) -> None:
    owner = UserId(value=uuid4())
    category_id = uuid4()
    first = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=category_id,
        title="Cozy studio",
        description=None,
        attributes={"rooms": 1},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    assert first.is_flagged is False

    dup = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=category_id,
        title="Cozy studio",
        description=None,
        attributes={"rooms": 1},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=True,
        now=NOW,
    )
    assert dup.is_flagged is True
    # BRULE-17: still transitions to PUBLISHED (the row is truthful); I-06 is what withholds it.
    assert dup.lifecycle_state.value == "PUBLISHED"
    assert dup.is_publicly_visible(now=NOW) is False
    assert "ListingFlagged" in [e.event_type for e in fake_outbox.events]


# --- edit / optimistic locking --------------------------------------------------------------------


async def test_edit_listing_rebinds_to_current_form_version(
    use_cases: ListingUseCases,
    fake_categories: FakeCategoryFormPort,
    fake_listings: FakeListingRepository,
) -> None:
    owner = UserId(value=uuid4())
    listing = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    original_version_id = listing.form_definition_version_id
    new_version_id = uuid4()
    fake_categories.form_definition_version_id = new_version_id

    edited = await use_cases.edit_listing(
        listing_id=listing.id,
        actor_user_id=owner,
        expected_lock_version=listing.lock_version,
        title="Updated",
        description=None,
        attributes=None,
        price=None,
        location=None,
        now=NOW,
    )
    assert edited.form_definition_version_id == new_version_id
    assert edited.form_definition_version_id != original_version_id


async def test_edit_listing_stale_lock_version_raises(use_cases: ListingUseCases) -> None:
    owner = UserId(value=uuid4())
    listing = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    with pytest.raises(StaleListingVersionError):
        await use_cases.edit_listing(
            listing_id=listing.id,
            actor_user_id=owner,
            expected_lock_version=listing.lock_version + 1,
            title="x",
            description=None,
            attributes=None,
            price=None,
            location=None,
            now=NOW,
        )


async def test_edit_listing_non_owner_raises(use_cases: ListingUseCases) -> None:
    owner = UserId(value=uuid4())
    other = UserId(value=uuid4())
    listing = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    with pytest.raises(NotListingOwnerError):
        await use_cases.edit_listing(
            listing_id=listing.id,
            actor_user_id=other,
            expected_lock_version=listing.lock_version,
            title="x",
            description=None,
            attributes=None,
            price=None,
            location=None,
            now=NOW,
        )


# --- status transitions ---------------------------------------------------------------------------


async def test_change_status_renew_extends_expiry(use_cases: ListingUseCases) -> None:
    owner = UserId(value=uuid4())
    listing = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=True,
        now=NOW,
    )
    renewed = await use_cases.change_status(
        listing_id=listing.id,
        actor_user_id=owner,
        action="RENEW",
        reason=None,
        now=NOW,
    )
    assert renewed.expires_at == NOW + timedelta(days=30)


async def test_change_status_delete_transitions_to_deleted(use_cases: ListingUseCases) -> None:
    owner = UserId(value=uuid4())
    listing = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    await use_cases.delete_listing(listing_id=listing.id, actor_user_id=owner, now=NOW)
    reloaded = await use_cases.get_listing(listing.id)
    assert reloaded.lifecycle_state.value == "DELETED"


async def test_get_listing_not_found_raises(use_cases: ListingUseCases) -> None:
    with pytest.raises(ListingNotFoundError):
        await use_cases.get_listing(ListingId(value=uuid4()))


# --- expiry sweep worker path ----------------------------------------------------------------------


async def test_sweep_expired_publishes_exactly_once_across_two_polls(
    use_cases: ListingUseCases, fake_outbox: FakeOutbox
) -> None:
    owner = UserId(value=uuid4())
    await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=True,
        now=NOW,
    )
    future = NOW + timedelta(days=31)

    swept_first = await use_cases.sweep_expired(now=future, batch_size=10)
    swept_second = await use_cases.sweep_expired(now=future, batch_size=10)

    assert swept_first == 1
    assert swept_second == 0
    expired_events = [e for e in fake_outbox.events if e.event_type == "ListingExpired"]
    assert len(expired_events) == 1


# --- media asset-status projection (X-06) -----------------------------------------------------------


async def test_apply_media_status_projection_updates_attached_image(
    use_cases: ListingUseCases,
    fake_media: FakeMediaAssetReaderPort,
    fake_listings: FakeListingRepository,
) -> None:
    owner = UserId(value=uuid4())
    media_asset_id = uuid4()
    fake_media.seed(media_asset_id)
    listing = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=[media_asset_id],
        publish=False,
        now=NOW,
    )
    await use_cases.apply_media_status_projection(
        media_asset_id=media_asset_id, status=ImageStatus.CLEAN, now=NOW
    )
    updated = await fake_listings.get_by_id(listing.id)
    assert updated is not None
    assert updated.images[0].status is ImageStatus.CLEAN


async def test_apply_media_status_projection_is_a_noop_for_unattached_asset(
    use_cases: ListingUseCases,
) -> None:
    await use_cases.apply_media_status_projection(
        media_asset_id=uuid4(), status=ImageStatus.CLEAN, now=NOW
    )  # must not raise


# --- moderation command port ------------------------------------------------------------------------


async def test_unflag_listing_clears_the_flag(use_cases: ListingUseCases) -> None:
    owner = UserId(value=uuid4())
    category_id = uuid4()
    first = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=category_id,
        title="Same title",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    dup = await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=category_id,
        title="Same title",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )
    assert dup.is_flagged is True
    unflagged = await use_cases.unflag_listing(listing_id=dup.id, reason="reviewed", now=NOW)
    assert unflagged.is_flagged is False
    assert first  # keep reference alive for readability


async def _create_draft(use_cases: ListingUseCases, *, owner: UserId) -> Listing:
    return await use_cases.create_listing(
        owner_user_id=owner,
        owner_profile_id=None,
        listing_type=ListingType.ADVERTISEMENT,
        category_id=uuid4(),
        title="x",
        description=None,
        attributes={"rooms": 2},
        price=None,
        location=None,
        image_media_asset_ids=None,
        publish=False,
        now=NOW,
    )


async def test_publish_listing_standalone_method(use_cases: ListingUseCases) -> None:
    owner = UserId(value=uuid4())
    draft = await _create_draft(use_cases, owner=owner)
    published = await use_cases.publish_listing(listing_id=draft.id, actor_user_id=owner, now=NOW)
    assert published.lifecycle_state.value == "PUBLISHED"


async def test_edit_listing_no_bound_form_raises(
    use_cases: ListingUseCases, fake_categories: FakeCategoryFormPort
) -> None:
    owner = UserId(value=uuid4())
    draft = await _create_draft(use_cases, owner=owner)
    fake_categories.form_binding_available = False
    with pytest.raises(CategoryFormUnavailableError):
        await use_cases.edit_listing(
            listing_id=draft.id,
            actor_user_id=owner,
            expected_lock_version=draft.lock_version,
            title="x",
            description=None,
            attributes=None,
            price=None,
            location=None,
            now=NOW,
        )


async def test_attach_reorder_list_and_detach_images_standalone(
    use_cases: ListingUseCases, fake_media: FakeMediaAssetReaderPort
) -> None:
    owner = UserId(value=uuid4())
    draft = await _create_draft(use_cases, owner=owner)
    first_id, second_id = uuid4(), uuid4()
    fake_media.seed(first_id)
    fake_media.seed(second_id)

    first_image = await use_cases.attach_image(
        listing_id=draft.id, actor_user_id=owner, media_asset_id=first_id, now=NOW
    )
    second_image = await use_cases.attach_image(
        listing_id=draft.id, actor_user_id=owner, media_asset_id=second_id, now=NOW
    )
    assert [i.position for i in (first_image, second_image)] == [1, 2]

    listed = await use_cases.list_images(draft.id)
    assert len(listed) == 2

    reordered = await use_cases.reorder_images(
        listing_id=draft.id,
        actor_user_id=owner,
        ordered_image_ids=(second_image.id, first_image.id),
        now=NOW,
    )
    assert [i.id for i in reordered] == [second_image.id, first_image.id]

    await use_cases.detach_image(
        listing_id=draft.id, actor_user_id=owner, image_id=second_image.id, now=NOW
    )
    remaining = await use_cases.list_images(draft.id)
    assert len(remaining) == 1


async def test_change_status_suspend_archive_restore(
    use_cases: ListingUseCases, fake_outbox: FakeOutbox
) -> None:
    owner = UserId(value=uuid4())
    draft = await _create_draft(use_cases, owner=owner)
    published = await use_cases.publish_listing(listing_id=draft.id, actor_user_id=owner, now=NOW)

    suspended = await use_cases.change_status(
        listing_id=published.id, actor_user_id=owner, action="SUSPEND", reason="pause", now=NOW
    )
    assert suspended.lifecycle_state.value == "SUSPENDED"

    archived = await use_cases.change_status(
        listing_id=suspended.id, actor_user_id=owner, action="ARCHIVE", reason=None, now=NOW
    )
    assert archived.lifecycle_state.value == "ARCHIVED"

    restored = await use_cases.change_status(
        listing_id=archived.id, actor_user_id=owner, action="RESTORE", reason=None, now=NOW
    )
    assert restored.lifecycle_state.value == "PUBLISHED"

    event_types = [e.event_type for e in fake_outbox.events]
    assert "ListingSuspended" in event_types
    assert "ListingArchived" in event_types
    assert event_types.count("ListingPublished") == 2  # first publish + restore


async def test_change_status_unsupported_action_raises(use_cases: ListingUseCases) -> None:
    owner = UserId(value=uuid4())
    draft = await _create_draft(use_cases, owner=owner)
    with pytest.raises(ValueError, match="unsupported changeListingStatus action"):
        await use_cases.change_status(
            listing_id=draft.id, actor_user_id=owner, action="BOGUS", reason=None, now=NOW
        )


async def test_UNF_015_record_view_emits_listing_viewed(
    use_cases: ListingUseCases, fake_outbox: FakeOutbox
) -> None:
    """FR-ADV-010/DDD Sec 5.3 ViewRecordingPolicy, wired per ADR-0005's own deferred step --
    the event schema was already frozen, only this producer call was outstanding. `composition_
    root.py`'s catalog outbox fanout already routes `ListingViewed` to analytics (Task P-15);
    nothing there needed to change."""
    owner = UserId(value=uuid4())
    listing = await _create_draft(use_cases, owner=owner)
    viewer = UserId(value=uuid4())

    await use_cases.record_view(listing.id, viewer_user_id=viewer, now=NOW)

    view_events = [e for e in fake_outbox.events if e.event_type == "ListingViewed"]
    assert len(view_events) == 1
    assert view_events[0].actor == viewer.value
    assert view_events[0].aggregate_id == listing.id.value
    assert view_events[0].payload == {
        "listingId": str(listing.id.value),
        "viewerUserId": str(viewer.value),
    }


async def test_UNF_015_record_view_allows_anonymous_viewer(
    use_cases: ListingUseCases, fake_outbox: FakeOutbox
) -> None:
    """Anonymous views are valid (ADR-0005's own payload note: "viewerUserId (nullable --
    anonymous views are valid)")."""
    owner = UserId(value=uuid4())
    listing = await _create_draft(use_cases, owner=owner)

    await use_cases.record_view(listing.id, viewer_user_id=None, now=NOW)

    view_events = [e for e in fake_outbox.events if e.event_type == "ListingViewed"]
    assert len(view_events) == 1
    assert view_events[0].actor is None
    assert view_events[0].payload["viewerUserId"] is None
