# ADR-0001: Add BC-06 (Media) asset-status events to the frozen event catalogue

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-07-11

**Author**: Claude Sonnet 5, drafting under Task P-06 (Media) at the explicit direction of the
repository owner, after surfacing the conflict below rather than silently resolving it.

## Context

`contracts/README.md` (written under Task P-01) documents a known, deliberate inconsistency
between two approved documents:

- **SAD §7.2**'s module-catalogue table lists media's (BC-06) public interface as
  `"MediaIntakePort, asset-status events"` — i.e. SAD asserts media publishes events.
- **DDD Domain Model §6** ("the authoritative v1 event catalogue") has no BC-06 row at all — no
  media event is named anywhere in that table.

P-01 resolved this, at the time, by matching DDD §6's literal table: `contracts/events/` has no
`media.py`, and `contracts/README.md` records the gap explicitly under "Two documented gaps (not
invented around)" rather than inventing an event name to satisfy SAD's wording.

Task P-06 (Media) now requires implementing this module for real, and its own deliverables
depend on an actual event mechanism existing:

- DDD §5.6 (BC-06's own aggregate section, which — unlike §6 — clearly describes BC-06 in
  detail) names `ScanStatus`/`ProcessingStatus` as core `MediaAsset` value objects and a
  `QuarantinePolicy` ("quarantined assets are never delivered").
- DDD's cross-context integration table (row **X-06**) states explicitly: *"{Catalog, Profiles,
  Ad-Serving} → Media / Synchronous interface + async status events (ACL) / Owners hold
  MediaAssetRef only; **Media pushes ScanCompleted/ProcessingCompleted status**; failures never
  block listing creation (QR-05)."* This is informal prose, not a frozen schema, but it is DDD's
  own text describing the same mechanism SAD names formally.
- The P-06 task brief itself requires: "Asset-status events... publishing... that other contexts
  can project," "a test proving the status-event is emitted via the outbox," and "consumers read
  status via events and never write MediaAsset state."
- Rule 5 of the platform's Absolute Architecture Rules: "cross-context integration is
  asynchronous via the transactional outbox (never dual-write)." Without an event, the only way
  for Catalog/Profiles/Ads to learn an asset's status is a synchronous read of `getMedia` on
  every poll — workable, but it is exactly the dual-write/synchronous-coupling pattern the outbox
  pattern exists to avoid, and it contradicts DDD's own X-06 row, which explicitly calls for
  "Synchronous interface **+ async status events**," not synchronous-only.

This is therefore not "inventing a new capability the documents never described" — DDD §5.6 and
DDD's own X-06 row, and SAD §7.2, all independently describe media pushing status via events.
The only artifact that is silent is DDD §6's summary table, which appears to have simply omitted
a BC-06 row when it was compiled (BC-06 is the only bounded context among rows BC-01–BC-04,
BC-07–BC-09, BC-11, BC-13 that owns a real aggregate with lifecycle transitions and has no
row at all — every other context that publishes nothing, e.g. `search`/`media`'s own DTO-only
neighbours, is a context that does not own a mutable aggregate in the first place).

## Decision

Amend DDD §6's event catalogue to add a BC-06 row, and freeze three media events in
`contracts/events/media.py`, following the exact `EventEnvelope`-subclass pattern every other
context's event file already uses (`identity.py`, `configuration.py`, etc.):

- **`MediaAssetAccepted`** — emitted when: an upload is registered as intake-valid (type/size
  checked) and admitted to the processing pipeline. Principal consumers: none in v1 (informational
  audit trail); reserved for a future task that wants to reflect "upload in progress" state.
- **`MediaAssetReady`** — emitted when: scanning and processing both complete successfully
  (`ScanStatus.CLEAN` + `ProcessingStatus.COMPLETED`); the asset becomes delivery-available.
  Principal consumers: Catalog, Profiles, Ads (per SAD's dependency table — the modules that will
  attach `MediaAssetRef`s in later tasks).
- **`MediaAssetRejected`** — emitted when: scanning quarantines the asset OR processing fails
  terminally; the asset never becomes delivery-available (QuarantinePolicy, I-20). Principal
  consumers: Catalog, Profiles, Ads (so an owning context can surface "image failed" instead of
  waiting forever).

These names formalize DDD's own X-06 prose ("ScanCompleted/ProcessingCompleted") into the
Accepted/Ready/Rejected vocabulary already used by every other v1 event family for a comparable
three-state outcome (cf. `VerificationRequested`/`BusinessVerified`/`VerificationRejected` in
BC-02), for internal consistency with the rest of the frozen catalogue rather than introducing a
new naming convention.

`contracts/events/__init__.py`'s `EVENT_CATALOGUE` grows from 50 to 53 entries;
`contracts/tests/test_event_catalogue.py`'s `DDD_SEC_6_EVENT_NAMES` oracle set is updated to
add a `# BC-06` block with these three names and the `== 53` count, with a comment pointing back
to this ADR so the discrepancy with the currently-published DDD §6 table is traceable rather than
silently patched.

## Alternatives considered

1. **Do nothing; media publishes no event in v1** (honor DDD §6's literal table as-is). Rejected:
   leaves P-06's own required deliverables (outbox event test, "consumers read status via events"
   validation-checklist item) unsatisfiable, and leaves Catalog/Profiles/Ads with no non-polling
   way to learn asset status, contradicting DDD's own X-06 row and Absolute Architecture Rule 5.
2. **Synchronous-only status** (Catalog etc. call `getMedia` directly instead of consuming an
   event). Rejected: DDD's X-06 row explicitly specifies "Synchronous interface **+** async status
   events," not synchronous-only; polling on every check is a weaker, chattier integration than
   the outbox pattern the rest of the platform uses uniformly, and it still would not satisfy the
   task's own explicit "prove the event is emitted via the outbox" deliverable.
3. **A single combined `MediaAssetStatusChanged` event carrying the new status as a payload
   field**, instead of three distinct event types. Rejected for consistency with the rest of the
   catalogue: every other multi-outcome family in `contracts/events/` (verification, listing
   lifecycle, banner campaign) uses one event type per named transition rather than one generic
   event with a status field, and `contracts/errors/problem.py`-style "closed vocabulary in the
   type system, not a string field" is the established idiom here.

## Consequences

- `contracts/events/media.py` (new file) and `contracts/events/__init__.py` (registry entry) are
  both touched — an interface-change event per Playbook §18, which is why this ADR exists rather
  than a silent edit.
- `contracts/tests/test_event_catalogue.py` is updated in the same change (not a separate PR),
  per `contracts/README.md`'s amendment-process rule 4 ("every module that consumes the changed
  shape updates in the same PR").
- `contracts/README.md`'s own "Two documented gaps" section is updated to record that this gap is
  now resolved by this ADR, rather than leaving stale text describing a gap that no longer exists.
- This ADR does **not** itself edit DDD Domain Model v1.0 or SAD v1.0 (those are immutable source
  documents outside version control here, per Playbook §18's governance note: "the affected
  approved documents are re-versioned through change control" as a separate, human-owned step).
  This ADR is the durable record of *why* `contracts/` now differs from the currently-published
  DDD §6 table, pending that re-versioning.

## Approved-document references touched

- DDD Domain Model v1.0 §5.6 (BC-06 aggregate), §6 (event catalogue — gains a BC-06 row), X-06
  (cross-context integration table).
- SAD v1.0 §7.2 (module catalogue, media's public-interface column).
- `contracts/README.md` ("Two documented gaps" section, amendment process).
- Absolute Architecture Rule 5 (async cross-context integration via the outbox).
