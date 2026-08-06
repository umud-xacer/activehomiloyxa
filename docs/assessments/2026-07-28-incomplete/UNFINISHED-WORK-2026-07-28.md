# Active Home v1 — Unfinished Work Report (2026-07-28)

**Baseline:** `origin/main` @ `853d5a9` (after PR #26 and PR #27 merged).
**Nature:** read-only discovery. Nothing was implemented, completed or modified; the only files
written are the three artifacts in `docs/assessments/2026-07-28-incomplete/`.
**Companions:** `UNFINISHED-BACKLOG-2026-07-28.md` (the pick-up-and-work list),
`INCOMPLETENESS-SCAN-2026-07-28.md` (raw sweep + real gate output).

---

## 1. Executive summary

The application code is, by a clear margin, the most finished part of this project — and the
project is much less finished than the application code makes it look. The mechanical sweep came
back remarkably clean: **zero** `pass`-only bodies, **zero** ellipsis bodies, **zero** `FIXME`,
**zero** frontend TODOs, **zero** no-op handlers, **zero** mocks on production paths, all 42
`NotImplementedError`s proven at runtime to be composition-root override points that are in fact
overridden, all 56 declared events emitted, all 13 schemas migrated with partitioning and 32
triggers, and all four locales complete at 796/796 keys. `ruff`, `mypy --strict`, `import-linter`
(49 contracts, 0 broken) and the migration-safety gate all pass, with 87.81% total coverage and no
domain/application file under the 90% floor. That is not a half-built codebase.

What is unfinished sits almost entirely *around* the code, and it is the part that decides whether
this ships. **The product cannot be installed**: migrations fail against a genuinely empty
database for all 13 modules, and there is no way to create the first administrator — both only
worked in prior testing because a human did them by hand. **It cannot be deployed**: there is no
CD pipeline, no staging, no `api`/`web`/`worker` container, no TLS, and nginx has no upstreams.
**It cannot be recovered**: there is no backup tooling and no tested restore, which is the single
control the availability argument rests on for a one-node deployment. Two documented security
mitigations — per-module DB roles, cited against threats T-4 and I-4 — are built, unit-tested
against a scratch schema, and then never provisioned, so a compromised module reads every schema.
And two quality gates are **red on `main` right now**: the full-stack E2E gate and the frontend
E2E gate, both of which are configured to run only on merge-to-main and therefore never blocked a
pull request. On top of that sit the functional defects the 2026-07-27 verification already
found, of which the `option_membership` blocker — which makes every `select` form field unusable —
is confirmed still present on this commit.

The honest summary: **the thirteen bounded contexts are largely done; the product around them is
not.** Roughly, backend domain logic is MOSTLY complete, the frontend is MOSTLY complete, and
foundation/infrastructure/operations is BARELY STARTED.

### Headline table

| Area | Rating | BLOCKER | MAJOR |
|---|---|---|---|
| Foundation (install, migrations, bootstrap, DI, backbone) | **PARTIAL** | 2 | 2 |
| M-01 Identity & Access | MOSTLY | 0 | 2 |
| M-02 Business Profiles & Verification | MOSTLY | 0 | 1 |
| M-03 Catalog & Listings | **PARTIAL** | 1 | 3 |
| M-04 Configuration & Metadata | MOSTLY | 0 | 0 |
| M-05 Search & Discovery | MOSTLY | 0 | 2 |
| M-06 Media | COMPLETE | 0 | 0 |
| M-07 Messaging & Contact | COMPLETE | 0 | 0 |
| M-08 Billing & Entitlements | COMPLETE | 0 | 0 |
| M-09 Moderation | COMPLETE | 0 | 0 |
| M-10 Notifications | MOSTLY | 0 | 0 |
| M-11 Ads / Banners | **PARTIAL (unverified)** | 0 | 0 |
| M-12 Administration | MOSTLY | 0 | 1 |
| M-13 Analytics & Audit | **PARTIAL** | 0 | 2 |
| Frontend (screens, flows, dynamic form, portals, i18n, a11y) | MOSTLY | 0 | 1 |
| Cross-cutting — platform/API behaviour | **PARTIAL** | 1 | 2 |
| Cross-cutting — security controls | **PARTIAL** | 0 | 1 |
| Cross-cutting — deployment & operations | **BARELY STARTED** | 0 | 4 |
| Cross-cutting — CI gates & traceability | MOSTLY | 0 | 2 |

**Totals: 3 BLOCKER, 18 MAJOR, 11 MINOR, 2 COSMETIC** across 34 items.

A note on M-11 Ads: it is rated PARTIAL **(unverified)** rather than COMPLETE because the
2026-07-27 verification never exercised the campaign lifecycle and this sweep found no evidence
either way. Under Rule 2, absence of evidence is unfinished-until-proven.

---

## 2. STARTED-BUT-NOT-DONE findings

Grouped by area. Full detail and "done when" criteria in the backlog.

### Foundation / platform
* **UNF-003 (BLOCKER)** — `composition_root`'s 13 session dependencies use `session_scope()` as a
  FastAPI `yield` dependency, so the commit lands in dependency teardown, after the response.
  8/10 immediate re-reads returned the previous value.
* **UNF-011 (MAJOR)** — `backbone/errors/middleware.py` re-raises after writing the Problem
  document, destroying the keep-alive connection: `['401','ReadError','401','ReadError']`.
* **UNF-018 (MAJOR)** — `backbone/outbox/dispatcher.py` moves failed events to `DEAD` with no
  retry, no replay and no alert; 32 rows stranded during a real outage.

### Catalog
* **UNF-002 (BLOCKER)** — `catalog/domain/policies.py:95` reads the allowed set from
  `spec.params["options"]`, but `FieldValidatorSpec` never carries the field's own `options`, so
  `option_membership` can never pass. Confirmed still present on `853d5a9`.
* **UNF-020 (MAJOR)** — attributes outside the bound form are accepted and persisted.
* **UNF-004 (MAJOR)** — `tests/integration/test_catalog_listing_to_search_index.py:155` calls
  `_listing_payload` without `await` after PR #26 made it async; QG-03b is red on `main`.

### Search / Analytics / Admin
* **UNF-017 (MAJOR)** — the `radiusKm` parameter is accepted and ignored.
* **UNF-021 (MAJOR)** — `NEWEST` is whitelisted and publishable but the API only accepts `RECENCY`.
* **UNF-016 (MAJOR)** — owner statistics return `null` counters.
* **UNF-019 (MAJOR)** — `/admin/dashboard` returns every field `null`.
* **UNF-030 (MINOR)** — operational reports enumerate 6 of the 8 closed metrics.

### Security / Infrastructure
* **UNF-006 (MAJOR)** — `schema_and_role_ddl()` exists and is tested against a *scratch* schema,
  but has **zero** production callers, **zero** migrations creating roles, and **zero** `ah_*`
  roles in a migrated database.
* **UNF-009 (MAJOR)** — `nginx.conf` carries `TODO(next infra task): TLS termination (443) +
  reverse-proxy upstreams`; it serves only `/healthz`, so the realtime WSS gateway has no edge route.
* **UNF-010 (MAJOR)** — compose ships no `api`/`web`/`worker` container; the nine workers have no
  container, restart policy or supervision.
* **UNF-031 (MINOR)** — per-module pools exhaust a default `max_connections=100`.

### Frontend
* **UNF-005 (MAJOR)** — QG-10b red on `main`: `/` resolves to `/en`, not the configured
  `/uz-Latn`. Red *before* this session's merges too.
* **UNF-023 (MINOR)** — `dynamic-form.tsx:128` honours only the full-width `renderingHint`; the
  other six whitelisted hints are inert.
* **UNF-034 (COSMETIC)** — two untranslated strings.

### Tooling / traceability
* **UNF-022 (MINOR)** — QG-06 prints 110 unimplemented operations when the real number is 3.
* **UNF-024 (MINOR)** — the `test_I<nn>` prefix collides between global and module-local
  invariants; the Domain Model's 1:1 traceability claim does not hold mechanically.
* **UNF-025 (MINOR)** — the `test_FR_*` convention is honoured by 2 of 89 FRs (known, P-20).
* **UNF-026 (MINOR)** — the NFR-PERF SLO benchmarks skip in CI for want of seeded data.
* **UNF-033 (COSMETIC)** — stale TODO in `scripts/coverage.sh:8`.

---

## 3. NEVER-STARTED findings (the holes)

Found by walking each document's required list and checking for a working, reachable
implementation — not by reading code.

### From the Infrastructure & Deployment Architecture / DevSecOps / DEC-16
* **UNF-007 (MAJOR) — no CD pipeline or staging deploy.** `.github/workflows/` contains only
  `ci.yml`; no deploy job, environment, image push or orchestration exists. `ci.yml:20` says so
  itself. The ETT's **AC-DEPLOY** acceptance dimension cannot be satisfied, and the merge-only
  E2E gates are documented to run "against staging (post-deploy)" — a contract that currently
  has no staging to run against.
* **UNF-008 (MAJOR) — no backups, no tested restore.** Zero references to `pg_dump`/`pg_restore`/
  backup/restore anywhere in `scripts/`, `deployment/` or `.github/`. Infra §13 requires
  PostgreSQL + MinIO + configuration backups; §9 leans on **tested restore** to justify 99.9% on
  a single node with RPO ≤ 15 min / RTO ≤ 4 h (NFR-BAK-001, NFR-REC-001). None of it exists.
* **UNF-001 (BLOCKER) — no fresh-database bring-up.** No `db-migrate.sh`/`db-seed.sh`
  (`scripts/README.md` admits this), and `alembic upgrade head` fails on all 13 modules against an
  empty database.

### From the Security Architecture
* **UNF-006 (MAJOR) — per-module DB roles (PD-06) never provisioned.** Documented as in place and
  relied upon by threat mitigations **T-4** and **I-4**, and by the workers' "run under per-module
  DB credentials". Counted as started-not-done above because the DDL helper exists; as a *control*
  it has never been started.

### From the SRS / contracts
* **UNF-014 (MAJOR) — FR-AUTH-002 acceptance (1)**: no endpoint anywhere redeems the confirmation
  token; accounts are `ACTIVE` at creation.
* **UNF-013 (MAJOR)** — `listTeamMembers` / `addTeamMember` / `removeTeamMember`: 3 frozen-contract
  operations with no implementing route (107 served of 110).
* **UNF-015 (MAJOR) — FR-ADV-010 / BC-03 ViewRecordingPolicy**: `ListingViewed` is in the closed
  vocabulary and is never emitted.
* **UNF-012 (MAJOR) — FR-ADMIN-006 unreachable on a fresh install**: no bootstrap for the first
  administrator (and maker–checker needs two).

### Checked and found genuinely present (no hole)
Recording these so the negative result is auditable:
* All **13** module schemas, with partitioning on `analytics.audit_entry`,
  `analytics.metric_event`, `notifications.notification`, and 32 triggers.
* All **56** contract events emitted; only `UserBlocked` is unconsumed, and that is deliberate
  (an explicit notifications test asserts it produces nothing).
* All **8** configuration entities exist on Head+Version with a working pre-activation gate,
  `WhitelistRegistry`, and maker–checker enforcement.
* All **42** DI override points are satisfied at runtime (41 by the API app, 1 by the realtime app).
* All **24** invariants have a real guard and at least one covering test (4 are not *named* for
  their invariant — UNF-024).
* All **four** locales complete (796/796), dual-script Uzbek as two distinct locales per DEC-19.
* `/health` and `/ready` exist and behave (`/ready` correctly returns 503 when a dependency is down).

---

## 4. Mechanical-sweep summary

| Sweep | Result |
|---|---|
| `TODO` / `FIXME` / `XXX` / `HACK` / `WIP` | 5 / 0 / 2 (both false positives) / 0 / 0 |
| "coming soon" / "not implemented" | 0 / 3 (all deliberate, documented) |
| `pass`-only bodies outside Protocol/ABC | **0** |
| `...` bodies outside Protocol/ABC | **0** |
| `raise NotImplementedError` bodies | 42 — all DI override points, **all overridden at runtime** |
| Swallowing `except: pass` | 1, deliberate and documented (`messaging/interfaces/ws.py:54`) |
| Frontend markers / no-op handlers / prod mocks | **0 / 0 / 0** |
| Locale keys | 796 in each of 4 locales; 0 missing, 0 empty |
| Events declared / never emitted / never consumed | 56 / **0** / 1 (deliberate) |
| Skipped tests | 124 (all `POSTGRES_HOST not set`), plus 2 seed-gated perf skips. No `xfail`, no unconditional skips |

### Gate results (real output, this commit)

| Gate | Result |
|---|---|
| QG-01 lint | PASS — 650 files formatted, all checks passed |
| QG-02 mypy --strict | PASS — no issues in 672 source files |
| QG-03 tests (live infra) | 1727 passed, 2 failed (1 environmental), 2 skipped |
| QG-04 coverage | PASS — **87.81%** total; no domain/application file below the 90% floor |
| QG-05 import-linter | PASS — 49 contracts kept, 0 broken |
| QG-06 contract drift | PASS (0 undocumented routes) — but misreports the unimplemented count |
| QG-07 security | PASS (was red at `e1ec08b`) |
| QG-09 migration safety | PASS |
| QG-10 frontend build/lint/test | PASS |
| **QG-03b full-stack E2E** | **FAIL** — `_listing_payload` never awaited |
| **QG-10b frontend E2E** | **FAIL** — default-locale redirect |

**The structural point:** both red gates carry `-- merge to main + nightly`, so neither runs on a
pull request. Two gates have been failing on `main` with nothing blocking merges. That is itself
an unfinished piece of the delivery system, independent of the two bugs.

---

## 5. Reconciliation with prior reports

Three prior report sets exist and were read: `docs/assessments/2026-07-24-audit/*-2026-07-24`,
`docs/assessments/2026-07-27-verification/*-2026-07-27`, and `docs/assessments/2026-07-24-acceptance/gap_report.md` (P-20).

**Already known, still true.** The verification report's three BLOCKERs all survive on this
commit. `option_membership` (UNF-002) was re-checked in source — `_check_option_membership` still
reads `spec.params["options"]` and `FieldValidatorSpec` still has no `options` field. Fresh-DB
migrations (UNF-001) and commit-after-response (UNF-003) are unchanged. The team endpoints, email
confirmation, `ListingViewed`, owner statistics, radius, outbox DEAD, first-admin bootstrap,
admin dashboard, keep-alive, unknown attributes and sort-vocabulary items all carry forward.

**Already known and now fixed.** `QG-07 security` was red on `main` at `e1ec08b` and is green at
`853d5a9`. The verification's DEF-011 (incomplete config draft returning 500) was addressed by
PR #26's `fix(config): saving an incomplete draft returned 500 instead of a gate error`, and
`configuration/test_use_cases.py::test_validate_reports_gate_errors_without_mutating_status`
covers the gate path; it is therefore **not** carried into this backlog.

**Previously reported as fine, now unfinished.** `docs/assessments/2026-07-24-acceptance/gap_report.md` records the
critical-journey and cross-module integration suites as passing at P-20. **QG-03b is now red**
(UNF-004): PR #26 made `_listing_payload` async without updating the integration test's call site.
This regression landed via the PR-#26 merge performed on 2026-07-27 in the preceding session, and
PR CI could not have caught it because QG-03b does not run on pull requests.

**Missed by all three prior reports — new in this sweep.** The infrastructure and operations
holes are the significant new material: no CD pipeline (UNF-007), no backups or tested restore
(UNF-008), per-module DB roles never provisioned (UNF-006), nginx without TLS or upstreams
(UNF-009), no application containers (UNF-010), and QG-10b red on `main` (UNF-005). The prior
gap report explicitly scoped infra out ("every one of the 11 [NFR gaps] is an infra/load-testing/
frontend concern explicitly out of scope for this task"), and the verification was behavioural, so
none of them walked the infrastructure document's required list. Also new: the QG-06 miscount
(UNF-022), the invariant-naming collision (UNF-024) and the never-running SLO benchmarks (UNF-026).

**Where I disagree with a prior report.** `gap_report.md` states "**89/89 FR ids** have a
plausible covering test … Zero FR ids came up with no covering test at all." That is a fair
statement about *test existence*, but it should not be read as coverage of acceptance criteria:
the 2026-07-27 verification exercised the running system and found FR-ADV-010, FR-MAP-003,
FR-ANALYTICS-002 and FR-AUTH-002(1) failing their stated acceptance criteria despite having
"covering" tests. Existence of a test is not evidence the criterion is met.

---

## 6. Prioritised backlog (summary)

Full entries in `UNFINISHED-BACKLOG-2026-07-28.md`.

* **BLOCKER (3):** UNF-001 fresh-DB bring-up · UNF-002 `option_membership` · UNF-003 commit-after-response.
* **MAJOR (18):** UNF-004 QG-03b · UNF-005 QG-10b · UNF-006 DB roles · UNF-007 CD · UNF-008
  backups · UNF-009 nginx · UNF-010 containers · UNF-011 keep-alive · UNF-012 first admin ·
  UNF-013 team ops · UNF-014 email confirmation · UNF-015 ListingViewed · UNF-016 owner stats ·
  UNF-017 radius · UNF-018 outbox DEAD · UNF-019 admin dashboard · UNF-020 unknown attributes ·
  UNF-021 sort vocabulary.
* **MINOR (11):** UNF-022 … UNF-032.
* **COSMETIC (2):** UNF-033, UNF-034.

---

## 7. Recommended completion order

Dependency-ordered. Each step unblocks the next.

**Step 1 — stop the bleeding on `main` (hours).** Fix UNF-004 (add the missing `await`) and
decide UNF-005 (locale default), then **make QG-03b and QG-10b run on pull requests**, or at
minimum alert on a red `main`. Until the merge-only gates block something, every later fix can
regress silently — which is exactly how UNF-004 got in. *Prompt: P-20 / new work.*

**Step 2 — make the product installable (days).** UNF-001 (schemas + roles + a migration runner,
with a CI job that migrates a genuinely empty database) then UNF-012 (first-administrator
bootstrap). Nothing downstream — deployment, restore drills, a staging environment — can be built
or tested until a clean install works. *Prompt: new work.*

**Step 3 — close the two BLOCKER behaviours (days).** UNF-002 (`option_membership`, which
currently makes the dynamic form engine's select fields unusable and undercuts the core
configurability story) and UNF-003 (commit inside the request boundary; this one change also
fixes the duplicate-registration 500 and removes a class of race). Do UNF-003 with care — it
touches all 13 modules' session wiring. *Prompt: P-07 / P-04 / new work.*

**Step 4 — restore the security posture (days).** UNF-006: provision `ah_<module>` roles in the
now-working bring-up, connect each service with its own credentials, and assert cross-schema
denial against the real database. This is step 4 rather than step 2 only because it rides on the
bring-up work; it is the highest-value *security* item, since two threat mitigations are
currently documented-but-absent. *Prompt: P-22.*

**Step 5 — deployability and recoverability (weeks).** UNF-010 (containers) → UNF-009 (nginx TLS
and upstreams) → UNF-007 (CD to staging) → UNF-008 (backups **and a rehearsed restore**). Order
matters: there is nothing to deploy until the containers exist, nowhere to deploy until CD
exists, and no honest availability claim until a restore has actually been performed. *Prompt: new work.*

**Step 6 — the remaining MAJOR functional gaps (days).** Group by module to avoid thrashing:
catalog (UNF-020), search (UNF-017, UNF-021), analytics (UNF-015 → UNF-016 → UNF-030, in that
order since statistics depend on the metric), platform (UNF-011, UNF-018), profiles (UNF-013),
identity (UNF-014), admin (UNF-019). *Prompts: P-07, P-08, P-22, P-15, P-05, P-14.*

**Step 7 — verification you can trust (days).** UNF-026 (seed and run the SLO benchmarks so
NFR-PERF is measured rather than assumed), UNF-024 and UNF-025 (make invariant and FR
traceability greppable), UNF-022 (fix the QG-06 miscount). These are MINOR individually but
together they are why the project's own reports have been able to look greener than the product
is. *Prompts: P-21, new work.*

**Step 8 — polish.** The remaining MINOR and COSMETIC items.

### What this report cannot tell you

M-11 Ads is unverified end to end — the campaign lifecycle has never been exercised by any prior
report or by this one, so its COMPLETE-looking code is unproven. Listing expiry, badge expiry and
entitlement expiry are all untested for the same reason (they need elapsed time), and they are the
class of feature that fails silently in production. And every quality gate here measures the
backend far more thoroughly than the frontend: there is one frontend E2E spec, and it is currently
failing.
