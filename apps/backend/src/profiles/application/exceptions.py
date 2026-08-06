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
