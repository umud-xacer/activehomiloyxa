# Active Home v1 — Defect Register (2026-07-27)

Baseline verified: `origin/main` @ `e1ec08b` (P-21, "§5.2 structured config editors").
Method: behavioural testing of the running system (HTTP + WSS + real browser). See
`VERIFICATION-REPORT-2026-07-27.md` §2 for bring-up. Evidence files referenced below live in
`docs/assessments/2026-07-27-verification/evidence/`.

Ordered BLOCKER → MAJOR → MINOR → COSMETIC, then by module.

| ID | Severity | Module | Class | One line |
|---|---|---|---|---|
| DEF-001 | BLOCKER | Infra/Data | BROKEN | Alembic migrations cannot be applied to a fresh database |
| DEF-002 | BLOCKER | Catalog/Config | BUG | `option_membership` rejects values that ARE configured options |
| DEF-003 | BLOCKER | Platform/API | BUG | Commit runs after the response — read-after-write violated globally |
| DEF-004 | MAJOR | Platform/API | BUG | Every mapped error response tears down the keep-alive connection |
| DEF-005 | MAJOR | Identity | MISSING | Email confirmation is inert; accounts are ACTIVE on creation |
| DEF-006 | MAJOR | Search/Geo | BUG | Radius search does not filter by distance at all |
| DEF-007 | MAJOR | Profiles | MISSING | The three business-profile *team* contract operations are absent |
| DEF-008 | MAJOR | Analytics | MISSING | `ListingViewed` metric is never recorded |
| DEF-009 | MAJOR | Analytics | BUG | Owner listing statistics return `null` counts |
| DEF-010 | MAJOR | Catalog | BUG | Attributes not in the bound form are silently accepted |
| DEF-011 | MAJOR | Configuration | BUG | An incomplete config draft returns 500 instead of a validation error |
| DEF-012 | MAJOR | Platform/Infra | BUG | Failed outbox events go DEAD and are never retried |
| DEF-013 | MAJOR | Search/Config | DEVIATES | Configurable sort vocabulary (`NEWEST`) ≠ API vocabulary (`RECENCY`) |
| DEF-014 | MAJOR | Identity/Infra | MISSING | No API path to assign the first administrator |
| DEF-015 | MAJOR | Administration | BUG | `/admin/dashboard` returns every field `null` |
| DEF-016 | MINOR | Identity | DEVIATES | Provider failure surfaces as HTTP 500 `DEPENDENCY_DEGRADED` |
| DEF-017 | MINOR | Configuration | DEVIATES | Config `definition` documents require snake_case in a camelCase API |
| DEF-018 | MINOR | Configuration | DEVIATES | `publishConfigVersion` must be called twice; no approve operation exists |
| DEF-019 | MINOR | Configuration | DEVIATES | Publish request body optional in the contract, mandatory in the implementation |
| DEF-020 | MINOR | Analytics | DEVIATES | Operational reports enumerate 6 of the 8 closed metrics |
| DEF-021 | MINOR | Infra | DEVIATES | Per-module connection pools exhaust a default PostgreSQL `max_connections` |

---

## BLOCKER

### DEF-001 — Alembic migrations cannot be applied to a fresh database
* **Area/module:** Infrastructure / all 13 module schemas.
* **Doc violated:** Infrastructure & Deployment Architecture (environment bring-up); DevSecOps
  Architecture (migration execution); Physical Database Design §2 (schema-per-module).
  `scripts/README.md` itself states migration/seed helpers "are not here yet".
* **Reproduction:**
  1. `CREATE DATABASE active_home_fresh;` (empty, no schemas).
  2. Point `POSTGRES_DB` at it.
  3. For any module: `alembic -c apps/backend/src/<module>/infrastructure/migrations/alembic.ini upgrade head`.
* **Expected:** the migration runs; its first statement `CREATE SCHEMA IF NOT EXISTS <module>`
  creates the schema (Physical DB §2 schema-per-module).
* **Observed:** all 13 modules fail with
  `asyncpg.exceptions.InvalidSchemaNameError: schema "<module>" does not exist`, raised while
  creating `<module>.alembic_version`. `backbone/migrations/env_support.py` sets
  `version_table_schema=<module>`, so Alembic tries to create its version table in a schema that
  the not-yet-run migration is supposed to create. 0/13 succeed.
* **Why it is not caught:** every integration conftest pre-creates the schema
  (`apps/backend/tests/*/integration/conftest.py`: `CREATE SCHEMA IF NOT EXISTS "<module>"`), so
  CI never exercises a genuinely fresh database.
* **Severity:** BLOCKER — there is no supported way to stand the product up from nothing.
* **Evidence:** bring-up transcript, §2 of the report. Workaround used for this verification:
  pre-create the 13 schemas by hand (`bringup.sh`).
* **Suspected layer:** infra / data.
* **Handbook prompt:** new work (add `scripts/db-migrate.sh` that creates schemas first, or move
  schema creation into `env_support.py` before `context.configure`).

### DEF-002 — `option_membership` rejects values that ARE configured options
* **Area/module:** Catalog attribute validation ↔ Configuration form engine.
* **Doc violated:** FR-FORM-002 "SHALL validate listing submissions against the category's
  configured validation rules ... valid ones are accepted"; FR-CFG-003 "configured
  rules/filters/sorts apply"; BRULE-08.
* **Reproduction:**
  1. Author a `form-definition` with a `select` field `condition`, options `new` / `used`, and a
     validator binding `{"validator_type": "option_membership", "params": {}}`. Publish it.
  2. Bind it to a category and publish the category.
  3. `GET /api/v1/categories/{id}/form` — the response contains
     `"options":[{"value":"new",...},{"value":"used",...}]` and
     `"validators":[{"validatorType":"option_membership","params":{}}]`.
  4. `POST /api/v1/listings` with `"attributes": {"rooms":3,"area_m2":50,"condition":"new"}`.
* **Expected:** 201 — `new` is one of the two configured options the API just served.
* **Observed:** `422` —
  `{"path":"/attributes/condition","rule":"attribute_validation","message":"'new' is not an allowed option"}`.
  The validator reads its permitted set from the binding's `params` (empty as authored) instead
  of from the field's own `options` list.
* **Impact:** every `select`/`multiselect` field is unusable. Any category whose form contains
  one cannot receive listings at all, so the dynamic form engine — the product's central
  configurability claim — is only usable for text/number/boolean fields.
* **Severity:** BLOCKER.
* **Evidence:** `evidence/res_catalog.json` (`FORM-002-*`); isolation transcript in report §3.3.
* **Suspected layer:** domain (catalog attribute validation) — possibly configuration (the
  publish gate should reject an `option_membership` binding with empty params).
* **Handbook prompt:** P-07 (form engine) / P-04 (configuration gate).

### DEF-003 — Commit runs after the response: read-after-write violated globally
* **Area/module:** Platform (`composition_root` session wiring) — affects every write endpoint.
* **Doc violated:** FR-USER-001 "edits persist and are reflected immediately";
  `backbone/persistence/engine.py` docstring "One use case = one Session = one transaction"
  (Physical DB §13).
* **Reproduction:**
  1. Register and log in.
  2. Loop 10×: `PATCH /api/v1/me {"displayName":"NameN"}` then immediately `GET /api/v1/me`.
* **Expected:** every `GET` returns the value just written.
* **Observed:** **8 of 10** immediate re-reads return the *previous* value — always exactly one
  revision behind. `PATCH` returns `200` whose body echoes the NEW value while the next `GET`
  returns the OLD one:
  ```
  iter0: wrote 'Name0', immediate read 'N0'    STALE
  iter1: wrote 'Name1', immediate read 'Name0' STALE
  ...
  read-after-write violated on 8/10 immediate re-reads
  ```
* **Cause:** `session_scope()` is consumed as a FastAPI `yield` dependency
  (`composition_root._identity_session` and its siblings), so the transaction commits during
  dependency teardown — after the response has been sent.
* **Related symptoms with the same root cause:**
  * `POST /auth/register/email` returns `202` but the account is unusable for ~0.7 s (measured);
    an immediate login returns 401.
  * Registering the same address twice inside that window returns **500**, not `409
    DUPLICATE_KEY` — so FR-AUTH-002 acceptance (2) fails under concurrency.
* **Severity:** BLOCKER — any client that writes then reads (including the product's own UI) can
  show the user stale data, and it makes write endpoints unsafe to compose.
* **Evidence:** `evidence/res_identity.json`; transcript in report §3.1.
* **Suspected layer:** API / DI wiring.
* **Handbook prompt:** new work.

---

## MAJOR

### DEF-004 — Every mapped error response tears down the keep-alive connection
* **Area/module:** Platform (`backbone/errors/middleware.py`).
* **Doc violated:** `contracts/openapi.yaml` — every error path is specified to return a Problem
  document; NFR-REL-001/002.
* **Reproduction:** with a single connection-pooling HTTP client, issue the same failing request
  four times:
  ```python
  c = httpx.Client(base_url=".../api/v1")
  for i in range(4): c.post("/auth/login/email", json={"email":"ghost@x.invalid","password":"..."} )
  ```
* **Expected:** four `401` Problem responses.
* **Observed:** `['401', 'ReadError', '401', 'ReadError']` — alternate requests get
  `Server disconnected without sending a response` / `ECONNRESET`. Characterised across codes:
  | Response | Behaviour |
  |---|---|
  | `200` | fine |
  | `422` (FastAPI's own `RequestValidationError` handler) | fine |
  | `401`, `403`, `404`, `409` (ExceptionMapper) | **connection destroyed on alternate requests** |
  The exception is re-raised after the Problem response is written, so uvicorn tears the
  connection down.
* **Impact:** any pooled client sees ~50 % hard failures on error paths — including the Next.js
  server-side fetch (undici pools by default), so "not found" and "forbidden" pages will
  intermittently render as crashes.
* **Severity:** MAJOR.
* **Evidence:** report §3.1; the whole verification harness had to disable keep-alive
  (`max_keepalive_connections=0`) to proceed.
* **Suspected layer:** API middleware.
* **Handbook prompt:** new work.

### DEF-005 — Email confirmation is inert; accounts are ACTIVE on creation
* **Area/module:** Identity & Access.
* **Doc violated:** FR-AUTH-002 acceptance "(1) confirmation link activates the account".
* **Reproduction:**
  1. `POST /api/v1/auth/register/email {"email":"x@example.invalid","password":"...","displayName":"X"}` → `202`.
  2. Read the message in Mailpit — body is exactly
     `Confirmation token: <43-char opaque token, redacted>`.
  3. Without redeeming anything, `POST /api/v1/auth/login/email` with the same credentials.
* **Expected:** the account is not usable until the confirmation link is redeemed; login refused.
* **Observed:** `identity.user_account.status = 'ACTIVE'` immediately at creation, and login
  succeeds (`200`, session issued). The mail contains a bare token and **no link**, and there is
  **no operation anywhere in `contracts/openapi.yaml`** that redeems such a token. The token
  gates nothing.
* **Severity:** MAJOR — an unverified address can hold a full account, and a documented
  acceptance criterion has no implementation.
* **Evidence:** `evidence/res_identity.json` (`AUTH-002-*`).
* **Suspected layer:** domain + API + contract (the contract itself lacks the endpoint, so this
  needs an ADR, not just code).
* **Handbook prompt:** P-05 / new work.

### DEF-006 — Radius search does not filter by distance
* **Area/module:** Search & Discovery / Maps & Geo.
* **Doc violated:** FR-MAP-003 "SHALL allow users to discover listings within a chosen radius of
  a location. Acceptance: **only** listings within the radius are returned."
* **Reproduction:** publish listings in Tashkent (41.311, 69.240) and Samarkand (39.654, 66.959)
  — ~270 km apart — then:
  ```
  GET /api/v1/search?lat=41.311&lon=69.240&radiusKm=1     -> 20 hits
  GET /api/v1/search?lat=41.311&lon=69.240&radiusKm=5     -> 20 hits
  GET /api/v1/search?lat=41.311&lon=69.240&radiusKm=50    -> 20 hits
  GET /api/v1/search?lat=41.311&lon=69.240&radiusKm=500   -> 20 hits
  GET /api/v1/search                       (no radius)    -> 20 hits
  ```
  At `radiusKm=1` the response still contains `Samarqandda gʻishtli uy` and
  `Самарқандда ғиштли уй`.
* **Expected:** the Samarkand listings are excluded at 1 km and 5 km.
* **Observed:** identical result sets at every radius — the parameter is accepted and ignored.
* **Severity:** MAJOR — a "Must" requirement, and the map/radius UI is one of the documented
  primary discovery paths.
* **Evidence:** `evidence/res_search.json` (`MAP-003-radius`) plus the transcript in report §3.4.
* **Suspected layer:** search (query building — the geo clause is not applied).
* **Handbook prompt:** P-08 / new work.

### DEF-007 — Business-profile team operations are absent
* **Area/module:** Business Profiles.
* **Doc violated:** `contracts/openapi.yaml` operationIds `listTeamMembers`, `addTeamMember`,
  `removeTeamMember`; Enterprise Technical Task §3 (business dashboard lists `listTeamMembers`).
* **Reproduction:** `GET /api/v1/business-profiles/{profileId}/team` as the profile owner.
* **Expected:** `200` with the team roster.
* **Observed:** `404` — the route does not exist. A full diff of the live OpenAPI against the
  frozen contract shows **107 of 110** operations served and **0** undocumented extras; these
  three are the only gap.
* **Severity:** MAJOR (contract non-conformance on a documented surface).
* **Evidence:** `evidence/res_profiles.json` (`PROF-team-endpoint`); route diff in report §3.
* **Suspected layer:** API.
* **Handbook prompt:** P-15.

### DEF-008 — `ListingViewed` metric is never recorded
* **Area/module:** Catalog → Analytics.
* **Doc violated:** FR-ADV-010 "SHALL display full listing detail ... and SHALL record a view
  event. Acceptance: the detail view renders; **a view metric is recorded** (DEC-06)";
  Domain Model §5 BC-03 "ViewRecordingPolicy — emits a `ListingViewed` metric on detail view
  (FR-ADV-010)"; §5 BC-13 lists `ListingViewed` first in the closed v1 vocabulary.
* **Reproduction:** publish a listing; `GET /api/v1/listings/{id}` repeatedly (anonymous and
  authenticated); wait for the analytics worker; then
  `select metric_key, count(*) from analytics.metric_event group by 1`.
* **Expected:** `LISTING_VIEWED` rows.
* **Observed:** none, ever. Across the whole verification run only `FAVORITE_ADDED`,
  `CHAT_INITIATED` and `PHONE_REVEALED` were ever emitted. `GET /admin/reports?report=LISTINGS_OVERVIEW`
  confirms it from the product's own surface: `"LISTING_VIEWED": 0` after dozens of detail views.
* **Severity:** MAJOR — a "Must" acceptance criterion, and it is the headline number owners and
  operators are meant to see.
* **Evidence:** `evidence/res_ops.json` (`ANALYTICS-001-coverage`), `evidence/res_catalog.json`.
* **Suspected layer:** domain (catalog view-recording policy not wired).
* **Handbook prompt:** P-07 / P-22.

### DEF-009 — Owner listing statistics return `null` counts
* **Area/module:** Analytics.
* **Doc violated:** FR-ANALYTICS-002 "SHALL present basic performance statistics to listing
  owners. Acceptance: **owners see counts** for their listings."
* **Reproduction:** as a listing owner, publish a listing, fetch it 6× as an anonymous user, wait
  for the analytics projection, then `GET /api/v1/listings/{id}/statistics`.
* **Expected:** numeric counts.
* **Observed:** `200` with
  `{"listingId":"…","views":null,"contactClicks":null,"phoneReveals":null,"chatsInitiated":null,"favorites":0}`
  — four of the five counters are `null` rather than `0` or a real count. (`views` is also
  affected by DEF-008, but `null` ≠ `0` is a separate contract/DTO problem.)
* **Severity:** MAJOR.
* **Evidence:** `evidence/res_ops.json` (`ANALYTICS-002-owner-stats`).
* **Suspected layer:** analytics projection / DTO mapping.
* **Handbook prompt:** P-22.

### DEF-010 — Attributes not in the bound form are silently accepted
* **Area/module:** Catalog.
* **Doc violated:** `contracts/openapi.yaml` `AttributeMap` — "typed values keyed by the field
  `code` of the bound FormDefinition version"; FR-FORM-002.
* **Reproduction:** `POST /api/v1/listings` with
  `"attributes": {"rooms":3, "area_m2":50, "unknown_field":"x"}`.
* **Expected:** rejected — `unknown_field` is in no version of the bound form.
* **Observed:** `201 Created`; the key is persisted into `catalog.listing.attribute_document`.
* **Severity:** MAJOR — arbitrary client-controlled keys enter the aggregate and are projected
  into the search index, defeating the "attributes are the bound form's fields" invariant.
* **Evidence:** `evidence/res_catalog.json` (`FORM-002-unknown-field`).
* **Suspected layer:** domain.
* **Handbook prompt:** P-07.

### DEF-011 — An incomplete configuration draft returns 500 instead of a validation error
* **Area/module:** Configuration.
* **Doc violated:** Configuration & Metadata Framework §9 (pre-activation validation gate);
  FR-CFG-002.
* **Reproduction:** `POST /api/v1/admin/config/category` with
  `{"code":"probe-cat","businessOwner":"X","definition":{}}` as a super-admin.
* **Expected:** `422` with field-level errors from the gate (the gate exists and works when the
  draft reaches it — see `validate`, which correctly returns `{"valid":false,"errors":[…]}`).
* **Observed:** `500 DEPENDENCY_DEGRADED`; the server log shows
  `NotNullViolationError: null value in column "form_definition_id" of relation "category_version"`.
  Reproduced identically for `product-definition` and `placement-slot` — the promoted columns are
  written before the gate runs.
* **Severity:** MAJOR — the config portal's primary authoring path 500s on ordinary operator
  mistakes.
* **Evidence:** report §3.2 transcript.
* **Suspected layer:** API / persistence.
* **Handbook prompt:** P-04.

### DEF-012 — Failed outbox events go DEAD and are never retried
* **Area/module:** Platform (outbox dispatcher) → Search projection.
* **Doc violated:** DEC-09 (transactional outbox — never dual-write); Infrastructure/DevSecOps
  degradation guidance (a slow or unavailable consumer must not lose the write); the outbox
  exists precisely to guarantee eventual delivery.
* **Reproduction:** make the search index reject writes (any sustained OpenSearch unavailability;
  in this run the index entered `read_only_allow_delete` under a disk watermark), publish
  listings, then restore the index.
* **Expected:** the dispatcher keeps retrying and the backlog drains once the dependency returns.
* **Observed:** `catalog.outbox_event` rows reach `dispatch_status='DEAD'` (32 at one point) and
  are **never retried**. The listings stayed `PUBLISHED` in the catalog but were permanently
  absent from search. A paid `PREMIUM` listing (promotion entitlement active,
  `promotion_kind='PREMIUM'` in the catalog) was invisible in search until an operator manually
  ran `UPDATE catalog.outbox_event SET dispatch_status='PENDING' WHERE dispatch_status='DEAD'`.
  There is no automated DLQ drain, no replay endpoint, and no alert.
* **Severity:** MAJOR — silent, permanent divergence between the write model and the read model
  after any transient dependency outage, with direct revenue impact.
* **Note:** the outage in this environment was induced by host disk pressure, not by the product;
  the *response to* the outage is the defect.
* **Evidence:** `evidence/` worker logs; report §5.
* **Suspected layer:** infra / platform (dispatcher retry policy).
* **Handbook prompt:** new work.

### DEF-013 — Configurable sort vocabulary does not match the API's
* **Area/module:** Search ↔ Configuration.
* **Doc violated:** FR-SRCH-003 "results reorder per the **selected configured** sort option";
  FR-CFG-003.
* **Reproduction:**
  1. Publish a `search-configuration` whose `sort_options` are
     `["RELEVANCE","NEWEST","PRICE_ASC","PRICE_DESC"]` — this passes the whitelist gate, because
     `configuration/domain/whitelist.py` defines `SORT_OPTIONS = {RELEVANCE, NEWEST, PRICE_ASC, PRICE_DESC}`.
  2. `GET /api/v1/search?q=uy&sort=NEWEST`.
* **Expected:** results ordered by recency.
* **Observed:** `422` — `"Input should be 'RELEVANCE', 'RECENCY', 'PRICE_ASC' or 'PRICE_DESC'"`.
  The frozen contract also says `RECENCY`. So an administrator can legitimately author and
  publish a sort option that the search API refuses to accept. `RELEVANCE`, `PRICE_ASC` and
  `PRICE_DESC` all work.
* **Severity:** MAJOR (a configured option is unusable; the two vocabularies must be one).
* **Evidence:** `evidence/res_search.json` (`SRCH-003-sort-NEWEST`).
* **Suspected layer:** configuration whitelist vs contract (pick one spelling; whichever changes
  needs an ADR because the contract is frozen).
* **Handbook prompt:** P-04 / P-08.

### DEF-014 — No API path to assign the first administrator
* **Area/module:** Identity & Access / bring-up.
* **Doc violated:** FR-ADMIN-006 (Super Administrator assigns roles) is unreachable on a fresh
  install; Configuration Framework §2.3 additionally requires **two** distinct super-admins for
  maker–checker.
* **Reproduction:** bring up a fresh database, run the configuration seed (which creates the
  `super-admin` and `administrator` role *definitions* but assigns them to nobody), then try to
  grant anyone a role. `POST /api/v1/admin/users/{id}/roles` itself requires
  `identity:role:assign`, which nobody holds.
* **Expected:** a documented bootstrap path (CLI, seed flag, or first-user rule).
* **Observed:** none exists. This verification had to
  `INSERT INTO identity.role_assignment (...)` directly, twice, to obtain a maker and a checker.
* **Severity:** MAJOR — the product cannot be administered after a clean install without direct
  database access.
* **Evidence:** `bootstrap_admin.py` in the harness; report §2.
* **Suspected layer:** API / infra.
* **Handbook prompt:** new work.

### DEF-015 — `/admin/dashboard` returns every field null
* **Area/module:** Administration.
* **Doc violated:** FR-ADMIN-001 / Enterprise Technical Task M-12 — `/admin` composes the other
  modules' operator interfaces.
* **Reproduction:** `GET /api/v1/admin/dashboard` as a super-admin, on a database containing
  20 users, 82 listings, 13 moderation cases, 12 invoices and 2 verification cases.
* **Expected:** populated counts.
* **Observed:** `200` with
  `{"activeListings":null,"pendingModeration":null,"pendingVerification":null,"pendingInvoices":null,"newUsers7d":null}`
  — the composition returns the shape but never fills it. The operator home page
  (`/en/admin`) correspondingly renders an almost-empty document (239 characters).
* **Severity:** MAJOR (the operator landing surface carries no information).
* **Evidence:** `evidence/res_ops.json` (`ADMIN-dashboard`), `evidence/admin-config-portal.png`.
* **Suspected layer:** admin composition module.
* **Handbook prompt:** P-14.

---

## MINOR

### DEF-016 — Provider failure surfaces as HTTP 500
`POST /api/v1/auth/otp` with unusable Eskiz credentials returns
`{"status":500,"code":"DEPENDENCY_DEGRADED","title":"Internal server error"}` and is logged as
"unhandled exception". A degraded *downstream* dependency should be 502/503 (the same code is
used correctly on `/ready`, which returns 503), and the title contradicts the code.
**Positive evidence:** the adapter genuinely called `https://notify.eskiz.uz/api/auth/login` and
received 401 — the provider boundary is correctly formed and dispatched.
Layer: API. Prompt: P-05.

### DEF-017 — Config `definition` documents require snake_case in a camelCase API
Every DTO on the wire is camelCase (`CamelModel`), but the opaque `definition` blob is validated
by snake_case pydantic models (`configuration/domain/content.py`, `extra="forbid"`).
`descriptor.displayOrder` is rejected as `extra_forbidden`; `descriptor.display_order` validates.
Nothing in the contract types `definition`, so no clause is broken — but the operator/frontend
surface is inconsistent and undiscoverable. Layer: API. Prompt: P-04 / P-21.

### DEF-018 — `publishConfigVersion` must be called twice; no approve operation exists
Configuration Framework §2.3 documents "author (maker) → validation gate → approver (checker) →
publish". The implementation collapses approve and publish into the single
`publishConfigVersion` operation: the first call returns **200** but moves the version to
`APPROVAL` (head still `DRAFT`, `current_version_id` NULL); a second call by a non-author moves
it to `PUBLISHED`. A 200 that reads as "published" but has not published is a trap for operators
and for the config portal.
**Positive evidence:** maker–checker itself is correctly enforced — the author's own approval is
refused `403 "The approver must be a different principal from the author"`.
Layer: API / contract. Prompt: P-18 / P-21.

### DEF-019 — Publish request body optional in the contract, mandatory in the implementation
`publishConfigVersion.requestBody` has no `required: true` in `contracts/openapi.yaml`; the live
application declares `required: true` and returns `422 {"path":"/body","rule":"missing"}` when it
is omitted. Layer: API. Prompt: P-18.

### DEF-020 — Operational reports enumerate 6 of the 8 closed metrics
`GET /api/v1/admin/reports?report=LISTINGS_OVERVIEW` returns
`counts: {LISTING_VIEWED, CONTACT_BUTTON_CLICKED, PHONE_REVEALED, CHAT_INITIATED, FAVORITE_ADDED,
PREMIUM_LISTING_STAT}` — `BANNER_IMPRESSION_RECORDED` and `BANNER_CLICK_RECORDED` are absent,
though BRULE-20 / Domain Model §5 BC-13 define a closed set of eight and FR-ADMIN-005 says
reports reflect "the v1 metric set". Layer: analytics. Prompt: P-22.

### DEF-021 — Per-module connection pools exhaust a default PostgreSQL
Running the documented component set (API + realtime gateway + the nine outbox workers) against
`postgres:17-alpine` with its default `max_connections=100` exhausts the server:
`FATAL: sorry, too many clients already`, with 98 connections idle. Each process builds one
engine per module (13 schemas), each with its own pool. `deployment/compose/docker-compose.yml`
does not tune `max_connections`, and no document states a required value.
Consequence during this run: the realtime WSS upgrade returned HTTP 500 until workers were
stopped. Layer: infra. Prompt: new work.

---

## NEEDS-HUMAN (see `HUMAN-TEST-SCRIPTS-2026-07-27.md`)

| Item | Doc | Verified to |
|---|---|---|
| Real SMS OTP delivery (Eskiz) | FR-AUTH-001, FR-NOTIF-003, BRULE-01 | Provider boundary — the adapter really calls `notify.eskiz.uz/api/auth/login`; rejected because the credentials are placeholders |
| Google federated sign-in | FR-AUTH-003 | Invalid-token path only (`422`); the success path needs real OAuth credentials |
| Web-push delivery | FR-NOTIF-002 | Not exercised — needs a real VAPID key pair and a browser push subscription |
| Live email delivery (production SMTP) | FR-NOTIF-001 | Verified against a local Mailpit sink; production SMTP with STARTTLS+AUTH untested |
| Yandex Maps rendering | FR-MAP-002 | Not exercised — needs a real `YANDEX_MAPS_API_KEY` |

## OUT-OF-SCOPE / v2 creep

None found. See report §6 — reviews/ratings, online payment, video/PDF media, saved-search
digests, CMS, recommendations, Kubernetes and multi-currency are all absent, and the exclusions
are actively enforced (video/PDF uploads are refused; no online payment operation exists).
