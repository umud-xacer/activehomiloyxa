# ADR-0010: Legal-entity onboarding, 5-day free trial, public landing page visibility gating, and Payme/Click payment gateway integration

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-08-14

**Author**: Claude Sonnet 5, at the explicit direction of the repository owner (business
requirement: LEGAL_ENTITY accounts must complete a mandatory profile before publishing, get a
5-day free trial of public visibility, lose that visibility if they don't convert to a paid
subscription, and be able to pay via Payme/Click).

## Context

`profiles/BC-02`'s event catalogue (`contracts/events/profiles.py`) is explicitly frozen: *"Do
not add an event here that is not a row in DDD Sec 6 for this context; do not remove one either
without an ADR."* No trial/subscription concept of any kind exists anywhere in `profiles` today
— `BusinessProfile` (DDD Sec 5.2) has no onboarding-completion or trial-window fields, and
DDD Sec 6 lists no `TrialSubscriptionStarted`/`TrialSubscriptionEnded` events.

Separately, `billing/application/ports.py`'s `PaymentProviderPort` was deliberately built as an
open seam for exactly this situation — its own docstring: *"FR-BILL-004/BRULE-15: online
providers can be added in v2 without changing business logic."* `OfflineManualPaymentAdapter` is
the only registered implementation today (BRULE-15: "settled offline in v1"); this ADR is the v2
this seam was built for.

Three existing pieces of infrastructure make this addable without redesigning already-approved
modules:
1. `profiles.subscription_entitlement_projection` (added by migration `a4c1f9e7d203`, itself
   already a documented "locally-necessary projection table" precedent under the Monetization
   task) is the single read model every downstream consumer (`get_subscription_status`, the
   dashboard `SubscriptionBanner`, `companies/index.tsx`'s public-directory filter) already reads
   to decide "is this profile currently entitled."
2. `billing → catalog` visibility propagation (`handle_subscription_visibility_event` →
   `ListingUseCases.suspend_all_by_owner_profile`/`reactivate_all_by_owner_profile` → search
   reindex via the existing catalog-outbox consumer) is fully built and already the mechanism a
   paid subscription's activation/expiry drives.
3. `catalog_worker.py` already runs multiple `OutboxDispatcher` loops draining other modules'
   outboxes into catalog's own projections — the documented idiom for "catalog is the consumer,
   so catalog's own worker runs the dispatcher."

## Decision

1. **`BusinessProfile` (DDD Sec 5.2) gains three nullable fields**: `onboarding_completed_at`,
   `trial_starts_at`, `trial_ends_at` (migration, `profiles` schema, purely additive). A new
   `complete_onboarding()` domain transition enforces the mandatory-field precondition (name,
   ≥1 phone, logo, description, address, ≥1 portfolio item) and, on success, starts a 5-day
   trial window. This is a one-time transition per profile (raises if already completed) —
   mirrors `issue_badge`'s "no setter, no alternate path" discipline.
2. **The trial is projected directly into `subscription_entitlement_projection`**, not minted as
   a real `billing.Entitlement` — `EntitlementFactory.activate_from_paid_order` structurally
   requires `order.status is PAID` (I-14), and a free trial has no `Order`/`Invoice` at all.
   Bypassing or relaxing that guard to accommodate a trial would weaken I-14 for every paid
   entitlement too; kept untouched.
3. **DDD Sec 6 (profiles event catalogue) gains two events**: `TrialSubscriptionStarted`,
   `TrialSubscriptionEnded` — same envelope shape as every existing profiles event, emitted by
   `complete_onboarding()` and the new trial-expiry sweep worker respectively. A dedicated
   `catalog.infrastructure.event_projection.handle_trial_subscription_event` (structurally
   identical to `handle_subscription_visibility_event`, sharing its suspend/restore calls and
   lapse-reason constant) consumes them — deliberately a separate event pair and handler rather
   than reusing billing's `EntitlementActivated`/`EntitlementExpired` vocabulary verbatim, since
   profiles emitting an event literally named `EntitlementActivated` for something that
   structurally is not a billing `Entitlement` would misdescribe its own producer (this
   codebase's own precedent: `catalog` already keeps `handle_entitlement_event`/
   `handle_subscription_visibility_event`/`handle_listing_promotion_event` as separate functions
   even where near-identical, one per producer+concern). Wired as a fifth route on the ALREADY
   existing `make_profiles_notification_projection_handler()` fan-out (run by
   `notifications_worker.py`'s `provide_profiles_notification_projection_dispatcher`) rather than
   a new `OutboxDispatcher` — profiles' `outbox_event` table already has exactly one dispatcher
   draining it (`OutboxDispatcher`'s own documented "only one dispatcher can safely claim a given
   row" constraint), so a new consumer of that table is always a new branch on the existing
   fan-out handler, the same pattern this handler's own docstring already uses for its four
   prior routes (notifications, analytics, search, identity).
4. **A new public read path 404s a not-currently-entitled profile**: `GET
   /business-profiles/slug/{slug}` (new operation, new route using `BusinessProfile.slug` —
   already a field, previously unused by any route) raises when `subscriptionStatus` is not
   `ACTIVE`. The existing by-id `getBusinessProfile` stays permissive by design (the owner's own
   dashboard must keep reading it regardless of entitlement state, to show the paywall).
5. **`billing.PaymentProviderPort` gains two v2 implementations**: `PaymeAdapter`, `ClickAdapter`
   (`billing/infrastructure/`), plus two new unauthenticated-but-signature-verified webhook
   routers implementing each provider's own server-to-server protocol (Payme's JSON-RPC
   `CheckPerformTransaction`/`CreateTransaction`/`PerformTransaction`/`CancelTransaction`/
   `CheckTransaction`/`GetStatement`; Click's `Prepare`/`Complete`). A new, non-aggregate
   `ProviderTransactionRow` (billing schema) tracks each provider's own transaction handshake
   state independently of `Invoice`/`Order` — required because Payme's protocol creates a
   provider-side transaction *before* our `Invoice` may ever become `PAID`, and can cancel it
   without our aggregates transitioning at all. `PaymentUseCases.confirm_payment` itself is
   **not modified** — a webhook handler that has already verified the provider's signature and
   walked that provider's own state machine to its "money captured" step calls it exactly the
   way `OfflineManualPaymentAdapter`'s caller does today, satisfying FR-BILL-004's "without
   changing business logic" promise. `OfflineManualPaymentAdapter`/the admin-confirm endpoint
   are kept, unmodified, as a fallback (dev environments, or any product/order type this ADR
   does not route through a gateway).

## Alternatives considered

1. **Model the trial as a real, zero-price `billing.Entitlement`.** Rejected: requires either
   relaxing `EntitlementFactory.activate_from_paid_order`'s `order.status is PAID` guard (I-14,
   load-bearing for every paid entitlement, not just this one) or inventing a parallel
   `Order`/`Invoice` pair with a fabricated PAID state for a transaction that never happened —
   both weaken a frozen invariant to serve a case it was never meant to cover.
2. **Reuse `EntitlementActivated`/`EntitlementExpired` event types verbatim from profiles' own
   outbox for the trial**, to avoid touching the frozen event catalogue at all. Rejected: it
   works mechanically (catalog's handler only branches on `event_type`/payload shape) but
   produces an event named for an aggregate (`Entitlement`) that does not exist for a trial grant
   — a misleading audit trail, and inconsistent with this module's own "one handler per
   producer+concern" precedent.
3. **Route Payme/Click confirmation through a new use-case method instead of
   `PaymentUseCases.confirm_payment`.** Rejected: `confirm_payment`'s three-aggregate
   transaction (Invoice→PAID, Order→PAID, Entitlement activation) is exactly what a successful
   gateway payment must trigger, and `PaymentProviderPort.confirm()` was already shaped to let a
   v2 adapter answer differently from the v1 offline one without any use-case change.

## Consequences

- `profiles/domain/business_profile.py`, `profiles/domain/exceptions.py`,
  `profiles/application/{ports,profile_use_cases,exceptions}.py`,
  `profiles/infrastructure/{persistence/{models,repository},worker,event_projection?}.py`,
  `profiles/interfaces/{routers,dto}.py`, a new `profiles` migration, `contracts/events/
  profiles.py`, `contracts/openapi.yaml` are all touched.
- `catalog/infrastructure/event_projection.py` gains the new handler; `composition_root.py`'s
  existing profiles-outbox fan-out handler (run by `notifications_worker.py`, not
  `catalog_worker.py`) gains the new route; no change to `catalog/domain` or `catalog_worker.py`.
- `billing/infrastructure/{payme_adapter,click_adapter,webhook_routers}.py` (new),
  `billing/infrastructure/persistence/models.py` (new `ProviderTransactionRow`), a new `billing`
  migration, new env vars (`PAYME_*`/`CLICK_*`, placeholders until the repository owner
  registers real merchant accounts — end-to-end payment testing is blocked on that, sandbox/unit
  verification only until then).
- Frontend: `organization/setup.tsx` (new), `companies/$slug.tsx` (renamed from `$profileId.tsx`,
  with new not-entitled-404 handling), `components/auth/SubscriptionGate.tsx` (new),
  `require-auth.ts` gains `requireOnboardedLegalEntity`, `subscriptions.tsx` gains gateway
  checkout buttons alongside the existing admin-confirm flow.
- This ADR does **not** edit DDD Domain Model v1.0, SAD v1.0, or Security Architecture v1.0
  (immutable source documents outside version control here) — it is the durable record of why
  `contracts/`/the codebase now differ from those documents' current "no trial/subscription
  concept" framing, pending human re-versioning of the approved documents.

## Approved-document references touched

- `contracts/events/profiles.py` (DDD Sec 6 event catalogue — two new rows).
- `contracts/openapi.yaml` (`completeOnboarding`, `getBusinessProfileBySlug`, Payme/Click webhook
  operations, `BusinessProfile` DTO's three new fields).
- `billing/application/ports.py`'s `PaymentProviderPort` (FR-BILL-004/BRULE-15) — the seam this
  ADR fills, not a change to the seam itself.
