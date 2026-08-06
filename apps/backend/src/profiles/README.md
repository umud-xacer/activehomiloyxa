# profiles -- module charter

STATUS: implemented (Task P-11) -- the generic BusinessProfile/VerificationCase aggregates,
the badge-issuance policy (I-13), the paid-verification gate (I-12), the reviewer workflow,
all 13 profiles-tagged `contracts/openapi.yaml` operations this task's scope covers, event
publication/consumption via the transactional outbox, and the moderation command port. This
README is the module's public charter -- read it before working in this module (Playbook Sec 13).

## Bounded context

- **Module**: `profiles` (BC-02, Core domain per DDD/SAD classification)
- **Responsibilities**: Company pages (8 profile types), portfolios, the manual paid-verification
  workflow, and the verified-badge lifecycle -- the platform's trust core.

## Owned aggregates / entities (DDD Sec 5.2)

- **`BusinessProfile`** (`domain/business_profile.py`) -- the company presence. `ProfileType` is a
  closed set of exactly eight codes (see "The ProfileType vocabulary correction" below):
  `CONSTRUCTION_COMPANY`, `MANUFACTURER`, `BUILDER`, `SUPPLIER`, `CONTRACTOR`, `ARCHITECT`,
  `INTERIOR_DESIGNER`, `SERVICE_PROVIDER`. Lifecycle `Created -> Active -> Archived`
  (`create()`+`activate()` are always composed together in one request -- no document describes a
  distinct manual activation step). Holds the ordered `PortfolioItem` child entities (<=50) and
  the badge sub-state (`VerifiedBadge | None`; `None` = never verified).
- **`VerificationCase`** (`domain/verification_case.py`) -- the manual verification work item.
  Lifecycle `Requested -> InReview -> Approved | Rejected`; the latter two are **terminal and
  immutable** (every mutating method's first check refuses once terminal -- see
  `TerminalVerificationCaseError`). Holds the ordered `SubmittedDocument` child entities.
- **`ApprovedVerificationProof`** (`domain/verification_case.py`) -- not an aggregate; the
  structural guard for I-13 (see below).

## I-13: the badge-issuance guard (this module's primary invariant)

*"A VerifiedBadge exists only from an approved case, displays only within validity, and is
withdrawn on expiry."*

`BusinessProfile.issue_badge` is the **only** method on this codebase that can set a badge's
status to `VALID`, and it requires an `ApprovedVerificationProof` -- a type that can itself only
be constructed via `ApprovedVerificationProof.from_case(case)`, which raises
`BadgeNotIssuableWithoutApprovedCaseError` unless `case.status is APPROVED`. There is no setter,
no alternate constructor, and no other call path to `VALID` (mirrors the same "one constructor, no
bypass" discipline `billing.domain.entitlement.EntitlementFactory.activate_from_paid_order`
establishes for I-14). Proven both directions in `apps/backend/tests/profiles/
test_business_profile.py::test_I13_*` and `integration/test_repository_live.py` (against a real
database).

Badge validity: `issue_badge`'s `valid_until` is supplied by the caller
(`VerificationUseCases.decide_verification`), computed from the **entitlement's own** validity
window (`VerificationEligibilityRepository.get_by_entitlement_id`) -- DDD Sec 5.2's
`BadgeIssuanceService` says the period comes "from the configured verification product terms";
since profiles cannot import `configuration` (SAD Sec 8.1), this is realised transitively via the
entitlement, whose own `valid_until` billing already computed from the configured product's
`term_days`. `expire_badge`/`revoke_badge` are the only two transitions out of `VALID`
(`EXPIRED` via the sweep worker, `REVOKED` via the moderation command port).

## I-12: the paid-verification gate

*"A VerificationCase requires submitted image documents and an active VerificationEligibility
entitlement before entering the queue."*

`VerificationCase.create` structurally enforces the documents half (raises
`NoDocumentsSubmittedError` if given none). The entitlement-active half is enforced by
`VerificationUseCases.request_verification`, which checks a **locally projected** read model
(`VerificationEligibilityRepository`, `profiles.verification_entitlement_projection` -- not in the
documented Physical Database Design, a locally-necessary addition following the exact precedent
`catalog.infrastructure.persistence.models.SubscriptionProjectionRow` set for I-08), populated only
by `infrastructure.event_projection.handle_entitlement_event` consuming billing's own
`EntitlementActivated`/`EntitlementExpired`/`EntitlementRevoked` events (X-03) -- **profiles never
imports billing, never queries it synchronously** (`test_boundary_import.py` proves the
import-linter contract has teeth with a deliberate-violation-then-revert test).

## The ProfileType vocabulary correction (ADR-0002)

The frozen `contracts/openapi.yaml` (from Task P-01) originally enumerated a *different*
eight-value `profileType` set (`INDIVIDUAL_SELLER`, `REAL_ESTATE_AGENCY`, `DEVELOPER`,
`MATERIALS_SUPPLIER`, `ARCHITECT_DESIGNER`, `PROPERTY_MANAGER`, plus `CONSTRUCTION_COMPANY`/
`SERVICE_PROVIDER`) that conflicted with SRS Sec 4 / DDD Sec 5.2's own eight named types. Surfaced
to the repository owner rather than resolved unilaterally; the owner directed following SRS/DDD
naming and amending the OpenAPI contract. See `docs/adr/0002-business-profile-type-vocabulary-
correction.md` for the full record -- `contracts/openapi.yaml`, `docs/Active-Home-OpenAPI-3.1-
Specification-v1.0.yaml`, `docs/frontend_docs/`'s copy, and this module's own `interfaces/{dto,
ports}.py` were all corrected together in the same change as this task.

## Public interface (`interfaces/`)

- **Routers** (`interfaces/routers.py`): `profiles_router` (`Business Profiles` tag, 11
  operations) + `admin_profiles_router` (`Administration` tag, 2 operations --
  `listVerificationQueue`/`decideVerification`, mirroring `billing.interfaces.routers`'s own
  precedent of implementing admin-tagged operations locally when they act purely on this module's
  own aggregates).
- **`interfaces/moderation_port.py`**: `ProfileModerationPort` (`revoke_badge`/`archive_profile`)
  -- the command port BC-11 (moderation, out of this task's scope) will later invoke, mirroring
  `catalog.interfaces.moderation_port.ListingModerationPort`'s exact precedent. Gated by the
  `profiles:profile:moderate` permission key (declared in `configuration.domain.whitelist.
  PERMISSION_KEYS`, not yet consulted anywhere -- same "capability exists, no caller wires it yet"
  status as `catalog:listing:moderate`).
- **`interfaces/ports.py`** (frozen Task P-01 stubs): `ProfileQueryPort`, `VerificationPort`.
  `ProfileQueryPort` still declares `addTeamMember`/`removeTeamMember`/`listTeamMembers` -- see
  "Known gaps" below for why no router implements them.

The `interfaces/` package is this module's *only* importable surface (AIR-02). Nothing in
`application/`, `domain/`, or `infrastructure/` may be imported by another module, ever.

## Events (`contracts/events/profiles.py`, frozen since Task P-01)

**Published**, all via the transactional outbox (never dual-write):

| Event | Emitted when |
|---|---|
| `BusinessProfileCreated` | `ProfileUseCases.create_profile` -- consumed by `identity` since P-20 (see that module's own README's "Events consumed" section) to keep `UserAccount.owned_profile_ids` in sync; a real, confirmed integration defect (a real user could never `switchActingProfile` to a profile they just created) until that fix landed. |
| `VerificationRequested` | `VerificationUseCases.request_verification` |
| `BusinessVerified` | `VerificationUseCases.decide_verification` (outcome `APPROVED`) |
| `VerificationRejected` | `VerificationUseCases.decide_verification` (outcome `REJECTED`) |
| `VerifiedBadgeExpired` | The badge-expiry sweep, **and** the moderation-invoked `revoke_badge` command -- there is no separate `VerifiedBadgeRevoked` event in the frozen catalogue; search's own `handle_verified_badge_cleared` already treats both as "badge no longer valid" identically, so both real triggers publish this one event type. |

**Consumed** (idempotent via `ProcessedEventRow`, `infrastructure/event_projection.py`):

- Billing's `EntitlementActivated`/`EntitlementExpired`/`EntitlementRevoked` (X-03), filtered to
  `entitlementType == "VERIFICATION_ELIGIBILITY"` -- projects `VerificationEligibilitySnapshot`
  (I-12). Wired end-to-end: `composition_root.make_billing_entitlement_fanout_handler` extends the
  same ONE dispatcher already draining billing's outbox for catalog's `ACTIVE_SUBSCRIPTION`
  routing (`provide_catalog_entitlement_projection_dispatcher`, run from `catalog_worker.py`) --
  two independent dispatchers on the same outbox table would race on `dispatch_status`, so this
  module's own worker (`profiles_worker.py`) does NOT also drain billing's outbox.
- Media's `MediaAssetRejected` (X-06) -- removes the referencing `PortfolioItem`/
  `SubmittedDocument` (neither child entity's physical schema has a status column to flip instead;
  a no-op on a terminal `VerificationCase`, since terminal-immutability wins). **Not wired to a
  live dispatcher** -- media's own `outbox_event` table has no dispatcher draining it at all yet,
  for any consumer (a pre-existing, documented gap: `catalog/README.md`'s own "Known gaps" #1
  names the same situation for catalog's equivalent media consumer). `composition_root.
  make_profiles_media_status_projection_handler` builds the handler closure so the wiring is one
  line away once a future task decides which worker process owns media's outbox drain.

## Downstream verification: search's badge flag

`search.infrastructure.event_projection.handle_verified_badge_applied`/
`handle_verified_badge_cleared` (built under Task P-08) consume `BusinessVerified`/
`VerificationRejected`/`VerifiedBadgeExpired` and flip `ListingSearchDocument.verified_badge` for
every listing owned by the profile. Proven end-to-end against the REAL events this module
publishes in `apps/backend/tests/profiles/integration/test_downstream_search_projection_live.py`
(an in-memory `SearchIndexPort` stand-in).

**RESOLVED (Task P-20), two confirmed integration defects**: (1) despite being fully built and
unit-tested since P-08, these two handlers were never actually wired to any dispatcher anywhere
in `composition_root.py` -- `composition_root.make_profiles_notification_projection_handler` now
attaches search's own `make_search_event_handler` as a third route, closing the gap end to end
(proven against a real OpenSearch cluster by `tests/integration/test_profiles_badge_to_search.py`).
(2) the "`opensearch:2.19.0` image rejects search's own `flattened`-typed mapping" note above was
a misdiagnosis, not an environment defect: `flattened` is Elasticsearch's own field-type name;
OpenSearch's native equivalent is `flat_object` (added since OpenSearch 2.x, never adopted
Elastic's name) -- `search/infrastructure/opensearch_index.py`'s `INDEX_MAPPING` now uses the
correct name, and `test_opensearch_index_live.py` passes against a real cluster.

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: `shared_kernel`, `identity`, `media` (via their `interfaces/` packages
only).

MUST NOT import: `configuration`, `catalog`, `search`, `messaging`, `billing`, `ads`,
`notifications`, `moderation`, `admin`, `analytics`. **No billing import** -- the paid-
verification entitlement fact arrives exclusively as a projected event (X-03), never a synchronous
call. `apps/backend/tests/profiles/test_boundary_import.py` proves this with a deliberate
`import billing`/`import configuration`/`import catalog` probe that breaks the
`cross-module-profiles` contract, then reverts it.

## Configuration consumed

**None.** Unlike `catalog`/`billing`, `profiles` does not statically import `configuration` (SAD
Sec 8.1's own table). The one business parameter that would normally be configuration-sourced --
the verification SLA target (BRULE-05: "design phase sets the exact value") -- is instead a fixed
platform constant (`domain/policies.py::VERIFICATION_SLA_HOURS = 72`), the same reasoning
`catalog.domain.listing.MAX_IMAGE_ATTACHMENTS` documents for its own fixed literal.

## Migrations

`infrastructure/migrations/versions/023d4efe95eb_*.py` -- hand-written (not autogenerated, same
reasoning as every other module's first migration: `include_schemas=True` autogeneration against
the shared dev database proposes dropping other modules' already-applied tables). Creates
`profiles.business_profile`, `portfolio_item`, `verification_case`, `submitted_document`,
`verification_entitlement_projection` (the I-12 local projection, not in the documented Physical
Database Design -- see `catalog.subscription_projection`'s own precedent), `outbox_event`,
`processed_event`. Verified end-to-end against real PostgreSQL (`alembic upgrade head` /
`alembic downgrade base`, both clean) during this task.

## Known gaps (flagged, not silently worked around)

- **`listTeamMembers`/`addTeamMember`/`removeTeamMember` are not implemented.** The frozen
  `interfaces/ports.py`/`interfaces/dto.py` stubs (Task P-01) declare a `TeamMember` DTO and three
  `ProfileQueryPort` methods, but no approved document (SRS, DDD, Physical Database Design) models
  a "team member" concept for BC-02 -- DDD Sec 5.2's own `BusinessProfile` aggregate lists only
  `PortfolioItem` as a child entity. The DTO's own docstring says team membership is "realised as
  an identity `RoleAssignment` scoped to the profile," but identity's frozen `interfaces/ports.py`
  (the only surface profiles may import) exposes no port for assigning a role scoped to a profile
  that another module could call -- `identity.application.admin_use_cases.
  AdminIdentityUseCases.assign_role`/`revoke_role` exist but are not exposed via `interfaces/`.
  Implementing this would mean either inventing a new BC-02 aggregate no document describes, or
  adding a new cross-module port to identity -- both are frozen-interface changes needing a human
  decision (AIR-19), and P-11's own Scope/Deliverables never mention team management. Left
  unimplemented rather than guessed at; `interfaces/ports.py`'s stub methods remain as declared
  (frozen from P-01) so a future task has the exact shape to build against once this is resolved.
- **Media asset-status projection (`MediaAssetRejected`) is not wired to a live dispatcher.** See
  "Events" above -- a pre-existing gap shared with catalog's own equivalent consumer, not
  something this task's scope extends to fixing (which worker process should own media's outbox
  drain is a cross-cutting decision affecting every consumer of media's events, not just this
  module's).
- **The badge-expiry sweep worker's own `EntitlementActivated` fanout is coupled to
  `catalog_worker.py`'s process.** `provide_profiles_badge_expiry_worker` (this module's own sweep
  over `business_profile.badge_valid_until`) is independent and runs from `profiles_worker.py`,
  but the entitlement PROJECTION consumer (I-12) is folded into the same dispatcher catalog's
  worker already runs (`make_billing_entitlement_fanout_handler`), since only one dispatcher may
  safely drain billing's `outbox_event` table. `profiles_worker.py`'s own docstring documents this.

## Coverage / quality gates (Task P-11 run)

- `ruff format --check` / `ruff check`: clean (one pre-existing, repo-wide `UP042` warning on the
  `class X(str, Enum)` pattern every module's `domain/value_objects.py` uses identically --
  confirmed pre-existing on `catalog.domain.value_objects` too, not a regression).
- `mypy --strict`: clean, 0 errors.
- `import-linter` (all 49 contracts, whole repo): 49 kept, 0 broken.
- `tools/check_migration_safety.py` (QG-09): OK.
- Domain/application coverage floor (90%): every file in `profiles/domain/` and
  `profiles/application/` is >= 97.5% (several at 100%).
- Overall `profiles/` coverage (scoped run): 85.12% (>= 80% floor).
- 103 tests: 46 domain, 8+16 application (`ProfileUseCases`/`VerificationUseCases`), 14 API, 4
  boundary-import, 7 integration (5 real-Postgres repository/outbox-atomicity, 2 downstream
  search-projection).
- **Pre-existing, unrelated failures found during full-suite verification** (not caused by this
  task, reproducible in complete isolation without any `profiles/` file present): `catalog`'s,
  `billing`'s, and `media`'s own `infrastructure/persistence/repository.py`/`worker.py` files hit
  the identical `sqlalchemy.exc.MissingGreenlet` class of bug this task found and fixed in its own
  repository (missing an explicit `session.refresh()` after a versioned UPDATE before re-hydrating
  -- see this module's own `infrastructure/persistence/repository.py::save()` methods' comments),
  plus one flaky `StaleDataError` test and one media-worker double-processing assertion. Confirmed
  by running those exact test files in isolation, both before and unrelated to this task's own
  `composition_root.py` changes. Flagged for a future task to fix (AIR-01 -- out of scope to
  silently patch another module's code here).

## Layout

```
profiles/
|-- interfaces/       # PUBLIC surface: routers, moderation command port, DTOs/ports, DI, errors
|-- application/      # use cases (ProfileUseCases, VerificationUseCases) + ports
|-- domain/           # BusinessProfile, VerificationCase aggregates, value objects, policies
|-- infrastructure/   # SQLAlchemy repositories, media adapter, event projections, sweep worker
`-- README.md         # this file
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
