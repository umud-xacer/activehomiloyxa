# analytics -- module charter

STATUS: implemented (Task P-15) -- the `AuditEntry` and `MetricEvent` immutable fact aggregates,
`ClosedVocabularyPolicy`, the `ListingStatistics`/`OperationalReport` projections, eight idempotent
event consumers, the partition-precreate scheduled job, and the two Administration-tagged
`contracts/openapi.yaml` operations this module owns (`queryAuditLog`/`getAdminReports`). This
README is the module's public charter -- read it before working in this module (Playbook Sec 13).

## Bounded context

- **Module**: `analytics` (BC-13, Generic domain per DDD/SAD classification)
- **Responsibilities**: the terminal event SINK of the entire platform -- consumes audit/metric
  facts, stores them immutably, projects them for reading. Commands nothing; nothing imports it
  (SAD Sec 8: `"analytics: shared_kernel (event sink)"`).

## Owned aggregates / entities (DDD Sec 5.13)

- **`AuditEntry`** (`domain/audit_entry.py`) -- an immutable fact: Actor, Action, Target,
  Timestamp, context payload (FR-AUDIT-001, I-22). `target_type`/`target_id`/`actor_user_id` are
  bare identifiers only, never dereferenced transactionally (Database Architecture Sec 3.12) --
  analytics stores exactly what the triggering event's own payload carried.
- **`MetricEvent`** (`domain/metric_event.py`) -- an immutable engagement fact from the closed v1
  metric vocabulary (DEC-06/BRULE-20/I-23): vocabulary key, subject refs (`listing_id`/`user_id`/
  `campaign_id`), timestamp, dedup key.

Both are plain (non-`frozen=True`) dataclasses with a hand-written `__setattr__`/`__delattr__`
override raising `ImmutableFactMutationError` -- `@dataclass(frozen=True)` cannot itself be
combined with a custom `__setattr__` (Python raises `TypeError` at class-definition time if you
try), so immutability here is implemented by hand rather than via the decorator. Construction
goes through a `create()` staticmethod using `object.__setattr__` to bypass the guard exactly
once, at build time.

## The closed metric vocabulary (DDD Sec 5.13, DEC-06/BRULE-20/I-23 -- this module's signature property)

Exactly eight keys, verified against the Domain Model's own literal list, no others:

```
ListingViewed, ContactButtonClicked, PhoneRevealed, ChatInitiated,
FavoriteAdded, PremiumListingStat, BannerImpressionRecorded, BannerClickRecorded
```

`domain/value_objects.py::MetricKey` (a `StrEnum`, persisted values SCREAMING_SNAKE_CASE to match
the Physical Database Design's own `metric_key` CHECK-constraint literals) is the closed set;
`ClosedVocabularyPolicy.validate` is the first-class domain guard every `MetricEvent.create` call
runs internally -- there is no path that stores a metric key outside the eight, proven by
`test_value_objects.py::test_closed_vocabulary_rejects_anything_outside_the_eight_keys` (this
module's signature test) and enforced a SECOND, independent time by the database's own
`ck_metric_event_metric_key` CHECK constraint (`test_repository_live.py::
test_closed_vocabulary_check_constraint_rejects_an_unknown_metric_key`).

## Three of the eight keys have no real producer yet (ADR-0005)

`ListingViewed`/`ContactButtonClicked`/`PremiumListingStat` had no event class anywhere in
`contracts/events/` before this task -- DDD Sec 6's own event catalogue table omitted them
despite Sec 5.13's own 8-key vocabulary and Sec 5.3's own `ViewRecordingPolicy` naming
`ListingViewed` explicitly. `docs/adr/0005-analytics-missing-metric-events.md` (drafted at the
repository owner's explicit direction) freezes all three as real event classes in
`contracts/events/catalog.py`, but does **not** wire a producer -- `catalog`'s own use cases are
untouched (AIR-01: this is an `analytics` task, not a `catalog` one). `infrastructure/
event_projection.py::handle_catalog_event` is built and fully tested for all three keys against
synthetic `EventEnvelope`s (`integration/test_event_projection_live.py`), and IS wired live in
`composition_root.py` against catalog's real outbox -- so the moment a future task adds the
`outbox.append(ListingViewed(...))`/etc. calls to `catalog/application/listing_use_cases.py`,
analytics starts capturing them with no analytics-side change at all. Until then, this route only
ever sees `FavoriteAdded` in practice.

## No counters, ever -- metric writes are append-only facts (I-23)

`MetricEvent`/`AuditEntry` carry no counter fields. `ListingStatistics` (see below) IS a set of
counters, but it is a separate, explicitly rebuildable PROJECTION, never the fact store itself --
mirrors the same "counters live in the projection, never the fact/aggregate" discipline
`ads.BannerCampaign` already established for I-23's other half (DEC-06's own note: "impression/
click counters ... are MetricEvents in BC-13 with report projections").

## Idempotency is data (I-23) -- every metric/audit write dedups on the triggering event id

`infrastructure/event_projection.py`'s eight handler functions (one per emitting module) all wrap
`backbone.idempotency.idempotent_consume`, keyed on `(envelope.event_id, handler_name)` via each
module's own local `ProcessedEventRow` ledger -- a redelivered event is a no-op, never a double
count. Proven for EVERY one of the eight metric families individually (`integration/
test_event_projection_live.py::test_I23_*`), not just once generically -- and proven at the
PROJECTION level too (`test_I23_redelivery_does_not_double_count_the_listing_statistics_
projection`), since idempotent fact-capture alone doesn't guarantee an idempotent derived counter
unless the projection update is inside the same idempotent-consume block (it is: `MetricUseCases.
record_metric` appends the fact AND advances `ListingStatistics` in one call).

## Append-only, immutable, at BOTH layers (PD-07)

`AuditEntry`/`MetricEvent` reject UPDATE/DELETE at the domain level (`ImmutableFactMutationError`,
see above) and, independently, at the database level: `analytics.audit_entry`/`analytics.
metric_event` each carry a `trg_<table>_immutability` guard trigger
(`backbone.migrations.guard_trigger_ddl`, built in P-03 with these exact two tables named in its
own docstring as the primary use case) that rejects every UPDATE and DELETE unconditionally, no
exceptions. Proven independently of the domain-level guard in `integration/
test_repository_live.py::test_I22_the_database_rejects_*`/`test_I23_the_database_rejects_*` (raw
SQL, bypassing the domain entirely).

## Time-partitioned fact tables + the partition-precreate job (Physical DB Sec 2/Sec 16)

`analytics.audit_entry`/`analytics.metric_event` are declaratively RANGE-partitioned by month on
`occurred_at` (created via hand-written raw DDL in the migration -- SQLAlchemy has no declarative
`PARTITION BY` helper), matching the Physical DB Design's own text naming these two (plus
`notifications.notification`) as "the three highest-volume append-only tables ... partitioned by
month from day one." Unlike `notifications.notification` (P-13, which deliberately deferred real
partition precreation as out of scope at the time, leaving a single `DEFAULT` catch-all
partition), this task's own validation checklist explicitly requires the ongoing job, so it's
built for real: `infrastructure/partition_worker.py::PartitionPrecreateWorker` (mirrors `ads.
infrastructure.worker.CampaignScheduleSweepWorker`'s `run_once()`/`run_forever(stop_event)`
shape), backed by a new, generic, reusable DDL generator added to shared infra --
`backbone/migrations/partitioning.py::upcoming_month_partition_ddls` -- since `notifications`
could adopt real partition precreation later using the exact same helper, without duplicating
this logic. `analytics_worker.py` runs it continuously (default: daily, 3 months ahead).
Integration-tested for real (`integration/test_partition_worker_live.py`): the worker creates a
FAR-future month's partition the migration itself never precreated, and re-running it is a cheap,
idempotent no-op (`CREATE TABLE IF NOT EXISTS`).

## `MetricEventCaptured`/`AuditEntryRecorded` are in-process signals, not outbox events

Physical DB Sec 2.13's own per-module `outbox_event` table list (`identity, profiles, catalog,
configuration, media, messaging, billing, ads, moderation`) deliberately EXCLUDES `analytics` --
confirmed by direct inspection, not assumption. This means `contracts/events/analytics.py`'s
`MetricEventCaptured`/`AuditEntryRecorded` (DDD Sec 6: "(sink) ... On ingestion ... Reports/
statistics projections") cannot be literal outbox-dispatched events requiring a second worker
hop -- there is no table for them to be written to. Resolution: `MetricUseCases.record_metric`
appends the `MetricEvent` fact AND synchronously advances the `ListingStatistics` projection in
the SAME call (one transaction, DEC-09's "never dual-write" spirit applied to a projection rather
than a second aggregate). `analytics.projection_checkpoint` (same shape as `search.
projection_checkpoint`) and `listing_statistics.as_of_position` exist specifically to support the
REBUILD capability below, not a live async dispatch pipeline.

## `ListingStatistics`/`OperationalReport`: rebuildable projections, not aggregates

- **`ListingStatistics`** (FR-ANALYTICS-002) -- per-listing counters (`views`/`contactClicks`/
  `phoneReveals`/`chatsInitiated`/`favorites`) for owners. `MetricUseCases.
  rebuild_listing_statistics()` discards every row and replays the full `MetricEvent` fact stream
  from position zero, deterministically reconstructing identical counters (DB Architecture Sec
  3.12: "read models... may be discarded and reprojected") -- proven in `test_metric_use_cases.py
  ::test_rebuild_listing_statistics_reconstructs_the_projection_identically`. `PHONE_REVEALED`
  never updates this projection: messaging's existing (already-merged) `PhoneRevealed` payload
  carries `conversationId`/`revealerUserId`/`revealedUserId` but no `listingId` at all, so the
  fact is captured correctly (I-23's capture requirement is satisfied) but cannot be attributed to
  a listing as currently shaped -- a documented gap, not a bug (see "Known gaps").
  `PREMIUM_LISTING_STAT`/banner metrics are captured but have no matching counter on this
  projection at all (Physical DB Sec 3.12's own column list has none).
- **`OperationalReport`** (FR-ADMIN-005) -- five fixed report keys (`contracts/openapi.yaml`'s own
  already-frozen `getAdminReports` enum): `LISTINGS_OVERVIEW` (MetricEvent aggregation),
  `REVENUE` (AuditEntry `PaymentConfirmed` facts, summed by currency), `VERIFICATION_SLA`
  (AuditEntry `BusinessVerified`/`VerificationRejected` decision counts -- throughput, not
  request-to-decision latency, since `VerificationRequested` is a self-service action never
  audited under I-22's own scope), `MODERATION_THROUGHPUT` (AuditEntry `ModerationActionTaken`
  facts grouped by verb), and `USER_GROWTH` (see "Known gaps" -- no data source exists).

## No-dereference guarantee (this module's own architectural discipline)

Analytics never calls back into another module to resolve an actor/target ref -- every field
stored anywhere in this module comes from the triggering event's own `payload` dict.
Structurally enforced (`analytics` imports `shared_kernel` only -- `cross-module-analytics`,
`tools/importlinter.cfg`) and proven by direct inspection
(`test_boundary_import.py::test_I03_a_deliberate_forbidden_import_breaks_the_contract_then_
reverts`, parametrized across every other module).

## Known gaps (flagged, not silently worked around)

- **`PHONE_REVEALED` never updates `ListingStatistics`** -- see above. Closing this needs a
  `messaging`-module change (adding `listingId` to `PhoneRevealed`'s payload), out of this task's
  scope (AIR-01).
- **`ListingViewed`/`ContactButtonClicked`/`PremiumListingStat` have no real producer** -- see
  "ADR-0005" above. The consumer is built, tested, and wired live; only the emitting side
  (`catalog`) is missing the actual `outbox.append(...)` calls.
- **`USER_GROWTH` has no data source in v1** -- `UserRegistered` is neither an administrative
  action under I-22's own scope (a self-service signup, not an admin/moderation/config action)
  nor one of the eight closed metric-vocabulary keys, so analytics never ingests it at all.
  `getAdminReports(report="USER_GROWTH")` returns an honest `{"available": false, "reason": ...}`
  rather than a fabricated count. Closing this needs either an ADR extending I-22's own scope or
  a dedicated growth-counter ingestion path -- a future task's call, not invented here.
- **`getListingStatistics` (`/listings/{listingId}/statistics`) is NOT this module's endpoint.**
  That operation is tagged `Listings` (not `Administration`), so `contracts/README.md`'s own
  P-01 tag-routing rule already assigned it to `catalog`, which already implements it (partially
  -- `views`/`contactClicks`/`phoneReveals`/`chatsInitiated` hardcoded `null`, `catalog/README.md`
  "Known gaps" #3, its own explicit attribution to analytics). Since "nothing imports analytics"
  is an absolute rule and `catalog`'s router has no injection point for cross-module data at all
  (the nulls are hardcoded literals in the router body, not a port), closing this gap would
  require modifying `catalog/interfaces/routers.py` directly -- a `catalog`-module change, out of
  P-15's own declared scope (`apps/backend/src/analytics/` only) and AIR-01. `analytics` itself
  builds the full, real, tested `ListingStatistics` capability (`MetricUseCases.
  get_listing_statistics`/`rebuild_listing_statistics`) -- it is simply not reachable through an
  HTTP endpoint analytics itself owns.
- **A pre-existing, repo-wide `MissingGreenlet` bug and a `pytestmark`-in-conftest limitation**
  (both already documented in `ads/README.md`'s own "Known gaps", reproduced identically here,
  not introduced by this task) also apply to this module's own integration suite when a real
  UPDATE/mutation path is exercised at the ORM layer and when filtering by `-m "not integration"`
  respectively -- flagged for completeness, not re-litigated.

## Public interface (`interfaces/`)

One router (`analytics_router`, tagged `Administration` -- matching `contracts/openapi.yaml`'s
own tag, not a new `Analytics` tag; `contracts/README.md`'s P-01 rule already routes
`Administration`-tagged operations to the module owning the underlying data), two operations:

- **`queryAuditLog`** (`GET /admin/audit-log`) -- FR-AUDIT-002, filterable/cursor-paginated,
  gated by `analytics:audit:read`.
- **`getAdminReports`** (`GET /admin/reports`) -- FR-ADMIN-005, gated by `analytics:reports:read`
  -- a DIFFERENT permission key than `queryAuditLog`'s, proven independently gated in
  `test_api.py` (a token authorized for one 403s on the other), mirroring `profiles.interfaces.
  di`'s own `get_acting_user`/`get_acting_reviewer` two-permission-one-module split.

Exposes NO command surface -- `interfaces/ports.py::AnalyticsQueryPort` declares only these two
read operations; `test_boundary_import.py::test_I04` inspects it directly and asserts no
"record"/"capture"/"ingest"/"write"/"create"-shaped method exists anywhere.

## Events (`contracts/events/*.py`, frozen since Task P-01, extended by ADR-0005)

**Published**: none to the outbox (see "`MetricEventCaptured`/`AuditEntryRecorded`" above).

**Consumed**, one handler function per emitting module, all wired live in `composition_root.py`:

| Emitting outbox | Route | Consumer wiring |
|---|---|---|
| moderation | `ModerationActionTaken` -> AuditEntry | Folded into `make_moderation_notification_projection_handler` (notifications' existing dispatcher) -- run by `notifications_worker.py`. |
| configuration | 9 `ConfigurationChanged` specialisations -> AuditEntry | The FIRST dispatcher ever built for configuration's own outbox -- `provide_analytics_configuration_projection_dispatcher`, run by the NEW `analytics_worker.py`. |
| billing | `PaymentConfirmed` -> AuditEntry | Folded into `make_billing_entitlement_fanout_handler` (catalog+profiles+notifications+ads' existing combined handler) -- run by `catalog_worker.py`. |
| identity | `AccountSuspended`/`AccountClosed` -> AuditEntry | Folded into `make_identity_account_status_projection_handler` (catalog+notifications' existing dispatcher) -- run by `catalog_worker.py`. |
| profiles | `BusinessVerified`/`VerificationRejected` -> AuditEntry | Folded into `make_profiles_notification_projection_handler` (notifications' existing dispatcher) -- run by `notifications_worker.py`. |
| catalog | `FavoriteAdded`/`ListingViewed`/`ContactButtonClicked`/`PremiumListingStat` -> MetricEvent | Folded into `make_catalog_outbox_fanout_handler` (search+messaging+moderation+notifications' existing combined handler) -- run by `search_worker.py`. |
| messaging | `PhoneRevealed`/`ChatInitiated` -> MetricEvent | Folded into `make_messaging_report_projection_handler` (moderation+notifications' existing dispatcher) -- run by `moderation_worker.py`. |
| ads | `BannerImpressionRecorded`/`BannerClickRecorded` -> MetricEvent | The FIRST dispatcher ever built for ads' own outbox -- `provide_analytics_ads_projection_dispatcher`, run by the NEW `analytics_worker.py`. |

`UserRegistered` (identity) and `VerificationRequested` (profiles) are deliberately NOT
consumed -- neither is an audited administrative action under I-22's own literal scope, and
neither is a closed-vocabulary metric.

Only ONE dispatcher may safely drain a given outbox table -- every already-multi-consumer outbox
above gets a new ROUTE folded into its existing combined handler, never a second dispatcher;
configuration's and ads' outboxes get their first-ever dispatcher, both new in this task.

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: `shared_kernel` ONLY. The strictest module in the codebase alongside
`notifications`/`moderation` -- not even another module's own `interfaces/` package.

MUST NOT import: every other module, without exception.

Nothing imports `analytics` -- proven by the shared `sink-modules-have-no-inbound-imports`
contract (covering `admin`/`analytics`/`notifications` together) AND by a repo-wide grep
(`test_boundary_import.py::test_I05_no_other_module_statically_imports_analytics`).

## Migrations

`infrastructure/migrations/versions/d8ee38154c92_*.py` -- hand-written. Creates `analytics.
audit_entry`/`analytics.metric_event` (both `PARTITION BY RANGE (occurred_at)`, three months of
partitions precreated at migration time, immutability guard triggers), `analytics.
listing_statistics`/`analytics.projection_checkpoint` (plain, mutable, no guard -- rebuildable
projections), `analytics.processed_event`. Verified end-to-end against real PostgreSQL during
this task -- including a dedicated `integration/conftest.py` that runs the REAL migration via
`alembic.command.upgrade` (a deliberate deviation from every other module's `metadata.create_all`-
based fixture setup, since neither partitioning nor the guard trigger can be produced by ORM
metadata alone; documented in that file's own docstring).

## Coverage / quality gates (Task P-15 run)

- `ruff format --check --config tools/ruff.toml` / `ruff check --config tools/ruff.toml`: clean
  for every `analytics`-owned file and every file this task touched
  (`composition_root.py`/`main.py`/`analytics_worker.py`/`backbone/migrations/partitioning.py`/
  `configuration/domain/whitelist.py`).
- `mypy --config-file tools/mypy.ini`: clean, 0 errors, across `analytics/` + every touched file.
- `import-linter` (all 49 contracts, whole repo): 49 kept, 0 broken.
- Domain coverage: 100% across every file in `analytics/domain/`. Application coverage:
  96.9-100% across every file in `analytics/application/` (only line 111 of
  `report_use_cases.py`, the `UnknownReportError` raise, is a defensive branch FastAPI's own
  routing already makes unreachable in practice).
- Overall module coverage (full suite: unit + integration against real Postgres): 92.19% (>= 80%
  floor).
- 95 tests: 27 domain (value-object closed-vocabulary + immutability, both fact types), 27
  application (audit/metric/report use cases, incl. the projection-rebuild test), 12 API
  (incl. the two-different-permissions authorization matrix), 17 boundary-import/descope-
  isolation, and 14 + 18 + 2 + 1 real-Postgres integration (repository round-trip incl. DB-level
  immutability guard + CHECK constraint; event-projection incl. I-22 audit-coverage-by-family and
  I-23 idempotency-by-family; partition-precreate worker; migration smoke test).
- **A whole-repo regression found and fixed during verification**: `configuration.domain.
  whitelist.EVENT_KEYS` is a hand-kept literal copy of `contracts.events.EVENT_CATALOGUE`'s keys
  (its own docstring commits to zero drift, checked by `tests/configuration/test_whitelist.py`);
  ADR-0005's three new events broke that parity until `EVENT_KEYS` was updated in the same
  change, mirroring exactly how ADR-0001's three media events were added there before.
- **Pre-existing, unrelated conditions found during verification** (not caused by this task,
  reproducible in complete isolation without any `analytics/` file present, already documented in
  `ads/README.md`'s/`notifications/README.md`'s own run notes): the repo-wide `MissingGreenlet`
  `save()` bug and the `pytestmark`-in-conftest marker-propagation limitation. Flagged, not
  silently patched (AIR-01).

## Layout

```
analytics/
|-- interfaces/       # PUBLIC surface: analytics_router, DTOs/ports, DI, errors
|-- application/      # AuditUseCases, MetricUseCases, ReportUseCases + ports
|-- domain/           # AuditEntry, MetricEvent, MetricKey, ClosedVocabularyPolicy, exceptions
|-- infrastructure/   # Sqlalchemy*Repository, event projections, partition-precreate worker,
|                      # migrations
`-- README.md          # this file
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
