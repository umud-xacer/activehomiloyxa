# billing -- module charter

STATUS (Task P-09): fully implemented across all four layers -- the `Order`/`Invoice`/
`Entitlement` aggregates, the offline-manual payment confirmation flow (DEC-02/BRULE-14/15), the
sanctioned synchronous three-aggregate transaction (I-14, DB Architecture Sec 1.3's *other*
exception), the entitlement expiry sweep worker, and the eight billing/administration-tagged API
operations. This README is the module's public charter -- read it before working in this module
(Playbook Sec 13). See `TRACEABILITY.md` for the requirement -> code -> test matrix.

## Bounded context

- **Module**: `billing` (BC-08, Supporting domain per DDD/SAD classification)
- **Responsibilities**: Orders, invoices, offline payment confirmation, entitlement activation/
  expiry, the v2 payment-provider abstraction (reserved, deliberately unused in v1).

## Owned aggregates / entities (DDD Sec 5.8)

- **`Order` [P]** (`billing.domain.order.Order`) -- `purchaser_profile_id`, a frozen
  `ProductSnapshot` (I-07: later `ProductDefinition` changes never retroactively alter an existing
  order), a `TargetRef` (PROFILE/LISTING/SLOT_BOOKING, `ck_booking_shape`-shaped), `amount`, the
  five-state lifecycle `Pending -> Invoiced -> Paid -> Fulfilled | Cancelled`. `fulfill()` exists
  for lifecycle completeness but has no API caller in v1 (see "Known gaps").
- **`Invoice` [P]** (`billing.domain.invoice.Invoice`) -- `order_id` (FK, `UNIQUE` -- the 1:1 lives
  here, never a reciprocal `invoice_id` column on `purchase_order`), `invoice_number` (`UNIQUE`,
  from `billing.invoice_number_seq`), a `PaymentConfirmation` value object once paid, lifecycle
  `Issued -> Paid | Void`. `void()` exists for lifecycle completeness but has no API caller in v1.
- **`Entitlement` [P]** (`billing.domain.entitlement.Entitlement`) -- `entitlement_type`
  (`ACTIVE_SUBSCRIPTION`/`LISTING_PROMOTION`/`VERIFICATION_ELIGIBILITY`/`BANNER_SLOT_BOOKING`, the
  closed four-member set), `promotion_kind` (only for `LISTING_PROMOTION`), `valid_from`/
  `valid_until` (`NOT NULL` at the physical layer -- there is no "pending" entitlement
  representation), lifecycle `Active -> Expired | Revoked`. **`EntitlementFactory.
  activate_from_paid_order` is the ONLY constructor anywhere in the codebase** (proven
  structurally, `test_entitlement.py::test_I14_entitlement_has_exactly_one_constructor`) -- this
  is what makes I-14 true structurally, not just by caller discipline. `revoke()` exists for
  lifecycle completeness but has no API caller in v1.

## I-14 and the sanctioned synchronous transaction (DB Architecture Sec 1.3)

I-14: "An Entitlement activates only upon administrator-confirmed payment of its invoice; no
online payment path exists in v1." `PaymentUseCases.confirm_payment` is billing's own instance of
the system's *second* sanctioned synchronous multi-aggregate transaction (catalog/P-07 owns the
first, its own state-transition + outbox write) -- `Invoice.confirm_payment()`, `Order.mark_paid()`,
and `EntitlementFactory.activate_from_paid_order()` all commit together in one `AsyncSession`, or
none of them do. Proven by `integration/test_payment_transaction_live.py`'s forced-failure test (a
raised exception after all three saves + both outbox appends but before commit leaves zero rows in
any of the three tables). This is an explicit, documented exception to "one aggregate per
transaction" -- implemented deliberately and only here, never generalised elsewhere in this module
or copied into another.

## Offline billing (DEC-02, BRULE-14/15)

No payment gateway in v1. `PaymentProviderPort` (`billing.application.ports`) is a real, callable
Protocol reserved for v2 online providers (Click/Payme/Uzum/Freedom Pay/Stripe); its only v1
implementation is `OfflineManualPaymentAdapter`, which returns the operator's own
`confirmed: bool` attestation verbatim with zero I/O and no network/SDK call of any kind
(`test_payment_use_cases.py::TestOfflineOnly`, source-inspection + class-enumeration proof). The
frozen P-01 stub `interfaces.ports.PaymentProviderPort` (an empty marker Protocol) is left
untouched, matching the "P-01 stubs are vestigial scaffolding, never implemented" precedent
established by `interfaces.ports.OrderPort` (also untouched, seven methods, zero implementations)
-- routers call `OrderUseCases`/`PaymentUseCases`/`EntitlementUseCases` directly.

## Public interface (`interfaces/`)

Order/invoice/entitlement DTOs and the frozen P-01 `OrderPort`/`PaymentProviderPort` stubs
(`interfaces/dto.py`, `interfaces/ports.py`, both untouched). The `interfaces/` package is this
module's *only* importable surface (AIR-02). Nothing in `application/`, `domain/`, or
`infrastructure/` may be imported by another module, ever.

## Routers (`interfaces/routers.py`) -- exactly the eight billing/administration-tagged operations

`billing_router` (tags=["Billing"]): `listProducts` (public, `security: []`), `listMyOrders`,
`createOrder`, `getOrder`, `getOrderInvoice`, `listMyEntitlements` -- all self-service, gated only
by `_acting_profile`'s ownership check (`NotOrderPurchaserError`, mirroring catalog's own
`NotListingOwnerError` pattern), never `AuthorizationPort`. `admin_billing_router`
(tags=["Administration"]): `adminListInvoices`, `confirmInvoicePayment` -- mounted alongside
`billing_router` in the same `interfaces/routers.py` module (mirrors `configuration.interfaces.
routers`'s own `admin_config_router` precedent: an admin surface that acts purely on this module's
own aggregates stays in this module, not deferred to a future `admin` module).

## Authentication bridge and the real admin authorization check

SAD Table 3 permits billing to import `identity` directly (unlike catalog/search), but this
module's own source never does -- `interfaces.auth.ActingUser`/`ActingOperator` are declared here,
resolved for real only in `composition_root.py` (mirrors catalog's own discipline of not exercising
every permission its dependency table technically allows). `provide_billing_acting_operator`
(backing `confirmInvoicePayment`) is the one place in this module that runs the REAL Security Sec
4.2 Gate-3 check: `identity.domain.AuthorizationService().authorize(context,
"billing:invoice:confirm_payment")`, raising `PermissionDeniedError`/`WrongActingProfileError` on
failure (already globally mapped to 403). Unlike catalog's own `catalog:listing:moderate`
(declared in `configuration.domain.whitelist.PERMISSION_KEYS` but never actually consulted by any
caller, pending a future moderation module), `billing:invoice:confirm_payment` **is** wired
end-to-end and consulted for real. Scenarios for it are added to the shared harness at
`tests/authorization_matrix.py::BILLING_MATRIX`, concatenated into `tests/
test_authorization_matrix.py::SCENARIOS` alongside identity's and catalog's own contributions
(TEST-02/QG-08) rather than a second, standalone suite.

## Events published (`contracts/events/billing.py`, frozen since Task P-01)

`OrderPlaced`, `InvoiceIssued` (published eagerly inside the same `createOrder` call -- see
"Design notes" below), `PaymentConfirmed`, `EntitlementActivated`, `EntitlementExpired`. Published
via the transactional outbox (`backbone.outbox.OutboxWriter`), same transaction as the state
change that triggers each one -- never dual-write. `EntitlementRevoked` is defined in the event
catalogue and wired in `EntitlementUseCases.revoke`, but that use case has no API caller in v1
(see "Known gaps").

### The `EntitlementActivated` payload serves four entitlement types and two non-discriminating consumers

Neither known consumer (catalog's `handle_entitlement_event`; search's own equivalent, once
merged) discriminates by `entitlementType` internally -- each unconditionally applies whatever
payload it receives. `_entitlement_activated_payload` (`payment_use_cases.py`) therefore builds one
rich, superset payload (`entitlementId`, `orderId`, `entitlementType`, `ownerProfileId`,
`targetId`, `listingId` (nullable), `kind` (nullable), `productDefinitionId`, `quota`, `validFrom`,
`validUntil`) carrying every field either consumer shape needs
(`test_payment_use_cases.py::test_I03_entitlement_activated_payload_matches_the_frozen_shape_both_consumers_need`),
and **routing by entitlement type happens in `composition_root.py`**, not inside billing itself --
`make_catalog_entitlement_projection_handler` only forwards events where
`payload["entitlementType"] == "ACTIVE_SUBSCRIPTION"` to catalog's handler. Misrouting a
`LISTING_PROMOTION` event into catalog's subscription-quota upsert would silently corrupt that
profile's quota snapshot; this filtering is what prevents it.

## Design notes (judgment calls, flagged as such)

- **`createOrder` eagerly issues the order's own invoice in the same call.** FR-BILL-001 requires
  an invoice for every purchase order unconditionally, there is no separate "issue invoice"
  OpenAPI operation, and the 1:1 Order:Invoice relationship makes eager issuance the only design
  that gives `getOrderInvoice` something to return immediately after `createOrder`. The returned
  `Order.status` is therefore `INVOICED`, not `PENDING`, despite that operation's own OpenAPI
  prose description saying "Order placed (Pending)" -- treated as informal, non-normative prose
  (the schema's `status` enum, not a literal runtime assertion).
- **Invoice number format `INV-######`** (`SqlalchemyInvoiceRepository.next_invoice_number`, via
  `nextval('billing.invoice_number_seq')`) -- no format is documented anywhere; the uniqueness
  constraint is (Physical DB Design), the display format is not.
- **ProductType -> EntitlementType/TargetType/PromotionKind mapping**
  (`billing.domain.product_mapping`) -- no document enumerates this literally.
  `SUBSCRIPTION -> ACTIVE_SUBSCRIPTION` (PROFILE), `PREMIUM`/`FEATURED`/`TOP_PLACEMENT ->
  LISTING_PROMOTION` (LISTING, sub-typed by the matching `PromotionKind`), `VERIFICATION ->
  VERIFICATION_ELIGIBILITY` (PROFILE), `BANNER_PLACEMENT -> BANNER_SLOT_BOOKING` (SLOT_BOOKING) --
  inferred as the unique mapping consistent with the four-member `EntitlementType` set, the
  six-member `ProductType` set, and each product's own `TargetType` requirement.
- **Entitlement validity window**: for `BANNER_PLACEMENT`, taken directly from the order's own
  `TargetRef.booking_window`. For every other product type, `valid_from = now` (the payment
  confirmation instant), `valid_until = valid_from + term_days`; `MissingTermError` if
  `term_days` is `None` for a non-slot product (fails closed, DEC-21).

## The entitlement expiry sweep worker (`infrastructure/worker.py`, `apps/backend/src/billing_worker.py`)

No inbound API surface -- `EntitlementExpiryWorker.run_once()`/`run_forever(stop_event)` polls
`EntitlementRepository.list_expiring_active`, mirrors `CatalogExpiryWorker`'s exact shape (fresh
`AsyncSession` per batch). `EntitlementUseCases.sweep_expired` transitions each lapsed
`Entitlement` to `Expired` and appends `EntitlementExpired` in the same session -- one aggregate
per iteration (DEC-09), not the three-aggregate sanctioned exception (that is `confirm_payment`'s
own, scoped there only).

## Dependencies (SAD Sec 8.1 -- authoritative, enforced by `tools/importlinter.cfg`)

MAY statically import: `shared_kernel`, `configuration`, `identity` -- confirmed unchanged from the
P-01 stub, and only their `interfaces/` packages. In practice this module's own source never
imports `identity` at all (see "Authentication bridge" above).

MUST NOT import: `catalog`, `profiles`, `ads` internals -- and no static dependency on any of the
three at all (`billing-catalog-profiles-ads-no-cycle`, AIR-10 named cycle: billing<->catalog/
profiles/ads is events-only, X-03), `search`, `media`, `messaging`, `notifications`, `moderation`,
`admin`, `analytics` internals.

## Configuration consumed (DEC-21: never hardcode a configurable value)

Every `ProductDefinition` (price, term, quota) is read live from `configuration` via
`ConfigurationProductDefinitionAdapter` (reuses the same narrow `_ConfigurationReader` bridge
pattern `search`'s own configuration adapter established), never hardcoded. The
`billing:invoice:confirm_payment` permission key (`configuration.domain.whitelist.
PERMISSION_KEYS`, this task's own extension) gates `confirmInvoicePayment` and, unlike catalog's
still-unconsulted `catalog:listing:moderate`, is wired end-to-end in this task.

## Migrations

`infrastructure/migrations/versions/2ed0cdddb299_..._schema.py` creates `billing.
invoice_number_seq`, `billing.purchase_order` (`ck_booking_shape`: `target_type='SLOT_BOOKING' =
booking_window IS NOT NULL`), `billing.invoice` (`ck_paid_shape`: `status='PAID' =
payment_confirmed_by IS NOT NULL AND payment_confirmed_at IS NOT NULL`), `billing.entitlement`
(`ck_promo_shape`, `valid_until > valid_from`), `billing.outbox_event`, `billing.processed_event`,
plus partial indexes on `purchase_order.status`, `entitlement.(activation_state, valid_until)`
(the sweep's own query shape), and `entitlement.target_id`. Hand-written, not `alembic revision
--autogenerate`. Corrections to a `PAID` invoice happen by `VOID` + a new invoice, never by
editing a paid row (append-only financial record discipline) -- `void()` exists on `Invoice` for
this but has no API caller in v1.

## Known gaps (flagged, not silently worked around)

1. **Search-side downstream verification deferred pending PR #5 merge.** This billing-p09
   worktree branched from `main` *before* Task P-08 (search, PR #5) merged --
   `apps/backend/src/search/` here is still the frozen P-01 stub (no domain/application/
   infrastructure code at all), so there is no `search.infrastructure.event_projection.
   handle_entitlement_activated` to wire against or call in an integration test. Billing's own
   `EntitlementActivated` payload already carries every field that consumer needs (`listingId`/
   `kind`/`entitlementId`/`validUntil`), verified directly against P-08's own source in
   `test_payment_use_cases.py::test_I03_*`, but the live-consumer wiring/verification for search
   must wait until PR #5 is merged into `main`.
2. **Catalog's `handle_entitlement_event` has no "withdraw quota" capability.** It unconditionally
   upserts a fresh `SubscriptionSnapshot` from whatever `EntitlementActivated` payload it
   receives, regardless of event type, and has no code path that clears one --
   `QuotaEnforcementService.check_can_create` is also not expiry-aware (no `valid_until` check
   against the snapshot it reads). Routing `EntitlementExpired`/`EntitlementRevoked` events to
   catalog's consumer would therefore either be a no-op or, worse, silently *reapply* stale quota
   data -- the opposite of "withdrawal". `composition_root.
   _CATALOG_RELEVANT_ENTITLEMENT_EVENT_TYPES = {"EntitlementActivated"}` deliberately excludes
   them. This is catalog's own pre-existing (P-07) limitation, not this task's to fix (AIR-01).
3. **`Order.fulfill`, `Invoice.void`, `Entitlement.revoke` are unwired lifecycle capabilities.**
   All three are implemented and domain-tested (guarded, typed-exception-on-illegal-transition)
   because the Domain Model documents their state machines, but no OpenAPI operation in v1 calls
   any of them -- there is no "mark fulfilled", "void an invoice", or "revoke an entitlement" admin
   endpoint in `contracts/openapi.yaml`'s billing-tagged operations.
4. **Invoice number format and the ProductType->EntitlementType mapping are undocumented judgment
   calls**, not literally specified anywhere in the source documents -- see "Design notes" above
   for the reasoning behind each.
5. **Pre-existing, unrelated**: `tools/check_migration_safety.py` flags a false positive on this
   migration file's own docstring (prose containing the words "DROP TABLE/COLUMN" trips its naive
   keyword scanner) -- the exact same standardised docstring template every already-merged
   module's first migration uses verbatim (`identity`/`media`/`catalog`/`search`), not introduced
   or unique to this task.

## Coverage / quality gates (Task P-09 run)

101 tests (`apps/backend/tests/billing/`: 90 fast unit/API + 11 Postgres-gated integration, plus 3
new rows in `tests/authorization_matrix.py::BILLING_MATRIX`), mypy --strict clean, ruff clean,
bandit SAST clean, all 49 `tools/importlinter.cfg` contracts kept (including every billing-specific
one: `layers-billing`, `no-infra-inbound-billing`, `cross-module-billing`,
`billing-catalog-profiles-ads-no-cycle`), domain coverage 97.96% (two defensively-unreachable branches in
`billing.domain.entitlement`: `EntitlementFactory`'s own `UnsupportedProductTypeError` guard --
`ENTITLEMENT_TYPE_BY_PRODUCT` already covers every member of the closed `ProductType` set, so the
`None` branch can never fire from a valid `Order` -- and `_validity_window`'s own
`BANNER_PLACEMENT` booking-window re-check, which `Order.create`'s `TargetTypeMismatchError` guard
and `TargetRef`'s own construction invariant already jointly guarantee can never be `None`. Both
are checked rather than trusted per QG-07/Security Architecture I-5's "no bare assert gating
production control flow" -- fail-closed guards kept even though unreachable through the public
API), application coverage 100%, overall module coverage 84.64%. The Postgres-only integration tests (`integration/`) are present and structurally correct
but unexecutable in this sandbox (no `POSTGRES_HOST`), the same class of gap already documented
for every prior task's own integration suites.

## Layout

```
billing/
|-- interfaces/       # PUBLIC surface: routers, published ports (frozen P-01 stubs), DTOs, auth, di, errors
|-- application/      # use cases (order/payment/entitlement) + ports
|-- domain/           # aggregates (Order/Invoice/Entitlement), value objects, product mapping, invariants
|-- infrastructure/   # adapters: persistence, configuration adapter, offline payment adapter, outbox, worker
|-- README.md         # this file
`-- TRACEABILITY.md    # requirement -> code -> test matrix
```

Dependencies point inward only (`interfaces -> application -> domain`); `infrastructure/`
implements the ports `application/` declares and is never imported by `interfaces/`,
`application/`, or `domain/` (enforced by `tools/importlinter.cfg`).
