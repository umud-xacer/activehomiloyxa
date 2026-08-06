"""catalog -- typed domain exceptions, one per invariant violated (Playbook Sec 6). Mirrors
`identity.domain.exceptions`/`media.domain.exceptions`'s style. `interfaces/errors.py` maps each
of these to a `contracts.errors.Problem` (closed `ErrorCode` vocabulary).
"""

from __future__ import annotations

from uuid import UUID


class CatalogDomainError(Exception):
    """Base for every typed exception raised by catalog's domain/ layer."""


# --- lifecycle (I-05) --------------------------------------------------------------------------


class IllegalListingStateTransitionError(CatalogDomainError):
    """I-05: "only the transitions of the fixed lifecycle graph are legal." Attempted a
    transition method from a `LifecycleState` it does not accept."""

    def __init__(self, transition: str, current: str) -> None:
        self.transition = transition
        self.current = current
        super().__init__(f"cannot {transition} a listing in state {current}")


class ListingAlreadyFlaggedError(CatalogDomainError):
    """`Listing.flag` called on an already-flagged listing (idempotency guard, not a hard
    invariant -- kept typed since a moderation-triggered double-flag is a caller bug worth
    surfacing distinctly from a generic illegal-transition)."""


class ListingNotFlaggedError(CatalogDomainError):
    """`Listing.unflag` called on a listing that is not currently flagged."""


# --- images (I-04, BRULE-06/11) ----------------------------------------------------------------


class ImageLimitExceededError(CatalogDomainError):
    """I-04/BRULE-06: at most ten image attachments. The 11th `attach_image` call raises this."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        super().__init__(f"a listing may carry at most {limit} image attachments")


class ImageAttachmentNotFoundError(CatalogDomainError):
    def __init__(self, image_id: UUID) -> None:
        self.image_id = image_id
        super().__init__(f"no image attachment {image_id} on this listing")


class DuplicateImagePositionError(CatalogDomainError):
    """`reorder_images` was given a set of ids that does not exactly match the listing's current
    attachments (Physical DB `UNIQUE(listing_id, position)` -- enforced here first so a bad
    reorder request fails with a typed domain error, not a raw `IntegrityError`)."""


# --- attribute validation (I-07, DB Architecture Sec 14.3) -------------------------------------


class AttributeValidationError(CatalogDomainError):
    """The validation engine [P] rejected the submitted AttributeSet against one or more
    configured rules [C] bound to the frozen FormDefinition version."""

    def __init__(self, failures: tuple[str, ...]) -> None:
        self.failures = failures
        super().__init__(f"attribute validation failed: {'; '.join(failures)}")


# --- quota (I-08, BRULE-07) ---------------------------------------------------------------------


class QuotaExceededError(CatalogDomainError):
    """I-08: "listing creation beyond the owner's plan quota is refused." Raised by
    `QuotaEnforcementService` (`application/quota_service.py`), not the aggregate itself -- the
    quota check reads the projected subscription snapshot, which the aggregate has no access to
    (domain imports shared_kernel only)."""

    def __init__(self, limit: int, current: int) -> None:
        self.limit = limit
        self.current = current
        super().__init__(f"quota exceeded: {current} active listings, plan limit is {limit}")


# --- ownership (I-01) ---------------------------------------------------------------------------


class NotListingOwnerError(CatalogDomainError):
    """`updateListing`/`deleteListing`/`changeListingStatus`'s "ownership validated": the caller
    is neither the owning account nor acting as the owning business profile. Maps to 403
    `PERMISSION_DENIED` -- an ownership check, not an `AuthorizationPort` gate (self-service
    scope, mirroring `media.application.exceptions.NotAssetOwnerError`)."""

    def __init__(self, listing_id: UUID) -> None:
        self.listing_id = listing_id
        super().__init__(f"caller does not own listing {listing_id}")
