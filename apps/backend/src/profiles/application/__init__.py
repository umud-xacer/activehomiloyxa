"""profiles/application -- use cases + ports (Task P-11). Depends only on `profiles.domain`,
`shared_kernel`, and `contracts.events.profiles`."""

from __future__ import annotations

from profiles.application.exceptions import (
    MediaAssetNotFoundError,
    NotProfileOwnerError,
    ProfileNotFoundError,
    ProfilesApplicationError,
    VerificationCaseNotFoundError,
    VerificationNotEligibleError,
)
from profiles.application.ports import (
    BusinessProfileRepository,
    MediaAssetReaderPort,
    MediaAssetSnapshot,
    VerificationCaseRepository,
    VerificationEligibilityRepository,
    VerificationEligibilitySnapshot,
)
from profiles.application.profile_use_cases import ProfileUseCases
from profiles.application.verification_use_cases import VerificationUseCases

__all__ = [
    "BusinessProfileRepository",
    "MediaAssetNotFoundError",
    "MediaAssetReaderPort",
    "MediaAssetSnapshot",
    "NotProfileOwnerError",
    "ProfileNotFoundError",
    "ProfileUseCases",
    "ProfilesApplicationError",
    "VerificationCaseNotFoundError",
    "VerificationCaseRepository",
    "VerificationEligibilityRepository",
    "VerificationEligibilitySnapshot",
    "VerificationNotEligibleError",
    "VerificationUseCases",
]
