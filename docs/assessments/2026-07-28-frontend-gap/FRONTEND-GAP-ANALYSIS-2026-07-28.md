# Frontend Gap Analysis — Documentation vs. Implementation

**Pass:** P-FEGAP (frontend-only, documentation-driven audit)
**Date:** 2026-07-28
**Commit assessed:** `d66562e`
**Scope:** `apps/frontend/` only. Backend assessed only where it is the *cause* of a frontend gap.
**Method:** static audit — every one of the 17 approved `.docx` baseline documents was extracted to
text and read; the three frontend documents were read in full and treated as the yardstick. Findings
were derived from source reading plus scripted counting, then the highest-severity claims were
re-verified by hand against primary sources (the frozen `contracts/openapi.yaml` and the code).
The quality gates were executed. No code was modified.

**Nothing in this report was accepted on assertion.** Where a claim is not directly verifiable by
static reading (runtime behaviour, visual rendering, real backend responses), it is labelled
*Unverified* rather than asserted.

---

## Yardstick

The binding documents for this audit, in precedence order:

1. `docs/frontend_docs/Active-Home-Frontend-UI-UX-Functional-Specification-v1.0.docx` — screen-by-screen blueprint (§1–§21)
2. `docs/frontend_docs/Active-Home-Frontend-Architecture-and-Engineering-Handbook-v1.0.docx` — FE-\*/FAIR-\* rules (§1–§22)
3. `docs/frontend_docs/Active-Home-Frontend-Component-Library-and-Design-System-v1.0.docx` — DS-\* rules (§1–§15)
4. `contracts/openapi.yaml` — frozen API contract (86 paths, 110 operationIds)
5. `docs/adr/0001…0006` — the six approved amendments

Citations below use the document's own section numbers (e.g. *UI/UX §5.2*, *Handbook §11*, *DS §2.7*)
and rule ids (e.g. *FAIR-01*, *FE-ROUTE-02*, *DS-TOKEN-02*).

---

## Executive Summary

The Active Home frontend is a **genuinely well-engineered but materially incomplete** application.
It is not a prototype and it is not scaffolding: 273 TypeScript files, 24k lines, all ten quality
signals green (typecheck clean, lint clean, 131/131 unit tests pass). The code that exists is
disciplined — module boundaries hold, the generated OpenAPI client is used almost everywhere, server-
side route guards are real, and the dynamic form engine is a faithful implementation of the hardest
requirement in the specification.

The gap is not *quality*. The gap is **coverage, cross-cutting rigour, and three unbuildable
promises**.

Three findings dominate everything else:

**1. Two of the specification's central architectural promises cannot be built against the frozen
contract.** The Handbook's configuration-driven rendering model (§11) and its permission-key gating
model (FE-ROUTE-02/FE-CFG-01) both depend on backend surfaces that do not exist in
`contracts/openapi.yaml`. This is not a frontend defect — it is a specification-vs-contract
inconsistency that requires an ADR. The frontend has, correctly and repeatedly, *escalated in
comments rather than inventing endpoints* (FAIR-03/FAIR-16 compliance). Credit is due for that; it is
also why several "missing screens" below are the right call rather than an omission.

**2. The cross-cutting mandates are the weakest area, and they are mandates, not preferences.**
`ErrorState` appears on 1 of 31 pages. Skeletons appear on 1. There are 2 component tests for 60
components. There is no Storybook at all — a documented MUST with a CI gate (DS-DOC-01). The design
token system that DS §2 specifies in detail is roughly one-third present: no z-index scale, no motion
tokens, no elevation, no typography roles, no spacing scale, no status colours beyond one. The
mandated shared error mapper exists and is **dead code** — nine modules hand-roll their own instead.

**3. Two silent correctness defects sit on the most important flows.** Every field in the dynamic
form engine — the flagship listing wizard — has an **unassociated label and unlinked error message**,
because `FormControl` injects `id`/`aria-describedby` through a Radix `Slot` into a function component
that ignores them. And **no side-effecting POST in the entire application sends an `Idempotency-Key`**,
despite 18 contract operations declaring it, making double-submit duplication possible on listing
creation, order creation, messaging, and payment confirmation.

Beyond those: business-profile creation is entirely unimplemented (blocking the B2B half of a B2C+B2B
marketplace), listing images cannot be changed after creation, verification decisions are made without
the operator ever seeing the submitted documents, and the whole Yandex Maps surface — location picker,
radius search, map view, detail map — does not exist.

### Scores

All scores are **higher-is-better** and are defined explicitly to avoid ambiguity.

| Metric | Score | Basis |
|---|---|---|
| Overall implementation completeness | **68%** | Weighted across screens, flows, and cross-cutting mandates |
| Frontend feature completion | **72%** | ~33.5 of 50 specified screens fully or substantially working |
| Documentation compliance | **56%** | Of 168 discrete, checkable doc requirements: 61 ✅, 55 🟡, 42 🔴, 10 ⚠️ |
| Production readiness | **4 / 10** | 8 Critical + 22 High open; a11y and idempotency defects are release-blocking |
| Technical debt health | **6 / 10** | Low *accidental* debt (clean, documented, no god-files); high *structural* debt (missing DS foundation, dead abstractions, near-zero component tests) |
| UX | **6 / 10** | Core journeys work and are thoughtfully built; no maps, no upload progress/cancel, weak error/loading states, several dead-end flows |
| Architecture compliance | **7 / 10** | Module boundaries, contract-first typing, server guards and escalation discipline are genuinely strong; token/component/state layering is not |
| Maintainability | **7 / 10** | Exceptional inline documentation and reasoning; undermined by absent component tests and duplicated primitives |
| Scalability | **5 / 10** | Zero virtualization, zero code-splitting, no memoization on list items, all lists capped or unbounded |

### What is genuinely good (stated so the report is not read as uniformly negative)

- **The dynamic form engine** (`src/shared/forms/`) faithfully implements UI/UX §12 — all 8 whitelisted
  field types via a registry, options from definition, reactive conditional visibility, hidden-field
  pruning, schema compiled from whitelisted validators, `onBlur` validation mode. No per-category code
  exists anywhere. This is the hardest requirement in the specification and it was met.
- **Escalation discipline.** Roughly a dozen gaps are accompanied by comments that correctly identify a
  contract limitation and explicitly decline to invent an endpoint (FAIR-03/16). `site-footer.tsx:13-27`,
  `dashboard-nav.tsx:20-31`, `admin-nav.tsx:18-32`, `messaging/types/messaging.ts:13-33`,
  `admin/reports/page.tsx:26-35` are all model examples.
- **Server-side route guards are real** — `(app)/layout.tsx:20-23` and `(admin)/layout.tsx:22-28` are
  async Server Components that `redirect()` before children render. No client-side access decisions,
  no auth flash. FE-ROUTE-01 is met.
- **Session model is exactly right.** Opaque `HttpOnly` cookie, forwarded server-side, never read or
  decoded, zero JWT/refresh logic. FAIR-12/FE-AUTH-01 fully met.
- **Localization is high quality, not placeholder.** 801 keys, key sets identical across all four
  locales, only 1.1–1.7% of values byte-identical to English (all legitimately so: brand name, locale
  self-labels, `SMS`/`JSON`). Translations are fluent and ICU placeholders are handled correctly.
- **Optimistic concurrency handling is careful and correct** — `lockVersion` echoed, 409 distinguished
  from `QUOTA_EXCEEDED` on the same status code, reload-not-retry semantics documented.
- **Image delivery on the highest-traffic surface is correct** — `next/image` with `fill`, `sizes`,
  `priority`, CDN `THUMBNAIL` variant, and CLEAN-only enforced twice (`resolve-media.ts:41`).

---

## The Three Contract Gaps (root causes, not frontend defects)

These are the highest-value findings in the audit. Each blocks a documented MUST and each requires an
ADR against `contracts/openapi.yaml` — none can be fixed inside `apps/frontend`.

### CG-1 — No public configuration-snapshot endpoint

**Verified:** all 86 contract paths enumerated; every configuration path is under `/admin/config/*`
(10 paths, operator-authenticated authoring). There is no public read projection of PlatformSettings.

Handbook §11's central table requires `useNavigation()`, `useFeatureFlag(key)`, `useTheme()`,
`useStaticPage(key)` — all sourced from "PlatformSettings snapshot". None of those sources exist.
Downstream consequences, all correctly escalated in code rather than faked:

| Doc requirement | Status | Because |
|---|---|---|
| UI/UX §2.9/§2.10 `/p/[pageKey]` static pages (about, contact, terms, privacy, verification-info) | 🔴 route absent | No endpoint serves page content |
| FE-LAYOUT-01 — "layouts contain no hardcoded menu items" | ⚠️ violated | `dashboard-nav.tsx:33-42`, `admin-nav.tsx:33-42` are literal arrays |
| FE-DS-01 — brand/logo from config, "re-branding = config change, no deploy" | 🔴 | Brand is static OKLCH in `globals.css:56-108`; app name hardcoded in message catalogues |
| `useFeatureFlag` — incl. UI/UX §2.1 "banner slot (if ads flag on)" | 🔴 | No flag source |
| UI/UX §5.2 Platform Settings / SEO / Feature Flags / Static Pages editors | 🔴 | Authoring exists only as raw JSON; no read side to validate against |

**Recommendation:** ADR adding a public `GET /platform-settings` (or `/config/snapshot`) returning the
resolved, versioned public snapshot the Handbook §11 already assumes the backend distributes.

### CG-2 — `Account` exposes role codes, not permission keys

**Verified** against the contract schema: `Account` has `roles: array[string]` ("Role codes assigned to
the account") and `additionalProperties: false`. There is no permission-key array.

Handbook §11 requires "the acting identity's **effective permission keys**" for `usePermissions()`;
FE-ROUTE-02 requires admin features "gated by permission key reflected from the backend, never by
hardcoded role checks"; UI/UX §1.4–§1.6 require operator sidebars where "items [are] shown per
permission key" and "a moderator never sees billing/config items because they lack the keys".

The frontend cannot evaluate a permission key it is never sent. It resolved this the *correct* way —
it hardcodes no role→capability map (verified: zero literal role comparisons anywhere in `src/`), shows
all operator nav items to any role-holder, and defers to backend `PERMISSION_DENIED`. But the result is
that **all 8 admin sub-pages share one coarse "has ≥1 role" gate** (`(admin)/layout.tsx:26-28`), and the
permission-key half of FE-ROUTE-02 is not expressed anywhere in the frontend.

**Recommendation:** ADR adding `permissions: string[]` (flattened effective keys) to `Account`.

### CG-3 — No CSRF mechanism exists in the contract

**Verified:** zero occurrences of "csrf" in `src/` **and** zero in `contracts/openapi.yaml`; the only
security scheme is `sessionCookie`.

Handbook §9 states "Cookie-authenticated state-changing requests send the CSRF token per the backend's
scheme (Security §9)". No such scheme is in the contract, so there is nothing for the frontend to send.
Current mitigation is real but is a browser-enforced fallback, not an application-level defence:
`next.config.ts:32-41` proxies `/api/v1/*` same-origin, and `ah_session` is `Secure`+`SameSite=Lax`.

**Recommendation:** contract owner to either specify the CSRF header/scheme or record an ADR accepting
`SameSite=Lax` + same-origin proxying as the v1 control.

Two smaller contract gaps, noted for completeness: **no moderation `claim` operation** exists (blocking
UI/UX §7's "Open → In Review (claim)" workflow), and **`business-type` / `permission-group` are not
`ConfigEntityTypePath` members** (the enum has 8 entries), blocking two of UI/UX §5.2's required editors.

---

## Findings Register

**Format note.** The audit brief asks for 14 fields per finding. Critical and High findings below carry
the full 14. Medium and Low findings are given as dense tables (ID, title, category, description +
expected/actual, doc ref, file, fix, effort) — at 72 findings, full prose for every Low would bury the
signal without adding information. Effort is in ideal engineer-days.

### CRITICAL (8)

---

**FE-001 — Every dynamic form field has an unassociated label and unlinked error message**

- **Severity:** Critical · **Category:** Accessibility / Correctness
- **Description:** `FormControl` (`src/shared/ui/form.tsx:103-118`) uses Radix `Slot` to inject `id`,
  `aria-describedby`, and `aria-invalid` onto its child. In `dynamic-form.tsx:150-156` that child is
  `<Control>` — a *function component* (`TextControl`, `SelectControl`, …) that destructures only
  `{definition, field, describedBy, invalid}` and never spreads or reads the injected props. `Slot`
  clones the element and passes them; the component silently discards them.
- **Expected:** DS §6 / UI/UX §12 / FE-A11Y-01 — every field labelled via `FormField`, errors linked by
  `aria-describedby`, `aria-invalid` set, first error focused and announced (WCAG 2.2 AA).
- **Actual:** The rendered `<Input>` has **no `id`**, so `<FormLabel htmlFor={formItemId}>` points at a
  non-existent element — the label is not programmatically associated. `aria-describedby` is `undefined`
  (`dynamic-form.tsx` never passes `describedBy`), so `FormMessage` and `FormDescription` are never
  linked. `aria-invalid` alone survives, because it is passed explicitly.
- **Doc reference:** Handbook §17 (FE-A11Y-01), DS §5.2 + §8, UI/UX §12 "Errors show inline,
  field-associated, localized"
- **Files:** `src/shared/ui/form.tsx:103-118`, `src/shared/forms/dynamic-form.tsx:150-156`,
  `src/shared/forms/field-registry.tsx:34-204`
- **Root cause:** Radix `Slot` prop-merging only reaches DOM elements or components that forward
  unknown props; the registry's controls do neither.
- **Fix:** Have each control accept and spread the injected props (`...rest` onto the underlying DOM
  input), or pass `describedBy`/`id` explicitly from `dynamic-form.tsx`. Add a jest-axe test per field
  type.
- **Effort:** 1.5 d · **Dependencies:** none · **Screens:** Listing wizard step 2, listing edit, every
  category-driven form — i.e. the entire core authoring path.

---

**FE-002 — No side-effecting request sends `Idempotency-Key`**

- **Severity:** Critical · **Category:** API integration / Data integrity
- **Description:** Zero occurrences of `Idempotency-Key`/`idempotencyKey` in `src/` (verified by grep).
  18 contract operations declare the parameter; 8 of them are called by the frontend.
- **Expected:** Contract + Handbook §9 — "the client generates one for create/order/upload calls per
  API §6.7"; CLAUDE.md: "Side-effecting POSTs accept an `Idempotency-Key` header."
- **Actual:** Header never sent on `verifyOtp`, `registerEmail`, `requestVerification`, `createListing`,
  `initMediaUpload`, `startConversation`, `sendMessage`, `createOrder`, `confirmInvoicePayment`.
- **Doc reference:** Handbook §9 (Retry policy), CLAUDE.md API contract section
- **Files:** `src/modules/identity/api/auth.ts:46,85`; `src/modules/profiles/api/verification.ts:44-49`;
  `src/modules/catalog/api/mutate-listing.ts:87`; `src/modules/media/api/upload.ts:50`;
  `src/modules/messaging/api/actions.ts:32,47-50`; `src/modules/billing/api/billing.ts:44`;
  `src/modules/admin/api/ops.ts:48-50`
- **Root cause:** No central mutation wrapper; each module calls `browserApiClient` directly, so there
  was no single place the header would naturally be added.
- **Fix:** Add a `mutate()` helper in `shared/api` that generates a UUID per logical operation and sets
  the header; route all writes through it. Key must be stable across retries of the *same* user intent.
- **Effort:** 2 d · **Dependencies:** pairs naturally with FE-003 · **Screens:** wizard publish, order
  creation, invoice confirmation, chat send, OTP verify, registration, media upload, verification request.

---

**FE-003 — The mandated shared error mapper is dead code; nine modules hand-roll their own**

- **Severity:** Critical · **Category:** Architecture / Error handling
- **Description:** `mapResponseToAppError` and `ApiError` are defined in `src/shared/api/errors.ts` and
  re-exported at `index.ts:2`, but have **zero consumers** anywhere in `src/` (verified).
- **Expected:** FE-ERR-01 (MUST) — "All errors render through the shared error mapper + UI states";
  Handbook §9 — "Every response is normalised through **one** error mapper… The stable `code` drives UX".
- **Actual:** Nine independent `classify(status)` functions exist, and only two of the nine branch on the
  Problem `code` at all — the rest switch on raw HTTP status, which the contract explicitly says is not
  the discriminator. `traceId` is extracted nowhere, so although `ErrorState` accepts a `traceId` prop
  (`error-state.tsx:21,53`), **no caller ever supplies one** — the support-reference affordance the docs
  require is structurally unreachable.
- **Doc reference:** Handbook §9 + §18 (FE-ERR-01), UI/UX §17 (the code→UX mapping table)
- **Files:** `src/shared/api/errors.ts` (unused); classifiers in `identity/api/auth.ts`,
  `identity/api/account.ts`, `catalog/api/mutate-listing.ts`, `billing/api/billing.ts`,
  `messaging/api/actions.ts`, `profiles/api/company.ts`, `configuration/api/admin-config.ts`,
  `admin/api/ops.ts`, `admin/api/moderation.ts`
- **Root cause:** The mapper was written but never adopted; per-module classifiers were easier to add
  incrementally and nothing enforced the rule.
- **Fix:** Adopt the mapper in `shared/api`'s client wrapper so every call returns a typed `AppError`
  carrying `code`/`traceId`/`details`; collapse the nine classifiers into consumers of it.
- **Effort:** 4 d · **Dependencies:** unblocks FE-004, FE-010, FE-017 · **Screens:** all.

---

**FE-004 — Backend 422 field errors are never mapped back onto their fields**

- **Severity:** Critical · **Category:** Business logic / Forms
- **Description:** The wizard receives `details[]` and renders them as a raw bulleted list of
  `path: message` strings in an `Alert`, at both the details step and the publish step.
- **Expected:** UI/UX §12 + §17 + Handbook §18 — "Backend field-level 422 `details[]` map back onto the
  exact fields **by path**"; "first error focused + announced".
- **Actual:** `details[]` is rendered as `{entry.path}: {entry.message}` — a machine path shown verbatim
  to end users (e.g. `attributes.floor_count: ...`). `DynamicForm` exposes no API to set server errors on
  fields, so the mapping cannot happen. No focus move, no live-region announcement.
- **Doc reference:** UI/UX §12 ("Error handling"), UI/UX §17 (row 1), FE-ERR-01 ("no raw error strings")
- **Files:** `src/modules/catalog/components/wizard/details-step.tsx:142-157`,
  `.../listing-wizard.tsx:138-146`, `src/shared/forms/dynamic-form.tsx` (no `serverErrors` prop)
- **Root cause:** The engine was built for client validation only; the server-error path was never wired.
- **Fix:** Add a `serverErrors` prop to `DynamicForm` that calls RHF `setError` by field code, focuses
  the first, and announces via a live region.
- **Effort:** 2 d · **Dependencies:** FE-003 · **Screens:** wizard, listing edit, all config editors.

---

**FE-005 — Business-profile creation is entirely unimplemented**

- **Severity:** Critical · **Category:** Feature completeness
- **Description:** `createBusinessProfile` (contract line 509) has no implementation anywhere in
  `src/modules/profiles/api/*` and no UI calls it (verified: zero hits).
- **Expected:** UI/UX §4 (entire Business Dashboard), FR-PROF — a user can create a company page.
- **Actual:** `dashboard/business/page.tsx:54-64` renders a dead-end `EmptyState` with **no `action`
  prop** — no create CTA, no route, no form. Any account not already owning a profile can never obtain
  one through the UI. `archiveBusinessProfile`, `addPortfolioItem`, `removePortfolioItem` are likewise
  never called, so portfolio management (UI/UX §4.1) does not exist either.
- **Doc reference:** UI/UX §4.1, Handbook §3 (`profiles` module responsibilities)
- **Files:** `src/app/[locale]/(app)/dashboard/business/page.tsx:54-64`, `src/modules/profiles/api/`
- **Root cause:** Feature not built; the empty state masks it as an ordinary "nothing yet" condition.
- **Fix:** Create-profile form (type picker from the closed 8-type set, localized name), plus portfolio
  add/remove/reorder using the existing `MediaUploader`.
- **Effort:** 5 d · **Dependencies:** none · **Screens:** Business dashboard, company profile, portfolio,
  and transitively verification/subscription/team, which all require a profile to exist.

---

**FE-006 — Verification decisions are made without the operator ever seeing the documents**

- **Severity:** Critical · **Category:** Business logic / Trust & Safety
- **Description:** `verification-decision.tsx` contains **zero** references to `document`, `image`,
  `media`, or `VerificationCase.documents` (verified by grep over the whole file).
- **Expected:** UI/UX §6.2 — "Shows submitted documents (CLEAN images), SLA countdown."
- **Actual:** The operator sees case metadata and an approve/reject control with a required reason, but
  never the evidence. `VerificationCase.documents` is a **required** property in the contract
  (`openapi.yaml:4150,4200`) and is simply not read.
- **Doc reference:** UI/UX §6.2, FR-PROF-004/005
- **Files:** `src/modules/profiles/components/verification-decision.tsx` (whole file)
- **Root cause:** Feature omission.
- **Fix:** Render `documents` through the existing CLEAN-only `resolve-media` + `MediaGallery` path.
- **Effort:** 1.5 d · **Dependencies:** none · **Screens:** Admin → Business Verification queue.
- **Risk:** Operators are approving paid business verification on unseen evidence — a direct trust and
  fraud exposure, and the decision is audited server-side as if it were informed.

---

**FE-007 — No Storybook; DS-DOC-01 is a MUST with a CI gate**

- **Severity:** Critical · **Category:** Documentation compliance / Design system
- **Description:** No `.storybook/`, no `*.stories.*` files, no `storybook` dependency anywhere in the
  repository (verified by `find` + `package.json` inspection).
- **Expected:** DS §13 — "Storybook is mandatory (DS-DOC-01)… Every reusable component MUST have a
  Storybook story before merge (a CI gate, DevSecOps §4)"; DS-AI-08 "⚙ story-presence gate". Stories must
  cover all variants, all states, mobile/tablet/desktop viewports, and an a11y check; a "Foundations"
  section must render the token catalogue as the visual source of truth (DS-TOKEN-03).
- **Actual:** Absent in full. QG-10 (frontend gate) cannot be enforcing it.
- **Doc reference:** DS §13, DS-DOC-01, DS-AI-08, DS-TOKEN-03
- **Files:** repository-wide absence
- **Root cause:** Not scaffolded; the CI gate that would have caught it does not check for stories.
- **Fix:** Scaffold Storybook 8 + `@storybook/addon-a11y`, author stories for the base set, add the
  token Foundations page, and wire the presence gate into QG-10.
- **Effort:** 6 d · **Dependencies:** best done with FE-008 · **Screens:** n/a (developer surface).

---

**FE-008 — The design token system specified in DS §2 is roughly one-third implemented**

- **Severity:** Critical · **Category:** Design system / Consistency
- **Description:** `src/styles/globals.css` is a stock shadcn "new-york" token set, not the specified
  Active Home token architecture.
- **Expected:** DS §2 — two-tier primitive/semantic tokens with the naming convention
  `--<category>-<role>-<variant?>-<state?>`; semantic colours (`--color-bg/-surface/-surface-muted/-fg/
  -fg-muted/-primary/-primary-fg/…`); status colours success/warning/danger/info each with `-fg`/`-bg`;
  brand tokens from config; a typography scale **plus type roles** (display, h1–h4, body, body-sm,
  caption, label, overline); a 4px spacing scale; radius; shadows; `--elevation-0…5`; `--opacity-*`;
  the ordered `--z-*` scale (base 0 → tooltip 1600, DS-TOKEN-02); motion `--duration-*`/`--ease-*`.
- **Actual, verified missing entirely:** `--z-*` (0 defined; **29 raw `z-10/20/50` usages**, so every
  overlay — Dialog, Sheet, Drawer, Popover, DropdownMenu, ContextMenu, Menubar, HoverCard, Tooltip,
  Select, AlertDialog — stacks on an undifferentiated `z-50`); `--duration-*`/`--ease-*` (0);
  `--elevation-*` (0, only 3 ad-hoc shadows); typography scale and type roles (0); spacing scale (0);
  `--opacity-*` (0); `warning`/`danger`/`info` status colours (0 — only a bare `success` with no pair);
  `--color-brand`/`-fg` (0). Naming convention does not match the spec anywhere.
- **Doc reference:** DS §2.1–§2.9, DS-TOKEN-01/02/03, FE-DS-02
- **Files:** `src/styles/globals.css` (the repository's only stylesheet)
- **Root cause:** shadcn's default theme was adopted as-is; the specified token layer was never authored
  on top of it.
- **Fix:** Author the semantic token layer (including the z and motion scales), map Tailwind v4 theme
  keys onto it, then migrate components off raw utilities. Lint rule to ban raw `z-` and bracket values.
- **Effort:** 8 d · **Dependencies:** blocks FE-009 and much of Phase 4 · **Screens:** all.

---

### HIGH (22)

---

**FE-009 — No map, location picker, or radius control exists anywhere**

- **Severity:** High · **Category:** Feature completeness / UX
- **Description:** The entire Maps component family is absent. `@types/yandex-maps` is a declared
  devDependency with **zero usages** (verified).
- **Expected:** DS §5.8 (Map, LocationPicker, MapMarker, MapCluster, RadiusControl); UI/UX §8 step 2
  ("location (YandexLocationPicker)"); §2.4 (map on listing detail); §9 ("Map search & radius…
  viewport/center/radius in URL; list↔map hover sync; cluster markers"); §2.2 (mobile full-screen map
  toggle, "radius within 0.1–200 km" validation).
- **Actual:** Location is entered as **two raw latitude/longitude number inputs** — in the wizard
  (`details-step.tsx:99-139`) and in the form engine (`field-registry.tsx:171-204`). No map renders on
  listing detail. No radius control exists in search (verified: no radius UI in any search component).
  Asking a consumer marketplace user in Uzbekistan to type decimal coordinates is not a usable flow.
- **Doc reference:** DS §5.8, UI/UX §2.2/§2.4/§8/§9, DEC-18 (Yandex Maps behind a port)
- **Files:** `src/modules/catalog/components/wizard/details-step.tsx:99-139`,
  `src/shared/forms/field-registry.tsx:166-204`, `src/modules/search/` (no map component)
- **Root cause:** Deferred; needs `NEXT_PUBLIC_YANDEX_MAPS_API_KEY`. The code documents this honestly at
  `field-registry.tsx:167-169`, correctly noting the numeric inputs double as §13's required non-map
  fallback — but the fallback was shipped *instead of*, not *in addition to*, the map.
- **Fix:** `Map`/`LocationPicker`/`RadiusControl` components, `dynamic()`-imported; wire into the
  `location` registry entry, listing detail, and search (radius + viewport in URL per FE-SEARCH-01).
- **Effort:** 8 d · **Dependencies:** Yandex API key provisioning · **Screens:** wizard, listing detail,
  search, category.

---

**FE-010 — Fetch failures are indistinguishable from "no data" across every server-side list**

- **Severity:** High · **Category:** Error handling
- **Description:** Server fetchers uniformly `catch` and return `[]`/`null`, discarding status entirely.
- **Expected:** UI/UX §17/§18, UX-AI-06/14 — distinct error state with retry on every screen; 403 →
  friendly "no access"; 5xx → error + retry + traceId.
- **Actual:** A 401, 403, 404, 500, 503 and a genuinely empty collection all render the same "nothing
  here yet" `EmptyState`. Verified across `admin/api/ops-server.ts:39,56,91,111`,
  `admin/api/admin-server.ts:25,53,66`, `profiles/api/verification-server.ts:28-43`,
  `catalog/api/get-listing.ts:13-24`, `billing/api/billing-server.ts:15-38`,
  `media/api/upload.ts:73-83`. Only `getAdminDashboard` (`admin-server.ts:13-30`) distinguishes
  "unavailable" from real zeros, and documents why (DEF-14).
- **Doc reference:** UI/UX §17, §18; Handbook §18; UX-AI-06
- **Files:** as listed above
- **Root cause:** `if (error || !data) return []` idiom adopted repo-wide for terse call sites.
- **Fix:** Return a discriminated `Result` from server fetchers; render `ErrorState` vs `EmptyState`
  accordingly.
- **Effort:** 4 d · **Dependencies:** FE-003 · **Screens:** all admin screens, all dashboard lists,
  listing detail, business profile.

---

**FE-011 — `ErrorState` on 1 of 31 pages; no per-segment `error.tsx` or `loading.tsx`**

- **Severity:** High · **Category:** Feature completeness / UX
- **Description:** Scripted count across all 31 `page.tsx` files: `ErrorState` appears in **1**
  (`search`), skeletons in **1** (`home`). There is exactly one `loading.tsx` in the entire app
  (`(public)/search/`) and one `error.tsx` (`[locale]/`), plus `global-error.tsx`. **No `error.tsx` or
  `loading.tsx` exists anywhere under `(admin)/` or `(app)/`.**
- **Expected:** UX-AI-06 (review-blocking) — "Always implement loading, empty, and error states (+
  success) for **every** screen"; Handbook §5 — "`error.tsx` per route segment", "`loading.tsx` per
  segment provides Suspense fallbacks (skeletons)"; UI/UX §18 lists the required skeleton per major
  screen (Home, Search, Listing detail, Dashboard, tables, chat, wizard, config editors).
- **Actual:** 29 of 31 pages have no loading skeleton and no recoverable error boundary; a segment
  failure escalates to the single root boundary.
- **Doc reference:** UI/UX §18, Handbook §5, UX-AI-06/14
- **Files:** `src/app/[locale]/**` (absence)
- **Root cause:** States were implemented per-screen ad hoc; empty was done well (15 pages), loading and
  error were not.
- **Fix:** Add `loading.tsx` + `error.tsx` per route segment with content-shaped skeletons.
- **Effort:** 5 d · **Dependencies:** FE-010 · **Screens:** all except home and search.

---

**FE-012 — 2 component tests for 60 components; no integration or journey E2E**

- **Severity:** High · **Category:** Testing / Production readiness
- **Description:** 16 test files, 131 tests, all passing — but almost entirely pure-logic unit tests.
  Verified: 60 component files, **2** `*.test.tsx`. RTL/jest-axe appear in 2 files. MSW is 34 lines of
  hand-written handlers used by exactly 1 test. E2E is a single `smoke.spec.ts` with 6 tests.
- **Expected:** Handbook §19 — Component tests (RTL + jest-axe) for base/shared/business components every
  PR; Integration tests with MSW for feature flows (form submit, search, auth) every PR; **E2E critical
  journeys: register → create → publish → search → message → purchase**, plus locale switch and a11y
  smoke. FE-TEST-01 (MUST) — "API mocks (MSW) are **derived from the OpenAPI spec**".
- **Actual:** No component test suite, no integration flow tests, no journey E2E. MSW handlers are
  hand-written, so FE-TEST-01 is unmet — tests cannot catch shapes the backend does not serve.
- **Doc reference:** Handbook §19, FE-TEST-01
- **Files:** `src/**/*.test.*`, `e2e/smoke.spec.ts`, `src/test/msw/handlers.ts`
- **Root cause:** Logic-first testing strategy; UI testing deferred.
- **Fix:** Generate MSW handlers from `openapi.yaml`; add component+axe tests for the base set and each
  form field type; add the six-step journey E2E.
- **Effort:** 10 d · **Dependencies:** FE-001 fix should land first · **Screens:** n/a.

---

**FE-013 — Listing images cannot be changed after creation**

- **Severity:** High · **Category:** Feature completeness
- **Description:** `attachListingImage`, `detachListingImage`, `reorderListingImages`,
  `listListingImages`, `deleteMedia` are never called anywhere (verified).
- **Expected:** UI/UX §3.2 (owner manages listings), §8 (reorder, index 0 = primary), BRULE-06 (≤10
  images); the contract provides all four image operations.
- **Actual:** Images can be set **only** at creation via inline `imageMediaAssetIds`.
  `listing-edit-form.tsx` contains zero image code, and `ListingUpdateRequest` carries no image field —
  so an owner who uploads a wrong photo can never fix it.
- **Doc reference:** UI/UX §3.2/§8, contract `/listings/{listingId}/images`
- **Files:** `src/modules/catalog/components/listing-edit-form.tsx`, `src/modules/catalog/api/mutate-listing.ts:79-81`
- **Root cause:** Edit flow scoped to text fields only.
- **Fix:** Add a media section to the edit form reusing `MediaUploader` + the attach/detach/reorder ops.
- **Effort:** 3 d · **Dependencies:** none · **Screens:** My Ads → Edit listing.

---

**FE-014 — Categories editor is a single-node form, not a tree**

- **Severity:** High · **Category:** Feature completeness / Config authoring
- **Description:** `category-editor.tsx` edits one node (name, path, status, form binding, parent
  dropdown). There is no tree.
- **Expected:** UI/UX §5.2 (in a section marked **CRITICAL**) — "Categories: **tree editor**
  (parent/order/path preview), localized names, bind exactly one form definition (required), status
  Active/Retired; structural moves warn about remap. (I-02/I-03.)"
- **Actual:** No visual tree, no ordering UI, no subtree path preview, no structural-move warning. The
  file documents the limitation and its cause (no assembled-taxonomy endpoint, no transactional reparent
  operation) at `category-editor.tsx:24-48`.
- **Doc reference:** UI/UX §5.2
- **Files:** `src/modules/configuration/components/category-editor.tsx:24-48`
- **Root cause:** Partly a contract limitation (no reparent operation), partly unbuilt UI.
- **Fix:** Tree view over `listCategories` with drag-reorder; ADR if a transactional reparent op is needed.
- **Effort:** 5 d · **Dependencies:** possible ADR · **Screens:** Product Owner → Categories.

---

**FE-015 — Form builder has no live preview, and cannot edit validators, conditional visibility, or rendering hints**

- **Severity:** High · **Category:** Feature completeness / Config authoring
- **Description:** Two distinct gaps in the same editor. Verified: zero `preview`/`DynamicForm`
  references in `form-builder.tsx`.
- **Expected:** UI/UX §5.2 — "Dynamic Forms: section builder → fields builder (add field: code,
  localized label, field type from whitelist, required, facet-eligible, options for select types,
  **validators from whitelist with params**, **conditional-visibility rule**, **rendering hint**, order).
  **Live preview via the real form engine** (§12)."
- **Actual:** No preview — even though a working engine (`DynamicForm`) exists in the same codebase and
  is imported by the wizard. `validators`, `conditional_visibility`, `rendering_hint` and `default_value`
  are preserved by object-spread but **editable only by switching to the raw-JSON view**
  (self-documented at `form-builder.tsx:26-30`). Facet-eligible and field-type picker do work.
- **Doc reference:** UI/UX §5.2, §12; I-07/I-16
- **Files:** `src/modules/configuration/components/form-builder.tsx:26-30`
- **Root cause:** Structured builder implemented for the simple field properties only.
- **Fix:** Add a validator picker (params per whitelisted validator), a conditional-visibility rule
  builder, a rendering-hint selector, and mount `DynamicForm` beside the builder as a live preview.
- **Effort:** 6 d · **Dependencies:** none — the engine already exists · **Screens:** Product Owner →
  Dynamic Forms.
- **Note:** This is the highest-leverage config gap. The *engine* supports validators and conditional
  visibility fully; the *authoring surface* is the bottleneck, so Product Owners cannot use capabilities
  the platform already has without hand-editing JSON.

---

**FE-016 — Platform Settings / Feature Flags / SEO / Static Pages have no structured editor**

- **Severity:** High · **Category:** Feature completeness / Config authoring
- **Description:** All Platform Settings sub-concerns fall through to the generic raw-JSON textarea.
  `asPlatformSettings` exists (`definition-content.ts:423-427`) but is never imported by any component.
- **Expected:** UI/UX §5.2 — "settings editor with typed keys; flags as **typed toggles** (controlled
  track); SEO templates + static pages as keyed content."
- **Actual:** Raw JSON editing only for every one of them.
- **Doc reference:** UI/UX §5.2 (CRITICAL section)
- **Files:** `src/modules/configuration/components/draft-editor.tsx:19-42`
- **Root cause:** Editor not built. Compounded by CG-1 — there is no read side to validate against.
- **Fix:** Typed settings editor with toggle controls for flags and keyed content editors for SEO/static
  pages.
- **Effort:** 5 d · **Dependencies:** CG-1 for the read path · **Screens:** Product Owner → Platform Settings.

---

**FE-017 — Session expiry discards the return route; the plumbing exists but is unwired**

- **Severity:** High · **Category:** Authentication / UX
- **Description:** Guards redirect to a bare `/login` with no return target.
- **Expected:** Handbook §10 + UI/UX §17 — "the API layer clears session context, **preserves the current
  route as a return target**, and routes to login… In-flight unsaved form data is preserved where feasible."
- **Actual:** `(app)/layout.tsx:23` and `(admin)/layout.tsx:25` call `redirect({href:"/login"})` with no
  param. `login/page.tsx` never reads a redirect target. `EmailLoginForm` and `PhoneOtpForm` both accept
  a `redirectTo` prop that **no caller ever passes** — every use falls back to `"/"`. A session expiring
  mid-edit returns the user to the home page with their work lost.
- **Doc reference:** Handbook §10, UI/UX §17 (Session expiration row)
- **Files:** `src/app/[locale]/(app)/layout.tsx:23`, `(admin)/layout.tsx:25`,
  `src/modules/identity/components/email-login-form.tsx:16,38`, `phone-otp-form.tsx:27,64`
- **Root cause:** Props were designed for this and never connected.
- **Fix:** Pass `?returnTo=` through the redirect, read it in the login page, wire the existing props.
  Preserve wizard draft (already in localStorage) explicitly.
- **Effort:** 1.5 d · **Dependencies:** none · **Screens:** every authenticated screen.

---

**FE-018 — 118 physical CSS directions, 0 logical (FE-I18N-02 systemic violation)**

- **Severity:** High · **Category:** i18n / Architecture
- **Description:** Scripted count: **118** physical-direction utilities (`ml-`, `mr-`, `pl-`, `pr-`,
  `left-`, `right-`, `text-left`, `text-right`, `border-l/r`, `rounded-l/r`) against **0** genuine
  logical usages (`ms-`, `me-`, `ps-`, `pe-`, `start-`, `end-`, `text-start/end`).
- **Expected:** FE-I18N-02 (MUST) — "Use logical CSS properties throughout for future RTL"; DS §8;
  Handbook §15 — "Do not hardcode physical directions", so a future RTL locale is "a configuration/token
  change, not a rewrite".
- **Actual:** Not a partial migration — logical properties are used nowhere. Distribution: 86 in
  `shared/ui`, 24 in `modules`, 4 in `app`, 3 in `shared/layout`, 1 in `shared/forms`. Live offenders
  include `media-gallery.tsx:75,85,89`, `listing-card.tsx:63`, `category-picker.tsx:115,135,188`,
  `media-uploader.tsx:213,222`, `site-header.tsx:56,61,75`, and the used shadcn primitives
  `dialog.tsx:41,47,57`, `sheet.tsx:41,43,64,75`, `dropdown-menu.tsx` (11).
- **Doc reference:** FE-I18N-02, Handbook §15, DS §8
- **Files:** as above
- **Root cause:** Default Tailwind/shadcn idiom; no lint rule bans physical utilities.
- **Fix:** Codemod to logical equivalents; add an ESLint/Tailwind rule to prevent regression.
- **Effort:** 3 d · **Dependencies:** none · **Screens:** all.

---

**FE-019 — No `hreflang` alternates on any route**

- **Severity:** High · **Category:** SEO / i18n
- **Description:** Zero occurrences of `alternates`/`hreflang` in `src/`, despite 30 route files
  implementing `generateMetadata`. No `sitemap.ts` either (only `public/robots.txt`).
- **Expected:** Handbook §15 — "Locale is part of the URL for SEO and shareability (**hreflang alternates
  emitted**)"; SSR/SEO is a Baseline constraint and the platform ships four first-class locales.
- **Actual:** The four locale variants of every page are uncrosslinked, so search engines see them as
  unrelated or duplicate content — a direct loss for a marketplace whose discovery depends on organic
  search.
- **Doc reference:** Handbook §15, §16 (FE-PERF-01)
- **Files:** all 30 `generateMetadata` implementations, e.g. `(public)/listings/[slug]/page.tsx:42-50`
- **Root cause:** Omission.
- **Fix:** Add `alternates.languages` to a shared metadata helper; add `sitemap.ts` with locale alternates.
- **Effort:** 1.5 d · **Dependencies:** none · **Screens:** all public routes.

---

**FE-020 — `renderingHint` is leaked to users as visible helper text**

- **Severity:** High · **Category:** Business logic / i18n / UX
- **Description:** Any `renderingHint` other than `"full-width"` is rendered into `<FormDescription>`.
- **Expected:** UI/UX §12 — `renderingHint` is a **layout** directive: "responsive columns from
  `renderingHint` + breakpoint tokens (1-col mobile → multi-col desktop)".
- **Actual:** `dynamic-form.tsx:157-160` renders the raw hint value as the field's description. A machine
  token (e.g. `"two-column"`, `"compact"`) is displayed to end users as if it were guidance —
  untranslated, in all four locales. Only `"full-width"` is honoured as layout; the section grid is
  otherwise hardcoded `sm:grid-cols-2`.
- **Doc reference:** UI/UX §12 ("Field layout"), FE-I18N-01
- **Files:** `src/shared/forms/dynamic-form.tsx:123,157-160`
- **Root cause:** Unrecognised hints were given a fallback rendering instead of being ignored.
- **Fix:** Map hints to column spans; never render the hint as text. Add a `hint`/`helpText` field to the
  definition if author-supplied guidance is wanted.
- **Effort:** 1 d · **Dependencies:** none · **Screens:** every dynamic form.

---

**FE-021 — Wizard preview renders raw attribute codes instead of form labels**

- **Severity:** High · **Category:** Business logic
- **Description:** The preview step lists `Object.entries(draft.attributes)` using the **field code** as
  the term, and `JSON.stringify` for object values.
- **Expected:** UI/UX §8 step 4 — "Renders the listing exactly as the public detail page will show it
  (**attributes paired with form labels**)"; FE-ADV-01 (MUST) — attributes rendered "by pairing the stored
  `AttributeMap` with the bound `FormDefinition`'s field labels/types".
- **Actual:** `listing-wizard.tsx:302` renders `{code}` (e.g. `floor_count`), and `:305` emits raw JSON
  for range/location values. The `FormDefinition` is already loaded one step earlier, so the labels are
  in hand. The public detail page does this correctly via `listing-attributes.tsx` — so preview and
  reality diverge, which is precisely what the step exists to prevent.
- **Doc reference:** UI/UX §8, FE-ADV-01
- **Files:** `src/modules/catalog/components/wizard/listing-wizard.tsx:298-311`
- **Root cause:** Preview built without threading the definition through.
- **Fix:** Reuse `ListingAttributes` with the bound definition.
- **Effort:** 0.5 d · **Dependencies:** none · **Screens:** Wizard step 4.

---

**FE-022 — Admin "Advertisement Management" (§6.4) does not exist**

- **Severity:** High · **Category:** Feature completeness
- **Description:** No route, no nav entry, no listing lookup UI for operators.
- **Expected:** UI/UX §6.4 — "search/inspect **any** listing; apply moderation actions
  (hide/suspend/remove/request correction) via moderation. Ownership not required (operator authority);
  all actions audited."
- **Actual:** Absent entirely (verified by `find` over `(admin)/` and `admin-nav.tsx:33-42`). Operators
  can only act on listings that already surfaced in the moderation queue — they cannot proactively look
  one up.
- **Doc reference:** UI/UX §6.4
- **Files:** absence under `src/app/[locale]/(admin)/`
- **Fix:** Listing search/inspect page reusing `searchListings` + `applyModerationAction`.
- **Effort:** 3 d · **Dependencies:** none · **Screens:** new Admin → Advertisements.

---

**FE-023 — Moderation has no case detail, no history, and no claim workflow**

- **Severity:** High · **Category:** Feature completeness
- **Description:** `getModerationCase` is implemented and exported but **never called by any page or
  component** (verified) — dead code.
- **Expected:** UI/UX §7 — case detail showing "subject (listing/conversation/user), origin (user report
  vs automated flag), reason/rule, **history**"; workflow "Open → In Review (**claim**) → Resolved.
  Optimistic claim; conflict if already claimed"; "queue list + detail **drawer** on desktop, stacked on
  mobile".
- **Actual:** A flat list of rows. Origin and reason appear inline (`moderation-case-row.tsx:71-86`), but
  there is no detail view, no history, no drawer, and no claim. The closed verb set and required note are
  correctly implemented and contract-typed.
- **Doc reference:** UI/UX §7
- **Files:** `src/modules/admin/api/admin-server.ts:60-71` (unused), `src/app/[locale]/(admin)/admin/moderation/page.tsx`
- **Root cause:** Detail view unbuilt; the claim workflow is additionally blocked — **no `claim`
  operation exists in the contract** (verified), so that half needs an ADR.
- **Fix:** Case-detail drawer consuming `getModerationCase`; ADR for a claim/assign operation.
- **Effort:** 4 d (+ADR) · **Dependencies:** ADR for claim · **Screens:** Moderation queue.

---

**FE-024 — Invoice payment is confirmed with no dialog and no note**

- **Severity:** High · **Category:** Business logic / Financial
- **Description:** `confirm()` calls `confirmInvoicePayment(invoice.id)` directly from the click handler.
- **Expected:** UI/UX §6.7 — "Validation: **confirm dialog + optional note**. Audited."
- **Actual:** No confirmation step at all, and the `note` parameter the API supports
  (`admin/api/ops.ts:46-57`) is never passed. Confirming an offline payment activates entitlements and is
  audited as an operator decision — a single misclick is irreversible from the UI.
- **Doc reference:** UI/UX §6.7, DEC-02 (offline billing)
- **Files:** `src/modules/admin/components/invoice-row.tsx:34-46,68-82`
- **Fix:** `ConfirmDialog` with an optional note field.
- **Effort:** 0.5 d · **Dependencies:** needs a `ConfirmDialog` component (FE-034) · **Screens:** Admin → Invoices.

---

**FE-025 — Admin Reports render raw JSON; no charts, no export**

- **Severity:** High · **Category:** Feature completeness
- **Description:** Report datasets are rendered as `<pre>{JSON.stringify(...)}</pre>`.
- **Expected:** UI/UX §6.6 — "Rendered as **charts + export**"; DS §5.11 Chart component with a data-table
  alternative and labelled axes.
- **Actual:** No charts, no export button. The page documents a *defensible* reason for not charting
  (`reports/page.tsx:26-35`): `getAdminReports` returns `additionalProperties: true` with no declared
  shape, so charting would mean guessing a schema per report. That reasoning holds for charts — **it does
  not explain the missing export**, which needs no schema.
- **Doc reference:** UI/UX §6.6
- **Files:** `src/app/[locale]/(admin)/admin/reports/page.tsx:26-35,77-83`
- **Fix:** Add CSV/JSON export now; ADR to declare a response schema per report, then chart.
- **Effort:** 1 d export, +3 d charts after ADR · **Dependencies:** ADR for chart schemas · **Screens:** Admin → Reports.

---

**FE-026 — React Query `retry: false` globally; `Retry-After` never honoured**

- **Severity:** High · **Category:** API integration / Resilience
- **Description:** `providers.tsx:27` sets `retry: false` on the `QueryClient` — the only retry config in
  the app. Zero occurrences of `Retry-After`/`retryAfter` in `src/`.
- **Expected:** Handbook §9 — "Idempotent GETs retry with capped exponential backoff… on network/5xx";
  "On 429, honour `Retry-After`"; UI/UX §17 — 429 → "Try again in Ns" with the control disabled per
  `Retry-After`.
- **Actual:** Every `useQuery` in the app inherits zero retries, so one transient blip is a hard error
  with no automatic recovery. 429 handling shows a generic notice without the wait time, even though the
  contract defines `Retry-After` headers (`openapi.yaml:3465,3484`).
- **Doc reference:** Handbook §9, UI/UX §17 (Rate limited row)
- **Files:** `src/app/[locale]/providers.tsx:24-28`
- **Fix:** Enable capped exponential backoff for GETs; parse `Retry-After` into countdown UX.
- **Effort:** 1.5 d · **Dependencies:** FE-003 · **Screens:** all.

---

**FE-027 — Google OAuth callback bypasses `shared/api` with a raw `fetch` and hand-written body**

- **Severity:** High · **Category:** Architecture
- **Description:** Raw `fetch()` to `${serverBaseUrl}/auth/login/google` with a manually constructed JSON
  body.
- **Expected:** FE-API-01 (MUST) — "All HTTP goes through `shared/api`; no fetch/axios in components or
  modules"; FAIR-05 — generated types only.
- **Actual:** The shape matches `GoogleSignInRequest` today, but nothing enforces that at compile time —
  a contract change here would not produce a type error. This is the one API call in the application not
  protected by the generated client. (The other raw `fetch`, the presigned PUT to MinIO in
  `upload.ts:58`, is correct by design and outside the contract.)
- **Doc reference:** Handbook §9 (FE-API-01), FAIR-03/05
- **Files:** `src/app/api/auth/google/callback/route.ts:39-46`
- **Fix:** Use `getServerApiClient().POST("/auth/login/google", …)`.
- **Effort:** 0.5 d · **Dependencies:** none · **Screens:** Google sign-in.

---

**FE-028 — Hardcoded English strings reach screen-reader users in all four locales**

- **Severity:** High · **Category:** i18n / Accessibility
- **Description:** Live components carry untranslated `aria-label`/`sr-only` text.
- **Expected:** FE-I18N-01 (MUST) — "No user-facing string is hardcoded in a component."
- **Actual:** `media-gallery.tsx:73,83` (`"Previous image"`, `"Next image"`);
  `listing-card-skeleton.tsx:21` (`"Loading listings"`); `field-registry.tsx:138,152,179,192`
  (`"min"`, `"max"`, `"latitude"`, `"longitude"` — on every range and location field in every dynamic
  form); `dialog.tsx:49` and `sheet.tsx:66` (`sr-only "Close"`, confirmed live in 7 and 3 files). A
  Russian or Uzbek screen-reader user hears English.
- **Doc reference:** FE-I18N-01, DS §8
- **Files:** as listed
- **Fix:** Route through `t()`; for the shadcn primitives, thread a localized label prop.
- **Effort:** 1 d · **Dependencies:** none · **Screens:** listing grids, galleries, all dynamic forms, all dialogs.

---

**FE-029 — Dark theme is fully authored but unreachable; brand is hardcoded**

- **Severity:** High · **Category:** Design system
- **Description:** `globals.css:110-153` defines a complete `.dark` token override block. Nothing in the
  application ever sets it — no `ThemeProvider`, no `next-themes`, no `data-theme` attribute anywhere
  (verified, zero hits for all three).
- **Expected:** DS §3 — themes on `[data-theme]`, `ThemeProvider` persisting to a cookie, SSR reads the
  cookie to avoid flash, "v1 exposes light only in UI; the switcher is **wired** but hidden behind a
  feature flag"; brand tokens from the PlatformSettings snapshot (FE-DS-01).
- **Actual:** Dead code — authored, unreachable, and silently rotting. Brand colours are static OKLCH
  literals (`globals.css:56-108`) and the app name is hardcoded in the message catalogues, so re-branding
  requires a deploy — the exact outcome DEC-21 exists to prevent.
- **Doc reference:** DS §3, FE-DS-01, DEC-21
- **Files:** `src/styles/globals.css:56-153`, `src/app/[locale]/layout.tsx:18-19`
- **Fix:** Add `ThemeProvider` with cookie persistence and SSR read; source brand tokens from config once
  CG-1 lands.
- **Effort:** 2 d (+CG-1 for brand) · **Dependencies:** CG-1 · **Screens:** all.

---

**FE-030 — `listingType` is hardcoded; PRODUCT and SERVICE listings cannot be created**

- **Severity:** High · **Category:** Feature completeness
- **Description:** `EMPTY_DRAFT.listingType` is fixed to `"ADVERTISEMENT"` and no UI ever changes it
  (verified — the only writes are the constant and the submit).
- **Expected:** `ListingCreateRequest.listingType` is **required** with enum
  `ADVERTISEMENT | PRODUCT | SERVICE`. UI/UX §8 covers listing creation generally.
- **Actual:** Two of the three listing types are unreachable through the UI.
- **Doc reference:** `contracts/openapi.yaml` `ListingCreateRequest`
- **Files:** `src/modules/catalog/components/wizard/wizard-state.ts:21,30`
- **Root cause:** Type selection never added to the wizard.
- **Fix:** Add a type step or selector. **Ambiguity flagged:** no frontend document specifies *where* the
  choice belongs or whether category selection should imply it — this needs a product decision, not a
  guess.
- **Effort:** 1.5 d · **Dependencies:** product decision · **Screens:** Wizard step 1.

---

### MEDIUM (28)

| ID | Title | Category | Expected vs. Actual | Doc | File(s) | Fix | Eff. |
|---|---|---|---|---|---|---|---|
| FE-031 | No virtualization anywhere | Performance | Handbook §16 + DS §12: virtualize >~50 rows (search, chat, audit, admin grids). Actual: `@tanstack/react-virtual` is a dependency with **zero usages**; audit log is a plain `.map()` capped at 100 | H §16, DS §12 | `admin/audit/page.tsx:82-100`, `chat-thread.tsx`, `search-results.tsx` | Adopt TanStack Virtual on the four long lists | 3 d |
| FE-032 | No code splitting | Performance | Handbook §16/DS §12: `dynamic()`-import Map, Charts, Lightbox, ConfigDraftEditor. Actual: **zero** `next/dynamic`/`React.lazy` in `src/`; `chart.tsx` (331 L) and `draft-editor.tsx` (447 L) load eagerly | H §16 | repo-wide | `dynamic()` the heavy client widgets | 1 d |
| FE-033 | List items not memoized | Performance | DS §12: memoize `AdvertisementCard`/table rows. Actual: no `React.memo` on `listing-card.tsx` or any admin row | DS §12 | `catalog/components/listing-card.tsx` | Wrap in `memo`, stabilize callbacks | 1 d |
| FE-034 | Missing design-system primitives | Design system | DS §4/§5 require Icon, Text/Heading, Spinner, VisuallyHidden, AppShell, PageContainer, Grid, Stack, Chip, Tag, DescriptionList, StatCard, DatePicker, RangeSlider, Autocomplete, ConfirmDialog, InlineMessage, Lightbox. Actual: all absent | DS §4, §5 | `src/shared/ui/` | Build the missing set | 6 d |
| FE-035 | Heading markup copy-pasted 21× | Consistency | DS §5.1 Text/Heading with type roles. Actual: literal `font-display text-2xl font-semibold` repeated in 19 files | DS §5.1, FAIR-04 | 19 page files | Introduce `Heading`, migrate | 1.5 d |
| FE-036 | Hand-rolled inputs duplicate `Input`'s own classes | Design system | FAIR-06/DS-AI-02: never hand-roll. Actual: raw `<input>` with a near-identical class string | FAIR-06 | `admin/users/page.tsx:49`, `admin/audit/page.tsx:58,66` | Use `Input` | 0.5 d |
| FE-037 | Hand-rolled buttons/checkboxes | Design system | As above. Actual: raw `<button>` ×4, raw `<input type=checkbox>` ×2 | FAIR-06 | `media-gallery.tsx:100`, `category-picker.tsx:131`, `notification-list.tsx:113`, `dynamic-form.tsx:174`, `form-builder.tsx:388,403` | Use `Button`/`Checkbox` | 1 d |
| FE-038 | `date` field renders a native text input, not `DatePicker` | Forms / i18n | UI/UX §12: `date → DatePicker`, localized month/day names, keyboard grid. Actual: `TextControl` with `type="date"`; `calendar.tsx` + `react-day-picker` exist and are unused. Native input formats by *browser* locale, not app locale | UI/UX §12, DS §5.2 | `field-registry.tsx:39,207` | Build `DatePicker`, wire registry | 1.5 d |
| FE-039 | `range` field renders two number inputs, not `RangeSlider` | Forms | UI/UX §12: `range → RangeSlider`, dual-thumb, arrow keys, `aria-valuenow/-valuetext`. Actual: two `<Input type=number>`; `slider.tsx` exists and is unused | UI/UX §12, DS §5.2 | `field-registry.tsx:130-164` | Build `RangeSlider`, wire registry | 1.5 d |
| FE-040 | Currency is a free-text field | Business logic / Data integrity | UI/UX §16 mirrors contract constraints; `Money.currency` is constrained. Actual: a 3-char free-text `Input` uppercased on change — a user can type `XYZ` | UI/UX §16 | `wizard/details-step.tsx:89-97` | `Select` over allowed currencies (UZS in v1) | 0.5 d |
| FE-041 | Upload has no progress, cancel, or retry | UX / Forms | DS §5.2 FileUpload states `idle/drag-over/uploading(progress)/scanning/clean/error/quarantined`, ProgressBar `aria-valuenow`; UI/UX §19 "progress bar for media upload". Actual: **zero** progress/cancel/retry (grep-verified); a spinner stands in | DS §5.2, UI/UX §8/§19 | `media/components/media-uploader.tsx` | Add XHR progress, abort, retry | 2.5 d |
| FE-042 | Uploader controls below minimum touch target | Accessibility | DS §8/UI/UX §14: ≥44px preferred on touch. Actual: remove `size-7` (28px), reorder `size-6` (24px) | DS §8 | `media-uploader.tsx:222,235,246` | Enlarge to 44px on touch | 0.5 d |
| FE-043 | User-uploaded thumbnails have `alt=""` | Accessibility | DS §5.7: content images need alt. Actual: `alt=""` on photos the user must distinguish to reorder/delete | DS §5.7 | `media-uploader.tsx:201` | Add positional alt ("Photo 2 of 5") | 0.25 d |
| FE-044 | Logout does not clear the query cache | Auth / Security | Handbook §10: "clears session/query caches". Actual: only `["session","me"]` invalidated; no `queryClient.clear()`, no reload — unlike `close-account.tsx:62-64`, which does it correctly and explains why | H §10 | `shared/layout/account-menu.tsx:49-60` | `queryClient.clear()` + hard navigation | 0.5 d |
| FE-045 | Notification read-state never invalidates the bell | State / API | Handbook §8: single owner for server state. Actual: `notification-list.tsx:46-76` mutates then updates local `useState` only; the bell's `["notifications","unread"]` query stays stale 60–120 s | H §8 | `notifications/components/notification-list.tsx:46-76` | `invalidateQueries` after mutation | 0.5 d |
| FE-046 | 503 `DEPENDENCY_DEGRADED` unhandled except via search's body flag | Error handling | UI/UX §17: 503 → reduced functionality with subtle notice. Actual: contract declares 503 on `listCategories`, `getCategoryForm`, `searchListingsGet/Post`; only the 200-body `degraded:true` case is handled | UI/UX §17 | `search-listings-server.ts:27-38`, `use-categories.ts`, `get-category-form.ts` | Branch on 503 | 1 d |
| FE-047 | `as never` casts defeat contract-drift protection | Type safety | FAIR-03/05: generated types enforce the contract. Actual: 10 sites declare inline body types then cast `as never`; shapes match today but a contract change would not error | FAIR-05 | `mutate-listing.ts:220`, `admin-config.ts:39,61,79,133,159`, `config-ops.ts:181`, `company.ts:36`, `verification.ts:48`, `ops.ts:50` | Use `components["schemas"][…]` directly | 1.5 d |
| FE-048 | 403 not distinguishable from empty on read paths | Authorization / UX | UI/UX §17: 403 → friendly "no access". Actual: read failures collapse to empty (see FE-010); only write paths distinguish `PERMISSION_DENIED` (which they do consistently and well) | UI/UX §17 | `admin/api/*-server.ts` | Ride on FE-010 | — |
| FE-049 | Audit log missing actor and date-range filters | Feature completeness | UI/UX §6.5: "Filters: actor, target type, action, **date range**". Actual: only action + targetType; `actorUserId` is supported server-side and unused | UI/UX §6.5 | `admin/audit/page.tsx:57-77`, `ops-server.ts:68-96` | Add the two filters | 1 d |
| FE-050 | 4 of 5 admin KPI tiles do not link to their queue | UX | UI/UX §6: "each KPI links to its queue". Actual: only `pendingModeration` has an href; the other four are `null` although the target routes exist | UI/UX §6 | `admin/page.tsx:41-57` | Add hrefs | 0.25 d |
| FE-051 | Config head list missing "current version" and "updated" columns | Feature completeness | UI/UX §5.1: DataTable of heads (code, status, **current version**, owner, **updated**) | UI/UX §5.1 | `admin/config/[entityType]/page.tsx:59-65` | Add columns | 0.5 d |
| FE-052 | Chat: no 4000-char limit, no virtualized history, no read receipts | Feature completeness | UI/UX §10: composer "text, 1–4000 chars", "delivered/read status", "virtualized history for long threads". Actual: no maxLength (grep: no `4000`), no virtualization, no `readAt` | UI/UX §10, §16 | `messaging/components/chat-thread.tsx` | Add limit + counter; virtualize. Read receipts need a contract op (none exists) | 2 d |
| FE-053 | No saved searches | Feature completeness | UI/UX §3.6 permits omission **only** behind a feature flag ("flagged off rather than faked") | UI/UX §3.6 | `dashboard-nav.tsx:20-27` | Correct to omit; requires the flag mechanism (CG-1) to be compliant | — |
| FE-054 | Business dashboard cannot deep-link to a specific profile | UX / Routing | Handbook §4: `(app)/business/[profileId]`. Actual: consolidated to one route scoped to `ownedProfileIds[0]`; an owner of 2+ profiles cannot reach the second except via the acting-context switcher | H §4 | `dashboard/business/page.tsx:52` | Add `[profileId]` segment | 1.5 d |
| FE-055 | Whitelist mirrors have no drift test | Maintainability | Backend whitelists are mirrored as literal arrays (`FIELD_TYPES`, `VALIDATOR_TYPES`, `PERMISSION_KEYS`, `MODERATION_ACTIONS`, `PRODUCT_TYPES`, `EVENT_KEYS`, `CONFIG_ENTITY_TYPES`). Legitimately code, not config — but a backend rename desyncs pickers silently | AIR/FAIR-01 note | `configuration/types/definition-content.ts:95-461`, `admin/api/moderation.ts:19-29` | Add a contract-derived drift test | 1 d |
| FE-056 | MSW handlers not derived from OpenAPI | Testing | FE-TEST-01 (MUST): mocks derived from the spec. Actual: 34 hand-written lines | FE-TEST-01 | `src/test/msw/handlers.ts` | Generate from `openapi.yaml` | 1.5 d |
| FE-057 | `prefers-reduced-motion` ignored | Accessibility | DS §10/UI/UX §19: all decorative motion disabled when set. Actual: **zero** occurrences in `src/`; `animate-marquee`/`float`/`shimmer` run unconditionally | DS §10 | `styles/globals.css:205-242` | Add the media query | 0.5 d |
| FE-058 | Motion exceeds the 300 ms ceiling | Design system | DS §10/DS-MOTION-01: nothing over ~300 ms except progress. Actual: `duration-700` on the listing-card hover scale | DS-MOTION-01 | `catalog/components/listing-card.tsx:52` | Use a motion token ≤300 ms | 0.25 d |

---

### LOW (14)

| ID | Title | Category | Note | File(s) | Eff. |
|---|---|---|---|---|---|
| FE-059 | 26 of 48 `shared/ui` components entirely unused | Dead code | Includes `sidebar.tsx` (738 L, the repo's largest file), `menubar`, `context-menu`, `carousel`, `command`, `resizable`. Notably `pagination` and `breadcrumb` are unused *because* those features are unbuilt (UI/UX §2.3/§2.4 require breadcrumbs; §13 requires Pagination) | `src/shared/ui/` | 1 d |
| FE-060 | `hasRole`/`hasAnyRole` are dead code | Dead code / Risk | Never called; a future contributor could wire them to a literal role check, violating FAIR-02 | `shared/config/use-permissions.ts:21-22` | 0.25 d |
| FE-061 | `formDefinitionVersionId` is captured then discarded | Dead state | Correct **not** to submit it (`ListingCreateRequest` has `additionalProperties: false` and no such field), but it is stored in the draft and never used | `wizard/wizard-state.ts:20`, `details-step.tsx:178` | 0.25 d |
| FE-062 | Unreachable `"VALIDATION_ERROR"` branch | Correctness | Contract's closed vocabulary uses `VALIDATION_FAILED`; masked today by a `status === 422` fallthrough | `catalog/api/mutate-listing.ts:51` | 0.1 d |
| FE-063 | Space Grotesk lacks Cyrillic glyphs | i18n / Branding | `--font-display` ships latin/latin-ext/vietnamese only; ru and uz-Cyrl headings silently fall back to Inter, so the display face differs by locale. Degrades gracefully, so easy to miss | `styles/globals.css:3-4,17` | 0.5 d |
| FE-064 | Hardcoded English in 10 unused shadcn primitives | i18n | `"Previous"`, `"Next"`, `"Toggle Sidebar"` etc. Currently unreachable (FE-059) but will violate FE-I18N-01 the moment they are used | `shared/ui/*` | 0.5 d |
| FE-065 | 5 raw hex colours | Design system | 4 are the Google "G" brand mark (legitimate); 1 is a recharts selector, not a style choice | `identity/components/google-button.tsx:56-65`, `ui/chart.tsx:51` | 0.1 d |
| FE-066 | 30 arbitrary Tailwind bracket values in feature code | Design system | `text-[11px]`, `h-[60vh]`, `max-w-[80%]`, `w-[11.5rem]`, a raw `oklch()` baked into a gradient | `(public)/page.tsx:45,49`, `chat-thread.tsx:109,121,131`, `listing-card.tsx:65,71`, `sort-select.tsx:24` | 1 d |
| FE-067 | No `Idempotency-Key` on `getAdminReports` | Contract oddity | The contract requires it on a **GET** — worth querying with the contract owner | `admin/api/ops-server.ts:108` | 0.1 d |
| FE-068 | `searchListingsPost` never used | Coverage | Only the GET variant is called; fine today, but the POST variant exists for filter sets too large for a query string | `search/api/search-listings.ts:38` | — |
| FE-069 | `assignRole`/`revokeRole` unused | Coverage | ADR-0006 added them; no admin role-management UI exists | — | 2 d |
| FE-070 | `listMyOrders`/`getOrder` unused | Coverage | No order-history screen (UI/UX §4.4 shows invoice status only) | — | 1.5 d |
| FE-071 | Product tier names untranslated | i18n | `Premium`/`Featured` left in English across ru/uz — plausibly intentional brand terms; needs a product decision | `i18n/messages/*.json` | 0.1 d |
| FE-072 | `boolean` control uses the field code as a DOM id | Correctness | Two sections sharing a field code would produce duplicate ids | `shared/forms/field-registry.tsx:121` | 0.1 d |

---

## Documentation Compliance Matrix

Legend: ✅ Fully Implemented · 🟡 Partially Implemented · 🔴 Missing · ⚠️ Implemented Incorrectly

### UI/UX Functional Specification

| § | Requirement | Status | Evidence |
|---|---|---|---|
| 1.1 | Public navigation (config-driven) | 🟡 | Header/footer exist; category links config-derived; menus hardcoded (CG-1) |
| 1.2 | Authenticated nav | ⚠️ | `dashboard-nav.tsx:33-42` hardcoded `ITEMS` array (FE-LAYOUT-01) |
| 1.3 | Business dashboard nav | 🟡 | Consolidated single route, no per-profile scope (FE-054) |
| 1.4–1.6 | Operator navs "shown per permission key" | 🔴 | Not expressible — CG-2 |
| 2.1 | Home | ✅ | Hero, category tiles, skeletons, promoted/recent grids |
| 2.2 | Search results | 🟡 | URL-driven, facets, sort, cursor, degraded, 429 ✅; no map, no radius, no list/grid toggle |
| 2.3 | Category page | 🟡 | Served via `/search?categoryId`; no `/c/[slug]`, no category header/breadcrumb |
| 2.4 | Listing detail | 🟡 | Gallery, attributes-by-label, phone reveal, chat, favorite, report ✅; **no map** |
| 2.5 | Business profile | ✅ | Header, portfolio display, listings, chat |
| 2.6 | Login | ✅ | Phone/email/Google, throttle UX, generic messages |
| 2.7 | Registration | ✅ | All three methods |
| 2.8 | Recovery | ✅ | Neutral no-enumeration message |
| 2.9–2.10 | Static pages `/p/[pageKey]` | 🔴 | CG-1 — no endpoint |
| 2.11–2.12 | 404 / 500 | ✅ | `not-found.tsx`, `error.tsx`, `global-error.tsx` |
| 3.1 | Dashboard overview | 🟡 | Widgets present; no per-widget retry |
| 3.2 | My Ads | ✅ | State tabs, lifecycle actions, 409 fallback |
| 3.3 | Favorites | ✅ | Optimistic toggle with rollback |
| 3.4 | Messages | 🟡 | WS + REST fallback ✅; no virtualization, no char limit, no read receipts |
| 3.5 | Notifications | 🟡 | List + read ✅; bell cache stale (FE-045) |
| 3.6 | Saved searches | 🔴 | Correctly omitted, but the required feature-flag path needs CG-1 |
| 3.7 | Profile | ✅ | With 409 handling |
| 3.8 | Settings | ✅ | Preferences, password, sessions, close-account with typed confirm |
| 4.1 | Company profile | 🟡 | Edit ✅; **no create** (FE-005); no portfolio management |
| 4.2 | Employees | 🟡 | `team-manager.tsx` exists; requires an existing profile |
| 4.3 | Advertisements (business) | 🟡 | Shared with My Ads |
| 4.4 | Subscription | 🟡 | Plan cards, entitlements, order→invoice ✅; no order history |
| 4.5 | Verification | 🟡 | Request flow ✅ |
| 4.6 | Statistics | 🟡 | Data fetched; charts minimal |
| 5.1 | Config lifecycle (list/history/compare/validate/publish/maker-checker/rollback/409/import-export) | ✅ | Genuinely strong — all implemented, publish gated on validation |
| 5.2 | Categories tree | 🔴 | FE-014 |
| 5.2 | Dynamic Forms builder | 🟡 | FE-015 — no preview, no validator/visibility authoring |
| 5.2 | Roles | 🟡 | Key picker ✅; no group UI, no flattened preview |
| 5.2 | Permission Groups | 🔴 | Not a contract entity type |
| 5.2 | Business Types | 🔴 | Not a contract entity type |
| 5.2 | Products, Slots, Search Config | ✅ | Working editors |
| 5.2 | Notification Templates | 🟡 | No token picker, no preview render |
| 5.2 | Platform Settings / Flags / SEO / Static Pages | 🔴 | FE-016 — raw JSON only |
| 6.1 | User management | ✅ | Filters, reason, confirm dialog |
| 6.2 | Verification queue | ⚠️ | FE-006 — documents never shown |
| 6.3/7 | Moderation queue | 🟡 | FE-023 — no detail, history, or claim |
| 6.4 | Advertisement management | 🔴 | FE-022 |
| 6.5 | Audit log | 🟡 | FE-049, not virtualized |
| 6.6 | Reports | 🟡 | FE-025 |
| 6.7 | Invoices | ⚠️ | FE-024 — no confirm dialog |
| 6.8 | Config deep-link | ✅ | |
| 8 | Creation wizard | 🟡 | All 5 steps ✅; no map picker, no type selector, preview shows codes |
| 9 | Search experience | 🟡 | URL-driven, debounced keyboard-navigable suggest, degraded, promoted-labelled ✅; no map/radius |
| 10 | Messaging | 🟡 | Text-only correctly per domain; gaps per FE-052 |
| 11 | Notification centre | 🟡 | Backend-rendered content respected ✅ |
| 12 | Dynamic form rendering | 🟡 | Engine excellent; FE-001, FE-004, FE-020, FE-038, FE-039 |
| 13 | Reusable components | 🟡 | ~60% of the canonical set exists (FE-034) |
| 14 | Responsive behaviour | 🟡 | Mobile-first grids and sticky bars present; no evidence of five-breakpoint testing |
| 15 | Accessibility WCAG 2.2 AA | ⚠️ | Good foundations (no div-onClick, all icon buttons labelled, single h1); undermined by FE-001, FE-028, FE-042 |
| 16 | Client validation | 🟡 | `onBlur`+submit ✅; server errors unmapped (FE-004) |
| 17 | Error handling | ⚠️ | Mapper dead (FE-003); most codes unhandled |
| 18 | Empty/loading/skeleton | ⚠️ | Empty good; loading and error largely absent (FE-011) |
| 19 | Micro-interactions | 🟡 | Present; no reduced-motion, one over-long duration |
| 20 | UX-AI-01…15 | 🟡 | 01 🟡 · 02 🟡(CG-2) · 03 🟡 · 04 🟡 · 05 ✅ · 06 🔴 · 07 ⚠️ · 08 ✅ · 09 ✅ · 10 ✅ · 11 🟡 · 12 ✅ · 13 ✅ · 14 🔴 · 15 ✅(exemplary) |

### Handbook rules

| Rule | Status | Note |
|---|---|---|
| FE-STRUCT-01 | ✅ | `shared/` is business-logic-free |
| FE-ROUTE-01 | ✅ | Real server-layout guards |
| FE-ROUTE-02 | 🔴 | CG-2 |
| FE-LAYOUT-01 | ⚠️ | Hardcoded nav arrays |
| FE-DS-01 / FE-DS-02 | 🔴 | Brand hardcoded; tokens largely absent |
| FE-STATE-01 | ✅ | No server data in Zustand/context |
| FE-STATE-02 / FE-SEARCH-01 | ✅ | Search state fully URL-driven |
| FE-SEARCH-02 | ✅ | Facets/sorts from config |
| FE-API-01 | 🟡 | One violation (FE-027) |
| FE-API-02 / FAIR-12 | ✅ | No JWT/refresh anywhere |
| FE-AUTH-01 | ✅ | Opaque server-owned session |
| FE-CFG-01 | 🔴 | CG-2 |
| FE-FORM-01 | ✅ | Exactly one engine, no per-category code |
| FE-FORM-02 | 🟡 | Client-only validation ✅; server errors unmapped |
| FE-ADV-01 | 🟡 | Correct on detail page; violated in wizard preview |
| FE-I18N-01 | 🟡 | Feature code clean; FE-028 exceptions |
| FE-I18N-02 | 🔴 | FE-018 |
| FE-PERF-01 | 🟡 | SSR ✅; no dynamic imports |
| FE-A11Y-01 | ⚠️ | FE-001 |
| FE-ERR-01 | ⚠️ | FE-003 |
| FE-TEST-01 | 🔴 | FE-056 |
| FAIR-01…16 | — | 01 🟡 · 02 ✅(no hardcoded map) · 03 ✅ · 04 🟡 · 05 🟡 · 06 🟡 · 07 ✅ · 08 🟡 · 09 ✅ · 10 ✅ · 11 🟡 · 12 ✅ · 13 ✅ · 14 ⚠️ · 15 ✅ · 16 ✅ |

### Design System rules

| Rule | Status | Note |
|---|---|---|
| DS-TOKEN-01/02/03 | 🔴 | FE-008 |
| DS-THEME-01 | 🟡 | Components are theme-agnostic; no provider (FE-029) |
| DS-CLASS-01 | 🟡 | Flat `shared/ui`; no `composite/` or `layout/` subfolders |
| DS-FORM-01/02 | ⚠️ | `FormField` used but association broken (FE-001) |
| DS-COMP-01/02 | ✅ | No forking, no nested modals/forms, no interactive-in-interactive |
| DS-A11Y-01 | ⚠️ | FE-001 |
| DS-MOTION-01 | 🔴 | No motion tokens; FE-057, FE-058 |
| DS-DOC-01 | 🔴 | FE-007 |
| DS-LAYOUT-01 | ✅ | Route-group layouts, no duplicated chrome |
| DS-AI-13 | ✅ | Correctly no VideoPlayer/PDFPreview/ReviewCard |

---

## Statistics

| Metric | Count |
|---|---|
| **Total findings** | **72** |
| Critical | 8 |
| High | 22 |
| Medium | 28 |
| Low | 14 |
| Contract gaps (need an ADR, not a frontend fix) | 5 (CG-1, CG-2, CG-3, moderation `claim`, 2 missing config entity types) |
| Missing features (🔴) | 42 doc requirements |
| Incomplete features (🟡) | 55 doc requirements |
| Implemented incorrectly (⚠️) | 10 doc requirements |
| Architecture / rule violations | 14 (FE-LAYOUT-01, FE-API-01, FE-I18N-02, FE-ERR-01, FE-A11Y-01, FE-TEST-01, FE-DS-01/02, DS-TOKEN-01/02/03, DS-MOTION-01, DS-DOC-01, FAIR-04/06) |
| Logic / correctness bugs | 9 (FE-001, FE-004, FE-020, FE-021, FE-030, FE-040, FE-045, FE-062, FE-072) |
| UI consistency issues | 8 |
| Performance issues | 6 (FE-031, FE-032, FE-033, plus bundle/eager-load effects) |
| Accessibility issues | 7 (FE-001, FE-028, FE-042, FE-043, FE-057, plus contrast-unverified, focus-order-unverified) |
| Security-relevant issues | 3 (FE-002 idempotency, FE-044 logout cache, CG-3 CSRF) |
| Code-quality issues | 12 (dead code, duplication, type escapes) |
| Documentation mismatches | 107 (🔴+🟡+⚠️ across all three frontend documents) |
| Unused declared dependencies | 2 (`@types/yandex-maps`, `@tanstack/react-virtual`) |
| Unused `shared/ui` components | 26 of 48 |

**Quality gates at `d66562e`:** `tsc --noEmit` clean · `eslint .` clean · `vitest run` 131/131 pass.
The application does not fail its own gates — the gates do not cover the mandates it misses.

---

## Prioritized Action Plan

Ordered so nothing depends on work scheduled after it. Effort is ideal engineer-days; the phases are
sequential but work *within* a phase is largely parallelizable.

### Phase 0 — Contract decisions (blocks Phases 2 and 4) · ~ADR effort only

These are architecture decisions, not code. Per AIR-19/FAIR-16 they must be resolved by humans through
governance before the dependent frontend work can start honestly.

1. **ADR: public configuration snapshot endpoint** (CG-1) — unblocks static pages, feature flags,
   config-driven nav, brand-from-config.
2. **ADR: `permissions: string[]` on `Account`** (CG-2) — unblocks FE-ROUTE-02 permission-key gating.
3. **ADR: CSRF scheme, or accept `SameSite=Lax` + same-origin proxy as the v1 control** (CG-3).
4. **ADR: moderation `claim`/assign operation** — unblocks FE-023's workflow half.
5. **ADR: `business-type` and `permission-group` config entity types** — unblocks two §5.2 editors.
6. **ADR: declared response schema per admin report** — unblocks FE-025's charts.
7. **Product decision:** where `listingType` is chosen (FE-030).

### Phase 1 — Critical blockers · ~19 d

Release-blocking correctness, integrity, and trust defects. No dependencies on Phase 0.

1. FE-001 form-field a11y association — **1.5 d** *(do first; FE-012's tests depend on it)*
2. FE-003 adopt the shared error mapper — **4 d** *(unblocks FE-004, FE-010, FE-026, FE-046)*
3. FE-002 `Idempotency-Key` on all writes — **2 d** *(pairs with FE-003's client wrapper)*
4. FE-004 map 422 `details[]` onto fields — **2 d** *(needs FE-003)*
5. FE-006 render verification documents — **1.5 d**
6. FE-021 wizard preview uses form labels — **0.5 d**
7. FE-024 invoice confirm dialog — **0.5 d**
8. FE-027 route Google callback through `shared/api` — **0.5 d**
9. FE-017 preserve return route on session expiry — **1.5 d**
10. FE-044 clear query cache on logout — **0.5 d**
11. FE-020 stop leaking `renderingHint` as text — **1 d**
12. FE-045 invalidate the notification bell — **0.5 d**
13. FE-062 / FE-072 correctness one-liners — **0.25 d**
14. FE-026 retry policy + `Retry-After` — **1.5 d** *(needs FE-003)*
15. FE-010 distinguish fetch failure from empty — **4 d** *(needs FE-003)*

### Phase 2 — Functional gaps · ~48 d

Documented features that do not exist. Items marked ⟨P0⟩ require a Phase 0 ADR.

1. FE-005 business-profile creation + portfolio management — **5 d** *(unblocks §4 entirely)*
2. FE-013 post-creation listing image management — **3 d**
3. FE-009 Maps: LocationPicker, detail map, search radius/map — **8 d**
4. FE-015 form-builder validators/visibility/hints **+ live preview** — **6 d** *(highest config leverage)*
5. FE-014 categories tree editor — **5 d**
6. FE-016 Platform Settings / flags / SEO / static pages editors — **5 d** ⟨P0-1⟩
7. FE-022 admin Advertisement Management — **3 d**
8. FE-023 moderation case detail + claim — **4 d** ⟨P0-4⟩
9. FE-011 per-segment `loading.tsx` / `error.tsx` + skeletons — **5 d** *(needs FE-010)*
10. Static pages `/p/[pageKey]` — **2 d** ⟨P0-1⟩
11. FE-030 listing type selector — **1.5 d** ⟨P0-7⟩
12. FE-025 report export (charts deferred) — **1 d**

### Phase 3 — UX improvements · ~16 d

1. FE-041 upload progress / cancel / retry — **2.5 d**
2. FE-038 / FE-039 DatePicker and RangeSlider wired into the registry — **3 d**
3. FE-052 chat char limit, virtualized history — **2 d**
4. FE-049 audit actor + date-range filters — **1 d**
5. FE-040 currency select — **0.5 d**
6. FE-042 / FE-043 touch targets and thumbnail alt text — **0.75 d**
7. FE-050 / FE-051 KPI links, config list columns — **0.75 d**
8. FE-019 hreflang + sitemap — **1.5 d**
9. FE-054 business `[profileId]` deep-link — **1.5 d**
10. FE-046 503 degraded handling — **1 d**
11. FE-057 / FE-058 reduced motion, duration ceiling — **0.75 d**

### Phase 4 — Refactoring (design system foundation) · ~24 d

Deliberately after Phases 1–3: FE-008 is broad and merge-conflict-prone, so it should land once
feature churn has settled.

1. FE-008 author the full token layer (z, motion, elevation, typography roles, spacing, status, brand) — **8 d**
2. FE-007 Storybook + a11y addon + Foundations token page + QG-10 gate — **6 d**
3. FE-034 missing primitives (Icon, Heading, Spinner, PageContainer, ConfirmDialog, Chip, StatCard…) — **6 d**
4. FE-018 codemod physical → logical CSS properties + lint rule — **3 d**
5. FE-029 ThemeProvider; brand from config — **2 d** ⟨P0-1⟩
6. FE-035 / FE-036 / FE-037 migrate duplicated markup onto primitives — **3 d**
7. FE-047 remove `as never` casts — **1.5 d**

### Phase 5 — Technical debt cleanup · ~19 d

1. FE-012 component + integration + journey E2E suite — **10 d** *(after FE-001 and Phase 4 primitives)*
2. FE-056 generate MSW handlers from OpenAPI — **1.5 d**
3. FE-031 virtualization on the four long lists — **3 d**
4. FE-032 / FE-033 code splitting + list memoization — **2 d**
5. FE-055 whitelist drift tests — **1 d**
6. FE-059 / FE-060 / FE-061 remove dead code and unused deps — **1.5 d**
7. FE-063 / FE-064 / FE-066 font Cyrillic coverage, primitive strings, arbitrary values — **2 d**

**Total ≈ 126 engineer-days** (~25 weeks for one engineer; ~7–8 weeks for a team of four given the
parallelism within phases), excluding Phase 0 governance time.

---

## Ambiguities and Limits of This Audit

Stated explicitly rather than guessed, per the brief.

**Ambiguous requirements** — flagged, not resolved:
1. **`listingType` placement** (FE-030). No frontend document says where the user chooses it, or whether
   leaf-category selection should imply it. Product decision.
2. **UI/UX §2.3 category page.** The spec offers `/search?categoryId=…` *or* `/c/[slug]` as alternatives.
   The implementation takes the first, so a dedicated category header and breadcrumb are absent. Whether
   that satisfies §2.3 depends on reading; flagged rather than scored as outright missing.
3. **UI/UX §3.6 saved searches.** Omission is permitted *only* behind a feature flag. The feature is
   omitted and no flag exists (because flags need CG-1), so compliance is technically incomplete via a
   dependency, not by choice.
4. **"Charts + export" for reports** (FE-025). The code's reason for not charting an undeclared schema is
   sound; whether the spec intends charts to be blocked on an ADR or to be built speculatively is unclear.
5. **Product tier names** `Premium`/`Featured` untranslated (FE-071) — brand terms or a translation gap?

**Not verified — do not treat as passing:**
- **Runtime and visual behaviour.** No dev server, browser, or backend was run. Responsive behaviour
  across the five mandated breakpoints (UI/UX §14), colour-contrast ratios, actual focus order, real
  screen-reader output, and CLS/bundle metrics are **unassessed**. The responsive and contrast rows in
  the matrix reflect *code structure only*.
- **Backend `Problem.code` values in practice.** Error-classification logic was read, not exercised.
- **Axe coverage breadth.** One Playwright axe check runs against the home page only; no page-level axe
  results exist for any other route.
- **Whether `slider.tsx` supports dual-thumb range mode** — affects FE-039's effort estimate only.
- **Sitemap/hreflang outside `src/`** — only `src/` and `public/` were searched.

**Relationship to earlier passes.** This pass is frontend-scoped and does not supersede
`2026-07-28-incomplete/`, `2026-07-27-verification/`, `2026-07-24-audit/`, or `2026-07-24-acceptance/`.
Where it disagrees with them it says so here rather than amending them, per this folder's convention.
Two carry-forward lessons from the index proved true again: a green gate is not evidence a requirement is
met (all gates pass at `d66562e` while 8 Critical findings stand), and each pass sees only what its method
can see — this one is static, so every runtime claim above is explicitly withheld.
