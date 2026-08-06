# search -- requirement traceability matrix (Task P-08)

Maps each requirement/invariant this module satisfies to its implementing code and the named test
that proves it. Mirrors `catalog/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-SRCH-001 | Full-text search over listing content | `OpenSearchIndexAdapter.search`/`_build_query_body`; `SqlalchemyFallbackIndexRepository.search` (trigram) | `test_api.py::test_I02_returns_a_matching_listing`; `integration/test_repository_live.py::test_trigram_search_matches_a_partial_misspelled_query` |
| FR-SRCH-002 | Faceted filtering, restricted to configured facet-eligible fields | `SearchUseCases.search`/`.facets`; `SearchConfigurationSnapshot.facet_field_codes` | `test_search_use_cases.py::TestFacetConfigDriven`; `test_api.py::test_I04_deep_object_filters_are_parsed_off_raw_query_params` |
| FR-SRCH-003 | Configurable sort vocabulary (relevance/recency/price asc/desc) | `search.domain.value_objects.SortOption`; `opensearch_index._SORT_FIELD_BY_OPTION` | `test_opensearch_index.py::test_I07_sort_option_selects_the_documented_sort_field` |
| FR-SRCH-004 | Cross-script (Latin<->Cyrillic) matching, both directions | `search.domain.cross_script.normalize_for_matching` | `test_cross_script.py` (54 tests, both directions, digraphs, apostrophe variants); `test_api.py::test_I03_cross_script_query_matches_latin_indexed_content`; `integration/test_opensearch_index_live.py::test_cross_script_search_matches_a_cyrillic_query_against_latin_content` |
| FR-MAP-001 | Listings carry a pre-geocoded location | `ListingSearchDocument.location` (`GeoLocation`, carried verbatim from the event payload) | `test_search_document.py` |
| FR-MAP-003 | Geo/radius search | `search.domain.query.GeoFilter`; `SqlalchemyFallbackIndexRepository._geo_bounding_box`; `opensearch_index._build_query_body`'s `geo_distance` clause | `integration/test_repository_live.py::test_geo_bounding_box_includes_a_nearby_listing`/`test_geo_bounding_box_excludes_a_far_away_listing`; `test_opensearch_index.py::test_I06_geo_filter_becomes_a_geo_distance_clause`; `integration/test_opensearch_index_live.py::test_geo_radius_search_finds_a_nearby_listing` |
| NFR-REL-002 | If OpenSearch is unavailable, fall back to a basic PostgreSQL query, no error | `SearchUseCases.search`/`.facets`/`.suggest` (`DegradationPolicy [P]`) | `test_search_use_cases.py::TestDegradationPolicy`; `test_api.py::test_I07_falls_back_to_postgres_and_reports_degraded_true_when_the_index_is_unavailable` |
| NFR-PERF-001 | Search p95 < 500ms | N/A in this sandbox -- no live OpenSearch/Postgres to benchmark against; `_build_query_body`/`SqlalchemyFallbackIndexRepository.search` are both single-round-trip, index-backed queries (GIN trigram, geo btree, OpenSearch's own scoring), no N+1 pattern anywhere in the query path | Deferred to a CI/staging environment with real datastores -- flagged, not silently skipped |

## Domain invariants (DDD Sec 9 / BC-05)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-17 | Promoted search results are always labelled and never exceed the configured per-page cap | `search.domain.ranking.apply_promotion_cap` | `test_ranking.py` (9 tests: zero cap, partial cap, no re-ordering, no organic removal, negative-cap guard); `test_search_use_cases.py::TestPromotionCap` |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| DEC-09/DEC-19 | Cross-script matching via a symmetric normalizer applied at both index and query time | `search.domain.cross_script.normalize_for_matching` | `test_cross_script.py::TestNormalizeForMatchingSymmetry` |
| DEC-12 | Ranking blends relevance + recency + capped, labelled promotion boost sourced from Billing | `opensearch_index._build_query_body`'s `function_score`; `apply_promotion_cap` | `test_opensearch_index.py::test_I08_promoted_documents_get_a_function_score_boost_not_a_hard_reorder`; `test_ranking.py` |
| DEC-21 | Configuration is data -- no hardcoded facet/sort/cap default | `search.domain.ranking.apply_promotion_cap`'s `cap` parameter; `ConfigurationSearchConfigurationAdapter` | `test_configuration_adapter.py` |
| X-02 | Search learns about listings solely through published events, never a static import | `search.infrastructure.event_projection`; `search-scope`/`cross-module-search` import-linter contracts | `test_boundary_import.py` (static + deliberate-violation-then-revert) |
| X-03 | Promotion/verification badge state locally projected from Billing/Profiles events | `IndexingUseCases.apply_promotion`/`clear_promotion`/`apply_verified_badge` | `test_indexing_use_cases.py::TestPromotionProjection`/`TestVerifiedBadgeFanOut`; `test_event_projection.py::TestEntitlementRouting`/`TestVerifiedBadgeRouting` |
| DM-06 | Deleted is a state, never a row removal | `IndexingUseCases.update_listing_visibility` (`ListingDeleted` -> `publicly_visible=false`) | `test_indexing_use_cases.py::test_I05_deleted_is_represented_as_publicly_visible_false_not_a_row_removal` |
| Logical Sec 18 | Idempotent event consumption via ProcessedEvent ledger | `search.infrastructure.event_projection`'s handlers, each wrapped in `idempotent_consume` | `test_event_projection.py::TestIdempotency` (fast tier, `FakeIdempotentSession`); `integration/test_event_projection_live.py::test_listing_published_redelivery_applies_the_projection_once` (real Postgres `INSERT ... ON CONFLICT`) |
| DB Architecture Sec 12 | Full reindex = replay from the owners' data via their interfaces/events; projection fully rebuildable | `OpenSearchIndexAdapter.delete_index`; `SqlalchemyProjectionCheckpointRepository.reset` | `integration/test_event_projection_live.py::test_projection_rebuild_is_deterministic` (discard + replay, byte-for-byte equivalent projection) |
| SAD Sec 8.1 | search imports ONLY shared_kernel + configuration | `tools/importlinter.cfg` `search-scope`/`cross-module-search` contracts | `test_boundary_import.py`; `lint-imports` (49 kept, 0 broken) |

## Validation checklist cross-reference (P-08 prompt)

| Checklist item | Evidence |
|---|---|
| search imports ONLY shared_kernel+configuration (import-linter + deliberate-violation-then-revert) | `test_boundary_import.py::test_I01_search_scope_contract_currently_passes`, `test_I02_a_deliberate_catalog_import_breaks_the_search_scope_contract_then_reverts` |
| Index written ONLY by the indexing worker | `SearchIndexPort.index_document`/`.delete_document` called only from `IndexingUseCases`; the request path (`SearchUseCases`) only ever calls `.search`/`.facets`/`.suggest` |
| Projection fully rebuildable | `integration/test_event_projection_live.py::test_projection_rebuild_is_deterministic` |
| Indexing idempotent | `test_event_projection.py::TestIdempotency`; `integration/test_event_projection_live.py::test_listing_published_redelivery_applies_the_projection_once` |
| Cross-script matching works both directions | `test_cross_script.py` (54 tests); `test_api.py::test_I03_cross_script_query_matches_latin_indexed_content` |
| Facets/sorts entirely from SearchConfiguration snapshot | `test_search_use_cases.py::TestFacetConfigDriven`; `test_configuration_adapter.py` |
| Paid ranking blended and CAPPED | `test_ranking.py`; `test_search_use_cases.py::TestPromotionCap` |
| PostgreSQL trigram fallback works | `integration/test_repository_live.py::test_trigram_search_matches_a_partial_misspelled_query` |
| Search p95 <500ms | Deferred -- no live datastores in this sandbox; see NFR-PERF-001 row above |
| opensearch-py confined to infrastructure/ | `provider-sdk-confined-to-infrastructure` import-linter contract KEPT; `opensearchpy` imported only in `opensearch_index.py` |
| Every search OpenAPI operation implemented, contract conformance green | `test_api.py` (13 tests across all 4 operations); `tools/check_contract_drift.py` reports zero drift on any `/search*` route (its overall exit is non-zero only due to a pre-existing, unrelated `configuration` admin-router drift, already documented in `catalog/README.md`'s own "Known gaps") |
| Coverage floors met (domain/app >=90%, overall >=80%) | Domain 100%, application 97.53% (combined 98.80%) -- see README "Coverage / quality gates" |
| mypy --strict / ruff / import-linter clean | See README "Coverage / quality gates" |
