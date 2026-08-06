"""Shared fixtures for `search`'s fast (no-DB, no-OpenSearch) unit + API tests: in-memory fakes for
every port `application/ports.py` declares, mirroring `apps/backend/tests/catalog/conftest.py`'s
pattern exactly."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy import Insert
from sqlalchemy.dialects.postgresql import dialect as pg_dialect
from sqlalchemy.ext.asyncio import AsyncSession

from search.application.exceptions import SearchIndexUnavailableError
from search.application.ports import (
    FacetResult,
    FacetSpec,
    SearchConfigurationSnapshot,
    SearchHitResult,
    SearchResultPage,
    SuggestionResult,
)
from search.domain import ListingSearchDocument, SearchQuery, SortOption


@dataclass
class FakeSearchIndex:
    """Implements `search.application.ports.SearchIndexPort` -- an in-memory OpenSearch stand-in.
    `unavailable=True` makes every query method raise `SearchIndexUnavailableError`, exercising
    `SearchUseCases`' own `DegradationPolicy [P]` fallback switch without a real OpenSearch."""

    documents: dict[UUID, ListingSearchDocument] = field(default_factory=dict)
    unavailable: bool = False
    suggestions: tuple[SuggestionResult, ...] = ()
    facet_results: tuple[FacetResult, ...] = ()

    async def index_document(self, document: ListingSearchDocument) -> None:
        self.documents[document.listing_id] = document

    async def delete_document(self, listing_id: UUID) -> None:
        self.documents.pop(listing_id, None)

    async def get_document(self, listing_id: UUID) -> ListingSearchDocument | None:
        return self.documents.get(listing_id)

    async def find_listing_ids_by_owner_profile(self, owner_profile_id: UUID) -> tuple[UUID, ...]:
        return tuple(
            doc.listing_id
            for doc in self.documents.values()
            if doc.owner_profile_id == owner_profile_id
        )

    async def search(
        self, query: SearchQuery, *, facet_specs: tuple[FacetSpec, ...]
    ) -> SearchResultPage:
        if self.unavailable:
            raise SearchIndexUnavailableError
        candidates = [doc for doc in self.documents.values() if doc.publicly_visible]
        if query.q:
            needle = query.q.lower()
            candidates = [
                doc
                for doc in candidates
                if needle in doc.title_normalized_latin or needle in doc.title_normalized_cyrillic
            ]
        if query.category_id is not None:
            candidates = [doc for doc in candidates if doc.category_id == query.category_id]
        if query.listing_type is not None:
            candidates = [doc for doc in candidates if doc.listing_type == query.listing_type]
        if query.verified_only:
            candidates = [doc for doc in candidates if doc.verified_badge]
        # promoted-first ordering, mirroring a relevance+promotion-blended OpenSearch score --
        # `apply_promotion_cap` (I-17) is exercised by `SearchUseCases`, not this fake.
        candidates.sort(key=lambda doc: doc.promotion is None)
        hits = tuple(SearchHitResult(document=doc) for doc in candidates[: query.limit])
        return SearchResultPage(hits=hits, next_cursor=None, total=len(candidates))

    async def facets(
        self, category_id: UUID | None, facet_specs: tuple[FacetSpec, ...]
    ) -> tuple[FacetResult, ...]:
        if self.unavailable:
            raise SearchIndexUnavailableError
        return self.facet_results

    async def suggest(self, q: str, *, limit: int) -> tuple[SuggestionResult, ...]:
        if self.unavailable:
            raise SearchIndexUnavailableError
        return self.suggestions[:limit]


@dataclass
class FakeFallbackIndex:
    """Implements `search.application.ports.FallbackIndexPort` -- an in-memory stand-in for
    search's own Postgres `listing_fallback_document` table."""

    documents: dict[UUID, ListingSearchDocument] = field(default_factory=dict)

    async def upsert_document(self, document: ListingSearchDocument) -> None:
        self.documents[document.listing_id] = document

    async def delete_document(self, listing_id: UUID) -> None:
        self.documents.pop(listing_id, None)

    async def search(self, query: SearchQuery) -> SearchResultPage:
        candidates = [doc for doc in self.documents.values() if doc.publicly_visible]
        if query.q:
            needle = query.q.lower()
            candidates = [
                candidate for candidate in candidates if needle in candidate.title.lower()
            ]
        if query.category_id is not None:
            candidates = [
                candidate for candidate in candidates if candidate.category_id == query.category_id
            ]
        hits = tuple(SearchHitResult(document=doc) for doc in candidates[: query.limit])
        return SearchResultPage(hits=hits, next_cursor=None, total=None)


class FakeConfigurationSnapshotPort:
    """Implements `search.application.ports.ConfigurationSnapshotPort`. Defaults to a small,
    representative facet/sort/cap snapshot; tests override `.snapshot` for other shapes."""

    def __init__(self) -> None:
        self.snapshot = SearchConfigurationSnapshot(
            facet_field_codes=("condition", "rooms"),
            sort_options=(SortOption.RELEVANCE, SortOption.RECENCY, SortOption.PRICE_ASC),
            default_sort=SortOption.RELEVANCE,
            promotion_page_cap=2,
        )

    async def get_search_configuration(
        self, category_id: UUID | None
    ) -> SearchConfigurationSnapshot:
        return self.snapshot


class _FakeInsertResult:
    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount


class FakeIdempotentSession:
    """A minimal stand-in for `AsyncSession`, scoped ONLY to `backbone.idempotency.consumer.
    idempotent_consume`'s own `INSERT ... ON CONFLICT DO NOTHING` contract -- real
    `AsyncSession.execute` would need a live Postgres connection to run that construct (a
    dialect-specific `pg_insert(...).on_conflict_do_nothing(...)`, not portable to sqlite), which
    this test tier deliberately has none of. Compiles the statement (no DB round-trip) to read its
    bound `event_id`/`handler` params, and tracks `(event_id, handler)` pairs already seen to
    return `rowcount=0` on a repeat -- exactly the real INSERT's conflict semantics, just done in
    Python. `search/infrastructure/event_projection.py`'s handlers never call any other session
    method (the actual document writes go through `SearchIndexPort`/`FallbackIndexPort`, not this
    session), so this is sufficient to exercise their idempotency/routing contract at the fast
    tier -- the ledger row's own durability is covered by the (skipped-without-Postgres)
    integration tier instead."""

    def __init__(self) -> None:
        self.seen: set[tuple[Any, str]] = set()

    async def execute(self, stmt: Insert) -> _FakeInsertResult:
        params = stmt.compile(dialect=pg_dialect()).params  # type: ignore[no-untyped-call]
        key = (params["event_id"], params["handler"])
        if key in self.seen:
            return _FakeInsertResult(rowcount=0)
        self.seen.add(key)
        return _FakeInsertResult(rowcount=1)


@pytest.fixture
def fake_session() -> AsyncSession:
    # `FakeIdempotentSession` satisfies `idempotent_consume`'s own usage of `AsyncSession`
    # structurally (its only call is `.execute(...)`) but isn't a nominal `AsyncSession` subclass
    # -- cast at the fixture boundary once, rather than a `# type: ignore[arg-type]` at every one
    # of `test_event_projection.py`'s many `dispatch_search_event(fake_session, ...)` call sites.
    return cast(AsyncSession, FakeIdempotentSession())


@pytest.fixture
def fake_index() -> FakeSearchIndex:
    return FakeSearchIndex()


@pytest.fixture
def fake_fallback() -> FakeFallbackIndex:
    return FakeFallbackIndex()


@pytest.fixture
def fake_configuration() -> FakeConfigurationSnapshotPort:
    return FakeConfigurationSnapshotPort()
