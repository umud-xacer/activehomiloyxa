# search -- module charter

STATUS (Task P-08): fully implemented across all four layers -- the `ListingSearchDocument`
read-model projection, the cross-script (Uzbek Latin<->Cyrillic) normalizer, the capped
promotion-ranking policy, the OpenSearch adapter + PostgreSQL degradation fallback, the idempotent
event-projection pipeline, and the four search-tagged API operations. This is the platform's only
true CQRS context -- it owns NO business aggregate, only a rebuildable projection. This README is
the module's public charter -- read it before working in this module (Playbook Sec 13). See
`TRACEABILITY.md` for the requirement -> code -> test matrix.

## Bounded context

- **Module**: `search` (BC-05, Core domain per DDD/SAD classification -- "the read model")
- **Responsibilities**: Index projection from events, full-text/faceted/geo-radius/cross-script
  query, capped paid ranking, PostgreSQL fallback when OpenSearch is unavailable.

## Owned aggregates / entities (DDD Sec 5.5)

- **`ListingSearchDocument` [P]** (`search.domain.search_document.ListingSearchDocument`) -- NOT
  an aggregate ("no invariants beyond idempotent upsert", Domain Model Sec 5.5's own words). Built
  exclusively from event-payload fields (X-02); `search.domain` never imports `catalog`, so every
  field here traces to a name a frozen `contracts/events/catalog.py` payload could plausibly
  carry. `.project()` constructs fresh from a content event; `.with_content`/`.with_visibility`/
  `.with_promotion`/`.with_verified_badge` each re-project exactly the fields their own producing
  event stream owns, leaving every other field untouched.
- **`CrossScriptNormalizationService` [P]** (`search.domain.cross_script`) -- pure Latin<->Cyrillic
  transliteration (DEC-19, FR-SRCH-004; SAD/SRS named risk R-2). Applied identically to indexed
  text (at projection time) and query text (at query time), so a query in either script matches
  content in either script, by construction, both directions.
- **`RankingService [P]` / `PromotionCapAndLabelPolicy [P mechanism, C value]`**
  (`search.domain.ranking.apply_promotion_cap`) -- I-17, BC-05's sole invariant: "Promoted search
  results are always labelled and never exceed the configured per-page cap." The relevance/
  recency BLEND is engine-specific (OpenSearch `function_score` / the fallback's own `ORDER BY`);
  the CAP is portable domain logic, applied identically regardless of which port served the
  request.
- **`DegradationPolicy [P]`** (`search.application.search_use_cases.SearchUseCases`) -- NFR-REL-002:
  falls back to the PostgreSQL trigram/geo path when OpenSearch is unavailable, never raising,
  always returning a (possibly reduced) result set with `degraded=true`.

## Public interface (`interfaces/`)

Four operations (`contracts/openapi.yaml`, tag `Search`): `searchListingsGet` (`GET /search`),
`searchListingsPost` (`POST /search`), `getFacets` (`GET /search/facets`), `suggest`
(`GET /search/suggest`). Every one declares `security: []` -- public, no `ActingUser` dependency
anywhere in this module. The `interfaces/` package is this module's *only* importable surface
(AIR-02). Nothing in `application/`, `domain/`, or `infrastructure/` may be imported by another
module, ever.

`SearchQueryPort` (the frozen P-01 `interfaces/ports.py` stub) is intentionally left
unimplemented, matching the established precedent across every other merged module (`catalog`,
`media`, `identity`): these P-01 Protocols are vestigial scaffolding that later real-implementation
tasks never actually implement via `class X(SomeQueryPort)` -- routers call a `XxxUseCases` class
directly instead (`search.interfaces.routers` calls `SearchUseCases`).

## THE CRITICAL BOUNDARY RULE (SAD Sec 8.1, `search-scope`/`cross-module-search`)

`search` may statically import ONLY `shared_kernel` and `configuration` (and only
`configuration.interfaces`). It must NOT import `catalog`, `billing`, `profiles`, or any other
module -- not even their `interfaces/`. Everything this module knows about listings, promotions,
and verification badges it learns from EVENTS carrying the data in their payloads. Verified two
ways:

1. **Static**: `lint-imports --contract search-scope` / `--contract cross-module-search` --
   currently `KEPT` (`tools/importlinter.cfg`).
2. **Behavioural**: `apps/backend/tests/search/test_boundary_import.py` writes a scratch module
   containing `import catalog` inside `search/infrastructure/`, re-runs the contract, asserts it
   now reports BROKEN, deletes the scratch file, and confirms the contract returns to KEPT --
   proving the check actually has teeth, not just that it currently happens to pass.

## Events consumed (`infrastructure/event_projection.py`)

Every handler wraps `backbone.idempotency.consumer.idempotent_consume` against search's own
`ProcessedEventRow` ledger, keyed on the producing event's `event_id`:

| Event(s) | Handler | Effect |
|---|---|---|
| `ListingPublished`, `ListingEdited` | `handle_listing_published`/`handle_listing_edited` | `IndexingUseCases.upsert_listing_content` -- content-bearing; raises `MalformedEventPayloadError` on a missing required field (see "Known gaps" #1) |
| `ListingSuspended`, `ListingArchived`, `ListingDeleted`, `ListingExpired`, `ListingRenewed` | `handle_listing_visibility_event` | `IndexingUseCases.update_listing_visibility` -- visibility-only, never raises. `ListingDeleted` is represented as `publicly_visible=false`, never a row removal (DM-06's "Deleted is a state" discipline) |
| `EntitlementActivated` | `handle_entitlement_activated` | `IndexingUseCases.apply_promotion` -- contract-only (BC-08/billing not yet built) |
| `EntitlementExpired`, `EntitlementRevoked` | `handle_entitlement_cleared` | `IndexingUseCases.clear_promotion` -- contract-only |
| `BusinessVerified` | `handle_verified_badge_applied` | `IndexingUseCases.apply_verified_badge(verified_badge=true)`, fanned out to every listing owned by the profile -- contract-only (BC-02/profiles not yet built) |
| `VerificationRejected`, `VerifiedBadgeExpired` | `handle_verified_badge_cleared` | Same fan-out, `verified_badge=false` |

`SearchConfigurationChanged` (configuration) has NO handler, deliberately: `ConfigurationSnapshotPort`
reads the `SearchConfiguration` snapshot LIVE on every query (no local cache/copy), so there is
nothing for this event to invalidate -- facet/sort/cap changes apply on the very next query, zero
propagation delay, a stronger guarantee than an eventually-consistent projection would give.

Publishes: none (read-model sink).

## The `EventHandler`-session gap, and how this module resolves it

`backbone.outbox.dispatcher.EventHandler` is `Callable[[EventEnvelope], Awaitable[None]]` -- it
carries no `AsyncSession`, yet every handler above needs one (for its own ledger insert).
Catalog's own two handlers (`handle_media_event`/`handle_entitlement_event`) take `session` as a
parameter and are, per `catalog/README.md`'s own "Known gaps", consequently never actually wired
to a dispatcher. `search.infrastructure.event_projection.make_search_event_handler` instead opens
and commits its OWN fresh session per event, independent of `OutboxDispatcher.drain_once()`'s own
outer session (which only claims/marks outbox rows, never sees the handler's effects). This is
safe, not merely convenient: a crash between the handler's own commit and the outer dispatcher
marking the row `DISPATCHED` causes harmless redelivery, made a no-op by `idempotent_consume`'s
ledger -- exactly matching `OutboxDispatcher`'s own documented at-least-once contract.
`search.infrastructure.worker.SearchIndexingWorker` wires one `OutboxDispatcher` per producing
module's outbox table (only `catalog`'s exists today; `billing_outbox_model`/`profiles_outbox_model`
stay `None` until BC-08/BC-02 ship), all sharing this one handler.

## The PostgreSQL fallback table is search-owned, not `catalog.listing`

Physical DB Design's own text places the fallback's trigram/geo indexes "on `catalog.listing`" --
this task's CRITICAL BOUNDARY RULE and its Excluded-scope line ("any import of catalog") make that
literal placement impossible without violating AIR-01 and ABSOLUTE ARCHITECTURE RULE 3 ("No
cross-module database access, ever"). Resolution: search owns a small denormalised copy
(`search.listing_fallback_document`), populated by the SAME idempotent indexing pipeline that
writes to OpenSearch (`IndexingUseCases` writes both sinks on every projection event) -- one
projection, two sinks, never a second, independently-updated source of truth. The trigram GIN and
geo bounding-box indexes are relocated here, matching the Physical DB Design's own INDEX STRATEGY
exactly, just on search's own table.

## Cross-script matching (FR-SRCH-004, DEC-19, SAD/SRS risk R-2)

`search.domain.cross_script.normalize_for_matching` computes `(as_latin, as_cyrillic)` once, at
projection time (stored as `title_normalized_latin`/`title_normalized_cyrillic` shadow fields) and
again, identically, on the query string at search time. Handles the flagged apostrophe edge case
for the oʻ/gʻ digraphs (six known Unicode "apostrophe-like" variants folded to one canonical
marker before matching) without guessing a missing apostrophe (a real data-quality issue, left
uncorrected rather than risking a false-positive fold).
`apps/backend/tests/search/test_cross_script.py` is the thorough, both-directions test set this
risk demands (54 tests: every digraph, every apostrophe variant, idempotency, mixed-script input,
symmetry both directions).

## Ranking and the promotion cap (DEC-12, I-17)

Blend (BM25 relevance + recency + a `function_score` promotion boost) is engine-specific query
construction (`opensearch_index._build_query_body`) or the fallback's own `ORDER BY`. The CAP
itself -- never let more than `promotion_page_cap` promoted results survive one page -- is pure,
portable domain logic (`search.domain.ranking.apply_promotion_cap`), applied ONCE, in
`SearchUseCases.search`, uniformly regardless of which port produced the ranked candidates. A
dropped promoted candidate is removed from its own position, never bumped elsewhere and never used
to displace an organic result beyond what the rules allow.

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: `shared_kernel`, `configuration.interfaces` only.

MUST NOT import: every other module, including `catalog` -- learns about listings solely through
the published event stream (X-02), never a static import. Re-declares `ListingType`/
`PromotionKind` itself (`search.domain.value_objects`) rather than importing catalog's own
versions -- a projected value's *shape* crossing an event payload is not the same thing as
depending on the producing module's code.

## Migrations

`infrastructure/migrations/versions/a74b1a3366d5_search_create_projection_schema.py` creates
`search.projection_checkpoint`, `search.listing_fallback_document` (GIN trigram index on `title`
via `postgresql_where=publicly_visible`, btree geo index, owner-profile index), `search.
processed_event`. Also runs `CREATE EXTENSION IF NOT EXISTS pg_trgm` -- this migration is the
first user of `pg_trgm` in the codebase. Hand-written, not `alembic revision --autogenerate`
(matches catalog's own precedent reasoning).

## Known gaps (flagged, not silently worked around)

1. **RESOLVED (Task P-20)**: catalog's own `ListingUseCases._listing_payload()` (Task P-07) used
   to send only `listingId`/`ownerUserId`/`categoryId`/`lifecycleState`/`isFlagged`/`expiresAt`/
   `reason` on every listing event -- NOT the `title`/`description`/`categoryPath`/`listingType`/
   `attributes`/`price`/`location`/`slug`/`publishedAt` that `ListingSearchDocument` documentedly
   needs (DB Architecture Sec 3.5: "rebuilt from Catalog events: text fields..."), so
   `handle_listing_published`/`handle_listing_edited` never successfully indexed a real listing.
   P-20 (cross-module integration hardening) widened `_listing_payload()` to carry every field
   these handlers require, purely additively -- the five visibility-only handlers and every other
   consumer of catalog's outbox read only the fields they already expect and are unaffected. Also
   now carries the listing's current `promotion` projection (see item 10, below).
2. **Billing/profiles projections are contract-only**: `EntitlementActivated`/`EntitlementExpired`/
   `EntitlementRevoked` (BC-08) and `BusinessVerified`/`VerificationRejected`/`VerifiedBadgeExpired`
   (BC-02) have no real producer yet -- both modules are built in later tasks. Handlers are fully
   built and tested against synthetic `EventEnvelope`s (unit + `integration/
   test_event_projection_live.py`'s pattern), with a defensible, documented reading of each
   event's assumed payload shape, pending each module's own frozen contract.
3. **`GeocodingPort` has zero callers**: the Domain Model names this port on BC-05, but no use case
   in this task calls it -- every listing event payload already carries a pre-geocoded
   `GeoLocation` (captured upstream by whoever authored the listing, per FR-MAP-001), so search
   never geocodes on its own read-only projection path. Declared for interface completeness/
   traceability per the Domain Model's own port list, not silently dropped.
4. ~~**`Facet.label` echoes the field code, not an authored translation**~~ -- **CLOSED**. The
   label does not live one level below on the `FormField` after all: `SearchConfigurationContent.
   facets` carries its own `LocalizedText` per facet, authored beside the field code on the very
   same document, and the adapter was simply dropping it while reading `field_code`.
   `SearchConfigurationSnapshot` now carries `(field_code, label)` pairs and `SearchUseCases`
   attaches them on both the `/search` and `/search/facets` paths -- the latter mattering most,
   since it is the one the filter panel actually reads and its own docstring already claimed the
   dimension's "field_code/label" came from the snapshot. `_field_code_label` survives as the
   fallback for a facet configured without a label. Filter headings now read "Xonalar"/"Комнаты"/
   "Rooms" instead of `rooms`.
5. **OpenSearch integration tests never run in this repo's CI as currently configured**: `.github/
   workflows/ci.yml`'s QG-03 job spins up `postgres`/`redis` service containers but not
   `opensearch` -- `integration/test_opensearch_index_live.py` (gated on `OPENSEARCH_HOST`) will
   always self-skip there, same as locally without `scripts/dev-up.sh` running. The fast,
   no-cluster-needed equivalent of everything it covers (`_document_to_source`/
   `_source_to_document`/`_build_query_body`) lives in `test_opensearch_index.py` and DOES run in
   CI. **Consequence, found by Task P-20**: because this suite had genuinely never run against a
   real cluster before, `INDEX_MAPPING`'s `"attributes": {"type": "flattened"}` -- Elasticsearch's
   field-type name for arbitrary-JSON-as-queryable-leaves -- was never valid on real OpenSearch at
   all (OpenSearch's own equivalent, added natively, is named `flat_object`); every real call to
   `ensure_index` failed with `mapper_parsing_exception: No handler for type [flattened]`.
   **Follow-up, found by running the real cluster**: `flat_object` made `ensure_index` succeed
   but is not properly aggregatable in OpenSearch 2.19 -- a terms aggregation over
   `attributes.<field_code>` returns bucket keys like `java.lang.Object@5d7731b2`. Every facet
   panel therefore showed its dimension names with garbage values or, once those were discarded,
   none at all, and the resulting exception took the WHOLE query down the degradation path, so
   `degraded: true` was effectively permanent -- costing native geo, cross-script matching and
   `categoryId` scoping, all of which the fallback answers less well or not at all. `attributes`
   is now an ordinary `object` with a dynamic template typing each leaf `keyword`, and values are
   stringified on write so aggregation keys and `term` filters agree. Mapping explosion is not a
   risk here: the projection stores only the facet-eligible field codes selected in the
   SearchConfiguration snapshot (DB Architecture Sec 12), an admin-chosen set.

   P-20 fixed the mapping and, separately, three of this suite's own tests that called
   `adapter._client.indices.refresh(...)` directly with `await` even though `_client` is the sync
   `opensearchpy.OpenSearch` client `OpenSearchIndexAdapter` always wraps in `asyncio.to_thread`
   (also never caught, for the same reason). P-20 additionally wired a real OpenSearch service
   into CI's QG-03 job, so this entire suite -- and this class of defect -- is caught going
   forward instead of only self-skipping.
6. **Fixed, found and fixed during this task**: `opensearch_index._document_to_source` previously
   omitted the `promotion_entitlement_id` field entirely, so `_source_to_document` always fell back
   to `UUID(int=0)` on read -- every promoted document served from OpenSearch silently lost its
   real entitlement id (the PostgreSQL fallback path was never affected -- its own repository
   always round-tripped this field correctly). Fixed; regression-tested by
   `test_opensearch_index.py::test_I02_round_trips_a_promoted_documents_entitlement_id`.
7. **Pre-existing, unrelated, left untouched (AIR-01)**: `catalog.domain.value_objects`/
   `identity.domain.value_objects`'s already-merged `class X(str, Enum):` declarations violate
   ruff's `UP042` ("inherit from `enum.StrEnum` instead") -- five and four occurrences
   respectively, predating this task. `search`'s own new enums use `enum.StrEnum` directly and are
   fully clean; catalog's/identity's existing violations were not touched. Similarly, two
   pre-existing `RUF100` "unused noqa: SLF001" findings in `composition_root.py` (lines predating
   this task's edits, on `configuration`/`media` router imports) were confirmed via `git show
   HEAD` to already exist before this task's changes and were left untouched.
8. **Pre-existing integration-test skip-fixture ordering quirk**: running `apps/backend/tests/
   */integration/` locally without `POSTGRES_HOST` set errors (`MissingInfraConfigError`) rather
   than cleanly skipping via the `_skip_without_datastores` autouse fixture -- confirmed identical
   in catalog's own already-merged `integration/` suite (`apps/backend/tests/catalog/integration/`
   exhibits the exact same behaviour), so this is a codebase-wide, pre-existing pytest
   fixture-ordering characteristic, not something introduced by or specific to this task. CI sets
   `POSTGRES_HOST`, so this never surfaces there.
9. **Pre-existing, unrelated**: `tools/check_contract_drift.py` reconfirms `identity/README.md`'s/
   `catalog/README.md`'s own already-documented gap (`configuration`'s admin routers use
   snake_case path parameters where `contracts/openapi.yaml` specifies camelCase) -- search's own
   four routes match the spec exactly and report zero drift; the `configuration` mismatch is
   unrelated to this task and was left untouched (AIR-01).
10. **RESOLVED (Task P-20), architecture decision recorded**: this module's own `handle_
    entitlement_activated`/`handle_entitlement_cleared` (direct billing -> search promotion
    consumers) were built and unit-tested but never wired to any dispatcher anywhere -- a second,
    confirmed integration defect alongside item 1's payload gap ("the promotion is reflected in
    ... search ranking" was silently non-functional). Two designs were possible (billing -> search
    directly, using these handlers; or billing -> catalog -> search, through the ordinary
    listing-content channel); the repository owner chose the latter, matching the frozen event
    contract's own `EntitlementActivated` docstring ("Principal consumers: Catalog
    (promotion/quota)..."). Implemented in `catalog.infrastructure.event_projection.
    handle_listing_promotion_event` (new) + `composition_root.make_billing_entitlement_fanout_
    handler`'s new sixth route -- `handle_entitlement_activated`/`handle_entitlement_cleared` in
    THIS module are consequently unreachable from any real dispatcher and are dead code by that
    decision. Left in place rather than deleted (a cross-module removal decision belongs to a
    follow-up task, not a side effect of this one) but flagged here explicitly rather than left to
    look like live, exercised code.

## Coverage / quality gates (Task P-08 run)

157 tests (139 fast unit/API + 18 Postgres/OpenSearch-gated integration, `apps/backend/tests/
search/`), mypy --strict clean, ruff clean (search's own code -- pre-existing, unrelated
codebase-wide findings noted above), all 49 `tools/importlinter.cfg` contracts kept including a
deliberate-violation-then-revert proof of `search-scope`, domain coverage 100%, application
coverage 97.53% (combined domain+application 98.80%, both well above the 90% floor), bandit SAST
clean, no new dependencies added (`opensearch-py==3.2.0` was already pinned). The Postgres/
OpenSearch-gated integration tests are present and structurally correct but unexecutable in this
sandbox (no `POSTGRES_HOST`/`OPENSEARCH_HOST`), the same class of gap already documented for
P-05/P-06/P-07's own integration suites.

## Layout

```
search/
|-- interfaces/       # PUBLIC surface: routers, published ports, DTOs, event contracts
|-- application/      # use cases (commands/queries) + ports
|-- domain/           # aggregates, value objects, domain events, policies, invariants
|-- infrastructure/   # adapters: persistence, OpenSearch adapter, configuration adapter, outbox, worker, event projection
|-- README.md         # this file
`-- TRACEABILITY.md    # requirement -> code -> test matrix
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
