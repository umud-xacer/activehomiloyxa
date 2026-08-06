# ADR-0005: Add the three unrepresented closed-vocabulary metric events to the frozen event catalogue

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-07-14

**Author**: Claude Sonnet 5, drafting under Task P-15 (Analytics & Audit) at the explicit
direction of the repository owner, after surfacing the conflict below rather than silently
resolving it.

## Context

DDD Domain Model §5.13 names the v1 closed metric vocabulary (DEC-06/BRULE-20/I-23) as exactly
eight keys: `ListingViewed`, `ContactButtonClicked`, `PhoneRevealed`, `ChatInitiated`,
`FavoriteAdded`, `PremiumListingStat`, `BannerImpressionRecorded`, `BannerClickRecorded`.

`contracts/events/` (frozen, Task P-01) — "the authoritative v1 event catalogue" per its own
docstring — defines event classes for only five of the eight: `PhoneRevealed`/`ChatInitiated`
(`messaging.py`), `FavoriteAdded` (`catalog.py`), `BannerImpressionRecorded`/
`BannerClickRecorded` (`ads.py`). Three keys have no corresponding event class anywhere in
`contracts/events/`, and no module publishes them today:

- **`ListingViewed`** — DDD §5.3 (catalog's own aggregate section) names a `ViewRecordingPolicy`
  explicitly: *"emits a ListingViewed metric on detail view (FR-ADV-010)"* — catalog's own
  domain model already names this policy by this exact event name. `catalog`'s real P-07
  implementation (`interfaces/routers.py::get_listing`) has no such call; `catalog/README.md`'s
  own "Known gaps" #3 already flags the absence, attributing it to analytics ("Analytics-owned
  ... outside this module's declared dependency set").
- **`ContactButtonClicked`** — named in FR-ANALYTICS-001, DEC-06, and DDD §5.13's own metric
  list, but never given an event class or a producing call site anywhere.
- **`PremiumListingStat`** — same: named in FR-ANALYTICS-001/DEC-06/DDD §5.13, no event class, no
  producer.

This is the same class of gap ADR-0001 already resolved for BC-06 (media): DDD §6's own event
catalogue table (the literal "Context | Event | Emitted when | Principal consumers" table) has
no row for any of these three names either — confirmed by direct inspection, the same omission
ADR-0001 documents for media. Task P-15 (this task)'s own brief assumes analytics "consumes the
metric events already being emitted by catalog (views, ...)" — an assumption this repository's
actual state does not support for these three keys specifically.

Surfaced to the repository owner via three options (build consumers against synthetic events
only and leave the contract untouched; also freeze the three event classes now via this ADR;
stop building ingestion for the three keys entirely, deviating from the Domain Model's own
8-key list). The owner's explicit direction: **draft this ADR and add the three event classes
now** — the schema should exist and be frozen, even though wiring the real `outbox.append()`
call inside catalog's own use cases remains a separate, future task (out of P-15's declared
scope, which is `apps/backend/src/analytics/` only, per Absolute Architecture Rule 8/AIR-01 —
"do not modify another `src/<module>` as a side effect").

## Decision

Freeze three new event classes in `contracts/events/catalog.py`, following the exact
`EventEnvelope`-subclass pattern every other event in that file already uses. All three are
catalog-owned: `ListingViewed` per DDD §5.3's own `ViewRecordingPolicy` attribution;
`ContactButtonClicked` and `PremiumListingStat` by the same reasoning — both are listing-detail-
page engagement facts on catalog's own `Listing` aggregate, occurring at the same call site
(`getListing`) `ListingViewed` does, and catalog already owns the `PromotionMarker` VO
`PremiumListingStat` reports on (DDD §5.3: `PromotionMarker (Premium/Featured/TopPlacement with
validity — projected from entitlements)`) — never messaging's, since `PhoneRevealed`/
`ChatInitiated` already cover messaging's own, more specific downstream actions:

- **`ListingViewed`** — emitted when: a listing's detail view renders (FR-ADV-010). Principal
  consumer: Analytics. Payload (once a producer exists): `listingId`, `viewerUserId` (nullable —
  anonymous views are valid).
- **`ContactButtonClicked`** — emitted when: a user clicks the listing detail page's "contact
  seller" call-to-action, prior to choosing a specific channel (phone reveal or chat — both
  already have their own, more specific metric). Principal consumer: Analytics. Payload:
  `listingId`, `userId` (nullable).
- **`PremiumListingStat`** — emitted when: an engagement fact occurs on a listing currently
  carrying an active `PromotionMarker` (Premium/Featured/TopPlacement). Principal consumer:
  Analytics. Payload: `listingId`, `promotionKind`.

`contracts/events/__init__.py`'s `EVENT_CATALOGUE` grows from 53 to 56 entries;
`contracts/tests/test_event_catalogue.py`'s `DDD_SEC_6_EVENT_NAMES` oracle set is updated to add
a comment block with these three names under `# BC-03` and the `== 56` count, pointing back to
this ADR, mirroring exactly how ADR-0001's own BC-06 block is recorded there.

This ADR does **not** wire a real producer. `catalog/application/listing_use_cases.py` and
`catalog/interfaces/routers.py::get_listing` are untouched by this change — freezing the event
schema is this ADR's only scope. `analytics/infrastructure/event_projection.py`'s consumer
function for these three keys is built and fully tested against synthetic `EventEnvelope`s in
Task P-15's own test suite, exactly as `handle_media_event`/`handle_ads_event` were built ahead
of their own real producers in earlier tasks, but is not wired to a live dispatcher in
`composition_root.py` against catalog's outbox — `catalog`'s outbox already has no live drain
path for these event types, so there is nothing to wire against yet. A future task closes this
gap in two steps: (1) add the actual `outbox.append(ListingViewed(...))` /
`ContactButtonClicked(...)` / `PremiumListingStat(...)` calls to catalog's own use cases (a
`catalog`-module change, AIR-01), and (2) route catalog's outbox through analytics' already-built
consumer in `composition_root.py`.

## Alternatives considered

1. **Do nothing; leave the three keys entirely unimplemented in analytics.** Rejected: deviates
   from DDD §5.13's own literal 8-key `ClosedVocabularyPolicy` list — the policy is meant to be
   the closed *ceiling* on what may be captured, not a description of what happens to have a
   producer today. A `ClosedVocabularyPolicy` that only recognizes 5 of the 8 documented keys
   would itself be a silently-narrowed, undocumented deviation.
2. **Build the consumer against synthetic events only, without touching `contracts/events/`.**
   Considered, and the smaller-blast-radius option (touches only `analytics/`, mirrors the
   media/ads precedent exactly) — but leaves the event *schema itself* unfrozen, meaning a future
   task wiring the real producer would still need to draft this exact ADR before it could act.
   The repository owner directed doing it now instead, since the schema question is fully
   answerable today (unlike the producer-wiring question, which depends on a future task's own
   scope).
3. **Route `ContactButtonClicked`/`PremiumListingStat` through `messaging`/`ads` instead of
   `catalog`.** Rejected: `PhoneRevealed`/`ChatInitiated` already cover messaging's own specific
   contact actions; `ContactButtonClicked` is the generic, prior-to-channel-choice click that
   only makes sense as a listing-detail-page (catalog) fact. `PremiumListingStat` reports on
   catalog's own `PromotionMarker`, not an ads banner-campaign concept.

## Consequences

- `contracts/events/catalog.py` (three new classes) and `contracts/events/__init__.py` (registry
  entries) are both touched — an interface-change event per Playbook §18, which is why this ADR
  exists rather than a silent edit.
- `contracts/tests/test_event_catalogue.py` is updated in the same change (not a separate PR),
  per `contracts/README.md`'s amendment-process rule 4.
- `contracts/README.md`'s own "Gaps resolved by ADR" section gains an entry recording that this
  gap is now resolved by this ADR.
- This ADR does **not** itself edit DDD Domain Model v1.0 or SAD v1.0 (immutable source documents
  outside version control here, per Playbook §18's governance note). This ADR is the durable
  record of *why* `contracts/` now differs from the currently-published DDD §6 table, pending
  that re-versioning.
- `catalog/README.md`'s "Known gaps" #3 remains accurate and unedited by this ADR — it already
  correctly attributes the missing data to analytics; it is not re-opened here, since wiring the
  real producer is still out of both P-07's (already merged) and P-15's (this task) declared
  scope.

## Approved-document references touched

- DDD Domain Model v1.0 §5.3 (catalog's `ViewRecordingPolicy`/`PromotionMarker`), §5.13
  (`ClosedVocabularyPolicy`'s 8-key list), §6 (event catalogue — gains three BC-03 rows).
- SRS v1.0 FR-ADV-010, FR-ANALYTICS-001.
- Baseline v1.1 DEC-06.
- `contracts/README.md` ("Gaps resolved by ADR" section, amendment process).
- Absolute Architecture Rule 8/AIR-01 (no side-effect modification of another module) — the
  reason the producer-side wiring is explicitly deferred, not attempted here.
