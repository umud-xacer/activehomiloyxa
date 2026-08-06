"""The profile-moderation command port BC-11 (out of this task's scope) will later invoke -- a
fresh, profiles-designed Protocol (Task P-11), mirroring how P-07 designed `catalog.interfaces.
moderation_port.ListingModerationPort` fresh: no OpenAPI operation exposes this (never a REST
endpoint), consulted in-process only, by a caller that has already authorized itself against a
moderation permission key via `identity.interfaces.ports.AuthorizationPort` before invoking this
port -- exactly the trust boundary `ListingModerationPort`'s own docstring describes.

`Revoked` is a documented `VerifiedBadge` sub-state (Domain Model Sec 5.2, Physical DB Design's
own `badge_status` CHECK constraint) but no document names its triggering actor beyond "e.g.
following a moderation action" (this task's own scope note) -- exposing it here, rather than
inventing a REST endpoint or a new cross-module port on identity, is the narrowest reading that
satisfies both "the capability must exist" and "moderation invokes it through profiles'
interfaces/, never profiles' internals" (AIR-02).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from profiles.application import ProfileUseCases
from shared_kernel import BusinessProfileId


class ProfileModerationPort(Protocol):
    async def revoke_badge(self, profile_id: UUID) -> None:
        """Moderation-invoked badge revocation (`BusinessProfile.revoke_badge`). Raises
        `profiles.domain.exceptions.IllegalBadgeTransitionError` if the profile currently has no
        `VALID` badge; `profiles.application.exceptions.ProfileNotFoundError` if it does not
        exist."""
        ...

    async def archive_profile(self, profile_id: UUID) -> None:
        """Moderation-invoked profile archival (`BusinessProfile.archive`), e.g. following
        account suspension. Raises `profiles.domain.exceptions.
        IllegalProfileStatusTransitionError` if the profile is not `ACTIVE`;
        `profiles.application.exceptions.ProfileNotFoundError` if it does not exist."""
        ...


class ProfilesModerationAdapter:
    """Implements `ProfileModerationPort` by delegating to `profiles.application.ProfileUseCases`
    -- the concrete instance wired at the composition root for a future moderation module to
    consume, mirroring exactly how `catalog.interfaces.moderation_port.
    CatalogListingModerationAdapter` is wired for every other module today."""

    def __init__(self, use_cases: ProfileUseCases) -> None:
        self._use_cases = use_cases

    async def revoke_badge(self, profile_id: UUID) -> None:
        await self._use_cases.moderation_revoke_badge(
            BusinessProfileId(value=profile_id), now=datetime.now(UTC)
        )

    async def archive_profile(self, profile_id: UUID) -> None:
        await self._use_cases.moderation_archive_profile(
            BusinessProfileId(value=profile_id), now=datetime.now(UTC)
        )
