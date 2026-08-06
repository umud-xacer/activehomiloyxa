# Active Home v1 — Unfinished-Work Backlog (2026-07-28)

Baseline `origin/main` @ `853d5a9`. Ordered **BLOCKER → MAJOR → MINOR → COSMETIC**, and within
each band in **dependency order** (a foundation item before what depends on it).

Kind: **SND** = started-but-not-done · **NS** = never-started.
Effort: rough T-shirt (S ≤ ½ day · M ≈ 1–3 days · L > 3 days).
"Prior" = already reported by `docs/assessments/2026-07-27-verification/` (V), `docs/assessments/2026-07-24-audit/` (A),
`docs/assessments/2026-07-24-acceptance/gap_report.md` (G), or **NEW** in this sweep.

| ID | Sev | Kind | Prior | Area | One line | Eff |
|---|---|---|---|---|---|---|
| UNF-001 | BLOCKER | NS | NEW | infra/data | Fresh-database migration path does not exist (schemas + roles + runner) | M |
| UNF-002 | BLOCKER | SND | V | catalog | `option_membership` can never pass — select fields unusable | S |
| UNF-003 | BLOCKER | SND | V | platform | Commit runs in dependency teardown — read-after-write violated globally | M |
| UNF-004 | MAJOR | SND | NEW | catalog/tests | QG-03b red on `main`: `_listing_payload` awaited nowhere in the integration test | S |
| UNF-005 | MAJOR | SND | NEW | frontend | QG-10b red on `main`: default-locale redirect resolves to `/en`, not `/uz-Latn` | S |
| UNF-006 | MAJOR | SND | NEW | security/infra | Per-module DB roles (PD-06) built and unit-tested, never provisioned | M |
| UNF-007 | MAJOR | NS | NEW | infra | No CD pipeline / staging deploy of any kind | L |
| UNF-008 | MAJOR | NS | NEW | infra | No backup tooling and no tested restore (RPO ≤15 min / RTO ≤4 h unmet) | L |
| UNF-009 | MAJOR | SND | NEW | infra | `nginx.conf` has no TLS termination and no api/web/realtime upstreams | M |
| UNF-010 | MAJOR | SND | NEW | infra | Compose file ships no `api`, `web` or `worker` container | M |
| UNF-011 | MAJOR | SND | NEW | platform | Every mapped error tears down the keep-alive connection | S |
| UNF-012 | MAJOR | NS | V | identity | No first-administrator bootstrap path | S |
| UNF-013 | MAJOR | NS | V | profiles | 3 contract operations (team roster) unimplemented | M |
| UNF-014 | MAJOR | NS | V | identity | Email-confirmation token is issued but nothing can redeem it | M |
| UNF-015 | MAJOR | NS | V | analytics | `ListingViewed` metric never emitted | S |
| UNF-016 | MAJOR | SND | V | analytics | Owner listing statistics return `null` counts | S |
| UNF-017 | MAJOR | SND | V | search | Radius parameter accepted and ignored | S |
| UNF-018 | MAJOR | SND | V | platform | Outbox events reach `DEAD` and are never retried | M |
| UNF-019 | MAJOR | SND | V | admin | `/admin/dashboard` returns every field `null` | S |
| UNF-020 | MAJOR | SND | V | catalog | Attributes outside the bound form silently accepted | S |
| UNF-021 | MAJOR | SND | V | search/config | Configurable sort `NEWEST` unusable (API wants `RECENCY`) | S |
| UNF-022 | MINOR | SND | NEW | tooling | QG-06 reports 110 unimplemented operations when the real number is 3 | S |
| UNF-023 | MINOR | SND | NEW | frontend | `renderingHint` only honours the full-width hint | S |
| UNF-024 | MINOR | SND | NEW | tests | `test_I<nn>` prefix collides between global and module-local invariants | M |
| UNF-025 | MINOR | SND | G | tests | `test_FR_*` naming convention followed by 2 of 89 FRs | L |
| UNF-026 | MINOR | SND | NEW | perf | NFR-PERF SLO benchmarks never run (seed-gated skip) | S |
| UNF-027 | MINOR | SND | V | configuration | Config `definition` documents require snake_case in a camelCase API | S |
| UNF-028 | MINOR | SND | V | configuration | `publishConfigVersion` must be called twice; no approve operation | S |
| UNF-029 | MINOR | SND | V | configuration | Publish body optional in contract, mandatory in code | S |
| UNF-030 | MINOR | SND | V | analytics | Reports enumerate 6 of the 8 closed metrics | S |
| UNF-031 | MINOR | SND | V | infra | Per-module pools exhaust a default `max_connections` | S |
| UNF-032 | MINOR | SND | V | identity | Provider failure surfaces as HTTP 500 | S |
| UNF-033 | COSMETIC | SND | NEW | tooling | `scripts/coverage.sh` carries a stale TODO | S |
| UNF-034 | COSMETIC | SND | NEW | frontend | Two strings untranslated (`ru`, `uz-Latn`) | S |

---

# BLOCKER

## UNF-001 — No fresh-database migration path (schemas, roles, runner)
* **Kind:** NEVER-STARTED · **Area:** infrastructure / data · **Effort:** M · **Prompt:** new work
* **Location:** no implementation found. `scripts/` has no `db-migrate.sh`/`db-seed.sh`;
  `scripts/README.md` states migration/seed helpers "are not here yet".
* **Required by:** Infrastructure & Deployment Architecture (environment bring-up); DevSecOps
  Architecture (migration execution); Physical DB Design §2 ("one schema per module") and PD-06.
* **Evidence:** against an empty database, `alembic upgrade head` fails for **all 13** modules —
  `InvalidSchemaNameError: schema "<module>" does not exist`. `backbone/migrations/env_support.py`
  sets `version_table_schema=<module>`, so Alembic creates `<module>.alembic_version` *before*
  running the migration whose first statement is `CREATE SCHEMA IF NOT EXISTS <module>`.
  Masked in CI because every integration conftest pre-creates the schema.
* **Depends on / blocks:** blocks UNF-006 (roles are provisioned by the same missing step) and
  every deployment item (UNF-007, UNF-008).
* **Done when:** on a genuinely empty database, one documented command creates the 13 schemas,
  their per-module roles, and applies all migrations to head; a CI job runs that command against
  a fresh database so the conftest masking cannot recur.

## UNF-002 — `option_membership` can never pass; select fields unusable
* **Kind:** STARTED-NOT-DONE · **Area:** catalog (+ configuration) · **Effort:** S · **Prompt:** P-07 / P-04
* **Location:** `apps/backend/src/catalog/domain/policies.py:95` `_check_option_membership`;
  `apps/backend/src/catalog/domain/value_objects.py:91` `FieldValidatorSpec`.
* **Required by:** FR-FORM-002 "validate listing submissions against the category's configured
  validation rules … valid ones are accepted"; FR-CFG-003; BRULE-08.
* **Evidence (still present on `853d5a9`):**
  ```python
  allowed = spec.params.get("options", [])       # policies.py:96
  ```
  `FieldValidatorSpec` carries `field_code, validator_type, params, required_field` — the field's
  own `options` list is never translated into the spec, so `allowed` is always `[]` for a binding
  authored as `{"validator_type": "option_membership", "params": {}}`. Runtime confirmation from
  the 2026-07-27 verification: the API serves `options:[new,used]` for the field and then rejects
  `"new"` with `'new' is not an allowed option`.
* **Impact:** every `select`/`multiselect` field is unusable; any category whose form has one
  cannot receive listings. This is the product's central configurability claim.
* **Done when:** a listing with a value drawn from the served `options` is accepted; a value
  outside them is rejected; the publish gate refuses an `option_membership` binding that could
  never pass; a named test covers both directions.

## UNF-003 — Commit runs after the response; read-after-write violated globally
* **Kind:** STARTED-NOT-DONE · **Area:** platform / DI wiring · **Effort:** M · **Prompt:** new work
* **Location:** `apps/backend/src/composition_root.py` — `_identity_session()` and its 12 siblings
  consume `backbone.persistence.engine.session_scope()` as a FastAPI `yield` dependency.
* **Required by:** FR-USER-001 "edits persist and are reflected immediately"; Physical DB §13 and
  `engine.py`'s own docstring "One use case = one Session = one transaction".
* **Evidence:** 10× `PATCH /me` + immediate `GET /me` → **8/10** reads returned the previous
  value, always exactly one revision behind. `POST /auth/register/email` returns `202` but the
  account is unusable for ~0.7 s; a duplicate inside that window returns **500**, not `409`.
* **Done when:** the transaction commits inside the request boundary; a test asserts
  read-after-write on at least one write endpoint per module; duplicate registration returns 409.

---

# MAJOR

## UNF-004 — QG-03b is red on `main`: `_listing_payload` never awaited
* **Kind:** STARTED-NOT-DONE · **Area:** catalog / cross-module tests · **Effort:** S · **Prompt:** P-20
* **Location:** `tests/integration/test_catalog_listing_to_search_index.py:155`.
* **Required by:** ETT §14 (acceptance/testing); DEC-09 outbox correctness.
* **Evidence:** CI run 30284100032 @ `853d5a9` — `1 failed, 1728 passed`;
  `RuntimeWarning: coroutine 'ListingUseCases._listing_payload' was never awaited`.
  PR #26 changed `def _listing_payload` → `async def _listing_payload` (production call sites were
  updated with `await`); this test's call site was not. QG-03b does not run on PRs
  (`-- merge to main + nightly`), so the PR could not catch it.
* **Note:** this regression landed via the PR-#26 merge performed on 2026-07-27.
* **Done when:** the call site awaits, QG-03b is green on `main`, and the merge-only gates are
  either run on PRs or made blocking with an alert.

## UNF-005 — QG-10b is red on `main`: default-locale redirect
* **Kind:** STARTED-NOT-DONE · **Area:** frontend · **Effort:** S · **Prompt:** P-17
* **Location:** `apps/frontend/e2e/smoke.spec.ts:7`; `apps/frontend/src/shared/i18n/routing.ts`.
* **Required by:** FR-LOC-001; DEC-19 (dual-script Uzbek as two locales); UI/UX Spec §2.
* **Evidence:** `expect(page).toHaveURL(/\/uz-Latn$/)` → actual `http://127.0.0.1:3000/en`,
  `<html lang="en">`, 3 attempts, failing on `main` **before** this session's merges (also red at
  `e1ec08b`). Locale negotiation from `Accept-Language` overrides the configured `defaultLocale`.
* **Decide first:** is the requirement "always land on `uz-Latn`" or "negotiate, defaulting to
  `uz-Latn`"? The documents do not state it; whichever is chosen, the other of {test, routing
  config} must change. Record the decision — this is also a documentation gap.
* **Done when:** QG-10b is green and the chosen behaviour is stated in the UI/UX spec.

## UNF-006 — Per-module DB roles (PD-06) built, tested, never provisioned
* **Kind:** STARTED-NOT-DONE · **Area:** security / infrastructure · **Effort:** M · **Prompt:** P-22
* **Location:** `apps/backend/src/backbone/persistence/schema_role.py:32` `schema_and_role_ddl()`.
* **Required by:** Security Architecture §"Database (PostgreSQL 17)" — *"One PG role per module,
  DML only on its own schema (PD-06) — no cross-module reads even if application code is
  compromised"*; cited again as the mitigation for **T-4** (SQL injection blast radius) and
  **I-4** (cross-module data leak through a compromised module); and for workers ("run under
  per-module DB credentials").
* **Evidence:**
  ```
  callers of schema_and_role_ddl() outside tests: 0
  migrations containing CREATE ROLE/CREATE USER:  0
  ah_* roles in a fully migrated database:        0
  ```
  `test_schema_role_convention.py` proves the DDL works — but only against a **scratch** schema
  and role the test creates and drops itself. The application connects as one shared role for all
  13 schemas.
* **Why it matters:** two threat-model mitigations are documented as in place and are not.
* **Done when:** migration/bring-up provisions `ah_<module>` per schema, each service connects
  with its own credentials, and a test asserts a module's role cannot read another schema in the
  **real** database (not a scratch one).

## UNF-007 — No CD pipeline or staging deploy
* **Kind:** NEVER-STARTED · **Area:** infrastructure · **Effort:** L · **Prompt:** new work
* **Location:** no implementation found — `.github/workflows/` contains only `ci.yml`; no deploy
  job, environment, registry push, or orchestration step.
* **Required by:** DEC-16 (CI/CD & environments); Infrastructure & Deployment Architecture;
  ETT §13 deployment deliverables. The ETT's **AC-DEPLOY** dimension is unverifiable without it.
* **Evidence:** `ci.yml:20` — *"No CD pipeline / staging deploy exists yet in this repo (only
  ci.yml)"*; `ci.yml:113` repeats it. Jobs are all quality gates; none deploy.
* **Knock-on:** QG-03b/QG-10b are documented to run "against staging (post-deploy)" and instead
  run against throwaway compose services — so the "post-deploy" half of that contract is fiction.
* **Done when:** a pipeline builds images, deploys to staging on merge to `main`, and the
  merge-only E2E gates run against that deployment.

## UNF-008 — No backups and no tested restore
* **Kind:** NEVER-STARTED · **Area:** infrastructure · **Effort:** L · **Prompt:** new work
* **Location:** no implementation found — zero files under `scripts/`, `deployment/`, `.github/`
  reference `pg_dump`, `pg_restore`, `backup` or `restore`.
* **Required by:** NFR-BAK-001, NFR-REC-001; Infra §13 and §9 — *"Backups + WAL/PITR bound data
  loss to RPO ≤ 15 min and enable RTO ≤ 4 h rebuilds"*; *"PostgreSQL and MinIO and the
  configuration data are backed up"*; §9 explicitly relies on **tested restore** to justify the
  99.9% target on a single node.
* **Evidence:** the recovery story is the *only* thing standing between a single-node disk
  failure and total data loss, and none of it exists.
* **Done when:** scheduled PostgreSQL (WAL/PITR) + MinIO backups run, and a **restore drill** is
  executed and documented with measured RPO/RTO against the stated targets.

## UNF-009 — nginx has no TLS and no application upstreams
* **Kind:** STARTED-NOT-DONE · **Area:** infrastructure · **Effort:** M · **Prompt:** new work
* **Location:** `deployment/nginx/nginx.conf:4,28`.
* **Required by:** Infra §5 (TLS termination), §6 (edge routing to `api`/`web`/`realtime`);
  Security Architecture (TLS to the cluster).
* **Evidence:** `# TODO(next infra task): TLS termination (443) + reverse-proxy upstreams for …`;
  the file currently serves only a static `/healthz`. Consequence: the realtime WSS gateway has
  **no published route at all** — it is reachable only by bypassing the edge.
* **Done when:** nginx terminates TLS and proxies `api`, `web` and the `realtime` WSS upgrade;
  the realtime gateway is reachable through the edge as designed.

## UNF-010 — Compose ships no application containers
* **Kind:** STARTED-NOT-DONE · **Area:** infrastructure · **Effort:** M · **Prompt:** new work
* **Location:** `deployment/compose/docker-compose.yml` — services are `postgres, redis,
  opensearch, minio, clamav, realtime, nginx`.
* **Required by:** Infra §6 container table (`api`, `web`, `worker` containers).
* **Evidence:** the file's own header admits it. `docker compose up` therefore does **not** bring
  up the product; the API, the nine workers and the frontend must all be started by hand. The
  nine `*_worker.py` processes have no container, no restart policy and no supervision.
* **Done when:** `docker compose up` yields a working system, workers included, with health
  checks and restart policies.

## UNF-011 — Every mapped error tears down the keep-alive connection
* **Kind:** STARTED-NOT-DONE · **Area:** platform · **Effort:** S · **Prompt:** new work
* **Location:** `apps/backend/src/backbone/errors/middleware.py`.
* **Required by:** `contracts/openapi.yaml` (a Problem document on every error path); NFR-REL-001/002.
* **Evidence:** one pooled client, four identical failing requests →
  `['401', 'ReadError', '401', 'ReadError']`. Affects every ExceptionMapper-produced status
  (401/403/404/409); **not** FastAPI's own 422 handler and not 2xx. Any pooled client — including
  the app's own Next.js server-side fetch — sees ~50% hard failures on error paths.
* **Done when:** repeated error responses on one connection all return their Problem document.

## UNF-012 — No first-administrator bootstrap
* **Kind:** NEVER-STARTED · **Area:** identity / bring-up · **Effort:** S · **Prompt:** new work
* **Location:** no implementation found.
* **Required by:** FR-ADMIN-006; Configuration Framework §2.3 (maker–checker needs **two**
  distinct approvers).
* **Evidence:** `POST /admin/users/{id}/roles` itself requires `identity:role:assign`, which
  nobody holds on a fresh install. The 2026-07-27 verification had to
  `INSERT INTO identity.role_assignment` twice by hand. The configuration seed creates the
  `super-admin` role *definition* but assigns it to no one.
* **Done when:** a documented command grants the first super-admin(s) without direct DB access.

## UNF-013 — Business-profile team operations unimplemented
* **Kind:** NEVER-STARTED · **Area:** profiles · **Effort:** M · **Prompt:** P-15
* **Location:** no route — `apps/backend/src/profiles/interfaces/routers.py:10` documents the
  deliberate omission.
* **Required by:** `contracts/openapi.yaml` operationIds `listTeamMembers`, `addTeamMember`,
  `removeTeamMember`; ETT §3 business dashboard lists `listTeamMembers`.
* **Evidence:** contract 110 ops, app 107, difference exactly these three; `GET …/team` → 404.
* **Note:** the contract is frozen (DEC-21), so either implement them or record an ADR removing
  them. Leaving a frozen contract 3 operations short is the unfinished state.
* **Done when:** the three operations are served and contract-conformant, or an ADR removes them.

## UNF-014 — Email-confirmation token cannot be redeemed
* **Kind:** NEVER-STARTED · **Area:** identity · **Effort:** M · **Prompt:** P-05 / new work
* **Location:** no endpoint anywhere in `contracts/openapi.yaml` or the app.
* **Required by:** FR-AUTH-002 acceptance "(1) confirmation link activates the account".
* **Evidence:** accounts are created `status='ACTIVE'` and log in immediately; the email body is
  exactly `Confirmation token: <token>` — no link — and nothing consumes the token.
* **Done when:** either redemption exists and gates login, or an ADR records that v1 accepts
  unconfirmed email and the pointless token/email is removed.

## UNF-015 — `ListingViewed` metric never emitted
* **Kind:** NEVER-STARTED (the policy has no implementation) · **Area:** catalog → analytics · **Effort:** S · **Prompt:** P-07 / P-22
* **Required by:** FR-ADV-010 "*a view metric is recorded (DEC-06)*"; Domain Model §5 BC-03
  *"ViewRecordingPolicy — emits a ListingViewed metric on detail view"*; BC-13 closed vocabulary.
* **Evidence:** after dozens of detail fetches, `analytics.metric_event` contained only
  `FAVORITE_ADDED`, `CHAT_INITIATED`, `PHONE_REVEALED`. The product's own report agrees:
  `GET /admin/reports?report=LISTINGS_OVERVIEW` → `"LISTING_VIEWED": 0`.
* **Done when:** a detail fetch emits `ListingViewed` idempotently and it appears in owner
  statistics and operational reports.

## UNF-016 — Owner listing statistics return `null`
* **Kind:** STARTED-NOT-DONE · **Area:** analytics · **Effort:** S · **Prompt:** P-22
* **Required by:** FR-ANALYTICS-002 "owners see **counts** for their listings".
* **Evidence:** `GET /listings/{id}/statistics` →
  `{"views":null,"contactClicks":null,"phoneReveals":null,"chatsInitiated":null,"favorites":0}`.
* **Depends on:** UNF-015 for `views` to be non-zero, but the `null`-vs-`0` bug is separate.
* **Done when:** every counter is an integer and reflects recorded metrics.

## UNF-017 — Radius search ignores the radius
* **Kind:** STARTED-NOT-DONE · **Area:** search · **Effort:** S · **Prompt:** P-08
* **Required by:** FR-MAP-003 "**only** listings within the radius are returned".
* **Evidence:** identical 20-hit result sets at `radiusKm` = 1, 5, 50, 500 and with no radius at
  all; Samarkand listings (~270 km away) returned at `radiusKm=1` from Tashkent. Note the
  repository layer *does* have geo tests (`test_geo_bounding_box_*`,
  `test_geo_radius_search_finds_a_nearby_listing`), so the gap is in the API→query wiring, not
  the store.
* **Done when:** out-of-radius listings are excluded, proven by an API-level test.

## UNF-018 — Outbox events reach `DEAD` and are never retried
* **Kind:** STARTED-NOT-DONE · **Area:** platform · **Effort:** M · **Prompt:** new work
* **Location:** `apps/backend/src/backbone/outbox/dispatcher.py`.
* **Required by:** DEC-09 (transactional outbox — the mechanism exists precisely to guarantee
  eventual delivery); Infra §9 degradation ("component failures degrade rather than outright
  fail").
* **Evidence:** during a sustained index outage, 32 `catalog.outbox_event` rows reached
  `dispatch_status='DEAD'` and were never retried; the listings stayed `PUBLISHED` but were
  permanently absent from search. Recovery required a manual
  `UPDATE … SET dispatch_status='PENDING'`. There is no automated drain, no replay endpoint and
  no alert.
* **Done when:** bounded retry with backoff, an operator-visible replay, and an alert on
  non-empty DEAD.

## UNF-019 — `/admin/dashboard` returns every field null
* **Kind:** STARTED-NOT-DONE · **Area:** admin · **Effort:** S · **Prompt:** P-14
* **Required by:** FR-ADMIN-001; ETT M-12 (`/admin` composes the other modules' operator surfaces).
* **Evidence:** on a database with 20 users, 82 listings, 13 moderation cases and 12 invoices →
  `{"activeListings":null,"pendingModeration":null,"pendingVerification":null,
  "pendingInvoices":null,"newUsers7d":null}`. The operator landing page renders ~239 characters.
* **Done when:** the dashboard shows real counts composed from the owning modules.

## UNF-020 — Attributes outside the bound form silently accepted
* **Kind:** STARTED-NOT-DONE · **Area:** catalog · **Effort:** S · **Prompt:** P-07
* **Required by:** `AttributeMap` — "typed values keyed by the field `code` of the bound
  FormDefinition version"; FR-FORM-002.
* **Evidence:** `POST /listings` with `attributes.unknown_field` → `201`, persisted into
  `catalog.listing.attribute_document` and projected into the search index.
* **Done when:** unknown keys are rejected with a field-level error.

## UNF-021 — Configurable sort `NEWEST` is unusable
* **Kind:** STARTED-NOT-DONE · **Area:** search ↔ configuration · **Effort:** S · **Prompt:** P-04 / P-08
* **Required by:** FR-SRCH-003 "results reorder per the **selected configured** sort option".
* **Evidence:** `configuration/domain/whitelist.py` → `SORT_OPTIONS = {RELEVANCE, NEWEST,
  PRICE_ASC, PRICE_DESC}`; a search configuration containing `NEWEST` publishes cleanly; but
  `GET /search?sort=NEWEST` → `422 "Input should be 'RELEVANCE', 'RECENCY', 'PRICE_ASC' or
  'PRICE_DESC'"`. Two vocabularies disagree on one member.
* **Done when:** one vocabulary; a configured sort option is always usable. Contract change needs
  an ADR.

---

# MINOR

## UNF-022 — QG-06 misreports the unimplemented-operation count
`tools/check_contract_drift.py:94` prints `len(spec_routes)` (110) instead of
`len(spec_routes - app_routes)` (3), so the gate's own output hides the real gap.
**Done when:** the message reports the 3 and, ideally, names them. · S · new work

## UNF-023 — `renderingHint` only honours the full-width hint
`apps/frontend/src/shared/forms/dynamic-form.tsx:128` — *"only a full-width hint is honoured for
now"*. Config Framework §5.1 defines a `RenderingHint` vocabulary of 7
(`DEFAULT, DROPDOWN, RADIO, CHECKBOX_GROUP, SLIDER, MAP_PICKER, TEXTAREA`); the engine ignores
the rest, so an administrator can author a hint that has no effect.
**Done when:** each whitelisted hint renders distinctly, or the vocabulary is narrowed by ADR. · S · P-17

## UNF-024 — Invariant test-naming collides
The Domain Model §"Invariants are the test oracle" claims I-01…I-24 "map 1:1 to test names …
giving reviewers a traceable checklist". They do not: `search`, `notifications` and
`shared_kernel` renumber `I01…` for their own local invariants, so `test_I14` matches both
billing's entitlement invariant and a search cross-script test. I-09/I-11/I-17/I-18 have no
`test_I<nn>` in their owning module (all four *are* covered by other names — see the scan file).
The doc's own example `test_I08_quota_exceeded_refused` does not exist.
**Done when:** global invariant tests use a distinct prefix and all 24 are greppable. · M · new work

## UNF-025 — `test_FR_*` convention followed by 2 of 89 FRs
Already reported in `docs/assessments/2026-07-24-acceptance/gap_report.md` (P-20) and still true.
**Done when:** requirement-traced tests are greppable by FR id, or the convention is retired. · L · new work

## UNF-026 — NFR-PERF SLO benchmarks never run
`tests/performance/test_benchmark_search.py:77` and `test_benchmark_write_path.py:78` skip with
*"run `python -m tests.performance.seed_cli` first"*. The harness, the operations and the SLO
targets (`target_p95_ms: 300`, NFR-PERF-002) and baseline reports all exist — but nothing seeds
the data in CI, so the SLOs are **unverified**.
**Done when:** CI seeds and runs the benchmarks and compares against the baselines. · S · P-21

## UNF-027 — Config `definition` documents require snake_case
Every DTO on the wire is camelCase; the opaque `definition` blob is validated by snake_case
models in `configuration/domain/content.py` (`extra="forbid"`), so `descriptor.displayOrder` is
rejected and `descriptor.display_order` accepted. Undiscoverable for operators and the config
portal. · S · P-04/P-21

## UNF-028 — `publishConfigVersion` must be called twice
Config Framework §2.3 documents "author → validation gate → approver → publish" as distinct
steps; the implementation collapses them into one operation called twice, the first call
returning `200` with status `APPROVAL` while the head is still `DRAFT`. · S · P-18

## UNF-029 — Publish body optional in contract, mandatory in code
`publishConfigVersion.requestBody` has no `required: true` in the contract; the app declares it
required and 422s without it. · S · P-18

## UNF-030 — Reports enumerate 6 of the 8 closed metrics
`GET /admin/reports?report=LISTINGS_OVERVIEW` omits `BANNER_IMPRESSION_RECORDED` and
`BANNER_CLICK_RECORDED` though BRULE-20 / BC-13 define a closed set of eight. · S · P-22

## UNF-031 — Per-module pools exhaust a default `max_connections`
API + realtime + nine workers, each building one engine per module, exhausted
`max_connections=100` (`FATAL: sorry, too many clients already`, 98 idle). Compose does not tune
it and no document states a required value. Must be settled before any load testing. · S · P-21

## UNF-032 — Provider failure surfaces as HTTP 500
`POST /auth/otp` with an unreachable provider returns `500 DEPENDENCY_DEGRADED` titled "Internal
server error"; a degraded downstream reads as 502/503 (`/ready` already does this correctly). · S · P-05

---

# COSMETIC

## UNF-033 — Stale TODO in `scripts/coverage.sh:8`
*"TODO: remove entirely once every module also has domain/application …"* — the condition may now
hold; verify and delete. · S

## UNF-034 — Two untranslated strings
`ru → company.userIdLabel = "User id"`; `uz-Latn → business.portfolioHeading = "Portfolio"`.
All other 796×4 keys are present, non-empty and genuinely localised. · S · P-17
