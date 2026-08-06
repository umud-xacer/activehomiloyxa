# ADR-0007: Add `accountKind` + admin registration review to the frozen OpenAPI contract

**Status**: Proposed (drafted by an AI agent per Playbook §18 — "agents may draft, never
ratify"; requires human architect approval before the affected approved documents are
re-versioned through change control).

**Date**: 2026-08-03

**Author**: Claude Sonnet 5, drafting under an explicit product request from the repository
owner: every new account picks one of three platform-facing roles at signup (individual /
legal-entity-manufacturer / investor), fills a short role-specific questionnaire ("anketa"), and
an admin reviewer must approve that questionnaire before the account's role-specific workspace
unlocks.

## Context

Neither concept exists anywhere in the approved documents or the frozen contract today:

- `identity.domain.value_objects.AccountStatus` is a closed three-value set
  (`ACTIVE`/`SUSPENDED`/`CLOSED`) with no `PENDING` member — `identity/README.md`'s own "Known
  gaps" already flags this exact wall for a *different* feature (`registerEmail`'s own
  description says "pending email confirmation" but nothing enforces it).
- `profiles.domain.value_objects.ProfileType` is a closed, **business-only** eight-value set
  (`CONSTRUCTION_COMPANY`, `MANUFACTURER`, `BUILDER`, `SUPPLIER`, `CONTRACTOR`, `ARCHITECT`,
  `INTERIOR_DESIGNER`, `SERVICE_PROVIDER`). ADR-0002 already deliberately removed an
  `INDIVIDUAL_SELLER`-shaped value from this exact enum, on the grounds that "an individual, not
  a business" does not belong in a business-*profile* vocabulary. `INVESTOR` has the same
  problem: it is not a business-profile type either.
- `profiles.domain.verification_case.VerificationCase` already implements a complete
  request → reviewer-decides → approved/rejected workflow, but it is scoped to a **paid,
  opt-in trust badge** on an already-active `BusinessProfile` (gated by a billing entitlement) —
  not an account-activation gate, and profiles' own accounts have no equivalent for a plain
  individual signup.
- `moderation` is reactive-only (acts only on already-published `ContentReported`/
  `ListingFlagged` events) and is structurally forbidden from importing any other module's
  `interfaces/` package, including identity's — a poor fit for "review a brand-new account before
  it is ever active."

## Decision

Add an **additive-only** set of fields/operations, deliberately not reusing or widening either
`AccountStatus` or `ProfileType`:

- New `identity.domain.value_objects.AccountKind` (`INDIVIDUAL` | `LEGAL_ENTITY` | `INVESTOR`)
  and `RegistrationReviewStatus` (`PENDING` | `APPROVED` | `REJECTED`), both **orthogonal** to
  `AccountStatus` — a `SUSPENDED` account can still be mid-review, an `ACTIVE` account can still
  be `PENDING` review. Login (`AccountStatus.ACTIVE`) is completely unaffected; `review_status`
  only gates the role-specific workspace the frontend routes to after login.
- `UserAccount` gains `account_kind`, `anketa` (freeform JSONB, mirrors
  `BusinessProfile.contacts`'s own "no fixed shape" pattern — the questionnaire's fields differ
  per `account_kind` and are a frontend/product concern, not a domain one), `review_status`,
  `review_decision` (mirrors `profiles.domain.value_objects.Decision` exactly: outcome, reason,
  reviewer id, timestamp).
- `RegisterEmailRequest`/`OtpVerifyRequest` gain optional `accountKind` (default `INDIVIDUAL`)
  and `anketa` fields, populated at signup. `Account` (the `/me` response) gains
  `accountKind`/`reviewStatus`/`reviewReason` so the frontend can route a logged-in user to the
  correct pending/rejected/role-specific screen.
- Two new operations, tagged `Administration`, implemented in `identity`'s own
  `interfaces/routers.py` (NOT a new module) — same tag-routing rule ADR-0006 already
  established, and the same shape as `profiles`'s `listVerificationQueue`/`decideVerification`:
  - **`GET /admin/registration-queue`** (`listRegistrationQueue`) → `RegistrationQueuePage`
    (each item: identity + full `anketa`, oldest-first).
  - **`POST /admin/registration-queue/{accountId}/decision`** (`decideRegistration`) →
    `UserAdminView`, body `RegistrationDecisionRequest {outcome, reason?}`.
  - Gated by a **new** permission key `identity:registration:review` (Absolute Architecture Rule
    9/AIR-19 permits a new key only when no existing one already covers the capability —
    `identity:account:manage_status` covers suspend/reactivate, not "approve a signup," and
    `profiles:verification:review` is a different reviewer capability on a different aggregate;
    neither is a fit).
- Two new events, `RegistrationApproved`/`RegistrationRejected` (`contracts/events/identity.py`),
  mirroring `AccountSuspended`'s existing shape.

## Why the review gate lives in `identity`, not `moderation` or `profiles`

Mirrors ADR-0006's own reasoning for role assignment: the state being guarded
(`UserAccount.review_status`) is a field on identity's own aggregate root, so the transition
belongs inside identity's own domain method (`UserAccount.decide_registration`), guarded by its
own invariant (PENDING is the only state a decision can leave). `moderation`'s reactive-only,
no-cross-module-import architecture cannot reach a not-yet-published account at all; `profiles`
already has its own review workflow for a narrower, billing-gated, post-activation concern and
structurally cannot see `identity.domain` beyond typed ids. Putting a second implementation next
to `profiles.VerificationCase` would duplicate the pattern for no benefit — the two are copies of
the same idea at two different aggregates, exactly as `profiles.VerificationCase` and this
feature's `RegistrationDecision`/`decide_registration` now are.

## Alternatives considered

1. **Add `INDIVIDUAL`/`INVESTOR` to `profiles.ProfileType`.** Rejected: reverses ADR-0002's own
   explicit correction, and `INVESTOR` is not a business-profile type any more than `INDIVIDUAL`
   is — both belong on the account, not on a `BusinessProfile`.
2. **Add `PENDING` to `AccountStatus`.** Rejected: `AccountStatus` already governs *login*
   (`UserAccount.require_active`) across every authentication path; overloading it to also gate
   *workspace access* would mean a reviewer decision blocks login itself, which the product
   requirement does not ask for (the wizard's own 4th step already shows a "pending review"
   screen to a fully logged-in account) and would touch far more call sites for no benefit.
3. **Route review through `moderation`.** Rejected in Context above — architecturally excluded
   by moderation's own reactive-only, no-cross-import design.

## Consequences

- `contracts/openapi.yaml` and `docs/Active-Home-OpenAPI-3.1-Specification-v1.0.yaml` (its source)
  gain: `AccountKind`/`RegistrationReviewStatus` enums, `accountKind`/`anketa` on
  `RegisterEmailRequest`/`OtpVerifyRequest`, `accountKind`/`reviewStatus`/`reviewReason` on
  `Account`, two new schemas (`RegistrationDecisionRequest`, `RegistrationQueueItem` +
  `RegistrationQueuePage`), two new paths.
- `identity/domain/{value_objects,user_account,exceptions}.py`,
  `identity/application/{admin_use_cases,auth_use_cases}.py`,
  `identity/infrastructure/persistence/{models,repository}.py` (new migration
  `a1b2c3d4e5f6`), `identity/interfaces/{dto,di,routers}.py`, `composition_root.py`, `main.py`
  all gain additive changes only — no existing column, field, endpoint, or use-case signature is
  removed or repurposed.
- `configuration/domain/whitelist.py` gains one new permission key
  (`identity:registration:review`); the already-published `super-admin`/`administrator`
  role-definitions were re-versioned (v2) to include it.
- This ADR does **not** itself edit SRS v1.0 or the Domain Model v1.0 (immutable source documents
  outside version control here, per Playbook §18's governance note). This ADR is the durable
  record of why `contracts/` now differs from those documents, pending human ratification.

## Approved-document references touched

- SRS v1.0 (no existing FR covers this — a net-new product requirement, not a correction of an
  existing one; a human architect should assign this an FR id at ratification time).
- DDD Domain Model v1.0 §5.1 (`UserAccount` aggregate — new fields), §5.2 (contrast with
  `ProfileType`, which this ADR deliberately does not widen).
- `identity/README.md`, `profiles/README.md` (cross-reference note), `configuration/domain/
  whitelist.py` (new key + comment).
- Absolute Architecture Rule 9/AIR-19 (new permission key justified above — no existing key
  covers this capability).
