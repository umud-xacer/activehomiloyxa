"""profiles/application -- exceptions for facts the domain layer cannot know (missing rows,
cross-module lookups, optimistic-concurrency conflicts, authorization). Mirrors
`catalog.application.exceptions`'s style: one base, typed subclasses named for the invariant/
condition they signal.
"""

from __future__ import annotations

from uuid import UUID

from shared_kernel import BusinessProfileId


class ProfilesApplicationError(Exception):
    """Base for every typed exception raised by profiles' application/ layer."""


class ProfileNotFoundError(ProfilesApplicationError):
    def __init__(self, profile_id: BusinessProfileId | UUID) -> None:
        self.profile_id = profile_id
        super().__init__(f"business profile {profile_id} not found")


class VerificationCaseNotFoundError(ProfilesApplicationError):
    def __init__(self, case_id: UUID) -> None:
        self.case_id = case_id
        super().__init__(f"verification case {case_id} not found")


class NotProfileOwnerError(ProfilesApplicationError):
    """I-10: "every operation is scoped to the acting profile; cross-profile access is denied by
    default." Raised by a use case when the caller's resolved identity does not own the target
    `BusinessProfile`."""

    def __init__(self, profile_id: BusinessProfileId) -> None:
        self.profile_id = profile_id
        super().__init__(f"caller does not own business profile {profile_id}")


class VerificationNotEligibleError(ProfilesApplicationError):
    """I-12/X-03: "a verification case may proceed only when the corresponding verification
    entitlement is active" -- the unpaid-verification exception named in P-11's own deliverables.
    Raised by `VerificationUseCases.request_verification` when
    `VerificationEligibilityRepository.get_active_for_profile` returns `None` -- learned
    exclusively from billing's projected *events*, never a synchronous billing read (profiles has
    no static dependency on billing, SAD Sec 8.1)."""

    def __init__(self, profile_id: BusinessProfileId) -> None:
        self.profile_id = profile_id
        super().__init__(
            f"business profile {profile_id} has no active VerificationEligibility entitlement"
        )


class MediaAssetNotFoundError(ProfilesApplicationError):
    """Distinct from `media.application.exceptions.MediaAssetNotFoundError` -- profiles never
    imports media's own exception type (`cross-module-profiles`); this is profiles' own typed
    fact about a media asset id it could not resolve via `MediaAssetReaderPort`."""

    def __init__(self, media_asset_id: UUID) -> None:
        self.media_asset_id = media_asset_id
        super().__init__(f"media asset {media_asset_id} not found")


class PromoVideoNotVideoError(ProfilesApplicationError):
    """Promo videos must reference a `video/mp4`/`video/webm` media asset, not an image -- a fact
    about the referenced asset's content_type, learned via `MediaAssetReaderPort`, so it belongs
    here rather than on the aggregate (mirrors `MediaAssetNotFoundError`'s own placement)."""

    def __init__(self, media_asset_id: UUID, content_type: str | None) -> None:
        self.media_asset_id = media_asset_id
        self.content_type = content_type
        super().__init__(f"media asset {media_asset_id} is not a video (got {content_type!r})")


class PromoVideoTooLongError(ProfilesApplicationError):
    """The promo-video business rule's own hard cap: at most 30 seconds. Fails closed on an
    unreadable/unknown duration too (see `ProfileUseCases.add_promo_video`'s own docstring) --
    `duration_seconds=None` in this error means "could not be determined", not "unlimited"."""

    def __init__(
        self, media_asset_id: UUID, duration_seconds: float | None, max_seconds: float
    ) -> None:
        self.media_asset_id = media_asset_id
        self.duration_seconds = duration_seconds
        self.max_seconds = max_seconds
        super().__init__(
            f"media asset {media_asset_id} duration {duration_seconds!r}s exceeds the "
            f"{max_seconds}s promo-video cap (or could not be determined)"
        )


class PromoVideoNotReadyError(ProfilesApplicationError):
    """The referenced media asset has not finished the async scan/processing pipeline yet
    (`scan_status != CLEAN`) -- unlike portfolio images, a promo video must be fully processed
    before it can be attached, since duration is only known once processing has run."""

    def __init__(self, media_asset_id: UUID) -> None:
        self.media_asset_id = media_asset_id
        super().__init__(f"media asset {media_asset_id} is not yet ready (scan/processing pending)")


class ProfileNotPubliclyVisibleError(ProfilesApplicationError):
    """ADR-0010: raised by `get_public_profile_by_slug` when the profile's
    `subscription_status` is not `ACTIVE` (no trial, trial lapsed, subscription lapsed) --
    `interfaces/errors.py` maps this to a 404, same as `ProfileNotFoundError`, deliberately: a
    visitor should not be able to distinguish "never existed" from "exists but not currently
    entitled to a public landing page" from the response alone. The owner's own dashboard reads
    the by-id endpoint instead, which stays permissive (see `BusinessProfileRepository.
    get_by_slug`'s own docstring)."""

    def __init__(self, slug: str) -> None:
        self.slug = slug
        super().__init__(f"business profile {slug!r} is not currently publicly visible")
