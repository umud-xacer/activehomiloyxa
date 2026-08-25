"""Domain-layer invariant tests for `catalog.domain.listing.Listing` (Task P-07). Named
`test_I<nn>_*` for every invariant DDD Sec 9 assigns to catalog, mirroring
`apps/backend/tests/media/test_media_asset.py`'s own `test_I20_*` convention.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from catalog.domain.exceptions import (
    DuplicateImagePositionError,
    IllegalListingStateTransitionError,
    ImageAttachmentNotFoundError,
    ImageLimitExceededError,
    ListingAlreadyFlaggedError,
    ListingNotFlaggedError,
)
from catalog.domain.listing import MAX_IMAGE_ATTACHMENTS, Listing
from catalog.domain.value_objects import ImageStatus, LifecycleState, ListingType, TransitionKind
from shared_kernel import ListingId, UserId

NOW = datetime(2026, 7, 11, 12, 0, tzinfo=UTC)


def _new_listing(**overrides: object) -> Listing:
    defaults: dict[str, object] = {
        "listing_id": ListingId(value=uuid4()),
        "record_id": uuid4(),
        "listing_type": ListingType.ADVERTISEMENT,
        "owner_user_id": UserId(value=uuid4()),
        "owner_profile_id": None,
        "category_id": uuid4(),
        "category_path": "/real-estate/apartments",
        "form_definition_id": uuid4(),
        "form_definition_version_id": uuid4(),
        "title": "Nice 2-room apartment",
        "description": None,
        "attributes": {"rooms": 2},
        "price": None,
        "location": None,
        "slug": "nice-2-room-apartment",
        "now": NOW,
    }
    defaults.update(overrides)
    return Listing.create(**defaults)  # type: ignore[arg-type]


# --- I-01: ownership/category fixed for life ----------------------------------------------------


def test_I01_owner_and_category_survive_every_transition_and_edit() -> None:
    listing = _new_listing()
    owner, profile, category = listing.owner_user_id, listing.owner_profile_id, listing.category_id

    published = listing.publish(
        record_id=uuid4(), actor_user_id=owner.value, expires_at=NOW + timedelta(days=30), now=NOW
    )
    edited = published.edit_content(
        record_id=uuid4(),
        actor_user_id=owner.value,
        now=NOW,
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="Updated title",
    )
    suspended = edited.suspend(record_id=uuid4(), actor_user_id=owner.value, reason=None, now=NOW)

    for state in (listing, published, edited, suspended):
        assert state.owner_user_id == owner
        assert state.owner_profile_id == profile
        assert state.category_id == category


def test_I01_no_method_accepts_owner_or_category_as_a_parameter() -> None:
    """I-01's "fixed for life" is enforced by the type itself having no method that could touch
    them, not by a runtime check -- this test documents/pins that structural guarantee."""
    import inspect

    for name, method in inspect.getmembers(Listing, predicate=inspect.isfunction):
        if name in ("create", "__init__", "__eq__", "__repr__"):
            continue
        params = set(inspect.signature(method).parameters)
        assert "owner_user_id" not in params, name
        assert "owner_profile_id" not in params, name
        assert "category_id" not in params, name


# --- I-04 / BRULE-06: at most 10 image attachments, quarantine auto-detaches --------------------


def test_I04_eleventh_image_attachment_is_refused() -> None:
    listing = _new_listing()
    for _ in range(MAX_IMAGE_ATTACHMENTS):
        listing = listing.attach_image(image_id=uuid4(), media_asset_id=uuid4(), now=NOW)
    assert len(listing.images) == MAX_IMAGE_ATTACHMENTS

    with pytest.raises(ImageLimitExceededError):
        listing.attach_image(image_id=uuid4(), media_asset_id=uuid4(), now=NOW)


def test_I04_quarantined_asset_is_auto_detached_not_merely_flagged() -> None:
    listing = _new_listing()
    media_asset_id = uuid4()
    listing = listing.attach_image(image_id=uuid4(), media_asset_id=media_asset_id, now=NOW)
    listing = listing.update_image_status(
        media_asset_id=media_asset_id, status=ImageStatus.QUARANTINED, now=NOW
    )
    assert listing.images == ()


def test_I04_clean_status_update_keeps_the_attachment() -> None:
    listing = _new_listing()
    media_asset_id = uuid4()
    listing = listing.attach_image(image_id=uuid4(), media_asset_id=media_asset_id, now=NOW)
    listing = listing.update_image_status(
        media_asset_id=media_asset_id, status=ImageStatus.CLEAN, now=NOW
    )
    assert len(listing.images) == 1
    assert listing.images[0].status is ImageStatus.CLEAN


def test_I04_detach_renumbers_remaining_positions() -> None:
    listing = _new_listing()
    ids = [uuid4() for _ in range(3)]
    for image_id in ids:
        listing = listing.attach_image(image_id=image_id, media_asset_id=uuid4(), now=NOW)
    listing = listing.detach_image(ids[0], now=NOW)
    assert [i.position for i in listing.images] == [1, 2]
    assert [i.id for i in listing.images] == ids[1:]


# --- I-05: only legal transitions; every transition recorded ------------------------------------


def test_I05_illegal_transition_raises_and_leaves_state_unchanged() -> None:
    listing = _new_listing()  # DRAFT
    with pytest.raises(IllegalListingStateTransitionError):
        listing.suspend(
            record_id=uuid4(), actor_user_id=listing.owner_user_id.value, reason=None, now=NOW
        )
    assert listing.lifecycle_state is LifecycleState.DRAFT


def test_I05_every_transition_method_appends_exactly_one_record() -> None:
    listing = _new_listing()
    assert [t.transition_kind for t in listing.transitions] == [TransitionKind.CREATE]

    listing = listing.publish(
        record_id=uuid4(), actor_user_id=listing.owner_user_id.value, expires_at=NOW, now=NOW
    )
    assert [t.transition_kind for t in listing.transitions] == [
        TransitionKind.CREATE,
        TransitionKind.PUBLISH,
    ]

    listing = listing.suspend(
        record_id=uuid4(), actor_user_id=listing.owner_user_id.value, reason="test", now=NOW
    )
    assert listing.transitions[-1].transition_kind is TransitionKind.SUSPEND
    assert listing.transitions[-1].from_state is LifecycleState.PUBLISHED
    assert listing.transitions[-1].to_state is LifecycleState.SUSPENDED


def test_I05_delete_is_terminal() -> None:
    listing = _new_listing().delete(
        record_id=uuid4(), actor_user_id=None, reason="owner request", now=NOW
    )
    assert listing.lifecycle_state is LifecycleState.DELETED
    with pytest.raises(IllegalListingStateTransitionError):
        listing.delete(record_id=uuid4(), actor_user_id=None, reason=None, now=NOW)


def test_I05_restore_republishes_from_suspended_or_archived() -> None:
    listing = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW
    )
    suspended = listing.suspend(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)
    restored = suspended.restore(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)
    assert restored.lifecycle_state is LifecycleState.PUBLISHED
    assert restored.transitions[-1].transition_kind is TransitionKind.RESTORE


# --- I-06: the single authoritative public-visibility rule ---------------------------------------


def test_I06_draft_is_never_publicly_visible() -> None:
    listing = _new_listing()
    assert listing.is_publicly_visible(now=NOW) is False


def test_I06_published_unflagged_unexpired_is_visible() -> None:
    listing = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW + timedelta(days=1), now=NOW
    )
    assert listing.is_publicly_visible(now=NOW) is True


def test_I06_flagged_published_listing_is_not_visible() -> None:
    """BRULE-17/DEC-14: a flagged listing is PUBLISHED but withheld -- realised as this one
    predicate, not a separate queued sub-state."""
    listing = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW + timedelta(days=1), now=NOW
    )
    listing = listing.flag(record_id=uuid4(), reason="duplicate-detection", now=NOW)
    assert listing.lifecycle_state is LifecycleState.PUBLISHED
    assert listing.is_publicly_visible(now=NOW) is False


def test_I06_expired_published_listing_is_not_visible() -> None:
    listing = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW - timedelta(seconds=1), now=NOW
    )
    assert listing.is_publicly_visible(now=NOW) is False


def test_I06_suspended_listing_is_not_visible() -> None:
    listing = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW + timedelta(days=1), now=NOW
    )
    listing = listing.suspend(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)
    assert listing.is_publicly_visible(now=NOW) is False


def test_I06_edited_state_is_visible_too() -> None:
    listing = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW + timedelta(days=1), now=NOW
    )
    listing = listing.edit_content(
        record_id=uuid4(),
        actor_user_id=uuid4(),
        now=NOW,
        form_definition_id=listing.form_definition_id,
        form_definition_version_id=listing.form_definition_version_id,
        title="Edited title",
    )
    assert listing.lifecycle_state is LifecycleState.EDITED
    assert listing.is_publicly_visible(now=NOW) is True


# --- I-07: bound FormDefinitionVersion frozen at creation, rebinds only on edit ------------------


def test_I07_form_binding_is_fixed_at_creation() -> None:
    listing = _new_listing()
    original_form_id = listing.form_definition_id
    original_version_id = listing.form_definition_version_id

    published = listing.publish(record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW)
    assert published.form_definition_id == original_form_id
    assert published.form_definition_version_id == original_version_id


def test_I07_edit_rebinds_to_the_version_application_resolves_as_current() -> None:
    listing = _new_listing()
    new_form_id, new_version_id = uuid4(), uuid4()
    edited = listing.edit_content(
        record_id=uuid4(),
        actor_user_id=uuid4(),
        now=NOW,
        form_definition_id=new_form_id,
        form_definition_version_id=new_version_id,
    )
    assert edited.form_definition_id == new_form_id
    assert edited.form_definition_version_id == new_version_id


# --- flagging (BRULE-17; moderation command port) -------------------------------------------------


def test_flag_twice_raises() -> None:
    listing = _new_listing().flag(record_id=uuid4(), reason="dup", now=NOW)
    with pytest.raises(ListingAlreadyFlaggedError):
        listing.flag(record_id=uuid4(), reason="dup", now=NOW)


def test_unflag_when_not_flagged_raises() -> None:
    listing = _new_listing()
    with pytest.raises(ListingNotFlaggedError):
        listing.unflag(record_id=uuid4(), reason=None, now=NOW)


def test_unflag_clears_the_flag_without_an_event_bearing_transition_kind() -> None:
    listing = _new_listing().flag(record_id=uuid4(), reason="dup", now=NOW)
    listing = listing.unflag(record_id=uuid4(), reason="reviewed, cleared", now=NOW)
    assert listing.is_flagged is False
    assert listing.transitions[-1].transition_kind is TransitionKind.UNFLAG


# --- expiry/renewal (FR-ADV-006/007): recorded transitions, not states, idempotent sweep --------


def test_expiry_and_renewal_never_change_lifecycle_state() -> None:
    listing = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW
    )
    expired = listing.record_expiry(record_id=uuid4(), now=NOW)
    assert expired.lifecycle_state is LifecycleState.PUBLISHED
    assert expired.transitions[-1].transition_kind is TransitionKind.EXPIRE
    assert expired.transitions[-1].from_state == expired.transitions[-1].to_state

    renewed = expired.renew(
        record_id=uuid4(), actor_user_id=uuid4(), new_expires_at=NOW + timedelta(days=30), now=NOW
    )
    assert renewed.lifecycle_state is LifecycleState.PUBLISHED
    assert renewed.expires_at == NOW + timedelta(days=30)
    assert renewed.transitions[-1].transition_kind is TransitionKind.RENEW


def test_record_expiry_is_idempotent_across_repeated_sweep_polls() -> None:
    listing = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW
    )
    once = listing.record_expiry(record_id=uuid4(), now=NOW)
    twice = once.record_expiry(record_id=uuid4(), now=NOW)
    assert len(once.transitions) == len(twice.transitions)
    assert once.transitions == twice.transitions


# --- archive ---------------------------------------------------------------------------------


def test_archive_from_published_and_suspended_both_succeed() -> None:
    published = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW
    )
    archived = published.archive(
        record_id=uuid4(), actor_user_id=uuid4(), reason="listing removed", now=NOW
    )
    assert archived.lifecycle_state is LifecycleState.ARCHIVED
    assert archived.transitions[-1].transition_kind is TransitionKind.ARCHIVE

    suspended = published.suspend(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)
    archived_from_suspended = suspended.archive(
        record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW
    )
    assert archived_from_suspended.lifecycle_state is LifecycleState.ARCHIVED


def test_archive_from_draft_raises() -> None:
    with pytest.raises(IllegalListingStateTransitionError):
        _new_listing().archive(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)


# --- mark as sold (2026-08-25) ---------------------------------------------------------------


def test_mark_sold_from_published_and_edited_both_succeed() -> None:
    published = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW
    )
    sold = published.mark_sold(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)
    assert sold.lifecycle_state is LifecycleState.SOLD
    assert sold.transitions[-1].transition_kind is TransitionKind.SELL
    assert sold.is_publicly_visible(now=NOW) is False

    edited = published.edit_content(
        record_id=uuid4(),
        actor_user_id=uuid4(),
        now=NOW,
        form_definition_id=uuid4(),
        form_definition_version_id=uuid4(),
        title="edited title",
    )
    sold_from_edited = edited.mark_sold(
        record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW
    )
    assert sold_from_edited.lifecycle_state is LifecycleState.SOLD


def test_mark_sold_from_draft_raises() -> None:
    with pytest.raises(IllegalListingStateTransitionError):
        _new_listing().mark_sold(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)


def test_mark_sold_twice_raises() -> None:
    sold = (
        _new_listing()
        .publish(record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW)
        .mark_sold(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)
    )
    with pytest.raises(IllegalListingStateTransitionError):
        sold.mark_sold(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)


def test_restore_from_sold_returns_to_published() -> None:
    sold = (
        _new_listing()
        .publish(record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW)
        .mark_sold(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)
    )
    restored = sold.restore(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)
    assert restored.lifecycle_state is LifecycleState.PUBLISHED
    assert restored.transitions[-1].transition_kind is TransitionKind.RESTORE


# --- images: reorder / detach / status update edge cases ------------------------------------------


def test_reorder_images_reassigns_positions_by_array_index() -> None:
    listing = _new_listing()
    ids = [uuid4() for _ in range(3)]
    for image_id in ids:
        listing = listing.attach_image(image_id=image_id, media_asset_id=uuid4(), now=NOW)

    reordered = listing.reorder_images((ids[2], ids[0], ids[1]), now=NOW)
    assert [i.id for i in reordered.images] == [ids[2], ids[0], ids[1]]
    assert [i.position for i in reordered.images] == [1, 2, 3]


def test_reorder_images_with_mismatched_id_set_raises() -> None:
    listing = _new_listing().attach_image(image_id=uuid4(), media_asset_id=uuid4(), now=NOW)
    with pytest.raises(DuplicateImagePositionError):
        listing.reorder_images((uuid4(),), now=NOW)


def test_detach_unknown_image_raises() -> None:
    listing = _new_listing()
    with pytest.raises(ImageAttachmentNotFoundError):
        listing.detach_image(uuid4(), now=NOW)


def test_update_image_status_is_a_noop_for_an_unattached_asset() -> None:
    listing = _new_listing()
    unchanged = listing.update_image_status(
        media_asset_id=uuid4(), status=ImageStatus.CLEAN, now=NOW
    )
    assert unchanged is listing


# --- remaining illegal-transition guards + promotion projection ---------------------------------


def test_publish_twice_raises() -> None:
    published = _new_listing().publish(
        record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW
    )
    with pytest.raises(IllegalListingStateTransitionError):
        published.publish(record_id=uuid4(), actor_user_id=uuid4(), expires_at=NOW, now=NOW)


def test_edit_content_on_deleted_raises() -> None:
    deleted = _new_listing().delete(record_id=uuid4(), actor_user_id=None, reason=None, now=NOW)
    with pytest.raises(IllegalListingStateTransitionError):
        deleted.edit_content(
            record_id=uuid4(),
            actor_user_id=uuid4(),
            now=NOW,
            form_definition_id=uuid4(),
            form_definition_version_id=uuid4(),
            title="x",
        )


def test_restore_from_draft_raises() -> None:
    with pytest.raises(IllegalListingStateTransitionError):
        _new_listing().restore(record_id=uuid4(), actor_user_id=uuid4(), reason=None, now=NOW)


def test_renew_from_draft_raises() -> None:
    with pytest.raises(IllegalListingStateTransitionError):
        _new_listing().renew(record_id=uuid4(), actor_user_id=uuid4(), new_expires_at=NOW, now=NOW)


def test_record_expiry_from_draft_raises() -> None:
    with pytest.raises(IllegalListingStateTransitionError):
        _new_listing().record_expiry(record_id=uuid4(), now=NOW)


def test_flag_on_deleted_raises() -> None:
    deleted = _new_listing().delete(record_id=uuid4(), actor_user_id=None, reason=None, now=NOW)
    with pytest.raises(IllegalListingStateTransitionError):
        deleted.flag(record_id=uuid4(), reason="dup", now=NOW)


def test_apply_and_clear_promotion() -> None:
    from catalog.domain.value_objects import PromotionKind

    listing = _new_listing()
    entitlement_id = uuid4()
    promoted = listing.apply_promotion(
        kind=PromotionKind.FEATURED,
        valid_until=NOW + timedelta(days=7),
        entitlement_id=entitlement_id,
        now=NOW,
    )
    assert promoted.promotion is not None
    assert promoted.promotion.kind is PromotionKind.FEATURED
    assert promoted.promotion.entitlement_id == entitlement_id

    cleared = promoted.clear_promotion(now=NOW)
    assert cleared.promotion is None
