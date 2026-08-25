"""Direct construction tests for `profiles.domain.exceptions`/`profiles.application.exceptions`
subclasses whose `__init__`/message-formatting bodies are not otherwise exercised by a domain or
use-case test elsewhere in this package -- mirrors how the other backend modules cover their own
typed-exception message bodies (each subclass carries real, otherwise-untested logic: it stores
its constructor arguments as attributes and formats a specific error message)."""

from __future__ import annotations

from uuid import uuid4

from profiles.application.exceptions import (
    ProfileNotPubliclyVisibleError,
    PromoVideoNotReadyError,
    PromoVideoNotVideoError,
    PromoVideoTooLongError,
)
from profiles.domain.exceptions import (
    OnboardingAlreadyCompletedError,
    OnboardingIncompleteError,
    PromoVideoLimitExceededError,
    PromoVideoNotFoundError,
    SubCategoryNotInMainCategoryError,
)


def test_sub_category_not_in_main_category_error_message() -> None:
    error = SubCategoryNotInMainCategoryError("GENERAL_CONTRACTOR", "FINANCE_MORTGAGE")
    assert error.sub_category == "GENERAL_CONTRACTOR"
    assert error.main_category == "FINANCE_MORTGAGE"
    assert "GENERAL_CONTRACTOR" in str(error)
    assert "FINANCE_MORTGAGE" in str(error)


def test_promo_video_limit_exceeded_error_message() -> None:
    error = PromoVideoLimitExceededError(2)
    assert error.limit == 2
    assert "2" in str(error)


def test_promo_video_not_found_error_message() -> None:
    media_asset_id = uuid4()
    error = PromoVideoNotFoundError(media_asset_id)
    assert error.media_asset_id == media_asset_id
    assert str(media_asset_id) in str(error)


def test_onboarding_already_completed_error_message() -> None:
    profile_id = uuid4()
    error = OnboardingAlreadyCompletedError(profile_id)
    assert error.profile_id == profile_id
    assert str(profile_id) in str(error)


def test_onboarding_incomplete_error_message() -> None:
    error = OnboardingIncompleteError("logoMediaAssetId")
    assert error.missing_field == "logoMediaAssetId"
    assert "logoMediaAssetId" in str(error)


def test_promo_video_not_video_error_message() -> None:
    media_asset_id = uuid4()
    error = PromoVideoNotVideoError(media_asset_id, "image/png")
    assert error.media_asset_id == media_asset_id
    assert error.content_type == "image/png"
    assert "image/png" in str(error)


def test_promo_video_too_long_error_message() -> None:
    media_asset_id = uuid4()
    error = PromoVideoTooLongError(media_asset_id, 45.0, 30.0)
    assert error.duration_seconds == 45.0
    assert error.max_seconds == 30.0
    assert "45.0" in str(error)


def test_promo_video_too_long_error_with_unknown_duration() -> None:
    """`duration_seconds=None` means "could not be determined", not "unlimited" (fails closed) --
    the error message must still render cleanly for that case."""
    error = PromoVideoTooLongError(uuid4(), None, 30.0)
    assert error.duration_seconds is None
    assert "None" in str(error)


def test_promo_video_not_ready_error_message() -> None:
    media_asset_id = uuid4()
    error = PromoVideoNotReadyError(media_asset_id)
    assert error.media_asset_id == media_asset_id
    assert str(media_asset_id) in str(error)


def test_profile_not_publicly_visible_error_message() -> None:
    error = ProfileNotPubliclyVisibleError("acme-co")
    assert error.slug == "acme-co"
    assert "acme-co" in str(error)
