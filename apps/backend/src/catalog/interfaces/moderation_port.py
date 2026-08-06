"""The listing state-transition command port moderation (BC-11, Task P-12) invokes -- a
catalog-designed Protocol (Task P-07, extended by Task P-12 with the moderator-action verbs
BC-11 actually needs), mirroring how P-05 designed `identity.interfaces.ports.AuthorizationPort`
fresh: no OpenAPI operation exposes this (never a REST endpoint), consulted in-process only, by a
caller that has already authorized itself against `catalog:listing:moderate` via `identity.
interfaces.ports.AuthorizationPort` before invoking this port -- exactly the trust boundary
`AuthorizationPort`'s own docstring describes for every other module's use of it
(`catalog.domain.listing.Listing.unflag`'s own docstring).

Verb-to-transition mapping (moderation's closed `ResolutionAction` set, DDD Sec 5.11, extended by
`docs/adr/0003-moderation-profile-target-extension.md`): catalog has exactly three relevant
"withhold or remove" transitions (`suspend`/`archive`/`delete`) for five listing-directed verbs
(`Hide`/`Reject`/`Suspend`/`RequestCorrection`/`Remove`). No approved document specifies this
mapping (the same class of documentation gap `catalog.application.duplicate_detection_service`'s
own docstring names and resolves for FR-ADV-009's "no literal algorithm specified"); this task's
own defensible choice: `Hide`+`Suspend` -> `suspend_listing` (both "withhold, reversible"),
`Reject` -> `reject_listing`/`archive()` (a stronger, more final judgment), `Remove` ->
`remove_listing`/`delete()` (DM-06: permanent). `RequestCorrection`/`Dismiss` never call this
port at all -- neither changes a listing's own visibility state; `ModerationCase`'s own decision
record is sufficient (see `moderation/README.md`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from catalog.application import ListingUseCases
from shared_kernel import ListingId


class ListingModerationPort(Protocol):
    async def unflag_listing(self, listing_id: UUID, *, reason: str | None) -> None:
        """Reverses a `ListingFlagged` hold (BRULE-17/DEC-14) once moderation has reviewed and
        cleared it. Raises `catalog.domain.exceptions.ListingNotFlaggedError` if the listing is
        not currently flagged; `catalog.application.exceptions.ListingNotFoundError` if it does
        not exist."""
        ...

    async def hide_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        """Backs `ResolutionAction.HIDE` -- `Listing.suspend()`. See module docstring for the
        verb-to-transition mapping rationale."""
        ...

    async def reject_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        """Backs `ResolutionAction.REJECT` -- `Listing.archive()`."""
        ...

    async def suspend_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        """Backs `ResolutionAction.SUSPEND` -- `Listing.suspend()` (same transition as `HIDE`;
        the verb distinction lives in `ModerationCase.resolutionAction`'s own audit record)."""
        ...

    async def remove_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        """Backs `ResolutionAction.REMOVE` -- `Listing.delete()` (DM-06: a state, never a row
        removal)."""
        ...


class CatalogListingModerationAdapter:
    """Implements `ListingModerationPort` by delegating to `catalog.application.ListingUseCases`
    -- the concrete instance wired at the composition root for moderation to consume, mirroring
    exactly how identity's `AuthorizationPort` concrete adapter is wired for every other module
    today."""

    def __init__(self, use_cases: ListingUseCases) -> None:
        self._use_cases = use_cases

    async def unflag_listing(self, listing_id: UUID, *, reason: str | None) -> None:
        await self._use_cases.unflag_listing(
            listing_id=ListingId(value=listing_id), reason=reason, now=datetime.now(UTC)
        )

    async def hide_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        await self._use_cases.moderator_suspend_listing(
            listing_id=ListingId(value=listing_id),
            moderator_user_id=moderator_user_id,
            reason=reason,
            now=datetime.now(UTC),
        )

    async def reject_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        await self._use_cases.moderator_archive_listing(
            listing_id=ListingId(value=listing_id),
            moderator_user_id=moderator_user_id,
            reason=reason,
            now=datetime.now(UTC),
        )

    async def suspend_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        await self._use_cases.moderator_suspend_listing(
            listing_id=ListingId(value=listing_id),
            moderator_user_id=moderator_user_id,
            reason=reason,
            now=datetime.now(UTC),
        )

    async def remove_listing(
        self, listing_id: UUID, *, moderator_user_id: UUID, reason: str | None
    ) -> None:
        await self._use_cases.moderator_delete_listing(
            listing_id=ListingId(value=listing_id),
            moderator_user_id=moderator_user_id,
            reason=reason,
            now=datetime.now(UTC),
        )
