# ADR-0011: Add a `SOLD` listing lifecycle state and a `ListingSold` event

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-08-25

**Author**: Claude Sonnet 5, at the explicit direction of the repository owner ("Sotildi deb
belgilash" / "Mark as Sold" feature request), after shipping the code change first (commit
`c030232`) and only surfacing this ADR while closing a separate coverage-floor gate (QG-04) that
happened to walk through `contracts/events/__init__.py` and notice `ListingSold` was never
registered there — a real process gap this ADR also corrects, not just documents.

## Context

Unlike ADR-0001/ADR-0005 (both resolving a pre-existing mismatch between an already-approved
document and the frozen `contracts/` schema), this ADR records a genuinely **new** capability the
repository owner asked for directly, with no prior mention in DDD Domain Model v1.0: a seller
needs to mark a listing "sold" — removed from public catalog/search, kept in the seller's own
listings view, and still resolvable (not 404) at its own detail URL for anyone who already has the
link, showing a "sotilgan" (sold) badge.

DDD Domain Model §5.3 documents `LifecycleState [P]` as DEC-14's "fixed seven-state machine"
(`DRAFT`, `PENDING_VERIFICATION`, `PUBLISHED`, `EDITED`, `SUSPENDED`, `ARCHIVED`, `DELETED`) and
§6's event catalogue table has no BC-03 row for anything resembling a sale. Implementing the
feature required widening both:

- `catalog.domain.value_objects.LifecycleState` gained an eighth value, `SOLD`, reachable only
  from `PUBLISHED`/`EDITED` (`Listing.mark_sold`), and `TransitionKind` gained `SELL`
  (`catalog.listing_transition.transition_kind` CHECK, widened via migration `d4e1a9c2f6b7`).
- `contracts/events/catalog.py` gained `ListingSold` — deliberately NOT a reuse of `ListingArchived`
  (notifications' `queue_for_event` looks up a template by `event_type` literally, so reusing
  another event's name would render that event's own message text for a "sold" transition; the
  class's own docstring already recorded this reasoning at the point it was added).

The event class was added and correctly wired into `search`'s and `notifications`' own
event-type sets (both already treat it exactly like the five existing visibility-only events:
`ListingSuspended`/`ListingArchived`/`ListingDeleted`/`ListingExpired`/`ListingRenewed`), but
`contracts/events/__init__.py`'s `EVENT_CATALOGUE` registry — the actual "no event missing, no
event invented" oracle `contracts/tests/test_event_catalogue.py::test_I01_event_catalogue_
matches_ddd_sec_6_exactly` checks against — was never updated. This is why that test kept passing
despite the gap: `configuration.domain.whitelist.EVENT_KEYS` is checked for equality against
`EVENT_CATALOGUE.keys()`, not against every class literally defined in `catalog.py`, so an event
present in the module but absent from both the registry and the whitelist is invisible to every
existing drift check simultaneously. Caught only while investigating an unrelated QG-04
(domain/application coverage floor) gap that happened to walk through this exact file.

## Decision

1. **Widen DEC-14's seven-state machine to eight** (`catalog.domain.value_objects.LifecycleState.
   SOLD`), following the exact precedent `contracts/events/catalog.py`'s own ADR-0005 note already
   set for extending a "frozen" vocabulary for a real product need — not a reinterpretation of
   DEC-14, a documented, deliberate widening of it.
2. **Register `ListingSold` in `contracts/events/__init__.py`'s `EVENT_CATALOGUE`** (import +
   dict entry, alongside the other BC-03 listing-lifecycle events) and **add it to
   `contracts/tests/test_event_catalogue.py`'s `DDD_SEC_6_EVENT_NAMES` oracle** (under a new `#
   BC-03 (ADR-0011 -- new feature, not in DDD Sec 6's published table)` comment, count `56 -> 57`),
   mirroring exactly how ADR-0001/ADR-0005 record their own additions there.
3. **Add `"ListingSold"` to `configuration.domain.whitelist.EVENT_KEYS`** so the notification
   system's own whitelist gate (I-16) recognizes it as a real, catalogued event key rather than an
   invisible one two independent checks both silently missed.

`SOLD`'s visibility behavior deliberately does NOT reuse `ARCHIVED`'s event or `is_publicly_
visible()`'s own state set semantics beyond what's already true: `SOLD` stays excluded from
`_VISIBLE_STATES` (so it drops out of search/catalog listing exactly like `ARCHIVED` does), but
`catalog.interfaces.routers.get_listing` carries an explicit carve-out so a non-owner can still
resolve a `SOLD` listing's detail page (not 404) — the one behavioral difference from every other
non-visible state, and the reason `SOLD` could not simply have been implemented as a relabelled
`ARCHIVED`.

## Alternatives considered

1. **Reuse `ListingArchived` instead of a new `ListingSold` event.** Rejected: would misrepresent
   the transition to every real consumer of that event's own name (notifications' template
   lookup is literally keyed on `event_type`), producing a wrong-content notification ("your
   listing was archived") for an actually-sold listing.
2. **Leave the registry/whitelist/oracle gap unfixed since nothing currently consumes
   `ListingSold` from either list at runtime.** Rejected: the whole point of `EVENT_CATALOGUE` +
   `DDD_SEC_6_EVENT_NAMES` + `EVENT_KEYS` is to be the single source of truth a future change can
   trust without re-deriving it from every producer's own source by hand — leaving `ListingSold`
   invisible to all three would silently reproduce the exact "no event missing, no event invented"
   violation Task P-01 was built to prevent, for a real event with a real, already-shipped
   producer.

## Consequences

- `contracts/events/__init__.py` (one import, one registry entry) and
  `contracts/tests/test_event_catalogue.py` (`DDD_SEC_6_EVENT_NAMES` gains `ListingSold`, count
  `56 -> 57`) are both touched in the same change as this ADR, per `contracts/README.md`'s own
  amendment-process rule 4.
- `configuration/domain/whitelist.py`'s `EVENT_KEYS` gains `ListingSold`, and
  `apps/backend/tests/configuration/test_whitelist.py`'s zero-drift test now genuinely proves
  zero drift (it was previously passing only because both sides of the comparison independently
  omitted the same name).
- `contracts/README.md`'s "Gaps resolved by ADR" section gains an entry for this ADR.
- This ADR does **not** itself edit DDD Domain Model v1.0 (immutable source document outside
  version control here, per Playbook §18's governance note). This ADR is the durable record of
  *why* `contracts/`/`catalog/domain/` now differ from the currently-published DDD §5.3/§6
  content, pending that re-versioning.

## Approved-document references touched

- DDD Domain Model v1.0 §5.3 (`LifecycleState [P]`, DEC-14's seven-state machine — gains an
  eighth value), §6 (event catalogue — gains one BC-03 row).
- `contracts/README.md` ("Gaps resolved by ADR" section, amendment process).
