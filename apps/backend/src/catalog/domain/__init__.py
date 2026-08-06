"""catalog/domain -- the Listing aggregate, its ImageAttachment/LifecycleTransitionRecord child
entities, the Favorite aggregate, value objects, the validation-engine policy, and typed
exceptions (Task P-07). Imports `shared_kernel` only (Clean Architecture rule 1); never imported
by another module (`domain/` is never part of a module's public surface, AIR-02)."""

from __future__ import annotations

from catalog.domain.exceptions import (
    AttributeValidationError,
    CatalogDomainError,
    DuplicateImagePositionError,
    IllegalListingStateTransitionError,
    ImageAttachmentNotFoundError,
    ImageLimitExceededError,
    ListingAlreadyFlaggedError,
    ListingNotFlaggedError,
    NotListingOwnerError,
    QuotaExceededError,
)
from catalog.domain.favorite import Favorite
from catalog.domain.image_attachment import ImageAttachment
from catalog.domain.lifecycle_transition_record import LifecycleTransitionRecord
from catalog.domain.listing import MAX_IMAGE_ATTACHMENTS, Listing
from catalog.domain.policies import (
    generate_slug,
    normalize_title_for_duplicate_matching,
    validate_attribute_set,
)
from catalog.domain.saved_search import SavedSearch
from catalog.domain.value_objects import (
    FieldValidatorSpec,
    ImageStatus,
    LifecycleState,
    ListingType,
    PromotionKind,
    PromotionMarker,
    TransitionKind,
    ValidatorType,
)

__all__ = [
    "MAX_IMAGE_ATTACHMENTS",
    "AttributeValidationError",
    "CatalogDomainError",
    "DuplicateImagePositionError",
    "Favorite",
    "FieldValidatorSpec",
    "IllegalListingStateTransitionError",
    "ImageAttachment",
    "ImageAttachmentNotFoundError",
    "ImageLimitExceededError",
    "ImageStatus",
    "LifecycleState",
    "LifecycleTransitionRecord",
    "Listing",
    "ListingAlreadyFlaggedError",
    "ListingNotFlaggedError",
    "ListingType",
    "NotListingOwnerError",
    "PromotionKind",
    "PromotionMarker",
    "QuotaExceededError",
    "TransitionKind",
    "ValidatorType",
    "generate_slug",
    "normalize_title_for_duplicate_matching",
    "validate_attribute_set",
]
