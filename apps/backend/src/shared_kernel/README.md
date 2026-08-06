# shared_kernel

STATUS: complete per DDD Sec 5.14 (Task P-02), minus the one item deliberately not built here
-- see "What's deliberately NOT here" below. No aggregates, no domain services, no business
rules; 100% test coverage.

Not one of the thirteen bounded contexts -- the zero-dependency base every module (including
`admin`) statically depends on (SAD Sec 7, Sec 8.1; Playbook Sec 2 "Shared-code rule", AIR-01).
This is the *only* code every one of the 13 modules is allowed to import.

## Scope (DDD Sec 5.14, exhaustive: "the shared kernel contains only ... nothing with business
behaviour enters the shared kernel")

```
shared_kernel/
├── value_objects/
│   ├── money.py             Money (non-negative, <=2dp decimal amount + currency; +, -, comparison)
│   ├── localized_text.py    LocalizedText (uz_latn / uz_cyrl / ru / en, DEC-19; none required)
│   ├── geo_location.py      GeoLocation (WGS-84 lat/long, range-validated)
│   ├── validity_period.py   ValidityPeriod (valid_from / valid_until, until > from when present)
│   ├── locale.py            Locale (the four locale/script codes, StrEnum)
│   └── typed_id.py          TypedId base + UserId, ListingId
├── events/
│   └── envelope.py          EventEnvelope (event id, type, occurred-at, actor, aggregate ref, version)
├── outbox/
│   └── port.py              OutboxPort (Protocol; append-to-outbox capability, no implementation)
└── README.md                this file
```

Import via the flat top-level surface: `from shared_kernel import Money, LocalizedText,
GeoLocation, ValidityPeriod, Locale, TypedId, UserId, ListingId, EventEnvelope, OutboxPort,
CurrencyMismatchError` (re-exported from `shared_kernel/__init__.py`; the `value_objects/
events/outbox` split is an internal organisation detail, not part of the import path).

### Typed identifiers

Per-concept, not a generic parametrised wrapper: Database Architecture & Logical Data Model
Sec 10 ("Identifier Strategy") is explicit -- "Internal ID ... wrapped in the strongly-typed
identifier VOs of the shared kernel (`UserId`, `ListingId`, ...)." They live here, not in the
owning module's `domain/`, because a typed id must be nameable by *every* module holding a
cross-context reference to the aggregate it identifies (e.g. `catalog.Listing.owner_user_id`
needs `UserId` without `catalog` importing `identity.domain`, which the import matrix forbids
outright) -- shared_kernel is the only package every module may import.

`TypedId` is a real wrapper class (a frozen, self-validating Pydantic model), not
`typing.NewType`: a `NewType` is erased at runtime (the identity function), so it cannot satisfy
this task's "validates on construction, raising typed exceptions" or "equality/hashing
behaviour" requirements -- there would be nothing to validate and no runtime type to
distinguish. `UserId(value=x) != ListingId(value=x)` even for the same UUID, both statically and
at runtime (`test_I08` in `apps/backend/tests/shared_kernel/test_typed_id.py`).

Only `UserId` and `ListingId` are defined -- the two the Database Architecture document names by
example. Every other concept (`OrderId`, `CategoryId`, `MediaAssetId`, ...) is added here, one
`TypedId` subclass at a time, by whichever later task's domain/application code first needs to
name an aggregate it doesn't own. Inventing the full ~24-entry roster now, before those
aggregates exist, would itself be the "module-specific type" this task's scope excludes.

### The event envelope

`EventEnvelope` is structurally identical to `contracts/events/`'s catalogue by construction,
not by convention: every one of the 50 events in `contracts/events/` is a direct subclass of
`shared_kernel.EventEnvelope`, so there is exactly one definition, not two kept in sync by hand.
`apps/backend/tests/shared_kernel/test_envelope_contracts_parity.py` proves this field-for-field
(constructing one instance from each "definition" per the checklist, even though they resolve to
the same class hierarchy) and that the field set matches DDD Sec 5.14's list exactly.

### The outbox abstraction

`OutboxPort` is a `Protocol` (marked `@runtime_checkable` for `isinstance` conformance checks) --
one method, `async def append(self, event: EventEnvelope) -> None`. It says what it means to
stage an event for dispatch as part of the caller's current transaction (DEC-09: never
dual-write; Physical DB Sec 2.13's `outbox_event` table is the eventual concrete shape). No
persistence, no transaction plumbing, no concrete adapter -- that is a module's own
`infrastructure/` layer, built in the persistence-backbone task.

## What's deliberately NOT here

**The Problem error envelope.** An earlier draft of this task's own instructions asked for a
`Problem`/`ValidationError` type here "consistent with `contracts/errors/`" -- but DDD Sec 5.14's
list is explicit and exhaustive ("contains only: strongly-typed identifiers; Money;
LocalizedText; GeoLocation; ValidityPeriod; Locale/Script; the domain-event envelope; and the
outbox abstraction") and does not mention an error envelope anywhere. Adding one here would
itself violate this same task's "no extra type" checklist item. Resolved (2026, this task) by
leaving `contracts/errors/problem.py` as the sole definition and not duplicating it into
`shared_kernel` -- if a future task decides domain/application code genuinely needs a
kernel-level Problem type independent of the `contracts` package, that is a Domain Model
amendment (an ADR adding it to Sec 5.14's list), not a routine addition here.

**PII.** Per Security Architecture Sec 12/10: typed ids wrap only an opaque UUID and "never
carry business meaning" -- never a phone number, email, or other raw PII value. `LocalizedText`
is for public display text (category names, listing titles); phone/email fields elsewhere in the
codebase are plain `str`, never `LocalizedText`. Nothing in `shared_kernel` logs anything (it
has no I/O at all), so the "never log secrets/OTP/tokens/full PII" rule doesn't apply to this
package directly, but its VOs must never become a vehicle for smuggling PII into a log line
either (e.g. never put a raw phone number in a `payload` dict and call it done -- that's still a
logging-boundary concern for whoever writes the log).

## Allowed static dependencies

MAY statically import: nothing (no other module, per SAD Sec 8.1) -- enforced by
`tools/importlinter.cfg`'s `shared-kernel-is-a-true-leaf` contract.

MUST NOT import: any of the 13 bounded-context modules.

## Layout

`shared_kernel` does not follow the four-layer module shape (`interfaces/application/domain/
infrastructure`) -- it is pure, framework-free shared types, not a bounded context with its own
lifecycle.
