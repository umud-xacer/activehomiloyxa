# Active Home

Configuration-driven advertising/lead-generation marketplace for the housing & construction
sector in Uzbekistan (B2C + B2B). See `CLAUDE.md` for the full working context and `docs/` for
the approved architecture/requirements documents -- those documents are the source of truth;
this README is an entry point, not a substitute for them.

**Repository state**: toolchain scaffolded (P-00), contracts frozen (P-01), shared kernel (P-02),
the persistence/outbox/migration/error-envelope/logging backbone (P-03), the configuration module
(P-04, BC-04), the identity module (P-05, BC-01: accounts, phone-OTP/email/Google auth,
server-side sessions, the multi-profile acting-context, and the default-deny
`AuthorizationService` every later module's own authorization will be tested against), and the
media module (P-06, BC-06: presigned direct-to-MinIO image upload, an async intake worker
[malware scan, EXIF/GPS strip, thumbnail/optimized variants], opaque delivery references, and
asset-status events) are implemented. Every other business module (catalog, profiles, ...) is
still interface stubs only.
See each `apps/backend/src/<module>/README.md` for that module's charter, and
`apps/backend/src/backbone/README.md` for the shared infrastructure layer they all build on.

## Layout

```
apps/backend/    FastAPI modular monolith -- 13 bounded-context modules under src/<module>/,
                 plus src/shared_kernel/ (DDD value objects, P-02) and src/backbone/ (shared
                 persistence/outbox/migration/error/logging infrastructure, P-03)
apps/frontend/   Next.js app (placeholder -- not scaffolded yet)
packages/shared/ cross-cutting, business-logic-free utilities (placeholder)
contracts/       FROZEN openapi.yaml/event schema/interface stubs (P-01)
deployment/      Docker Compose datastore topology, nginx config, env templates
docs/            the approved architecture/requirements documents (read-only; ADR-only changes)
scripts/         idempotent dev/build/quality-gate helpers
tests/           cross-module integration/API/e2e suites -- seeded with the authorization
                 allow/deny matrix harness (P-05); the next suite arrives with the first task
                 spanning two or more modules' own interfaces
tools/           ruff/mypy/pytest/coverage config, import-linter contracts, security scanners
```

## Governing documents

Read `CLAUDE.md` first, then the specific `docs/*.docx` it points you to for the task at hand.
The **AI-Assisted Development & Engineering Playbook** is the binding day-to-day engineering
standard (repo layout, naming, quality gates, ADR process).

## Getting started

```bash
scripts/dev-install.sh   # create .venv, install pinned tooling + both Python packages editable
scripts/dev-up.sh        # start PostgreSQL/Redis/OpenSearch/MinIO/nginx (deployment/compose)
scripts/lint.sh          # QG-01
scripts/typecheck.sh     # QG-02
scripts/check-import-boundaries.sh  # QG-05
scripts/test.sh          # QG-03
scripts/coverage.sh      # QG-04
scripts/security-scan.sh # QG-07
```

All ten quality gates (QG-01..QG-10, Playbook Sec 16) run in CI on every PR
(`.github/workflows/ci.yml`) and are required, non-bypassable status checks on `main`.

## Contributing

Trunk-based, PR-gated (`feature/<module>-<short-desc>` branches); every quality gate must be
green; no self-merge. See the Playbook Sec 9 (Branching Strategy) and Sec 10 (Code Review
Standards). When a task appears to need something not in the approved documents -- a new
endpoint shape, a new cross-module dependency, a hardcoded configurable value -- stop and
surface it; it is an architecture decision (ADR), not a workaround (Playbook AIR-19).
