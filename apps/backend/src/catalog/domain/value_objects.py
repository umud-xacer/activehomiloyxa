"""catalog -- value objects (DDD Sec 5.3 BC-03). Persistence-ignorant, mirrors
`media.domain.value_objects`'s style.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import UUID


class ListingType(StrEnum):
    """DDD Sec 5.3 VO `ListingType [P]` -- a closed vocabulary."""

    ADVERTISEMENT = "ADVERTISEMENT"
    PRODUCT = "PRODUCT"
    SERVICE = "SERVICE"


class LifecycleState(StrEnum):
    """DDD Sec 5.3 VO `LifecycleState [P]` -- originally the fixed seven-state machine (DEC-14),
    widened to eight 2026-08-25 for the "Mark as Sold" feature (real product request, not a
    reinterpretation of DEC-14 -- the same class of deliberate, documented extension
    `contracts/events/catalog.py`'s own ADR-0005 note already established for that "frozen"
    catalogue). `SOLD` behaves like `ARCHIVED` for visibility (excluded from `_VISIBLE_STATES`,
    so it drops out of search/catalog listing) but is reachable only from `PUBLISHED`/`EDITED`
    (`Listing.mark_sold`) and, unlike every other non-visible state, is still resolvable at its
    own public detail URL (`catalog.interfaces.routers.get_listing`'s explicit carve-out) so a
    buyer following an old link sees "sotilgan" rather than a 404. `PENDING_VERIFICATION` is part
    of the frozen schema's CHECK constraint but is not entered by any transition this task
    implements: BRULE-17 ("moderation is post-publication in v1") confirms v1 has no
    pre-publication verification gate -- reserved for a future task, the same class of
    dormant-but-frozen enum value as `identity.domain.AccountStatus` having no `PENDING` in P-05.
    `EXPIRED`/`RENEWED` are deliberately NOT states here -- FR-ADV-006/DDD Sec 5.3 calls them
    "RECORDED transitions": expiry/renewal only move `Listing.expires_at`, recorded via a
    `LifecycleTransitionRecord` and an event, while `lifecycle_state` itself stays
    `PUBLISHED`/`EDITED` (I-06's visibility rule already accounts for expiry via `expires_at`,
    independently of `lifecycle_state`)."""

    DRAFT = "DRAFT"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    PUBLISHED = "PUBLISHED"
    EDITED = "EDITED"
    SUSPENDED = "SUSPENDED"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"
    SOLD = "SOLD"


class ImageStatus(StrEnum):
    """Projected from media's `MediaAsset.scan_status` (X-06) -- verbatim from
    `contracts/openapi.yaml`'s `ListingImage.status`."""

    PENDING = "PENDING"
    CLEAN = "CLEAN"
    QUARANTINED = "QUARANTINED"


class PromotionKind(StrEnum):
    """DDD Sec 5.3 VO `PromotionMarker` kind -- projected from billing entitlement events (X-03).
    Verbatim from `contracts/openapi.yaml`'s `ListingPromotion.kind`."""

    PREMIUM = "PREMIUM"
    FEATURED = "FEATURED"
    TOP_PLACEMENT = "TOP_PLACEMENT"


class TransitionKind(StrEnum):
    """Physical DB `catalog.listing_transition.transition_kind` CHECK -- the complete, closed set
    of twelve recordable transition kinds (the authoritative list; NOT 1:1 with
    `ListingStatusChangeRequest.action`'s seven API-facing verbs -- `CREATE`/`EDIT`/`EXPIRE`/
    `FLAG`/`UNFLAG` have no API action of their own, see `listing.py`'s per-method docstrings for
    which caller triggers each). `SELL` added 2026-08-25 alongside `LifecycleState.SOLD`."""

    CREATE = "CREATE"
    PUBLISH = "PUBLISH"
    EDIT = "EDIT"
    SUSPEND = "SUSPEND"
    ARCHIVE = "ARCHIVE"
    DELETE = "DELETE"
    EXPIRE = "EXPIRE"
    RENEW = "RENEW"
    FLAG = "FLAG"
    UNFLAG = "UNFLAG"
    RESTORE = "RESTORE"
    SELL = "SELL"


ValidatorType = Literal[
    "required", "length", "numeric_range", "pattern_safe", "option_membership", "image_count"
]
"""The closed set of validator types `configuration.interfaces.dto.ValidatorBinding.validator_type`
declares -- the exact vocabulary `policies.py`'s validation engine [P] must implement, no more,
no less (DB Architecture Sec 14.3: "AttributeSet vs FormDefinition version -- validation engine
[P] in catalog, executing configured rules [C]")."""


@dataclass(frozen=True)
class FieldValidatorSpec:
    """One configured rule [C] bound to one form field -- the domain-layer shape the validation
    engine consumes, translated by `application/` from `configuration.interfaces.dto.FormField`/
    `ValidatorBinding` (catalog's domain never imports `configuration`, AIR-02)."""

    field_code: str
    validator_type: ValidatorType
    params: dict[str, Any]
    required_field: bool
    """Whether the FIELD ITSELF (`FormField.required`) is mandatory -- distinct from a
    `validator_type="required"` binding, which is one specific configured rule among several a
    field may carry."""


@dataclass(frozen=True)
class PromotionMarker:
    """DDD Sec 5.3 VO -- Premium/Featured/TopPlacement with validity, projected from billing
    entitlement events (X-03). Never constructed from a synchronous billing read -- catalog does
    not import billing (AIR-10 named-cycle exclusion)."""

    kind: PromotionKind
    valid_until: datetime
    entitlement_id: UUID
