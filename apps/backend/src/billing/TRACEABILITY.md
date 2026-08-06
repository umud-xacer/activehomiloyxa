# billing -- requirement traceability matrix (Task P-09)

Maps each requirement/invariant this module satisfies to its implementing code and the named test
that proves it. Mirrors `catalog/TRACEABILITY.md`'s shape exactly.

## Functional requirements (SRS)

| Requirement | Summary | Code | Test |
|---|---|---|---|
| FR-BILL-001 | Generate an invoice for every purchase order | `OrderUseCases.create_order` (eagerly issues the invoice in the same call, see README "Design notes") | `test_order_use_cases.py::TestCreateOrder`; `test_api.py::TestCreateOrder` |
| FR-BILL-002 | Payment confirmed manually by an operator; entitlement activates only then | `PaymentUseCases.confirm_payment` | `test_payment_use_cases.py::TestConfirmPaymentSanctionedTransaction`; `test_entitlement.py::TestI14ActivationOnlyOnConfirmedPayment` |
| FR-BILL-004 | Payment-provider abstraction exists so v2 can add online providers without changing business logic; v1 has exactly one implementation | `billing.application.ports.PaymentProviderPort`; `OfflineManualPaymentAdapter` | `test_payment_use_cases.py::TestOfflineOnly` (structural: exactly one `*PaymentAdapter` class, source-inspected for no network/SDK call) |
| FR-SUBS-003 | Entitlement (subscription/promotion/verification/banner) activates on confirmed offline payment | `EntitlementFactory.activate_from_paid_order` | `test_entitlement.py::test_I14_confirmed_payment_activates_the_entitlement` |
| FR-SUBS-004 | The system tracks entitlement validity and deactivates entitlements at end of term | `EntitlementUseCases.sweep_expired`; `EntitlementExpiryWorker` | `test_entitlement_use_cases.py::TestSweepExpired`; `integration/test_repository_live.py::test_entitlement_list_expiring_active_finds_only_past_due_active_rows` |

## Domain invariants (DDD Sec 9)

| Invariant | Text | Code | Named test |
|---|---|---|---|
| I-07 | A frozen `ProductSnapshot` binds at order creation; later `ProductDefinition` changes never retroactively alter an existing order | `ProductSnapshot`; `Order.create` (copies the snapshot in, never re-reads `configuration`) | `test_order.py::test_I07_product_snapshot_is_frozen_at_creation`; `test_order_use_cases.py::test_I07_product_snapshot_is_frozen_at_order_creation` |
| I-14 | An Entitlement activates only upon administrator-confirmed payment of its invoice; no online payment path exists in v1 | `EntitlementFactory.activate_from_paid_order` (checks `order.status == "PAID"` first, before anything else; the sole constructor for `Entitlement` anywhere in the codebase) | `test_entitlement.py::test_I14_confirmed_payment_activates_the_entitlement`, `test_I14_no_activation_without_confirmed_payment` (parametrized PENDING/INVOICED/CANCELLED), `test_I14_entitlement_has_exactly_one_constructor` (structural proof); `test_payment_use_cases.py::TestConfirmPaymentSanctionedTransaction`; `test_api.py::test_I14_authorized_operator_confirms_payment_and_activates_entitlement`, `test_I14b_declined_payment_returns_409_and_activates_nothing` |
| I-15 | An expired Entitlement confers no benefit -- withdrawn on `EntitlementExpired` | `EntitlementUseCases.sweep_expired`; `Entitlement.expire` | `test_entitlement.py::test_expire_moves_active_to_expired`; `test_entitlement_use_cases.py::TestSweepExpired` |

## Business rules / decisions

| Rule | Summary | Code | Test |
|---|---|---|---|
| DEC-02 | No payment gateway in v1 -- payment confirmed manually by operator | `OfflineManualPaymentAdapter` | `test_payment_use_cases.py::TestOfflineOnly` |
| BRULE-14 | Offline payment: entitlement activates only on confirmed offline payment | `PaymentUseCases.confirm_payment` -> `EntitlementFactory.activate_from_paid_order` | `test_payment_use_cases.py::TestConfirmPaymentSanctionedTransaction` |
| BRULE-15 | Payment abstraction reserved for v2; no online payment path exists or is reachable in v1 | `billing.application.ports.PaymentProviderPort` (Protocol, one implementation); frozen `interfaces.ports.PaymentProviderPort` stub left untouched | `test_payment_use_cases.py::TestOfflineOnly` |
| DB Architecture Sec 1.3 (2nd sanctioned sync exception) | Invoice->Paid + Order->Paid + Entitlement activation commit in ONE transaction | `PaymentUseCases.confirm_payment`, same `AsyncSession` for all three repository saves + both outbox appends | `integration/test_payment_transaction_live.py::test_forced_failure_rolls_back_invoice_order_entitlement_and_both_outbox_rows`, `test_successful_commit_persists_all_three_aggregates_and_both_events_together` |
| Physical DB Design (invoice numbering) | `invoice_number` unique, sourced from `billing.invoice_number_seq` | `SqlalchemyInvoiceRepository.next_invoice_number` | `integration/test_repository_live.py::test_invoice_numbers_are_sequential` |
| Logical Sec 18 (outbox, no dual-write) | Every billing event published via the transactional outbox, same transaction as its triggering state change | `OutboxWriter.append`, called inside every use case's own session, never a separate commit | `integration/test_payment_transaction_live.py` (both tests); `test_payment_use_cases.py::test_I02_publishes_payment_confirmed_and_entitlement_activated_events` |

## Cross-context event contract

| Concern | Code | Test |
|---|---|---|
| `EntitlementActivated` payload shape serves both known consumers (catalog's `ownerProfileId`/`entitlementId`; search's `listingId`/`kind`) | `payment_use_cases.py::_entitlement_activated_payload` | `test_payment_use_cases.py::test_I03_entitlement_activated_payload_matches_the_frozen_shape_both_consumers_need` |
| Only `EntitlementActivated` (`ACTIVE_SUBSCRIPTION`) is routed to catalog's quota projection -- `Expired`/`Revoked` deliberately excluded (catalog's own P-07 gap, see README "Known gaps" #2) | `composition_root.make_catalog_entitlement_projection_handler`; `_CATALOG_RELEVANT_ENTITLEMENT_EVENT_TYPES`/`_CATALOG_RELEVANT_ENTITLEMENT_TYPES` | `integration/test_downstream_catalog_projection_live.py::test_catalog_subscription_projection_reacts_to_a_real_entitlement_activated_event` |
| Billing has no static dependency on catalog/profiles/ads (AIR-10) | `tools/importlinter.cfg`'s `cross-module-billing`/`billing-catalog-profiles-ads-no-cycle` contracts | `test_boundary_import.py::test_I01_cross_module_billing_contract_currently_passes`, `test_I02_a_deliberate_catalog_import_breaks_the_contract_then_reverts`, `test_I03_billing_catalog_profiles_ads_no_cycle_contract_currently_passes` |

## Admin authorization (`confirmInvoicePayment`)

| Concern | Code | Test |
|---|---|---|
| `billing:invoice:confirm_payment` gates the operation, wired end-to-end (unlike catalog's still-unconsulted `catalog:listing:moderate`) | `composition_root.provide_billing_acting_operator` -> `identity.domain.AuthorizationService.authorize` | `test_api.py::TestConfirmInvoicePayment::test_I12_unauthenticated_caller_gets_401`, `test_I13_unauthorized_operator_gets_403` |
| Scenarios contributed to the shared release-blocking authorization matrix (TEST-02/QG-08) | `tests/authorization_matrix.py::BILLING_MATRIX` | `tests/test_authorization_matrix.py::test_authorization_allow_deny_matrix` (`SCENARIOS = [*IDENTITY_MATRIX, *CATALOG_MATRIX, *BILLING_MATRIX]`) |

## Validation checklist cross-reference (P-09 prompt)

| Checklist item | Evidence |
|---|---|
| Entitlement activation ONLY on confirmed payment, proven both directions | `test_entitlement.py::TestI14ActivationOnlyOnConfirmedPayment` |
| Invoice->Paid + Order->Paid + entitlement activation ATOMIC in one transaction, forced failure leaves no partial state | `integration/test_payment_transaction_live.py::test_forced_failure_rolls_back_invoice_order_entitlement_and_both_outbox_rows` |
| ProductSnapshot frozen at order time | `test_order.py::test_I07_product_snapshot_is_frozen_at_creation`; `test_order_use_cases.py::test_I07_product_snapshot_is_frozen_at_order_creation` |
| Billing has NO static import of catalog/profiles/ads, import-linter enforced | `test_boundary_import.py`; `lint-imports` (`billing-catalog-profiles-ads-no-cycle`, `cross-module-billing` KEPT) |
| PaymentProviderPort exists but exactly ONE v1 implementation, no online provider implemented/stubbed/configured/reachable | `test_payment_use_cases.py::TestOfflineOnly` |
| Entitlement expiry sweep runs, expires, emits correct events | `test_entitlement_use_cases.py::TestSweepExpired`; `infrastructure/worker.py::EntitlementExpiryWorker` |
| Every billing event matches `contracts/events/`, published via outbox atomically, no dual-write | `integration/test_payment_transaction_live.py`; `contracts/events/billing.py` (frozen since P-01, used verbatim) |
| Downstream consumers (catalog quota/promotion projection) demonstrably react to real entitlement events | `integration/test_downstream_catalog_projection_live.py` -- search-side equivalent deferred, see README "Known gaps" #1 (PR #5/P-08 not merged into `main` on this branch) |
| Admin confirm-payment correctly authorised, authorization matrix extended and green | `test_api.py::TestConfirmInvoicePayment`; `tests/test_authorization_matrix.py` |
| Every billing OpenAPI operation implemented, contract conformance green | `test_api.py` (all 8 operations exercised end-to-end via `TestClient` + `main.create_app()`); routes confirmed via `/openapi.json` introspection (this FastAPI version wraps `app.routes` in opaque `_IncludedRouter` objects, so direct route introspection is unreliable) |
| Coverage floors met, mypy --strict/ruff/import-linter clean | See README "Coverage / quality gates": domain 97.96%, application 100%, overall 84.64%; mypy/ruff/bandit clean; 49/49 import-linter contracts kept |
