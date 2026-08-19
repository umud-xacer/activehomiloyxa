"""`OpenSearchIndexAdapter` -- implements `search.application.ports.SearchIndexPort`.
`opensearchpy` is the only place an OpenSearch SDK type appears (`provider-sdk-confined-to-
infrastructure`, tools/importlinter.cfg); every method boundary is `str`/`UUID`/domain types only.

`opensearch-py==3.2.0` is pinned without the `[async]` extra (no `aiohttp` dependency exists in
`apps/backend/pyproject.toml`) -- the plain synchronous `OpenSearch` client is used, and every
network call runs off the event loop via `asyncio.to_thread` (Playbook Sec 6: "I/O ... MUST be
non-blocking"), the exact same pattern `media.infrastructure.object_storage.MinioStorageAdapter`
already established for boto3 (also sync-only).

Cross-script matching (FR-SRCH-004/DEC-19) does NOT rely on an OpenSearch-side transliteration
analyzer -- the transliteration itself already happened in Python (`search.domain.cross_script`)
at both index time (`ListingSearchDocument.title_normalized_latin`/`_cyrillic`) and query time
(`_build_query_body`, below). OpenSearch's job is only to tokenize/match plain-alphabet text it's
handed, in whichever of the two canonical scripts a given field holds -- a `standard` analyzer
suffices for that. A `russian` analyzer subfield on `title`/`description` (Baseline Sec 5.8:
"Russian analyzer for RU content") gives proper stemming for Russian-authored listings, the one
piece of linguistic analysis actually delegated to OpenSearch itself.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from opensearchpy import NotFoundError, OpenSearch, TransportError

from search.application.exceptions import SearchIndexUnavailableError
from search.application.ports import (
    FacetBucketResult,
    FacetResult,
    FacetSpec,
    SearchHitResult,
    SearchResultPage,
    SuggestionResult,
)
from search.domain import (
    ListingSearchDocument,
    ListingType,
    PromotionKind,
    PromotionMarker,
    SearchQuery,
    SortOption,
)
from search.domain.cross_script import normalize_for_matching
from shared_kernel import GeoLocation, Money

INDEX_MAPPING: dict[str, Any] = {
    "settings": {"index": {"number_of_shards": 1, "number_of_replicas": 0}},
    "mappings": {
        # Facet values are indexed as `keyword` per attribute, which is what makes a terms
        # aggregation over them work at all. `flat_object` (below, in the history this replaces)
        # is queryable by dotted path but NOT properly aggregatable in OpenSearch 2.19: a terms
        # agg on `attributes.<code>` returns bucket keys like `java.lang.Object@5d7731b2` --
        # confirmed by direct `curl` against the running cluster -- so every filter panel showed
        # its dimension names with either garbage values or, once those were discarded upstream,
        # no values at all.
        #
        # Mapping explosion is bounded and does not need `flat_object`'s protection here: the
        # projection stores the *facet-relevant subset only*, "exactly the facet-eligible field
        # codes selected in the SearchConfiguration snapshot" (DB Architecture Sec 12,
        # `ListingSearchDocument.attributes`), which is a small admin-chosen set, not arbitrary
        # listing content.
        "dynamic_templates": [
            {
                "attribute_values_as_keyword": {
                    "path_match": "attributes.*",
                    "match_mapping_type": "*",
                    "mapping": {"type": "keyword", "ignore_above": 256},
                }
            }
        ],
        "properties": {
            "listing_id": {"type": "keyword"},
            "owner_profile_id": {"type": "keyword"},
            "title": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"ru": {"type": "text", "analyzer": "russian"}},
            },
            "title_normalized_latin": {"type": "text", "analyzer": "standard"},
            "title_normalized_cyrillic": {"type": "text", "analyzer": "standard"},
            "description": {
                "type": "text",
                "analyzer": "standard",
                "fields": {"ru": {"type": "text", "analyzer": "russian"}},
            },
            "category_id": {"type": "keyword"},
            "category_path": {"type": "keyword"},
            "listing_type": {"type": "keyword"},
            # An ordinary object; the dynamic template above types each leaf as `keyword`.
            # (P-20 moved this from Elasticsearch's `flattened` to OpenSearch's `flat_object`
            # because the former does not exist here at all -- `ensure_index` failed with
            # `mapper_parsing_exception: No handler for type [flattened]`. `flat_object` fixed
            # index creation but, as the note above records, is not aggregatable.)
            "attributes": {"type": "object"},
            "price_amount": {"type": "double"},
            "price_currency": {"type": "keyword"},
            "location": {"type": "geo_point"},
            "promotion_kind": {"type": "keyword"},
            "promotion_valid_until": {"type": "date"},
            "promotion_entitlement_id": {"type": "keyword"},
            "verified_badge": {"type": "boolean"},
            "publicly_visible": {"type": "boolean"},
            "slug": {"type": "keyword"},
            # Never queried or aggregated -- carried only so a result card can render a
            # thumbnail without a second round trip per hit. `index: False` keeps it out of the
            # inverted index while still returning it in `_source`.
            "primary_image_thumbnail_url": {"type": "keyword", "index": False},
            "published_at": {"type": "date"},
            "updated_at": {"type": "date"},
        },
    },
}

_SORT_FIELD_BY_OPTION: dict[SortOption, list[dict[str, Any]]] = {
    SortOption.RELEVANCE: [{"_score": {"order": "desc"}}],
    SortOption.RECENCY: [{"published_at": {"order": "desc", "missing": "_last"}}],
    SortOption.PRICE_ASC: [{"price_amount": {"order": "asc", "missing": "_last"}}],
    SortOption.PRICE_DESC: [{"price_amount": {"order": "desc", "missing": "_last"}}],
}


def _build_query_body(query: SearchQuery, *, facet_specs: tuple[FacetSpec, ...]) -> dict[str, Any]:
    """FR-SRCH-001 (full-text) + FR-SRCH-002 (facet filters) + FR-SRCH-004 (cross-script) +
    FR-MAP-003 (radius) + FR-SRCH-003 (sort), blended into one query. Relevance/recency/promotion
    BLENDING (DEC-12) happens via `_SORT_FIELD_BY_OPTION`'s own relevance-first default plus a
    `function_score` boost for promoted documents; the hard CAP on how many promoted hits survive
    (I-17) is enforced afterwards, in `search.domain.ranking.apply_promotion_cap`, never here --
    a boost only influences ranking, it cannot itself guarantee a count ceiling."""
    must: list[dict[str, Any]] = []
    filters: list[dict[str, Any]] = [{"term": {"publicly_visible": True}}]

    if query.q:
        q_latin, q_cyrillic = normalize_for_matching(query.q)
        must.append(
            {
                "bool": {
                    "should": [
                        {
                            "multi_match": {
                                "query": query.q,
                                "fields": [
                                    "title^3",
                                    "title.ru^3",
                                    "description",
                                    "description.ru",
                                ],
                            }
                        },
                        # Character-level typo tolerance ("mibel" -> "mebel", "katel" -> "kotej"
                        # within edit distance) -- `fuzziness: AUTO` is OpenSearch's own built-in
                        # Damerau-Levenshtein match (0 for len<3, 1 for len<6, else 2), applied only
                        # on the exact-title fields since fuzzy + multi_match's own phrase scoring
                        # would double-fuzz and blow up irrelevant matches. A near-exact hit still
                        # outranks a fuzzy one -- `boost: 2` here is deliberately lower than the
                        # `^3` on the exact `multi_match` title fields above.
                        {
                            "match": {
                                "title_normalized_latin": {
                                    "query": q_latin,
                                    "boost": 2,
                                    "fuzziness": "AUTO",
                                }
                            }
                        },
                        {
                            "match": {
                                "title_normalized_cyrillic": {
                                    "query": q_cyrillic,
                                    "boost": 2,
                                    "fuzziness": "AUTO",
                                }
                            }
                        },
                    ],
                    "minimum_should_match": 1,
                }
            }
        )
    if query.category_id is not None:
        filters.append({"term": {"category_id": str(query.category_id)}})
    if query.category_path_prefix is not None:
        # `category_path` is a `keyword` field (exact-token, not analyzed) -- `prefix` matches it
        # like a plain string prefix, no special mapping needed. Subtree aggregation for a parent
        # category page; independent of (and compatible with, if both happened to be set) the
        # exact `category_id` filter above.
        filters.append({"prefix": {"category_path": {"value": query.category_path_prefix}}})
    if query.owner_profile_id is not None:
        filters.append({"term": {"owner_profile_id": str(query.owner_profile_id)}})
    if query.listing_type is not None:
        filters.append({"term": {"listing_type": query.listing_type.value}})
    for field_code, value in query.filters.items():
        if any(spec.field_code == field_code for spec in facet_specs):
            filters.append({"term": {f"attributes.{field_code}": value}})
    if query.price_min is not None:
        filters.append({"range": {"price_amount": {"gte": float(query.price_min)}}})
    if query.price_max is not None:
        filters.append({"range": {"price_amount": {"lte": float(query.price_max)}}})
    if query.verified_only:
        filters.append({"term": {"verified_badge": True}})
    if query.geo is not None:
        filters.append(
            {
                "geo_distance": {
                    "distance": f"{query.geo.radius_km}km",
                    "location": {
                        "lat": query.geo.center.latitude,
                        "lon": query.geo.center.longitude,
                    },
                }
            }
        )

    base_query: dict[str, Any] = {"bool": {"must": must, "filter": filters}}
    scored_query: dict[str, Any] = {
        "function_score": {
            "query": base_query,
            "functions": [{"filter": {"exists": {"field": "promotion_kind"}}, "weight": 1.5}],
            "score_mode": "sum",
            "boost_mode": "sum",
        }
    }

    body: dict[str, Any] = {
        "query": scored_query,
        "size": query.limit,
        "sort": _SORT_FIELD_BY_OPTION[query.sort],
    }
    if query.cursor:
        body["from"] = int(query.cursor)
    return body


def _document_to_source(document: ListingSearchDocument) -> dict[str, Any]:
    return {
        "listing_id": str(document.listing_id),
        "owner_profile_id": (str(document.owner_profile_id) if document.owner_profile_id else None),
        "title": document.title,
        "title_normalized_latin": document.title_normalized_latin,
        "title_normalized_cyrillic": document.title_normalized_cyrillic,
        "description": document.description,
        "category_id": str(document.category_id),
        "category_path": document.category_path,
        "listing_type": document.listing_type.value,
        # Values are stringified so the aggregation keys and the `term` filters built by
        # `_build_query_body` agree. A facet is categorical by definition, and filter values
        # arrive off the query string as strings -- indexing `rooms: 3` as a number while
        # filtering with `"3"` is the sort of mismatch that returns nothing and explains
        # nothing. `None` is dropped rather than indexed as the string "None".
        "attributes": {
            code: str(value) for code, value in document.attributes.items() if value is not None
        },
        "price_amount": float(document.price.amount) if document.price else None,
        "price_currency": document.price.currency if document.price else None,
        "location": (
            {"lat": document.location.latitude, "lon": document.location.longitude}
            if document.location
            else None
        ),
        "promotion_kind": document.promotion.kind.value if document.promotion else None,
        "promotion_valid_until": (
            document.promotion.valid_until.isoformat()
            if document.promotion and document.promotion.valid_until
            else None
        ),
        "promotion_entitlement_id": (
            str(document.promotion.entitlement_id) if document.promotion else None
        ),
        "verified_badge": document.verified_badge,
        "publicly_visible": document.publicly_visible,
        "slug": document.slug,
        "primary_image_thumbnail_url": document.primary_image_thumbnail_url,
        "published_at": document.published_at.isoformat() if document.published_at else None,
        "updated_at": document.updated_at.isoformat(),
    }


def _source_to_document(source: dict[str, Any]) -> ListingSearchDocument:
    price = (
        Money(amount=Decimal(str(source["price_amount"])), currency=source["price_currency"])
        if source.get("price_amount") is not None and source.get("price_currency")
        else None
    )
    location = (
        GeoLocation(latitude=source["location"]["lat"], longitude=source["location"]["lon"])
        if source.get("location")
        else None
    )
    promotion = (
        PromotionMarker(
            kind=PromotionKind(source["promotion_kind"]),
            valid_until=(
                datetime.fromisoformat(source["promotion_valid_until"])
                if source.get("promotion_valid_until")
                else None
            ),
            entitlement_id=(
                UUID(source["promotion_entitlement_id"])
                if source.get("promotion_entitlement_id")
                else UUID(int=0)
            ),
        )
        if source.get("promotion_kind")
        else None
    )
    return ListingSearchDocument(
        listing_id=UUID(source["listing_id"]),
        owner_profile_id=(
            UUID(source["owner_profile_id"]) if source.get("owner_profile_id") else None
        ),
        title=source["title"],
        title_normalized_latin=source["title_normalized_latin"],
        title_normalized_cyrillic=source["title_normalized_cyrillic"],
        description=source.get("description"),
        category_id=UUID(source["category_id"]),
        category_path=source["category_path"],
        listing_type=ListingType(source["listing_type"]),
        attributes=source.get("attributes") or {},
        price=price,
        location=location,
        promotion=promotion,
        verified_badge=source.get("verified_badge", False),
        publicly_visible=source.get("publicly_visible", False),
        slug=source["slug"],
        primary_image_thumbnail_url=source.get("primary_image_thumbnail_url"),
        published_at=(
            datetime.fromisoformat(source["published_at"]) if source.get("published_at") else None
        ),
        updated_at=datetime.fromisoformat(source["updated_at"]),
    )


class OpenSearchIndexAdapter:
    def __init__(self, client: OpenSearch, *, index_name: str) -> None:
        self._client = client
        self._index_name = index_name

    async def ensure_index(self) -> None:
        """Idempotent index creation -- called once at worker/app startup, and by the rebuild
        capability after `delete_index`."""
        exists = await asyncio.to_thread(self._client.indices.exists, index=self._index_name)
        if not exists:
            await asyncio.to_thread(
                self._client.indices.create, index=self._index_name, body=INDEX_MAPPING
            )

    async def delete_index(self) -> None:
        """The rebuild capability's first step: discard the projection entirely (DB Architecture
        Sec 12: "full reindex = replay from the owners' data via their interfaces/events")."""
        await asyncio.to_thread(self._client.indices.delete, index=self._index_name, ignore=[404])

    async def index_document(self, document: ListingSearchDocument) -> None:
        try:
            await asyncio.to_thread(
                self._client.index,
                index=self._index_name,
                id=str(document.listing_id),
                body=_document_to_source(document),
                refresh=False,
            )
        except TransportError as exc:
            raise SearchIndexUnavailableError() from exc

    async def delete_document(self, listing_id: UUID) -> None:
        try:
            await asyncio.to_thread(
                self._client.delete, index=self._index_name, id=str(listing_id), ignore=[404]
            )
        except TransportError as exc:
            raise SearchIndexUnavailableError() from exc

    async def get_document(self, listing_id: UUID) -> ListingSearchDocument | None:
        try:
            response = await asyncio.to_thread(
                self._client.get, index=self._index_name, id=str(listing_id)
            )
        except NotFoundError:
            return None
        except TransportError as exc:
            raise SearchIndexUnavailableError() from exc
        return _source_to_document(response["_source"])

    async def find_listing_ids_by_owner_profile(self, owner_profile_id: UUID) -> tuple[UUID, ...]:
        try:
            response = await asyncio.to_thread(
                self._client.search,
                index=self._index_name,
                body={
                    "query": {"term": {"owner_profile_id": str(owner_profile_id)}},
                    "_source": False,
                    "size": 10000,
                },
            )
        except TransportError as exc:
            raise SearchIndexUnavailableError() from exc
        return tuple(UUID(hit["_id"]) for hit in response["hits"]["hits"])

    async def search(
        self, query: SearchQuery, *, facet_specs: tuple[FacetSpec, ...]
    ) -> SearchResultPage:
        body = _build_query_body(query, facet_specs=facet_specs)
        try:
            response = await asyncio.to_thread(
                self._client.search, index=self._index_name, body=body
            )
        except TransportError as exc:
            raise SearchIndexUnavailableError() from exc
        hits = tuple(
            SearchHitResult(document=_source_to_document(hit["_source"]))
            for hit in response["hits"]["hits"]
        )
        total = response["hits"]["total"]["value"]
        current_offset = int(query.cursor) if query.cursor else 0
        next_cursor = (
            str(current_offset + len(hits)) if current_offset + len(hits) < total else None
        )
        return SearchResultPage(hits=hits, next_cursor=next_cursor, total=total)

    async def facets(
        self, category_id: UUID | None, facet_specs: tuple[FacetSpec, ...]
    ) -> tuple[FacetResult, ...]:
        if not facet_specs:
            return ()
        aggs = {
            spec.field_code: {"terms": {"field": f"attributes.{spec.field_code}", "size": 50}}
            for spec in facet_specs
        }
        filters: list[dict[str, Any]] = [{"term": {"publicly_visible": True}}]
        if category_id is not None:
            filters.append({"term": {"category_id": str(category_id)}})
        body = {"query": {"bool": {"filter": filters}}, "size": 0, "aggs": aggs}
        try:
            response = await asyncio.to_thread(
                self._client.search, index=self._index_name, body=body
            )
        except TransportError as exc:
            raise SearchIndexUnavailableError() from exc
        results = []
        for spec in facet_specs:
            buckets = response.get("aggregations", {}).get(spec.field_code, {}).get("buckets", [])
            results.append(
                FacetResult(
                    field_code=spec.field_code,
                    buckets=tuple(
                        FacetBucketResult(value=str(b["key"]), count=b["doc_count"])
                        for b in buckets
                    ),
                )
            )
        return tuple(results)

    async def suggest(self, q: str, *, limit: int) -> tuple[SuggestionResult, ...]:
        q_latin, q_cyrillic = normalize_for_matching(q)
        body = {
            "query": {
                "bool": {
                    "filter": [{"term": {"publicly_visible": True}}],
                    "should": [
                        {"match_phrase_prefix": {"title": q}},
                        {"match_phrase_prefix": {"title_normalized_latin": q_latin}},
                        {"match_phrase_prefix": {"title_normalized_cyrillic": q_cyrillic}},
                    ],
                    "minimum_should_match": 1,
                }
            },
            "size": limit,
            "_source": ["title", "listing_id"],
        }
        try:
            response = await asyncio.to_thread(
                self._client.search, index=self._index_name, body=body
            )
        except TransportError as exc:
            raise SearchIndexUnavailableError() from exc
        return tuple(
            SuggestionResult(
                text=hit["_source"]["title"],
                type_="LISTING",
                ref_id=UUID(hit["_source"]["listing_id"]),
            )
            for hit in response["hits"]["hits"]
        )
