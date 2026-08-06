# catalog -- module charter

STATUS (Task P-07): fully implemented across all four layers -- the `Listing`/`Favorite`
aggregates, the validation engine executing configured form rules, quota enforcement from a
locally projected billing snapshot, duplicate detection, the expiry sweep worker, idempotent
media/entitlement event projections, and the fifteen catalog/favorites-tagged API operations.
This README is the module's public charter -- read it before working in this module (Playbook
Sec 13). See `TRACEABILITY.md` for the requirement -> code -> test matrix.

## Bounded context

- **Module**: `catalog` (BC-03, Core domain per DDD/SAD classification -- "the marketplace core")
- **Responsibilities**: Listing lifecycle, attribute sets, quotas, expiry/renewal, favourites,
  duplicate detection.

## Owned aggregates / entities (DDD Sec 5.3)

- **`Listing` [P]** (`catalog.domain.listing.Listing`) -- `listing_type`, `owner_user_id`/
  `owner_profile_id`/`category_id` fixed for life (I-01), `category_path`, the bound
  `form_definition_id`/`form_definition_version_id` (I-07), `title`/`description`/`attributes`
  (the AttributeSet, DM-02 -- one typed JSONB document, EAV explicitly rejected), `price`,
  `location`, the seven-state `lifecycle_state` (DEC-14), `is_flagged`, `expires_at`,
  `published_at`, a projected `promotion`, `slug`, `lock_version`. Owns two child entity
  collections inside its own aggregate boundary (one repository, one unit of work):
  - **`ImageAttachment`** -- ordered (`position` 1-10), `media_asset_id` (`MediaAssetRef`, never a
    `media.domain` import), a projected `status` (I-04).
  - **`LifecycleTransitionRecord`** -- append-only, produced by the aggregate's own transition
    methods (I-05), never assembled after the fact.
- **`Favorite` [P]** (`catalog.domain.favorite.Favorite`) -- a distinct, minimal aggregate root
  (`user_id`, `listing_id`, `created_at`), its own repository/unit of work "so favoriting never
  contends with listing writes" (DDD Sec 5.3).
- **Validation engine [P]** (`catalog.domain.policies.validate_attribute_set`) -- fixed,
  whitelisted code executing configured rules `[C]` (the six `ValidatorType`s
  `configuration.interfaces.dto.ValidatorBinding` declares); collects every failure at once.
- **`QuotaEnforcementService`** (`catalog.application.quota_service`) -- I-08.
- **`DuplicateDetectionService`** (`catalog.application.duplicate_detection_service`) -- FR-ADV-009.

## The eight domain invariants (DDD Sec 9)

| # | Text (as implemented) | Enforced by |
|---|---|---|
| I-01 | `owner_user_id`/`owner_profile_id`/`category_id` fixed for life | `Listing`'s own methods -- none accepts them as a parameter (structural, `test_I01_no_method_accepts_owner_or_category_as_a_parameter`) |
| I-02 | One bound form per category | `CategoryFormPort.get_current_form_binding`; `configuration` owns the "one bound form" guarantee |
| I-04 | At most 10 image attachments, quarantined assets never remain listed | `Listing.attach_image`/`update_image_status` |
| I-05 | Only legal transitions in the fixed graph are accepted; every transition recorded | Each transition method's own guard + `_record` (never a separate post-hoc assembly) |
| I-06 | Public visibility = Published-or-Edited AND unflagged AND unexpired, one authoritative rule | `Listing.is_publicly_visible` -- the only place this predicate is evaluated |
| I-07 | Bound FormDefinitionVersion frozen at creation; a later publish never retroactively invalidates; an explicit edit rebinds to the then-current version | `Listing.form_definition_id`/`form_definition_version_id` (own field docstring); `edit_content`'s `form_definition_id`/`form_definition_version_id` params |
| I-08 | Quota enforced from a locally projected subscription snapshot only; catalog never imports billing | `QuotaEnforcementService`; `cross-module-catalog`/`billing-catalog-profiles-ads-no-cycle` import-linter contracts |

See `TRACEABILITY.md` for the named test proving each one.

## Public interface (`interfaces/`)

`ListingPort` (fifteen operations, frozen since Task P-01) plus `ListingModerationPort` (a fresh,
catalog-designed, non-REST Protocol for the moderation-invoked unflag command -- BC-11 is out of
this task's scope, but the port it will call already exists). The `interfaces/` package is this
module's *only* importable surface (AIR-02). Nothing in `application/`, `domain/`, or
`infrastructure/` may be imported by another module, ever.

## Routers (`interfaces/routers.py`) -- exactly the fifteen catalog/favorites-tagged operations

`listListings`/`getListing`/`listListingImages` declare `security: []` in
`contracts/openapi.yaml` (public browse/detail) -- routed through `get_optional_acting_user`,
which never raises on a missing session (so `getListing` can still grant an owner extended
visibility into their own draft, per its own "non-owners see only visible listings" description).
Every other operation requires a session (`get_acting_user`). No more, no less (QG-06 contract
conformance -- verified via `main.app.openapi()` reporting exactly these fifteen operationIds).

## Authentication bridge (catalog never imports identity)

`cross-module-catalog` (`tools/importlinter.cfg`) forbids every layer of this module from
importing `identity`. `interfaces/auth.py` declares `ActingUser(account_id: UserId,
acting_profile_id: BusinessProfileId | None)` -- unlike media's own `ActingUser` (account id
only), catalog's create/quota paths need the acting business-profile context too.
`composition_root.provide_catalog_acting_user`/`provide_catalog_optional_acting_user` reuse
identity's already-built session machinery (`ApplicationAuthorizationService.
resolve_acting_context`), reading `acting_profile_id` straight off the resolved `Session` domain
object -- the composition root is the one place allowed to see both modules' internals.

## The validation engine and I-07's rebind rule

`catalog.domain.policies.validate_attribute_set` executes the closed six-`validator_type`
vocabulary (`required`/`length`/`numeric_range`/`pattern_safe`/`option_membership`/`image_count`)
against the AttributeSet, collecting every failure in one round-trip. The bound form version is
resolved fresh by `CategoryFormPort.get_current_form_binding` both at `createListing` **and**
every `updateListing` (`interfaces/dto.py::ListingUpdateRequest`'s own "re-binds/re-validates
against the current form version") -- the listing then holds that binding fixed until its *next*
edit, never drifting on its own as `configuration` publishes further versions in between
(`catalog.infrastructure.configuration_adapter` bridges to `configuration.application.
category_read.CategoryReadUseCases` directly, not the DTO-typed `ConfigurationPort`, since the
read use case's own `dict | None` return is the actual "not found" signal this module needs).

## BRULE-17/DEC-14: post-publication visibility

An unflagged listing is visible immediately on publish; a flagged one (duplicate-detection hit)
is withheld. Implemented as **one** authoritative rule (`Listing.is_publicly_visible`, I-06)
rather than a queued sub-state: `publish()` fires regardless of `is_flagged`, and the domain
event payload carries `isFlagged`/`expiresAt` so downstream consumers (Search, Notifications) can
replicate the same predicate rather than trusting catalog to withhold the event itself.

## Events published (`contracts/events/catalog.py`, frozen since Task P-01)

`ListingCreated`, `ListingDraftSaved`, `ListingPublished` (also republished, unchanged, by
`RESTORE` -- no dedicated `ListingRestored` event exists in the frozen catalogue), `ListingEdited`,
`ListingSuspended`, `ListingArchived`, `ListingDeleted`, `ListingExpired`, `ListingRenewed`,
`ListingFlagged`, `FavoriteAdded`, `FavoriteRemoved`. `UNFLAG` records a transition but publishes
no event (same governance boundary as `RESTORE`'s). Published via the transactional outbox
(`backbone.outbox.OutboxWriter`), same transaction as the state change that triggers each one --
never dual-write (DEC-09; DB Architecture Sec 1.3's second sanctioned synchronous exception,
proven by `integration/test_transactional_outbox_live.py`'s forced-failure test).

## The expiry sweep worker (`infrastructure/worker.py`, `apps/backend/src/catalog_worker.py`)

No inbound API surface -- a poll loop over `ListingRepository.list_expiring`, mirroring
`media.infrastructure.worker.MediaIntakeWorker`'s `run_once()`/`run_forever(stop_event)` shape
(fresh `AsyncSession` per batch). `Listing.record_expiry` is idempotent by construction (a no-op
if the most recent transition is already `EXPIRE`), so a listing re-selected on a later poll
before its owner renews it is never re-fired.

## Idempotent cross-module event projections (`infrastructure/event_projection.py`)

Two handlers, `handle_media_event`/`handle_entitlement_event`, each wrapped in
`backbone.idempotency.consumer.idempotent_consume` against catalog's own `ProcessedEventRow`
ledger:

- **Media asset-status projection** (X-06): `MediaAssetReady`/`MediaAssetRejected` ->
  `Listing.update_image_status` (CLEAN, or auto-detach on QUARANTINED). Media has a real producer
  (`media.infrastructure.persistence.models.OutboxEventRow`), so this handler *can* be wired for
  real -- see "Known gaps" #1 for why it isn't wired into `composition_root.py` in this task.
- **Entitlement projection** (I-08): a billing entitlement event -> `catalog.
  subscription_projection`, upserted keyed on `owner_profile_id`. Billing (BC-08) does not exist
  as a module yet, so this handler is fully built and tested against synthetic `EventEnvelope`s
  (`integration/test_event_projection_live.py`, mirroring `backbone`'s own
  `test_dispatcher_idempotency.py` pattern) but has no real producer to wire against.

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: `shared_kernel`, `configuration`, `identity`, `media` -- confirmed
unchanged from the P-01 stub, and only their `interfaces/` packages.

MUST NOT import: `profiles`, `search`, `billing` internals -- and no static dependency on billing
at all (`billing-catalog-profiles-ads-no-cycle`, AIR-10 named cycle), `messaging`,
`notifications`, `moderation`, `admin`, `analytics` internals.

## Configuration consumed (DEC-21: never hardcode a configurable value)

`listing.default_expiry_days` (`configuration.domain.whitelist.SETTINGS_SCHEMA`, read via
`ConfigurationPlatformSettingsAdapter`) drives both the initial `publish()` expiry term and every
`RENEW` extension. The `catalog:listing:moderate` permission key
(`configuration.domain.whitelist.PERMISSION_KEYS`, this task's own extension of that catalogue)
gates the moderation-invoked unflag command -- consulted by the *caller* (a future moderation
module) via `identity.interfaces.ports.AuthorizationPort`, not by catalog itself (mirrors how
`AuthorizationPort` is "consulted in-process by every other module" without the callee
re-validating).

## Migrations

`infrastructure/migrations/versions/c9f482b269ed_...py` creates `catalog.listing`,
`catalog.image_attachment` (`ON DELETE CASCADE`), `catalog.listing_transition` (`ON DELETE
RESTRICT` -- the audit trail must never disappear as a side effect of the listing row's own
lifecycle), `catalog.favorite` (`ON DELETE RESTRICT`, physical `DELETE` permitted on the
favorite row itself), `catalog.subscription_projection` (keyed by `owner_profile_id` alone, no
`AggregateMixin` -- a projection, not an aggregate), `catalog.outbox_event`,
`catalog.processed_event`. **No GIN index on `attribute_document`** (DM-02/Physical DB "catalog
schema" section) -- faceting/filtering on AttributeSet content is BC-05/search's job. Hand-written,
not `alembic revision --autogenerate` (see the migration file's own docstring). Kept in sync with
`infrastructure/persistence/models.py` by `apps/backend/tests/catalog/test_models.py`'s static
parity check (which also proves DM-02's "no EAV table exists").

## Known gaps (flagged, not silently worked around)

1. ~~**Media event projection not wired into `composition_root.py`**~~ -- **CLOSED**.
   `handle_media_event` is now a route on `composition_root.make_media_outbox_fanout_handler`,
   the single handler behind the one `OutboxDispatcher` draining `media.outbox_event`, run by
   `media_worker.py` (the producing module's own worker, so neither consumer's worker becomes a
   hidden dependency of the other's projection). The "second independent consumer would need a
   different mechanism" this entry anticipated is exactly what that fan-out is: profiles' and
   ads' equivalent handlers -- unwired for the same reason -- are the second and third routes on
   it, rather than three racing dispatchers.

   Wiring alone was not sufficient. Scanning often finishes *before* the owner attaches the
   image, and `MediaAssetReady` is consumed once: the projection looks up the listing holding the
   asset, finds none, and correctly no-ops -- after which nothing re-examines that asset, so the
   attachment stayed `PENDING` for the rest of its life and the CLEAN-only interface never showed
   the photo. `Listing.attach_image` now seeds the attachment from the scan status the attach
   path had already fetched; the event still covers the other ordering.
2. **Attach-time media ownership check is existence-only**: `media.interfaces.dto.MediaAsset`
   (the only shape `MediaIntakePort.get_media` returns) carries no uploader/owner field --
   `getMedia`'s own docstring makes this a deliberate media-side choice ("no ownership check ...
   delivery metadata is meant to be readable by whatever page embeds the image"), not an
   oversight this module could work around. `attachListingImage` therefore only verifies the
   referenced media asset *exists*, not that the caller uploaded it.
3. **`getListingStatistics` is partial**: `favorites` is catalog's own real data; `views`/
   `contactClicks`/`phoneReveals`/`chatsInitiated` are Analytics-owned (BC-13, outside this
   module's declared dependency set) and return `null`.
4. **Identity account-suspension events not consumed**: DDD/DB Architecture mention catalog
   hiding a suspended/closed account's listings by consuming identity's `AccountSuspended`/
   `AccountClosed` events, but this task's own Included/Dependencies sections never name this
   (exhaustively itemized otherwise) -- treated the same way P-06 treated its own out-of-scope
   purge job: documented, not built.
5. **Billing quota projection has no real producer**: see "Idempotent cross-module event
   projections" above -- `handle_entitlement_event` is complete and tested against synthetic
   events; BC-08 does not exist as of this task, so no listener is ever actually wired.
6. **Pre-existing, unrelated**: `tools/check_contract_drift.py` reconfirms `identity/README.md`'s
   own already-documented gap (`configuration`'s admin routers use snake_case path parameters
   where `contracts/openapi.yaml` specifies camelCase) -- catalog's own fifteen routes match the
   spec exactly and report zero drift; the `configuration` mismatch is unrelated to this task and
   was left untouched (AIR-01). Similarly, `tools/check_migration_safety.py` flags a false
   positive on identity's and media's own already-merged migration file *docstrings* (prose
   containing the words "DROP TABLE/COLUMN" trips its naive keyword scanner) -- pre-existing,
   not introduced by this task, and catalog's own migration carries correct `# approved-
   destructive:` markers on every real `op.drop_table(...)` line in its `downgrade()`.

## Coverage / quality gates (Task P-07 run)

120 tests (`apps/backend/tests/catalog/` unit + integration + API, plus 5 new rows in
`tests/authorization_matrix.py::CATALOG_MATRIX`), mypy --strict clean, ruff clean (five
pre-existing, codebase-wide style notes carried over unchanged from identity/media precedent:
`UP042` "inherit from StrEnum" on every `(str, Enum)` value object), all 49
`tools/importlinter.cfg` contracts kept, domain coverage 100%, application coverage 99% (one
defensively-unreachable branch: `Listing.update_image_status`'s own "not attached" no-op can
never fire from `apply_media_status_projection`'s call site, since `get_by_image_media_asset_id`
only ever returns a listing that already holds the asset attached), bandit SAST clean (one
low-severity, pre-existing-pattern `B101` note, same class as two already-merged occurrences
elsewhere), pip-audit clean (no new dependencies added this task). The Postgres-only integration
tests (`integration/`) are present and structurally correct but unexecutable in this sandbox (no
`POSTGRES_HOST`), the same class of gap already documented for P-05/P-06's own integration
suites.

## Layout

```
catalog/
|-- interfaces/       # PUBLIC surface: routers, published ports, DTOs, event contracts, moderation port
|-- application/      # use cases (commands/queries) + ports
|-- domain/           # aggregates, value objects, domain events, policies, invariants
|-- infrastructure/   # adapters: persistence, configuration/media adapters, outbox, worker, event projection
|-- README.md         # this file
`-- TRACEABILITY.md    # requirement -> code -> test matrix
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
