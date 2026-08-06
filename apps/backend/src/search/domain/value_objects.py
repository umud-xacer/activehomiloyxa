"""search -- value objects (DDD Sec 5.5 BC-05). Persistence-ignorant, mirrors
`catalog.domain.value_objects`'s style. Closed vocabularies here are the exact same [P]
enumerations catalog already froze (`PromotionKind`, `ListingType`) -- search re-declares them
rather than importing catalog's own module (`search-scope`, tools/importlinter.cfg forbids any
import of `catalog`), since a projected value's *shape* crossing an event payload is not the
same thing as depending on the producing module's code.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class ListingType(StrEnum):
    """Verbatim from `contracts/openapi.yaml` `SearchRequest.listingType` / catalog's own frozen
    `ListingType [P]` -- projected onto `ListingSearchDocument`, never re-derived."""

    ADVERTISEMENT = "ADVERTISEMENT"
    PRODUCT = "PRODUCT"
    SERVICE = "SERVICE"


class PromotionKind(StrEnum):
    """DDD Sec 5.3 `PromotionMarker` kind, projected from billing entitlement events (X-03).
    Verbatim from `contracts/openapi.yaml` `SearchHitPromoted.kind`."""

    PREMIUM = "PREMIUM"
    FEATURED = "FEATURED"
    TOP_PLACEMENT = "TOP_PLACEMENT"


class SortOption(StrEnum):
    """The `[P]` sort vocabulary (DB Architecture Sec 12: "Only the [P] sort vocabulary as
    enabled by SearchConfiguration"). Verbatim from `contracts/openapi.yaml`
    `SearchRequest.sort`/`GET /search`'s `sort` query param enum. `SearchConfiguration.
    sort_options`/`default_sort` (configuration.domain.content.SearchConfigurationContent) select
    a SUBSET of this fixed vocabulary and its default -- the vocabulary itself is [P], never
    configurable (DEC-21's own "configuration is data" boundary)."""

    RELEVANCE = "RELEVANCE"
    RECENCY = "RECENCY"
    PRICE_ASC = "PRICE_ASC"
    PRICE_DESC = "PRICE_DESC"


class SuggestionType(StrEnum):
    """Verbatim from `contracts/openapi.yaml` `Suggestion.type`."""

    QUERY = "QUERY"
    CATEGORY = "CATEGORY"
    LISTING = "LISTING"


@dataclass(frozen=True)
class PromotionMarker:
    """DDD Sec 5.3 `PromotionMarker` VO, projected onto `ListingSearchDocument` from billing's
    `EntitlementActivated`/`EntitlementExpired`/`EntitlementRevoked` events (X-03: "promotion...
    state [is] locally projected, so listing pages and search never block on Billing"). No
    catalog/billing import -- built purely from event-payload fields."""

    kind: PromotionKind
    valid_until: datetime | None
    entitlement_id: UUID
