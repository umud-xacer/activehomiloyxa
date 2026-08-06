# tests/

Cross-module integration, API-contract, and end-to-end suites (Playbook Sec 2). Module-local
unit and integration tests live beside their module instead: `apps/backend/tests/` (mirroring
`apps/backend/src/<module>/`) and `packages/shared/tests/`.

STATUS (Task P-20): all thirteen modules are implemented (P-04..P-16); this task builds the
cross-cutting suites that prove they work together as one system, per-directory:

- `authorization/` -- the consolidated allow/deny matrix (QG-08, TEST-02). `matrix.py` is the
  reusable harness first built in P-05 (`AuthorizationScenario` + `run_authorization_matrix`,
  driving `identity.domain.AuthorizationService.authorize` directly); `test_matrix.py` runs every
  module's contributed scenario list, PLUS a self-check that greps `composition_root.py` for
  every literal permission key ever passed to `AuthorizationService.authorize` and fails if any
  isn't covered by a scenario. `test_configuration_admin_default_deny.py` covers the OTHER
  permission-key family (`config:*:manage`/`config:*:approve`, checked by a different,
  header-based mechanism -- see its own module docstring for why). `test_no_route_grants_access.py`
  is the mechanical, contract-driven sweep: every `contracts/openapi.yaml` operation NOT marked
  `security: []` must reject a request carrying no session at all, derived from the frozen
  contract itself rather than a hand-kept endpoint list.
- `integration/` -- cross-module eventual-consistency assertions, each with a bounded, explicit
  async wait (SAD Sec 9/19: eventual consistency, never assumed-synchronous).
- `degradation/` -- the documented fallback paths (OpenSearch down, media processing lag, a slow
  async consumer) -- all three are requirements, not resilience nice-to-haves.
- `idempotency/` -- outbox-replay-produces-no-duplicate-side-effects, system-wide.
- `e2e/` -- the critical cross-module journey (register -> ... -> entitlement -> promoted in
  search -> metrics visible), plus its localized/cross-script variants.
- `acceptance/` -- the acceptance-pack mapping (every SRS FR/TC-* id and ETT AC-* dimension to its
  covering test), and the gap report it's built from.
- `performance/` (Task P-21) -- the NFR-PERF-001/002 benchmark harness: seeds a synthetic dataset
  through real use cases, drives a REAL `uvicorn` subprocess with real HTTP requests, reports
  p50/p95/p99 per operation against the documented targets. See `performance/README.md` for how
  to run it and its own disclosed environmental limitations.

## Conventions (Playbook Sec 5, Sec 11)

- Invariant tests: `test_I<nn>_<description>` (DDD invariants I-01...I-24).
- Requirement-traced tests: include the FR/NFR/BRULE id, e.g. `test_FR_ADV_002_max_ten_images`.
- End-to-end suites cover the critical user journeys named in Playbook Sec 11: register -> create
  listing -> publish -> search -> message -> purchase -> confirm-payment -> entitlement, plus
  degradation paths (search fallback, non-blocking media).
- Synthetic data only, never real PII or secrets (TEST-01, AIR-16).
- The authorization matrix suite (allow/deny per permission key + ownership) is release-blocking
  (TEST-02, QG-08).
- `integration/`/`degradation/`/`e2e/` need real PostgreSQL/Redis (all) and, for `e2e/` and the
  search/media-touching parts of `integration/`/`degradation/`, real OpenSearch/MinIO too
  (`scripts/dev-up.sh`) -- each suite's own `conftest.py` skips gracefully when the datastore
  it needs isn't reachable, mirroring every module-local `integration/` suite's own convention.
- CI (`.github/workflows/ci.yml`): `qg08-authorization-matrix` now runs `tests/authorization/`
  against real Postgres/Redis service containers (no longer silently skips). A new
  `qg03b-full-stack-e2e` job runs the whole suite again with OpenSearch + a manually-started
  MinIO container (GitHub Actions `services:` entries can't override a container's command,
  which `minio/minio` needs), gated to push-to-main and a nightly `schedule:` trigger rather than
  every PR (DevSecOps' own End-to-end cadence, "on merge to main ... ; nightly") -- this
  approximates that cadence with ephemeral CI containers since no CD/staging deploy exists yet
  to run the doc's literal "against staging" model against.
