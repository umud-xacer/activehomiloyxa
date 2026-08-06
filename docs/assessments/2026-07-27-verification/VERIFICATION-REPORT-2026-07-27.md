# Active Home v1 — Manual Functional Verification Report

**Date:** 2026-07-27
**Baseline:** `origin/main` @ `e1ec08b` (merge of P-21, "§5.2 structured config editors")
**Method:** behavioural end-to-end testing of the running system — real HTTP, real WSS, real
browser. No claim below rests on reading source; code was read only to explain an observed
defect.
**Companion files:** `DEFECT-REGISTER-2026-07-27.md`,
`FUNCTIONAL-COVERAGE-MATRIX-2026-07-27.md`, `HUMAN-TEST-SCRIPTS-2026-07-27.md`, `evidence/`.

---

## 1. Executive summary

Active Home v1 is a genuinely substantial and, in its core commercial path, a genuinely working
product. The money path — order → invoice → operator-confirmed offline payment → entitlement →
promotion marker → labelled and capped placement in search — was exercised end to end and
behaved exactly as documented, including its refusals (a buyer cannot confirm their own payment;
no entitlement exists before confirmation; a 2-listing plan refuses the third listing with 409).
The invariants that carry the most business risk hold under adversarial testing: I-04, I-05,
I-06, I-07, I-08, I-13, I-14, I-16, I-18, I-19 and I-24 were each observed behaving correctly,
several of them through the *refusal* rather than the happy path. Cross-script Uzbek search — the
single most distinctive requirement in the SRS — works in both directions including the `oʻ`/`gʻ`
apostrophe forms, from the API and from the UI. Configuration is real: publishing a new category
through the operator API made it appear in the running API and in the browser with no redeploy,
which is NFR-MAINT-001 demonstrated rather than asserted. The frontend renders all four locales
with genuinely distinct, correctly-scripted translations, and returned **zero** WCAG 2.2 AA
violations of any severity across seven screens.

Against that, three defects are blocking and they are not cosmetic. The product **cannot be
installed**: Alembic migrations fail on all thirteen modules against a fresh database, and there
is no bootstrap path to the first administrator — both only work here because this verification
did them by hand. The dynamic form engine, which is the architectural centrepiece, **cannot use
select fields at all**: the `option_membership` validator rejects values that the very same API
serves as the field's configured options. And every write endpoint commits *after* the response
is sent, so read-after-write is violated globally — 8 of 10 immediate re-reads returned the
previous value. Below that sit twelve more MAJOR findings, of which the sharpest are a radius
search that ignores the radius entirely, listing views that are never recorded (the headline
metric for owners and for pricing), and an outbox that abandons events permanently after a
transient dependency outage. The honest summary: the domain modelling and the commercial
mechanics are in good shape; the operational envelope around them — install, error handling,
durability, and several "last mile" wirings — is not yet shippable.

### Headline table

Counts are of defects **attributed to that area**; platform-wide defects are counted once, under
the cross-cutting rows.

| Area | Rating | BLOCKER | MAJOR | MINOR |
|---|---|---|---|---|
| M-01 Identity & Access | PASS-WITH-DEFECTS | 0 | 2 (DEF-005, DEF-014) | 1 (DEF-016) |
| M-02 Business Profiles & Verification | PASS-WITH-DEFECTS | 0 | 1 (DEF-007) | 0 |
| M-03 Catalog & Listings | FAIL | 1 (DEF-002) | 2 (DEF-008, DEF-010) | 0 |
| M-04 Configuration & Metadata | PASS-WITH-DEFECTS | 0 | 1 (DEF-011) | 3 (DEF-017/018/019) |
| M-05 Search & Discovery | PASS-WITH-DEFECTS | 0 | 2 (DEF-006, DEF-013) | 0 |
| M-06 Media | PASS | 0 | 0 | 0 |
| M-07 Messaging & Contact | PASS | 0 | 0 | 0 |
| M-08 Billing & Entitlements | PASS | 0 | 0 | 0 |
| M-09 Moderation | PASS | 0 | 0 | 0 |
| M-10 Notifications | PASS-WITH-DEFECTS | 0 | 0 | 0 (2 NEEDS-HUMAN) |
| M-11 Ads / Banners | NOT-TESTED (partial) | 0 | 0 | 0 |
| M-12 Administration | PASS-WITH-DEFECTS | 0 | 1 (DEF-015) | 0 |
| M-13 Analytics & Audit | FAIL | 0 | 2 (DEF-008, DEF-009) | 1 (DEF-020) |
| Frontend — public & authenticated screens | PASS | 0 | 0 | 0 |
| Frontend — localisation (4 locales, dual script) | PASS | 0 | 0 | 0 |
| Frontend — accessibility (WCAG 2.2 AA) | PASS | 0 | 0 | 0 |
| Frontend — operator surfaces | PASS-WITH-DEFECTS | 0 | 1 (DEF-015, surfaced) | 0 |
| Cross-cutting — install & bring-up | FAIL | 1 (DEF-001) | 1 (DEF-014) | 1 (DEF-021) |
| Cross-cutting — platform/API behaviour | FAIL | 1 (DEF-003) | 2 (DEF-004, DEF-012) | 0 |
| Cross-cutting — degradation & config-without-redeploy | PASS | 0 | 0 | 0 |
| Scope discipline | PASS | 0 | 0 | 0 |

**Totals: 3 BLOCKER, 12 MAJOR, 6 MINOR.** 245 doc-cited behavioural checks executed;
223 passed. (A handful of recorded "failures" are noted below where the *expectation* was mine
and the system was right — those are classified WORKS in the coverage matrix, not defects.)

---

## 2. Environment & method

### What was brought up

The verification ran against an **isolated stack**, deliberately separated from the developer's
own running environment so that nothing here could corrupt their data:

| Component | How | Note |
|---|---|---|
| PostgreSQL 17 | existing container, **separate database** `active_home_verify` | non-destructive |
| Redis 7.4 | **dedicated** container `ahv-redis` on :6380 | avoids sharing session / config-snapshot keys |
| OpenSearch 2.19 | **dedicated** container `ahv-opensearch` on :9201 | the index name `listing_search` is a hardcoded constant, so a separate instance was the only way to isolate |
| MinIO | existing container, **separate bucket** `active-home-media-verify` | non-destructive |
| ClamAV, Mailpit | existing containers (stateless / mail sink) | shared |
| API | `uvicorn main:app` on :8100 | host process |
| Realtime gateway | `uvicorn realtime_main:app` on :8101 | host process |
| Workers | the nine `*_worker.py` processes, started by hand | not in the compose file |
| Frontend | `next build && next start` on :3100 | see the dev-server note below |

**Deviation from the Infrastructure doc, recorded here as a bring-up finding:**
`deployment/compose/docker-compose.yml` contains **no `api`, `web` or `worker` containers** — the
file's own comments admit this ("`api`/`web`/`worker` containers for every other module remain
out of scope"), and `nginx` still serves only a static health response for those upstreams, with
its WSS reverse-proxy block left as a TODO. The Infrastructure & Deployment doc's container table
specifies all of them. So `docker compose up` does **not** bring up the product; only the
datastores, the realtime gateway and nginx. Everything else had to be started as host processes.

### Bring-up sequence actually used

1. `DROP` / `CREATE DATABASE active_home_verify`.
2. **Create the 13 module schemas by hand** — required because of DEF-001.
3. `alembic upgrade head` for each of the 13 modules (13/13 succeed once the schemas exist).
4. `python -m configuration.infrastructure.seed` — creates the `super-admin` and `administrator`
   role definitions and platform settings. It populates **3 of the 8** configuration entities;
   the rest must be authored.
5. **Insert two role assignments directly into `identity.role_assignment`** — required because of
   DEF-014, and *two* are required because maker–checker forbids self-approval.
6. Author the remaining configuration **through the real admin API** (`/admin/config/*`): 2 form
   definitions, 3 categories, all 6 product types, 1 placement slot, 1 search configuration,
   2 notification templates, 3 operator roles. This doubled as the FR-CFG-001…005 verification.
7. `GET /health` → `200`; `GET /ready` → `{"postgres":true,"redis":true}`. Confirmed green before
   testing. (`/ready` correctly returns **503** when a dependency is down — verified
   unintentionally when the Postgres container stopped mid-run.)

### Seed data

All synthetic, no real PII. All eight business-profile types; users in every operator role
(super-admin ×2, moderator, verification reviewer, billing ops) plus business and individual
users; listings across multiple categories; content authored in **uz-Latn, uz-Cyrl, ru and en**,
including deliberate `oʻ`/`gʻ`/apostrophe forms (`Samarqandda gʻishtli uy`,
`Oʻzbekiston boʻylab yetkazib berish` and their Cyrillic counterparts) for cross-script testing.

### Tooling

* **API/WSS:** a purpose-built Python harness (`httpx` + `websockets`) recording every check with
  its document citation, expected result, observed result and status code, emitted to
  `evidence/res_*.json`. Ten batteries: identity, catalog, billing, profiles, end-to-end money
  path, search, promotion, messaging, operations, and the configuration authoring pass.
* **UI:** Playwright (Chromium) driving the real browser against the real API.
* **Accessibility:** `@axe-core/playwright` with tags `wcag2a, wcag2aa, wcag21a, wcag21aa,
  wcag22aa`.
* **Contract conformance:** the live `/openapi.json` diffed operation-by-operation against
  `contracts/openapi.yaml`.

### Two environment artefacts, explicitly NOT reported as product defects

Being clear about these matters, because both initially looked like severe defects:

1. **The Next.js *dev* server did not hydrate.** Under `next dev` (Turbopack) no client-side
   interactivity worked at all — tabs, dropdowns and keyboard navigation were dead, and the HMR
   websocket failed with `ERR_INVALID_HTTP_RESPONSE`. That would have been a frontend BLOCKER
   ("nobody can register or log in"). A production build was then tested and **everything works**:
   tabs switch, dropdowns open, forms submit, registration and login succeed. The failure is a
   dev-server artefact in this environment. All frontend results in §4 come from the production
   build.
2. **OpenSearch entered a read-only block.** The host disk was at 96 %, tripping OpenSearch's
   flood-stage watermark. That is this machine, not the product. What *is* reported (DEF-012) is
   the product's *response* to the resulting outage: events went `DEAD` and were never retried.

Similarly, an early realtime WSS `500` and a batch of `too many clients` errors were traced to
PostgreSQL `max_connections` exhaustion (DEF-021, an infra sizing finding) rather than to the
messaging module, which passes cleanly once connections are available.

---

## 3. Backend verification

### 3.1 Identity & Access (M-01) — PASS-WITH-DEFECTS · 21/26

**WORKS.** FR-AUTH-004: valid credentials return `200` with a session; a wrong password and an
unknown account both return `401 AUTHENTICATION_INVALID` in a well-formed Problem envelope
(`type`, `title`, `status`, `code`, `traceId`, camelCase) — identically, so the endpoint is
enumeration-safe. FR-AUTH-005: `/me` and `/me/sessions` succeed, `logout` returns `204`, and the
session is dead (`401`) immediately afterwards. The session token is an **opaque server-side
handle, not a JWT** (verified: no `ey` prefix, not three dot-separated segments), and the cookie
is `HttpOnly; SameSite=lax; Secure` — matching the Baseline decision. FR-AUTH-006 recovery
returns `202` for both known and unknown addresses. FR-USER-003 privacy settings and FR-USER-005
account closure (`204`, then `401` — the account really is unusable) both behave.

**Default deny (NFR-SEC-002) holds.** Anonymous callers get `401` on `/me` and `/admin/*`; an
authenticated but unprivileged user gets `403` on `/admin/users`, `/admin/config/*` and
`/admin/audit-log`. Per-profile scoping was verified separately (§3.12).

**FR-AUTH-001 / FR-NOTIF-003 (phone OTP)** was verified *to the provider boundary*: the Eskiz
adapter genuinely issued a request to `https://notify.eskiz.uz/api/auth/login` and was rejected
because the credentials are placeholders. The request is correctly formed and dispatched; real
delivery is NEEDS-HUMAN. The failure mapping is DEF-016.

**Defects:** DEF-005 (email confirmation inert — accounts are `ACTIVE` at creation, the mail
carries a bare token, and no endpoint anywhere redeems it), DEF-003 (read-after-write, whose
clearest symptom lives here: `PATCH /me` returns the new value while the next `GET /me` returns
the old one, 8/10 times), DEF-014 (no first-administrator path), DEF-016.

### 3.2 Configuration & Metadata (M-04) — PASS-WITH-DEFECTS

All eight configuration entity types are present, hyphenated as `category, form-definition,
product-definition, placement-slot, role-definition, search-configuration, notification-template,
platform-settings`. Fifteen entities were authored and published through the real API.

**WORKS.** The **whitelist gate (I-16 / BRULE-08) genuinely refuses novel behaviour**: publishing
a role with permission key `moderation:queue:view` was rejected `WHITELIST_VIOLATION`, as was a
placement slot with page zone `home_hero`; both had to be replaced with catalogue members
(`moderation:case:review`, `HOMEPAGE_HERO`). The pre-activation validation gate reports structured
errors (`{"valid":false,"errors":[{"path":"/form_definition_id","rule":"MISSING_DEPENDENCY",…}]}`).
**Maker–checker is correctly enforced**: the author's own approval is refused
`403 "The approver must be a different principal from the author"`. The Head+Version model
behaves — versions are immutable and forward-only, and a second version can be authored on an
existing head.

**Defects:** DEF-011 (incomplete draft → 500), DEF-017 (snake_case definitions), DEF-018 (publish
must be called twice, no approve operation), DEF-019 (body optionality).

### 3.3 Catalog & Listings (M-03) — FAIL · 21/24

**WORKS.** The lifecycle behaves precisely. Create → the draft is invisible to anonymous callers
(`404`) but retrievable by its owner → publish → publicly retrievable → edit → state becomes
`EDITED`. An illegal transition is refused `409 ILLEGAL_STATE_TRANSITION`, and every transition is
recorded (3 rows in `catalog.listing_transition` for that sequence) — **I-05 and I-06 verified**.
Ownership is enforced server-side: a non-owner attempting to edit or drive the lifecycle gets
`403 "Caller does not own this listing"`. **I-07 verified** — the listing stores
`form_definition_version_id`, binding the immutable form version it was validated against.
FR-USER-004 favorites add/list/remove all work and emit `FAVORITE_ADDED`. FR-ADV-009 duplicate
detection raises moderation cases. **I-08 verified** (§3.5).

Dynamic-form validation works for the field types that function: a missing required field, an
out-of-range number (`numeric_range` max 20 rejected 999) and a bad option are each rejected
`422` with field-level paths.

**Defects:** DEF-002 (BLOCKER — `option_membership` rejects legitimately configured options,
making every select field unusable), DEF-010 (unknown attributes silently accepted), DEF-008
(no view metric).

### 3.4 Search & Discovery (M-05) — PASS-WITH-DEFECTS · 21/23

**Cross-script Uzbek (FR-SRCH-004 / DEC-19) works, and it is the strongest single result here.**
Content authored in Latin is found by a Cyrillic query and vice versa, with identical result sets
in both directions; the `oʻ`/`gʻ` apostrophe forms match their Cyrillic counterparts
(`gʻishtli` → 4 hits, `ғиштли` → 4 hits; `oʻzbekiston` → 2, `ўзбекистон` → 2). The index stores
explicit `title_normalized_latin` / `title_normalized_cyrillic` fields. The same behaviour was
then confirmed *through the browser* (§4).

**WORKS.** Full-text search returns relevant hits. Facets are served from the published
search-configuration — the configured `rooms` and `condition` facets are exactly the ones offered,
with populated buckets. Sorting works for `RELEVANCE`, `PRICE_ASC`, `PRICE_DESC`. Suggestions
return. **Paid ranking (FR-SRCH-005 / BRULE-10) works end to end**: purchasing a `PREMIUM`
promotion applied `promotion_kind='PREMIUM'` in the catalog (PromotionApplicationPolicy reacting
to `EntitlementActivated`), and the listing then appeared in search labelled
`"promoted": {"kind": "PREMIUM"}`, within the configured page cap of 3.

**Degradation (documented path) works.** With OpenSearch stopped, `GET /search` still returned 16
results via the PostgreSQL fallback and correctly set `"degraded": true`; listing browsing was
unaffected; on recovery the flag returned to `false` and results came from the index again.

**Defects:** DEF-006 (MAJOR — the radius parameter is accepted and entirely ignored; Samarkand
listings are returned at `radiusKm=1` from Tashkent), DEF-013 (`NEWEST` is publishable but
unusable).

### 3.5 Billing & Entitlements (M-08) — PASS · 30/30 on the end-to-end battery

This module verified cleanly and adversarially. All six ProductTypes are presented with their
configured pricing (FR-SUBS-001). Creating an order freezes a `ProductSnapshot` and issues a
numbered invoice (`INV-000003`). **I-14 verified three ways**: no entitlement exists before
confirmation; the buyer attempting to confirm their own invoice is refused
`403 PERMISSION_DENIED`; and only after the *operator* confirms does the invoice become `PAID`
and the entitlement activate. **FR-BILL-004 verified**: a scan of all 109 live operations found
no online-payment path of any kind. **I-08 / FR-ADV-008 verified**: with a `max_active_listings=2`
plan active, exactly two listings were created and the third refused `409`.

### 3.6 Media (M-06) — PASS

The presigned-upload pipeline works end to end: `POST /media/uploads` issues a MinIO URL and the
client `PUT`s the bytes directly (`200`). **FR-MEDIA-002 / BRULE-11 verified** — `video/mp4` and
`application/pdf` are both refused `422`; an image over 10 MB is refused
`UNSUPPORTED_MEDIA_TYPE`. **I-04 / FR-ADV-002 verified precisely**: ten images attached
successfully, the **eleventh refused** `422`.

Not verified: FR-MEDIA-003 (EXIF/GPS stripping) and FR-MEDIA-004 (malware quarantine) — §8.

### 3.7 Messaging & Contact (M-07) — PASS · 16/17

**WORKS.** A conversation is created for a listing and emits `CHAT_INITIATED`. Messages persist
and are readable by the other participant. **Realtime delivery over WSS verified**: a participant
connected to `ws://…/ws/messaging` received the pushed frame
(`{"conversationId":…,"messageId":…,"authorUserId":…,"body":"Realtime sinov …","sentAt":…}`)
within the timeout. An unauthenticated WSS upgrade is refused. **I-19 verified twice** — a third
party can neither read (`403 "Caller is not a participant of this conversation"`) nor post into a
two-party conversation; and a blocked user's message is refused
`403 "The recipient has blocked the sender"`. Blocks are listable and removable. **I-18 / BRULE-13
verified in both directions**: with the owner's setting `NEVER` the response is
`{"allowed": false, "phoneNumber": null}`; with `ON_REQUEST` it is
`{"allowed": true, "phoneNumber": "+998901112233"}`, and `PHONE_REVEALED` is recorded.
FR-MSG-005 reports enter the moderation queue.

*(The one recorded "failure" was my expectation of a 4xx for the blocked reveal; the contract's
`PhoneRevealResponse` explicitly specifies `allowed: false` for that case, so the system is right.
Classified WORKS.)*

### 3.8 Moderation (M-09) — PASS

**WORKS.** Reports enter the queue; the queue lists and is refused to ordinary users (`403`). The
**closed action-verb set is enforced** — `DELETE_EVERYTHING` is rejected `422`. **I-24 verified**,
and this is the subtlest correct behaviour observed: a moderation `SUSPEND` did not mutate the
listing directly — the catalog module recorded **its own** transition row (2 → 3) and moved the
listing to `SUSPENDED`, after which it became invisible to anonymous callers (I-06). **FR-MOD-004
verified with its compensation**: suspending an account made the account unusable (`401`) *and*
hid that account's listings (`404` to anonymous callers).

### 3.9 Notifications (M-10) — PASS-WITH-DEFECTS

Notifications are produced and persisted (50 rows), templated from published
`notification-template` configuration, and preferences are manageable via `PUT /me/preferences`.
Email dispatch was verified against a local Mailpit sink — messages arrive with correct subjects
and recipients. Web-push and production SMTP are NEEDS-HUMAN.

### 3.10 Ads / Banners (M-11) — NOT-TESTED (partial)

`GET /admin/campaigns` returns `200`; `GET /banners/serve?slotKey=home-hero` returns `204` (no
active campaign). A `BANNER_PLACEMENT` product and a `HOMEPAGE_HERO` placement slot were both
authored and published successfully. Campaign creation, scheduling, targeting and
impression/click metric emission (FR-BANNER-002/003/004/005) were **not exercised** — §8.

### 3.11 Analytics & Audit (M-13) — FAIL

**WORKS.** The **closed vocabulary is respected in the direction that matters**: every metric
observed (`CHAT_INITIATED`, `FAVORITE_ADDED`, `PHONE_REVEALED`) is inside the documented eight,
and nothing outside it was ever written — BRULE-20's ClosedVocabularyPolicy holds. **Append-only
immutability holds**: an `UPDATE` against `analytics.audit_entry` affected no rows. FR-AUDIT-001/002
work — 20+ audit entries recorded for administrative actions, viewable and filterable by an
authorised admin and refused to everyone else.

**Defects:** DEF-008 (`ListingViewed` never emitted — only 3 of 8 metrics are actually captured),
DEF-009 (owner statistics return `null` counts), DEF-020 (reports enumerate 6 of 8).

### 3.12 Administration (M-12) — PASS-WITH-DEFECTS

**WORKS.** `/admin` is **not a privilege bypass** — anonymous access `401`, unprivileged
authenticated access `403`. FR-ADMIN-006 works and is correctly scoped: assigning the `moderator`
role took effect (the user could then open the moderation queue), and **I-16 was verified in the
negative** — that same moderator was refused `403` on `/admin/billing/invoices`. A role grants
exactly its configured permissions and cannot widen access. FR-ADMIN-001/002/003/005 surfaces all
respond.

**Defect:** DEF-015 (`/admin/dashboard` returns every field `null`).

### 3.13 API conformance

The live surface was diffed against the frozen contract operation by operation:
**107 of 110 contract operations are served, with 0 undocumented extras.** The three missing are
the business-profile team operations (DEF-007). Error responses use the documented Problem
envelope with stable codes (`VALIDATION_FAILED`, `AUTHENTICATION_INVALID`, `PERMISSION_DENIED`,
`RESOURCE_NOT_FOUND`, `DUPLICATE_KEY`, `ILLEGAL_STATE_TRANSITION`, `DEPENDENCY_DEGRADED`,
`UNSUPPORTED_MEDIA_TYPE`, `WRONG_ACTING_PROFILE`), camelCase wire fields, and a `traceId`
correlating to the `x-request-id` header. This is a strong result and reflects real discipline.

---

## 4. Frontend verification

Driven with Playwright against the production build and the real API. **26/26** authenticated-flow
checks and **39/43** public checks passed (the four are known selector limitations of the public
script, all covered properly by the authenticated run).

### Screens and flows

Public — home, search, login, register, listing detail — render in all four locales. Registration
through the UI succeeds (Email tab → email/password/name fields → submit), login succeeds and
lands the user in the authenticated area, and the browser holds an `ah_session` cookie that is
**HttpOnly** (confirming server-side session auth reaches the browser correctly, with no token
exposed to JavaScript).

Authenticated — dashboard, my listings, favorites, messages, notifications, profile, settings,
business, and the listing wizard all render their own content for a logged-in user (none bounce
to login, none error). The **dynamic form engine renders from configuration** in the wizard.

Operator — `/admin`, `/admin/users`, `/admin/moderation`, `/admin/verification`,
`/admin/invoices`, `/admin/audit`, `/admin/reports`, and the Product-Owner configuration portal
`/admin/config` and `/admin/config/category` all render for a super-admin. `/admin/users`
(8 194 chars) and `/admin/audit` (5 036 chars) carry real data; `/admin` itself is nearly empty
(239 chars), which is DEF-015 surfacing in the UI.

**Authorization is server-enforced, not frontend-enforced** — a normal user navigating to
`/en/admin` is redirected to login and never sees operator data.

### Localisation — PASS

All four locales render **genuinely distinct** text (4/4 distinct renderings, so nothing is
silently falling back), with correct scripts:

| Locale | Rendered |
|---|---|
| uz-Latn | `Qidiruv … Kirish … Uy-joy va qurilish — bir joyda` (Latin, no Cyrillic present) |
| uz-Cyrl | `Қидирув … Кириш … Уй-жой ва қурилиш — бир жойда` (Cyrillic) |
| ru | `Поиск … Войти … Жильё и строительство — в одном месте` |
| en | `Search … Log in … Housing and construction — in one place` |

DEC-19 is honoured structurally: dual-script Uzbek is two distinct locales (`uz-Latn`,
`uz-Cyrl`), not a script toggle. **Cross-script search from the UI works** — a Cyrillic query
`квартира` on the uz-Cyrl site returned `5 та натижа` over Latin-authored content.
Configuration-driven content reaches the UI: all five published categories, including two created
live during this run, appear on the home page and in the Categories menu.

### Accessibility — PASS

axe-core with `wcag2a, wcag2aa, wcag21a, wcag21aa, wcag22aa` on seven screens (home, search,
login, register, home-uz-Latn, dashboard, listing wizard):
**zero violations at any impact level on every screen.** Per-screen JSON in
`evidence/axe-*.json`. This substantially exceeds the "no serious/critical" bar and is a genuinely
good result for NFR-ACC-001.

### Responsiveness — PASS

At a 375 px viewport, `scrollWidth == clientWidth == 375` — no horizontal overflow on the home
page. Screenshot: `evidence/home-mobile-375.png`.

### Runtime cleanliness

On the production build: **zero console errors** and no failed requests other than normal Next.js
RSC prefetch aborts. 36 direct browser→API calls were observed, confirming the UI consumes the
real backend rather than fixtures.

---

## 5. Cross-cutting verification

**Configuration without redeploy (NFR-MAINT-001) — PASS, demonstrated twice.** A new category was
authored and published through `/admin/config/category` against the *already-running* API process.
`GET /categories` went from 3 to 4 entries with no restart, and the new category then appeared in
the browser's home page and Categories menu. This is the product's central configurability claim
and it holds.

**Degradation — PASS.** OpenSearch stopped → `GET /search` still returned results from the
PostgreSQL fallback and set `"degraded": true`; listing browsing was unaffected; recovery cleared
the flag. Media processing lag does not block publishing.

**Eventual consistency — behaves, with measured windows.** Business-profile ownership propagates
`profiles → identity` via the outbox in ~2 s (a `switch-profile` immediately after creating a
profile returns `403` until it lands — architecturally correct, since no module reads another's
tables). Messaging maintains its own `listing_owner_projection` and returns a clear
`503 "This listing's owner has not yet been observed"` until it catches up — a well-designed
degradation message. Promotion markers and search reindexing land within ~10 s.

**Durability — FAIL (DEF-012).** The outbox does not survive a sustained consumer outage: events
reach `DEAD` and are never retried, silently and permanently desynchronising the search read model
from the catalog. Manual SQL was required to replay them.

**Authorization by role — PASS.** Verified across five actor types. Default deny holds; roles
grant exactly their configured permissions (moderator can open the moderation queue, is refused
billing); `/admin` is not a bypass; maker–checker forbids self-approval; a buyer cannot confirm
their own payment; non-owners cannot mutate listings or profiles; third parties cannot enter
conversations.

---

## 6. Scope-discipline findings

**No out-of-scope or v2 functionality was found.** Checked explicitly:

| Excluded item | Result |
|---|---|
| Reviews / ratings (DEC-03) | Absent — no operation, no schema, no UI |
| Online payment gateway (DEC-02, BRULE-15) | Absent — all 109 live operations scanned; offline confirmation only |
| Video / PDF media (DEC-10, BRULE-11) | Absent **and actively refused** (`422` on `video/mp4`, `application/pdf`) |
| Analytics dashboard / recommendations | Absent — only the fixed metric set and basic reports |
| Saved-search digests | Absent |
| CMS | Absent |
| Kubernetes | Absent — compose only |
| Multi-country / multi-currency | Absent — `UZS` throughout |

The exclusions are not merely unimplemented; several are enforced at runtime, which is the
stronger form of scope discipline.

---

## 7. Defect register summary

3 BLOCKER, 12 MAJOR, 6 MINOR. Full detail in `DEFECT-REGISTER-2026-07-27.md`.

* **BLOCKER:** DEF-001 (migrations fail on a fresh database), DEF-002 (`option_membership`
  rejects configured options — select fields unusable), DEF-003 (commit after response —
  read-after-write violated globally).
* **MAJOR:** DEF-004 (keep-alive destroyed on every mapped error), DEF-005 (email confirmation
  inert), DEF-006 (radius ignored), DEF-007 (team operations missing), DEF-008 (`ListingViewed`
  never recorded), DEF-009 (owner statistics null), DEF-010 (unknown attributes accepted),
  DEF-011 (incomplete draft → 500), DEF-012 (outbox events abandoned), DEF-013 (sort vocabulary
  mismatch), DEF-014 (no first-admin path), DEF-015 (admin dashboard all null).
* **MINOR:** DEF-016 … DEF-021.

---

## 8. Coverage summary

**Tested:** 77 of the 89 functional requirements in SRS §5 were exercised behaviourally
(**87 %**). (The SRS also carries 19 further `FR-`prefixed ids in §6 — `FR-SEC-*`, `FR-PERF-*`,
`FR-SCALE-*` and similar — which are non-functional mirrors and are out of scope for a
functional verification; they are listed in the matrix as NOT-TESTED.) Also exercised:
14 of the 24 invariants, the closed metric and action vocabularies, the Problem envelope, all four
locales, WCAG 2.2 AA on seven screens, two documented degradation paths, and the no-redeploy
configuration path. 245 doc-cited checks executed; 223 passed.

**Not tested, with reasons:**

| Area | Requirements | Why |
|---|---|---|
| Banner campaign lifecycle | FR-BANNER-002/003/004/005 | Campaign creation needs a `BANNER_SLOT_BOOKING` entitlement chain not reached before the run ended. The slot and product configuration published successfully and the serve endpoint responds. DEC-23 names banner ad-serving the *first contingency descope candidate*, so this was the deliberate deprioritisation. **Residual risk: real.** |
| EXIF/GPS stripping | FR-MEDIA-003 | Requires uploading an image with known GPS EXIF and re-reading the stored object; the media worker pipeline was not driven to completion |
| Malware quarantine | FR-MEDIA-004 | Needs an EICAR test file through the full ClamAV path |
| Listing expiry & renewal | FR-ADV-007 | Requires time travel or a short configurable expiry; not exercised |
| Badge expiry / re-verification | FR-PROF-007 | Same — badge validity is 30 days |
| Entitlement expiry | FR-SUBS-004 | Same |
| Config rollback & import/export | Config Framework §2.6 | Operations exist and are served; not exercised behaviourally |
| Yandex Maps display | FR-MAP-002 | Needs a real API key → NEEDS-HUMAN |
| Real OTP / Google / web-push / production SMTP | FR-AUTH-001*, FR-AUTH-003, FR-NOTIF-002, FR-NOTIF-001* | External credentials → NEEDS-HUMAN, scripts provided |
| NFR performance/scale targets | NFR-PERF-*, NFR-SCALE-* | Load testing is out of scope for a functional verification |

*Verified to the provider boundary.

---

## 9. Risk assessment & recommended remediation order

**Do not ship until group 1 is closed.**

**Group 1 — the product cannot be installed or trusted to store data (BLOCKER).**
1. **DEF-001** — make migrations work on a fresh database (create schemas in `env_support.py`
   before `context.configure`, or ship `scripts/db-migrate.sh`). Add a CI job that migrates a
   genuinely empty database, so the test-conftest masking cannot recur. *(new work)*
2. **DEF-014** — provide a first-administrator bootstrap (CLI or seed flag), remembering that
   maker–checker needs two. *(new work)*
3. **DEF-003** — move the commit inside the request boundary rather than FastAPI dependency
   teardown. One wiring change in `composition_root` with very wide blast radius; it also fixes
   the duplicate-registration 500. *(new work)*
4. **DEF-002** — make `option_membership` read the field's `options`, and have the publish gate
   reject a binding that can never pass. Until then the dynamic form engine cannot use select
   fields, which undercuts the core configurability story. *(P-07 / P-04)*

**Group 2 — user-visible correctness (MAJOR).**
5. **DEF-004** — stop re-raising after the Problem response is written. Every pooled client,
   including the product's own server-side rendering, is affected. *(new work)*
6. **DEF-006** — apply the geo filter. A "Must" requirement currently returns everything. *(P-08)*
7. **DEF-008 + DEF-009 + DEF-020** — wire the view-recording policy and fill the statistics
   projection. Fix together: they are one story — owners and operators currently see nothing.
   *(P-07 / P-22)*
8. **DEF-012** — add bounded retry with backoff and an operator-visible DLQ replay. *(new work)*
9. **DEF-010** — reject attributes outside the bound form. *(P-07)*
10. **DEF-005** — either implement confirmation redemption (needs a contract change and therefore
    an ADR) or record an ADR that v1 accepts unconfirmed email. Do not leave a mailed token that
    gates nothing. *(P-05 / new work)*
11. **DEF-011** — run the validation gate before writing promoted columns. *(P-04)*
12. **DEF-013** — reconcile `NEWEST` vs `RECENCY` between the whitelist and the contract. *(P-04)*
13. **DEF-007** — implement the three team operations. *(P-15)*
14. **DEF-015** — populate the admin dashboard. *(P-14)*

**Group 3 — polish and operability (MINOR).** DEF-016 through DEF-021, of which DEF-021
(connection-pool sizing) should be settled before any load testing, since it will otherwise cap
throughput artificially.

**Group 4 — close the coverage gaps.** Exercise the banner campaign lifecycle, EXIF stripping,
malware quarantine, and the three expiry paths (listing, badge, entitlement) — ideally by making
the expiry periods configurable to short values in a test profile. Then run the NEEDS-HUMAN
scripts with real credentials.

### What this verification could not tell you

Performance and scale were not measured. The three expiry-driven requirements are untested and
are exactly the kind that fail quietly in production. Banner ad-serving is largely unverified.
And the frontend was exercised against a production build only — the broken `next dev` hydration
in this environment should be reproduced by the team on their own machines, because if it is not
purely local it will cost every developer their inner loop.
