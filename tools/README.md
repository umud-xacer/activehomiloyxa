# tools/

Quality-gate machinery (Playbook Sec 2, Sec 16). Nothing here is business logic; this directory
is the CI-enforcement backbone. Prefer the wrapper scripts in `scripts/` over invoking these
directly -- they set the right working directory and flags.

| File | Gate | Purpose |
|---|---|---|
| `ruff.toml` | QG-01 | Lint + format config |
| `mypy.ini` | QG-02 | `mypy --strict` config |
| `pytest.ini` | QG-03 | Test discovery + markers |
| `coverage.ini` | QG-04 | Overall 80% floor (`fail_under`) |
| `check_domain_coverage.py` | QG-04 | The stricter 90% domain/application floor (COV-01), computed from `coverage.json` since coverage.py alone cannot express two different floors for different directories |
| `importlinter.cfg` | QG-05 | The full static import matrix (SAD Sec 8.1) as enforceable contracts |
| `security/bandit.yaml` | QG-07 (SAST) | Python security linting |
| `security/gitleaks.toml` | QG-07 (secret scan) | Committed-secret detection |

## `importlinter.cfg`

Encodes, module by module: (1) the allowed-imports table (SAD Sec 8.1) as `forbidden`
contracts -- both "may not import this other module at all" and "may only import that other
module's `interfaces/` package, never its `domain/application/infrastructure`" (AIR-02); (2) the
inward-only Clean Architecture layering inside each module (`interfaces -> application ->
domain`) as `layers` contracts; (3) that nothing may import a module's `infrastructure/` package
except that module itself (DIP -- infrastructure is wired at the composition root, never
statically imported); (4) that `domain/` imports no framework/ORM/provider SDK (Playbook Sec 6);
(5) that provider/datastore SDK types (SQLAlchemy, Redis, boto3, opensearch-py, ...) never cross
into `interfaces/`/`application/` (DEC-18); (5b) that the web framework itself (FastAPI/Starlette)
is confined to `interfaces/` -- `application/` stays framework-agnostic (SAD Sec 7.1 draws
`interfaces/` as "HTTP routers · published ports · DTOs"; Sec 10's sequence diagram labels it
"interfaces/ (router + authz)") -- kept as a separate contract from (5) because FastAPI is the
fixed delivery framework every module's `interfaces/` is built with, not a swappable provider;
(6) named defense-in-depth contracts for the invariants the docs call out explicitly by name: the
billing<->catalog/profiles/ads cycle (AIR-10), configuration's leaf-free hub status, search's
`{shared_kernel, configuration}`-only scope, and the admin/analytics/notifications sink rule.

Acyclicity of the whole graph is *not* asserted as its own contract: it falls out automatically
once every per-module allow-list contract holds simultaneously, because the allowed edges (SAD
Sec 8.1) form a fixed DAG rooted at `shared_kernel` -- there is no way to satisfy all of them and
still have a cycle. Run `lint-imports --config tools/importlinter.cfg` from `apps/backend/` (or
via `scripts/check-import-boundaries.sh`, which sets `PYTHONPATH=apps/backend/src` correctly).

Changing this file is an architecture event (Playbook Sec 2 "contracts/... changed only through
the interface-change process"; here read as: changing the *matrix itself* needs an ADR amending
SAD Sec 8, per COMPLY-01 -- fixing a bug in how the matrix is *encoded* does not).
