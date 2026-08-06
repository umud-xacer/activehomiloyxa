# moderation -- module charter

STATUS: implemented (Task P-12) -- the `ModerationCase` aggregate, the fixed `ResolutionAction`
verb set (extended by ADR-0003 to cover profiles as a fourth target), report intake, automated
flagging (reactive-only), the reviewer queue, `ModerationActionService`'s "compensations, not
cascades" dispatch through three narrow command ports, all 3 moderation-tagged
`contracts/openapi.yaml` operations, event publication/consumption via the transactional outbox,
and the composition-root wiring bridging catalog/identity/profiles. This README is the module's
public charter -- read it before working in this module (Playbook Sec 13).

## Bounded context

- **Module**: `moderation` (BC-11, Supporting domain per DDD/SAD classification)
- **Responsibilities**: Report intake, automated flagging, the moderation work queue, the closed
  action-verb set, and issuing compensating commands to the modules that actually own the state
  being moderated (catalog/identity/profiles) -- never mutating their state directly.

## Owned aggregates / entities (DDD Sec 5.11)

- **`ModerationCase`** (`domain/moderation_case.py`) -- the work item. Lifecycle
  `Open -> InReview -> Resolved`; `Resolved` is **terminal and immutable** (every mutating
  method's first check is `_guard_not_terminal` -- see `TerminalModerationCaseError`; no method
  on this class can touch a case once `status` is `RESOLVED`). Holds a `Subject` (what is being
  moderated), an `Origin` (how the case entered the queue), and, once resolved, a `Resolution`
  (the verb + note + moderator + timestamp).
- **`ModerationActionService`** (`application/action_service.py`) -- not an aggregate; the
  module's single most important class (see "The interface-only-action guarantee" below).

## The interface-only-action guarantee (this module's primary invariant)

*"Moderation state changes are executed only by the owning context on command from Moderation,
never by direct mutation"* (I-24; DDD Sec 5.11: "executes the verb by issuing commands to BC-03
or BC-01 through their explicit interfaces").

`ModerationActionService.execute` is the **only** place a resolved `ModerationCase`'s
`ResolutionAction` turns into an actual cross-module effect, and it does so exclusively through
three narrow, moderation-owned `Protocol`s declared in `application/ports.py`
(`ListingModerationCommandPort`/`AccountSuspensionCommandPort`/`ProfileModerationCommandPort`) --
never a static import of catalog/identity/profiles, never a direct write to another module's
tables, never a reimplementation of another module's state machine. Proven two ways:
statically, by the `cross-module-moderation` import-linter contract (stricter than every other
module's own -- it forbids **all 12** other bounded-context modules outright, including their
`interfaces/` packages, not just their internals -- see "Dependencies" below and
`apps/backend/tests/moderation/test_boundary_import.py`); and behaviourally, by
`apps/backend/tests/moderation/test_action_service.py`, which asserts every verb reaches
**exactly one** command-port method with the right arguments and no others are touched.

The concrete bridge adapters implementing these three Protocols against the real target ports
(`catalog.interfaces.moderation_port.CatalogListingModerationAdapter`,
`identity.application.AdminIdentityUseCases.change_user_status`,
`profiles.interfaces.moderation_port.ProfilesModerationAdapter`) are defined entirely in
`apps/backend/src/composition_root.py` (`_ModerationListingCommandBridge`/
`_ModerationAccountSuspensionBridge`/`_ModerationProfileCommandBridge`) -- the one place allowed
to see every module's internals at once -- never inside `moderation/` itself.

## BR-MOD-02: the fixed verb set, and the subject-scoped legality guard

`domain/value_objects.py::ResolutionAction` is a closed nine-value enum (`HIDE`, `REJECT`,
`SUSPEND`, `REQUEST_CORRECTION`, `REMOVE`, `SUSPEND_ACCOUNT`, `DISMISS`, plus ADR-0003's
`REVOKE_BADGE`/`ARCHIVE_PROFILE`) -- `[P]` per DDD's own marker convention, changeable only by
release + ADR, never by configuration. Not every verb is legal for every `SubjectType`:
`ACTIONS_BY_SUBJECT_TYPE` maps each of the four subject types (`LISTING`/`USER`/`PROFILE`/
`CONVERSATION`) to the verbs that make semantic sense for it (e.g. `SUSPEND_ACCOUNT` needs a
`UserRef` to suspend, so applying it to a `LISTING`-subject case is a caller bug, not a legal
decision). `ModerationCase.resolve` enforces this structurally, raising
`InvalidResolutionForSubjectError` -- there is no path to a resolved case with an
invalid verb/subject pairing. Verb-to-catalog-transition mapping (5 listing-directed verbs onto
catalog's 3 relevant lifecycle transitions) is documented in
`catalog.interfaces.moderation_port`'s own module docstring (this task's own defensible choice,
no approved document specifies the literal mapping -- the same class of gap
`catalog.application.duplicate_detection_service` names for FR-ADV-009).

## ADR-0003: extending Subject/ResolutionAction to cover profiles

DDD Sec 5.11's own `Subject`/`ResolutionAction` tables name only `Listing`/`Conversation`/`User`
targets and 7 verbs -- no path to badge-revocation/profile-archival exists, even though DDD Sec
5.2's own `VerifiedBadge` sub-state table documents `Revoked` as triggered "e.g. following a
moderation action" and the frozen `contracts/openapi.yaml` (Task P-01) already reserved
`ModerationCase.subjectType`/`resolutionAction` as open string enums that this task's own scope
explicitly names profiles as a fourth target for. Surfaced to the repository owner rather than
resolved unilaterally; the owner directed extending the model via ADR to add `PROFILE` as a
fourth subject type and `REVOKE_BADGE`/`ARCHIVE_PROFILE` as two new verbs. See
`docs/adr/0003-moderation-profile-target-extension.md` for the full record --
`contracts/openapi.yaml`, `docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml`,
`docs/frontend_docs/`'s copy, and this module's own `interfaces/{dto,ports}.py` were all
extended together in the same change as this task.

## The FlaggingService is reactive-only

DDD Sec 5.11 names a `FlaggingService [P]` ("automated validation rules... flag content at or
after publication," FR-MOD-002) as part of this bounded context. Because moderation may
statically import `shared_kernel` only (stricter than every other module -- SAD Sec 8.1's own
moderation row), it structurally **cannot** read `configuration`'s rule definitions or
`catalog`'s content to evaluate a flagging rule itself. The rule *evaluation* therefore happens
entirely in the content-owning module (catalog's own duplicate-detection flow, Task P-07);
moderation's `auto_flag` use case (`application/moderation_use_cases.py`) only opens/attaches a
`ModerationCase` once catalog's real `ListingFlagged` event has already arrived
(`infrastructure/event_projection.py::handle_listing_flagged`). This is a logically forced
consequence of the enforced import-linter contract, not an implementation shortcut.

## Public interface (`interfaces/`)

- **Router** (`interfaces/routers.py`): `admin_moderation_router` (`Administration` tag, 3
  operations: `listModerationQueue`/`getModerationCase`/`applyModerationAction`), gated end-to-end
  by the `moderation:case:review` permission key.
- **`interfaces/ports.py`** (frozen Task P-01 stubs): `ModerationPort`, `ModerationCommandTargetPort`.
- Report submission (`createReport`) is **not** implemented here -- it is messaging's own
  operation (Task P-10, `messaging.application.report_use_cases.ReportUseCases.create_report`);
  moderation only consumes the resulting `ContentReported` event.

The `interfaces/` package is this module's *only* importable surface (AIR-02). Nothing in
`application/`, `domain/`, or `infrastructure/` may be imported by another module, ever.

## Events (`contracts/events/moderation.py`, frozen since Task P-01)

**Published**, via the transactional outbox (never dual-write):

| Event | Emitted when |
|---|---|
| `ModerationActionTaken` | `ModerationUseCases.resolve_case`, in the SAME transaction as the case's own resolution (DB Architecture Sec 1.3) -- the target-command dispatch (`ModerationActionService.execute`) is a SEPARATE, eventually-consistent step run immediately after, never inside the same transaction (mirrors `profiles.application.VerificationUseCases.decide_verification`'s own two-phase commit-then-react shape). |

**Consumed** (idempotent via `ProcessedEventRow`, `infrastructure/event_projection.py`):

- Messaging's real `ContentReported` (Task P-10) -- opens/attaches a `ModerationCase`
  (`handle_content_reported`). Wired end-to-end: `composition_root.
  make_messaging_report_projection_handler`, run by the new `moderation_worker.py` process (the
  first, and as of this task only, consumer of messaging's `outbox_event` table).
- Catalog's real `ListingFlagged` (Task P-07) -- opens/attaches a `ModerationCase`
  (`handle_listing_flagged`). Catalog's outbox already had one consumer (search/messaging, via
  `composition_root.make_catalog_outbox_fanout_handler`, run by `search_worker.py`) -- a second,
  independent `OutboxDispatcher` on the same table would race it (`FOR UPDATE SKIP LOCKED` only
  protects against the SAME dispatcher's own concurrent workers), so this route is folded into
  that SAME combined handler rather than given its own dispatcher.

## The account-suspension compensation chain (DB Architecture Sec 14.4's worked example)

*"Account suspension -> listings hidden by catalog's own transition."* Resolving a `USER`-subject
case with `SUSPEND_ACCOUNT` calls `AccountSuspensionCommandPort.suspend_account`
(`composition_root._ModerationAccountSuspensionBridge`, delegating to identity's real
`AdminIdentityUseCases.change_user_status`), which publishes a real `AccountSuspended` event on
identity's own outbox. Draining that event (`composition_root.
make_identity_account_status_projection_handler`, run by `catalog_worker.py` -- catalog is the
CONSUMER, so its own worker process runs the dispatcher) routes it into catalog's already-built
`handle_identity_event`, which calls `ListingUseCases.suspend_all_by_owner` -- suspending every
currently-visible (`PUBLISHED`/`EDITED`) listing that account owns, through the SAME
`Listing.suspend()` transition an owner-invoked status change would use, appending catalog's OWN
`LifecycleTransitionRecord`. Moderation never writes catalog's tables, and identity never reaches
into catalog's schema -- the fact arrives via the outbox (X-04), a compensation, never a cascade.
Proven end-to-end against real PostgreSQL + Redis, spanning all three modules' schemas, in
`apps/backend/tests/moderation/integration/test_account_suspension_compensation_live.py`.

**Discovered and fixed as part of this task**: this integration test surfaced a genuine
pre-existing bug in catalog's own `SqlalchemyListingRepository.save()` (missing the
`session.refresh(row)` call after a versioned UPDATE, causing `sqlalchemy.exc.MissingGreenlet` on
every `get_by_id`-then-`save()` sequence in a fresh session) -- the identical bug class already
found and fixed in `profiles.infrastructure.persistence.repository`'s own `save()` methods during
Task P-11. Surfaced to the repository owner rather than silently patched or routed around; the
owner directed applying the same one-line fix, mirroring the existing precedent exactly.

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: `shared_kernel` only.

MUST NOT import: `identity`, `profiles`, `catalog`, `configuration`, `search`, `media`,
`messaging`, `billing`, `ads`, `notifications`, `admin`, `analytics` -- **not even their own
`interfaces/` packages**, unlike every other module's own `cross-module-*` contract. Every
cross-module effect is issued at runtime through the module's own narrow local Protocols
(`application/ports.py`), with the concrete bridge to the real target module's port built entirely
in `composition_root.py`. `apps/backend/tests/moderation/test_boundary_import.py` proves this with
a deliberate `import catalog`/`import identity`/`import profiles`/`import catalog.interfaces`
probe that breaks the `cross-module-moderation` contract, then reverts it.

## Configuration consumed

**None.** Moderation cannot statically import `configuration` (SAD Sec 8.1's own table) -- see
"The FlaggingService is reactive-only" above for why this is a structural consequence, not a gap.

## Migrations

`infrastructure/migrations/versions/2742dd06f884_*.py` -- hand-written (not autogenerated, same
reasoning as every other module's first migration). Creates `moderation.moderation_case`,
`outbox_event`, `processed_event`. `subject_type`'s `PROFILE` value and `resolution_action`'s
`REVOKE_BADGE`/`ARCHIVE_PROFILE` values are not in the documented Physical Database Design's own
CHECK constraint list -- added per ADR-0003. Verified end-to-end against real PostgreSQL
(`alembic upgrade head` / `alembic downgrade base`, both clean) during this task.

## Known gaps (flagged, not silently worked around)

- **`CONVERSATION`-subject cases can never reach a messaging-specific command.** No document
  names a conversation-directed catalog/identity/profiles command beyond suspending the reported
  user's account -- messaging is not a command target in this task's own Dependencies list (only
  identity/catalog/profiles/configuration). A `CONVERSATION`-subject case can request correction,
  suspend the reported user's account, or be dismissed, never a listing- or profile-specific verb.
- **No dedicated worker exists for messaging's outbox drain until this task.** `moderation_worker.py`
  is new (Task P-12) -- messaging's `outbox_event` table had no consumer at all before this task.

## Coverage / quality gates (Task P-12 run)

- `ruff format --check` / `ruff check`: clean.
- `mypy --strict`: clean, 0 errors (362 source files).
- `import-linter` (all 49 contracts, whole repo): 49 kept, 0 broken.
- `tools/check_migration_safety.py` (QG-09): OK. This task also **fixed a universal false-positive
  in the checker itself** (docstring-prose lines matching destructive-operation patterns, and
  `ruff format`'s multi-line wrapping moving the approval marker off the exact matched line) --
  a defect in shared tooling blocking every module's own QG-09 run, not routed around per the
  standing orders' explicit instruction to fix a gate rather than bypass it.
- Domain/application coverage floor (90%): every file in `moderation/domain/` and
  `moderation/application/` is >= 95.8% (most at 100%).
- Overall repo coverage (full suite): 86.9% (>= 80% floor).
- 85 tests: 24 domain (`ModerationCase` + policies), 22 application (use cases + the dedicated
  interface-only-action suite), 3 boundary-import (deliberate-violation-then-revert, including the
  stricter "even `catalog.interfaces` is forbidden" case), 15 API, 21 integration (real-Postgres
  repository/outbox-atomicity/event-projection, plus the 3-schema account-suspension compensation
  test).
- **Pre-existing, unrelated failures found during full-suite verification** (not caused by this
  task, reproducible in complete isolation without any `moderation/` file present): `billing`'s own
  `infrastructure/persistence/repository.py` still has the unfixed `MissingGreenlet` bug class
  (out of this task's scope -- billing was never touched), plus one flaky catalog
  `StaleDataError` test, one media storage-key/worker test pair, and OpenSearch's own pre-existing
  `flattened`-mapping rejection (all previously documented in `profiles/README.md`'s own "Known
  gaps" / Task P-11 run notes). Flagged, not silently patched (AIR-01).

## Layout

```
moderation/
|-- interfaces/       # PUBLIC surface: admin router, DTOs/ports, DI, errors
|-- application/      # ModerationUseCases, ModerationActionService + narrow command ports
|-- domain/           # ModerationCase aggregate, value objects, policies
|-- infrastructure/   # SqlalchemyModerationCaseRepository, event projections
`-- README.md         # this file
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
