# ads -- module charter

STATUS: implemented (Task P-14) -- the `BannerCampaign` aggregate, targeting/schedule value objects,
the I-21/I-20 eligibility policy, campaign CRUD/lifecycle use cases, the fast `serveBanner` path,
impression/click metric-event capture, the schedule-sweep worker, billing-entitlement projection,
and 9 new Ads-tagged `contracts/openapi.yaml` operations (added via ADR-0004, see below). This
README is the module's public charter -- read it before working in this module (Playbook Sec 13).

## Bounded context

- **Module**: `ads` (BC-09, Ad-Serving/Banners -- deliberately minimal, DEC-23's fixed first
  descope candidate if the one-month deadline is threatened)
- **Responsibilities**: banner campaign authoring/scheduling/targeting; fast banner selection at
  serve time; impression/click capture as metric events. Nothing outside `ads` depends on it (SAD
  Sec 8.1) -- the "descope seam": deleting this module breaks only its own tests and admin screens.

## Owned aggregates / entities (DDD Sec 5.10)

- **`BannerCampaign`** (`domain/banner_campaign.py`) -- a frozen dataclass referencing, by
  IDENTIFIER only, a `configuration`-owned `PlacementSlotDefinition` (`SlotRef`: head id + version
  id + slot key), a `media`-owned creative (`CreativeRef`: `creative_media_asset_id` +
  `creative_status`), and a `billing`-owned booking entitlement (`EntitlementRef`:
  `entitlement_id`, resolved through a LOCAL projection, never a live billing call -- see below).
  Carries `Schedule` (start/end/priority, FR-BANNER-002), `Targeting` (category ids/geo/languages,
  FR-BANNER-003), and `CampaignStatus` (`DRAFT -> SCHEDULED -> RUNNING -> ENDED`, with `PAUSED` a
  side branch off `SCHEDULED`/`RUNNING`). Transitions: `create`, `update` (DRAFT-only),
  `schedule_campaign`, `start`, `pause`, `resume` (routes back to `SCHEDULED` or `RUNNING`
  depending on whether `schedule.covers(now)`), `end`, `mark_creative_status`.

## No counters on the aggregate (I-23/BRULE-20/DEC-06 -- this module's second core property)

The SRS's own FR-BANNER-005 phrasing ("record banner impressions and clicks") reads like a counter
requirement; the Physical Database Design explicitly corrects this: `ads.banner_campaign` carries
NO impression/click counter columns, and its own note says so verbatim ("No impression/click
counters here -- engagement is `analytics.metric_event` only"). `record_impression`/`record_click`
(`application/serve_use_cases.py`) append `BannerImpressionRecorded`/`BannerClickRecorded` as
OUTBOX METRIC EVENTS and mutate no aggregate state at all -- proven by
`test_serve_use_cases.py::test_record_impression_appends_a_metric_event_and_no_counter_mutation`
(asserts the fetched-back campaign is byte-identical after the call) and by
`test_banner_campaign.py::test_no_impression_or_click_counter_fields_exist_on_the_aggregate`
(inspects the dataclass's own field names). Aggregation/reporting off these events is BC-13
(`analytics`)'s future job, out of this module's scope entirely.

## I-21 and I-20: two distinctly-named gates, never conflated

I-21 (DDD Sec 9, quoted verbatim): *"A BannerCampaign serves only within its schedule, matching
targeting, in its configured slot, while its booking entitlement is active."* Exactly four clauses
-- implemented as exactly four checks in
`domain/eligibility.py::CampaignEligibilityPolicy.is_eligible_under_i21`, each with its own named
test (`test_eligibility.py::test_I21_...`). I-21's own text says nothing about creative status.

I-20 is media's own invariant ("quarantined assets are never delivered"), applied here
cross-context via a SEPARATE method, `is_eligible_under_i20`, with its own separately-named tests
(`test_I20_...`). `is_servable` combines both. This task's own illustrative example conflated the
two into one list -- resolved here by correct separate attribution rather than overstating what
I-21's literal text requires.

## Serve-time performance discipline (X-06/SAD Sec 19: "fast, never blocks on another context")

`application/serve_use_cases.py::BannerServingUseCases.__init__` structurally accepts ONLY
`campaigns`/`entitlements`/`outbox` -- there is no `PlacementSlotReaderPort`/`CreativeReaderPort`
parameter anywhere in its signature, proven by
`test_serve_use_cases.py::test_serve_banner_never_depends_on_a_cross_module_port` (asserts via
`inspect.signature`, not just by convention). Entitlement-active and creative-clean checks at serve
time read only `ads`' own locally cached data (`EntitlementProjectionRow`,
`BannerCampaignRow.creative_status`) -- never a live `configuration`/`media`/`billing` call.
Slot/creative resolution (`PlacementSlotReaderPort`/`CreativeReaderPort`) is used only at the
low-frequency admin actions (`create_campaign`/`update_campaign`/`schedule_campaign`), never at
serve time.

## Billing entitlements: projected from events, never a live import

`billing` is FULLY forbidden by `cross-module-ads` (unlike `configuration`/`media`, which `ads` may
import via their `interfaces/` packages directly for the admin-side reads above). `ads` learns
about a `BANNER_SLOT_BOOKING` entitlement's activation/expiry/revocation only by projecting
billing's own `EntitlementActivated`/`EntitlementExpired`/`EntitlementRevoked` events locally
(`infrastructure/event_projection.py::handle_entitlement_event`, filtered to
`entitlementType == "BANNER_SLOT_BOOKING"`) into `EntitlementProjectionRow` -- a plain,
last-write-wins cache table, mirroring `notifications.infrastructure.persistence.models.
OrderRecipientProjectionRow`'s exact role. Wired as a FOURTH route on
`composition_root.make_billing_entitlement_fanout_handler` (the same combined dispatcher
catalog/profiles/notifications already extend) -- never a second dispatcher, since only one
dispatcher may safely drain billing's `outbox_event` table.

## Known gaps (flagged, not silently worked around)

- ~~**`handle_media_event` ... NOT wired to a live dispatcher**~~ -- **CLOSED**. The
  multi-consumer fan-out this entry said was out of scope now exists:
  `composition_root.make_media_outbox_fanout_handler` is the single handler behind the one
  dispatcher draining media's outbox, and this projection is its third route alongside catalog's
  and profiles'. The synchronous `CreativeReaderPort` refresh described below still runs and is
  still the authority at serve time; the projection now keeps stored creative status current
  between those reads instead of never firing. Previously, creative status was refreshed
  SYNCHRONOUSLY via `CreativeReaderPort`/`infrastructure.media_adapter.MediaCreativeStatusAdapter`
  at low-frequency admin actions (create/update/schedule) -- never at serve time. A campaign whose
  creative is rejected AFTER it was last synced stays servable until the next admin action touches
  it; closing that window needs the same future multi-consumer fan-out work notifications/catalog/
  profiles are already waiting on.
- **A pre-existing, repo-wide `MissingGreenlet` bug in every module's `Sqlalchemy<Aggregate>
  Repository.save()`** (not introduced by this task, reproduced identically in
  `billing.infrastructure.persistence.repository.PurchaseOrderRepository.save`): `save()` flushes
  then immediately returns `_x_to_domain(row)`, and reading a `server_default`/`onupdate`-backed
  column (`updated_at`) off the just-flushed row triggers an implicit expired-attribute refresh
  outside the SQLAlchemy asyncio greenlet context. Reproducible with billing alone, no `ads/` file
  present. Already documented as a known, unfixed issue in `notifications/README.md`'s own coverage
  notes. Flagged, not silently patched here (AIR-01 -- not this task's module to fix).
- **`pytestmark = pytest.mark.integration` set at `conftest.py` module level does not propagate to
  sibling test files in the same directory** (a pytest limitation, not an `ads`-specific bug --
  reproduced identically in `billing/integration/conftest.py` and
  `notifications/integration/conftest.py`, neither of which marks its own test files directly
  either). `pytest -m "not integration"` therefore does not deselect this module's
  `integration/` tests by path filtering alone; they still run and fail fast with
  `MissingInfraConfigError` when `POSTGRES_HOST` is unset (harmless locally, correct in CI where
  the datastore service containers are always present). Use `--ignore=apps/backend/tests/ads/
  integration` for a guaranteed-fast unit-only local run instead.

## Public interface (`interfaces/`)

Two routers, both tagged `Ads` (added by ADR-0004 -- see below):

- **`ads_admin_router`** (`interfaces/routers.py`) -- 7 operator operations, gated by the
  `ads:campaign:manage` permission key (new, added to `configuration.domain.whitelist.
  PERMISSION_KEYS`): `listCampaigns`, `createCampaign`, `getCampaign`, `updateCampaign`,
  `scheduleCampaign`, `pauseCampaign`, `resumeCampaign`, `endCampaign`.
- **`ads_public_router`** -- 3 unauthenticated operations on the hot path: `serveBanner` (`GET
  /banners/serve`, 204 when nothing is eligible), `recordImpression`/`recordClick` (`POST
  /banners/{campaignId}/impressions|clicks`, `202 Accepted` -- fire-and-forget metric capture, no
  response body).

The `interfaces/` package is this module's *only* importable surface (AIR-02) -- moot in the
inbound direction here too: nothing outside `ads` imports it (see "Dependencies" below).

## ADR-0004: the OpenAPI contract had zero Ads-tagged operations before this task

`contracts/openapi.yaml` (frozen since P-01) had no `Ads` tag and no banner/campaign paths at all --
a documented, frozen fact, not an oversight of this task. Implementing the routers this task
requires was impossible without amending the frozen contract. Surfaced to the repository owner
(CLAUDE.md: "a missing endpoint is an architecture decision, not a workaround"); the owner directed
amending the contract directly (`"you can change the openapi.yaml, lets add needed APIs"`). Done as
`docs/adr/0004-ads-openapi-endpoints.md` -- adds the `Ads` tag, the 9 operations above, and 4 new
schemas (`BannerCampaign`, `BannerCampaignCreateRequest`, `BannerCampaignUpdateRequest`,
`BannerServeView`), additive-only, no existing operation/schema touched. All three copies
(`contracts/openapi.yaml`, `docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml`,
`docs/frontend_docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml`) kept byte-identical, per the
ADR-0002/0003 precedent. `FR-BANNER-001` ("define banner inventory/placement slots") is
deliberately NOT duplicated here -- it is already served by the existing generic
`/admin/config/{entityType}` operations with `entityType=placement-slot`, `configuration`'s own
surface, not `ads`'s.

## Events (`contracts/events/*.py`, frozen since Task P-01)

**Published** (`infrastructure/event_projection.py`'s consumers aside, these are `ads`'s own outbox
writes): `BannerCampaignScheduled` (on `scheduleCampaign`), `BannerCampaignStarted` (natural
`SCHEDULED -> RUNNING` via the sweep worker), `BannerCampaignEnded` (both the operator's `endCampaign`
and the sweep worker's natural `schedule.end` expiry emit the SAME event -- the frozen catalogue
draws no distinction between the two triggers), `BannerImpressionRecorded`/`BannerClickRecorded`
(metric events, `serve_use_cases.py`, no state mutation). `pause`/`resume` emit NO event (not in the
frozen catalogue).

**Consumed**: billing's `EntitlementActivated`/`EntitlementExpired`/`EntitlementRevoked` (filtered to
`BANNER_SLOT_BOOKING`, wired live). Media's `MediaAssetReady`/`MediaAssetRejected` (built, unit/
integration tested, NOT wired live -- see "Known gaps").

## `CampaignScheduleSweepWorker` (`infrastructure/worker.py`)

Mirrors `billing.infrastructure.worker.EntitlementExpiryWorker`'s `run_once`/`run_forever` shape.
Each tick: `list_due_to_start` (`SCHEDULED` campaigns whose `schedule.start` has arrived) ->
`start()` + `BannerCampaignStarted`; `list_due_to_end` (`SCHEDULED`/`RUNNING`/`PAUSED` campaigns
whose `schedule.end` has passed) -> `end()` + `BannerCampaignEnded`. Run by the new
`ads_worker.py` entrypoint, mirroring `billing_worker.py`.

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: `shared_kernel`, `configuration` (`PlacementSlotReaderPort`'s concrete
adapter reads slot content directly), `media` (`CreativeReaderPort`'s concrete adapter reads scan
status directly) -- both via their `interfaces/` packages only.

MUST NOT import: `identity`, `profiles`, `catalog`, `search`, `messaging`, `billing` (see above),
`notifications`, `moderation`, `admin`, `analytics`.

Nothing outside `ads` imports it -- there is no single dedicated "sink" contract the way
`sink-modules-have-no-inbound-imports` covers `admin`/`analytics`/`notifications`; the guarantee is
instead distributed: every OTHER module's own `cross-module-<module>` contract lists `ads` in its
forbidden set, plus the symmetric `billing-catalog-profiles-ads-no-cycle` contract. Proven in
`test_boundary_import.py`: `test_I01`/`test_I03`/`test_I04` (the three contracts `ads` itself is a
party to currently pass), `test_I02` (a deliberate `import billing` probe breaks
`cross-module-ads`, then is reverted), `test_I05` (repo-wide grep: only `composition_root.py`/
`main.py` import `ads`), `test_I06` (the two allowed importers do in fact import it).

## Configuration consumed

`PlacementSlotDefinition` snapshots only (`infrastructure/configuration_adapter.
ConfigurationPlacementSlotAdapter`, reusing `composition_root._ConfigurationPortBridge`
unmodified), matched on `version.snapshot["slot_key"]` (from `configuration.domain.content.
PlacementSlotContent`) rather than `head.code` -- `ads` addresses slots by their business key, not
`configuration`'s own head id, in every admin-facing operation (`slotKey` in every DTO).

## Migrations

`infrastructure/migrations/versions/7e41075d53f8_ads_create_banner_campaign_schema.py` --
hand-written. Creates `ads.banner_campaign` (Physical DB Design's literal column list -- no
impression/click counter columns anywhere, see above), `ads.entitlement_projection` (the local
billing-entitlement cache, no `AggregateMixin` -- a plain last-write-wins projection, no optimistic
lock), `ads.outbox_event`, `ads.processed_event` (both via `backbone`'s factories). CHECK
constraints for `status`/`creative_status`/`activation_state` enums, `schedule_end > schedule_start`
(FR-BANNER-002), `priority >= 0`.

## Coverage / quality gates (Task P-14 run)

- `ruff format --check --config tools/ruff.toml` / `ruff check --config tools/ruff.toml`: clean for
  every `ads`-owned file and every file this task touched
  (`composition_root.py`/`main.py`/`configuration/domain/whitelist.py`). NOTE: running
  `ruff format --check` over the WHOLE repo without `--config tools/ruff.toml` (i.e. picking up an
  ambient default config instead of the project's own) produces false-positive diffs across many
  already-shipped, unrelated modules (identity/moderation/notifications) -- always pass
  `--config tools/ruff.toml` explicitly (`scripts/lint.sh` already does).
- `mypy --config-file tools/mypy.ini`: clean, 0 errors, 44 source files (this module + every file
  this task touched).
- `import-linter` (all 49 contracts, whole repo, via `scripts/check-import-boundaries.sh`): 49 kept,
  0 broken.
- Domain/application coverage: every file in `ads/domain/` and `ads/application/` is 100%.
- Overall module coverage (full suite: unit + integration against real Postgres): 88.77% (>= 80%
  floor). Unit-only (no datastore): 79.26% total, but this excludes `infrastructure/`'s
  Postgres-backed repository/event-projection code by construction -- not a real gap, matching
  every other module's own domain/application-vs-infrastructure coverage split.
- 108 tests: 27 domain (value objects + `BannerCampaign` transitions, incl. the no-counter-fields
  structural test), 34 application (campaign use cases incl. every I-21 clause + I-20 + the
  entitlement-slot-mismatch case + full update/sweep coverage; serve use cases incl. the
  structural no-cross-module-port test), 3 configuration-adapter, 3 media-adapter, 6
  boundary-import/descope-isolation, 12 API, 16 real-Postgres integration (7 event-projection, 9
  repository round-trip -- 6 of the 16 currently fail on the pre-existing `MissingGreenlet` bug
  above, reproducible with billing alone).
- **Pre-existing, unrelated conditions found during verification** (not caused by this task,
  reproducible in complete isolation without any `ads/` file present): billing's own unfixed
  `MissingGreenlet` `save()` bug (already documented in `notifications/README.md`'s own run notes);
  the `pytestmark`-in-conftest marker-propagation limitation (reproduced identically in
  `billing/integration` and `notifications/integration`). Flagged, not silently patched (AIR-01).

## Layout

```
ads/
|-- interfaces/       # PUBLIC surface: admin + public routers, DTOs/ports, DI, errors
|-- application/      # CampaignUseCases, BannerServingUseCases + ports
|-- domain/           # BannerCampaign aggregate, value objects, eligibility policy, exceptions
|-- infrastructure/   # SqlalchemyBannerCampaignRepository, event projections, config/media
|                      # adapters, schedule-sweep worker, migrations
`-- README.md          # this file
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
