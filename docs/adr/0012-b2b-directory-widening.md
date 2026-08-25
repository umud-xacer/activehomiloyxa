# ADR-0012: B2B Directory professional upgrade — sector taxonomy widening, registration-approval gate

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never ratify";
requires human architect approval before the affected approved documents are re-versioned
through change control).

**Date**: 2026-08-25

**Author**: Claude Sonnet 5, at the explicit direction of the repository owner ("Tashkilotlar"
B2B directory professional-upgrade request: public company landing pages, a registration
moderation flow, B2B subscription tariffs, and admin-editable sector icons).

## Context

A codebase survey (this session, three parallel agents covering the backend `profiles` domain,
the frontend organizations UI, and billing/configuration patterns) found the platform already had
a complete public landing page (`/companies/$slug`), a mandatory onboarding wizard, and a
generic term-agnostic subscription-purchase flow (`/subscriptions`). Two genuine gaps remained,
both requiring a widening of a documented closed vocabulary this project's own ADR governance
process covers (see `docs/adr/0011-mark-as-sold-listing-lifecycle-state.md`, the immediate
precedent):

1. **`profiles.domain.value_objects.MainCategory`** was a fixed 6-value `StrEnum` (Finance/
   Mortgage, Construction Contractors, Manufacturers/Materials, Architecture/Interior, Repair
   Services, Real Estate Agencies) with a matching 27-value `SubCategory` set, both backed by a
   `CHECK` constraint on `profiles.business_profile`. The repository owner asked for the B2B
   directory's sector list to cover 10 sectors, explicitly naming the four missing ones:
   Transport & Logistics, Legal/Consulting/Accounting, Home Appliances & Equipment, and
   Hospitality Services.
2. **`profiles.domain.value_objects.ProfileStatus`** was `CREATED → ACTIVE → ARCHIVED`, with
   `application.ProfileUseCases.create_profile` composing `.create()` + `.activate()` in the same
   request — a new company went public the instant it was created, with no admin sign-off step of
   any kind. The repository owner explicitly asked for new registrations to default to a
   `PENDING_REVIEW` state, invisible on the public directory/landing page, until a reviewer
   approves or rejects them via a new `/admin/organizations` panel tab.

Both are the same category of change ADR-0011 already established a precedent for in this
project: a real, already-shipped-or-shipping feature that needs a documented closed vocabulary
widened, with the widening done through the project's ADR + safe-migration + DTO/OpenAPI Literal
+ event-catalogue-registration ritual rather than silently.

While registering this ADR's two new domain events, a **second, unrelated pre-existing gap** was
found and fixed in the same pass: `TrialSubscriptionStarted`/`TrialSubscriptionEnded`
(`contracts/events/profiles.py`, added by ADR-0010) had themselves never been registered in
`contracts/events/__init__.py`'s `EVENT_CATALOGUE`, `configuration/domain/whitelist.py`'s
`EVENT_KEYS`, or `contracts/tests/test_event_catalogue.py`'s oracle set — the identical class of
gap this session already found once for `catalog`'s `ListingSold` (ADR-0011). All four events
(the two ADR-0010 events plus this ADR's own two new ones) are registered together in this same
change.

## Decision

1. **Widen `MainCategory` 6 → 10** with `TRANSPORT_LOGISTICS`, `LEGAL_CONSULTING_ACCOUNTING`,
   `HOME_APPLIANCES_EQUIPMENT`, `HOSPITALITY_SERVICES`, and widen `SubCategory` with 5 new
   sub-categories under each (20 total, all globally-unique member names since `SubCategory` is
   one flat enum): Transport & Logistics → `FREIGHT_TRANSPORT`/`COURIER_DELIVERY`/`CAR_RENTAL`/
   `LOGISTICS_WAREHOUSING`/`MOVING_SERVICES`; Legal/Consulting/Accounting → `LAW_FIRM`/
   `ACCOUNTING_FIRM`/`BUSINESS_CONSULTING`/`TAX_ADVISORY`/`NOTARY_SERVICES`; Home Appliances &
   Equipment → `HOME_APPLIANCE_STORE`/`ELECTRONICS_RETAILER`/`APPLIANCE_SERVICE_CENTER`
   (deliberately distinct from the existing `REPAIR_SERVICES` sector's `APPLIANCE_REPAIR_SERVICE`
   — different sector, different concept: a retail/service center vs. a household-repair
   house-call)/`EQUIPMENT_RENTAL`/`HVAC_EQUIPMENT_SUPPLIER`; Hospitality Services →
   `HOTEL_OPERATOR`/`GUESTHOUSE_OPERATOR`/`EVENT_VENUE`/`CATERING_SERVICE`/`TRAVEL_AGENCY`. A
   single migration (`f6b7c8d9e0a1`) widens both `ck_business_profile_main_category` and
   `ck_business_profile_sub_category` — safe (every existing value still satisfies the new,
   larger `IN (...)` list), following `d4e1a9c2f6b7`'s own drop-and-recreate-under-the-same-name
   pattern (Postgres cannot `ALTER` a `CHECK` constraint in place).
2. **Widen `ProfileStatus`** `CREATED → ACTIVE → ARCHIVED` to `CREATED → PENDING_REVIEW → ACTIVE
   → ARCHIVED`, with `PENDING_REVIEW → REJECTED` and `REJECTED → PENDING_REVIEW` (the latter
   folded into the existing `update_details` edit call — editing a rejected profile resubmits it,
   no separate endpoint). `create_profile` now composes `.create()` + `.submit_for_review()`
   instead of `.create()` + `.activate()`. The same migration widens
   `ck_business_profile_status` to the five-value set.
3. **New domain events** `BusinessProfileApproved`/`BusinessProfileRejected`
   (`contracts/events/profiles.py`), published by the new `ProfileUseCases.decide_registration`
   use case (`profiles:profile:manage`-gated, same permission `adminArchiveBusinessProfile`
   already uses — no new permission key). Registered in `EVENT_CATALOGUE`/`EVENT_KEYS`/the
   `test_event_catalogue.py` oracle alongside the two ADR-0010 events this same pass found
   unregistered (count 57 → 61).
4. **Visibility gate**: `ProfileUseCases.get_public_profile_by_slug` and `list_public_profiles`
   now additionally require `status == ProfileStatus.ACTIVE` (previously only the subscription
   check). `catalog`'s existing subscription-lapse suspend/reactivate mechanism
   (`suspend_all_by_owner_profile`/`reactivate_all_by_owner_profile`,
   `infrastructure.event_projection.handle_subscription_visibility_event`) is mirrored with a new
   `_PENDING_REVIEW_REASON`-scoped pair reacting to `BusinessProfileApproved`/
   `BusinessProfileRejected`, so a pending/rejected company's own catalog listings stay hidden
   the same way a subscription-lapsed company's do — reusing the exact reason-scoped
   suspend/reactivate discipline already in place, not inventing a new mechanism.

## Alternatives considered

1. **Model the registration-approval gate as a new `VerificationCase`-shaped aggregate**, reusing
   the existing paid trust-badge review workflow's exact shape. Rejected: `VerificationCase` is
   structurally a *paid, optional* badge product (`VERIFICATION_ELIGIBILITY` entitlement-gated,
   I-12's own precondition) — conflating it with a *mandatory, free* registration gate would
   either break I-12's "no case without an active paid entitlement" invariant or require carving
   out a confusing free-tier exception inside a class whose whole identity is "the paid
   verification workflow." A plain `ProfileStatus` widening (the same shape `catalog`'s `SOLD`
   status extension already used this session) is simpler and does not disturb the trust-badge
   system at all.
2. **A 9th `configuration.ConfigEntityType` for B2B sector icons**, reusing the exact category
   maker-checker CRUD catalog categories use. Rejected as disproportionate for this ADR's own
   scope (sector taxonomy + approval gate) — the icon-management mechanism is a separate, later
   piece of this same feature request and is tracked separately, not decided here.
3. **Leave `REJECTED` terminal**, requiring a dedicated resubmission endpoint. Rejected: folding
   resubmission into the owner's existing `update_details` edit call (the natural "fix what the
   reviewer flagged" action) needs no new endpoint and matches how a rejected company would
   naturally interact with the system — edit, then wait for re-review.

## Consequences

- `profiles/domain/value_objects.py`, `profiles/domain/business_profile.py`,
  `profiles/application/profile_use_cases.py`, `profiles/infrastructure/persistence/{models,
  repository}.py`, `profiles/interfaces/{dto,routers}.py`, `contracts/openapi.yaml`, and
  `contracts/events/profiles.py` are all touched in this same change, per this project's own
  precedent for a governed vocabulary widening.
- `contracts/events/__init__.py`, `configuration/domain/whitelist.py`, and
  `contracts/tests/test_event_catalogue.py` gain four entries (not two) — the two new events this
  ADR adds, plus the two ADR-0010 events this pass found were never registered.
- `catalog/application/listing_use_cases.py`'s `reactivate_all_by_owner_profile` gains a `reason`
  parameter (previously hardcoded to the subscription-lapse reason only) so it can be reused for
  the new pending-review suspend/reactivate pair without duplicating its pagination/guard logic.
- A `LEGAL_ENTITY` account cannot create a catalog listing before completing onboarding
  (`requireOnboardedLegalEntity`, ADR-0010) — by the time real listings exist, onboarding (and
  therefore a subscription/trial) already exists too, so the new pending-review catalog gate only
  becomes practically relevant once a company has both onboarded and published listings, exactly
  mirroring when the pre-existing subscription gate becomes relevant.
- This ADR does **not** itself edit any pre-existing approved document (DDD Domain Model,
  Physical Database Design) outside version control here (Playbook §18's governance note). It is
  the durable record of *why* `profiles/`'s vocabulary now differs from whatever those documents
  currently say, pending the human-governance re-versioning step.

## Approved-document references touched

- DDD Domain Model (`profiles.MainCategory`/`SubCategory`/`ProfileStatus` closed vocabularies —
  each gains new members) and its BC-02 event table (gains two new rows).
- `contracts/README.md` ("Gaps resolved by ADR" section — gains a bullet, mirroring ADR-0011's
  own entry there).
