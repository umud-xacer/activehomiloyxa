# notifications -- module charter

STATUS: implemented (Task P-13) -- the `Notification` aggregate, the 24-event `EventKey` subset
consumer, template resolution from `configuration` snapshots by key+version, preference
enforcement, the three channel adapters (email/web-push/Eskiz SMS) behind ports, the dispatch
worker wiring, and all 3 notifications-tagged `contracts/openapi.yaml` operations. This README is
the module's public charter -- read it before working in this module (Playbook Sec 13).

## Bounded context

- **Module**: `notifications` (BC-10, Generic domain per DDD/SAD classification)
- **Responsibilities**: Template-based delivery over email/web-push/SMS, driven ENTIRELY by
  domain events published by other modules; preference enforcement (FR-NOTIF-004). A PURE event
  sink -- no other module imports it, and it exposes no inbound command port.

## Owned aggregates / entities (DDD Sec 5.10)

- **`Notification`** (`domain/notification.py`) -- one delivery record: `RecipientRef`
  (an id only), `event_key`, `Channel` (`EMAIL`/`WEB_PUSH`/`SMS`), the resolved template
  reference (`template_id`/`template_version_id`, both `configuration`-owned), the frozen
  rendered content (`RenderedContent` -- subject/body, "no live template dependency": a later
  template edit never mutates an already-created notification), `DeliveryStatus`
  (`QUEUED -> SENT | FAILED`), the opaque `provider_message_ref`, and the independent `read_at`
  flag. No setters -- `mark_sent`/`mark_failed` (legal only from `QUEUED`) and
  `mark_read`/`mark_unread` (independent of delivery status) are the only transitions.

## The interface-only-sink guarantee (this module's primary architectural property)

*"Notifications is a PURE event sink... it exposes no inbound command surface to other
modules... If a module 'needs to send a notification', it does not call notifications; it
publishes its own domain event and notifications reacts."* (P-13 task charter, SAD Sec 8.2:
"nothing imports admin, analytics, or notifications -- they are terminal consumers/sinks.")

Proven two ways: statically, by the ALREADY-FROZEN `sink-modules-have-no-inbound-imports` and
`cross-module-notifications` import-linter contracts (the latter stricter than most modules --
`shared_kernel, configuration` only, not even another module's own `interfaces/` package); and by
direct inspection (`apps/backend/tests/notifications/test_boundary_import.py::
test_I04_no_inbound_command_port_exists_for_other_modules_to_call`) that `interfaces/ports.py`'s
frozen `NotificationPort` declares only the 3 user-facing read/read-status methods -- no
"send"/"dispatch"/"notify" method exists anywhere.

## The EventKey subset (mechanically derived, not guessed)

DDD Sec 6's own cross-reference to "the EventKey vocabulary for notification templates (Sec 8.8)"
points to a section that does not exist in the current Domain Model document (confirmed: Sec 8
only has 8.1-8.3). Rather than guess, this task used the one genuinely authoritative,
code-verifiable anchor available: `contracts/events/*.py`'s own frozen class docstrings (Task
P-01), each of which already carries a `"""Principal consumers: ..."""` line copied verbatim
from DDD Sec 6's own event catalogue table. Grepping every event class for "Notifications" in
that line yields exactly 24 events across 7 emitting modules -- enumerated in full in
`apps/backend/tests/notifications/integration/test_event_projection_live.py::
test_exactly_the_documented_24_events_produce_a_notification`, so a future divergence (adding or
removing a route in `infrastructure/event_projection.py` without updating that test) breaks it
deliberately:

| Module | Events |
|---|---|
| identity | `UserRegistered`, `AccountSuspended`, `AccountClosed` |
| profiles | `VerificationRequested`, `BusinessVerified`, `VerificationRejected`, `VerifiedBadgeExpired` |
| catalog | `ListingPublished`, `ListingSuspended`, `ListingArchived`, `ListingDeleted`, `ListingExpired`, `ListingRenewed` |
| billing | `OrderPlaced`, `InvoiceIssued`, `PaymentConfirmed`, `EntitlementExpired`, `EntitlementRevoked` |
| ads | `BannerCampaignScheduled`, `BannerCampaignStarted`, `BannerCampaignEnded` |
| messaging | `ChatInitiated`, `MessageSent` |
| moderation | `ModerationActionTaken` |

`EntitlementActivated` is deliberately excluded (its own frozen docstring never lists
Notifications as a consumer) -- notifications never invents a route the catalogue doesn't name.

## Recipient resolution: identity is off-limits, so composition_root bridges instead

The task's own text suggested reading preferences "through identity's interfaces/" -- but SAD Sec
8.1's own dependency table AND the already-frozen `tools/importlinter.cfg`
(`cross-module-notifications`) both list `identity` as FORBIDDEN for notifications (`shared_kernel,
configuration` only). Surfaced to the repository owner rather than silently resolved; the owner
directed mirroring moderation's own established pattern: `application/ports.py` declares a
narrow, notifications-owned `RecipientDirectoryPort` Protocol; the CONCRETE bridge
(`composition_root._RecipientDirectoryBridge`) reads identity's/profiles'/catalog's real
repositories directly, entirely inside `composition_root.py` (the one place allowed to see every
module's internals) -- `notifications/` itself never statically imports any of them.

Several of the 24 events identify a `BusinessProfileId` (billing/profiles) or a `ListingId`
(a `LISTING`-subject `ModerationActionTaken`), never a `UserId` directly -- the bridge resolves
the owner's `UserId` first (via profiles'/catalog's own repository), then identity's contact
info/preferences. `InvoiceIssued`'s own payload carries neither a profile nor user reference at
all -- resolved instead via a local, notifications-owned `order_recipient_projection` table (not
in the documented Physical Database Design -- the same "locally necessary addition" precedent
`catalog.subscription_projection`/`profiles.verification_entitlement_projection` already
established), populated by that same order's own preceding `OrderPlaced` event.

## Recipient locale: no persisted signal exists, so v1 defaults to uz_latn

No approved document specifies where a recipient's preferred locale for ASYNCHRONOUS dispatch is
persisted -- `identity.user_account` has no locale column anywhere (confirmed against DDD Sec
5.1's own `UserAccount` VO list and the Physical Database Design's full column list), and
`Accept-Language` is explicitly transport-only/per-request (CLAUDE.md), unusable for a background
worker reacting to an event with no active HTTP request. Surfaced to the repository owner; the
owner directed: build the full 4-locale resolution/rendering machinery for real (proven by
`test_dispatch_use_cases.py`'s own parametrized locale test, and the fallback-chain test), but
every REAL dispatch resolves to the canonical `uz_latn` (DEC-19,
`application/dispatch_use_cases.py::_DEFAULT_LOCALE`) until a future task adds a persisted
per-recipient locale preference.

## Web-push: the port and adapter are real; no subscription ever reaches them in v1

Web-push delivery needs a per-browser `PushSubscription` (endpoint + p256dh/auth keys). Checked
exhaustively: `contracts/openapi.yaml`, the Physical Database Design, and the Domain Model name no
operation, schema, or table for registering one -- only the `webPush` boolean opt-in exists on
`NotificationPreferences`. Per CLAUDE.md's own rule ("never hand-write or guess an endpoint that
isn't an operationId... a missing endpoint is an architecture decision"), this task does not
invent one. Surfaced to the repository owner; the owner directed building `WebPushProviderPort`
and its VAPID-signed `pywebpush`-based adapter for real (tested against a synthetic subscription,
`test_providers.py`), documented plainly here that no real subscription ever reaches it in v1 --
a future task adds the registration surface via ADR.

## Preference model: channel-only, never per-category

`contracts/openapi.yaml`'s own `NotificationPreferences` schema (despite its description text
mentioning "by category") has exactly three boolean fields -- `email`/`webPush`/`sms` -- with
`additionalProperties: false`, matching identity's own already-built `NotificationPreferences`
domain VO exactly. Preference enforcement here is therefore channel-only, never per-category or
per-event-type; `application/dispatch_use_cases.py::_preference_allows` is the one place this is
checked.

## Public interface (`interfaces/`)

- **Router** (`interfaces/routers.py`): `notifications_router` (`Notifications` tag, 3
  operations: `listNotifications`/`setNotificationRead`/`markAllNotificationsRead`). Every query
  is scoped to the acting user's own `recipient_user_id` -- ownership is enforced structurally,
  not via a permission key (mirrors catalog/media's own self-service model, not
  moderation/profiles' admin-gated one): a notification belonging to another user is
  indistinguishable from one that does not exist (`NotificationNotFoundError` -> 404), never
  leaking existence via a 403.
- Preference management (`updatePreferences`, `PUT /me/preferences`) is identity's own operation
  (tagged `Users`, already implemented in P-05) -- notifications owns no preference-writing
  endpoint at all, only READS preferences via its own `RecipientDirectoryPort` bridge.

The `interfaces/` package is this module's *only* importable surface (AIR-02) -- moot here in the
inbound direction, since nothing may import it at all (see above).

## Events (`contracts/events/*.py`, frozen since Task P-01)

**Published**: none. Notifications is a pure sink (X-08: "events consumed against the EventKey
catalogue... Notifications is a terminal consumer").

**Consumed** (idempotent via `ProcessedEventRow`, `infrastructure/event_projection.py`, one
handler function per emitting module): the 24-event subset above. Wired end-to-end:

| Emitting outbox | Consumer wiring |
|---|---|
| identity | Folded into `composition_root.make_identity_account_status_projection_handler` (already draining identity's outbox for catalog's own P-12 compensation) -- run by `catalog_worker.py`. |
| catalog | Folded into `composition_root.make_catalog_outbox_fanout_handler` (search+messaging+moderation's existing combined handler) -- run by `search_worker.py`. |
| billing | Folded into `composition_root.make_billing_entitlement_fanout_handler` (catalog+profiles' existing combined handler) -- run by `catalog_worker.py`. |
| messaging | Folded into `composition_root.make_messaging_report_projection_handler` (moderation's existing handler) -- run by `moderation_worker.py`. |
| profiles | The FIRST dispatcher ever built for profiles' own outbox (previously completely undrained) -- `composition_root.provide_profiles_notification_projection_dispatcher`, run by the NEW `notifications_worker.py`. |
| moderation | The FIRST dispatcher ever built for moderation's own outbox -- `composition_root.provide_moderation_notification_projection_dispatcher`, run by `notifications_worker.py`. |
| ads | `infrastructure.event_projection.handle_ads_event` exists and is unit-tested via synthetic `EventEnvelope`s, but `ads` (BC-09) is still an `interfaces/`-only stub with no real aggregate/outbox -- no dispatcher can be wired against a table that does not exist. Its own `bookingProfileId` payload-field assumption is therefore UNVERIFIED against real ads code. |

Only ONE dispatcher may safely drain a given outbox table (`FOR UPDATE SKIP LOCKED` only protects
against the SAME dispatcher's own concurrent workers) -- every already-multi-consumer outbox
above gets a new ROUTE folded into its existing combined handler, never a second dispatcher.

## Transaction hygiene (Playbook Sec 6): never a provider call inside an open transaction

`application/dispatch_use_cases.py::NotificationDispatchUseCases` is deliberately split in two:
`queue_for_event` (resolves recipient/template/preference, writes `QUEUED` rows -- called INSIDE
the idempotent-consumer's own DB transaction) and `dispatch_queued` (the actual channel-provider
call + persisting the outcome -- called AFTER that transaction commits, in the worker's own
post-commit step, each item getting its own fresh session for the follow-up `mark_sent`/
`mark_failed` write). Proven by `test_dispatch_use_cases.py::
test_queue_for_event_never_calls_any_provider_port`.

## Fail-closed dispatch

Any exception from a channel-provider call (missing credentials -- `required_env` raises at
adapter construction; a provider error; a timeout) marks the notification `FAILED`, never `SENT`,
and never silently falls back to a different channel (each dispatch call is scoped to exactly one
channel). Logged with ONLY safe identifiers (notification id, channel, event_key) -- never the
recipient's email/phone/push endpoint or the rendered message body (Security Sec 12).

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: `shared_kernel`, `configuration` only.

MUST NOT import: `identity`, `profiles`, `catalog`, `search`, `media`, `messaging`, `billing`,
`ads`, `moderation`, `admin`, `analytics` -- recipient/profile/listing resolution happens entirely
in `composition_root.py`'s own `_RecipientDirectoryBridge` (see above).
`apps/backend/tests/notifications/test_boundary_import.py` proves this with a deliberate
`import identity`/`import profiles`/`import catalog`/... probe that breaks the
`cross-module-notifications` contract, then reverts it. Also proves (separately)
`sink-modules-have-no-inbound-imports` -- nothing imports notifications.

## Configuration consumed

`NotificationTemplate` snapshots only (`infrastructure/configuration_adapter.
ConfigurationNotificationTemplateAdapter`, reusing `composition_root._ConfigurationPortBridge`
unmodified, the same entity-type-agnostic bridge catalog/billing/search/identity already reuse).
Resolved by `event_key` at dispatch time -- never cached against a specific version beyond what's
frozen onto the `Notification` row itself once rendered.

## Migrations

`infrastructure/migrations/versions/f1e649e88396_*.py` -- hand-written. Creates
`notifications.notification` (the FIRST RANGE-partitioned table any module in this codebase has
needed -- Physical DB Sec 2.10 names it monthly-partitioned on `created_at`, PD-04; created via
raw DDL since Alembic/SQLAlchemy have no declarative `PARTITION BY` helper, with a single
`DEFAULT` partition catching every row -- provisioning real monthly partitions ahead of time is
deployment/ops tooling, out of this task's scope), `order_recipient_projection` (the local
projection, see above), `processed_event`. `read_at` is not in the documented Physical Database
Design's own column list -- added because the already-frozen `contracts/openapi.yaml` requires it
(`Notification.readAt`, `setNotificationRead`, `markAllNotificationsRead`). Unlike every other
implemented module, there is no `outbox_event` table here -- notifications never publishes.
Verified end-to-end against real PostgreSQL (`alembic upgrade head` / `alembic downgrade base`,
both clean, plus a real INSERT/SELECT round-trip against the partitioned table) during this task.

## Known gaps (flagged, not silently worked around)

- **Recipient locale is not yet a real per-user signal** -- every dispatch resolves to `uz_latn`
  until a future task persists a preferred-locale field somewhere (not on `identity.user_account`
  today, and adding one is out of this task's scope -- AIR-01, that module is already merged).
- **Web-push has no subscription-registration surface** -- the port/adapter are real and tested,
  but no code path in v1 ever constructs a real `WebPushSubscriptionSnapshot`, since no
  operation/table for it exists anywhere in the approved documents.
- **`ads`' event consumer is unverified against real payloads** -- `handle_ads_event`'s own
  `bookingProfileId` field assumption cannot be checked against real code, since `ads` (BC-09) is
  still an `interfaces/`-only stub with zero real implementation.
- **`ModerationActionTaken` on a `CONVERSATION`-subject case is never notified** -- no reliable
  single "affected user" id exists anywhere in that event's own payload chain (a conversation has
  two participants, and the case's own payload never names which one is at fault).
- **OTP delivery never routes through this module** -- DDD Sec 5.10's own "Policies" row names an
  `OtpChannelPolicy [P]` conceptually under BC-10, but no OTP-related event exists anywhere in the
  frozen event catalogue for this module to react to, and identity's own already-built
  `AuthenticationUseCases` sends OTP directly via its own Eskiz adapter
  (`identity.domain.value_objects.NotificationPreferences`'s own docstring: "OTP is always
  delivered via SMS regardless of preference... enforced by the OTP send path never consulting
  this VO"). Confirmed as an already-settled precedent from Task P-05, not reopened here.
- **Discovered and fixed a genuine bug in catalog's own repository during P-12's own compensation
  test, not this task** -- unrelated to notifications; noted here only because
  `_RecipientDirectoryBridge.resolve_recipient_for_listing` reads catalog's `SqlalchemyListing
  Repository` and would have hit the same class of bug had it not already been fixed.

## Coverage / quality gates (Task P-13 run)

- `ruff format --check` / `ruff check`: clean.
- `mypy --strict`: clean, 0 errors (373+ source files, whole backend).
- `import-linter` (all 49 contracts, whole repo): 49 kept, 0 broken.
- `tools/check_migration_safety.py` (QG-09): OK.
- Domain/application coverage floor (90%): every file in `notifications/domain/` and
  `notifications/application/` is >= 92.6% (most at 100%).
- Overall repo coverage (full suite): 86.6% (>= 80% floor).
- 83 tests: 9 domain (`Notification` transitions), 30 application (dispatch use cases +
  notification use cases, including all-four-locale/preference-suppression/fail-closed/
  transaction-hygiene), 6 configuration-adapter, 6 boundary-import/no-inbound-surface/provider-
  isolation, 8 provider adapters (email/Eskiz/web-push, each mocked at the wire boundary), 1 PII,
  19 API, 4 real-Postgres integration (repository round-trip) + the EventKey-coverage/idempotency/
  InvoiceIssued-projection integration suite (23 positive cases + 10 negative cases + 2 dedicated
  tests, all against real Postgres).
- **Pre-existing, unrelated failures found during full-suite verification** (not caused by this
  task, reproducible in complete isolation without any `notifications/` file present, already
  documented in `moderation/README.md`'s own run notes): billing's own unfixed `MissingGreenlet`
  bug, one flaky catalog `StaleDataError` test, one media storage-key/worker test pair, and
  OpenSearch's own pre-existing `flattened`-mapping rejection. Flagged, not silently patched
  (AIR-01).

## Layout

```
notifications/
|-- interfaces/       # PUBLIC surface: user-facing router, DTOs/ports, DI, errors
|-- application/      # NotificationUseCases, NotificationDispatchUseCases + ports
|-- domain/           # Notification aggregate, value objects, typed exceptions
|-- infrastructure/   # SqlalchemyNotificationRepository, event projections, provider adapters
`-- README.md         # this file
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
