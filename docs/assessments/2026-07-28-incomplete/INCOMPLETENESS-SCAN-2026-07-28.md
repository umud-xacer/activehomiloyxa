# Active Home v1 — Raw Incompleteness Scan (2026-07-28)

Baseline: `origin/main` @ `853d5a9` (after PR #26 and PR #27 merged).
This file is the raw mechanical evidence. Interpretation lives in
`UNFINISHED-WORK-2026-07-28.md`; the actionable list lives in `UNFINISHED-BACKLOG-2026-07-28.md`.

---

## 1. Quality-gate commands — real output

Every command below was actually executed. Where the local environment could not satisfy a gate,
the CI result for the same commit is quoted instead and labelled as such.

| Gate | Command | Result |
|---|---|---|
| QG-01 lint | `bash scripts/lint.sh` | **PASS** — `650 files already formatted`, `All checks passed!` |
| QG-02 types | `bash scripts/typecheck.sh` | **PASS** — `Success: no issues found in 672 source files` |
| QG-03 tests (no infra) | `pytest -c tools/pytest.ini` | 1426 passed, **124 skipped**, **181 errors** — every error is `MissingInfraConfigError`; env-gated, not a code defect |
| QG-03/04 tests (with live infra) | `coverage run … pytest` | **1727 passed, 2 failed, 2 skipped**. 1 of the 2 failures is environmental (see §4) |
| QG-04 coverage | `coverage report` + `check_domain_coverage.py` | **TOTAL 87.81%** (floor 80) · `QG-04 OK: no domain/application file is below the 90% floor` |
| QG-05 architecture | `bash scripts/check-import-boundaries.sh` | **PASS** — `Contracts: 49 kept, 0 broken` |
| QG-06 API contract | `python tools/check_contract_drift.py` | **PASS** — `107 registered route(s) all exist` … but the printed count of unimplemented ops is wrong (§3, UNF-022) |
| — OpenAPI validity | `python tools/validate_openapi.py` | **PASS** — well-formed 3.1, every `$ref` resolves, no legacy `nullable:` |
| QG-07 security | CI job 90033624939 @ `ec6d993` | **PASS** (was failing on `main` @ `e1ec08b`; fixed by the gitleaks allowlist in PR #27) |
| QG-09 migrations | `python tools/check_migration_safety.py` | **PASS** — `no edited-applied migrations, no unmarked destructive operations` |
| QG-10 frontend | CI job @ `853d5a9` | **PASS** — build/lint/test |
| **QG-03b full-stack E2E** | CI run 30284100032 @ `853d5a9` | **FAIL** — `1 failed, 1728 passed, 2 skipped` |
| **QG-10b frontend E2E** | CI run 30284100032 @ `853d5a9` | **FAIL** — smoke spec, 3 attempts |

### The two red gates on `main`

Both are **merge-only** gates (`-- merge to main + nightly`), so neither runs on a pull request.
That is why both went unnoticed.

```
QG-03b: FAILED tests/integration/test_catalog_listing_to_search_index.py::
        test_a_real_listing_published_event_is_indexed_and_becomes_searchable
        pydantic_core.ValidationError: 1 validation error for ListingPublished
        payload  Input should be a valid dictionary
                 [input_value=<coroutine object Listing...yload>, input_type=coroutine]
        RuntimeWarning: coroutine 'ListingUseCases._listing_payload' was never awaited
        tests/integration/test_catalog_listing_to_search_index.py:149
```

```
QG-10b: ✘ e2e/smoke.spec.ts:4:1 › home page renders and redirects the default locale
        Error: expect(page).toHaveURL(expected) failed
        Expected pattern: /\/uz-Latn$/
        unexpected value  "http://127.0.0.1:3000/en"
        locator resolved to <html lang="en" dir="ltr">
```

Git evidence for the QG-03b regression:

```
main @ cb70221 (pre-merge):  def _listing_payload(self, listing, *, reason=None) -> dict[str, Any]:
main @ 853d5a9 (post-merge): async def _listing_payload(
tests/integration/test_catalog_listing_to_search_index.py:155
                             payload=use_cases._listing_payload(listing),   # no await
```

CI history confirms which gate was already red before the merges:

| Commit | Red gates |
|---|---|
| `e1ec08b` (before both merges) | QG-07 security · **QG-10b frontend E2E** |
| `a9deb50` (after PR #27) | QG-10b frontend E2E |
| `853d5a9` (after PR #26) | **QG-03b full-stack E2E** · QG-10b frontend E2E |

So **QG-10b was already failing before this session's merges**; **QG-03b was made red by PR #26**.

---

## 2. Marker sweep — whole repo (backend + frontend)

Excludes `node_modules`, `.next`, `__pycache__`, `.venv`, caches and `docs/`.

| Marker | Hits |
|---|---|
| `TODO` | 5 |
| `FIXME` | 0 |
| `XXX` | 2 (both false positives — the literal `FR-XXX-NNN` id pattern in prose) |
| `HACK` | 0 |
| `WIP` | 0 |
| `coming soon` | 0 |
| `not implemented` | 3 (all deliberate, documented absences) |
| `temporary` | 3 (2 in vendored OpenAPI prose, 1 `.gitignore` comment) |
| `for now` | 2 |

### Every TODO, with file:line

```
deployment/nginx/nginx.conf:28   # TODO(next infra task): TLS termination (443) + reverse-proxy
                                   upstreams for …
deployment/compose/docker-compose.yml:9    (cross-reference to the nginx TODO)
deployment/compose/docker-compose.yml:151  (cross-reference to the nginx TODO)
deployment/README.md:13          nginx skeleton "only a /healthz endpoint for now"
scripts/coverage.sh:8            # TODO: remove entirely once every module also has
                                   domain/application …
```

### "for now" / partial-implementation admissions

```
apps/frontend/src/shared/forms/dynamic-form.tsx:128
    // renderingHint"); only a full-width hint is honoured for now, and anything …
deployment/nginx/nginx.conf:4
    # TLS termination (Infra Sec 5), when the api/web containers exist. For now this proves …
```

### Deliberate, documented non-implementations (not accidental)

```
apps/backend/src/profiles/interfaces/routers.py:10
    listTeamMembers/addTeamMember/removeTeamMember are deliberately NOT implemented here
apps/backend/src/profiles/README.md:186   (same, with rationale)
apps/frontend/README.md:428   Notification deep-linking is not implemented, for want of
                              anything to link with
```

---

## 3. Python stub sweep (AST-based, not grep)

Ran over `apps/backend/src`, `packages/shared/src`, `contracts`, `tools`, classifying each
function body and excluding `Protocol`/`ABC` members.

| Pattern | Count outside Protocol/ABC |
|---|---|
| `raise NotImplementedError` as the whole body | **42** — all in `*/interfaces/di.py` |
| `...` (Ellipsis) as the whole body | **0** |
| `pass` as the whole body | **0** |
| `except …: pass` (swallowing) | **1** |

### The 42 `NotImplementedError` bodies are NOT stubs — verified at runtime

They are FastAPI composition-root override points (dependency inversion: `interfaces` never
imports `infrastructure`). Verified by importing the real apps and inspecting
`app.dependency_overrides`:

```
declared DI placeholders: 42
overridden by main app:   41
not overridden by main:    1  -> messaging.interfaces.di.get_message_subscriber
```

The one outlier is overridden by the **realtime** app, not the API app:

```
realtime_main.app.dependency_overrides -> ['get_acting_user',
                                           'get_conversation_use_cases',
                                           'get_message_subscriber']
```

**Conclusion: DI wiring is complete. 42/42 override points are satisfied. No finding.**

### The single swallowing `except`

`apps/backend/src/messaging/interfaces/ws.py:54` — deliberate and documented:
`_mark_delivered_best_effort` uses `contextlib.suppress` so a malformed frame cannot kill the
socket read loop. **No finding.**

---

## 4. Test-suite tells

* **124 skips** (no-infra run) — every one is conditional on `POSTGRES_HOST not set`, e.g.
  `SKIPPED [87] tests/authorization/test_no_route_grants_access.py:68: POSTGRES_HOST not set`.
  None are `xfail`, none are unconditional `skip`. **Not abandoned tests.**
* **2 skips** (with-infra run) — both are honest, actionable seed-gated skips:
  ```
  tests/performance/test_benchmark_search.py:77: no SearchConfiguration published --
      run `python -m tests.performance.seed_cli` first
  tests/performance/test_benchmark_write_path.py:78: no seeded data -- run … first
  ```
  Consequence: the NFR-PERF SLO benchmarks do **not** run in CI, so the performance targets are
  unverified (UNF-032).
* **No** `assert True`, no empty test files, no assertion-free tests were found.
* **Running the suite dirties the working tree.** The performance harness rewrites its own
  tracked baselines — after a full run, `git status` showed
  `M tests/performance/baseline_report_async_lag.json` and
  `M tests/performance/baseline_report_interactive.json`. (The same two files were already
  modified in the developer's checkout at the start of this session, so this is reproducible, not
  incidental.) A test run should not mutate tracked files; recorded as an observation rather than
  a numbered item because it is a harness-ergonomics issue, not unfinished product functionality.
  Both files were reverted here so this task modified nothing.
* Local run had a **second** failure that CI did not:
  `tests/e2e/test_critical_buyer_seller_journey.py` — `assert '…' in set()`.
  **Environmental, not a product defect**: the shared local OpenSearch had
  `"read_only_allow_delete": "true"` (host disk at 96%, flood-stage watermark), so nothing could
  be indexed. CI's clean run shows this test **passing** — only 1 failure there. Not reported as
  a finding.

---

## 5. Frontend sweep

| Check | Result |
|---|---|
| `TODO`/`FIXME`/`XXX`/`HACK`/`WIP`/"coming soon" in `src`, `e2e` | **0 hits** |
| No-op handlers (`onClick={() => {}}`, `href="#"`) | **0 hits** |
| MSW / mock usage outside tests | **0** — confined to `src/test/msw/*`, `src/test/setup.ts` and one `*.test.ts` |
| Hardcoded data in place of API data | none found |

### Locale completeness — all four locales

```
locale       keys  missing-vs-en  extra  empty  identical-to-en
en            796              0      0      0                0
ru            796              0      0      0               10
uz-Cyrl       796              0      0      0               14
uz-Latn       796              0      0      0               15
```

Every identical-to-English value was inspected. All are legitimate — brand name (`ActiveHome`),
loanwords used verbatim in Uzbek/Russian (`Email`, `SMS`, `JSON`), product-type proper nouns
(`Premium`, `Featured`), language endonyms (`Русский`, `English`), and a phone placeholder.
Only two look genuinely untranslated: `ru → company.userIdLabel = "User id"` and
`uz-Latn → business.portfolioHeading = "Portfolio"` (UNF-034, COSMETIC).

---

## 6. Wiring sweep

### Event catalogue (contracts/events)

```
declared events: 56
never referenced from an emitting site:  0
never referenced from a consuming site:  1  -> UserBlocked
```

`UserBlocked` is deliberately unconsumed — `notifications` has an explicit parametrised test
asserting it produces no notification
(`test_events_outside_the_subset_never_produce_a_notification[UserBlocked-…]`), and block
enforcement is synchronous in `messaging`. **No finding.**

### Database (a fully migrated database)

```
schemas: admin ads analytics billing catalog configuration identity media messaging
         moderation notifications profiles search  (13/13 + public)
partitioned tables: analytics.audit_entry, analytics.metric_event, notifications.notification
triggers: 32
per-module DB roles matching 'ah_%': 0        <-- see below
```

### Per-module DB roles (PD-06) — built but never provisioned

```
callers of schema_and_role_ddl() outside tests:  0   (only its own definition + re-export)
migrations containing CREATE ROLE / CREATE USER: 0
ah_* roles in a fully migrated database:         0
```

The helper `backbone/persistence/schema_role.py::schema_and_role_ddl()` exists and is proven by
`apps/backend/tests/backbone/integration/test_schema_role_convention.py` — but only against a
**scratch** schema/role created by the test itself. Nothing in the real migration or bring-up
path ever calls it (UNF-006).

### Contract coverage

```
app routes:                       107
spec operations:                  110
intersection:                     107
registered-but-undocumented:        0
documented-but-unimplemented:       3  -> listTeamMembers, addTeamMember, removeTeamMember
```

Note the gate prints `110 operation(s) not yet implemented` because it reports
`len(spec_routes)` instead of `len(spec_routes - app_routes)` (UNF-022).

---

## 7. Deployment / operations sweep

```
.github/workflows/           ci.yml            (the only workflow)
ci.yml jobs:  qg01-lint qg02-typecheck qg05-architecture qg03-tests qg03b-full-stack-e2e
              qg04-coverage qg06-api-contract qg07-security qg08-authorization-matrix
              qg09-migration-safety qg10-frontend qg10b-frontend-e2e
deploy / staging / registry / kubectl / helm steps:  none
pg_dump | pg_restore | backup | restore in scripts/, deployment/, .github/:  0 files
```

`ci.yml` states the gap in its own comments:

```
.github/workflows/ci.yml:20   No CD pipeline / staging deploy exists yet in this repo
                              (only ci.yml), so …
.github/workflows/ci.yml:113  … (no CD/staging deploy exists yet).
```

`deployment/compose/docker-compose.yml` likewise admits its own gap: it contains **no `api`,
`web` or `worker` service** — only the datastores, `realtime`, and an nginx that serves a static
`/healthz`.

---

## 8. Invariant traceability sweep (I-01 … I-24)

For each invariant, the owning bounded context was taken from the Domain Model §9 table, then its
module's test tree was searched for a `test_I<nn>_*` name.

| Result | Invariants |
|---|---|
| Named test present in the owning module | I-01, I-03, I-04, I-05, I-06, I-07, I-08, I-10, I-12, I-13, I-14, I-15, I-16, I-19, I-20, I-21, I-22, I-23, I-24 (19) |
| **No `test_I<nn>_*` in the owning module** | **I-09, I-11, I-17, I-18** (4) |
| Name resolves to a *different* module's local invariant | I-02 (configuration's `test_I22_…` matched; search/notifications/shared_kernel each renumber from I-01) |

All four of the unnamed ones **are** covered, by ordinarily-named tests — sometimes in a
different module:

* **I-09** (phone/email uniqueness) → `identity/test_models.py::test_user_account_has_partial_unique_indexes_on_phone_and_email`, `test_auth_use_cases.py::test_register_email_duplicate_raises`
* **I-11** (roles from the fixed catalogue) → `configuration/test_whitelist.py`, `test_gate.py::test_role_definition_missing_permission_group_dependency_refused`
* **I-17** (promoted labelled + capped) → search's *local* `test_I02_drops_all_promoted_candidates_when_cap_is_zero`, `test_I08_negative_cap_raises_invalid_promotion_cap_error`
* **I-18** (phone reveal per PrivacySettings) → `identity/test_public_port_adapters.py::test_reveal_phone_returns_the_number_when_mode_permits` / `…_returns_none_when_mode_is_never` / `…_unknown_account_fails_closed`

So there is **no missing guard** — but the Domain Model's claim that "§9's I-01…I-24 map 1:1 to
test names … giving reviewers a traceable checklist" does not hold mechanically, because module
suites reuse the `I<nn>` prefix for their own local invariants. The doc's own worked example,
`test_I08_quota_exceeded_refused`, does not exist; the real test is
`test_I08_quota_exceeded_blocks_creation`. Recorded as UNF-024 (MINOR, traceability).
