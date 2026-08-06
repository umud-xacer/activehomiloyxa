"""search -- the query model. A pure, engine-agnostic representation of a search request, built
by `application/` from either the GET query-parameter shape or the POST `SearchRequest` body
(`interfaces/dto.py`, frozen) before being handed to whichever `SearchIndexPort`/`FallbackQueryPort`
adapter serves the request -- neither adapter (nor the caller) needs to know which HTTP shape the
request originally arrived in.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from search.domain.value_objects import ListingType, SortOption
from shared_kernel import GeoLocation


@dataclass(frozen=True)
class GeoFilter:
    """FR-MAP-003: radius search around a point."""

    center: GeoLocation
    radius_km: float


@dataclass(frozen=True)
class SearchQuery:
    """`q` is matched cross-script (FR-SRCH-004) against both normalized shadow fields;
    `filters` keys must be facet-eligible field codes per the current `SearchConfiguration`
    snapshot (DB Architecture Sec 12: "never arbitrary attributes") -- `application/` validates
    that before constructing this, not this type itself (a pure value object has no I/O to check
    the snapshot with)."""

    q: str | None
    category_id: UUID | None
    owner_profile_id: UUID | None
    """Monetization/B2B-directory task: filters to one business profile's own listings -- lets a
    company's landing page render its own "Xizmatlar" (services) list by reusing the ordinary
    catalog/search read path instead of a parallel services concept. `owner_profile_id` is already
    indexed (`ListingSearchDocument.owner_profile_id`, written for the badge-reindex fan-out) but
    was never exposed as a query filter until now."""
    listing_type: ListingType | None
    filters: dict[str, str]
    price_min: Decimal | None
    price_max: Decimal | None
    verified_only: bool
    geo: GeoFilter | None
    sort: SortOption
    cursor: str | None
    limit: int
