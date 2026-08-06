# messaging -- module charter

STATUS (Task P-10): fully implemented across all four layers, shared by TWO runtimes (DEC-11) --
the stateless HTTP tier (`main.py`, ten REST operations) and a separate realtime gateway
(`realtime_main.py`, one WebSocket endpoint), both invoking the exact same `application`/`domain`
code. This README is the module's public charter -- read it before working in this module
(Playbook Sec 13). See `TRACEABILITY.md` for the requirement -> code -> test matrix.

## Bounded context

- **Module**: `messaging` (BC-07, Supporting domain per DDD/SAD classification)
- **Responsibilities**: Real-time, listing-scoped conversations; blocking; rate limiting;
  privacy-gated phone reveal; abuse reporting (intake only).

## Owned aggregates / entities (DDD Sec 5.7)

- **`Conversation` [P]** (`messaging.domain.conversation.Conversation`) -- `listing` (`ListingRef`,
  id-only), `participants` (`ParticipantPair` -- exactly two fixed `UserId`s, I-19), `status`
  (`INITIATED`/`ACTIVE`/`ARCHIVED`), `messages` (its own `Message` children, no repository of
  their own), `last_message_at`. `Conversation.start` always produces `ACTIVE` with exactly one
  message (`startConversation` sends its first message atomically -- no "empty conversation"
  operation exists). `archive()` is lifecycle-complete but unwired (no OpenAPI operation calls
  it).
  - **`Message`** (`messaging.domain.message.Message`) -- `author_user_id`, `body`, `sent_at`,
    `delivered_at` (set by the realtime gateway on successful WS push), `read_at` (**no v1 code
    path ever sets this** -- see "Known gaps").
- **`Block` [P]** (`messaging.domain.block.Block`) -- a directed `BlockPair`, its own independent
  aggregate/repository, consulted on every send/initiate. No update methods: unblock is a
  physical `DELETE` (Physical DB Design), not a guarded transition.

## I-19 (DDD Sec 9) -- proven at every layer, enforced inside the aggregate

"A Conversation has exactly two participants; a blocked user can neither initiate nor continue
contact with the blocker." Both clauses are checked **inside** `Conversation.start`/`send_message`
themselves (`BlockedParticipantError`/`NotAParticipantError`), not only by the calling use case --
the use case resolves the block fact via `BlockRepository` *before* calling the aggregate and
passes it in as a plain boolean, mirroring `identity.domain.policies.OtpThrottlePolicy`'s and
`billing.domain.entitlement.EntitlementFactory`'s own "pure domain decision from an
externally-resolved fact" shape (domain/ itself performs no I/O, Rule 1). Proven at the domain
layer (`test_conversation.py::TestI19*`), the application layer
(`test_conversation_use_cases.py`'s own I-19 tests), and the API layer
(`test_api.py`'s 403 assertions).

## The two runtimes share one core (DEC-11)

- **Stateless HTTP tier** (`apps/backend/src/main.py` mounts `messaging.interfaces.routers.
  messaging_router`): all ten REST operations. Holds no WebSocket/connection state -- publishing
  to Redis (`RealtimePublisherPort`) is a fire-and-forget bus write, not a held connection.
- **Realtime gateway** (`apps/backend/src/realtime_main.py`, a SEPARATE FastAPI app/process):
  mounts only `messaging.interfaces.ws.realtime_router` (`GET /ws/messaging`). Authenticates the
  same session (`get_acting_user` -- FastAPI resolves `Cookie`/`Header` params identically for
  HTTP and WebSocket routes) *before* `websocket.accept()`, matching SAD Sec 6's "the realtime
  tier authenticates the same session before upgrading to WebSocket" -- an unauthenticated caller
  never completes the WSS upgrade (verified: `test_api.py::TestStatelessHttpTier`, and manually
  via `TestClient.websocket_connect` raising `InvalidSessionTokenError` for no cookie). No
  client-to-server wire protocol exists in v1 (`sendMessage` is REST-only) -- this endpoint is a
  pure server -> client push channel: it relays `MessageSubscriberPort.listen`'s Redis pub/sub
  yields and marks each relayed message `delivered_at` via the SAME `ConversationUseCases.
  mark_message_delivered` the HTTP tier's own module defines.
- **Neither runtime duplicates business logic** -- both call into the exact same
  `ConversationUseCases`/`BlockUseCases`/`ReportUseCases` classes; `interfaces/routers.py` and
  `interfaces/ws.py` are both thin translation layers only.

Redis is a bus, never the source of truth: one channel per recipient user
(`messaging:user:{userId}`), not per conversation -- a single WS connection receives every
message across every conversation its owner participates in without re-subscribing when a new
conversation starts. A message published while the recipient has no active connection is not lost
(PostgreSQL already has it, fetched on the next `listMessages` call) -- only its live push is
missed.

## Public interface (`interfaces/`)

Frozen P-01 stubs (`interfaces/dto.py`, `interfaces/ports.py`) untouched. `interfaces/routers.py`
(REST, HTTP tier only) and `interfaces/ws.py` (WebSocket, realtime tier only) are this task's own
real implementation. The `interfaces/` package is this module's *only* importable surface
(AIR-02).

## Routers (`interfaces/routers.py`) -- exactly the ten messaging-tagged operations

`listConversations`, `startConversation`, `getConversation`, `listMessages`, `sendMessage`,
`revealPhone`, `listBlocks`, `blockUser`, `unblockUser`, `createReport`. All session-authenticated
(no `security: []` override in `contracts/openapi.yaml` for any of the ten). Ownership is a
domain-level guard (`NotAParticipantError` -> 403), never `AuthorizationPort` -- messaging has no
permission-gated operation at all (see "Authentication bridge" below).

## Authentication bridge (messaging DOES statically import identity's interfaces/, deliberately)

Unlike catalog/billing (which chose self-imposed restraint even though SAD Sec 8.1 permits
`-> identity` for them too), messaging's own `application/ports.py` imports `identity.interfaces.
ports.ContactPolicyPort` directly rather than reinventing an identical Protocol -- its own
docstring names messaging as the intended, purpose-built consumer ("consulted in-process by
messaging (privacy-gated phone reveal)"), and only `identity.interfaces` (never `identity.domain`/
`identity.infrastructure`) crosses the boundary (AIR-02). Session/account resolution itself
(`provide_messaging_acting_user`) still lives entirely at the composition root, matching every
other module's own discipline.

### `ContactPolicyPort.reveal_phone` -- an additive extension to identity's own designated surface

`ContactPolicyPort` (built in P-05, never wired to a real consumer until this task) originally
exposed only `get_phone_reveal_mode` (the enum decision), not the phone number itself -- no port
anywhere returned account phone data to another module. This task adds one new method,
`reveal_phone(account_id) -> str | None`, to `identity.interfaces.ports.ContactPolicyPort` and
implements it on `identity.infrastructure.public_port_adapters.ContactPolicyPortAdapter` (mode
check + the actual number read, both staying inside identity -- the module that owns the data and
the decision to release it). This is additive and non-breaking (the pre-existing method is
untouched, and nothing called `ContactPolicyPort` before this task), mirroring the P-09 precedent
of extending `configuration.domain.whitelist.PERMISSION_KEYS` -- touching another module's own
*designated extension point*, not its internals. New tests added to
`apps/backend/tests/identity/test_public_port_adapters.py` (all 4 pass; the other 9 pre-existing
identity tests in that file are unaffected).

## The listing-owner projection -- resolving `startConversation`'s recipient without importing catalog

`ConversationCreateRequest` carries `listingId` + `message` only, deliberately no recipient field
(a client-asserted recipient would let a caller message an arbitrary user under someone else's
real listing id). The server must resolve "who owns this listing" from `listingId` alone, but
messaging may not import `catalog` (AIR-10). The mechanism: a local, idempotent projection
(`listing_owner_projection`, keyed by `listing_id`) rebuilt from catalog's own `ListingCreated`
event (I-01: owner is fixed for life, so one observation per listing is sufficient) --
`ListingOwnerReaderPort`/`SqlalchemyListingOwnerProjectionReader` on the read side,
`infrastructure.event_projection.handle_listing_created` (idempotent via messaging's own
`ProcessedEventRow` ledger) on the write side. `ListingOwnerUnknownError` (503
`DEPENDENCY_DEGRADED`) is returned, never guessed, when the projection has not yet observed a
listing.

### A real, confirmed wiring conflict, and how it was resolved

Catalog's own `outbox_event` table already had exactly one consumer wired at the composition root
before this task: `search.infrastructure.worker.SearchIndexingWorker`'s own internal
`OutboxDispatcher` (Task P-08). `backbone.outbox.dispatcher.OutboxDispatcher.drain_once` claims
rows by mutating a SHARED `dispatch_status` column (`FOR UPDATE SKIP LOCKED` only protects against
two workers of the *same* dispatcher double-claiming a row -- not against two *independent*
dispatcher instances racing for the same table). A second, independent `OutboxDispatcher` on
catalog's outbox for this task's own projection need would race search's for every row, including
`ListingCreated` -- which search's own handler silently ignores but would still mark `DISPATCHED`
if it won that race, permanently starving messaging's projection. `catalog/README.md`'s own "Known
gaps" #1 already anticipated exactly this situation ("a future task adding a second independent
consumer ... would need a different mechanism").

**Resolution**: `composition_root.make_catalog_outbox_fanout_handler` builds ONE combined handler
-- search's own `make_search_event_handler` (imported unmodified from `search.infrastructure`)
runs first, then `handle_listing_created` (only for the one event type it cares about) --
attached to the ONE dispatcher (`provide_catalog_outbox_fanout_dispatcher`) that now drains
catalog's outbox. `search_worker.py`'s entrypoint runs this combined dispatcher instead of
constructing `SearchIndexingWorker` directly (that class's own `catalog_outbox_model` constructor
parameter has no default, so passing one back in would recreate the exact race this exists to
avoid). **Neither `search/` nor `catalog/`'s own source is modified** -- only composition-root
wiring and which worker entrypoint runs it, both explicitly outside every module's package tree
and exempt from `tools/importlinter.cfg`'s module-boundary contracts by design. `search`'s own
read path (`provide_search_use_cases`, used by `search_router`) is completely unaffected.

## Rate limiting (BR-MSG-03) -- an implementation-chosen constant, same precedent as identity's OTP throttle

Security Sec 3.1 and BR-MSG-03 only specify a QUALITATIVE control ("per-user messaging rate
limits ... on both conversation initiation and message send") -- no literal number appears
anywhere in the approved documents, the exact same situation `identity.domain.policies.
OtpThrottlePolicy` already faced for NFR-SEC-004 (that module's own docstring: "no literal numbers
appear in the approved documents"). `messaging.domain.policies.MessageRateLimitPolicy` follows
that precedent exactly: a fixed, flagged constant (`MESSAGE_RATE_LIMIT_MAX_PER_WINDOW = 20` per
`MESSAGE_RATE_LIMIT_WINDOW_SECONDS = 60`), counted per-user (not per-conversation) across every
conversation the author has sent into. Unlike identity's threshold, this one cannot even in
principle be sourced from `configuration` -- SAD Sec 8.1's static import matrix permits messaging
to import only `shared_kernel` + `identity`, not `configuration`.

## Events published (`contracts/events/messaging.py`, frozen since Task P-01)

`ChatInitiated` (conversation start only), `MessageSent` (every message, both the atomic first
one and every reply -- so Notifications can decide whether to page an offline recipient),
`UserBlocked`, `PhoneRevealed` (only on a permitted reveal), `ContentReported` (routed to
moderation, BC-11 -- this task does NOT implement moderation case handling, only the intake
event). Published via the transactional outbox, same transaction as the state change that
triggers each one. No phone number is ever placed in an event payload (PII discipline, Security
Sec 3.1).

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: `shared_kernel`, `identity` -- confirmed unchanged from the P-01 stub, and
only `identity.interfaces`.

MUST NOT import: `configuration`, `catalog`, `profiles`, `search`, `media`, `billing`, `ads`,
`notifications`, `moderation`, `admin`, `analytics` internals -- listings are referenced by
identifier only (`ListingRef`); NO static dependency on catalog at all (verified: `test_boundary_
import.py`, a deliberate `import catalog` breaks the `cross-module-messaging` contract, then
reverts).

## Migrations

`infrastructure/migrations/versions/98f4e9a7713f_..._schema.py` creates `messaging.conversation`
(`ck_conversation_distinct_participants`, `ux_conversation_listing_initiator`), `messaging.message`
(FK `ON DELETE CASCADE`, no `AggregateMixin` -- append-only, only `delivered_at`/`read_at` ever
mutate post-insert), `messaging.block` (`ck_block_distinct_users`, `ux_block_blocker_blocked`, no
`AggregateMixin` -- create + physical delete only), `messaging.listing_owner_projection` (keyed by
`listing_id` itself, no `AggregateMixin` -- a projection, not an aggregate), `messaging.
outbox_event`, `messaging.processed_event`. Hand-written, not `alembic revision --autogenerate`
(same reason as every prior module's first migration).

## The realtime gateway container (Infra Sec 6, `realtime`)

`Dockerfile` (repo root's own first-ever application Dockerfile -- no Dockerfile existed anywhere
in this repository before this task, and no prior task added one) builds a slim Python 3.13 image
running `uvicorn realtime_main:app`. `deployment/compose/docker-compose.yml` gains a `realtime`
service: private network only (no published host port -- reached only via nginx's own WSS
upgrade, matching every other backing/app service's existing pattern), `GET /health` healthcheck,
depends on `postgres`+`redis`. Scoped to only the `realtime` service -- `api`/`web`/`worker`
containers for every OTHER module remain out of this task's scope (they were explicitly excluded
from every prior task too; see `deployment/compose/docker-compose.yml`'s own header comment).

## Known gaps (flagged, not silently worked around)

1. **No `markMessageRead` operation or WS write protocol exists.** `Message.read_at` is modelled
   (the physical column exists) but no v1 code path -- REST or WebSocket -- ever sets it. No
   document specifies a read-receipt mechanism; inventing one would be undocumented behaviour.
2. **`Conversation.archive()` is implemented and domain-tested but has no API caller.** No
   OpenAPI operation archives a conversation; the physical/status schema documents the state
   (matches the precedent of billing's own unwired `Order.fulfill`/`Invoice.void`).
3. **`MESSAGE_RATE_LIMIT_MAX_PER_WINDOW`/`_WINDOW_SECONDS` are undocumented judgment calls** --
   see "Rate limiting" above for the reasoning and the precedent this follows.
4. **The `RateLimitExceededError` -> 429 mapping carries no `Retry-After`/`X-RateLimit-*`
   header** -- `simple_problem_builder` (`backbone.errors`) has no header-attachment mechanism at
   all; `identity.interfaces.errors`'s own `OtpThrottledError` -> 429 mapping has the identical
   gap. Pre-existing, shared, not unique to this task.
5. **"Presence" has zero behavioural specification anywhere** in the approved documents (it
   appears only as a noun in container diagrams) -- no presence/online-status feature is built;
   only the mandatory WS session-authentication step is implemented.
6. **No scenarios were added to `tests/authorization_matrix.py`.** That shared harness is built
   specifically around `identity.domain.AuthorizationService.authorize` (permission-key Gate-3/4
   checks) -- messaging has zero permission-gated operations (every ownership check is a domain
   guard, `NotAParticipantError`, never an `AuthorizationPort` call), the same situation catalog's
   own self-service CRUD already established (only catalog's one genuinely permission-gated op,
   `catalog:listing:moderate`, got matrix scenarios). I-19's participant/ownership scenarios are
   instead proven directly at the domain, application, and API layers (`test_I19_*` across three
   files) -- adding artificial matrix entries would misrepresent what that harness tests.
7. **Pre-existing, unrelated**: `tools/check_migration_safety.py` flags a false positive on this
   migration file's own docstring (the same standardised template every prior module's first
   migration uses verbatim), and the codebase-wide `ruff`/`mypy` pre-existing findings in
   `identity`/`catalog`/`media` and `apps/backend/tests/backbone/` are unrelated to this task and
   were left untouched (AIR-01).

## Coverage / quality gates (Task P-10 run)

76 tests (`apps/backend/tests/messaging/`: 63 fast unit/API + 13 Postgres/Redis-gated
integration), plus 4 new tests in `apps/backend/tests/identity/test_public_port_adapters.py` for
the `ContactPolicyPort.reveal_phone` extension. mypy --strict clean, ruff clean, bandit SAST
clean, all 49 `tools/importlinter.cfg` contracts kept, domain coverage 98.90%, application
coverage 96.61%, overall module coverage 81.14%. The Postgres/Redis-gated integration tests
(`integration/`) are present and structurally correct but unexecutable in this sandbox (no
`POSTGRES_HOST`/`REDIS_HOST`), the same class of gap already documented for every prior task's own
integration suites.

## Layout

```
messaging/
|-- interfaces/       # PUBLIC surface: REST routers (HTTP tier), WS router (realtime tier), auth, di, errors, frozen P-01 DTOs/ports
|-- application/      # use cases (conversation/block/report) + ports
|-- domain/           # Conversation (+ Message children), Block, value objects, policies, invariants
|-- infrastructure/   # adapters: persistence, Redis pub/sub, catalog listing-owner event projection
|-- README.md         # this file
`-- TRACEABILITY.md    # requirement -> code -> test matrix
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
